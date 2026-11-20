"""Pages are sent to a person only when reading the page image really failed.

- A reading key whose project was deleted or suspended (or that is invalid) is benched; the page keeps
  waiting and no failed try is counted against it.
- A text layer that looks damaged is read from the page image instead of going straight to a person.
- backend/scripts/requeue_pages.py sends wrongly flagged pages back, never touching corrected pages or
  replacing text that an analysis may already cite.

Gemini is never called: replies are faked.
"""
import importlib.util
import json
import sqlite3
import uuid
from pathlib import Path

import httpx
import pymupdf
import pytest

from backend.app.core.config import settings
from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.extraction import vision
from backend.app.modules.extraction.page_router import REASON_DAMAGED_TEXT, TEXT_LAYER, route_page
from backend.app.modules.extraction.service import extraction_service
from backend.app.modules.extraction.vision import VisionResult, is_dead_key_reply, read_page_image
from backend.app.modules.extraction.vision_jobs import process_pending_vision_pages
from backend.app.tests.test_page_reading import _client, _ingest, _pages, bijoy_pdf

ROOT = Path(__file__).resolve().parents[3]
DELETED = json.dumps({"error": {"code": 401, "message": "The bound service account is deleted or disabled.",
                                "status": "UNAUTHENTICATED"}})
INVALID = json.dumps({"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.",
                                "status": "INVALID_ARGUMENT"}})
# What a legacy-font page's text layer looks like when the font is not recognised by name.
GARBLED = "~8. \\5W'R~~~~;qJf\\bc~C<f'~~~'ft9J,Cm\\5W'R~c<Wr9i~~ ~Q. \\5W'R~~~~~\\5W'R~~q~~ <!1~\\5W'R~~~'W'f"


@pytest.fixture(autouse=True)
def _fresh_keys():
    vision._dead_keys.clear()
    vision._exhausted_until.clear()
    yield
    vision._dead_keys.clear()
    vision._exhausted_until.clear()


# --------------------------------------------------------------------------- dead keys
def test_dead_key_replies_are_recognised():
    assert is_dead_key_reply(401, DELETED)
    assert is_dead_key_reply(400, INVALID)
    assert is_dead_key_reply(403, '{"error": {"status": "PERMISSION_DENIED"}}')
    assert is_dead_key_reply(403, "Consumer has been suspended.")
    # A bad request about the page itself, or a busy or quota reply, is not the key's fault.
    assert not is_dead_key_reply(400, '{"error": {"message": "Request contains an invalid argument."}}')
    assert not is_dead_key_reply(429, DELETED)
    assert not is_dead_key_reply(503, "")


async def test_a_dead_key_is_benched_and_the_page_is_not_blamed(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "dead-key")
    monkeypatch.setattr(settings, "GEMINI_EXTRA_API_KEYS", "good-key")
    seen = []
    async with _client([httpx.Response(401, text=DELETED)], seen) as client:
        result = await read_page_image(b"png", api_key="dead-key", client=client)
    assert len(seen) == 1  # no retries on a dead key
    assert not result.success and result.transient and result.key_dead
    assert "reading key no longer works" in result.error
    assert vision.available_gemini_keys() == ["good-key"]
    assert vision.working_gemini_keys() == ["good-key"]


async def test_read_images_json_moves_on_from_a_dead_key(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "dead-key")
    monkeypatch.setattr(settings, "GEMINI_EXTRA_API_KEYS", "good-key")
    monkeypatch.setattr(vision, "_key_turn", iter(range(0, 10 ** 6, 2)))  # start with the first key
    ok = {"candidates": [{"content": {"parts": [{"text": '{"answer": 1}'}]}}]}
    seen = []
    async with _client([httpx.Response(401, text=DELETED), httpx.Response(200, json=ok)], seen) as client:
        result = await vision.read_images_json([b"png"], "prompt", {"type": "object"}, model="m", client=client)
    assert result.success and result.data == {"answer": 1} and len(seen) == 2


async def test_vision_job_keeps_a_page_waiting_when_the_key_is_dead():
    _doc_id, version_id = await _ingest(bijoy_pdf())

    async def dead(png):
        return VisionResult(success=False, error="the reading key no longer works", transient=True, key_dead=True)

    for _ in range(settings.VISION_MAX_ATTEMPTS + 1):
        async with AsyncSessionLocal() as db:
            await process_pending_vision_pages(db, reader=dead, version_id=version_id)
    page = (await _pages(version_id))[0]
    assert page.quality_status == "PENDING_VISION" and page.vision_attempts == 0


# --------------------------------------------------------------------------- damaged text layer
def _garbled_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    for i in range(6):
        page.insert_text((40, 72 + 18 * i), GARBLED, fontname="helv", fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


def test_damaged_text_layer_is_read_from_the_page_image():
    pdf = _garbled_pdf()
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        assert route_page(doc[0]).route == TEXT_LAYER  # the font name gives nothing away
    page = extraction_service.extract_document_pages(pdf)[0]
    assert page["quality_status"] == "PENDING_VISION"
    assert page["route_reason"] == REASON_DAMAGED_TEXT
    assert page["raw_text"] == "" and page["cleaned_text"] == ""
    assert "\\5W'R" in page["native_text"]  # the text layer is kept aside for a person


def test_clean_english_page_still_uses_the_text_layer():
    from backend.app.tests.test_page_reading import english_pdf

    page = extraction_service.extract_document_pages(english_pdf())[0]
    assert page["quality_status"] == "SUCCESS_NATIVE" and page["raw_text"]


def test_a_short_clean_page_keeps_its_text():
    """A cover page or a one-line memo is short, not damaged: its text stays searchable."""
    from backend.app.tests.test_page_reading import english_pdf

    page = extraction_service.extract_document_pages(english_pdf("Banks must file the return monthly."))[0]
    assert page["extraction_method"] == "TEXT_LAYER"
    assert page["raw_text"] == "Banks must file the return monthly."
    assert page["quality_status"] in ("SUCCESS_NATIVE", "NEEDS_HUMAN_REVIEW")


# --------------------------------------------------------------------------- requeue script
def _load_script():
    spec = importlib.util.spec_from_file_location("requeue_pages", ROOT / "backend" / "scripts" / "requeue_pages.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_db(path: Path) -> dict:
    conn = sqlite3.connect(path)
    conn.executescript("""
        create table documents (id text primary key, title text);
        create table document_versions (id text primary key, document_id text);
        create table document_analyses (id text primary key, document_version_id text);
        create table document_pages (id text primary key, document_version_id text, page_number int,
            raw_text text, cleaned_text text, native_text text, extraction_method text, quality_status text,
            quality_score real, line_boxes text, vision_attempts int, vision_error text,
            is_human_corrected int, updated_at text);
    """)
    ids = {}

    def doc(name, analysed=False):
        d, v = uuid.uuid4().hex, uuid.uuid4().hex
        conn.execute("insert into documents values (?, ?)", (d, name))
        conn.execute("insert into document_versions values (?, ?)", (v, d))
        if analysed:
            conn.execute("insert into document_analyses values (?, ?)", (uuid.uuid4().hex, v))
        ids[name] = d
        return v

    def page(name, version, method, status, text="", attempts=0, error=None, corrected=0):
        conn.execute("insert into document_pages values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (name, version, 1, text, text, None, method, status, 0.3, None, attempts, error, corrected, None))

    fresh, analysed, handed = doc("fresh"), doc("analysed", analysed=True), doc("handed")
    page("key_page", analysed, "GEMINI_VISION", "NEEDS_HUMAN_REVIEW", attempts=5, error="HTTP 401: " + DELETED)
    page("damaged_fresh", fresh, "TEXT_LAYER", "NEEDS_HUMAN_REVIEW", text=GARBLED)
    page("damaged_analysed", analysed, "TEXT_LAYER", "NEEDS_HUMAN_REVIEW", text=GARBLED)
    page("damaged_handed", handed, "TEXT_LAYER", "NEEDS_HUMAN_REVIEW", text=GARBLED)
    page("really_failed", fresh, "GEMINI_VISION", "NEEDS_HUMAN_REVIEW", attempts=5,
         error="unusable answer: Gemini answer has no text lines.")
    page("corrected", fresh, "TEXT_LAYER", "NEEDS_HUMAN_REVIEW", text=GARBLED, corrected=1)
    page("short_clean", fresh, "TEXT_LAYER", "NEEDS_HUMAN_REVIEW", text="This page is intentionally left blank")
    page("good", fresh, "TEXT_LAYER", "SUCCESS_NATIVE", text="Clean text")
    conn.commit()
    conn.close()
    return ids


def _rows(path: Path) -> dict:
    with sqlite3.connect(path) as conn:
        return {r[0]: r[1:] for r in conn.execute(
            "select id, quality_status, extraction_method, raw_text, native_text, vision_attempts, vision_error "
            "from document_pages")}


def test_requeue_dry_run_changes_nothing(tmp_path, capsys):
    script = _load_script()
    db = tmp_path / "app.db"
    _make_db(db)
    before = _rows(db)
    assert script.main(["--db", str(db)]) == 0
    assert _rows(db) == before
    out = capsys.readouterr().out
    assert "stopped working: 1 " in out and "Nothing changed" in out
    assert not list(tmp_path.glob("*.before-requeue-*"))


def test_requeue_sends_back_only_the_safe_pages(tmp_path):
    script = _load_script()
    db = tmp_path / "app.db"
    ids = _make_db(db)
    repo = tmp_path / "work"
    (repo / "inbox").mkdir(parents=True)
    (repo / "inbox" / f"{uuid.UUID(ids['handed'])}.txt").write_text("handed out", encoding="utf-8")

    assert script.main(["--db", str(db), "--repo", str(repo), "--yes"]) == 0
    rows = _rows(db)
    # The key failure goes back even though its circular is analysed: the page was empty.
    assert rows["key_page"][0] == "PENDING_VISION" and rows["key_page"][4:] == (0, None)
    # A damaged page of an untouched circular is read from the image; its text layer is kept aside.
    assert rows["damaged_fresh"][:4] == ("PENDING_VISION", "GEMINI_VISION", "", GARBLED)
    # Text an analysis may cite is never replaced.
    assert rows["damaged_analysed"][0] == "NEEDS_HUMAN_REVIEW" and rows["damaged_analysed"][2] == GARBLED
    assert rows["damaged_handed"][0] == "NEEDS_HUMAN_REVIEW"
    # A real failure goes straight to the reader's stronger route; no page is left for a person.
    assert rows["really_failed"][0] == "PENDING_VISION" and rows["really_failed"][4] == settings.VISION_MAX_ATTEMPTS
    # A short clean page keeps its text and counts as read.
    assert rows["short_clean"][0] == "SUCCESS_NATIVE" and rows["short_clean"][2] == "This page is intentionally left blank"
    # Corrected pages and good pages stay as they were.
    assert rows["corrected"][0] == "NEEDS_HUMAN_REVIEW" and rows["corrected"][2] == GARBLED
    assert rows["good"][0] == "SUCCESS_NATIVE"
    assert len(list(tmp_path.glob("app.before-requeue-*.db"))) == 1

    # Running it again finds nothing more to send back.
    conn = sqlite3.connect(db)
    try:
        assert script.apply(conn, script.plan(conn, script.handed_out([repo / "inbox"]))) == 0
        # Once a circular is marked to be analysed again, its damaged pages are read too.
        redo = tmp_path / "REDO.txt"
        redo.write_text(f"{uuid.UUID(ids['handed'])} | went out with a damaged page\n"
                        f"{uuid.UUID(ids['analysed'])} | went out with a damaged page\n", encoding="utf-8")
        groups = script.plan(conn, script.handed_out([repo / "inbox"]), script.redo_keys(redo))
        # ... but never the pages of a circular already analysed in the app.
        assert [p for p, _d, _t in groups["damaged"]] == ["damaged_handed"]
    finally:
        conn.close()
