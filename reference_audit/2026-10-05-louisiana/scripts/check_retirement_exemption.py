"""Check whether Louisiana's published 2026 retirement income exemption moves any output.

policyengine-us 2.15.17 carries the R.S. 47:44.1 exemption for filers 65 and older at
$12,000 for 2026 (parameters/gov/states/la/tax/income/exempt_income/retirement/cap.yaml:
2025-01-01 only, no uprating). The Department of Revenue published $12,324 for tax year
2026 before the freeze, in its Notice of Intent on LAC 61:I.1311 (Louisiana Register,
June 20, 2026, p. 1050, doc 2606#052). That is $12,000 x 1.027, the same 2.7% it later
applied to the standard deduction in RIB 26-019.

Recomputes every output with ``latest_final`` and the 2026 cap at $12,324 and lists every
output that changes against ``latest_final`` alone.

  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=<checkout> \\
    <triage>/.venv-pe21517/bin/python \\
    reference_audit/2026-10-05-louisiana/scripts/check_retirement_exemption.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "sweep_la_standard_deduction", HERE / "sweep_la_standard_deduction.py"
)
sweep = importlib.util.module_from_spec(spec)
sys.modules["sweep_la_standard_deduction"] = sweep
spec.loader.exec_module(sweep)

OUT = HERE.parent / "verification/check_retirement_exemption.json"
CAP = "gov.states.la.tax.income.exempt_income.retirement.cap"
PUBLISHED_2026 = 12_324
_SYSTEMS: dict[str, object] = {}


def _cap_reform():
    from policyengine_core.reforms import Reform

    def modify(parameters):
        bracket = parameters.get_child(CAP).brackets[1]
        assert float(bracket.amount("2026-01-01")) in (12_000, PUBLISHED_2026)
        bracket.amount.update(period="2026", value=PUBLISHED_2026)
        return parameters

    class reform(Reform):
        def apply(self):
            self.modify_parameters(modify)

    return reform


def _system(published: bool):
    key = "published" if published else "baseline"
    if key not in _SYSTEMS:
        from policyengine_us import CountryTaxBenefitSystem

        if sweep._FIX_DIR is None:
            sweep._FIX_DIR = sweep._assemble_fixes()
        reforms = (sweep._load_latest_final(sweep._FIX_DIR),)
        if published:
            reforms += (_cap_reform(),)
        _SYSTEMS[key] = CountryTaxBenefitSystem(reform=reforms)
    return _SYSTEMS[key]


def run(args: tuple[str, list[str]]) -> dict:
    from policybench.scenarios import scenario_from_dict
    from policyengine_us import Simulation

    scenario_json, variables = args
    scenario = scenario_from_dict(json.loads(scenario_json))
    situation = sweep.build_situation(scenario)
    values = {}
    for published in (False, True):
        sim = Simulation(tax_benefit_system=_system(published), situation=situation)
        values[published] = sweep._outputs(sim, scenario, variables)
    cap = float(_system(True).parameters.get_child(CAP).brackets[1].amount("2026-01-01"))
    return {
        "scenario_id": scenario.id,
        "state": scenario.state,
        "cap": cap,
        "changes": {
            v: [values[False][v], values[True][v]]
            for v in variables
            if abs(values[True][v] - values[False][v]) > 1e-6
        },
    }


def main() -> None:
    from policybench.scenarios import scenario_from_dict
    from policybench.spec import expand_programs_for_scenario

    meta = json.loads((sweep.RUN / "reference_outputs.csv.meta.json").read_text())
    reference = pd.read_csv(sweep.RUN / "reference_outputs.csv")
    indexed = reference.set_index(["scenario_id", "variable"])["value"]
    jobs = []
    for _, row in pd.read_csv(sweep.RUN / "scenarios.csv").iterrows():
        scenario = scenario_from_dict(json.loads(row["scenario_json"]))
        variables = [
            v
            for v in expand_programs_for_scenario(meta["programs"], scenario)
            if (scenario.id, v) in indexed.index
        ]
        jobs.append((row["scenario_json"], variables))
    with ProcessPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(run, jobs))
    summary = {
        "policyengine_us": version("policyengine-us"),
        "retirement_cap_2026_under_check": sorted({r["cap"] for r in results}),
        "outputs_compared": sum(len(j[1]) for j in jobs),
        "changed_outputs": {
            f"{r['scenario_id']}/{v}": pair
            for r in results
            for v, pair in r["changes"].items()
        },
    }
    OUT.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
