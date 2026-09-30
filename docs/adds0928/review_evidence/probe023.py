import json, copy, importlib.util, sys
from pathlib import Path
import pandas as pd
WT = Path("/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2")
from policybench.ground_truth import _extract_person_value, _pe_variable_for_output
from policybench.scenarios import scenario_from_dict
from policyengine_us import CountryTaxBenefitSystem, Simulation
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *

spec = importlib.util.spec_from_file_location("lf", Path("/private/tmp/claude-501/-Users-maxghenis-Library-Application-Support-Claude-scratch-workspaces-ee3763f4-e7ea-4177-bcaf-1362266768c1-4457aa9d-2dc0-4bcf-a128-e50adae6be25-scratch-2026-09-22-c3da5e/3dd3d124-a1eb-44ed-ac89-ce3df9700101/scratchpad/fixes/latest_final.py"))
lf = importlib.util.module_from_spec(spec); sys.modules["lf"]=lf; spec.loader.exec_module(lf)

sc = pd.read_csv(WT/"paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/scenarios.csv")
row = sc[sc.scenario_id=="scenario_023"].iloc[0]
scenario = scenario_from_dict(json.loads(row["scenario_json"]))
base = scenario.to_pe_household()

class wdp_ssa(Variable):
    pass

class ca_wdp_disability_eligible(Variable):
    value_type = bool
    entity = Person
    label = "WDP disability per SSA definition (pre-SGA)"
    definition_period = YEAR
    defined_for = StateCode.CA
    def formula(person, period, parameters):
        return person("meets_ssi_disability_criteria", period) | person("is_blind", period) | (person("social_security_disability", period) > 0)

class law_reform(Reform):
    def apply(self):
        lf.reform.apply(self)
        self.update_variable(ca_wdp_disability_eligible)

def run(label, system, ssi_crit):
    sit = copy.deepcopy(base)
    for pid, p in sit["people"].items():
        p["meets_ssi_disability_criteria"] = {"2026": ssi_crit}
    sim = Simulation(tax_benefit_system=system, situation=sit)
    pe_var = _pe_variable_for_output("head_medicaid_eligible", "us")
    v = float(_extract_person_value(sim.calculate(pe_var, 2026), scenario, "head_medicaid_eligible"))
    cat = sim.calculate("medicaid_category", 2026)
    print(label, "pe_var=", pe_var, "head_medicaid_eligible=", v, "category=", list(cat), "ca_wdp_eligible=", list(sim.calculate("ca_wdp_eligible", 2026)))

ref_sys = CountryTaxBenefitSystem(reform=lf.reform)
law_sys = CountryTaxBenefitSystem(reform=law_reform)
run("latest_final, readingA (ssi_crit False):", ref_sys, False)
run("latest_final, readingB (ssi_crit True): ", ref_sys, True)
run("WDP-per-SSA, readingA:", law_sys, False)
run("WDP-per-SSA, readingB:", law_sys, True)
