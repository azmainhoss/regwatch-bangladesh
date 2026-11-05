from datetime import date
from io import BytesIO
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.storage import storage_service
from backend.app.database.session import get_async_db
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.documents.schemas import DocumentPageRead, DocumentRead, DocumentUploadResponse, DocumentVersionRead
from backend.app.modules.documents.service import document_ingestion_service

router = APIRouter(prefix="/documents", tags=["Documents & Ingestion"])


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
    db: AsyncSession = Depends(get_async_db)
):
    """
    Direct document dropzone and manual submission endpoint:
    Accepts an official regulatory PDF, computes SHA-256 hash,
    stores in immutable storage, extracts page-by-page, and updates catalog.
    """
    if not file.filename.lower().endswith(".pdf"):
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


@router.get("", response_model=List[DocumentRead])
async def list_documents(
    institution_id: Optional[UUID] = Query(None),
    department_id: Optional[UUID] = Query(None),
    document_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    publication_status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db)
):
    query = select(Document).options(selectinload(Document.versions)).order_by(Document.publication_date.desc())

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


@router.get("/{document_id}/pdf")
async def stream_document_pdf(
    document_id: UUID,
    version_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Streams the original immutable PDF file directly from storage
    to power side-by-side verification and in-browser reading.
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
