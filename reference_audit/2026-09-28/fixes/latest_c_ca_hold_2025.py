"""c_ca_hold_2025 on policyengine-us 2.15.17: California's 2025 published indexed amounts held for 2026.

Rule (reference sidecar, 2026-09-22): a scored reference follows from the stated facts
and from law published before the 2026-07-03 reference freeze. California's 2026
indexed amounts rest on the June 2026 California CPI (BLS 2026-07-14; DIR 2026-08-12),
so the last amounts FTB published before the freeze are the 2025 amounts.

Port of r19_ca_convention.py (written for 1.755.4). What 2.15.17 carries, read from its
built parameter tree (latest/port_state/p21517.json, classify.txt, proj_21517.json):
  * Every amount r19 set is still a CPI projection in 2.15.17 (2026 value identical to
    1.755.4's), so all of r19's VALUES are kept.
  * The CalEITC final phase-out breakpoints are now projected from the 2019 $200/$505
    bases without annual rounding: 2.15.17 gives $251/$635 for 2025 and $257/$649 for
    2026. The statutory derived amount under RTC 17052(o) with annual rounding under
    17041(h) is $252/$636 (r19 derivation), held for 2025 and 2026 as before.
  * NEW in this port: 30 amounts that 1.755.4 carried at their 2025 values but 2.15.17
    now uprates by California CPI (upstream PolicyEngine/policyengine-us#9059, commit
    df3482f4ef 2026-07-21, "fix inert uprating on six CA breakdown parameters"; #9429,
    commit 2572674b97 2026-09-16). They are held at the 2025 amounts FTB published:
      standard deduction $5,706 / $11,412
        (FTB Tax News, October 2025, "2025 Indexing" table;
         https://www.ftb.ca.gov/about-ftb/newsroom/tax-news/2025/10.html)
      AMT exemption $92,749 / $123,667 / $61,830; AMTI phase-out lower
        $347,808 / $463,745 / $231,868 and upper $718,804 / $958,413 / $479,188
        (FTB 2025 Schedule P (540) instructions, exemption worksheet;
         https://www.ftb.ca.gov/forms/2025/2025-540-p-instructions.html)
      exemption-credit phase-out and itemized-deduction limitation AGI thresholds
        $252,203 / $504,411 / $378,310 (FTB 2025 Form 540 booklet and 2025 Schedule CA
        (540) instructions; https://www.ftb.ca.gov/forms/2025/2025-540-booklet.html,
        https://www.ftb.ca.gov/forms/2025/2025-540-ca-instructions.html)
    FTB's October 2025 Tax News says the complete 2025 amounts are posted in late
    December 2025, i.e. before the freeze.

Only parameters change: formulas are 2.15.17's. 2.15.17 applies a reform after its
uprating pass (policyengine_us/system.py), so a 2026 update is not re-uprated.
"""

from policyengine_core.parameters import Parameter
from policyengine_core.periods import period
from policyengine_core.reforms import Reform

FIX_ID = "latest_c_ca_hold_2025"
DESCRIPTION = (
    "California 2025 published indexed amounts held for 2026 on policyengine-us 2.15.17 "
    "(r19 set plus the 30 amounts 2.15.17 newly projects)."
)
P = "gov.states.ca.tax.income."
STATUSES = ("SINGLE", "SEPARATE", "JOINT", "SURVIVING_SPOUSE", "HEAD_OF_HOUSEHOLD")

# ---- r19_ca_convention.py VALUES (unchanged) -------------------------------------
VALUES_2026 = {}
BRACKETS = {
    "single": [11079, 26264, 41452, 57542, 72724, 371479, 445771, 742953],
    "separate": [11079, 26264, 41452, 57542, 72724, 371479, 445771, 742953],
    "joint": [22158, 52528, 82904, 115084, 145448, 742958, 891542, 1485906],
    "surviving_spouse": [22158, 52528, 82904, 115084, 145448, 742958, 891542, 1485906],
    "head_of_household": [22173, 52530, 67716, 83805, 98990, 505208, 606251, 1010417],
}
for _status, _values in BRACKETS.items():
    for _i, _value in enumerate(_values, 1):
        VALUES_2026[P + f"rates.{_status}[{_i}].threshold"] = _value
VALUES_2026.update({
    P + "exemptions.amount": 153,
    P + "exemptions.dependent_amount": 475,
    P + "credits.earned_income.eligibility.max_investment_income": 4814,
    P + "credits.earned_income.phase_out.final.start[0].amount": 252,
    P + "credits.earned_income.phase_out.final.start[1].amount": 636,
    P + "credits.foster_youth.amount[1].amount": 1189,
    P + "credits.foster_youth.phase_out.start": 27425,
    P + "credits.young_child.amount": 1189,
    P + "credits.young_child.loss_threshold": 35640,
    P + "credits.young_child.phase_out.start": 27425,
})
for _i, _value in enumerate([4661, 6998, 9823]):
    for _branch in ["earned_income_amount", "phase_out.start"]:
        VALUES_2026[P + f"credits.earned_income.{_branch}[{_i}].amount"] = _value
for _status in STATUSES:
    VALUES_2026[P + f"credits.renter.income_cap.{_status}"] = (
        53994 if _status in ("SINGLE", "SEPARATE") else 107988
    )

# ---- new for 2.15.17: amounts it now projects, held at FTB's 2025 amounts ----------
NEW_IN_2_15_17 = {}


def _by_status(path, single, joint, head, separate):
    for status, value in {
        "SINGLE": single,
        "JOINT": joint,
        "SURVIVING_SPOUSE": joint,
        "HEAD_OF_HOUSEHOLD": head,
        "SEPARATE": separate,
    }.items():
        NEW_IN_2_15_17[P + path + "." + status] = value


_by_status("deductions.standard.amount", 5_706, 11_412, 11_412, 5_706)
_by_status("amt.exemption.amount", 92_749, 123_667, 92_749, 61_830)
_by_status("amt.exemption.amti.threshold.lower", 347_808, 463_745, 347_808, 231_868)
_by_status("amt.exemption.amti.threshold.upper", 718_804, 958_413, 718_804, 479_188)
_by_status("exemptions.phase_out.start", 252_203, 504_411, 378_310, 252_203)
_by_status("deductions.itemized.limit.agi_threshold", 252_203, 504_411, 378_310, 252_203)
assert len(NEW_IN_2_15_17) == 30
VALUES_2026.update(NEW_IN_2_15_17)

# The statutory 2025 CalEITC breakpoints also replace 2.15.17's projected 2025 entry.
VALUES_2025 = {
    P + "credits.earned_income.phase_out.final.start[0].amount": 252,
    P + "credits.earned_income.phase_out.final.start[1].amount": 636,
}


def modify(parameters):
    seen = set()
    for param in parameters.get_descendants():
        if not isinstance(param, Parameter):
            continue
        if param.name in VALUES_2026:
            param.update(period=period("year:2026-01-01:1"), value=VALUES_2026[param.name])
            seen.add(param.name)
        if param.name in VALUES_2025:
            param.update(period=period("year:2025-01-01:1"), value=VALUES_2025[param.name])
    missing = set(VALUES_2026) - seen
    assert not missing, sorted(missing)
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(modify)
