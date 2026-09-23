"""Sensitivity: net income keeps its cents in every state (a TANF procedure that includes cents, 7 CFR 273.10(e)(1)(ii)(B)), with the 30 percent contribution rounded up (r26)."""
import numpy as np

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *
from policyengine_us.variables.gov.usda.snap.snap_expected_contribution import snap_expected_contribution as _base_contribution

FIX_ID = 'r29_snap_net_cents'
DESCRIPTION = 'Net income keeps cents in every state, contribution rounded up.'


class snap_expected_contribution(_base_contribution):
    def formula(spm_unit, period, parameters):
        if period.start.year != 2026:
            return _base_contribution.formula(spm_unit, period, parameters)
        rate = parameters(period).gov.usda.snap.expected_contribution
        net = spm_unit('snap_net_income', period)
        return np.ceil(np.round(net * rate, 2))


class reform(Reform):
    def apply(self):
        self.update_variable(snap_expected_contribution)
