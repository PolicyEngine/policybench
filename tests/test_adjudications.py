"""Developer adjudications resolve non-final judge verdicts auditably."""

import json
from pathlib import Path

import pandas as pd
import pytest

from policybench.adjudications import (
    AdjudicationError,
    apply_adjudications,
    load_adjudications,
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
    path.write_text(json.dumps({"adjudications": [_entry(), _entry()]}))
    with pytest.raises(AdjudicationError, match="duplicate"):
        load_adjudications(path)
    path.write_text(json.dumps({"adjudications": [_entry(reasoning="")]}))
    with pytest.raises(AdjudicationError, match="missing"):
        load_adjudications(path)


def test_committed_record_is_applied_to_the_frozen_annotations():
    entries = load_adjudications(ANNOTATIONS / "us_adjudications.json")
    assert len(entries) == 1
    entry = entries[0]
    assert (entry["scenario_id"], entry["variable"]) == ("scenario_064", "ssi")
    assert entry["judge_failure_source"] == "prompt_ambiguity"
    assert entry["adjudicated_failure_source"] == "llm_error"
    rows = pd.read_csv(ANNOTATIONS / "us_audit_row_annotations.csv")
    cases = pd.read_csv(ANNOTATIONS / "us_case_notes.csv")
    verify_adjudications_applied(rows, cases, entries)
    assert "prompt_ambiguity" not in set(rows["failure_source"])
    manifest = json.loads((ROOT / "paper/snapshot/20260501/manifest.json").read_text())
    block = manifest["audit_annotation_artifacts"]["developer_adjudications"]
    assert block["cases"] == 1
    assert block["by_judge_verdict"] == {"prompt_ambiguity": 1}
    assert manifest["audit_annotation_artifacts"]["files"]["us_adjudications.json"]


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
