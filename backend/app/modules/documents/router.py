import asyncio
from datetime import date
from io import BytesIO
from typing import List, Optional
from uuid import UUID
import pymupdf as fitz
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.storage import storage_service
from backend.app.database.session import get_async_db
from backend.app.modules.identity.deps import get_current_user
from backend.app.modules.identity.models import User
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.documents.schemas import (
    DashboardStatsRead,
    DocumentPageRead,
    DocumentRead,
    DocumentUploadResponse,
    DocumentVersionRead,
    PageCorrectionRequest,
)
from backend.app.modules.documents.service import document_ingestion_service
from backend.app.modules.institutions.models import Institution, InstitutionDepartment
from backend.app.modules.sources.models import Source

router = APIRouter(prefix="/documents", tags=["Documents & Ingestion"])

MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

# Robust synthetic/test record detection matching both schema and test suites
SYNTHETIC_SQL_CONDITIONS = [
    Document.title.ilike("Sample%"),
    Document.title.ilike("%Test%"),
    Document.title.ilike("Gate Policy%"),
    Document.title.ilike("%Citation Policy%"),
    Document.title.ilike("%Test Directive%"),
    func.coalesce(Document.reference_number, "").ilike("BRPD(P)%"),
    func.coalesce(Document.reference_number, "").ilike("VCP-%"),
    func.coalesce(Document.reference_number, "").ilike("UTD-%"),
    func.coalesce(Document.reference_number, "").ilike("GP-%"),
]


def is_synthetic_record(title: Optional[str], reference_number: Optional[str], status: Optional[str] = None, page_count: int = 0) -> bool:
    t_low = (title or "").lower()
    r_low = (reference_number or "").lower()
    if "sample" in t_low or "test" in t_low or "gate policy" in t_low or "citation policy" in t_low:
        return True
    if r_low.startswith("brpd(p)") or r_low.startswith("vcp-") or r_low.startswith("utd-") or r_low.startswith("gp-"):
        return True
    if status == "DRAFT" and page_count == 0:
        return True
    return False


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    institution_id: UUID = Form(...),
    title: str = Form(...),
    publication_date: date = Form(...),
    department_id: Optional[UUID] = Form(None),
    reference_number: Optional[str] = Form(None),
    title_bn: Optional[str] = Form(None),
    document_type: str = Form("CIRCULAR"),
    effective_date: Optional[date] = Form(None),
    source_url: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Direct document dropzone and manual submission endpoint:
    Requires authentication.
    Validates PDF magic bytes, enforces 50MB file size limit,
    computes SHA-256 hash, stores in immutable storage,
    extracts page-by-page, and updates catalog.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF documents are supported for regulatory ingestion."
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded."
        )

    if len(content) > MAX_DOCUMENT_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {MAX_DOCUMENT_SIZE_BYTES // (1024*1024)}MB."
        )

    # Magic bytes check: PDF header must begin with %PDF-
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format: file does not have a valid PDF header signature."
        )

    # Verify structural integrity of PDF
    try:
        test_doc = fitz.open(stream=content, filetype="pdf")
        if len(test_doc) == 0:
            test_doc.close()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Malformed PDF: document contains 0 pages."
            )
        test_doc.close()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Malformed or corrupt PDF document: {str(e)}"
        )

    doc, version, page_count = await document_ingestion_service.ingest_document(
        db=db,
        pdf_bytes=content,
        institution_id=institution_id,
        title=title,
        publication_date=publication_date,
        department_id=department_id,
        reference_number=reference_number,
        title_bn=title_bn,
        document_type=document_type,
        effective_date=effective_date,
        source_url=source_url
    )

    return DocumentUploadResponse(
        document=DocumentRead.model_validate(doc),
        version=DocumentVersionRead.model_validate(version),
        pages_extracted=page_count,
        message="Document successfully ingested and extracted page-by-page."
    )


@router.get("/stats", response_model=DashboardStatsRead)
async def get_dashboard_stats(db: AsyncSession = Depends(get_async_db)):
    """
    Computes truthful live metrics across genuine publications, extracted pages,
    synthetic test fixtures, and active source monitoring status.
    """
    # Fetch all documents with their versions
    query = select(Document).options(selectinload(Document.versions))
    docs = (await db.execute(query)).scalars().all()

    total_docs = len(docs)
    genuine_docs = []
    synthetic_docs = []

    for d in docs:
        page_cnt = d.versions[0].page_count if d.versions else 0
        if is_synthetic_record(d.title, d.reference_number, d.publication_status, page_cnt):
            synthetic_docs.append(d)
        else:
            genuine_docs.append(d)

    genuine_pages = sum(d.versions[0].page_count for d in genuine_docs if d.versions)
    synthetic_pages = sum(d.versions[0].page_count for d in synthetic_docs if d.versions)
    total_pages = genuine_pages + synthetic_pages

    verified_count = sum(1 for d in genuine_docs if (d.publication_status or "").startswith("PUBLISHED"))
    awaiting_count = sum(1 for d in genuine_docs if d.publication_status == "AWAITING_REVIEW")
    draft_count = sum(1 for d in docs if d.publication_status == "DRAFT")

    # Fetch distinct departments and sources
    dept_stmt = select(InstitutionDepartment.code).distinct().order_by(InstitutionDepartment.code)
    dept_codes = (await db.execute(dept_stmt)).scalars().all()
    clean_dept_codes = sorted(list(set(c for c in dept_codes if c)))

    src_stmt = select(Source).order_by(Source.created_at.desc()).limit(1)
    primary_src = (await db.execute(src_stmt)).scalars().first()

    src_status = primary_src.access_restriction_status if primary_src else "CLEAR"
    if src_status == "IMPERVA_TSPD_CAPTCHA":
        src_msg = "Automated portal monitoring restricted by Imperva WAF anti-bot challenge. Manual dropzone active."
    elif src_status == "CLEAR" and primary_src and primary_src.is_active:
        src_msg = "Official Bangladesh Bank portal monitoring active."
    else:
        src_msg = "Manual dropzone active."

    return DashboardStatsRead(
        total_documents=total_docs,
        genuine_documents_count=len(genuine_docs),
        genuine_pages_count=genuine_pages,
        synthetic_documents_count=len(synthetic_docs),
        synthetic_pages_count=synthetic_pages,
        verified_publications_count=verified_count,
        awaiting_review_count=awaiting_count,
        draft_documents_count=draft_count,
        total_pages_extracted=total_pages,
        departments_monitored_count=len(clean_dept_codes),
        departments_codes=clean_dept_codes,
        primary_authority="Bangladesh Bank",
        source_monitoring_status=src_status,
        source_monitoring_message=src_msg,
    )


@router.get("", response_model=List[DocumentRead])
async def list_documents(
    institution_id: Optional[UUID] = Query(None),
    department_id: Optional[UUID] = Query(None),
    document_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    publication_status: Optional[str] = Query(None),
    corpus_type: Optional[str] = Query(None, description="'GENUINE', 'SYNTHETIC_SAMPLE', or 'ALL'"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db)
):
    # Sort genuine official publications first, then by publication date desc
    order_clause = [
        case((Document.title.ilike("Sample%"), 1), else_=0),
        Document.publication_date.desc(),
        Document.created_at.desc(),
    ]
    query = select(Document).options(selectinload(Document.versions)).order_by(*order_clause)

    if institution_id:
        query = query.where(Document.institution_id == institution_id)
    if department_id:
        query = query.where(Document.department_id == department_id)
    if document_type:
        query = query.where(Document.document_type == document_type)
    if publication_status:
        query = query.where(Document.publication_status == publication_status)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (Document.title.ilike(search_pattern)) |
            (Document.reference_number.ilike(search_pattern))
        )

    # API-level isolation: professional feed defaults strictly to genuine publications
    is_synthetic_sql = or_(*SYNTHETIC_SQL_CONDITIONS)
    c_upper = (corpus_type or "GENUINE").upper()
    if c_upper == "GENUINE":
        query = query.where(~is_synthetic_sql)
    elif c_upper in ("SYNTHETIC_SAMPLE", "TEST"):
        query = query.where(is_synthetic_sql)
    # When c_upper == "ALL", return all records (e.g. for administrators)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db)
):
    query = select(Document).options(selectinload(Document.versions)).where(Document.id == document_id)
    result = await db.execute(query)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{document_id}/versions/{version_id}/pages", response_model=List[DocumentPageRead])
async def get_document_pages(
    document_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_async_db)
):
    query = (
        select(DocumentPage)
        .where(DocumentPage.document_version_id == version_id)
        .order_by(DocumentPage.page_number)
    )
    result = await db.execute(query)
    pages = result.scalars().all()
    if not pages:
        raise HTTPException(status_code=404, detail="No pages found for this document version")
    return pages


@router.get("/{document_id}/versions/{version_id}/report")
async def get_document_extraction_report(
    document_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Returns the comprehensive document extraction completeness and quality report.
    """
    query = (
        select(DocumentPage)
        .where(DocumentPage.document_version_id == version_id)
        .order_by(DocumentPage.page_number)
    )
    result = await db.execute(query)
    pages = result.scalars().all()
    if not pages:
        raise HTTPException(status_code=404, detail="No pages found for this document version")

    from backend.app.modules.extraction.service import extraction_service
    page_dicts = [
        {
            "page_number": p.page_number,
            "raw_text": p.raw_text,
            "extraction_method": p.extraction_method,
            "ocr_confidence": p.ocr_confidence,
            "has_tables": p.has_tables,
            "extracted_tables": p.extracted_tables or []
        }
        for p in pages
    ]
    report = extraction_service.generate_document_report(page_dicts)
    return report.model_dump()


@router.get("/{document_id}/versions/{version_id}/tables")
async def get_document_tables(
    document_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieves all structured tables extracted across the pages of this document version.
    """
    query = (
        select(DocumentPage)
        .where(
            DocumentPage.document_version_id == version_id,
            DocumentPage.has_tables == True
        )
        .order_by(DocumentPage.page_number)
    )
    result = await db.execute(query)
    pages = result.scalars().all()
    
    all_tables = []
    for p in pages:
        for tbl in p.extracted_tables or []:
            tbl_copy = dict(tbl)
            tbl_copy["page_number"] = p.page_number
            all_tables.append(tbl_copy)
    return all_tables


@router.post("/{document_id}/versions/{version_id}/pages/{page_no}/correct")
async def submit_human_correction(
    document_id: UUID,
    version_id: UUID,
    page_no: int,
    payload: PageCorrectionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Submits a human correction for a specific page without overwriting raw extracted text.
    """
    query = select(DocumentPage).where(
        DocumentPage.document_version_id == version_id,
        DocumentPage.page_number == page_no
    )
    result = await db.execute(query)
    page_record = result.scalar_one_or_none()
    if not page_record:
        raise HTTPException(status_code=404, detail="Page record not found")

    page_record.human_corrected_text = payload.corrected_text
    page_record.cleaned_text = payload.corrected_text
    page_record.is_human_corrected = True
    page_record.extraction_method = "HUMAN_CORRECTED"
    page_record.quality_status = "SUCCESS_NORMALIZED"
    page_record.quality_score = 1.0

    await db.commit()
    await db.refresh(page_record)
    return {
        "message": f"Human correction successfully applied to page {page_no}.",
        "page_number": page_no,
        "is_human_corrected": True,
        "extraction_method": page_record.extraction_method
    }


@router.post("/{document_id}/extract")
async def retrigger_extraction(
    document_id: UUID,
    version_id: Optional[UUID] = None,
    preferred_language: str = Query("auto"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retriggers page-level extraction for a document version.
    """
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    target_version_id = version_id or doc.current_version_id
    if not target_version_id:
        raise HTTPException(status_code=404, detail="Document has no active version")

    version = await db.get(DocumentVersion, target_version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Document version not found")

    pdf_bytes = storage_service.get_file_bytes(version.storage_path)
    from backend.app.modules.extraction.service import extraction_service
    extracted_pages = await asyncio.to_thread(
        extraction_service.extract_document_pages,
        pdf_bytes=pdf_bytes,
        ocr_fallback=True,
        preferred_language=preferred_language
    )

    # Delete old pages and insert new pages
    existing_pages_query = select(DocumentPage).where(DocumentPage.document_version_id == version.id)
    existing_pages = (await db.execute(existing_pages_query)).scalars().all()
    for ep in existing_pages:
        await db.delete(ep)
    await db.flush()

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
    return {
        "message": f"Successfully re-extracted {len(extracted_pages)} pages for document {doc.title}.",
        "page_count": len(extracted_pages)
    }


@router.get("/{document_id}/pdf")
async def stream_document_pdf(
    document_id: UUID,
    version_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Streams the original immutable PDF file directly from storage
    to power side-by-side verification and in-browser reading.
    Public regulatory circulars are publicly accessible, but protected by existence checks.
    """
    if version_id:
        version = await db.get(DocumentVersion, version_id)
    else:
        doc = await db.get(Document, document_id)
        if not doc or not doc.current_version_id:
            raise HTTPException(status_code=404, detail="Document or active version not found")
        version = await db.get(DocumentVersion, doc.current_version_id)

    if not version:
        raise HTTPException(status_code=404, detail="Document version not found")

    try:
        pdf_bytes = storage_service.get_file_bytes(version.storage_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Original PDF file is missing from storage")

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename={version.file_sha256[:12]}.pdf",
            "Content-Length": str(len(pdf_bytes)),
            "X-SHA256-Checksum": version.file_sha256,
            "Cache-Control": "public, max-age=86400"
        }
    )
