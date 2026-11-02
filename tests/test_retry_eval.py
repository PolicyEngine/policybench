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


def test_run_retry_models_hands_all_models_one_provenance_file(tmp_path, monkeypatch):
    """A retry round writes PolicyEngine provenance once, at its root, and
    every model's chunk workers get that file."""
    import json

    from policybench.config import DEFAULT_PROGRAM_SET, get_programs
    from policybench.policyengine_runtime import (
        POLICYENGINE_PROVENANCE_ENV,
        POLICYENGINE_PROVENANCE_FILENAME,
    )
    from policybench.retry_eval import run_retry_models
    from policybench.spec import expand_programs_for_scenario
    from tests.test_chunked_eval import (
        MOCK_BUNDLES,
        _complete_chunk_writer,
        _probe_scenarios,
        _write_manifest,
    )

    scenarios = _probe_scenarios(3)
    manifest = _write_manifest(tmp_path / "scenarios.csv", scenarios)
    programs = get_programs("us", DEFAULT_PROGRAM_SET)
    models = ["gpt-5.5", "grok-4.3"]
    source = tmp_path / "predictions.csv"
    pd.DataFrame(
        [
            {
                "model": model,
                "scenario_id": scenario.id,
                "variable": variable,
                "prediction": None,
                "explanation": "",
                "error": "Missing predictions after repair",
            }
            for model in models
            for scenario in scenarios
            for variable in expand_programs_for_scenario(programs, scenario)
        ]
    ).to_csv(source, index=False)
    preparation = prepare_retry_round(
        country="us",
        source_predictions=source,
        scenario_manifest=manifest,
        output_dir=tmp_path / "retry",
    )
    writes = []

    def fake_writer(python, path, countries, env, **kwargs):
        writes.append(Path(path))
        bundles = {country: MOCK_BUNDLES[country] for country in countries}
        Path(path).write_text(json.dumps({"policyengine_bundles": bundles}))
        return True

    monkeypatch.setattr(
        "policybench.chunked_eval.run_policyengine_provenance_writer", fake_writer
    )
    chunk_calls = []
    monkeypatch.setattr(
        "policybench.chunked_eval.run_chunk",
        _complete_chunk_writer(scenarios, chunk_calls),
    )

    run_retry_models(
        preparation=preparation,
        country="us",
        chunk_size=1,
        parallel=2,
        model_parallel=2,
    )

    path = (tmp_path / "retry" / POLICYENGINE_PROVENANCE_FILENAME).resolve()
    assert writes == [path]
    assert len(chunk_calls) == 6
    assert {call["env"][POLICYENGINE_PROVENANCE_ENV] for call in chunk_calls} == {
        str(path)
    }
    assert not list(
        (tmp_path / "retry" / "model_runs").glob(
            f"*/{POLICYENGINE_PROVENANCE_FILENAME}"
        )
    )
