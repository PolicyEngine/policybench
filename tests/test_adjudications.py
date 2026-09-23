"""Developer adjudications resolve non-final judge verdicts auditably."""

import json
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from policybench.adjudications import (
    AdjudicationError,
    apply_adjudications,
    load_adjudications,
    unresolved_suspect_cases,
    verify_adjudications_applied,
)

ROOT = Path(__file__).resolve().parents[1]
RUN_LABEL = "us_full_run_20260612_policyengine_4_16_1_populace"
ANNOTATIONS = ROOT / "annotations" / RUN_LABEL


def _entry(**overrides: object) -> dict:
    entry = {
        "country": "us",
        "scenario_id": "scenario_001",
        "variable": "ssi",
        "judge_model": "claude-opus-5",
        "judge_failure_source": "prompt_ambiguity",
        "judge_failure_subtype": "age_disability",
        "adjudicated_failure_source": "llm_error",
        "adjudicated_failure_subtype": "age_disability",
        "adjudicated_on": "2026-09-05",
        "adjudicator": "developer",
        "reasoning": "The prompt fixes unlisted facts to false.",
    }
    entry.update(overrides)
    return entry


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = pd.DataFrame(
        [
            ("us", "scenario_001", "ssi", "m1", "prompt_ambiguity", "age_disability"),
            ("us", "scenario_001", "ssi", "m2", "prompt_ambiguity", "age_disability"),
            (
                "us",
                "scenario_001",
                "ssi",
                "m3",
                "parse_contract_failure",
                "missing_output",
            ),
            ("us", "scenario_002", "snap", "m1", "llm_error", "thresholds_rates"),
        ],
        columns=[
            "country",
            "scenario_id",
            "variable",
            "model",
            "failure_source",
            "failure_subtype",
        ],
    )
    rows["reference_suspect"] = False
    rows["annotation"] = "diagnosis"
    cases = pd.DataFrame(
        [
            (
                "us",
                "scenario_001",
                "ssi",
                3,
                "prompt_ambiguity",
                "age_disability",
                "note one.",
            ),
            (
                "us",
                "scenario_002",
                "snap",
                1,
                "llm_error",
                "thresholds_rates",
                "note two.",
            ),
        ],
        columns=[
            "country",
            "scenario_id",
            "variable",
            "wrong_model_count",
            "case_failure_sources",
            "case_failure_subtypes",
            "case_annotation",
        ],
    )
    return rows, cases


def test_apply_rewrites_only_the_judged_class_and_records_the_adjudication():
    rows, cases = _frames()
    out_rows, out_cases, report = apply_adjudications(rows, cases, [_entry()])

    case_rows = out_rows[out_rows["scenario_id"] == "scenario_001"]
    assert case_rows["failure_source"].tolist() == [
        "llm_error",
        "llm_error",
        "parse_contract_failure",
    ]
    assert out_rows.loc[3, "failure_source"] == "llm_error"
    note = out_cases.loc[0]
    assert note["case_failure_sources"] == "llm_error"
    assert "Developer adjudication (2026-09-05)" in note["case_annotation"]
    assert "returned prompt_ambiguity" in note["case_annotation"]
    assert out_cases.loc[1, "case_annotation"] == "note two."
    assert report == [
        {
            "case": ["us", "scenario_001", "ssi"],
            "rows_rewritten": 2,
            "from": "prompt_ambiguity",
            "to": "llm_error",
        }
    ]
    # The originals are untouched and a second application changes nothing.
    assert rows.loc[0, "failure_source"] == "prompt_ambiguity"
    again_rows, again_cases, _ = apply_adjudications(out_rows, out_cases, [_entry()])
    pd.testing.assert_frame_equal(again_rows, out_rows)
    pd.testing.assert_frame_equal(again_cases, out_cases)


def test_verify_rejects_unapplied_or_missing_cases():
    rows, cases = _frames()
    with pytest.raises(AdjudicationError, match="still carry"):
        verify_adjudications_applied(rows, cases, [_entry()])
    out_rows, out_cases, _ = apply_adjudications(rows, cases, [_entry()])
    verify_adjudications_applied(out_rows, out_cases, [_entry()])
    with pytest.raises(AdjudicationError, match="unknown case"):
        apply_adjudications(rows, cases, [_entry(scenario_id="scenario_999")])


def test_load_validates_the_record(tmp_path: Path):
    path = tmp_path / "us_adjudications.json"
    assert load_adjudications(path) == []
    path.write_text(json.dumps({"adjudications": [_entry()]}))
    assert len(load_adjudications(path)) == 1
    path.write_text(
        json.dumps(
            {"adjudications": [_entry(adjudicated_failure_source="needs_review")]}
        )
    )
    with pytest.raises(AdjudicationError, match="must be final"):
        load_adjudications(path)
    path.write_text(
        json.dumps(
            {"adjudications": [_entry(adjudicated_failure_source="prompt_ambiguity")]}
        )
    )
    with pytest.raises(AdjudicationError, match="excluded_from_scoring"):
        load_adjudications(path)
    path.write_text(
        json.dumps(
            {
                "adjudications": [
                    _entry(
                        adjudicated_failure_source="prompt_ambiguity",
                        excluded_from_scoring=True,
                    )
                ]
            }
        )
    )
    assert load_adjudications(path)[0]["excluded_from_scoring"] is True
    path.write_text(json.dumps({"adjudications": [_entry(excluded_from_scoring=True)]}))
    with pytest.raises(AdjudicationError, match="only valid with"):
        load_adjudications(path)
    path.write_text(json.dumps({"adjudications": [_entry(), _entry()]}))
    with pytest.raises(AdjudicationError, match="duplicate"):
        load_adjudications(path)
    path.write_text(json.dumps({"adjudications": [_entry(reasoning="")]}))
    with pytest.raises(AdjudicationError, match="missing"):
        load_adjudications(path)


def test_committed_record_is_applied_to_the_frozen_annotations():
    entries = load_adjudications(ANNOTATIONS / "us_adjudications.json")
    assert len(entries) == 63
    assert Counter(e["adjudicated_failure_source"] for e in entries) == Counter(
        {"reference_engine_defect": 28, "prompt_ambiguity": 24, "llm_error": 11}
    )
    # Every excluded output has its adjudication; the six llm_error entries are
    # the references a flag questioned and the adjudication affirmed or replaced
    # with a regenerated reference.
    assert sum(bool(e.get("excluded_from_scoring")) for e in entries) == 52
    keys = {(e["scenario_id"], e["variable"]) for e in entries}
    assert ("scenario_064", "ssi") in keys and (
        "scenario_074",
        "head_medicare_eligible",
    ) in keys
    opus = next(
        e
        for e in entries
        if (e["scenario_id"], e["variable"]) == ("scenario_064", "ssi")
    )
    assert opus["judge_failure_source"] == "prompt_ambiguity"
    rejudged = next(
        e
        for e in entries
        if (e["scenario_id"], e["variable"]) == ("scenario_067", "ssi")
    )
    assert rejudged["judge_model"] == "claude-opus-5-5"
    assert rejudged["reference_verdict"] == "unlisted_input"
    rows = pd.read_csv(ANNOTATIONS / "us_audit_row_annotations.csv")
    cases = pd.read_csv(ANNOTATIONS / "us_case_notes.csv")
    verify_adjudications_applied(rows, cases, entries)
    ambiguous = rows[rows["failure_source"] == "prompt_ambiguity"]
    assert set(zip(ambiguous["scenario_id"], ambiguous["variable"])) <= keys
    manifest = json.loads((ROOT / "paper/snapshot/20260501/manifest.json").read_text())
    block = manifest["audit_annotation_artifacts"]["developer_adjudications"]
    assert block["cases"] == 63
    # The judge's own class for each case (its verdict.json), not the
    # adjudicated one; the freezer refuses a record that differs from it.
    assert block["by_judge_verdict"] == {
        "llm_error": 45,
        "prompt_ambiguity": 2,
        "reference_engine_defect": 11,
        "reference_model_issue_fixed": 5,
    }
    assert block["by_judge_verdict"] == dict(
        Counter(e["judge_failure_source"] for e in entries)
    )
    assert block["judge_flagged_by_reference_verdict"] == {
        "affirmed": 5,
        "engine_defect": 19,
        "regenerated": 6,
        "unlisted_input": 8,
    }
    assert manifest["audit_annotation_artifacts"]["files"]["us_adjudications.json"]
    assert manifest["reference_exclusions"]["outputs"] == 52


def test_verify_requires_agreement_with_the_complete_record():
    rows, cases = _frames()
    out_rows, out_cases, _ = apply_adjudications(rows, cases, [_entry()])
    verify_adjudications_applied(out_rows, out_cases, [_entry()])

    # A revised subtype fails until the revision is re-applied.
    revised = _entry(adjudicated_failure_subtype="thresholds_rates")
    with pytest.raises(AdjudicationError, match="subtype other than"):
        verify_adjudications_applied(out_rows, out_cases, [revised])
    re_rows, re_cases, _ = apply_adjudications(out_rows, out_cases, [revised])
    verify_adjudications_applied(re_rows, re_cases, [revised])
    assert re_cases.loc[0, "case_annotation"].count("Developer adjudication") == 1

    # Revised reasoning replaces the sentence rather than accumulating.
    reworded = _entry(reasoning="Different reasoning.")
    with pytest.raises(AdjudicationError, match="does not carry"):
        verify_adjudications_applied(out_rows, out_cases, [reworded])
    rw_rows, rw_cases, _ = apply_adjudications(out_rows, out_cases, [reworded])
    verify_adjudications_applied(rw_rows, rw_cases, [reworded])
    note = rw_cases.loc[0, "case_annotation"]
    assert "Different reasoning." in note
    assert "The prompt fixes unlisted facts to false." not in note

    # A case note edited to disagree with its rows fails closed.
    bad_cases = out_cases.copy()
    bad_cases.loc[0, "case_failure_subtypes"] = "thresholds_rates"
    with pytest.raises(AdjudicationError, match="case note"):
        verify_adjudications_applied(out_rows, bad_cases, [_entry()])
    bad_rows = out_rows.copy()
    bad_rows.loc[1, "failure_subtype"] = "thresholds_rates"
    with pytest.raises(AdjudicationError, match="subtype other than"):
        verify_adjudications_applied(bad_rows, out_cases, [_entry()])


def _suspect_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, cases = _frames()
    rows.loc[rows["scenario_id"] == "scenario_001", "reference_suspect"] = True
    rows.loc[rows["scenario_id"] == "scenario_001", "failure_source"] = (
        "reference_model_issue_fixed"
    )
    cases["reference_suspect"] = [True, False]
    cases.loc[0, "case_failure_sources"] = "reference_model_issue_fixed"
    return rows, cases


def _verdict_entry(verdict: str, **overrides: object) -> dict:
    source = {
        "affirmed": "llm_error",
        "regenerated": "llm_error",
        "engine_defect": "reference_engine_defect",
        "unlisted_input": "prompt_ambiguity",
        "later_law": "reference_later_law",
    }[verdict]
    entry = _entry(
        judge_failure_source="reference_model_issue_fixed",
        adjudicated_failure_source=source,
        reference_verdict=verdict,
        reference_basis="42 U.S.C. 1382c(a)(3)(A)",
    )
    if verdict not in ("affirmed", "regenerated"):
        entry["excluded_from_scoring"] = True
    entry.update(overrides)
    return entry


@pytest.mark.parametrize(
    "verdict",
    ["affirmed", "regenerated", "engine_defect", "unlisted_input", "later_law"],
)
def test_reference_verdict_clears_the_suspect_flag_and_is_recorded(tmp_path, verdict):
    rows, cases = _suspect_frames()
    entry = _verdict_entry(verdict)
    path = tmp_path / "adj.json"
    path.write_text(json.dumps({"adjudications": [entry]}))
    assert load_adjudications(path)[0]["reference_verdict"] == verdict
    assert unresolved_suspect_cases(cases, [entry | {"reference_verdict": None}]) == [
        ("us", "scenario_001", "ssi")
    ]
    out_rows, out_cases, _ = apply_adjudications(rows, cases, [entry])
    assert not out_rows["reference_suspect"].any()
    assert not out_cases["reference_suspect"].any()
    assert "42 U.S.C. 1382c(a)(3)(A)" in out_cases.loc[0, "case_annotation"]
    verify_adjudications_applied(out_rows, out_cases, [entry])
    assert unresolved_suspect_cases(out_cases, [entry]) == []


def test_reference_verdict_must_match_class_and_scoring(tmp_path):
    path = tmp_path / "adj.json"
    bad = [
        (_verdict_entry("affirmed", excluded_from_scoring=True), "only valid with"),
        (
            _verdict_entry(
                "engine_defect", adjudicated_failure_source="prompt_ambiguity"
            ),
            "requires adjudicated_failure_source",
        ),
        (_verdict_entry("unlisted_input", reference_basis=""), "reference_basis"),
        (_verdict_entry("engine_defect", reference_verdict="maybe"), "unknown"),
        (
            _verdict_entry("engine_defect", reference_verdict=None),
            "requires a reference_verdict",
        ),
    ]
    for entry, message in bad:
        path.write_text(json.dumps({"adjudications": [entry]}))
        with pytest.raises(AdjudicationError, match=message):
            load_adjudications(path)


def test_verification_fails_while_a_verdict_leaves_the_flag_set():
    rows, cases = _suspect_frames()
    entry = _verdict_entry("affirmed")
    out_rows, out_cases, _ = apply_adjudications(rows, cases, [entry])
    out_rows.loc[0, "reference_suspect"] = True
    with pytest.raises(AdjudicationError, match="still carry reference_suspect"):
        verify_adjudications_applied(out_rows, out_cases, [entry])
