"""Draft an actions file for build_references_upgrade.py from a first compute pass.

Adapted from reference_audit/2026-10-12-engine-upgrade/actions_from_cells.py.
Input: the builder's first-pass computed.csv on the new release (every output
against the 20261014 references: fix, scenario_id, state, variable, frozen,
recomputed, delta, moved), or a cells table in the US hub's cells_pe<ver>.csv
form, and the exclusion records (20261014's, read from git). No release spec
rules exclusions here: the build is staged for the next board release.

Output: a DRAFT actions file ("draft": true, which the builder refuses until a
reviewer clears it) and, on stdout, every judgment call it drafted. Nothing is
decided silently: each moved output is classified by

  status          scored, or excluded in 20261014;
  audited target  whether the new value lands within $1 of its record's
                  corrected value (alternative_value) or, with --evidence, of
                  the corrected value the record's fix modules give on a
                  pre-fix engine (a "fix_modules" target, which the builder
                  also checks the modules leave unchanged on the new engine);
                  and the hub's own column;
  reason          engine defect or unlisted input;

and lands in exactly one place:

  regenerated_exclusions  an engine-defect record the new engine lands on
                  (PROPOSED: confirm the upstream fix and its release);
  excluded_rechecked  any other excluded output that moves, with a drafted
                  reason (PROPOSED: check the reason). An unlisted-input record
                  stays excluded even when the new engine lands on its
                  alternative value: the engine then assumes that reading by
                  default, and the prompt still does not state the input;
  approved / new_exclusions  a scored move a RULES entry recognizes, with drafted
                  cause and basis or a drafted record (PROPOSED: check every
                  sentence against the build's trace);
  review only     a scored move no rule recognizes (UNDECIDED: the builder
                  refuses it as an unreviewed move until a reviewer adds it).

  PYTHONPATH=<checkout> python actions_from_cells.py \\
    --computed <pass1>/computed.csv --engine X.Y.Z [--date YYYY-MM-DD] \\
    [--evidence reference_audit/2026-10-22-engine-upgrade/evidence/pe<ver>.json] \\
    [--upstreams reference_audit/2026-10-22-engine-upgrade/upstreams.json] \\
    --out actions.draft.json
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "scripts"))

from build_references_upgrade import (  # noqa: E402
    ENGINE_DEFECT,
    PREVIOUS_ENGINE,
    ROOT,
    TARGET_FIX_MODULES,
    UNNAMED_UPSTREAM,
    Refusal,
    beyond,
    key_of,
    load_base,
    load_evidence,
    sha256,
)

UNLISTED = "reference_depends_on_unlisted_input"
CELL_TOL = 0.006  # the hub's table rounds to cents
TARGET_TOL = 1.0


@dataclass(frozen=True)
class Cell:
    scenario_id: str
    state: str
    variable: str
    previous: float
    new: float
    status: str
    audited_target: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.scenario_id, self.variable)


def money(value: float) -> str:
    return f"${value:,.2f}"


# --- Rules for scored moves -------------------------------------------------
# Each rule recognizes one documented kind of scored move and drafts its action.
# The text states what the upstream pull request documents and what the
# 2.60.0 first pass's traces show; a reviewer checks it against the build's
# trace (reference_traces.json).

CA_MCE_PR = "PolicyEngine/policyengine-us#10036"
BREAKFAST_PR = "PolicyEngine/policyengine-us#10238"
# The FY2026 SNAP minimum allotment for the 48 states and DC (7 U.S.C.
# 2017(a)), as policyengine-us carries it for every month of 2026 under the
# pre-freeze conventions.
SNAP_MIN_ALLOTMENT_2026 = 24.0
# States whose free breakfast regardless of household income #10238 models,
# by standing statute in force for all of 2026, enacted before the
# 2026-07-03 reference freeze: what the statute provides, and the condition
# #10238 notes it does not model (it also assumes a student at a covered
# school).
UNIVERSAL_BREAKFAST = {
    "PA": (
        "Pennsylvania Act 33 of 2023 (24 P.S. § 13-1337.1(c.2), codified December "
        "13, 2023) provides a free breakfast to students at participating schools "
        "regardless of household income, reimbursed to the extent funds are "
        "available",
        "the funding condition",
    ),
    "AR": (
        "Arkansas Act 123 of 2025 (SB 59; A.C.A. § 6-18-722(f)) gives each public "
        "school student who does not otherwise receive a free breakfast one "
        "breakfast a day at no cost, upon request, from the 2025-26 school year",
        "the request condition",
    ),
}


def _ca_mce_minimum_allotment(cell: Cell, engine: str, date: str) -> dict:
    return {
        "action": "approved",
        "rule": "ca_snap_mce_no_net_income_test",
        "entry": {
            "scenario_id": cell.scenario_id,
            "variable": cell.variable,
            "value": cell.new,
            "cause": "ca_snap_mce_no_net_income_test_10036",
            "basis": (
                "California's Modified Categorical Eligibility (MCE) makes a "
                "household with gross income within 200% of the poverty guideline "
                "categorically eligible for CalFresh without the net income test, "
                "elderly or disabled households included (CDSS ACL 12-62, 13-32, "
                "14-56 and 15-42; 7 CFR 273.2(j)(2)), and gives an eligible one- "
                "or two-person household the minimum allotment (CDSS MCE letter, "
                "June 30, 2014; 7 U.S.C. 2017(a); 7 CFR 273.10(e)(2)(ii)(C)). "
                f"{PREVIOUS_ENGINE} applied the net income test to MCE households "
                "with an elderly or disabled member, so a one-person household "
                "whose net income exceeds 100% of the guideline was ineligible "
                f"and its SNAP was $0. {CA_MCE_PR} (Remove the BBCE net income "
                "test from California's Modified Categorical Eligibility) drops "
                f"that test; on {engine} the household is categorically eligible "
                "and its calculated allotment, the maximum less 30% of net income, "
                f"is below the ${SNAP_MIN_ALLOTMENT_2026:,.0f} minimum, so it "
                f"receives ${SNAP_MIN_ALLOTMENT_2026:,.0f} a month "
                f"(snap_min_allotment): {money(cell.new)} for 2026."
            ),
        },
        "call": (
            "APPROVE (CalFresh MCE net income test removed, #10036; minimum "
            "allotment) - confirm the gross and net income, the 200% gross limit "
            "and the minimum in the build trace"
        ),
    }


def _state_universal_breakfast(cell: Cell, engine: str, date: str) -> dict:
    law, unmodeled = UNIVERSAL_BREAKFAST[cell.state]
    return {
        "action": "approved",
        "rule": "state_universal_free_breakfast",
        "entry": {
            "scenario_id": cell.scenario_id,
            "variable": cell.variable,
            "value": cell.new,
            "cause": "state_universal_free_breakfast_10238",
            "basis": (
                f"{law}. {BREAKFAST_PR} (Model state school meal coverage beyond "
                "universal meals) models it for a student enrolled at a covered "
                f"school, without {unmodeled}: on "
                f"{engine} state_has_universal_free_school_breakfast is true for "
                f"{cell.state}, so the household's K-12 children take the free "
                "breakfast tier (school_meal_breakfast_tier) whatever their "
                "income while lunch stays in the paid tier "
                "(school_meal_lunch_tier), and free_school_meals is positive. "
                "The output asks whether PolicyEngine returns positive annual "
                f"free school meal support, so it is 1; on {PREVIOUS_ENGINE} the "
                "household's income put both meals in the paid tier and it was 0."
            ),
        },
        "call": (
            f"APPROVE ({cell.state} universal free breakfast, #10238) - confirm "
            "the breakfast tier, the paid lunch tier and the enactment date"
        ),
    }


RULES = (
    (
        lambda c: (
            c.state == "CA"
            and c.variable == "snap"
            and c.previous == 0
            and abs(c.new - 12 * SNAP_MIN_ALLOTMENT_2026) <= CELL_TOL
        ),
        _ca_mce_minimum_allotment,
    ),
    (
        lambda c: (
            c.state in UNIVERSAL_BREAKFAST
            and c.variable == "free_school_meals_eligible"
            and c.previous == 0
            and c.new == 1
        ),
        _state_universal_breakfast,
    ),
)


# --- Inputs --------------------------------------------------------------------


def read_cells(path: Path, board: dict, computed: dict | None) -> list[Cell]:
    with Path(path).open(newline="") as source:
        rows = list(csv.DictReader(source))
    keys = {(r["scenario_id"], r["variable"]) for r in rows}
    if keys != set(board) or len(rows) != len(board):
        raise Refusal("the cells table does not list exactly the 20261014 outputs")
    cells = []
    for r in rows:
        k = (r["scenario_id"], r["variable"])
        if abs(float(r["frozen_20261014"]) - board[k]) > CELL_TOL:
            raise Refusal(f"{k}: the table's frozen value is not 20261014's")
        new = float(r["new"])
        if computed is not None:
            if abs(computed[k] - new) > CELL_TOL:
                raise Refusal(f"{k}: computed {computed[k]} is not the table's {new}")
            new = computed[k]
        cells.append(
            Cell(
                k[0],
                r["state"],
                k[1],
                board[k],
                new,
                r["status"],
                r.get("audited_target", ""),
            )
        )
    return cells


def cells_from_computed(path: Path, board: dict, records: dict) -> list[Cell]:
    """Every output of a builder pass's computed.csv as a cell: its 20261014
    reference (which must be the row's frozen column), its new value and its
    status. No hub column: the audited target is left to the evidence."""
    with Path(path).open(newline="") as source:
        rows = list(csv.DictReader(source))
    keys = [(r["scenario_id"], r["variable"]) for r in rows]
    if set(keys) != set(board) or len(keys) != len(board):
        raise Refusal("computed.csv does not list exactly the 20261014 outputs")
    cells = []
    for r, k in zip(rows, keys):
        if abs(float(r["frozen"]) - board[k]) > 1e-6:
            raise Refusal(f"{k}: computed.csv's frozen value is not 20261014's")
        status = (
            "excluded 20261014: "
            + str(records[k].get("root_cause") or records[k]["reason_code"])
            if k in records
            else "scored"
        )
        cells.append(Cell(k[0], r["state"], k[1], board[k], float(r["recomputed"]), status, ""))
    return cells


def read_computed(path: Path) -> dict:
    with Path(path).open(newline="") as source:
        return {
            (r["scenario_id"], r["variable"]): float(r["recomputed"])
            for r in csv.DictReader(source)
        }


def engine_from_path(path: Path) -> str:
    match = re.fullmatch(r"cells_pe(\d+\.\d+\.\d+)\.csv", Path(path).name)
    if not match:
        raise Refusal(f"cannot read the engine from {Path(path).name}; pass --engine")
    return match.group(1)


# --- Drafting ------------------------------------------------------------------


def last_upgrade(meta: dict) -> dict:
    """The base's last engine upgrade revision (2026-10-13, on 2.41.0)."""
    return [r for r in meta["revisions"] if r["kind"] == "engine_upgrade"][-1]


def last_upgrade_rechecks(meta: dict) -> dict:
    """The base's last engine upgrade's rechecks, by output."""
    return {key_of(r): r for r in last_upgrade(meta)["excluded_outputs_rechecked"]}


def value_key(engine: str) -> str:
    """A recheck's field for its engine's value ("value_on_2_41_0")."""
    return "value_on_" + engine.removeprefix("policyengine-us ").replace(".", "_")


# What an earlier upgrade's recheck says of an output whose reference the
# stated facts do not decide (scenario_080's SNAP, 2026-09-29).
INDETERMINATE = "indeterminate on the stated facts"


def indeterminate_rechecks(meta: dict) -> dict:
    """The outputs an earlier engine upgrade's recheck found indeterminate on
    the stated facts, each with that upgrade's date (the first such recheck)."""
    found: dict = {}
    for revision in meta["revisions"]:
        if revision["kind"] != "engine_upgrade":
            continue
        for item in revision.get("excluded_outputs_rechecked", []):
            if INDETERMINATE in item.get("reason", ""):
                found.setdefault(key_of(item), revision["date"])
    return found


def second_reason(record: dict) -> str:
    """The record's note when it names an unlisted input besides the defect."""
    note = str(record.get("note", ""))
    return note if "unlisted input" in note.lower() else ""


def record_basis(record: dict) -> str:
    return str(
        record.get("unlisted_input")
        or record.get("root_cause")
        or record["reason_code"]
    )


def upstream_for(record: dict, key, upstreams: dict | None) -> str:
    """The upstream fix a regeneration names: the output's own entry in
    ``upstreams``, else each of its root causes' (joined with "; "), else the
    record's own upstream."""
    if not upstreams:
        return record.get("upstream", "")
    own = upstreams.get("outputs", {}).get(f"{key[0]}|{key[1]}")
    if own:
        return own
    causes = str(record.get("root_cause", "")).split("+")
    fixes = [upstreams.get("root_causes", {}).get(cause) for cause in causes]
    if causes and all(fixes):
        return "; ".join(dict.fromkeys(fixes))
    return record.get("upstream", "")


def draft_actions(
    cells: list[Cell],
    records: dict,
    previous_rechecks: dict,
    previous_upgrade: dict,
    *,
    engine_version: str,
    date: str,
    precise: bool,
    evidence: dict | None = None,
    upstreams: dict | None = None,
    indeterminate: dict | None = None,
) -> tuple[dict, list[dict]]:
    """The draft actions file and the judgment calls, one per moved output.

    ``records`` maps each excluded output to its 20261014 record.
    ``previous_rechecks`` and ``previous_upgrade`` are the base's last engine
    upgrade's rechecks and revision (last_upgrade): a recheck whose engine
    value has not moved since says so. ``evidence`` is {"ref": {path, sha256},
    "doc": the loaded evidence file}: a pre-fix engine's values for
    engine-defect outputs without and with their fix modules. ``indeterminate``
    maps an output an earlier upgrade's recheck found indeterminate on the
    stated facts to that upgrade's date (indeterminate_rechecks): such an
    output stays excluded even where the new engine fixes its defect, since an
    engine cannot settle the facts."""
    indeterminate = indeterminate or {}
    evidence_items = {}
    if evidence is not None:
        for item in evidence["doc"]["items"]:
            evidence_items[key_of(item)] = item
    engine = f"policyengine-us {engine_version}"
    previous_engine = previous_upgrade["engine_version"]
    previous_number = previous_engine.removeprefix("policyengine-us ")
    previous_date = previous_upgrade["date"]
    ver_key = value_key(previous_engine)
    actions = {
        "engine": engine,
        "previous_engine": PREVIOUS_ENGINE,
        "date": date,
        "draft": True,
        "approved": [],
        "regenerated_exclusions": [],
        "new_exclusions": [],
        "excluded_rechecked": [],
    }
    calls = []

    def call(cell: Cell, decision: str, text: str, where: str) -> None:
        calls.append(
            {
                "scenario_id": cell.scenario_id,
                "state": cell.state,
                "variable": cell.variable,
                "previous": cell.previous,
                "new": cell.new,
                "status": cell.status,
                "hub_audited_target": cell.audited_target,
                "decision": decision,
                "placed_in": where,
                "call": text,
            }
        )

    def lands(cell: Cell, aim: float) -> bool:
        return abs(cell.new - aim) <= TARGET_TOL and not beyond(
            cell.variable, aim, cell.new
        )

    for cell in cells:
        k = cell.key
        if not beyond(cell.variable, cell.previous, cell.new):
            continue
        if k in records:
            record = records[k]
            source = "20261014"
            kept_value = cell.previous
            earlier = previous_rechecks.get(k)
            unmoved = earlier is not None and abs(float(earlier[ver_key]) - cell.new) <= 1e-3
            if record["reason_code"] == ENGINE_DEFECT:
                target = float(record["alternative_value"])
                target_spec = {"kind": "record"}
                target_text = f"the corrected value {money(target)} the "
                target_text += f"{record['decided_on']} record computed"
                item = evidence_items.get(k)
                if not lands(cell, target) and item is not None:
                    target = float(item["corrected_value"])
                    target_spec = {
                        "kind": TARGET_FIX_MODULES,
                        "modules": list(item["modules"]),
                        "evidence": dict(evidence["ref"]),
                    }
                    target_text = (
                        f"the corrected value {money(target)} its fix modules "
                        f"({' + '.join(item['modules'])}) give on "
                        f"{evidence['doc']['engine']}, which still has the defect "
                        f"({money(float(item['engine_value']))} without them)"
                    )
                on_target = lands(cell, target)
                second = second_reason(record)
                if on_target and k in indeterminate:
                    reason = (
                        f"Stays excluded on {engine}: the engine gives "
                        f"{money(cell.new)}, on the record's corrected value "
                        f"{money(target)}, so its defect ({record['root_cause']}) "
                        f"is fixed there, but the {indeterminate[k]} recheck found "
                        f"the output {INDETERMINATE}, a second reason that a new "
                        f"engine does not settle; the record keeps {money(kept_value)}."
                    )
                    text = (
                        f"RECHECK ({source} engine defect {record['root_cause']} "
                        f"lands on target, but the {indeterminate[k]} recheck found "
                        f"it {INDETERMINATE}): regenerate only if a reviewer rules "
                        "that reason out"
                    )
                elif on_target and second:
                    reason = (
                        f"Stays excluded on {engine}: the engine gives "
                        f"{money(cell.new)}, on the record's corrected value "
                        f"{money(target)}, but the record names a second reason "
                        f"that a new engine does not settle ({second}); the record "
                        f"keeps {money(kept_value)}."
                    )
                    text = (
                        f"RECHECK ({source} engine defect {record['root_cause']} "
                        "lands on target, but the record's note names an unlisted "
                        "input too): regenerate only if a reviewer rules that "
                        "reason out"
                    )
                elif on_target:
                    upstream = upstream_for(record, k, upstreams)
                    actions["regenerated_exclusions"].append(
                        {
                            "scenario_id": k[0],
                            "variable": k[1],
                            "alternative_value": float(record["alternative_value"]),
                            "tolerance": TARGET_TOL,
                            "upstream": upstream,
                            "basis": (
                                f"An engine defect fixed upstream ({upstream}) is "
                                f"regenerated with the fix: {engine} gives "
                                f"{money(cell.new)}, within $1 of {target_text} "
                                f"({record['root_cause']}: {record['defect']})."
                            ),
                            "target": target_spec,
                        }
                    )
                    hub = cell.audited_target
                    note = (
                        ""
                        if hub in ("", "yes")
                        else f" The hub's table disagrees ({hub}); resolve it first."
                    )
                    if earlier is not None:
                        note += (
                            f" It was rechecked on {previous_date}: read that "
                            f"reason in the {previous_date} engine_upgrade revision."
                        )
                    if upstream.strip().lower() in UNNAMED_UPSTREAM:
                        note += (
                            " The record names no upstream fix; the builder "
                            "refuses the regeneration until upstream names it."
                        )
                    call(
                        cell,
                        "PROPOSED",
                        f"REGENERATE ({source} engine defect {record['root_cause']}): "
                        f"lands on {money(cell.new)} vs target {money(target)}. "
                        "Confirm the fix is released upstream and name it in "
                        f"upstream ({upstream or 'empty'}).{note}",
                        "regenerated_exclusions",
                    )
                    continue
                elif (
                    second
                    and unmoved
                    and "corrected value" in earlier.get("reason", "")
                    and "second reason" in earlier.get("reason", "")
                ):
                    # The previous upgrade's recheck found this value on its
                    # corrected value (directly, or as the value an earlier
                    # recheck found there), and the engine has not moved it
                    # since. The record's own alternative value predates that
                    # evidence, so missing it says nothing about the defect;
                    # the second reason keeps the output excluded.
                    reason = (
                        f"Stays excluded on {engine}: the engine gives "
                        f"{money(cell.new)}, the value {previous_engine} gave when "
                        f"the {previous_date} recheck found it on its corrected "
                        "value, but the record names a second reason that a new "
                        f"engine does not settle ({second}); the record keeps "
                        f"{money(kept_value)}."
                    )
                    text = (
                        f"RECHECK ({source} engine defect {record['root_cause']}, "
                        f"on the corrected value the {previous_date} recheck found, "
                        "with a second reason)"
                    )
                else:
                    reason = (
                        f"Stays excluded on {engine}: the engine gives "
                        f"{money(cell.new)}, {money(abs(cell.new - target))} from "
                        f"the record's corrected value {money(target)}, so the "
                        f"defect ({record['root_cause']}) is not fixed in this "
                        f"release; the record keeps {money(kept_value)}."
                    )
                    if cell.audited_target.startswith("pending"):
                        reason += (
                            " The US hub's sweep marks it pending on more than one "
                            f"fix ({cell.audited_target.removeprefix('pending: ')})."
                        )
                    text = (
                        f"RECHECK ({source} engine defect {record['root_cause']}, "
                        f"off target by {money(abs(cell.new - target))})"
                    )
            elif lands(cell, float(record["alternative_value"])):
                # The engine now takes the record's alternative reading, by a
                # default for the input the prompt does not state; the stated
                # facts still do not decide the output.
                reason = (
                    f"Stays excluded on {engine}: the engine gives "
                    f"{money(cell.new)}, the record's alternative value, since it "
                    "takes that reading by default, but the reference depends on "
                    f"an input the prompt does not state ({record_basis(record)}; "
                    f"{record['reason_code']}), and an engine default does not "
                    f"settle it; the record keeps {money(kept_value)}."
                )
                text = (
                    f"RECHECK ({source} {record['reason_code']}; the engine lands on "
                    "the alternative reading): regenerate only if a reviewer rules "
                    "that the stated facts decide it"
                )
            else:
                reason = (
                    f"Stays excluded on {engine}: the reference depends on "
                    f"{record_basis(record)} ({record['reason_code']}), which an "
                    f"engine release does not settle; the record keeps "
                    f"{money(kept_value)}, and {engine} gives {money(cell.new)}."
                )
                text = f"RECHECK ({source} {record['reason_code']})"
            if unmoved:
                reason += (
                    f" The value is {previous_number}'s, rechecked on "
                    f"{previous_date} (the {previous_date} engine_upgrade "
                    "revision's excluded_outputs_rechecked)."
                )
            elif earlier is not None:
                reason += (
                    f" {previous_engine} gave {money(float(earlier[ver_key]))} "
                    f"when it was rechecked on {previous_date}."
                )
            actions["excluded_rechecked"].append(
                {"scenario_id": k[0], "variable": k[1], "reason": reason}
            )
            call(
                cell,
                "PROPOSED",
                text + " - check the drafted reason",
                "excluded_rechecked",
            )
            continue
        for matches, propose in RULES:
            if matches(cell):
                proposal = propose(cell, engine, date)
                actions[proposal["action"]].append(proposal["entry"])
                text = proposal["call"]
                if not precise:
                    text += (
                        "; the value is the table's, rounded to cents: rerun with "
                        "--computed (the builder's computed.csv) before the build"
                    )
                call(cell, "PROPOSED", text, proposal["action"])
                break
        else:
            call(
                cell,
                "UNDECIDED",
                "scored move no rule recognizes: approve it (cause, basis) or "
                "exclude it (a complete record); the builder refuses it until then",
                "review only",
            )
    for name in (
        "approved",
        "regenerated_exclusions",
        "new_exclusions",
        "excluded_rechecked",
    ):
        actions[name].sort(key=key_of)
    actions["review"] = calls
    return actions, calls


def print_calls(calls: list[dict]) -> None:
    print(f"{len(calls)} moved outputs; every call below needs a reviewer:")
    for c in calls:
        print(
            f"  [{c['decision']}] {c['scenario_id']} {c['state']} {c['variable']}: "
            f"{c['previous']:,.2f} -> {c['new']:,.2f} ({c['status']}) -> "
            f"{c['placed_in']}\n      {c['call']}"
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cells")
    parser.add_argument("--computed")
    parser.add_argument("--engine")
    parser.add_argument("--date")
    parser.add_argument("--evidence", help="a committed evidence file, repo-relative")
    parser.add_argument("--upstreams", help="upstreams.json: the fix each regeneration names")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    evidence = None
    if args.evidence:
        ref = {"path": args.evidence, "sha256": sha256(ROOT / args.evidence)}
        evidence = {"ref": ref, "doc": load_evidence(ref)}
    if not (args.cells or args.computed):
        parser.error("pass --computed (a builder pass) or --cells (a hub table)")
    engine_version = args.engine or engine_from_path(Path(args.cells))
    date = args.date or datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    base = load_base()
    records = {key_of(r): r for r in base.exclusions["exclusions"]}
    computed = read_computed(Path(args.computed)) if args.computed else None
    if args.cells:
        cells = read_cells(Path(args.cells), base.reference.values(), computed)
    else:
        cells = cells_from_computed(
            Path(args.computed), base.reference.values(), records
        )
    actions, calls = draft_actions(
        cells,
        records,
        last_upgrade_rechecks(base.meta),
        last_upgrade(base.meta),
        engine_version=engine_version,
        date=date,
        precise=computed is not None,
        evidence=evidence,
        upstreams=json.loads(Path(args.upstreams).read_text()) if args.upstreams else None,
        indeterminate=indeterminate_rechecks(base.meta),
    )
    Path(args.out).write_text(json.dumps(actions, indent=2) + "\n")
    print_calls(calls)
    print(f"DRAFT -> {args.out} (draft: true; the builder refuses it until reviewed)")


if __name__ == "__main__":
    main()
