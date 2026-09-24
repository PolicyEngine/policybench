"""Treat child support paid as USDA's State Options Reports record it (engine defect).

7 CFR 273.9(c)(17) lets a state exclude legally obligated child support paid to
nonhousehold members from gross income; a state that does not take the option
deducts the payments when computing net income under 7 CFR 273.9(d)(5).
policyengine-us 1.755.4 reads gov.usda.snap.income.deductions.child_support as
"exclude from gross income" (snap_child_support_gross_income_deduction and
snap_gross_test_income subtract the payments before the gross income test when
it is true), but its values carry the opposite meaning: they were entered in
2022 as "can be deducted from net income" and relabeled in 2023 without being
flipped. From 2021-10-01 the engine therefore excludes child support from gross
income in the deduction states, Michigan among them, and deducts it in the
exclusion states. USDA's SNAP State Options Report lists Michigan as a
deduction state (16th edition, "Treatment of Child Support Payments", p. 15;
17th edition, p. 21), and Michigan's Bridges Eligibility Manual 556 subtracts
child support at line 20, after gross income (line 10).

The fix is open upstream and not merged: PolicyEngine/policyengine-us#9586,
head 3f156660320436e02258a94b40bc6e7ba1d7208e. VALUES below are that head's
policyengine_us/parameters/gov/usda/snap/income/deductions/child_support.yaml,
every jurisdiction and date (true = excluded from gross income), copied
verbatim; the pull request changes no formula. The module replaces each
jurisdiction's history from 2010-01-01 with them, as the pull request does.
"""

from policyengine_core.periods import instant
from policyengine_core.reforms import Reform

FIX_ID = "r33_snap_child_support_treatment"
DESCRIPTION = (
    "Set the SNAP child support exclusion flag to USDA's State Options Report "
    "values, as PolicyEngine/policyengine-us#9586 (head 3f15666) does."
)
UPSTREAM_PR = "PolicyEngine/policyengine-us#9586"
UPSTREAM_HEAD = "3f156660320436e02258a94b40bc6e7ba1d7208e"
PARAMETER = "gov.usda.snap.income.deductions.child_support"

# policyengine-us#9586 at 3f15666: jurisdiction -> ((effective date, excluded), ...)
VALUES = {
    "AK": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "AL": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "AR": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "AZ": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "CA": (("2010-01-01", True), ("2017-10-01", True), ("2022-10-01", True), ("2023-10-01", True), ("2024-10-01", True),),
    "CO": (("2010-01-01", False), ("2017-10-01", True), ("2022-10-01", True), ("2023-10-01", True), ("2024-10-01", True),),
    "CT": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "DC": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "DE": (("2010-01-01", False), ("2010-06-10", True), ("2017-10-01", True), ("2022-10-01", True), ("2023-10-01", True), ("2024-10-01", True),),
    "FL": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "GA": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "GU": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "HI": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "IA": (("2010-01-01", False), ("2017-10-01", True), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "ID": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "IL": (("2010-01-01", True), ("2017-10-01", True), ("2022-10-01", True), ("2023-10-01", True), ("2024-10-01", True),),
    "IN": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "KS": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "KY": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "LA": (("2010-01-01", False), ("2017-10-01", True), ("2022-10-01", True), ("2023-10-01", False), ("2024-10-01", False),),
    "MA": (("2010-01-01", False), ("2017-01-13", True), ("2017-10-01", True), ("2022-10-01", True), ("2023-10-01", True), ("2024-10-01", True),),
    "MD": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "ME": (("2010-01-01", False), ("2017-10-01", True), ("2022-10-01", True), ("2023-10-01", True), ("2024-10-01", True),),
    "MI": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "MN": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "MO": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", True), ("2023-10-01", True), ("2024-10-01", True),),
    "MS": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "MT": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "NC": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "ND": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "NE": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "NH": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "NJ": (("2010-01-01", False), ("2017-10-01", True), ("2022-10-01", True), ("2023-10-01", True), ("2024-10-01", True),),
    "NM": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "NV": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "NY": (("2010-01-01", False), ("2017-10-01", True), ("2022-10-01", True), ("2023-10-01", True), ("2024-10-01", True),),
    "OH": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "OK": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "OR": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-01-19", True), ("2023-10-01", True), ("2024-10-01", True),),
    "PA": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "RI": (("2010-01-01", False), ("2017-10-01", True), ("2022-10-01", True), ("2023-10-01", True), ("2024-10-01", True),),
    "SC": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "SD": (("2010-01-01", False), ("2017-10-01", True), ("2022-10-01", True), ("2023-10-01", True), ("2024-10-01", True),),
    "TN": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "TX": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "UT": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "VA": (("2010-01-01", False), ("2017-10-01", False), ("2018-10-31", True), ("2022-10-01", True), ("2023-10-01", True), ("2024-10-01", True),),
    "VI": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "VT": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", True), ("2024-10-01", False),),
    "WA": (("2010-01-01", False), ("2017-10-01", True), ("2022-10-01", True), ("2023-10-01", True), ("2024-10-01", True),),
    "WI": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "WV": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
    "WY": (("2010-01-01", False), ("2017-10-01", False), ("2022-10-01", False), ("2023-10-01", False), ("2024-10-01", False),),
}


def _apply(parameters):
    node = parameters.gov.usda.snap.income.deductions.child_support
    for state, history in VALUES.items():
        child = node.children[state]
        # Each update without a stop replaces the values from its start on,
        # so applying the dates in order reproduces the upstream history.
        for start, value in history:
            child.update(start=instant(start), value=value)
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_apply)
