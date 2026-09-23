"""Include Schedule E estate/trust income in gross income for 2026 only.

IRC 61(a)(14), 102(b), 652(a), and 662(a) include the beneficiary's
taxable estate/trust income. This sandbox changes only the 2026 source list.
It does not alter QBI qualification or loss treatment.
"""

from policyengine_core.reforms import Reform

FIX_ID = "r03_estate_income_v2"
DESCRIPTION = "Append estate_income to federal gross-income sources in 2026 only."


def _add_estate_income(parameters):
    node = parameters.gov.irs.gross_income.sources
    current = list(node("2026-01-01"))
    if "estate_income" not in current:
        node.update(period="2026", value=current + ["estate_income"])
    return parameters


class EstateIncomeInGrossIncome2026(Reform):
    def apply(self):
        self.modify_parameters(_add_estate_income)


reform = EstateIncomeInGrossIncome2026
