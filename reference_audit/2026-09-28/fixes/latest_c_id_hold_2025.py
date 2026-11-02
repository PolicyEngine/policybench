"""c_id_hold_2025 on policyengine-us 2.15.17: Idaho's 2025 zero-rate thresholds held for 2026.

Rule (reference sidecar, 2026-09-22): Idaho's 2026 zero-rate taxable income thresholds
hold the 2025 amounts ($4,811 single; $9,622 joint and head of household) the Tax
Commission published (2025 Form 40 instructions, rev. 2026-03-02, p. 9), the last
located before the 2026-07-03 reference freeze. The retirement-benefit caps take their
statutory 2026 values under Idaho Code 63-3022A, from SSA's 2026 maximum
full-retirement-age benefit ($4,152/month, SSA release 2025-10-24): $49,824 / $74,736.

Port of r19_id_convention.py (default mode). What 2.15.17 carries: every value r19 set
is still an uprated projection in 2.15.17, identical to 1.755.4's (thresholds
4,920.03 / 9,840.06; caps 49,308.72 / 73,963.07), so all are kept. 2.15.17's 2025
SEPARATE cap is already 0, so r19's 2025 repair is a no-op there and is kept only for
parity.
"""

from policyengine_core.parameters import Parameter
from policyengine_core.reforms import Reform

FIX_ID = "latest_c_id_hold_2025"
DESCRIPTION = "Idaho 2025 thresholds held for 2026; SSA-derived 2026 retirement caps (2.15.17)."

THRESHOLDS = {
    "single": 4_811,
    "separate": 4_811,
    "joint": 9_622,
    "head_of_household": 9_622,
    "surviving_spouse": 9_622,
}
CAPS_2026 = {
    "SINGLE": 49_824,
    "SEPARATE": 0,
    "JOINT": 74_736,
    "HEAD_OF_HOUSEHOLD": 49_824,
    "SURVIVING_SPOUSE": 49_824,
}
VALUES = {
    f"gov.states.id.tax.income.main.{status}[1].threshold": value
    for status, value in THRESHOLDS.items()
}
VALUES.update(
    {
        f"gov.states.id.tax.income.deductions.retirement_benefits.cap.{status}": value
        for status, value in CAPS_2026.items()
    }
)


def _modify(parameters):
    found = set()
    for parameter in parameters.get_descendants():
        if isinstance(parameter, Parameter) and parameter.name in VALUES:
            parameter.update(period="2026", value=VALUES[parameter.name])
            found.add(parameter.name)
            if parameter.name.endswith("retirement_benefits.cap.SEPARATE"):
                parameter.update(period="2025", value=0)
    assert found == set(VALUES), f"Missing Idaho parameters: {set(VALUES) - found}"
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_modify)
