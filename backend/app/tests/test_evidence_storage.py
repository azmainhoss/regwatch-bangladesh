"""Evidence files: short storage layout, old layout still downloads, save failures give a plain JSON error."""
import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.core.storage import LocalStorageService
from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.compliance import routes_tasks
from backend.app.modules.compliance.models import TaskEvidence
from backend.app.tests.test_compliance_workspace import PDF, base, one_item, task_for, upload, workspace


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def long_root() -> Path:
    """A storage root about 130 characters long: the short layout stays under 260, the old one does not."""
    root = Path(tempfile.mkdtemp(prefix="rw_long_"))
    while len(str(root)) < 100:
        root = root / "a_rather_long_folder_name"
    root = root / ("x" * (130 - len(str(root)) - 1))
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.mark.asyncio
async def test_short_layout_under_a_long_storage_root(client, monkeypatch):
    svc = LocalStorageService(str(long_root()))
    monkeypatch.setattr(routes_tasks, "storage_service", svc)
    ws = await workspace()
    rid, items, *_ = await one_item(client, ws)
    t = await task_for(client, ws, items[0]["id"], assignee="ANALYST")
    task_id = t["task"]["id"]
    up = await upload(client, ws, task_id)
    assert up.status_code == 201, up.text
    eid = up.json()["evidence"]["id"]
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(TaskEvidence).where(TaskEvidence.id == eid))).scalar_one()
        rel = row.storage_path
    parts = rel.replace("\\", "/").split("/")
    assert parts[0] == "evidence" and parts[1] == str(ws.org_id) and len(parts) == 4
    assert parts[2] == row.file_sha256[:2]
    assert len(str(svc.get_absolute_path(rel))) < 260
    # old layout would have been too long for Windows
    old = len(str(svc.root_dir)) + len(f"/evidence/{ws.org_id}/{items[0]['id']}/{task_id}/ab/cd/{row.file_sha256}.pdf")
    assert old > 260
    dl = await client.get(f"{base(ws)}/tasks/{task_id}/evidence/{eid}/download", headers=ws.headers("ANALYST"))
    assert dl.status_code == 200 and dl.content == PDF


@pytest.mark.asyncio
async def test_old_layout_still_downloads(client, monkeypatch):
    svc = LocalStorageService(tempfile.mkdtemp(prefix="rw_old_"))
    monkeypatch.setattr(routes_tasks, "storage_service", svc)
    ws = await workspace()
    rid, items, *_ = await one_item(client, ws)
    t = await task_for(client, ws, items[0]["id"], assignee="ANALYST")
    task_id = t["task"]["id"]
    up = await upload(client, ws, task_id)
    eid = up.json()["evidence"]["id"]
    # move the file to the old long layout and point the row at it
    old_ns = f"evidence/{ws.org_id}/{items[0]['id']}/{task_id}"
    rel, _, _ = svc.store_file(old_ns, "evidence", PDF, ".pdf", fanout=2)
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(TaskEvidence).where(TaskEvidence.id == eid))).scalar_one()
        os.remove(svc.get_absolute_path(row.storage_path))
        row.storage_path = rel
        await db.commit()
    dl = await client.get(f"{base(ws)}/tasks/{task_id}/evidence/{eid}/download", headers=ws.headers("ANALYST"))
    assert dl.status_code == 200 and dl.content == PDF


@pytest.mark.asyncio
async def test_save_failure_is_a_plain_json_error(client, monkeypatch):
    class Broken:
        def store_file(self, *a, **k):
            raise FileNotFoundError("path too long")

    monkeypatch.setattr(routes_tasks, "storage_service", Broken())
    ws = await workspace()
    rid, items, *_ = await one_item(client, ws)
    t = await task_for(client, ws, items[0]["id"], assignee="ANALYST")
    up = await upload(client, ws, t["task"]["id"])
    assert up.status_code == 500
    assert "could not be saved" in up.json()["detail"]
    assert "path too long" not in up.text
    after = await client.get(f"{base(ws)}/tasks/{t['task']['id']}/evidence", headers=ws.headers("ANALYST"))
    assert after.json() == []
