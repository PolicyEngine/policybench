"""Compute scenario_023 head_medicaid_eligible under both readings of "is disabled".

The prompt states only that the California head is disabled. Her MAGI is above
the 138% adult limit, so Medi-Cal is open to her only through a disability
pathway, here the 250% Working Disabled Program. That program requires the
federal (SSA) definition of disability (42 CFR 435.540(a); the LA DPSS 250% WDP
policy the engine cites), which is policyengine-us's meets_ssi_disability_criteria,
the input that already excludes this household's SNAP. 2.15.17's
ca_wdp_disability_eligible reads the broad is_disabled flag instead.

The script runs the reference system (fixes/latest_final.py on policyengine-us
2.15.17) and the same system with the WDP disability test following the SSA
definition, each with the stated facts, reading A (the head does not meet the
SSI/SSA disability criteria) and reading B (she does). It asserts that the
reference system reproduces the committed reference, and writes
verification/probe_023_medicaid.json.

latest_c_irs_sales_tax_2025.py reads r19_irs_sales_tax_2025.json beside itself,
and that table is committed in ../2026-09-22/fixes, so the script loads the fix
modules from a temporary copy of fixes/ with the table added, as the builder's
docstring does. Run from the checkout:

  OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD .venv/bin/python \\
    reference_audit/2026-09-28/scripts/probe_023_medicaid.py
"""

from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent
ROOT = AUDIT.parents[1]
RUN = ROOT / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
OUT = AUDIT / "verification" / "probe_023_medicaid.json"
ENGINE = "2.15.17"
YEAR = 2026
SCENARIO = "scenario_023"
OUTPUT = "head_medicaid_eligible"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    if version("policyengine-us") != ENGINE:
        raise SystemExit(f"need policyengine-us {ENGINE}, have {version('policyengine-us')}")

    from policyengine_core.reforms import Reform
    from policyengine_us import CountryTaxBenefitSystem, Simulation
    from policyengine_us.model_api import YEAR as PERIOD_YEAR
    from policyengine_us.model_api import Person, StateCode, Variable

    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output
    from policybench.scenarios import scenario_from_dict

    sweep = _load("probe_sweep", HERE / "sweep.py")  # the references' household builder

    with tempfile.TemporaryDirectory(prefix="probe023-") as scratch:
        fixes = Path(scratch)
        for module in (AUDIT / "fixes").glob("*.py"):
            shutil.copyfile(module, fixes / module.name)
        shutil.copyfile(
            AUDIT.parent / "2026-09-22" / "fixes" / "r19_irs_sales_tax_2025.json",
            fixes / "r19_irs_sales_tax_2025.json",
        )
        latest_final = _load("probe_latest_final", fixes / "latest_final.py")

        class ca_wdp_disability_eligible(Variable):
            value_type = bool
            entity = Person
            label = "California 250% WDP disability eligible (SSA definition)"
            definition_period = PERIOD_YEAR
            defined_for = StateCode.CA

            def formula(person, period, parameters):
                # 2.15.17 reads is_disabled here; the law reads the SSA definition.
                return (
                    person("meets_ssi_disability_criteria", period)
                    | person("is_blind", period)
                    | (person("social_security_disability", period) > 0)
                )

        class wdp_ssa_definition(Reform):
            def apply(self):
                latest_final.reform.apply(self)
                self.update_variable(ca_wdp_disability_eligible)

        systems = {
            "latest_final": CountryTaxBenefitSystem(reform=latest_final.reform),
            "latest_final_wdp_ssa_definition": CountryTaxBenefitSystem(
                reform=wdp_ssa_definition
            ),
        }

    with (RUN / "scenarios.csv").open(newline="") as source:
        csv.field_size_limit(sys.maxsize)
        row = next(r for r in csv.DictReader(source) if r["scenario_id"] == SCENARIO)
    scenario = scenario_from_dict(json.loads(row["scenario_json"]))
    situation = sweep.build_situation(scenario)
    readings = {
        "stated_facts": None,
        "reading_a": False,  # does not meet the SSI/SSA disability criteria
        "reading_b": True,  # meets them
    }
    pe_variable = _pe_variable_for_output(OUTPUT, "us")
    results = {}
    for system_name, system in systems.items():
        for reading, criteria in readings.items():
            household = copy.deepcopy(situation)
            if criteria is not None:
                for person in household["people"].values():
                    person["meets_ssi_disability_criteria"] = {str(YEAR): criteria}
            sim = Simulation(tax_benefit_system=system, situation=household)
            value = float(
                _extract_person_value(sim.calculate(pe_variable, YEAR), scenario, OUTPUT)
            )
            head = 0  # the household's only person
            results[f"{system_name}/{reading}"] = {
                OUTPUT: value,
                "medicaid_category": str(
                    sim.calculate("medicaid_category", YEAR).decode_to_str()[head]
                ),
                "ca_wdp_disability_eligible": bool(
                    sim.calculate("ca_wdp_disability_eligible", YEAR)[head]
                ),
                "ca_wdp_eligible": bool(sim.calculate("ca_wdp_eligible", YEAR)[head]),
                "medicaid_income_level": round(
                    float(sim.calculate("medicaid_income_level", YEAR)[head]), 4
                ),
                "ssi": float(sim.calculate("ssi", YEAR)[head]),
            }

    with (RUN / "reference_outputs.csv").open(newline="") as source:
        reference = next(
            float(r["value"])
            for r in csv.DictReader(source)
            if (r["scenario_id"], r["variable"]) == (SCENARIO, OUTPUT)
        )
    stated = results["latest_final/stated_facts"][OUTPUT]
    if stated != reference:
        raise SystemExit(f"reference system gives {stated}, committed {reference}")

    record = {
        "scenario_id": SCENARIO,
        "variable": OUTPUT,
        "pe_variable": pe_variable,
        "engine_version": f"policyengine-us {ENGINE}",
        "committed_reference": reference,
        "fix_module": {
            "module": "fixes/latest_final.py",
            "sha256": _sha256(AUDIT / "fixes" / "latest_final.py"),
        },
        "probe_sha256": _sha256(Path(__file__)),
        "readings": {
            "stated_facts": "the scenario as built, meets_ssi_disability_criteria unset",
            "reading_a": "meets_ssi_disability_criteria false: the head does not meet "
            "the SSI/SSA disability criteria",
            "reading_b": "meets_ssi_disability_criteria true: the head meets them",
        },
        "systems": {
            "latest_final": "the reference system: policyengine-us 2.15.17 with "
            "fixes/latest_final.py; ca_wdp_disability_eligible reads is_disabled",
            "latest_final_wdp_ssa_definition": "the same with "
            "ca_wdp_disability_eligible reading meets_ssi_disability_criteria "
            "(the SSA definition, 42 CFR 435.540(a)) in place of is_disabled",
        },
        "results": results,
    }
    OUT.write_text(json.dumps(record, indent=1) + "\n")
    for key, value in results.items():
        print(key, json.dumps(value))


if __name__ == "__main__":
    main()
