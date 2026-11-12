"""Page images for the source-page viewer, and word-exact quote boxes on English text-layer pages."""
import io
import uuid

import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import select

from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.analysis.sentences import SentenceIndex
from backend.app.modules.analysis.service import AnalysisService
from backend.app.modules.documents import page_images
from backend.app.modules.documents.models import DocumentPage, DocumentVersion
from backend.app.modules.extraction.page_router import has_word_boxes, route_page, text_layer_lines_by_page
from backend.app.tests.factories import make_institution, make_user


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _two_sentence_pdf() -> bytes:
    """One page whose second printed line holds the end of one sentence and the start of the next."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "All scheduled banks must classify their loans", fontsize=11)
    page.insert_text((72, 116), "into three stages. Stage two loans need a", fontsize=11)
    page.insert_text((72, 132), "provision of five percent from January 2026.", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _page_lines(pdf: bytes):
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        route = route_page(doc[0])
        return route.text, route.line_boxes


async def _upload(client, token, inst_id, pdf: bytes, visibility=None):
    data = {
        "institution_id": str(inst_id),
        "title": f"Page image circular {uuid.uuid4().hex[:8]}",
        "publication_date": "2026-03-01",
        "reference_number": f"IMG-{uuid.uuid4().hex[:6]}",
    }
    if visibility:
        data["visibility"] = visibility
    resp = await client.post(
        "/api/v1/documents/upload", data=data,
        files={"file": ("c.pdf", pdf, "application/pdf")}, headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["document"]


# ---------------------------------------------------------------------------
# Word boxes on English text-layer pages
# ---------------------------------------------------------------------------
def test_text_layer_lines_carry_word_boxes():
    _text, lines = _page_lines(_two_sentence_pdf())
    assert [l["text"] for l in lines][1] == "into three stages. Stage two loans need a"
    words = lines[1]["words"]
    assert [w["text"] for w in words] == ["into", "three", "stages.", "Stage", "two", "loans", "need", "a"]
    for w in words:
        ymin, xmin, ymax, xmax = w["box_2d"]
        assert 0 <= ymin < ymax <= 1000 and 0 <= xmin < xmax <= 1000
        # Every word sits inside its line's box.
        lb = lines[1]["box_2d"]
        assert lb[1] <= xmin and xmax <= lb[3]
    # Words run left to right.
    assert [w["box_2d"][1] for w in words] == sorted(w["box_2d"][1] for w in words)


def test_sentence_boxes_stop_at_the_words_the_sentence_covers():
    text, lines = _page_lines(_two_sentence_pdf())
    index = SentenceIndex.build([{"page_number": 1, "cleaned_text": text.strip(), "line_boxes": lines}])
    s1, s2 = index.sentences["p1.s1"], index.sentences["p1.s2"]
    assert s1.text.endswith("into three stages.")
    assert s2.text.startswith("Stage two")
    assert s1.line_indexes == [0, 1] and s2.line_indexes == [1, 2]

    shared_line = lines[1]
    words = {w["text"]: w["box_2d"] for w in shared_line["words"]}
    # Sentence 1 on the shared line: from "into" to "stages." only.
    b1 = s1.boxes[1]
    assert b1[1] == words["into"][1] and b1[3] == words["stages."][3]
    assert b1[3] < shared_line["box_2d"][3]
    # Sentence 2 on the shared line: from "Stage" to the line end.
    b2 = s2.boxes[0]
    assert b2[1] == words["Stage"][1] and b2[3] == words["a"][3]
    assert b2[1] > b1[3]
    # A line fully inside the sentence keeps its full width.
    assert s1.boxes[0][1] == lines[0]["box_2d"][1] and s1.boxes[0][3] == lines[0]["box_2d"][3]

    # Quoting both sentences widens the shared line back to cover both parts.
    span = index.resolve(["p1.s1", "p1.s2"])
    assert [b["line_index"] for b in span.boxes] == [0, 1, 2]
    assert span.boxes[1]["box_2d"][1] == b1[1] and span.boxes[1]["box_2d"][3] == b2[3]

    # Only the second sentence: its quote boxes start mid-line.
    only_two = index.resolve(["p1.s2"])
    assert only_two.boxes[0] == {"page_number": 1, "line_index": 1, "box_2d": b2}


def test_lines_without_words_fall_back_to_the_line_box():
    lines = [
        {"text": "এক লাইন। দুই", "box_2d": [100, 50, 120, 900]},
        {"text": "লাইন শেষ।", "box_2d": [121, 50, 140, 600]},
    ]
    text = "\n".join(l["text"] for l in lines)
    index = SentenceIndex.build([{"page_number": 2, "cleaned_text": text, "line_boxes": lines}])
    assert index.sentences["p2.s2"].boxes == [[100, 50, 120, 900], [121, 50, 140, 600]]


@pytest.mark.asyncio
async def test_analysis_adds_word_boxes_to_older_text_layer_pages(client):
    inst = await make_institution()
    _admin, token = await make_user(is_superuser=True)
    doc = await _upload(client, token, inst.id, _two_sentence_pdf())

    # Pretend the page was read before word boxes were stored.
    async with AsyncSessionLocal() as db:
        page = (await db.execute(
            select(DocumentPage).where(DocumentPage.document_version_id == uuid.UUID(doc["current_version_id"]))
        )).scalar_one()
        page.line_boxes = [{"text": l["text"], "box_2d": l["box_2d"]} for l in page.line_boxes]
        await db.commit()

    async with AsyncSessionLocal() as db:
        version = (await db.execute(
            select(DocumentVersion).where(DocumentVersion.id == uuid.UUID(doc["current_version_id"]))
        )).scalar_one()
        await db.refresh(version, ["pages"])
        assert not has_word_boxes(version.pages[0].line_boxes)
        assert await AnalysisService._fill_text_layer_word_boxes(version) == 1
        assert has_word_boxes(version.pages[0].line_boxes)


def test_text_layer_lines_by_page_skips_pages_without_a_text_layer():
    doc = pymupdf.open()
    doc.new_page()  # blank: goes to page-image reading
    p2 = doc.new_page()
    p2.insert_text((72, 100), "Banks must report every quarter to the Department of Off-site Supervision.")
    pdf = doc.tobytes()
    doc.close()
    by_page = text_layer_lines_by_page(pdf)
    assert list(by_page) == [2]
    assert by_page[2][0]["words"][0]["text"] == "Banks"


# ---------------------------------------------------------------------------
# Page image endpoint
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_page_image_is_a_real_image_and_is_cached(client):
    inst = await make_institution()
    _admin, token = await make_user(is_superuser=True)
    doc = await _upload(client, token, inst.id, _two_sentence_pdf())
    url = f"/api/v1/documents/{doc['id']}/versions/{doc['current_version_id']}/pages/1/image"

    resp = await client.get(url, params={"dpi": 140}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "image/webp"
    assert resp.headers["x-page-dpi"] == "144"
    assert resp.headers["cache-control"].startswith("public")
    img = Image.open(io.BytesIO(resp.content))
    assert img.format == "WEBP"
    # A4 at 144 dpi: 595 x 842 points -> about 1190 x 1684 pixels.
    assert abs(img.width - 1190) <= 2 and abs(img.height - 1684) <= 2

    cached = page_images.cache_path(doc["current_version_id"], 1, 144, "webp")
    assert cached.is_file()
    again = await client.get(url, params={"dpi": 144}, headers=_auth(token))
    assert again.content == resp.content

    png = await client.get(url, params={"format": "png", "dpi": 96}, headers=_auth(token))
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert png.content.startswith(b"\x89PNG")

    assert (await client.get(url.replace("/pages/1/", "/pages/2/"), headers=_auth(token))).status_code == 404
    assert (await client.get(url.replace("/pages/1/", "/pages/0/"), headers=_auth(token))).status_code == 404
    assert (await client.get(url, params={"format": "gif"}, headers=_auth(token))).status_code == 422


@pytest.mark.asyncio
async def test_page_image_follows_document_access_rules(client):
    inst = await make_institution()
    _admin, token_admin = await make_user(is_superuser=True)
    _owner, token_owner = await make_user()
    _other, token_other = await make_user()

    shared = await _upload(client, token_admin, inst.id, _two_sentence_pdf())
    private = await _upload(client, token_owner, inst.id, _two_sentence_pdf())
    assert private["is_private"] is True

    def image_url(d):
        return f"/api/v1/documents/{d['id']}/versions/{d['current_version_id']}/pages/1/image"

    # Shared: any signed-in user (and, like the other read endpoints, anonymous readers).
    for headers in (_auth(token_admin), _auth(token_owner), _auth(token_other), {}):
        assert (await client.get(image_url(shared), headers=headers)).status_code == 200

    # Private: only the owner. Everyone else, superusers included, gets a 404.
    owner_resp = await client.get(image_url(private), headers=_auth(token_owner))
    assert owner_resp.status_code == 200
    assert owner_resp.headers["cache-control"] == "private, no-store"
    for headers in (_auth(token_other), _auth(token_admin), {}):
        assert (await client.get(image_url(private), headers=headers)).status_code == 404

    # A version id that belongs to another document is a 404 too.
    mixed = f"/api/v1/documents/{shared['id']}/versions/{private['current_version_id']}/pages/1/image"
    assert (await client.get(mixed, headers=_auth(token_owner))).status_code == 404
    assert (await client.get(
        f"/api/v1/documents/{uuid.uuid4()}/versions/{uuid.uuid4()}/pages/1/image", headers=_auth(token_owner)
    )).status_code == 404
