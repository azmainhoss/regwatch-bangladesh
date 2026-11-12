import re
from abc import ABC, abstractmethod
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ListingOutcome(str, Enum):
    """Result of one listing check. Anything but OK means "failed, try later", never "nothing new"."""
    OK = "OK"
    CHALLENGE = "CHALLENGE"  # bot check page (/TSPD/, "bobcmn", "What code is in the image")
    NO_TABLE = "NO_TABLE"  # 200 reply without the circular table
    HTTP_ERROR = "HTTP_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"


class CandidatePublication(BaseModel):
    title: str
    reference_number: Optional[str] = None
    department_code: Optional[str] = None
    publication_date: Optional[date] = None
    detail_url: str
    file_url: Optional[str] = None
    language: Optional[str] = None
    publication_type: Optional[str] = "CIRCULAR"
    metadata: Dict[str, Any] = {}


class AntiBotChallenge(BaseModel):
    is_blocked: bool
    challenge_type: Optional[str] = None  # e.g. "IMPERVA_TSPD_CAPTCHA", "CLOUDFLARE_TURNSTILE", "RATE_LIMIT_429"
    status_code: int
    support_id: Optional[str] = None
    details: str = ""


class DiscoveryResult(BaseModel):
    pages_inspected: int = 0
    candidate_publications: List[CandidatePublication] = []
    anti_bot_challenge: Optional[AntiBotChallenge] = None
    errors: List[str] = []
    outcome: ListingOutcome = ListingOutcome.OK
    status_code: Optional[int] = None
    bytes_received: int = 0


class FetchedFile(BaseModel):
    """A downloaded file with the reply headers the archive keeps."""
    content: Optional[bytes] = None
    challenge: Optional[AntiBotChallenge] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    fetched_at: Optional[datetime] = None
    url: Optional[str] = None

    @property
    def rejected(self) -> bool:
        """The site refused this one file ("Request Rejected"). Skip it; it is not a block."""
        return bool(self.challenge and self.challenge.challenge_type == "REQUEST_REJECTED")


class BaseSourceConnector(ABC):
    @abstractmethod
    async def discover_publications(self, max_pages: int = 1, mode: str = "poll") -> DiscoveryResult:
        """Checks the listing for publications. mode "poll" is the light recent check,
        "reconcile" the full list. The result's outcome must be OK before rows are trusted."""
        pass

    @abstractmethod
    async def download_document(self, file_url: str) -> tuple[Optional[bytes], Optional[AntiBotChallenge]]:
        """Downloads the PDF file bytes while respecting access restrictions."""
        pass

    async def fetch_document(self, file_url: str) -> FetchedFile:
        """Downloads a file and keeps its reply headers. Connectors may override this."""
        content, challenge = await self.download_document(file_url)
        return FetchedFile(content=content, challenge=challenge, url=file_url)

    @staticmethod
    def is_request_rejected(content: str) -> bool:
        lowered = content.lower()
        return "request rejected" in lowered or "the requested url was rejected" in lowered

    @staticmethod
    def detect_anti_bot_challenge(content: str, status_code: int) -> Optional[AntiBotChallenge]:
        """
        Inspects HTTP response to detect WAF / bot challenge pages deterministically.
        Never attempts to bypass or solve challenges.
        """
        lowered = content.lower()
        # Only flag genuine bot check pages, not harmless mentions of cookies in normal 200 OK responses
        is_imperva_challenge = (
            ("what code is in the image" in lowered or "bobcmn" in lowered or "/tspd/" in lowered)
            or (status_code in (403, 503) and ("tspd_" in content or "support id is:" in lowered))
        )
        if is_imperva_challenge:
            # Extract support ID if present
            support_id = None
            m = re.search(r"support id is:\s*(\d+)", content, re.IGNORECASE)
            if m:
                support_id = m.group(1)
            return AntiBotChallenge(
                is_blocked=True,
                challenge_type="IMPERVA_TSPD_CAPTCHA",
                status_code=status_code,
                support_id=support_id,
                details="Bot check page (TSPD/image code) instead of content. The check failed and will be retried after a back-off."
            )

        if "cf-browser-verification" in lowered or "ray id:" in lowered:
            return AntiBotChallenge(
                is_blocked=True,
                challenge_type="CLOUDFLARE_CHALLENGE",
                status_code=status_code,
                details="Cloudflare challenge page detected."
            )

        if status_code == 429:
            return AntiBotChallenge(
                is_blocked=True,
                challenge_type="RATE_LIMIT_429",
                status_code=status_code,
                details="HTTP 429 Too Many Requests: Rate limit exceeded."
            )

        return None

