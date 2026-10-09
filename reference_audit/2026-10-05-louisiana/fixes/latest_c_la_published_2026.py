"""c_la_published_2026 on policyengine-us 2.15.17: Louisiana's 2026 standard deduction as the Department of Revenue published it.

DRAFT, not applied to any published reference: adopting it changes two scored references
and waits for Max's ruling (see ../README.md).

Rule (benchmark card): a scored reference follows from law published before the
2026-07-03 reference freeze; where policyengine-us carries a 2026 amount it computed from
a price index rather than one a government published, the reference takes the amount
published before the freeze or, where none was, the last one published.

La. R.S. 47:294(B) adjusts the standard deduction from January 1, 2026 by the percentage
increase in CPI-U "for the previous calendar year". policyengine-us 2.15.17 carries an
explicit 2026 entry of $12,835 single and separate and $25,670 for the other statuses
(PolicyEngine/policyengine-us#8411, merged 2026-05-24): PolicyEngine's own computation,
$12,500 x 324.054 / 315.605 rounded to the dollar, which no Louisiana publication states.

Before the freeze the Department of Revenue published one 2026 amount, $12,875 single and
separate and $25,750 for the other statuses ($12,500 x 1.03, from the CPI-U data available
on December 1, 2025):
  - the "Louisiana estimated standard deduction" on line 3 of the worksheet in the 2026
    Form IT-540ESi instructions (created 2025-12-03);
  - the 2026 income tax withholding tables, LAC 61:I.1501: Emergency Rule signed
    2025-12-23, effective 2026-01-01 (Louisiana Register, January 20, 2026), Notice of
    Intent (February 20, 2026, pp. 308-317, repromulgated March 20, 2026), Rule (May 20,
    2026, LR 52:749); RIB 26-005; the R-1306 and R-1210 employer formulas.
The rule documents and RIB 26-005 say the amounts allowed on 2026 returns may differ
slightly once calendar-year 2025 CPI-U is released, and the Legislative Fiscal Office's
remark in the Notice of Intent reads the statute as December to December (about 2.68%).
After the freeze, RIB 26-019 (2026-09-28) set the 2026 return amount at $12,838 and
$25,676 ($12,500 x 1.027); under it the two references are $820.26 and $305.05.

This module is the alternative the audit does not recommend: it applies the convention to
policyengine-us's explicit entry and reads the provisional $12,875 as "the amount published
before the freeze".
https://www.doa.la.gov/media/hffhilyf/2605.docx
https://www.doa.la.gov/media/5tqefehu/2602.docx

policyengine-us 2.15.17 reads the amount only in la_standard_deduction, and through it
la_taxable_income; la_withheld_income_tax uses the federal standard deduction, so the
change does not reach the federal SALT deduction. Recomputing all 1,984 outputs moves
exactly two, both scored: scenario_051 and scenario_077 state income tax before
refundable credits, each by -$1.20 (verification/sweep_la_standard_deduction.log).

The 2.15.17 entry is explicit, not uprated, so the September 22 projection screen
(r18_hold_all_projections.py, which diffs the uprated tree against the tree with uprating
disabled) could not see it.
"""

from policyengine_core.parameters import Parameter
from policyengine_core.reforms import Reform

FIX_ID = "latest_c_la_published_2026"
DESCRIPTION = "Louisiana 2026 standard deduction as LDR published it before the freeze (2.15.17)"
ROOT = "gov.states.la.tax.income.deductions.standard.amount."
SINGLE_STATUSES = ("SINGLE", "SEPARATE")
DOUBLE_STATUSES = ("JOINT", "HEAD_OF_HOUSEHOLD", "SURVIVING_SPOUSE")
PUBLISHED_2026 = {ROOT + s: 12_875 for s in SINGLE_STATUSES}
PUBLISHED_2026.update({ROOT + s: 25_750 for s in DOUBLE_STATUSES})
# What 2.15.17 carries. policyengine-us applies a reform set twice (before uprating and
# again with its structural reforms), so a second pass finds the published amount.
ENGINE_2026 = {ROOT + s: 12_835 for s in SINGLE_STATUSES}
ENGINE_2026.update({ROOT + s: 25_670 for s in DOUBLE_STATUSES})
PUBLISHED_2025 = {name: (12_500 if value == 12_875 else 25_000) for name, value in PUBLISHED_2026.items()}


def _convention(parameters):
    seen = set()
    for parameter in parameters.get_descendants():
        if not isinstance(parameter, Parameter) or parameter.name not in PUBLISHED_2026:
            continue
        assert float(parameter("2025-01-01")) == PUBLISHED_2025[parameter.name], (
            parameter.name,
            parameter("2025-01-01"),
        )
        assert float(parameter("2026-01-01")) in (
            ENGINE_2026[parameter.name],
            PUBLISHED_2026[parameter.name],
        ), (parameter.name, parameter("2026-01-01"))
        parameter.update(period="2026", value=PUBLISHED_2026[parameter.name])
        seen.add(parameter.name)
    missing = set(PUBLISHED_2026) - seen
    assert not missing, sorted(missing)
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_convention)
