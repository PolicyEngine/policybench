"""2026 sensitivity: read adult tax dependents as children of their claimant.

This is an alternative interpretation of an unlisted relationship, not a rule
that every adult dependent is a child. 42 CFR 435.603(b), (d), and (f)(2)
include a claimed natural/adopted/step child in the claimant's MAGI household
without an age limit. Section (f)(2)(i) instead sends other dependents to the
non-filer rules. The frozen prompts do not distinguish these relationships.

Only the Medicaid relationship predicate changes. Ages, SSI disability
criteria, income definitions, and all unrelated formulas remain as encoded.
The original formula applies before and after calendar 2026.

Primary source (2025 edition, printed before the reference freeze):
https://www.govinfo.gov/content/pkg/CFR-2025-title42-vol4/pdf/CFR-2025-title42-vol4-sec435-603.pdf
"""

from policyengine_core.reforms import Reform
from policyengine_us.variables.gov.hhs.medicaid.income.medicaid_claimed_by_parent_in_tax_unit import (
    medicaid_claimed_by_parent_in_tax_unit as original_relationship,
)

FIX_ID = "r067_adult_dependent_relationship"
DESCRIPTION = (
    "For 2026 only, interpret adult tax dependents as natural/adopted/step "
    "children of their claimant for Medicaid MAGI household construction."
)


class medicaid_claimed_by_parent_in_tax_unit(original_relationship):
    def formula_2026_01_01(person, period, parameters):
        encoded = original_relationship.formula(person, period, parameters)
        adult_dependent = person("is_tax_unit_dependent", period) & (
            person("age", period) >= 18
        )
        return encoded | adult_dependent

    def formula_2027_01_01(person, period, parameters):
        return original_relationship.formula(person, period, parameters)


class reform(Reform):
    def apply(self):
        self.update_variable(medicaid_claimed_by_parent_in_tax_unit)
