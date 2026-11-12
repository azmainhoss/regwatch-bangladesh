import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.core.logging import logger
import backend.app.database.models  # Ensure all models are registered in SQLAlchemy mapper registry
from backend.app.modules.documents.models import Document, DocumentVersion
from backend.app.modules.documents.service import document_ingestion_service
from backend.app.modules.institutions.models import Institution, InstitutionDepartment
from backend.app.modules.sources.connector.bangladesh_bank import BangladeshBankConnector
from backend.app.modules.sources.connector.base import BaseSourceConnector, ListingOutcome
from backend.app.modules.sources.models import Source, SourceDiscovery, SourceRun
from backend.app.modules.sources.url_policy import DisallowedSourceURL, validate_source_url

# Bot checks on a file download mean the whole site is refusing us: stop and back off.
SITE_BLOCK_TYPES = ("IMPERVA_TSPD_CAPTCHA", "CLOUDFLARE_CHALLENGE", "RATE_LIMIT_429")


def backoff_minutes(consecutive_failures: int) -> int:
    """Minutes to wait after this many failed checks in a row.
    One failure: no extra wait (the next scheduled check is the retry).
    Two: 30 min, then doubling, never more than 6 h (both configurable)."""
    if consecutive_failures < 2:
        return 0
    start = settings.BB_BACKOFF_START_MINUTES
    return min(start * 2 ** (consecutive_failures - 2), settings.BB_BACKOFF_MAX_MINUTES)


def source_retry_after(source: Source) -> Optional[datetime]:
    raw = (source.config or {}).get("retry_after")
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def source_in_backoff(source: Source, now: Optional[datetime] = None) -> bool:
    retry_after = source_retry_after(source)
    return bool(retry_after and (now or datetime.now(timezone.utc)) < retry_after)


def _note_failure(source: Source, reason: str) -> None:
    config = dict(source.config or {})
    failures = int(config.get("consecutive_failures", 0)) + 1
    config["consecutive_failures"] = failures
    wait = backoff_minutes(failures)
    if wait:
        config["retry_after"] = (datetime.now(timezone.utc) + timedelta(minutes=wait)).isoformat()
        logger.warning(f"Source '{source.name}': {failures} failed checks in a row, backing off {wait} min ({reason}).")
    else:
        config.pop("retry_after", None)
    source.config = config  # reassign so the JSON change is saved


def _note_success(source: Source) -> None:
    config = dict(source.config or {})
    if config.get("consecutive_failures") or config.get("retry_after"):
        config.pop("consecutive_failures", None)
        config.pop("retry_after", None)
        source.config = config


class SourceMonitoringService:
    # Discoveries in these states have already been handled and must not be re-ingested.
    NON_APPROVABLE_STATUSES = ("REJECTED", "INGESTED", "DOWNLOADED")

    def __init__(self):
        self._crawler_lock = asyncio.Lock()

    @staticmethod
    def get_connector_for_source(source: Source) -> BaseSourceConnector:
        # Extensible connector factory
        return BangladeshBankConnector(base_url=source.base_url)

    @staticmethod
    def _scope_to_source(query, source_id: UUID):
        """Restrict a SourceDiscovery query to discoveries made by one source."""
        return query.join(SourceRun, SourceDiscovery.source_run_id == SourceRun.id).where(
            SourceRun.source_id == source_id
        )

    async def execute_source_monitoring(
        self,
        db: AsyncSession,
        source_id: UUID,
        run_type: str = "SCHEDULED_POLL",
        mode: str = "poll",
    ) -> SourceRun:
        """
        Executes a continuous monitoring cycle:
        1. Runs the listing check (mode "poll": last 7 days by date filter; "reconcile": full list).
        2. Downloads and ingests the newest discoveries (paced, one request at a time).
        3. Updates audit logs and source health metrics.
        """
        run = await self.execute_discovery_scan(db=db, source_id=source_id, run_type=run_type, mode=mode)
        if run.status == "COMPLETED":
            # Automatically ingest newly discovered circulars or steadily drain the pending queue
            batch_count = min(run.valid_documents_discovered, 5) if run.valid_documents_discovered > 0 else 5
            try:
                backfill_res = await self.execute_backfill_batch(
                    db=db,
                    source_id=source_id,
                    batch_size=batch_count
                )
                if backfill_res.get("successful", 0) > 0:
                    logger.info(f"Auto-ingested {backfill_res.get('successful', 0)} circulars during monitoring poll.")
                    run.downloaded_count = backfill_res.get("successful", 0)
                    run.downloads_successful = backfill_res.get("successful", 0)
                    await db.commit()
            except Exception as e:
                logger.error(f"Error auto-ingesting circulars during monitoring poll: {e}")
            # The backfill may have rolled back the session; reload the run before returning it.
            await db.refresh(run)
        return run

    async def execute_discovery_scan(
        self,
        db: AsyncSession,
        source_id: UUID,
        run_type: str = "DISCOVERY_SCAN",
        mode: str = "poll",
    ) -> SourceRun:
        """
        Discovers and catalogs publications from the official source into the SourceDiscovery registry.
        """
        source = await db.get(Source, source_id)
        if not source:
            raise ValueError(f"Source with ID {source_id} does not exist.")

        now = datetime.now(timezone.utc)
        source.last_attempted_run_at = now

        run = SourceRun(
            source_id=source.id,
            run_type=run_type,
            status="STARTED",
            started_at=now
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        logger.info(f"Executing discovery scan for '{source.name}' (Run ID: {run.id})...")
        run_id = run.id

        try:
            connector = self.get_connector_for_source(source)
            # Hold the lock across fetch and dedupe so two scans cannot insert the same URL.
            async with self._crawler_lock:
                discovery_result = await connector.discover_publications(max_pages=1, mode=mode)
                return await self._record_discovery_result(db, source, run, discovery_result)
        except Exception as e:
            logger.error(f"Error during discovery scan {run_id}: {e}")
            await db.rollback()
            run = await db.get(SourceRun, run_id)
            source = await db.get(Source, source_id)
            run.status = "FAILED_RETRY"
            run.error_count += 1
            run.error_log = str(e)
            run.completed_at = datetime.now(timezone.utc)
            source.last_error = str(e)
            _note_failure(source, str(e))
            await db.commit()
            await db.refresh(run)
            return run

    async def _record_discovery_result(self, db: AsyncSession, source: Source, run: SourceRun, discovery_result) -> SourceRun:
        """Stores the candidates found by a listing check. Called while holding the crawler lock."""
        now = datetime.now(timezone.utc)
        outcome = getattr(discovery_result, "outcome", ListingOutcome.OK)
        run.outcome = outcome.value
        run.pages_inspected = discovery_result.pages_inspected
        run.candidate_links_discovered = len(discovery_result.candidate_publications)
        source.last_checked_at = now

        # Anything but a clean table is "failed, try later", never "nothing new".
        if outcome != ListingOutcome.OK:
            details = "; ".join(discovery_result.errors) or outcome.value
            run.status = "FAILED_RETRY"
            run.error_count += 1
            run.error_log = f"{outcome.value}: {details}"
            run.completed_at = now
            ch = discovery_result.anti_bot_challenge
            if ch:
                run.access_restricted = True
                run.access_restriction_details = ch.model_dump()
                source.access_restriction_status = ch.challenge_type or "RESTRICTED"
            source.last_error = run.error_log
            _note_failure(source, run.error_log)
            await db.commit()
            await db.refresh(run)
            logger.warning(f"Source run {run.id} failed ({outcome.value}); will retry: {details}")
            return run

        # Dedupe key: the PDF URL, per source. Parsed rows are compared, never raw HTML.
        existing_urls_q = await db.execute(
            self._scope_to_source(select(SourceDiscovery.file_url), source.id)
        )
        existing_urls = {u for u in existing_urls_q.scalars().all() if u}

        new_discoveries = []
        for cand in discovery_result.candidate_publications:
            if not cand.file_url:
                continue
            if cand.file_url in existing_urls:
                run.duplicate_count += 1
                continue
            existing_urls.add(cand.file_url)
            run.valid_documents_discovered += 1
            new_discoveries.append(SourceDiscovery(
                source_run_id=run.id,
                source_url=cand.detail_url,
                file_url=cand.file_url,
                title=cand.title,
                department_code=cand.department_code,
                reference_number=cand.reference_number,
                publication_date=cand.publication_date,
                language=cand.language,
                publication_type=cand.publication_type or "CIRCULAR",
                discovered_metadata=cand.metadata,
                status="VALIDATED",
            ))

        if new_discoveries:
            db.add_all(new_discoveries)
            source.last_discovered_publication_at = now

        run.discovered_count = run.valid_documents_discovered
        run.status = "COMPLETED"
        run.completed_at = now
        source.access_restriction_status = "CLEAR"
        source.last_successful_run_at = now
        source.last_error = None
        _note_success(source)

        await db.commit()
        await db.refresh(run)
        logger.info(f"Discovery scan {run.id} completed: {run.valid_documents_discovered} new, {run.duplicate_count} already known.")
        return run

    async def execute_backfill_batch(
        self,
        db: AsyncSession,
        source_id: UUID,
        batch_size: int = 10,
        department: Optional[str] = None,
        year: Optional[int] = None,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes a batch collection and ingestion of discovered candidates into the repository.
        """
        source = await db.get(Source, source_id)
        if not source:
            raise ValueError(f"Source with ID {source_id} does not exist.")

        # Build query for eligible candidates
        query = self._scope_to_source(select(SourceDiscovery), source_id).where(
            SourceDiscovery.status.in_(["VALIDATED", "DISCOVERED", "DOWNLOAD_PENDING", "FAILED"]),
            SourceDiscovery.retry_count < 3
        )

        if department:
            query = query.where(SourceDiscovery.department_code == department.upper())
        if language:
            query = query.where(SourceDiscovery.language.ilike(f"%{language}%"))
        if year:
            query = query.where(func.extract('year', SourceDiscovery.publication_date) == year)

        # Order by newest publication date first
        query = query.order_by(SourceDiscovery.publication_date.desc().nullslast()).limit(batch_size)

        result = await db.execute(query)
        candidates = result.scalars().all()

        if not candidates:
            return {
                "status": "COMPLETED",
                "message": "No eligible pending candidates matching criteria.",
                "attempted": 0,
                "successful": 0,
                "duplicates": 0,
                "failed": 0,
                "ingested_documents": []
            }

        # Cache department mapping
        dept_result = await db.execute(
            select(InstitutionDepartment).where(InstitutionDepartment.institution_id == source.institution_id)
        )
        depts_by_code = {d.code: d.id for d in dept_result.scalars().all()}

        source_institution_id = source.institution_id
        connector = self.get_connector_for_source(source)
        successful = 0
        duplicates = 0
        failed = 0
        skipped = 0
        ingested_items = []

        # The connector paces every request (one at a time, BB_REQUEST_INTERVAL_SECONDS apart).
        async with self._crawler_lock:
            candidate_ids = [c.id for c in candidates]
            for disc_id in candidate_ids:
                disc = await db.get(SourceDiscovery, disc_id)
                if disc is None:
                    continue
                disc.last_attempted_at = datetime.now(timezone.utc)
                try:
                    fetched = await connector.fetch_document(disc.file_url or disc.source_url)
                    challenge = fetched.challenge

                    if fetched.rejected:
                        # One refused file is not a block: note it and carry on with the next one.
                        disc.status = "SKIPPED_REJECTED"
                        disc.error_message = challenge.details
                        skipped += 1
                        await db.commit()
                        continue

                    if challenge and challenge.challenge_type in SITE_BLOCK_TYPES:
                        # The site is refusing us: leave the file queued, stop, and back off.
                        disc.status = "DOWNLOAD_PENDING"
                        disc.error_message = challenge.details
                        source = await db.get(Source, source_id)
                        source.access_restriction_status = challenge.challenge_type
                        source.last_error = challenge.details
                        _note_failure(source, challenge.details)
                        failed += 1
                        await db.commit()
                        break

                    if challenge:
                        disc.status = "FAILED"
                        disc.retry_count += 1
                        disc.error_message = challenge.details
                        failed += 1
                        await db.commit()
                        continue

                    pdf_bytes = fetched.content
                    if not pdf_bytes:
                        disc.status = "FAILED"
                        disc.retry_count += 1
                        disc.error_message = "Empty payload received from source."
                        failed += 1
                        await db.commit()
                        continue

                    disc.etag = fetched.etag
                    disc.last_modified = fetched.last_modified
                    disc.fetched_at = fetched.fetched_at

                    # Same file already in the repository: record it as a duplicate, do not re-ingest.
                    file_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
                    existing_version = (await db.execute(
                        select(DocumentVersion)
                        .join(Document, Document.id == DocumentVersion.document_id)
                        .where(DocumentVersion.file_sha256 == file_sha256, Document.owner_user_id.is_(None))
                        .limit(1)
                    )).scalars().first()
                    if existing_version is not None:
                        disc.status = "DUPLICATE"
                        disc.document_id = existing_version.document_id
                        disc.file_hash = file_sha256
                        disc.file_size = len(pdf_bytes)
                        disc.error_message = None
                        duplicates += 1
                        await db.commit()
                        continue

                    # Ingest document into repository
                    dept_id = depts_by_code.get(disc.department_code) if disc.department_code else None

                    doc, version, page_count = await document_ingestion_service.ingest_document(
                        db=db,
                        pdf_bytes=pdf_bytes,
                        institution_id=source_institution_id,
                        department_id=dept_id,
                        reference_number=disc.reference_number,
                        title=disc.title or "Official Circular",
                        publication_date=disc.publication_date or datetime.now(timezone.utc).date(),
                        source_url=disc.file_url or disc.source_url,
                        document_type=disc.publication_type or "CIRCULAR",
                        language=disc.language,
                        etag=fetched.etag,
                        last_modified=fetched.last_modified,
                        fetched_at=fetched.fetched_at,
                    )

                    # Mark as honest machine-processed publication
                    doc.publication_status = "PUBLISHED_MACHINE_PROCESSED"

                    disc = await db.get(SourceDiscovery, disc_id)
                    disc.status = "INGESTED"
                    disc.document_id = doc.id
                    disc.file_hash = version.file_sha256
                    disc.file_size = version.file_size_bytes
                    disc.etag = fetched.etag
                    disc.last_modified = fetched.last_modified
                    disc.fetched_at = fetched.fetched_at
                    disc.error_message = None
                    successful += 1

                    ingested_items.append({
                        "document_id": str(doc.id),
                        "reference_number": doc.reference_number,
                        "title": doc.title,
                        "department": disc.department_code,
                        "publication_date": str(doc.publication_date),
                        "page_count": page_count,
                        "file_size_bytes": version.file_size_bytes,
                        "file_sha256": version.file_sha256,
                        "language": version.language
                    })

                    await db.commit()

                    # Automatically trigger AI Regulatory Intelligence pipeline
                    try:
                        from backend.app.modules.analysis.service import AnalysisService
                        await AnalysisService.analyze_document_version(
                            db=db,
                            document_id=doc.id
                        )
                        logger.info(f"Auto-analysis successfully executed for {doc.reference_number} ({doc.id})")
                    except Exception as analysis_err:
                        logger.warning(f"Auto-analysis deferred for {doc.reference_number}: {analysis_err}")

                    import gc
                    gc.collect()

                except Exception as e:
                    logger.error(f"Error ingesting discovery {disc_id}: {e}")
                    # Throw away any half-written document rows before recording the failure.
                    await db.rollback()
                    disc = await db.get(SourceDiscovery, disc_id)
                    if disc is not None:
                        disc.status = "FAILED"
                        disc.retry_count += 1
                        disc.last_attempted_at = datetime.now(timezone.utc)
                        disc.error_message = str(e)
                        await db.commit()
                    failed += 1

        return {
            "status": "COMPLETED",
            "message": f"Successfully ingested {successful} circular(s) into repository.",
            "attempted": len(candidates),
            "successful": successful,
            "duplicates": duplicates,
            "failed": failed,
            "skipped_rejected": skipped,
            "ingested_documents": ingested_items
        }

    async def recheck_archive(self, db: AsyncSession, connector: Optional[BaseSourceConnector] = None) -> Dict[str, Any]:
        """
        Weekly check for silently replaced files (DECISIONS.md 5).

        For every CURRENT version (each language variant has its own) of a shared-library
        document that came from bb.org.bd:
        HEAD the PDF; if its ETag or Last-Modified changed, download it. A different SHA-256
        becomes a new version of the same document (the old one is kept, marked SUPERSEDED);
        the same SHA-256 only refreshes the stored headers. A version with no stored headers
        yet just records them. Private uploads (owner_user_id set) are never rechecked.
        Every request goes through the same pace and lock as the new-circular check.
        """
        connector = connector or BangladeshBankConnector()
        rows = (await db.execute(
            select(DocumentVersion.id, Document.id, func.coalesce(DocumentVersion.source_url, Document.source_url))
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.owner_user_id.is_(None),
                Document.is_synthetic_fixture.is_(False),
                DocumentVersion.status == "CURRENT",
            )
            .order_by(Document.publication_date.desc())
        )).all()

        summary = {"checked": 0, "unchanged": 0, "baselined": 0, "same_file": 0, "new_versions": 0,
                   "skipped_rejected": 0, "errors": 0, "stopped": None}
        for version_id, doc_id, url in rows:
            if not url:
                continue
            try:
                url = validate_source_url(url, upgrade_http=True)
            except DisallowedSourceURL:
                continue

            async with self._crawler_lock:
                head = await connector.head_document(url)
            summary["checked"] += 1
            if head.challenge:
                if head.challenge.challenge_type in SITE_BLOCK_TYPES + ("NETWORK_EXCEPTION",):
                    summary["stopped"] = head.challenge.details
                    break
                summary["errors"] += 1
                continue

            version = await db.get(DocumentVersion, version_id)
            if version.etag is None and version.last_modified is None:
                version.etag, version.last_modified, version.fetched_at = head.etag, head.last_modified, head.fetched_at
                version.source_url = version.source_url or url
                summary["baselined"] += 1
                await db.commit()
                continue

            changed = (head.etag is not None and head.etag != version.etag) or (
                head.last_modified is not None and head.last_modified != version.last_modified
            )
            if not changed:
                summary["unchanged"] += 1
                continue

            async with self._crawler_lock:
                fetched = await connector.fetch_document(url)
            if fetched.rejected:
                summary["skipped_rejected"] += 1
                continue
            if fetched.challenge or not fetched.content:
                if fetched.challenge and fetched.challenge.challenge_type in SITE_BLOCK_TYPES:
                    summary["stopped"] = fetched.challenge.details
                    break
                summary["errors"] += 1
                continue

            new_sha = hashlib.sha256(fetched.content).hexdigest()
            version = await db.get(DocumentVersion, version_id)
            if new_sha == version.file_sha256:
                version.etag, version.last_modified, version.fetched_at = fetched.etag, fetched.last_modified, fetched.fetched_at
                summary["same_file"] += 1
                await db.commit()
                continue

            doc = await db.get(Document, doc_id)
            try:
                _doc, new_version, _pages = await document_ingestion_service.ingest_document(
                    db=db,
                    pdf_bytes=fetched.content,
                    institution_id=doc.institution_id,
                    department_id=doc.department_id,
                    reference_number=doc.reference_number,
                    title=doc.title,
                    publication_date=doc.publication_date,
                    document_type=doc.document_type,
                    source_url=url,
                    etag=fetched.etag,
                    last_modified=fetched.last_modified,
                    fetched_at=fetched.fetched_at,
                    target_document_id=doc_id,
                    language=version.language,
                )
            except Exception as e:
                logger.error(f"Archive recheck could not store the new version of {url}: {e}")
                summary["errors"] += 1
                continue

            if new_version.document_id == doc_id and new_version.id != version_id:
                _doc.publication_status = "PUBLISHED_MACHINE_PROCESSED"
                summary["new_versions"] += 1
                logger.info(f"Archive recheck: {url} was replaced on the site; stored as version {new_version.version_number}.")
            else:
                # The new bytes match a file already stored elsewhere: keep the headers only.
                version = await db.get(DocumentVersion, version_id)
                version.etag, version.last_modified, version.fetched_at = fetched.etag, fetched.last_modified, fetched.fetched_at
                summary["same_file"] += 1
            await db.commit()

        logger.info(f"Archive recheck finished: {summary}")
        return summary

    async def get_source_stats(self, db: AsyncSession, source_id: UUID) -> Dict[str, Any]:
        """Calculates comprehensive operational coverage and telemetry metrics."""
        source = await db.get(Source, source_id)
        if not source:
            raise ValueError(f"Source with ID {source_id} does not exist.")

        def scoped(q):
            return self._scope_to_source(q, source_id)

        count_q = select(func.count(SourceDiscovery.id))

        total_discovered = await db.scalar(scoped(count_q)) or 0

        total_ingested = await db.scalar(
            scoped(count_q).where(SourceDiscovery.status == "INGESTED")
        ) or 0

        total_pending = await db.scalar(
            scoped(count_q).where(SourceDiscovery.status.in_(["VALIDATED", "DISCOVERED", "DOWNLOAD_PENDING"]))
        ) or 0

        total_duplicates = await db.scalar(
            scoped(count_q).where(SourceDiscovery.status == "DUPLICATE")
        ) or 0

        total_failed = await db.scalar(
            scoped(count_q).where(SourceDiscovery.status == "FAILED")
        ) or 0

        # Department breakdown
        dept_counts_q = await db.execute(
            scoped(select(SourceDiscovery.department_code, func.count(SourceDiscovery.id)))
            .group_by(SourceDiscovery.department_code)
        )
        dept_breakdown = {row[0] or "UNKNOWN": row[1] for row in dept_counts_q.all()}

        # Year breakdown
        year_counts_q = await db.execute(
            scoped(select(func.extract('year', SourceDiscovery.publication_date), func.count(SourceDiscovery.id)))
            .where(SourceDiscovery.publication_date != None)
            .group_by(func.extract('year', SourceDiscovery.publication_date))
            .order_by(func.extract('year', SourceDiscovery.publication_date).desc())
        )
        year_breakdown = {str(int(row[0])): row[1] for row in year_counts_q.all() if row[0]}

        # Language breakdown
        lang_counts_q = await db.execute(
            scoped(select(SourceDiscovery.language, func.count(SourceDiscovery.id)))
            .group_by(SourceDiscovery.language)
        )
        lang_breakdown = {row[0] or "Unknown": row[1] for row in lang_counts_q.all()}

        return {
            "source_id": source.id,
            "source_name": source.name,
            "is_active": source.is_active,
            "total_discovered": total_discovered,
            "total_ingested": total_ingested,
            "total_pending": total_pending,
            "total_duplicates": total_duplicates,
            "total_failed": total_failed,
            "department_breakdown": dept_breakdown,
            "year_breakdown": year_breakdown,
            "language_breakdown": lang_breakdown,
            "last_polled_at": source.last_checked_at,
            "last_successful_run_at": source.last_successful_run_at,
            "access_restriction_status": source.access_restriction_status
        }

    async def approve_and_ingest_discovery(
        self,
        db: AsyncSession,
        discovery_id: UUID
    ) -> Document:
        """Approves a validated discovery item and ingests it into the document repository."""
        discovery = await db.get(SourceDiscovery, discovery_id)
        if not discovery:
            raise LookupError(f"Discovery {discovery_id} not found.")

        if discovery.status in self.NON_APPROVABLE_STATUSES:
            raise ValueError(
                f"Discovery {discovery_id} is {discovery.status} and cannot be approved."
            )

        source_run = await db.get(SourceRun, discovery.source_run_id)
        source = await db.get(Source, source_run.source_id) if source_run else None
        if not source:
            raise LookupError(f"Source for discovery {discovery_id} not found.")

        connector = self.get_connector_for_source(source)
        async with self._crawler_lock:
            fetched = await connector.fetch_document(discovery.file_url or discovery.source_url)
        pdf_bytes, challenge = fetched.content, fetched.challenge

        if fetched.rejected:
            discovery.status = "SKIPPED_REJECTED"
            discovery.error_message = challenge.details
            await db.commit()
            raise PermissionError(f"Download skipped: {challenge.details}")

        if challenge:
            discovery.status = "RESTRICTED" if challenge.challenge_type in SITE_BLOCK_TYPES else "FAILED"
            discovery.error_message = challenge.details
            await db.commit()
            raise PermissionError(f"Download restricted: {challenge.details}")

        if not pdf_bytes:
            discovery.status = "FAILED"
            await db.commit()
            raise RuntimeError("Failed to retrieve file content.")

        dept_id = None
        if discovery.department_code:
            dept_q = await db.execute(
                select(InstitutionDepartment).where(
                    InstitutionDepartment.institution_id == source.institution_id,
                    InstitutionDepartment.code == discovery.department_code
                )
            )
            dept = dept_q.scalar_one_or_none()
            if dept:
                dept_id = dept.id

        try:
            doc, version, page_count = await document_ingestion_service.ingest_document(
                db=db,
                pdf_bytes=pdf_bytes,
                institution_id=source.institution_id,
                department_id=dept_id,
                reference_number=discovery.reference_number,
                title=discovery.title or "Official Circular",
                publication_date=discovery.publication_date or datetime.now(timezone.utc).date(),
                source_url=discovery.file_url or discovery.source_url,
                document_type=discovery.publication_type or "CIRCULAR",
                language=discovery.language,
                etag=fetched.etag,
                last_modified=fetched.last_modified,
                fetched_at=fetched.fetched_at,
            )
        except Exception as e:
            await db.rollback()
            discovery = await db.get(SourceDiscovery, discovery_id)
            discovery.status = "FAILED"
            discovery.retry_count += 1
            discovery.error_message = str(e)
            await db.commit()
            raise

        doc.publication_status = "PUBLISHED_MACHINE_PROCESSED"
        discovery = await db.get(SourceDiscovery, discovery_id)
        discovery.status = "INGESTED"
        discovery.document_id = doc.id
        discovery.file_hash = version.file_sha256
        discovery.file_size = version.file_size_bytes
        discovery.etag = fetched.etag
        discovery.last_modified = fetched.last_modified
        discovery.fetched_at = fetched.fetched_at
        await db.commit()
        return doc

    async def reject_discovery(
        self,
        db: AsyncSession,
        discovery_id: UUID,
        reason: str
    ) -> SourceDiscovery:
        discovery = await db.get(SourceDiscovery, discovery_id)
        if not discovery:
            raise ValueError(f"Discovery {discovery_id} not found.")

        discovery.status = "REJECTED"
        discovery.rejection_reason = reason
        await db.commit()
        await db.refresh(discovery)
        return discovery


source_monitoring_service = SourceMonitoringService()
