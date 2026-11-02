"""Tabulate, for every household with a Medicare-eligible person, where the premium goes.

Reads verification/sweep_part_b_households.json and writes
verification/part_b_households.csv: one row per household with the premium the engine
charges, the federal itemization election and medical expense deduction with and
without it, the household's federal, state and SNAP outputs, the state-tax variables
the ``no_part_b`` propagation trace shows moving, and whether any output moved.

  python reference_audit/2026-10-05-medicare-part-b/scripts/explain_households.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
HOUSEHOLDS = HERE / "verification/sweep_part_b_households.json"
OUT = HERE / "verification/part_b_households.csv"
FEDERAL = "federal_income_tax_before_refundable_credits"
STATE = "state_income_tax_before_refundable_credits"
STATE_PREFIX = re.compile(r"^[a-z]{2}_")
# Engine variables with a two-letter prefix that are not state programs.
NOT_STATE = ("tax_", "is_", "ca_oc_")


def main() -> None:
    households = json.loads(HOUSEHOLDS.read_text())["households"]
    rows = []
    for h in households:
        if not h["medicare_eligible"]:
            continue
        person = h["baseline_person"]
        base, no_b = h["baseline_units"], h["readings"]["no_part_b"]["units"]
        outputs = h["baseline"]
        no_b_outputs = h["readings"]["no_part_b"]["outputs"]
        trace = h["readings"]["no_part_b"]["trace"]
        state_vars = sorted(
            r["variable"]
            for r in trace
            if STATE_PREFIX.match(r["variable"])
            and not r["variable"].startswith(NOT_STATE)
        )
        itemizes_moved = any(r["variable"] == "tax_unit_itemizes" for r in trace)
        moved = sorted(
            v
            for v in outputs
            if (
                round(no_b_outputs[v]) != round(outputs[v])
                if v.endswith("_eligible")
                else abs(no_b_outputs[v] - outputs[v]) > 1.0
            )
        )
        rows.append(
            {
                "scenario_id": h["scenario_id"],
                "state": h["state"],
                "medicare_eligible_people": sum(
                    person["is_medicare_eligible"].values()
                ),
                "part_b_premium": sum(person["medicare_part_b_premium"].values()),
                "msp_part_b_coverage": sum(
                    person["msp_part_b_premium_coverage"].values()
                ),
                "federal_itemizes": bool(base["tax_unit_itemizes"]),
                "federal_itemizes_without_part_b": (
                    (not bool(base["tax_unit_itemizes"]))
                    if itemizes_moved
                    else bool(base["tax_unit_itemizes"])
                ),
                "medical_expense_deduction": base["medical_expense_deduction"],
                "medical_expense_deduction_without_part_b": no_b[
                    "medical_expense_deduction"
                ],
                "federal_output": outputs.get(FEDERAL),
                "state_output": outputs.get(STATE),
                "snap": outputs.get("snap"),
                "snap_without_part_b": no_b_outputs.get("snap"),
                "state_variables_moving": ";".join(state_vars),
                "outputs_moved": ";".join(moved),
            }
        )
    table = pd.DataFrame(rows)
    table.to_csv(OUT, index=False)
    with pd.option_context("display.width", 250, "display.max_rows", 100):
        print(
            table.drop(columns=["state_variables_moving"])
            .round(2)
            .to_string(index=False)
        )
        print()
        print(
            table[["scenario_id", "state", "state_variables_moving"]].to_string(
                index=False
            )
        )


if __name__ == "__main__":
    main()
