from pathlib import Path

import pandas as pd

from policybench.retry_eval import (
    merge_retry_predictions,
    prepare_retry_round,
    response_retry_units,
    run_retry_round,
)


def _source_predictions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "model": ["model_a", "model_a", "model_b", "model_b"],
            "scenario_id": ["s1", "s1", "s1", "s1"],
            "variable": ["tax", "benefit", "tax", "benefit"],
            "prediction": [1.0, None, 2.0, 3.0],
            "explanation": [
                "Tax. value = 1",
                "",
                "Tax. value = 2",
                "Benefit. value = 3",
            ],
            "error": [None, "Missing predictions after repair: benefit", None, None],
        }
    )


def _scenario_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "scenario_id": ["s1", "s2"],
            "country": ["us", "us"],
            "scenario_json": ["{}", "{}"],
        }
    )


def test_response_retry_units_targets_whole_model_scenario_response():
    units = response_retry_units(_source_predictions())

    assert units.to_dict("records") == [
        {
            "model": "model_a",
            "scenario_id": "s1",
            "missing_predictions": 1,
            "missing_explanations": 1,
            "infrastructure_error_rows": 0,
            "source_rows": 2,
        }
    ]


def test_prepare_retry_round_preserves_originals_and_writes_model_manifests(tmp_path):
    predictions_path = tmp_path / "predictions.csv"
    scenarios_path = tmp_path / "scenarios.csv"
    _source_predictions().to_csv(predictions_path, index=False)
    _scenario_manifest().to_csv(scenarios_path, index=False)

    preparation = prepare_retry_round(
        country="us",
        source_predictions=predictions_path,
        scenario_manifest=scenarios_path,
        output_dir=tmp_path / "retry",
    )

    assert preparation.target_units[["model", "scenario_id"]].to_dict("records") == [
        {"model": "model_a", "scenario_id": "s1"}
    ]
    originals = pd.read_csv(preparation.original_failed_rows_path)
    assert set(originals["variable"]) == {"tax", "benefit"}
    manifest = pd.read_csv(preparation.scenario_manifest_paths["model_a"])
    assert manifest["scenario_id"].tolist() == ["s1"]


def test_merge_retry_predictions_replaces_only_fully_valid_full_responses(tmp_path):
    source_path = tmp_path / "source.csv"
    retry_path = tmp_path / "retry.csv"
    target_path = tmp_path / "target.csv"
    _source_predictions().to_csv(source_path, index=False)
    pd.DataFrame(
        {
            "model": ["model_a", "model_a"],
            "scenario_id": ["s1", "s1"],
            "variable": ["tax", "benefit"],
            "prediction": [10.0, 20.0],
            "explanation": ["Retry tax. value = 10", "Retry benefit. value = 20"],
            "error": [None, None],
        }
    ).to_csv(retry_path, index=False)
    pd.DataFrame({"model": ["model_a"], "scenario_id": ["s1"]}).to_csv(
        target_path,
        index=False,
    )

    outputs = merge_retry_predictions(
        source_predictions=source_path,
        retry_predictions=retry_path,
        target_units=target_path,
        output_dir=tmp_path / "merged",
    )

    merged = pd.read_csv(outputs["merged_predictions"])
    model_a = merged[merged["model"] == "model_a"].sort_values("variable")
    assert model_a["prediction"].tolist() == [20.0, 10.0]
    replaced = pd.read_csv(outputs["replaced_original_responses"])
    assert set(replaced["variable"]) == {"tax", "benefit"}


def test_merge_retry_predictions_rejects_partial_retry_response(tmp_path):
    source_path = tmp_path / "source.csv"
    retry_path = tmp_path / "retry.csv"
    target_path = tmp_path / "target.csv"
    _source_predictions().to_csv(source_path, index=False)
    pd.DataFrame(
        {
            "model": ["model_a"],
            "scenario_id": ["s1"],
            "variable": ["tax"],
            "prediction": [10.0],
            "explanation": ["Retry tax. value = 10"],
            "error": [None],
        }
    ).to_csv(retry_path, index=False)
    pd.DataFrame({"model": ["model_a"], "scenario_id": ["s1"]}).to_csv(
        target_path,
        index=False,
    )

    outputs = merge_retry_predictions(
        source_predictions=source_path,
        retry_predictions=retry_path,
        target_units=target_path,
        output_dir=tmp_path / "merged",
    )

    merged = pd.read_csv(outputs["merged_predictions"])
    model_a = merged[merged["model"] == "model_a"].sort_values("variable")
    assert model_a["prediction"].fillna(-1).tolist() == [-1.0, 1.0]
    rejected = pd.read_csv(outputs["rejected_retry_units"])
    assert rejected["reason"].str.contains("variable set").any()


def test_run_retry_round_can_prepare_only(tmp_path):
    predictions_path = tmp_path / "predictions.csv"
    scenarios_path = tmp_path / "scenarios.csv"
    _source_predictions().to_csv(predictions_path, index=False)
    _scenario_manifest().to_csv(scenarios_path, index=False)

    outputs = run_retry_round(
        country="us",
        source_predictions=predictions_path,
        scenario_manifest=scenarios_path,
        output_dir=tmp_path / "retry",
        prepare_only=True,
    )

    assert Path(outputs["target_units"]).exists()
    assert Path(outputs["original_failed_responses"]).exists()


def test_run_retry_round_with_no_targets_writes_merged_copy(tmp_path):
    predictions_path = tmp_path / "predictions.csv"
    scenarios_path = tmp_path / "scenarios.csv"
    clean_predictions = _source_predictions()
    clean_predictions["prediction"] = clean_predictions["prediction"].fillna(0)
    clean_predictions["explanation"] = clean_predictions["explanation"].replace(
        "",
        "Benefit. value = 0",
    )
    clean_predictions["error"] = None
    clean_predictions.to_csv(predictions_path, index=False)
    _scenario_manifest().to_csv(scenarios_path, index=False)

    outputs = run_retry_round(
        country="us",
        source_predictions=predictions_path,
        scenario_manifest=scenarios_path,
        output_dir=tmp_path / "retry",
    )

    retry = pd.read_csv(outputs["retry_predictions"])
    merged = pd.read_csv(outputs["merged_predictions"])
    accepted = pd.read_csv(outputs["accepted_retry_units"])
    rejected = pd.read_csv(outputs["rejected_retry_units"])
    assert list(retry.columns) == list(clean_predictions.columns)
    sort_columns = ["model", "scenario_id", "variable"]
    expected = clean_predictions.sort_values(sort_columns).reset_index(drop=True)
    pd.testing.assert_frame_equal(
        merged.drop(columns=["error"]),
        expected.drop(columns=["error"]),
        check_dtype=False,
    )
    assert merged["error"].isna().all()
    assert list(accepted.columns) == ["model", "scenario_id"]
    assert list(rejected.columns) == ["model", "scenario_id", "reason"]
