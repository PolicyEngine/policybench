"""The analyze CLI keeps excluded outputs inspectable in its dashboard export."""

import hashlib
import json
from pathlib import Path

import pandas as pd

from policybench.cli import main

BUNDLE = {
    "model_package": "policyengine-us",
    "model_version": "1.755.4",
    "data_package": "populace-data",
    "data_version": "0.1.0",
    "default_dataset": "populace_us_2024",
    "default_dataset_uri": "hf://policyengine/populace-us/populace_us_2024.h5@build",
    "bundle_id": "us-4.16.1",
}

EXCLUSION = {
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


def _write_inputs(root: Path) -> None:
    reference = pd.DataFrame(
        [
            ("scenario_001", "ssi", 0.0),
            ("scenario_001", "snap", 1200.0),
            ("scenario_002", "ssi", 500.0),
        ],
        columns=["scenario_id", "variable", "value"],
    )
    ground_truth = root / "reference_outputs.csv"
    reference.to_csv(ground_truth, index=False)
    (root / "reference_outputs.csv.meta.json").write_text(
        json.dumps(
            {
                "country": "us",
                "reference_csv_sha256": hashlib.sha256(
                    ground_truth.read_bytes()
                ).hexdigest(),
                "row_count": len(reference),
                "policyengine_bundles": {"us": BUNDLE},
            }
        )
    )
    (root / "reference_exclusions.json").write_text(
        json.dumps({"exclusions": [EXCLUSION]})
    )
    pd.DataFrame(
        [
            # Model a matches the frozen SSI reference; model b takes the
            # alternative reading. Both are right on everything scored.
            ("a", "scenario_001", "ssi", 0.0),
            ("a", "scenario_001", "snap", 1200.0),
            ("a", "scenario_002", "ssi", 500.0),
            ("b", "scenario_001", "ssi", 11928.0),
            ("b", "scenario_001", "snap", 1200.0),
            ("b", "scenario_002", "ssi", 500.0),
        ],
        columns=["model", "scenario_id", "variable", "prediction"],
    ).to_csv(root / "predictions.csv", index=False)
    pd.DataFrame(
        {
            "scenario_id": ["scenario_001", "scenario_002"],
            "country": ["us", "us"],
            "state": ["WI", "CA"],
            "filing_status": ["SINGLE", "SINGLE"],
            "num_adults": [1, 1],
            "num_children": [0, 0],
            "total_income": [10000.0, 20000.0],
        }
    ).to_csv(root / "scenarios.csv", index=False)


def test_analyze_export_keeps_excluded_rows_and_the_exclusion_record(
    tmp_path, monkeypatch, capsys
):
    _write_inputs(tmp_path)
    dashboard = tmp_path / "data.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "policybench",
            "analyze",
            "-g",
            str(tmp_path / "reference_outputs.csv"),
            "-p",
            str(tmp_path / "predictions.csv"),
            "-s",
            str(tmp_path / "scenarios.csv"),
            "-o",
            str(tmp_path / "analysis"),
            "--app-data-output",
            str(dashboard),
        ],
    )

    main()

    assert "reference exclusions: 1 outputs removed from scoring" in (
        capsys.readouterr().out
    )
    payload = json.loads(dashboard.read_text(encoding="utf-8"))["countries"]["us"]
    assert [entry["variable"] for entry in payload["referenceExclusions"]] == ["ssi"]
    assert payload["referenceExclusions"][0]["scenarioId"] == "scenario_001"
    rows = payload["scenarioPredictions"]["scenario_001"]["ssi"]
    assert rows["a"]["scored"] is False and rows["b"]["scored"] is False
    assert rows["b"]["prediction"] == 11928.0
    assert rows["b"]["excludedInput"] == "meets_ssi_disability_criteria"
    assert payload["scenarioPredictions"]["scenario_001"]["snap"]["a"]["scored"] is True
    stats = {row["model"]: row for row in payload["modelStats"]}
    assert stats["a"]["n"] == stats["b"]["n"] == 2
    assert stats["a"]["exact"] == stats["b"]["exact"] == 100.0
    # Every model-output row survives the export, excluded ones included.
    row_count = sum(
        len(models)
        for variables in payload["scenarioPredictions"].values()
        for models in variables.values()
    )
    assert row_count == 6
