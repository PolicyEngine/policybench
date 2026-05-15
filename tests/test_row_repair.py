from pathlib import Path

import pandas as pd

from policybench.row_repair import (
    merge_row_repair_predictions,
    prepare_row_repair_round,
    row_repair_targets,
    run_row_repair_round,
)


def _source_predictions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "model": ["model_a", "model_a", "model_b"],
            "scenario_id": ["s1", "s1", "s1"],
            "variable": ["tax", "benefit", "tax"],
            "prediction": [1.0, None, 3.0],
            "explanation": ["Tax. value = 1", None, "Tax. value = 3"],
            "raw_response": [None, None, None],
            "error": [None, "Missing prediction after repair: benefit", None],
        }
    )


def _clean_predictions() -> pd.DataFrame:
    frame = _source_predictions()
    frame["prediction"] = frame["prediction"].fillna(2.0)
    frame["explanation"] = frame["explanation"].fillna("Benefit. value = 2")
    frame["error"] = None
    return frame


def _scenario_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "scenario_id": ["s1"],
            "country": ["us"],
            "scenario_json": ["{}"],
        }
    )


def test_row_repair_targets_selects_individual_broken_rows() -> None:
    targets = row_repair_targets(_source_predictions())

    assert targets.to_dict("records") == [
        {
            "model": "model_a",
            "scenario_id": "s1",
            "variable": "benefit",
        }
    ]


def test_prepare_row_repair_round_reparses_and_writes_targets(tmp_path: Path) -> None:
    predictions_path = tmp_path / "predictions.csv"
    scenarios_path = tmp_path / "scenarios.csv"
    _source_predictions().to_csv(predictions_path, index=False)
    _scenario_manifest().to_csv(scenarios_path, index=False)

    preparation = prepare_row_repair_round(
        source_predictions=predictions_path,
        scenario_manifest=scenarios_path,
        output_dir=tmp_path / "repair",
        country="us",
    )

    assert preparation.target_rows.to_dict("records") == [
        {
            "model": "model_a",
            "scenario_id": "s1",
            "variable": "benefit",
        }
    ]
    assert preparation.target_rows_path.exists()
    assert preparation.reparsed_source_predictions.exists()


def test_prepare_row_repair_round_preserves_source_without_merge_name_collision(
    tmp_path: Path,
) -> None:
    predictions_path = tmp_path / "merged_predictions.csv.gz"
    scenarios_path = tmp_path / "scenarios.csv"
    _source_predictions().to_csv(predictions_path, index=False)
    _scenario_manifest().to_csv(scenarios_path, index=False)

    preparation = prepare_row_repair_round(
        source_predictions=predictions_path,
        scenario_manifest=scenarios_path,
        output_dir=tmp_path / "repair",
        country="us",
    )
    outputs = merge_row_repair_predictions(
        source_predictions=preparation.reparsed_source_predictions,
        repair_predictions=tmp_path / "does_not_exist.csv",
        output_dir=preparation.output_dir,
    )

    assert preparation.source_predictions_copy.name == "source_predictions.csv.gz"
    assert preparation.source_predictions_copy.exists()
    assert outputs["merged_predictions"].name == "merged_predictions.csv.gz"
    assert preparation.source_predictions_copy != outputs["merged_predictions"]


def test_merge_row_repair_predictions_replaces_only_valid_rows(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.csv"
    repair_path = tmp_path / "repair.csv"
    _source_predictions().to_csv(source_path, index=False)
    pd.DataFrame(
        {
            "country": ["us", "us"],
            "attempt": [1, 1],
            "model": ["model_a", "model_b"],
            "scenario_id": ["s1", "s1"],
            "variable": ["benefit", "tax"],
            "prediction": [22.0, None],
            "explanation": ["Repair benefit. value = 22", ""],
            "raw_response": ["raw", "raw"],
            "error": [None, "Missing prediction after repair: tax"],
        }
    ).to_csv(repair_path, index=False)

    outputs = merge_row_repair_predictions(
        source_predictions=source_path,
        repair_predictions=repair_path,
        output_dir=tmp_path / "merged",
    )

    merged = pd.read_csv(outputs["merged_predictions"])
    repaired = merged[
        (merged["model"] == "model_a") & (merged["variable"] == "benefit")
    ].iloc[0]
    untouched = merged[
        (merged["model"] == "model_b") & (merged["variable"] == "tax")
    ].iloc[0]
    assert repaired["prediction"] == 22.0
    assert repaired["explanation"] == "Repair benefit. value = 22"
    assert untouched["prediction"] == 3.0
    assert untouched["explanation"] == "Tax. value = 3"
    rejected = pd.read_csv(outputs["rejected_row_repair_rows"])
    assert rejected.empty


def test_run_row_repair_round_with_no_targets_writes_merged_copy(
    tmp_path: Path,
) -> None:
    predictions_path = tmp_path / "predictions.csv"
    scenarios_path = tmp_path / "scenarios.csv"
    clean_predictions = _clean_predictions()
    clean_predictions.to_csv(predictions_path, index=False)
    _scenario_manifest().to_csv(scenarios_path, index=False)

    outputs = run_row_repair_round(
        country="us",
        source_predictions=predictions_path,
        scenario_manifest=scenarios_path,
        output_dir=tmp_path / "repair",
    )

    merged = pd.read_csv(outputs["merged_predictions"])
    sort_columns = ["model", "scenario_id", "variable"]
    expected = (
        pd.read_csv(predictions_path).sort_values(sort_columns).reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(
        merged.drop(columns=["error"]),
        expected.drop(columns=["error"]),
        check_dtype=False,
    )
    assert merged["error"].isna().all()
