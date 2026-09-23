"""Round California's SNAP (CalFresh) net income to the nearest dollar (engine defect).

California's CalFresh budgeting rounds net income to the nearest whole dollar
before applying 30 percent (CDSS summary of MPP 63-503.311, p. 1, dated
2015-08-04: https://www.cdss.ca.gov/shd/res/pdf/ParaRegs-Food-Stamps-Income.pdf;
corroborated by Santa Clara County's CalFresh computation instructions).
policyengine-us 1.755.4 applies no California-specific rounding. Split out of
r13_hold_fy2026_v2. Limited to calendar 2026.
"""
import numpy as np

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *
from policyengine_us.variables.gov.usda.snap.income.snap_net_income import snap_net_income as _base_net

FIX_ID = 'r27_ca_snap_net_income_rounding'
DESCRIPTION = "Round California's SNAP net income to the nearest dollar before the 30% contribution, per MPP 63-503.311."


class snap_net_income(_base_net):
    def formula(spm_unit, period):
        net = _base_net.formula(spm_unit, period)
        if period.start.year != 2026:
            return net
        state = spm_unit.household('state_code_str', period)
        return where(state == 'CA', np.floor(net + 0.5), net)


class reform(Reform):
    def apply(self):
        self.update_variable(snap_net_income)
