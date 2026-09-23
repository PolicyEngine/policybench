"""California's last published indexed amounts at the 2026-07-03 freeze.

2025 FTB sources (all amounts held for tax year 2026):
https://www.ftb.ca.gov/about-ftb/newsroom/tax-news/2025/10.html
https://www.ftb.ca.gov/forms/2025/2025-540-tax-rate-schedules.pdf
https://www.ftb.ca.gov/forms/2025/2025-540-booklet.html
https://www.ftb.ca.gov/forms/2025/2025-3514-booklet.html
https://www.ftb.ca.gov/forms/2026/2026-540-es-instructions.html

The CalEITC final-phase credit breakpoints are computed from RTC 17052(o)'s
2019 $200/$505 bases and FTB's published annual indexing factors, rounding
annually under RTC 17041(h): 1.4%, 4.4%, 8.3%, 3.1%, 3.3%, 3.0% (2020-25).
This gives $252/$636, not the engine's projected 2025 $257/$649.
They are statutory derived amounts, not amounts printed by name in Form 3514.
Renter's joint/HOH/surviving cap is $107,988; engine 2025 has $107,987.

Only parameters change: existing withholding and credit formulas remain.
HOLD_PREFIXES optionally restricts the parameter overrides for attribution.
"""

import os
from policyengine_core.parameters import Parameter
from policyengine_core.periods import period
from policyengine_core.reforms import Reform

FIX_ID = "r19_ca_convention"
DESCRIPTION = "California published 2025 amounts carried into 2026, correcting 2025 CalEITC forecast breakpoints."
P = "gov.states.ca.tax.income."
VALUES = {}

BRACKETS = {
    "single": [11079, 26264, 41452, 57542, 72724, 371479, 445771, 742953],
    "separate": [11079, 26264, 41452, 57542, 72724, 371479, 445771, 742953],
    "joint": [22158, 52528, 82904, 115084, 145448, 742958, 891542, 1485906],
    "surviving_spouse": [22158, 52528, 82904, 115084, 145448, 742958, 891542, 1485906],
    "head_of_household": [22173, 52530, 67716, 83805, 98990, 505208, 606251, 1010417],
}
for status, values in BRACKETS.items():
    for i, value in enumerate(values, 1):
        VALUES[P + f"rates.{status}[{i}].threshold"] = value

VALUES.update({
    P + "exemptions.amount": 153,
    P + "exemptions.dependent_amount": 475,
    P + "credits.earned_income.eligibility.max_investment_income": 4814,
    P + "credits.earned_income.phase_out.final.start[0].amount": 252,
    P + "credits.earned_income.phase_out.final.start[1].amount": 636,
    P + "credits.foster_youth.amount[1].amount": 1189,
    P + "credits.foster_youth.phase_out.start": 27425,
    P + "credits.young_child.amount": 1189,
    P + "credits.young_child.loss_threshold": 35640,
    P + "credits.young_child.phase_out.start": 27425,
})
for i, value in enumerate([4661, 6998, 9823]):
    for branch in ["earned_income_amount", "phase_out.start"]:
        VALUES[P + f"credits.earned_income.{branch}[{i}].amount"] = value
for status in ["SINGLE", "SEPARATE", "JOINT", "SURVIVING_SPOUSE", "HEAD_OF_HOUSEHOLD"]:
    VALUES[P + f"credits.renter.income_cap.{status}"] = (
        53994 if status in ["SINGLE", "SEPARATE"] else 107988
    )


def modify(parameters):
    prefixes = [s.strip() for s in os.environ.get("HOLD_PREFIXES", "").split(",") if s.strip()]
    seen = set()
    for param in parameters.get_descendants():
        if isinstance(param, Parameter) and param.name in VALUES:
            if prefixes and not any(param.name.startswith(s) for s in prefixes):
                continue
            param.update(period=period("year:2026-01-01:1"), value=VALUES[param.name])
            # Repair the projected 2025 breakpoints too, so the held value is
            # sourced law rather than another engine forecast.
            if ".earned_income.phase_out.final.start[" in param.name:
                param.update(period=period("year:2025-01-01:1"), value=VALUES[param.name])
            seen.add(param.name)
    expected = {name for name in VALUES if not prefixes or any(name.startswith(s) for s in prefixes)}
    assert seen == expected, sorted(expected - seen)
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(modify)
