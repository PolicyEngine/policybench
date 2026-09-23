"""Apply the benchmark's FY2026 SNAP financial schedule for calendar 2026.

This is the user-directed reference-freeze convention, not a statement that
FY2026 law remains effective after September 2026. Compared with r13_hold_fy2026,
hold the SNAP poverty guideline as well, and retain the published FY2026 minimum
in October-December (including Hawaii's $41). Do not change other programs' FPG.
The required full-year arithmetic check also exposed California's final-net
rounding choice: round net income to the nearest dollar before applying 30%.

Sources: USDA FY2026 COLA memorandum, attachment pp. 3-7 (signed 2025-08-14);
7 USC 2017(a); 7 CFR 273.10(e)(2)(ii)(A),(C); CDSS's statewide summary of
MPP 63-503.311 (p. 1, dated 2015-08-04):
https://www.cdss.ca.gov/shd/res/pdf/ParaRegs-Food-Stamps-Income.pdf
Santa Clara County's CalFresh benefit computation instructions corroborate both
elderly/disabled and other household procedures:
https://stgenssa.sccgov.org/debs/program_handbooks/calfresh/assets/CalFresh/Budgeting_Concepts/Computation.htm
Preserve other states' existing net-income treatment and state minimum overrides.
Parameter and variable changes are limited to calendar 2026.
"""
import numpy as np

from policyengine_core.periods import instant
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *
from policyengine_us.variables.gov.usda.snap.income.snap_fpg import snap_fpg as _base_fpg
from policyengine_us.variables.gov.usda.snap.income.snap_net_income import snap_net_income as _base_net
from policyengine_us.variables.gov.usda.snap.snap_min_allotment import snap_min_allotment as _base_min
from policyengine_us.variables.gov.usda.snap.snap_expected_contribution import snap_expected_contribution as _base_contribution

FIX_ID = 'r13_hold_fy2026_v2'
DESCRIPTION = 'Hold FY2026 SNAP schedules, including SNAP FPG and published minimum, for calendar 2026; round contribution up and California final net income to the nearest dollar.'
FY2026_MINIMUM = {
    'CONTIGUOUS_US': 24, 'GU': 35, 'VI': 31,
    'AK_URBAN': 31, 'AK_RURAL_1': 39, 'AK_RURAL_2': 48, 'HI': 41,
}


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


class snap_min_allotment(_base_min):
    def formula(spm_unit, period, parameters):
        if period.start.year != 2026:
            return _base_min.formula(spm_unit, period, parameters)
        p = parameters(period).gov.usda.snap.min_allotment
        region = spm_unit.household('snap_region_str', period)
        federal = np.array([FY2026_MINIMUM[str(r)] for r in np.asarray(region)], dtype=float)
        minimum = (spm_unit('snap_unit_size', period) <= p.maximum_household_size) * federal
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


class snap_expected_contribution(_base_contribution):
    def formula(spm_unit, period, parameters):
        if period.start.year != 2026:
            return _base_contribution.formula(spm_unit, period, parameters)
        rate = parameters(period).gov.usda.snap.expected_contribution
        net = np.floor(spm_unit('snap_net_income', period))
        return np.ceil(np.round(net * rate, 2))


class snap_net_income(_base_net):
    def formula(spm_unit, period):
        net = _base_net.formula(spm_unit, period)
        if period.start.year != 2026:
            return net
        state = spm_unit.household('state_code_str', period)
        return where(state == 'CA', np.floor(net + 0.5), net)


class reform(Reform):
    def apply(self):
        self.modify_parameters(_hold)
        self.update_variable(snap_fpg)
        self.update_variable(snap_min_allotment)
        self.update_variable(snap_expected_contribution)
        self.update_variable(snap_net_income)
