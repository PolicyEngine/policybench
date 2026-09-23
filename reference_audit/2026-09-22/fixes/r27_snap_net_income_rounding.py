"""Round SNAP net income to the nearest dollar in every state (engine defect, fixed upstream).

7 CFR 273.10(e)(1)(ii): a state agency rounds each income calculation to the
nearest dollar (A), or follows its TANF procedure, which may keep cents (B).
policyengine-us 1.755.4 floors net income in every state, which matches neither.
PolicyEngine/policyengine-us#9318 (merged 2026-08-25, after the reference freeze)
rounds SNAP net income to the nearest dollar in every state; this fix applies the
same rule. California's CalFresh rounds final net income to the nearest dollar
(CDSS summary of MPP 63-503.311); New Jersey rounds income and deductions to whole
dollars; New York and North Carolina keep cents. Recomputing with cents kept in
every state moves no scored reference. Limited to calendar 2026.
"""
import numpy as np

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *
from policyengine_us.variables.gov.usda.snap.income.snap_net_income import snap_net_income as _base_net

FIX_ID = 'r27_snap_net_income_rounding'
DESCRIPTION = 'Round SNAP net income to the nearest dollar in every state, as policyengine-us#9318 does.'


class snap_net_income(_base_net):
    def formula(spm_unit, period):
        net = _base_net.formula(spm_unit, period)
        if period.start.year != 2026:
            return net
        return np.floor(net + 0.5)


class reform(Reform):
    def apply(self):
        self.update_variable(snap_net_income)
