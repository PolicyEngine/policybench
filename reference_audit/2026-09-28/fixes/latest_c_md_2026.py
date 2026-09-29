"""c_md_2026 on policyengine-us 2.15.17: Maryland's published withholding allowance and 2025 holds.

Rule (reference sidecar, 2026-09-22): Maryland's 2026 withholding allowance is the
$3,400 the Comptroller published in the 2026 Employer Withholding Guide (revised
December 2025); the 2026 flat standard deduction holds the published 2025 amounts
($3,350; $6,700), because no 2026 return amount was located before the 2026-07-03
reference freeze (provisional); the child and dependent care credit caps hold their
2025 amounts. Basis: Md. Tax-Gen. 10-217 (Chapter 604 of 2025); Comptroller Tax Alert
rev. 2025-12-22; 2026 Employer Withholding Guide.

Port of r19_md_convention.py (default mode, provisional holds included). What 2.15.17
carries: every value r19 set is unchanged from 1.755.4 in 2.15.17 (withholding table
2,800/5,700 for 2026 and 2,750/5,600 for 2025; flat deduction 3,400/6,850; CDCC caps
114,600/178,250 and 62,250/93,450), so all are kept.

Not a law convention and NOT in this module: 2.15.17 adds Maryland county income tax
to state_income_tax_before_refundable_credits and to the Maryland withholding proxy
(upstream #8888, commit 6b0bca0b9f, 2026-07-05). See latest_md_local_output_scope.py.
"""

from policyengine_core.parameters import Parameter
from policyengine_core.reforms import Reform

FIX_ID = "latest_c_md_2026"
DESCRIPTION = "Maryland published 2026 withholding allowance and provisional 2025 return/CDCC holds (2.15.17)"
STATUSES = ("SINGLE", "SEPARATE", "JOINT", "HEAD_OF_HOUSEHOLD", "SURVIVING_SPOUSE")
DOUBLE = {"JOINT", "HEAD_OF_HOUSEHOLD", "SURVIVING_SPOUSE"}
ROOT = "gov.states.md.tax.income."

VALUES = {}
for _status in STATUSES:
    # Legacy table; its only live 2025/26 reader in 2.15.17 is md_withheld_income_tax,
    # which reads SINGLE (state and, in 2.15.17, county withholding share it).
    VALUES[ROOT + "deductions.standard.max." + _status] = {2025: 3350, 2026: 3400}
    VALUES[ROOT + "deductions.standard.flat_deduction.amount." + _status] = {
        2026: 6700 if _status in DOUBLE else 3350
    }
    VALUES[ROOT + "credits.cdcc.eligibility.agi_cap." + _status] = {
        2026: 174300 if _status == "JOINT" else 112100
    }
    VALUES[ROOT + "credits.cdcc.eligibility.refundable_agi_cap." + _status] = {
        2026: 91400 if _status == "JOINT" else 60900
    }


def _modify(parameters):
    found = set()
    for parameter in parameters.get_descendants():
        if isinstance(parameter, Parameter) and parameter.name in VALUES:
            for year, value in VALUES[parameter.name].items():
                parameter.update(period=str(year), value=value)
            found.add(parameter.name)
    assert found == set(VALUES), sorted(set(VALUES) - found)
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_modify)
