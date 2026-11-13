"""Sending email with the standard library only. Email is off unless SMTP_HOST and SMTP_FROM are set.

The password is a SecretStr. It is never logged, returned or stored in an error text: every error
goes through redact() first.
"""
import base64
import smtplib
import socket
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Optional

from backend.app.core.config import settings
from backend.app.core.logging import logger

LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
_warned = False


def email_configured() -> bool:
    if not (settings.SMTP_HOST and settings.SMTP_FROM):
        return False
    if (settings.is_production and settings.SMTP_TLS_MODE == "none"
            and settings.SMTP_HOST.strip().lower() not in LOCAL_HOSTS):
        global _warned
        if not _warned:
            _warned = True
            logger.warning("Email is off: plain SMTP is only allowed to a local relay.")
        return False
    return True


def _password() -> Optional[str]:
    pw = settings.SMTP_PASSWORD
    value = pw.get_secret_value() if pw is not None else ""
    return value or None


def redact(text) -> str:
    """Removes the password (and its base64 forms) from a text, then cuts it to 500 characters."""
    out = str(text or "")
    pw = _password()
    if pw:
        user = settings.SMTP_USERNAME or ""
        forms = {
            pw,
            base64.b64encode(pw.encode()).decode(),
            base64.b64encode(f"\0{user}\0{pw}".encode()).decode(),
            base64.b64encode(f"{user}\0{user}\0{pw}".encode()).decode(),
        }
        for form in sorted(forms, key=len, reverse=True):
            if form:
                out = out.replace(form, "***")
    return out[:500]


def _clean_header(value: str) -> str:
    return str(value or "").replace("\r", "").replace("\n", "")


def build_message(to: str, subject: str, text: str, html: str) -> EmailMessage:
    sender = _clean_header(settings.SMTP_FROM or "")
    domain = sender.split("@", 1)[1] if "@" in sender else None
    msg = EmailMessage()
    msg["From"] = formataddr((_clean_header(settings.SMTP_FROM_NAME), sender))
    msg["To"] = _clean_header(to)
    msg["Subject"] = _clean_header(subject)
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=domain)
    msg["Auto-Submitted"] = "auto-generated"
    msg["List-Unsubscribe"] = f"<{settings.APP_PUBLIC_URL}/alerts/settings>"
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def _open(host: str, port: int):
    """Opens one connection. A single place the tests can replace."""
    timeout = settings.SMTP_TIMEOUT_SECONDS
    mode = settings.SMTP_TLS_MODE
    if mode == "ssl":
        return smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context())
    smtp = smtplib.SMTP(host, port, timeout=timeout)
    smtp.ehlo()
    if mode == "starttls":
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
    return smtp


@dataclass
class SendResult:
    ok: bool
    outcome: str  # SENT, RETRY, FAILED
    smtp_code: Optional[int] = None
    error: Optional[str] = None
    message_id: Optional[str] = None


def send_now(msg: EmailMessage) -> SendResult:
    """Sends one message. Never raises."""
    smtp = None
    try:
        smtp = _open(settings.SMTP_HOST, settings.SMTP_PORT)
        pw = _password()
        if settings.SMTP_USERNAME and pw:
            smtp.login(settings.SMTP_USERNAME, pw)
        smtp.send_message(msg)
        return SendResult(True, "SENT", 250, None, msg["Message-ID"])
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as exc:
        code = getattr(exc, "smtp_code", None)
        if code is None and isinstance(exc, smtplib.SMTPRecipientsRefused):
            codes = [v[0] for v in exc.recipients.values()]
            code = codes[0] if codes else None
        retry = code is not None and 400 <= int(code) < 500
        return SendResult(False, "RETRY" if retry else "FAILED", code, redact(f"{type(exc).__name__}: {exc}"))
    except smtplib.SMTPConnectError as exc:
        return SendResult(False, "RETRY", getattr(exc, "smtp_code", None), redact(f"{type(exc).__name__}: {exc}"))
    except smtplib.SMTPAuthenticationError as exc:
        # The administrator may fix the password, so this is worth another try later.
        return SendResult(False, "RETRY", getattr(exc, "smtp_code", None), redact(f"{type(exc).__name__}: {exc}"))
    except smtplib.SMTPResponseException as exc:
        code = exc.smtp_code
        outcome = "FAILED" if 500 <= code < 600 else "RETRY"
        return SendResult(False, outcome, code, redact(f"{type(exc).__name__}: {exc.smtp_error!r}"))
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, socket.timeout, TimeoutError, OSError,
            ssl.SSLError) as exc:
        return SendResult(False, "RETRY", None, redact(f"{type(exc).__name__}: {exc}"))
    except Exception as exc:  # anything unexpected: try again later, keep the class name only
        return SendResult(False, "RETRY", None, redact(type(exc).__name__))
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                pass
