"""Hold the FY2026 SNAP schedule for calendar 2026 (publication convention only).

The user-directed reference-freeze convention, not a statement that FY2026 law
remains effective after September 2026: October-December 2026 use the FY2026
SNAP figures, the last USDA published before the 2026-07-03 freeze, in place of
policyengine-us 1.755.4's projected FY2027 figures. It holds the SNAP uprating
index, and with it the maximum allotments, deductions and minimum the engine
derives from it. The poverty guideline is not held: the engine already uses the
2026 HHS guideline (published in January 2026, before the freeze) from October.

This is r13_hold_fy2026_v2 without its formula corrections, which are engine
defects swept separately: r26_snap_contribution_rounding (7 CFR
273.10(e)(2)(ii)(A)), r27_ca_snap_net_income_rounding (MPP 63-503.311) and
r28_snap_min_allotment_rounding (7 CFR 273.10(e)(2)(ii)(C)); and without v2's
poverty-guideline and published-minimum overrides.

Sources: USDA FY2026 SNAP COLA memorandum, attachment pp. 3-7 (signed
2025-08-14); 7 USC 2017(a). Parameter changes are limited to calendar 2026.
"""
import numpy as np

from policyengine_core.periods import instant
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *

FIX_ID = 'r13_hold_fy2026_v3'
DESCRIPTION = 'Hold the FY2026 SNAP uprating index for calendar 2026.'
def _hold(parameters):
    index = parameters.gov.usda.snap.uprating
    index.update(start=instant('2026-10-01'), stop=instant('2026-12-31'),
                 value=index('2025-10-01'))
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_hold)
