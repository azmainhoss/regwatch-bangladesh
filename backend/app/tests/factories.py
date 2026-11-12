"""Small helpers that create real database rows for tests."""
import uuid
from datetime import date
from typing import Optional, Tuple

from backend.app.core.security import create_access_token, get_password_hash
from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.identity.models import User
from backend.app.modules.institutions.models import Institution
from backend.app.modules.obligations.models import Obligation


async def make_user(is_superuser: bool = False) -> Tuple[User, str]:
    async with AsyncSessionLocal() as db:
        user = User(
            email=f"user_{uuid.uuid4().hex[:8]}@example.test",
            hashed_password=get_password_hash("Password123!"),
            full_name="Test User",
            is_active=True,
            is_superuser=is_superuser,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user, create_access_token(subject=str(user.id))


async def make_institution() -> Institution:
    async with AsyncSessionLocal() as db:
        inst = Institution(
            name="Bangladesh Bank (test)",
            code=f"BBT{uuid.uuid4().hex[:6].upper()}",
            website_url="https://www.bb.org.bd",
        )
        db.add(inst)
        await db.commit()
        await db.refresh(inst)
        return inst


async def make_document(
    pages: int = 2,
    status: str = "EXTRACTED",
    title: Optional[str] = None,
    reference_number: Optional[str] = None,
) -> Tuple[Document, DocumentVersion, list]:
    inst = await make_institution()
    async with AsyncSessionLocal() as db:
        doc = Document(
            institution_id=inst.id,
            title=title or f"Fixture circular {uuid.uuid4().hex[:6]}",
            reference_number=reference_number or f"FIX-{uuid.uuid4().hex[:6]}",
            publication_date=date(2026, 1, 1),
            publication_status=status,
            is_synthetic_fixture=True,
        )
        db.add(doc)
        await db.flush()
        version = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            file_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            file_size_bytes=100,
            storage_path="originals/none.pdf",
            page_count=pages,
        )
        db.add(version)
        await db.flush()
        doc.current_version_id = version.id
        page_rows = []
        for n in range(1, pages + 1):
            page = DocumentPage(
                document_version_id=version.id,
                page_number=n,
                raw_text=f"Banks shall maintain liquidity ratio on page {n}.",
                cleaned_text=f"Banks shall maintain liquidity ratio on page {n}.",
            )
            db.add(page)
            page_rows.append(page)
        await db.commit()
        for p in page_rows:
            await db.refresh(p)
        await db.refresh(doc)
        await db.refresh(version)
        return doc, version, page_rows


async def make_obligation() -> Obligation:
    _doc, version, pages = await make_document(pages=1)
    async with AsyncSessionLocal() as db:
        obl = Obligation(
            document_version_id=version.id,
            page_id=pages[0].id,
            obligation_type="MANDATORY",
            title="Maintain liquidity ratio",
            requirement_description="Banks shall maintain the liquidity ratio.",
            supporting_text="Banks shall maintain liquidity ratio on page 1.",
            applicability_summary="Scheduled banks",
        )
        db.add(obl)
        await db.commit()
        await db.refresh(obl)
        return obl
