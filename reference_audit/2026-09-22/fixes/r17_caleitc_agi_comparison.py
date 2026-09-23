"""CalEITC: the second credit lookup at adjusted gross income (FTB 3514 worksheet lines 3-5).

California's earned income tax credit follows the federal structure: when adjusted gross
income exceeds the income at which the credit starts to phase out, the filer looks the
credit up a second time at AGI and takes the smaller of the two amounts (Cal. R&TC
17052(c); FTB 3514 instructions, CalEITC worksheet lines 3-5). policyengine-us 1.755.4's
ca_eitc phases out on filer_adjusted_earnings only; ca_eitc_eligible tests AGI solely
against the credit's maximum income. A filer whose AGI exceeds earnings in the phase-out
range (for example, one with a taxable retirement distribution) gets too large a credit.

This module keeps the 1.755.4 schedule and adds the AGI lookup, for 2026 only.
Env R17_AGI = "federal" (default: adjusted_gross_income) or "ca" (ca_agi) picks the AGI.
"""

import os

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *

FIX_ID = "r17_caleitc_agi_comparison"
AGI_VARIABLE = "ca_agi" if os.environ.get("R17_AGI") == "ca" else "adjusted_gross_income"


def _credit(income, child_count, p):
    phase_in_rate = p.phase_in.rate.calc(child_count) * p.adjustment.factor
    phase_in_max_income = p.earned_income_amount.calc(child_count)
    phased_in_amount = min_(income, phase_in_max_income) * phase_in_rate
    phase_out_min_income = p.phase_out.start.calc(child_count)
    phase_out_rate = p.phase_out.rate.calc(child_count) * p.adjustment.factor
    second_phase_out_start_eitc = p.phase_out.final.start.calc(child_count)
    maximum_eitc = phase_in_max_income * phase_in_rate
    earnings_range_of_first_phase_out = (
        maximum_eitc - second_phase_out_start_eitc
    ) / phase_out_rate
    second_phase_out_start = phase_out_min_income + earnings_range_of_first_phase_out
    second_phase_out_end = p.phase_out.final.end
    phase_out_income = min_(
        max_(0, income - phase_out_min_income), earnings_range_of_first_phase_out
    )
    amount_after_first_phase_out = phased_in_amount - phase_out_income * phase_out_rate
    share = min_(
        (income - second_phase_out_start) / (second_phase_out_end - second_phase_out_start),
        1,
    )
    return where(
        income > second_phase_out_start,
        amount_after_first_phase_out * (1 - share),
        amount_after_first_phase_out,
    )


class ca_eitc(Variable):
    value_type = float
    entity = TaxUnit
    label = "CalEITC"
    unit = USD
    definition_period = YEAR
    defined_for = "ca_eitc_eligible"

    def formula(tax_unit, period, parameters):
        p = parameters(period).gov.states.ca.tax.income.credits.earned_income
        earned_income = tax_unit("filer_adjusted_earnings", period)
        child_count = tax_unit("eitc_child_count", period)
        by_earnings = _credit(earned_income, child_count, p)
        if period.start.year != 2026:
            return by_earnings
        agi = tax_unit(AGI_VARIABLE, period)
        by_agi = _credit(max_(agi, 0), child_count, p)
        return where(
            agi > p.phase_out.start.calc(child_count),
            min_(by_earnings, by_agi),
            by_earnings,
        )


class reform(Reform):
    def apply(self):
        self.update_variable(ca_eitc)
