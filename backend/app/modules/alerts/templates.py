"""Fixed alert text. Every value comes from the stored payload; the words around it are fixed here.

The same strings are used for the inbox and for email. Nothing here states a claim of its own.
The only quote that can ever appear is the stored quote of a confirmed link, copied unchanged.
"""
import html
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional

MAX_TITLE = 160

ADMIN_QUEUES = {
    "discoveries": ("new circular", "new circulars", "to approve", "/admin?tab=queue"),
    "analyses": ("analysis", "analyses", "to review", "/admin?tab=library"),
    "links": ("link", "links", "to confirm", "/admin?tab=links"),
    "pages": ("page", "pages", "to check", "/admin?tab=library"),
}


@dataclass
class Rendered:
    title: str
    body: str
    detail: Optional[str]
    link: str
    severity: str
    quote_text: Optional[str] = None
    quote_page_number: Optional[int] = None
    quote_document_id: Optional[str] = None
    quote_label: Optional[str] = None  # "From {ref}, page {n}:"
    org_name: Optional[str] = None


def fmt_date(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        try:
            value = date.fromisoformat(str(value)[:10])
        except ValueError:
            return str(value)
    return f"{value.day} {value.strftime('%b %Y')}"


def clip(text: Optional[str], limit: int = MAX_TITLE) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _ref(p: Dict[str, Any], key: str = "reference_number") -> str:
    return clip(p.get(key)) or "A circular"


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _item_link(p: Dict[str, Any]) -> str:
    return f"/workspace/{p.get('organization_id')}/items/{p.get('item_id')}"


def _task_link(p: Dict[str, Any]) -> str:
    return f"{_item_link(p)}#task-{p.get('task_id')}"


def render(kind: str, p: Dict[str, Any], organization_id: Optional[str] = None) -> Rendered:
    p = dict(p or {})
    if organization_id and not p.get("organization_id"):
        p["organization_id"] = str(organization_id)
    org = clip(p.get("organization_name"), 120)
    actor = clip(p.get("actor_name"), 120) or "Someone"
    task_title = clip(p.get("task_title"))
    item_title = clip(p.get("item_title"))

    if kind == "CIRCULAR_PUBLISHED":
        return Rendered(
            title=f"New circular: {_ref(p)}",
            body=f"{clip(p.get('title'))}. Published {fmt_date(p.get('publication_date'))}.".replace(" Published .", ""),
            detail=None, link=f"/?doc={p.get('document_id')}", severity="info",
        )

    if kind == "REGISTER_SOURCE_CHANGED":
        change = p.get("change_kind")
        n = int(p.get("item_count") or 0)
        items = f"{n} {_plural(n, 'item', 'items')}"
        ref = _ref(p)
        if n == 1 and p.get("item_ids"):
            link = f"/workspace/{p.get('organization_id')}/items/{p['item_ids'][0]}"
        else:
            reg = (p.get("register_ids") or [None])[0]
            link = f"/workspace/{p.get('organization_id')}/registers/{reg}?changed=1" if reg else f"/workspace/{p.get('organization_id')}"
        quote = {}
        if change in ("AMENDED", "REPLACED", "REPEALED"):
            verb = {"AMENDED": "amended", "REPLACED": "replaced", "REPEALED": "repealed"}[change]
            verb3 = {"AMENDED": "amends", "REPLACED": "replaces", "REPEALED": "repeals"}[change]
            title = f"{ref} was {verb}"
            body = (f"{_ref(p, 'by_reference_number')} {verb3} it. {items} in your registers at {org} "
                    f"{_plural(n, 'points', 'point')} to it. Please check {_plural(n, 'it', 'them')}.")
            severity = "bad" if change == "REPEALED" else "warn"
            if p.get("link_quote"):
                quote = {
                    "quote_text": p["link_quote"],
                    "quote_page_number": p.get("link_quote_page"),
                    "quote_document_id": p.get("by_document_id"),
                    "quote_label": f"From {_ref(p, 'by_reference_number')}"
                                   + (f", page {p.get('link_quote_page')}:" if p.get("link_quote_page") else ":"),
                }
        elif change == "NEW_VERSION":
            title = f"New version of {ref}"
            body = (f"A newer version of this circular was published. {items} at {org} "
                    f"{_plural(n, 'points', 'point')} to the older one.")
            severity = "warn"
        else:
            title = f"{ref} was withdrawn"
            body = f"{items} at {org} {_plural(n, 'points', 'point')} to it."
            severity = "bad"
        return Rendered(title=title, body=body, detail=None, link=link, severity=severity, org_name=org, **quote)

    if kind == "TASK_ASSIGNED":
        return Rendered(
            title=f"Task assigned to you: {task_title}",
            body=f"{actor} assigned you a task at {org}." + (f" Due {fmt_date(p.get('due_date'))}." if p.get("due_date") else ""),
            detail=None, link=_task_link(p), severity="info", org_name=org,
        )
    if kind == "ITEM_LEAD_ASSIGNED":
        return Rendered(
            title=f"You lead an item: {item_title}",
            body=f"{actor} made you the lead at {org}." + (f" Deadline {fmt_date(p.get('deadline'))}." if p.get("deadline") else ""),
            detail=None, link=_item_link(p), severity="info", org_name=org,
        )
    if kind == "TASK_CANCELLED":
        return Rendered(
            title=f"Task cancelled: {task_title}", body=f"{actor} cancelled this task at {org}.",
            detail=None, link=_item_link(p), severity="info", org_name=org,
        )
    if kind == "EVIDENCE_AWAITING_REVIEW":
        return Rendered(
            title=f"Evidence to review: {task_title}", body=f"{actor} uploaded evidence at {org}.",
            detail=None, link=f"/workspace/{p.get('organization_id')}/review", severity="info", org_name=org,
        )
    if kind == "ITEM_AWAITING_SIGNOFF":
        return Rendered(
            title=f"Item ready for sign-off: {item_title}", body=f"{actor} sent it for sign-off at {org}.",
            detail=None, link=_item_link(p), severity="info", org_name=org,
        )
    if kind == "TASK_REVIEWED":
        decision = p.get("decision")
        word, sev = {
            "APPROVED": ("approved", "info"),
            "CHANGES_REQUESTED": ("needs changes", "warn"),
            "REJECTED": ("rejected", "bad"),
        }.get(decision, ("reviewed", "info"))
        return Rendered(
            title=f"Evidence {word}: {task_title}", body=f"{actor} reviewed your evidence at {org}.",
            detail=(p.get("comments") or None), link=_task_link(p), severity=sev, org_name=org,
        )
    if kind == "ITEM_SIGNOFF_DECIDED":
        approved = p.get("decision") == "APPROVED"
        return Rendered(
            title=f"Item {'signed off as compliant' if approved else 'sent back'}: {item_title}",
            body=f"{actor} decided at {org}.", detail=(p.get("comments") or None),
            link=_item_link(p), severity="info" if approved else "warn", org_name=org,
        )
    if kind == "ITEM_DUE_SOON":
        n = int(p.get("days_left") or 0)
        head = "Due today" if n == 0 else f"Due in {n} {_plural(n, 'day', 'days')}"
        return Rendered(
            title=f"{head}: {item_title}", body=f"Deadline {fmt_date(p.get('deadline'))} at {org}.",
            detail=None, link=_item_link(p), severity="warn", org_name=org,
        )
    if kind == "TASK_DUE_SOON":
        n = int(p.get("days_left") or 0)
        head = "Task due today" if n == 0 else f"Task due in {n} {_plural(n, 'day', 'days')}"
        return Rendered(
            title=f"{head}: {task_title}", body=f"Due {fmt_date(p.get('due_date'))} at {org}.",
            detail=None, link=_task_link(p), severity="warn", org_name=org,
        )
    if kind == "ITEM_OVERDUE":
        return Rendered(
            title=f"Overdue: {item_title}", body=f"The deadline was {fmt_date(p.get('deadline'))} at {org}.",
            detail=None, link=_item_link(p), severity="bad", org_name=org,
        )
    if kind == "TASK_OVERDUE":
        return Rendered(
            title=f"Overdue task: {task_title}", body=f"It was due {fmt_date(p.get('due_date'))} at {org}.",
            detail=None, link=_task_link(p), severity="bad", org_name=org,
        )
    if kind == "ADMIN_QUEUE":
        one, many, tail, link = ADMIN_QUEUES.get(p.get("queue"), ("item", "items", "to review", "/admin"))
        n = int(p.get("count") or 0)
        return Rendered(
            title=f"{n} {one if n == 1 else many} {tail}",
            body="They are waiting in the admin review queue.", detail=None, link=link, severity="info",
        )
    raise ValueError(f"Unknown alert kind: {kind}")


# ---------------------------------------------------------------------------
# Email layout
# ---------------------------------------------------------------------------
FOOTER = "You get this email because of your alert settings. Change them here: {url}/alerts/settings"


def email_subject(r: Rendered) -> str:
    prefix = f"[{r.org_name}] " if r.org_name else ""
    return (prefix + r.title).replace("\r", " ").replace("\n", " ")[:300]


def _abs(base: str, link: str) -> str:
    return f"{base}{link}"


def instant_email(r: Rendered, base_url: str):
    """(subject, text, html). Never includes the in-app detail (reviewer comments)."""
    text = [r.title, "", r.body]
    if r.quote_text:
        lbl = (r.quote_label or "").rstrip(":")
        text += ["", f'"{r.quote_text}" ({lbl[:1].lower() + lbl[1:]})']
    text += ["", f"Open: {_abs(base_url, r.link)}", "", "--", FOOTER.format(url=base_url)]
    h = [
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;padding:16px;color:#1f2937">',
        f'<h1 style="font-size:18px;margin:0 0 12px">{html.escape(r.title)}</h1>',
        f'<p style="margin:0 0 12px;line-height:1.5">{html.escape(r.body)}</p>',
    ]
    if r.quote_text:
        h.append(
            '<div style="border-left:3px solid #9ca3af;padding:4px 12px;margin:0 0 12px;color:#374151">'
            f'<div style="font-size:12px;color:#6b7280;margin-bottom:4px">{html.escape(r.quote_label or "")}</div>'
            f'<div>{html.escape(r.quote_text)}</div></div>'
        )
    h.append(
        f'<p style="margin:16px 0"><a href="{html.escape(_abs(base_url, r.link), quote=True)}" '
        'style="display:inline-block;background:#1d4ed8;color:#ffffff;padding:10px 16px;border-radius:6px;text-decoration:none">'
        "Open in RegWatch</a></p>"
    )
    h.append(
        f'<p style="font-size:12px;color:#6b7280;margin:24px 0 0">You get this email because of your alert settings. '
        f'<a href="{html.escape(base_url, quote=True)}/alerts/settings">Change them here</a>.</p></div>'
    )
    return email_subject(r), "\n".join(text), "".join(h)


MAX_DIGEST_LINES = 50


def digest_email(sections, total: int, base_url: str):
    """sections: list of (heading, [(title, link), ...]). Returns (subject, text, html)."""
    subject = f"RegWatch daily summary: {total} {_plural(total, 'alert', 'alerts')}"
    text, h = [subject, ""], [
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;padding:16px;color:#1f2937">',
        f'<h1 style="font-size:18px;margin:0 0 12px">{html.escape(subject)}</h1>',
    ]
    shown = 0
    for heading, lines in sections:
        lines = lines[: max(0, MAX_DIGEST_LINES - shown)]
        if not lines:
            continue
        text += [heading, ""]
        h.append(f'<h2 style="font-size:15px;margin:16px 0 6px">{html.escape(heading)}</h2><ul style="padding-left:18px;margin:0">')
        for title, link in lines:
            url = _abs(base_url, link)
            text.append(f"- {title}: {url}")
            h.append(f'<li style="margin:4px 0"><a href="{html.escape(url, quote=True)}">{html.escape(title)}</a></li>')
            shown += 1
        text.append("")
        h.append("</ul>")
    if total > shown:
        more = total - shown
        text += [f"and {more} more in your inbox: {base_url}/alerts", ""]
        h.append(f'<p style="margin:12px 0"><a href="{html.escape(base_url, quote=True)}/alerts">and {more} more in your inbox</a></p>')
    text += ["--", FOOTER.format(url=base_url)]
    h.append(
        f'<p style="font-size:12px;color:#6b7280;margin:24px 0 0">You get this email because of your alert settings. '
        f'<a href="{html.escape(base_url, quote=True)}/alerts/settings">Change them here</a>.</p></div>'
    )
    return subject, "\n".join(text), "".join(h)
