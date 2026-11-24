"""Reader emails approved by the owner on 2026-11-25: welcome, password reset, the branded daily digest and
one-click unsubscribe (RFC 8058). Templates are in brand.py.

Tokens are signed with SECRET_KEY, so nothing extra is stored:
- unsubscribe: "<user id>.<signature>"; it never expires and only turns the daily digest off.
- password reset: "<user id>.<expiry>.<signature>"; the signature covers the current password hash, so the link
  stops working once the password is changed (single use) or after RESET_MINUTES.
"""
import base64
import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.modules.alerts import brand, mailer
from backend.app.modules.alerts.models import AlertPreference, EmailOutbox

RESET_MINUTES = 60
# Outbox kinds that come from insights@ (the rest come from alerts@).
INSIGHTS_KINDS = {"DIGEST", "WELCOME"}
# Outbox kinds that carry the one-click unsubscribe header (the digest and new-circular alerts).
UNSUB_KINDS = {"DIGEST", "INSTANT"}


def _key() -> bytes:
    return (settings.SECRET_KEY or "dev-only").encode()


def _sig(text: str, n: int = 32) -> str:
    return base64.urlsafe_b64encode(hmac.new(_key(), text.encode(), hashlib.sha256).digest()).decode().rstrip("=")[:n]


def base_url() -> str:
    return (settings.APP_PUBLIC_URL or "https://amarcircular.com").rstrip("/")


# ------------------------------------------------------------------------------------------------ unsubscribe


def unsubscribe_token(user_id) -> str:
    uid = str(user_id)
    return f"{uid}.{_sig('unsub:' + uid, 24)}"


def read_unsubscribe_token(token: str) -> Optional[str]:
    uid, _, sig = (token or "").partition(".")
    if not uid or not sig or not hmac.compare_digest(sig, _sig("unsub:" + uid, 24)):
        return None
    return uid


def unsubscribe_page_url(user_id) -> str:
    """The link in the email footer: a page that confirms, then turns the digest off."""
    return f"{base_url()}/u/{unsubscribe_token(user_id)}"


def unsubscribe_post_url(user_id) -> str:
    """The List-Unsubscribe URL mail apps POST to (one click, no page)."""
    return f"{base_url()}/api/v1/email/unsubscribe/{unsubscribe_token(user_id)}"


async def unsubscribe(db: AsyncSession, user_id: str) -> None:
    """Turns the daily digest of new circulars off for one person (the "library" alert group)."""
    pref = (await db.execute(select(AlertPreference).where(AlertPreference.user_id == user_id))).scalar_one_or_none()
    if pref is None:
        pref = AlertPreference(user_id=user_id, channels={}, email_enabled=True,
                               library_department_codes=[], library_document_types=[], library_keywords=[])
        db.add(pref)
    channels = dict(pref.channels or {})
    library = dict(channels.get("library") or {})
    library["email"] = "OFF"
    channels["library"] = library
    pref.channels = channels
    pref.lock_version = (pref.lock_version or 1) + 1
    await db.commit()


# ------------------------------------------------------------------------------------------------ password reset


def reset_token(user) -> str:
    exp = int(time.time()) + RESET_MINUTES * 60
    uid = str(user.id)
    return f"{uid}.{exp}.{_sig(f'reset:{uid}:{exp}:{user.hashed_password}')}"


def parse_reset_token(token: str) -> Optional[Tuple[str, int, str]]:
    parts = (token or "").split(".")
    if len(parts) != 3 or not parts[1].isdigit():
        return None
    return parts[0], int(parts[1]), parts[2]


def reset_token_valid(token: str, user) -> bool:
    parsed = parse_reset_token(token)
    if not parsed or user is None:
        return False
    uid, exp, sig = parsed
    if uid != str(user.id) or exp < int(time.time()):
        return False
    return hmac.compare_digest(sig, _sig(f"reset:{uid}:{exp}:{user.hashed_password}"))


# ------------------------------------------------------------------------------------------------ queueing


def _queue(db: AsyncSession, user, kind: str, key: str, email: brand.Email) -> None:
    db.add(EmailOutbox(
        user_id=user.id, organization_id=None, to_address=user.email, kind=kind, dedupe_key=key,
        notification_ids=[], subject=email.subject, text_body=email.text, html_body=email.html,
        status="PENDING", attempts=0, next_attempt_at=datetime.now(timezone.utc),
    ))


def queue_welcome(db: AsyncSession, user) -> None:
    """After sign-up step 1. Does nothing while email is off. Caller commits."""
    if not mailer.email_configured() or not user.email:
        return
    first = (user.full_name or "").split(" ")[0] or None
    _queue(db, user, "WELCOME", f"welcome:{user.id}", brand.welcome(base_url(), first))


def queue_reset(db: AsyncSession, user) -> None:
    """A password-reset email. One per user per minute (dedupe key). Caller commits."""
    if not mailer.email_configured() or not user.email:
        return
    url = f"{base_url()}/reset-password?token={reset_token(user)}"
    _queue(db, user, "RESET", f"reset:{user.id}:{int(time.time()) // 60}", brand.password_reset(base_url(), url, RESET_MINUTES))


def sender_for(kind: str) -> Tuple[str, str]:
    """(name, address). Names are the approved ones; addresses come from settings (SMTP_FROM for the digest and
    welcome, SMTP_ALERTS_FROM for alerts and resets), so test and development servers never send as the live site."""
    if kind in INSIGHTS_KINDS:
        return brand.INSIGHTS_FROM[0], settings.SMTP_FROM or brand.INSIGHTS_FROM[1]
    return brand.ALERTS_FROM[0], settings.SMTP_ALERTS_FROM or settings.SMTP_FROM or brand.ALERTS_FROM[1]
