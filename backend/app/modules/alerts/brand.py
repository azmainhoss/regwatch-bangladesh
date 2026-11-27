"""Branded email layout and the reader-facing emails (drafts for owner approval, 2026-11-25).

Nothing here is sent until the owner approves the drafts and SMTP is configured. Plain-text versions are built
alongside every HTML body. All values are escaped; links are absolute.

Senders (owner-approved 2026-11-24):
- Daily digest and other updates: "Amar Circular" <insights@amarcircular.com>
- Alerts and password resets:    "Amar Circular Alerts" <alerts@amarcircular.com>
"""
import html
from dataclasses import dataclass
from typing import List, Optional

INSIGHTS_FROM = ("Amar Circular", "insights@amarcircular.com")
ALERTS_FROM = ("Amar Circular Alerts", "alerts@amarcircular.com")

GREEN = "#0E694D"
INK = "#161E1B"
INK2 = "#48544F"
INK3 = "#68746F"
LINE = "#DEE3E0"
CANVAS = "#F5F7F5"
MARK = "#FFECA8"
FONT = "'Source Sans 3','Segoe UI',Roboto,Helvetica,Arial,sans-serif"


@dataclass
class Email:
    sender: tuple
    subject: str
    preheader: str
    html: str
    text: str


@dataclass
class DigestCircular:
    reference: str
    title: str
    date: str
    url: str
    point: Optional[str] = None  # first AI verified summary point, if any
    verified: bool = False


def _e(s: str) -> str:
    return html.escape(s or "", quote=True)


def button(label: str, url: str) -> str:
    return (
        f'<a href="{_e(url)}" style="display:inline-block;background:{GREEN};color:#ffffff;font-weight:700;'
        f'font-size:15px;padding:12px 22px;border-radius:8px;text-decoration:none">{_e(label)}</a>'
    )


def layout(base: str, preheader: str, body: str, footer_html: str) -> str:
    """The shared shell: logo header, white card, footer. Table-based so Gmail and Outlook render it the same."""
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>Amar Circular</title></head>
<body style="margin:0;padding:0;background:{CANVAS}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{_e(preheader)}&#8199;&#65279;&#847;&#8199;&#65279;&#847;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CANVAS}"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;font-family:{FONT};color:{INK}">
<tr><td style="padding:0 4px 16px">
  <a href="{_e(base)}/" style="text-decoration:none;color:{INK}">
    <img src="{_e(base)}/icons/apple-touch-icon.png" width="32" height="32" alt="" style="vertical-align:middle;border-radius:8px;border:0">
    <span style="vertical-align:middle;font-size:18px;font-weight:700;margin-left:8px">Amar Circular</span>
  </a>
</td></tr>
<tr><td style="background:#ffffff;border:1px solid {LINE};border-radius:14px;padding:28px 28px 24px">{body}</td></tr>
<tr><td style="padding:18px 8px 0;font-size:12.5px;line-height:1.6;color:{INK3}">{footer_html}</td></tr>
</table></td></tr></table></body></html>"""


def footer(base: str, unsubscribe_url: Optional[str], why: str) -> str:
    parts = [_e(why)]
    links = []
    if unsubscribe_url:
        links.append(f'<a href="{_e(unsubscribe_url)}" style="color:{INK3}">Unsubscribe from these emails</a>')
    links.append(f'<a href="{_e(base)}/alerts/settings" style="color:{INK3}">Email settings</a>')
    parts.append(" · ".join(links))
    parts.append("Amar Circular summarises Bangladesh Bank circulars. This is not an official reference; please check the original circular before making any decision.")
    return "<br>".join(parts)


def _footer_text(base: str, unsubscribe_url: Optional[str], why: str) -> List[str]:
    out = ["--", why]
    if unsubscribe_url:
        out.append(f"Unsubscribe: {unsubscribe_url}")
    out.append(f"Email settings: {base}/alerts/settings")
    out.append("This is not an official reference; please check the original circular before making any decision.")
    return out


# ------------------------------------------------------------------------------------------------ the emails


def daily_digest(base: str, day_label: str, circulars: List[DigestCircular], unsubscribe_url: str) -> Email:
    """Sent every day (owner, 2026-11-25): how many circulars came that day, with each one listed. On a day with
    none, a short "no new circulars" note. No AI verified / AI draft marks in email (owner)."""
    n = len(circulars)
    if n:
        first = circulars[0].reference
        subject = f"{n} new Bangladesh Bank circular{'s' if n != 1 else ''} today: {first}" + (f" and {n - 1} more" if n > 1 else "")
        preheader = "; ".join(c.title for c in circulars[:2])[:140]
        heading = f"{n} new circular{'s' if n != 1 else ''} from Bangladesh Bank"
        lead = ""
    else:
        subject = "No new Bangladesh Bank circulars today"
        preheader = f"Nothing new from Bangladesh Bank on {day_label}."
        heading = "No new circulars today"
        lead = "Bangladesh Bank did not publish any new circulars today. The full library is one click away."
    rows = []
    text = [heading + f" ({day_label})", ""]
    for c in circulars:
        point = f'<p style="margin:8px 0 0;font-size:14.5px;line-height:1.5;color:{INK2}">{_e(c.point)}</p>' if c.point else ""
        rows.append(
            f'<tr><td style="padding:16px 0;border-top:1px solid {LINE}">'
            f'<div style="font-size:13px;font-weight:700;color:{GREEN}">{_e(c.reference)}</div>'
            f'<a href="{_e(c.url)}" style="display:block;margin-top:4px;font-size:16px;font-weight:700;line-height:1.35;color:{INK};text-decoration:none">{_e(c.title)}</a>'
            f'<div style="margin-top:2px;font-size:13px;color:{INK3}">{_e(c.date)}</div>{point}</td></tr>'
        )
        text += [f"{c.reference}: {c.title} ({c.date})"] + ([f"  {c.point}"] if c.point else []) + [f"  {c.url}", ""]
    table = f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(rows)}</table>' if rows else ""
    cta_url = base + ("/dashboard?box=today" if n else "/dashboard")
    body = (
        f'<p style="margin:0;font-size:13px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:{INK3}">Daily update · {_e(day_label)}</p>'
        f'<h1 style="margin:6px 0 4px;font-size:24px;line-height:1.25">{_e(heading)}</h1>'
        + (f'<p style="margin:0 0 8px;font-size:15px;color:{INK2}">{_e(lead)}</p>' if lead else "")
        + f'{table}'
        f'<div style="margin-top:20px">{button("Open the library", cta_url)}</div>'
    )
    why = "You get this daily update because you registered at amarcircular.com."
    text += ["Open the library: " + cta_url, ""] + _footer_text(base, unsubscribe_url, why)
    return Email(INSIGHTS_FROM, subject, preheader, layout(base, preheader, body, footer(base, unsubscribe_url, why)), "\n".join(text))


def welcome(base: str, first_name: Optional[str]) -> Email:
    hi = f"Welcome, {first_name}" if first_name else "Welcome to Amar Circular"
    subject = "Welcome to Amar Circular"
    preheader = "Every Bangladesh Bank circular, summarised the day it is issued, with the exact page in the original."
    body = (
        f'<h1 style="margin:0 0 10px;font-size:24px;line-height:1.25">{_e(hi)}</h1>'
        f'<p style="margin:0 0 14px;font-size:15.5px;line-height:1.6;color:{INK2}">Your free account is ready. Here is what you can do:</p>'
        f'<ul style="margin:0 0 18px;padding-left:20px;font-size:15px;line-height:1.7;color:{INK}">'
        "<li><b>Read every circular</b> with its summary, what changed, requirements and dates.</li>"
        "<li><b>Check any point</b> on the exact page of the original, highlighted.</li>"
        "<li><b>Save circulars</b> to Read later and your own lists.</li>"
        "<li><b>Get a daily digest</b> of new circulars by email.</li></ul>"
        f'{button("Open the library", base + "/dashboard")}'
    )
    why = "You get this email because you just registered at amarcircular.com."
    text = [hi, "", "Your free account is ready.", "", f"Open the library: {base}/dashboard", ""] + _footer_text(base, None, why)
    return Email(INSIGHTS_FROM, subject, preheader, layout(base, preheader, body, footer(base, None, why)), "\n".join(text))


def password_reset(base: str, reset_url: str, minutes: int = 60) -> Email:
    subject = "Reset your Amar Circular password"
    preheader = f"This link works for {minutes} minutes."
    body = (
        f'<h1 style="margin:0 0 10px;font-size:22px">Reset your password</h1>'
        f'<p style="margin:0 0 18px;font-size:15.5px;line-height:1.6;color:{INK2}">Someone (hopefully you) asked to reset the password '
        f'for this email address. The link works for {minutes} minutes and can be used once.</p>'
        f'{button("Choose a new password", reset_url)}'
        f'<p style="margin:18px 0 0;font-size:14px;line-height:1.6;color:{INK3}">If you did not ask for this, ignore this email; your password stays the same.</p>'
    )
    why = "You get this email because a password reset was requested for your account."
    text = ["Reset your password", "", f"Choose a new password (works for {minutes} minutes): {reset_url}", "",
            "If you did not ask for this, ignore this email."] + _footer_text(base, None, why)
    return Email(ALERTS_FROM, subject, preheader, layout(base, preheader, body, footer(base, None, why)), "\n".join(text))


def circular_changed(base: str, saved_ref: str, saved_title: str, verb: str, by_ref: str, by_url: str,
                     quote: Optional[str], quote_page: Optional[int], unsubscribe_url: str) -> Email:
    """A circular the person saved or follows was amended, replaced or repealed."""
    subject = f"{saved_ref} was {verb} by {by_ref}"
    preheader = f"A circular you saved has changed: {saved_title}"[:140]
    q = ""
    if quote:
        q = (f'<div style="margin:0 0 18px;padding:10px 14px;border-left:3px solid {GREEN};background:#F7FAF8">'
             f'<div style="font-size:12.5px;color:{INK3};margin-bottom:4px">From {_e(by_ref)}{f", page {quote_page}" if quote_page else ""}:</div>'
             f'<div style="font-size:14.5px;line-height:1.55"><span style="background:{MARK}">{_e(quote)}</span></div></div>')
    body = (
        f'<p style="margin:0;font-size:13px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:{INK3}">Saved circular changed</p>'
        f'<h1 style="margin:6px 0 10px;font-size:22px;line-height:1.3">{_e(saved_ref)} was {_e(verb)}</h1>'
        f'<p style="margin:0 0 14px;font-size:15.5px;line-height:1.6;color:{INK2}"><b>{_e(by_ref)}</b> {_e(verb)} '
        f'“{_e(saved_title)}”, which is in your saved circulars.</p>{q}'
        f'{button("See what changed", by_url)}'
    )
    why = "You get this alert because this circular is in your Read later, Favourites or lists."
    text = [f"{saved_ref} was {verb} by {by_ref}", "", saved_title, ""] + ([f'"{quote}"', ""] if quote else []) + \
        [f"See what changed: {by_url}", ""] + _footer_text(base, unsubscribe_url, why)
    return Email(ALERTS_FROM, subject, preheader, layout(base, preheader, body, footer(base, unsubscribe_url, why)), "\n".join(text))
