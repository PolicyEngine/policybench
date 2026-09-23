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
DECIDED_ON = "2026-09-22"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _references() -> dict[tuple[str, str], float]:
    with (RUN_DIR / "reference_outputs.csv").open(newline="") as source:
        return {
            (row["scenario_id"], row["variable"]): float(row["value"])
            for row in csv.DictReader(source)
        }


def _exclusions() -> list[dict]:
    return _load(RUN_DIR / "reference_exclusions.json")["exclusions"]


def _causes() -> dict[str, dict]:
    return {
        name: cause
        for name, cause in _load(AUDIT / "root_causes.json").items()
        if isinstance(cause, dict)
    }


def _moves() -> list[dict]:
    with (AUDIT / "sweep_moves.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    for row in rows:
        for field in ("frozen", "baseline", "recomputed", "delta"):
            row[field] = float(row[field])
        row["moved_over_1"] = row["moved_over_1"] == "True"
    return rows


def _is_flag(variable: str) -> bool:
    return variable.endswith("_eligible")


def test_sweep_rows_are_internally_consistent():
    causes = _causes()
    rows = _moves()
    assert rows
    for row in rows:
        key = (row["root_cause"], row["scenario_id"], row["variable"])
        assert abs(row["delta"] - (row["recomputed"] - row["baseline"])) < 1e-4, key
        if _is_flag(row["variable"]):
            moved = row["recomputed"] != row["baseline"]
        else:
            moved = abs(row["recomputed"] - row["baseline"]) > 1
        assert row["moved_over_1"] == moved, key
        if row["class"] == "screen":
            continue
        cause = causes[row["root_cause"]]
        assert row["class"] == cause["class"], key
        # Only the SNAP rounding defects are measured against a convention.
        expected = cause.get("measured_against", "frozen")
        assert row["measured_against"] == expected, key
        if expected == "frozen":
            assert row["baseline"] == row["frozen"], key


def test_every_regenerated_reference_names_a_committed_fix():
    meta = _load(RUN_DIR / "reference_outputs.csv.meta.json")
    causes = _causes()
    references = _references()
    excluded = {(e["scenario_id"], e["variable"]) for e in _exclusions()}
    convention_rows = {}
    for row in _moves():
        if row["class"] == "convention":
            convention_rows.setdefault(row["root_cause"], {})[
                (row["scenario_id"], row["variable"])
            ] = row
    assert meta["revisions"]
    for revision in meta["revisions"]:
        module = AUDIT / "fixes" / revision["fix_module"]
        assert module.exists(), revision["fix_module"]
        digest = hashlib.sha256(module.read_bytes()).hexdigest()
        assert digest == revision["fix_module_sha256"], revision["fix_module"]
        convention = revision["convention"]
        assert causes[convention]["class"] == "convention"
        changed = {(c["scenario_id"], c["variable"]): c for c in revision["changed"]}
        for key, change in changed.items():
            # A regenerated reference is scored and is the frozen CSV's value.
            assert key not in excluded, key
            assert abs(references[key] - change["regenerated"]) < 1e-6, key
        # The convention regenerates exactly the scored outputs its sweep moves,
        # to the value its sweep computes.
        swept = {
            key: row
            for key, row in convention_rows.get(convention, {}).items()
            if key not in excluded
        }
        assert set(swept) == set(changed), convention
        for key, row in swept.items():
            assert abs(row["recomputed"] - changed[key]["regenerated"]) < 1e-3, key


def test_every_new_exclusion_has_a_qualifying_move_of_its_class():
    causes = _causes()
    moved = {}
    for row in _moves():
        if row["moved_over_1"]:
            moved.setdefault((row["scenario_id"], row["variable"]), []).append(row)
    unlisted_texts = {
        name: cause["unlisted_input"]
        for name, cause in causes.items()
        if cause.get("class") == "unlisted_input"
    }
    new = [e for e in _exclusions() if e["decided_on"] == DECIDED_ON]
    assert new
    for entry in new:
        key = (entry["scenario_id"], entry["variable"])
        rows = moved.get(key, [])
        if entry["reason_code"] == "reference_engine_defect":
            named = set(entry["root_cause"].split("+"))
            supporting = {
                row["root_cause"] for row in rows if row["class"] == "engine_defect"
            }
            assert named <= supporting, (key, named, supporting)
            continue
        assert entry["reason_code"] == "reference_depends_on_unlisted_input", key
        supporting = [
            row["root_cause"]
            for row in rows
            if row["class"] == "unlisted_input"
            and unlisted_texts[row["root_cause"]] in entry["unlisted_input"]
        ]
        assert supporting, (key, entry["unlisted_input"])


def test_no_qualifying_move_is_left_scored():
    """Every output a defect fix or an unlisted-input reading moves is excluded."""
    causes = _causes()
    excluded = {(e["scenario_id"], e["variable"]) for e in _exclusions()}
    for row in _moves():
        if row["class"] not in ("engine_defect", "unlisted_input"):
            continue
        if not row["moved_over_1"]:
            continue
        key = (row["scenario_id"], row["variable"])
        not_confirmed = causes[row["root_cause"]].get("not_confirmed", {})
        if f"{key[0]}:{key[1]}" in not_confirmed:
            continue
        assert key in excluded, (row["root_cause"], key)


def test_snap_net_income_procedures_move_no_scored_reference():
    excluded = {(e["scenario_id"], e["variable"]) for e in _exclusions()}
    with (AUDIT / "snap_net_income_sensitivity.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    assert rows
    for row in rows:
        assert (row["scenario_id"], row["variable"]) in excluded, row["scenario_id"]
