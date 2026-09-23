"""NY IT-214 verification fix, limited to the assigned 2026 benchmark.

The original fix's undated formula applies the 2025+ Part RR tables even in
2024. Preserve baseline formulas outside 2026, and retain the verified original
2026 calculation. This is a sandbox correction, not a complete historical model.

Sources: Tax Law 606(e)(1)(A)(ii), (1)(F)(ii), (3)(B), and (7),
https://www.nysenate.gov/legislation/laws/TAX/606 ; 2025 IT-214 and IT-214-I,
https://www.tax.ny.gov/pdf/current_forms/it/it214_fill_in.pdf and
https://www.tax.ny.gov/pdf/current_forms/it/it214i.pdf .
"""

import numpy as np
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *  # noqa: F401,F403
from policyengine_us.variables.gov.states.ny.tax.income.credits.ny_real_property_tax_credit import (
    ny_real_property_tax_credit as BaselineNYRPTC,
)

FIX_ID = "r09_ny_rptc_rent_cap_v2"
DESCRIPTION = "NY IT-214 renter cap and Part RR rules; sandbox correction limited to 2026."


def closed_band(income, tops, values):
    index = np.searchsorted(np.asarray(tops, dtype=float), income, side="left")
    return np.append(np.asarray(values, dtype=float), 0.0)[index]


class ny_real_property_tax_credit(BaselineNYRPTC):
    defined_for = StateCode.NY

    def formula(tax_unit, period, parameters):
        if period.start.year != 2026:
            return BaselineNYRPTC.formula(tax_unit, period, parameters)

        p = parameters(period).gov.states.ny.tax.income.credits.real_property_tax
        elderly = tax_unit.any(tax_unit.members("age", period) >= p.elderly_age)
        rent = add(tax_unit, period, ["rent"])
        taxes = add(tax_unit, period, ["real_estate_taxes"])
        assessed_value = add(tax_unit, period, ["assessed_property_value"])
        income = np.floor(max_(tax_unit("adjusted_gross_income", period), 0) + 0.5)
        scale = p.excess_real_property_tax
        rate = closed_band(income, list(scale.thresholds[1:]) + [p.max_agi], list(scale.amounts))
        excess = max_(0, taxes + rent * p.rent_tax_equivalent - income * rate)
        eligible = ((assessed_value <= p.max_property_value)
                    & (rent <= p.max_rent) & (income <= p.max_agi))
        amount = where(
            elderly,
            closed_band(income, [3000, 5000, 7000, 9000, 11000, 14000, 18000],
                        [375, 330, 300, 260, 230, 200, 150]),
            closed_band(income, [5000, 9000, 14000, 18000], [75, 70, 60, 50]),
        )
        return where(eligible & (excess > 0), amount, 0)


class reform(Reform):
    def apply(self):
        self.update_variable(ny_real_property_tax_credit)
