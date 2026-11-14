"""Recompute every US reference output twice on the installed policyengine-us:
as the 2.60.0 reference build computes it, and with the household's stated
auto loan interest treated as qualified passenger vehicle loan interest.

Baseline, the reference build's recipe
(reference_audit/2026-10-22-engine-upgrade/scripts/build_references_upgrade.py,
main() and compute_outputs()):
  system    = CountryTaxBenefitSystem(reform=latest_final.reform), with
              reference_audit/2026-09-28/fixes/latest_final.py imported in place
  household = reference_audit/2026-09-28/scripts/sweep.py build_situation(scenario)
  outputs   = expand_programs_for_scenario(programs, scenario), each
              _extract_person_value(sim.calculate(_pe_variable_for_output(v), 2026))
The households and the program list are the frozen snapshot's
(paper/snapshot/20260501/runs/<run>/scenarios.csv and the "programs" of
reference_outputs.csv.meta.json).

Alternative: the same, after copying the household's stated auto_loan_interest
(households.household.auto_loan_interest, a Household input) into
households.household.qualified_passenger_vehicle_loan_interest, the input that
auto_loan_interest_deduction reads (policyengine-us 2.60.0,
variables/gov/irs/income/taxable_income/deductions/auto_loan_interest/
auto_loan_interest_deduction.py, lines 16-21). A household that states no auto
loan interest is left unchanged and computed once.

Writes OUT_DIR/computed.csv (one row per output: base, alt), OUT_DIR/traces.json
(intermediate values for each household that states auto loan interest) and
OUT_DIR/engine_run.json (engine versions and the sha256 of every input read).

Usage, from the repository root with the root on PYTHONPATH:
  python reference_audit/2026-11-11-car-loan-interest/scripts/compute_outputs.py \
      [--out-dir reference_audit/2026-11-11-car-loan-interest/verification] \
      [--scenarios scenario_000 ...]
"""

from __future__ import annotations

import argparse
import copy
import csv
import datetime
import hashlib
import importlib.util
import json
import sys
import time
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AUDIT = HERE.parent
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
FIXES = ROOT / "reference_audit/2026-09-28/fixes"
HARNESS = ROOT / "reference_audit/2026-09-28/scripts/sweep.py"
YEAR = 2026
STATED = "auto_loan_interest"
ENGINE_INPUT = "qualified_passenger_vehicle_loan_interest"
# Intermediate values recorded for households that state auto loan interest.
TRACE_VARIABLES = (
    "auto_loan_interest_deduction",
    "agi_plus_section_911_931_933_exclusions",
    "adjusted_gross_income",
    "tax_unit_itemizes",
    "taxable_income",
    "standard_deduction",
    "taxable_income_deductions",
)


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def alternative_situation(situation: dict) -> tuple[dict, bool]:
    """Copy the stated auto loan interest into the engine's qualifying input."""
    household = situation["households"]["household"]
    if STATED not in household:
        return situation, False
    if ENGINE_INPUT in household:
        raise SystemExit(f"{ENGINE_INPUT} already set: {household[ENGINE_INPUT]}")
    alt = copy.deepcopy(situation)
    alt["households"]["household"][ENGINE_INPUT] = copy.deepcopy(household[STATED])
    return alt, True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=str(AUDIT / "verification"))
    parser.add_argument("--scenarios", nargs="*")
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(ROOT))
    import pandas as pd
    from policyengine_us import CountryTaxBenefitSystem, Simulation

    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output
    from policybench.scenarios import scenario_from_dict
    from policybench.spec import expand_programs_for_scenario

    harness = load_module("car_loan_sweep_harness", HARNESS)
    final = load_module("car_loan_latest_final", FIXES / "latest_final.py")
    system = CountryTaxBenefitSystem(reform=final.reform)

    meta_path = RUN / "reference_outputs.csv.meta.json"
    programs = json.loads(meta_path.read_text())["programs"]
    scenarios = pd.read_csv(RUN / "scenarios.csv")
    if args.scenarios:
        scenarios = scenarios[scenarios["scenario_id"].isin(args.scenarios)]

    rows, traces = [], []
    started = time.time()
    for _, srow in scenarios.iterrows():
        scenario = scenario_from_dict(json.loads(srow["scenario_json"]))
        situation = harness.build_situation(scenario)
        alt, patched = alternative_situation(situation)
        if not patched:
            assert json.dumps(alt, sort_keys=True) == json.dumps(
                situation, sort_keys=True
            )
        sims = {"base": Simulation(tax_benefit_system=system, situation=situation)}
        if patched:
            sims["alt"] = Simulation(tax_benefit_system=system, situation=alt)
        values = {}
        for kind, sim in sims.items():
            for variable in expand_programs_for_scenario(programs, scenario):
                pe_variable = _pe_variable_for_output(variable, "us")
                values[(kind, variable)] = float(
                    _extract_person_value(
                        sim.calculate(pe_variable, YEAR), scenario, variable
                    )
                )
            if patched:
                trace = {
                    "scenario_id": scenario.id,
                    "kind": kind,
                    "state": srow["state"],
                    "filing_status": srow["filing_status"],
                    "stated_auto_loan_interest": situation["households"]["household"][
                        STATED
                    ],
                }
                for tv in TRACE_VARIABLES:
                    trace[tv] = [float(x) for x in sim.calculate(tv, YEAR)]
                trace["engine_input_value"] = [
                    float(x) for x in sim.calculate(ENGINE_INPUT, YEAR)
                ]
                traces.append(trace)
        for variable in expand_programs_for_scenario(programs, scenario):
            base = values[("base", variable)]
            rows.append(
                {
                    "scenario_id": scenario.id,
                    "state": srow["state"],
                    "variable": variable,
                    "base": base,
                    "alt": values.get(("alt", variable), base),
                    "alt_computed": patched,
                }
            )
        print(f"{scenario.id} done ({time.time() - started:.0f}s)", flush=True)

    with (out_dir / "computed.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / "traces.json").write_text(json.dumps(traces, indent=1) + "\n")
    inputs = [
        RUN / "scenarios.csv",
        meta_path,
        FIXES / "latest_final.py",
        HARNESS,
    ]
    run = {
        "engine": f"policyengine-us {version('policyengine-us')}",
        "policyengine_core": version("policyengine-core"),
        "computed_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "inputs": {relative(path): sha256(path) for path in inputs},
        "households": len(scenarios),
        "households_with_alternative": len({t["scenario_id"] for t in traces}),
        "outputs": len(rows),
        "seconds": round(time.time() - started, 1),
    }
    (out_dir / "engine_run.json").write_text(json.dumps(run, indent=1) + "\n")
    print(f"SUMMARY rows={len(rows)} seconds={run['seconds']:.0f}")


if __name__ == "__main__":
    main()
