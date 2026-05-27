"""Checks for the frozen manuscript snapshot artifacts."""

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from policybench.annotation_validation import validate_snapshot_audit
from policybench.spec import output_group_id

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "paper" / "snapshot" / "20260501"
ANNOTATIONS_DIR = (
    ROOT / "annotations" / "full_run_20260513_policyengine_4_4_4_nested_outputs"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_hash(path: Path, expected_hash: str) -> None:
    assert path.exists(), f"Missing snapshot artifact: {path}"
    assert sha256(path) == expected_hash


def test_snapshot_manifest_hashes_match_committed_artifacts():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    artifacts = manifest["committed_snapshot_artifacts"]
    assert artifacts
    for filename, expected_hash in artifacts.items():
        _assert_hash(SNAPSHOT_DIR / filename, expected_hash)


def test_snapshot_manifest_hashes_match_top_level_files():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    files = manifest["files"]
    assert files
    for artifact in files:
        _assert_hash(SNAPSHOT_DIR / artifact["path"], artifact["sha256"])


def test_snapshot_manifest_hashes_match_source_run_artifacts():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    source_artifacts = manifest["source_run_artifacts"]

    checked = 0
    for run_manifest in source_artifacts.values():
        if not isinstance(run_manifest, dict) or "path" not in run_manifest:
            continue
        run_dir = ROOT / run_manifest["path"]
        for relative_path, expected_hash in run_manifest["files"].items():
            _assert_hash(run_dir / relative_path, expected_hash)
            checked += 1
    assert checked


def test_snapshot_manifest_hashes_match_rendered_paper_artifacts():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    rendered_artifacts = manifest["rendered_paper_artifacts"]

    pdf = rendered_artifacts["pdf"]
    _assert_hash(ROOT / pdf["path"], pdf["sha256"])

    web = rendered_artifacts["web"]
    web_dir = ROOT / web["path"]
    for relative_path, expected_hash in web["files"].items():
        _assert_hash(web_dir / relative_path, expected_hash)


def test_snapshot_manifest_hashes_match_population_weight_artifact():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    artifact = manifest["population_weight_artifact"]
    _assert_hash(ROOT / artifact["path"], artifact["sha256"])


def test_snapshot_manifest_hashes_match_response_retry_artifacts():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    retry_artifacts = manifest["response_retry_artifacts"]
    retry_dir = ROOT / retry_artifacts["path"]
    for relative_path, expected_hash in retry_artifacts["files"].items():
        _assert_hash(retry_dir / relative_path, expected_hash)


def test_snapshot_manifest_hashes_match_row_repair_artifacts():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    repair_artifacts = manifest["row_repair_artifacts"]
    repair_dir = ROOT / repair_artifacts["path"]
    for relative_path, expected_hash in repair_artifacts["files"].items():
        _assert_hash(repair_dir / relative_path, expected_hash)


def test_snapshot_manifest_hashes_match_audit_annotation_artifacts():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    annotation_artifacts = manifest["audit_annotation_artifacts"]
    annotation_dir = ROOT / annotation_artifacts["path"]
    for relative_path, expected_hash in annotation_artifacts["files"].items():
        _assert_hash(annotation_dir / relative_path, expected_hash)


def _snapshot_country_payloads(manifest: dict) -> dict[str, dict]:
    payloads = {}
    for country, run_label in manifest["source_run_labels"].items():
        run_dir = ROOT / manifest["source_run_artifacts"][run_label]["path"]
        payloads[country] = json.loads((run_dir / "data.json").read_text())
    return payloads


def test_committed_app_payload_matches_frozen_source_run_export():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    expected_payload = {"countries": _snapshot_country_payloads(manifest)}
    app_payload = json.loads((ROOT / "app" / "src" / "data.json").read_text())

    assert app_payload == expected_payload


def _aggregate_scenario_metric(country_payload: dict, metric: str) -> dict[str, float]:
    """Mirror the app/Python household-normalized row aggregation."""
    output_weights = country_payload["globalWeights"]["household"]
    grouped_weights = {}
    for variable, weight in output_weights.items():
        group = output_group_id(variable)
        grouped_weights[group] = grouped_weights.get(group, 0.0) + weight
    totals: dict[str, dict[str, float]] = {}
    for variable_map in country_payload["scenarioPredictions"].values():
        variables = [
            (variable, model_map)
            for variable, model_map in variable_map.items()
            if output_group_id(variable) in grouped_weights
        ]
        group_counts: dict[str, int] = {}
        for variable, _ in variables:
            group = output_group_id(variable)
            group_counts[group] = group_counts.get(group, 0) + 1
        raw_row_weights = {}
        denominator = 0.0
        for variable, _ in variables:
            group = output_group_id(variable)
            raw_weight = grouped_weights[group] / group_counts[group]
            raw_row_weights[variable] = raw_weight
            denominator += raw_weight
        if denominator <= 0:
            continue

        models = {model for _, model_map in variables for model in model_map}
        for model in models:
            household_score = 0.0
            for variable, model_map in variables:
                row = model_map[model]
                household_score += (raw_row_weights[variable] / denominator) * row[
                    metric
                ]
            entry = totals.setdefault(model, {"score": 0.0, "households": 0.0})
            entry["score"] += household_score
            entry["households"] += 1

    return {
        model: entry["score"] / entry["households"] for model, entry in totals.items()
    }


def test_scenario_row_scores_reproduce_committed_model_stats():
    app_payload = json.loads((ROOT / "app" / "src" / "data.json").read_text())

    metric_pairs = {
        "score": "score",
        "exact": "exact",
        "within1pct": "within1pct",
        "within5pct": "within5pct",
        "within10pct": "within10pct",
    }
    for country_payload in app_payload["countries"].values():
        model_stats = {
            row["model"]: row
            for row in country_payload["modelStats"]
            if row["condition"] == "no_tools"
        }
        for row_metric, model_metric in metric_pairs.items():
            aggregated = _aggregate_scenario_metric(country_payload, row_metric)
            for model, score in aggregated.items():
                assert score == pytest.approx(
                    model_stats[model][model_metric],
                    abs=1e-9,
                )


def _prompt_payload_sha256(country_payload: dict) -> str:
    prompts = {
        scenario_id: scenario.get("prompt")
        for scenario_id, scenario in sorted(country_payload["scenarios"].items())
    }
    payload = json.dumps(prompts, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def test_snapshot_prompt_payload_hashes_are_frozen_to_source_runs():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    country_payloads = _snapshot_country_payloads(manifest)

    for country, run_label in manifest["source_run_labels"].items():
        expected_hash = manifest["source_run_artifacts"][run_label][
            "prompt_payload_sha256"
        ]
        assert _prompt_payload_sha256(country_payloads[country]) == expected_hash


def test_snapshot_source_run_payloads_match_scope():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    country_payloads = _snapshot_country_payloads(manifest)
    dashboard = {"countries": country_payloads}

    for country, expected_households in manifest["scope"]["households"].items():
        country_payload = dashboard["countries"][country]
        assert len(country_payload["scenarios"]) == expected_households
        assert (
            len(country_payload["programStats"])
            == manifest["scope"]["output_groups"][country]
        )

        scenarios = pd.read_csv(SNAPSHOT_DIR / f"{country}_scenarios.csv")
        references = pd.read_csv(SNAPSHOT_DIR / f"{country}_reference_outputs.csv")
        assert scenarios["scenario_id"].nunique() == expected_households
        assert references["scenario_id"].nunique() == expected_households

    expected_models = manifest["scope"]["models"]
    for country in ("us", "uk"):
        country_models = [
            row
            for row in dashboard["countries"][country]["modelStats"]
            if row["condition"] == "no_tools"
        ]
        assert len(country_models) == expected_models
        top_model = max(country_models, key=lambda row: row["within1pct"])
        assert top_model["model"] == "gpt-5.5"


def test_snapshot_copied_artifacts_match_source_runs():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())

    for country, run_label in manifest["source_run_labels"].items():
        run_dir = ROOT / manifest["source_run_artifacts"][run_label]["path"]
        copied_scenarios = pd.read_csv(SNAPSHOT_DIR / f"{country}_scenarios.csv")
        source_scenarios = pd.read_csv(run_dir / "scenarios.csv")
        pd.testing.assert_frame_equal(copied_scenarios, source_scenarios)

        copied_references = pd.read_csv(
            SNAPSHOT_DIR / f"{country}_reference_outputs.csv"
        )
        source_references = pd.read_csv(run_dir / "reference_outputs.csv")
        pd.testing.assert_frame_equal(copied_references, source_references)


def test_snapshot_deviation_audit_annotations_are_complete_and_final():
    expected_wrong_rows = {
        "us": 4_039,
        "uk": 2_732,
    }
    expected_sources = {
        "us": {"llm_error": 4_039},
        "uk": {"llm_error": 2_732},
    }

    for country in ["us", "uk"]:
        result = validate_snapshot_audit(
            snapshot_dir=SNAPSHOT_DIR,
            annotations_dir=ANNOTATIONS_DIR,
            country=country,
        )
        assert len(result["wrong"]) == expected_wrong_rows[country]
        assert result["missing_rows"].empty
        assert result["unresolved_rows"].empty
        assert result["missing_cases"].empty

        annotations = pd.concat(
            pd.read_csv(path)
            for path in sorted(ANNOTATIONS_DIR.glob(f"{country}_*_annotations.csv"))
        )
        audited = result["wrong"].merge(
            annotations[["model", "scenario_id", "variable", "failure_source"]],
            on=["model", "scenario_id", "variable"],
            how="left",
        )
        assert (
            audited["failure_source"].value_counts().to_dict()
            == expected_sources[country]
        )
