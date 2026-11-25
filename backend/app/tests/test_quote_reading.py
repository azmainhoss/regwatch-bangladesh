"""Claim checks, chunk 4 (docs/specs/CLAIM_CHECKS_SPEC.md section 7): the second reading of quoted sentences
on pages read from their image. Every call goes to a fake service (httpx.MockTransport); nothing uses the network."""
import base64
import io
import json
import uuid
from datetime import date
from types import SimpleNamespace

import httpx
import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.storage import storage_service
from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.analysis import auto
from backend.app.modules.analysis.models import AnalysisClaim
from backend.app.modules.claims import reading as R
from backend.app.modules.claims import reading_jobs as J
from backend.app.modules.claims.models import QuoteReadingCheck
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.analysis.sentences import SentenceIndex
from sqlalchemy.orm import selectinload
from backend.app.modules.extraction import vision, vision_jobs
from backend.app.tests import test_claim_checks as cc
from backend.app.tests.factories import make_user


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
async def _fresh_quota(monkeypatch):
    monkeypatch.setattr(vision, "_exhausted_until", {})
    # Checks left waiting by other tests would be read first; start every test with none waiting.
    async with AsyncSessionLocal() as db:
        for row in (await db.execute(select(QuoteReadingCheck).where(QuoteReadingCheck.status == "WAITING"))).scalars().all():
            row.status = "NOT_NEEDED"
        await db.commit()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def no_sleep(_seconds):
    return None


# ---------------------------------------------------------------------------
# A fake reading service
# ---------------------------------------------------------------------------
class FakeService:
    """Answers each call from a script. An entry is a list of crops (each a list of lines), a callable
    taking the number of images, or an HTTP status number (429 with the daily-limit wording, or any other)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []  # (model, number of images, image sizes)

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        parts = body["contents"][0]["parts"]
        images = [p for p in parts if "inlineData" in p]
        sizes = []
        for p in images:
            with Image.open(io.BytesIO(base64.b64decode(p["inlineData"]["data"]))) as img:
                sizes.append(img.size)
        model = request.url.path.split("/models/")[1].split(":")[0]
        self.calls.append((model, len(images), sizes))
        entry = self.script.pop(0) if self.script else 500
        if callable(entry):
            entry = entry(len(images))
        if isinstance(entry, int):
            if entry == 429:
                return httpx.Response(429, json={"error": {"message": "Quota exceeded for GenerateRequestsPerDayPerProjectPerModel"}})
            return httpx.Response(entry, json={"error": {"message": "x"}})
        crops = [{"index": i + 1, "lines": lines} for i, lines in enumerate(entry)]
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps({"crops": crops})}]}}]})

    def sender(self):
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

        async def send(images, model):
            return await vision.read_images_json(
                images, R.STRICT_PROMPT.format(n=len(images)), R.READING_SCHEMA, model=model,
                api_key="test-key", client=client, sleep=no_sleep,
            )

        return send


def blank_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)
    data = doc.tobytes()
    doc.close()
    return data


# ---------------------------------------------------------------------------
# Plain pieces
# ---------------------------------------------------------------------------
def test_levenshtein():
    assert R.levenshtein("kitten", "sitting") == 3
    assert R.levenshtein("", "abc") == 3 and R.levenshtein("abc", "abc") == 0
    assert R.levenshtein("কোনো শাখা", "কোনো শাখা") == 0


def test_same_reading_ignores_punctuation_spacing_and_digit_script():
    a = "সকল ব্যাংক ২০২৬ সালের মধ্যে প্রতিবেদন দাখিল করবে।"
    b = "সকল ব্যাংক  2026 সালের মধ্যে প্রতিবেদন, দাখিল করবে"
    assert R.same_reading(a, b)


def test_illegible_is_never_the_same():
    assert not R.same_reading("Banks shall report monthly.", "Banks shall [illegible] monthly.")
    assert not R.same_reading("Banks shall [illegible] monthly.", "Banks shall [illegible] monthly.")


def test_numbers_negations_and_codes_must_match():
    base = "Banks shall not open new branches within 45 days."
    assert R.same_reading(base, base)
    assert not R.same_reading(base, base.replace("45", "46"))
    assert not R.same_reading(base, base.replace("shall not", "shall"))
    assert not R.same_reading("See BRPD Circular No. 14.", "See BRPD Circular No. 41.", codes=["BRPD"])
    assert not R.same_reading("See BRPD Circular No. 14.", "See DOS Circular No. 14.", codes=["BRPD", "DOS"])
    assert R.same_reading("See BRPD Circular No. 14.", "See BRPD Circular No. 14", codes=["BRPD"])


def test_a_number_the_text_layer_confirms_counts_as_present():
    ours = "Banks shall keep a 45 day notice period."
    theirs = "Banks shall keep a 46 day notice period."
    assert not R.same_reading(ours, theirs)
    assert R.same_reading(ours, theirs, confirmed=R.confirmed_figures(ours, "Notice period 45 days"))
    # a figure the text layer does not have is still compared
    assert not R.same_reading(ours, theirs, confirmed=R.confirmed_figures(ours, "Notice period 90 days"))
    # a single digit is never confirmed by the text layer
    assert R.confirmed_figures("Banks shall wait 5 days.", "5") == []
    # the second reading cannot add figures of its own beyond the ones it replaced
    assert not R.same_reading(ours, "Banks shall keep a 46 day notice period of 7 days.", confirmed=["45"])


def test_edit_share_just_under_and_just_over_three_percent():
    a = "word" * 25  # 100 characters
    just_under = "xx" + a[2:]  # 2 edits: 2%
    at_limit = "xxx" + a[3:]  # 3 edits: 3%
    just_over = "xxxx" + a[4:]  # 4 edits: 4%
    assert R.same_reading(a, just_under)
    assert R.same_reading(a, at_limit)
    assert not R.same_reading(a, just_over)


def test_locate_sentence_in_a_whole_page_reading():
    page = "বাংলাদেশ ব্যাংক\nপ্রধান কার্যালয়, ঢাকা\nসকল তফসিলি ব্যাংক প্রতি মাসে প্রতিবেদন দাখিল করবে।\nধন্যবাদান্তে"
    found = R.locate_in_page_reading("সকল তফসিলি ব্যাংক প্রতি মাসে প্রতিবেদন দাখিল করবে।", page)
    assert found == "সকল তফসিলি ব্যাংক প্রতি মাসে প্রতিবেদন দাখিল করবে।"
    assert R.locate_in_page_reading("সম্পূর্ণ ভিন্ন একটি বাক্য যা পাতায় নেই এবং মেলে না", page) is None


def test_reply_parsing_uses_the_crop_numbers_and_tolerates_gaps():
    data = {"crops": [{"index": 2, "lines": ["b"]}, {"index": 1, "lines": ["a1", "a2"]}]}
    assert R._texts_from_reply(data, 2) == ["a1\na2", "b"]
    assert R._texts_from_reply({"crops": [{"index": 1, "lines": ["a"]}]}, 2) == ["a", None]
    assert R._texts_from_reply({"nope": 1}, 1) == [None]


# ---------------------------------------------------------------------------
# One page, rows and fake service (no database)
# ---------------------------------------------------------------------------
NEG_LINE = "কোনো নতুন শাখা খোলা যাবে না।"
NEG_DROPPED = "কোনো নতুন শাখা খোলা যাবে।"
NEG_OTHER = "কোনো নতুন শাখা খোলা হবে।"


def page_of(lines, native=None, method="GEMINI_VISION", corrected=False):
    text = "\n".join(lines)
    boxes = [{"text": ln, "box_2d": [50 + i * 40, 100, 80 + i * 40, 900]} for i, ln in enumerate(lines)]
    return SimpleNamespace(page_number=1, raw_text=text, cleaned_text=text, native_text=native, line_boxes=boxes,
                           extraction_method=method, is_human_corrected=corrected)


def row_for(page, i, **kw):
    ln = page.line_boxes[i]["text"]
    return SimpleNamespace(
        status="WAITING", our_text=ln, line_indexes=[i], reads=[], attempts=0, last_error=None, checked_at=None,
        sentence_id=f"p1.s{i + 1}", page_text_sha=R.page_text_sha(page.cleaned_text), **kw,
    )


@pytest.mark.asyncio
async def test_same_reading_is_clean_with_one_call_per_page():
    lines = ["বাংলাদেশ ব্যাংক", NEG_LINE, "সকল ব্যাংক প্রতিবেদন দাখিল করবে।"]
    page = page_of(lines)
    rows = [row_for(page, i) for i in range(3)]
    fake = FakeService([[[ln] for ln in lines]])
    out = await R.check_page(page, rows, blank_pdf(), fake.sender())
    assert [r.status for r in rows] == ["CLEAN"] * 3
    assert out["calls"] == 1 and out["clean"] == 3
    model, n_images, sizes = fake.calls[0]
    assert model == settings.QUOTE_CHECK_MODEL and n_images == 3
    # each crop is a strip of the page, not the whole page
    assert all(h < 842 * settings.QUOTE_CHECK_DPI / 72 for _w, h in sizes)
    assert rows[0].reads[0]["kind"] == "CROP" and rows[0].checked_at is not None


@pytest.mark.asyncio
async def test_lines_next_to_ours_in_the_strip_do_not_count_against_us():
    ours = "সকল তফসিলি ব্যাংক প্রতি মাসে প্রতিবেদন দাখিল করবে।"
    above, below = "পূর্ববর্তী অনুচ্ছেদের শেষ লাইন এখানে আছে", "পরবর্তী অনুচ্ছেদের প্রথম লাইন এখানে আছে এবং আরও কিছু"
    page = page_of([ours])
    row = row_for(page, 0)
    fake = FakeService([[[above, ours, below]]])
    out = await R.check_page(page, [row], blank_pdf(), fake.sender())
    assert row.status == "CLEAN" and out["calls"] == 1
    assert row.reads[0]["text"] == ours and len(row.reads[0]["full"].split(chr(10))) == 3

    # a strip that holds only other lines (the line box was off) is a crop miss, not a misreading:
    # the whole page is read instead, and our lines found there decide
    page = page_of([ours])
    row = row_for(page, 0)
    fake = FakeService([[[above, below]], [[above, ours, below]]])
    out = await R.check_page(page, [row], blank_pdf(), fake.sender())
    assert row.status == "CLEAN" and out["calls"] == 2
    assert [x["kind"] for x in row.reads] == ["CROP_MISS", "PAGE"]

    # when the page reading does not hold our lines either, the point stays unclear (never "misread")
    page = page_of([ours])
    row = row_for(page, 0)
    fake = FakeService([[[above, below]], [[above, below]]])
    await R.check_page(page, [row], blank_pdf(), fake.sender())
    assert row.status == "UNCLEAR"


def test_bangla_spelling_variants_match_but_a_missing_word_does_not():
    # hasant / conjunct and danda differences between two correct readings of the same print
    assert R.same_reading("অন্য কোনো ইন্সট্রুমেন্টের মাধ্যমে প্রদান করা হলো।", "অন্য কোনো ইনস্ট্রুমেন্টের মাধ্যমে প্রদান করা হলো.")
    assert R.same_reading("সরকারি ব্যাংকসমূহকে জানানো হলো।", "সরকারী ব্যাংকসমূহকে জানানো হলো।")
    # a whole word on one side only changes the meaning ("new applications")
    assert not R.same_reading("এ সার্কুলারের আওতায় আবেদন গ্রহণের তারিখ হতে", "এ সার্কুলারের আওতায় নতুন আবেদন গ্রহণের তারিখ হতে")
    # numbers stay exact
    assert not R.same_reading("প্রজ্ঞাপন নং ১৭৭", "প্রজ্ঞাপন নং ৭১৭")


@pytest.mark.asyncio
async def test_a_number_that_differs_is_clean_when_the_text_layer_confirms_ours():
    ours = "Banks shall keep a 45 day notice period."
    page = page_of([ours], native="Notice period 45 days")
    row = row_for(page, 0)
    fake = FakeService([[["Banks shall keep a 46 day notice period."]]])
    out = await R.check_page(page, [row], blank_pdf(), fake.sender())
    assert row.status == "CLEAN" and out["calls"] == 1 and row.numbers_confirmed == ["45"]

    # without the text layer the same difference goes to the tie-break; the third reading agrees with ours
    page = page_of([ours], native=None)
    row = row_for(page, 0)
    fake = FakeService([[["Banks shall keep a 46 day notice period."]], [[ours]]])
    out = await R.check_page(page, [row], blank_pdf(), fake.sender())
    assert row.status == "CLEAN" and out["calls"] == 2
    assert [c[0] for c in fake.calls] == [settings.QUOTE_CHECK_MODEL, settings.QUOTE_TIEBREAK_MODEL]


@pytest.mark.asyncio
async def test_dropped_na_goes_to_the_tie_break_and_the_third_reading_decides():
    for third, expected in ((NEG_LINE, "CLEAN"), (NEG_DROPPED, "MISREAD"), (NEG_OTHER, "UNCLEAR")):
        page = page_of([NEG_LINE])
        row = row_for(page, 0)
        fake = FakeService([[[NEG_DROPPED]], [[third]]])
        out = await R.check_page(page, [row], blank_pdf(), fake.sender())
        assert row.status == expected, third
        assert out["calls"] == 2
        first, second = fake.calls
        assert first[0] == settings.QUOTE_CHECK_MODEL and second[0] == settings.QUOTE_TIEBREAK_MODEL
        # the sharper reading is a tighter, sharper crop: no padding and a higher resolution
        assert second[2][0][0] > first[2][0][0]
        assert [r["kind"] for r in row.reads] == ["CROP", "SHARP_CROP"]
        if expected == "MISREAD":
            assert row.reads[-1]["text"] == NEG_DROPPED  # the sharper reading is the one kept and shown


@pytest.mark.asyncio
async def test_busy_and_quota_replies_leave_the_row_waiting_and_count_no_attempt():
    page = page_of([NEG_LINE])
    row = row_for(page, 0)
    # busy: 503 on every try
    fake = FakeService([503] * 10)
    out = await R.check_page(page, [row], blank_pdf(), fake.sender())
    assert row.status == "WAITING" and row.attempts == 0 and out["waiting_busy"] == 1 and out["stop"]
    # the daily limit
    fake = FakeService([429])
    out = await R.check_page(page, [row], blank_pdf(), fake.sender())
    assert row.status == "WAITING" and row.attempts == 0 and out["out_of_quota"]


@pytest.mark.asyncio
async def test_three_real_failures_make_the_sentence_unclear():
    page = page_of([NEG_LINE])
    row = row_for(page, 0)
    for expected_attempts in (1, 2):
        out = await R.check_page(page, [row], blank_pdf(), FakeService([400]).sender())
        assert row.status == "WAITING" and row.attempts == expected_attempts and out["failed"] == 1
    await R.check_page(page, [row], blank_pdf(), FakeService([400]).sender())
    assert row.attempts == 3 and row.status == "UNCLEAR" and row.last_error


@pytest.mark.asyncio
async def test_text_layer_and_human_corrected_pages_need_no_reading_and_no_call():
    for page in (page_of([NEG_LINE], method="TEXT_LAYER"), page_of([NEG_LINE], corrected=True)):
        row = row_for(page, 0)
        fake = FakeService([])
        out = await R.check_page(page, [row], blank_pdf(), fake.sender())
        assert row.status == "NOT_NEEDED" and fake.calls == [] and out["not_needed"] == 1


@pytest.mark.asyncio
async def test_a_page_whose_text_changed_leaves_its_old_rows_alone():
    page = page_of([NEG_LINE])
    row = row_for(page, 0)
    page.cleaned_text = page.raw_text = NEG_LINE + " (corrected wording)"
    fake = FakeService([])
    await R.check_page(page, [row], blank_pdf(), fake.sender())
    assert row.status == "NOT_NEEDED" and fake.calls == []


@pytest.mark.asyncio
async def test_up_to_twelve_crops_share_one_call():
    lines = [f"Line number {i} of the page ends here." for i in range(13)]
    page = page_of(lines)
    rows = [row_for(page, i) for i in range(12)]
    fake = FakeService([lambda n: [[lines[i]] for i in range(n)]])
    out = await R.check_page(page, rows, blank_pdf(), fake.sender())
    assert out["calls"] == 1 and fake.calls[0][1] == 12 and {r.status for r in rows} == {"CLEAN"}

    rows = [row_for(page, i) for i in range(13)]
    fake = FakeService([lambda n: [[lines[i]] for i in range(n)], lambda n: [[lines[12]]]])
    out = await R.check_page(page, rows, blank_pdf(), fake.sender())
    assert [c[1] for c in fake.calls] == [12, 1] and out["calls"] == 2


@pytest.mark.asyncio
async def test_without_line_boxes_the_whole_page_is_read_and_the_sentence_is_found():
    lines = ["বাংলাদেশ ব্যাংক", NEG_LINE, "সকল ব্যাংক প্রতিবেদন দাখিল করবে।"]
    page = page_of(lines)
    page.line_boxes = None
    row = SimpleNamespace(status="WAITING", our_text=NEG_LINE, line_indexes=[1], reads=[], attempts=0, last_error=None,
                          checked_at=None, sentence_id="p1.s2", page_text_sha=R.page_text_sha(page.cleaned_text))
    fake = FakeService([[lines]])
    out = await R.check_page(page, [row], blank_pdf(), fake.sender())
    assert row.status == "CLEAN" and out["calls"] == 1 and row.reads[0]["kind"] == "PAGE"
    assert fake.calls[0][1] == 1  # the whole page: one image

    # a sentence that cannot be found in the reading is unclear
    fake = FakeService([[["মোটেই অন্য একটি লেখা যা মেলে না", "আরেকটি অসম্পর্কিত লাইন এখানে"]]])
    row.status, row.reads = "WAITING", []
    await R.check_page(page, [row], blank_pdf(), fake.sender())
    assert row.status == "UNCLEAR"


# ---------------------------------------------------------------------------
# The service call: key rotation and quota
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_key_out_of_quota_for_the_second_reading_does_not_stop_page_reading(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "key-a")
    monkeypatch.setattr(settings, "GEMINI_EXTRA_API_KEYS", "key-b")
    seen = []

    def handler(request):
        seen.append(request.headers["x-goog-api-key"])
        if request.headers["x-goog-api-key"] == "key-a":
            return httpx.Response(429, json={"error": {"message": "GenerateRequestsPerDayPerProjectPerModel"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"crops": [{"index": 1, "lines": ["x"]}]}'}]}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        # rotation starts wherever the counter is, so run until key-a has been tried
        for _ in range(2):
            res = await vision.read_images_json([b"png"], "p", R.READING_SCHEMA, model=settings.QUOTE_CHECK_MODEL, client=client, sleep=no_sleep)
            assert res.success and res.data["crops"][0]["lines"] == ["x"]
    assert "key-a" in seen and seen[-1] == "key-b"
    assert vision.available_gemini_keys(settings.QUOTE_CHECK_MODEL) == ["key-b"]
    assert vision.available_gemini_keys() == ["key-a", "key-b"]  # page reading has its own quota

    # every key used up: no request is made at all
    vision.mark_key_exhausted("key-b", settings.QUOTE_CHECK_MODEL)
    res = await vision.read_images_json([b"png"], "p", R.READING_SCHEMA, model=settings.QUOTE_CHECK_MODEL)
    assert res.quota_exhausted and res.transient and res.not_sent


# ---------------------------------------------------------------------------
# The job, claims and the document status (database)
# ---------------------------------------------------------------------------
LINES = [
    "All scheduled banks.",
    "Banks shall submit the monthly liquidity report by 31 December 2026.",
    "Banks shall not open new branches without approval.",
    "This amends BRPD Circular No. 14 dated 23 September 2012.",
    "This comes into force with immediate effect, except for state-owned banks.",
]


async def image_circular(monkeypatch, **kw):
    text = "\n".join(LINES)
    doc, version, pages = await cc.doc_with_text("PUBLISHED_MACHINE_PROCESSED", text)
    boxes = [{"text": ln, "box_2d": [80 + i * 60, 100, 120 + i * 60, 900]} for i, ln in enumerate(LINES)]
    async with AsyncSessionLocal() as db:
        page = await db.get(DocumentPage, pages[0].id)
        page.extraction_method = "GEMINI_VISION"
        page.quality_status = "SUCCESS_VISION"
        page.line_boxes = boxes
        await db.commit()
    payload = cc.payload_for(cc.make_ctx(text), deadline_c="2026-12-31")
    analysis = await cc.run_analysis(doc.id, payload, monkeypatch)
    monkeypatch.setattr(storage_service, "get_file_bytes", lambda path: blank_pdf())
    return doc, version, pages, analysis


async def claims_of(analysis_id):
    return await cc.load_claims(analysis_id)


async def doc_status(doc_id):
    async with AsyncSessionLocal() as db:
        return (await db.get(Document, doc_id)).publication_status


async def waiting_rows(page_id):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(QuoteReadingCheck).where(QuoteReadingCheck.page_id == page_id)
                                 .order_by(QuoteReadingCheck.sentence_id))).scalars().all()


def counts_of(claims):
    from backend.app.modules.claims import status as S
    return S.counts([c for c in claims if c.kind != "PROVISION"])


@pytest.mark.asyncio
async def test_a_clean_second_reading_releases_the_points_and_recomputes_the_status(monkeypatch):
    doc, _v, pages, analysis = await image_circular(monkeypatch)
    before = await claims_of(analysis.id)
    assert counts_of(before)["checking"] > 0 and counts_of(before)["shown"] == 0
    assert await doc_status(doc.id) == "PUBLISHED_MACHINE_PROCESSED"  # AI draft until a point passes
    rows = await waiting_rows(pages[0].id)
    assert {r.status for r in rows} == {"WAITING"} and len(rows) == 5

    fake = FakeService([[[ln] for ln in LINES]])
    async with AsyncSessionLocal() as db:
        summary = await J.process_pending_quote_checks(db, limit=10, send=fake.sender())
    assert summary["calls"] == 1 and summary["clean"] == 5 and summary["claims_rerouted"] > 0
    assert {r.status for r in await waiting_rows(pages[0].id)} == {"CLEAN"}

    after = await claims_of(analysis.id)
    c = counts_of(after)
    assert c["checking"] == 0 and c["shown"] > 0 and c["total"] == counts_of(before)["total"]
    # every point passed: nothing is held for a person
    assert all(c.check_status in ("PASSED", "NOT_SHOWN", "WAITING_FOR_PERSON") for c in after if c.kind != "PROVISION")
    assert not any(c.review_queue == "REQUIRED" for c in after)
    assert await doc_status(doc.id) == "PUBLISHED_MACHINE_VERIFIED"
    # the job has nothing left to do
    async with AsyncSessionLocal() as db:
        again = await J.process_pending_quote_checks(db, limit=10, send=FakeService([]).sender())
    assert again["calls"] == 0 and again["pages"] == 0


@pytest.mark.asyncio
async def test_a_misread_sentence_hides_its_point_and_shows_the_second_reading_to_the_reviewer(client, monkeypatch):
    doc, _v, pages, analysis = await image_circular(monkeypatch)
    assert await doc_status(doc.id) == "PUBLISHED_MACHINE_VERIFIED"
    dropped = LINES[2].replace("shall not", "shall")
    first = [[ln] for ln in LINES]
    first[2] = [dropped]
    fake = FakeService([first, [[dropped]]])
    async with AsyncSessionLocal() as db:
        summary = await J.process_pending_quote_checks(db, limit=10, send=fake.sender())
    assert summary["misread"] == 1 and summary["clean"] == 4 and summary["calls"] == 2

    claims = await claims_of(analysis.id)
    bad = [c for c in claims if "p1.s3" in (c.evidence or {}).get("quote", [])]
    assert bad and all(c.check_status in ("WAITING_FOR_PERSON", "NOT_SHOWN") for c in bad)
    assert any(ch["name"] == "QUOTE_READING" and ch["result"] == "FAIL" for c in bad for ch in c.checks)
    # a high-stakes point that failed goes to a person, and the circular's status follows
    assert any(c.review_queue == "REQUIRED" for c in bad)
    assert await doc_status(doc.id) == "AWAITING_REVIEW"

    _a, admin_token = await make_user(is_superuser=True)
    rows = (await client.get("/api/v1/claims/review?queue=REQUIRED&limit=50", headers=auth(admin_token))).json()["items"]
    mine = [r for r in rows if r["circular"]["id"] == str(doc.id) and r["second_reading"]]
    assert mine and mine[0]["second_reading"] == dropped
    # the stored readings keep the model's name on the server only
    assert "model" not in json.dumps(mine[0])


@pytest.mark.asyncio
async def test_points_a_person_decided_are_never_checked_again(monkeypatch):
    doc, _v, pages, analysis = await image_circular(monkeypatch)
    claims = await claims_of(analysis.id)
    target = next(c for c in claims if c.check_status == "CHECKING")
    async with AsyncSessionLocal() as db:
        row = await db.get(AnalysisClaim, target.id)
        row.check_status = "APPROVED"
        row.checks = [{"name": "QUOTE_READING", "result": "WAIT", "message": "Waiting for the second reading of page 1."}]
        await db.commit()
    dropped = [[ln.replace("shall not", "shall").replace("31 December", "30 December")] for ln in LINES]
    fake = FakeService([dropped, dropped])
    async with AsyncSessionLocal() as db:
        await J.process_pending_quote_checks(db, limit=10, send=fake.sender())
    async with AsyncSessionLocal() as db:
        row = await db.get(AnalysisClaim, target.id)
    assert row.check_status == "APPROVED"
    assert row.checks == [{"name": "QUOTE_READING", "result": "WAIT", "message": "Waiting for the second reading of page 1."}]


@pytest.mark.asyncio
async def test_newest_circular_is_read_first(monkeypatch):
    old_doc, _v1, old_pages, _a1 = await image_circular(monkeypatch)
    new_doc, _v2, new_pages, _a2 = await image_circular(monkeypatch)
    async with AsyncSessionLocal() as db:
        (await db.get(Document, old_doc.id)).publication_date = date(2024, 3, 1)
        (await db.get(Document, new_doc.id)).publication_date = date(2026, 11, 1)
        await db.commit()
        first = await J.pending_page_ids(db, 1)
        both = await J.pending_page_ids(db, 5)
    assert first == [new_pages[0].id]
    assert both[:2] == [new_pages[0].id, old_pages[0].id]


@pytest.mark.asyncio
async def test_a_busy_service_changes_nothing_and_a_quota_reply_stops_the_job(monkeypatch):
    doc, _v, pages, analysis = await image_circular(monkeypatch)
    async with AsyncSessionLocal() as db:
        summary = await J.process_pending_quote_checks(db, limit=10, send=FakeService([503] * 10).sender())
    assert summary["waiting_busy"] == 1 and summary["checked"] == 0
    async with AsyncSessionLocal() as db:
        summary = await J.process_pending_quote_checks(db, limit=10, send=FakeService([429]).sender())
    assert summary["out_of_quota"] is True
    rows = await waiting_rows(pages[0].id)
    assert {r.status for r in rows} == {"WAITING"} and {r.attempts for r in rows} == {0}
    assert counts_of(await claims_of(analysis.id))["shown"] == 0


@pytest.mark.asyncio
async def test_without_a_key_nothing_is_sent(monkeypatch):
    await image_circular(monkeypatch)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "GEMINI_EXTRA_API_KEYS", None)
    async with AsyncSessionLocal() as db:
        summary = await J.process_pending_quote_checks(db, limit=10)
    assert summary["waiting_no_key"] >= 1 and summary["calls"] == 0


@pytest.mark.asyncio
async def test_the_circular_says_how_long_checking_will_take_and_when_it_is_paused(monkeypatch):
    doc, _v, pages, _analysis = await image_circular(monkeypatch)
    monkeypatch.setattr(vision_jobs, "page_reader_running", lambda: False)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "k1")
    monkeypatch.setattr(settings, "GEMINI_EXTRA_API_KEYS", None)
    monkeypatch.setattr(settings, "VISION_WORKER_ENABLED", True)
    async with AsyncSessionLocal() as db:
        status = await auto.reading_status(db, await db.get(Document, doc.id))
    assert status["pages_waiting"] == 0 and status["quote_checks_waiting"] == 1
    assert status["minutes_left"] >= 1 and status["state"] == "READING"

    # page reading has quota but the second reading's model does not: paused, with the reset time
    vision.mark_key_exhausted("k1", settings.QUOTE_CHECK_MODEL)
    async with AsyncSessionLocal() as db:
        status = await auto.reading_status(db, await db.get(Document, doc.id))
    assert status["state"] == "PAUSED_DAILY_LIMIT" and status["resumes_at"]

    # the checked view of the circular carries the same promise
    from backend.app.modules.claims import view
    async with AsyncSessionLocal() as db:
        body = await view.build_view(db, await db.get(Document, doc.id), None)
    assert body["counts"]["checking"] > 0 and body["checking"]["paused_until"]


@pytest.mark.asyncio
async def test_the_paused_state_follows_the_page_readers_own_notes(monkeypatch, tmp_path):
    doc, _v, pages, _analysis = await image_circular(monkeypatch)
    lock = tmp_path / "page_reader.lock"
    lock.write_text(json.dumps({"pid": 1, "state": "reading", "quote_quota_back_at": "2026-11-14T08:05:00+00:00"}))
    monkeypatch.setattr(vision_jobs, "PAGE_READER_LOCK", lock)
    monkeypatch.setattr(vision_jobs, "page_reader_running", lambda: True)
    async with AsyncSessionLocal() as db:
        status = await auto.reading_status(db, await db.get(Document, doc.id))
    assert status["state"] == "PAUSED_DAILY_LIMIT" and status["resumes_at"] == "2026-11-14T08:05:00+00:00"


# ---------------------------------------------------------------------------
# A page correction
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_page_correction_checks_the_points_again(client, monkeypatch):
    doc, version, pages, analysis = await image_circular(monkeypatch)
    _a, admin_token = await make_user(is_superuser=True)
    before = await claims_of(analysis.id)
    on_s2 = [c for c in before if (c.evidence or {}).get("quote") == ["p1.s2"] and c.kind in ("OBLIGATION", "DATE")]
    on_s3 = [c for c in before if (c.evidence or {}).get("quote") == ["p1.s3"]]
    assert on_s2 and on_s3 and counts_of(before)["checking"] > 0

    # a person fixes the wording of the "monthly report" line and drops the "new branches" line
    lines = list(LINES)
    lines[1] = "Banks shall submit the monthly liquidity report by 31 December 2026 (fixed)."
    corrected = "\n".join(lines[:2] + lines[3:])
    res = await client.post(
        f"/api/v1/documents/{doc.id}/versions/{version.id}/pages/1/correct",
        json={"corrected_text": corrected, "correction_notes": "Checked against the page image."},
        headers=auth(admin_token),
    )
    assert res.status_code == 200

    after = {c.id: c for c in await claims_of(analysis.id)}
    # found again (the sentence now reads a little differently, so the old words are still inside it)
    assert all(after[c.id].check_status != "CHECKING" for c in on_s2)
    # gone
    for c in on_s3:
        got = after[c.id]
        assert got.check_status == "NOT_SHOWN"
        assert got.checks[0]["message"] == "The quoted words are no longer on page 1 after its reading was corrected."
    # the corrected page counts as read by a person: nothing waits for a second reading
    assert {r.status for r in await waiting_rows(pages[0].id)} == {"NOT_NEEDED"}
    assert counts_of(list(after.values()))["checking"] == 0
    # the new quote words come from the corrected page
    kept = after[on_s2[0].id]
    assert kept.evidence["quote"] and kept.evidence["quote"] != ["p1.s3"]


@pytest.mark.asyncio
async def test_a_page_correction_leaves_decided_points_alone(client, monkeypatch):
    doc, version, pages, analysis = await image_circular(monkeypatch)
    _a, admin_token = await make_user(is_superuser=True)
    claims = await claims_of(analysis.id)
    target = next(c for c in claims if (c.evidence or {}).get("quote") == ["p1.s3"])
    async with AsyncSessionLocal() as db:
        row = await db.get(AnalysisClaim, target.id)
        row.check_status = "REJECTED"
        await db.commit()
    corrected = "\n".join(LINES[:2] + LINES[3:])
    res = await client.post(
        f"/api/v1/documents/{doc.id}/versions/{version.id}/pages/1/correct",
        json={"corrected_text": corrected, "correction_notes": "x y z"},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    async with AsyncSessionLocal() as db:
        assert (await db.get(AnalysisClaim, target.id)).check_status == "REJECTED"


# ---------------------------------------------------------------------------
# No reading inside a web request
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_reading_call_is_made_inside_a_web_request(client, monkeypatch):
    doc, version, pages, analysis = await image_circular(monkeypatch)
    _a, admin_token = await make_user(is_superuser=True)
    _u, user_token = await make_user()

    async def boom(*args, **kwargs):
        raise AssertionError("a reading call was made inside a web request")

    monkeypatch.setattr(R, "send_images", boom)
    monkeypatch.setattr(vision, "read_images_json", boom)
    monkeypatch.setattr(vision, "read_page_image", boom)
    monkeypatch.setattr(vision, "_generate", boom)
    monkeypatch.setattr(J, "process_pending_quote_checks", boom)

    claims = await claims_of(analysis.id)
    some = next(c for c in claims if c.check_status in ("NOT_SHOWN", "WAITING_FOR_PERSON", "CHECKING"))
    for url in (f"/api/v1/documents/{doc.id}/claims", f"/api/v1/documents/{doc.id}/claims?all=1",
                "/api/v1/claims/review?queue=REQUIRED", "/api/v1/claims/review/counts",
                f"/api/v1/documents/{doc.id}/reading-status"):
        res = await client.get(url, headers=auth(admin_token))
        assert res.status_code == 200, url
    res = await client.post(f"/api/v1/claims/{some.id}/approve", json={}, headers=auth(admin_token))
    assert res.status_code in (200, 409)
    res = await client.post(f"/api/v1/claims/{some.id}/reject", json={"reason": "OTHER", "note": "n"}, headers=auth(admin_token))
    assert res.status_code in (200, 409)
    res = await client.post(
        f"/api/v1/documents/{doc.id}/versions/{version.id}/pages/1/correct",
        json={"corrected_text": "\n".join(LINES), "correction_notes": "same words"}, headers=auth(admin_token),
    )
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Self-correction: both readers agree, ours differs only in a figure
# ---------------------------------------------------------------------------
def test_figure_fixes_only_for_safe_figure_differences():
    # a legacy-font text layer reversed the digits; both readers agree on 717
    assert R.figure_fixes("প্রজ্ঞাপন নং-বিআরপিডি-২(আর-১)১৭৭/২০২৬-৩০৫৮ এর অনুলিপি", "প্রজ্ঞাপন নং-বিআরপিডি-২(আর-১)৭১৭/২০২৬-৩০৫৮ এর অনুলিপি") == [["177", "717"]]
    # single digits (even written "০৩") are never changed
    assert R.figure_fixes("পরবর্তী ০৩ (তিন) মাসের মধ্যে", "পরবর্তী ০৫ (তিন) মাসের মধ্যে") is None
    # a figure the PDF's text layer confirms is ours, not theirs
    assert R.figure_fixes("Circular No. 14 dated 2012", "Circular No. 41 dated 2012", confirmed=["14"]) is None
    # words differ too: not a figure-only difference
    assert R.figure_fixes("২৫ কোটি টাকা ঋণ", "২৫ কোটি টাকা নতুন ঋণ") is None
    assert R.figure_fixes("Circular No. 14 applies", "Circular No. 41 no longer applies") is None
    # the same old figure kept elsewhere would be rewritten too: refused
    assert R.figure_fixes("ধারা ১৭৭ এবং ১৭৭ উপধারা", "ধারা ৭১৭ এবং ১৭৭ উপধারা") is None
    # the count of figures must match
    assert R.figure_fixes("No. 14 of 2012", "No. 14") is None


def test_apply_figure_fixes_changes_whole_figures_in_both_scripts():
    out = R.apply_figure_fixes("notification no. 177 (১৭৭); 1177 and ১১৭৭ stay", [["177", "717"]])
    assert out == "notification no. 717 (৭১৭); 1177 and ১১৭৭ stay"


@pytest.mark.asyncio
async def test_two_agreeing_readings_correct_our_figure_and_the_point_is_shown_with_it(monkeypatch):
    doc, _v, pages, analysis = await image_circular(monkeypatch)
    async with AsyncSessionLocal() as db:
        page = await db.get(DocumentPage, pages[0].id)
        page.native_text = None  # an image-read page: no text layer to confirm our figures
        await db.commit()
    theirs = LINES[3].replace("No. 14", "No. 41")
    first = [[ln] for ln in LINES]
    first[3] = [theirs]
    fake = FakeService([first, [[theirs]]])
    async with AsyncSessionLocal() as db:
        summary = await J.process_pending_quote_checks(db, limit=10, send=fake.sender())
    assert summary["corrected"] == 1 and summary["misread"] == 0 and summary["clean"] == 4

    row = [r for r in await waiting_rows(pages[0].id) if r.sentence_id == "p1.s4"][0]
    assert row.status == "CORRECTED" and R.fixes_of(row) == [["14", "41"]]

    claims = await claims_of(analysis.id)
    cited = [c for c in claims if "p1.s4" in [i for ids in (c.evidence or {}).values() for i in (ids or [])]]
    assert cited
    for c in cited:
        reading = [ch for ch in c.checks if ch["name"] == "QUOTE_READING"]
        assert reading and reading[0]["result"] == "PASS"
        assert "14" not in json.dumps(c.fields) or "41" in json.dumps(c.fields)
    changed = [c for c in cited if c.original_fields is not None]
    assert changed, [(c.kind, c.fields) for c in cited]
    for c in changed:
        assert "41" in json.dumps(c.fields, ensure_ascii=False)
        assert (c.review_note or "").startswith("Figures corrected from two agreeing page readings")
    # the quote readers see carries the corrected figure
    async with AsyncSessionLocal() as db:
        from backend.app.modules.analysis.models import ClaimCitation
        quotes = (await db.execute(select(ClaimCitation.quoted_text).where(ClaimCitation.claim_id.in_([c.id for c in cited])))).scalars().all()
    assert quotes and all("No. 14 " not in q for q in quotes) and any("No. 41" in q for q in quotes)


@pytest.mark.asyncio
async def test_agreeing_readings_with_a_word_difference_stay_misread(monkeypatch):
    doc, _v, pages, analysis = await image_circular(monkeypatch)
    dropped = LINES[2].replace("shall not", "shall")
    first = [[ln] for ln in LINES]
    first[2] = [dropped]
    fake = FakeService([first, [[dropped]]])
    async with AsyncSessionLocal() as db:
        summary = await J.process_pending_quote_checks(db, limit=10, send=fake.sender())
    assert summary["misread"] == 1 and summary["corrected"] == 0


# ---------------------------------------------------------------------------
# A proven correction spreads to the same reference elsewhere in the circular
# ---------------------------------------------------------------------------
SPREAD_LINES = [
    "All scheduled banks under section 177 of the Act.",
    "Banks shall submit the monthly liquidity report by 31 December 2026.",
    "Banks shall not open new branches without approval.",
    "This amends notification BRPD(R-1)(Law Review)177/2026-4454 of the Bank.",
    "This comes into force with immediate effect under BRPD(R-1)(Law Review)177/2026-4454, except for state-owned banks.",
]


async def spread_circular(monkeypatch):
    text = "\n".join(SPREAD_LINES)
    doc, version, pages = await cc.doc_with_text("PUBLISHED_MACHINE_PROCESSED", text)
    boxes = [{"text": ln, "box_2d": [80 + i * 60, 100, 120 + i * 60, 900]} for i, ln in enumerate(SPREAD_LINES)]
    async with AsyncSessionLocal() as db:
        page = await db.get(DocumentPage, pages[0].id)
        page.extraction_method, page.quality_status, page.line_boxes, page.native_text = "GEMINI_VISION", "SUCCESS_VISION", boxes, None
        await db.commit()
    payload = cc.payload_for(cc.make_ctx(text), deadline_c="2026-12-31")
    analysis = await cc.run_analysis(doc.id, payload, monkeypatch)
    monkeypatch.setattr(storage_service, "get_file_bytes", lambda path: blank_pdf())
    return doc, pages, analysis


def test_contexts_tell_the_same_reference_from_a_plain_number():
    from backend.app.modules.claims.autofix import contexts
    a = contexts("প্রজ্ঞাপন নং-বিআরপিডি-২(আর-১)(ল’রিভিউ)১৭৭/ ২০২৬-৪৪৫৪ এর অনুলিপি", "177")
    b = contexts("প্রজ্ঞাপন নং-বিআরপিডি-২(আর-১)(ল'রিভিউ)১৭৭/২০২৬-৪৪৫ তারিখঃ", "177")
    assert a == b and len(a[0][0]) >= 6  # different apostrophe and spacing: still the same reference
    assert contexts("ধারা ১৭৭ অনুযায়ী", "177") != a


@pytest.mark.asyncio
async def test_a_proven_correction_spreads_to_the_same_reference_but_not_to_a_plain_number(monkeypatch):
    from backend.app.modules.claims.autofix import load_fixes

    doc, pages, analysis = await spread_circular(monkeypatch)
    proven = SPREAD_LINES[3].replace("177/", "717/")
    other = SPREAD_LINES[4].replace("177/", "717/").replace("immediate", "later")  # disagrees in a word too
    first = [[ln] for ln in SPREAD_LINES]
    first[3], first[4] = [proven], [other]
    tie = [[proven], [SPREAD_LINES[4].replace("immediate", "full")]]  # s5: the two readings disagree (unclear)
    async with AsyncSessionLocal() as db:
        summary = await J.process_pending_quote_checks(db, limit=10, send=FakeService([first, tie]).sender())
    assert summary["corrected"] == 1

    rows = {r.sentence_id: r for r in await waiting_rows(pages[0].id)}
    assert rows["p1.s4"].status == "CORRECTED" and rows["p1.s5"].status in ("MISREAD", "UNCLEAR")
    assert rows["p1.s1"].status == "CLEAN"
    async with AsyncSessionLocal() as db:
        from backend.app.modules.analysis.service import pages_payload_for
        version = (await db.execute(select(DocumentVersion).options(selectinload(DocumentVersion.pages)).where(DocumentVersion.id == pages[0].document_version_id))).scalars().first()
        index = SentenceIndex.build(pages_payload_for(version))
        fixes = await load_fixes(db, version.pages, {}, index)
    assert fixes.get("p1.s4") == [["177", "717"]]
    assert fixes.get("p1.s5") == [["177", "717"]]  # same reference: spread
    assert "p1.s1" not in fixes  # "section 177" is a different figure (and its reading was clean): never changed

    # the point quoting the spread sentence carries the corrected figure, and stays honest about its check
    claims = await claims_of(analysis.id)
    on_s2 = [c for c in claims if "p1.s5" in [i for ids in (c.evidence or {}).values() for i in (ids or [])]]
    async with AsyncSessionLocal() as db:
        from backend.app.modules.analysis.models import ClaimCitation
        quotes = (await db.execute(select(ClaimCitation.quoted_text).where(ClaimCitation.claim_id.in_([c.id for c in on_s2])))).scalars().all()
    assert on_s2 and quotes and all("177/2026" not in q for q in quotes if "Law Review" in q)
