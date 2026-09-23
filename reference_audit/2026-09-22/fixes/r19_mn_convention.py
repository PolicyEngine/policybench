"""Minnesota published-parameter convention, reference freeze 2026-07-03.

Primary sources:
2026, dated 2025-12-01 (linked by agency release 2025-12-16):
https://www.revenue.state.mn.us/sites/default/files/2025-12/inflation-adjusted-amounts-2026.pdf
2025, dated 2024-12-11:
https://www.revenue.state.mn.us/sites/default/files/2024-12/inflation-adjusted-amounts-2025.pdf

Every projected Minnesota parameter covered by those publications is explicitly
set for 2026. The 51 projected 2025 renter entries are explicitly set for 2025.
Marriage-credit cap is treated separately; see report and source note below.
Only parameter values change, leaving all formula behavior unchanged.
"""

from policyengine_core.parameters import Parameter
from policyengine_core.reforms import Reform

FIX_ID = "r19_mn_convention"
DESCRIPTION = "Minnesota amounts published before the 2026-07-03 reference freeze"
PREFIX = "gov.states.mn.tax.income."


def _status(single, joint, head=None, separate=None):
    return dict(
        SINGLE=single,
        JOINT=joint,
        HEAD_OF_HOUSEHOLD=single if head is None else head,
        SEPARATE=single if separate is None else separate,
        SURVIVING_SPOUSE=joint,
    )


VALUES_2026 = {}


def _statuses(path, values):
    VALUES_2026.update({PREFIX + path + "." + key: value for key, value in values.items()})


_statuses("amt.fractional_income_threshold", _status(73100, 97470, separate=48740))
_statuses("deductions.standard.base", _status(15300, 30600, 23000))
_statuses("deductions.standard.extra", _status(2000, 1600, separate=1600))
for deduction in ("standard", "itemized"):
    _statuses(f"deductions.{deduction}.reduction.agi_threshold.low", _status(244400, 244400, separate=122200))
    _statuses(f"deductions.{deduction}.reduction.agi_threshold.high", _status(337800, 337800, separate=168900))
_statuses("exemptions.agi_threshold", _status(244500, 366700, 305600, 183350))
_statuses("subtractions.pension_income.cap", _status(13850, 27690))
for subtraction in ("pension_income", "social_security"):
    _statuses(f"subtractions.{subtraction}.reduction.start", _status(86410, 110780, separate=55390))
# The source explicitly labels both alternate-subtraction tables Not Indexed.
_statuses("subtractions.social_security.alternative_amount", _status(4560, 5840, separate=2920))
_statuses("subtractions.social_security.income_amount", _status(69250, 88630, separate=44315))
for name, value in {
    "exemptions.amount": 5300,
    "credits.cdcc.phaseout_threshold": 65610,
    "credits.cwfc.ctc.amount": 1800,
    "credits.cwfc.phase_out.threshold.joint": 38770,
    "credits.cwfc.phase_out.threshold.other": 32680,
    "credits.cwfc.wfc.phase_in[1].threshold": 9690,
    "credits.cwfc.wfc.additional.amount[1].amount": 1020,
    "credits.cwfc.wfc.additional.amount[2].amount": 2330,
    "credits.cwfc.wfc.additional.amount[3].amount": 2770,
}.items():
    VALUES_2026[PREFIX + name] = value

# Earliest located 2026 agency form: near-final draft 2026-08-03, cap $1,894.
# Hold the $1,851 cap printed in the 2025 final draft dated 2025-10-15.
# An earlier 2026 publication was not located; see report's explicit limitation.
# https://www.revenue.state.mn.us/sites/default/files/2026-08/m1ma-26-grid.pdf
# https://www.revenue.state.mn.us/sites/default/files/2025-10/m1ma-25-grid-0.pdf
VALUES_2026[PREFIX + "credits.marriage.maximum_amount"] = 1851

RATE_THRESHOLDS_2026 = {
    "single": (33310, 109430, 203150),
    "joint": (48700, 193480, 337930),
    "separate": (24350, 96740, 168965),
    "head_of_household": (41010, 164800, 270060),
    "surviving_spouse": (48700, 193480, 337930),
}
for status, thresholds in RATE_THRESHOLDS_2026.items():
    for index, value in enumerate(thresholds, 1):
        VALUES_2026[f"{PREFIX}rates.{status}[{index}].threshold"] = value

# Full renter schedule, compressed only where adjacent values are equal in the
# agency table; indices match the existing engine's three single-amount scales.
RENTER_VALUES = {
    2025: {
        "claimant_share": (6670, 15530, 22160, 31030, 37690, 46540, 53180, 62060, 68720, 77570),
        "percent_of_income": (8860, 11070, 15530, 19960, 24360, 28820, 31030, 33240, 37690, 39890, 77570),
        "max_thresholds": (8860, 11070, 15530, 19960, 22160, 24360, 28820, 62060, 64260, 66480, 68720, 70920, 73140, 75350, 77570),
        "max_amounts": (2720, 2640, 2580, 2500, 2440, 2380, 2300, 2240, 2040, 1830, 1550, 1360, 1220, 680, 270),
    },
    2026: {
        "claimant_share": (6820, 15880, 22670, 31740, 38540, 47590, 54390, 63470, 70280, 79330),
        "percent_of_income": (9060, 11320, 15880, 20410, 24920, 29470, 31740, 34000, 38540, 40800, 79330),
        "max_thresholds": (9060, 11320, 15880, 20410, 22670, 24920, 29470, 63470, 65720, 68000, 70280, 72530, 74810, 77070, 79330),
        "max_amounts": (2780, 2700, 2640, 2560, 2490, 2430, 2360, 2290, 2080, 1870, 1590, 1390, 1250, 690, 270),
    },
}


def _renters(year):
    result = {}
    values = RENTER_VALUES[year]
    for scale in ("claimant_share", "percent_of_income"):
        for index, value in enumerate(values[scale], 1):
            result[f"{PREFIX}credits.renters.{scale}[{index}].threshold"] = value
    for index, value in enumerate(values["max_thresholds"], 1):
        result[f"{PREFIX}credits.renters.max_credit[{index}].threshold"] = value
    for index, value in enumerate(values["max_amounts"]):
        result[f"{PREFIX}credits.renters.max_credit[{index}].amount"] = value
    return result


VALUES_2025 = _renters(2025)
VALUES_2026.update(_renters(2026))


def _convention(parameters):
    indexed = {p.name: p for p in parameters.get_descendants() if isinstance(p, Parameter)}
    for year, values in ((2025, VALUES_2025), (2026, VALUES_2026)):
        for name, value in values.items():
            indexed[name].update(period=str(year), value=value)
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_convention)
