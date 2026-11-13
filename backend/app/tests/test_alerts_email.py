"""Alert email: off by default, instant mail, retry and backoff, password safety, daily summary, expiry, test mail."""
import base64
import email as email_lib
import email.policy
import logging
import smtplib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import func, select, update

from backend.app.core.config import settings
from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.alerts import mailer
from backend.app.modules.alerts import router as alerts_router
from backend.app.modules.alerts.digest import build_digests
from backend.app.modules.alerts.dispatch import dispatch_pending
from backend.app.modules.alerts.models import (
    AlertEvent, AlertNotification, AlertPreference, EmailDeliveryAttempt, EmailOutbox,
)
from backend.app.modules.alerts.worker import BACKOFF, send_due_emails
from backend.app.modules.organizations.models import Organization
from backend.app.tests.fake_smtp import FakeSMTP
from backend.app.tests.factories import make_user
from backend.app.tests.test_alerts import H, announce, dispatch, make_ws, notes, published_doc, quiet
from backend.app.tests.test_compliance_workspace import base, one_item, task_for, upload

PASSWORD = "s3cret-test"
USERNAME = "mailer"
AN = AlertNotification


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
async def _fresh():
    alerts_router._last_poll_sweep.clear()
    alerts_router._last_test_email.clear()
    mailer._warned = False
    async with AsyncSessionLocal() as db:
        await db.execute(update(AlertEvent).where(AlertEvent.status == "PENDING").values(status="SUPPRESSED"))
        await db.execute(update(EmailOutbox).where(EmailOutbox.status.in_(["PENDING", "SENDING"])).values(status="EXPIRED"))
        await db.commit()
    yield


def configure(monkeypatch, server, **over):
    values = dict(
        SMTP_HOST="127.0.0.1", SMTP_PORT=server.port, SMTP_FROM="alerts@regwatch.test", SMTP_USERNAME=USERNAME,
        SMTP_PASSWORD=SecretStr(PASSWORD), SMTP_TLS_MODE="none", APP_PUBLIC_URL="http://app.test",
    )
    values.update(over)
    for k, v in values.items():
        monkeypatch.setattr(settings, k, v)


@pytest.fixture
def smtp(monkeypatch):
    servers = []

    def make(mode="ok"):
        s = FakeSMTP(mode).start()
        servers.append(s)
        configure(monkeypatch, s)
        return s

    yield make
    for s in servers:
        s.stop()


async def outbox_for(user, kind=None):
    async with AsyncSessionLocal() as db:
        q = select(EmailOutbox).where(EmailOutbox.user_id == user.id)
        if kind:
            q = q.where(EmailOutbox.kind == kind)
        return list((await db.execute(q.order_by(EmailOutbox.created_at, EmailOutbox.id))).scalars().all())


async def get_row(row_id):
    async with AsyncSessionLocal() as db:
        return await db.get(EmailOutbox, row_id)


async def attempts_of(row_id):
    async with AsyncSessionLocal() as db:
        return list((await db.execute(
            select(EmailDeliveryAttempt).where(EmailDeliveryAttempt.outbox_id == row_id).order_by(EmailDeliveryAttempt.attempt_no)
        )).scalars().all())


async def send(now=None):
    async with AsyncSessionLocal() as db:
        return await send_due_emails(db, now)


def aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


async def queue_one(client):
    """A bank, a task assigned to the analyst, and the instant-email row that makes."""
    ws = await make_ws({"COMPLIANCE_OFFICER": None, "REVIEWER": None, "ANALYST": "A"})
    _rid, items, *_ = await one_item(client, ws)
    t = await task_for(client, ws, items[0]["id"], assignee="ANALYST")
    await dispatch()
    rows = await outbox_for(ws.users["ANALYST"], "INSTANT")
    return ws, items[0]["id"], t["task"]["id"], rows


# ---------------------------------------------------------------------------
# 18. Email off: nothing is sent, nothing is queued, nothing is logged
# ---------------------------------------------------------------------------
async def test_email_off_sends_nothing_and_logs_nothing(client, monkeypatch, caplog):
    def refuse(*a, **k):
        raise AssertionError("A mail connection was opened while email is off.")

    monkeypatch.setattr(smtplib, "SMTP", refuse)
    monkeypatch.setattr(smtplib, "SMTP_SSL", refuse)
    assert settings.SMTP_HOST in ("", None) and settings.SMTP_FROM in ("", None)
    assert mailer.email_configured() is False
    async with AsyncSessionLocal() as db:
        before = (await db.execute(select(func.count(EmailOutbox.id)))).scalar_one()
    caplog.set_level(logging.DEBUG)
    ws = await make_ws({"COMPLIANCE_OFFICER": None, "ANALYST": "A"})
    _rid, items, *_ = await one_item(client, ws)
    await task_for(client, ws, items[0]["id"], assignee="ANALYST")
    u, _t = await make_user()
    doc, _v, _p = await published_doc()
    await announce(doc)
    await dispatch()
    note = (await notes(ws.users["ANALYST"], kind="TASK_ASSIGNED"))[0]
    assert note.email_mode == "INSTANT" and note.emailed_at is None     # chosen, but never queued
    async with AsyncSessionLocal() as db:
        assert await send_due_emails(db) == 0
        assert await build_digests(db, datetime.now(timezone.utc) + timedelta(hours=12)) == 0
        await db.commit()
        after = (await db.execute(select(func.count(EmailOutbox.id)))).scalar_one()
    assert after == before
    # the inbox works the same, the poll says email is off, the test mail is refused
    poll = await client.get("/api/v1/alerts/summary", headers=ws.headers("ANALYST"))
    assert poll.json()["email_configured"] is False and poll.json()["unread_count"] == 1
    admin, admin_token = await make_user(is_superuser=True)
    refused = await client.post("/api/v1/alerts/admin/test-email", headers=H(admin_token))
    assert refused.status_code == 409 and "SMTP_HOST" in refused.json()["detail"]
    bad = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert bad == [], [r.getMessage() for r in bad]
    _ = u


# ---------------------------------------------------------------------------
# 19. Instant email
# ---------------------------------------------------------------------------
async def test_instant_email_is_built_and_sent(client, smtp):
    srv = smtp("ok")
    ws, iid, tid, rows = await queue_one(client)
    analyst = ws.users["ANALYST"]
    assert len(rows) == 1 and rows[0].status == "PENDING"
    assert await send() >= 1
    mine = [m for m in srv.messages if analyst.email in m[1]]
    assert len(mine) == 1 and mine[0][0] == "alerts@regwatch.test" and USERNAME in srv.auth_users
    msg = email_lib.message_from_bytes(mine[0][2], policy=email.policy.default)
    async with AsyncSessionLocal() as db:
        org = await db.get(Organization, uuid.UUID(ws.org_id))
    assert msg["Subject"] == f"[{org.name}] Task assigned to you: Collect proof"
    assert msg["To"] == analyst.email and msg["Auto-Submitted"] == "auto-generated"
    plain = msg.get_body(("plain",)).get_content()
    html_part = msg.get_body(("html",)).get_content()
    link = f"http://app.test/workspace/{ws.org_id}/items/{iid}#task-{tid}"
    footer = "Change them here: http://app.test/alerts/settings"
    assert link in plain and link in html_part and footer in plain
    assert "Open in RegWatch" in html_part
    row = await get_row(rows[0].id)
    assert row.status == "SENT" and row.sent_at is not None and row.attempts == 1
    attempts = await attempts_of(row.id)
    assert [a.outcome for a in attempts] == ["SENT"]
    note = (await notes(analyst, kind="TASK_ASSIGNED"))[0]
    assert note.emailed_at is not None


async def test_instant_email_never_carries_reviewer_comments(client, smtp):
    srv = smtp("ok")
    ws, _iid, tid, rows = await queue_one(client)
    await send()
    assert (await upload(client, ws, tid)).status_code == 201
    secret = "Private reviewer note 7731"
    ch = await client.post(f"{base(ws)}/tasks/{tid}/reviews", headers=ws.headers("REVIEWER"),
                           json={"decision": "CHANGES_REQUESTED", "comments": secret})
    assert ch.status_code == 201, ch.text
    await dispatch()
    note = (await notes(ws.users["ANALYST"], kind="TASK_REVIEWED"))[0]
    assert note.detail == secret                          # in the app only
    await send()
    sent = [m for m in srv.messages if ws.users["ANALYST"].email in m[1]]
    assert len(sent) == 2
    assert all(secret.encode() not in m[2] and b"proof.pdf" not in m[2] for m in sent)
    assert any(b"needs changes" in m[2] for m in sent)


# ---------------------------------------------------------------------------
# 20. Retry and backoff
# ---------------------------------------------------------------------------
async def test_temporary_failure_retries_with_backoff_then_fails(client, smtp):
    srv = smtp("temp_fail")
    ws, _iid, _tid, rows = await queue_one(client)
    rid = rows[0].id
    now = datetime.now(timezone.utc)
    await send(now)
    row = await get_row(rid)
    assert row.status == "PENDING" and row.attempts == 1
    assert abs((aware(row.next_attempt_at) - now).total_seconds() - BACKOFF[0]) < 5
    # not due yet: nothing happens
    assert await send(now + timedelta(seconds=30)) == 0
    assert (await get_row(rid)).attempts == 1
    for n in range(2, settings.ALERTS_EMAIL_MAX_ATTEMPTS + 1):
        now = aware((await get_row(rid)).next_attempt_at) + timedelta(seconds=1)
        await send(now)
        row = await get_row(rid)
        assert row.attempts == n
        if n < settings.ALERTS_EMAIL_MAX_ATTEMPTS:
            assert row.status == "PENDING"
            assert abs((aware(row.next_attempt_at) - now).total_seconds() - BACKOFF[n - 1]) < 5
    assert row.status == "FAILED" and row.last_error
    attempts = await attempts_of(rid)
    assert [a.attempt_no for a in attempts] == list(range(1, settings.ALERTS_EMAIL_MAX_ATTEMPTS + 1))
    assert [a.outcome for a in attempts][:-1] == ["RETRY"] * (settings.ALERTS_EMAIL_MAX_ATTEMPTS - 1)
    assert attempts[-1].outcome == "FAILED" and attempts[-1].smtp_code == 451
    assert srv.messages == []
    # the alert is still in the inbox
    inbox = (await client.get("/api/v1/alerts", headers=ws.headers("ANALYST"))).json()
    assert [a["kind"] for a in inbox["alerts"]] == ["TASK_ASSIGNED"]
    # an administrator can retry it
    admin, admin_token = await make_user(is_superuser=True)
    again = await client.post(f"/api/v1/alerts/admin/outbox/{rid}/retry", headers=H(admin_token))
    assert again.status_code == 200 and again.json()["status"] == "PENDING"
    row = await get_row(rid)
    assert row.status == "PENDING" and row.attempts == 0
    assert (await client.post(f"/api/v1/alerts/admin/outbox/{rid}/retry", headers=H(admin_token))).status_code == 409
    assert (await client.post(f"/api/v1/alerts/admin/outbox/{uuid.uuid4()}/retry", headers=H(admin_token))).status_code == 404
    _ = admin


async def test_permanent_failure_stops_after_one_try(client, smtp):
    smtp("perm_fail")
    ws, _iid, _tid, rows = await queue_one(client)
    await send()
    row = await get_row(rows[0].id)
    assert row.status == "FAILED" and row.attempts == 1
    attempts = await attempts_of(row.id)
    assert [(a.outcome, a.smtp_code) for a in attempts] == [("FAILED", 550)]
    assert len(await notes(ws.users["ANALYST"], kind="TASK_ASSIGNED")) == 1
    assert (await notes(ws.users["ANALYST"], kind="TASK_ASSIGNED"))[0].emailed_at is None


async def test_dropped_connection_is_retried(client, smtp):
    smtp("drop")
    ws, _iid, _tid, rows = await queue_one(client)
    await send()
    row = await get_row(rows[0].id)
    assert row.status == "PENDING" and row.attempts == 1
    assert [a.outcome for a in await attempts_of(row.id)] == ["RETRY"]
    assert len(await notes(ws.users["ANALYST"], kind="TASK_ASSIGNED")) == 1


# ---------------------------------------------------------------------------
# 21. The password never leaks
# ---------------------------------------------------------------------------
def forms():
    return [
        PASSWORD,
        base64.b64encode(PASSWORD.encode()).decode(),
        base64.b64encode(f"\0{USERNAME}\0{PASSWORD}".encode()).decode(),
    ]


async def test_password_never_appears_anywhere(client, smtp, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    srv = smtp("ok")
    admin, admin_token = await make_user(is_superuser=True)
    bodies = []

    # a good send
    ws, _iid, _tid, rows = await queue_one(client)
    await send()
    # a failing connection whose error text contains the password in every form
    f = forms()

    def boom(host, port):
        raise OSError(f"connect failed, auth {f[0]} / {f[1]} / {f[2]}")

    real_open = mailer._open
    monkeypatch.setattr(mailer, "_open", boom)
    ws2, _i2, _t2, rows2 = await queue_one(client)
    await send()
    row = await get_row(rows2[0].id)
    assert row.status == "PENDING" and "***" in row.last_error
    attempt = (await attempts_of(row.id))[0]
    assert "***" in attempt.error

    # status and test mail (the test mail goes through the same failing path, then the real one)
    r1 = await client.get("/api/v1/alerts/admin/email-status", headers=H(admin_token))
    assert r1.status_code == 200
    bodies.append(r1.text)
    data = r1.json()
    assert data["password_set"] is True and data["username_set"] is True and "password" not in data
    r2 = await client.post("/api/v1/alerts/admin/test-email", headers=H(admin_token))
    bodies.append(r2.text)
    assert r2.json()["ok"] is False
    monkeypatch.setattr(mailer, "_open", real_open)
    alerts_router._last_test_email.clear()
    r3 = await client.post("/api/v1/alerts/admin/test-email", headers=H(admin_token))
    bodies.append(r3.text)
    assert r3.json()["ok"] is True
    bodies.append((await client.get("/api/v1/alerts/admin/outbox", headers=H(admin_token))).text)

    async with AsyncSessionLocal() as db:
        stored = [r[0] or "" for r in (await db.execute(select(EmailOutbox.last_error))).all()]
        stored += [r[0] or "" for r in (await db.execute(select(EmailDeliveryAttempt.error))).all()]
    haystacks = bodies + stored + [r.getMessage() for r in caplog.records]
    for text in haystacks:
        for secret in f:
            assert secret not in text
    _ = (ws, rows)


# ---------------------------------------------------------------------------
# 22. Daily summary
# ---------------------------------------------------------------------------
async def test_daily_summary(client, smtp):
    smtp("ok")
    user, _t = await make_user()
    now_before = datetime(2031, 5, 5, 4, 0, tzinfo=timezone.utc)   # 10:00 in Dhaka
    now_after = datetime(2031, 5, 5, 5, 0, tzinfo=timezone.utc)    # 11:00 in Dhaka
    async with AsyncSessionLocal() as db:
        ids = []
        for i in range(2):
            n = AN(user_id=user.id, kind="CIRCULAR_PUBLISHED", group="library", dedupe_key=f"digest-test:{uuid.uuid4()}",
                   severity="info", title=f"New circular: DIG-{i}", body="Body.", link=f"/?doc={uuid.uuid4()}",
                   in_app=True, email_mode="DIGEST", created_at=now_before - timedelta(hours=2 + i))
            db.add(n)
            await db.flush()
            ids.append(n.id)
        read = await db.get(AN, ids[1])
        read.read_at = now_before - timedelta(hours=1)
        await db.commit()
    async with AsyncSessionLocal() as db:
        assert await build_digests(db, now_before) == 0
        await db.commit()
    assert await outbox_for(user, "DIGEST") == []
    async with AsyncSessionLocal() as db:
        assert await build_digests(db, now_after) >= 1
        await db.commit()
    rows = await outbox_for(user, "DIGEST")
    assert len(rows) == 1 and rows[0].dedupe_key == f"digest:{user.id}:2031-05-05"
    assert rows[0].notification_ids == [str(ids[0])]
    assert rows[0].subject == "RegWatch daily summary: 1 alert" and "DIG-0" in rows[0].text_body
    assert "DIG-1" not in rows[0].text_body
    async with AsyncSessionLocal() as db:
        assert await build_digests(db, now_after + timedelta(hours=1)) == 0     # one a day
        await db.commit()
    assert len(await outbox_for(user, "DIGEST")) == 1
    async with AsyncSessionLocal() as db:
        unread = await db.get(AN, ids[0])
        was_read = await db.get(AN, ids[1])
        assert unread.emailed_at is not None and was_read.emailed_at is None


# ---------------------------------------------------------------------------
# 23. Old unsent mail expires
# ---------------------------------------------------------------------------
async def test_old_pending_mail_expires_and_is_never_sent(client, smtp):
    srv = smtp("ok")
    user, _t = await make_user()
    async with AsyncSessionLocal() as db:
        row = EmailOutbox(
            user_id=user.id, to_address=user.email, kind="INSTANT", dedupe_key=f"instant:{uuid.uuid4()}",
            notification_ids=[], subject="Old", text_body="old", html_body="<p>old</p>", status="PENDING",
            attempts=0, next_attempt_at=datetime.now(timezone.utc) - timedelta(hours=50),
            created_at=datetime.now(timezone.utc) - timedelta(hours=settings.ALERTS_EMAIL_MAX_AGE_HOURS + 1),
        )
        db.add(row)
        await db.commit()
        rid = row.id
    await send()
    assert (await get_row(rid)).status == "EXPIRED"
    assert srv.messages == [] and await attempts_of(rid) == []


# ---------------------------------------------------------------------------
# 24. Test email
# ---------------------------------------------------------------------------
async def test_test_email_goes_only_to_the_caller(client, smtp):
    srv = smtp("ok")
    admin, admin_token = await make_user(is_superuser=True)
    normal, normal_token = await make_user()
    assert (await client.post("/api/v1/alerts/admin/test-email", headers=H(normal_token))).status_code == 403
    ok = await client.post("/api/v1/alerts/admin/test-email", headers=H(admin_token))
    assert ok.status_code == 200 and ok.json()["ok"] is True and admin.email in ok.json()["detail"]
    assert [m[1] for m in srv.messages] == [[admin.email]]
    msg = email_lib.message_from_bytes(srv.messages[0][2], policy=email.policy.default)
    assert msg["Subject"] == "RegWatch test email"
    assert "Email from RegWatch works." in msg.get_body(("plain",)).get_content()
    again = await client.post("/api/v1/alerts/admin/test-email", headers=H(admin_token))
    assert again.status_code == 429
    rows = await outbox_for(admin, "TEST")
    assert len(rows) == 1 and rows[0].status == "SENT"
    # the outbox list never shows subject, body or the full address
    listing = await client.get("/api/v1/alerts/admin/outbox", headers=H(admin_token), params={"status": "SENT"})
    assert listing.status_code == 200
    row = [r for r in listing.json()["rows"] if r["id"] == str(rows[0].id)][0]
    assert row["to_masked"] == f"{admin.email[0]}***@example.test"
    assert not ({"subject", "text_body", "html_body", "to_address"} & set(row))
    assert (await client.get("/api/v1/alerts/admin/outbox", headers=H(normal_token))).status_code == 403
    assert (await client.get("/api/v1/alerts/admin/email-status", headers=H(normal_token))).status_code == 403
    status = (await client.get("/api/v1/alerts/admin/email-status", headers=H(admin_token))).json()
    assert status["configured"] is True and status["host"] == "127.0.0.1" and status["from_address"] == "alerts@regwatch.test"
    assert status["outbox"]["sent_24h"] >= 1 and status["worker_running"] is False


# ---------------------------------------------------------------------------
# 25. Plain mail is refused in production unless the relay is local
# ---------------------------------------------------------------------------
def test_production_plain_smtp_guard(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_FROM", "alerts@regwatch.test")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SMTP_TLS_MODE", "none")
    monkeypatch.setattr(settings, "SMTP_HOST", "mail.example.com")
    assert mailer.email_configured() is False
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    assert mailer.email_configured() is True
    monkeypatch.setattr(settings, "SMTP_HOST", "mail.example.com")
    monkeypatch.setattr(settings, "SMTP_TLS_MODE", "starttls")
    assert mailer.email_configured() is True
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "SMTP_TLS_MODE", "none")
    assert mailer.email_configured() is True
    monkeypatch.setattr(settings, "SMTP_FROM", "")
    assert mailer.email_configured() is False


def test_headers_cannot_be_injected(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_FROM", "alerts@regwatch.test")
    msg = mailer.build_message("a@b.test\r\nBcc: x@y.test", "Hello\r\nBcc: z@y.test", "text", "<p>html</p>")
    assert msg["Bcc"] is None and "\n" not in str(msg["Subject"]) and "\n" not in str(msg["To"])
    assert msg["List-Unsubscribe"].endswith("/alerts/settings>")
