"""Limit the heat-and-eat standard utility allowance to elderly or disabled households (engine defect).

P.L. 119-21 sec. 10103(a) (approved 2025-07-04) amended 7 U.S.C.
2014(e)(6)(C)(iv)(I): a LIHEAP payment makes a household eligible for the
standard utility allowance only if the household has an elderly or disabled
member (the text inserts "with an elderly or disabled member" after
"households"). policyengine-us 1.755.4 still grants the allowance to every household in a state
whose always_standard flag models heat-and-eat (Pennsylvania's has been true since
2015-10-01). This fix keeps the flag only for households with a USDA elderly or
disabled member; households with heating or cooling expenses keep the allowance
through the engine's own expense path. Limited to calendar 2026.
"""
import numpy as np

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *
from policyengine_us.variables.gov.usda.snap.income.deductions.shelter.snap_state_using_standard_utility_allowance import (
    snap_state_using_standard_utility_allowance as _base,
)

FIX_ID = 'r30_snap_heat_and_eat_sua'
DESCRIPTION = 'Grant the heat-and-eat standard utility allowance only to households with an elderly or disabled member, per P.L. 119-21 sec. 10103.'


class snap_state_using_standard_utility_allowance(_base):
    def formula(spm_unit, period, parameters):
        flag = _base.formula(spm_unit, period, parameters)
        if period.start.year != 2026:
            return flag
        elderly_disabled = spm_unit('has_usda_elderly_disabled', period.this_year)
        return np.asarray(flag).astype(bool) & np.asarray(elderly_disabled).astype(bool)


class reform(Reform):
    def apply(self):
        self.update_variable(snap_state_using_standard_utility_allowance)
