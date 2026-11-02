"""c_wi_published_2026 on policyengine-us 2.15.17: Wisconsin's published 2026 standard deduction.

Rule (reference sidecar, 2026-09-22): Wisconsin's 2026 standard deduction and tax
brackets are the amounts DOR published before the 2026-07-03 reference freeze (2026
Form 1-ES instructions, rev. 1-26, pp. 2-3; 2026 WT-4A worksheet, rev. 11-25, p. 2).

Port of r19_wi_convention.py. What 2.15.17 carries:
  * Brackets: the 12 bracket thresholds r19 set are now explicit 2026 entries in
    2.15.17 (parameters/gov/states/wi/tax/income/rates/*.yaml cite the 2026 Form 1-ES
    instructions) and equal r19's values exactly. They are not re-set; the module
    asserts they still match.
  * Standard deduction: still projected. 2.15.17 uprates the 2025 amounts by
    gov.irs.uprating rounded to $10 (upstream commit 94e40f1471, 2026-09-01), giving
    13,870 / 25,680 / 12,200 / 17,920 maxima and 19,990 / 28,850 / 13,690 / 19,990
    phase-out starts, not DOR's published 13,960 / 25,840 / 12,280 / 18,030 and
    20,120 / 29,040 / 13,780 / 20,120 (and 58,827 for the head-of-household second
    phase-out threshold). These 10 values are set here.
SURVIVING_SPOUSE keeps the engine's JOINT alias, as in r19.
"""

from policyengine_core.parameters import Parameter
from policyengine_core.reforms import Reform

FIX_ID = "latest_c_wi_published_2026"
DESCRIPTION = "Wisconsin 2026 standard deduction from the published 1-ES (brackets already in 2.15.17)"
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
# Published 2026 brackets that 2.15.17 already carries (checked, not set).
CARRIED = {}
for _status, _thresholds in {
    "single": (15_110, 51_950, 332_720),
    "head_of_household": (15_110, 51_950, 332_720),
    "joint": (20_150, 69_260, 443_630),
    "separate": (10_080, 34_630, 221_820),
}.items():
    for _index, _amount in enumerate(_thresholds, start=1):
        CARRIED[ROOT + f"rates.{_status}[{_index}].threshold"] = _amount


def _convention(parameters):
    seen, checked = set(), set()
    for parameter in parameters.get_descendants():
        if not isinstance(parameter, Parameter):
            continue
        if parameter.name in VALUES:
            parameter.update(period="2026", value=VALUES[parameter.name])
            seen.add(parameter.name)
        elif parameter.name in CARRIED:
            assert abs(float(parameter("2026-01-01")) - CARRIED[parameter.name]) < 1e-9, (
                parameter.name, parameter("2026-01-01"))
            checked.add(parameter.name)
    if seen != set(VALUES) or checked != set(CARRIED):
        raise ValueError(
            f"Missing Wisconsin parameters: {sorted((set(VALUES) - seen) | (set(CARRIED) - checked))}"
        )
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_convention)
