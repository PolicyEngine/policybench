"""r33: California AGI adds back the federal educator-expense deduction.

Defect (policyengine-us 2.38.6 and earlier)
--------------------------------------------
variables/gov/states/ca/tax/income/ca_additions.py adds only ca_hsa_addition to
federal AGI, so California AGI keeps the federal above-the-line educator
expense deduction (educator_expense_ald, IRC 62(a)(2)(D)).

California law
--------------
California does not conform to the federal educator-expense deduction:
R&TC 17072(b), and the FTB's 2025 Instructions for Schedule CA (540),
Section C, line 11 ("California law does not conform to federal law regarding
educator expenses"), which restores the federally claimed amount to
California AGI. Release 20261010's Opus 5.5 judge flagged it on CA
scenario_099's state income tax (reference_audit/2026-10-09-engine-upgrade/
final_actions.json, excluded_rechecked).

Fix
---
ca_educator_expense_addition adds educator_expense_ald for California tax
units, and ca_additions adds it to ca_hsa_addition: the two variables
PolicyEngine/policyengine-us#10052 (merged 2026-10-12, released in 2.41.0)
defines, with the same adds lists. On an engine that already has them the
reform replaces each with an identical definition and changes nothing.
"""

from __future__ import annotations

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *  # noqa: F401,F403

FIX_ID = "r33_ca_educator_expense_addback"
DESCRIPTION = (
    "California AGI adds back the federal educator-expense deduction "
    "(R&TC 17072(b); Schedule CA (540) Section C line 11)."
)


class ca_educator_expense_addition(Variable):
    value_type = float
    entity = TaxUnit
    label = "California educator expense addition"
    documentation = (
        "Federal above-the-line educator expense deduction claimed on this "
        "return, restored to California AGI under R&TC 17072(b)."
    )
    unit = USD
    definition_period = YEAR
    defined_for = StateCode.CA
    reference = (
        "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=RTC&sectionNum=17072",
        "https://www.ftb.ca.gov/forms/2025/2025-540-booklet.pdf#page=64",
    )
    adds = ["educator_expense_ald"]


class ca_additions(Variable):
    value_type = float
    entity = TaxUnit
    label = "CA AGI additions to federal AGI"
    unit = USD
    definition_period = YEAR
    reference = "https://www.ftb.ca.gov/forms/2021/2021-540.pdf"
    defined_for = StateCode.CA
    adds = ["ca_hsa_addition", "ca_educator_expense_addition"]


class reform(Reform):
    def apply(self):
        self.update_variable(ca_educator_expense_addition)
        self.update_variable(ca_additions)
