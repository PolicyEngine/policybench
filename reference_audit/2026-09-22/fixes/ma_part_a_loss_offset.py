"""2026-only sandbox: carry the existing MA Part A loss offset into tax.

M.G.L. c. 62, section 2(c)(2), (c)(4): capital losses reduce Part A
interest/dividends, subject to the combined $2,000 limit already calculated
by ma_part_a_agi. Section 2(f) taxes adjusted, not gross, Part A income.
https://malegislature.gov/Laws/GeneralLaws/PartI/TitleIX/Chapter62/Section2

The primary reform retains the baseline's Part B interest classification to
isolate the confirmed dividend defect. The companion module selects the
alternative reading that the unspecified interest is ordinary Part A interest.
Neither reform restores the bank-interest exemption repealed from 2024.

This is a narrow tax-base connection fix, not a rewrite of MA capital-loss
netting, carryovers, collectibles, or Part C. All inherited AGI rules remain.
Only scenario_081 is in MA in the 100-household frozen bundle.
"""

from policyengine_core.reforms import Reform
from policyengine_us.model_api import add, max_, min_
from policyengine_us.variables.gov.states.ma.tax.income.gross_income.ma_part_a_gross_income import (
    ma_part_a_gross_income as OriginalGross,
)
from policyengine_us.variables.gov.states.ma.tax.income.taxable_income.ma_part_a_taxable_dividend_income import (
    ma_part_a_taxable_dividend_income as OriginalDividends,
)
from policyengine_us.variables.gov.states.ma.tax.income.taxable_income.ma_part_a_div_excess_exemption import (
    ma_part_a_div_excess_exemption as OriginalDividendExcess,
)
from policyengine_us.variables.gov.states.ma.tax.income.taxable_income.ma_part_a_taxable_capital_gains_income import (
    ma_part_a_taxable_capital_gains_income as OriginalGains,
)
from policyengine_us.variables.gov.states.ma.tax.income.taxable_income.ma_part_a_cg_excess_exemption import (
    ma_part_a_cg_excess_exemption as OriginalGainsExcess,
)

FIX_ID = "ma_part_a_loss_offset"
DESCRIPTION = "2026 MA: use loss-adjusted Part A dividends in the tax and exemption allocation."


def build(*, ordinary_interest=False):
    def gross_interest_and_dividends(tax_unit, period):
        variables = ["dividend_income"]
        if ordinary_interest:
            variables.append("taxable_interest_income")
        return add(tax_unit, period, variables)

    def adjusted_interest_and_dividends(tax_unit, period):
        # ST losses reduce interest/dividends; LT losses first absorb ST gains.
        # Thus the remaining 5% component cannot exceed either gross I&D or
        # total Part A AGI. Reuse the engine's existing $2,000 loss calculation.
        return min_(
            gross_interest_and_dividends(tax_unit, period),
            tax_unit("ma_part_a_agi", period),
        )

    class ma_part_a_gross_income(OriginalGross):
        def formula(tax_unit, period, parameters):
            base = OriginalGross.formula(tax_unit, period, parameters)
            if period.start.year != 2026 or not ordinary_interest:
                return base
            return base + add(tax_unit, period, ["taxable_interest_income"])

    class ma_part_a_taxable_dividend_income(OriginalDividends):
        def formula(tax_unit, period, parameters):
            if period.start.year != 2026:
                return OriginalDividends.formula(tax_unit, period, parameters)
            return max_(
                0,
                adjusted_interest_and_dividends(tax_unit, period)
                - tax_unit("ma_part_b_excess_exemption", period),
            )

    class ma_part_a_div_excess_exemption(OriginalDividendExcess):
        def formula(tax_unit, period, parameters):
            if period.start.year != 2026:
                return OriginalDividendExcess.formula(tax_unit, period, parameters)
            return max_(
                0,
                tax_unit("ma_part_b_excess_exemption", period)
                - adjusted_interest_and_dividends(tax_unit, period),
            )

    class ma_part_a_taxable_capital_gains_income(OriginalGains):
        def formula(tax_unit, period, parameters):
            if period.start.year != 2026:
                return OriginalGains.formula(tax_unit, period, parameters)
            return max_(
                0,
                tax_unit("ma_part_a_agi", period)
                - adjusted_interest_and_dividends(tax_unit, period)
                - tax_unit("ma_part_a_div_excess_exemption", period),
            )

    class ma_part_a_cg_excess_exemption(OriginalGainsExcess):
        def formula(tax_unit, period, parameters):
            if period.start.year != 2026:
                return OriginalGainsExcess.formula(tax_unit, period, parameters)
            return max_(
                0,
                tax_unit("ma_part_a_div_excess_exemption", period)
                - (
                    tax_unit("ma_part_a_agi", period)
                    - adjusted_interest_and_dividends(tax_unit, period)
                ),
            )

    class PartALossOffset(Reform):
        def apply(self):
            for variable in (
                ma_part_a_taxable_dividend_income,
                ma_part_a_div_excess_exemption,
                ma_part_a_taxable_capital_gains_income,
                ma_part_a_cg_excess_exemption,
            ):
                self.update_variable(variable)
            if ordinary_interest:
                self.update_variable(ma_part_a_gross_income)

    return PartALossOffset


reform = build()
