"""The fourth engine upgrade's reference builder, its narratives, its draft
actions and its committed build (reference_audit/2026-10-22-engine-upgrade, on
release 20261014, staged for the next board release).

Adapted from tests/test_build_references_upgrade_1012.py, which tests the
2026-10-12 audit's copies. The planning logic is the same; the base, the
previous engine and this audit's own fix modules differ, and no release spec
rules exclusions (the build is staged, not frozen with a release).

The engine is stubbed: each test hands the builder's pure planning step a dict
of computed values. Properties (Hypothesis) state the builder's invariants:

- every refusal fires: an unexplained move, scored or excluded; an approved
  output that does not move; a regenerated output off its audited target; a new
  exclusion on an output that does not move; a rechecked output that does not
  move; an output named by two lists;
- a removed record's output is scored at its new engine value;
- every output the upgrade does not change keeps its bytes in the reference
  CSV, and every earlier sidecar revision keeps its bytes;
- the records' order does not depend on the order of the actions' lists;
- the paper's partition of the revision's changes agrees with the builder.

The committed build is checked against itself and its inputs: re-planning the
committed computed.csv with final_actions.json and writing the result
reproduces the committed reference CSV, sidecar and exclusion record byte for
byte (a differential test of the build that needs no engine).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import random
import sys
import types
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
UPGRADE = ROOT / "reference_audit" / "2026-10-22-engine-upgrade"
BUILD = UPGRADE / "reference-build"
RUN_DIR = (
    ROOT
    / "paper/snapshot/20260501/runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
)
SETTINGS = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


def _module(name: str, path: Path, builder=None):
    """Load ``path`` as ``name``. This audit's narratives and drafting scripts
    import ``build_references_upgrade`` by name, which the 2026-10-09 and
    2026-10-12 tests may already have loaded from their folders: ``builder``
    stands in under that name while the module loads, and the earlier entry is
    put back."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    previous = sys.modules.get("build_references_upgrade")
    if builder is not None:
        sys.modules["build_references_upgrade"] = builder
    try:
        spec.loader.exec_module(module)
    finally:
        if builder is not None:
            if previous is None:
                sys.modules.pop("build_references_upgrade", None)
            else:
                sys.modules["build_references_upgrade"] = previous
    return module


build = _module(
    "build_references_upgrade_1022",
    UPGRADE / "scripts" / "build_references_upgrade.py",
)
narratives = _module(
    "narratives_upgrade_1022", UPGRADE / "scripts" / "narratives_upgrade.py", build
)
drafting = _module("actions_from_cells_1022", UPGRADE / "actions_from_cells.py", build)


def test_this_audits_scripts_use_this_audits_builder():
    assert build.BASE_COMMIT == "bf845cbe4e92de495150c8660c35ea357d996a8c"
    assert build.PREVIOUS_ENGINE == "policyengine-us 2.41.0"
    assert build.LOCAL_FIXES_REL == "reference_audit/2026-10-22-engine-upgrade/fixes"
    assert narratives.BASE_COMMIT == build.BASE_COMMIT
    assert drafting.PREVIOUS_ENGINE == build.PREVIOUS_ENGINE
    assert drafting.load_base is build.load_base


ENGINE = "policyengine-us 9.9.9"
DATE = "2026-10-23"
NOW = "2026-10-23T12:00:00+00:00"
S = "state_income_tax_before_refundable_credits"
F = "federal_income_tax_before_refundable_credits"
FLAG = "head_medicaid_eligible"


# --- A small synthetic base --------------------------------------------------


def _defect(sid, variable, frozen, alternative, decided_on="2026-09-22"):
    return {
        "scenario_id": sid,
        "variable": variable,
        "reason_code": "reference_engine_defect",
        "root_cause": f"r_{sid}",
        "alternative_reading": "The rule as the law states it.",
        "frozen_value": frozen,
        "alternative_value": alternative,
        "engine_version": "policyengine-us 1.755.4",
        "decided_on": decided_on,
        "decided_by": "developer",
        "defect": "a defect",
        "law": "a law",
        "upstream": "to be filed",
        "note": "a note",
    }


def _unlisted(sid, variable, frozen, alternative, decided_on="2026-09-05"):
    return {
        "scenario_id": sid,
        "variable": variable,
        "reason_code": "reference_depends_on_unlisted_input",
        "unlisted_input": "an input",
        "alternative_reading": "Another reading.",
        "frozen_value": frozen,
        "alternative_value": alternative,
        "engine_version": "policyengine-us 1.755.4",
        "decided_on": decided_on,
        "decided_by": "developer",
        "note": "a note",
    }


# scenario, variable, base value, impact weight
ROWS = [
    ("scenario_001", S, 1000.0, ""),
    ("scenario_001", "local_income_tax", 0.0, ""),
    ("scenario_002", S, 500.25, "1.5"),
    ("scenario_002", F, 250.5, ""),
    ("scenario_003", S, 1200.0, ""),
    ("scenario_003", "snap", 3000.0, ""),
    ("scenario_004", S, 700.0, ""),
    ("scenario_004", F, 4100.0, ""),
    ("scenario_005", S, 820.35, ""),
    ("scenario_005", FLAG, 1.0, "0.0"),
    ("scenario_006", "local_income_tax", 0.0, ""),
    ("scenario_006", "snap", 120.0, ""),
    ("scenario_007", "snap", 0.0, ""),
    ("scenario_007", "free_school_meals_eligible", 0.0, "0.0"),
    ("scenario_023", FLAG, 1.0, ""),
]
# Release 20261014's record, in its shape: the 2026-09-22 records, then the
# later ones (decided 2026-10-06 on 2.15.17), then the 2026-09-29 audit's tail.
LATER = [
    {
        **_defect("scenario_004", S, 700.0, 690.0, decided_on="2026-10-06"),
        "engine_version": "policyengine-us 2.15.17",
    },
    {
        **_unlisted("scenario_004", F, 4100.0, 5300.0, decided_on="2026-10-06"),
        "engine_version": "policyengine-us 2.15.17",
    },
    {
        **_unlisted("scenario_005", S, 820.35, 820.26, decided_on="2026-10-06"),
        "reason_code": "reference_law_published_after_freeze",
        "root_cause": "later",
        "published": "later",
        "law": "a law",
        "engine_version": "policyengine-us 2.15.17",
    },
]
BASE_RECORDS = [
    _defect("scenario_002", F, 250.5, 300.0),  # fixed below: regenerated
    _defect("scenario_003", "snap", 3000.0, 2500.0),  # unfixed
    _unlisted("scenario_006", "snap", 120.0, 0.0),
    *LATER,
]
TAIL = _unlisted("scenario_023", FLAG, 1.0, 0.0, decided_on="2026-09-29")
FIRST_REVISION = {
    "date": "2026-09-29",
    "kind": "engine_upgrade",
    "engine_version": "policyengine-us 2.15.17",
    "previous_engine_version": "policyengine-us 1.755.4",
    "fix_modules": [],
    "excluded_outputs_rechecked": [],
    "changed": [],
}
SECOND_REVISION = {
    "date": "2026-10-10",
    "kind": "engine_upgrade",
    "engine_version": "policyengine-us 2.38.6",
    "previous_engine_version": "policyengine-us 2.15.17",
    "fix_modules": [],
    "excluded_outputs_rechecked": [],
    "regenerated_exclusions": [],
    "changed": [],
}
# Release 20261013's upgrade, the base's last revision: this audit's builder
# upgrades from its engine.
THIRD_REVISION = {
    "date": "2026-10-13",
    "kind": "engine_upgrade",
    "engine_version": "policyengine-us 2.41.0",
    "previous_engine_version": "policyengine-us 2.38.6",
    "fix_modules": [],
    "excluded_outputs_rechecked": [],
    "regenerated_exclusions": [],
    "changed": [],
}


def _csv_text(rows=ROWS) -> str:
    lines = ["scenario_id,variable,value,impact_weight\n"]
    lines += [f"{s},{v},{repr(float(x))},{w}\n" for s, v, x, w in rows]
    return "".join(lines)


def _base() -> build.Base:
    exclusions = {
        "schema_version": 1,
        "rule": "rule",
        "derivation": "Derived.",
        "exclusions": copy.deepcopy(BASE_RECORDS) + [copy.deepcopy(TAIL)],
    }
    return build.Base(
        reference=build.parse_reference_csv(_csv_text()),
        meta={
            "programs": [],
            "policyengine_bundles": {"us": {}},
            "reference_csv_sha256": "x",
            "regenerated_at_utc": "2026-09-29T15:04:45+00:00",
            "revisions": [
                {"date": "2026-09-22", "kind": "convention", "changed": []},
                copy.deepcopy(FIRST_REVISION),
                copy.deepcopy(SECOND_REVISION),
                copy.deepcopy(THIRD_REVISION),
            ],
        },
        exclusions=exclusions,
        scenarios_csv="",
        frozen={(s, v): x - 1.0 for s, v, x, _ in ROWS},
    )


def _unchanged() -> dict:
    return {(s, v): x for s, v, x, _ in ROWS}


def _new_exclusion(sid, value) -> dict:
    record = _unlisted(sid, "local_income_tax", value, 0.0, decided_on=DATE)
    record["engine_version"] = ENGINE
    return record


def _actions(**lists) -> dict:
    """Actions on the synthetic base."""
    actions = {
        "engine": ENGINE,
        "previous_engine": "policyengine-us 2.41.0",
        "date": DATE,
        "approved": [],
        "regenerated_exclusions": [],
        "new_exclusions": [],
        "excluded_rechecked": [],
    }
    actions.update(lists)
    return actions


def _regenerate(sid, variable, alternative, tolerance=1.0):
    return {
        "scenario_id": sid,
        "variable": variable,
        "alternative_value": alternative,
        "tolerance": tolerance,
        "upstream": "PolicyEngine/policyengine-us#1",
        "basis": "Fixed upstream.",
    }


def _full():
    """A complete upgrade: one approval, two regenerations (a 2026-09-22 record
    and a later one), one new exclusion, one recheck, a within-$1 move."""
    computed = _unchanged()
    computed[("scenario_001", S)] = 1010.0  # approved
    computed[("scenario_002", F)] = 300.4  # regenerated (2026-09-22 record)
    computed[("scenario_004", S)] = 690.2  # regenerated (2026-10-06 record)
    computed[("scenario_006", "local_income_tax")] = 670.55  # new exclusion
    computed[("scenario_003", "snap")] = 2900.0  # rechecked: off target
    computed[("scenario_002", S)] = 500.75  # within $1
    actions = _actions(
        approved=[
            {
                "scenario_id": "scenario_001",
                "variable": S,
                "value": 1010.0,
                "cause": "a_cause",
                "basis": "A basis.",
            }
        ],
        regenerated_exclusions=[
            _regenerate("scenario_002", F, 300.0),
            _regenerate("scenario_004", S, 690.0),
        ],
        new_exclusions=[_new_exclusion("scenario_006", 670.55)],
        excluded_rechecked=[
            {"scenario_id": "scenario_003", "variable": "snap", "reason": "Not fixed."}
        ],
    )
    return computed, actions


def _plan(computed, actions):
    base = _base()
    return base, build.plan_upgrade(base, actions, computed)


def _write(tmp_path, computed, actions):
    base, plan = _plan(computed, actions)
    assert plan.problems == []
    written = build.write_outputs(
        tmp_path,
        base,
        plan,
        actions,
        bundle={"policyengine_version": "6.1.2", "bundled_model_version": "2.2.1"},
        fix_modules=[{"module": "m.py", "sha256": "0"}],
        provenance={"builder_sha256": "0"},
        traces={
            f"{c['scenario_id']}|{c['variable']}": {
                "pe_variable": c["variable"],
                "trace": "t\nu",
            }
            for c in plan.changed + plan.within
        },
        now=NOW,
    )
    return base, plan, written


# --- The full upgrade ---------------------------------------------------------


def test_a_complete_upgrade_writes_consistent_records(tmp_path):
    computed, actions = _full()
    base, plan, written = _write(tmp_path, computed, actions)
    revision = written.meta["revisions"][-1]
    assert revision["kind"] == "engine_upgrade"
    assert revision["engine_version"] == ENGINE
    assert revision["previous_engine_version"] == "policyengine-us 2.41.0"
    assert written.meta["revisions"][:-1] == base.meta["revisions"]
    assert [r["kind"] for r in written.meta["revisions"]].count("engine_upgrade") == 4
    causes = {
        (c["scenario_id"], c["variable"]): c["cause"] for c in revision["changed"]
    }
    assert causes == {
        ("scenario_001", S): "a_cause",
        ("scenario_002", F): "regenerated_upstream_fix",
        ("scenario_004", S): "regenerated_upstream_fix",
        ("scenario_006", "local_income_tax"): (
            "excluded_reference_depends_on_unlisted_input"
        ),
        ("scenario_002", S): "engine_upgrade_within_1",
    }
    (rechecked,) = revision["excluded_outputs_rechecked"]
    assert rechecked == {
        "scenario_id": "scenario_003",
        "variable": "snap",
        "kept_value": 3000.0,
        "value_on_9_9_9": 2900.0,
        "reason": "Not fixed.",
    }
    assert [build.key_of(r) for r in revision["regenerated_exclusions"]] == [
        ("scenario_002", F),
        ("scenario_004", S),
    ]
    # No release spec rules exclusions here, so the revision lists none kept.
    assert "kept_exclusions_from_release" not in revision
    keys = [build.key_of(r) for r in written.exclusions["exclusions"]]
    assert keys == [
        ("scenario_003", "snap"),
        ("scenario_006", "snap"),
        ("scenario_004", F),
        ("scenario_005", S),
        ("scenario_006", "local_income_tax"),
        ("scenario_023", FLAG),
    ]
    assert written.exclusions["derivation"].startswith("Derived. On 2026-10-23")
    derivation = written.exclusions["derivation"]
    assert "from policyengine-us 2.41.0 to policyengine-us 9.9.9" in derivation
    assert "(reference_audit/2026-10-22-engine-upgrade)" in derivation
    assert "behind two excluded outputs" in derivation
    assert "sidecar's fourth engine_upgrade revision" in derivation
    assert "One scored output the new engine moved was excluded" in derivation
    assert "that stay excluded, one moved" in derivation
    values = build.parse_reference_csv(written.csv_text).values()
    assert values[("scenario_003", "snap")] == 3000.0  # rule 5: kept
    assert values[("scenario_006", "local_income_tax")] == 670.55
    assert set(written.traces) == {f"{k[0]}|{k[1]}" for k in causes}
    on_disk = (tmp_path / "reference_outputs.csv.meta.json").read_text()
    assert on_disk == build.dump_record(written.meta)
    assert (
        build.sha256_bytes(written.csv_text.encode())
        == (written.meta["reference_csv_sha256"])
    )


def test_the_papers_partition_agrees_with_the_builder(tmp_path):
    """Differential: the paper reads the written sidecar and record as the
    builder planned them (engine_upgrades_from rebuilds the record around each
    upgrade from regenerated_exclusions' removed records)."""
    from policybench.paper_results import engine_upgrades_from

    computed, actions = _full()
    _, plan, written = _write(tmp_path, computed, actions)
    *_, upgrade = engine_upgrades_from(
        written.meta["revisions"], written.exclusions["exclusions"]
    )
    assert (upgrade.previous_engine_version, upgrade.engine_version) == (
        "2.41.0",
        "9.9.9",
    )
    groups = {
        name: sorted(build.key_of(c) for c in group)
        for name, group in upgrade.partition.items()
    }
    assert groups == {
        "scored_changes": [("scenario_001", S)],
        "within_tolerance": [("scenario_002", S)],
        "new_exclusions": [("scenario_006", "local_income_tax")],
        "restored": [("scenario_002", F), ("scenario_004", S)],
    }
    assert upgrade.restored == {build.key_of(r) for r in plan.regenerated}
    assert [upgrade.rechecked_value(r) for r in upgrade.rechecked] == [2900.0]


def test_a_later_record_that_moves_is_rechecked_and_keeps_its_value(tmp_path):
    """A record decided after the 2026-09-22 audit (later law, here) that the
    new engine moves is drafted as a recheck and keeps its value (rule 5); no
    two lists may name one output."""
    computed = _unchanged()
    computed[("scenario_005", S)] = 830.0
    drafted, _ = _draft(computed)
    actions = {k: v for k, v in drafted.items() if k not in ("draft", "review")}
    assert [build.key_of(e) for e in actions["excluded_rechecked"]] == [
        ("scenario_005", S)
    ]
    build.validate_actions(actions)
    _, plan, written = _write(tmp_path, computed, actions)
    assert [build.key_of(r) for r in plan.rechecked] == [("scenario_005", S)]
    assert (
        build.parse_reference_csv(written.csv_text).values()[("scenario_005", S)]
        == 820.35
    )
    for name in ("approved", "regenerated_exclusions", "new_exclusions"):
        with pytest.raises(build.Refusal, match="is in both"):
            build.validate_actions(
                {**actions, name: [{"scenario_id": "scenario_005", "variable": S}]}
            )


def test_the_release_spec_keys_are_gone():
    """The 2026-10-12 builder drafted against a release spec; this one stages a
    build with no release, so those keys are refused as unknown."""
    for key, value in (
        ("release_spec_sha256", "spec"),
        ("kept_exclusions_from_release", []),
    ):
        with pytest.raises(build.Refusal, match="unknown actions keys"):
            build.validate_actions({**_actions(), key: value})


def test_the_written_date_must_be_the_actions_date(tmp_path):
    computed, actions = _full()
    base, plan = _plan(computed, actions)
    with pytest.raises(build.Refusal, match="does not fall on the actions date"):
        build.write_outputs(
            tmp_path,
            base,
            plan,
            actions,
            bundle={},
            fix_modules=[],
            provenance={},
            traces={},
            now="2026-10-24T00:00:01+00:00",
        )


# --- Refusals ------------------------------------------------------------------


def _problems(computed, actions) -> list[str]:
    return _plan(computed, actions)[1].problems


@SETTINGS
@given(delta=st.floats(min_value=1.01, max_value=1e5) | st.floats(-1e5, -1.01))
def test_an_unexplained_scored_move_is_refused(delta):
    computed = _unchanged()
    computed[("scenario_001", S)] += delta
    (problem,) = _problems(computed, _actions())
    assert problem.startswith("unreviewed move ('scenario_001'")


def test_a_flag_flip_is_a_move():
    computed = _unchanged()
    computed[("scenario_005", FLAG)] = 0.0
    (problem,) = _problems(computed, _actions())
    assert "unreviewed move ('scenario_005', 'head_medicaid_eligible')" in problem


@SETTINGS
@given(delta=st.floats(min_value=1.01, max_value=1e4))
def test_an_excluded_move_without_a_recheck_is_refused(delta):
    computed = _unchanged()
    computed[("scenario_006", "snap")] += delta
    (problem,) = _problems(computed, _actions())
    assert problem.startswith("excluded output moved without a recheck")


@SETTINGS
@given(delta=st.floats(min_value=-1.0, max_value=1.0))
def test_an_approved_output_that_does_not_move_is_refused(delta):
    computed = _unchanged()
    computed[("scenario_001", S)] += delta
    approved = [
        {
            "scenario_id": "scenario_001",
            "variable": S,
            "value": computed[("scenario_001", S)],
            "cause": "c",
            "basis": "b",
        }
    ]
    (problem,) = _problems(computed, _actions(approved=approved))
    assert problem.startswith("approved ('scenario_001'") and "does not move" in problem


def test_an_approved_output_that_lands_elsewhere_is_refused():
    computed = _unchanged()
    computed[("scenario_001", S)] = 1010.0
    approved = [
        {
            "scenario_id": "scenario_001",
            "variable": S,
            "value": 1010.01,
            "cause": "c",
            "basis": "b",
        }
    ]
    (problem,) = _problems(computed, _actions(approved=approved))
    assert "!= approved" in problem


@SETTINGS
@given(
    miss=st.floats(min_value=0.0, max_value=50.0),
    tolerance=st.floats(min_value=0.0, max_value=1.0),
)
def test_a_regenerated_output_must_land_within_its_tolerance(miss, tolerance):
    computed = _unchanged()
    computed[("scenario_002", F)] = 300.0 + miss
    actions = _actions(
        regenerated_exclusions=[_regenerate("scenario_002", F, 300.0, tolerance)]
    )
    problems = _problems(computed, actions)
    if abs(computed[("scenario_002", F)] - 300.0) <= tolerance:
        assert problems == []
    else:
        (problem,) = problems
        assert "misses its audited target" in problem


def test_a_regeneration_must_name_the_records_target_and_a_small_tolerance():
    computed = _unchanged()
    computed[("scenario_002", F)] = 300.0
    wrong_target = _actions(
        regenerated_exclusions=[_regenerate("scenario_002", F, 301.0)]
    )
    assert "is not the record's" in _problems(computed, wrong_target)[0]
    wide = _actions(regenerated_exclusions=[_regenerate("scenario_002", F, 300.0, 1.5)])
    assert "tolerance 1.5 outside" in _problems(computed, wide)[0]


def test_only_an_engine_defect_is_regenerated():
    computed = _unchanged()
    computed[("scenario_006", "snap")] = 0.0
    actions = _actions(
        regenerated_exclusions=[_regenerate("scenario_006", "snap", 0.0)]
    )
    (problem,) = _problems(computed, actions)
    assert "not an engine defect" in problem


# --- A fix-modules target: a record decided on an older engine ----------------
#
# scenario_003 snap's record was decided on 1.755.4 (frozen 3000, corrected
# 2500). Other engine changes have since moved the output, so its
# alternative_value is stale: the audited fix module, run on a pre-fix engine,
# gives the target instead.

PRE_FIX = "policyengine-us 9.9.8"
MODULE = "r_fix_v2.py"
EVIDENCE = {"path": "evidence/pre_fix.json", "sha256": "e" * 64}


def _evidence(engine_value=3100.0, corrected=2600.3, engine=PRE_FIX, pin="p" * 64):
    return {
        "kind": build.EVIDENCE_KIND,
        "engine": engine,
        "modules": {MODULE: pin},
        "items": [
            {
                "scenario_id": "scenario_003",
                "variable": "snap",
                "modules": [MODULE],
                "engine_value": engine_value,
                "corrected_value": corrected,
            }
        ],
    }


def _module_target(**target):
    entry = _regenerate("scenario_003", "snap", 2500.0)
    entry["target"] = {
        "kind": "fix_modules",
        "modules": [MODULE],
        "evidence": dict(EVIDENCE),
        **target,
    }
    return entry


def _module_plan(
    value=2600.0, after=2600.1, evidence=None, pins=None, entry=None, deps=None
):
    computed = _unchanged()
    computed[("scenario_003", "snap")] = value
    base = _base()
    actions = _actions(regenerated_exclusions=[entry or _module_target()])
    return build.plan_upgrade(
        base,
        actions,
        computed,
        evidence={EVIDENCE["path"]: evidence or _evidence()},
        module_pins={MODULE: "p" * 64} if pins is None else pins,
        module_values={(("scenario_003", "snap"), (MODULE,)): after},
        module_deps=deps,
    )


def test_a_fix_modules_target_pins_the_siblings_its_modules_load():
    """r02_ira_219g_v2.py runs r02_ira_219g.py: the evidence must pin that
    sibling at the bytes committed at the base, and the target records it."""
    sibling = "r_fix.py"
    deps = {MODULE: [sibling]}
    missing = _module_plan(deps=deps, pins={MODULE: "p" * 64, sibling: "s" * 64})
    assert any("does not pin the siblings" in p for p in missing.problems)
    doc = _evidence()
    doc["modules"][sibling] = "s" * 64
    plan = _module_plan(
        deps=deps, evidence=doc, pins={MODULE: "p" * 64, sibling: "s" * 64}
    )
    assert plan.problems == []
    (regenerated,) = plan.regenerated
    assert regenerated["target"]["dependencies"] == [
        {"module": sibling, "sha256": "s" * 64}
    ]
    stale = _module_plan(
        deps=deps, evidence=doc, pins={MODULE: "p" * 64, sibling: "t" * 64}
    )
    assert any("does not pin the siblings" in p for p in stale.problems)


def test_module_dependencies_are_found_transitively():
    files = {
        "a_v2.py": b"x = Path(__file__).with_name('a.py')",
        "a.py": b'y = Path(__file__).with_name( "b.json" )',
        "b.json": b"{}",
    }
    assert build.module_dependencies("a_v2.py", files.__getitem__) == ["a.py", "b.json"]
    assert build.module_dependencies("b.json", files.__getitem__) == []


def test_a_module_whose_closure_cannot_be_established_is_refused():
    """The delta review's case: c13v3_upstream_plus_r30.py loads six siblings
    through _HERE / f"{name}.py"; pinning only the wrapper would let a loaded
    sibling change unseen, so the builder refuses it."""
    with pytest.raises(build.Refusal, match="cannot be established"):
        build.module_dependencies("c13v3_upstream_plus_r30.py", build.committed_fix)
    with pytest.raises(build.Refusal, match="cannot be established"):
        build.audit_module_pins(["c13v3_upstream_plus_r30.py"])


def test_the_committed_modules_siblings_are_the_ones_they_load():
    """On the real fixes: r01, r02 and r03's v2 modules each load a sibling."""
    deps = {
        m: build.module_dependencies(m, build.committed_fix)
        for m in (
            "r01_ira_compensation_v2.py",
            "r02_ira_219g_v2.py",
            "r03_estate_income__qbi_false_v2.py",
            "r07_idaho_health_premiums_v2.py",
        )
    }
    assert deps["r01_ira_compensation_v2.py"] == ["r01_ira_compensation.py"]
    assert deps["r02_ira_219g_v2.py"] == ["r02_ira_219g.py"]
    assert deps["r03_estate_income__qbi_false_v2.py"][0] == "r03_estate_income_v2.py"
    assert deps["r07_idaho_health_premiums_v2.py"] == []


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"after": float("nan")}, "still moves"),
        ({"evidence": _evidence(corrected=float("nan"))}, "not finite"),
        ({"value": float("nan"), "after": 2600.0}, "non-finite"),
    ],
)
def test_a_non_finite_value_is_refused(kwargs, message):
    problems = _module_plan(**kwargs).problems
    assert any(message in p for p in problems), problems


def test_a_record_target_misses_a_drifted_output():
    computed = _unchanged()
    computed[("scenario_003", "snap")] = 2600.0
    actions = _actions(
        regenerated_exclusions=[_regenerate("scenario_003", "snap", 2500.0)]
    )
    (problem,) = _problems(computed, actions)
    assert "misses its audited target" in problem and "(record)" in problem


def test_a_fix_modules_target_regenerates_a_drifted_output(tmp_path):
    plan = _module_plan()
    assert plan.problems == []
    (regenerated,) = plan.regenerated
    target = regenerated["target"]
    assert target == {
        "kind": "fix_modules",
        "value": 2600.3,
        "engine": PRE_FIX,
        "engine_value": 3100.0,
        "modules": [{"module": MODULE, "sha256": "p" * 64}],
        "dependencies": [],
        "evidence": EVIDENCE["path"],
        "evidence_sha256": EVIDENCE["sha256"],
        "value_with_modules": 2600.1,
    }
    assert regenerated["audited_alternative_value"] == 2500.0
    assert regenerated["regenerated"] == 2600.0
    assert plan.new_values[("scenario_003", "snap")] == 2600.0


def test_a_record_target_is_the_default_and_names_its_engine():
    computed = _unchanged()
    computed[("scenario_002", F)] = 300.4
    actions = _actions(regenerated_exclusions=[_regenerate("scenario_002", F, 300.0)])
    (regenerated,) = _plan(computed, actions)[1].regenerated
    assert regenerated["target"] == {
        "kind": "record",
        "value": 300.0,
        "engine": "policyengine-us 1.755.4",
    }


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"evidence": _evidence(engine=ENGINE)}, "it must come from one"),
        (
            {"evidence": _evidence(engine="policyengine-us 10.0.0")},
            "not an engine older",
        ),
        ({"pins": {MODULE: "q" * 64}}, "ran other bytes"),
        ({"pins": {}}, "unknown fix modules"),
        ({"evidence": _evidence(corrected=3100.5)}, "shows no defect"),
        ({"after": 2590.0}, "still moves it"),
        ({"value": 2610.0, "after": 2610.0}, "misses its audited target"),
        (
            {"entry": _module_target(modules=["other.py"]), "pins": {"other.py": "0"}},
            "has 0 items",
        ),
        ({"entry": _module_target(modules=[])}, "names no modules"),
        ({"entry": _module_target(extra=1)}, "takes kind, modules and evidence"),
        (
            {"entry": _module_target(evidence={"path": "x", "sha256": "0"})},
            "evidence is not loaded",
        ),
        ({"entry": _module_target(kind="guess")}, "unknown target kind"),
    ],
)
def test_a_fix_modules_target_refuses(kwargs, message):
    problems = _module_plan(**kwargs).problems
    assert problems and any(message in p for p in problems), problems


def test_a_record_target_takes_no_other_fields():
    computed = _unchanged()
    computed[("scenario_002", F)] = 300.0
    entry = _regenerate("scenario_002", F, 300.0)
    entry["target"] = {"kind": "record", "modules": [MODULE]}
    (problem,) = _problems(computed, _actions(regenerated_exclusions=[entry]))
    assert "takes no other fields" in problem


@SETTINGS
@given(
    effect=st.floats(min_value=1.01, max_value=5e3) | st.floats(-5e3, -1.01),
    drift=st.floats(min_value=-5e3, max_value=5e3),
    landing=st.floats(min_value=-3.0, max_value=3.0),
    leftover=st.floats(min_value=-3.0, max_value=3.0),
)
def test_a_fix_modules_regeneration_needs_a_landing_and_nothing_left_to_fix(
    effect, drift, landing, leftover
):
    """On the pre-fix engine the module moves the output by ``effect``; the new
    engine lands ``landing`` from the corrected value, and the module, applied
    again there, moves it by ``leftover``. It regenerates exactly when both
    are within $1."""
    before = 3000.0 + drift
    corrected = before + effect
    value = corrected + landing
    plan = _module_plan(
        value=value,
        after=value + leftover,
        evidence=_evidence(engine_value=before, corrected=corrected),
    )
    ok = abs(landing) <= 1.0 and abs(leftover) <= 1.0
    assert (plan.problems == []) == ok, plan.problems
    if ok:
        assert plan.new_values.get(("scenario_003", "snap"), 3000.0) in (value, 3000.0)
        assert [r["target"]["value"] for r in plan.regenerated] == [corrected]


def test_the_derivation_names_the_audited_corrected_value(tmp_path):
    computed, actions = _full()
    _, _, written = _write(tmp_path, computed, actions)
    derivation = written.exclusions["derivation"]
    assert "within $1 of its audited corrected value" in derivation or (
        "each landing within $1 of its audited corrected value" in derivation
    )
    assert "record's corrected value" not in derivation


@SETTINGS
@given(delta=st.floats(min_value=-1.0, max_value=1.0))
def test_a_new_exclusion_on_an_output_that_does_not_move_is_refused(delta):
    computed = _unchanged()
    computed[("scenario_006", "local_income_tax")] = delta
    actions = _actions(new_exclusions=[_new_exclusion("scenario_006", delta)])
    problems = _problems(computed, actions)
    assert any("does not move" in p for p in problems)


def test_a_new_exclusion_must_carry_the_engine_value_and_date():
    computed = _unchanged()
    computed[("scenario_006", "local_income_tax")] = 670.55
    record = _new_exclusion("scenario_006", 670.0)
    record["decided_on"] = "2026-10-22"
    problems = _problems(computed, _actions(new_exclusions=[record]))
    assert len(problems) == 2
    assert "frozen_value 670.0 != engine 670.55" in problems[0]
    assert "decided_on '2026-10-22' != '2026-10-23'" in problems[1]


def test_a_rechecked_output_that_does_not_move_is_refused():
    actions = _actions(
        excluded_rechecked=[
            {"scenario_id": "scenario_006", "variable": "snap", "reason": "r"}
        ]
    )
    (problem,) = _problems(_unchanged(), actions)
    assert problem.startswith("rechecked ('scenario_006', 'snap') does not move")


def test_actions_on_the_wrong_kind_of_output_are_refused():
    computed = _unchanged()
    computed[("scenario_003", "snap")] = 0.0
    approved = [
        {
            "scenario_id": "scenario_003",
            "variable": "snap",
            "value": 0.0,
            "cause": "c",
            "basis": "b",
        }
    ]
    problems = _problems(computed, _actions(approved=approved))
    assert any(
        "approved names ('scenario_003', 'snap'), which is excluded" in p
        for p in problems
    )
    rechecked = [{"scenario_id": "scenario_001", "variable": S, "reason": "r"}]
    problems = _problems(_unchanged(), _actions(excluded_rechecked=rechecked))
    assert problems == [
        f"excluded_rechecked names ('scenario_001', '{S}'), which is scored"
    ]


def test_the_actions_file_is_validated():
    with pytest.raises(build.Refusal, match="draft"):
        build.validate_actions({**_actions(), "draft": True})
    build.validate_actions({**_actions(), "draft": True}, allow_draft=True)
    with pytest.raises(build.Refusal, match="unknown actions keys"):
        build.validate_actions({**_actions(), "approve": []})
    twice = _actions(
        approved=[{"scenario_id": "scenario_001", "variable": S}],
        excluded_rechecked=[{"scenario_id": "scenario_001", "variable": S}],
    )
    with pytest.raises(
        build.Refusal, match="is in both approved and excluded_rechecked"
    ):
        build.validate_actions(twice)
    with pytest.raises(build.Refusal, match="policyengine-us X.Y.Z"):
        build.validate_actions({**_actions(), "engine": "2.36.0"})


def test_a_previous_engine_other_than_the_base_is_refused():
    problems = _problems(
        _unchanged(), {**_actions(), "previous_engine": "policyengine-us 2.2.1"}
    )
    assert problems == [
        "previous_engine is policyengine-us 2.2.1, not policyengine-us 2.41.0"
    ]


# --- Properties --------------------------------------------------------------


@SETTINGS
@given(
    federal=st.floats(min_value=299.0, max_value=301.0),
    later=st.floats(min_value=689.0, max_value=691.0),
)
def test_a_removed_record_is_scored_at_its_new_value(tmp_path, federal, later):
    computed = _unchanged()
    computed[("scenario_002", F)] = federal
    computed[("scenario_004", S)] = later
    actions = _actions(
        regenerated_exclusions=[
            _regenerate("scenario_002", F, 300.0),
            _regenerate("scenario_004", S, 690.0),
        ]
    )
    _, plan, written = _write(tmp_path, computed, actions)
    values = build.parse_reference_csv(written.csv_text).values()
    excluded = {build.key_of(r) for r in written.exclusions["exclusions"]}
    for key, value in ((("scenario_002", F), federal), (("scenario_004", S), later)):
        assert key not in excluded
        assert values[key] == value
        (change,) = [c for c in plan.changed if build.key_of(c) == key]
        assert (
            change["regenerated"] == value
            and change["cause"] == "regenerated_upstream_fix"
        )
    (removed,) = [
        r
        for r in written.meta["revisions"][-1]["regenerated_exclusions"]
        if build.key_of(r) == ("scenario_002", F)
    ]
    assert removed["record"] == BASE_RECORDS[0]
    assert removed["value_on_9_9_9"] == federal


@SETTINGS
@given(
    moves=st.dictionaries(
        st.sampled_from([(s, v) for s, v, _, _ in ROWS]),
        st.floats(min_value=-1.0, max_value=1.0),
    )
)
def test_unchanged_outputs_keep_their_bytes(tmp_path, moves):
    """Moves within the tolerance, anywhere: excluded outputs keep their values,
    scored ones take the engine's and are listed; every other row keeps its
    bytes; earlier revisions keep theirs."""
    computed = _unchanged()
    for key, delta in moves.items():
        if key[1].endswith("_eligible"):  # a 0/1 flag: any change is a move
            continue
        computed[key] += delta
    base, plan, written = _write(tmp_path, computed, _actions())
    excluded = {build.key_of(r) for r in base.exclusions["exclusions"]}
    rows = build.parse_reference_csv(written.csv_text).rows
    listed = {build.key_of(c) for c in plan.within}
    for old, new in zip(base.reference.rows, rows, strict=True):
        if old.key in excluded or abs(computed[old.key] - old.value) <= build.EPS:
            assert new.raw == old.raw
            assert old.key not in listed
        else:
            assert new.value == computed[old.key]
            assert old.key in listed
    for before, after in zip(base.meta["revisions"], written.meta["revisions"]):
        assert json.dumps(before) == json.dumps(after)


@SETTINGS
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_the_records_do_not_depend_on_the_actions_order(tmp_path, seed):
    computed, actions = _full()
    shuffled = copy.deepcopy(actions)
    rng = random.Random(seed)
    for name in (
        "approved",
        "regenerated_exclusions",
        "new_exclusions",
        "excluded_rechecked",
    ):
        rng.shuffle(shuffled[name])
    shuffled["new_exclusions"].append(_new_exclusion("scenario_001", 50.0))
    computed = {**computed, ("scenario_001", "local_income_tax"): 50.0}
    actions = {
        **actions,
        "new_exclusions": actions["new_exclusions"]
        + [_new_exclusion("scenario_001", 50.0)],
    }
    rng.shuffle(shuffled["new_exclusions"])
    _, _, first = _write(tmp_path / "a", computed, actions)
    _, _, second = _write(tmp_path / "b", computed, shuffled)
    for name in (
        "reference_exclusions.json",
        "reference_outputs.csv",
        "reference_outputs.csv.meta.json",
    ):
        assert (tmp_path / "a" / name).read_bytes() == (
            tmp_path / "b" / name
        ).read_bytes()
    keys = [build.key_of(r) for r in first.exclusions["exclusions"]]
    assert keys[-3:] == [
        ("scenario_001", "local_income_tax"),
        ("scenario_006", "local_income_tax"),
        ("scenario_023", FLAG),
    ]


@SETTINGS
@given(
    values=st.dictionaries(
        st.sampled_from([(s, v) for s, v, _, _ in ROWS]),
        st.floats(allow_nan=False, allow_infinity=False, width=32),
    )
)
def test_rendering_rewrites_only_the_named_rows(values):
    reference = build.parse_reference_csv(_csv_text())
    text = build.render_reference_csv(reference, values)
    rows = build.parse_reference_csv(text).rows
    for old, new in zip(reference.rows, rows, strict=True):
        if old.key in values:
            assert new.value == float(values[old.key])
            assert new.fields[3] == old.fields[3]
        else:
            assert new.raw == old.raw


# --- The real base ---------------------------------------------------------------


@pytest.fixture(scope="module")
def real_base():
    return build.load_base()


def test_the_base_is_release_20261014(real_base):
    assert len(real_base.reference.rows) == 1984
    assert len(real_base.exclusions["exclusions"]) == 49
    kinds = [r["kind"] for r in real_base.meta["revisions"]]
    assert kinds.count("engine_upgrade") == 3 and kinds[-1] == "engine_upgrade"
    assert real_base.meta["revisions"][-1]["engine_version"] == build.PREVIOUS_ENGINE
    assert build.key_of(real_base.exclusions["exclusions"][-1]) == build.AUDIT_TAIL
    # The base CSV round-trips byte for byte through the row parser.
    raw = build.git_blob(build.BASE_COMMIT, f"{build.RUN}/reference_outputs.csv")
    assert build.render_reference_csv(real_base.reference, {}) == raw.decode()


def test_the_base_commit_is_on_main_and_its_references_are_2_41_0s():
    """BASE_COMMIT (release 20261014, #221) is an ancestor of HEAD, and its four
    reference files are release 20261013's (#217), which installed 2.41.0."""
    import subprocess

    ancestor = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "merge-base",
            "--is-ancestor",
            build.BASE_COMMIT,
            "HEAD",
        ],
        capture_output=True,
    )
    assert ancestor.returncode == 0
    for name, pin in build.BASE_SHA256.items():
        blob = build.git_blob(
            "bc305793c527531e7b3573dc789a436a7bc883d5", f"{build.RUN}/{name}"
        )
        assert build.sha256_bytes(blob) == pin, name


def test_the_snapshot_holds_the_base_or_this_build():
    """Until a board release installs this build, the snapshot's reference
    files are the base's; once one installs it, they are the build's. Either
    way each file is one of the two, and the three move together."""
    names = (
        "reference_outputs.csv",
        "reference_outputs.csv.meta.json",
        "reference_exclusions.json",
    )
    on_disk = [build.sha256(RUN_DIR / n) for n in names]
    base = [build.BASE_SHA256[n] for n in names]
    built = [build.sha256(BUILD / n) for n in names]
    assert on_disk in (base, built)


def test_the_fix_modules_are_the_first_upgrades(real_base, tmp_path):
    """In place, the conventions are the 2026-09-29 upgrade's; the sales tax
    tables must sit beside them."""
    import shutil

    for path in build.FIXES.glob("*.py"):
        shutil.copy(path, tmp_path / path.name)
    with pytest.raises(build.Refusal, match="r19_irs_sales_tax_2025.json is missing"):
        build.fix_module_pins(real_base.meta, tmp_path)
    shutil.copy(build.SALES_TAX_SOURCE, tmp_path / build.SALES_TAX_TABLES)
    pins = build.fix_module_pins(real_base.meta, tmp_path)
    assert [p["module"] for p in pins][-2:] == [
        "latest_final.py",
        build.SALES_TAX_TABLES,
    ]
    assert len(pins) == 13
    (tmp_path / "latest_c_md_2026.py").write_text("# edited\n")
    with pytest.raises(build.Refusal, match="latest_c_md_2026.py is not the module"):
        build.fix_module_pins(real_base.meta, tmp_path)


def test_the_fix_entry_tables_and_harness_are_pinned_in_place(
    real_base, tmp_path, monkeypatch
):
    """Imported in place, latest_final.py, the sales tax tables and sweep.py
    are each checked against the bytes committed at the base commit, not
    against themselves."""
    import shutil

    for path in build.FIXES.glob("*.py"):
        shutil.copy(path, tmp_path / path.name)
    shutil.copy(build.SALES_TAX_SOURCE, tmp_path / build.SALES_TAX_TABLES)
    monkeypatch.setattr(build, "FIXES", tmp_path)
    build.fix_module_pins(real_base.meta, tmp_path)
    entry = tmp_path / "latest_final.py"
    original = entry.read_bytes()
    entry.write_bytes(original + b"# edited\n")
    with pytest.raises(build.Refusal, match="latest_final.py is not"):
        build.fix_module_pins(real_base.meta, tmp_path)
    entry.write_bytes(original)
    tables = tmp_path / build.SALES_TAX_TABLES
    tables.write_text(tables.read_text() + " ")
    monkeypatch.setattr(build, "SALES_TAX_SOURCE", tables)
    with pytest.raises(build.Refusal, match="r19_irs_sales_tax_2025.json is not"):
        build.fix_module_pins(real_base.meta, tmp_path)

    assert build.harness_pin()["sha256"] == build.sha256(build.HARNESS)
    harness = tmp_path / "sweep.py"
    harness.write_text(build.HARNESS.read_text() + "# edited\n")
    with pytest.raises(build.Refusal, match="sweep.py is not"):
        build.harness_pin(harness)


def test_the_real_base_on_its_own_values_plans_no_change(real_base):
    """A stub engine that returns 20261014's values: the plan changes
    nothing."""
    computed = real_base.reference.values()
    plan = build.plan_upgrade(real_base, _actions(), computed)
    assert plan.problems == [] and plan.changed == [] and plan.within == []


# --- Narratives ----------------------------------------------------------------


EXPLANATIONS = (
    "country,scenario_id,variable,reference_value,trace_lines,explanation,error\n"
    f'us,scenario_001,{S},1000.0,3,"Old, text.",\n'
    "us,scenario_001,local_income_tax,0.0,1,No local tax.,\n"
    f'us,scenario_002,{S},500.25,2,"Said ""500.25"".",\n'
    "us,scenario_002,federal_income_tax_before_refundable_credits,250.5,4,Fed.,\n"
    'us,scenario_003,snap,3000.0,9,"Multi\nline",\n'
    "us,scenario_004,state_income_tax_before_refundable_credits,700.0,1,AZ.,\n"
    "us,scenario_006,local_income_tax,0.0,1,No county.,\n"
)


class _Response:
    def __init__(self, text):
        self.choices = [
            types.SimpleNamespace(message=types.SimpleNamespace(content=text))
        ]


def _scenarios():
    import pandas as pd

    return pd.DataFrame(
        [
            {
                "scenario_id": f"scenario_00{i}",
                "state": "IN",
                "filing_status": "single",
                "num_adults": 1,
                "num_children": 0,
                "total_income": 1000.0,
            }
            for i in range(1, 8)
        ]
    )


def _narrate(tmp_path, completion, hand=None):
    computed, actions = _full()
    del actions["new_exclusions"][0]
    computed[("scenario_006", "local_income_tax")] = 0.0
    _write(tmp_path, computed, actions)
    return narratives.write_narratives(
        tmp_path, EXPLANATIONS, _scenarios(), completion=completion, hand_corrected=hand
    )


def test_narratives_rewrite_only_the_changed_rows(tmp_path):
    prompts = []

    def completion(**kwargs):
        prompts.append(kwargs)
        value = float(
            kwargs["messages"][0]["content"]
            .split("REFERENCE VALUE: ")[1]
            .split("\n")[0]
        )
        return _Response(f"# Heading\nPolicyEngine gives ${narratives.money(value)}.")

    text, results = _narrate(tmp_path, completion)
    assert {r[:2] for r in results} == {
        ("scenario_001", S),
        ("scenario_002", F),
        ("scenario_004", S),
        ("scenario_002", S),
    }
    assert all(p["model"] == "claude-haiku-4-5" for p in prompts)
    assert all("policyengine-us 9.9.9" in p["messages"][0]["content"] for p in prompts)
    old = narratives.parse_rows(EXPLANATIONS)[1]
    new = narratives.parse_rows(text)[1]
    changed = {r[:2] for r in results}
    for (fields, raw), (new_fields, new_raw) in zip(old, new, strict=True):
        if (fields[1], fields[2]) in changed:
            assert new_fields[5].startswith("PolicyEngine gives $")
            assert new_fields[4] == "2" and new_fields[6] == ""
        else:
            assert raw == new_raw
    assert f"us,scenario_001,{S},1010.0,2,PolicyEngine gives $1,010." not in text
    assert '1010.0,2,"PolicyEngine gives $1,010."' in text


def test_the_narratives_need_the_fourth_engine_upgrade(tmp_path):
    computed, actions = _full()
    del actions["new_exclusions"][0]
    computed[("scenario_006", "local_income_tax")] = 0.0
    _write(tmp_path, computed, actions)
    sidecar = tmp_path / "reference_outputs.csv.meta.json"
    meta = json.loads(sidecar.read_text())
    meta["revisions"] = [r for r in meta["revisions"] if r["date"] != "2026-10-13"]
    sidecar.write_text(json.dumps(meta))
    with pytest.raises(build.Refusal, match="fourth engine upgrade"):
        narratives.write_narratives(
            tmp_path, EXPLANATIONS, _scenarios(), completion=_value_narrator()
        )


def _value_narrator(mention: str = ""):
    def completion(**kwargs):
        value = float(
            kwargs["messages"][0]["content"]
            .split("REFERENCE VALUE: ")[1]
            .split("\n")[0]
        )
        return _Response(f"PolicyEngine gives ${narratives.money(value)}.{mention}")

    return completion


def test_a_rebuild_reuses_the_narratives_whose_writer_inputs_are_unchanged(tmp_path):
    """Build A on 9.9.9, build B on 9.9.10 with one approved value moved: B
    reuses A's narratives for every changed output whose value, cause,
    grounding (the engine's name aside), variable and trace are A's, and only
    those; a narrative that names A's engine is written again."""
    computed, actions = _full()
    del actions["new_exclusions"][0]
    computed[("scenario_006", "local_income_tax")] = 0.0
    _write(tmp_path / "a", computed, actions)
    text_a, _ = narratives.write_narratives(
        tmp_path / "a", EXPLANATIONS, _scenarios(), completion=_value_narrator()
    )
    later = copy.deepcopy(actions)
    later["engine"] = "policyengine-us 9.9.10"
    later["approved"][0]["value"] = 1020.0
    moved = dict(computed)
    moved[("scenario_001", S)] = 1020.0
    _write(tmp_path / "b", moved, later)
    reuse = narratives.reusable_narratives(tmp_path / "b", tmp_path / "a", text_a)
    assert set(reuse) == {("scenario_002", F), ("scenario_004", S), ("scenario_002", S)}
    calls = []

    def counting(**kwargs):
        calls.append(kwargs)
        return _value_narrator()(**kwargs)

    text_b, results = narratives.write_narratives(
        tmp_path / "b", EXPLANATIONS, _scenarios(), completion=counting, reuse=reuse
    )
    assert len(calls) == 1 and "1020.0" in calls[0]["messages"][0]["content"]
    rows_a = {(f[1], f[2]): f for f, _ in narratives.parse_rows(text_a)[1]}
    rows_b = {(f[1], f[2]): f for f, _ in narratives.parse_rows(text_b)[1]}
    for key in reuse:
        assert rows_b[key] == rows_a[key]
    named, _ = narratives.write_narratives(
        tmp_path / "a",
        EXPLANATIONS,
        _scenarios(),
        completion=_value_narrator(" On policyengine-us 9.9.9."),
    )
    assert narratives.reusable_narratives(tmp_path / "b", tmp_path / "a", named) == {}
    same = narratives.reusable_narratives(tmp_path / "a", tmp_path / "a", named)
    assert set(same) == {
        ("scenario_001", S),
        ("scenario_002", F),
        ("scenario_004", S),
        ("scenario_002", S),
    }


@pytest.mark.parametrize(
    "text, value, ok",
    [
        ("Refundable credits are $0.00.", 0.0, True),
        ("Refundable credits are $0.", 0.0, True),
        ("In tax year 2026 the household gets nothing.", 0.0, False),
        ("Tax is $1,916.61 after credits.", 1916.606201, True),
        ("Tax is $1,916 after credits.", 1916.606201, False),
        ("The refund is -$12.50.", -12.5, True),
        ("It owes $2,116.61 before a $200 credit.", 1916.61, False),
    ],
)
def test_a_narrative_states_its_amount_as_dollars_to_the_cent(text, value, ok):
    assert narratives.states_amount(text, value) is ok


@SETTINGS
@given(cents=st.integers(min_value=0, max_value=10**9))
def test_a_formatted_amount_is_always_recognized(cents):
    value = cents / 100
    assert narratives.states_amount(f"PolicyEngine gives ${value:,.2f}.", value)
    assert narratives.states_amount(
        f"PolicyEngine gives ${narratives.money(value)}.", value
    )


def test_reuse_refuses_a_narratives_file_from_another_build(tmp_path):
    computed, actions = _full()
    del actions["new_exclusions"][0]
    computed[("scenario_006", "local_income_tax")] = 0.0
    _write(tmp_path / "a", computed, actions)
    text_a, _ = narratives.write_narratives(
        tmp_path / "a", EXPLANATIONS, _scenarios(), completion=_value_narrator()
    )
    assert narratives.reusable_narratives(tmp_path / "a", tmp_path / "a", text_a)
    with pytest.raises(build.Refusal, match="is not --reuse-from's narratives"):
        narratives.reusable_narratives(tmp_path / "a", tmp_path / "a", EXPLANATIONS)


@pytest.mark.parametrize("stated", ["nan", "inf", "-inf", "", "n/a"])
def test_reuse_refuses_a_source_value_that_is_not_a_finite_number(tmp_path, stated):
    computed, actions = _full()
    del actions["new_exclusions"][0]
    computed[("scenario_006", "local_income_tax")] = 0.0
    _write(tmp_path / "a", computed, actions)
    text_a, _ = narratives.write_narratives(
        tmp_path / "a", EXPLANATIONS, _scenarios(), completion=_value_narrator()
    )
    rows = {(f[1], f[2]): (f, raw) for f, raw in narratives.parse_rows(text_a)[1]}
    fields, raw = rows[("scenario_002", F)]
    edited = raw.replace(f",{fields[3]},", f",{stated},", 1)
    assert edited != raw
    with pytest.raises(build.Refusal, match="is not --reuse-from's narratives"):
        narratives.reusable_narratives(
            tmp_path / "a", tmp_path / "a", text_a.replace(raw, edited)
        )


def test_a_narrative_that_omits_the_value_is_retried_then_refused(tmp_path):
    calls = []

    def stubborn(**kwargs):
        calls.append(kwargs)
        return _Response("No figure here.")

    with pytest.raises(build.Refusal, match="omits"):
        _narrate(tmp_path, stubborn)
    assert len(calls) == 1 + narratives.RETRIES
    assert "must state the value" in calls[-1]["messages"][0]["content"]


def test_hand_corrected_narratives_must_state_the_value_and_be_changed(tmp_path):
    def completion(**kwargs):
        value = float(
            kwargs["messages"][0]["content"]
            .split("REFERENCE VALUE: ")[1]
            .split("\n")[0]
        )
        return _Response(f"Gives ${narratives.money(value)}.")

    hand = {f"scenario_001|{S}": "Corrected: $1,010 of tax."}
    text, _ = _narrate(tmp_path / "a", completion, hand)
    assert "Corrected: $1,010 of tax." in text
    with pytest.raises(build.Refusal, match="did not change"):
        _narrate(tmp_path / "b", completion, {"scenario_003|snap": "x"})
    with pytest.raises(build.Refusal, match="omits"):
        _narrate(tmp_path / "c", completion, {f"scenario_001|{S}": "No value."})


def test_a_new_exclusion_is_grounded_on_its_alternative_reading():
    item = {
        "scenario_id": "s",
        "variable": "v",
        "cause": "excluded_reference_depends_on_unlisted_input",
        "basis": "b",
    }
    record = {
        "reason_code": "reference_depends_on_unlisted_input",
        "alternative_reading": "Read so.",
    }
    text = narratives.grounding_for(item, {("s", "v"): record})
    assert text.endswith("an input the prompt does not state. Read so.")
    assert narratives.grounding_for({**item, "cause": "a"}, {("s", "v"): record}) == "b"


def test_the_writer_is_anthropics(tmp_path, monkeypatch):
    import policybench.case_reference_explanations as writer

    monkeypatch.setattr(writer, "REFERENCE_MODEL", "gpt-6-luna")
    with pytest.raises(build.Refusal, match="Anthropic"):
        _narrate(tmp_path, lambda **_: _Response(""))


def _narration_inputs(tmp_path):
    computed, actions = _full()
    del actions["new_exclusions"][0]
    computed[("scenario_006", "local_income_tax")] = 0.0
    _, plan, _ = _write(tmp_path / "build", computed, actions)
    explanations = tmp_path / "explanations.csv"
    explanations.write_text(EXPLANATIONS)
    hand = {
        f"{c['scenario_id']}|{c['variable']}": (
            f"Hand: ${narratives.money(c['regenerated'])}."
        )
        for c in plan.changed + plan.within
    }
    return explanations, hand


def test_the_narrative_run_never_uses_an_openai_key(tmp_path, monkeypatch):
    """Without a key, a run that would call the writer is refused; a run whose
    narratives are all hand-corrected needs none and never calls it. Neither
    keeps an OpenAI key in its environment."""
    import os

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    explanations, hand = _narration_inputs(tmp_path)
    args = [
        "--references",
        str(tmp_path / "build"),
        "--explanations",
        str(explanations),
        "--out",
        str(tmp_path / "out.csv"),
    ]
    with pytest.raises(build.Refusal, match="ANTHROPIC_API_KEY"):
        narratives.main(args)
    assert "OPENAI_API_KEY" not in os.environ
    partial = dict(list(hand.items())[1:])
    (tmp_path / "partial.json").write_text(json.dumps(partial))
    with pytest.raises(build.Refusal, match="1 narratives need the writer"):
        narratives.main([*args, "--hand-corrected", str(tmp_path / "partial.json")])
    (tmp_path / "hand.json").write_text(json.dumps(hand))
    narratives.main([*args, "--hand-corrected", str(tmp_path / "hand.json")])
    written = (tmp_path / "out.csv").read_text()
    for text in hand.values():
        assert text in written


def test_the_committed_explanations_round_trip_byte_for_byte():
    path = ROOT / "annotations" / "us_full_run_20260612_policyengine_4_16_1_populace"
    text = (path / "us_case_reference_explanations.csv").read_text()
    assert narratives.rewrite_explanations(text, {}) == text


# --- Draft actions ---------------------------------------------------------------


def _cells(computed, states=None):
    base = _base()
    states = states or {}
    return [
        drafting.Cell(
            r.key[0],
            states.get(r.key, "XX"),
            r.key[1],
            r.value,
            computed[r.key],
            "",
            "",
        )
        for r in base.reference.rows
    ]


def _draft(computed, states=None, records=None, earlier=None, **kwargs):
    base = _base()
    records = records or {build.key_of(r): r for r in base.exclusions["exclusions"]}
    return drafting.draft_actions(
        _cells(computed, states),
        records,
        earlier or {},
        THIRD_REVISION,
        engine_version="9.9.9",
        date=DATE,
        precise=True,
        **kwargs,
    )


def test_the_draft_places_every_moved_output_and_prints_each_call(tmp_path):
    computed, _ = _full()
    computed[("scenario_001", "local_income_tax")] = 670.55
    computed[("scenario_006", "local_income_tax")] = 0.0
    computed[("scenario_007", "snap")] = 288.0
    computed[("scenario_007", "free_school_meals_eligible")] = 1.0
    states = {
        ("scenario_001", "local_income_tax"): "IN",
        ("scenario_001", S): "ZZ",
        ("scenario_007", "snap"): "CA",
        ("scenario_007", "free_school_meals_eligible"): "PA",
    }
    actions, calls = _draft(computed, states)
    assert actions["draft"] is True
    assert set(actions) == {
        "engine",
        "previous_engine",
        "date",
        "draft",
        "approved",
        "regenerated_exclusions",
        "new_exclusions",
        "excluded_rechecked",
        "review",
    }
    placed = {
        (c["scenario_id"], c["variable"]): (c["decision"], c["placed_in"])
        for c in calls
    }
    assert placed == {
        ("scenario_001", S): ("UNDECIDED", "review only"),
        ("scenario_001", "local_income_tax"): ("UNDECIDED", "review only"),
        ("scenario_002", F): ("PROPOSED", "regenerated_exclusions"),
        ("scenario_004", S): ("PROPOSED", "regenerated_exclusions"),
        ("scenario_003", "snap"): ("PROPOSED", "excluded_rechecked"),
        ("scenario_007", "snap"): ("PROPOSED", "approved"),
        ("scenario_007", "free_school_meals_eligible"): ("PROPOSED", "approved"),
    }
    # The records name no upstream fix, so the builder refuses the regenerations
    # until a reviewer names them; cleared, the draft builds except for the
    # undecided moves.
    base = _base()
    cleared = {k: v for k, v in actions.items() if k not in ("draft", "review")}
    build.validate_actions(cleared)
    problems = build.plan_upgrade(base, cleared, computed).problems
    assert problems == [
        f"unreviewed move ('scenario_001', '{S}'): 1000.0 -> 1010.0",
        "unreviewed move ('scenario_001', 'local_income_tax'): 0.0 -> 670.55",
        f"regenerated ('scenario_002', '{F}') names no upstream fix ('to be filed')",
        f"regenerated ('scenario_004', '{S}') names no upstream fix ('to be filed')",
    ]
    for entry in cleared["regenerated_exclusions"]:
        entry["upstream"] = "PolicyEngine/policyengine-us#1"
    problems = build.plan_upgrade(base, cleared, computed).problems
    assert problems == [
        f"unreviewed move ('scenario_001', '{S}'): 1000.0 -> 1010.0",
        "unreviewed move ('scenario_001', 'local_income_tax'): 0.0 -> 670.55",
    ]


def test_the_draft_keeps_an_on_target_record_that_names_a_second_reason():
    computed = _unchanged()
    computed[("scenario_002", F)] = 300.0
    base = _base()
    records = {build.key_of(r): copy.deepcopy(r) for r in base.exclusions["exclusions"]}
    records[("scenario_002", F)]["note"] = (
        "The output also moves under r23 (unlisted input)."
    )
    actions, calls = _draft(computed, records=records)
    assert actions["regenerated_exclusions"] == []
    (entry,) = actions["excluded_rechecked"]
    assert "names a second reason" in entry["reason"]
    assert calls[0]["placed_in"] == "excluded_rechecked"


def test_an_unlisted_input_record_the_engine_lands_on_stays_excluded():
    """scenario_006 snap's record is an unlisted input with alternative $0; an
    engine that now gives $0 takes that reading by a default, which does not
    state the input: the draft rechecks it, and the builder refuses to
    regenerate it (only an engine defect is regenerated)."""
    computed = _unchanged()
    computed[("scenario_006", "snap")] = 0.0
    actions, calls = _draft(computed)
    assert actions["regenerated_exclusions"] == []
    (entry,) = actions["excluded_rechecked"]
    assert "the record's alternative value" in entry["reason"]
    assert "an engine default does not settle it" in entry["reason"]
    assert entry["reason"].count("which") <= 1
    (call,) = calls
    assert "lands on the alternative reading" in call["call"]
    cleared = {k: v for k, v in actions.items() if k not in ("draft", "review")}
    assert build.plan_upgrade(_base(), cleared, computed).problems == []
    regenerate = _actions(
        regenerated_exclusions=[_regenerate("scenario_006", "snap", 0.0)]
    )
    (problem,) = _problems(computed, regenerate)
    assert "not an engine defect" in problem


def test_a_value_the_previous_upgrade_found_on_target_keeps_that_finding():
    """The 2026-10-13 recheck found scenario_003 snap on its corrected value and
    kept it excluded for a second reason. The engine has not moved it since,
    so it misses the record's older alternative value without the defect being
    unfixed: the draft says so and keeps the second reason. A value that moved
    since is drafted as off target, with the previous engine's value."""
    computed = _unchanged()
    computed[("scenario_003", "snap")] = 2600.0
    base = _base()
    records = {build.key_of(r): copy.deepcopy(r) for r in base.exclusions["exclusions"]}
    records[("scenario_003", "snap")]["note"] = (
        "The output also moves under r23 (unlisted input)."
    )
    earlier = {
        ("scenario_003", "snap"): {
            "value_on_2_41_0": 2600.0,
            "reason": (
                "Stays excluded on policyengine-us 2.41.0: the engine gives "
                "$2,600.00, the value policyengine-us 2.38.6 gave when release "
                "20261010's recheck found it on its corrected value, but the "
                "record names a second reason that a new engine does not settle."
            ),
        }
    }
    actions, _ = _draft(computed, records=records, earlier=earlier)
    (entry,) = actions["excluded_rechecked"]
    assert "is not fixed" not in entry["reason"]
    assert (
        "the value policyengine-us 2.41.0 gave when the 2026-10-13 recheck found it "
        "on its corrected value" in entry["reason"]
    )
    assert "names a second reason" in entry["reason"]
    assert entry["reason"].endswith(
        "The value is 2.41.0's, rechecked on 2026-10-13 "
        "(the 2026-10-13 engine_upgrade revision's excluded_outputs_rechecked)."
    )
    moved = {
        ("scenario_003", "snap"): {
            **earlier[("scenario_003", "snap")],
            "value_on_2_41_0": 2550.0,
        }
    }
    actions, _ = _draft(computed, records=records, earlier=moved)
    (entry,) = actions["excluded_rechecked"]
    assert "is not fixed in this release" in entry["reason"]
    assert entry["reason"].endswith(
        "policyengine-us 2.41.0 gave $2,550.00 when it was rechecked on 2026-10-13."
    )


def test_the_draft_aims_a_drifted_record_at_its_fix_modules_evidence():
    computed = _unchanged()
    computed[("scenario_003", "snap")] = 2600.0
    without, _ = _draft(computed)
    assert without["regenerated_exclusions"] == []
    assert "$100.00 from the record's" in without["excluded_rechecked"][0]["reason"]
    doc = _evidence()
    actions, calls = _draft(computed, evidence={"ref": dict(EVIDENCE), "doc": doc})
    (entry,) = actions["regenerated_exclusions"]
    assert entry["target"] == {
        "kind": "fix_modules",
        "modules": [MODULE],
        "evidence": EVIDENCE,
    }
    assert entry["alternative_value"] == 2500.0
    assert "$2,600.30 its fix modules (r_fix_v2.py) give on" in entry["basis"]
    assert [c["placed_in"] for c in calls] == ["regenerated_exclusions"]
    cleared = {k: v for k, v in actions.items() if k not in ("draft", "review")}
    entry["upstream"] = "PolicyEngine/policyengine-us#1"
    plan = build.plan_upgrade(
        _base(),
        cleared,
        computed,
        evidence={EVIDENCE["path"]: doc},
        module_pins={MODULE: "p" * 64},
        module_values={(("scenario_003", "snap"), (MODULE,)): 2600.0},
    )
    assert plan.problems == []
    assert [r["target"]["kind"] for r in plan.regenerated] == ["fix_modules"]


def test_a_regeneration_must_name_its_upstream_fix():
    computed = _unchanged()
    computed[("scenario_002", F)] = 300.0
    for upstream in ("", "to be filed", "To be filed "):
        entry = {**_regenerate("scenario_002", F, 300.0), "upstream": upstream}
        (problem,) = _problems(computed, _actions(regenerated_exclusions=[entry]))
        assert "names no upstream fix" in problem


def test_the_draft_rules_recognize_the_documented_scored_moves():
    """The two kinds of scored move 2.60.0 makes: California MCE's minimum
    allotment (#10036) and a state's universal free breakfast (#10238). Each
    rule matches only its own move."""
    fsm = "free_school_meals_eligible"
    cells = {
        "ca_mce": drafting.Cell("s1", "CA", "snap", 0.0, 288.0, "scored", ""),
        "ca_other_amount": drafting.Cell("s1", "CA", "snap", 0.0, 300.0, "scored", ""),
        "ca_from_positive": drafting.Cell(
            "s1", "CA", "snap", 24.0, 288.0, "scored", ""
        ),
        "ny_minimum": drafting.Cell("s1", "NY", "snap", 0.0, 288.0, "scored", ""),
        "pa_breakfast": drafting.Cell("s2", "PA", fsm, 0.0, 1.0, "scored", ""),
        "ar_breakfast": drafting.Cell("s2", "AR", fsm, 0.0, 1.0, "scored", ""),
        "sc_breakfast": drafting.Cell("s2", "SC", fsm, 0.0, 1.0, "scored", ""),
        "pa_lost": drafting.Cell("s2", "PA", fsm, 1.0, 0.0, "scored", ""),
        "pa_reduced": drafting.Cell(
            "s2", "PA", "reduced_price_school_meals_eligible", 0.0, 1.0, "scored", ""
        ),
    }
    rules = {
        name: [
            propose(c, ENGINE, DATE)["rule"]
            for matches, propose in drafting.RULES
            if matches(c)
        ]
        for name, c in cells.items()
    }
    assert rules == {
        "ca_mce": ["ca_snap_mce_no_net_income_test"],
        "ca_other_amount": [],
        "ca_from_positive": [],
        "ny_minimum": [],
        "pa_breakfast": ["state_universal_free_breakfast"],
        "ar_breakfast": ["state_universal_free_breakfast"],
        "sc_breakfast": [],
        "pa_lost": [],
        "pa_reduced": [],
    }
    snap = drafting._ca_mce_minimum_allotment(cells["ca_mce"], ENGINE, DATE)["entry"]
    assert snap["value"] == 288.0 and snap["cause"].endswith("_10036")
    assert "PolicyEngine/policyengine-us#10036" in snap["basis"]
    assert "$24 a month" in snap["basis"] and "$288.00 for 2026" in snap["basis"]
    for state, law in (("PA", "Act 33 of 2023"), ("AR", "Act 123 of 2025")):
        cell = cells[f"{state.lower()}_breakfast"]
        entry = drafting._state_universal_breakfast(cell, ENGINE, DATE)["entry"]
        assert entry["value"] == 1.0 and entry["cause"].endswith("_10238")
        assert law in entry["basis"] and "#10238" in entry["basis"]
        assert "PolicyEngine returns positive annual free school meal" in entry["basis"]


def test_the_cells_table_must_be_against_20261014(tmp_path):
    board = {("scenario_001", S): 1000.0}
    path = tmp_path / "cells_pe2.60.0.csv"
    path.write_text(
        "scenario_id,state,variable,frozen_20261014,new,delta,moved,status,audited_target\n"
        f"scenario_001,IN,{S},999.0,1000.0,1.0,False,scored,\n"
    )
    with pytest.raises(build.Refusal, match="not 20261014's"):
        drafting.read_cells(path, board, None)
    assert drafting.engine_from_path(path) == "2.60.0"
    path.write_text(path.read_text().replace("999.0", "1000.0"))
    (cell,) = drafting.read_cells(path, board, None)
    assert cell.new == 1000.0 and cell.state == "IN"
    with pytest.raises(build.Refusal, match="not the table's"):
        drafting.read_cells(path, board, {("scenario_001", S): 1000.5})


def test_a_regeneration_names_the_upstream_fix_the_map_gives():
    upstreams = {
        "outputs": {"scenario_064|state": "PolicyEngine/policyengine-us#9801"},
        "root_causes": {"r02": "#10032", "r11": "#10034"},
    }
    record = {"root_cause": "r02+r11", "upstream": "to be filed"}
    assert drafting.upstream_for(record, ("scenario_005", "state"), upstreams) == (
        "#10032; #10034"
    )
    assert drafting.upstream_for(record, ("scenario_064", "state"), upstreams) == (
        "PolicyEngine/policyengine-us#9801"
    )
    partial = {"root_cause": "r02+r99", "upstream": "PolicyEngine/policyengine-us#1"}
    assert drafting.upstream_for(partial, ("s", "v"), upstreams) == (
        "PolicyEngine/policyengine-us#1"
    )
    assert drafting.upstream_for(record, ("s", "v"), None) == "to be filed"


def test_an_output_found_indeterminate_earlier_is_rechecked_not_regenerated():
    computed = _unchanged()
    computed[("scenario_003", "snap")] = 2600.0
    evidence = {"ref": dict(EVIDENCE), "doc": _evidence()}
    plain, _ = _draft(computed, evidence=evidence)
    assert [build.key_of(e) for e in plain["regenerated_exclusions"]] == [
        ("scenario_003", "snap")
    ]
    actions, calls = _draft(
        computed,
        evidence=evidence,
        indeterminate={("scenario_003", "snap"): "2026-09-29"},
    )
    assert actions["regenerated_exclusions"] == []
    (entry,) = actions["excluded_rechecked"]
    assert drafting.INDETERMINATE in entry["reason"]
    assert "the 2026-09-29 recheck found" in entry["reason"]
    assert "second reason" in entry["reason"]
    (call,) = [c for c in calls if c["scenario_id"] == "scenario_003"]
    assert call["placed_in"] == "excluded_rechecked"


def test_indeterminate_rechecks_reads_every_upgrade_revision():
    meta = {
        "revisions": [
            {"kind": "convention", "date": "2026-09-22"},
            {
                "kind": "engine_upgrade",
                "date": "2026-09-29",
                "excluded_outputs_rechecked": [
                    {
                        "scenario_id": "scenario_001",
                        "variable": "snap",
                        "reason": f"... {drafting.INDETERMINATE}, and stays excluded.",
                    },
                    {"scenario_id": "scenario_002", "variable": "ssi", "reason": "x"},
                ],
            },
            {
                "kind": "engine_upgrade",
                "date": "2026-10-10",
                "excluded_outputs_rechecked": [
                    {
                        "scenario_id": "scenario_001",
                        "variable": "snap",
                        "reason": f"again {drafting.INDETERMINATE}",
                    }
                ],
            },
        ]
    }
    assert drafting.indeterminate_rechecks(meta) == {
        ("scenario_001", "snap"): "2026-09-29"
    }
    sidecar = json.loads((RUN_DIR / "reference_outputs.csv.meta.json").read_text())
    assert drafting.indeterminate_rechecks(sidecar) == {
        ("scenario_080", "snap"): "2026-09-29"
    }


def test_the_previous_upgrade_is_the_bases_last():
    sidecar = json.loads(
        build.git_blob(
            build.BASE_COMMIT, f"{build.RUN}/reference_outputs.csv.meta.json"
        )
    )
    last = drafting.last_upgrade(sidecar)
    assert (last["date"], last["engine_version"]) == (
        "2026-10-13",
        build.PREVIOUS_ENGINE,
    )
    assert drafting.value_key(last["engine_version"]) == "value_on_2_41_0"
    assert set(drafting.last_upgrade_rechecks(sidecar)) == {
        build.key_of(r) for r in last["excluded_outputs_rechecked"]
    }


# --- This audit's own fix modules ------------------------------------------------


R33 = "r33_ca_educator_expense_addback.py"


def test_a_module_in_neither_fixes_folder_is_refused():
    """This audit adds no fix module of its own (no regeneration needs a
    fix_modules target). The 2026-10-12 audit's r33 is in neither the
    2026-09-22 fixes at the base nor this audit's fixes/, so it is refused; a
    2026-09-22 module is found where it is committed."""
    assert not (build.LOCAL_FIXES).exists() or not any(build.LOCAL_FIXES.iterdir())
    with pytest.raises(build.Refusal, match="neither in"):
        build.fix_location(R33)
    rel, _ = build.fix_location("r02_ira_219g_v2.py")
    assert rel == f"{build.AUDIT_FIXES_REL}/r02_ira_219g_v2.py"
    assert not build.is_local_fix("r02_ira_219g_v2.py")
    assert not build.is_local_fix(R33)


def _local_fixes(monkeypatch, tmp_path, local: dict):
    """Stand ``local`` in as this audit's committed fixes/ and its checkout."""
    real = build.fix_location

    def located(name):
        if name in local:
            return f"{build.LOCAL_FIXES_REL}/{name}", local[name]
        return real(name)

    monkeypatch.setattr(build, "fix_location", located)
    copy_dir = tmp_path / "fixes"
    copy_dir.mkdir()
    for name, blob in local.items():
        (copy_dir / name).write_bytes(blob)
    monkeypatch.setattr(build, "LOCAL_FIXES", copy_dir)
    return copy_dir


def test_a_local_modules_pin_names_its_path(monkeypatch, tmp_path):
    _local_fixes(monkeypatch, tmp_path, {"rx_local.py": b"reform = None\n"})
    pins = build.audit_module_pins(["r02_ira_219g_v2.py", "rx_local.py"])
    assert build.module_pin("rx_local.py", pins) == {
        "module": "rx_local.py",
        "sha256": build.sha256_bytes(b"reform = None\n"),
        "path": f"{build.LOCAL_FIXES_REL}/rx_local.py",
    }
    assert set(build.module_pin("r02_ira_219g_v2.py", pins)) == {"module", "sha256"}


def test_a_local_module_edited_after_its_commit_is_refused(monkeypatch, tmp_path):
    copy_dir = _local_fixes(monkeypatch, tmp_path, {"rx_local.py": b"X = 1\n"})
    (copy_dir / "rx_local.py").write_bytes(b"X = 2\n")
    with pytest.raises(build.Refusal, match="as committed at HEAD"):
        build.audit_module_pins(["rx_local.py"])


def test_a_local_module_cannot_pin_a_sibling_from_the_audited_fixes(
    tmp_path, monkeypatch
):
    loads = b'from pathlib import Path\nSIBLING = Path(__file__).with_name("%s")\n'
    _local_fixes(
        monkeypatch,
        tmp_path,
        {
            "rx_shadow.py": loads % b"r02_ira_219g_v2.py",
            "rx_beside.py": loads % b"rx_helper.py",
            "rx_helper.py": b"X = 1\n",
        },
    )
    with pytest.raises(build.Refusal, match="rx_shadow.py loads r02_ira_219g_v2.py"):
        build.audit_module_pins(["rx_shadow.py"])
    pins = build.audit_module_pins(["rx_beside.py"])
    assert set(pins) == {"rx_beside.py", "rx_helper.py"}
    assert build.module_pin("rx_helper.py", pins)["path"] == (
        f"{build.LOCAL_FIXES_REL}/rx_helper.py"
    )


@SETTINGS
@given(
    moved=st.dictionaries(
        st.sampled_from([(s, v) for s, v, _, _ in ROWS]),
        st.floats(min_value=1.5, max_value=5e3) | st.floats(-5e3, -1.5),
    )
)
def test_the_draft_places_every_moved_output_exactly_once(moved):
    """Whatever moves, each output that moves beyond the tolerance gets exactly
    one call, and lands in exactly one list (or review only); nothing else is
    listed."""
    computed = _unchanged()
    for key, delta in moved.items():
        computed[key] = (
            (1.0 - computed[key])
            if key[1].endswith("_eligible")
            else (computed[key] + delta)
        )
    actions, calls = _draft(computed)
    beyond = {k for k, v in computed.items() if build.beyond(k[1], _unchanged()[k], v)}
    assert sorted((c["scenario_id"], c["variable"]) for c in calls) == sorted(beyond)
    listed = [
        build.key_of(e)
        for name in (
            "approved",
            "regenerated_exclusions",
            "new_exclusions",
            "excluded_rechecked",
        )
        for e in actions[name]
    ]
    review_only = [
        (c["scenario_id"], c["variable"])
        for c in calls
        if c["placed_in"] == "review only"
    ]
    assert sorted(listed + review_only) == sorted(beyond)
    assert len(set(listed)) == len(listed)


# --- The committed build ---------------------------------------------------------
#
# The build this audit stages for the next board release. Its inputs are
# committed beside it, so the tests check it against them without an engine.

FINAL = UPGRADE / "final_actions.json"
APPROVED = {
    ("scenario_028", "free_school_meals_eligible"): 1.0,
    ("scenario_031", "snap"): 288.0,
    ("scenario_117", "free_school_meals_eligible"): 1.0,
    ("scenario_123", "free_school_meals_eligible"): 1.0,
}
# The four outputs whose records cite r24 (who paid for the disability
# coverage); 2.60.0 lands each on its record's alternative value.
R24 = {
    ("scenario_002", F),
    ("scenario_107", F),
    ("scenario_121", F),
    ("scenario_121", S),
}
# narratives_upgrade.py with hand_corrected_narratives.json on this build and
# release 20261014's explanations (no writer call).
EXPLANATIONS_SHA256 = "a1691832890b9f6b9140ff1df199421cb7d8179b971cbb8cee19bc0333b682a4"
EXPLANATIONS_PATH = (
    "annotations/us_full_run_20260612_policyengine_4_16_1_populace/"
    "us_case_reference_explanations.csv"
)


def _computed(path: Path) -> dict:
    import csv

    with path.open(newline="") as source:
        return {
            (r["scenario_id"], r["variable"]): float(r["recomputed"])
            for r in csv.DictReader(source)
        }


@pytest.fixture(scope="module")
def committed():
    meta = json.loads((BUILD / "reference_outputs.csv.meta.json").read_text())
    return types.SimpleNamespace(
        csv_text=(BUILD / "reference_outputs.csv").read_text(),
        meta=meta,
        revision=meta["revisions"][-1],
        exclusions=json.loads((BUILD / "reference_exclusions.json").read_text()),
        traces=json.loads((BUILD / "reference_traces.json").read_text()),
        actions=json.loads(FINAL.read_text()),
        computed=_computed(BUILD / "computed.csv"),
    )


def test_the_committed_build_reproduces_from_its_inputs(real_base, committed, tmp_path):
    """Differential: the base, the committed computed.csv and final_actions.json,
    planned and written with the committed revision's provenance, bundle, fix
    modules, traces and time, give the committed files byte for byte."""
    build.validate_actions(committed.actions)
    plan = build.plan_upgrade(real_base, committed.actions, committed.computed)
    assert plan.problems == []
    build.write_outputs(
        tmp_path,
        real_base,
        plan,
        committed.actions,
        bundle=committed.meta["policyengine_bundles"]["us"],
        fix_modules=committed.revision["fix_modules"],
        provenance=committed.revision["provenance"],
        traces=committed.traces,
        now=committed.meta["regenerated_at_utc"],
    )
    for name in (
        "reference_outputs.csv",
        "reference_outputs.csv.meta.json",
        "reference_exclusions.json",
        "reference_traces.json",
    ):
        assert (tmp_path / name).read_bytes() == (BUILD / name).read_bytes(), name


def test_the_committed_revision_names_this_audits_inputs(real_base, committed):
    revision = committed.revision
    assert revision["kind"] == "engine_upgrade"
    assert revision["engine_version"] == "policyengine-us 2.60.0"
    assert revision["previous_engine_version"] == build.PREVIOUS_ENGINE
    assert revision["date"] == committed.actions["date"] == "2026-10-23"
    assert committed.meta["regenerated_at_utc"][:10] == revision["date"]
    assert committed.meta["revisions"][:-1] == real_base.meta["revisions"]
    provenance = revision["provenance"]
    assert provenance["builder_sha256"] == build.sha256(
        UPGRADE / "scripts" / "build_references_upgrade.py"
    )
    assert provenance["actions_sha256"] == build.sha256(FINAL)
    assert provenance["harness_sha256"] == build.sha256(build.HARNESS)
    assert provenance["base_commit"] == build.BASE_COMMIT
    assert committed.meta["reference_csv_sha256"] == build.sha256(
        BUILD / "reference_outputs.csv"
    )
    assert committed.meta["policyengine_bundles"]["us"]["model_version"] == "2.60.0"
    assert {build.key_of(c): c["regenerated"] for c in revision["changed"]} == APPROVED
    assert {build.key_of(c): c["cause"] for c in revision["changed"]} == {
        k: (
            "ca_snap_mce_no_net_income_test_10036"
            if k[1] == "snap"
            else "state_universal_free_breakfast_10238"
        )
        for k in APPROVED
    }
    assert revision["regenerated_exclusions"] == []
    assert revision["new_exclusions"] == []
    assert len(revision["excluded_outputs_rechecked"]) == 16
    assert set(committed.traces) == {f"{k[0]}|{k[1]}" for k in APPROVED}


def test_the_committed_csv_moves_only_the_approved_outputs(real_base, committed):
    import pandas as pd

    from policybench.reference_exclusions import (
        load_reference_exclusions,
        verify_exclusions_against_reference,
    )

    assert committed.csv_text == build.render_reference_csv(
        real_base.reference, APPROVED
    )
    verify_exclusions_against_reference(
        pd.read_csv(BUILD / "reference_outputs.csv"),
        load_reference_exclusions(BUILD / "reference_exclusions.json"),
    )
    base_doc = real_base.exclusions
    assert {k: v for k, v in committed.exclusions.items() if k != "derivation"} == {
        k: v for k, v in base_doc.items() if k != "derivation"
    }
    added = committed.exclusions["derivation"].removeprefix(base_doc["derivation"])
    assert added == (
        " On 2026-10-23 the references moved from policyengine-us 2.41.0 to"
        " policyengine-us 2.60.0 with the same pre-freeze conventions"
        " (reference_audit/2026-10-22-engine-upgrade), and every output was"
        " recomputed there. Of the excluded outputs that stay excluded, 16 moved;"
        " each was re-reviewed and keeps the value it was decided on"
        " (excluded_outputs_rechecked)."
    )


def test_the_committed_computed_values_are_every_scored_reference(committed):
    references = build.parse_reference_csv(committed.csv_text).values()
    excluded = {build.key_of(r) for r in committed.exclusions["exclusions"]}
    assert set(committed.computed) == set(references)
    for key, value in references.items():
        if key not in excluded:
            assert abs(committed.computed[key] - value) <= build.EPS, key
    for item in committed.revision["excluded_outputs_rechecked"]:
        key = build.key_of(item)
        assert key in excluded
        assert item["kept_value"] == references[key]
        assert item["value_on_2_60_0"] == committed.computed[key]
        assert build.beyond(key[1], references[key], committed.computed[key])


def test_the_r24_outputs_land_on_their_alternatives_and_stay_excluded(committed):
    """2.60.0 counts employment disability benefits in gross income unless an
    input it defaults to zero says the recipient paid for the coverage
    (#10185), so the four r24 outputs land on their records' alternative
    values. The records are unlisted-input exclusions (r24 is classed
    unlisted_input) and the prompt still does not state who paid, so they stay
    excluded at their decided $0."""
    root_causes = json.loads(
        (ROOT / "reference_audit" / "2026-09-22" / "root_causes.json").read_text()
    )
    root_causes = root_causes.get("root_causes", root_causes)
    assert (
        root_causes["r24_disability_benefits_taxability"]["class"] == "unlisted_input"
    )
    records = {build.key_of(r): r for r in committed.exclusions["exclusions"]}
    references = build.parse_reference_csv(committed.csv_text).values()
    rechecked = {build.key_of(r): r for r in committed.actions["excluded_rechecked"]}
    for key in R24:
        record = records[key]
        assert record["reason_code"] == "reference_depends_on_unlisted_input"
        assert "r24_disability_benefits_taxable" in record["note"]
        assert references[key] == record["frozen_value"] == 0.0
        assert abs(committed.computed[key] - record["alternative_value"]) <= 1e-3
        assert "an engine default does not settle it" in rechecked[key]["reason"]
        assert "policyengine-us#10185" in rechecked[key]["reason"]


def test_the_final_actions_are_the_reviewed_draft(real_base, committed):
    """Drafted again from the committed computed.csv, the outputs land in the
    same lists with the same values and causes; the review only adds figures
    and upstream pull requests to a basis or a reason."""
    records = {build.key_of(r): r for r in real_base.exclusions["exclusions"]}
    cells = drafting.cells_from_computed(
        BUILD / "computed.csv", real_base.reference.values(), records
    )
    drafted, calls = drafting.draft_actions(
        cells,
        records,
        drafting.last_upgrade_rechecks(real_base.meta),
        drafting.last_upgrade(real_base.meta),
        engine_version="2.60.0",
        date="2026-10-23",
        precise=True,
        indeterminate=drafting.indeterminate_rechecks(real_base.meta),
    )
    final = committed.actions
    assert drafted["draft"] is True and final["draft"] is False
    for name in (
        "approved",
        "regenerated_exclusions",
        "new_exclusions",
        "excluded_rechecked",
    ):
        assert [build.key_of(e) for e in final[name]] == [
            build.key_of(e) for e in drafted[name]
        ], name
    for d, f in zip(drafted["approved"], final["approved"], strict=True):
        assert (d["value"], d["cause"]) == (f["value"], f["cause"])
    for d, f in zip(
        drafted["excluded_rechecked"], final["excluded_rechecked"], strict=True
    ):
        assert f["reason"].startswith(d["reason"])
    assert final["review"] == drafted["review"]
    assert {c["decision"] for c in calls} == {"PROPOSED"}


def test_the_hand_corrected_narratives_rebuild_the_explanations(committed):
    """The four narratives replace the writer for every changed output (no
    writer call), and on release 20261014's explanations they give the CSV
    the next board release installs. Each states the trace's figures."""
    import hashlib

    import pandas as pd

    hand = json.loads((UPGRADE / "hand_corrected_narratives.json").read_text())
    assert set(hand) == {f"{k[0]}|{k[1]}" for k in APPROVED}

    def refuse(**_):
        raise AssertionError("the narrative writer must not run")

    base_text = build.git_blob(build.BASE_COMMIT, EXPLANATIONS_PATH).decode()
    text, results = narratives.write_narratives(
        BUILD,
        base_text,
        pd.DataFrame(columns=["scenario_id"]),
        completion=refuse,
        hand_corrected=hand,
    )
    assert hashlib.sha256(text.encode()).hexdigest() == EXPLANATIONS_SHA256
    assert {(r[0], r[1]) for r in results} == set(APPROVED)
    figures = {
        "scenario_031|snap": (
            ["$288", "$24", "$1,987.79", "$2,608.33", "$1,611", "$298", "$484"],
            [
                "snap = 288",
                "snap_min_allotment = 24",
                "snap_net_income = 1611",
                "tanf_non_cash_gross_income_limit = 2608.33",
                "snap_expected_contribution = 484",
                "snap_max_allotment = 298",
            ],
        ),
        "scenario_028|free_school_meals_eligible": (
            ["$1,112.40", "$61,277", "1.86", "$33,000", "$2.90", "$0.84"],
            [
                "free_school_meals = 1112.4",
                "school_meal_countable_income = 61277",
                "school_meal_fpg_ratio = 1.86",
                "spm_unit_fpg = 33000",
                "school_meal_daily_subsidy = 2.9",
                "school_meal_paid_daily_subsidy = 0.84",
            ],
        ),
        "scenario_117|free_school_meals_eligible": (
            ["$741.60", "$248,675", "6.43", "$38,680"],
            [
                "free_school_meals = 741.6",
                "school_meal_countable_income = 248675",
                "school_meal_fpg_ratio = 6.43",
                "spm_unit_fpg = 38680",
            ],
        ),
        "scenario_123|free_school_meals_eligible": (
            ["$370.80", "$145,002", "5.31", "$27,320"],
            [
                "free_school_meals = 370.8",
                "school_meal_countable_income = 145002",
                "school_meal_fpg_ratio = 5.31",
                "spm_unit_fpg = 27320",
            ],
        ),
    }
    for key, (stated, traced) in figures.items():
        for figure in stated:
            assert figure in hand[key], (key, figure)
        for line in traced:
            assert line in committed.traces[key]["trace"], (key, line)
    # Free breakfast is $2.06 a school day over 180 days, per K-12 child.
    assert round((2.90 - 0.84) * 180, 2) == 370.80
    assert round(3 * 370.80, 2) == 1112.40 and round(2 * 370.80, 2) == 741.60


def test_the_timing_record_dates_the_sweep_on_the_newest_release(committed):
    timing = json.loads((UPGRADE / "verification" / "sweep_timing.json").read_text())
    sweep = timing["reference_sweep"]
    engine = committed.revision["engine_version"].removeprefix("policyengine-us ")
    assert sweep["engine"] == engine == "2.60.0"
    assert sweep["first_output_sha256"] == build.sha256(BUILD / "computed.csv")
    uploads = timing["pypi"]["wheel_uploaded_at_utc"]
    assert (
        uploads[engine][:19]
        <= sweep["engine_installed_at_utc"][:19]
        <= sweep["first_output_at_utc"][:19]
    )

    def key(version):
        return tuple(int(p) for p in version.split("."))

    assert [
        v
        for v, at in uploads.items()
        if key(v) > key(engine) and at[:19] < sweep["first_output_at_utc"][:19]
    ] == []
    check = timing["publication_check"]
    for name in (
        "computed.csv",
        "reference_outputs.csv",
        "reference_outputs.csv.meta.json",
        "reference_exclusions.json",
    ):
        assert check["build_sha256"][name] == build.sha256(BUILD / name), name
    assert (
        check["build_sha256"]["builder"]
        == committed.revision["provenance"]["builder_sha256"]
    )
    assert check["scored_outputs"] == 1984 - len(committed.exclusions["exclusions"])
    assert check.get("scored_differ", []) == []


def test_the_superseded_sweep_differs_only_on_the_approved_school_meals():
    """The first sweep, on 2.59.0, was cut off before its build; 2.60.0 differs
    from it on exactly the three school-meal flags #10238 moves."""
    doc = json.loads((UPGRADE / "verification" / "superseded_2_59_0.json").read_text())
    assert doc["sweep_timing_2_59_0"]["reference_sweep"]["engine"] == "2.59.0"
    assert doc["first_pass_2_60_0_sha256"] == build.sha256(BUILD / "computed.csv")
    assert {
        (d["scenario_id"], d["variable"]) for d in doc["differ_2_59_0_vs_2_60_0"]
    } == {k for k in APPROVED if k[1] == "free_school_meals_eligible"}
    assert all(d["scored"] for d in doc["differ_2_59_0_vs_2_60_0"])
