"""Pre-launch security review (VAPT): one regression test for each fix.

Covers sign-in brute force and sign-up limits, the bcrypt length bug, sessions ending on a password reset,
login timing, API docs off in production, admin-only progress page, limits on Ask / email / uploads /
listings, page pictures that cannot fill the memory, the page-reader queue order, browser-only caching
of signed-in files, and the storage folder boundary.
"""
import io
import os
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import update

from backend.app.core.config import settings
from backend.app.core.ratelimit import RateLimiter
from backend.app.core.security import get_password_hash
from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.identity.models import User
from backend.app.tests.factories import make_institution, make_user
from backend.app.tests.fake_smtp import FakeSMTP

API = "/api/v1"
REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


def _pdf(width: float = 595, height: float = 842, text: str = "Banks shall keep records.") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    page.insert_text((72, 72), f"{text} {uuid.uuid4().hex[:6]}", fontname="helv", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


# --------------------------------------------------------------------------- limiter itself
def test_rate_limiter_counts_inside_its_window_only(monkeypatch):
    import backend.app.core.ratelimit as rl

    now = [1000.0]
    monkeypatch.setattr(rl.time, "monotonic", lambda: now[0])
    lim = RateLimiter()
    assert all(lim.allow("k", 3, 60) for _ in range(3))
    assert not lim.allow("k", 3, 60)
    assert lim.allow("other", 3, 60)  # keys are separate
    now[0] += 61
    assert lim.allow("k", 3, 60)  # the window moved on
    assert not lim.allow("k", 3, 60, cost=3)  # a cost larger than what is left is refused


# --------------------------------------------------------------------------- sign-in and sign-up
class _Acct:
    def __init__(self, email):
        self.email = email


async def _account(client) -> "_Acct":
    """A user created through sign-up (password Password123!), so it can also sign in through the API."""
    from backend.app.core.ratelimit import limiter

    email = f"acct_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(f"{API}/auth/register", json={"email": email, "password": "Password123!", "full_name": "A"})
    assert r.status_code == 201, r.text
    limiter.reset()  # the sign-up itself is not what the test counts
    return _Acct(email)


@pytest.mark.asyncio
async def test_wrong_passwords_for_one_account_are_limited(client):
    user = await _account(client)
    other = await _account(client)
    for _ in range(20):
        r = await client.post(f"{API}/auth/login", json={"email": user.email, "password": "wrong-password"})
        assert r.status_code == 401
    # Even the right password now waits, so guessing cannot go on.
    r = await client.post(f"{API}/auth/login", json={"email": user.email, "password": "Password123!"})
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    # Another account is not affected.
    r = await client.post(f"{API}/auth/login", json={"email": other.email, "password": "Password123!"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_a_few_wrong_passwords_do_not_block_the_real_user(client):
    user = await _account(client)
    for _ in range(5):
        await client.post(f"{API}/auth/login", json={"email": user.email, "password": "typo"})
    r = await client.post(f"{API}/auth/login", json={"email": user.email, "password": "Password123!"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_sign_in_attempts_from_one_address_are_limited(client):
    for i in range(30):
        r = await client.post(f"{API}/auth/login", json={"email": f"nobody{i}@example.com", "password": "x"})
        assert r.status_code == 401
    r = await client.post(f"{API}/auth/login", json={"email": "nobody-last@example.com", "password": "x"})
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_successful_sign_ins_from_one_office_are_not_limited(client):
    user = await _account(client)
    for _ in range(31):  # more than the failed-attempt limit for one address
        r = await client.post(f"{API}/auth/login", json={"email": user.email, "password": "Password123!"})
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_sign_ups_from_one_address_are_limited(client, monkeypatch):
    import backend.app.modules.identity.router as identity_router

    assert identity_router.REGISTER_PER_IP == (30, 3600)
    monkeypatch.setattr(identity_router, "REGISTER_PER_IP", (3, 3600))
    for i in range(3):
        r = await client.post(f"{API}/auth/register", json={
            "email": f"new_{uuid.uuid4().hex[:8]}@example.com", "password": "Password123!", "full_name": "N"})
        assert r.status_code == 201, r.text
    r = await client.post(f"{API}/auth/register", json={
        "email": f"new_{uuid.uuid4().hex[:8]}@example.com", "password": "Password123!", "full_name": "N"})
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_password_longer_than_bcrypt_allows_is_a_clear_error_not_a_crash(client):
    r = await client.post(f"{API}/auth/register", json={
        "email": f"long_{uuid.uuid4().hex[:8]}@example.com", "password": "a" * 73, "full_name": "Long"})
    assert r.status_code == 422
    # 72 bytes is still fine.
    r = await client.post(f"{API}/auth/register", json={
        "email": f"long_{uuid.uuid4().hex[:8]}@example.com", "password": "a" * 72, "full_name": "Long"})
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_unknown_email_still_spends_a_password_check(client, monkeypatch):
    import backend.app.modules.identity.router as identity_router

    calls = []
    monkeypatch.setattr(identity_router, "burn_password_check", lambda pw: calls.append(pw))
    r = await client.post(f"{API}/auth/login", json={"email": f"ghost_{uuid.uuid4().hex[:6]}@example.com", "password": "pw"})
    assert r.status_code == 401
    assert calls == ["pw"]


@pytest.mark.asyncio
async def test_password_reset_ends_old_sessions(client):
    email = f"reset_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(f"{API}/auth/register", json={"email": email, "password": "Password123!", "full_name": "R"})
    token = r.json()["access_token"]
    assert (await client.get(f"{API}/auth/me", headers=_auth(token))).status_code == 200
    async with AsyncSessionLocal() as db:  # what manage_accounts.py reset-password does
        await db.execute(update(User).where(User.email == email).values(hashed_password=get_password_hash("NewPassword456!")))
        await db.commit()
    assert (await client.get(f"{API}/auth/me", headers=_auth(token))).status_code == 401
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": "NewPassword456!"})
    assert (await client.get(f"{API}/auth/me", headers=_auth(r.json()["access_token"]))).status_code == 200


@pytest.mark.asyncio
async def test_deactivated_account_token_stops_working(client):
    user, token = await make_user()
    async with AsyncSessionLocal() as db:
        await db.execute(update(User).where(User.id == user.id).values(is_active=False))
        await db.commit()
    assert (await client.get(f"{API}/auth/me", headers=_auth(token))).status_code == 403
    assert (await client.get(f"{API}/documents", headers=_auth(token))).status_code == 403


@pytest.mark.asyncio
async def test_tokens_signed_with_another_key_or_none_algorithm_are_refused(client):
    import jwt

    user, _ = await make_user()
    forged = jwt.encode({"sub": str(user.id)}, "not-the-server-key-0123456789abcdef0123", algorithm="HS256")
    none_alg = jwt.encode({"sub": str(user.id)}, None, algorithm="none")
    for t in (forged, none_alg):
        assert (await client.get(f"{API}/auth/me", headers=_auth(t))).status_code == 401


# --------------------------------------------------------------------------- information leaks
def test_api_docs_are_off_in_production():
    code = (
        "import asyncio\n"
        "from httpx import ASGITransport, AsyncClient\n"
        "from backend.app.main import app\n"
        "async def main():\n"
        "    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://t') as c:\n"
        "        print([(await c.get(p)).status_code for p in ('/api/v1/openapi.json', '/api/v1/docs', '/api/v1/redoc', '/api/v1/health')])\n"
        "asyncio.run(main())\n"
    )
    env = dict(os.environ, ENVIRONMENT="production", SECRET_KEY="x" * 64, SEED_ON_STARTUP="false", SCHEDULER_ENABLED="false")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "[404, 404, 404, 200]"


@pytest.mark.asyncio
async def test_api_docs_still_work_in_development(client):
    assert (await client.get(f"{API}/openapi.json")).status_code == 200


@pytest.mark.asyncio
async def test_progress_summary_is_for_administrators_only(client):
    _u, reader = await make_user()
    _a, admin = await make_user(is_superuser=True)
    assert (await client.get(f"{API}/summary", headers=_auth(reader))).status_code == 403
    assert (await client.get(f"{API}/summary", headers=_auth(admin))).status_code == 200


# --------------------------------------------------------------------------- abuse limits
@pytest.mark.asyncio
async def test_source_listings_cannot_ask_for_everything(client):
    _u, token = await make_user()
    for path in ("/sources/runs", "/sources/discoveries"):
        assert (await client.get(f"{API}{path}", params={"limit": -1}, headers=_auth(token))).status_code == 422
        assert (await client.get(f"{API}{path}", params={"limit": 100000}, headers=_auth(token))).status_code == 422
        assert (await client.get(f"{API}{path}", params={"limit": 50}, headers=_auth(token))).status_code == 200


@pytest.mark.asyncio
async def test_ask_has_a_length_cap_and_a_per_person_rate(client, monkeypatch):
    import backend.app.modules.research.router as research_router
    from backend.app.modules.research.service import ResearchService

    _u, token = await make_user()
    r = await client.post(f"{API}/research/query", json={"query": "x" * 4001}, headers=_auth(token))
    assert r.status_code == 422

    async def fake_answer(**kwargs):
        return {"query": kwargs["query"], "answer": "ok", "is_grounded": True, "citations": []}

    monkeypatch.setattr(ResearchService, "query_regulatory_knowledge", staticmethod(fake_answer))
    monkeypatch.setattr(research_router, "QUESTIONS_PER_USER", (2, 600))
    codes = [(await client.post(f"{API}/research/query", json={"query": "liquidity ratio"}, headers=_auth(token))).status_code
             for _ in range(3)]
    assert codes[2] == 429 and codes[0] != 429 and codes[1] != 429
    _other, other_token = await make_user()  # per person, not for everyone
    r = await client.post(f"{API}/research/query", json={"query": "liquidity ratio"}, headers=_auth(other_token))
    assert r.status_code != 429


@pytest.fixture
def mail(monkeypatch):
    s = FakeSMTP("ok").start()
    for k, v in dict(SMTP_HOST="127.0.0.1", SMTP_PORT=s.port, SMTP_FROM="alerts@regwatch.test", SMTP_USERNAME=None,
                     SMTP_PASSWORD=None, SMTP_TLS_MODE="none", APP_PUBLIC_URL="http://app.test").items():
        monkeypatch.setattr(settings, k, v)
    yield s
    s.stop()


@pytest.mark.asyncio
async def test_emailing_a_circular_is_capped_per_person(client, mail, monkeypatch):
    import backend.app.modules.share.router as share_router
    from backend.app.tests.test_search_and_ask import make_real_doc

    monkeypatch.setattr(share_router, "EMAIL_RECIPIENTS_PER_USER", (5, 3600))
    _u, token = await make_user()
    doc, _ = await make_real_doc(["Banks shall keep records."], reference=f"DOS Circular No. {uuid.uuid4().hex[:4]}")
    body = {"document_id": str(doc.id), "to": ["a@example.com", "b@example.com"], "attach_pdf": False}
    codes = [(await client.post(f"{API}/share/email", json=body, headers=_auth(token))).status_code for _ in range(3)]
    assert codes == [200, 200, 429]  # 2 + 2 people sent, the next 2 would pass 5
    assert len(mail.messages) == 2


@pytest.mark.asyncio
async def test_private_uploads_are_capped_per_person(client, monkeypatch):
    import backend.app.modules.documents.router as documents_router

    monkeypatch.setattr(documents_router, "PRIVATE_UPLOADS_PER_USER", (1, 3600))
    inst = await make_institution()
    _u, token = await make_user()

    async def upload():
        return await client.post(
            f"{API}/documents/upload",
            files={"file": ("c.pdf", _pdf(), "application/pdf")},
            data={"institution_id": str(inst.id), "title": "My circular", "publication_date": "2026-01-01"},
            headers=_auth(token),
        )

    assert (await upload()).status_code == 201
    assert (await upload()).status_code == 429


# --------------------------------------------------------------------------- PDF pages that would fill the memory
def test_capped_dpi_only_touches_absurd_pages():
    from backend.app.modules.extraction.vision import MAX_RENDER_PIXELS, capped_dpi

    doc = pymupdf.open(stream=_pdf(), filetype="pdf")
    a4 = doc[0]
    assert capped_dpi(a4, 300) == 300 and capped_dpi(a4, 192) == 192
    big = pymupdf.open(stream=_pdf(14400, 14400), filetype="pdf")[0]  # 200 x 200 inches, the PDF maximum
    dpi = capped_dpi(big, 192)
    assert dpi < 192 and (200 * dpi) ** 2 <= MAX_RENDER_PIXELS


def test_page_picture_of_a_huge_page_stays_small():
    from backend.app.modules.documents.page_images import render_page_image
    from backend.app.modules.extraction.vision import MAX_RENDER_PIXELS, render_page_png

    data = render_page_image(_pdf(14400, 14400), 1, 192, "png")
    w, h = Image.open(io.BytesIO(data)).size
    assert w * h <= MAX_RENDER_PIXELS
    w, h = Image.open(io.BytesIO(render_page_png(_pdf(14400, 14400), 1, 300))).size
    assert w * h <= MAX_RENDER_PIXELS
    # An ordinary A4 page keeps its exact size.
    w, h = Image.open(io.BytesIO(render_page_image(_pdf(), 1, 144, "png"))).size
    assert (w, h) == (1190, 1684)


# --------------------------------------------------------------------------- page-reader queue order
@pytest.mark.asyncio
async def test_page_reader_reads_shared_circulars_before_private_uploads():
    from backend.app.core.storage import storage_service
    from backend.app.modules.extraction.service import STATUS_PENDING_VISION
    from backend.app.modules.extraction.vision import VisionResult
    from backend.app.modules.extraction.vision_jobs import process_pending_vision_pages

    inst = await make_institution()
    owner, _ = await make_user()
    sizes = {}
    async with AsyncSessionLocal() as db:
        for label, owner_id, when, width in (("private", owner.id, date(2099, 12, 31), 500), ("shared", None, date(2099, 1, 1), 300)):
            path, sha, size = storage_service.store_file("originals", "t", _pdf(width, width))
            doc = Document(institution_id=inst.id, title=f"{label} {uuid.uuid4().hex[:6]}", publication_date=when,
                           publication_status="EXTRACTED", owner_user_id=owner_id)
            db.add(doc)
            await db.flush()
            v = DocumentVersion(document_id=doc.id, version_number=1, file_sha256=sha, file_size_bytes=size,
                                storage_path=path, page_count=1)
            db.add(v)
            await db.flush()
            doc.current_version_id = v.id
            db.add(DocumentPage(document_version_id=v.id, page_number=1, raw_text="", cleaned_text="",
                                quality_status=STATUS_PENDING_VISION, is_human_corrected=False))
            sizes[label] = round(width / 72 * settings.VISION_DPI)
        await db.commit()

    seen = []

    async def reader(png: bytes):
        seen.append(Image.open(io.BytesIO(png)).size[0])
        return VisionResult(success=False, error="test", transient=True)

    async with AsyncSessionLocal() as db:
        await process_pending_vision_pages(db, limit=1, reader=reader)
    # The private upload dated later did not jump the queue (pictures: shared ~834 px wide, private ~1389 px).
    assert len(seen) == 1 and abs(seen[0] - sizes["shared"]) <= 2


# --------------------------------------------------------------------------- caching and storage
@pytest.mark.asyncio
async def test_signed_in_pdf_is_cached_by_the_browser_only(client):
    _a, admin = await make_user(is_superuser=True)
    inst = await make_institution()
    r = await client.post(
        f"{API}/documents/upload",
        files={"file": ("c.pdf", _pdf(), "application/pdf")},
        data={"institution_id": str(inst.id), "title": "Shared circular", "publication_date": "2026-01-01"},
        headers=_auth(admin),
    )
    assert r.status_code == 201, r.text
    doc_id = r.json()["document"]["id"]
    _u, reader = await make_user()
    pdf = await client.get(f"{API}/documents/{doc_id}/pdf", headers=_auth(reader))
    assert pdf.status_code == 200
    assert pdf.headers["cache-control"] == "private, max-age=86400"
    assert "public" not in pdf.headers["cache-control"]


def test_storage_paths_cannot_leave_the_storage_folder(tmp_path):
    from backend.app.core.storage import LocalStorageService

    root = tmp_path / "storage"
    svc = LocalStorageService(str(root))
    (tmp_path / "secret.txt").write_text("secret")
    rel, _sha, _n = svc.store_file("originals", "x", b"%PDF-1.4 ok", ".pdf")
    assert svc.get_file_bytes(rel) == b"%PDF-1.4 ok"
    assert svc.get_file_bytes(rel.replace("/", "\\")) == b"%PDF-1.4 ok"  # saved on Windows
    for bad in ("../secret.txt", "..\\secret.txt", "originals/../../secret.txt", "originals\\..\\..\\secret.txt",
                str(tmp_path / "secret.txt"), "/etc/passwd"):
        with pytest.raises(PermissionError):
            svc.get_file_bytes(bad)
        with pytest.raises(PermissionError):
            svc.get_absolute_path(bad)
        assert svc.file_exists(bad) is False
