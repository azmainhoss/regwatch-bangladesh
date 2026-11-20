"""Matching and every metric, on two small hand-made keys and predictions (made up for these tests)."""
from datetime import date

import pytest

import score as S

Q1 = "Banks shall submit the monthly return to Bangladesh Bank and shall keep a copy of it for five years."
Q3 = "No bank shall open a branch without prior approval."
QX = "Banks must display the notice board in every branch lobby."
QE = "Enclosed form: list of branches to be filled in by each bank."
QIMM = "This will take effect immediately."
P1, P2 = "9001_0_p1", "9001_0_p2"


def claim(kind, page, text, shown=True, fields=None, checks=None):
    return {
        "kind": kind, "fields": fields or {}, "shown": shown, "check_status": "PASSED" if shown else "NOT_SHOWN",
        "quote": text, "fragments": [{"page_id": page, "text": text, "sentence_ids": []}], "evidence_pages": [page],
        "checks": checks if checks is not None else [{"name": "HAS_EVIDENCE", "result": "PASS"}],
    }


def ob(page, text, typ="MANDATORY", who="SCHEDULED_BANK", deadline=None, freq=None, shown=True, checks=None):
    return claim("OBLIGATION", page, text, shown, {"obligation_type": typ, "who": who, "deadline": deadline, "frequency": freq}, checks)


def key_a():
    return {
        "row": 9001, "metadata": {"issue_date": "2018-10-09"},
        "effective": {"basis": "immediate", "date": None, "quote": QIMM, "page_id": P1},
        "applies_to": [{"entity": "all_scheduled_banks", "quote": "All scheduled banks", "page_id": P1}],
        "exempt": [],
        "obligations": [
            {"id": "o1", "page_id": P1, "quote": Q1, "type": "report", "subject": "all_scheduled_banks", "deadline": "monthly"},
            {"id": "o2", "page_id": P1, "quote": Q1, "type": "keep_records", "subject": "all_scheduled_banks", "deadline": None},
            {"id": "o3", "page_id": P1, "quote": Q3, "type": "must_not", "subject": "all_scheduled_banks", "deadline": None},
        ],
        "relationships": [{"type": "references", "target_reference": "BRPD Circular No. 14", "target_date": "2012-09-23",
                           "quote": "In reference to BRPD Circular No. 14", "page_id": P1}],
        "key_changes": [], "summary_points": [{"text": "No branch without approval", "quote": Q3, "page_id": P1}],
        "enclosures": [{"what": "form", "page_ids": [P2]}], "page_notes": [],
    }


def run_a():
    return {"status": "OK", "calls_made": 1, "tokens": {"total": 100}, "claims": [
        ob(P1, Q1, "REPORTING", freq="MONTHLY"),
        ob(P1, Q1, "RECORD_RETENTION"),
        ob(P1, Q3, "PROHIBITION", shown=False,
           checks=[{"name": "DUTY_WORDING", "result": "FAIL"}, {"name": "HAS_EVIDENCE", "result": "PASS"}]),
        ob(P1, QX, "MANDATORY"),
        ob(P2, QE, "MANDATORY"),
        claim("LINK", P1, "In reference to BRPD Circular No. 14", True,
              {"claimed_type": "AMENDS", "target_hint": "BRPD Circular No. 14 dated 23 September 2012"}),
        claim("DATE", P1, QIMM, True, {"date_kind": "EFFECTIVE", "date": "2018-10-09"}),
        claim("APPLIES_TO", P1, "All scheduled banks", True, {"entity": "SCHEDULED_BANK"}),
        claim("SUMMARY_POINT", P1, Q3, True, {"text": "No branch without approval"}),
    ]}


def key_b():
    return {
        "row": 9002, "metadata": {"issue_date": "2024-12-01"},
        "effective": {"basis": "not_stated", "date": None, "quote": None, "page_id": None},
        "applies_to": [{"entity": "nbfis", "quote": "All NBFIs", "page_id": "9002_0_p1"}], "exempt": [],
        "obligations": [{"id": "o1", "page_id": "9002_0_p1", "quote": Q3, "type": "must_not", "subject": "nbfis", "deadline": None}],
        "relationships": [], "key_changes": [], "summary_points": [], "enclosures": [], "page_notes": [],
    }


def run_b():
    return {"status": "OK", "claims": [
        ob("9002_0_p1", Q3, "PROHIBITION", who="NBFI"),
        claim("DATE", "9002_0_p1", "Effective from the issue date", True, {"date_kind": "EFFECTIVE", "date": "2024-12-01"}),
    ]}


WINDOW_A = {P1, P2}
ISSUE_A = date(2018, 10, 9)


def test_two_duty_sentence_matches_both_key_items():
    r = S.score_row(key_a(), run_a(), WINDOW_A, ISSUE_A)
    n = r["counts"]
    assert n["ob_fully_right_shown"] == 2  # the report and the keep_records duty on one sentence
    assert n["key_obligations"] == 3


def test_hidden_right_claim_is_a_false_alarm_and_shown_wrong_is_a_leak():
    r = S.score_row(key_a(), run_a(), WINDOW_A, ISSUE_A)
    n = r["counts"]
    assert n["right_hidden"] == 1  # the Q3 obligation: right, but hidden
    # wrong and shown: the QX obligation, the enclosure obligation, the AMENDS link (key says references)
    assert n["wrong_shown"] == 3
    stat = S.check_stats([r])["DUTY_WORDING"]
    assert stat["failed_right"] == 1 and stat["failed_wrong"] == 0


def test_enclosure_page_obligation_is_wrong():
    r = S.score_row(key_a(), run_a(), WINDOW_A, ISSUE_A)
    assert r["counts"]["obligations_on_enclosures"] == 1
    assert r["counts"]["ob_pred_shown"] == 4  # 2 right, 2 wrong


def test_obligations_outside_the_window_are_not_scored():
    r = S.score_row(key_a(), run_a(), {P1}, ISSUE_A)
    assert r["counts"]["obligations_outside_window"] == 1
    assert r["counts"]["ob_pred_shown"] == 3


def test_false_change_claim_when_key_only_references():
    r = S.score_row(key_a(), run_a(), WINDOW_A, ISSUE_A)
    assert r["counts"]["false_change_claims"] == 1
    assert r["counts"]["links_matched_shown"] == 1
    assert r["counts"]["links_type_right_shown"] == 0
    m = S.metrics(r["counts"], int(r["effective"]["right"]), 1)
    assert m["links"]["score"] == 0.0  # recall * type accuracy minus the false change claim, floored at zero


def test_immediate_effect_needs_issue_date_and_an_immediate_phrase():
    r = S.score_row(key_a(), run_a(), WINDOW_A, ISSUE_A)
    assert r["effective"]["right"] is True
    bad = run_a()
    bad["claims"][6] = claim("DATE", P1, "The new rule is described below.", True, {"date_kind": "EFFECTIVE", "date": "2018-10-09"})
    assert S.score_row(key_a(), bad, WINDOW_A, ISSUE_A)["effective"]["right"] is False


def test_issue_date_given_as_effective_when_key_says_not_stated():
    r = S.score_row(key_b(), run_b(), None, date(2024, 12, 1))
    assert r["effective"]["right"] is False
    assert r["effective"]["issue_date_as_effective"] is True


def test_not_stated_is_right_when_nothing_is_predicted():
    run = {"status": "OK", "claims": [ob("9002_0_p1", Q3, "PROHIBITION", who="NBFI")]}
    r = S.score_row(key_b(), run, None, date(2024, 12, 1))
    assert r["effective"]["right"] is True


def test_empty_answer_row_scores_zero_everywhere():
    run = {"status": "EMPTY_ANSWER", "claims": []}
    r = S.score_row(key_a(), run, WINDOW_A, ISSUE_A)
    assert r["failed"] is True
    assert r["counts"]["ob_pred_shown"] == 0 and r["counts"]["key_obligations"] == 3
    assert r["effective"]["right"] is False
    zero = {"status": "OK", "claims": []}  # zero claims counts as a failure too
    assert S.score_row(key_a(), zero, WINDOW_A)["failed"] is True


def test_headline_two_rows_and_weights():
    rows = [
        {"row": 9001, "key": key_a(), "run": run_a(), "window": WINDOW_A, "issue": ISSUE_A},
        {"row": 9002, "key": key_b(), "run": run_b(), "window": None, "issue": date(2024, 12, 1)},
    ]
    res = S.score_all(rows)
    t = res["total"]
    assert t["rows"]["scored"] == 2
    assert t["obligation"]["fully_right_shown"] == 3  # 2 + 1
    assert t["obligation"]["predicted_shown"] == 5  # 4 + 1
    assert t["obligation"]["recall"] == pytest.approx(3 / 4)
    assert t["effective"]["right"] == 1 and t["effective"]["issue_date_as_effective"] == 1
    assert t["leak_rate"] == pytest.approx(t["claims"]["wrong_shown"] / t["claims"]["shown_scored"])
    expected = 100 * (
        S.WEIGHTS["obligation_f1"] * t["obligation"]["f1"] + S.WEIGHTS["links"] * t["links"]["score"]
        + S.WEIGHTS["effective"] * t["effective"]["accuracy"] + S.WEIGHTS["applies_to"] * t["applies_to"]["f1"]
        + S.WEIGHTS["summary_changes"] * t["summary_changes"]["f1"] + S.WEIGHTS["no_false_alarm"] * (1 - t["false_alarm_rate"])
    ) - S.LEAK_PENALTY * t["leak_rate"]
    assert t["score"] == pytest.approx(expected)
    assert set(res["checks"]) >= {"DUTY_WORDING", "HAS_EVIDENCE"}


def test_a_leak_costs_more_than_it_gains():
    row = {"row": 9001, "key": key_a(), "run": run_a(), "window": WINDOW_A, "issue": ISSUE_A}
    base = S.score_all([row])["total"]["score"]
    more = run_a()
    more["claims"].append(ob(P1, "Banks must pay a fee of Tk 5 on every deposit slip.", "MANDATORY"))
    worse = S.score_all([{**row, "run": more}])["total"]["score"]
    assert worse < base


def test_overlap_rule_half_of_the_shorter_quote():
    assert S.overlap("shall submit the return monthly", "Banks shall submit the return monthly to Bangladesh Bank") == 1.0
    assert S.overlap("abc def ghi jkl", "zzz yyy xxx www") < 0.5


def test_deadline_rules():
    def f(**k):
        return k
    assert S.deadline_right(f(deadline=None, frequency="ONE_TIME"), None)
    assert not S.deadline_right(f(deadline=None, frequency="MONTHLY"), None)
    assert S.deadline_right(f(deadline="2025-01-31"), "2025-01-31")
    assert not S.deadline_right(f(deadline="2025-02-01"), "2025-01-31")
    assert S.deadline_right(f(deadline="within 15 days of each quarter end"), "within 15 days of each quarter-end")
    assert S.deadline_right(f(deadline=None, frequency="QUARTERLY"), "quarterly")
    assert not S.deadline_right(f(deadline=None, frequency="MONTHLY"), "quarterly")


def test_entity_mapping_and_scheduled_bank_subtypes():
    assert S.map_entity("SCHEDULED_BANK") == "all_scheduled_banks"
    assert S.entities_equal(S.map_entity("something odd"), "other:residents")
    run = {"status": "OK", "claims": [claim("APPLIES_TO", P1, "All banks", True, {"entity": "PRIVATE_COMMERCIAL_BANK"})]}
    r = S.score_row(key_a(), run, WINDOW_A)
    assert r["counts"]["applies_pred_right"] == 1 and r["counts"]["applies_key_found"] == 1


def test_link_on_enclosure_page_is_wrong():
    run = {"status": "OK", "claims": [claim("LINK", P2, "mentions BRPD Circular No. 14", True,
                                             {"claimed_type": "REFERENCES", "target_hint": "BRPD Circular No. 14"})]}
    r = S.score_row(key_a(), run, WINDOW_A)
    assert r["counts"]["links_matched_shown"] == 0
    assert r["counts"]["wrong_shown"] == 1
