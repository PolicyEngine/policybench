"""r01 verification correction: restrict the deduction, preserve contributions.

The original r01 zeros traditional_ira_contributions for a dependent even when
that person has compensation and can lawfully contribute under IRC 219(a)/(b).
The restriction belongs to the parent's return, not to that contribution.

Reuse the reviewed original compensation and spousal calculation, but retain
PolicyEngine's unmasked underlying contribution variable. A separate
traditional_ira_deduction represents the head's and joint spouse's deduction on
this tax unit. Replace the IRA item in the federal ALD list so all its consumers
(AGI, person AGI, section 86 MAGI, student-loan MAGI and Medicaid AGI) use that
return-level restriction consistently. Preserve MA disallowance and MS federal
conformity by replacing the deduction item in those lists too.

The new compensation cap can fall below $1. Replace the existing scale
denominator floor of $1 with a zero-only guard, avoiding over-reduction of
positive requested contributions below $1.

All activation and parameter substitutions are confined to calendar year 2026.
The original 219(g) phase-out and Roth income-phase-out omissions stay outside
this root cause; r02 can overwrite traditional_ira_deduction when composed.

Authorities checked in verification:
- https://www.law.cornell.edu/uscode/text/26/219 (a), (b), (c), (f)
- https://www.law.cornell.edu/uscode/text/26/408A (c)(2)
- https://www.irs.gov/publications/p590a (compensation and spousal contribution)
- https://www.irs.gov/pub/irs-drop/n-25-67.pdf (p. 4: $7,500 and $1,100)
- https://malegislature.gov/Laws/GeneralLaws/PartI/TitleIX/Chapter62/Section2
  (d)(1)(F): Massachusetts excludes the IRC 219 deduction.
- https://www.dor.ms.gov/sites/default/files/tax-forms/individual/80100251%202.pdf
  (line 50): Mississippi IRA adjustment follows federal deductibility.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from policyengine_core.periods import period as make_period
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *

_spec = spec_from_file_location("r01_verified_original", Path(__file__).with_name("r01_ira_compensation.py"))
_original = module_from_spec(_spec)
_spec.loader.exec_module(_original)

FIX_ID = "r01_ira_compensation_v2"
DESCRIPTION = "2026 r01 compensation/spousal/dollar limits, with head/joint-spouse-only IRA deduction separated from actual contributions."
OLD = "traditional_ira_contributions"
NEW = "traditional_ira_deduction"
YEAR_2026 = make_period("year:2026-01-01:1")
_compensation_limit = _original._make_ira_contribution_limit(True)


class ira_contribution_limit(Variable):
    value_type = float
    entity = Person
    label = "IRA contribution limit (r01 verification)"
    unit = USD
    definition_period = YEAR
    reference = "https://www.law.cornell.edu/uscode/text/26/219"

    def formula(person, period, parameters):
        if period.start.year != 2026:
            return _original._dollar_limit(person, period, parameters)
        return _compensation_limit.formula(person, period, parameters)


class ira_contribution_scale(Variable):
    value_type = float
    entity = Person
    label = "IRA contribution scale with a zero-only denominator guard"
    definition_period = YEAR
    reference = "https://www.law.cornell.edu/uscode/text/26/219#b_1"

    def formula(person, period, parameters):
        desired = add(person, period, [OLD + "_desired", "roth_ira_contributions_desired"])
        denominator = max_(desired, 1) if period.start.year != 2026 else where(desired > 0, desired, 1)
        return min_(person("ira_contribution_limit", period) / denominator, 1)


class traditional_ira_deduction(Variable):
    value_type = float
    entity = Person
    label = "Traditional IRA deduction on this tax unit (before section 219(g))"
    unit = USD
    definition_period = YEAR
    reference = "https://www.law.cornell.edu/uscode/text/26/219#a"

    def formula(person, period, parameters):
        contributions = person(OLD, period)
        if period.start.year != 2026:
            return contributions
        claimant = person("is_tax_unit_head", period) | (
            person("is_tax_unit_spouse", period)
            & person.tax_unit("tax_unit_is_joint", period)
        )
        return contributions * claimant


def modify_parameters(parameters):
    _original._set_2026_dollar_limits(parameters)
    # Explicit period updates restore the original list in 2027.
    for node in (
        parameters.gov.irs.ald.deductions,
        parameters.gov.states.ma.tax.income.ald.disallowed,
        parameters.gov.states.ms.tax.income.adjustments.adjustments,
    ):
        values = [NEW if value == OLD else value for value in node("2026-01-01")]
        node.update(period=YEAR_2026, value=values)
    return parameters


class reform(Reform):
    def apply(self):
        self.update_variable(_original.ira_compensation)
        self.update_variable(ira_contribution_limit)
        self.update_variable(ira_contribution_scale)
        self.update_variable(traditional_ira_deduction)
        self.modify_parameters(modify_parameters)
