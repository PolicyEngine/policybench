"""Make the SNAP allotment a whole-dollar amount (engine defect).

7 CFR 273.10(e)(2)(ii)(A): if 30 percent of net income ends in cents, the State
agency either rounds that 30 percent up to the next whole dollar or leaves it
unrounded and rounds the allotment down to the next lower dollar. With a
whole-dollar maximum allotment both methods give the same allotment.
policyengine-us 1.755.4 does neither: snap_expected_contribution is
floor(snap_net_income) * 0.3, and the allotment keeps the cents. This fix takes
method (1). Split out of r13_hold_fy2026_v2, where the verifier added it to
reproduce USDA's allotment arithmetic. Limited to calendar 2026.
"""
import numpy as np

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *
from policyengine_us.variables.gov.usda.snap.snap_expected_contribution import snap_expected_contribution as _base_contribution

FIX_ID = 'r26_snap_contribution_rounding'
DESCRIPTION = 'Round the SNAP expected contribution (30% of net income) up to the next whole dollar, per 7 CFR 273.10(e)(2)(ii)(A).'


class snap_expected_contribution(_base_contribution):
    def formula(spm_unit, period, parameters):
        if period.start.year != 2026:
            return _base_contribution.formula(spm_unit, period, parameters)
        rate = parameters(period).gov.usda.snap.expected_contribution
        net = np.floor(spm_unit('snap_net_income', period))
        return np.ceil(np.round(net * rate, 2))


class reform(Reform):
    def apply(self):
        self.update_variable(snap_expected_contribution)
