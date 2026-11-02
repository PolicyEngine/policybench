"""Secondary readings behind the numbers the proposed records' notes cite.

sweep_salt_withholding.py settles which outputs the state income tax in SALT moves.
This script computes the side values the records and the README quote, on the same
reference system (policyengine-us 2.15.17 + latest_final) and the same households:

``corrected_liability``
    The liability reading with the state liability an existing engine-defect record
    corrects: scenario_081's Massachusetts tax at r22's corrected $8,232.900391 and
    scenario_022's California tax at r11's corrected $1,968.80542 (both recorded on
    1.755.4; r11 was not ported to 2.15.17).
``payroll_in_salt``
    Every household, with mandatory employee state payroll contributions
    (``employee_state_payroll_tax``: CA SDI, MA/CT paid leave and the rest) added to
    the income side of SALT, once on top of the withholding estimate and once on top
    of the liability. policyengine-us 2.15.17 computes them for the payroll tax output
    and leaves them out of SALT; Rev. Rul. 2025-4 treats state paid-leave
    contributions as 164(a)(3) income taxes, and Trujillo v. Commissioner, 68 T.C. 670
    (1977), held the same for CA SDI.
``no_local_sales``
    Every household, with ``local_sales_tax`` at 0 (the engine sets it to 20% of the
    state table amount, an estimate of an unlisted locality), on the reference and
    under the zero reading.
``no_part_b``
    Every household, with each person's ``medicare_part_b_premium`` at 0. The engine
    adds a modeled Part B premium to medical expenses for Medicare-eligible people the
    prompt never says are enrolled; scenario_114 also under the liability reading and
    the literal reading (no withholding, no local sales tax, no Part B).
``md_counties``
    scenario_068 and scenario_078 under the liability reading at each of Maryland's 24
    county rates (the county is not a benchmark input; 2.15.17 defaults to Allegany).
``r02_120``
    scenario_120 federal on 2.15.17 with r02's IRA fix (latest_alt_r02_ira_219g), under
    the reference, liability and zero readings.

  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=<checkout> \\
    <triage>/.venv-pe21517/bin/python reference_audit/2026-10-05/scripts/variants.py \\
      --out reference_audit/2026-10-05/verification/variants.json
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep_salt_withholding as base  # noqa: E402

MD_COUNTIES = (
    "ALLEGANY_COUNTY_MD",
    "ANNE_ARUNDEL_COUNTY_MD",
    "BALTIMORE_COUNTY_MD",
    "BALTIMORE_CITY_MD",
    "CALVERT_COUNTY_MD",
    "CAROLINE_COUNTY_MD",
    "CARROLL_COUNTY_MD",
    "CECIL_COUNTY_MD",
    "CHARLES_COUNTY_MD",
    "DORCHESTER_COUNTY_MD",
    "FREDERICK_COUNTY_MD",
    "GARRETT_COUNTY_MD",
    "HARFORD_COUNTY_MD",
    "HOWARD_COUNTY_MD",
    "KENT_COUNTY_MD",
    "MONTGOMERY_COUNTY_MD",
    "PRINCE_GEORGE_S_COUNTY_MD",
    "QUEEN_ANNE_S_COUNTY_MD",
    "SOMERSET_COUNTY_MD",
    "ST_MARY_S_COUNTY_MD",
    "TALBOT_COUNTY_MD",
    "WASHINGTON_COUNTY_MD",
    "WICOMICO_COUNTY_MD",
    "WORCESTER_COUNTY_MD",
)
CORRECTED_LIABILITY = {"scenario_081": 8232.900391, "scenario_022": 1968.80542}
FEDERAL = "federal_income_tax_before_refundable_credits"
STATE = "state_income_tax_before_refundable_credits"
_R02 = None


def _r02_system():
    global _R02
    if _R02 is None:
        from policyengine_us import CountryTaxBenefitSystem

        base._system()  # assembles the fix directory
        fix_dir = base._FIX_DIR
        for name in ("r02_ira_219g.py", "r02_ira_219g_v2.py"):
            shutil.copy2(base.AUDIT_0922 / "fixes" / name, fix_dir / name)
        path = fix_dir / "latest_alt_r02_ira_219g.py"
        spec = importlib.util.spec_from_file_location("latest_alt_r02", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["latest_alt_r02"] = module
        spec.loader.exec_module(module)
        _R02 = CountryTaxBenefitSystem(reform=module.reform)
    return _R02


def _sim(
    situation, *, withheld=None, tax_unit=None, people=None, household=None, system=None
):
    from policyengine_us import Simulation

    situation = copy.deepcopy(situation)
    tu = situation["tax_units"]["tax_unit"]
    if withheld is not None:
        tu["state_withheld_income_tax"] = {base.PERIOD: withheld}
    for name, value in (tax_unit or {}).items():
        tu[name] = {base.PERIOD: value}
    for person in situation["people"].values():
        for name, value in (people or {}).items():
            person[name] = {base.PERIOD: value}
    for name, value in (household or {}).items():
        situation["households"]["household"][name] = {base.PERIOD: value}
    return Simulation(tax_benefit_system=system or base._system(), situation=situation)


def _liability(sim) -> float:
    return base._salt_income_tax(sim, "liability")


def _fixed_point(situation, **kwargs):
    sim = _sim(situation, **kwargs)
    withheld = _liability(sim)
    for _ in range(base.MAX_ITERATIONS):
        sim = _sim(situation, withheld=withheld, **kwargs)
        implied = _liability(sim)
        if abs(implied - withheld) < base.CONVERGED:
            return sim, withheld
        withheld = implied
    raise RuntimeError("liability reading did not converge")


def household_variants(job) -> dict:
    from policybench.scenarios import scenario_from_dict

    scenario_json, variables = job
    scenario = scenario_from_dict(json.loads(scenario_json))
    situation = base.build_situation(scenario)
    sid = scenario.id

    def outputs(sim):
        return base._outputs(sim, scenario, variables)

    reference = _sim(situation)
    estimate = base._tax_unit_value(reference, "state_withheld_income_tax")
    payroll = base._tax_unit_value(reference, "employee_state_payroll_tax")
    liability_sim, liability = _fixed_point(situation)
    result = {
        "scenario_id": sid,
        "state": scenario.state,
        "estimate": estimate,
        "liability": liability,
        "employee_state_payroll_tax": payroll,
        "local_sales_tax": base._tax_unit_value(reference, "local_sales_tax"),
        "medicare_part_b_premium": float(
            reference.calculate("medicare_part_b_premium", base.YEAR).sum()
        ),
        "reference": outputs(reference),
        "liability_outputs": outputs(liability_sim),
        "payroll_in_salt": {
            "estimate": outputs(_sim(situation, withheld=estimate + payroll)),
            "liability": outputs(_sim(situation, withheld=liability + payroll)),
        },
        "no_local_sales": {
            "reference": outputs(_sim(situation, tax_unit={"local_sales_tax": 0.0})),
            "zero": outputs(
                _sim(situation, withheld=0.0, tax_unit={"local_sales_tax": 0.0})
            ),
        },
        "no_part_b": {
            "reference": outputs(
                _sim(situation, people={"medicare_part_b_premium": 0.0})
            ),
        },
    }
    if sid in CORRECTED_LIABILITY:
        result["corrected_liability"] = {
            "withheld": CORRECTED_LIABILITY[sid],
            "outputs": outputs(_sim(situation, withheld=CORRECTED_LIABILITY[sid])),
        }
    if sid == "scenario_114":
        no_b = {"medicare_part_b_premium": 0.0}
        sim, withheld = _fixed_point(situation, people=no_b)
        result["no_part_b"]["liability"] = {"withheld": withheld, **outputs(sim)}
        literal = _sim(
            situation, withheld=0.0, tax_unit={"local_sales_tax": 0.0}, people=no_b
        )
        result["no_part_b"]["literal"] = outputs(literal)
        result["no_part_b"]["literal_itemizes"] = base._tax_unit_value(
            literal, "tax_unit_itemizes"
        )
    if scenario.state == "MD":
        counties = {}
        for county in MD_COUNTIES:
            sim, withheld = _fixed_point(situation, household={"county": county})
            counties[county] = {
                "withheld": withheld,
                FEDERAL: outputs(sim)[FEDERAL],
                "reference_federal": outputs(
                    _sim(situation, household={"county": county})
                )[FEDERAL],
            }
        result["md_counties"] = counties
    if sid == "scenario_120":
        system = _r02_system()
        r02_ref = _sim(situation, system=system)
        r02_liability = base._salt_income_tax(r02_ref, "liability")
        result["r02_120"] = {
            "reference": outputs(r02_ref)[FEDERAL],
            "liability": outputs(
                _sim(situation, withheld=r02_liability, system=system)
            )[FEDERAL],
            "zero": outputs(_sim(situation, withheld=0.0, system=system))[FEDERAL],
        }
    return result


def moved(results, key_path) -> list[dict]:
    rows = []
    for r in results:
        node = r
        for key in key_path:
            node = node[key]
        for variable, value in node.items():
            if not isinstance(value, float):
                continue
            ref = r["reference"][variable]
            binary = variable.endswith(base.BINARY_SUFFIXES)
            if (round(value) != round(ref)) if binary else abs(value - ref) > 1.0:
                rows.append(
                    {
                        "scenario_id": r["scenario_id"],
                        "variable": variable,
                        "reference": ref,
                        "value": value,
                        "delta": value - ref,
                    }
                )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    from policybench.scenarios import scenario_from_dict
    from policybench.spec import expand_programs_for_scenario

    meta = json.loads((base.RUN / "reference_outputs.csv.meta.json").read_text())
    reference = pd.read_csv(base.RUN / "reference_outputs.csv")
    indexed = reference.set_index(["scenario_id", "variable"])["value"]
    jobs = []
    for _, row in pd.read_csv(base.RUN / "scenarios.csv").iterrows():
        scenario = scenario_from_dict(json.loads(row["scenario_json"]))
        variables = [
            v
            for v in expand_programs_for_scenario(meta["programs"], scenario)
            if (scenario.id, v) in indexed.index
        ]
        jobs.append((row["scenario_json"], variables))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = sorted(
            pool.map(household_variants, jobs), key=lambda r: r["scenario_id"]
        )

    mismatched = [
        (r["scenario_id"], v)
        for r in results
        for v, value in r["reference"].items()
        if abs(value - float(indexed[(r["scenario_id"], v)])) > 1e-3
    ]
    excluded = {
        (e["scenario_id"], e["variable"])
        for e in json.loads((base.RUN / "reference_exclusions.json").read_text())[
            "exclusions"
        ]
    }
    mismatched = [k for k in mismatched if k not in excluded]
    summary = {
        "scored_reference_mismatches": mismatched,
        "moved": {
            "payroll_in_salt_estimate": moved(results, ["payroll_in_salt", "estimate"]),
            "payroll_in_salt_liability": moved(
                results, ["payroll_in_salt", "liability"]
            ),
            "no_local_sales_reference": moved(results, ["no_local_sales", "reference"]),
            "no_local_sales_zero": moved(results, ["no_local_sales", "zero"]),
            "no_part_b_reference": moved(results, ["no_part_b", "reference"]),
        },
        "households_with_part_b": sorted(
            r["scenario_id"] for r in results if r["medicare_part_b_premium"] > 0
        ),
    }
    for rows in summary["moved"].values():
        for row in rows:
            row["excluded"] = (row["scenario_id"], row["variable"]) in excluded
    Path(args.out).write_text(
        json.dumps({"summary": summary, "households": results}, indent=1) + "\n"
    )
    print(json.dumps(summary, indent=1))
    for r in results:
        for key in ("corrected_liability", "md_counties", "r02_120"):
            if key in r:
                value = r[key]
                if key == "corrected_liability":
                    value = {
                        "withheld": value["withheld"],
                        FEDERAL: value["outputs"][FEDERAL],
                    }
                if key == "md_counties":
                    feds = [c[FEDERAL] for c in value.values()]
                    value = {
                        "min": min(feds),
                        "max": max(feds),
                        "allegany": value["ALLEGANY_COUNTY_MD"][FEDERAL],
                        "reference_range": [
                            min(c["reference_federal"] for c in r[key].values()),
                            max(c["reference_federal"] for c in r[key].values()),
                        ],
                    }
                print(r["scenario_id"], key, json.dumps(value))
        if r["scenario_id"] == "scenario_114":
            print(
                "scenario_114 no_part_b",
                json.dumps(
                    {
                        k: (
                            v
                            if not isinstance(v, dict)
                            else {x: v[x] for x in (FEDERAL, STATE) if x in v}
                        )
                        for k, v in r["no_part_b"].items()
                    }
                ),
            )


if __name__ == "__main__":
    main()
