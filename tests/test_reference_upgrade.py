"""The 2026-09-29 engine upgrade: every reference change is reviewed and reproducible.

References come from the newest policyengine-us release when PolicyBench begins
the reference sweep, with the conventions that hold law published before the
2026-07-03 freeze re-expressed for it (Max's ruling, 2026-09-28); before
publishing, PolicyBench checks that the newest release on PyPI gives the same
values and records when it checked. PolicyBench began sweeping the references
on policyengine-us 2.15.17 at 01:42 UTC on 2026-09-29, built them at 11:57 UTC
and rebuilt them (record text only) later that day, and checked them on 2.17.0,
the newest release when it read PyPI at 14:58 UTC that day.
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
# The newest release when PolicyBench checked PyPI before publishing, and its
# sweep under the same fix module.
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


def _builder():
    """build_references_latest.py, for its record functions (no engine import)."""
    import importlib.util
    import sys

    path = AUDIT / "scripts" / "build_references_latest.py"
    spec = importlib.util.spec_from_file_location("build_references_latest", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_each_rechecked_reason_is_the_reviewers_full_text():
    """The sidecar and final_actions.json record, for each excluded output the
    upgrade rechecked, its cluster review's corrected_per_output reason in
    full, as clusters.json holds it."""
    clusters = {c["id"]: c for c in _load(AUDIT / "clusters.json")["clusters"]}
    actions = {
        (a["scenario_id"], a["variable"]): a
        for a in _load(AUDIT / "final_actions.json")["excluded_rechecked"]
    }
    rechecked = _upgrade()["excluded_outputs_rechecked"]
    assert len(rechecked) == len(actions) == 19
    for record in rechecked:
        key = (record["scenario_id"], record["variable"])
        action = actions[key]
        (reason,) = [
            item["reason"]
            for item in clusters[action["cluster"]]["review"]["corrected_per_output"]
            if (item["scenario_id"], item["variable"]) == key
        ]
        assert record["reason"] == reason, key
        assert action["reason"] == reason, key


def test_the_builder_writes_the_committed_records():
    """Differential check: build_references_latest.py's record functions, which
    rewrite_reference_records.py also applies, give the committed records: each
    rechecked reason, the audit exclusions (appended last, as final_actions.json
    records them), the derivation and the serialization."""
    build = _builder()
    actions = _load(AUDIT / "final_actions.json")
    clusters = {c["id"]: c for c in _load(AUDIT / "clusters.json")["clusters"]}
    by_key = {
        (a["scenario_id"], a["variable"]): a for a in actions["excluded_rechecked"]
    }
    for record in _upgrade()["excluded_outputs_rechecked"]:
        entry = by_key[(record["scenario_id"], record["variable"])]
        assert record["reason"] == build.reviewed_reason(clusters, entry)
    path = RUN_DIR / "reference_exclusions.json"
    exclusions = _load(path)
    audit = build.audit_exclusions(actions)
    tail = exclusions["exclusions"][len(exclusions["exclusions"]) - len(audit) :]
    assert tail == list(audit.values())
    marker = f" On {UPGRADE_DATE} the references moved to policyengine-us {ENGINE}"
    base, _ = exclusions["derivation"].split(marker)
    decided = len(actions["new_exclusions"]) + len(audit)
    assert exclusions["derivation"] == build.exclusion_derivation(
        base, decided, len(audit)
    )
    for name in ("reference_exclusions.json", "reference_outputs.csv.meta.json"):
        raw = (RUN_DIR / name).read_text()
        assert build.dump_record(json.loads(raw)) == raw, name


def _audit_exclusions() -> dict[tuple[str, str], dict]:
    """Outputs the audit excluded on review, apart from any engine change."""
    return {
        (a["scenario_id"], a["variable"]): a
        for a in _load(AUDIT / "final_actions.json").get("audit_exclusions", [])
    }


def test_new_exclusions_are_computed_on_the_reference_engine():
    """The records decided on the upgrade's day: the three the revision lists
    and the one the audit excluded on review. Each alternative moves the output
    beyond the exact-match tolerance ($1, or any change for a 0/1 flag)."""
    from policybench.paper_results import moves_beyond_tolerance

    added = [e for e in _exclusions().values() if e["decided_on"] == "2026-09-29"]
    listed = {
        (c["scenario_id"], c["variable"])
        for c in _upgrade()["changed"]
        if c["cause"] == "excluded_reference_depends_on_unlisted_input"
    }
    references = _references()
    assert len(added) == 4 and len(listed) == 3
    assert {(e["scenario_id"], e["variable"]) for e in added} == (
        listed | set(_audit_exclusions())
    )
    for entry in added:
        key = (entry["scenario_id"], entry["variable"])
        assert entry["reason_code"] == "reference_depends_on_unlisted_input"
        assert entry["engine_version"] == f"policyengine-us {ENGINE}"
        assert abs(entry["frozen_value"] - references[key]) < 1e-3, key
        assert moves_beyond_tolerance(
            key[1], entry["frozen_value"], entry["alternative_value"]
        ), key


def test_the_audit_exclusion_is_recorded_and_computed():
    """scenario_023 head_medicaid_eligible: the excl_snap_ssi_disability
    investigation and its review flagged it, clusters.json records the
    disposition, final_actions.json lists the exclusion with the record the
    exclusion file carries, and the probe on 2.15.17 gives both values. The
    reference did not move, so the engine_upgrade revision does not list it."""
    key = ("scenario_023", "head_medicaid_eligible")
    audit = _audit_exclusions()
    assert set(audit) == {key}
    action = audit[key]
    record = _exclusions()[key]
    assert record == action["exclusion"]
    assert record["unlisted_input"] == "meets_ssi_disability_criteria"
    assert record["decided_on"] == action["decided_on"] == UPGRADE_DATE
    # The same unlisted input excludes the household's SNAP.
    assert _exclusions()[(key[0], "snap")]["unlisted_input"] == record["unlisted_input"]
    assert key not in {(c["scenario_id"], c["variable"]) for c in _upgrade()["changed"]}
    row = _sweep()[key]
    assert row["moved_vs_board"] == "False"
    for column in ("v11_1755", "board_20260922c", "raw_2_15_17", "final", "reference"):
        assert float(row[column]) == record["frozen_value"], column
    assert (row["cluster"], row["action"]) == (
        action["flagged_by"],
        "exclude_unlisted_input",
    )

    # The flag and its disposition.
    record_clusters = _load(AUDIT / "clusters.json")
    cluster = next(
        c for c in record_clusters["clusters"] if c["id"] == action["flagged_by"]
    )
    assert "head_medicaid_eligible" in cluster["investigation"]["summary"]
    assert any("head_medicaid_eligible" in p for p in cluster["review"]["problems"])
    (reconciled,) = [
        r
        for r in record_clusters["reconciliations"]
        if (r["scenario_id"], r["variable"]) == key
    ]
    assert reconciled["final_action"] == "exclude_unlisted_input"
    assert reconciled["cites_review"] == cluster["id"]
    assert reconciled["decided_on"] == UPGRADE_DATE

    # The probe's values, on the reference engine with the committed fix module.
    probe = _load(AUDIT / "verification" / "probe_023_medicaid.json")
    assert probe["engine_version"] == f"policyengine-us {ENGINE}"
    script = AUDIT / "scripts" / "probe_023_medicaid.py"
    assert probe["probe_sha256"] == hashlib.sha256(script.read_bytes()).hexdigest()
    module = AUDIT / probe["fix_module"]["module"]
    assert probe["fix_module"]["sha256"] == (
        hashlib.sha256(module.read_bytes()).hexdigest()
    )
    assert probe["committed_reference"] == _references()[key]
    results = {
        name: r["head_medicaid_eligible"] for name, r in probe["results"].items()
    }
    for reading in ("stated_facts", "reading_a", "reading_b"):
        assert results[f"latest_final/{reading}"] == record["frozen_value"]
    law = "latest_final_wdp_ssa_definition"
    assert results[f"{law}/reading_a"] == record["alternative_value"] == 0.0
    assert results[f"{law}/reading_b"] == record["frozen_value"] == 1.0
    category = probe["results"]["latest_final/stated_facts"]["medicaid_category"]
    assert category == "WORKING_DISABLED_BUY_IN"
    assert f"medicaid_category {category}" in record["alternative_reading"]
    magi = probe["results"]["latest_final/stated_facts"]["medicaid_income_level"]
    assert (
        f"{magi * 100:.1f}% of the federal poverty guideline"
        in (record["alternative_reading"])
    )
    review = (AUDIT / "verification" / "reviews" / "pr182_review_023.md").read_text()
    assert "Reading A" in review and "Reading B" in review


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
    # 1,984 outputs less 56 exclusions: the 52 of release 20260922c, the
    # three the upgrade added and the one the audit excluded on review.
    assert len(scored) == 1928
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
    """Lead's rulings on the wording: "newest" holds at a stated time, and the
    publication check says when it ran rather than claiming what is newest at
    publication. The sidecar's revision keeps the rule as it was written on
    2026-09-29."""
    sweep_rule = (
        "References come from the newest policyengine-us release when PolicyBench "
        "begins the reference sweep"
    )
    assert sweep_rule in _upgrade()["rule"]
    assert "Max's ruling, 2026-09-28" in _upgrade()["rule"]
    readme = " ".join((AUDIT / "README.md").read_text().split())
    assert (
        f"1. {sweep_rule}. Before publishing, PolicyBench checks that the newest "
        "release on PyPI gives the same values, and records when it checked "
        "(step 6 of the method)."
    ) in readme
    read_at = _load(AUDIT / "verification" / "sweep_timing.json")["pypi"]["read_at_utc"]
    assert (
        f"6. **Verify.** Before publishing, PolicyBench read PyPI on {read_at[:10]} "
        f"at {read_at[11:16]} UTC, when policyengine-us {VERIFICATION_ENGINE} was "
        "the newest release"
    ) in readme


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
    read_at = timing["pypi"]["read_at_utc"]
    assert (
        f"policyengine-us {VERIFICATION_ENGINE}, the newest release when "
        f"PolicyBench checked PyPI on {read_at[:10]} at {read_at[11:16]} UTC"
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


RERUN_SWEEPS = AUDIT / "verification" / "rerun_sweeps.json"


def _moves_beyond_tolerance(variable: str, before: float, after: float) -> bool:
    if variable.endswith("_eligible"):
        return round(after) != round(before)
    return abs(after - before) > 1.0


def test_the_rerun_sweeps_move_no_scored_output_beyond_the_tolerance():
    """verification/rerun_sweeps.json lists every output each exclusion sweep
    re-run on 2.15.17 moves. Set against the same calculation without its fix
    or reading (its baseline), no sweep moves a scored output by more than the
    $1 exact-match tolerance, and three scored state income tax outputs move by
    less. Against the conventions sweep alone, the 40-hour sweep also moves
    scenario_066's SNAP; the stated-hours alias, which the references apply,
    gives it the same value. Four sweeps are the September 22 audit's, and one
    (the state and local tax refund reading) is new."""
    summary = _load(RERUN_SWEEPS)
    sweep = _sweep()
    references = _references()
    exclusions = _exclusions()
    assert summary["engine"] == ENGINE

    # The modules the summary names are the committed ones, and the baselines'
    # values are the committed sweep's.
    for entry in (*summary["baselines"].values(), *summary["sweeps"]):
        module = AUDIT / entry["module"]
        assert (
            hashlib.sha256(module.read_bytes()).hexdigest() == (entry["module_sha256"])
        ), entry["module"]
    alias = summary["baselines"]["latest_map_stated_hours"]
    (only,) = alias["differs_from_latest_conventions"]
    alias_key = (only["scenario_id"], only["variable"])
    assert alias_key == ("scenario_066", "snap")
    assert only["latest_map_stated_hours"] == references[alias_key]
    assert float(sweep[alias_key]["conventions"]) == only["latest_conventions"]

    root_causes = _load(ROOT / "reference_audit" / "2026-09-22" / "root_causes.json")
    september_22 = [s for s in summary["sweeps"] if s["september_22_root_cause"]]
    new = [s for s in summary["sweeps"] if not s["september_22_root_cause"]]
    assert len(september_22) == 4 and len(new) == 1
    assert new[0]["sweep"] == "latest_alt_salt_refund_no_prior_benefit"
    for entry in september_22:
        assert entry["september_22_root_cause"] in root_causes

    beyond_own, within_own, beyond_conventions = [], [], []
    for entry in summary["sweeps"]:
        assert entry["outputs"] == 1984
        assert entry["baseline"] in summary["baselines"]
        for move in entry["moves"]:
            key = (move["scenario_id"], move["variable"])
            assert abs(
                float(sweep[key]["conventions"]) - move["latest_conventions"]
            ) < (1e-6), key
            if entry["baseline"] == "latest_conventions":
                assert move["baseline"] == move["latest_conventions"], key
            elif key != alias_key:
                assert move["baseline"] == move["latest_conventions"], key
            if key in exclusions:
                continue
            label = (entry["sweep"], *key)
            if _moves_beyond_tolerance(key[1], move["baseline"], move["recomputed"]):
                beyond_own.append(label)
            elif move["recomputed"] != move["baseline"]:
                within_own.append(label)
            if _moves_beyond_tolerance(
                key[1], move["latest_conventions"], move["recomputed"]
            ):
                beyond_conventions.append(label)
    assert beyond_own == []
    assert sorted(within_own) == [
        (
            "latest_alt_r02_ira_219g",
            "scenario_082",
            "state_income_tax_before_refundable_credits",
        ),
        (
            "latest_alt_salt_refund_no_prior_benefit",
            "scenario_078",
            "state_income_tax_before_refundable_credits",
        ),
        (
            "latest_alt_salt_refund_no_prior_benefit",
            "scenario_117",
            "state_income_tax_before_refundable_credits",
        ),
    ]
    assert beyond_conventions == [("latest_alt_unlisted_hours_40", *alias_key)]

    # The README, the card and the paper state the same counts.
    words = {1: "one", 3: "three", 4: "four"}
    readme = " ".join((AUDIT / "README.md").read_text().split())
    assert (
        f"On {ENGINE}, PolicyBench re-ran {words[len(september_22)]} of the "
        "September 22 sweeps over every output"
    ) in readme
    assert (
        "Against those baselines, no sweep moves a scored output by more than the "
        f"$1 exact-match tolerance. {words[len(within_own)].capitalize()} scored "
        "state income tax outputs move by less"
    ) in readme
    card = " ".join((ROOT / "docs" / "benchmark_card.md").read_text().split())
    assert (
        f"On policyengine-us {ENGINE}, PolicyBench re-ran "
        f"{words[len(september_22)]} of the September 22 sweeps"
    ) in card
    assert (
        f"Set against the same {ENGINE} calculation without its fix or reading, "
        "no sweep moves a scored output by more than the $1 exact-match "
        f"tolerance, and {words[len(within_own)]} scored outputs move by less."
    ) in card
    for text in (readme, card):
        assert "re-ran five" not in text
        assert "move no scored output except" not in text


def test_paper_results_count_the_rerun_sweeps_the_same_way():
    """Differential check: paper_results' partition of the re-run sweeps'
    moves, which renders the paper's sentence, agrees with the test above."""
    from policybench.paper_results import r

    assert r.rerun_sweep_september_22_count == 4
    assert r.rerun_sweep_new_count == 1
    assert r.rerun_sweep_scored_beyond_tolerance_count == 0
    assert r.rerun_sweep_scored_within_tolerance_count == 3
    # The paper's two clock times come from the timing record.
    timing = _load(AUDIT / "verification" / "sweep_timing.json")["pypi"]
    uploaded = timing["wheel_uploaded_at_utc"][ENGINE]
    assert r.reference_engine_uploaded_utc == uploaded[11:16]
    assert r.publication_check_pypi_read_date == timing["read_at_utc"][:10]
    assert r.publication_check_pypi_read_utc == timing["read_at_utc"][11:16]
    assert r.publication_check_policyengine_us_version == timing["newest_at_read"]
