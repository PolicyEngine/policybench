"""2026 sensitivity: adult tax dependents are not children of their claimant.

This is the reverse bound of the omitted adult-dependent relationship, not a
universal adult-dependent rule. 42 CFR 435.603(f)(2)(i) sends a dependent other
than the claimant's spouse or natural/adopted/step child to non-filer rules.
Only the Medicaid relationship predicate changes; all other encoding remains.

Primary source published before the reference freeze:
https://www.govinfo.gov/content/pkg/CFR-2025-title42-vol4/pdf/CFR-2025-title42-vol4-sec435-603.pdf
"""

from policyengine_core.reforms import Reform
from policyengine_us.variables.gov.hhs.medicaid.income.medicaid_claimed_by_parent_in_tax_unit import (
    medicaid_claimed_by_parent_in_tax_unit as original_relationship,
)

FIX_ID = "r067_adult_dependent_nonchild"
DESCRIPTION = (
    "For 2026 only, interpret adult tax dependents as people other than their "
    "claimant's natural/adopted/step children for Medicaid household rules."
)


class medicaid_claimed_by_parent_in_tax_unit(original_relationship):
    def formula_2026_01_01(person, period, parameters):
        encoded = original_relationship.formula(person, period, parameters)
        adult_dependent = person("is_tax_unit_dependent", period) & (
            person("age", period) >= 18
        )
        return encoded & ~adult_dependent

    def formula_2027_01_01(person, period, parameters):
        return original_relationship.formula(person, period, parameters)


class reform(Reform):
    def apply(self):
        self.update_variable(medicaid_claimed_by_parent_in_tax_unit)
