"""Check the draft convention module against the sweep, output by output.

Recomputes all 1,984 outputs with ``fixes/latest_final_la.py`` (latest_final plus
``latest_c_la_published_2026``) and compares each with the ``ldr_published`` column of
``verification/sweep_la_standard_deduction.csv``, which the sweep computed with an inline
reform. The two are separate implementations of the same parameter change, so they must
agree on every output to the cent. Also checks the module's parameter values on the
engine: 2026 single and separate $12,875, the other statuses $25,750; 2025 unchanged at
$12,500 and $25,000.

  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=<checkout> \\
    <triage>/.venv-pe21517/bin/python \\
    reference_audit/2026-10-05-louisiana/scripts/verify_convention_module.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
SWEEP = HERE / "verification/sweep_la_standard_deduction.csv"
OUT = HERE / "verification/verify_convention_module.json"
YEAR = 2026
AGREE = 0.005
RENAME = {"partnership_se_income": "partnership_self_employment_net_earnings"}
PARAMETER = "gov.states.la.tax.income.deductions.standard.amount"

_SYSTEM = None


def _system():
    global _SYSTEM
    if _SYSTEM is None:
        from policyengine_us import CountryTaxBenefitSystem

        path = HERE / "fixes/latest_final_la.py"
        spec = importlib.util.spec_from_file_location("latest_final_la", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["latest_final_la"] = module
        spec.loader.exec_module(module)
        _SYSTEM = CountryTaxBenefitSystem(reform=module.reform)
    return _SYSTEM


def run_scenario(args: tuple[str, list[str]]) -> dict:
    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output
    from policybench.scenarios import scenario_from_dict
    from policyengine_us import Simulation

    scenario_json, variables = args
    scenario = scenario_from_dict(json.loads(scenario_json))
    situation = scenario.to_pe_household()
    for person in situation["people"].values():
        for old, new in RENAME.items():
            if old in person:
                person[new] = person.pop(old)
    sim = Simulation(tax_benefit_system=_system(), situation=situation)
    return {
        "scenario_id": scenario.id,
        "values": {
            v: float(
                _extract_person_value(
                    sim.calculate(_pe_variable_for_output(v, "us"), YEAR), scenario, v
                )
            )
            for v in variables
        },
    }


def parameter_values() -> dict[str, dict[str, float]]:
    node = _system().parameters.get_child(PARAMETER)
    return {
        status: {
            year: float(node.get_child(status)(f"{year}-01-01"))
            for year in ("2025", "2026")
        }
        for status in ("SINGLE", "SEPARATE", "JOINT", "HEAD_OF_HOUSEHOLD", "SURVIVING_SPOUSE")
    }


def main() -> None:
    from policybench.scenarios import scenario_from_dict
    from policybench.spec import expand_programs_for_scenario

    meta = json.loads((RUN / "reference_outputs.csv.meta.json").read_text())
    reference = pd.read_csv(RUN / "reference_outputs.csv")
    indexed = reference.set_index(["scenario_id", "variable"])["value"]
    jobs = []
    for _, row in pd.read_csv(RUN / "scenarios.csv").iterrows():
        scenario = scenario_from_dict(json.loads(row["scenario_json"]))
        variables = [
            v
            for v in expand_programs_for_scenario(meta["programs"], scenario)
            if (scenario.id, v) in indexed.index
        ]
        jobs.append((row["scenario_json"], variables))
    with ProcessPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(run_scenario, jobs))

    sweep = pd.read_csv(SWEEP).set_index(["scenario_id", "variable"])
    disagreements = []
    compared = 0
    for result in results:
        for variable, value in result["values"].items():
            expected = float(sweep.loc[(result["scenario_id"], variable), "ldr_published"])
            compared += 1
            if abs(value - expected) > AGREE:
                disagreements.append(
                    {
                        "scenario_id": result["scenario_id"],
                        "variable": variable,
                        "module": value,
                        "sweep_ldr_published": expected,
                    }
                )
    params = parameter_values()
    expected_params = {
        status: {"2025": base, "2026": published}
        for status, base, published in (
            ("SINGLE", 12_500.0, 12_875.0),
            ("SEPARATE", 12_500.0, 12_875.0),
            ("JOINT", 25_000.0, 25_750.0),
            ("HEAD_OF_HOUSEHOLD", 25_000.0, 25_750.0),
            ("SURVIVING_SPOUSE", 25_000.0, 25_750.0),
        )
    }
    summary = {
        "policyengine_us": version("policyengine-us"),
        "outputs_compared": compared,
        "disagreements": disagreements,
        "parameters": params,
        "parameters_as_expected": params == expected_params,
    }
    OUT.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=1, sort_keys=True))
    if disagreements or not summary["parameters_as_expected"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
