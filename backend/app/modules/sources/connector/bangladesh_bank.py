import asyncio
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin
import httpx
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.modules.sources.connector.base import (
    AntiBotChallenge,
    BaseSourceConnector,
    CandidatePublication,
    DiscoveryResult,
)


class BangladeshBankConnector(BaseSourceConnector):
    DEFAULT_BASE_URL = "https://www.bb.org.bd/en/index.php/mediaroom/circular"

    def __init__(self, base_url: Optional[str] = None, user_agent: Optional[str] = None):
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.user_agent = user_agent or settings.BB_CRAWLER_USER_AGENT
        self.domain = "https://www.bb.org.bd"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
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

    def parse_listing_html(self, html_content: str, source_page_url: str) -> List[CandidatePublication]:
        """
        Parses Bangladesh Bank circular listing HTML table or links.
        Extracts high-fidelity candidate circular items with dates, references, and PDF URLs.
        Collects both English and Bangla publications.
        """
        candidates: List[CandidatePublication] = []

        # Strategy 1: High-fidelity Table Row parsing (Official BB Circular format)
        row_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
        cell_pattern = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL | re.IGNORECASE)
        link_pattern = re.compile(r'href=["\']([^"\']+\.pdf)["\']', re.IGNORECASE)

        rows = row_pattern.findall(html_content)
        for row_html in rows:
            cells = cell_pattern.findall(row_html)
            if len(cells) >= 4:
                date_str = re.sub(r"<[^>]+>", "", cells[0]).strip()
                title_raw = re.sub(r"<[^>]+>", "", cells[1]).strip()

                links_cell2 = link_pattern.findall(cells[2])
                links_cell3 = link_pattern.findall(cells[3])

                if not title_raw or len(title_raw) < 4:
                    continue

                pub_date = self.parse_publication_date(date_str)
                pub_type = self.infer_publication_type(title_raw, None)

                # Extract reference number from title (e.g. BRPD Circular No. 15, DOS Circular Letter No. 02)
                ref_match = re.search(
                    r"((?:BRPD|DOS|FEPD|PSD|SFD|DBI|SMESPD|ACD|SDAD|FID|FEID|DFIM|DMD|DCM)[\w\-]*(?:\s+Circular\s+Letter|\s+Circular|\s+Letter)?\s*(?:No\.|Letter No\.)?\s*[\w\-\/]+)",
                    title_raw,
                    re.IGNORECASE
                )
                ref_no = ref_match.group(1).strip() if ref_match else None

                # Process English PDF link
                if links_cell2:
                    eng_pdf_rel = links_cell2[0]
                    eng_pdf_url = urljoin(source_page_url, eng_pdf_rel)
                    dept_code = self.infer_department_code(title_raw, ref_no, eng_pdf_url)
                    candidates.append(CandidatePublication(
                        title=title_raw,
                        reference_number=ref_no,
                        department_code=dept_code,
                        publication_date=pub_date,
                        detail_url=source_page_url,
                        file_url=eng_pdf_url,
                        language="English",
                        publication_type=pub_type,
                        metadata={"raw_date": date_str, "language": "English", "relative_href": eng_pdf_rel}
                    ))

                # Process Bangla PDF link
                if links_cell3:
                    bn_pdf_rel = links_cell3[0]
                    bn_pdf_url = urljoin(source_page_url, bn_pdf_rel)
                    dept_code = self.infer_department_code(title_raw, ref_no, bn_pdf_url)
                    candidates.append(CandidatePublication(
                        title=title_raw,
                        reference_number=ref_no,
                        department_code=dept_code,
                        publication_date=pub_date,
                        detail_url=source_page_url,
                        file_url=bn_pdf_url,
                        language="Bangla",
                        publication_type=pub_type,
                        metadata={"raw_date": date_str, "language": "Bangla", "relative_href": bn_pdf_rel}
                    ))

        if candidates:
            return candidates

        # Strategy 2: Fallback anchor tag parsing
        anchor_pattern = re.compile(
            r'<a[^>]+href=["\']([^"\']+\.pdf)["\'][^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL
        )

        for match in anchor_pattern.finditer(html_content):
            href, anchor_text = match.groups()
            cleaned_anchor = re.sub(r"<[^>]+>", "", anchor_text).strip()
            
            full_pdf_url = urljoin(source_page_url, href)

            ref_match = re.search(
                r"((?:BRPD|DOS|FEPD|PSD|SFD|DBI|DFIM|SMESPD|ACD|FID|FEID)\s*(?:Circular|Circular Letter)?\s*(?:No\.|Letter No\.)?\s*[\w\-\/]+)",
                cleaned_anchor,
                re.IGNORECASE
            )
            ref_number = ref_match.group(1).strip() if ref_match else None

            date_match = re.search(r"(\d{1,2}[-\/\s]([A-Za-z]{3,}|\d{1,2})[-\/\s]\d{2,4})", cleaned_anchor)
            pub_date = self.parse_publication_date(date_match.group(1)) if date_match else None

            if not pub_date:
                url_date_match = re.search(r"([a-z]{3})(\d{1,2})(\d{4})", full_pdf_url.lower())
                if url_date_match:
                    month_str, day_str, year_str = url_date_match.groups()
                    try:
                        pub_date = datetime.strptime(f"{day_str} {month_str} {year_str}", "%d %b %Y").date()
                    except ValueError:
                        pass

            dept_code = self.infer_department_code(cleaned_anchor, ref_number, full_pdf_url)
            title = cleaned_anchor if len(cleaned_anchor) > 5 else (ref_number or "Bangladesh Bank Circular")
            pub_type = self.infer_publication_type(title, ref_number)

            candidates.append(CandidatePublication(
                title=title,
                reference_number=ref_number,
                department_code=dept_code,
                publication_date=pub_date,
                detail_url=source_page_url,
                file_url=full_pdf_url,
                language="English" if "e.pdf" in full_pdf_url.lower() else "Bangla",
                publication_type=pub_type,
                metadata={"raw_anchor": cleaned_anchor, "relative_href": href}
            ))

        return candidates

    async def discover_publications(self, max_pages: int = 1) -> DiscoveryResult:
        result = DiscoveryResult()
        
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            try:
                resp = await client.get(self.base_url, headers=self._get_headers())
                result.pages_inspected += 1

                # 1. Anti-bot challenge inspection
                challenge = self.detect_anti_bot_challenge(resp.text, resp.status_code)
                if challenge:
                    logger.warning(f"Anti-bot challenge detected while accessing {self.base_url}: {challenge.challenge_type}")
                    result.anti_bot_challenge = challenge
                    return result

                if resp.status_code != 200:
                    result.errors.append(f"HTTP {resp.status_code} received from {self.base_url}")
                    return result

                # 2. Parse candidates from HTML
                candidates = self.parse_listing_html(resp.text, self.base_url)
                result.candidate_publications = candidates
                logger.info(f"Discovered {len(candidates)} candidate circulars from {self.base_url}")

            except httpx.RequestError as req_err:
                logger.error(f"Network error connecting to {self.base_url}: {req_err}")
                result.errors.append(str(req_err))

        return result

    async def download_document(
        self,
        file_url: str,
        max_retries: int = 3,
        backoff_base_seconds: float = 1.0
    ) -> Tuple[Optional[bytes], Optional[AntiBotChallenge]]:
        """
        Downloads a document file from the official source with exponential backoff retry
        and strict magic-bytes verification.
        """
        async with httpx.AsyncClient(timeout=35.0, follow_redirects=True) as client:
            last_challenge = None
            for attempt in range(max_retries):
                try:
                    resp = await client.get(file_url, headers=self._get_headers())
                    # Check for challenge in response
                    challenge = self.detect_anti_bot_challenge(resp.text, resp.status_code)
                    if challenge:
                        return None, challenge

                    if resp.status_code == 200:
                        content = resp.content
                        # Ensure it is genuinely a PDF (%PDF-) and not an HTML challenge or error page
                        if not content.startswith(b"%PDF-"):
                            challenge = self.detect_anti_bot_challenge(resp.text, resp.status_code)
                            if challenge:
                                return None, challenge
                            return None, AntiBotChallenge(
                                is_blocked=True,
                                challenge_type="INVALID_CONTENT_TYPE",
                                status_code=resp.status_code,
                                details="Response returned non-PDF content (likely an unrecognized bot challenge or error page)."
                            )
                        return content, None
                    elif resp.status_code in [500, 502, 503, 504]:
                        # Transient server error on Bangladesh Bank side, retry with backoff
                        logger.warning(f"HTTP {resp.status_code} downloading {file_url} (attempt {attempt + 1}/{max_retries})")
                        last_challenge = AntiBotChallenge(
                            is_blocked=False,
                            challenge_type="HTTP_SERVER_ERROR",
                            status_code=resp.status_code,
                            details=f"Transient HTTP {resp.status_code} error from source."
                        )
                    else:
                        return None, AntiBotChallenge(
                            is_blocked=False,
                            challenge_type="HTTP_ERROR",
                            status_code=resp.status_code,
                            details=f"Download failed with HTTP status {resp.status_code}"
                        )
                except (httpx.RequestError, httpx.TimeoutException) as req_err:
                    logger.warning(f"Network error downloading {file_url} (attempt {attempt + 1}/{max_retries}): {req_err}")
                    last_challenge = AntiBotChallenge(
                        is_blocked=False,
                        challenge_type="NETWORK_EXCEPTION",
                        status_code=0,
                        details=f"Network exception downloading file: {str(req_err)}"
                    )

                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff_base_seconds * (2 ** attempt))

            return None, last_challenge or AntiBotChallenge(
                is_blocked=False,
                challenge_type="MAX_RETRIES_EXCEEDED",
                status_code=0,
                details=f"Failed to download after {max_retries} attempts."
            )


