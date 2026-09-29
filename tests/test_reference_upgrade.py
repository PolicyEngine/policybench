"""The 2026-09-28 engine upgrade: every reference change is reviewed and reproducible.

Max, 2026-09-28: references come from the newest policyengine-us, with the
conventions that hold law published before the 2026-07-03 freeze re-expressed
for it. reference_audit/2026-09-28 records the modules, the per-output sweep,
and each root-cause cluster's investigation and independent review.
"""

from __future__ import annotations

import csv
import hashlib
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "reference_audit" / "2026-09-28"
RUN_DIR = (
    ROOT
    / "paper"
    / "snapshot"
    / "20260501"
    / "runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
)
ENGINE = "2.15.17"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _upgrade() -> dict:
    revisions = _load(RUN_DIR / "reference_outputs.csv.meta.json")["revisions"]
    upgrades = [r for r in revisions if r["kind"] == "engine_upgrade"]
    assert len(upgrades) == 1 and revisions[-1] is upgrades[0]
    return upgrades[0]


def _references() -> dict[tuple[str, str], float]:
    with (RUN_DIR / "reference_outputs.csv").open(newline="") as source:
        return {
            (r["scenario_id"], r["variable"]): float(r["value"])
            for r in csv.DictReader(source)
        }


def _sweep() -> dict[tuple[str, str], dict]:
    with (AUDIT / "sweep_moves.csv").open(newline="") as source:
        return {(r["scenario_id"], r["variable"]): r for r in csv.DictReader(source)}


def _exclusions() -> dict[tuple[str, str], dict]:
    records = _load(RUN_DIR / "reference_exclusions.json")["exclusions"]
    return {(e["scenario_id"], e["variable"]): e for e in records}


def test_engine_and_provenance_name_the_newest_release():
    upgrade = _upgrade()
    assert upgrade["engine_version"] == f"policyengine-us {ENGINE}"
    assert upgrade["previous_engine_version"] == "policyengine-us 1.755.4"
    bundle = _load(RUN_DIR / "reference_outputs.csv.meta.json")["policyengine_bundles"][
        "us"
    ]
    assert bundle["model_version"] == ENGINE
    assert bundle["model_matches_policyengine_bundle"] is False
    pins = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
        "dependencies"
    ]
    assert f"policyengine-us=={ENGINE}" in pins
    assert f"policyengine=={bundle['policyengine_version']}" in pins


def test_every_module_the_revision_names_is_committed_unchanged():
    for entry in _upgrade()["fix_modules"]:
        path = AUDIT / "fixes" / entry["module"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], path


def test_the_sweep_table_is_the_committed_reference():
    references = _references()
    sweep = _sweep()
    exclusions = _exclusions()
    assert set(sweep) == set(references) and len(sweep) == 1984
    for key, row in sweep.items():
        assert abs(float(row["reference"]) - references[key]) < 1e-6, key
        assert (row["excluded"] == "True") == (key in exclusions), key
        record = exclusions.get(key)
        if record is None or record["decided_on"] == "2026-09-29":
            # Scored, or excluded in this wave: the engine value is the reference.
            assert abs(float(row["final"]) - references[key]) < 1e-3, key
        else:
            # Excluded earlier: keeps the value its record was decided on.
            assert abs(float(row["board_20260922c"]) - references[key]) < 1e-6, key


def test_every_changed_reference_is_listed_and_reviewed():
    references = _references()
    sweep = _sweep()
    actions = _load(AUDIT / "final_actions.json")
    clusters = {c["id"]: c for c in _load(AUDIT / "clusters.json")["clusters"]}
    approved = {(a["scenario_id"], a["variable"]) for a in actions["approved"]}
    added = {(e["scenario_id"], e["variable"]) for e in actions["new_exclusions"]}
    changed = {(c["scenario_id"], c["variable"]): c for c in _upgrade()["changed"]}
    board = {k: float(r["board_20260922c"]) for k, r in sweep.items()}
    differ = {k for k in references if abs(references[k] - board[k]) > 1e-9}
    assert differ == set(changed)
    for key, change in changed.items():
        assert abs(change["regenerated"] - references[key]) < 1e-9, key
        assert abs(change["previous"] - board[key]) < 1e-9, key
        within_one = abs(change["regenerated"] - change["previous"]) <= 1.0
        assert key in approved or key in added or within_one, key
    record = _load(AUDIT / "clusters.json")
    reconciled = {
        (r["scenario_id"], r["variable"]): r for r in record["reconciliations"]
    }
    for key in approved | added:
        row = sweep[key]
        expected = "adopt_latest" if key in approved else "exclude_unfixed_defect"
        if key in reconciled:
            # Overridden only on another cluster's review that names the output.
            entry = reconciled[key]
            cited = clusters[entry["cites_review"]]["review"]
            assert key in added and entry["final_action"] == "exclude_unlisted_input"
            assert any(key[0].removeprefix("scenario_") in p for p in cited["problems"])
            continue
        review = {
            (c["scenario_id"], c["variable"]): c
            for c in clusters[row["cluster"]]["review"]["corrected_per_output"]
        }[key]
        assert review["action"] == expected, (key, review["action"])


def test_every_output_that_moves_has_a_reviewed_cluster():
    clusters = {c["id"]: c for c in _load(AUDIT / "clusters.json")["clusters"]}
    for key, row in _sweep().items():
        if row["moved_vs_board"] != "True":
            continue
        cluster = clusters[row["cluster"]]
        assert key in {(o["scenario_id"], o["variable"]) for o in cluster["outputs"]}
        assert cluster["review"]["corrected_per_output"], row["cluster"]


def test_new_exclusions_are_computed_on_the_newest_engine():
    added = [e for e in _exclusions().values() if e["decided_on"] == "2026-09-29"]
    references = _references()
    assert len(added) == 3
    for entry in added:
        key = (entry["scenario_id"], entry["variable"])
        assert entry["reason_code"] == "reference_depends_on_unlisted_input"
        assert entry["engine_version"] == f"policyengine-us {ENGINE}"
        assert abs(entry["frozen_value"] - references[key]) < 1e-3, key
        assert abs(entry["alternative_value"] - entry["frozen_value"]) > 1, key
