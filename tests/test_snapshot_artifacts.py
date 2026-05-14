"""Checks for the frozen manuscript snapshot artifacts."""

import hashlib
import json
from pathlib import Path

import pandas as pd

from policybench.analysis import build_global_dashboard_payload

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "paper" / "snapshot" / "20260501"


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


def _snapshot_country_payloads(manifest: dict) -> dict[str, dict]:
    payloads = {}
    for country, run_label in manifest["source_run_labels"].items():
        run_dir = ROOT / manifest["source_run_artifacts"][run_label]["path"]
        payloads[country] = json.loads((run_dir / "data.json").read_text())
    return payloads


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
    dashboard = {
        "countries": country_payloads,
        "global": build_global_dashboard_payload(country_payloads),
    }

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

    shared_models = manifest["scope"]["models"]
    assert len(dashboard["global"]["modelStats"]) == shared_models
    assert dashboard["global"]["modelStats"][0]["model"] == "gpt-5.5"


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
