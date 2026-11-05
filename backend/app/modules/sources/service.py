from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.logging import logger
import backend.app.database.models  # Ensure all models are registered in SQLAlchemy mapper registry
from backend.app.modules.documents.models import Document, DocumentVersion
from backend.app.modules.documents.service import document_ingestion_service
from backend.app.modules.institutions.models import Institution, InstitutionDepartment
from backend.app.modules.sources.connector.bangladesh_bank import BangladeshBankConnector
from backend.app.modules.sources.connector.base import BaseSourceConnector
from backend.app.modules.sources.models import Source, SourceDiscovery, SourceRun


class SourceMonitoringService:
    @staticmethod
    def get_connector_for_source(source: Source) -> BaseSourceConnector:
        # Extensible connector factory
        return BangladeshBankConnector(base_url=source.base_url)

    async def execute_source_monitoring(
        self,
        db: AsyncSession,
        source_id: UUID,
        run_type: str = "MANUAL_TRIGGER"
    ) -> SourceRun:
        """
        Executes a complete source monitoring cycle:
        1. Creates SourceRun audit record.
        2. Queries remote portal and checks for anti-bot / WAF gates.
        3. Parses candidates and evaluates deduplication against repository.
        4. Ingests or marks for admin review.
        5. Updates run statistics and health indicators.
        """
        source = await db.get(Source, source_id)
        if not source:
            raise ValueError(f"Source with ID {source_id} does not exist.")

        # Update source attempted run timestamp
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

        connector = self.get_connector_for_source(source)
        logger.info(f"Executing source monitoring for '{source.name}' (Run ID: {run.id})...")

        try:
            discovery_result = await connector.discover_publications(max_pages=1)
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

            # Process candidates
            for cand in discovery_result.candidate_publications:
                # Check duplicate candidate by file_url or reference_number
                existing_disc = await db.execute(
                    select(SourceDiscovery).where(
                        (SourceDiscovery.file_url == cand.file_url) |
                        (
                            (SourceDiscovery.reference_number != None) &
                            (SourceDiscovery.reference_number == cand.reference_number)
                        )
                    )
                )
                if existing_disc.scalar_one_or_none():
                    run.duplicate_count += 1
                    continue

                # Also check if document already exists in main documents table
                existing_doc = None
                if cand.reference_number:
                    doc_q = await db.execute(
                        select(Document).where(
                            Document.institution_id == source.institution_id,
                            Document.reference_number == cand.reference_number
                        )
                    )
                    existing_doc = doc_q.scalar_one_or_none()

                if existing_doc:
                    status_disc = "DUPLICATE"
                    run.duplicate_count += 1
                else:
                    status_disc = "VALIDATED"
                    run.valid_documents_discovered += 1

                discovery = SourceDiscovery(
                    source_run_id=run.id,
                    source_url=cand.detail_url,
                    file_url=cand.file_url,
                    title=cand.title,
                    department_code=cand.department_code,
                    reference_number=cand.reference_number,
                    publication_date=cand.publication_date,
                    discovered_metadata=cand.metadata,
                    status=status_disc
                )
                db.add(discovery)

            # Record success metrics
            run.discovered_count = run.valid_documents_discovered
            run.downloaded_count = run.downloads_successful
            run.status = "COMPLETED"
            run.completed_at = datetime.now(timezone.utc)
            source.access_restriction_status = "CLEAR"
            source.last_successful_run_at = datetime.now(timezone.utc)
            source.last_checked_at = datetime.now(timezone.utc)
            source.last_error = None

            await db.commit()
            await db.refresh(run)
            logger.info(f"Source run {run.id} completed successfully ({run.valid_documents_discovered} new, {run.duplicate_count} duplicate).")
            return run

        except Exception as e:
            logger.error(f"Error during source run {run.id}: {e}")
            run.status = "FAILED"
            run.error_count += 1
            run.error_log = str(e)
            run.completed_at = datetime.now(timezone.utc)
            source.last_error = str(e)
            await db.commit()
            await db.refresh(run)
            return run

    async def approve_and_ingest_discovery(
        self,
        db: AsyncSession,
        discovery_id: UUID
    ) -> Document:
        """Approves a validated discovery item and ingests it into the document repository."""
        discovery = await db.get(SourceDiscovery, discovery_id)
        if not discovery:
            raise ValueError(f"Discovery {discovery_id} not found.")

        source_run = await db.get(SourceRun, discovery.source_run_id)
        source = await db.get(Source, source_run.source_id)

        # Download file
        connector = self.get_connector_for_source(source)
        pdf_bytes, challenge = await connector.download_document(discovery.file_url or discovery.source_url)

        if challenge:
            discovery.status = "RESTRICTED"
            await db.commit()
            raise PermissionError(f"Download restricted: {challenge.details}")

        if not pdf_bytes:
            discovery.status = "FAILED"
            await db.commit()
            raise ValueError("Failed to retrieve file content.")

        # Find department ID if department_code is set
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

        doc, version, page_count = await document_ingestion_service.ingest_document(
            db=db,
            pdf_bytes=pdf_bytes,
            institution_id=source.institution_id,
            department_id=dept_id,
            reference_number=discovery.reference_number,
            title=discovery.title or "Official Circular",
            publication_date=discovery.publication_date or datetime.utcnow().date(),
            source_url=discovery.file_url or discovery.source_url
        )

        discovery.status = "INGESTED"
        discovery.document_id = doc.id
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
