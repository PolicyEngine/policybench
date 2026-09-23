"""Idaho parameters under PolicyBench's 2026-07-03 publication freeze.

Tax thresholds: retain the last Idaho-published amounts found, $4,811/$9,622,
in the 2025 Form 40 instructions, revision 2026-03-02, page 9.  A 2026
Commission-published threshold/factor was not verified; this limitation is
documented in sweep/verify/r19_id_report.md.

Retirement caps: Idaho Code 63-3022A defines the maximum via Social Security's
full-retirement-age benefit.  SSA's 2026 fact sheet, linked from its 2025-10-24
release, publishes $4,152/month: $49,824/year single and $74,736 with spouse.
These are law-derived amounts, not a located Idaho 2026 publication.  The
optional ID_RETIREMENT_CAP_MODE=held sensitivity instead uses the published
2025 caps; no benchmark household is eligible for this deduction.

Sources:
https://tax.idaho.gov/wp-content/uploads/forms/EIN00046/EIN00046_03-02-2026.pdf
https://legislature.idaho.gov/statutesrules/idstat/title63/t63ch30/sect63-3022a/
https://www.ssa.gov/cola/factsheets/2026.html
https://www.ssa.gov/news/en/press/releases/2025-10-24.html
"""

import os

from policyengine_core.parameters import Parameter
from policyengine_core.reforms import Reform


FIX_ID = "r19_id_convention"
DESCRIPTION = "Hold Idaho tax thresholds; use pre-freeze SSA-derived retirement caps."

THRESHOLDS = {
    "single": 4_811,
    "separate": 4_811,
    "joint": 9_622,
    "head_of_household": 9_622,
    "surviving_spouse": 9_622,
}
CAPS_2025 = {
    "SINGLE": 48_216,
    "SEPARATE": 0,
    "JOINT": 72_324,
    "HEAD_OF_HOUSEHOLD": 48_216,
    "SURVIVING_SPOUSE": 48_216,
}
CAPS_2026 = {
    "SINGLE": 49_824,
    "SEPARATE": 0,
    "JOINT": 74_736,
    "HEAD_OF_HOUSEHOLD": 49_824,
    "SURVIVING_SPOUSE": 49_824,
}


def _modify(parameters):
    caps = CAPS_2025 if os.environ.get("ID_RETIREMENT_CAP_MODE") == "held" else CAPS_2026
    values = {
        f"gov.states.id.tax.income.main.{status}[1].threshold": value
        for status, value in THRESHOLDS.items()
    }
    values.update(
        {
            f"gov.states.id.tax.income.deductions.retirement_benefits.cap.{status}": value
            for status, value in caps.items()
        }
    )
    found = set()
    for parameter in parameters.get_descendants():
        if isinstance(parameter, Parameter) and parameter.name in values:
            parameter.update(period="2026", value=values[parameter.name])
            found.add(parameter.name)
            if parameter.name.endswith("retirement_benefits.cap.SEPARATE"):
                # The only projected Idaho 2025 entry.  Its zero is correct.
                parameter.update(period="2025", value=0)
    assert found == set(values), f"Missing Idaho parameters: {set(values) - found}"
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_modify)
