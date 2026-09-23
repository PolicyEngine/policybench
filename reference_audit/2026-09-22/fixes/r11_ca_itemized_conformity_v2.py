"""r11 v2: Bound every adjustment to 2026, including regular-tax formulas.

Independent verification found the original undated replacement variables
affected 2025 and 2027 while its AMT parameter edit affected only 2026.
This version preserves the original 2026 operations and baseline formulas
outside 2026. SB 711 (Stats. 2025 ch. 231), sections 1 and 11, had already
established the cited conformity date and miscellaneous-deduction exception
before the July 3, 2026 reference freeze.
https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260SB711

California itemized deductions stop inheriting two federal-only 2026 rules.

Defect (policyengine-us 1.755.4)
--------------------------------
variables/gov/states/ca/tax/income/deductions/itemized/
ca_itemized_deductions_pre_limitation.py builds the California (Schedule CA (540)
Part II) total as

    itemized_deductions_less_salt + ca_investment_interest_expense_deduction
    + real_estate_taxes - investment_interest_expense

and itemized_deductions_less_salt sums the federal list in
parameters/gov/irs/deductions/itemized_deductions.yaml, which includes the
federal charitable_deduction and misc_deduction. For 2026 that carries two
federal-only rules into California:

  * charitable_deduction applies the OBBBA 0.5%-of-AGI floor
    (IRC 170(b)(1)(I); gov.irs.deductions.itemized.charity.floor.applies = true
    from 2026-01-01, amount 0.005) and the federal 60% cash ceiling
    (gov.irs.deductions.itemized.charity.ceiling.all = 0.6).
  * misc_deduction returns 0 because gov.irs.deductions.itemized.misc.applies is
    false from 2018 (IRC 67(g) suspension, made permanent by OBBBA).

California law for tax year 2026
--------------------------------
  * Conformity date: R&TC 17024.5(a)(1)(Q): the IRC "as enacted on" January 1,
    2025 for taxable years beginning on or after January 1, 2025 (text as amended
    by Stats. 2026 ch. 236, SB 1435, effective 2026-09-14). OBBBA (P.L. 119-21,
    enacted 2025-07-04) is after that date, and FTB's 2025 Schedule CA (540)
    instructions say "In general, California R&TC does not conform to the OBBBA."
    R&TC 17201(a) brings in IRC Part VI (incl. section 170) "except as otherwise
    provided".
  * Charitable contributions: no 0.5% floor (it exists only in the post-OBBBA
    IRC). Overall ceiling 50% of federal AGI: FTB 2025 Schedule CA (540)
    instructions, lines 11 and 12, "California limits the amount of your
    deduction to 50% of your federal AGI." For 2026 this is also what the IRC as
    of 2025-01-01 gives: the 60% cash limit of 170(b)(1)(G) applied only to years
    "before January 1, 2026", and R&TC 17024.5(h)(6) makes a provision that
    becomes inoperative after the specified date inoperative for California too,
    leaving the 170(b)(1)(A) 50% limit. "AGI" in AGI-based limitations is federal
    AGI: R&TC 17024.5(h)(2)(A).
  * Miscellaneous itemized deductions: R&TC 17076(a) applies IRC 67 (the 2% floor);
    R&TC 17076(c) (as amended by Stats. 2025 ch. 231, SB 711): "Section 67(g) of
    the Internal Revenue Code ... shall not apply." FTB 2025 Schedule CA (540)
    instructions, lines 19-22: the federal suspension "California law does not
    conform"; form lines 22-25: total job expenses/misc, line 23 = federal
    Form 1040 line 11b (federal AGI), line 24 = 2% of line 23, line 25 = line 22
    minus line 24.
  * CA AMT: 2025 Schedule P (540) instructions, Part I line 5 "Miscellaneous
    itemized deductions: Enter on this line the amount from Schedule CA (540),
    Part II, line 25." The engine already lists misc_deduction as this add-back
    (parameters/gov/states/ca/tax/income/amt/amti/sources.yaml, "line 5"); once
    California's own line-25 amount is allowed for regular tax, the line-5
    add-back must use it too. The installed total-AMTI formula separately adds
    all pre-limitation deductions, instead of reversing only the high-income
    limitation. That inherited issue is outside this narrow fix; all five
    California bundle households have zero AMT before and after this fix.

What this fix changes (tax year 2026 only; nothing federal is touched)
----------------------------------------------------------------------
  1. New ca_charitable_deduction: the engine's own federal charitable_deduction
     computation (same inputs, same non-cash sub-ceilings 0.5 / 0.3 of AGI from
     gov.irs.deductions.itemized.charity.ceiling) with the floor branch removed
     and the overall ceiling set to 50% of federal (positive) AGI.
  2. New ca_misc_deduction: total_misc_deductions (engine sources
     unreimbursed_business_employee_expenses + tax_preparation_fees) above
     gov.irs.deductions.itemized.misc.floor (0.02, IRC 67(a)) x federal positive
     AGI -- i.e. the engine's own misc_deduction formula without the 67(g) switch.
  3. ca_itemized_deductions_pre_limitation: same adds/subtracts as 1.755.4, plus
     ca_charitable_deduction + ca_misc_deduction and minus the federal
     charitable_deduction + misc_deduction that itemized_deductions_less_salt
     carried in.
  4. gov.states.ca.tax.income.amt.amti.sources for 2026: misc_deduction ->
     ca_misc_deduction (Schedule P line 5 = Schedule CA line 25).
The R&TC 17077 high-income limitation (ca_itemized_deductions), the itemize /
standard choice (ca_deductions), and everything else stay as the engine has them.
"""

from __future__ import annotations

from policyengine_core.periods import instant
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *  # noqa: F401,F403

FIX_ID = "r11_ca_itemized_conformity_v2"
DESCRIPTION = (
    "California itemized deductions (Schedule CA (540) Part II) use a California "
    "charitable deduction (IRC 170 as of 2025-01-01: no OBBBA 0.5%-of-AGI floor, "
    "50%-of-federal-AGI ceiling) and allow miscellaneous itemized deductions above "
    "2% of federal AGI (R&TC 17076(c): IRC 67(g) does not apply), instead of the "
    "federal 2026 charitable_deduction and misc_deduction; the CA AMT line-5 "
    "add-back uses the same California misc amount."
)

# FTB 2025 Schedule CA (540) instructions, lines 11-12; IRC 170(b)(1)(A) as of the
# California specified date (R&TC 17024.5(a)(1)(Q), (h)(6)).
CA_CHARITY_CEILING_FRACTION_OF_FEDERAL_AGI = 0.5


class ca_charitable_deduction(Variable):
    value_type = float
    entity = TaxUnit
    label = "California charitable contribution deduction"
    unit = USD
    definition_period = YEAR
    defined_for = StateCode.CA
    reference = (
        "https://www.ftb.ca.gov/forms/2025/2025-540-ca-instructions.html",
        "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=RTC&sectionNum=17024.5",
        "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=RTC&sectionNum=17201",
    )

    end = "2026-12-31"

    def formula_2026(tax_unit, period, parameters):
        # Same computation as the engine's federal charitable_deduction
        # (1.755.4) without the OBBBA floor branch, with California's overall
        # 50%-of-federal-AGI ceiling in place of the federal 60%.
        cash_donations = add(tax_unit, period, ["charitable_cash_donations"])
        non_cash_donations = add(tax_unit, period, ["charitable_non_cash_donations"])
        non_cash_to_non_50_pct = add(
            tax_unit, period, ["charitable_non_cash_donations_non_50_pct_orgs"]
        )
        non_cash_to_50_pct = non_cash_donations - non_cash_to_non_50_pct
        federal_agi = tax_unit("positive_agi", period)
        p = parameters(period).gov.irs.deductions.itemized.charity
        capped_non_cash = min_(
            non_cash_to_50_pct, p.ceiling.non_cash * federal_agi
        ) + min_(
            non_cash_to_non_50_pct,
            p.ceiling.non_cash_to_non_50_pct_org * federal_agi,
        )
        return min_(
            capped_non_cash + cash_donations,
            CA_CHARITY_CEILING_FRACTION_OF_FEDERAL_AGI * federal_agi,
        )


class ca_misc_deduction(Variable):
    value_type = float
    entity = TaxUnit
    label = "California miscellaneous itemized deductions above 2% of federal AGI"
    unit = USD
    definition_period = YEAR
    defined_for = StateCode.CA
    reference = (
        "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=RTC&sectionNum=17076",
        "https://www.ftb.ca.gov/forms/2025/2025-540-ca.pdf",
    )

    end = "2026-12-31"

    def formula_2026(tax_unit, period, parameters):
        # Schedule CA (540) Part II lines 22-25: IRC 67 applies (R&TC 17076(a)),
        # 67(g) does not (R&TC 17076(c)); line 23 is federal AGI.
        p = parameters(period).gov.irs.deductions.itemized.misc
        expenses = tax_unit("total_misc_deductions", period)
        federal_agi = tax_unit("positive_agi", period)
        return max_(0, expenses - p.floor * federal_agi)


class ca_itemized_deductions_pre_limitation(Variable):
    value_type = float
    entity = TaxUnit
    label = "California pre-limitation itemized deductions"
    unit = USD
    definition_period = YEAR
    reference = (
        "https://www.ftb.ca.gov/forms/2025/2025-540-ca-instructions.html"
    )
    defined_for = StateCode.CA

    def formula(tax_unit, period, parameters):
        # Reproduce the baseline adds/subtracts outside the audited year.
        additions = [
            "itemized_deductions_less_salt",
            "ca_investment_interest_expense_deduction",
            "real_estate_taxes",
        ]
        subtractions = ["investment_interest_expense"]
        if period.start.year == 2026:
            additions += ["ca_charitable_deduction", "ca_misc_deduction"]
            subtractions += ["charitable_deduction", "misc_deduction"]
        # Keep v1's exact operation order to avoid changing 2026 rounding.
        result = add(tax_unit, period, additions)
        for variable in subtractions:
            result = result - add(tax_unit, period, [variable])
        return result


def _modify(parameters):
    node = parameters.gov.states.ca.tax.income.amt.amti.sources
    current = list(node(instant("2026-01-01")))
    # Reforms can be applied more than once while the system is built; keep the
    # edit idempotent.
    if "ca_misc_deduction" in current:
        return parameters
    updated = ["ca_misc_deduction" if s == "misc_deduction" else s for s in current]
    node.update(
        start=instant("2026-01-01"),
        stop=instant("2026-12-31"),
        value=updated,
    )
    return parameters


class reform(Reform):
    def apply(self):
        self.update_variable(ca_charitable_deduction)
        self.update_variable(ca_misc_deduction)
        self.update_variable(ca_itemized_deductions_pre_limitation)
        self.modify_parameters(_modify)
