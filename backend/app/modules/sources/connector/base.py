from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class CandidatePublication(BaseModel):
    title: str
    reference_number: Optional[str] = None
    department_code: Optional[str] = None
    publication_date: Optional[date] = None
    detail_url: str
    file_url: Optional[str] = None
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


class BaseSourceConnector(ABC):
    @abstractmethod
    async def discover_publications(self, max_pages: int = 1) -> DiscoveryResult:
        """Discovers candidate regulatory publications from the remote source."""
        pass

    @abstractmethod
    async def download_document(self, file_url: str) -> tuple[Optional[bytes], Optional[AntiBotChallenge]]:
        """Downloads the PDF file bytes while respecting access restrictions."""
        pass

    @staticmethod
    def detect_anti_bot_challenge(content: str, status_code: int) -> Optional[AntiBotChallenge]:
        """
        Inspects HTTP response to detect WAF / bot challenge pages deterministically.
        Never attempts to bypass or solve challenges.
        """
        lowered = content.lower()
        if "what code is in the image?" in lowered or "bobcmn" in lowered or "tspd_" in content:
            # Extract support ID if present
            support_id = None
            import re
            m = re.search(r"support id is:\s*(\d+)", content, re.IGNORECASE)
            if m:
                support_id = m.group(1)
            return AntiBotChallenge(
                is_blocked=True,
                challenge_type="IMPERVA_TSPD_CAPTCHA",
                status_code=status_code,
                support_id=support_id,
                details="Access restricted by Imperva/TSPD WAF JavaScript challenge. Automation halted per security rules."
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

