"""Wisconsin 2026 indexed parameters published before the reference freeze.

Primary source: Wisconsin DOR 2026 Form 1-ES instructions, pp. 2-3,
https://www.revenue.wi.gov/TaxForms2026/2026-Form1-ES-inst.pdf
Revision R. 1-26; laws as of January 16, 2026. The official 2026 forms
index records February 6, 2026, 08:08 for the final instructions.

Replace all 22 projected Wisconsin entries, retaining existing formula and
filing-status mappings. SURVIVING_SPOUSE retains the engine's JOINT alias;
Wisconsin's separate surviving-spouse filing-status issue is outside this
parameter-only audit. No Wisconsin 2025 entry is projected in r18's inventory.
"""

import os

from policyengine_core.parameters import Parameter
from policyengine_core.reforms import Reform


FIX_ID = "r19_wi_convention"
DESCRIPTION = "Wisconsin 2026 standard deductions and brackets from published 1-ES"

ROOT = "gov.states.wi.tax.income."
VALUES = {
    ROOT + "deductions.standard.max.SINGLE": 13_960,
    ROOT + "deductions.standard.max.JOINT": 25_840,
    ROOT + "deductions.standard.max.SEPARATE": 12_280,
    ROOT + "deductions.standard.max.HEAD_OF_HOUSEHOLD": 18_030,
    ROOT + "deductions.standard.max.SURVIVING_SPOUSE": 25_840,
    ROOT + "deductions.standard.phase_out.single[1].threshold": 20_120,
    ROOT + "deductions.standard.phase_out.joint[1].threshold": 29_040,
    ROOT + "deductions.standard.phase_out.separate[1].threshold": 13_780,
    ROOT + "deductions.standard.phase_out.head_of_household[1].threshold": 20_120,
    ROOT + "deductions.standard.phase_out.head_of_household[2].threshold": 58_827,
}
for _status, _thresholds in {
    "single": (15_110, 51_950, 332_720),
    "head_of_household": (15_110, 51_950, 332_720),
    "joint": (20_150, 69_260, 443_630),
    "separate": (10_080, 34_630, 221_820),
}.items():
    for _index, _amount in enumerate(_thresholds, start=1):
        VALUES[ROOT + f"rates.{_status}[{_index}].threshold"] = _amount


def _convention(parameters):
    # Optional prefix restriction provides causal attribution without copying
    # the reform or modifying the triage harness.
    prefixes = tuple(filter(None, os.environ.get("WI_PREFIXES", "").split(",")))
    seen = set()
    for parameter in parameters.get_descendants():
        if isinstance(parameter, Parameter) and parameter.name in VALUES:
            if prefixes and not parameter.name.startswith(prefixes):
                continue
            parameter.update(period="2026", value=VALUES[parameter.name])
            seen.add(parameter.name)
    expected = {name for name in VALUES if not prefixes or name.startswith(prefixes)}
    if seen != expected:
        raise ValueError(f"Missing Wisconsin parameters: {sorted(expected - seen)}")
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_convention)
