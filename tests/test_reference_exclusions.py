"""Outputs whose reference depends on an unlisted input are scored for no model."""

import json
from pathlib import Path

import pandas as pd
import pytest

from policybench.analysis import analyze_no_tools, build_dashboard_payload
from policybench.reference_exclusions import (
    FILENAME,
    ReferenceExclusionError,
    exclusion_keys,
    load_reference_exclusions,
    scored_reference_for,
    split_reference,
    verify_exclusions_against_reference,
)

ROOT = Path(__file__).resolve().parents[1]
RUN_LABEL = "us_full_run_20260612_policyengine_4_16_1_populace"
RUN_DIR = ROOT / "paper" / "snapshot" / "20260501" / "runs" / RUN_LABEL


def _entry(**overrides: object) -> dict:
    entry = {
        "scenario_id": "scenario_001",
        "variable": "ssi",
        "reason_code": "reference_depends_on_unlisted_input",
        "unlisted_input": "meets_ssi_disability_criteria",
        "alternative_reading": "The 'is disabled' fact is read as the SSI criterion.",
        "frozen_value": 0.0,
        "alternative_value": 11928.0,
        "engine_version": "policyengine-us 1.755.4",
        "decided_on": "2026-09-05",
        "decided_by": "developer",
    }
    entry.update(overrides)
    return entry


def _reference() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("scenario_001", "ssi", 0.0, None),
            ("scenario_001", "snap", 1200.0, None),
            ("scenario_002", "ssi", 500.0, None),
        ],
        columns=["scenario_id", "variable", "value", "impact_weight"],
    )


def test_split_removes_only_excluded_outputs_and_verifies_frozen_values():
    scored, excluded = split_reference(_reference(), [_entry()])
    assert list(zip(scored["scenario_id"], scored["variable"])) == [
        ("scenario_001", "snap"),
        ("scenario_002", "ssi"),
    ]
    assert list(zip(excluded["scenario_id"], excluded["variable"])) == [
        ("scenario_001", "ssi")
    ]
    with pytest.raises(ReferenceExclusionError, match="does not match"):
        verify_exclusions_against_reference(_reference(), [_entry(frozen_value=7.0)])
    with pytest.raises(ReferenceExclusionError, match="not a reference"):
        verify_exclusions_against_reference(
            _reference(), [_entry(scenario_id="scenario_999")]
        )


def test_load_validates_the_record(tmp_path: Path):
    path = tmp_path / FILENAME
    assert load_reference_exclusions(path) == []
    path.write_text(json.dumps({"exclusions": [_entry()]}))
    assert exclusion_keys(load_reference_exclusions(path)) == {("scenario_001", "ssi")}
    path.write_text(json.dumps({"exclusions": [_entry(alternative_value=0.0)]}))
    with pytest.raises(ReferenceExclusionError, match="same reference"):
        load_reference_exclusions(path)
    path.write_text(json.dumps({"exclusions": [_entry(reason_code="vibes")]}))
    with pytest.raises(ReferenceExclusionError, match="reason_code"):
        load_reference_exclusions(path)
    path.write_text(json.dumps({"exclusions": [_entry(), _entry()]}))
    with pytest.raises(ReferenceExclusionError, match="duplicate"):
        load_reference_exclusions(path)
    path.write_text(json.dumps({"exclusions": [_entry(decided_by="")]}))
    with pytest.raises(ReferenceExclusionError, match="missing"):
        load_reference_exclusions(path)


def test_scoring_ignores_excluded_outputs_symmetrically(tmp_path: Path):
    reference = _reference()
    predictions = pd.DataFrame(
        [
            # Model A matches the frozen reference on the excluded output; B does
            # not. Both are right on everything else, so both must score 100.
            ("a", "scenario_001", "ssi", 0.0),
            ("a", "scenario_001", "snap", 1200.0),
            ("a", "scenario_002", "ssi", 500.0),
            ("b", "scenario_001", "ssi", 11928.0),
            ("b", "scenario_001", "snap", 1200.0),
            ("b", "scenario_002", "ssi", 500.0),
        ],
        columns=["model", "scenario_id", "variable", "prediction"],
    )
    scenarios = pd.DataFrame(
        {
            "scenario_id": ["scenario_001", "scenario_002"],
            "country": ["us", "us"],
            "state": ["WI", "CA"],
            "filing_status": ["SINGLE", "SINGLE"],
            "num_adults": [1, 1],
            "num_children": [0, 0],
            "total_income": [10000.0, 20000.0],
        }
    )
    exclusions = [_entry()]
    scored, excluded = split_reference(reference, exclusions)
    analysis = analyze_no_tools(scored, predictions, scenarios=scenarios)
    payload = build_dashboard_payload(
        scored,
        predictions,
        analysis,
        scenarios,
        policyengine_bundles={"us": {"model_version": "test"}},
        excluded_reference=excluded,
        reference_exclusions=exclusions,
    )
    stats = {row["model"]: row for row in payload["modelStats"]}
    assert stats["a"]["exact"] == stats["b"]["exact"] == 100.0
    assert stats["a"]["n"] == stats["b"]["n"] == 2
    rows = payload["scenarioPredictions"]["scenario_001"]["ssi"]
    assert rows["a"]["scored"] is False and rows["b"]["scored"] is False
    assert rows["b"]["excludedInput"] == "meets_ssi_disability_criteria"
    assert payload["scenarioPredictions"]["scenario_001"]["snap"]["a"]["scored"] is True
    assert [e["variable"] for e in payload["referenceExclusions"]] == ["ssi"]
    # Without the record nothing changes shape and every row is scored.
    plain = build_dashboard_payload(
        reference,
        predictions,
        analyze_no_tools(reference, predictions, scenarios=scenarios),
        scenarios,
        policyengine_bundles={"us": {"model_version": "test"}},
    )
    assert plain["referenceExclusions"] == []
    assert plain["scenarioPredictions"]["scenario_001"]["ssi"]["b"]["scored"] is True
    assert plain["modelStats"][0]["n"] == 3


def test_frozen_snapshot_carries_the_exclusion_record():
    scored, exclusions = scored_reference_for(RUN_DIR / "reference_outputs.csv")
    assert len(exclusions) == 11
    inputs = {e["unlisted_input"] for e in exclusions}
    assert inputs == {
        "meets_ssi_disability_criteria",
        "months_receiving_social_security_disability",
    }
    reference = pd.read_csv(RUN_DIR / "reference_outputs.csv")
    assert len(scored) == len(reference) - 11
    verify_exclusions_against_reference(reference, exclusions)
