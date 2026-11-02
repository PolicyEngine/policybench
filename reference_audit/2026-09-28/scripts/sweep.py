"""Recompute every PolicyBench reference under one fix and list the outputs that move.

A fix is a Python module that defines either or both of:
  reform                         a policyengine_core Reform subclass (or None)
  patch(situation, scenario)     returns an edited copy of the situation dict
and optionally FIX_ID and DESCRIPTION strings.

Run with the policyengine-us 1.755.4 triage venv:
  cd /Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/sweep
  PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/opus55 \
    ../.venv-pe1755/bin/python sweep.py --fix fixes/r01_ira_compensation.py --out out/r01.csv
  (no --fix: the baseline, which must reproduce all 1,984 frozen references)

The output CSV has one row per reference output: scenario_id, variable, frozen,
recomputed, delta, moved. An amount output moves when |delta| > 1 (the exact-match
tolerance); a binary output moves when the flag flips. The script prints the
moved rows and a summary line.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

from policybench.ground_truth import _extract_person_value, _pe_variable_for_output
from policybench.scenarios import scenario_from_dict
from policybench.spec import expand_programs_for_scenario

BUNDLE = Path(
    "/Users/maxghenis/PolicyEngine/policybench/results/local/newmodels/publish/"
    "us_full_run_20260612_policyengine_4_16_1_populace/us"
)
# The frozen v1.1 bundle (reference_outputs.csv sha256 b9136a15...), read-only. Not
# adds202609/publish/: the fold overwrites that dir with the regenerated references.
YEAR = 2026
BINARY_SUFFIXES = ("_eligible",)
# The v1.1 reference run renamed this input for policyengine-us 1.755.4
# (results/local/v1_1_runbook.md step 3; v1_1/us/scenarios_patched.csv).
RENAME = {"partnership_se_income": "partnership_self_employment_net_earnings"}


def build_situation(scenario) -> dict:
    situation = scenario.to_pe_household()
    for person in situation["people"].values():
        for old, new in RENAME.items():
            if old in person:
                person[new] = person.pop(old)
    return situation


def load_fix(path: str | None):
    if not path:
        return None, None, "baseline"
    spec = importlib.util.spec_from_file_location("fix_module", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["fix_module"] = module
    spec.loader.exec_module(module)
    return (
        getattr(module, "reform", None),
        getattr(module, "patch", None),
        getattr(module, "FIX_ID", Path(path).stem),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix")
    parser.add_argument("--out", required=True)
    parser.add_argument("--scenarios", nargs="*", help="restrict to these scenario ids")
    args = parser.parse_args()

    from policyengine_us import CountryTaxBenefitSystem, Simulation

    reform, patch, fix_id = load_fix(args.fix)
    # Build the reformed system once and share it across households: passing
    # reform= to each Simulation re-applies it to a fresh copy every time.
    system = CountryTaxBenefitSystem(reform=reform) if reform is not None else None
    meta = json.loads((BUNDLE / "reference_outputs.csv.meta.json").read_text())
    programs = meta["programs"]
    frozen = pd.read_csv(BUNDLE / "reference_outputs.csv").set_index(
        ["scenario_id", "variable"]
    )["value"]
    scenarios = pd.read_csv(BUNDLE / "scenarios.csv")
    if args.scenarios:
        scenarios = scenarios[scenarios["scenario_id"].isin(args.scenarios)]

    rows = []
    for _, srow in scenarios.iterrows():
        scenario = scenario_from_dict(json.loads(srow["scenario_json"]))
        situation = build_situation(scenario)
        if patch is not None:
            situation = patch(copy.deepcopy(situation), scenario)
        sim = (
            Simulation(tax_benefit_system=system, situation=situation)
            if system is not None
            else Simulation(situation=situation)
        )
        for variable in expand_programs_for_scenario(programs, scenario):
            key = (scenario.id, variable)
            if key not in frozen.index:
                continue
            pe_variable = _pe_variable_for_output(variable, "us")
            value = float(
                _extract_person_value(sim.calculate(pe_variable, YEAR), scenario, variable)
            )
            ref = float(frozen[key])
            delta = value - ref
            binary = variable.endswith(BINARY_SUFFIXES)
            moved = (round(value) != round(ref)) if binary else abs(delta) > 1.0
            rows.append(
                {
                    "fix": fix_id,
                    "scenario_id": scenario.id,
                    "state": srow["state"],
                    "variable": variable,
                    "frozen": ref,
                    "recomputed": value,
                    "delta": delta,
                    "moved": moved,
                }
            )
    out = pd.DataFrame(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    moved = out[out["moved"]]
    with pd.option_context("display.width", 200, "display.max_rows", 500):
        print(moved[["scenario_id", "state", "variable", "frozen", "recomputed", "delta"]].to_string(index=False))
    print(
        f"SUMMARY fix={fix_id} outputs={len(out)} moved={len(moved)} "
        f"small_nonzero_deltas={int(((out['delta'].abs() > 1e-6) & ~out['moved']).sum())}"
    )


if __name__ == "__main__":
    main()
