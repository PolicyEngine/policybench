"""The 2026-09-29 engine upgrade: every reference change is reviewed and reproducible.

Max, 2026-09-28: references come from the newest policyengine-us, with the
conventions that hold law published before the 2026-07-03 freeze re-expressed
for it. PolicyBench began sweeping the references on policyengine-us 2.15.17 on
2026-09-29, rebuilt them at 11:57 UTC, and checked them on 2.17.0, the release
current at publication. reference_audit/2026-09-28 records the modules, the
per-output sweeps, and each root-cause cluster's investigation and independent
review.
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
# The release current at publication, and its sweep under the same fix module.
VERIFICATION_ENGINE = "2.17.0"
VERIFICATION_CSV = AUDIT / "verification" / "latest_final_2170.csv"
VERIFICATION_LOG = AUDIT / "verification" / "latest_final_2170.log"


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


def test_engine_and_provenance_name_the_recorded_release():
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


def test_new_exclusions_are_computed_on_the_reference_engine():
    added = [e for e in _exclusions().values() if e["decided_on"] == "2026-09-29"]
    references = _references()
    assert len(added) == 3
    for entry in added:
        key = (entry["scenario_id"], entry["variable"])
        assert entry["reason_code"] == "reference_depends_on_unlisted_input"
        assert entry["engine_version"] == f"policyengine-us {ENGINE}"
        assert abs(entry["frozen_value"] - references[key]) < 1e-3, key
        assert abs(entry["alternative_value"] - entry["frozen_value"]) > 1, key


def _verification_rows() -> dict[tuple[str, str], dict]:
    with VERIFICATION_CSV.open(newline="") as source:
        return {(r["scenario_id"], r["variable"]): r for r in csv.DictReader(source)}


def test_the_publication_release_recomputes_every_scored_reference():
    """policyengine-us 2.17.0, run with the fix module the references were
    built with (latest_final: the ported conventions and the Maryland adapter),
    gives the committed value for every scored output."""
    rows = _verification_rows()
    references = _references()
    exclusions = _exclusions()
    assert set(rows) == set(references) and len(rows) == 1984
    assert {row["engine"] for row in rows.values()} == {VERIFICATION_ENGINE}
    assert {row["fix"] for row in rows.values()} == {"latest_final"}
    scored = set(references) - set(exclusions)
    assert len(scored) == 1929
    for key in scored:
        assert float(rows[key]["recomputed"]) == references[key], key
    # The sweep's frozen column is the committed reference, so its "moved"
    # outputs are excluded ones: the 19 the upgrade rechecked, each at the
    # value the sidecar records for 2.15.17.
    rechecked = {
        (r["scenario_id"], r["variable"]): r
        for r in _upgrade()["excluded_outputs_rechecked"]
    }
    moved = {key for key, row in rows.items() if row["moved"] == "True"}
    assert moved == set(rechecked) and moved <= set(exclusions)
    for key, record in rechecked.items():
        assert float(rows[key]["recomputed"]) == record["value_on_2_15_17"], key
    log = VERIFICATION_LOG.read_text().splitlines()
    assert log[0] == f"policyengine-us {VERIFICATION_ENGINE}"
    assert log[-1] == (
        f"SUMMARY fix=latest_final outputs=1984 moved={len(rechecked)} "
        "small_nonzero_deltas=0"
    )


def test_the_publication_release_agrees_with_the_reference_engine_everywhere():
    """2.17.0 and 2.15.17 give the same value for all 1,984 outputs under the
    same conventions and adapter (sweep_moves.csv's final column is 2.15.17
    with latest_final, written to fewer significant digits)."""
    rows = _verification_rows()
    sweep = _sweep()
    assert set(rows) == set(sweep)
    for key, row in rows.items():
        assert abs(float(row["recomputed"]) - float(sweep[key]["final"])) < 1e-9, key
