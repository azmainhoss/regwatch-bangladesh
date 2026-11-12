"""Shared test setup.

Points the app at a throwaway SQLite database and storage folder before any
application module is imported, so the test run never touches ./data/regwatch.db
or ./storage.
"""
import os
import shutil
import tempfile
from pathlib import Path

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="regwatch_test_"))
_TEST_DB = _TEST_ROOT / "test.db"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB.as_posix()}"
os.environ["SYNC_DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["STORAGE_LOCAL_ROOT"] = str(_TEST_ROOT / "storage")
os.environ["ENVIRONMENT"] = "development"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["AI_PROVIDER"] = "mock"
os.environ["ANALYSIS_PROVIDER"] = "mock"
os.environ["ANALYSIS_MODEL"] = ""
os.environ["OPENAI_COMPAT_BASE_URL"] = ""
os.environ["OPENAI_COMPAT_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["BB_REQUEST_INTERVAL_SECONDS"] = "0"

import pytest  # noqa: E402

from backend.app.database.models import Base  # noqa: E402
from backend.app.database.session import sync_engine  # noqa: E402

Base.metadata.create_all(bind=sync_engine)


def _load_reference_data() -> None:
    """Load the project's development seed (Bangladesh Bank, its departments, the
    circular source and the demo organization) that the API tests expect."""
    import asyncio
    import contextlib
    import io

    from backend.app.database.session import async_engine
    from backend.scripts.seed import seed

    async def _run():
        with contextlib.redirect_stdout(io.StringIO()):
            await seed()
        await async_engine.dispose()

    asyncio.run(_run())


_load_reference_data()


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail fast if a test tries to open a real network socket."""
    import socket

    real_connect = socket.socket.connect

    def guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in ("127.0.0.1", "localhost", "::1") and self.family in (socket.AF_INET, socket.AF_INET6):
            raise RuntimeError(f"Tests must not use the network (tried to reach {address!r})")
        return real_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    yield


def pytest_sessionfinish(session, exitstatus):
    try:
        sync_engine.dispose()
        shutil.rmtree(_TEST_ROOT, ignore_errors=True)
    except Exception:
        pass
