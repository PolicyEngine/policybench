"""Checks for the frozen manuscript snapshot artifacts."""

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "paper" / "snapshot" / "20260501"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_snapshot_manifest_hashes_match_committed_artifacts():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    artifacts = manifest["committed_snapshot_artifacts"]

    assert artifacts
    for filename, expected_hash in artifacts.items():
        path = SNAPSHOT_DIR / filename
        assert path.exists(), f"Missing snapshot artifact: {filename}"
        assert sha256(path) == expected_hash


def test_snapshot_manifest_matches_dashboard_export():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    dashboard_path = ROOT / manifest["dashboard_export"]["path"]
    assert sha256(dashboard_path) == manifest["dashboard_export"]["sha256"]
    dashboard = json.loads(dashboard_path.read_text())

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
