import asyncio
from datetime import date
from typing import Optional, Tuple
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.storage import storage_service
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.extraction.service import extraction_service


class DocumentIngestionService:
    @staticmethod
    async def ingest_document(
        db: AsyncSession,
        pdf_bytes: bytes,
        institution_id: UUID,
        title: str,
        publication_date: date,
        department_id: Optional[UUID] = None,
        reference_number: Optional[str] = None,
        title_bn: Optional[str] = None,
        document_type: str = "CIRCULAR",
        effective_date: Optional[date] = None,
        source_url: Optional[str] = None
    ) -> Tuple[Document, DocumentVersion, int]:
        """
        Ingests a PDF document into the system:
        1. Stores immutable file in originals namespace.
        2. Computes SHA-256 hash.
        3. Deduplicates or creates new version.
        4. Extracts text page-by-page.
        5. Saves Document, DocumentVersion, and DocumentPages transactionally.
        """
        # Store file immutably
        storage_path, file_sha256, file_size = storage_service.store_file(
            namespace=settings.ORIGINALS_STORAGE_NAMESPACE,
            filename_prefix=reference_number or "doc",
            content=pdf_bytes,
            extension=".pdf"
        )

        # Check if identical document content already exists
        existing_version_query = await db.execute(
            select(DocumentVersion).where(DocumentVersion.file_sha256 == file_sha256)
        )
        existing_version = existing_version_query.scalar_one_or_none()

        if existing_version:
            logger.info(f"Duplicate document found with SHA-256 {file_sha256}. Reusing existing version {existing_version.id}")
            doc_query = await db.execute(
                select(Document).options(selectinload(Document.versions)).where(Document.id == existing_version.document_id)
            )
            doc = doc_query.scalar_one()
            return doc, existing_version, existing_version.page_count

        # Check if document with same reference number exists under institution
        doc = None
        if reference_number:
            existing_doc_query = await db.execute(
                select(Document).where(
                    Document.institution_id == institution_id,
                    Document.reference_number == reference_number
                ).options(selectinload(Document.versions))
            )
            doc = existing_doc_query.scalar_one_or_none()

        if not doc:
            doc = Document(
                institution_id=institution_id,
                department_id=department_id,
                reference_number=reference_number,
                title=title,
                title_bn=title_bn,
                document_type=document_type,
                publication_date=publication_date,
                effective_date=effective_date,
                source_url=source_url,
                publication_status="EXTRACTING"
            )
            db.add(doc)
            await db.flush()
            version_num = 1
        else:
            version_num = len(doc.versions) + 1
            doc.publication_status = "EXTRACTING"

        # Run page extraction in worker thread so event loop remains responsive for health checks
        should_ocr = (len(pdf_bytes) <= 2500000) and (getattr(settings, "ENVIRONMENT", "development") != "production")
        extracted_pages = await asyncio.to_thread(
            extraction_service.extract_document_pages,
            pdf_bytes=pdf_bytes,
            ocr_fallback=should_ocr
        )
        page_count = len(extracted_pages)
        is_scanned = any(p["extraction_method"] == "OCR_TESSERACT" for p in extracted_pages)

        # Determine language
        sample_text = " ".join([p["raw_text"][:200] for p in extracted_pages[:3]])
        has_bangla = bool(any(ord(c) >= 0x0980 and ord(c) <= 0x09FF for c in sample_text))
        has_english = bool(any(c.isalpha() and ord(c) < 128 for c in sample_text))
        lang = "mixed" if (has_bangla and has_english) else ("bn" if has_bangla else "en")

        version = DocumentVersion(
            document_id=doc.id,
            version_number=version_num,
            file_sha256=file_sha256,
            file_size_bytes=file_size,
            file_mime_type="application/pdf",
            storage_path=storage_path,
            page_count=page_count,
            language=lang,
            is_scanned=is_scanned
        )
        db.add(version)
        await db.flush()

        doc.current_version_id = version.id
        doc.publication_status = "EXTRACTED"

        # Insert page records
        for p in extracted_pages:
            page_record = DocumentPage(
                document_version_id=version.id,
                page_number=p["page_number"],
                raw_text=p["raw_text"],
                native_text=p.get("native_text"),
                ocr_text=p.get("ocr_text"),
                cleaned_text=p["cleaned_text"],
                extraction_method=p["extraction_method"],
                ocr_confidence=p["ocr_confidence"],
                has_tables=p["has_tables"],
                extracted_tables=p["extracted_tables"],
                quality_status=p.get("quality_status", "SUCCESS_NATIVE"),
                quality_score=p.get("quality_score", 1.0),
                layout_hierarchy=p.get("layout_hierarchy", {}),
                human_corrected_text=None,
                is_human_corrected=False
            )
            db.add(page_record)

        await db.commit()
        # Reload doc with versions eager loaded for Pydantic serialization
        doc_query = await db.execute(
            select(Document).options(selectinload(Document.versions)).where(Document.id == doc.id)
        )
        doc = doc_query.scalar_one()
        version = await db.get(DocumentVersion, version.id)
        logger.info(f"Successfully ingested and extracted Document '{doc.title}' ({page_count} pages, SHA: {file_sha256[:8]}...)")
        import gc
        gc.collect()
        return doc, version, page_count


document_ingestion_service = DocumentIngestionService()
