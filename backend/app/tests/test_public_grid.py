"""Home page grid data (modules/library/public.py applies_grid)."""
import uuid
from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.main import app

from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.documents.models import Document
from backend.app.modules.library import public
from backend.app.tests.factories import make_institution


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_grid_lists_this_years_circulars(client):
    inst = await make_institution()
    ref = f"GRID Circular No. {uuid.uuid4().int % 9000 + 1000}/{date.today().year}"
    async with AsyncSessionLocal() as db:
        db.add(Document(institution_id=inst.id, title=f"{ref}: Grid test rules", reference_number=ref,
                        publication_date=date(date.today().year, 1, 2), publication_status="EXTRACTED", is_synthetic_fixture=False))
        await db.commit()
    public._GRID_CACHE.update(at=0.0, data=None)
    res = await client.get("/api/v1/public/grid")
    assert res.status_code == 200
    body = res.json()
    assert body["year"] == date.today().year and body["library"] >= 1
    hit = [c for c in body["circulars"] if c["ref"] == ref]
    assert hit and hit[0]["title"] == "Grid test rules" and hit[0]["ents"] == [] and hit[0]["mand"] == 0
