"""2026-only NJ worker UI/WF/SWF repair, independently verified.

NJDOL 2026 worker UI 0.003825, WF/SWF 0.000425, wage base $44,800:
https://www.nj.gov/labor/ea/employer-services/rate-info/
UI coverage and withholding: N.J.S.A. 43:21-7(d)(1)(D)-(F).
https://www.nj.gov/labor/myunemployment/assets/pdfs/UI_statute.pdf

Retains the original fix's covered nongovernmental-employer assumption, since
the input model has no governmental-reimbursable employer indicator. Such
workers instead have UI rate 0.000825. Does not alter employer contributions.
Unlike v1, this sandbox repair does not apply a 2026 base to later years or
invent historical zero contributions. Only benchmark tax year 2026 changes.
"""

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *

FIX_ID = "r05_nj_worker_ui_v2"
DESCRIPTION = "Add covered NJ workers' UI and WF/SWF contributions for 2026 only."


class nj_employee_unemployment_taxable_wages(Variable):
    value_type = float
    entity = Person
    label = "New Jersey worker UI and WF/SWF taxable wages (2026 repair)"
    definition_period = YEAR
    unit = USD
    defined_for = StateCode.NJ

    def formula(person, period, parameters):
        if period.start.year != 2026:
            return 0
        return min_(max_(0, person("employment_income", period)), 44_800)


class nj_employee_unemployment_insurance_contribution(Variable):
    value_type = float
    entity = Person
    label = "New Jersey worker unemployment insurance contribution (2026 repair)"
    definition_period = YEAR
    unit = USD
    defined_for = StateCode.NJ

    def formula(person, period, parameters):
        return 0.003825 * person("nj_employee_unemployment_taxable_wages", period)


class nj_employee_workforce_fund_contribution(Variable):
    value_type = float
    entity = Person
    label = "New Jersey worker WF/SWF contribution (2026 repair)"
    definition_period = YEAR
    unit = USD
    defined_for = StateCode.NJ

    def formula(person, period, parameters):
        return 0.000425 * person("nj_employee_unemployment_taxable_wages", period)


class nj_employee_state_payroll_tax(Variable):
    value_type = float
    entity = Person
    label = "New Jersey employee state payroll tax"
    definition_period = YEAR
    unit = USD
    defined_for = StateCode.NJ
    adds = [
        "nj_employee_temporary_disability_insurance_contribution",
        "nj_employee_family_leave_insurance_contribution",
        "nj_employee_unemployment_insurance_contribution",
        "nj_employee_workforce_fund_contribution",
    ]


class reform(Reform):
    def apply(self):
        self.update_variable(nj_employee_unemployment_taxable_wages)
        self.update_variable(nj_employee_unemployment_insurance_contribution)
        self.update_variable(nj_employee_workforce_fund_contribution)
        self.update_variable(nj_employee_state_payroll_tax)
