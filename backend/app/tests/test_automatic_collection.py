import pytest
from datetime import date
from uuid import uuid4
import httpx
from sqlalchemy import select

from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.documents.models import Document, DocumentVersion
from backend.app.modules.sources.connector.bangladesh_bank import BangladeshBankConnector
from backend.app.modules.sources.connector.base import AntiBotChallenge, CandidatePublication
from backend.app.modules.sources.models import Source, SourceDiscovery, SourceRun
from backend.app.modules.sources.service import source_monitoring_service
from backend.app.workers.scheduler import ScheduledMonitoringService


@pytest.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


SAMPLE_BB_ROW_HTML = """
<table class="table">
  <tr>
    <td>07/11/2026</td>
    <td>BRPD-1 Circular Letter No. 37: Pre-Finance Scheme to support the closed industry and service sectors.</td>
    <td><a href="/mediaroom/circulars/brpd/nov072026brpd37e.pdf">English</a></td>
    <td><a href="/mediaroom/circulars/brpd/nov072026brpd37.pdf">Bangla</a></td>
  </tr>
  <tr>
    <td>05/11/2026</td>
    <td>DOS Circular Letter No. 22: Scheduled Bank will remain closed on 31 December 2025.</td>
    <td><a href="/mediaroom/circulars/dos/nov052026dos22e.pdf">English</a></td>
    <td></td>
  </tr>
  <tr>
    <td>02/11/2026</td>
    <td>FEPD Circular No. 10: Guidelines on foreign exchange operations</td>
    <td></td>
    <td><a href="/mediaroom/circulars/fepd/nov022026fepd10.pdf">Bangla</a></td>
  </tr>
</table>
"""


def test_bb_parser_extracts_candidates_accurately():
    connector = BangladeshBankConnector()
    candidates = connector.parse_listing_html(SAMPLE_BB_ROW_HTML, "https://www.bb.org.bd/en/index.php/mediaroom/circular")

    # Row 1 has both English and Bangla -> 2 candidates
    # Row 2 has English -> 1 candidate
    # Row 3 has Bangla -> 1 candidate
    # Total candidates = 4
    assert len(candidates) == 4

    # Check Candidate 1: English BRPD
    c1 = candidates[0]
    assert c1.department_code == "BRPD"
    assert c1.language == "English"
    assert c1.reference_number == "BRPD-1 Circular Letter No. 37"
    assert c1.publication_type == "CIRCULAR_LETTER"
    assert c1.publication_date == date(2026, 11, 7)
    assert c1.file_url == "https://www.bb.org.bd/mediaroom/circulars/brpd/nov072026brpd37e.pdf"

    # Check Candidate 2: Bangla BRPD
    c2 = candidates[1]
    assert c2.department_code == "BRPD"
    assert c2.language == "Bangla"
    assert c2.reference_number == "BRPD-1 Circular Letter No. 37"
    assert c2.file_url == "https://www.bb.org.bd/mediaroom/circulars/brpd/nov072026brpd37.pdf"

    # Check Candidate 3: English DOS
    c3 = candidates[2]
    assert c3.department_code == "DOS"
    assert c3.language == "English"
    assert c3.reference_number == "DOS Circular Letter No. 22"
    assert c3.publication_type == "CIRCULAR_LETTER"

    # Check Candidate 4: Bangla FEPD
    c4 = candidates[3]
    assert c4.department_code == "FEPD"
    assert c4.language == "Bangla"
    assert c4.reference_number == "FEPD Circular No. 10"
    assert c4.publication_type == "POLICY_GUIDELINE"


def test_bb_date_parser_formats():
    assert BangladeshBankConnector.parse_publication_date("07/11/2026") == date(2026, 11, 7)
    assert BangladeshBankConnector.parse_publication_date("07-11-2026") == date(2026, 11, 7)
    assert BangladeshBankConnector.parse_publication_date("07/11/26") == date(2026, 11, 7)
    assert BangladeshBankConnector.parse_publication_date("27 Nov 2024") == date(2024, 11, 27)
    assert BangladeshBankConnector.parse_publication_date("invalid-date") is None


def test_bb_infer_department_and_type():
    assert BangladeshBankConnector.infer_department_code("Notice", None, "https://www.bb.org.bd/mediaroom/circulars/smespd/sme01.pdf") == "SMESPD"
    assert BangladeshBankConnector.infer_department_code("BRPD Circular No. 1", None, "https://example.com/file.pdf") == "BRPD"
    assert BangladeshBankConnector.infer_department_code("Foreign Exchange Notice", "FEPD-1", "https://example.com/file.pdf") == "FEPD"

    assert BangladeshBankConnector.infer_publication_type("BRPD Circular Letter No. 1", None) == "CIRCULAR_LETTER"
    assert BangladeshBankConnector.infer_publication_type("Credit Risk Guidelines", None) == "POLICY_GUIDELINE"
    assert BangladeshBankConnector.infer_publication_type("Master Circular on Capital Adequacy", None) == "CIRCULAR"


def test_anti_bot_detection_mechanisms():
    connector = BangladeshBankConnector()

    # Imperva TSPD challenge detection
    imperva_html = "<html><body>What code is in the image? bobcmn Support ID is: 123456789</body></html>"
    ch = connector.detect_anti_bot_challenge(imperva_html, 200)
    assert ch is not None
    assert ch.is_blocked is True
    assert ch.challenge_type == "IMPERVA_TSPD_CAPTCHA"
    assert ch.support_id == "123456789"

    # Cloudflare challenge
    cf_html = "<html><body>cf-browser-verification Ray ID: abcd1234ef</body></html>"
    ch2 = connector.detect_anti_bot_challenge(cf_html, 403)
    assert ch2 is not None
    assert ch2.challenge_type == "CLOUDFLARE_CHALLENGE"

    # Rate limiting
    ch3 = connector.detect_anti_bot_challenge("Too many requests", 429)
    assert ch3 is not None
    assert ch3.challenge_type == "RATE_LIMIT_429"

    # Clean standard HTML
    clean_html = "<html><body><h1>Bangladesh Bank Circulars</h1></body></html>"
    assert connector.detect_anti_bot_challenge(clean_html, 200) is None


class _FakeResponse:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.text = content.decode("utf-8", errors="ignore")
        self.headers = headers or {}


@pytest.mark.asyncio
async def test_download_document_magic_bytes_validation(monkeypatch):
    connector = BangladeshBankConnector()
    corrupted_html = b"<html><body>Error 404 Not Found</body></html>"
    calls = []

    async def fake_get(self, url, **kwargs):
        calls.append(url)
        return _FakeResponse(200, corrupted_html)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    content, challenge = await connector.download_document(
        "https://www.bb.org.bd/mediaroom/circulars/brpd/corrupt.pdf", backoff_base_seconds=0
    )
    assert content is None
    assert challenge is not None
    assert challenge.challenge_type == "INVALID_CONTENT_TYPE"
    assert calls == ["https://www.bb.org.bd/mediaroom/circulars/brpd/corrupt.pdf"]

    # A genuine PDF payload is accepted
    async def fake_pdf_get(self, url, **kwargs):
        return _FakeResponse(200, b"%PDF-1.7 minimal")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_pdf_get)
    content, challenge = await connector.download_document(
        "https://www.bb.org.bd/mediaroom/circulars/brpd/ok.pdf", backoff_base_seconds=0
    )
    assert challenge is None
    assert content.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_source_monitoring_stats(db_session):
    from backend.app.tests.factories import make_institution

    inst = await make_institution()
    source_a = Source(institution_id=inst.id, name=f"Stats source A {uuid4().hex[:6]}",
                      base_url="https://www.bb.org.bd/en/index.php/mediaroom/circular")
    source_b = Source(institution_id=inst.id, name=f"Stats source B {uuid4().hex[:6]}",
                      base_url="https://www.bb.org.bd/en/index.php/mediaroom/circular")
    db_session.add_all([source_a, source_b])
    await db_session.flush()
    run_a = SourceRun(source_id=source_a.id, run_type="TEST", status="COMPLETED")
    run_b = SourceRun(source_id=source_b.id, run_type="TEST", status="COMPLETED")
    db_session.add_all([run_a, run_b])
    await db_session.flush()

    def disc(run, status, dept, lang, year):
        return SourceDiscovery(
            source_run_id=run.id,
            source_url="https://www.bb.org.bd/list",
            file_url=f"https://www.bb.org.bd/{uuid4().hex}.pdf",
            department_code=dept,
            language=lang,
            publication_date=date(year, 1, 15),
            status=status,
        )

    db_session.add_all([
        disc(run_a, "INGESTED", "BRPD", "English", 2025),
        disc(run_a, "VALIDATED", "BRPD", "Bangla", 2026),
        disc(run_a, "DUPLICATE", "DOS", "English", 2026),
        disc(run_a, "FAILED", "DOS", "English", 2026),
        # Belongs to another source and must not be counted for source A
        disc(run_b, "INGESTED", "FEPD", "English", 2024),
        disc(run_b, "INGESTED", "FEPD", "English", 2024),
    ])
    await db_session.commit()

    stats = await source_monitoring_service.get_source_stats(db_session, source_a.id)
    assert stats["source_id"] == source_a.id
    assert stats["total_discovered"] == 4
    assert stats["total_ingested"] == 1
    assert stats["total_pending"] == 1
    assert stats["total_duplicates"] == 1
    assert stats["total_failed"] == 1
    assert stats["department_breakdown"] == {"BRPD": 2, "DOS": 2}
    assert stats["year_breakdown"] == {"2026": 3, "2025": 1}
    assert stats["language_breakdown"] == {"English": 3, "Bangla": 1}

    stats_b = await source_monitoring_service.get_source_stats(db_session, source_b.id)
    assert stats_b["total_discovered"] == 2
    assert stats_b["total_ingested"] == 2


@pytest.mark.asyncio
async def test_scheduled_monitoring_service_lifecycle():
    service = ScheduledMonitoringService()
    assert service._is_running is False
    await service.start()
    assert service._is_running is True
    await service.stop()
    assert service._is_running is False
