"""Round the SNAP gross and net income standards up to whole dollars (engine defect).

7 CFR 273.9(a)(3): the monthly income standards are the poverty guideline times
130 percent (gross) or 100 percent (net), divided by 12 and rounded up to the next
whole dollar. policyengine-us 1.755.4 compares income to the unrounded standard
through an income-to-poverty ratio. Fixed upstream in PolicyEngine/policyengine-us
#9162 (merged 2026-07-28), after the reference freeze. Limited to calendar 2026.
"""
import numpy as np

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *
from policyengine_us.variables.gov.usda.snap.eligibility.meets_snap_gross_income_test import meets_snap_gross_income_test as _base_gross
from policyengine_us.variables.gov.usda.snap.eligibility.meets_snap_net_income_test import meets_snap_net_income_test as _base_net

FIX_ID = 'r31_snap_income_limit_rounding'
DESCRIPTION = 'Round the SNAP gross and net income standards up to the next whole dollar, per 7 CFR 273.9(a)(3).'


class meets_snap_gross_income_test(_base_gross):
    def formula(spm_unit, period, parameters):
        if period.start.year != 2026:
            return _base_gross.formula(spm_unit, period, parameters)
        p = parameters(period).gov.usda.snap.income.limit
        limit = np.ceil(np.round(p.gross * spm_unit('snap_fpg', period), 4))
        income = spm_unit('snap_gross_income', period)
        return spm_unit('has_usda_elderly_disabled', period) | (income <= limit)


class meets_snap_net_income_test(_base_net):
    def formula(spm_unit, period, parameters):
        if period.start.year != 2026:
            return _base_net.formula(spm_unit, period, parameters)
        p = parameters(period).gov.usda.snap.income.limit
        limit = np.ceil(np.round(p.net * spm_unit('snap_fpg', period), 4))
        return spm_unit('snap_net_income', period) <= limit


class reform(Reform):
    def apply(self):
        self.update_variable(meets_snap_gross_income_test)
        self.update_variable(meets_snap_net_income_test)
