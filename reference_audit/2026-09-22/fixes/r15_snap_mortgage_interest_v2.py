"""r15 v2: alternate SNAP shelter reading, with tax-unit-local input fallback.

Classification: unlisted_input, not a proved engine-law defect. The benchmark
prompts list mortgage interest but do not explicitly state that the encumbered
home is the SNAP household's occupied shelter. This module implements the
alternative reading that first-home interest (or person interest where the
tax unit has no populated interest structure) belongs to the occupied home.
It does not establish that reading as the unique interpretation of the prompt.

7 CFR 273.9(d)(6)(ii)(A) allows continuing mortgage charges, including interest,
for occupied shelter. Paragraph (D) also permits certain temporarily vacant
homes; first/second-home labels alone do not resolve those occupancy facts.
https://www.ecfr.gov/current/title-7/subtitle-B/chapter-II/subchapter-C/part-273/subpart-D/section-273.9
7 USC 2014(e)(6)(A)-(B) gives the 50% excess-shelter test and the cap exception
for households with an elderly or disabled member.
https://uscode.house.gov/view.xhtml?req=(title:7%20section:2014%20edition:prelim)

As in v1, the listed interest is a lower bound of total payments; unlisted
principal is not invented. The SNAP-only increment is max(interest minus
mortgage_payments, 0), preventing double counting of the reported payment.
The first-versus-person fallback now occurs per tax unit before SPM-unit
aggregation. The remainder of the original SNAP shelter formula is unchanged.
No statutory dollar parameter is introduced. All 100 bundle scenarios have
one tax unit, so this correction should leave the benchmark sweep unchanged.
"""

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *

FIX_ID = "r15_snap_mortgage_interest_v2"
DESCRIPTION = (
    "Alternative occupied-home reading of listed mortgage interest for SNAP; "
    "choose first-home versus person inputs per tax unit before aggregation."
)


class snap_mortgage_interest_shelter_cost(Variable):
    value_type = float
    entity = SPMUnit
    label = "SNAP shelter cost from listed mortgage interest beyond mortgage_payments"
    unit = USD
    definition_period = YEAR
    reference = (
        "https://www.ecfr.gov/current/title-7/subtitle-B/chapter-II/subchapter-C/part-273/subpart-D/section-273.9#p-273.9(d)(6)(ii)(A)",
    )

    def formula(spm_unit, period, parameters):
        person = spm_unit.members
        head = person("is_tax_unit_head", period)
        first = person.tax_unit("first_home_mortgage_interest", period)
        second = person.tax_unit("second_home_mortgage_interest", period)
        # Choose the input representation separately for each tax unit.
        # A populated structure for one tax unit must not suppress another
        # tax unit's person-only mortgage interest within the same SPM unit.
        interest_by_person = where(
            first + second > 0,
            head * first,
            person("home_mortgage_interest", period),
        )
        occupied_home_interest = spm_unit.sum(interest_by_person)
        mortgage_payments = spm_unit("mortgage_payments", period)
        return max_(occupied_home_interest - mortgage_payments, 0)


class snap_excess_shelter_expense_deduction(Variable):
    value_type = float
    entity = SPMUnit
    definition_period = MONTH
    documentation = (
        "Excess shelter expense deduction for calculating SNAP benefit amount"
    )
    label = "SNAP shelter deduction"
    reference = ("United States Code, Title 7, Section 2014(e)(6)",)
    unit = USD

    def formula(spm_unit, period, parameters):
        # Identical to policyengine-us 1.755.4 except for the mortgage-interest
        # term added to housing_cost.
        p = parameters(period).gov.usda.snap.income.deductions.excess_shelter_expense
        net_income_pre_shelter = spm_unit("snap_net_income_pre_shelter", period)
        subtracted_income = p.income_share_disregard * net_income_pre_shelter
        mortgage_interest = (
            spm_unit("snap_mortgage_interest_shelter_cost", period.this_year)
            / MONTHS_IN_YEAR
        )
        housing_cost = (
            add(spm_unit, period, ["snap_utility_allowance", "housing_cost"])
            + mortgage_interest
        )
        uncapped_ded = max_(housing_cost - subtracted_income, 0)
        state_group = spm_unit.household("snap_region_str", period)
        ded_cap = p.cap[state_group]
        capped_ded = min_(uncapped_ded, ded_cap)
        has_elderly_disabled = spm_unit("has_usda_elderly_disabled", period)
        non_homeless_shelter_deduction = where(
            has_elderly_disabled, uncapped_ded, capped_ded
        )
        state = spm_unit.household("state_code_str", period)
        homeless_deduction = p.homeless.deduction * p.homeless.available[state]
        return where(
            spm_unit.household("is_homeless", period)
            & (housing_cost > 0)
            & (homeless_deduction > non_homeless_shelter_deduction),
            homeless_deduction,
            non_homeless_shelter_deduction,
        )


class reform(Reform):
    def apply(self):
        self.update_variable(snap_mortgage_interest_shelter_cost)  # adds it; safe on re-apply
        self.update_variable(snap_excess_shelter_expense_deduction)
