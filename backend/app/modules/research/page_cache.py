"""In-memory copy of every page's search text, for a fast "Ask" page lookup.

Scanning 35 MB of page text with SQL LIKE takes seconds; scanning the same text held in memory
takes well under 0.1 s. The copy never goes stale: database triggers write the id of every page
whose text, version or document changes into a small change log, and each lookup first applies
the log entries it has not seen yet (a primary-key read, normally empty). Every writer is covered,
including the page reader and the archive import that run in other processes.

The copy only picks candidate pages. The winning pages are loaded fresh from the database, with
the visibility rules applied again, so quotes always come from the stored page text.
SQLite only; other databases use the SQL lookup in service.py.
"""
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text

from backend.app.core.logging import logger
from backend.app.database.session import sync_engine

CHANGE_TABLE = "search_page_changes"
KEEP_CHANGES = 50000  # older change rows are pruned; a cache that falls behind them reloads fully

_TRIGGERS = {
    "trg_search_pages_ins": f"""CREATE TRIGGER IF NOT EXISTS trg_search_pages_ins AFTER INSERT ON document_pages
        BEGIN INSERT INTO {CHANGE_TABLE}(page_id) VALUES (NEW.id); END""",
    "trg_search_pages_upd": f"""CREATE TRIGGER IF NOT EXISTS trg_search_pages_upd
        AFTER UPDATE OF raw_text, cleaned_text, document_version_id, page_number ON document_pages
        BEGIN INSERT INTO {CHANGE_TABLE}(page_id) VALUES (NEW.id); END""",
    "trg_search_pages_del": f"""CREATE TRIGGER IF NOT EXISTS trg_search_pages_del AFTER DELETE ON document_pages
        BEGIN INSERT INTO {CHANGE_TABLE}(page_id) VALUES (OLD.id); END""",
    "trg_search_versions_upd": f"""CREATE TRIGGER IF NOT EXISTS trg_search_versions_upd
        AFTER UPDATE OF status, document_id ON document_versions
        BEGIN INSERT INTO {CHANGE_TABLE}(page_id)
              SELECT id FROM document_pages WHERE document_version_id = NEW.id; END""",
    "trg_search_documents_upd": f"""CREATE TRIGGER IF NOT EXISTS trg_search_documents_upd
        AFTER UPDATE OF owner_user_id, institution_id ON documents
        BEGIN INSERT INTO {CHANGE_TABLE}(page_id)
              SELECT p.id FROM document_pages p JOIN document_versions v ON v.id = p.document_version_id
              WHERE v.document_id = NEW.id; END""",
}

_PAGE_SQL = """
SELECT p.id, p.page_number,
       CASE WHEN COALESCE(p.cleaned_text, '') != '' THEN p.cleaned_text ELSE COALESCE(p.raw_text, '') END,
       d.id, d.owner_user_id, d.institution_id, v.status
FROM document_pages p
JOIN document_versions v ON v.id = p.document_version_id
JOIN documents d ON d.id = v.document_id
"""


@dataclass
class CachedPage:
    page_id: str
    page_number: int
    text: str  # lower-cased search text
    doc_id: str
    owner_user_id: Optional[str]
    institution_id: Optional[str]
    superseded: bool


def _norm(value) -> Optional[str]:
    return None if value is None else str(value).replace("-", "").lower()


def _to_page(row) -> Optional[CachedPage]:
    page_id, page_number, body, doc_id, owner, inst, status = row
    if not body or not body.strip():
        return None
    return CachedPage(str(page_id), int(page_number), body.lower(), _norm(doc_id), _norm(owner), _norm(inst),
                      status == "SUPERSEDED")


class PageTextCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._pages: Dict[str, CachedPage] = {}
        self._ordered: Optional[List[CachedPage]] = None  # page-number order, rebuilt after changes
        self._seq = -1  # last change-log row applied; -1 = not loaded
        self._generation = 0  # bumped by each full load
        self._changed: Dict[str, int] = {}  # page id -> change-log row that last touched it

    # ------------------------------------------------------------------ setup / sync
    @staticmethod
    def _ensure_log(conn) -> None:
        conn.execute(text(
            f"CREATE TABLE IF NOT EXISTS {CHANGE_TABLE} (seq INTEGER PRIMARY KEY AUTOINCREMENT, page_id VARCHAR(36))"
        ))
        for ddl in _TRIGGERS.values():
            conn.execute(text(ddl))

    def _full_load(self, conn) -> None:
        self._ensure_log(conn)
        seq = conn.execute(text(f"SELECT COALESCE(MAX(seq), 0) FROM {CHANGE_TABLE}")).scalar() or 0
        pages = {}
        for row in conn.execute(text(_PAGE_SQL)):
            page = _to_page(row)
            if page:
                pages[page.page_id] = page
        self._pages, self._ordered, self._seq = pages, None, int(seq)
        self._generation += 1
        self._changed = {}
        # Keep the log small; a cache elsewhere that is behind the pruned rows reloads fully.
        conn.execute(text(f"DELETE FROM {CHANGE_TABLE} WHERE seq < :s"), {"s": int(seq) - KEEP_CHANGES})

    def _apply_changes(self, conn) -> None:
        rows = conn.execute(
            text(f"SELECT seq, page_id FROM {CHANGE_TABLE} WHERE seq > :s ORDER BY seq"), {"s": self._seq}
        ).all()
        if not rows:
            return
        if rows[0][0] > self._seq + 1:
            oldest = conn.execute(text(f"SELECT MIN(seq) FROM {CHANGE_TABLE}")).scalar()
            if oldest is not None and oldest > self._seq + 1:
                self._full_load(conn)  # some change rows were pruned before this copy saw them
                return
        ids = list(dict.fromkeys(str(pid) for _seq, pid in rows))
        fresh: Dict[str, CachedPage] = {}
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            marks = ", ".join(f":i{n}" for n in range(len(chunk)))
            for row in conn.execute(text(f"{_PAGE_SQL} WHERE p.id IN ({marks})"),
                                    {f"i{n}": v for n, v in enumerate(chunk)}):
                page = _to_page(row)
                if page:
                    fresh[page.page_id] = page
        for seq, pid in rows:
            self._changed[str(pid)] = int(seq)
        for pid in ids:
            if pid in fresh:
                self._pages[pid] = fresh[pid]
            else:
                self._pages.pop(pid, None)
        self._ordered = None
        self._seq = int(rows[-1][0])

    def sync(self) -> None:
        """Bring the copy up to date (blocking; run it off the event loop)."""
        with self._lock:
            with sync_engine.begin() as conn:
                if self._seq < 0:
                    self._full_load(conn)
                    logger.info(f"Search text cache loaded: {len(self._pages)} pages")
                else:
                    self._apply_changes(conn)

    def stamp(self) -> Tuple[int, int]:
        """Where the copy stands now: (full-load generation, last change applied)."""
        with self._lock:
            return self._generation, self._seq

    def unchanged_since(self, stamp: Tuple[int, int], page_ids: List[str], user_id: Optional[str]) -> bool:
        """True when none of these pages changed after `stamp` and all are still current and visible."""
        uid = _norm(user_id)
        with self._lock:
            if stamp[0] != self._generation:
                return False
            for pid in page_ids:
                page = self._pages.get(str(pid))
                if page is None or page.superseded or self._changed.get(str(pid), 0) > stamp[1]:
                    return False
                if page.owner_user_id is not None and page.owner_user_id != uid:
                    return False
        return True

    def owns_private_pages(self, user_id: Optional[str]) -> bool:
        uid = _norm(user_id)
        if uid is None:
            return False
        with self._lock:
            return any(p.owner_user_id == uid for p in self._pages.values())

    # ------------------------------------------------------------------ lookup
    def score(
        self,
        keywords: List[str],
        user_id: Optional[str],
        document_id: Optional[str],
        institution_id: Optional[str],
    ) -> List[Tuple[str, int]]:
        """(page id, keyword hits) for visible current pages, best first, ties in page-number order."""
        with self._lock:
            if self._ordered is None:
                self._ordered = sorted(self._pages.values(), key=lambda p: p.page_number)
            ordered = self._ordered
        uid, did, iid = _norm(user_id), _norm(document_id), _norm(institution_id)
        kws = keywords[:20]
        out: List[Tuple[str, int]] = []
        for p in ordered:
            if p.superseded or (p.owner_user_id is not None and p.owner_user_id != uid):
                continue
            if did is not None and p.doc_id != did:
                continue
            if iid is not None and p.institution_id != iid:
                continue
            body = p.text
            hits = 0
            for kw in kws:
                if kw in body:
                    hits += 1
            if hits or did is not None:
                out.append((p.page_id, hits))
        out.sort(key=lambda x: -x[1])
        return out


page_cache = PageTextCache()


def enabled() -> bool:
    return sync_engine.dialect.name == "sqlite"
