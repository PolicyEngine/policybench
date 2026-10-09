"""The second engine upgrade's reference builder, its narratives and its draft
actions (reference_audit/2026-10-09-engine-upgrade).

The engine is stubbed: each test hands the builder's pure planning step a dict
of computed values. Properties (Hypothesis) state the builder's invariants:

- every refusal fires: an unexplained move, scored or excluded; an approved
  output that does not move; a regenerated output off its audited target; a new
  exclusion on an output that does not move; a rechecked output that does not
  move; a ruled output neither kept nor regenerated;
- a removed record's output is scored at its new engine value;
- every output the upgrade does not change keeps its bytes in the reference
  CSV, and every earlier sidecar revision keeps its bytes;
- the records' order does not depend on the order of the actions' lists;
- the paper's partition of the revision's changes agrees with the builder.
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
UPGRADE = ROOT / "reference_audit" / "2026-10-09-engine-upgrade"
SETTINGS = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


def _module(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


build = _module(
    "build_references_upgrade", UPGRADE / "scripts" / "build_references_upgrade.py"
)
narratives = _module(
    "narratives_upgrade", UPGRADE / "scripts" / "narratives_upgrade.py"
)
drafting = _module("actions_from_cells", UPGRADE / "actions_from_cells.py")

ENGINE = "policyengine-us 9.9.9"
DATE = "2026-10-09"
NOW = "2026-10-09T12:00:00+00:00"
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
    ("scenario_023", FLAG, 1.0, ""),
]
BASE_RECORDS = [
    _defect("scenario_002", F, 250.5, 300.0),  # fixed below: regenerated
    _defect("scenario_003", "snap", 3000.0, 2500.0),  # unfixed
    _unlisted("scenario_006", "snap", 120.0, 0.0),
]
TAIL = _unlisted("scenario_023", FLAG, 1.0, 0.0, decided_on="2026-09-29")
RULED = [
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
FIRST_REVISION = {
    "date": "2026-09-29",
    "kind": "engine_upgrade",
    "engine_version": "policyengine-us 2.15.17",
    "previous_engine_version": "policyengine-us 1.755.4",
    "fix_modules": [],
    "excluded_outputs_rechecked": [],
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
            ],
        },
        exclusions=exclusions,
        scenarios_csv="",
        frozen={(s, v): x - 1.0 for s, v, x, _ in ROWS},
    )


def _release(base: build.Base) -> tuple[dict, set]:
    doc = copy.deepcopy(base.exclusions)
    doc["exclusions"] = (
        doc["exclusions"][:-1]
        + sorted(copy.deepcopy(RULED), key=build.key_of)
        + doc["exclusions"][-1:]
    )
    doc["derivation"] += " Ruled ten."
    return doc, {build.key_of(r) for r in RULED}


def _unchanged() -> dict:
    return {(s, v): x for s, v, x, _ in ROWS}


def _new_exclusion(sid, value) -> dict:
    record = _unlisted(sid, "local_income_tax", value, 0.0, decided_on=DATE)
    record["engine_version"] = ENGINE
    return record


def _actions(**lists) -> dict:
    """Actions on the synthetic base; unless given, the kept list is every
    ruled output the actions do not regenerate."""
    actions = {
        "engine": ENGINE,
        "previous_engine": "policyengine-us 2.15.17",
        "date": DATE,
        "release_spec_sha256": "spec",
        "approved": [],
        "regenerated_exclusions": [],
        "new_exclusions": [],
        "excluded_rechecked": [],
    }
    actions.update(lists)
    if "kept_exclusions_from_release" not in lists:
        regenerated = {build.key_of(r) for r in actions["regenerated_exclusions"]}
        actions["kept_exclusions_from_release"] = [
            {"scenario_id": k[0], "variable": k[1]}
            for k in sorted({build.key_of(r) for r in RULED} - regenerated)
        ]
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
    """A complete upgrade: one approval, two regenerations (one ruled), one new
    exclusion, one recheck, a within-$1 move."""
    computed = _unchanged()
    computed[("scenario_001", S)] = 1010.0  # approved
    computed[("scenario_002", F)] = 300.4  # regenerated (20261006 record)
    computed[("scenario_004", S)] = 690.2  # regenerated (ruled)
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
    release, ruled = _release(base)
    return base, release, build.plan_upgrade(base, release, ruled, actions, computed)


def _write(tmp_path, computed, actions):
    base, release, plan = _plan(computed, actions)
    assert plan.problems == []
    written = build.write_outputs(
        tmp_path,
        base,
        release,
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
    assert revision["previous_engine_version"] == "policyengine-us 2.15.17"
    assert written.meta["revisions"][:-1] == base.meta["revisions"]
    assert [r["kind"] for r in written.meta["revisions"]].count("engine_upgrade") == 2
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
    assert revision["kept_exclusions_from_release"] == [
        {"scenario_id": "scenario_004", "variable": F},
        {"scenario_id": "scenario_005", "variable": S},
    ]
    keys = [build.key_of(r) for r in written.exclusions["exclusions"]]
    assert keys == [
        ("scenario_003", "snap"),
        ("scenario_006", "snap"),
        ("scenario_004", F),
        ("scenario_005", S),
        ("scenario_006", "local_income_tax"),
        ("scenario_023", FLAG),
    ]
    assert written.exclusions["derivation"].startswith(
        "Derived. Ruled ten. On 2026-10-09"
    )
    derivation = written.exclusions["derivation"]
    assert "from policyengine-us 2.15.17 to policyengine-us 9.9.9" in derivation
    assert "behind two excluded outputs" in derivation
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
        "2.15.17",
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


def test_a_kept_ruled_output_that_moves_is_rechecked(tmp_path):
    """A ruled output the release keeps (later law, here) that the new engine
    moves is listed both as kept and as rechecked, and keeps its value (rule
    5). The draft lists it in both places, and the builder accepts it."""
    computed = _unchanged()
    computed[("scenario_005", S)] = 830.0
    base = _base()
    release, ruled = _release(base)
    drafted, _ = drafting.draft_actions(
        _cells(computed),
        release,
        ruled,
        {build.key_of(r) for r in base.exclusions["exclusions"]},
        {},
        engine_version="9.9.9",
        date=DATE,
        spec_sha256="spec",
        precise=True,
    )
    actions = {k: v for k, v in drafted.items() if k not in ("draft", "review")}
    assert ("scenario_005", S) in {
        build.key_of(e) for e in actions["kept_exclusions_from_release"]
    } & {build.key_of(e) for e in actions["excluded_rechecked"]}
    build.validate_actions(actions)
    _, plan, written = _write(tmp_path, computed, actions)
    assert [build.key_of(r) for r in plan.rechecked] == [("scenario_005", S)]
    assert (
        build.parse_reference_csv(written.csv_text).values()[("scenario_005", S)]
        == 820.35
    )
    # Kept may pair with rechecked only.
    for name in ("approved", "regenerated_exclusions", "new_exclusions"):
        with pytest.raises(build.Refusal, match="is in both"):
            build.validate_actions(
                {**actions, name: [{"scenario_id": "scenario_005", "variable": S}]}
            )


def test_the_written_date_must_be_the_actions_date(tmp_path):
    computed, actions = _full()
    base, release, plan = _plan(computed, actions)
    with pytest.raises(build.Refusal, match="does not fall on the actions date"):
        build.write_outputs(
            tmp_path,
            base,
            release,
            plan,
            actions,
            bundle={},
            fix_modules=[],
            provenance={},
            traces={},
            now="2026-10-10T00:00:01+00:00",
        )


# --- Refusals ------------------------------------------------------------------


def _problems(computed, actions) -> list[str]:
    return _plan(computed, actions)[2].problems


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


def _module_plan(value=2600.0, after=2600.1, evidence=None, pins=None, entry=None):
    computed = _unchanged()
    computed[("scenario_003", "snap")] = value
    base = _base()
    release, ruled = _release(base)
    actions = _actions(regenerated_exclusions=[entry or _module_target()])
    return build.plan_upgrade(
        base,
        release,
        ruled,
        actions,
        computed,
        evidence={EVIDENCE["path"]: evidence or _evidence()},
        module_pins={MODULE: "p" * 64} if pins is None else pins,
        module_values={(("scenario_003", "snap"), (MODULE,)): after},
    )


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
    (regenerated,) = _plan(computed, actions)[2].regenerated
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
    record["decided_on"] = "2026-10-08"
    problems = _problems(computed, _actions(new_exclusions=[record]))
    assert len(problems) == 2
    assert "frozen_value 670.0 != engine 670.55" in problems[0]
    assert "decided_on '2026-10-08' != '2026-10-09'" in problems[1]


def test_a_rechecked_output_that_does_not_move_is_refused():
    actions = _actions(
        excluded_rechecked=[
            {"scenario_id": "scenario_006", "variable": "snap", "reason": "r"}
        ]
    )
    (problem,) = _problems(_unchanged(), actions)
    assert problem.startswith("rechecked ('scenario_006', 'snap') does not move")


def test_every_ruled_output_is_kept_or_regenerated():
    actions = _actions(
        kept_exclusions_from_release=[{"scenario_id": "scenario_004", "variable": F}]
    )
    (problem,) = _problems(_unchanged(), actions)
    assert f"missing [('scenario_004', '{S}'), ('scenario_005', '{S}')]" in problem


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
        "previous_engine is policyengine-us 2.2.1, not policyengine-us 2.15.17"
    ]


# --- Properties --------------------------------------------------------------


@SETTINGS
@given(
    federal=st.floats(min_value=299.0, max_value=301.0),
    ruled=st.floats(min_value=689.0, max_value=691.0),
)
def test_a_removed_record_is_scored_at_its_new_value(tmp_path, federal, ruled):
    computed = _unchanged()
    computed[("scenario_002", F)] = federal
    computed[("scenario_004", S)] = ruled
    actions = _actions(
        regenerated_exclusions=[
            _regenerate("scenario_002", F, 300.0),
            _regenerate("scenario_004", S, 690.0),
        ]
    )
    _, plan, written = _write(tmp_path, computed, actions)
    values = build.parse_reference_csv(written.csv_text).values()
    excluded = {build.key_of(r) for r in written.exclusions["exclusions"]}
    for key, value in ((("scenario_002", F), federal), (("scenario_004", S), ruled)):
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
        if key[1] == FLAG:
            continue
        computed[key] += delta
    base, plan, written = _write(tmp_path, computed, _actions())
    excluded = {build.key_of(r) for r in _release(base)[0]["exclusions"]}
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
        "kept_exclusions_from_release",
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


def test_the_base_is_release_20261006(real_base):
    assert len(real_base.reference.rows) == 1984
    assert len(real_base.exclusions["exclusions"]) == 64
    kinds = [r["kind"] for r in real_base.meta["revisions"]]
    assert kinds.count("engine_upgrade") == 1 and kinds[-1] == "engine_upgrade"
    assert real_base.meta["revisions"][-1]["engine_version"] == build.PREVIOUS_ENGINE
    assert build.key_of(real_base.exclusions["exclusions"][-1]) == build.AUDIT_TAIL
    # The base CSV round-trips byte for byte through the row parser.
    raw = build.git_blob(build.BASE_COMMIT, f"{build.RUN}/reference_outputs.csv")
    assert build.render_reference_csv(real_base.reference, {}) == raw.decode()


def test_the_release_record_is_the_drivers(real_base):
    """Differential: the record the builder edits is finish_haiku55's."""
    release, ruled, spec_sha = build.release_record(real_base.exclusions)
    driver = sys.modules["finish_haiku55_for_upgrade"]
    expected = driver.build_release_exclusions(
        driver.base_exclusion_record(), driver.load_spec()
    )
    assert release == expected
    assert len(release["exclusions"]) == 74 and len(ruled) == 10
    assert spec_sha == build.sha256(ROOT / "docs" / "haiku55" / "spec.json")
    assert build.key_of(release["exclusions"][-1]) == build.AUDIT_TAIL


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
    """A stub engine that returns 20261006's values: the plan accepts the real
    release record with every ruled output kept, and changes nothing."""
    release, ruled, _ = build.release_record(real_base.exclusions)
    computed = real_base.reference.values()
    actions = _actions(
        kept_exclusions_from_release=[
            {"scenario_id": k[0], "variable": k[1]} for k in sorted(ruled)
        ]
    )
    plan = build.plan_upgrade(real_base, release, ruled, actions, computed)
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
            for i in range(1, 7)
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


def _value_narrator(mention: str = ""):
    def completion(**kwargs):
        value = float(
            kwargs["messages"][0]["content"].split("REFERENCE VALUE: ")[1].split("\n")[0]
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
    # A narrative that names the earlier engine is not reused.
    named, _ = narratives.write_narratives(
        tmp_path / "a",
        EXPLANATIONS,
        _scenarios(),
        completion=_value_narrator(" On policyengine-us 9.9.9."),
    )
    assert narratives.reusable_narratives(tmp_path / "b", tmp_path / "a", named) == {}


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


def test_the_narrative_run_never_uses_an_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import os

    with pytest.raises(build.Refusal, match="ANTHROPIC_API_KEY"):
        narratives.main(["--references", "x", "--explanations", "y", "--out", "z"])
    assert "OPENAI_API_KEY" not in os.environ


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


def test_the_draft_places_every_moved_output_and_prints_each_call(tmp_path):
    computed, _ = _full()
    computed[("scenario_001", "local_income_tax")] = 670.55  # IN county
    computed[("scenario_006", "local_income_tax")] = 0.0
    states = {
        ("scenario_001", "local_income_tax"): "IN",
        ("scenario_001", S): "ZZ",
    }
    base = _base()
    release, ruled = _release(base)
    actions, calls = drafting.draft_actions(
        _cells(computed, states),
        release,
        ruled,
        {build.key_of(r) for r in base.exclusions["exclusions"]},
        {},
        engine_version="9.9.9",
        date=DATE,
        spec_sha256="spec",
        precise=True,
    )
    assert actions["draft"] is True
    placed = {
        (c["scenario_id"], c["variable"]): (c["decision"], c["placed_in"])
        for c in calls
    }
    assert placed == {
        ("scenario_001", S): ("UNDECIDED", "review only"),
        ("scenario_001", "local_income_tax"): ("PROPOSED", "new_exclusions"),
        ("scenario_002", F): ("PROPOSED", "regenerated_exclusions"),
        ("scenario_004", S): ("PROPOSED", "regenerated_exclusions"),
        ("scenario_003", "snap"): ("PROPOSED", "excluded_rechecked"),
    }
    assert actions["kept_exclusions_from_release"] == [
        {"scenario_id": "scenario_004", "variable": F},
        {"scenario_id": "scenario_005", "variable": S},
    ]
    # The records name no upstream fix, so the builder refuses the regenerations
    # until a reviewer names them; cleared, the draft builds except for the
    # undecided move.
    cleared = {k: v for k, v in actions.items() if k not in ("draft", "review")}
    build.validate_actions(cleared)
    problems = build.plan_upgrade(base, release, ruled, cleared, computed).problems
    assert problems == [
        f"unreviewed move ('scenario_001', '{S}'): 1000.0 -> 1010.0",
        f"regenerated ('scenario_002', '{F}') names no upstream fix ('to be filed')",
        f"regenerated ('scenario_004', '{S}') names no upstream fix ('to be filed')",
    ]
    for entry in cleared["regenerated_exclusions"]:
        entry["upstream"] = "PolicyEngine/policyengine-us#1"
    problems = build.plan_upgrade(base, release, ruled, cleared, computed).problems
    assert problems == [f"unreviewed move ('scenario_001', '{S}'): 1000.0 -> 1010.0"]


def test_the_draft_keeps_an_on_target_record_that_names_a_second_reason():
    """A defect record whose note also names an unlisted input stays excluded
    (drafted as a recheck), even when the engine lands on its corrected value."""
    computed = _unchanged()
    computed[("scenario_002", F)] = 300.0
    base = _base()
    release, ruled = _release(base)
    for record in release["exclusions"]:
        if build.key_of(record) == ("scenario_002", F):
            record["note"] = "The output also moves under r23 (unlisted input)."
    actions, calls = drafting.draft_actions(
        _cells(computed),
        release,
        ruled,
        {build.key_of(r) for r in base.exclusions["exclusions"]},
        {},
        engine_version="9.9.9",
        date=DATE,
        spec_sha256="spec",
        precise=True,
    )
    assert actions["regenerated_exclusions"] == []
    (entry,) = actions["excluded_rechecked"]
    assert "names a second reason" in entry["reason"]
    assert calls[0]["placed_in"] == "excluded_rechecked"


def test_the_draft_aims_a_drifted_record_at_its_fix_modules_evidence():
    """scenario_003 snap misses its record's 1.755.4 corrected value; with
    evidence it is drafted against the modules' pre-fix corrected value, and
    the builder accepts the draft once the modules leave it unchanged."""
    computed = _unchanged()
    computed[("scenario_003", "snap")] = 2600.0
    base = _base()
    release, ruled = _release(base)
    kwargs = dict(
        engine_version="9.9.9", date=DATE, spec_sha256="spec", precise=True
    )
    args = (
        _cells(computed),
        release,
        ruled,
        {build.key_of(r) for r in base.exclusions["exclusions"]},
        {},
    )
    without, _ = drafting.draft_actions(*args, **kwargs)
    assert without["regenerated_exclusions"] == []
    assert "$100.00 from the record's" in without["excluded_rechecked"][0]["reason"]
    doc = _evidence()
    actions, calls = drafting.draft_actions(
        *args, **kwargs, evidence={"ref": dict(EVIDENCE), "doc": doc}
    )
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
        base,
        release,
        ruled,
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
    county = drafting.Cell(
        "scenario_015", "IN", "local_income_tax", 0.0, 670.55, "scored", ""
    )
    fund = drafting.Cell("scenario_076", "ID", S, 6818.34, 6828.34, "scored", "")
    other = drafting.Cell("scenario_076", "ID", S, 6818.34, 6838.34, "scored", "")
    proposals = [
        [
            propose(c, ENGINE, DATE)["rule"]
            for matches, propose in drafting.RULES
            if matches(c)
        ]
        for c in (county, fund, other)
    ]
    assert proposals == [
        ["indiana_county_unlisted"],
        ["idaho_permanent_building_fund"],
        [],
    ]
    record = drafting._indiana_county(county, ENGINE, DATE)["entry"]
    from policybench.reference_exclusions import REQUIRED_FIELDS_BY_REASON

    assert all(
        record[f] not in (None, "")
        for f in REQUIRED_FIELDS_BY_REASON[record["reason_code"]]
    )


def test_the_cells_table_must_be_against_20261006(tmp_path):
    board = {("scenario_001", S): 1000.0}
    path = tmp_path / "cells_pe2.37.1.csv"
    path.write_text(
        "scenario_id,state,variable,frozen_20261006,new,delta,moved,status,audited_target\n"
        f"scenario_001,IN,{S},999.0,1000.0,1.0,False,scored,\n"
    )
    with pytest.raises(build.Refusal, match="not 20261006's"):
        drafting.read_cells(path, board, None)
    assert drafting.engine_from_path(path) == "2.37.1"
    path.write_text(path.read_text().replace("999.0", "1000.0"))
    (cell,) = drafting.read_cells(path, board, None)
    assert cell.new == 1000.0 and cell.state == "IN"
    with pytest.raises(build.Refusal, match="not the table's"):
        drafting.read_cells(path, board, {("scenario_001", S): 1000.5})
