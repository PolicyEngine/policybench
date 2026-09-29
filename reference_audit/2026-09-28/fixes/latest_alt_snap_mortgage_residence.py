"""Alternative reading for the excluded output scenario_118 snap, on policyengine-us 2.15.17
plus every pre-freeze-law convention (latest_conventions.py).

NOT a reference fix and NOT a hold convention. The output stays excluded: its root cause
(triage/root_causes.json, r15_snap_mortgage_interest) is an unlisted input, "whether the
listed home mortgage interest is on the home the SNAP household occupies". This module
only recomputes the exclusion record's alternative_value on the new stack, the way
r15_snap_mortgage_interest_v2.py (written for 1.755.4) did on the 22c board stack.

Alternative reading (as in r15 v2): the listed mortgage interest is on the occupied home,
so it is a continuing mortgage charge counted as a shelter cost (7 CFR 273.9(d)(6)(ii)(A):
"Continuing charges for the shelter occupied by the household, ... including mortgage
payments ... and interest on such payments"). Unlisted principal is not invented; only
max(interest - mortgage_payments, 0) is added, so a reported payment is never counted
twice. First-home versus person interest is chosen per tax unit, as in r15 v2.

Port to 2.15.17. 2.15.17's snap_excess_shelter_expense_deduction differs from 1.755.4 in
two places (diff of the installed files): actual housing costs are multiplied by
snap_expense_counted_share (7 CFR 273.11(c)(2)(iii)) with the utility allowance added
unprorated, and the uncapped branch reads has_snap_elderly_disabled_member instead of
has_usda_elderly_disabled. This module copies the 2.15.17 formula verbatim and adds the
mortgage-interest term to the prorated actual housing costs. housing_cost and
mortgage_payments are identical in both versions and still exclude mortgage interest.
"""

import importlib.util
import sys
from pathlib import Path

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *

FIX_ID = "latest_alt_snap_mortgage_residence"
DESCRIPTION = (
    "latest_conventions plus the r15 alternative reading (listed mortgage interest is on the "
    "occupied home, a SNAP shelter cost), ported to 2.15.17; recomputes an alternative_value, "
    "not a reference"
)


def _load(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(f"alt_mortgage_part_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CONVENTIONS = _load("latest_conventions").reform


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
        # policyengine-us 2.15.17's formula, except for the mortgage-interest term.
        p = parameters(period).gov.usda.snap.income.deductions.excess_shelter_expense
        net_income_pre_shelter = spm_unit("snap_net_income_pre_shelter", period)
        subtracted_income = p.income_share_disregard * net_income_pre_shelter
        expense_share = spm_unit("snap_expense_counted_share", period)
        utility_allowance = spm_unit("snap_utility_allowance", period)
        mortgage_interest = (
            spm_unit("snap_mortgage_interest_shelter_cost", period.this_year)
            / MONTHS_IN_YEAR
        )
        housing_cost = (
            expense_share
            * (add(spm_unit, period, ["housing_cost"]) + mortgage_interest)
            + utility_allowance
        )
        uncapped_ded = max_(housing_cost - subtracted_income, 0)
        state_group = spm_unit.household("snap_region_str", period)
        ded_cap = p.cap[state_group]
        capped_ded = min_(uncapped_ded, ded_cap)
        has_elderly_disabled = spm_unit("has_snap_elderly_disabled_member", period)
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


class alternative_reading(Reform):
    """The r15 alternative reading alone (no conventions)."""

    def apply(self):
        self.update_variable(snap_mortgage_interest_shelter_cost)
        self.update_variable(snap_excess_shelter_expense_deduction)


class reform(Reform):
    def apply(self):
        CONVENTIONS.apply(self)
        alternative_reading.apply(self)
