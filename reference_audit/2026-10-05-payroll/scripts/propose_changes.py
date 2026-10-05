"""Draft both candidate records for payroll outputs that count an optional employer pass-through.

Reads the sweep (``sweep_payroll_scope.py``) and the program classification
(``program_classification.json``) and writes two alternative proposals, each in the
format a release would install:

``proposed_regenerations.json``
    One entry per scored output the output-scope adapter moves: the frozen reference,
    the regenerated value (policyengine-us 2.15.17 + latest_final +
    fixes/payroll_mandatory_scope.py), and the program law. A release that adopts it
    writes the values into the reference CSV and adds one ``output_scope`` revision to
    the reference sidecar, as the Maryland adapter was recorded.
``proposed_exclusions.json``
    One ``reference_depends_on_unlisted_input`` record per such output, in the format of
    the frozen run's ``reference_exclusions.json``. The unlisted input is whether the
    employer deducts the employee share, which the law leaves to the employer.

Both change published scores, so they wait for Max's ruling; ``decided_on`` is the date
the proposal was drafted and a release sets it to the ruling's date.

  python reference_audit/2026-10-05-payroll/scripts/propose_changes.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
SWEEP = HERE / "verification/sweep_payroll_scope.csv"
DECOMPOSITION = HERE / "verification/payroll_decomposition.csv"
CLASSIFICATION = HERE / "program_classification.json"
ADAPTER = HERE / "fixes/payroll_mandatory_scope.py"
DRAFTED_ON = "2026-10-05"
ENGINE = "policyengine-us 2.15.17"
OUTPUT = "payroll_tax"
STATUS = (
    f"proposed {DRAFTED_ON}; changes published scores, so it waits for Max's ruling "
    "(cos decision). decided_on is the draft date; a release sets it to the ruling's "
    "date. proposed_regenerations.json and proposed_exclusions.json are alternatives: "
    "a release adopts one of them, not both."
)


def money(value: float) -> str:
    return f"${value:,.2f}"


def program_for(leaf: str, programs: list[dict]) -> dict:
    for program in programs:
        if leaf in program["engine_variables"]:
            return program
    raise KeyError(leaf)


def adapter_optional() -> set[str]:
    """The programs payroll_mandatory_scope.py drops, read from its source."""
    import ast

    tree = ast.parse(ADAPTER.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "OPTIONAL" for t in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise SystemExit("the adapter defines no OPTIONAL")


def main() -> None:
    sweep = pd.read_csv(SWEEP)
    decomposition = pd.read_csv(DECOMPOSITION).set_index("scenario_id")
    classification = json.loads(CLASSIFICATION.read_text())
    programs = classification["programs"]
    adapter_sha = hashlib.sha256(ADAPTER.read_bytes()).hexdigest()

    # The adapter drops exactly the reviewed programs classified as optional.
    reviewed_optional = {
        leaf
        for program in programs
        if program["classification"] == "optional_employer_pass_through"
        and all(not v["refuted"] for v in program["review"].values())
        for leaf in program["engine_variables"]
    }
    if adapter_optional() != reviewed_optional:
        raise SystemExit(
            f"adapter OPTIONAL {sorted(adapter_optional())} differs from the reviewed "
            f"optional programs {sorted(reviewed_optional)}"
        )

    moved = sweep[sweep["moved_any"]]
    unexpected = moved[(moved["variable"] != OUTPUT) | moved["excluded"]]
    if not unexpected.empty:
        raise SystemExit(
            f"the adapter moves outputs this proposal does not cover:\n{unexpected}"
        )

    regenerated, excluded = [], []
    for row in moved.itertuples():
        d = decomposition.loc[row.scenario_id]
        leaves = dict(
            (k, float(v))
            for k, v in (
                item.split("=") for item in str(d["state_programs"]).split(";")
            )
        )
        removed = {
            leaf: amount
            for leaf, amount in leaves.items()
            if program_for(leaf, programs)["classification"]
            == "optional_employer_pass_through"
        }
        cited = []
        for leaf in removed:
            program = program_for(leaf, programs)
            if program not in cited:
                cited.append(program)
        names = " and ".join(p["program"] for p in cited)
        law = "; ".join(p["law_citation"] for p in cited)
        removed_text = ", ".join(
            f"{leaf} {money(amount)}" for leaf, amount in sorted(removed.items())
        )
        if abs(sum(removed.values()) - (row.final - row.scoped)) > 0.01:
            raise SystemExit(
                f"{row.scenario_id}: removed programs do not explain the move"
            )
        why = " ".join(p["employee_share_rule_text"] for p in cited)
        regenerated.append(
            {
                "scenario_id": row.scenario_id,
                "variable": OUTPUT,
                "state": row.state,
                "frozen_value": float(row.final),
                "regenerated_value": float(row.scoped),
                "removed": removed,
                "cause": "payroll_mandatory_scope",
                "basis": (
                    f"The output's definition counts mandatory employee state payroll "
                    f"taxes and excludes employer payroll taxes. {why} The frozen "
                    f"reference counts the largest share the employer may deduct "
                    f"({removed_text}); the regenerated value leaves it out and keeps "
                    f"employee Social Security and Medicare tax."
                ),
                "law": law,
                "engine_version": ENGINE,
                "fix_module": "payroll_mandatory_scope.py",
                "fix_module_sha256": adapter_sha,
                "applied_together_with": ["latest_final"],
            }
        )
        excluded.append(
            {
                "scenario_id": row.scenario_id,
                "variable": OUTPUT,
                "reason_code": "reference_depends_on_unlisted_input",
                "alternative_reading": (
                    f"The prompt defines payroll_tax as employee Social Security, "
                    f"Medicare and Additional Medicare Tax plus mandatory employee state "
                    f"payroll taxes. {why} The reference counts the largest employee "
                    f"share the employer may deduct ({removed_text}), as policyengine-us "
                    f"assumes. Read as an employer premium that is not a mandatory "
                    f"employee tax, or with an employer that does not deduct it, the "
                    f"output is employee federal payroll tax alone, the alternative "
                    f"value (policyengine-us 2.15.17 with latest_final and "
                    f"payroll_mandatory_scope)."
                ),
                "frozen_value": float(row.final),
                "alternative_value": float(row.scoped),
                "engine_version": ENGINE,
                "decided_on": DRAFTED_ON,
                "decided_by": "developer",
                "unlisted_input": (
                    f"whether the employer deducts the employee share of {names} from "
                    f"wages, which the law permits but does not require ({law})"
                ),
                "note": (
                    f"Found {DRAFTED_ON} by classifying every state program in the "
                    f"payroll references from primary law "
                    f"(reference_audit/2026-10-05-payroll/program_classification.json) "
                    f"and sweeping all 1,984 outputs with the programs classified as "
                    f"optional employer pass-through left out of employee state payroll "
                    f"tax; that moves this output alone in its household and no other "
                    f"output. The frozen value has been the reference since the first "
                    f"run (2026-06-15)."
                ),
            }
        )

    common = {
        "schema_version": 1,
        "status": STATUS,
        "classification": "program_classification.json",
        "sweep": "verification/sweep_payroll_scope.csv",
    }
    (HERE / "proposed_regenerations.json").write_text(
        json.dumps(
            {
                **common,
                "basis": (
                    "The benchmark's output definitions hold (reference_audit/2026-09-28 "
                    "rule 3): an output-scope adapter restores the payroll_tax "
                    "definition, as latest_md_local_output_scope.py restored the state "
                    "income tax output's."
                ),
                "regenerated": regenerated,
            },
            indent=2,
        )
        + "\n"
    )
    (HERE / "proposed_exclusions.json").write_text(
        json.dumps(
            {
                **common,
                "basis": (
                    "policybench/reference_exclusions.py: an output is excluded for every "
                    "model when its reference depends on an engine input the prompt "
                    "never listed and a careful reader could take the stated facts the "
                    "other way."
                ),
                "exclusions": excluded,
            },
            indent=2,
        )
        + "\n"
    )
    for item in regenerated:
        print(
            item["scenario_id"],
            item["state"],
            money(item["frozen_value"]),
            "->",
            money(item["regenerated_value"]),
            item["removed"],
        )


if __name__ == "__main__":
    main()
