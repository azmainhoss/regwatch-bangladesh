"""Relationship linking, in-force status, graph/timeline/status endpoints, admin review and old-vs-new compare."""
import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.audit.models import AuditEvent
from backend.app.modules.documents.compare import compare_page_texts, split_paragraphs
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.relationships.linking import link_relationship_targets, normalize_reference
from backend.app.modules.relationships.models import DocumentRelationship
from backend.app.tests.factories import make_institution, make_user


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _dept() -> str:
    """A department code no other test uses, so reference numbers never collide across tests."""
    return "T" + uuid.uuid4().hex[:7].upper()


async def make_doc(ref, owner=None, pub=date(2024, 1, 1), pages=("Banks shall keep records.",), title=None):
    inst = await make_institution()
    async with AsyncSessionLocal() as db:
        doc = Document(
            institution_id=inst.id,
            title=title or f"{ref}: a rule about records",
            reference_number=ref,
            publication_date=pub,
            publication_status="PUBLISHED_HUMAN_REVIEWED",
            owner_user_id=owner.id if owner else None,
        )
        db.add(doc)
        await db.flush()
        version = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            file_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            file_size_bytes=10,
            storage_path="originals/none.pdf",
            page_count=len(pages),
        )
        db.add(version)
        await db.flush()
        doc.current_version_id = version.id
        page_rows = []
        for n, body in enumerate(pages, start=1):
            page = DocumentPage(document_version_id=version.id, page_number=n, raw_text=body, cleaned_text=body)
            db.add(page)
            page_rows.append(page)
        await db.commit()
        for p in page_rows:
            await db.refresh(p)
        await db.refresh(doc)
        await db.refresh(version)
        return doc, version, page_rows


async def make_link(source, target=None, rel_type="AMENDS", status="VERIFIED", hint=None, quote="This circular amends it.", page=None):
    async with AsyncSessionLocal() as db:
        rel = DocumentRelationship(
            source_document_id=source.id,
            target_document_id=target.id if target else None,
            target_reference_hint=hint,
            relationship_type=rel_type,
            supporting_quote=quote,
            source_page_id=page.id if page else None,
            verification_status=status,
            detection_method="AI_INFERRED",
        )
        db.add(rel)
        await db.commit()
        await db.refresh(rel)
        return rel


async def reload_rel(rel_id):
    async with AsyncSessionLocal() as db:
        return await db.get(DocumentRelationship, rel_id)


# ---------------------------------------------------------------- normalize_reference

def test_normalize_reference_spacing_and_punctuation():
    a = normalize_reference("BRPD Circular No. 14/2023")
    b = normalize_reference("BRPD circular no.14 / 2023")
    c = normalize_reference("  BRPD   Circular  No 14 / 2023 ")
    d = normalize_reference("BRPD Circular Nos. 14/2023")
    assert a == b == c == d == "brpd circular no 14/2023"


def test_normalize_reference_bangla_digits():
    assert normalize_reference("BRPD Circular No ১৪/২০২৩") == normalize_reference("BRPD Circular No. 14/2023")
    assert normalize_reference("এসএমইএসপিডি সার্কুলার নং ০৫/২০২৬") == normalize_reference("এসএমইএসপিডি সার্কুলার নং 5/2026")


def test_normalize_reference_leading_zero_and_date_tail():
    assert normalize_reference("SMESPD Circular No. 05/2026") == normalize_reference("smespd circular no 5/2026")
    assert normalize_reference("BRPD Circular No. 14 dated 23 September 2012") == "brpd circular no 14"


def test_circular_and_circular_letter_are_different():
    assert normalize_reference("DOS Circular Letter No. 3/2024") != normalize_reference("DOS Circular No. 3/2024")
    assert normalize_reference("BRPD Master Circular No. 3/2024") != normalize_reference("BRPD Circular No. 3/2024")
    assert normalize_reference("BRPD Circular No. 3/2024") != normalize_reference("DOS Circular No. 3/2024")
    assert normalize_reference("BRPD Circular No. 3/2024") != normalize_reference("BRPD Circular No. 3/2025")


def test_normalize_reference_without_number_is_none():
    assert normalize_reference(None) is None
    assert normalize_reference("") is None
    assert normalize_reference("the Bank Company Act") is None


# ---------------------------------------------------------------- linking

@pytest.mark.asyncio
async def test_link_forward_when_target_already_exists():
    dept = _dept()
    older, _, _ = await make_doc(f"{dept} Circular No. 14/2023")
    newer, _, _ = await make_doc(f"{dept} Circular No. 20/2024")
    rel = await make_link(newer, None, hint=f"{dept} circular no.14 / 2023")
    async with AsyncSessionLocal() as db:
        assert await link_relationship_targets(db, newer.id) == 1
    assert str((await reload_rel(rel.id)).target_document_id) == str(older.id)
    async with AsyncSessionLocal() as db:
        assert await link_relationship_targets(db) == 0  # safe to run again


@pytest.mark.asyncio
async def test_link_in_reverse_when_cited_circular_arrives_later():
    dept = _dept()
    newer, _, _ = await make_doc(f"{dept} Circular No. 20/2024")
    rel = await make_link(newer, None, hint=f"{dept} Circular No. 14/2023")
    async with AsyncSessionLocal() as db:
        assert await link_relationship_targets(db, newer.id) == 0
    assert (await reload_rel(rel.id)).target_document_id is None
    older, _, _ = await make_doc(f"{dept} Circular No. 14/2023")
    async with AsyncSessionLocal() as db:
        assert await link_relationship_targets(db, older.id) == 1
    assert str((await reload_rel(rel.id)).target_document_id) == str(older.id)


@pytest.mark.asyncio
async def test_ambiguous_match_is_not_linked():
    dept = _dept()
    await make_doc(f"{dept} Circular No. 14/2023")
    await make_doc(f"{dept}  circular no 14/2023")
    src, _, _ = await make_doc(f"{dept} Circular No. 30/2024")
    rel = await make_link(src, None, hint=f"{dept} Circular No. 14/2023")
    async with AsyncSessionLocal() as db:
        assert await link_relationship_targets(db) == 0
    assert (await reload_rel(rel.id)).target_document_id is None


@pytest.mark.asyncio
async def test_circular_letter_hint_never_links_to_a_plain_circular():
    dept = _dept()
    await make_doc(f"{dept} Circular No. 3/2024")
    src, _, _ = await make_doc(f"{dept} Circular No. 30/2024")
    rel = await make_link(src, None, hint=f"{dept} Circular Letter No. 3/2024")
    async with AsyncSessionLocal() as db:
        await link_relationship_targets(db)
    assert (await reload_rel(rel.id)).target_document_id is None


@pytest.mark.asyncio
async def test_private_documents_never_become_link_targets():
    owner, _ = await make_user()
    dept = _dept()
    await make_doc(f"{dept} Circular No. 14/2023", owner=owner)
    src, _, _ = await make_doc(f"{dept} Circular No. 30/2024")
    rel = await make_link(src, None, hint=f"{dept} Circular No. 14/2023")
    async with AsyncSessionLocal() as db:
        await link_relationship_targets(db)
    assert (await reload_rel(rel.id)).target_document_id is None


@pytest.mark.asyncio
async def test_a_circular_is_never_linked_to_itself():
    dept = _dept()
    doc, _, _ = await make_doc(f"{dept} Circular No. 14/2023")
    rel = await make_link(doc, None, hint=f"{dept} Circular No. 14/2023", rel_type="REFERENCES")
    async with AsyncSessionLocal() as db:
        await link_relationship_targets(db)
    assert (await reload_rel(rel.id)).target_document_id is None


@pytest.mark.asyncio
async def test_dated_hint_links_to_the_circular_filed_with_that_year():
    dept = _dept()
    older, _, _ = await make_doc(f"{dept} Circular No. 14/2012")
    src, _, _ = await make_doc(f"{dept} Circular No. 30/2024")
    rel = await make_link(src, None, hint=f"{dept} Circular No. 14 dated 23 September 2012")
    async with AsyncSessionLocal() as db:
        await link_relationship_targets(db, src.id)
    assert str((await reload_rel(rel.id)).target_document_id) == str(older.id)


@pytest.mark.asyncio
async def test_ingesting_a_circular_links_earlier_citations(client):
    """The upload path calls the linker, so a circular that was cited before it arrived gets linked."""
    import pymupdf

    admin, token = await make_user(is_superuser=True)
    inst = await make_institution()
    dept = _dept()
    src, _, _ = await make_doc(f"{dept} Circular No. 30/2024")
    rel = await make_link(src, None, hint=f"{dept} Circular No. 14/2023")
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "Banks shall keep records.")
    data = pdf.tobytes()
    res = await client.post(
        "/api/v1/documents/upload",
        data={
            "institution_id": str(inst.id),
            "title": "Records rule",
            "publication_date": "2023-05-01",
            "reference_number": f"{dept} Circular No. 14/2023",
            "visibility": "shared",
        },
        files={"file": ("c.pdf", data, "application/pdf")},
        headers=_auth(token),
    )
    assert res.status_code == 201, res.text
    assert str((await reload_rel(rel.id)).target_document_id) == res.json()["document"]["id"]


# ---------------------------------------------------------------- status

async def status_of(client, doc, token=None):
    res = await client.get(f"/api/v1/relationships/document/{doc.id}/status", headers=_auth(token) if token else {})
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.asyncio
async def test_verified_repeal_makes_it_repealed(client):
    dept = _dept()
    old, _, pages = await make_doc(f"{dept} Circular No. 1/2020", pub=date(2020, 1, 1))
    new, _, new_pages = await make_doc(f"{dept} Circular No. 2/2024", pub=date(2024, 1, 1))
    await make_link(new, old, rel_type="REPEALS", quote="Circular No. 1 is hereby repealed.", page=new_pages[0])
    body = await status_of(client, old)
    assert body["in_force_status"] == "REPEALED"
    assert body["in_force_by"]["id"] == str(new.id)
    assert body["current_version"]["id"] == str(new.id)
    link = body["verified_incoming"][0]
    assert link["supporting_quote"] == "Circular No. 1 is hereby repealed."
    assert link["page_number"] == 1
    assert link["source_version_id"] == str(new.current_version_id)
    assert (await status_of(client, new))["in_force_status"] == "IN_FORCE"


@pytest.mark.asyncio
async def test_pending_link_is_listed_but_never_changes_status(client):
    dept = _dept()
    old, _, _ = await make_doc(f"{dept} Circular No. 1/2020")
    new, _, _ = await make_doc(f"{dept} Circular No. 2/2024")
    await make_link(new, old, rel_type="REPEALS", status="PENDING_REVIEW")
    body = await status_of(client, old)
    assert body["in_force_status"] == "IN_FORCE"
    assert body["in_force_by"] is None
    assert body["verified_incoming"] == []
    assert len(body["unconfirmed_incoming"]) == 1
    assert body["current_version"]["id"] == str(old.id)


@pytest.mark.asyncio
async def test_rejected_link_is_ignored_everywhere(client):
    dept = _dept()
    old, _, _ = await make_doc(f"{dept} Circular No. 1/2020")
    new, _, _ = await make_doc(f"{dept} Circular No. 2/2024")
    await make_link(new, old, rel_type="REPLACES", status="REJECTED")
    body = await status_of(client, old)
    assert body["in_force_status"] == "IN_FORCE"
    assert body["verified_incoming"] == [] and body["unconfirmed_incoming"] == []
    graph = (await client.get(f"/api/v1/relationships/document/{old.id}/graph")).json()
    assert graph["edges"] == []


@pytest.mark.asyncio
async def test_amendment_and_replacement_statuses(client):
    dept = _dept()
    a, _, _ = await make_doc(f"{dept} Circular No. 1/2020", pub=date(2020, 1, 1))
    b, _, _ = await make_doc(f"{dept} Circular No. 2/2021", pub=date(2021, 1, 1))
    c, _, _ = await make_doc(f"{dept} Circular No. 3/2022", pub=date(2022, 1, 1))
    await make_link(b, a, rel_type="AMENDS")
    assert (await status_of(client, a))["in_force_status"] == "AMENDED"
    await make_link(c, a, rel_type="SUPERSEDES")
    body = await status_of(client, a)
    assert body["in_force_status"] == "REPLACED"
    assert body["in_force_by"]["id"] == str(c.id)


@pytest.mark.asyncio
async def test_chain_follows_forward_to_the_newest_in_force(client):
    dept = _dept()
    a, _, _ = await make_doc(f"{dept} Circular No. 1/2020", pub=date(2020, 1, 1))
    b, _, _ = await make_doc(f"{dept} Circular No. 2/2021", pub=date(2021, 1, 1))
    c, _, _ = await make_doc(f"{dept} Circular No. 3/2022", pub=date(2022, 1, 1))
    await make_link(b, a, rel_type="REPLACES")
    await make_link(c, b, rel_type="SUPERSEDES")
    body = await status_of(client, a)
    assert body["in_force_status"] == "REPLACED"
    assert body["current_version"]["id"] == str(c.id)
    assert body["chain_has_cycle"] is False
    timeline = (await client.get(f"/api/v1/relationships/document/{a.id}/timeline")).json()
    assert [i["document"]["id"] for i in timeline["items"]] == [str(a.id), str(b.id), str(c.id)]
    assert [i["is_current"] for i in timeline["items"]] == [False, False, True]
    assert timeline["current_version"]["id"] == str(c.id)
    assert timeline["items"][1]["changes"][0]["relationship_type"] == "REPLACES"
    assert timeline["items"][1]["changes"][0]["target"]["id"] == str(a.id)


@pytest.mark.asyncio
async def test_cycle_does_not_hang(client):
    dept = _dept()
    a, _, _ = await make_doc(f"{dept} Circular No. 1/2020", pub=date(2020, 1, 1))
    b, _, _ = await make_doc(f"{dept} Circular No. 2/2021", pub=date(2021, 1, 1))
    await make_link(b, a, rel_type="REPLACES")
    await make_link(a, b, rel_type="REPLACES")
    body = await status_of(client, a)
    assert body["chain_has_cycle"] is True
    assert (await client.get(f"/api/v1/relationships/document/{a.id}/timeline")).status_code == 200
    assert (await client.get(f"/api/v1/relationships/document/{a.id}/graph?depth=3")).status_code == 200


@pytest.mark.asyncio
async def test_in_force_status_on_list_and_detail(client):
    dept = _dept()
    old, _, _ = await make_doc(f"{dept} Circular No. 1/2020", pub=date(2020, 1, 1))
    new, _, _ = await make_doc(f"{dept} Circular No. 2/2024", pub=date(2024, 1, 1))
    await make_link(new, old, rel_type="REPLACES")
    detail = (await client.get(f"/api/v1/documents/{old.id}")).json()
    assert detail["in_force_status"] == "REPLACED"
    assert detail["in_force_by_id"] == str(new.id)
    assert detail["in_force_by_reference"] == new.reference_number
    listing = (await client.get(f"/api/v1/documents?search={dept}&corpus_type=ALL")).json()
    by_id = {d["id"]: d for d in listing}
    assert by_id[str(old.id)]["in_force_status"] == "REPLACED"
    assert by_id[str(new.id)]["in_force_status"] == "IN_FORCE"


# ---------------------------------------------------------------- graph and access

@pytest.mark.asyncio
async def test_graph_has_unlinked_hint_nodes_and_dashed_pending_edges(client):
    dept = _dept()
    a, _, _ = await make_doc(f"{dept} Circular No. 1/2020", pub=date(2020, 1, 1))
    b, _, pages = await make_doc(f"{dept} Circular No. 2/2021", pub=date(2021, 1, 1))
    await make_link(b, a, rel_type="AMENDS", page=pages[0])
    await make_link(b, None, rel_type="REFERENCES", status="PENDING_REVIEW", hint=f"{dept} Circular No. 99/1999")
    graph = (await client.get(f"/api/v1/relationships/document/{b.id}/graph?depth=2")).json()
    nodes = {n["key"]: n for n in graph["nodes"]}
    assert nodes[str(a.id)]["in_force_status"] == "AMENDED"
    assert nodes[str(b.id)]["is_center"] is True
    hint_nodes = [n for n in graph["nodes"] if not n["in_library"]]
    assert len(hint_nodes) == 1 and hint_nodes[0]["title"] == f"{dept} Circular No. 99/1999"
    edge_types = {e["relationship_type"]: e for e in graph["edges"]}
    assert edge_types["AMENDS"]["page_number"] == 1
    assert edge_types["AMENDS"]["supporting_quote"]
    assert edge_types["REFERENCES"]["verification_status"] == "PENDING_REVIEW"
    assert edge_types["REFERENCES"]["target"] == hint_nodes[0]["key"]


@pytest.mark.asyncio
async def test_graph_depth_is_limited(client):
    dept = _dept()
    docs = [(await make_doc(f"{dept} Circular No. {i}/20{20 + i}", pub=date(2020 + i, 1, 1)))[0] for i in range(1, 6)]
    for newer, older in zip(docs[1:], docs[:-1]):
        await make_link(newer, older, rel_type="AMENDS")
    one = (await client.get(f"/api/v1/relationships/document/{docs[0].id}/graph?depth=1")).json()
    assert len(one["nodes"]) == 2
    three = (await client.get(f"/api/v1/relationships/document/{docs[0].id}/graph?depth=3")).json()
    assert len(three["nodes"]) == 4
    assert (await client.get(f"/api/v1/relationships/document/{docs[0].id}/graph?depth=4")).status_code == 422


@pytest.mark.asyncio
async def test_private_documents_stay_private_in_all_three_views(client):
    owner, owner_token = await make_user()
    other, other_token = await make_user()
    dept = _dept()
    shared, _, _ = await make_doc(f"{dept} Circular No. 1/2020", pub=date(2020, 1, 1))
    mine, _, _ = await make_doc(f"{dept} Circular No. 2/2024", owner=owner, pub=date(2024, 1, 1), title="My private circular")
    await make_link(mine, shared, rel_type="REPEALS")

    for view in ("status", "timeline", "graph"):
        url = f"/api/v1/relationships/document/{mine.id}/{view}"
        assert (await client.get(url)).status_code == 404
        assert (await client.get(url, headers=_auth(other_token))).status_code == 404
        assert (await client.get(url, headers=_auth(owner_token))).status_code == 200

    # The shared circular's page never reveals the private one to anyone else...
    for headers in ({}, _auth(other_token)):
        body = await (client.get(f"/api/v1/relationships/document/{shared.id}/status", headers=headers))
        data = body.json()
        assert data["in_force_status"] == "IN_FORCE"
        assert data["verified_incoming"] == []
        text = (await client.get(f"/api/v1/relationships/document/{shared.id}/graph", headers=headers)).text
        text += (await client.get(f"/api/v1/relationships/document/{shared.id}/timeline", headers=headers)).text
        assert "My private circular" not in text and str(mine.id) not in text
    # ...but the owner sees it.
    mine_view = (await client.get(f"/api/v1/relationships/document/{shared.id}/status", headers=_auth(owner_token))).json()
    assert mine_view["in_force_status"] == "REPEALED"
    assert mine_view["verified_incoming"][0]["source"]["is_private"] is True


# ---------------------------------------------------------------- admin review

@pytest.mark.asyncio
async def test_review_is_admin_only_and_updates_status(client):
    admin, admin_token = await make_user(is_superuser=True)
    user, user_token = await make_user()
    dept = _dept()
    old, _, _ = await make_doc(f"{dept} Circular No. 1/2020")
    new, _, pages = await make_doc(f"{dept} Circular No. 2/2024", pub=date(2024, 1, 1))
    rel = await make_link(new, old, rel_type="REPLACES", status="PENDING_REVIEW", page=pages[0])
    url = f"/api/v1/relationships/{rel.id}/review"

    assert (await client.post(url, json={"decision": "VERIFIED"})).status_code == 401
    assert (await client.post(url, json={"decision": "VERIFIED"}, headers=_auth(user_token))).status_code == 403
    assert (await reload_rel(rel.id)).verification_status == "PENDING_REVIEW"
    assert (await client.post(url, json={"decision": "MAYBE"}, headers=_auth(admin_token))).status_code == 422

    res = await client.post(url, json={"decision": "VERIFIED"}, headers=_auth(admin_token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["link"]["verification_status"] == "VERIFIED"
    assert body["target_in_force_status"] == "REPLACED"
    saved = await reload_rel(rel.id)
    assert saved.verification_status == "VERIFIED" and str(saved.reviewed_by) == str(admin.id) and saved.reviewed_at is not None
    assert (await status_of(client, old))["in_force_status"] == "REPLACED"

    async with AsyncSessionLocal() as db:
        events = (await db.execute(select(AuditEvent).where(AuditEvent.entity_id == rel.id))).scalars().all()
    assert len(events) == 1 and events[0].action == "RELATIONSHIP_REVIEWED"

    res = await client.post(url, json={"decision": "REJECTED"}, headers=_auth(admin_token))
    assert res.json()["target_in_force_status"] == "IN_FORCE"
    assert (await status_of(client, old))["in_force_status"] == "IN_FORCE"


@pytest.mark.asyncio
async def test_pending_list_and_relink_are_admin_only(client):
    admin, admin_token = await make_user(is_superuser=True)
    user, user_token = await make_user()
    dept = _dept()
    old, _, _ = await make_doc(f"{dept} Circular No. 1/2020")
    new, _, _ = await make_doc(f"{dept} Circular No. 2/2024")
    rel = await make_link(new, None, rel_type="AMENDS", status="PENDING_REVIEW", hint=f"{dept} Circular No. 1/2020")

    assert (await client.get("/api/v1/relationships/pending")).status_code == 401
    assert (await client.get("/api/v1/relationships/pending", headers=_auth(user_token))).status_code == 403
    assert (await client.post("/api/v1/relationships/relink", headers=_auth(user_token))).status_code == 403

    res = await client.post("/api/v1/relationships/relink", headers=_auth(admin_token))
    assert res.status_code == 200 and res.json()["linked"] >= 1
    assert str((await reload_rel(rel.id)).target_document_id) == str(old.id)

    pending = (await client.get("/api/v1/relationships/pending?limit=200", headers=_auth(admin_token))).json()
    ours = [l for l in pending["links"] if l["id"] == str(rel.id)]
    assert len(ours) == 1 and ours[0]["target"]["id"] == str(old.id)


@pytest.mark.asyncio
async def test_admin_cannot_review_a_link_from_someone_elses_private_upload(client):
    admin, admin_token = await make_user(is_superuser=True)
    owner, _ = await make_user()
    dept = _dept()
    mine, _, _ = await make_doc(f"{dept} Circular No. 2/2024", owner=owner)
    rel = await make_link(mine, None, status="PENDING_REVIEW", hint=f"{dept} Circular No. 1/2020")
    res = await client.post(f"/api/v1/relationships/{rel.id}/review", json={"decision": "VERIFIED"}, headers=_auth(admin_token))
    assert res.status_code == 404
    pending = (await client.get("/api/v1/relationships/pending?limit=200", headers=_auth(admin_token))).json()
    assert str(rel.id) not in [l["id"] for l in pending["links"]]


# ---------------------------------------------------------------- compare

def _ops(left, right):
    ops, stats, pages = compare_page_texts(left, right)
    return ops, stats


def test_compare_equal_text_is_all_equal():
    text = "1. Banks shall keep records.\n\n2. Banks shall report monthly."
    ops, stats = _ops([(1, text)], [(1, text)])
    assert [o.op for o in ops] == ["equal", "equal"]
    assert stats.equal == 2 and stats.insert == stats.delete == stats.replace == 0


def test_compare_finds_an_inserted_clause():
    left = "1. Banks shall keep records.\n2. Banks shall report monthly."
    right = "1. Banks shall keep records.\n1A. Banks shall appoint an officer.\n2. Banks shall report monthly."
    ops, stats = _ops([(1, left)], [(1, right)])
    assert [o.op for o in ops] == ["equal", "insert", "equal"]
    assert ops[1].right_text == "1A. Banks shall appoint an officer."
    assert ops[1].left_text is None


def test_compare_finds_a_deleted_clause():
    left = "1. Banks shall keep records.\n2. Banks shall report monthly."
    right = "1. Banks shall keep records."
    ops, _ = _ops([(1, left)], [(1, right)])
    assert [o.op for o in ops] == ["equal", "delete"]


def test_compare_word_level_diff_inside_a_changed_clause():
    left = "1. Banks shall maintain a provision of 1.00% on all loans."
    right = "1. Banks shall maintain a provision of 5.00% on all loans."
    ops, stats = _ops([(1, left)], [(1, right)])
    assert [o.op for o in ops] == ["replace"] and stats.replace == 1
    words = ops[0].words
    assert [(w.op, w.text.strip()) for w in words if w.op != "equal"] == [("delete", "1.00%"), ("insert", "5.00%")]
    assert "".join(w.text for w in words if w.op in ("equal", "delete")) == left
    assert "".join(w.text for w in words if w.op in ("equal", "insert")).strip() == right


def test_compare_bangla_text():
    left = "১. ব্যাংকসমূহ প্রতি মাসে প্রতিবেদন জমা দিবে।\n২. ঋণের সুদ হার ৯ শতাংশ।"
    right = "১. ব্যাংকসমূহ প্রতি ত্রৈমাসিকে প্রতিবেদন জমা দিবে।\n২. ঋণের সুদ হার ৯ শতাংশ।"
    ops, _ = _ops([(1, left)], [(1, right)])
    assert [o.op for o in ops] == ["replace", "equal"]
    changed = [(w.op, w.text.strip()) for w in ops[0].words if w.op != "equal"]
    assert changed == [("delete", "মাসে"), ("insert", "ত্রৈমাসিকে")]


def test_compare_pieces_are_exact_substrings_of_the_stored_text():
    left_pages = [(1, "1. Banks shall keep records for\n   five years.\n\n2. Fees are waived.\n"), (2, "3. Report by   June.\n")]
    right_pages = [(1, "1. Banks shall keep records for\n   ten years.\n\n2. Fees are waived.\n\n2A. New clause here.\n"), (2, "3. Report by   July.\n")]
    ops, _ = _ops(left_pages, right_pages)
    left_text = {n: t for n, t in left_pages}
    right_text = {n: t for n, t in right_pages}
    for op in ops:
        if op.left_text is not None:
            assert op.left_text in left_text[op.left_page]
        if op.right_text is not None:
            assert op.right_text in right_text[op.right_page]
        for w in op.words:
            if w.op in ("equal", "delete") and op.left_text is not None:
                assert w.text in op.left_text
            if w.op == "insert":
                assert w.text in op.right_text


def test_split_paragraphs_cuts_at_clause_numbers_without_losing_text():
    text = "Intro line\ncontinues here.\n1. First\n1.1 Sub clause\n(a) item\n5.00% is a number, not a clause\n\nLast."
    pieces = split_paragraphs(text)
    assert pieces == ["Intro line\ncontinues here.", "1. First", "1.1 Sub clause", "(a) item\n5.00% is a number, not a clause", "Last."]
    assert all(p in text for p in pieces)


@pytest.mark.asyncio
async def test_compare_endpoint_and_access(client):
    owner, owner_token = await make_user()
    other, other_token = await make_user()
    dept = _dept()
    old, old_v, _ = await make_doc(f"{dept} Circular No. 1/2020", pages=("1. Keep records.\n2. Report monthly.",))
    new, new_v, _ = await make_doc(f"{dept} Circular No. 2/2024", pages=("1. Keep records.\n2. Report quarterly.\n3. Appoint an officer.",))
    res = await client.get(f"/api/v1/documents/compare?left={old_v.id}&right={new_v.id}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert [o["op"] for o in body["ops"]] == ["equal", "replace", "insert"]
    assert body["stats"] == {"equal": 1, "insert": 1, "delete": 0, "replace": 1}
    assert body["left"]["reference_number"] == old.reference_number and body["truncated"] is False
    assert body["pages"][0]["right_page"] == 1

    same = (await client.get(f"/api/v1/documents/compare?left={old_v.id}&right={old_v.id}")).json()
    assert {o["op"] for o in same["ops"]} == {"equal"}

    mine, mine_v, _ = await make_doc(f"{dept} Circular No. 3/2025", owner=owner)
    url = f"/api/v1/documents/compare?left={old_v.id}&right={mine_v.id}"
    assert (await client.get(url)).status_code == 404
    assert (await client.get(url, headers=_auth(other_token))).status_code == 404
    assert (await client.get(url, headers=_auth(owner_token))).status_code == 200
    assert (await client.get(f"/api/v1/documents/compare?left={uuid.uuid4()}&right={old_v.id}")).status_code == 404
