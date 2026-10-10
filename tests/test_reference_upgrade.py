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

Later releases move the references again (Max, 2026-10-09: "yes i want to
wait for hte fixed engine"). Each appends its own engine_upgrade revision and
rewrites the working tree's references, exclusion record and pins. So every
2.15.17 fact here is pinned to the 2026-09-29 revision and to the files as the
releases on 2.15.17 committed them, read from git. The tests of the working
tree hold for any number of upgrades, keyed to the last; each runs on the
working tree and on a copy with a synthetic second upgrade
(tests/second_engine_upgrade.py, mock data).
"""

from __future__ import annotations

import csv
import functools
import hashlib
import io
import json
import subprocess
import tomllib
from pathlib import Path

import pytest

from tests.second_engine_upgrade import (
    Tree,
    paper_results_for,
    release_20261006,
    with_second_upgrade,
    working_tree,
)

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "reference_audit" / "2026-09-28"
RUN_PATH = (
    "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
RUN_DIR = ROOT / RUN_PATH
ENGINE = "2.15.17"
PREVIOUS_ENGINE = "1.755.4"
UPGRADE_DATE = "2026-09-29"
# The newest release when PolicyBench checked PyPI before publishing, and its
# sweep under the same fix module.
VERIFICATION_ENGINE = "2.17.0"
VERIFICATION_CSV = AUDIT / "verification" / "latest_final_2170.csv"
VERIFICATION_LOG = AUDIT / "verification" / "latest_final_2170.log"
# Release dashboard-data-20260929 (#182) wrote the 2.15.17 upgrade. Release
# dashboard-data-20261006 (#202) is the last whose references are on 2.15.17;
# between the two only the exclusion record changed (the 2026-10-05 review's
# eight). CI checks out full history.
UPGRADE_COMMIT = "d616e67c33b6f80dabf5cb7329f069f9a1de069d"
LAST_RELEASE_ON_ENGINE = "9ce4ade8382962a9134860c23f56d92509b5e57f"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


@functools.cache
def _committed(path: str, commit: str = LAST_RELEASE_ON_ENGINE) -> str:
    """A repository file as a release on 2.15.17 committed it."""
    shown = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{path}"], capture_output=True
    )
    assert shown.returncode == 0, (
        f"cannot read {path} at {commit[:12]}; fetch full history "
        f"(git fetch --unshallow): {shown.stderr.decode().strip()}"
    )
    return shown.stdout.decode()


def _committed_json(path: str, commit: str = LAST_RELEASE_ON_ENGINE) -> dict:
    return json.loads(_committed(path, commit))


def _sidecar_on_engine(commit: str = UPGRADE_COMMIT) -> dict:
    """The reference sidecar the 2026-09-29 upgrade wrote."""
    return _committed_json(f"{RUN_PATH}/reference_outputs.csv.meta.json", commit)


def _upgrades(revisions: list[dict]) -> list[dict]:
    return [r for r in revisions if r["kind"] == "engine_upgrade"]


def _upgrade_20260929(revisions: list[dict]) -> dict:
    """The 2026-09-29 move to 2.15.17, however many upgrades follow it."""
    (upgrade,) = [
        r
        for r in _upgrades(revisions)
        if r["date"] == UPGRADE_DATE
        and r["engine_version"] == f"policyengine-us {ENGINE}"
    ]
    return upgrade


def _last_upgrade(revisions: list[dict]) -> dict:
    """The upgrade behind the working references: the sidecar's last revision."""
    upgrades = _upgrades(revisions)
    assert upgrades and revisions[-1] is upgrades[-1]
    return upgrades[-1]


def _engine(label: str) -> str:
    return label.removeprefix("policyengine-us ")


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in _engine(version).split("."))


TREES = {
    "working_tree": working_tree,
    "second_upgrade": lambda: with_second_upgrade(release_20261006()),
}


def test_the_mock_upgrade_builds_on_release_20261006_whatever_the_tree_holds(
    monkeypatch,
):
    """The mock's base is release 20261006 as git holds it, so the fixture
    still builds once the release that moves the references lands: on a tree
    already past 2.15.17, or carrying the 2026-10-06 ruled records (one of
    them, scenario_082's state refundable credits, is the mock's later record),
    the mock refuses to build."""
    import tests.second_engine_upgrade as mock

    base = release_20261006()
    assert base.sidecar == _sidecar_on_engine(LAST_RELEASE_ON_ENGINE)
    assert base.exclusions == list(_exclusions().values())
    assert set(base.references) == set(_references()) and len(base.references) == 1984
    for key, value in _references().items():
        assert abs(base.references[key] - value) < 1e-6, key
    read_text = Path.read_text
    tracked = (ROOT / "paper", ROOT / "pyproject.toml")

    def no_working_tree(self, *args, **kwargs):
        assert not any(self.is_relative_to(p) for p in tracked), self
        return read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", no_working_tree)
    mock.release_20261006.cache_clear()
    try:
        rebuilt = with_second_upgrade(mock.release_20261006())
    finally:
        mock.release_20261006.cache_clear()
    assert _last_upgrade(rebuilt.sidecar["revisions"])["date"] == mock.MOCK_DATE
    with pytest.raises(ValueError, match="already moved past"):
        with_second_upgrade(rebuilt)
    later_record = {
        **base.exclusions[0],
        "scenario_id": mock.MOCK_LATER_RECORD[0],
        "variable": mock.MOCK_LATER_RECORD[1],
        "decided_on": "2026-10-06",
    }
    ruled = Tree(
        sidecar=base.sidecar,
        exclusions=[*base.exclusions, later_record],
        references=base.references,
        manifest=base.manifest,
        pins=base.pins,
    )
    with pytest.raises(ValueError, match="needs a scored output"):
        with_second_upgrade(ruled)


@pytest.fixture(params=sorted(TREES), scope="module")
def tree(request) -> Tree:
    """The working tree's reference records, and a copy with a synthetic
    second upgrade."""
    return TREES[request.param]()


@functools.cache
def _references() -> dict[tuple[str, str], float]:
    """The references on 2.15.17, as release 20261006 committed them."""
    rows = csv.DictReader(io.StringIO(_committed(f"{RUN_PATH}/reference_outputs.csv")))
    return {(r["scenario_id"], r["variable"]): float(r["value"]) for r in rows}


def _sweep() -> dict[tuple[str, str], dict]:
    with (AUDIT / "sweep_moves.csv").open(newline="") as source:
        return {(r["scenario_id"], r["variable"]): r for r in csv.DictReader(source)}


def _exclusions() -> dict[tuple[str, str], dict]:
    """The exclusion record on 2.15.17, as release 20261006 committed it."""
    records = _committed_json(f"{RUN_PATH}/reference_exclusions.json")["exclusions"]
    return {(e["scenario_id"], e["variable"]): e for e in records}


def _later_exclusions() -> dict[tuple[str, str], dict]:
    """Records decided after the upgrade: the 2026-10-05 audits' eight
    (reference_audit/2026-10-05, -medicare-part-b and -payroll). The upgrade's
    sweep and its publication check scored these outputs; each record is
    computed on the reference engine, and its frozen value is the reference."""
    return {
        key: record
        for key, record in _exclusions().items()
        if record["decided_on"] > UPGRADE_DATE
    }


def test_engine_and_provenance_name_the_recorded_release(tree):
    """The 2026-09-29 revision names 2.15.17 and 1.755.4, as the upgrade wrote
    it, and the releases on 2.15.17 pinned that engine and recorded it."""
    upgrade = _upgrade_20260929(tree.sidecar["revisions"])
    assert upgrade["engine_version"] == f"policyengine-us {ENGINE}"
    assert upgrade["previous_engine_version"] == f"policyengine-us {PREVIOUS_ENGINE}"
    assert upgrade == _upgrade_20260929(_sidecar_on_engine()["revisions"])
    for commit in (UPGRADE_COMMIT, LAST_RELEASE_ON_ENGINE):
        bundle = _sidecar_on_engine(commit)["policyengine_bundles"]["us"]
        assert bundle["model_version"] == ENGINE
        assert bundle["model_matches_policyengine_bundle"] is False
        pins = tomllib.loads(_committed("pyproject.toml", commit))["project"][
            "dependencies"
        ]
        assert f"policyengine-us=={ENGINE}" in pins
        assert f"policyengine=={bundle['policyengine_version']}" in pins


def test_the_reference_engine_is_the_last_upgrades(tree):
    """However many upgrades the sidecar records, the working references, the
    recorded bundle and the pins name the last one's engine, and the sidecar's
    rebuild is that upgrade's UTC day."""
    last = _last_upgrade(tree.sidecar["revisions"])
    engine = _engine(last["engine_version"])
    bundle = tree.sidecar["policyengine_bundles"]["us"]
    assert bundle["model_version"] == engine
    assert f"policyengine-us=={engine}" in tree.pins
    assert f"policyengine=={bundle['policyengine_version']}" in tree.pins
    assert tree.sidecar["regenerated_at_utc"][:10] == last["date"]
    refresh = tree.manifest["reference_output_refresh"]
    assert refresh["policyengine_us_version"] == engine
    assert refresh["regenerated_at_utc"] == tree.sidecar["regenerated_at_utc"]


def test_the_upgrades_extend_the_recorded_history_in_one_chain(tree):
    """Invariants for any number of upgrades: the sidecar keeps every revision
    the 2.15.17 releases committed, unchanged and in order; each upgrade starts
    from the engine the one before it moved to, with 1.755.4 first; engines
    and dates strictly increase; and each excluded output's value comes from
    an engine the references were on."""
    revisions = tree.sidecar["revisions"]
    committed = _sidecar_on_engine()["revisions"]
    assert _sidecar_on_engine(LAST_RELEASE_ON_ENGINE)["revisions"] == committed
    assert revisions[: len(committed)] == committed
    upgrades = _upgrades(revisions)
    chain = [upgrades[0]["previous_engine_version"]] + [
        u["engine_version"] for u in upgrades
    ]
    assert chain[0] == f"policyengine-us {PREVIOUS_ENGINE}"
    for before, after in zip(upgrades, upgrades[1:]):
        assert after["previous_engine_version"] == before["engine_version"]
        assert after["date"] > before["date"]
    keys = [_version_key(label) for label in chain]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    assert {e["engine_version"] for e in tree.exclusions} <= set(chain)


def test_every_reference_change_after_2_15_17_is_a_listed_revision(tree):
    """Differential check: release 20261006's references, moved by each later
    revision's changes in order (each starting from the value it lists as
    previous), are the tree's references; and every excluded output's
    reference is the value its record was decided on (rule 5)."""
    values = dict(_references())
    for revision in tree.sidecar["revisions"][len(_sidecar_on_engine()["revisions"]) :]:
        for change in revision.get("changed", []):
            key = (change["scenario_id"], change["variable"])
            assert abs(values[key] - change["previous"]) < 1e-6, key
            values[key] = change["regenerated"]
    assert set(values) == set(tree.references)
    for key, value in tree.references.items():
        assert abs(values[key] - value) < 1e-6, key
    for record in tree.exclusions:
        key = (record["scenario_id"], record["variable"])
        assert abs(record["frozen_value"] - tree.references[key]) < 1e-3, key


def test_every_later_upgrade_change_is_explained(tree):
    """No unexplained move in an upgrade after 2.15.17: every change names a
    cause and a basis; one labelled engine_upgrade_within_1 is within the
    exact-match tolerance; a change to an output the upgrade restores is its
    regeneration; a change to an output it newly excludes has a record decided
    that day on the new engine; and every other change is to an output scored
    before and after. Each rechecked output stays excluded, keeps its
    reference and moves on the new engine."""
    from policybench.paper_results import (
        engine_upgrades_from,
        moves_beyond_tolerance,
        references_as_of,
    )

    revisions = tree.sidecar["revisions"]
    upgrades = engine_upgrades_from(revisions, tree.exclusions)
    records = {(e["scenario_id"], e["variable"]): e for e in tree.exclusions}
    for upgrade in upgrades[1:]:
        revision = upgrade.revision
        references = references_as_of(tree.references, revisions, upgrade.date)
        for change in upgrade.changes:
            key = (change["scenario_id"], change["variable"])
            assert str(change.get("cause", "")).strip(), key
            assert str(change.get("basis", "")).strip(), key
            beyond = moves_beyond_tolerance(
                key[1], change["previous"], change["regenerated"]
            )
            if change["cause"] == "engine_upgrade_within_1":
                assert not beyond, key
            if key in upgrade.restored:
                assert change["cause"] == "regenerated_upstream_fix", key
            elif key in upgrade.excluded:
                record = records[key]
                assert key not in upgrade.excluded_before, key
                assert record["decided_on"] == revision["date"], key
                assert record["engine_version"] == revision["engine_version"], key
                assert change["cause"] == f"excluded_{record['reason_code']}", key
                assert beyond, key
            else:
                assert key not in upgrade.excluded_before, key
        for entry in revision.get("excluded_outputs_rechecked", []):
            key = (entry["scenario_id"], entry["variable"])
            assert key in upgrade.excluded_before & upgrade.excluded, key
            assert abs(entry["kept_value"] - references[key]) < 1e-6, key
            assert moves_beyond_tolerance(
                key[1], entry["kept_value"], upgrade.rechecked_value(entry)
            ), key


def test_an_exclusion_leaves_the_record_only_through_a_listed_restoration(tree):
    """An output release 20261006 excluded leaves the record only when a later
    revision lists it in regenerated_exclusions with the record it removes,
    so the paper can still tell what was excluded at each upgrade. A restored
    record release 20261006 did not hold was decided after it (a later
    release's record that an upgrade in that release removes). Every record
    the tree adds was decided after the 2026-10-05 review, and no restored
    output is still excluded."""
    before = _exclusions()
    now = {(e["scenario_id"], e["variable"]): e for e in tree.exclusions}
    later = tree.sidecar["revisions"][len(_sidecar_on_engine()["revisions"]) :]
    restored = {
        (entry["scenario_id"], entry["variable"]): entry
        for revision in later
        for entry in revision.get("regenerated_exclusions", [])
    }
    assert set(before) - set(now) <= set(restored)
    assert not set(restored) & set(now)
    for key, entry in restored.items():
        record = entry["record"]
        assert (record["scenario_id"], record["variable"]) == key
        if key in before:
            assert record == before[key], key
        else:
            assert record["decided_on"] > "2026-10-05", key
    for key in set(now) - set(before):
        assert now[key]["decided_on"] > "2026-10-05", key


def test_every_module_the_revision_names_is_committed_unchanged(tree):
    """The 2026-09-29 upgrade's modules are reference_audit/2026-09-28/fixes'
    files byte for byte; a later upgrade's modules are committed, unchanged,
    under some audit's fixes directory."""
    for entry in _upgrade_20260929(tree.sidecar["revisions"])["fix_modules"]:
        path = AUDIT / "fixes" / entry["module"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], path
    for upgrade in _upgrades(tree.sidecar["revisions"]):
        for entry in upgrade["fix_modules"]:
            digests = {
                hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (ROOT / "reference_audit").glob(
                    f"*/fixes/{entry['module']}"
                )
            }
            assert entry["sha256"] in digests, (upgrade["date"], entry["module"])


def test_the_sweep_table_is_the_committed_reference():
    """sweep_moves.csv marks the outputs excluded when the upgrade decided; an
    output a later record excludes was scored then, and its record keeps the
    reference engine's value."""
    references = _references()
    sweep = _sweep()
    exclusions = _exclusions()
    later = _later_exclusions()
    assert set(sweep) == set(references) and len(sweep) == 1984
    # 64 records less the 2026-10-05 audits' eight.
    assert len(later) == 8 and len(exclusions) - len(later) == 56
    assert sum(row["excluded"] == "True" for row in sweep.values()) == 56
    for key, row in sweep.items():
        assert abs(float(row["reference"]) - references[key]) < 1e-6, key
        record = exclusions.get(key)
        excluded_then = record is not None and key not in later
        assert (row["excluded"] == "True") == excluded_then, key
        if record is None or record["decided_on"] >= UPGRADE_DATE:
            # Scored, or excluded in this wave or later: the engine value is
            # the reference.
            assert abs(float(row["final"]) - references[key]) < 1e-3, key
        else:
            # Excluded earlier: keeps the value its record was decided on.
            assert abs(float(row["board_20260922c"]) - references[key]) < 1e-6, key
    for key, record in later.items():
        assert record["engine_version"] == f"policyengine-us {ENGINE}", key
        assert record["frozen_value"] == references[key], key


def test_every_changed_reference_is_listed_and_reviewed(tree):
    """Every changed output is listed, and one that moves beyond the
    exact-match tolerance ($1 for an amount, any change for a 0/1 flag, as
    paper_results.moves_beyond_tolerance and the builder count it) is an
    approved change or a new exclusion; only a move within the tolerance may
    be recorded as engine_upgrade_within_1."""
    from policybench.paper_results import moves_beyond_tolerance

    references = _references()
    sweep = _sweep()
    actions = _load(AUDIT / "final_actions.json")
    clusters = {c["id"]: c for c in _load(AUDIT / "clusters.json")["clusters"]}
    approved = {(a["scenario_id"], a["variable"]) for a in actions["approved"]}
    added = {(e["scenario_id"], e["variable"]) for e in actions["new_exclusions"]}
    changed = {
        (c["scenario_id"], c["variable"]): c
        for c in _upgrade_20260929(tree.sidecar["revisions"])["changed"]
    }
    board = {k: float(r["board_20260922c"]) for k, r in sweep.items()}
    differ = {k for k in references if abs(references[k] - board[k]) > 1e-9}
    assert differ == set(changed)
    for key, change in changed.items():
        assert abs(change["regenerated"] - references[key]) < 1e-9, key
        assert abs(change["previous"] - board[key]) < 1e-9, key
        beyond = moves_beyond_tolerance(
            key[1], change["previous"], change["regenerated"]
        )
        assert key in approved or key in added or not beyond, key
        if change["cause"] == "engine_upgrade_within_1":
            assert not beyond, key
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


def test_each_rechecked_reason_is_the_reviewers_full_text(tree):
    """The sidecar and final_actions.json record, for each excluded output the
    upgrade rechecked, its cluster review's corrected_per_output reason in
    full, as clusters.json holds it."""
    clusters = {c["id"]: c for c in _load(AUDIT / "clusters.json")["clusters"]}
    actions = {
        (a["scenario_id"], a["variable"]): a
        for a in _load(AUDIT / "final_actions.json")["excluded_rechecked"]
    }
    rechecked = _upgrade_20260929(tree.sidecar["revisions"])[
        "excluded_outputs_rechecked"
    ]
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


def test_the_builder_writes_the_committed_records(tree):
    """Differential check: build_references_latest.py's record functions, which
    rewrite_reference_records.py also applies, give the records the releases on
    2.15.17 committed: each rechecked reason, the audit exclusions (appended
    last, as final_actions.json records them), the derivation and the
    serialization."""
    build = _builder()
    actions = _load(AUDIT / "final_actions.json")
    clusters = {c["id"]: c for c in _load(AUDIT / "clusters.json")["clusters"]}
    by_key = {
        (a["scenario_id"], a["variable"]): a for a in actions["excluded_rechecked"]
    }
    upgrade = _upgrade_20260929(tree.sidecar["revisions"])
    for record in upgrade["excluded_outputs_rechecked"]:
        entry = by_key[(record["scenario_id"], record["variable"])]
        assert record["reason"] == build.reviewed_reason(clusters, entry)
    audit = build.audit_exclusions(actions)
    marker = f" On {UPGRADE_DATE} the references moved to policyengine-us {ENGINE}"
    decided = len(actions["new_exclusions"]) + len(audit)
    for commit in (UPGRADE_COMMIT, LAST_RELEASE_ON_ENGINE):
        exclusions = _committed_json(f"{RUN_PATH}/reference_exclusions.json", commit)
        tail = exclusions["exclusions"][len(exclusions["exclusions"]) - len(audit) :]
        assert tail == list(audit.values()), commit
        base, _ = exclusions["derivation"].split(marker)
        assert exclusions["derivation"] == build.exclusion_derivation(
            base, decided, len(audit)
        ), commit
        for name in ("reference_exclusions.json", "reference_outputs.csv.meta.json"):
            raw = _committed(f"{RUN_PATH}/{name}", commit)
            assert build.dump_record(json.loads(raw)) == raw, (commit, name)


def test_the_working_records_keep_the_builders_serialization():
    """Whatever later release wrote them, the working tree's exclusion record
    and sidecar are serialized as the builder serializes them."""
    build = _builder()
    for name in ("reference_exclusions.json", "reference_outputs.csv.meta.json"):
        raw = (RUN_DIR / name).read_text()
        assert build.dump_record(json.loads(raw)) == raw, name


def _audit_exclusions() -> dict[tuple[str, str], dict]:
    """Outputs the audit excluded on review, apart from any engine change."""
    return {
        (a["scenario_id"], a["variable"]): a
        for a in _load(AUDIT / "final_actions.json").get("audit_exclusions", [])
    }


def test_new_exclusions_are_computed_on_the_reference_engine(tree):
    """The records decided on the upgrade's day: the three the revision lists
    and the one the audit excluded on review. Each alternative moves the output
    beyond the exact-match tolerance ($1, or any change for a 0/1 flag)."""
    from policybench.paper_results import moves_beyond_tolerance

    added = [e for e in _exclusions().values() if e["decided_on"] == "2026-09-29"]
    listed = {
        (c["scenario_id"], c["variable"])
        for c in _upgrade_20260929(tree.sidecar["revisions"])["changed"]
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


def test_the_audit_exclusion_is_recorded_and_computed(tree):
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
    changed = _upgrade_20260929(tree.sidecar["revisions"])["changed"]
    assert key not in {(c["scenario_id"], c["variable"]) for c in changed}
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


def test_the_publication_release_recomputes_every_scored_reference(tree):
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
    # 1,984 outputs less 64 exclusions: the 52 of release 20260922c, the
    # three the upgrade added, the one the audit excluded on review, and the
    # eight the 2026-10-05 audits added.
    assert len(scored) == 1920
    # The check ran before the 2026-10-05 records: it covers the 1,928 outputs
    # scored then, which include those eight.
    later = _later_exclusions()
    scored_then = scored | set(later)
    assert len(later) == 8 and len(scored_then) == 1928
    for key in scored_then:
        assert float(rows[key]["recomputed"]) == references[key], key
    # The sweep's frozen column is the committed reference, so its "moved"
    # outputs are excluded ones: the 19 the upgrade rechecked, each at the
    # value the sidecar records for 2.15.17.
    rechecked = {
        (r["scenario_id"], r["variable"]): r
        for r in _upgrade_20260929(tree.sidecar["revisions"])[
            "excluded_outputs_rechecked"
        ]
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


def test_the_records_date_the_upgrade_by_its_utc_day(tree):
    """The revision, the exclusion record's derivation, each new exclusion's
    note and decided_on, and each new-exclusion basis in the sidecar name the
    upgrade's UTC day. The ruling's own date is labeled as Max's."""
    upgrade = _upgrade_20260929(tree.sidecar["revisions"])
    assert upgrade["date"] == UPGRADE_DATE
    assert _sidecar_on_engine()["regenerated_at_utc"][:10] == UPGRADE_DATE
    exclusions = _committed_json(f"{RUN_PATH}/reference_exclusions.json")
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
    # The records as the releases on 2.15.17 committed them keep the dating,
    # and in the tree so do the 2026-09-29 revision and every record decided
    # by the 2026-10-05 review. A later record may cite another 2026-09-28
    # event (d994's Louisiana records cite RIB 26-019, issued that day), so
    # the later releases' records and annotations are not scanned.
    annotations = "annotations/us_full_run_20260612_policyengine_4_16_1_populace"
    texts = {
        path: _committed(path)
        for path in (
            f"{RUN_PATH}/reference_exclusions.json",
            f"{RUN_PATH}/reference_outputs.csv.meta.json",
            f"{annotations}/us_adjudications.json",
            f"{annotations}/us_case_notes.csv",
        )
    }
    texts["final_actions.json"] = (AUDIT / "final_actions.json").read_text()
    texts["the tree's 2.15.17 records"] = json.dumps(
        [upgrade] + [e for e in tree.exclusions if e["decided_on"] <= "2026-10-05"]
    )
    for name, text in texts.items():
        text = text.replace("reference_audit/2026-09-28", "")
        for index in [i for i in range(len(text)) if text.startswith("2026-09-28", i)]:
            assert "Max's ruling, 2026-09-28" in text[index - 20 : index + 10], (
                name,
                text[index - 80 : index + 40],
            )


def test_the_engine_rule_is_anchored_to_the_sweep(tree):
    """Lead's rulings on the wording: "newest" holds at a stated time, and the
    publication check says when it ran rather than claiming what is newest at
    publication. The sidecar's revision keeps the rule as it was written on
    2026-09-29."""
    sweep_rule = (
        "References come from the newest policyengine-us release when PolicyBench "
        "begins the reference sweep"
    )
    rule = _upgrade_20260929(tree.sidecar["revisions"])["rule"]
    assert sweep_rule in rule
    assert "Max's ruling, 2026-09-28" in rule
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
    rebuilt = _sidecar_on_engine()["regenerated_at_utc"]
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


def test_the_pin_commit_came_while_the_reference_engine_was_newest():
    """The timing record's pin commit, checked without git: it follows
    policyengine-us 2.15.17's upload and the sweep's first output, and precedes
    2.16.0's upload and the reference build, as recorded."""
    timing = _load(AUDIT / "verification" / "sweep_timing.json")
    uploaded = timing["pypi"]["wheel_uploaded_at_utc"]
    sweep = timing["reference_sweep"]
    pin = sweep["pin_commit"]
    assert len(pin["commit"]) == 40 and int(pin["commit"], 16) >= 0
    assert pin["subject"] == f"Pin policyengine.py 6.1.2 and policyengine-us {ENGINE}"
    rebuilt = _sidecar_on_engine()["regenerated_at_utc"]
    assert (
        uploaded[ENGINE]
        < sweep["first_output_at_utc"]
        < pin["committed_at_utc"]
        < uploaded["2.16.0"]
        < rebuilt.replace("+00:00", "Z")
    )


def test_the_pin_commit_time_in_the_timing_record_is_gits():
    """Differential check of the timing record against git, where the commit is
    in this checkout's history (the release branch)."""
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

        pytest.skip(
            f"pin commit {pin['commit'][:12]} is not in this checkout's history: "
            "squash-merging PR #182 left it out of main's history; "
            "test_the_pin_commit_came_while_the_reference_engine_was_newest "
            "checks the recorded times without git"
        )
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


def test_paper_results_count_the_rerun_sweeps_the_same_way(tree):
    """Differential check: paper_results' partition of the re-run sweeps'
    moves, which renders the paper's sentence, agrees with the test above,
    and stays pinned to the 2026-09-29 upgrade however many follow it."""
    results = paper_results_for(tree)
    assert results.rerun_sweep_september_22_count == 4
    assert results.rerun_sweep_new_count == 1
    assert results.rerun_sweep_scored_beyond_tolerance_count == 0
    assert results.rerun_sweep_scored_within_tolerance_count == 3
    # The paper derives the upgrade's new exclusions from the new sweep:
    # beyond the tolerance, the state and local tax refund reading moves
    # exactly the three federal income tax outputs the upgrade excluded, and
    # otherwise only outputs excluded on 1.755.4.
    upgrade = results.september_upgrade
    assert upgrade.revision == _upgrade_20260929(tree.sidecar["revisions"])
    new_exclusions = {
        (c["scenario_id"], c["variable"]) for c in upgrade.partition["new_exclusions"]
    }
    assert set(results.rerun_sweep_new_excluded_outputs) == new_exclusions
    assert len(new_exclusions) == upgrade.new_exclusion_count == 3
    assert {variable for _, variable in new_exclusions} == {
        "federal_income_tax_before_refundable_credits"
    }
    assert results.rerun_sweep_new_excluded_count_word == "three"
    (new,) = [
        s for s in _load(RERUN_SWEEPS)["sweeps"] if not s["september_22_root_cause"]
    ]
    exclusions = _exclusions()
    beyond = {
        (move["scenario_id"], move["variable"])
        for move in new["moves"]
        if _moves_beyond_tolerance(
            move["variable"], move["baseline"], move["recomputed"]
        )
    }
    assert new_exclusions <= beyond
    assert all(
        exclusions[key]["engine_version"] == f"policyengine-us {PREVIOUS_ENGINE}"
        for key in beyond - new_exclusions
    )
    # The paper's two clock times come from the timing record.
    timing = _load(AUDIT / "verification" / "sweep_timing.json")["pypi"]
    uploaded = timing["wheel_uploaded_at_utc"][ENGINE]
    assert results.reference_engine_uploaded_utc == uploaded[11:16]
    assert results.publication_check_pypi_read_date == timing["read_at_utc"][:10]
    assert results.publication_check_pypi_read_utc == timing["read_at_utc"][11:16]
    assert results.publication_check_policyengine_us_version == timing["newest_at_read"]


def test_the_october_upgrade_commits_the_actions_its_sidecar_pins():
    """reference_audit/2026-10-09-engine-upgrade/final_actions.json is the
    actions file the frozen sidecar's last upgrade names by sha256, so the
    build can be checked against it. Its arrays give the counts the sidecar
    does; its free-text note predates CA 099's move to the rechecks, as the
    directory's README says, and stays as written."""
    audit = ROOT / "reference_audit/2026-10-09-engine-upgrade"
    actions_path = audit / "final_actions.json"
    sidecar = json.loads((RUN_DIR / "reference_outputs.csv.meta.json").read_text())
    upgrade = [r for r in sidecar["revisions"] if r["kind"] == "engine_upgrade"][-1]
    assert upgrade["engine_version"] == "policyengine-us 2.38.6"
    digest = hashlib.sha256(actions_path.read_bytes()).hexdigest()
    assert digest == upgrade["provenance"]["actions_sha256"]
    actions = json.loads(actions_path.read_text())
    assert actions["draft"] is False
    assert len(actions["regenerated_exclusions"]) == len(
        upgrade["regenerated_exclusions"]
    )
    assert len(actions["excluded_rechecked"]) == len(
        upgrade["excluded_outputs_rechecked"]
    )
    assert len(actions["new_exclusions"]) == len(upgrade["new_exclusions"])
    assert (
        len(actions["regenerated_exclusions"]),
        len(actions["excluded_rechecked"]),
    ) == (
        18,
        17,
    )
    # The erratum the README carries names the note's stale counts and the
    # arrays' counts; if the note were rewritten, the pin above would fail.
    assert "19 regenerations" in actions["note"] and "16 rechecks" in actions["note"]
    readme = (audit / "README.md").read_text()
    assert "19 regenerations and 16" in readme and "18 regenerations and 17" in readme
    assert digest[:8] in readme
