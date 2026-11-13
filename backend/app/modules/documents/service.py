import asyncio
from datetime import date, datetime
from typing import Optional, Tuple
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.storage import storage_service
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.extraction.service import STATUS_PENDING_VISION, extraction_service
from backend.app.modules.relationships.linking import link_relationship_targets

LANGUAGE_NAMES = {"english": "en", "en": "en", "bangla": "bn", "bengali": "bn", "bn": "bn", "mixed": "mixed"}


def normalize_language(value: Optional[str]) -> Optional[str]:
    """'English' / 'Bangla' (as the source listing says) or en / bn / mixed -> en / bn / mixed."""
    if not value:
        return None
    return LANGUAGE_NAMES.get(value.strip().lower())


def _url_key(url: Optional[str]) -> Optional[str]:
    """Compares URLs without caring about http/https or letter case."""
    if not url:
        return None
    url = url.strip().lower()
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            return url[len(prefix):]
    return url


def _effective_url(version: DocumentVersion, doc: Document) -> Optional[str]:
    return _url_key(version.source_url or doc.source_url)


def replaces(old: DocumentVersion, doc: Document, language: str, source_url: Optional[str]) -> bool:
    """A new file only replaces an older version with the same language and the same source URL.
    An English and a Bangla file of one circular are language variants: both stay CURRENT."""
    return old.language == language and _effective_url(old, doc) == _url_key(source_url)


def _same_owner(owner_user_id: Optional[UUID]):
    """Matches documents in the same visibility scope as the upload."""
    if owner_user_id is None:
        return Document.owner_user_id.is_(None)
    return Document.owner_user_id == owner_user_id


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
        source_url: Optional[str] = None,
        owner_user_id: Optional[UUID] = None,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        fetched_at: Optional[datetime] = None,
        target_document_id: Optional[UUID] = None,
        language: Optional[str] = None,
    ) -> Tuple[Document, DocumentVersion, int]:
        """
        Ingests a PDF document into the system.

        language ("English"/"Bangla" or en/bn/mixed) is the file's language as the source lists
        it; without it the language is worked out from the pages. A new file supersedes only
        older versions with the same language and the same source URL, so an English and a
        Bangla file with the same reference number are kept side by side as language variants.

        etag, last_modified and fetched_at are the download's reply headers; they are kept
        on the new version for the archive re-check. target_document_id files the PDF as a
        new version of that document (used when a known file was replaced on the site).

        owner_user_id=None files the document in the shared library; a user id makes it
        a private upload. Duplicate detection (same file hash, same reference number) only
        looks inside the same scope: a private upload never attaches to a shared document
        or another user's private one, and a shared ingest never attaches to a private one.

        Steps:
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
            select(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(DocumentVersion.file_sha256 == file_sha256, _same_owner(owner_user_id))
        )
        # file_sha256 is not unique (the same file can sit under several documents), so take the first match.
        existing_version = existing_version_query.scalars().first()

        if existing_version:
            logger.info(f"Duplicate document found with SHA-256 {file_sha256}. Reusing existing version {existing_version.id}")
            doc_query = await db.execute(
                select(Document).options(selectinload(Document.versions)).where(Document.id == existing_version.document_id)
            )
            doc = doc_query.scalar_one()
            return doc, existing_version, existing_version.page_count

        # Check if document with same reference number exists under institution
        doc = None
        if target_document_id is not None:
            target_query = await db.execute(
                select(Document)
                .where(Document.id == target_document_id, _same_owner(owner_user_id))
                .options(selectinload(Document.versions))
            )
            doc = target_query.scalars().first()
            if doc is None:
                raise LookupError(f"Document {target_document_id} not found in this scope.")
        elif reference_number:
            existing_doc_query = await db.execute(
                select(Document).where(
                    Document.institution_id == institution_id,
                    Document.reference_number == reference_number,
                    _same_owner(owner_user_id),
                ).options(selectinload(Document.versions))
            )
            doc = existing_doc_query.scalars().first()

        try:
            return await DocumentIngestionService._extract_and_save(
                db=db,
                doc=doc,
                pdf_bytes=pdf_bytes,
                institution_id=institution_id,
                title=title,
                publication_date=publication_date,
                department_id=department_id,
                reference_number=reference_number,
                title_bn=title_bn,
                document_type=document_type,
                effective_date=effective_date,
                source_url=source_url,
                owner_user_id=owner_user_id,
                storage_path=storage_path,
                file_sha256=file_sha256,
                file_size=file_size,
                etag=etag,
                last_modified=last_modified,
                fetched_at=fetched_at,
                language=language,
            )
        except Exception:
            # Leave no half-created document behind and no existing document stuck mid-extraction.
            await db.rollback()
            raise

    @staticmethod
    async def _extract_and_save(
        db: AsyncSession,
        doc: Optional[Document],
        pdf_bytes: bytes,
        institution_id: UUID,
        title: str,
        publication_date: date,
        department_id: Optional[UUID],
        reference_number: Optional[str],
        title_bn: Optional[str],
        document_type: str,
        effective_date: Optional[date],
        source_url: Optional[str],
        owner_user_id: Optional[UUID],
        storage_path: str,
        file_sha256: str,
        file_size: int,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        fetched_at: Optional[datetime] = None,
        language: Optional[str] = None,
    ) -> Tuple[Document, DocumentVersion, int]:
        previous_versions = []
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
                owner_user_id=owner_user_id,
                publication_status="EXTRACTING"
            )
            db.add(doc)
            await db.flush()
            version_num = 1
        else:
            # Existing document: its status only changes once the new version is extracted.
            previous_versions = list(doc.versions)
            version_num = max((v.version_number for v in previous_versions), default=0) + 1

        # Run page extraction in a worker thread so the event loop stays responsive.
        # Only text-layer pages are read here; Bangla and scanned pages wait for the vision job.
        extracted_pages = await asyncio.to_thread(extraction_service.extract_document_pages, pdf_bytes=pdf_bytes)
        page_count = len(extracted_pages)
        is_scanned = any(p.get("route_reason") == "near_empty" for p in extracted_pages)

        lang = normalize_language(language)
        if lang is None:
            page_langs = {p.get("language") for p in extracted_pages if p.get("language")}
            lang = "bn" if page_langs == {"bn"} else ("mixed" if page_langs == {"en", "bn"} else "en")

        version = DocumentVersion(
            document_id=doc.id,
            version_number=version_num,
            file_sha256=file_sha256,
            file_size_bytes=file_size,
            file_mime_type="application/pdf",
            storage_path=storage_path,
            page_count=page_count,
            language=lang,
            is_scanned=is_scanned,
            source_url=source_url,
            etag=etag,
            last_modified=last_modified,
            fetched_at=fetched_at,
            status="CURRENT",
        )
        db.add(version)
        await db.flush()

        # Older files with the same language and source URL stay in the archive, marked as replaced.
        # Language variants (English and Bangla files of one circular) are left CURRENT.
        replaced_ids = set()
        for old in previous_versions:
            if old.status != "SUPERSEDED" and replaces(old, doc, lang, source_url):
                old.status = "SUPERSEDED"
                replaced_ids.add(old.id)

        # The document's main version: the new file, unless it is only a language variant
        # of a current English file (English is read from the text layer and is ready first).
        current = next((v for v in previous_versions if v.id == doc.current_version_id), None)
        keep_current = (
            current is not None
            and current.id not in replaced_ids
            and current.status == "CURRENT"
            and current.language == "en"
            and lang != "en"
        )
        if not keep_current:
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
                line_boxes=p.get("line_boxes"),
                human_corrected_text=None,
                is_human_corrected=False
            )
            db.add(page_record)

        await db.commit()
        # Circulars that already cite this reference number can now be linked to it.
        if doc.owner_user_id is None and doc.reference_number:
            try:
                await link_relationship_targets(db, doc.id)
            except Exception as link_err:
                await db.rollback()
                logger.warning(f"Could not link relationships to document {doc.id}: {link_err}")
        if any(p.get("quality_status") == STATUS_PENDING_VISION for p in extracted_pages):
            from backend.app.modules.extraction.vision_jobs import vision_worker
            vision_worker.kick()
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
