"""Michigan amounts in Treasury's pre-freeze 2026 withholding guide.

Form 446, revision February 2026: personal exemption $5,900; private
retirement maximum $67,610 single/$135,220 joint (pages 1-2):
https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/SUW/TY2026/446_Withholding-Guide_2026.pdf
2025 Form 446, revision January 2025, gives $5,800 and $65,897/$131,794:
https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/SUW/TY2025/446_Withholding-Guide_2025.pdf

2025 other tables:
https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/IIT/TY2025/MI-1040-Book.pdf
https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/IIT/TY2025/MI-1040CR-7-Book.pdf
https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/IIT/TY2025/MI-1040CR-7.pdf

The January 2026 home-heating form and its instruction tables supply the last
published amounts. The FY2027 proposed LIHEAP plan says tax-year 2026 forms
will be available in January. For homestead, disability, and senior investment
deductions, a 2026 publication/date was not located: their holds are explicitly
provisional. Set MI_VERIFIED_ONLY=1 to omit the held tables and their 2025
repairs, retaining only the six verified 2026 personal/retirement leaves.
"""

import os

from policyengine_core.parameters import Parameter
from policyengine_core.reforms import Reform

FIX_ID = "r19_mi_convention"
DESCRIPTION = "Michigan published 2026 amounts and documented/provisional holds."
ROOT = "gov.states.mi.tax.income."
STATUSES = ("SINGLE", "JOINT", "SEPARATE", "HEAD_OF_HOUSEHOLD", "SURVIVING_SPOUSE")
PUBLISHED_2026 = {ROOT + "exemptions.personal": 5_900}
HELD_2025 = {
    ROOT + "exemptions.disabled.amount.base": 3_400,
    ROOT + "credits.homestead_property_tax.cap": 1_900,
    ROOT + "credits.homestead_property_tax.household_resources_limit": 71_500,
    ROOT + "credits.homestead_property_tax.property_value_limit": 165_400,
    ROOT + "credits.homestead_property_tax.reduction.start": 62_500,
    ROOT + "credits.home_heating.additional_exemption.amount": 212,
    ROOT + "credits.home_heating.alternate.heating_costs.cap": 3_765,
}
for status in STATUSES:
    PUBLISHED_2026[ROOT + "deductions.retirement_benefits.tier_one.amount." + status] = (
        135_220 if status == "JOINT" else 67_610
    )
    HELD_2025[ROOT + "deductions.interest_dividends_capital_gains.amount." + status] = (
        29_376 if status == "JOINT" else 14_688
    )
for i, amount in enumerate((604, 815, 1027, 1239, 1451, 1662)):
    HELD_2025[ROOT + f"credits.home_heating.standard.base[{i}].amount"] = amount
for i, amount in enumerate((18_592, 25_018, 31_449, 34_227)):
    HELD_2025[ROOT + f"credits.home_heating.alternate.household_resources.cap[{i}].amount"] = amount


def _convention(parameters):
    for parameter in parameters.get_descendants():
        if not isinstance(parameter, Parameter):
            continue
        if parameter.name in PUBLISHED_2026:
            parameter.update(period="2026", value=PUBLISHED_2026[parameter.name])
        if parameter.name in HELD_2025 and os.environ.get("MI_VERIFIED_ONLY") != "1":
            # Also correct projected 2025 entries rather than carrying a
            # forecast forward as though it were a published 2025 amount.
            for year in (2025, 2026):
                parameter.update(period=str(year), value=HELD_2025[parameter.name])
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_convention)
