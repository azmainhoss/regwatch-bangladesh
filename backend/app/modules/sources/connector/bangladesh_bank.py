import asyncio
import re
from datetime import date, datetime, timedelta, timezone
from html import unescape
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
import httpx
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.modules.sources.connector.base import (
    AntiBotChallenge,
    BaseSourceConnector,
    CandidatePublication,
    DiscoveryResult,
    FetchedFile,
    ListingOutcome,
)
from backend.app.modules.sources.connector.pacing import bb_request_gate
from backend.app.modules.sources.url_policy import DisallowedSourceURL, validate_source_url

MAX_REDIRECTS = 5
REDIRECT_STATUSES = (301, 302, 303, 307, 308)


class BangladeshBankConnector(BaseSourceConnector):
    DEFAULT_BASE_URL = "https://www.bb.org.bd/en/index.php/mediaroom/circular"

    def __init__(self, base_url: Optional[str] = None, user_agent: Optional[str] = None):
        # Refuse to build a connector for anything other than the official site.
        self.base_url = validate_source_url(base_url or self.DEFAULT_BASE_URL)
        self.user_agent = user_agent or settings.BB_CRAWLER_USER_AGENT
        self.domain = "https://www.bb.org.bd"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/pdf,*/*",
        }

    @staticmethod
    def parse_publication_date(date_str: str) -> Optional[date]:
        """Parses common Bangladesh Bank date formats."""
        cleaned = date_str.strip()
        formats = [
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%d/%m/%y",
            "%d-%m-%y",
            "%Y-%m-%d",
            "%d %b %Y",
            "%d %B %Y",
            "%b %d, %Y",
            "%B %d, %Y"
        ]
        for fmt in formats:
            try:
                return datetime.strptime(cleaned, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def infer_department_code(title: str, ref_number: Optional[str], url: str) -> Optional[str]:
        # 1. Inspect URL path (most accurate for official BB PDFs, e.g. /mediaroom/circulars/brpd/...)
        url_match = re.search(r"/circulars/([a-zA-Z0-9]+)/", url, re.IGNORECASE)
        if url_match:
            dept_slug = url_match.group(1).upper()
            if dept_slug in ["BRPD", "DOS", "FEPD", "PSD", "DFIM", "SMESPD", "SFD", "FID", "FEID", "ACD", "DMD", "DCM", "DBI", "SDAD"]:
                return dept_slug

        # 2. Inspect title and reference number
        combined = f"{title} {ref_number or ''} {url}".upper()
        depts = [
            "BRPD", "DOS", "FEPD", "PSD", "DFIM", "SMESPD",
            "SFD", "FID", "FEID", "ACD", "DMD", "DCM", "DBI", "SDAD"
        ]
        for dept in depts:
            if dept in combined:
                return dept
        return None

    @staticmethod
    def infer_publication_type(title: str, ref_number: Optional[str]) -> str:
        combined = f"{title} {ref_number or ''}".lower()
        if "circular letter" in combined or "circular-letter" in combined or "প্রজ্ঞাপন" in combined or "পত্র" in combined:
            return "CIRCULAR_LETTER"
        elif "guideline" in combined or "guidelines" in combined or "নীতিমালা" in combined or "policy" in combined:
            return "POLICY_GUIDELINE"
        return "CIRCULAR"

    # A PDF link inside a quoted attribute: href="..." or onclick="loadPDFDynamically('...')".
    _PDF_LINK = re.compile(r"""['"]([^'"\s<>]+?\.pdf)['"]""", re.IGNORECASE)
    _ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
    _CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL | re.IGNORECASE)
    _REF = re.compile(
        r"((?:BRPD|DOS|FEPD|PSD|SFD|DBI|SMESPD|ACD|SDAD|FID|FEID|DFIM|DMD|DCM)[\w\-]*(?:\s+Circular\s+Letter|\s+Circular|\s+Letter)?\s*(?:No\.|Letter No\.)?\s*[\w\-\/]+)",
        re.IGNORECASE,
    )

    @staticmethod
    def _clean_cell_text(cell_html: str) -> str:
        return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", cell_html))).strip()

    @staticmethod
    def classify_listing(status_code: int, html: str) -> Tuple[ListingOutcome, str]:
        """Sorts a listing reply into an outcome (same rules as research/detect/detect_test.py)."""
        low = html.lower()
        if "/tspd/" in low or "bobcmn" in low or "what code is in the image" in low:
            return ListingOutcome.CHALLENGE, "Bot check page instead of the circular list."
        if "request rejected" in low or "the requested url was rejected" in low:
            return ListingOutcome.HTTP_ERROR, "Request Rejected page instead of the circular list."
        if status_code != 200:
            return ListingOutcome.HTTP_ERROR, f"HTTP {status_code} from the circular list."
        i = low.find("<table")
        if i < 0 or "<th" not in low[i:i + 2000]:
            return ListingOutcome.NO_TABLE, "Reply has no circular table."
        return ListingOutcome.OK, ""

    def parse_listing_html(self, html_content: str, source_page_url: str) -> List[CandidatePublication]:
        """
        Parses the circular table: Date | Title | English | Bangla.
        Every PDF link in the English or Bangla cell becomes one candidate, keyed by its URL.
        Rows without a PDF link (for example "Not Available") give no candidate.
        """
        candidates: List[CandidatePublication] = []
        for row_html in self._ROW.findall(html_content):
            cells = self._CELL.findall(row_html)
            if len(cells) < 4:
                continue
            date_str = self._clean_cell_text(cells[0])
            title = self._clean_cell_text(cells[1])
            if not title or len(title) < 4:
                continue

            pub_date = self.parse_publication_date(date_str)
            pub_type = self.infer_publication_type(title, None)
            ref_match = self._REF.search(title)
            ref_no = ref_match.group(1).strip() if ref_match else None

            for lang, language, cell in (("en", "English", cells[2]), ("bn", "Bangla", cells[3])):
                seen_urls = []
                for href in self._PDF_LINK.findall(cell):
                    pdf_url = urljoin(source_page_url, unescape(href))
                    if pdf_url in seen_urls:
                        continue
                    seen_urls.append(pdf_url)
                    candidates.append(CandidatePublication(
                        title=title,
                        reference_number=ref_no,
                        department_code=self.infer_department_code(title, ref_no, pdf_url),
                        publication_date=pub_date,
                        detail_url=source_page_url,
                        file_url=pdf_url,
                        language=language,
                        publication_type=pub_type,
                        metadata={"raw_date": date_str, "language": language, "lang": lang, "relative_href": href},
                    ))
        return candidates

    # ---------------------------------------------------------------- requests

    async def _safe_request(self, client: httpx.AsyncClient, method: str, url: str) -> httpx.Response:
        """GET/HEAD a URL on the allow-list, following redirects only within the allow-list.
        Every hop is its own paced request."""
        current = validate_source_url(url, upgrade_http=True)
        for _ in range(MAX_REDIRECTS + 1):
            async with bb_request_gate.slot():
                if method == "HEAD":
                    resp = await client.head(current, headers=self._get_headers())
                else:
                    resp = await client.get(current, headers=self._get_headers())
            status_code = getattr(resp, "status_code", None)
            if status_code in REDIRECT_STATUSES:
                location = _header(resp, "location")
                if not location:
                    return resp
                current = validate_source_url(urljoin(current, location), upgrade_http=True)
                continue
            return resp
        raise DisallowedSourceURL(f"Too many redirects while fetching {url}")

    async def _safe_get(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        return await self._safe_request(client, "GET", url)

    async def _check_listing(self, method: str, form: Optional[Dict[str, str]] = None) -> DiscoveryResult:
        result = DiscoveryResult()
        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=False) as client:
                if method == "POST":
                    async with bb_request_gate.slot():
                        resp = await client.post(self.base_url, data=form, headers=self._get_headers())
                else:
                    resp = await self._safe_get(client, self.base_url)
        except (httpx.RequestError, httpx.TimeoutException) as req_err:
            logger.error(f"Network error checking {self.base_url}: {req_err}")
            result.outcome = ListingOutcome.NETWORK_ERROR
            result.errors.append(f"Network error: {type(req_err).__name__}: {req_err}")
            return result
        except DisallowedSourceURL as url_err:
            logger.error(f"Blocked fetch outside the source allow-list: {url_err}")
            result.outcome = ListingOutcome.HTTP_ERROR
            result.errors.append(str(url_err))
            return result

        result.pages_inspected = 1
        status_code = getattr(resp, "status_code", 0)
        html = resp.text if isinstance(getattr(resp, "text", None), str) else ""
        result.status_code = status_code
        result.bytes_received = len(html.encode("utf-8", "replace"))

        outcome, detail = self.classify_listing(status_code, html)
        result.outcome = outcome
        if outcome != ListingOutcome.OK:
            if outcome == ListingOutcome.CHALLENGE:
                result.anti_bot_challenge = self.detect_anti_bot_challenge(html, status_code) or AntiBotChallenge(
                    is_blocked=True, challenge_type="IMPERVA_TSPD_CAPTCHA", status_code=status_code, details=detail
                )
            logger.warning(f"Listing check of {self.base_url} failed: {outcome.value} ({detail})")
            result.errors.append(detail)
            return result

        result.candidate_publications = self.parse_listing_html(html, self.base_url)
        logger.info(f"Listing check found {len(result.candidate_publications)} PDF links on {self.base_url}")
        return result

    async def poll_recent(self, days: Optional[int] = None, today: Optional[date] = None) -> DiscoveryResult:
        """New-circular check: the site's date filter for the last `days` days (both ends inclusive)."""
        days = settings.BB_POLL_DAYS if days is None else days
        today = today or datetime.now(ZoneInfo(settings.MONITOR_TIMEZONE)).date()
        form = {
            "from_date": (today - timedelta(days=days)).strftime("%Y-%m-%d"),
            "to_date": today.strftime("%Y-%m-%d"),
            "search_circular": "Search",
        }
        return await self._check_listing("POST", form)

    async def full_reconcile(self) -> DiscoveryResult:
        """Daily double-check: the full circular list (about 2.6 MB), same parser."""
        return await self._check_listing("GET")

    async def discover_publications(self, max_pages: int = 1, mode: str = "poll") -> DiscoveryResult:
        if mode == "reconcile":
            return await self.full_reconcile()
        return await self.poll_recent()

    # --------------------------------------------------------------- downloads

    def _classify_file_reply(self, resp) -> Optional[AntiBotChallenge]:
        """Returns why a non-PDF reply is not a usable file."""
        status_code = getattr(resp, "status_code", 0)
        text = resp.text if isinstance(getattr(resp, "text", None), str) else ""
        low = text.lower()
        # Same order as the reference script: a real bot check first, then a per-file rejection.
        if "/tspd/" in low or "bobcmn" in low or "what code is in the image" in low:
            return self.detect_anti_bot_challenge(text, status_code)
        if self.is_request_rejected(text):
            return AntiBotChallenge(
                is_blocked=False,
                challenge_type="REQUEST_REJECTED",
                status_code=status_code,
                details="The site answered 'Request Rejected' for this one file. Skipped; other files carry on.",
            )
        return self.detect_anti_bot_challenge(text, status_code)

    async def fetch_document(
        self,
        file_url: str,
        max_retries: int = 3,
        backoff_base_seconds: float = 1.0,
    ) -> FetchedFile:
        """Downloads one file (paced) and keeps its ETag and Last-Modified headers."""
        try:
            file_url = validate_source_url(file_url, upgrade_http=True)
        except DisallowedSourceURL as url_err:
            return FetchedFile(url=file_url, challenge=AntiBotChallenge(
                is_blocked=False, challenge_type="DISALLOWED_URL", status_code=0, details=str(url_err)
            ))

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
            last_challenge = None
            for attempt in range(max_retries):
                try:
                    try:
                        resp = await self._safe_get(client, file_url)
                    except DisallowedSourceURL as url_err:
                        return FetchedFile(url=file_url, challenge=AntiBotChallenge(
                            is_blocked=False, challenge_type="DISALLOWED_URL", status_code=0, details=str(url_err)
                        ))
                    status_code = getattr(resp, "status_code", 0)
                    content = getattr(resp, "content", b"")
                    if status_code == 200 and isinstance(content, bytes) and content.startswith(b"%PDF-"):
                        return FetchedFile(
                            url=file_url,
                            content=content,
                            etag=_header(resp, "etag"),
                            last_modified=_header(resp, "last-modified"),
                            fetched_at=datetime.now(timezone.utc),
                        )

                    problem = self._classify_file_reply(resp)
                    if problem:
                        return FetchedFile(url=file_url, challenge=problem)

                    if status_code == 200:
                        return FetchedFile(url=file_url, challenge=AntiBotChallenge(
                            is_blocked=True,
                            challenge_type="INVALID_CONTENT_TYPE",
                            status_code=status_code,
                            details="Response returned non-PDF content (likely an unrecognized bot challenge or error page).",
                        ))
                    if status_code in (500, 502, 503, 504):
                        logger.warning(f"HTTP {status_code} downloading {file_url} (attempt {attempt + 1}/{max_retries})")
                        last_challenge = AntiBotChallenge(
                            is_blocked=False,
                            challenge_type="HTTP_SERVER_ERROR",
                            status_code=status_code,
                            details=f"Transient HTTP {status_code} error from source.",
                        )
                    else:
                        return FetchedFile(url=file_url, challenge=AntiBotChallenge(
                            is_blocked=False,
                            challenge_type="HTTP_ERROR",
                            status_code=status_code,
                            details=f"Download failed with HTTP status {status_code}",
                        ))
                except (httpx.RequestError, httpx.TimeoutException) as req_err:
                    logger.warning(f"Network error downloading {file_url} (attempt {attempt + 1}/{max_retries}): {req_err}")
                    last_challenge = AntiBotChallenge(
                        is_blocked=False,
                        challenge_type="NETWORK_EXCEPTION",
                        status_code=0,
                        details=f"Network exception downloading file: {req_err}",
                    )

                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff_base_seconds * (2 ** attempt))

            return FetchedFile(url=file_url, challenge=last_challenge or AntiBotChallenge(
                is_blocked=False,
                challenge_type="MAX_RETRIES_EXCEEDED",
                status_code=0,
                details=f"Failed to download after {max_retries} attempts.",
            ))

    async def download_document(
        self,
        file_url: str,
        max_retries: int = 3,
        backoff_base_seconds: float = 1.0
    ) -> Tuple[Optional[bytes], Optional[AntiBotChallenge]]:
        fetched = await self.fetch_document(file_url, max_retries=max_retries, backoff_base_seconds=backoff_base_seconds)
        return fetched.content, fetched.challenge

    async def head_document(self, file_url: str) -> FetchedFile:
        """HEAD request (paced) for the archive re-check. Returns headers only, no content."""
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
                resp = await self._safe_request(client, "HEAD", file_url)
        except DisallowedSourceURL as url_err:
            return FetchedFile(url=file_url, challenge=AntiBotChallenge(
                is_blocked=False, challenge_type="DISALLOWED_URL", status_code=0, details=str(url_err)
            ))
        except (httpx.RequestError, httpx.TimeoutException) as req_err:
            return FetchedFile(url=file_url, challenge=AntiBotChallenge(
                is_blocked=False, challenge_type="NETWORK_EXCEPTION", status_code=0, details=str(req_err)
            ))
        status_code = getattr(resp, "status_code", 0)
        if status_code != 200:
            text = resp.text if isinstance(getattr(resp, "text", None), str) else ""
            return FetchedFile(url=file_url, challenge=self.detect_anti_bot_challenge(text, status_code) or AntiBotChallenge(
                is_blocked=False,
                challenge_type="HTTP_ERROR",
                status_code=status_code,
                details=f"HEAD returned HTTP {status_code}",
            ))
        return FetchedFile(
            url=file_url,
            etag=_header(resp, "etag"),
            last_modified=_header(resp, "last-modified"),
            fetched_at=datetime.now(timezone.utc),
        )


def _header(resp, name: str) -> Optional[str]:
    headers = getattr(resp, "headers", None)
    if headers is None:
        return None
    try:
        value = headers.get(name)
        if value is None and isinstance(headers, dict):
            lowered = {str(k).lower(): v for k, v in headers.items()}
            value = lowered.get(name.lower())
    except Exception:
        return None
    return value if isinstance(value, str) else None
