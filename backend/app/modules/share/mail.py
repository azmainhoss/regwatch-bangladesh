"""The email that carries a circular to someone: its checked summary, what banks must do, key dates,
the mind map picture, and the original PDF attached.

Only points shown to readers (they passed every check) go into the email, so the email never says
more than the screen does.
"""
import base64
import html
import re
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Any, Dict, List, Optional

from backend.app.core.config import settings


def _fmt(d: Optional[str]) -> str:
    if not d:
        return ""
    try:
        return date.fromisoformat(str(d)[:10]).strftime("%d %b %Y").lstrip("0")
    except ValueError:
        return str(d)


def _readable(v: Optional[str]) -> str:
    return (v or "").replace("_", " ").capitalize()


def png_from_data_url(data_url: Optional[str]) -> Optional[bytes]:
    """The bytes of a "data:image/png;base64,..." picture, or None. At most 6 MB."""
    if not data_url:
        return None
    m = re.match(r"^data:image/png;base64,([A-Za-z0-9+/=\s]+)$", data_url.strip())
    if not m:
        return None
    raw = base64.b64decode(m.group(1))
    if not raw.startswith(b"\x89PNG") or len(raw) > 6 * 1024 * 1024:
        return None
    return raw


def points(view: Dict[str, Any]) -> Dict[str, List[str]]:
    s = view.get("sections") or {}
    out = {
        "summary": [i["fields"].get("text", "") for i in s.get("summary", [])],
        "changes": [i["fields"].get("text", "") for i in s.get("changes", [])],
        "requirements": [],
        "dates": [],
    }
    for i in s.get("requirements", []):
        f = i.get("fields", {})
        dl = _fmt(f.get("deadline")) or f.get("deadline_text") or ""
        page = i.get("page_number")
        out["requirements"].append(
            f"{f.get('title') or 'Requirement'}{f' (by {dl})' if dl else ''}{f' [page {page}]' if page else ''}"
        )
    for i in s.get("dates", []):
        f = i.get("fields", {})
        if f.get("date"):
            out["dates"].append(f"{_readable(f.get('date_kind'))}: {_fmt(f.get('date'))}")
    return {k: [x for x in v if x] for k, v in out.items()}


def build_share_email(
    *,
    to: List[str],
    sender_name: str,
    sender_email: Optional[str],
    doc,
    view: Dict[str, Any],
    note: Optional[str],
    mind_map_png: Optional[bytes],
    pdf_bytes: Optional[bytes],
    assignment_due: Optional[date] = None,
    is_assignment: bool = False,
) -> EmailMessage:
    ref = doc.reference_number or "Circular"
    title = doc.title or ""
    if ref and title.startswith(ref):
        title = title[len(ref):].lstrip(" :.-")
    link = f"{settings.APP_PUBLIC_URL.rstrip('/')}/?doc={doc.id}"
    p = points(view)

    subject = f"{'For you to act on: ' if is_assignment else ''}{ref}: {title}"[:200]
    intro = (
        f"{sender_name} assigned this Bangladesh Bank circular to you"
        + (f", to be done by {_fmt(str(assignment_due))}" if assignment_due else "")
        + "."
        if is_assignment
        else f"{sender_name} shared this Bangladesh Bank circular with you."
    )

    # Plain text
    lines = [intro, ""]
    if note:
        lines += [f"Note: {note}", ""]
    lines += [f"{ref}: {title}", f"Issued {_fmt(str(doc.publication_date))}", ""]
    for head, key in (("In short", "summary"), ("What changed", "changes"), ("What banks must do", "requirements"), ("Key dates", "dates")):
        if p[key]:
            lines.append(head)
            lines += [f"- {x}" for x in p[key]]
            lines.append("")
    if not any(p.values()):
        lines += ["The summary for this circular is not ready yet. The original PDF is attached.", ""]
    lines += [f"Open it in RegWatch: {link}", "", "Every point above comes from the circular itself; the original PDF is attached."]
    text = "\n".join(lines)

    # HTML
    e = html.escape
    def ul(items: List[str]) -> str:
        return "<ul style=\"margin:4px 0 14px 18px;padding:0\">" + "".join(f"<li style=\"margin:3px 0\">{e(x)}</li>" for x in items) + "</ul>"

    parts = [
        "<div style=\"font-family:Segoe UI,Roboto,Arial,sans-serif;font-size:15px;line-height:1.55;color:#1b2420;max-width:720px\">",
        f"<p>{e(intro)}</p>",
    ]
    if note:
        parts.append(f"<p style=\"background:#f1f5f3;border-left:3px solid #2f7d63;padding:8px 12px\">{e(note)}</p>")
    parts.append(f"<h2 style=\"font-size:19px;margin:14px 0 2px\">{e(ref)}: {e(title)}</h2>")
    parts.append(f"<p style=\"color:#5b6661;margin:0 0 12px\">Issued {e(_fmt(str(doc.publication_date)))} &middot; Bangladesh Bank</p>")
    for head, key in (("In short", "summary"), ("What changed", "changes"), ("What banks must do", "requirements"), ("Key dates", "dates")):
        if p[key]:
            parts.append(f"<h3 style=\"font-size:15px;margin:10px 0 0\">{head}</h3>{ul(p[key])}")
    if not any(p.values()):
        parts.append("<p>The summary for this circular is not ready yet. The original PDF is attached.</p>")
    mind_cid = make_msgid(domain="regwatch.local")
    if mind_map_png:
        parts.append("<h3 style=\"font-size:15px;margin:10px 0 6px\">Mind map</h3>")
        parts.append(f"<img src=\"cid:{mind_cid[1:-1]}\" alt=\"Mind map of the circular\" style=\"max-width:100%;border:1px solid #d5dbd8;border-radius:8px\">")
    parts.append(
        f"<p style=\"margin-top:18px\"><a href=\"{e(link)}\" style=\"background:#1f5c47;color:#fff;padding:9px 16px;border-radius:8px;text-decoration:none;font-weight:600\">Open in RegWatch</a></p>"
    )
    parts.append("<p style=\"color:#5b6661;font-size:13px\">Every point above comes from the circular itself. The original PDF is attached.</p></div>")
    html_body = "".join(parts)

    sender = (settings.SMTP_FROM or "").replace("\r", "").replace("\n", "")
    msg = EmailMessage()
    msg["From"] = formataddr((f"{sender_name} via {settings.SMTP_FROM_NAME}", sender)) if sender else settings.SMTP_FROM_NAME
    msg["To"] = ", ".join(t.replace("\r", "").replace("\n", "") for t in to)
    if sender_email:
        msg["Reply-To"] = sender_email.replace("\r", "").replace("\n", "")
    msg["Subject"] = subject.replace("\r", " ").replace("\n", " ")
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=sender.split("@", 1)[1] if "@" in sender else None)
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    if mind_map_png:
        msg.get_payload()[1].add_related(mind_map_png, maintype="image", subtype="png", cid=mind_cid, filename="mind-map.png")
    if pdf_bytes:
        safe = re.sub(r"[^A-Za-z0-9._ -]+", "-", ref).strip(" -") or "circular"
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=f"{safe}.pdf")
    return msg
