"""Hold the FY2026 SNAP schedule for calendar 2026 (publication convention only).

The user-directed reference-freeze convention, not a statement that FY2026 law
remains effective after September 2026: October-December 2026 use the FY2026
SNAP figures, the last published before the 2026-07-03 freeze, in place of
policyengine-us 1.755.4's projected FY2027 figures. It holds the SNAP uprating
index (and with it the maximum allotments, deductions and minimum that the
engine derives from it) and the SNAP poverty guideline; other programs' FPG are
unchanged.

This is r13_hold_fy2026_v2 without its formula corrections, which are engine
defects swept separately: r26_snap_contribution_rounding (7 CFR
273.10(e)(2)(ii)(A)), r27_ca_snap_net_income_rounding (MPP 63-503.311) and
r28_snap_min_allotment_rounding (7 CFR 273.10(e)(2)(ii)(C)). v2's published-
minimum override is dropped: the minimum follows the engine's formula on the
held maximum allotment, and r28 carries the rounding.

Sources: USDA FY2026 COLA memorandum, attachment pp. 3-7 (signed 2025-08-14);
7 USC 2017(a). Parameter and variable changes are limited to calendar 2026.
"""
import numpy as np

from policyengine_core.periods import instant
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *
from policyengine_us.variables.gov.usda.snap.income.snap_fpg import snap_fpg as _base_fpg

FIX_ID = 'r13_hold_fy2026_v3'
DESCRIPTION = 'Hold the FY2026 SNAP uprating index and SNAP poverty guideline for calendar 2026.'
def _hold(parameters):
    index = parameters.gov.usda.snap.uprating
    index.update(start=instant('2026-10-01'), stop=instant('2026-12-31'),
                 value=index('2025-10-01'))
    return parameters


class snap_fpg(_base_fpg):
    def formula(spm_unit, period, parameters):
        if period.start.year != 2026:
            return _base_fpg.formula(spm_unit, period, parameters)
        # Preserve this month's unit size while selecting the FY2026 schedule.
        size = spm_unit('snap_unit_size', period)
        state = spm_unit.household('state_group_str', period.this_year)
        p = parameters('2025-10-01').gov.hhs.fpg
        return (p.first_person[state] + p.additional_person[state] * (size - 1)) / MONTHS_IN_YEAR


class reform(Reform):
    def apply(self):
        self.modify_parameters(_hold)
        self.update_variable(snap_fpg)
