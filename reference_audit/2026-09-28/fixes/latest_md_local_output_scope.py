"""Candidate (not a law convention): keep Maryland county income tax out of the state output.

PolicyBench defines state_income_tax_before_refundable_credits as "state individual
income tax after nonrefundable credits and before refundable credits, excluding local
income and payroll taxes" (policybench/benchmark_specs.json, output prompt). Its
separate local_income_tax output names only NYC, Philadelphia, Kansas City and
St. Louis.

policyengine-us 2.15.17 adds md_local_income_tax_before_refundable_credits (Maryland
county income tax net of the local EITC and local poverty credit) to the list behind
state_income_tax_before_refundable_credits (parameters/gov/states/household/
state_income_tax_before_refundable_credits.yaml; upstream PolicyEngine/policyengine-us
#8888, commit 6b0bca0b9f, 2026-07-05). The county is not a benchmark input; with the
default UNKNOWN county 2.15.17 falls back to Allegany County's 3.03% rate
(variables/gov/states/md/tax/income/local/md_applicable_local_tax_rate.py). On 1.755.4
the list had no local entry, so the board's Maryland state amounts are state-only.

This module removes that one entry from the list, so the scored output again matches
its definition. It leaves the county tax in md_withheld_income_tax, i.e. in the federal
SALT deduction (local income taxes are deductible, IRC 164(a)(3)); see the port report
for scenario_078's federal output. Only the list changes; no formula or amount changes.
"""

from policyengine_core.reforms import Reform

FIX_ID = "latest_md_local_output_scope"
DESCRIPTION = "Exclude Maryland county income tax from the state income tax output (output definition)"
LOCAL = "md_local_income_tax_before_refundable_credits"


def _modify(parameters):
    param = parameters.gov.states.household.state_income_tax_before_refundable_credits
    current = list(param("2026-01-01"))
    if LOCAL in current:
        current.remove(LOCAL)
        param.update(period="year:2015-01-01:20", value=current)
    assert LOCAL not in param("2026-01-01")
    assert "md_income_tax_before_refundable_credits" in param("2026-01-01")
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_modify)
