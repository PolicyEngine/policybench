"""The 2026-09-29 engine upgrade: every reference change is reviewed and reproducible.

References come from the newest policyengine-us release when PolicyBench begins
the reference sweep, with the conventions that hold law published before the
2026-07-03 freeze re-expressed for it (Max's ruling, 2026-09-28); at publication
PolicyBench checks that the newest release gives the same values. PolicyBench
began sweeping the references on policyengine-us 2.15.17 at 01:42 UTC on
2026-09-29, built them at 11:57 UTC and rebuilt them (record text only) later
that day, and checked them on 2.17.0, the release current at publication.
reference_audit/2026-09-28 records the modules, the per-output sweeps, and each
root-cause cluster's investigation and independent review. Its directory name
is the US Eastern date the wave began; the records date the upgrade by its UTC
day, 2026-09-29.
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


UPGRADE_DATE = "2026-09-29"


def test_the_records_date_the_upgrade_by_its_utc_day():
    """The revision, the exclusion record's derivation, each new exclusion's
    note and decided_on, and each new-exclusion basis in the sidecar name the
    upgrade's UTC day. The ruling's own date is labeled as Max's."""
    upgrade = _upgrade()
    assert upgrade["date"] == UPGRADE_DATE
    assert (
        _load(RUN_DIR / "reference_outputs.csv.meta.json")["regenerated_at_utc"][:10]
        == UPGRADE_DATE
    )
    exclusions = _load(RUN_DIR / "reference_exclusions.json")
    assert (
        f"On {UPGRADE_DATE} the references moved to policyengine-us {ENGINE}"
        in (exclusions["derivation"])
    )
    decided = {(e["scenario_id"], e["variable"]): e for e in exclusions["exclusions"]}
    new = [
        c
        for c in upgrade["changed"]
        if c["cause"] == "excluded_reference_depends_on_unlisted_input"
    ]
    assert len(new) == 3
    for change in new:
        record = decided[(change["scenario_id"], change["variable"])]
        assert record["decided_on"] == UPGRADE_DATE
        assert change["basis"].startswith(
            f"Newly excluded from scoring on {record['decided_on']} "
        )
        assert f"Found in the {UPGRADE_DATE} engine upgrade" in record["note"]
    for path in (
        RUN_DIR / "reference_exclusions.json",
        RUN_DIR / "reference_outputs.csv.meta.json",
        AUDIT / "final_actions.json",
        ROOT
        / "annotations/us_full_run_20260612_policyengine_4_16_1_populace"
        / "us_adjudications.json",
        ROOT
        / "annotations/us_full_run_20260612_policyengine_4_16_1_populace"
        / "us_case_notes.csv",
    ):
        text = path.read_text().replace("reference_audit/2026-09-28", "")
        for index in [i for i in range(len(text)) if text.startswith("2026-09-28", i)]:
            assert "Max's ruling, 2026-09-28" in text[index - 20 : index + 10], (
                path.name,
                text[index - 80 : index + 40],
            )


def test_the_engine_rule_is_anchored_to_the_sweep():
    """Lead's ruling on the wording: "newest" holds at a stated time."""
    rule = (
        "References come from the newest policyengine-us release when PolicyBench "
        "begins the reference sweep; at publication PolicyBench checks that the "
        "newest release gives the same values."
    )
    assert rule in _upgrade()["rule"]
    assert "Max's ruling, 2026-09-28" in _upgrade()["rule"]
    readme = " ".join((AUDIT / "README.md").read_text().split())
    assert "1. " + rule in readme


def test_the_sweep_began_while_the_reference_engine_was_the_newest_release():
    """verification/sweep_timing.json: the sweep began after policyengine-us
    2.15.17 was uploaded and before 2.16.0 was, and the publication check ran
    on 2.17.0 after its upload, while it was still the newest release."""
    timing = _load(AUDIT / "verification" / "sweep_timing.json")
    uploaded = timing["pypi"]["wheel_uploaded_at_utc"]
    sweep = timing["reference_sweep"]
    assert sweep["engine"] == ENGINE
    releases = sorted(uploaded, key=lambda v: tuple(int(p) for p in v.split(".")))
    following = releases[releases.index(ENGINE) + 1]
    assert following == "2.16.0"
    assert (
        uploaded[ENGINE]
        < sweep["engine_installed_at_utc"]
        <= sweep["script_written_at_utc"]
        <= sweep["first_output_at_utc"]
        < uploaded[following]
    )
    assert sweep["pin_commit"]["committed_at_utc"] < uploaded[following]
    check = timing["publication_check"]
    assert check["engine"] == VERIFICATION_ENGINE == timing["pypi"]["newest_at_read"]
    assert (
        uploaded[VERIFICATION_ENGINE]
        < check["engine_installed_at_utc"]
        <= check["output_at_utc"]
        < timing["pypi"]["read_at_utc"]
    )
    # The build followed the sweep, and the stated times are the recorded ones.
    rebuilt = _load(RUN_DIR / "reference_outputs.csv.meta.json")["regenerated_at_utc"]
    assert sweep["first_output_at_utc"] < rebuilt.replace("+00:00", "Z")
    readme = " ".join((AUDIT / "README.md").read_text().split())
    assert f"rebuilt them at {rebuilt[11:16]} UTC" in readme
    assert f"(uploaded {uploaded[ENGINE][11:16]} UTC)" in readme
    assert (
        f"(uploaded {uploaded[VERIFICATION_ENGINE][:10]} "
        f"{uploaded[VERIFICATION_ENGINE][11:16]} UTC)"
    ) in readme
    assert f"began at {sweep['first_output_at_utc'][11:16]} UTC" in readme


def test_the_pin_commit_time_in_the_timing_record_is_gits():
    """Differential check of the timing record against git, where available."""
    import datetime
    import subprocess

    pin = _load(AUDIT / "verification" / "sweep_timing.json")["reference_sweep"][
        "pin_commit"
    ]
    shown = subprocess.run(
        ["git", "-C", str(ROOT), "log", "-1", "--format=%cI%n%s", pin["commit"]],
        capture_output=True,
        text=True,
    )
    if shown.returncode != 0:
        import pytest

        pytest.skip("git history unavailable")
    when, subject = shown.stdout.strip().split("\n", 1)
    utc = datetime.datetime.fromisoformat(when).astimezone(datetime.timezone.utc)
    assert utc.strftime("%Y-%m-%dT%H:%M:%SZ") == pin["committed_at_utc"]
    assert subject == pin["subject"]
