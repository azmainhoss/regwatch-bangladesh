"""Allow-list for outbound source fetches.

Sources may only point at the official Bangladesh Bank website over HTTPS.
This blocks server-side request forgery through a user-supplied base_url,
a crafted file link on a listing page, or a redirect to another host.
"""
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

ALLOWED_SOURCE_HOSTS = frozenset({"bb.org.bd", "www.bb.org.bd"})


class DisallowedSourceURL(ValueError):
    pass


def validate_source_url(url: Optional[str], *, upgrade_http: bool = False) -> str:
    """Return the URL if it is an https URL on an allowed host, else raise.

    With upgrade_http=True a plain http link to an allowed host is rewritten
    to https instead of being rejected (used for links found on listing pages).
    """
    if not url or not isinstance(url, str):
        raise DisallowedSourceURL("Source URL is required.")
    candidate = url.strip()
    parts = urlsplit(candidate)
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower().rstrip(".")

    if parts.username or parts.password:
        raise DisallowedSourceURL("Source URL must not contain credentials.")
    if host not in ALLOWED_SOURCE_HOSTS:
        raise DisallowedSourceURL(
            f"Source URL host '{host or '?'}' is not allowed. Only https://bb.org.bd and https://www.bb.org.bd are permitted."
        )
    if parts.port not in (None, 443):
        raise DisallowedSourceURL("Source URL must use the default HTTPS port.")
    if scheme != "https":
        if scheme == "http" and upgrade_http:
            return urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))
        raise DisallowedSourceURL("Source URL must use https.")
    return candidate


def is_allowed_source_url(url: Optional[str]) -> bool:
    try:
        validate_source_url(url)
        return True
    except DisallowedSourceURL:
        return False
