"""New-circular checker, request pacing, schedule and archive re-check.

Everything here runs on saved HTML and fake replies. No test talks to bb.org.bd.
"""
import asyncio
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pymupdf
import pytest
from sqlalchemy import select

from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.documents.models import Document, DocumentVersion
from backend.app.modules.documents.service import document_ingestion_service
from backend.app.modules.sources.connector.bangladesh_bank import BangladeshBankConnector
from backend.app.modules.sources.connector.base import AntiBotChallenge, FetchedFile, ListingOutcome
from backend.app.modules.sources.connector.pacing import RequestGate, bb_request_gate
from backend.app.modules.sources.models import Source, SourceDiscovery, SourceRun
from backend.app.modules.sources.service import backoff_minutes, source_in_backoff, source_monitoring_service
from backend.app.tests.factories import make_institution, make_user
from backend.app.workers.scheduler import next_run

BB_LIST_URL = "https://www.bb.org.bd/en/index.php/mediaroom/circular"
FIXTURES = Path(__file__).parent / "fixtures" / "bb_listing"
DATE_FILTER_REPLY = (FIXTURES / "date_filter_reply.html").read_text(encoding="utf-8")
DHAKA = ZoneInfo("Asia/Dhaka")

CHALLENGE_PAGE = """<html><head><script src="/TSPD/08a1b2c3?type=7"></script>
<script>window["bobcmn"] = "1011101";</script></head>
<body><b>What code is in the image?</b> Your support ID is: 1234567890.</body></html>"""

NO_TABLE_PAGE = "<html><body><h1>Circulars</h1><p>Service temporarily unavailable.</p></body></html>"

REJECTED_PAGE = """<html><head><title>Request Rejected</title></head>
<body>The requested URL was rejected. Please consult with your administrator.<br><br>
Your support ID is: 9876543210<br><br><a href='javascript:history.back();'>[Go Back]</a></body></html>"""


def _make_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


class _Reply:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.text = content.decode("utf-8", errors="ignore")
        self.headers = headers or {}


async def _make_source(institution_id) -> Source:
    async with AsyncSessionLocal() as db:
        src = Source(institution_id=institution_id, name=f"Checker source {uuid.uuid4().hex[:6]}", base_url=BB_LIST_URL)
        db.add(src)
        await db.commit()
        await db.refresh(src)
        return src


async def _add_discovery(source_id, file_url: str, pub_date: date) -> SourceDiscovery:
    async with AsyncSessionLocal() as db:
        run = SourceRun(source_id=source_id, run_type="TEST", status="COMPLETED")
        db.add(run)
        await db.flush()
        disc = SourceDiscovery(
            source_run_id=run.id, source_url=BB_LIST_URL, file_url=file_url,
            title=f"Fixture circular {uuid.uuid4().hex[:6]}", reference_number=f"FIX-{uuid.uuid4().hex[:6]}",
            publication_date=pub_date, status="VALIDATED",
        )
        db.add(disc)
        await db.commit()
        await db.refresh(disc)
        return disc


# ---------------------------------------------------------------------------
# Parsing the date-filter reply
# ---------------------------------------------------------------------------
def test_date_filter_reply_is_parsed_into_pdf_candidates():
    connector = BangladeshBankConnector()
    assert connector.classify_listing(200, DATE_FILTER_REPLY) == (ListingOutcome.OK, "")
    candidates = connector.parse_listing_html(DATE_FILTER_REPLY, BB_LIST_URL)

    urls = [c.file_url for c in candidates]
    assert urls == [
        "https://www.bb.org.bd/mediaroom/circulars/fepd/nov112026fepd-142e.pdf",
        "https://www.bb.org.bd/mediaroom/circulars/brpd/nov102026brpdl38e.pdf",
        "https://www.bb.org.bd/mediaroom/circulars/brpd/nov102026brpdl38.pdf",
        "https://www.bb.org.bd/mediaroom/circulars/dos/nov092026dos07.pdf",
    ]  # the onclick and the Download link of one file count once; "Not Available" gives nothing

    fepd = candidates[0]
    assert fepd.title == "FEPD-1 Circular No. 42: Import transactions under usance terms"
    assert fepd.publication_date == date(2026, 11, 11)
    assert fepd.reference_number == "FEPD-1 Circular No. 42"
    assert fepd.department_code == "FEPD"
    assert fepd.language == "English" and fepd.metadata["lang"] == "en"

    assert candidates[1].title == "BRPD Circular Letter No. 38: Loan rescheduling & one-time exit facility"
    assert candidates[1].metadata["lang"] == "en"
    assert candidates[2].metadata["lang"] == "bn" and candidates[2].language == "Bangla"
    assert candidates[3].metadata["lang"] == "bn" and candidates[3].department_code == "DOS"


def test_listing_outcomes():
    classify = BangladeshBankConnector.classify_listing
    assert classify(200, CHALLENGE_PAGE)[0] == ListingOutcome.CHALLENGE
    assert classify(200, NO_TABLE_PAGE)[0] == ListingOutcome.NO_TABLE
    assert classify(500, "<html>Internal Server Error</html>")[0] == ListingOutcome.HTTP_ERROR
    # A table with no header row is not the circular list
    assert classify(200, "<table><tr><td>x</td></tr></table>")[0] == ListingOutcome.NO_TABLE


def test_bare_pdf_links_outside_the_table_are_ignored():
    html = '<html><body><a href="/mediaroom/circulars/brpd/stray.pdf">BRPD Circular No. 1</a></body></html>'
    assert BangladeshBankConnector().parse_listing_html(html, BB_LIST_URL) == []


@pytest.mark.asyncio
async def test_poll_recent_posts_the_date_filter(monkeypatch):
    sent = {}

    async def fake_post(self, url, data=None, headers=None, **kwargs):
        sent.update(url=url, data=data, headers=headers)
        return _Reply(200, DATE_FILTER_REPLY.encode())

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    result = await BangladeshBankConnector().poll_recent(days=7, today=date(2026, 11, 12))
    assert result.outcome == ListingOutcome.OK
    assert len(result.candidate_publications) == 4
    assert sent["url"] == BB_LIST_URL
    assert sent["data"] == {"from_date": "2026-11-05", "to_date": "2026-11-12", "search_circular": "Search"}
    assert sent["headers"]["User-Agent"] == "RegWatchBot/0.1"


# ---------------------------------------------------------------------------
# Failed checks are FAILED_RETRY, never "COMPLETED with 0 new"
# ---------------------------------------------------------------------------
async def _run_check(monkeypatch, source_id, reply=None, error=None) -> SourceRun:
    async def fake_post(self, url, **kwargs):
        if error:
            raise error
        return reply

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    async with AsyncSessionLocal() as db:
        return await source_monitoring_service.execute_discovery_scan(db=db, source_id=source_id, run_type="TEST")


@pytest.mark.asyncio
@pytest.mark.parametrize("reply,error,outcome", [
    (_Reply(200, CHALLENGE_PAGE.encode()), None, "CHALLENGE"),
    (_Reply(200, NO_TABLE_PAGE.encode()), None, "NO_TABLE"),
    (_Reply(500, b"<html>Internal Server Error</html>"), None, "HTTP_ERROR"),
    (None, httpx.ConnectError("connection refused"), "NETWORK_ERROR"),
])
async def test_failed_listing_check_is_failed_retry(monkeypatch, reply, error, outcome):
    inst = await make_institution()
    src = await _make_source(inst.id)
    run = await _run_check(monkeypatch, src.id, reply, error)
    assert run.status == "FAILED_RETRY"
    assert run.outcome == outcome
    assert run.valid_documents_discovered == 0
    async with AsyncSessionLocal() as db:
        found = (await db.execute(
            select(SourceDiscovery).join(SourceRun).where(SourceRun.source_id == src.id)
        )).scalars().all()
        source = await db.get(Source, src.id)
    assert found == []
    assert source.last_successful_run_at is None
    assert source.config["consecutive_failures"] == 1


@pytest.mark.asyncio
async def test_repeated_failures_back_off_and_success_clears_it(monkeypatch):
    inst = await make_institution()
    src = await _make_source(inst.id)
    await _run_check(monkeypatch, src.id, _Reply(200, CHALLENGE_PAGE.encode()))
    await _run_check(monkeypatch, src.id, _Reply(200, CHALLENGE_PAGE.encode()))
    async with AsyncSessionLocal() as db:
        source = await db.get(Source, src.id)
        assert source.config["consecutive_failures"] == 2
        assert source_in_backoff(source)
        assert source.access_restriction_status == "IMPERVA_TSPD_CAPTCHA"

    ok = await _run_check(monkeypatch, src.id, _Reply(200, DATE_FILTER_REPLY.encode()))
    assert ok.status == "COMPLETED" and ok.outcome == "OK"
    async with AsyncSessionLocal() as db:
        source = await db.get(Source, src.id)
        assert not source_in_backoff(source)
        assert "consecutive_failures" not in source.config
        assert source.access_restriction_status == "CLEAR"


def test_backoff_rises_from_30_minutes_to_6_hours():
    assert [backoff_minutes(n) for n in (1, 2, 3, 4, 5, 6, 7, 20)] == [0, 30, 60, 120, 240, 360, 360, 360]


@pytest.mark.asyncio
async def test_successful_check_records_new_rows_once_by_pdf_url(monkeypatch):
    inst = await make_institution()
    src = await _make_source(inst.id)
    first = await _run_check(monkeypatch, src.id, _Reply(200, DATE_FILTER_REPLY.encode()))
    assert first.status == "COMPLETED"
    assert first.valid_documents_discovered == 4
    second = await _run_check(monkeypatch, src.id, _Reply(200, DATE_FILTER_REPLY.encode()))
    assert second.status == "COMPLETED"
    assert second.valid_documents_discovered == 0
    assert second.duplicate_count == 4


# ---------------------------------------------------------------------------
# Downloads: Request Rejected skips one file, the next one proceeds
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_request_rejected_file_is_skipped_and_next_file_proceeds(monkeypatch):
    inst = await make_institution()
    src = await _make_source(inst.id)
    rejected_url = f"https://www.bb.org.bd/mediaroom/circulars/brpd/rejected-{uuid.uuid4().hex[:6]}.pdf"
    good_url = f"https://www.bb.org.bd/mediaroom/circulars/brpd/good-{uuid.uuid4().hex[:6]}.pdf"
    # Newest first: the rejected file is tried before the good one.
    d_rejected = await _add_discovery(src.id, rejected_url, date(2026, 11, 11))
    d_good = await _add_discovery(src.id, good_url, date(2026, 11, 10))
    pdf = _make_pdf(f"Circular body {uuid.uuid4().hex}")
    calls = []

    async def fake_get(self, url, **kwargs):
        calls.append(url)
        if url == rejected_url:
            return _Reply(200, REJECTED_PAGE.encode())
        return _Reply(200, pdf, headers={"ETag": '"abc-123"', "Last-Modified": "Tue, 10 Nov 2026 09:30:00 GMT"})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with AsyncSessionLocal() as db:
        result = await source_monitoring_service.execute_backfill_batch(db=db, source_id=src.id, batch_size=10)

    assert calls == [rejected_url, good_url]
    assert result["skipped_rejected"] == 1
    assert result["successful"] == 1
    async with AsyncSessionLocal() as db:
        rejected = await db.get(SourceDiscovery, d_rejected.id)
        good = await db.get(SourceDiscovery, d_good.id)
        source = await db.get(Source, src.id)
        version = (await db.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == good.document_id)
        )).scalars().one()
    assert rejected.status == "SKIPPED_REJECTED"
    assert rejected.retry_count == 0
    assert good.status == "INGESTED"
    assert good.etag == '"abc-123"' and good.last_modified == "Tue, 10 Nov 2026 09:30:00 GMT"
    assert good.fetched_at is not None
    assert source.access_restriction_status == "CLEAR"  # one refused file does not mark the source restricted
    assert version.etag == '"abc-123"'
    assert version.source_url == good_url
    assert version.status == "CURRENT"


@pytest.mark.asyncio
async def test_bot_check_on_download_stops_the_batch(monkeypatch):
    inst = await make_institution()
    src = await _make_source(inst.id)
    d1 = await _add_discovery(src.id, f"https://www.bb.org.bd/mediaroom/circulars/x/{uuid.uuid4().hex[:6]}.pdf", date(2026, 11, 11))
    await _add_discovery(src.id, f"https://www.bb.org.bd/mediaroom/circulars/x/{uuid.uuid4().hex[:6]}.pdf", date(2026, 11, 10))
    calls = []

    async def fake_get(self, url, **kwargs):
        calls.append(url)
        return _Reply(200, CHALLENGE_PAGE.encode())

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with AsyncSessionLocal() as db:
        await source_monitoring_service.execute_backfill_batch(db=db, source_id=src.id, batch_size=10)
    assert len(calls) == 1
    async with AsyncSessionLocal() as db:
        disc = await db.get(SourceDiscovery, d1.id)
    assert disc.status == "DOWNLOAD_PENDING"  # still queued for a later try


# ---------------------------------------------------------------------------
# Pace: one request at a time, at least 15 s apart
# ---------------------------------------------------------------------------
class _FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


@pytest.mark.asyncio
async def test_gate_spaces_requests_15_seconds_apart():
    clock = _FakeClock()
    gate = RequestGate(min_gap_seconds=15, clock=clock, sleep=clock.sleep)
    starts = []
    for work in (2.0, 0.0, 0.0):
        async with gate.slot():
            starts.append(clock.now)
            clock.now += work  # time the request itself takes
    clock.now += 20  # a long pause: no wait needed
    async with gate.slot():
        starts.append(clock.now)
    assert clock.sleeps == [15, 15]
    assert starts[1] - (starts[0] + 2.0) == 15
    assert starts[2] - starts[1] == 15


@pytest.mark.asyncio
async def test_gate_allows_only_one_request_at_a_time():
    clock = _FakeClock()
    gate = RequestGate(min_gap_seconds=15, clock=clock, sleep=clock.sleep)
    inside = 0
    most = 0

    async def request():
        nonlocal inside, most
        async with gate.slot():
            inside += 1
            most = max(most, inside)
            await asyncio.sleep(0)
            inside -= 1

    await asyncio.gather(*(request() for _ in range(5)))
    assert most == 1
    assert clock.sleeps == [15, 15, 15, 15]


@pytest.mark.asyncio
async def test_connector_requests_go_through_the_shared_gate(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(bb_request_gate, "_min_gap", 15.0)
    monkeypatch.setattr(bb_request_gate, "clock", clock)
    monkeypatch.setattr(bb_request_gate, "sleep", clock.sleep)
    monkeypatch.setattr(bb_request_gate, "last_request_end", None)

    async def fake_post(self, url, **kwargs):
        return _Reply(200, DATE_FILTER_REPLY.encode())

    async def fake_get(self, url, **kwargs):
        return _Reply(200, b"%PDF-1.7 minimal")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    connector = BangladeshBankConnector()
    await connector.poll_recent(today=date(2026, 11, 12))
    await connector.fetch_document("https://www.bb.org.bd/mediaroom/circulars/brpd/a.pdf")
    await connector.fetch_document("https://www.bb.org.bd/mediaroom/circulars/brpd/b.pdf")
    assert clock.sleeps == [15, 15]


# ---------------------------------------------------------------------------
# Schedule (Asia/Dhaka)
# ---------------------------------------------------------------------------
def _dhaka(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=DHAKA)


@pytest.mark.parametrize("now,expected,kind", [
    # Sunday 15 Nov 2026, a working day: every 10 minutes
    (_dhaka(2026, 11, 15, 10, 5), _dhaka(2026, 11, 15, 10, 15), "poll"),
    # Friday 13 Nov 2026: hourly
    (_dhaka(2026, 11, 13, 12, 0), _dhaka(2026, 11, 13, 13, 0), "poll"),
    # After the window: next day at 10:00
    (_dhaka(2026, 11, 15, 18, 30), _dhaka(2026, 11, 16, 10, 0), "poll"),
    # Before the window: same day at 10:00
    (_dhaka(2026, 11, 15, 7, 0), _dhaka(2026, 11, 15, 10, 0), "poll"),
    # The daily full-list reconcile at 17:50 comes before the 17:55 poll
    (_dhaka(2026, 11, 15, 17, 45), _dhaka(2026, 11, 15, 17, 50), "reconcile"),
    # After the reconcile the next poll would fall outside the window
    (_dhaka(2026, 11, 15, 17, 51), _dhaka(2026, 11, 16, 10, 0), "poll"),
    # Friday 10:30: the weekly archive re-check at 11:00 comes before the 11:30 poll
    (_dhaka(2026, 11, 13, 10, 30), _dhaka(2026, 11, 13, 11, 0), "recheck"),
])
def test_next_run(now, expected, kind):
    assert next_run(now) == (expected, kind)


def test_next_run_friday_hourly_from_11():
    when, kind = next_run(_dhaka(2026, 11, 13, 11, 0))
    assert (when - _dhaka(2026, 11, 13, 11, 0), kind) == (timedelta(minutes=60), "poll")


def test_next_run_accepts_utc_input():
    # 04:05 UTC is 10:05 in Dhaka
    from datetime import timezone
    when, kind = next_run(datetime(2026, 11, 15, 4, 5, tzinfo=timezone.utc))
    assert when == _dhaka(2026, 11, 15, 10, 15) and kind == "poll"


# ---------------------------------------------------------------------------
# Weekly archive re-check
# ---------------------------------------------------------------------------
class _FakeArchiveSite:
    """Answers HEAD and GET for a few URLs; everything else is a 404."""

    def __init__(self):
        self.files = {}
        self.head_calls = []
        self.get_calls = []

    async def head_document(self, url):
        self.head_calls.append(url)
        if url not in self.files:
            return FetchedFile(url=url, challenge=AntiBotChallenge(
                is_blocked=False, challenge_type="HTTP_ERROR", status_code=404, details="not found"))
        content, etag, last_modified = self.files[url]
        return FetchedFile(url=url, etag=etag, last_modified=last_modified, fetched_at=datetime.now(DHAKA))

    async def fetch_document(self, url):
        self.get_calls.append(url)
        content, etag, last_modified = self.files[url]
        return FetchedFile(url=url, content=content, etag=etag, last_modified=last_modified,
                           fetched_at=datetime.now(DHAKA))


async def _ingest(url, pdf, etag, owner_user_id=None):
    inst = await make_institution()
    async with AsyncSessionLocal() as db:
        doc, version, _ = await document_ingestion_service.ingest_document(
            db=db, pdf_bytes=pdf, institution_id=inst.id, title=f"Archive test {uuid.uuid4().hex[:6]}",
            publication_date=date(2026, 10, 1), reference_number=f"ARCH-{uuid.uuid4().hex[:6]}",
            source_url=url, etag=etag, last_modified="Thu, 01 Oct 2026 10:00:00 GMT",
            fetched_at=datetime.now(DHAKA), owner_user_id=owner_user_id,
        )
        return doc.id, version.id


@pytest.mark.asyncio
async def test_recheck_changed_file_becomes_new_version_and_old_is_superseded():
    url = f"https://www.bb.org.bd/mediaroom/circulars/brpd/arch-{uuid.uuid4().hex[:6]}.pdf"
    old_pdf = _make_pdf(f"Original text {uuid.uuid4().hex}")
    new_pdf = _make_pdf(f"Replaced text {uuid.uuid4().hex}")
    doc_id, old_version_id = await _ingest(url, old_pdf, '"v1"')

    site = _FakeArchiveSite()
    site.files[url] = (new_pdf, '"v2"', "Mon, 09 Nov 2026 10:00:00 GMT")
    async with AsyncSessionLocal() as db:
        summary = await source_monitoring_service.recheck_archive(db, connector=site)
    assert url in site.head_calls and site.get_calls == [url]
    assert summary["new_versions"] >= 1

    async with AsyncSessionLocal() as db:
        doc = await db.get(Document, doc_id)
        versions = (await db.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == doc_id).order_by(DocumentVersion.version_number)
        )).scalars().all()
    assert [v.version_number for v in versions] == [1, 2]
    old, new = versions
    assert old.id == old_version_id and old.status == "SUPERSEDED"
    assert new.status == "CURRENT" and new.etag == '"v2"' and new.source_url == url
    assert doc.current_version_id == new.id


@pytest.mark.asyncio
async def test_recheck_same_file_only_updates_headers():
    url = f"https://www.bb.org.bd/mediaroom/circulars/brpd/same-{uuid.uuid4().hex[:6]}.pdf"
    pdf = _make_pdf(f"Unchanged text {uuid.uuid4().hex}")
    doc_id, version_id = await _ingest(url, pdf, '"v1"')

    site = _FakeArchiveSite()
    site.files[url] = (pdf, '"v1-gzip"', "Mon, 09 Nov 2026 10:00:00 GMT")
    async with AsyncSessionLocal() as db:
        await source_monitoring_service.recheck_archive(db, connector=site)
    assert site.get_calls == [url]

    async with AsyncSessionLocal() as db:
        versions = (await db.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == doc_id)
        )).scalars().all()
    assert len(versions) == 1
    assert versions[0].id == version_id
    assert versions[0].etag == '"v1-gzip"' and versions[0].last_modified == "Mon, 09 Nov 2026 10:00:00 GMT"
    assert versions[0].status == "CURRENT"


@pytest.mark.asyncio
async def test_recheck_unchanged_headers_downloads_nothing():
    url = f"https://www.bb.org.bd/mediaroom/circulars/brpd/still-{uuid.uuid4().hex[:6]}.pdf"
    pdf = _make_pdf(f"Steady text {uuid.uuid4().hex}")
    await _ingest(url, pdf, '"v1"')
    site = _FakeArchiveSite()
    site.files[url] = (pdf, '"v1"', "Thu, 01 Oct 2026 10:00:00 GMT")
    async with AsyncSessionLocal() as db:
        await source_monitoring_service.recheck_archive(db, connector=site)
    assert url in site.head_calls
    assert site.get_calls == []


@pytest.mark.asyncio
async def test_recheck_never_touches_private_uploads():
    user, _token = await make_user()
    url = f"https://www.bb.org.bd/mediaroom/circulars/brpd/private-{uuid.uuid4().hex[:6]}.pdf"
    await _ingest(url, _make_pdf(f"Private text {uuid.uuid4().hex}"), '"p1"', owner_user_id=user.id)
    site = _FakeArchiveSite()
    site.files[url] = (_make_pdf("changed"), '"p2"', "Mon, 09 Nov 2026 10:00:00 GMT")
    async with AsyncSessionLocal() as db:
        await source_monitoring_service.recheck_archive(db, connector=site)
    assert url not in site.head_calls
    assert url not in site.get_calls
