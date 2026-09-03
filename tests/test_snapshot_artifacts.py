"""Checks for the frozen manuscript snapshot artifacts."""

import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from policybench.annotation_validation import validate_snapshot_audit
from policybench.spec import output_group_id

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "paper" / "snapshot" / "20260501"
ANNOTATIONS_DIR = (
    ROOT
    / json.loads((SNAPSHOT_DIR / "manifest.json").read_text())[
        "audit_annotation_artifacts"
    ]["path"]
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


def test_published_dashboard_artifact_matches_frozen_source_run_export():
    """The published payload must equal the combined frozen run exports.

    The dashboard blob is no longer committed, so this recombines the
    committed per-country run exports exactly as export_full_run serializes
    them and checks the bytes hash to the manifest's published-artifact pin —
    the same equality the old committed-blob comparison enforced, offline.
    """
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    expected_payload = {"countries": _snapshot_country_payloads(manifest)}
    combined_bytes = json.dumps(expected_payload).encode("utf-8")
    digest = hashlib.sha256(combined_bytes).hexdigest()

    assert digest == manifest["published_dashboard_artifact"]["sha256"]


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
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    app_payload = {"countries": _snapshot_country_payloads(manifest)}

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
    for country in manifest["scope"]["households"]:
        country_models = [
            row
            for row in dashboard["countries"][country]["modelStats"]
            if row["condition"] == "no_tools"
        ]
        assert len(country_models) == expected_models
        top_model = max(country_models, key=lambda row: row["within1pct"])
        assert top_model["model"] == "gpt-5.6-sol"


def test_snapshot_serving_configuration_matches_frozen_roster():
    config = json.loads((SNAPSHOT_DIR / "model_serving_config.json").read_text())
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    country_payloads = _snapshot_country_payloads(manifest)
    frozen_models = {
        row["model"]
        for payload in country_payloads.values()
        for row in payload["modelStats"]
        if row["condition"] == "no_tools"
    }

    assert set(config["models"]) == frozen_models
    for model in ("claude-fable-5", "claude-opus-5", "claude-sonnet-5"):
        assert config["models"][model]["reasoning_setup"] == (
            "thinking does not engage under forced tool call"
        )
        assert config["models"][model]["tool_choice"] == "forced"

    assert config["models"]["kimi-k3"]["reasoning_setup"] == (
        "provider default; 49,152-token shared budget"
    )
    assert config["models"]["qwen3.8-max"]["reasoning_setup"] == (
        "provider default; 98,304-token shared budget"
    )


def test_snapshot_serving_configuration_records_evidence_schema():
    config = json.loads((SNAPSHOT_DIR / "model_serving_config.json").read_text())
    summary = config["evidence_summary"]

    assert re.fullmatch(r"[0-9a-f]{40}", config["registry_commit"])
    assert config["evidence_field_labels"] == {
        "registry_for_run_state": ["reasoning setup", "timeouts"],
        "run_state": [
            "answer contract",
            "request shape",
            "tool choice",
            "completion ceiling",
        ],
    }
    assert set(summary) == {"run_state", "registry"}
    assert sum(summary.values()) == len(config["models"])
    assert summary["run_state"] > 0

    observed = {"run_state": 0, "registry": 0}
    for row in config["models"].values():
        evidence = row["evidence"]
        kind = evidence["kind"]
        observed[kind] += 1
        if kind == "registry":
            assert evidence == {"kind": "registry"}
            assert set(row["registry_derived"]) == {
                "answer_contract",
                "provider_id",
                "reasoning_setup",
                "request_shape",
                "request_timeout_seconds",
                "shared_completion_budget_tokens",
                "tool_choice",
            }
            continue

        assert set(evidence) in (
            {"kind", "run", "fields", "treatment_fingerprint"},
            {
                "kind",
                "run",
                "fields",
                "treatment_fingerprint",
                "legacy_tool_choice_label",
            },
        )
        assert evidence["fields"] == sorted(evidence["treatment_fingerprint"])
        assert set(row["registry_derived"]) == {
            "reasoning_setup",
            "request_timeout_seconds",
            "shared_completion_budget_tokens",
        }
        assert not evidence["run"].endswith("_thinking")

    assert observed == summary


def test_run_state_serving_evidence_agrees_with_registry_fields():
    config = json.loads((SNAPSHOT_DIR / "model_serving_config.json").read_text())

    for row in config["models"].values():
        evidence = row["evidence"]
        if evidence["kind"] != "run_state":
            continue

        fingerprint = evidence["treatment_fingerprint"]
        assert {
            "model_id",
            "answer_contract",
            "tool_choice_mode",
            "chunk_size",
            "prompt_contract_version",
            "completion_budget_ceiling",
        } <= set(fingerprint)
        assert fingerprint["model_id"] == row["provider_id"]
        assert fingerprint["answer_contract"] == row["answer_contract"]
        assert isinstance(row["request_timeout_seconds"], int)
        assert row["request_timeout_seconds"] > 0
        chunk_size = (
            None
            if row["request_shape"] == "whole scenario"
            else int(row["request_shape"].split()[0])
        )
        assert fingerprint["chunk_size"] == chunk_size

        fingerprint_tool_choice = fingerprint["tool_choice_mode"]
        if "legacy_tool_choice_label" in evidence:
            assert row["answer_contract"] == "json"
            assert row["tool_choice"] is None
            assert fingerprint_tool_choice == evidence["legacy_tool_choice_label"]
        else:
            assert fingerprint_tool_choice == row["tool_choice"]


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
        "us": 7_840,
    }
    expected_sources = {
        "us": {"llm_error": 7_211, "parse_contract_failure": 629},
    }

    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    for country in manifest["source_run_labels"]:
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


def test_snapshot_audit_annotations_have_no_orphan_rows():
    """Every row annotation must describe a wrong cell of the frozen roster:
    an annotation key absent from the frozen wrong rows means the pinned CSV
    has drifted ahead of (or away from) the snapshot it certifies."""
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    for country in manifest["source_run_labels"]:
        result = validate_snapshot_audit(
            snapshot_dir=SNAPSHOT_DIR,
            annotations_dir=ANNOTATIONS_DIR,
            country=country,
        )
        keys = ["model", "scenario_id", "variable"]
        annotations = pd.concat(
            pd.read_csv(path)
            for path in sorted(ANNOTATIONS_DIR.glob(f"{country}_*_annotations.csv"))
        )
        orphans = annotations[keys].merge(
            result["wrong"][keys].drop_duplicates(), on=keys, how="left", indicator=True
        )
        assert (orphans["_merge"] == "both").all(), orphans[
            orphans["_merge"] != "both"
        ].head()
        assert len(annotations) == len(result["wrong"])


def test_snapshot_case_notes_agree_with_row_annotations():
    """Case notes aggregate the row annotations: one case per wrong
    (scenario, output) pair, and wrong_model_count equals the number of
    annotated rows in that case."""
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    for country in manifest["source_run_labels"]:
        rows = pd.concat(
            pd.read_csv(path)
            for path in sorted(ANNOTATIONS_DIR.glob(f"{country}_*_annotations.csv"))
        )
        cases = pd.read_csv(ANNOTATIONS_DIR / f"{country}_case_notes.csv")
        row_counts = (
            rows.groupby(["scenario_id", "variable"]).size().rename("row_count")
        )
        joined = cases.set_index(["scenario_id", "variable"]).join(
            row_counts, how="outer"
        )
        assert joined["wrong_model_count"].notna().all(), "rows without a case"
        assert joined["row_count"].notna().all(), "cases without rows"
        assert (
            joined["wrong_model_count"].astype(int) == joined["row_count"].astype(int)
        ).all(), joined[joined["wrong_model_count"] != joined["row_count"]].head()


def test_dashboard_pointer_matches_live_snapshot_artifact():
    """The committed artifact pointer must reference the manifest's live
    dashboard artifact — the machine-checked version of live_dashboard_note.

    The live artifact starts from the frozen export pinned under
    published_dashboard_artifact and may move ahead of it (injected metrics,
    newly benchmarked models), so the pointer is checked against the live
    entry; the frozen pin is covered by
    test_published_dashboard_artifact_matches_frozen_source_run_export.
    """
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    live = manifest["live_dashboard_artifact"]
    pointer = json.loads((ROOT / "app" / "src" / "data.artifact.json").read_text())
    assert pointer["sha256"] == live["sha256"]
    assert pointer["tag"] == live["tag"]
    assert pointer["asset"] == live["asset"]
    assert pointer["url"] == live["url"]
    assert live["derivation"]


def test_dashboard_blob_is_not_committed():
    """data.json is a published artifact, not source; only the pointer is
    committed (local exports are gitignored)."""
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", "app/src/data.json"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    ).stdout.strip()
    assert tracked == ""


def test_frozen_payload_provenance_matches_the_reference_sidecar():
    """The frozen data.json must name the policyengine-us that generated the
    references it scores against, as recorded by the reference sidecar and the
    manifest, not the exporting machine's installed runtime."""
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    expected = manifest["reference_output_refresh"]["policyengine_us_version"]
    for country, run_label in manifest["source_run_labels"].items():
        run_dir = ROOT / manifest["source_run_artifacts"][run_label]["path"]
        payload = json.loads((run_dir / "data.json").read_text())
        sidecar = json.loads((run_dir / "reference_outputs.csv.meta.json").read_text())
        sidecar_version = sidecar["policyengine_bundles"][country]["model_version"]
        assert sidecar_version == expected
        assert payload["policyengineBundles"][country]["model_version"] == expected


def test_reference_refresh_date_is_the_generation_date_not_the_snapshot_date():
    """The references were generated once (the sidecar's timestamp) and are
    byte-identical across freezes; the manifest must not advance their date
    with each publication."""
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    refresh = manifest["reference_output_refresh"]
    run_label = manifest["source_run_labels"]["us"]
    run_dir = ROOT / manifest["source_run_artifacts"][run_label]["path"]
    sidecar = json.loads((run_dir / "reference_outputs.csv.meta.json").read_text())
    assert refresh["generated_at_utc"] == sidecar["generated_at_utc"]
    assert refresh["date"] == sidecar["generated_at_utc"][:10]
    assert refresh["snapshot_date"] == manifest["snapshot_date"]
    assert refresh["date"] <= refresh["snapshot_date"]
