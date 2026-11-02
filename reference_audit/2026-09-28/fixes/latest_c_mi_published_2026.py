"""c_mi_published_2026 on policyengine-us 2.15.17: Michigan's published 2026 amounts and 2025 holds.

Rule (reference sidecar, 2026-09-22): Michigan's 2026 personal exemption ($5,900) and
retirement limits are those Treasury published in the 2026 Form 446 (revised February
2026), before the 2026-07-03 reference freeze; amounts with no located 2026 publication
(disability exemption, senior investment limits, homestead and home heating tables)
hold their published 2025 values, which also replace the engine's projected 2025
entries. Basis: Michigan Treasury Form 446 (2026, rev. February 2026); 2025 MI-1040
and MI-1040CR-7 instructions.
https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/SUW/TY2026/446_Withholding-Guide_2026.pdf
https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/IIT/TY2025/MI-1040-Book.pdf
https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/IIT/TY2025/MI-1040CR-7-Book.pdf

Port of r19_mi_convention.py (default mode). What 2.15.17 carries:
  * Retirement tier-one limits: 2.15.17 now has explicit 2026 entries of $67,610 /
    $135,220 (upstream #9073, commit b46a672edd 2026-09-04, and caf421bbe9 2026-09-12),
    equal to Form 446's. They are checked, not set.
  * Personal exemption: 2.15.17 still projects $5,950 for 2026; set to $5,900.
  * Every HELD_2025 amount is unchanged from 1.755.4 in 2.15.17; all are kept.
  * Home heating credit percentage: 2.15.17 sets 0.60 from 2025 (TY2025 MI-1040CR-7
    book, line 45) and carries it into 2026, which is the published-2025 hold this rule
    asks for; 1.755.4 had 0.52. Not set here.
"""

from policyengine_core.parameters import Parameter
from policyengine_core.reforms import Reform

FIX_ID = "latest_c_mi_published_2026"
DESCRIPTION = "Michigan 2026 Form 446 personal exemption and published-2025 holds (2.15.17)"
ROOT = "gov.states.mi.tax.income."
STATUSES = ("SINGLE", "JOINT", "SEPARATE", "HEAD_OF_HOUSEHOLD", "SURVIVING_SPOUSE")
PUBLISHED_2026 = {ROOT + "exemptions.personal": 5_900}
CARRIED_2026 = {ROOT + "credits.home_heating.credit_percentage": 0.6}
HELD_2025 = {
    ROOT + "exemptions.disabled.amount.base": 3_400,
    ROOT + "credits.homestead_property_tax.cap": 1_900,
    ROOT + "credits.homestead_property_tax.household_resources_limit": 71_500,
    ROOT + "credits.homestead_property_tax.property_value_limit": 165_400,
    ROOT + "credits.homestead_property_tax.reduction.start": 62_500,
    ROOT + "credits.home_heating.additional_exemption.amount": 212,
    ROOT + "credits.home_heating.alternate.heating_costs.cap": 3_765,
}
for _status in STATUSES:
    CARRIED_2026[ROOT + "deductions.retirement_benefits.tier_one.amount." + _status] = (
        135_220 if _status == "JOINT" else 67_610
    )
    HELD_2025[ROOT + "deductions.interest_dividends_capital_gains.amount." + _status] = (
        29_376 if _status == "JOINT" else 14_688
    )
for _i, _amount in enumerate((604, 815, 1027, 1239, 1451, 1662)):
    HELD_2025[ROOT + f"credits.home_heating.standard.base[{_i}].amount"] = _amount
for _i, _amount in enumerate((18_592, 25_018, 31_449, 34_227)):
    HELD_2025[ROOT + f"credits.home_heating.alternate.household_resources.cap[{_i}].amount"] = _amount


def _convention(parameters):
    seen, checked = set(), set()
    for parameter in parameters.get_descendants():
        if not isinstance(parameter, Parameter):
            continue
        if parameter.name in PUBLISHED_2026:
            parameter.update(period="2026", value=PUBLISHED_2026[parameter.name])
            seen.add(parameter.name)
        if parameter.name in HELD_2025:
            for year in (2025, 2026):
                parameter.update(period=str(year), value=HELD_2025[parameter.name])
            seen.add(parameter.name)
        if parameter.name in CARRIED_2026:
            assert abs(float(parameter("2026-01-01")) - CARRIED_2026[parameter.name]) < 1e-9, (
                parameter.name, parameter("2026-01-01"))
            checked.add(parameter.name)
    missing = (set(PUBLISHED_2026) | set(HELD_2025)) - seen | (set(CARRIED_2026) - checked)
    assert not missing, sorted(missing)
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_convention)
