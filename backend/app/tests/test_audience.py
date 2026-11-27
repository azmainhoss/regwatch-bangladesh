"""For you (owner, 2026-11-28): who each circular applies to, the reader's institution type, guessing it from the
company name, "Applies to me" / "Not for me", and the rule that one click never overrules the institution type."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.audience import service
from backend.app.modules.audience.known import guess_institution
from backend.app.modules.audience.rules import derive
from backend.app.modules.audience.service import DocFacts, Profile, Scorer
from backend.app.modules.documents.models import DocumentPage
from backend.app.modules.identity.models import UserProfile
from backend.app.tests.factories import make_document, make_user

API = "/api/v1"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def test_addressee_line_rules():
    bn = "বিআরপিডি সার্কুলার নং- ০৭\nব্যবস্থাপনা পরিচালক/প্রধান নির্বাহী\nবাংলাদেশে কার্যরত সকল তফসিলি ব্যাংক।\nপ্রিয় মহোদয়,\nঅনুমোদিত ডিলার পরে"
    assert derive("BRPD Circular No. 07/2019", "Charges", bn) == ({"SCHEDULED_BANK"}, "ADDRESSEE")
    en = "FEPD-2 Circular Letter No. 03\nHead Offices of all\nAuthorized Dealers in Bangladesh\nDear Sirs,"
    assert derive("FEPD-2 Circular Letter No. 03", "Price verification", en)[0] == {"AUTHORIZED_DEALER"}
    assert derive("DFIM Circular No. 2/2020", "x", "no addressee here") == ({"NBFI"}, "DEPARTMENT")
    assert derive("XYZ 1", "x", "") == (set(), "ADDRESSEE")


def test_company_guess():
    assert guess_institution("Mercantile Bank PLC") == ("CONVENTIONAL_BANK", True)
    assert guess_institution("First Security Islami Bank PLC") == ("ISLAMIC_BANK", True)
    assert guess_institution("Sonali Bank") == ("STATE_OWNED_BANK", True)
    assert guess_institution("Ansar Vdp Unnayan Bank") == ("SPECIALIZED_BANK", False)
    assert guess_institution("Union Capital Limited") == ("NBFI", False)
    assert guess_institution("M. S. Salekin & Co., Chartered Accountants") == ("AUDITOR", False)
    assert guess_institution("Rahman Rahman Huq") == ("AUDITOR", False)
    assert guess_institution("Rahimafrooz Bangladesh Ltd") is None
    assert guess_institution("") is None


def _facts(**docs):
    return {k: DocFacts(ref, dept, frozenset(topics), frozenset(ents)) for k, (ref, dept, topics, ents) in docs.items()}


def test_profile_match_reason_and_one_click_does_not_overrule():
    a, b, c, d = (uuid.uuid4() for _ in range(4))
    docs = _facts(**{
        str(a): ("FEPD Circular No. 1", "FEPD", {"FOREX"}, {"AUTHORIZED_DEALER"}),
        str(b): ("FEPD Circular No. 2", "FEPD", {"FOREX"}, {"AUTHORIZED_DEALER"}),
        str(c): ("FEPD Circular No. 3", "FEPD", {"FOREX"}, {"AUTHORIZED_DEALER"}),
        str(d): ("DFIM Circular No. 4", "DFIM", {"CREDIT"}, {"NBFI"}),
    })
    docs = {uuid.UUID(k): v for k, v in docs.items()}
    bank = Profile(kind="CONVENTIONAL_BANK", has_ad=True)
    s = Scorer(bank, docs, {})
    v = s.verdict(a)
    assert v.for_you and v.reason == "Applies to authorised dealers (AD branches). Your institution has AD branches."
    assert not s.verdict(d).for_you
    # One "Not for me" drops that circular only; similar ones stay flagged.
    s = Scorer(bank, docs, {a: (-1, True)})
    assert not s.verdict(a).for_you and s.verdict(b).for_you
    # Repeated "Not for me" on the same kind stops flagging it (nothing is hidden, only the flag goes).
    s = Scorer(bank, docs, {a: (-1, True), b: (-1, True)})
    assert not s.verdict(c).for_you


def test_applies_to_me_flags_similar():
    a, b, c = (uuid.uuid4() for _ in range(3))
    docs = {
        a: DocFacts("PSD Circular No. 1", "PSD", frozenset({"PAYMENTS"}), frozenset({"PAYMENT_SERVICE_PROVIDER"})),
        b: DocFacts("PSD Circular No. 2", "PSD", frozenset({"PAYMENTS"}), frozenset({"PAYMENT_SERVICE_PROVIDER"})),
        c: DocFacts("DFIM Circular No. 3", "DFIM", frozenset({"CREDIT"}), frozenset({"NBFI"})),
    }
    s = Scorer(Profile(kind="OTHER"), docs, {a: (1, True)})
    assert s.verdict(a).reason == "You marked this as applying to you."
    v = s.verdict(b)
    assert v.for_you and v.reason == "Similar to PSD Circular No. 1, which you marked as applying to you."
    assert not s.verdict(c).for_you
    # Removing a learned interest (muting its tags) stops the similarity.
    muted = Profile(kind="OTHER", muted={"dept:PSD", "topic:PAYMENTS", "entity:PAYMENT_SERVICE_PROVIDER"})
    assert not Scorer(muted, docs, {a: (1, True)}).verdict(b).for_you


def test_auditor_follows_everything():
    a = uuid.uuid4()
    docs = {a: DocFacts("BRPD 1", "BRPD", frozenset(), frozenset({"SCHEDULED_BANK"}))}
    v = Scorer(Profile(kind="AUDITOR"), docs, {}).verdict(a)
    assert v.for_you and "auditor" in v.reason


async def test_api_profile_guess_marks_and_flags(client):
    doc, version, _ = await make_document(pages=1, reference_number=f"FEPD-1 Circular No. {uuid.uuid4().hex[:4]}")
    async with AsyncSessionLocal() as db:
        page = (await db.execute(select(DocumentPage).where(DocumentPage.document_version_id == version.id))).scalar_one()
        page.cleaned_text = "Head Offices of all Authorized Dealers in Bangladesh\nDear Sirs,\nADs shall verify prices."
        await db.commit()
        await service.refresh_document(db, doc.id)
        await db.commit()

    user, token = await make_user()
    auth = {"Authorization": f"Bearer {token}"}
    # Company recognised: the type is filled in without asking.
    async with AsyncSessionLocal() as db:
        db.add(UserProfile(user_id=user.id, preferences={"company": "City Bank PLC"}))
        await db.commit()
    me = (await client.get(f"{API}/audience/me", headers=auth)).json()
    assert me["institution_type"] == "CONVENTIONAL_BANK" and me["has_ad"] is True and me["source"] == "company"

    flags = (await client.get(f"{API}/audience/flags", params={"ids": str(doc.id)}, headers=auth)).json()
    f = flags[str(doc.id)]
    assert f["for_you"] and f["applies_to"] == ["Authorised dealers (AD branches)"] and "AD branches" in f["reason"]

    r = await client.put(f"{API}/audience/marks/{doc.id}", json={"value": -1}, headers=auth)
    assert r.status_code == 200 and r.json()["for_you"] is False and r.json()["mark"] == -1
    r = await client.put(f"{API}/audience/marks/{doc.id}", json={"value": 0}, headers=auth)
    assert r.json()["for_you"] is True

    # Changing the type by hand: a finance company does not get AD circulars.
    me = (await client.put(f"{API}/audience/me/profile", json={"institution_type": "NBFI"}, headers=auth)).json()
    assert me["institution_type"] == "NBFI" and me["source"] == "user" and me["has_ad"] is False
    flags = (await client.get(f"{API}/audience/flags", params={"ids": str(doc.id)}, headers=auth)).json()
    assert flags[str(doc.id)]["for_you"] is False
    assert (await client.put(f"{API}/audience/me/profile", json={"institution_type": "BOGUS"}, headers=auth)).status_code == 422

    guess = (await client.get(f"{API}/audience/guess", params={"company": "Union Capital Limited"})).json()
    assert guess == {"institution_type": "NBFI", "has_ad": False}
    assert (await client.get(f"{API}/audience/guess", params={"company": "Karim Trading"})).json()["institution_type"] is None
