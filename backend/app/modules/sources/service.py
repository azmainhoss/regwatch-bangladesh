import asyncio
import hashlib
from datetime import datetime, timezone
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
from backend.app.modules.sources.connector.base import BaseSourceConnector
from backend.app.modules.sources.models import Source, SourceDiscovery, SourceRun


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
        run_type: str = "SCHEDULED_POLL"
    ) -> SourceRun:
        """
        Executes a continuous monitoring cycle:
        1. Runs discovery scan to find newly published circulars.
        2. Automatically collects and ingests newest publications into the repository.
        3. Updates audit logs and source health metrics.
        """
        run = await self.execute_discovery_scan(db=db, source_id=source_id, run_type=run_type)
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
        run_type: str = "DISCOVERY_SCAN"
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
                discovery_result = await connector.discover_publications(max_pages=1)
                return await self._record_discovery_result(db, source, run, discovery_result)
        except Exception as e:
            logger.error(f"Error during discovery scan {run_id}: {e}")
            await db.rollback()
            run = await db.get(SourceRun, run_id)
            source = await db.get(Source, source_id)
            run.status = "FAILED"
            run.error_count += 1
            run.error_log = str(e)
            run.completed_at = datetime.now(timezone.utc)
            source.last_error = str(e)
            await db.commit()
            await db.refresh(run)
            return run

    async def _record_discovery_result(self, db: AsyncSession, source: Source, run: SourceRun, discovery_result) -> SourceRun:
        """Stores the candidates found by a scan. Called while holding the crawler lock."""
        run.pages_inspected = discovery_result.pages_inspected
        run.candidate_links_discovered = len(discovery_result.candidate_publications)

        # Check if anti-bot challenge was triggered
        if discovery_result.anti_bot_challenge:
            ch = discovery_result.anti_bot_challenge
            run.status = "RESTRICTED"
            run.access_restricted = True
            run.access_restriction_details = ch.model_dump()
            run.error_log = ch.details
            run.completed_at = datetime.now(timezone.utc)

            source.access_restriction_status = ch.challenge_type or "RESTRICTED"
            source.last_error = ch.details
            source.last_checked_at = datetime.now(timezone.utc)

            await db.commit()
            await db.refresh(run)
            logger.warning(f"Source run {run.id} restricted: {ch.details}")
            return run

        # Query this source's existing file_urls and reference_numbers for fast in-memory deduplication
        existing_urls_q = await db.execute(
            self._scope_to_source(select(SourceDiscovery.file_url), source.id)
        )
        existing_urls = {u for u in existing_urls_q.scalars().all() if u}

        existing_doc_refs_q = await db.execute(
            select(Document.reference_number).where(
                Document.institution_id == source.institution_id,
                Document.reference_number != None,
                # Private uploads must not hide a circular from the shared library.
                Document.owner_user_id.is_(None),
            )
        )
        existing_doc_refs = {r for r in existing_doc_refs_q.scalars().all() if r}

        new_discoveries = []
        for cand in discovery_result.candidate_publications:
            if not cand.file_url:
                continue

            if cand.file_url in existing_urls:
                run.duplicate_count += 1
                continue

            is_dup_ref = bool(cand.reference_number and cand.reference_number in existing_doc_refs)
            status_disc = "DUPLICATE" if is_dup_ref else "VALIDATED"
            if status_disc == "DUPLICATE":
                run.duplicate_count += 1
            else:
                run.valid_documents_discovered += 1

            existing_urls.add(cand.file_url)

            discovery = SourceDiscovery(
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
                status=status_disc
            )
            new_discoveries.append(discovery)

        if new_discoveries:
            db.add_all(new_discoveries)

        run.discovered_count = run.valid_documents_discovered
        run.status = "COMPLETED"
        run.completed_at = datetime.now(timezone.utc)
        source.access_restriction_status = "CLEAR"
        source.last_successful_run_at = datetime.now(timezone.utc)
        source.last_checked_at = datetime.now(timezone.utc)
        source.last_discovered_publication_at = datetime.now(timezone.utc)
        source.last_error = None

        await db.commit()
        await db.refresh(run)
        logger.info(f"Discovery scan {run.id} completed: {run.valid_documents_discovered} new, {run.duplicate_count} duplicate.")
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
        ingested_items = []

        async with self._crawler_lock:
            candidate_ids = [c.id for c in candidates]
            for disc_id in candidate_ids:
                disc = await db.get(SourceDiscovery, disc_id)
                if disc is None:
                    continue
                disc.last_attempted_at = datetime.now(timezone.utc)
                try:
                    # Polite download pause respecting central bank rate limits
                    pause_sec = getattr(settings, "BB_REQUEST_INTERVAL_SECONDS", 2.0)
                    await asyncio.sleep(pause_sec)

                    pdf_bytes, challenge = await connector.download_document(disc.file_url or disc.source_url)

                    if challenge:
                        disc.status = "RESTRICTED" if challenge.is_blocked else "FAILED"
                        disc.retry_count += 1
                        disc.error_message = challenge.details
                        failed += 1
                        await db.commit()
                        continue

                    if not pdf_bytes:
                        disc.status = "FAILED"
                        disc.retry_count += 1
                        disc.error_message = "Empty payload received from source."
                        failed += 1
                        await db.commit()
                        continue

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
                        document_type=disc.publication_type or "CIRCULAR"
                    )

                    # Mark as honest machine-processed publication
                    doc.publication_status = "PUBLISHED_MACHINE_PROCESSED"

                    disc.status = "INGESTED"
                    disc.document_id = doc.id
                    disc.file_hash = version.file_sha256
                    disc.file_size = version.file_size_bytes
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
            "ingested_documents": ingested_items
        }

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
            pdf_bytes, challenge = await connector.download_document(discovery.file_url or discovery.source_url)

        if challenge:
            discovery.status = "RESTRICTED"
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
                document_type=discovery.publication_type or "CIRCULAR"
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
        discovery.status = "INGESTED"
        discovery.document_id = doc.id
        discovery.file_hash = version.file_sha256
        discovery.file_size = version.file_size_bytes
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
