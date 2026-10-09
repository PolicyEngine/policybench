"""r15 v2: alternate SNAP shelter reading of listed mortgage interest.

Classification: unlisted_input, not a proved engine-law defect. The benchmark
prompts list mortgage interest but do not explicitly state that the encumbered
home is the SNAP household's occupied shelter. This module implements the
alternative reading that the listed home mortgage interest (the person-level
home_mortgage_interest input) belongs to the occupied home.
It does not establish that reading as the unique interpretation of the prompt.

Revised 2026-10-09. The module first read the tax-unit
first_home_mortgage_interest and second_home_mortgage_interest inputs and, for
a tax unit that listed them, counted first-home interest only. policyengine-us
#9605 deletes those inputs, so it now reads only home_mortgage_interest, which
every benchmark household that lists the tax-unit inputs also lists, with the
same total. The two readings differ only where a second home is listed:
scenario_046 and scenario_120, whose person-level total includes the second
loan's 1,358.97 and 768.28. On policyengine-us 1.755.4 the sweep of all 1,984
outputs is byte-identical under both readings and equal to this module's
recorded sweep (triage/sweep/out/r15_snap_mortgage_interest_v2.csv, sha256
63c9120f...),
with situations built as before policybench stopped passing the tax-unit
inputs. 1.755.4 takes the interest amount only from those inputs, so the
current builder cannot reproduce that sweep on 1.755.4.

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
The remainder of the original SNAP shelter formula is unchanged.
No statutory dollar parameter is introduced.
"""

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *

FIX_ID = "r15_snap_mortgage_interest_v2"
DESCRIPTION = (
    "Alternative occupied-home reading of listed mortgage interest for SNAP, "
    "from the person-level home_mortgage_interest input."
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
        occupied_home_interest = add(spm_unit, period, ["home_mortgage_interest"])
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
