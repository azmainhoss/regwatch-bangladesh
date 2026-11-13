"""Small helpers that create real database rows for tests."""
import uuid
from datetime import date
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from backend.app.core.security import create_access_token, get_password_hash
from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.identity.models import User
from backend.app.modules.institutions.models import Institution
from backend.app.modules.obligations.models import Obligation
from backend.app.modules.organizations.models import Department, Organization, OrganizationMember


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


async def make_obligation_in(
    verified: bool = False,
    doc_status: str = "EXTRACTED",
    pages: int = 1,
    quote: Optional[str] = None,
    reference_number: Optional[str] = None,
) -> Tuple[Obligation, Document, DocumentVersion, list]:
    """An obligation plus its circular, version and pages."""
    doc, version, page_rows = await make_document(pages=pages, status=doc_status, reference_number=reference_number)
    async with AsyncSessionLocal() as db:
        obl = Obligation(
            document_version_id=version.id,
            page_id=page_rows[0].id,
            obligation_type="MANDATORY",
            title="Maintain liquidity ratio",
            requirement_description="Banks shall maintain the liquidity ratio.",
            supporting_text=quote or "Banks shall maintain liquidity ratio on page 1.",
            applicability_summary="Scheduled banks",
            verification_status="VERIFIED" if verified else "PENDING_REVIEW",
        )
        db.add(obl)
        await db.commit()
        await db.refresh(obl)
        return obl, doc, version, page_rows


async def make_obligation(verified: bool = False, doc_status: str = "EXTRACTED") -> Obligation:
    """With verified=True the quote counts as checked. Pass doc_status="PUBLISHED_MACHINE_PROCESSED" for a published
    circular (its current version is the version the obligation belongs to)."""
    obl, _doc, _version, _pages = await make_obligation_in(verified=verified, doc_status=doc_status)
    return obl


@dataclass
class Workspace:
    org_id: str
    departments: Dict[str, str] = field(default_factory=dict)  # key -> department id
    users: Dict[str, User] = field(default_factory=dict)  # role (or "ROLE:key") -> user
    tokens: Dict[str, str] = field(default_factory=dict)
    members: Dict[str, str] = field(default_factory=dict)  # role -> member id

    def headers(self, role: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[role]}"}


async def make_workspace(roles: Dict[str, Optional[str]], departments=("A", "B")) -> Workspace:
    """An organization with departments and one active member per role.
    `roles` maps a role name to the key of its department (or None)."""
    async with AsyncSessionLocal() as db:
        org = Organization(name=f"Bank {uuid.uuid4().hex[:6]}", entity_type="COMMERCIAL_BANK")
        db.add(org)
        await db.flush()
        ws = Workspace(org_id=str(org.id))
        depts = {}
        for key in departments:
            d = Department(organization_id=org.id, name=f"Dept {key} {uuid.uuid4().hex[:4]}")
            db.add(d)
            depts[key] = d
        await db.flush()
        ws.departments = {k: str(d.id) for k, d in depts.items()}
        await db.commit()
    for role, dept_key in roles.items():
        user, token = await make_user()
        async with AsyncSessionLocal() as db:
            member = OrganizationMember(
                organization_id=uuid.UUID(ws.org_id), user_id=user.id, role=role.split(":")[0], status="ACTIVE",
                department_id=uuid.UUID(ws.departments[dept_key]) if dept_key else None,
            )
            db.add(member)
            await db.commit()
            ws.members[role] = str(member.id)
        ws.users[role] = user
        ws.tokens[role] = token
    return ws
