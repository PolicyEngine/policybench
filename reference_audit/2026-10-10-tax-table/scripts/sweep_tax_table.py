"""Recompute every PolicyBench reference with the Tax Table in place of the rate schedule.

The references come from policyengine-us, which applies the section 1 rate
schedule exactly. Two engine variables do it, each through ``tax_at_main_rates``:

  income_tax_main_rates                 the tax on taxable income less the gains
                                        and dividends taxed at capital gain rates
                                        (Form 1040 line 16 without them; line 22
                                        of the Qualified Dividends and Capital
                                        Gain Tax Worksheet; line 44 of the
                                        Schedule D Tax Worksheet)
  tax_on_taxable_income_at_main_rates   the tax on all taxable income (lines 24
                                        and 46 of those worksheets), which caps
                                        the regular tax

The Form 1040 instructions send each of those look-ups to the Tax Table when the
amount is under $100,000. This script reruns every household on the reference
system (the installed policyengine-us, the pre-freeze conventions and the
Maryland adapter: reference_audit/2026-09-28/fixes/latest_final.py, through the
reference builder's own compute_outputs) under three variants of those two
formulas and writes every output under each:

  schedule_copy       the two formulas copied here with the look-up left as the
                      rate schedule. It must equal the baseline on every output,
                      which shows the copies are the engine's formulas.
  table               the look-up is the constructed 2026 Tax Table
                      (scripts/tax_table.py) for an amount under $100,000.
  table_whole_dollar  a look-up rounding sensitivity: as table, with each
                      looked-up amount rounded to a whole dollar first (a half
                      rounds up). At $100,000 or more the worksheet, which is
                      the schedule, is applied to the rounded amount. Nothing
                      else on the return is rounded, so this is not the
                      instructions' whole-dollar return, which rounds every
                      amount ("Rounding Off to Whole Dollars").

Everything downstream is the engine's: the capital gain cap, the alternative
minimum tax, the limit on nonrefundable credits, the refundable credits, and each
state's tax.

  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 uv run python \\
    reference_audit/2026-10-10-tax-table/scripts/sweep_tax_table.py

Writes verification/sweep_tax_table.csv, tax_units.csv and sweep_summary.json,
and prints the moved outputs. The frozen run is read from git at the release
commit (scripts/release.py) and never written.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))

import release  # noqa: E402
import tax_table  # noqa: E402

BUILDER = (
    ROOT / "reference_audit/2026-10-09-engine-upgrade/scripts/"
    "build_references_upgrade.py"
)
OUT = HERE / "verification"
YEAR = 2026
ENGINE = "2.38.6"
FEDERAL = "federal_income_tax_before_refundable_credits"
VARIANTS = ("schedule_copy", "table", "table_whole_dollar")
# The tolerance within which the baseline must reproduce a scored reference: the
# reference builder's own (FROZEN_TOL).
REPRODUCE_TOL = 1e-3
TAX_UNIT_VARIABLES = (
    "taxable_income",
    "capital_gains_excluded_from_taxable_income",
    "income_tax_main_rates",
    "tax_on_taxable_income_at_main_rates",
    "capital_gains_tax",
    "regular_tax_before_credits",
    "alternative_minimum_tax",
    "income_tax_before_credits",
    "income_tax_capped_non_refundable_credits",
    "income_tax_before_refundable_credits",
    "income_tax_refundable_credits",
    "foreign_earned_income_exclusion",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def engine_schedule(system) -> dict:
    """The engine's 2026 brackets, which must be Rev. Proc. 2025-32's."""
    bracket = system.parameters(f"{YEAR}-01-01").gov.irs.income.bracket
    names = {
        "single": "SINGLE",
        "joint": "JOINT",
        "separate": "SEPARATE",
        "head_of_household": "HEAD_OF_HOUSEHOLD",
    }
    rates = tuple(round(float(bracket.rates[str(i)]) * 100) for i in range(1, 8))
    thresholds = {
        status: tuple(
            float(getattr(bracket.thresholds[str(i)], name)) for i in range(1, 7)
        )
        for status, name in names.items()
    }
    surviving = tuple(
        float(bracket.thresholds[str(i)].SURVIVING_SPOUSE) for i in range(1, 7)
    )
    return {"rates": rates, "thresholds": thresholds, "surviving_spouse": surviving}


def check_engine_schedule(system) -> dict:
    found = engine_schedule(system)
    expected = {s: tuple(map(float, tax_table.SCHEDULES[YEAR][s])) for s in found["thresholds"]}
    if found["rates"] != tax_table.RATES or found["thresholds"] != expected:
        raise SystemExit(f"engine brackets are not Rev. Proc. 2025-32's: {found}")
    if found["surviving_spouse"] != expected["joint"]:
        raise SystemExit("surviving spouse brackets are not the joint brackets")
    return found


def look_up(variant: str):
    """The tax on an amount, given the engine's schedule tax on it."""

    def figure(amount, filing_status, schedule_tax, period):
        schedule_tax = np.asarray(schedule_tax, dtype=float)
        if variant == "schedule_copy" or period.start.year != YEAR:
            return schedule_tax
        out = schedule_tax.copy()
        names = filing_status.decode_to_str()
        rounded = variant == "table_whole_dollar"
        for i, value in enumerate(np.asarray(amount, dtype=float)):
            column = tax_table.COLUMN_FOR_FILING_STATUS[str(names[i])]
            value = float(np.floor(value + 0.5)) if rounded else float(value)
            if 0 <= value < tax_table.CEILING:
                out[i] = tax_table.table_tax(value, column, YEAR)
            elif rounded:
                # The rounded amount is at or over the ceiling: the Tax
                # Computation Worksheet on that amount, not the schedule tax on
                # the unrounded one.
                out[i] = tax_table.schedule_tax(value, column, YEAR)
        return out

    return figure


def table_reform(variant: str):
    """The two formulas, copied from policyengine-us 2.38.6, with the look-up swapped."""
    from policyengine_core.reforms import Reform
    from policyengine_us.model_api import max_, where
    from policyengine_us.variables.gov.irs.tax.federal_income.before_credits import (
        income_tax_main_rates as main_module,
    )
    from policyengine_us.variables.gov.irs.tax.federal_income.before_credits import (
        tax_on_taxable_income_at_main_rates as all_module,
    )
    from policyengine_us.variables.gov.irs.tax.federal_income.before_credits.tax_at_main_rates import (  # noqa: E501
        tax_at_main_rates,
    )

    figure = look_up(variant)

    def tax_on(amount, filing_status, bracket, period):
        schedule = tax_at_main_rates(amount, filing_status, bracket)
        return figure(amount, filing_status, schedule, period)

    class income_tax_main_rates(main_module.income_tax_main_rates):
        def formula(tax_unit, period, parameters):
            full_taxable_income = tax_unit(
                "taxable_income_plus_section_911_exclusion", period
            )
            cg_exclusion = tax_unit(
                "capital_gains_excluded_from_taxable_income", period
            )
            taxinc = max_(0, full_taxable_income - cg_exclusion)
            bracket = parameters(period).gov.irs.income.bracket
            filing_status = tax_unit("filing_status", period)
            tax = tax_on(taxinc, filing_status, bracket, period)
            excluded = max_(0, tax_unit("foreign_earned_income_exclusion", period))
            tax_on_excluded = tax_on(excluded, filing_status, bracket, period)
            return where(excluded > 0, max_(0, tax - tax_on_excluded), tax)

    class tax_on_taxable_income_at_main_rates(
        all_module.tax_on_taxable_income_at_main_rates
    ):
        def formula(tax_unit, period, parameters):
            taxable_income = tax_unit(
                "taxable_income_plus_section_911_exclusion", period
            )
            bracket = parameters(period).gov.irs.income.bracket
            filing_status = tax_unit("filing_status", period)
            tax = tax_on(max_(0, taxable_income), filing_status, bracket, period)
            excluded = max_(0, tax_unit("foreign_earned_income_exclusion", period))
            tax_on_excluded = tax_on(excluded, filing_status, bracket, period)
            return where(excluded > 0, max_(0, tax - tax_on_excluded), tax)

    class reform(Reform):
        def apply(self):
            self.update_variable(income_tax_main_rates)
            self.update_variable(tax_on_taxable_income_at_main_rates)

    return reform


def tax_unit_rows(system, scenarios, build_situation, label: str) -> list[dict]:
    """Each tax unit's federal regular tax chain on one system."""
    from policyengine_us import Simulation

    from policybench.scenarios import scenario_from_dict

    rows = []
    for _, srow in scenarios.iterrows():
        scenario = scenario_from_dict(json.loads(srow["scenario_json"]))
        sim = Simulation(
            tax_benefit_system=system, situation=build_situation(scenario)
        )
        status = sim.calculate("filing_status", YEAR).decode_to_str()
        itemizes = sim.calculate("tax_unit_itemizes", YEAR)
        gains = sim.calculate("has_qdiv_or_ltcg", YEAR)
        values = {v: sim.calculate(v, YEAR) for v in TAX_UNIT_VARIABLES}
        for i in range(len(status)):
            rows.append(
                {
                    "system": label,
                    "scenario_id": scenario.id,
                    "state": srow["state"],
                    "tax_unit": i,
                    "tax_units_in_household": len(status),
                    "filing_status": str(status[i]),
                    "itemizes": bool(itemizes[i]),
                    "has_qdiv_or_ltcg": bool(gains[i]),
                    **{v: float(values[v][i]) for v in TAX_UNIT_VARIABLES},
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", nargs="*", help="restrict to these ids (smoke)")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    installed = version("policyengine-us")
    if installed != ENGINE:
        raise SystemExit(f"need policyengine-us {ENGINE}, have {installed}")

    builder = load_module("tax_table_builder", BUILDER)
    harness = load_module("tax_table_sweep_harness", builder.HARNESS)
    final = load_module("tax_table_latest_final", builder.FIXES / "latest_final.py")

    from policyengine_us import CountryTaxBenefitSystem

    from policybench.paper_results import moves_beyond_tolerance
    from policybench.reference_exclusions import (
        exclusion_keys,
        load_reference_exclusions,
    )

    run = release.materialize(Path(tempfile.mkdtemp(prefix="pb-tax-table-")))
    meta = json.loads((run / "reference_outputs.csv.meta.json").read_text())
    if meta["policyengine_bundles"]["us"]["model_version"] != ENGINE:
        raise SystemExit("the frozen references were not built on this engine")
    reference = pd.read_csv(run / "reference_outputs.csv")
    frozen = reference.set_index(["scenario_id", "variable"])["value"]
    excluded = exclusion_keys(
        load_reference_exclusions(run / "reference_exclusions.json")
    )
    scenarios = pd.read_csv(run / "scenarios.csv")
    if args.scenarios:
        scenarios = scenarios[scenarios["scenario_id"].isin(args.scenarios)]
    states = dict(zip(scenarios["scenario_id"], scenarios["state"]))
    programs = meta["programs"]

    systems = {"baseline": CountryTaxBenefitSystem(reform=final.reform)}
    engine_brackets = check_engine_schedule(systems["baseline"])
    for variant in VARIANTS:
        systems[variant] = builder.corrected_system(final, [table_reform(variant)])

    computed = {
        name: builder.compute_outputs(
            system, scenarios, programs, harness.build_situation
        )
        for name, system in systems.items()
    }
    keys = list(computed["baseline"])
    rows = []
    for key in keys:
        scenario_id, variable = key
        row = {
            "scenario_id": scenario_id,
            "state": states[scenario_id],
            "variable": variable,
            "reference": float(frozen[key]),
            "scored": key not in excluded,
            **{name: computed[name][key] for name in systems},
        }
        for variant in ("table", "table_whole_dollar"):
            row[f"{variant}_delta"] = row[variant] - row["baseline"]
            row[f"{variant}_moves"] = bool(
                moves_beyond_tolerance(variable, row["baseline"], row[variant])
            )
        rows.append(row)
    sweep = pd.DataFrame(rows)

    # The baseline is the release's reference system: every scored reference.
    scored = sweep[sweep["scored"]]
    off = scored[(scored["baseline"] - scored["reference"]).abs() > REPRODUCE_TOL]
    if len(off):
        raise SystemExit(f"baseline misses scored references:\n{off.to_string()}")
    # The copied formulas are the engine's: bit-identical on every output.
    drift = sweep[sweep["schedule_copy"] != sweep["baseline"]]
    if len(drift):
        raise SystemExit(f"copied formulas differ from the engine:\n{drift.to_string()}")

    units = pd.DataFrame(
        [
            row
            for name in ("baseline", "table")
            for row in tax_unit_rows(
                systems[name], scenarios, harness.build_situation, name
            )
        ]
    )

    sweep.to_csv(out / "sweep_tax_table.csv", index=False)
    units.to_csv(out / "tax_units.csv", index=False)

    federal = sweep[sweep["variable"] == FEDERAL]
    moved = sweep[sweep["table_moves"]]
    # Federal income tax outputs of returns with $100,000 or more of taxable
    # income, where the look-up is the worksheet under every variant.
    at_or_over = set(
        units[
            (units["system"] == "baseline")
            & (units["taxable_income"] >= tax_table.CEILING)
        ]["scenario_id"]
    )
    federal_over = federal[federal["scenario_id"].isin(at_or_over)]
    summary = {
        "engine": f"policyengine-us {installed}",
        "policyengine_core": version("policyengine-core"),
        "reference_system": {
            "fixes": "reference_audit/2026-09-28/fixes/latest_final.py",
            "fixes_sha256": sha256(builder.FIXES / "latest_final.py"),
            "harness": builder.HARNESS_REL,
            "harness_sha256": sha256(builder.HARNESS),
            "builder": str(BUILDER.relative_to(ROOT)),
            "builder_sha256": sha256(BUILDER),
        },
        "release": {"tag": release.RELEASE, "commit": release.RELEASE_COMMIT},
        "inputs": {
            name: release.SHA256[name]
            for name in (
                "scenarios.csv",
                "reference_outputs.csv",
                "reference_outputs.csv.meta.json",
                "reference_exclusions.json",
            )
        },
        "engine_brackets_2026": {
            "rates_percent": list(engine_brackets["rates"]),
            "thresholds": {k: list(v) for k, v in engine_brackets["thresholds"].items()},
            "equal_rev_proc_2025_32": True,
        },
        "households": int(scenarios["scenario_id"].nunique()),
        "outputs": int(len(sweep)),
        "scored_outputs": int(sweep["scored"].sum()),
        "baseline_reproduces_scored_references": True,
        "baseline_max_abs_gap_to_scored_reference": float(
            (scored["baseline"] - scored["reference"]).abs().max()
        ),
        "schedule_copy_identical_to_baseline": True,
        "federal_outputs": int(len(federal)),
        "federal_scored": int(federal["scored"].sum()),
        "table_moves_by_variable": {
            variable: {
                "moved": int(len(group)),
                "scored": int(group["scored"].sum()),
            }
            for variable, group in moved.groupby("variable")
        },
        "table_changes_any_amount_by_variable": {
            variable: {
                "changed": int(len(group)),
                "scored": int(group["scored"].sum()),
                "max_abs_delta": float(group["table_delta"].abs().max()),
            }
            for variable, group in sweep[sweep["table_delta"].abs() > 1e-6].groupby(
                "variable"
            )
        },
        "look_up_rounding_sensitivity": {
            "outputs_differing_from_table": int(
                ((sweep["table"] - sweep["table_whole_dollar"]).abs() > 1e-6).sum()
            ),
            "federal_outputs_of_returns_at_100000_or_more": int(len(federal_over)),
            "max_abs_difference_among_them": float(
                (federal_over["table"] - federal_over["table_whole_dollar"])
                .abs()
                .max()
            ),
            "differing_by_more_than_1": [
                {"scenario_id": r.scenario_id, "variable": r.variable,
                 "scored": bool(r.scored), "table": r.table,
                 "table_whole_dollar": r.table_whole_dollar}
                for r in sweep[
                    (sweep["table"] - sweep["table_whole_dollar"]).abs() > 1
                ].itertuples()
            ],
        },
        "foreign_earned_income_exclusion_households": int(
            (units["foreign_earned_income_exclusion"] != 0).sum()
        ),
    }
    (out / "sweep_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with pd.option_context("display.width", 250, "display.max_rows", 500):
        print(
            moved[
                ["scenario_id", "state", "variable", "scored", "baseline", "table",
                 "table_delta"]
            ].to_string(index=False)
        )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
