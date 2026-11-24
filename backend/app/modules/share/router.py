"""Email a circular, and assign a circular to a team member (it shows on their home screen and is emailed).

- GET  /share/team                 people in the caller's organizations
- POST /share/email                email the circular (summary, mind map, PDF attached)
- POST /share/email/file           the same email as a .eml file, for the person's own mail app
- POST /share/assign               assign to one or more team members (+ email each)
- GET  /share/assignments          assigned to me / by me
- PATCH /share/assignments/{id}    mark done or open again

Isolation: a person can only assign to members of an organization they belong to, and only those two
people (and nobody from another bank) ever see the assignment.
"""
import asyncio
from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.storage import storage_service
from backend.app.database.session import get_async_db
from backend.app.modules.alerts.mailer import email_configured, send_now
from backend.app.modules.claims.view import build_view
from backend.app.modules.documents.access import get_visible_document
from backend.app.modules.documents.models import Document, DocumentVersion
from backend.app.modules.identity.deps import get_current_user
from backend.app.modules.identity.models import User
from backend.app.modules.organizations.models import Organization, OrganizationMember
from backend.app.modules.share.mail import build_share_email, png_from_data_url
from backend.app.modules.share.models import CircularAssignment
from backend.app.modules.plans.router import require

router = APIRouter(prefix="/share", tags=["Share and assign"])

# People one person may email a circular to per hour (the server's mail account has a daily cap).
EMAIL_RECIPIENTS_PER_USER = (60, 3600)

EMAIL_OFF = "Email is not set up on this server yet. Use \"Open in my mail app\" instead."


class TeamMember(BaseModel):
    user_id: UUID
    name: str
    email: str
    organization_id: UUID
    organization_name: str


class EmailRequest(BaseModel):
    document_id: UUID
    to: List[EmailStr] = Field(..., min_length=1, max_length=20)
    note: Optional[str] = Field(None, max_length=2000)
    mind_map_png: Optional[str] = None  # data URL made by the screen
    attach_pdf: bool = True


class EmailResult(BaseModel):
    sent: int
    message: str


class AssignRequest(BaseModel):
    document_id: UUID
    assignee_user_ids: List[UUID] = Field(..., min_length=1, max_length=50)
    note: Optional[str] = Field(None, max_length=2000)
    due_date: Optional[date] = None
    send_email: bool = True
    mind_map_png: Optional[str] = None


class AssignmentRead(BaseModel):
    id: UUID
    document_id: UUID
    reference_number: Optional[str] = None
    title: str
    publication_date: Optional[date] = None
    assigned_by_user_id: UUID
    assignee_user_id: UUID
    assigned_by_name: str
    assignee_name: str
    note: Optional[str] = None
    due_date: Optional[date] = None
    status: str
    email_status: Optional[str] = None
    created_at: datetime


class AssignResult(BaseModel):
    created: int
    emailed: int
    email_off: bool
    assignments: List[AssignmentRead]


class AssignmentUpdate(BaseModel):
    status: str = Field(..., pattern="^(OPEN|DONE)$")


async def _my_org_ids(db: AsyncSession, user: User) -> List[UUID]:
    return list((await db.execute(
        select(OrganizationMember.organization_id).where(OrganizationMember.user_id == user.id, OrganizationMember.status == "ACTIVE")
    )).scalars().all())


def _name(u: Optional[User]) -> str:
    return (u.full_name or u.email) if u else "Someone"


async def _parts(db: AsyncSession, doc: Document, user: User, attach_pdf: bool):
    view = await build_view(db, doc, user, admin=False)
    pdf = None
    if attach_pdf and doc.current_version_id:
        version = await db.get(DocumentVersion, doc.current_version_id)
        if version:
            try:
                pdf = storage_service.get_file_bytes(version.storage_path)
            except FileNotFoundError:
                pdf = None
    return view, pdf


@router.get("/team", response_model=List[TeamMember])
async def team(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    org_ids = await _my_org_ids(db, user)
    if not org_ids:
        return []
    rows = (await db.execute(
        select(User, Organization)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .where(OrganizationMember.organization_id.in_(org_ids), OrganizationMember.status == "ACTIVE", User.is_active == True)  # noqa: E712
        .order_by(User.full_name)
    )).all()
    seen = set()
    out: List[TeamMember] = []
    for u, org in rows:
        if (u.id, org.id) in seen:
            continue
        seen.add((u.id, org.id))
        out.append(TeamMember(user_id=u.id, name=_name(u), email=u.email, organization_id=org.id, organization_name=org.name))
    return out


@router.post("/email", response_model=EmailResult)
async def email_circular(body: EmailRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    await require(db, user, "email", "Emailing a circular")
    doc = await get_visible_document(db, body.document_id, user)
    if not email_configured():
        raise HTTPException(status_code=409, detail=EMAIL_OFF)
    from backend.app.core import ratelimit
    ratelimit.enforce(f"share-email:{user.id}", *EMAIL_RECIPIENTS_PER_USER, cost=len(body.to),
                      detail="You have emailed many people in the last hour. Please try again later, "
                             "or use \"Open in my mail app\".")
    view, pdf = await _parts(db, doc, user, body.attach_pdf)
    msg = build_share_email(
        to=[str(t) for t in body.to], sender_name=_name(user), sender_email=user.email, doc=doc, view=view,
        note=body.note, mind_map_png=png_from_data_url(body.mind_map_png), pdf_bytes=pdf,
    )
    result = await asyncio.to_thread(send_now, msg)
    if not result.ok:
        raise HTTPException(status_code=502, detail="The email could not be sent just now. Please try again in a minute.")
    n = len(body.to)
    return EmailResult(sent=n, message=f"Sent to {n} {'person' if n == 1 else 'people'}.")


@router.post("/email/file")
async def email_file(body: EmailRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    """The same email as a file the person's own mail app opens (Outlook, Apple Mail, Thunderbird)."""
    await require(db, user, "email", "Emailing a circular")
    doc = await get_visible_document(db, body.document_id, user)
    view, pdf = await _parts(db, doc, user, body.attach_pdf)
    msg = build_share_email(
        to=[str(t) for t in body.to], sender_name=_name(user), sender_email=user.email, doc=doc, view=view,
        note=body.note, mind_map_png=png_from_data_url(body.mind_map_png), pdf_bytes=pdf,
    )
    msg["X-Unsent"] = "1"  # opens as a draft ready to send in Outlook
    name = (doc.reference_number or "circular").replace("/", "-").replace(" ", "-")
    return Response(
        content=bytes(msg),
        media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="{name}.eml"'},
    )


async def _read_assignments(db: AsyncSession, rows: List[CircularAssignment]) -> List[AssignmentRead]:
    if not rows:
        return []
    doc_ids = {r.document_id for r in rows}
    user_ids = {r.assigned_by_user_id for r in rows} | {r.assignee_user_id for r in rows}
    docs = {d.id: d for d in (await db.execute(select(Document).where(Document.id.in_(doc_ids)))).scalars().all()}
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()}
    out = []
    for r in rows:
        d = docs.get(r.document_id)
        if not d:
            continue
        out.append(AssignmentRead(
            id=r.id, document_id=r.document_id, reference_number=d.reference_number, title=d.title,
            publication_date=d.publication_date, assigned_by_user_id=r.assigned_by_user_id,
            assignee_user_id=r.assignee_user_id, assigned_by_name=_name(users.get(r.assigned_by_user_id)),
            assignee_name=_name(users.get(r.assignee_user_id)), note=r.note, due_date=r.due_date,
            status=r.status, email_status=r.email_status, created_at=r.created_at,
        ))
    return out


@router.post("/assign", response_model=AssignResult, status_code=201)
async def assign(body: AssignRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    await require(db, user, "assign", "Assigning circulars to your team")
    doc = await get_visible_document(db, body.document_id, user)
    if doc.owner_user_id is not None and doc.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Circular not found.")
    org_ids = await _my_org_ids(db, user)
    if not org_ids:
        raise HTTPException(status_code=422, detail="Join your bank's workspace first; then you can assign circulars to your team.")
    members = (await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id.in_(org_ids),
            OrganizationMember.user_id.in_(body.assignee_user_ids),
            OrganizationMember.status == "ACTIVE",
        )
    )).scalars().all()
    org_of = {}
    for m in members:
        org_of.setdefault(m.user_id, m.organization_id)
    missing = [u for u in body.assignee_user_ids if u not in org_of]
    if missing:
        raise HTTPException(status_code=422, detail="You can only assign to people in your own workspace.")

    mail_on = body.send_email and email_configured()
    view = pdf = None
    png = png_from_data_url(body.mind_map_png)
    if mail_on:
        view, pdf = await _parts(db, doc, user, True)
    created: List[CircularAssignment] = []
    emailed = 0
    for uid in dict.fromkeys(body.assignee_user_ids):
        a = CircularAssignment(
            document_id=doc.id, organization_id=org_of[uid], assigned_by_user_id=user.id, assignee_user_id=uid,
            note=(body.note or "").strip() or None, due_date=body.due_date, status="OPEN",
            email_status=None if not body.send_email else ("OFF" if not mail_on else None),
        )
        db.add(a)
        created.append(a)
        if mail_on:
            assignee = await db.get(User, uid)
            msg = build_share_email(
                to=[assignee.email], sender_name=_name(user), sender_email=user.email, doc=doc, view=view,
                note=a.note, mind_map_png=png, pdf_bytes=pdf, assignment_due=body.due_date, is_assignment=True,
            )
            result = await asyncio.to_thread(send_now, msg)
            a.email_status = "SENT" if result.ok else "FAILED"
            emailed += 1 if result.ok else 0
    await db.commit()
    for a in created:
        await db.refresh(a)
    return AssignResult(created=len(created), emailed=emailed, email_off=body.send_email and not mail_on,
                        assignments=await _read_assignments(db, created))


@router.get("/assignments", response_model=List[AssignmentRead])
async def assignments(
    scope: str = Query("mine", pattern="^(mine|by_me|all)$"),
    status: Optional[str] = Query(None, pattern="^(OPEN|DONE)$"),
    document_id: Optional[UUID] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    q = select(CircularAssignment)
    if scope == "mine":
        q = q.where(CircularAssignment.assignee_user_id == user.id)
    elif scope == "by_me":
        q = q.where(CircularAssignment.assigned_by_user_id == user.id)
    else:
        q = q.where(or_(CircularAssignment.assignee_user_id == user.id, CircularAssignment.assigned_by_user_id == user.id))
    if status:
        q = q.where(CircularAssignment.status == status)
    if document_id:
        q = q.where(CircularAssignment.document_id == document_id)
    rows = (await db.execute(q.order_by(CircularAssignment.created_at.desc()).limit(200))).scalars().all()
    return await _read_assignments(db, list(rows))


@router.patch("/assignments/{assignment_id}", response_model=AssignmentRead)
async def update_assignment(assignment_id: UUID, body: AssignmentUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    a = await db.get(CircularAssignment, assignment_id)
    if not a or user.id not in (a.assignee_user_id, a.assigned_by_user_id):
        raise HTTPException(status_code=404, detail="Not found.")
    a.status = body.status
    a.done_at = datetime.now(timezone.utc) if body.status == "DONE" else None
    await db.commit()
    await db.refresh(a)
    return (await _read_assignments(db, [a]))[0]
