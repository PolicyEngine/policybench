"""The committed reference audit backs every regenerated reference and exclusion."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "reference_audit" / "2026-09-22"
RUN_DIR = (
    ROOT
    / "paper"
    / "snapshot"
    / "20260501"
    / "runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _references() -> dict[tuple[str, str], float]:
    with (RUN_DIR / "reference_outputs.csv").open(newline="") as source:
        return {
            (row["scenario_id"], row["variable"]): float(row["value"])
            for row in csv.DictReader(source)
        }


def test_every_regenerated_reference_names_a_committed_fix():
    meta = _load(RUN_DIR / "reference_outputs.csv.meta.json")
    causes = _load(AUDIT / "root_causes.json")
    references = _references()
    exclusions = {
        (entry["scenario_id"], entry["variable"])
        for entry in _load(RUN_DIR / "reference_exclusions.json")["exclusions"]
    }
    assert meta["revisions"]
    for revision in meta["revisions"]:
        module = AUDIT / "fixes" / revision["fix_module"]
        assert module.exists(), revision["fix_module"]
        digest = hashlib.sha256(module.read_bytes()).hexdigest()
        assert digest == revision["fix_module_sha256"], revision["fix_module"]
        assert causes[revision["convention"]]["class"] == "convention"
        for change in revision["changed"]:
            key = (change["scenario_id"], change["variable"])
            # A regenerated reference is scored and is the frozen CSV's value.
            assert key not in exclusions, key
            assert abs(references[key] - change["regenerated"]) < 1e-6, key


def test_every_exclusion_names_a_recorded_root_cause_or_input():
    causes = _load(AUDIT / "root_causes.json")
    defect_causes = {
        name
        for name, cause in causes.items()
        if isinstance(cause, dict) and cause.get("class") == "engine_defect"
    }
    unlisted_inputs = {
        cause["unlisted_input"]
        for cause in causes.values()
        if isinstance(cause, dict) and cause.get("class") == "unlisted_input"
    }
    for entry in _load(RUN_DIR / "reference_exclusions.json")["exclusions"]:
        if entry["reason_code"] == "reference_engine_defect":
            assert set(entry["root_cause"].split("+")) <= defect_causes, entry
            continue
        assert entry["reason_code"] == "reference_depends_on_unlisted_input"
        if entry["decided_on"] == "2026-09-22":
            # Each named input is one recorded root cause's, or a join of several.
            named = entry["unlisted_input"].split(" and ")
            assert any(
                entry["unlisted_input"] == value for value in unlisted_inputs
            ) or all(
                any(part in value for value in unlisted_inputs) for part in named
            ), entry["unlisted_input"]


def test_sweep_moves_cover_every_exclusion_and_regeneration():
    with (AUDIT / "sweep_moves.csv").open(newline="") as source:
        moves = {
            (row["scenario_id"], row["variable"])
            for row in csv.DictReader(source)
            if row["root_cause"] != "r18_hold_all_projections"
        }
    meta = _load(RUN_DIR / "reference_outputs.csv.meta.json")
    regenerated = {
        (change["scenario_id"], change["variable"])
        for revision in meta["revisions"]
        for change in revision["changed"]
    }
    new_exclusions = {
        (entry["scenario_id"], entry["variable"])
        for entry in _load(RUN_DIR / "reference_exclusions.json")["exclusions"]
        if entry["decided_on"] == "2026-09-22"
    }
    assert regenerated <= moves
    assert new_exclusions <= moves
