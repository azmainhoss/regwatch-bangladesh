"""The hand-analysis export hands a circular out only when every page has usable text.

A circular with a page still waiting to be read, or with a person because reading failed or its text is
damaged, is held back (and taken off the shared queue if nobody answered it yet). It goes out by itself
once read. Circulars that went out early are listed in REDO.txt. No database or model is used: the
export's inputs are faked.
"""
import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
GARBLED = "~8. \\5W'R~~~~;qJf\\bc~C<f'~~~'ft9J,Cm\\5W'R~c<Wr9i~~ ~Q. \\5W'R~~~~~\\5W'R~~q~~"


@pytest.fixture
def ma(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("manual_analysis", ROOT / "backend" / "scripts" / "manual_analysis.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    work = tmp_path / "work"
    monkeypatch.setattr(module, "WORK", work)
    monkeypatch.setattr(module, "INBOX", work / "inbox")
    monkeypatch.setattr(module, "ANSWERS", work / "answers")
    monkeypatch.setattr(module, "DONE", work / "done")
    monkeypatch.setattr(module, "REDO", work / "REDO.txt")

    def instructions():
        work.mkdir(parents=True, exist_ok=True)
        (work / "INSTRUCTIONS.md").write_text("rules", encoding="utf-8")

    monkeypatch.setattr(module, "write_instructions", instructions)
    monkeypatch.setattr(module, "_write_check_py", lambda repo: None)

    async def pages(version_id):
        return [{"page_number": 1, "raw_text": "Banks must report monthly.", "cleaned_text": "Banks must report monthly.",
                 "line_boxes": None}]

    monkeypatch.setattr(module, "_load_pages", pages)
    return module


def _row(name, waiting=0, stuck=0, analyses=0):
    return {"id": uuid.uuid4().hex, "version_id": uuid.uuid4().hex, "title": name, "reference": None,
            "date": "2026-01-01", "pages": 2, "chars": 100, "waiting": waiting, "analyses": analyses,
            "stuck": stuck, "unread": waiting + stuck}


def _export(ma, repo, rows, monkeypatch):
    monkeypatch.setattr(ma, "targets", lambda: rows)

    class Args:
        pass

    args = Args()
    args.repo, args.max_chars = str(repo), 60000
    asyncio.run(ma.cmd_export(args))


def test_pages_with_a_person_count_as_unread_only_without_usable_text(ma):
    assert ma.page_text_unusable("")
    assert ma.page_text_unusable(GARBLED)
    assert not ma.page_text_unusable("This page is intentionally left blank")
    assert not ma.page_text_unusable("Banks must file the return monthly.")


def test_export_holds_back_circulars_with_unread_pages(ma, tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    ready, waiting, stuck = _row("ready"), _row("waiting", waiting=1), _row("stuck", stuck=1)
    _export(ma, repo, [ready, waiting, stuck], monkeypatch)
    inbox = {p.stem for p in (repo / "inbox").glob("*.txt")}
    assert inbox == {ma._file_key(ready["id"])}
    assert (repo / "QUEUE.txt").read_text(encoding="utf-8") == f"inbox/{ma._file_key(ready['id'])}.txt\n"
    assert "held back 2 with unread pages" in capsys.readouterr().out


def test_an_unanswered_circular_handed_out_too_early_leaves_the_queue_and_comes_back_once_read(ma, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    row = _row("early", stuck=1)
    key = ma._file_key(row["id"])
    (repo / "inbox_long").mkdir(parents=True)
    (repo / "inbox_long" / f"{key}.txt").write_text("old text with a blank page", encoding="utf-8")
    ma.write_redo({key: "handed out while some pages were unread"})

    _export(ma, repo, [row], monkeypatch)
    assert not (repo / "inbox_long" / f"{key}.txt").exists()
    assert (repo / "QUEUE.txt").read_text(encoding="utf-8") == ""

    row.update(stuck=0, unread=0)  # its pages are read now
    _export(ma, repo, [row], monkeypatch)
    assert "Banks must report monthly." in (repo / "inbox" / f"{key}.txt").read_text(encoding="utf-8")
    assert ma.read_redo() == {}  # handed out again with every page read


def test_an_answered_circular_is_never_pulled_and_its_redo_waits_for_a_person(ma, tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    stuck, read = _row("answered, still stuck", stuck=1), _row("answered, now read", analyses=1)
    for row in (stuck, read):
        key = ma._file_key(row["id"])
        for folder in ("inbox", "answers"):
            (repo / folder).mkdir(parents=True, exist_ok=True)
        (repo / "inbox" / f"{key}.txt").write_text("text", encoding="utf-8")
        (repo / "answers" / f"{key}.json").write_text("{}", encoding="utf-8")
    ma.write_redo({ma._file_key(stuck["id"]): "r", ma._file_key(read["id"]): "r"})

    _export(ma, repo, [stuck, read], monkeypatch)
    # Answers and their inbox files stay; nothing is analysed again on its own.
    assert len(list((repo / "answers").glob("*.json"))) == 2
    assert (repo / "inbox" / f"{ma._file_key(stuck['id'])}.txt").exists()
    out = capsys.readouterr().out
    assert "1 circular(s) in REDO.txt are now fully read but already analysed" in out
    assert ma._file_key(read["id"]) in out
    assert len(ma.read_redo()) == 2


def test_mark_redo_adds_circulars(ma):
    class Args:
        docs = [uuid.uuid4().hex, str(uuid.uuid4())]
        reason = "went out with a damaged page"

    ma.cmd_mark_redo(Args())
    items = ma.read_redo()
    assert len(items) == 2 and set(items.values()) == {"went out with a damaged page"}
    assert all(str(uuid.UUID(k)) == k for k in items)


def test_an_approved_redo_waits_for_its_pages_then_goes_out_again_once(ma, tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    row = _row("approved redo", stuck=1, analyses=1)
    key = ma._file_key(row["id"])
    for folder in ("inbox", "answers"):
        (repo / folder).mkdir(parents=True, exist_ok=True)
    (repo / "inbox" / f"{key}.txt").write_text("old text with a damaged page", encoding="utf-8")
    (repo / "answers" / f"{key}.json").write_text("{}", encoding="utf-8")
    (ma.DONE).mkdir(parents=True)
    (ma.DONE / f"{key}.json").write_text("{}", encoding="utf-8")
    ma.write_redo({key: "approved: analysed while a page was unread"})

    _export(ma, repo, [row], monkeypatch)  # still unread: nothing moves
    assert (repo / "answers" / f"{key}.json").exists()
    assert (repo / "inbox" / f"{key}.txt").read_text(encoding="utf-8") == "old text with a damaged page"

    row.update(stuck=0, unread=0)  # read now: new text out, old answer out, old loaded answer set aside
    _export(ma, repo, [row], monkeypatch)
    assert f"Redo: {key} |" in capsys.readouterr().out
    assert "Banks must report monthly." in (repo / "inbox" / f"{key}.txt").read_text(encoding="utf-8")
    assert not (repo / "answers" / f"{key}.json").exists()
    assert (ma.DONE / "replaced" / f"{key}.json").exists() and not (ma.DONE / f"{key}.json").exists()
    assert (repo / "QUEUE.txt").read_text(encoding="utf-8") == f"inbox/{key}.txt\n"

    _export(ma, repo, [row], monkeypatch)  # waiting for the new answer: stays on the queue
    assert (repo / "inbox" / f"{key}.txt").exists()
    (repo / "answers" / f"{key}.json").write_text('{"new": 1}', encoding="utf-8")
    _export(ma, repo, [row], monkeypatch)  # the new answer is never removed again
    assert (repo / "answers" / f"{key}.json").read_text(encoding="utf-8") == '{"new": 1}'
    assert "Redo:" not in capsys.readouterr().out


def test_mark_redo_approved_marks_the_reason(ma):
    class Args:
        docs = [str(uuid.uuid4())]
        reason = "analysed while a page was unread"
        approved = True

    ma.cmd_mark_redo(Args())
    assert ma.redo_approved(ma.read_redo()) == set(Args.docs)


def test_an_approved_redo_analysed_only_in_the_app_goes_out_once_read(ma, tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    row = _row("analysed in the app", analyses=1)
    key = ma._file_key(row["id"])
    ma.write_redo({key: "approved: analysed while pages were damaged"})
    _export(ma, repo, [row], monkeypatch)
    assert f"Redo: {key} |" in capsys.readouterr().out
    assert (repo / "QUEUE.txt").read_text(encoding="utf-8") == f"inbox/{key}.txt\n"
    _export(ma, repo, [row], monkeypatch)
    assert "Redo:" not in capsys.readouterr().out and (repo / "inbox" / f"{key}.txt").exists()
