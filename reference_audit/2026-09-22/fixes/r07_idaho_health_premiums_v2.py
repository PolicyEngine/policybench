"""Idaho 2026 premium subtraction with a consistent deduction election.

Idaho Code 63-3022P excludes premiums already deducted or accounted for:
https://legislature.idaho.gov/statutesrules/idstat/Title63/T63CH30/SECT63-3022P/
Form 39R line 18 worksheet, printed pages 34-35, and Form 40 deduction election,
printed page 8, EIN00046 03-02-2026 (2025 instructions):
https://tax.idaho.gov/wp-content/uploads/forms/EIN00046/EIN00046_03-02-2026.pdf

The standard route keeps all otherwise available premium subtraction. The
itemized route loses the portion used as an itemized medical deduction. Compare
both combined reductions, rather than comparing the deductions in isolation.
Ties retain the standard deduction, as in v1's strict comparison. This is only
the 2026 benchmark repair; unrelated federal medical-expense modeling remains.
"""

from policyengine_core.periods import instant
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *

FIX_ID = "r07_idaho_health_premiums_v2"
DESCRIPTION = "Idaho health premium subtraction with consistent 2026 deduction election."
SUBTRACTION = "id_health_insurance_premiums_subtraction"


def available_and_itemized_portion(tax_unit, period):
    premiums = add(tax_unit, period, ["medical_expense_health_insurance_premiums"])
    elsewhere = tax_unit("self_employed_health_insurance_ald", period)
    available = max_(0, premiums - elsewhere)
    portion = min_(available, tax_unit("medical_expense_deduction", period))
    return available, portion


class id_itemizes_after_health_premiums(Variable):
    value_type = bool
    entity = TaxUnit
    label = "Idaho itemization benefits taxpayer after premium subtraction (2026 repair)"
    definition_period = YEAR
    defined_for = StateCode.ID

    def formula(tax_unit, period, parameters):
        available, portion = available_and_itemized_portion(tax_unit, period)
        mandatory = tax_unit("separate_filer_itemizes", period) & (available > 0)
        return mandatory | (
            tax_unit("id_itemized_deductions", period)
            > tax_unit("standard_deduction", period) + portion
        )


class id_health_insurance_premiums_subtraction(Variable):
    value_type = float
    entity = TaxUnit
    label = "Idaho health insurance premiums subtraction"
    unit = USD
    definition_period = YEAR
    defined_for = StateCode.ID

    def formula(tax_unit, period, parameters):
        available, portion = available_and_itemized_portion(tax_unit, period)
        return available - where(
            tax_unit("id_itemizes_after_health_premiums", period), portion, 0
        )


class id_deductions(Variable):
    value_type = float
    entity = TaxUnit
    label = "Idaho deductions"
    unit = USD
    definition_period = YEAR
    defined_for = StateCode.ID

    def formula(tax_unit, period, parameters):
        itemized = tax_unit("id_itemized_deductions", period)
        standard = tax_unit("standard_deduction", period)
        if period.start.year != 2026:
            return max_(itemized, standard)
        return where(
            tax_unit("id_itemizes_after_health_premiums", period), itemized, standard
        )


def _modify(parameters):
    node = parameters.gov.states.id.tax.income.subtractions.subtractions
    current = list(node(instant("2026-01-01")))
    if SUBTRACTION not in current:
        node.update(
            start=instant("2026-01-01"),
            stop=instant("2026-12-31"),
            value=current + [SUBTRACTION],
        )
    return parameters


class reform(Reform):
    def apply(self):
        self.update_variable(id_itemizes_after_health_premiums)
        self.update_variable(id_health_insurance_premiums_subtraction)
        self.update_variable(id_deductions)
        self.modify_parameters(_modify)
