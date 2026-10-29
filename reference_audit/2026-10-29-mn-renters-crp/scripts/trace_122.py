"""Scenario 122's Minnesota renter's credit, traced with and without a qualifying CRP.

Builds the household as sweep_crp.py does (the 2026-10-22 builder's harness and
latest_final conventions) on the installed policyengine-us, then reads the
renter's credit's inputs and result twice: as built, where
mn_renters_credit_qualifying_crp keeps its default, and with it set to true.
It also reads the 2026 max_credit schedule's last threshold with a positive
credit.

Usage: python trace_122.py OUT_JSON
"""

import copy
import datetime
import importlib.util
import io
import json
import sys
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BUILDER_PATH = ROOT / "reference_audit/2026-10-22-engine-upgrade/scripts/build_references_upgrade.py"
SCENARIO = "scenario_122"
VARIABLES = (
    "mn_renters_credit_qualifying_crp",
    "mn_renters_credit_household_income",
    "mn_rent_constituting_property_taxes",
    "mn_renters_credit_property_tax_exempt",
    "mn_renters_credit_eligible",
    "mn_renters_credit",
    "mn_refundable_credits",
)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    out_path = Path(sys.argv[1])
    sys.path.insert(0, str(ROOT))
    builder = load("trace_builder", BUILDER_PATH)
    import pandas as pd
    from policyengine_us import CountryTaxBenefitSystem, Simulation

    from policybench.scenarios import scenario_from_dict

    base = builder.load_base()
    builder.fix_module_pins(base.meta, builder.FIXES)
    harness = builder.load_module("trace_harness", builder.HARNESS)
    final = builder.load_module(f"trace_{builder.FIX_ENTRY}", builder.FIXES / f"{builder.FIX_ENTRY}.py")
    scenarios = pd.read_csv(io.StringIO(base.scenarios_csv)).set_index("scenario_id")
    scenario = scenario_from_dict(json.loads(scenarios.loc[SCENARIO, "scenario_json"]))
    system = CountryTaxBenefitSystem(reform=final.reform)
    built = harness.build_situation(scenario)

    def trace(situation: dict) -> dict:
        sim = Simulation(tax_benefit_system=system, situation=situation)
        values = {}
        for name in VARIABLES:
            value = sim.calculate(name, builder.YEAR)[0]
            values[name] = bool(value) if name in ("mn_renters_credit_qualifying_crp", "mn_renters_credit_property_tax_exempt", "mn_renters_credit_eligible") else round(float(value), 2)
        return values

    with_crp = copy.deepcopy(built)
    for unit in with_crp["tax_units"].values():
        unit["mn_renters_credit_qualifying_crp"] = {str(builder.YEAR): True}
    schedule = system.parameters(f"{builder.YEAR}-01-01").gov.states.mn.tax.income.credits.renters.max_credit
    brackets = [(float(t), float(a)) for t, a in zip(schedule.thresholds, schedule.amounts)]
    positive = [t for t, a in brackets if a > 0]
    doc = {
        "scenario": SCENARIO,
        "engine": f"policyengine-us {version('policyengine-us')}",
        "policyengine_core": version("policyengine-core"),
        "computed_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "conventions": f"{builder.FIXES_REL}/{builder.FIX_ENTRY}.py",
        "max_credit_last_positive_threshold": max(positive),
        "max_credit_first_zero_threshold": min(t for t, a in brackets if a == 0 and t > max(positive)),
        "as_built": trace(built),
        "with_qualifying_crp": trace(with_crp),
    }
    out_path.write_text(json.dumps(doc, indent=2) + "\n")
    print(json.dumps(doc, indent=1))


if __name__ == "__main__":
    main()
