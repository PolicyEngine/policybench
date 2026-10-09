"""Checks for the frozen manuscript snapshot artifacts."""

import calendar
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from policybench.annotation_validation import validate_snapshot_audit
from policybench.snapshot_payload import read_run_payload
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


def test_paper_page_snapshot_matches_the_manifest():
    """The /paper page names the manifest's snapshot and cache-keys its render.

    scripts/freeze_snapshot.py writes app/src/paperSnapshot.json whenever it
    pins the rendered paper, so a re-render changes the manuscript URLs the page
    embeds, and the page keeps no hand-kept snapshot date or cache key.
    """
    from scripts.freeze_snapshot import app_paper_snapshot

    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    rendered = manifest["rendered_paper_artifacts"]
    page_snapshot = json.loads(
        (ROOT / "app" / "src" / "paperSnapshot.json").read_text()
    )

    assert page_snapshot == app_paper_snapshot(manifest)
    assert page_snapshot["snapshotDate"] == manifest["snapshot_date"]
    assert page_snapshot["webVersion"] == rendered["web"]["files"]["index.html"][:12]
    assert page_snapshot["pdfVersion"] == rendered["pdf"]["sha256"][:12]

    # The whole file is checked, comments included, so nothing can hide a
    # hand-kept key or date behind a comment or inside a string.
    page = (ROOT / "app" / "src" / "app" / "paper" / "page.tsx").read_text()
    assert re.search(r"policybench\.pdf\?v=\$\{paperSnapshot\.pdfVersion\}", page)
    assert re.search(r"index\.html\?v=\$\{paperSnapshot\.webVersion\}", page)
    for field in ("responseWindow", "snapshotDate"):
        assert f"{{paperSnapshot.{field}}}" in page
    stray_keys = re.findall(
        r"\?v=(?!\$\{paperSnapshot\.(?:pdfVersion|webVersion)\})\S*", page
    )
    assert not stray_keys, f"cache keys not taken from paperSnapshot: {stray_keys}"
    month = "(?:{})\\.?".format(
        "|".join(f"{name[:3]}(?:{name[3:]})?" for name in calendar.month_name[1:])
        + "|Sept"
    )
    date_patterns = (
        r"20\d\d-?\d\d-?\d\d",  # 2026-09-22, 20260922
        rf"\b{month} \d{{1,2}}\b",  # September 22, Sept. 22
        rf"\b\d{{1,2}} {month}\b",  # 22 September
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",  # 9/22/2026
    )
    hard_coded = [m.group(0) for p in date_patterns for m in re.finditer(p, page)]
    assert not hard_coded, f"dates not taken from paperSnapshot: {hard_coded}"


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
        payloads[country] = read_run_payload(run_dir)
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
            # Outputs excluded from scoring carry scored=false on every row.
            and not any(row.get("scored") is False for row in model_map.values())
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
        assert top_model["model"] == "gpt-6-sol"


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
    compared_columns = [
        "scenario_id",
        "variable",
        "prediction",
        "explanation",
        "raw_response",
        "provider_resolved_model",
        "prompt_tokens",
        "completion_tokens",
        "error",
    ]

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
            if set(evidence) != {"kind"}:
                assert set(evidence) == {
                    "compared_columns",
                    "frozen_rows_sha256",
                    "kind",
                    "note",
                    "rows_match",
                    "source_predictions_sha256",
                    "source_rows_sha256",
                }
                assert evidence["compared_columns"] == compared_columns
                assert re.fullmatch(r"[0-9a-f]{64}", evidence["frozen_rows_sha256"])
                if evidence["source_rows_sha256"] is not None:
                    assert re.fullmatch(r"[0-9a-f]{64}", evidence["source_rows_sha256"])
                assert evidence["rows_match"] is False
                assert evidence["note"]
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
            {
                "kind",
                "run",
                "fields",
                "compared_columns",
                "frozen_rows_sha256",
                "rows_match",
                "source_predictions_sha256",
                "source_rows_sha256",
                "treatment_fingerprint",
            },
            {
                "kind",
                "run",
                "fields",
                "compared_columns",
                "frozen_rows_sha256",
                "rows_match",
                "source_predictions_sha256",
                "source_rows_sha256",
                "treatment_fingerprint",
                "legacy_tool_choice_label",
            },
        )
        assert evidence["rows_match"] is True
        assert evidence["compared_columns"] == compared_columns
        assert evidence["source_rows_sha256"] == evidence["frozen_rows_sha256"]
        assert re.fullmatch(r"[0-9a-f]{64}", evidence["source_predictions_sha256"])
        assert evidence["fields"] == sorted(evidence["treatment_fingerprint"])
        # Fingerprint version 2 and later also pins the reasoning setup, the
        # request timeout and the shared completion budget, so no serving field
        # is left to the registry; older fingerprints pin the four transport
        # fields only.
        fingerprint_version = evidence["treatment_fingerprint"].get(
            "fingerprint_version"
        )
        if fingerprint_version is not None and fingerprint_version >= 2:
            assert set(row["registry_derived"]) == set()
            # The fields that replace the registry must be pinned.
            assert {
                "thinking",
                "request_timeout_seconds",
                "initial_completion_budget_tokens",
            } <= set(evidence["treatment_fingerprint"])
            if fingerprint_version >= 3:
                assert "max_repair_rounds" in evidence["treatment_fingerprint"]
        else:
            assert set(row["registry_derived"]) == {
                "reasoning_setup",
                "request_timeout_seconds",
                "shared_completion_budget_tokens",
            }
        assert not evidence["run"].endswith("_thinking")

    assert observed == summary


@pytest.mark.parametrize(
    ("column", "different_value"),
    [
        ("prediction", 2.0),
        ("explanation", "A different explanation"),
        ("raw_response", "A different raw response"),
        ("provider_resolved_model", "provider/other-model"),
        ("prompt_tokens", 12),
        ("completion_tokens", 34),
        ("error", "provider_error"),
    ],
)
def test_freezer_downgrades_run_state_when_full_prediction_row_differs(
    tmp_path, column, different_value
):
    from scripts.freeze_snapshot import (
        PREDICTION_EVIDENCE_COLUMNS,
        _run_state_prediction_evidence,
    )

    run_state_path = tmp_path / "run" / "run_state.json"
    run_state_path.parent.mkdir()
    run_state_path.write_text("{}")
    source_path = run_state_path.with_name("predictions.csv")
    row = {
        "model": "example-model",
        "scenario_id": "scenario_000",
        "variable": "snap",
        "prediction": 1.0,
        "explanation": "An explanation",
        "raw_response": "A raw response",
        "provider_resolved_model": "provider/example-model",
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "error": None,
    }
    pd.DataFrame([row]).to_csv(source_path, index=False)
    frozen_row = {**row, column: different_value}
    frozen = pd.DataFrame([frozen_row])

    evidence = _run_state_prediction_evidence(
        run_state_path,
        frozen,
        "example-model",
    )

    assert evidence["compared_columns"] == list(PREDICTION_EVIDENCE_COLUMNS)
    assert evidence["kind"] == "registry"
    assert evidence["source_predictions_sha256"] == sha256(source_path)
    assert evidence["source_rows_sha256"] != evidence["frozen_rows_sha256"]
    assert evidence["rows_match"] is False
    assert evidence["note"] == (
        "Source predictions.csv rows do not match the frozen model rows; "
        "serving fields fall back to the registry."
    )


def test_freezer_full_row_hash_normalizes_empty_values_and_text_whitespace(
    tmp_path,
):
    from scripts.freeze_snapshot import _run_state_prediction_evidence

    run_state_path = tmp_path / "run" / "run_state.json"
    run_state_path.parent.mkdir()
    run_state_path.write_text("{}")
    source_path = run_state_path.with_name("predictions.csv")
    row = {
        "model": "example-model",
        "scenario_id": " scenario_000 ",
        "variable": " snap ",
        "prediction": 1,
        "explanation": " An explanation ",
        "raw_response": " A raw response ",
        "provider_resolved_model": " provider/example-model ",
        "prompt_tokens": 10.0,
        "completion_tokens": 20.0,
        "error": "",
    }
    pd.DataFrame([row]).to_csv(source_path, index=False)
    frozen = pd.DataFrame(
        [
            {
                **row,
                "scenario_id": "scenario_000",
                "variable": "snap",
                "explanation": "An explanation",
                "raw_response": "A raw response",
                "provider_resolved_model": "provider/example-model",
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "error": None,
            }
        ]
    )

    evidence = _run_state_prediction_evidence(
        run_state_path,
        frozen,
        "example-model",
    )

    assert evidence["kind"] == "run_state"
    assert evidence["rows_match"] is True
    assert evidence["source_rows_sha256"] == evidence["frozen_rows_sha256"]


def test_freezer_accepts_v3_fingerprint_and_compares_repair_rounds(tmp_path):
    from scripts.freeze_snapshot import (
        SUPPORTED_TREATMENT_FINGERPRINT_VERSIONS,
        _validate_treatment_fingerprint,
    )

    expected = {
        "model_id": "provider/model",
        "answer_contract": "tool",
        "tool_choice_mode": "forced",
        "chunk_size": None,
        "prompt_contract_version": "contract-v1",
        "completion_budget_ceiling": 128_000,
        "initial_completion_budget_tokens": 4_096,
        "thinking": None,
        "request_timeout_seconds": 20,
        "max_repair_rounds": 2,
    }
    fingerprint = {"fingerprint_version": 3, **expected}
    run_state_path = tmp_path / "run_state.json"

    assert SUPPORTED_TREATMENT_FINGERPRINT_VERSIONS == (1, 2, 3)
    assert _validate_treatment_fingerprint(
        fingerprint,
        expected,
        model="example-model",
        run_state_path=run_state_path,
    ) == (3, False)

    fingerprint["max_repair_rounds"] = 3
    with pytest.raises(SystemExit, match="max_repair_rounds"):
        _validate_treatment_fingerprint(
            fingerprint,
            expected,
            model="example-model",
            run_state_path=run_state_path,
        )


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
    # Release 20261006: release 20260930's counts (annotated 7,860; exact
    # misses 7,856; below full bounded score 9,967; unannotated 2,107;
    # llm_error 7,208 and parse_contract_failure 652) less the rows on the
    # eight outputs it excludes. On those outputs release 20260930 had 368
    # scored rows (8 outputs x 46 models), all below full bounded score; 333
    # had a legacy threshold score below 1, all exact misses and all
    # annotated (325 llm_error, 8 parse_contract_failure), and 35 did not.
    # Release 20261009: Claude Haiku 5.5's rows join, and the outputs the
    # 2026-10-06 rulings and the engine upgrade exclude leave the universe
    # while the ones it regenerates return (release 20261006: annotated 7,527,
    # below full bounded score 9,599, llm_error 6,883, parse failures 644).
    expected_audit_counts = {
        "us": {
            "annotated": 7_507,
            "exact_misses": 7_503,
            "annotated_exact_misses": 7_503,
            "annotated_exact_hits": 4,
            "below_full_bounded_score": 9_622,
            "unannotated_below_full_bounded_score": 2_115,
        }
    }
    expected_sources = {
        "us": {"llm_error": 6_861, "parse_contract_failure": 646},
    }

    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    payloads = _snapshot_country_payloads(manifest)
    for country in manifest["source_run_labels"]:
        result = validate_snapshot_audit(
            snapshot_dir=SNAPSHOT_DIR,
            annotations_dir=ANNOTATIONS_DIR,
            country=country,
        )
        assert result["missing_rows"].empty
        assert result["unresolved_rows"].empty
        assert result["missing_cases"].empty

        annotations = pd.concat(
            pd.read_csv(path)
            for path in sorted(ANNOTATIONS_DIR.glob(f"{country}_*_annotations.csv"))
        )
        key_columns = ["model", "scenario_id", "variable"]
        annotation_keys = set(
            annotations[key_columns].itertuples(index=False, name=None)
        )
        prediction_rows = [
            (model, scenario_id, variable, row)
            for scenario_id, variable_map in payloads[country][
                "scenarioPredictions"
            ].items()
            for variable, model_map in variable_map.items()
            for model, row in model_map.items()
            # Outputs excluded from scoring are outside the audit universe.
            if row.get("scored") is not False
        ]
        excluded_outputs = {
            (r.scenario_id, r.variable) for r in result["excluded_outputs"].itertuples()
        }
        annotation_keys = {
            k for k in annotation_keys if (k[1], k[2]) not in excluded_outputs
        }
        annotations = annotations[
            ~annotations.apply(
                lambda r: (r["scenario_id"], r["variable"]) in excluded_outputs, axis=1
            )
        ]

        def metric_keys(metric: str) -> set[tuple[str, str, str]]:
            return {
                (model, scenario_id, variable)
                for model, scenario_id, variable, row in prediction_rows
                if row[metric] < 100
            }

        legacy_threshold_keys = metric_keys("thresholdScore")
        exact_miss_keys = metric_keys("exact")
        below_full_bounded_score_keys = metric_keys("boundedScore")
        counts = expected_audit_counts[country]

        assert len(annotation_keys) == counts["annotated"]
        assert annotation_keys == legacy_threshold_keys
        assert len(exact_miss_keys) == counts["exact_misses"]
        assert (
            len(annotation_keys & exact_miss_keys) == counts["annotated_exact_misses"]
        )
        assert len(annotation_keys - exact_miss_keys) == counts["annotated_exact_hits"]
        assert len(below_full_bounded_score_keys) == counts["below_full_bounded_score"]
        assert (
            len(below_full_bounded_score_keys - annotation_keys)
            == counts["unannotated_below_full_bounded_score"]
        )
        assert len(result["wrong"]) == counts["annotated"]

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
    """Annotations must stay within the frozen legacy-threshold universe."""
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
        # Rows on outputs excluded from scoring stay annotated (as description)
        # but are not wrong rows; each carries its exclusion's descriptive class
        # (or parse_contract_failure for an answer that never parsed).
        excluded = result["excluded_outputs"]
        on_excluded = annotations.merge(
            excluded, on=["scenario_id", "variable"], how="inner"
        )
        assert set(on_excluded["failure_source"]) <= {
            "prompt_ambiguity",
            "reference_engine_defect",
            "reference_later_law",
            "parse_contract_failure",
        }
        scored_annotations = annotations.merge(
            excluded, on=["scenario_id", "variable"], how="left", indicator=True
        )
        scored_annotations = scored_annotations[
            scored_annotations["_merge"] == "left_only"
        ].drop(columns="_merge")
        orphans = scored_annotations[keys].merge(
            result["wrong"][keys].drop_duplicates(), on=keys, how="left", indicator=True
        )
        assert (orphans["_merge"] == "both").all(), orphans[
            orphans["_merge"] != "both"
        ].head()
        assert len(scored_annotations) == len(result["wrong"])


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
    """The frozen data.json.gz must name the policyengine-us that generated the
    references it scores against, as recorded by the reference sidecar and the
    manifest, not the exporting machine's installed runtime."""
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    expected = manifest["reference_output_refresh"]["policyengine_us_version"]
    for country, run_label in manifest["source_run_labels"].items():
        run_dir = ROOT / manifest["source_run_artifacts"][run_label]["path"]
        payload = read_run_payload(run_dir)
        sidecar = json.loads((run_dir / "reference_outputs.csv.meta.json").read_text())
        sidecar_version = sidecar["policyengine_bundles"][country]["model_version"]
        assert sidecar_version == expected
        assert payload["policyengineBundles"][country]["model_version"] == expected


STATED_HOURS = "weekly_hours_worked_before_lsr"


def test_manifest_names_the_build_the_households_came_from():
    """PolicyBench computes each scored reference with policyengine_us.Simulation
    from the household's own listed inputs, so no dataset enters a reference.
    The households came from the build the scenario draw recorded; the
    reference runtime's default dataset, which reference_output_refresh names,
    is a different build that reference computation never reads."""
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    run_label = manifest["source_run_labels"]["us"]
    run_dir = ROOT / manifest["source_run_artifacts"][run_label]["path"]
    drawn = json.loads((run_dir / "scenarios.csv.meta.json").read_text())[
        "policyengine_bundles"
    ]["us"]
    households = manifest["household_dataset"]
    assert households == {
        "source": f"runs/{run_label}/scenarios.csv.meta.json",
        "policyengine_us_data_build_id": drawn["certified_data_build_id"],
        "policyengine_us_dataset": drawn["default_dataset"],
        "policyengine_us_dataset_uri": drawn["default_dataset_uri"],
        "policyengine_us_data_artifact_sha256": drawn["certified_data_artifact_sha256"],
    }
    assert households["policyengine_us_data_build_id"] == (
        "populace-us-2024-5da5a95-20260611"
    )
    refresh = manifest["reference_output_refresh"]
    # The existing keys stay; they describe the reference runtime's bundle.
    assert set(refresh) >= {
        "policyengine_version",
        "policyengine_us_version",
        "policyengine_us_data_build_id",
        "policyengine_us_dataset",
        "policyengine_us_dataset_uri",
        "policyengine_us_data_artifact_sha256",
    }
    assert (
        refresh["policyengine_us_data_build_id"]
        != (households["policyengine_us_data_build_id"])
    )
    note = " ".join(manifest["reproducibility_notes"])
    # Each scored reference also depends on the modules and the builder alias
    # the sidecar's engine_upgrade revision pins: the publication conventions
    # (latest_c_*.py), the Maryland output-scope adapter, and the stated-hours
    # alias its builder note records.
    # A later upgrade (build_references_upgrade.py) inherits the conventions,
    # pins latest_final.py and the sales-tax table beside them, and records its
    # builder's note; the stated-hours alias is the earlier upgrade's, which
    # it builds households through (the delta review's finding 6).
    from scripts import freeze_snapshot

    sidecar = json.loads((run_dir / "reference_outputs.csv.meta.json").read_text())
    upgrades = [r for r in sidecar["revisions"] if r["kind"] == "engine_upgrade"]
    upgrade = upgrades[-1]
    modules = {entry["module"] for entry in upgrade["fix_modules"]}
    conventions = {m for m in modules if m.startswith("latest_c_")}
    base_modules = {"latest_conventions.py", "latest_md_local_output_scope.py"}
    if upgrade["builder"] == freeze_snapshot.UPGRADE_BUILDER:
        assert modules - conventions == base_modules | (
            freeze_snapshot.UPGRADE_SUPPORT_MODULES
        )
        earlier = [u for u in upgrades[:-1] if STATED_HOURS in u["builder"]]
        assert earlier
        assert conventions == {
            e["module"]
            for e in earlier[-1]["fix_modules"]
            if e["module"].startswith("latest_c_")
        }
    else:
        assert modules - conventions == base_modules
        assert STATED_HOURS in upgrade["builder"]
    assert len(conventions) == 9
    assert (
        "PolicyBench computes each scored reference output with "
        "policyengine_us.Simulation from policyengine-us "
        f"{refresh['policyengine_us_version']}, using the household's own "
        "listed inputs, the nine publication conventions, the Maryland "
        "output-scope adapter and the scenario builder's stated-hours alias, as "
        "the reference sidecar's engine_upgrade revision pins them "
        f"(fix_modules, builder); policyengine.py {refresh['policyengine_version']} "
        "is recorded for provenance only."
    ) in note
    assert (
        "The households were drawn from the certified PolicyEngine US populace "
        f"dataset ({households['policyengine_us_data_build_id']}, "
        f"{households['policyengine_us_dataset']})"
    ) in note
    assert "outputs were generated with policyengine.py" not in note
    # The paper guide states both builds from the same records, and what each
    # scored reference depends on.
    guide = re.sub(r"\s+", " ", (ROOT / "docs" / "paper.md").read_text())
    assert (
        "PolicyBench computes each scored reference with "
        "`policyengine_us.Simulation` from the household's own listed inputs, "
        "the nine publication conventions, the Maryland output-scope adapter and "
        "the scenario builder's stated-hours alias, as the reference sidecar's "
        "`engine_upgrade` revision pins them (`fix_modules`, `builder`)"
    ) in guide
    assert f"build {refresh['policyengine_us_data_build_id']}, from the" in guide
    assert f"policyengine.py {refresh['policyengine_version']} bundle" in guide
    assert f"({households['policyengine_us_data_build_id']})" in guide


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
    # A regeneration dates the references by when they were regenerated.
    assert refresh.get("regenerated_at_utc") == sidecar.get("regenerated_at_utc")
    generated = sidecar.get("regenerated_at_utc", sidecar["generated_at_utc"])
    assert refresh["date"] == generated[:10]
    assert refresh["snapshot_date"] == manifest["snapshot_date"]
    assert refresh["date"] <= refresh["snapshot_date"]


UPGRADE_FIXES = "reference_audit/2026-09-28/fixes"
REAL_CONVENTIONS = sorted(
    path.name for path in (ROOT / UPGRADE_FIXES).glob("latest_c_*.py")
)
SUPPORT_PATHS = {
    "latest_final.py": f"{UPGRADE_FIXES}/latest_final.py",
    "r19_irs_sales_tax_2025.json": (
        "reference_audit/2026-09-22/fixes/r19_irs_sales_tax_2025.json"
    ),
}


def _committed_pin(path: str) -> str:
    """The sha256 of a file as committed at HEAD."""
    shown = subprocess.run(
        ["git", "show", f"HEAD:{path}"], cwd=ROOT, check=True, capture_output=True
    )
    return hashlib.sha256(shown.stdout).hexdigest()


def _pinned(module: str, *, path: str | None = None) -> dict:
    """A fix_modules entry pinning a real committed module: the 2026-09-29
    form (no path) unless ``path`` is given, as a later upgrade writes it."""
    entry = {"module": module}
    if path is not None:
        entry["path"] = path
    entry["sha256"] = _committed_pin(path or f"{UPGRADE_FIXES}/{module}")
    return entry


def _MOCK_engine_upgrade(convention_count=9, **changes):
    """A MOCK sidecar revision, never evidence of a real engine build. Its
    modules are real committed conventions at their real pins, as many as
    the test needs, so the freeze's pin checks see committed bytes."""
    assert len(REAL_CONVENTIONS) == 9
    return {
        "kind": "engine_upgrade",
        "fix_modules": [
            _pinned(module) for module in REAL_CONVENTIONS[:convention_count]
        ]
        + [
            _pinned("latest_conventions.py"),
            _pinned("latest_md_local_output_scope.py"),
        ],
        "builder": "MOCK builder: weekly_hours_worked_before_lsr",
        **changes,
    }


def _MOCK_later_upgrade():
    """A MOCK later upgrade in the real builder's form: the inherited modules
    with their paths, plus latest_final.py and the sales-tax table."""
    from scripts import freeze_snapshot

    latest = _MOCK_engine_upgrade(builder=freeze_snapshot.UPGRADE_BUILDER)
    latest["fix_modules"] = [
        _pinned(entry["module"], path=f"{UPGRADE_FIXES}/{entry['module']}")
        for entry in latest["fix_modules"]
    ] + [_pinned(name, path=path) for name, path in SUPPORT_PATHS.items()]
    return latest


@pytest.mark.parametrize("previous_count", [0, 1, 3])
def test_MOCK_engine_setup_uses_the_last_upgrade(tmp_path, monkeypatch, previous_count):
    """Earlier MOCK upgrade modules cannot supply the final upgrade's count."""
    from scripts import freeze_snapshot

    sidecar = tmp_path / "MOCK_reference_outputs.csv.meta.json"
    sidecar.write_text(
        json.dumps(
            {
                "revisions": [_MOCK_engine_upgrade(1) for _ in range(previous_count)]
                + [_MOCK_engine_upgrade(7)]
            }
        )
    )
    monkeypatch.setattr(freeze_snapshot, "REFERENCE_META_SOURCE", sidecar)
    assert freeze_snapshot.read_reference_engine_setup() == {
        "convention_count": 7,
        "output_scope_adapter_count": 1,
    }


@pytest.mark.parametrize(
    ("revisions", "message"),
    [
        ([], "needs a final engine_upgrade revision"),
        ([{"kind": "MOCK_other"}], "needs a final engine_upgrade revision"),
        (
            [_MOCK_engine_upgrade(), {"kind": "MOCK_other"}],
            "needs a final engine_upgrade revision",
        ),
        (
            [_MOCK_engine_upgrade(), _MOCK_engine_upgrade(fix_modules=[])],
            "unexpected engine_upgrade fix_modules",
        ),
        (
            [_MOCK_engine_upgrade(), _MOCK_engine_upgrade(builder="MOCK missing")],
            "names no stated-hours alias",
        ),
    ],
)
def test_MOCK_engine_setup_refuses_an_invalid_last_revision(
    tmp_path, monkeypatch, revisions, message
):
    """A valid earlier MOCK revision cannot rescue invalid final metadata."""
    from scripts import freeze_snapshot

    sidecar = tmp_path / "MOCK_reference_outputs.csv.meta.json"
    sidecar.write_text(json.dumps({"revisions": revisions}))
    monkeypatch.setattr(freeze_snapshot, "REFERENCE_META_SOURCE", sidecar)
    with pytest.raises(SystemExit, match=message):
        freeze_snapshot.read_reference_engine_setup()


@pytest.mark.parametrize(
    ("changes", "missing", "message"),
    [
        ({}, "fix_modules", "fix_modules must be a list of module objects"),
        ({"fix_modules": None}, None, "fix_modules must be a list of module objects"),
        ({"fix_modules": {}}, None, "fix_modules must be a list of module objects"),
        (
            {"fix_modules": "MOCK_module.py"},
            None,
            "fix_modules must be a list of module objects",
        ),
        ({"fix_modules": [None]}, None, "needs a nonempty string module"),
        ({"fix_modules": ["MOCK_module.py"]}, None, "needs a nonempty string module"),
        ({"fix_modules": [{}]}, None, "needs a nonempty string module"),
        ({"fix_modules": [{"module": None}]}, None, "needs a nonempty string module"),
        ({"fix_modules": [{"module": 7}]}, None, "needs a nonempty string module"),
        ({"fix_modules": [{"module": ""}]}, None, "needs a nonempty string module"),
        ({"fix_modules": [{"module": " "}]}, None, "needs a nonempty string module"),
        ({"builder": None}, None, "builder note must be a string"),
        ({"builder": 7}, None, "builder note must be a string"),
        ({"builder": []}, None, "builder note must be a string"),
        ({"builder": {}}, None, "builder note must be a string"),
    ],
)
def test_MOCK_engine_setup_refuses_malformed_last_upgrade_fields(
    tmp_path, monkeypatch, changes, missing, message
):
    """Malformed MOCK final module/builder shapes receive explicit refusals."""
    from scripts import freeze_snapshot

    upgrade = _MOCK_engine_upgrade(**changes)
    if missing is not None:
        del upgrade[missing]
    sidecar = tmp_path / "MOCK_reference_outputs.csv.meta.json"
    sidecar.write_text(json.dumps({"revisions": [_MOCK_engine_upgrade(), upgrade]}))
    monkeypatch.setattr(freeze_snapshot, "REFERENCE_META_SOURCE", sidecar)
    with pytest.raises(SystemExit, match=message):
        freeze_snapshot.read_reference_engine_setup()


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ([], "the reference sidecar must be an object"),
        (None, "the reference sidecar must be an object"),
        ({"revisions": None}, "revisions must be a list of objects"),
        ({"revisions": {}}, "revisions must be a list of objects"),
        ({"revisions": [None]}, "revisions must be a list of objects"),
        ({"revisions": ["MOCK_revision"]}, "revisions must be a list of objects"),
    ],
)
def test_MOCK_engine_setup_refuses_malformed_sidecar_shapes(
    tmp_path, monkeypatch, metadata, message
):
    """A malformed MOCK sidecar container is refused before reading revisions."""
    from scripts import freeze_snapshot

    sidecar = tmp_path / "MOCK_reference_outputs.csv.meta.json"
    sidecar.write_text(json.dumps(metadata))
    monkeypatch.setattr(freeze_snapshot, "REFERENCE_META_SOURCE", sidecar)
    with pytest.raises(SystemExit, match=message):
        freeze_snapshot.read_reference_engine_setup()


@pytest.mark.parametrize(
    ("has_previous_alias", "support_modules", "builder_suffix", "accepted"),
    [
        (True, ["latest_final.py", "r19_irs_sales_tax_2025.json"], "", True),
        (False, ["latest_final.py", "r19_irs_sales_tax_2025.json"], "", False),
        (True, ["latest_final.py"], "", False),
        (True, [], "", False),
        (True, ["latest_final.py", "r19_irs_sales_tax_2025.json"], "MOCK", False),
        (None, ["latest_final.py", "r19_irs_sales_tax_2025.json"], "", False),
    ],
)
def test_MOCK_engine_setup_checks_the_known_upgrade_builder(
    tmp_path,
    monkeypatch,
    has_previous_alias,
    support_modules,
    builder_suffix,
    accepted,
):
    """The known builder route preserves only a recorded MOCK alias lineage."""
    from scripts import freeze_snapshot

    previous = _MOCK_engine_upgrade(
        builder=(
            None
            if has_previous_alias is None
            else (
                "MOCK weekly_hours_worked_before_lsr"
                if has_previous_alias
                else "MOCK missing"
            )
        )
    )
    latest = _MOCK_engine_upgrade(
        builder=freeze_snapshot.UPGRADE_BUILDER + builder_suffix
    )
    latest["fix_modules"] += [
        _pinned(name, path=SUPPORT_PATHS[name]) for name in support_modules
    ]
    sidecar = tmp_path / "MOCK_reference_outputs.csv.meta.json"
    sidecar.write_text(json.dumps({"revisions": [previous, latest]}))
    monkeypatch.setattr(freeze_snapshot, "REFERENCE_META_SOURCE", sidecar)
    if accepted:
        assert freeze_snapshot.read_reference_engine_setup() == {
            "convention_count": 9,
            "output_scope_adapter_count": 1,
        }
    else:
        with pytest.raises(
            SystemExit,
            match="unexpected engine_upgrade fix_modules|names no stated-hours alias",
        ):
            freeze_snapshot.read_reference_engine_setup()


def _zero_pin(module):
    def change(revisions):
        for entry in revisions[-1]["fix_modules"]:
            if entry["module"] == module:
                entry["sha256"] = "0" * 64

    return change


def _move(module, path):
    def change(revisions):
        for entry in revisions[-1]["fix_modules"]:
            if entry["module"] == module:
                entry["path"] = path

    return change


def _duplicate(module):
    def change(revisions):
        entries = revisions[-1]["fix_modules"]
        entries.append(next(dict(e) for e in entries if e["module"] == module))

    return change


def _drift_earlier(module):
    """The earlier upgrade's pin differs: the later one no longer inherits it."""

    def change(revisions):
        for entry in revisions[0]["fix_modules"]:
            if entry["module"] == module:
                entry["sha256"] = "1" * 64

    return change


def _drop_earlier_convention(revisions):
    revisions[0]["fix_modules"] = [
        e for e in revisions[0]["fix_modules"] if e["module"] != REAL_CONVENTIONS[0]
    ]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (None, None),
        # The delta review's case: an all-zero convention hash.
        (_zero_pin(REAL_CONVENTIONS[0]), "pins sha256 '0000"),
        (_zero_pin("latest_final.py"), "pins sha256 '0000"),
        (_zero_pin("r19_irs_sales_tax_2025.json"), "pins sha256 '0000"),
        (
            _move(
                "r19_irs_sales_tax_2025.json",
                f"{UPGRADE_FIXES}/r19_irs_sales_tax_2025.json",
            ),
            "names path",
        ),
        (
            _move(
                "latest_final.py", "reference_audit/2026-09-22/fixes/latest_final.py"
            ),
            "names path",
        ),
        (
            _move(
                REAL_CONVENTIONS[1], f"{UPGRADE_FIXES}/../fixes/{REAL_CONVENTIONS[1]}"
            ),
            "names path",
        ),
        (_duplicate(REAL_CONVENTIONS[2]), "more than once"),
        (_duplicate("latest_final.py"), "more than once"),
        (_drift_earlier(REAL_CONVENTIONS[3]), "not the earlier upgrade's pin"),
        (_drop_earlier_convention, "conventions are not the earlier upgrade's"),
    ],
)
def test_MOCK_a_later_upgrades_pins_are_its_committed_bytes(
    tmp_path, monkeypatch, change, message
):
    """MOCK revisions of real committed modules: a later upgrade's convention
    entries must be the earlier upgrade's pins, and every entry, the two
    support files included, the bytes committed at its path, each once."""
    from scripts import freeze_snapshot

    revisions = [_MOCK_engine_upgrade(), _MOCK_later_upgrade()]
    if change is not None:
        change(revisions)
    sidecar = tmp_path / "MOCK_reference_outputs.csv.meta.json"
    sidecar.write_text(json.dumps({"revisions": revisions}))
    monkeypatch.setattr(freeze_snapshot, "REFERENCE_META_SOURCE", sidecar)
    if message is None:
        assert freeze_snapshot.read_reference_engine_setup() == {
            "convention_count": 9,
            "output_scope_adapter_count": 1,
        }
    else:
        with pytest.raises(SystemExit, match=re.escape(message)):
            freeze_snapshot.read_reference_engine_setup()


def test_the_published_upgrades_pins_are_their_committed_bytes():
    """On the release's own sidecar: every engine_upgrade revision's modules,
    at their (stated or implied) paths, are the committed bytes."""
    from scripts import freeze_snapshot

    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    run_label = manifest["source_run_labels"]["us"]
    run_dir = ROOT / manifest["source_run_artifacts"][run_label]["path"]
    sidecar = json.loads((run_dir / "reference_outputs.csv.meta.json").read_text())
    upgrades = [r for r in sidecar["revisions"] if r["kind"] == "engine_upgrade"]
    for index, upgrade in enumerate(upgrades):
        inherits = upgrade.get("builder") == freeze_snapshot.UPGRADE_BUILDER
        freeze_snapshot.verify_fix_module_pins(
            upgrade["fix_modules"], upgrades[:index] if inherits else []
        )


def test_MOCK_reference_refresh_reads_the_latest_bundle_and_timestamp(
    tmp_path, monkeypatch
):
    """Refresh fields follow the latest MOCK build's top-level sidecar pins."""
    from scripts import freeze_snapshot

    reference = tmp_path / "reference_outputs.csv"
    reference.write_text("scenario_id,variable,value\nMOCK_case,MOCK_variable,7\n")
    bundle = {
        "policyengine_version": "MOCK_python",
        "model_version": "MOCK_latest",
        "certified_data_build_id": "MOCK_build",
        "default_dataset": "MOCK_dataset",
        "default_dataset_uri": "MOCK_uri",
        "certified_data_artifact_sha256": "MOCK_digest",
    }
    sidecar = reference.with_name(reference.name + ".meta.json")
    sidecar.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-06-12T00:00:00Z",
                "regenerated_at_utc": "2026-10-09T12:34:56Z",
                "policyengine_bundles": {"us": bundle},
                "revisions": [_MOCK_engine_upgrade(), _MOCK_engine_upgrade()],
            }
        )
    )
    monkeypatch.setattr(freeze_snapshot, "REFERENCE_META_SOURCE", sidecar)
    monkeypatch.setattr(freeze_snapshot, "RUN_DEST", tmp_path)
    monkeypatch.setattr(freeze_snapshot, "SNAPSHOT_DATE", "2026-10-09")
    assert freeze_snapshot.read_reference_refresh() == {
        "date": "2026-10-09",
        "generated_at_utc": "2026-06-12T00:00:00Z",
        "regenerated_at_utc": "2026-10-09T12:34:56Z",
        "snapshot_date": "2026-10-09",
        "reference_csv_sha256": sha256(reference),
        "row_count": 1,
        "policyengine_version": "MOCK_python",
        "policyengine_us_version": "MOCK_latest",
        "policyengine_us_data_build_id": "MOCK_build",
        "policyengine_us_dataset": "MOCK_dataset",
        "policyengine_us_dataset_uri": "MOCK_uri",
        "policyengine_us_data_artifact_sha256": "MOCK_digest",
    }


def _MOCK_freeze_run_setup(tmp_path, monkeypatch, *, upgraded):
    """A tiny MOCK compact run; no live stage or real freezer main is used."""
    from scripts import freeze_snapshot

    source = tmp_path / "MOCK_source" / "us"
    source.mkdir(parents=True)
    snapshot = tmp_path / "MOCK_snapshot"
    run = snapshot / "runs" / "MOCK_run"
    run.mkdir(parents=True)

    def write_reference(directory, value, version):
        reference = directory / "reference_outputs.csv"
        reference.write_text(
            f"scenario_id,variable,value\nMOCK_case,MOCK_variable,{value}\n"
        )
        metadata = {
            "country": "us",
            "reference_csv_sha256": sha256(reference),
            "row_count": 1,
            "policyengine_bundles": {
                "us": {
                    "model_package": "policyengine-us",
                    "model_version": version,
                    "data_package": "MOCK_data",
                    "data_version": "MOCK_version",
                    "default_dataset": "MOCK_dataset",
                    "default_dataset_uri": "MOCK_uri",
                }
            },
        }
        reference.with_name(reference.name + ".meta.json").write_text(
            json.dumps(metadata)
        )

    write_reference(run, 1, "MOCK_previous")
    write_reference(
        source, 2 if upgraded else 1, "MOCK_upgraded" if upgraded else "MOCK_previous"
    )
    (source / "scenarios.csv").write_text("scenario_id\nMOCK_case\n")
    (source / "scenarios.csv.meta.json").write_text('{"MOCK": "scenario metadata"}')
    (source / "predictions.csv").write_text("MOCK_prediction\n7\n")
    (source / "reference_exclusions.json").write_text('{"MOCK": "exclusions"}')
    (run / "MOCK_preserved").write_text("MOCK pre-freeze sentinel")
    names = ("reference_outputs.csv", "reference_outputs.csv.meta.json")
    committed_pins = {name: sha256(run / name) for name in names}
    replacement_pins = {name: sha256(source / name) for name in names}
    (snapshot / "manifest.json").write_text(
        json.dumps({"source_run_artifacts": {"MOCK_run": {"files": committed_pins}}})
    )
    dashboard = tmp_path / "MOCK_dashboard.json"
    dashboard.write_text(json.dumps({"countries": {"us": {"MOCK": "payload"}}}))
    monkeypatch.setattr(freeze_snapshot, "SOURCE_US", source)
    monkeypatch.setattr(freeze_snapshot, "SNAPSHOT_DIR", snapshot)
    monkeypatch.setattr(freeze_snapshot, "RUN_DEST", run)
    monkeypatch.setattr(freeze_snapshot, "RUN_LABEL", "MOCK_run")
    monkeypatch.setattr(
        freeze_snapshot,
        "REFERENCE_META_SOURCE",
        (source if upgraded else run) / "reference_outputs.csv.meta.json",
    )
    monkeypatch.setattr(
        freeze_snapshot, "REFERENCE_PINS", replacement_pins if upgraded else None
    )
    monkeypatch.setattr(freeze_snapshot, "PUBLISHED_DASHBOARD_SOURCE", dashboard)
    monkeypatch.setattr(
        freeze_snapshot,
        "PUBLISHED_DASHBOARD_ARTIFACT",
        {"bytes": dashboard.stat().st_size, "sha256": sha256(dashboard)},
    )

    def MOCK_analysis(destination):
        destination.mkdir()
        for name in (*freeze_snapshot.ANALYSIS_CSVS, "report.md"):
            (destination / name).write_text("MOCK analysis\n")

    monkeypatch.setattr(freeze_snapshot, "regenerate_analysis", MOCK_analysis)
    return source, run


@pytest.mark.parametrize("upgraded", [False, True])
def test_MOCK_freeze_run_binds_the_right_reference_source(
    tmp_path, monkeypatch, upgraded
):
    """MOCK upgrades validate publish provenance; baseline provenance is unchanged."""
    from scripts import freeze_snapshot

    source, run = _MOCK_freeze_run_setup(tmp_path, monkeypatch, upgraded=upgraded)
    validate = freeze_snapshot.reference_policyengine_bundles
    checked = []

    def record_validation(path, *args, **kwargs):
        checked.append(path)
        return validate(path, *args, **kwargs)

    monkeypatch.setattr(
        freeze_snapshot, "reference_policyengine_bundles", record_validation
    )
    files = freeze_snapshot.freeze_run()
    assert checked == [(source if upgraded else run) / "reference_outputs.csv"]
    assert (run / "reference_outputs.csv").read_bytes() == (
        source / "reference_outputs.csv"
    ).read_bytes()
    assert (run / "reference_outputs.csv.meta.json").read_bytes() == (
        source / "reference_outputs.csv.meta.json"
    ).read_bytes()
    assert files["reference_outputs.csv"] == sha256(source / "reference_outputs.csv")
    assert files["reference_outputs.csv.meta.json"] == sha256(
        source / "reference_outputs.csv.meta.json"
    )


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("reference_outputs.csv", "Publish reference outputs differ"),
        ("reference_outputs.csv.meta.json", "Reference metadata differs"),
    ],
)
def test_MOCK_freeze_run_refuses_changed_replacement_pins_before_writing(
    tmp_path, monkeypatch, name, message
):
    """A changed MOCK replacement CSV or sidecar leaves the old run untouched."""
    from scripts import freeze_snapshot

    source, run = _MOCK_freeze_run_setup(tmp_path, monkeypatch, upgraded=True)
    (source / name).write_bytes((source / name).read_bytes() + b" ")
    previous = {path.name: path.read_bytes() for path in run.iterdir()}
    with pytest.raises(SystemExit, match=message):
        freeze_snapshot.freeze_run()
    assert {path.name: path.read_bytes() for path in run.iterdir()} == previous


def test_MOCK_freeze_run_refuses_inconsistent_replacement_provenance_before_writing(
    tmp_path, monkeypatch
):
    """Correct MOCK file pins cannot rescue a sidecar with an incorrect CSV pin."""
    from policybench.full_run_export import ReferenceProvenanceError
    from scripts import freeze_snapshot

    source, run = _MOCK_freeze_run_setup(tmp_path, monkeypatch, upgraded=True)
    sidecar = source / "reference_outputs.csv.meta.json"
    metadata = json.loads(sidecar.read_text())
    metadata["reference_csv_sha256"] = "MOCK_wrong"
    sidecar.write_text(json.dumps(metadata))
    monkeypatch.setattr(
        freeze_snapshot,
        "REFERENCE_PINS",
        {
            "reference_outputs.csv": sha256(source / "reference_outputs.csv"),
            "reference_outputs.csv.meta.json": sha256(sidecar),
        },
    )
    previous = {path.name: path.read_bytes() for path in run.iterdir()}
    with pytest.raises(ReferenceProvenanceError, match="hash does not match"):
        freeze_snapshot.freeze_run()
    assert {path.name: path.read_bytes() for path in run.iterdir()} == previous


def _frozen_run_dir(manifest: dict) -> Path:
    run_label = manifest["source_run_labels"]["us"]
    return ROOT / manifest["source_run_artifacts"][run_label]["path"]


def test_frozen_predictions_and_usage_summary_agree_on_the_last_answer():
    """Two computations of the last answer agree: the freezer's window, from
    the frozen predictions, and the frozen usage summary's latest
    last_request_at, which policybench.analysis aggregates per model."""
    from scripts.freeze_snapshot import _utc_date, model_response_window

    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    run_dir = _frozen_run_dir(manifest)
    start = manifest["model_response_date"].split(" to ")[0]
    window = model_response_window(run_dir / "predictions.csv.gz", start)
    usage = pd.read_csv(run_dir / "analysis" / "usage_summary.csv")
    assert window == f"{start} to {_utc_date(usage['last_request_at'].max())}"


def test_model_response_window_ends_on_the_last_frozen_answer():
    """The manifest's window ends on the UTC date of the last answer the frozen
    predictions record, not on the release date, and its reproducibility
    notes state the same window."""
    from scripts.freeze_snapshot import _response_window_phrase, model_response_window

    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    start = manifest["model_response_date"].split(" to ")[0]
    window = model_response_window(
        _frozen_run_dir(manifest) / "predictions.csv.gz", start
    )
    assert manifest["model_response_date"] == window
    notes = " ".join(manifest["reproducibility_notes"])
    assert f"between {_response_window_phrase(window)}, as models" in notes
    assert f"recorded {window} response window" in notes


def test_rendered_paper_states_the_manifest_response_window():
    """The rendered manuscript's snapshot table names the manifest's window, so
    a manifest corrected without a re-render fails here."""
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    web = ROOT / manifest["rendered_paper_artifacts"]["web"]["path"]
    page = (web / "index.html").read_text()
    cells = re.findall(r"<td>Model response date</td>\s*<td>([^<]*)</td>", page)
    assert cells == [manifest["model_response_date"]]


def test_app_copy_of_serving_configuration_matches_the_frozen_file():
    """The scenario explorer bundles a copy of the frozen serving config.

    prepare-data refreshes it when the repository is present; the copy is
    tracked so tests and Vercel builds that see only app/ still have it.
    """
    frozen = ROOT / "paper" / "snapshot" / "20260501" / "model_serving_config.json"
    app_copy = ROOT / "app" / "src" / "model-serving-config.json"
    assert app_copy.read_bytes() == frozen.read_bytes()


def test_app_clean_preserves_the_tracked_serving_configuration():
    package = json.loads((ROOT / "app" / "package.json").read_text())
    clean_command = package["scripts"]["clean"]

    assert "src/model-serving-config.json" not in clean_command
    assert "src/paperSnapshot.json" not in clean_command


def test_manuscript_bootstrap_point_estimates_reproduce_model_stats():
    """The manuscript's uncertainty tables score the same outputs as the board.

    Mirrors ``load_snapshot_ground_truth`` / ``load_snapshot_predictions`` in
    paper/index.qmd: the scored reference (frozen CSV minus the exclusion
    record), filtered to headline outputs, fed to ``bootstrap_headline_cis``.
    Its point estimate for every model must equal the published exact score;
    a reference that still carried the excluded outputs would not.
    """
    from policybench.analysis import bootstrap_headline_cis
    from policybench.reference_exclusions import scored_reference_for
    from policybench.spec import get_output_ids

    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    for country, run_label in manifest["source_run_labels"].items():
        run_dir = ROOT / manifest["source_run_artifacts"][run_label]["path"]
        headline = set(get_output_ids(country, "headline"))

        def headline_only(frame: pd.DataFrame) -> pd.DataFrame:
            mask = frame["variable"].map(output_group_id).isin(headline)
            frame = frame[mask].reset_index(drop=True)
            frame["scenario_id"] = frame["scenario_id"].astype(str)
            return frame

        scored, exclusions = scored_reference_for(run_dir / "reference_outputs.csv")
        assert len(exclusions) > 0
        reference = headline_only(scored)
        predictions = headline_only(
            pd.read_csv(
                run_dir / "predictions.csv.gz",
                usecols=["model", "scenario_id", "variable", "prediction"],
            )
        )
        scenarios = pd.read_csv(run_dir / "scenarios.csv")
        market = dict(
            zip(
                scenarios["scenario_id"].astype(str),
                pd.to_numeric(scenarios["total_income"], errors="coerce").fillna(0.0),
            )
        )
        cis = bootstrap_headline_cis(
            reference, predictions, market, country=country, metric="exact", n_boot=20
        )
        published = {
            row["model"]: row["exact"]
            for row in read_run_payload(run_dir)["modelStats"]
            if row["condition"] == "no_tools"
        }
        assert set(cis["model"]) == set(published)
        for model, point in zip(cis["model"], cis["point"]):
            assert point * 100 == pytest.approx(published[model], abs=1e-6), model


def test_frozen_impact_summaries_score_the_scored_reference():
    """The legacy impact summary (run dir and top-level copy) must be computed
    on the scored reference, like every other published metric."""
    from policybench.reference_exclusions import scored_reference_for
    from scripts import freeze_snapshot

    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    for country, run_label in manifest["source_run_labels"].items():
        run_dir = ROOT / manifest["source_run_artifacts"][run_label]["path"]
        scored, exclusions = scored_reference_for(run_dir / "reference_outputs.csv")
        assert exclusions
        predictions = pd.read_csv(run_dir / "predictions.csv.gz")
        expected = freeze_snapshot.household_impact_summary_by_model(
            scored, predictions
        )
        frozen = pd.read_csv(run_dir / "analysis" / "impact_summary_by_model.csv")
        top_level = pd.read_csv(SNAPSHOT_DIR / f"{country}_impact_summary_by_model.csv")
        pd.testing.assert_frame_equal(
            frozen.sort_values("model").reset_index(drop=True),
            expected.sort_values("model").reset_index(drop=True),
            check_exact=False,
            atol=1e-9,
        )
        pd.testing.assert_frame_equal(top_level, frozen)
