"""The cache, the split guard and a whole run with the app's mock provider on two made-up circulars."""
import argparse
import asyncio
import json
import sys

import pytest

import common
import conftest
import provider_cache
import run_candidate as rc
import score as S
from backend.app.modules.analysis.providers.mock import MockAIProvider


class CountingMock(MockAIProvider):
    calls = 0

    async def generate_structured_json(self, *a, **k):
        CountingMock.calls += 1
        return await super().generate_structured_json(*a, **k)


@pytest.fixture(autouse=True)
def fake_world(monkeypatch):
    conftest.write_fake_inputs()
    CountingMock.calls = 0
    monkeypatch.setattr(provider_cache.CachingProvider, "_make_real", lambda self: [CountingMock()])
    yield


def mock_candidate(name="mock_test"):
    return common.Candidate(name=name, provider="mock", model="mock-regulatory-v1", prompt="app", method="whole_document",
                            paid=False, settings={}, raw={})


def rows():
    return {r.row: r for r in common.load_rows("dev")}


def run(row, cand, mode="run", force=False):
    return asyncio.run(rc.run_row(rows()[row], cand, mode, force))


def test_second_run_makes_no_provider_call():
    cand = mock_candidate("cache_check")
    first = run(9001, cand)
    assert first["status"] == "OK"
    assert first["calls_made"] == 1 and CountingMock.calls == 1 and first["cache_hit"] is False
    second = run(9001, cand)
    assert second["calls_made"] == 0 and CountingMock.calls == 1 and second["cache_hit"] is True
    assert [c["kind"] for c in second["claims"]] == [c["kind"] for c in first["claims"]]
    forced = run(9001, cand, force=True)
    assert forced["calls_made"] == 1 and CountingMock.calls == 2


def test_rescore_only_never_calls_and_reports_missing_answers():
    cand = mock_candidate("rescore_check")
    missing = run(9002, cand, mode="cache_only")
    assert missing["status"] == rc.STATUS_NOT_CACHED and CountingMock.calls == 0
    run(9002, cand)
    again = run(9002, cand, mode="cache_only")
    assert again["status"] == "OK" and again["cache_hit"] is True and CountingMock.calls == 1


def test_circular_with_missing_pages_is_not_ready():
    (common.inputs_dir() / "9002_0_p1.json").rename(common.inputs_dir() / "hold.json")
    try:
        res = run(9002, mock_candidate("not_ready_check"))
        assert res["status"] == rc.STATUS_NOT_READY and CountingMock.calls == 0
    finally:
        (common.inputs_dir() / "hold.json").rename(common.inputs_dir() / "9002_0_p1.json")


def test_changed_prompt_is_a_new_cache_entry(tmp_path):
    cand = mock_candidate("prompt_check")
    run(9001, cand)
    f = tmp_path / "variant.txt"
    f.write_text("=== SYSTEM ===\nBe careful. Entities: {entity_names}\n=== USER ===\nPages:\n{document_pages_text}\nAnswer in JSON.", encoding="utf-8")
    variant_cand = common.Candidate(name="prompt_check", provider="mock", model="mock-regulatory-v1", prompt=str(f),
                                    method="whole_document", paid=False, settings={}, raw={})
    variant = rc.load_prompt(variant_cand)
    res = asyncio.run(rc.run_row(rows()[9001], variant_cand, "run", False, variant=variant))
    assert res["cache_hit"] is False and CountingMock.calls == 2
    # and the app's own prompt is back afterwards
    from backend.app.modules.analysis import pipeline
    assert "Senior Regulatory Intelligence Engine" in pipeline.SYSTEM_REGULATORY_PROMPT


def test_reading_checks_do_not_block_image_read_pages():
    # A page read from its image would normally wait for a second reading and be hidden until it has one.
    rec_path = common.inputs_dir() / "9002_0_p1.json"
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    rec.update(method="GEMINI_VISION", quality_status="SUCCESS_VISION", model="reader")
    rec_path.write_text(json.dumps(rec), encoding="utf-8")
    try:
        res = run(9002, mock_candidate("reading_off_check"))
        assert res["status"] == "OK"
        assert res["claim_counts"]["checking"] == 0
        assert not any(c["name"] == "QUOTE_READING" for cl in res["claims"] for c in cl["checks"])
    finally:
        conftest.write_fake_inputs()


def test_test_split_needs_final(capsys, monkeypatch):
    with pytest.raises(common.ScorerError):
        common.require_split("test", False)
    common.require_split("test", True)
    monkeypatch.setattr(sys, "argv", ["run_candidate.py", "--candidate", "mock_test", "--split", "test"])
    assert rc.main() == 2
    assert "frozen" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["score.py", "--candidate", "mock_test", "--split", "test"])
    assert S.main() == 2
    assert not common.TEST_RUNS_LOG.exists() or "mock_test" not in common.TEST_RUNS_LOG.read_text(encoding="utf-8")


def test_whole_run_on_two_rows_gives_a_score(tmp_path, capsys, monkeypatch):
    cand_file = tmp_path / "mock_e2e.json"
    cand_file.write_text(json.dumps({"name": "mock_e2e", "provider": "mock", "model": "mock-regulatory-v1", "prompt": "app",
                                     "method": "whole_document", "paid": False}), encoding="utf-8")
    args = argparse.Namespace(candidate=str(cand_file), split="dev", rows="9001,9002", force=False, rescore_only=False,
                              final=False, batch=False, submit=False, collect=None, yes_spend=False)
    assert asyncio.run(rc.run_all(args)) == 0
    assert (common.runs_dir("mock_e2e") / "9001.json").exists() and (common.runs_dir("mock_e2e") / "9002.json").exists()
    # A made-up key for the made-up circular 9001 only (never a real answer key).
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "9001.json").write_text(json.dumps({
        "row": 9001, "metadata": {"issue_date": "2024-11-27"},
        "effective": {"basis": "not_stated", "date": None, "quote": None, "page_id": None},
        "applies_to": [{"entity": "all_scheduled_banks", "quote": "All scheduled commercial banks", "page_id": "9001_0_p1"}],
        "exempt": [],
        "obligations": [{"id": "o1", "page_id": "9001_0_p1", "type": "report", "subject": "all_scheduled_banks",
                         "quote": "All banks must submit an initial readiness report to BRPD within 31 December 2024.",
                         "deadline": "2024-12-31"}],
        "relationships": [], "key_changes": [], "summary_points": [], "enclosures": [], "page_notes": [],
    }), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["score.py", "--candidate", "mock_e2e", "--split", "dev", "--keys-dir", str(keys),
                                      "--json", str(tmp_path / "out.json")])
    assert S.main() == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1].startswith("SCORE ")
    float(out[-1].split()[1])
    assert (tmp_path / "out.json").exists()
    assert "1 circulars scored" in "\n".join(out)
