"""Round the SNAP minimum allotment to the nearest whole dollar (engine defect, fixed upstream).

7 CFR 273.10(e)(2)(ii)(C): "The minimum benefit is 8 percent of the maximum
allotment for a household of one, rounded to the nearest whole dollar."
policyengine-us 1.755.4 returns 8 percent of the maximum without rounding: $23.84
a month in FY2026, where USDA published $24. PolicyEngine/policyengine-us#9162
(merged 2026-07-28, after the reference freeze) applies the same rounding. This
fix follows the CFR's wording; for Hawaii it gives $40 against USDA's published
$41 (no benchmark household is in Hawaii). The state minimum overrides (DC, MD,
NJ) are unchanged. Limited to calendar 2026.
"""
import numpy as np

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *
from policyengine_us.variables.gov.usda.snap.snap_min_allotment import snap_min_allotment as _base_min

FIX_ID = 'r28_snap_min_allotment_rounding'
DESCRIPTION = 'Round the SNAP minimum allotment (8% of the one-person maximum) to the nearest whole dollar, per 7 CFR 273.10(e)(2)(ii)(C).'


class snap_min_allotment(_base_min):
    def formula(spm_unit, period, parameters):
        if period.start.year != 2026:
            return _base_min.formula(spm_unit, period, parameters)
        snap = parameters(period).gov.usda.snap
        region = spm_unit.household('snap_region_str', period)
        relevant_max = snap.max_allotment.main[region][
            str(snap.min_allotment.relevant_max_allotment_household_size)
        ]
        eligible = spm_unit('snap_unit_size', period) <= snap.min_allotment.maximum_household_size
        minimum = eligible * np.floor(snap.min_allotment.rate * relevant_max + 0.5)
        state = spm_unit.household('state_code_str', period)
        dc = parameters(period).gov.states.dc.dhs.snap.min_allotment
        if dc.in_effect:
            minimum = where(state == 'DC', dc.amount, minimum)
        md = parameters(period).gov.states.md.usda.snap.min_allotment
        if md.in_effect:
            minimum = where((state == 'MD') & spm_unit('md_snap_elderly_present', period), md.amount, minimum)
        nj = parameters(period).gov.states.nj.snap
        if nj.in_effect:
            minimum = where(state == 'NJ', nj.amount, minimum)
        return minimum


class reform(Reform):
    def apply(self):
        self.update_variable(snap_min_allotment)
