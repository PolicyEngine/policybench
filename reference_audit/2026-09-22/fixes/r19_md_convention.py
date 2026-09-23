"""Maryland parameter audit at the 2026-07-03 reference freeze.

The return-deduction/CDCC holds are provisional: no final 2026 publication
was located. See sweep/verify/r19_md_report.md. The withholding correction
is supported by the 2026 Employer Withholding Guide, revised December 2025,
and the dated 2026-04-09 US DOI payroll announcement.

Sources:
https://www.marylandcomptroller.gov/content/dam/mdcomp/tax/instructions/withholding/2026/withholding-guide.pdf
https://ibc.doi.gov/HRD/Payroll/Announcements/04-09-26
https://www.marylandcomptroller.gov/content/dam/mdcomp/tax/instructions/2025/resident-booklet.pdf
https://www.marylandcomptroller.gov/content/dam/mdcomp/tax/forms/2025/502cr.pdf
https://mgaleg.maryland.gov/2025RS/Chapters_noln/CH_604_hb0352e.pdf

Set MD_VERIFIED_ONLY=1 to omit the provisional return/CDCC holds and retain
only the published withholding correction (the source of scenario 078).
No withholding rates, exemptions, or formula behavior are changed.
"""

import os

from policyengine_core.parameters import Parameter
from policyengine_core.reforms import Reform

FIX_ID = "r19_md_convention"
DESCRIPTION = "Maryland published withholding deduction and provisional return/CDCC holds"
STATUSES = ("SINGLE", "SEPARATE", "JOINT", "HEAD_OF_HOUSEHOLD", "SURVIVING_SPOUSE")
DOUBLE = {"JOINT", "HEAD_OF_HOUSEHOLD", "SURVIVING_SPOUSE"}
ROOT = "gov.states.md.tax.income."


def _modify(parameters):
    values = {}
    for status in STATUSES:
        # This legacy table's only live 2025/26 reader is the withholding
        # proxy, which always reads SINGLE. Set the complete table to the
        # published withholding amount (the guide has no status split).
        values[ROOT + "deductions.standard.max." + status] = {2025: 3350, 2026: 3400}
        if os.environ.get("MD_VERIFIED_ONLY") != "1":
            # Return deductions: last published amounts. Min is obsolete
            # after 2024, so it is deliberately not assigned fictitious limits.
            values[ROOT + "deductions.standard.flat_deduction.amount." + status] = {
                2026: 6700 if status in DOUBLE else 3350
            }
            values[ROOT + "credits.cdcc.eligibility.agi_cap." + status] = {
                2026: 174300 if status == "JOINT" else 112100
            }
            values[ROOT + "credits.cdcc.eligibility.refundable_agi_cap." + status] = {
                2026: 91400 if status == "JOINT" else 60900
            }
    for parameter in parameters.get_descendants():
        if isinstance(parameter, Parameter) and parameter.name in values:
            for year, value in values[parameter.name].items():
                parameter.update(period=str(year), value=value)
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_modify)
