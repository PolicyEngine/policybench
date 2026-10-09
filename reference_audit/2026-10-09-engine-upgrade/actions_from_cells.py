"""Draft an actions file for build_references_upgrade.py from the US hub's sweep.

Input: the hub's cells_pe<ver>.csv (every output on the new release against the
20261006 references: scenario_id, state, variable, frozen_20261006, new, delta,
moved, status, audited_target), optionally the builder's computed.csv (or any
sweep.py output) for full-precision values, the release spec
(docs/haiku55/spec.json, through scripts/finish_haiku55.py) and the exclusion
records (20261006's, read from git, and the release's ruled ten).

Output: a DRAFT actions file ("draft": true, which the builder refuses until a
reviewer clears it) and, on stdout, every judgment call it drafted. Nothing is
decided silently: each moved output is classified by

  status          scored, excluded in 20261006, or ruled in the release;
  audited target  whether the new value lands within $1 of its record's
                  corrected value (alternative_value) or, with --evidence, of
                  the corrected value the record's fix modules give on a
                  pre-fix engine (a "fix_modules" target, which the builder
                  also checks the modules leave unchanged on the new engine);
                  and the hub's own column;
  reason          engine defect, unlisted input, or a ruled reason (later law,
                  household scope);

and lands in exactly one place:

  regenerated_exclusions  an engine-defect record the new engine lands on
                  (PROPOSED: confirm the upstream fix and its release);
  excluded_rechecked  any other excluded output that moves, with a drafted
                  reason (PROPOSED: check the reason);
  approved / new_exclusions  a scored move a RULES entry recognizes, with drafted
                  cause and basis or a drafted record (PROPOSED: check every
                  sentence against the build's trace);
  review only     a scored move no rule recognizes (UNDECIDED: the builder
                  refuses it as an unreviewed move until a reviewer adds it).

kept_exclusions_from_release lists every ruled output that is not regenerated.

  PYTHONPATH=<checkout> python actions_from_cells.py \\
    --cells ~/reviews/policybench-pe-upgrade-2026-10-09/cells_pe2.37.1.csv \\
    [--computed <build>/computed.csv] [--date YYYY-MM-DD] \\
    [--evidence reference_audit/2026-10-09-engine-upgrade/evidence/pe<ver>.json] \\
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
    release_record,
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
# The text states what the hub documented (README.md, HUB_BRIEF.md) and what the
# 2.36.0 rehearsal's traces show (local_income_tax = in_county_tax with county_str
# ADAMS_COUNTY_IN for scenario_015 and 067; state_income_tax_before_refundable_credits
# = id_income_tax_before_refundable_credits + id_pbf $10 for scenario_076); a
# reviewer checks it against the build's trace.


def _indiana_county(cell: Cell, engine: str, date: str) -> dict:
    return {
        "action": "new_exclusions",
        "rule": "indiana_county_unlisted",
        "entry": {
            "scenario_id": cell.scenario_id,
            "variable": cell.variable,
            "reason_code": UNLISTED,
            "unlisted_input": "county of residence (Indiana county income tax)",
            "alternative_reading": (
                "The prompt places the household in Indiana but states no county, "
                "and Indiana's county income taxes (IC 6-3.6) differ by county. "
                f"{engine} computes Indiana county tax (in_county_tax) in "
                "local_income_tax at the rate of the county it assigns a household "
                "with no stated county (Adams County on policyengine-us 2.36.0). "
                f"Read without a county, as {PREVIOUS_ENGINE} did, the household "
                "owes no county tax."
            ),
            "frozen_value": cell.new,
            "alternative_value": cell.previous,
            "engine_version": engine,
            "decided_on": date,
            "decided_by": "developer",
            "note": (
                f"Found in the {date} engine upgrade (the US hub's sweep, "
                "cells_pe<ver>.md: local-tax standardization wires Indiana county "
                "income tax into local_income_tax). The alternative is the "
                f"{PREVIOUS_ENGINE} reference."
            ),
        },
        "call": (
            "NEW EXCLUSION (unlisted input: county) - confirm the county the engine "
            "assumes in the build trace and the alternative value"
        ),
    }


def _idaho_building_fund(cell: Cell, engine: str, date: str) -> dict:
    return {
        "action": "approved",
        "rule": "idaho_permanent_building_fund",
        "entry": {
            "scenario_id": cell.scenario_id,
            "variable": cell.variable,
            "value": cell.new,
            "cause": "id_permanent_building_fund_tax",
            "basis": (
                "Idaho's $10 permanent building fund tax counts in state income "
                f"tax: on {engine}, state_income_tax_before_refundable_credits adds "
                "id_pbf ($10 for a filer liable for it, id_pbf_liable; Idaho Form 40 "
                "instructions) to Idaho income tax before refundable credits. The "
                "US hub's sweep dates the change to policyengine-us 2.30.0."
            ),
        },
        "call": (
            "APPROVE (+$10 permanent building fund tax, id_pbf in the 2.36.0 "
            "trace) - confirm the trace and the Idaho Code citation"
        ),
    }


RULES = (
    (
        lambda c: (
            c.state == "IN"
            and c.variable == "local_income_tax"
            and c.previous == 0
            and c.new > 0
        ),
        _indiana_county,
    ),
    (
        lambda c: (
            c.state == "ID"
            and c.variable == "state_income_tax_before_refundable_credits"
            and abs(c.new - c.previous - 10) <= CELL_TOL
        ),
        _idaho_building_fund,
    ),
)


# --- Inputs --------------------------------------------------------------------


def read_cells(path: Path, board: dict, computed: dict | None) -> list[Cell]:
    with Path(path).open(newline="") as source:
        rows = list(csv.DictReader(source))
    keys = {(r["scenario_id"], r["variable"]) for r in rows}
    if keys != set(board) or len(rows) != len(board):
        raise Refusal("the cells table does not list exactly the 20261006 outputs")
    cells = []
    for r in rows:
        k = (r["scenario_id"], r["variable"])
        if abs(float(r["frozen_20261006"]) - board[k]) > CELL_TOL:
            raise Refusal(f"{k}: the table's frozen value is not 20261006's")
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


def first_upgrade_rechecks(meta: dict) -> dict:
    first = [r for r in meta["revisions"] if r["kind"] == "engine_upgrade"][0]
    return {key_of(r): r for r in first["excluded_outputs_rechecked"]}


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


def draft_actions(
    cells: list[Cell],
    release: dict,
    ruled: set,
    base_excluded: set,
    first_rechecks: dict,
    *,
    engine_version: str,
    date: str,
    spec_sha256: str,
    precise: bool,
    evidence: dict | None = None,
) -> tuple[dict, list[dict]]:
    """The draft actions file and the judgment calls, one per moved output.

    ``evidence`` is {"ref": {path, sha256}, "doc": the loaded evidence file}:
    a pre-fix engine's values for engine-defect outputs without and with
    their fix modules."""
    evidence_items = {}
    if evidence is not None:
        for item in evidence["doc"]["items"]:
            evidence_items[key_of(item)] = item
    engine = f"policyengine-us {engine_version}"
    ver_key = "value_on_2_15_17"
    records = {key_of(r): r for r in release["exclusions"]}
    actions = {
        "engine": engine,
        "previous_engine": PREVIOUS_ENGINE,
        "date": date,
        "release_spec_sha256": spec_sha256,
        "draft": True,
        "approved": [],
        "regenerated_exclusions": [],
        "new_exclusions": [],
        "excluded_rechecked": [],
        "kept_exclusions_from_release": [],
    }
    calls = []
    regenerated = set()

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

    for cell in cells:
        k = cell.key
        if not beyond(cell.variable, cell.previous, cell.new):
            continue
        if k in records:
            record = records[k]
            source = "20261006" if k in base_excluded else "the release's ruling"
            kept_value = cell.previous
            if record["reason_code"] == ENGINE_DEFECT:

                def lands(aim: float) -> bool:
                    return abs(cell.new - aim) <= TARGET_TOL and not beyond(
                        cell.variable, aim, cell.new
                    )

                target = float(record["alternative_value"])
                target_spec = {"kind": "record"}
                target_text = f"the corrected value {money(target)} the "
                target_text += f"{record['decided_on']} record computed"
                item = evidence_items.get(k)
                if not lands(target) and item is not None:
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
                on_target = lands(target)
                second = second_reason(record)
                if on_target and second:
                    reason = (
                        f"Stays excluded on {engine}: the engine gives "
                        f"{money(cell.new)}, on the record's corrected value "
                        f"{money(target)}, but the record names a second reason "
                        f"that a new engine does not settle ({second}); the record "
                        f"keeps {money(kept_value)}."
                    )
                    actions["excluded_rechecked"].append(
                        {"scenario_id": k[0], "variable": k[1], "reason": reason}
                    )
                    call(
                        cell,
                        "PROPOSED",
                        f"RECHECK ({source} engine defect {record['root_cause']} "
                        "lands on target, but the record's note names an unlisted "
                        "input too): regenerate only if a reviewer rules that "
                        "reason out",
                        "excluded_rechecked",
                    )
                    continue
                if on_target:
                    regenerated.add(k)
                    upstream = record.get("upstream", "")
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
                    if k in first_rechecks:
                        note += (
                            " It was rechecked on 2026-09-29: read that reason in "
                            "the first engine_upgrade revision."
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
                reason = (
                    f"Stays excluded on {engine}: the engine gives {money(cell.new)}, "
                    f"{money(abs(cell.new - target))} from the record's corrected "
                    f"value {money(target)}, so the defect ({record['root_cause']}) "
                    f"is not fixed in this release; the record keeps "
                    f"{money(kept_value)}."
                )
                if cell.audited_target.startswith("pending"):
                    reason += (
                        " The US hub's sweep marks it pending on more than one fix "
                        f"({cell.audited_target.removeprefix('pending: ')})."
                    )
                text = (
                    f"RECHECK ({source} engine defect {record['root_cause']}, off "
                    f"target by {money(abs(cell.new - target))})"
                )
            else:
                reason = (
                    f"Stays excluded on {engine}: the reference depends on "
                    f"{record_basis(record)} ({record['reason_code']}), which an "
                    f"engine release does not settle; the record keeps "
                    f"{money(kept_value)}, and {engine} gives {money(cell.new)}."
                )
                text = f"RECHECK ({source} {record['reason_code']})"
            earlier = first_rechecks.get(k)
            if earlier is not None and abs(float(earlier[ver_key]) - cell.new) <= 1e-3:
                reason += (
                    " The value is 2.15.17's, rechecked on 2026-09-29 (the first "
                    "engine_upgrade revision's excluded_outputs_rechecked)."
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
    actions["kept_exclusions_from_release"] = [
        {"scenario_id": k[0], "variable": k[1]} for k in sorted(ruled - regenerated)
    ]
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
    parser.add_argument("--cells", required=True)
    parser.add_argument("--computed")
    parser.add_argument("--engine")
    parser.add_argument("--date")
    parser.add_argument("--evidence", help="a committed evidence file, repo-relative")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    evidence = None
    if args.evidence:
        ref = {"path": args.evidence, "sha256": sha256(ROOT / args.evidence)}
        evidence = {"ref": ref, "doc": load_evidence(ref)}
    engine_version = args.engine or engine_from_path(Path(args.cells))
    date = args.date or datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    base = load_base()
    release, ruled, spec_sha = release_record(base.exclusions)
    computed = read_computed(Path(args.computed)) if args.computed else None
    cells = read_cells(Path(args.cells), base.reference.values(), computed)
    actions, calls = draft_actions(
        cells,
        release,
        ruled,
        {key_of(r) for r in base.exclusions["exclusions"]},
        first_upgrade_rechecks(base.meta),
        engine_version=engine_version,
        date=date,
        spec_sha256=spec_sha,
        precise=computed is not None,
        evidence=evidence,
    )
    Path(args.out).write_text(json.dumps(actions, indent=2) + "\n")
    print_calls(calls)
    print(f"DRAFT -> {args.out} (draft: true; the builder refuses it until reviewed)")


if __name__ == "__main__":
    main()
