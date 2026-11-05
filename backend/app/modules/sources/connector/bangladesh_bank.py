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
        combined = f"{title} {ref_number or ''} {url}".upper()
        depts = ["BRPD", "DOS", "FEPD", "PSD", "DBI", "SFD", "DFIM", "SMESPD", "ACD", "SDG"]
        for dept in depts:
            if dept in combined:
                return dept
        return None

    def parse_listing_html(self, html_content: str, source_page_url: str) -> List[CandidatePublication]:
        """
        Parses Bangladesh Bank circular listing HTML table or links.
        Extracts candidate circular items.
        """
        candidates: List[CandidatePublication] = []

        # Find all <a> tags with href ending in .pdf or containing circulars
        # Pattern 1: Table row with date, title, link
        # Look for links to PDFs
        link_pattern = re.compile(
            r'<a[^>]+href=["\']([^"\']+\.pdf)["\'][^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL
        )

        for match in link_pattern.finditer(html_content):
            href, anchor_text = match.groups()
            cleaned_anchor = re.sub(r"<[^>]+>", "", anchor_text).strip()
            
            # Normalize URL
            full_pdf_url = urljoin(source_page_url, href)

            # Look for reference number in anchor or surrounding context
            ref_match = re.search(r"((BRPD|DOS|FEPD|PSD|SFD|DBI)\s*(Circular|Circular Letter)?\s*(No\.|Letter No\.)?\s*[\w\-\/]+)", cleaned_anchor, re.IGNORECASE)
            ref_number = ref_match.group(1).strip() if ref_match else None

            # Look for date in anchor or url
            date_match = re.search(r"(\d{1,2}[-\/\s]([A-Za-z]{3,}|\d{1,2})[-\/\s]\d{4})", cleaned_anchor)
            pub_date = self.parse_publication_date(date_match.group(1)) if date_match else None

            # Fallback date from URL pattern: e.g. nov272024brpd15e.pdf
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

            candidate = CandidatePublication(
                title=title,
                reference_number=ref_number,
                department_code=dept_code,
                publication_date=pub_date,
                detail_url=source_page_url,
                file_url=full_pdf_url,
                metadata={"raw_anchor": cleaned_anchor, "relative_href": href}
            )
            candidates.append(candidate)

        return candidates

    async def discover_publications(self, max_pages: int = 1) -> DiscoveryResult:
        result = DiscoveryResult()
        
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
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

    async def download_document(self, file_url: str) -> Tuple[Optional[bytes], Optional[AntiBotChallenge]]:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            try:
                resp = await client.get(file_url, headers=self._get_headers())
                # Check for challenge in response
                challenge = self.detect_anti_bot_challenge(resp.text, resp.status_code)
                if challenge:
                    return None, challenge

                if resp.status_code == 200:
                    content = resp.content
                    # Ensure it is actually a PDF and not an HTML challenge disguised as 200
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
                else:
                    return None, AntiBotChallenge(
                        is_blocked=False,
                        challenge_type="HTTP_ERROR",
                        status_code=resp.status_code,
                        details=f"Download failed with HTTP status {resp.status_code}"
                    )
            except httpx.RequestError as e:
                return None, AntiBotChallenge(
                    is_blocked=False,
                    challenge_type="NETWORK_EXCEPTION",
                    status_code=0,
                    details=f"Network exception downloading file: {str(e)}"
                )

