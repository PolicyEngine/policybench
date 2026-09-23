"""r24: count disability_benefits (employment disability benefits) in federal gross income.

policyengine-us 1.755.4 defines disability_benefits
(variables/household/income/person/general/disability_benefits.py) as "Disability
benefits from employment (not Social Security), except for worker's compensation", an
input with no formula, and gov.irs.gross_income.sources does not list it, so the
amount never reaches federal gross income, adjusted gross income, IRC 86 provisional
income, Medicaid MAGI, or any state tax that starts from federal AGI.

Whether such benefits are taxable depends on who paid for the coverage: benefits from
employer-paid coverage are included in gross income (IRC 105(a)), while benefits from
coverage the employee paid for with after-tax money are excluded (IRC 104(a)(3)). The
prompt lists the benefits without saying who paid for the coverage, so taxability is
an unlisted fact. This module encodes the employer-paid reading by appending
disability_benefits to gov.irs.gross_income.sources for 2026, the same way r16 treats
survivor_benefits; every federal-AGI consumer picks it up.
"""

from __future__ import annotations

from policyengine_core.periods import instant
from policyengine_core.reforms import Reform

FIX_ID = "r24_disability_benefits_taxable"
SOURCE = "disability_benefits"


class _DisabilityBenefitsInGrossIncome(Reform):
    def apply(self):
        def modify(parameters):
            node = parameters.gov.irs.gross_income.sources
            current = list(node("2026-01-01"))
            if SOURCE not in current:
                node.update(
                    start=instant("2026-01-01"),
                    stop=instant("2026-12-31"),
                    value=current + [SOURCE],
                )
            return parameters

        self.modify_parameters(modify)


reform = _DisabilityBenefitsInGrossIncome
