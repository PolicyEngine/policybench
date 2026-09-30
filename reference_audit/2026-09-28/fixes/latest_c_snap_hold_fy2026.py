"""Hold the FY2026 SNAP schedule for October-December 2026 (convention c_snap_hold_fy2026)
on policyengine-us 2.15.17.

This is a publication convention, not a claim that FY2026 law stays in force after
September 2026. The sidecar rule: "A scored reference follows from the stated facts
and from law published before the 2026-07-03 reference freeze. SNAP October-December
2026 hold the FY2026 schedule ..., the last USDA published before the 2026-07-03
reference freeze; USDA published FY2027 on 2026-08-21. The poverty guideline is the
2026 HHS guideline, published in January 2026."

Sources, with publication dates:
- USDA FNS, "SNAP Fiscal Year 2026 Cost-of-Living Adjustments", fns.usda.gov/snap/
  allotment/cola/fy26 (memo DATE August 13, 2025; page updated August 19, 2025;
  Wayback capture 20250902215244; the sidecar gives the signed memo as 2025-08-14):
  4-person maximum $994, minimum benefit $24, shelter cap $744, homeless shelter
  deduction $198.99, standard deduction $209 for sizes 1-3, asset limits $3,000 and
  $4,500 (at least one member 60+ or disabled).
- USDA FNA, "SNAP FY 2027 Cost-of-Living Adjustments", fna.usda.gov/snap/allotment/
  cola/fy27 (page updated August 28, 2026; memo dated 2026-08-21 per the sidecar and
  policyengine-us#9623): after the freeze.

Why the 1.755.4 module (r13_hold_fy2026_v3) cannot be reused. It held one leaf,
gov.usda.snap.uprating. policyengine-us 1.755.4 applied reforms before
uprate_parameters (system.py), so that hold also set the 339 leaves whose October-
December 2026 values the index produced (maximum allotments, deductions, shelter caps,
utility allowances).
policyengine-us 2.15.17 applies reforms after uprate_parameters (system.py, the
"issue #9075" comment), and encodes FY2027 as published values
(policyengine-us#9623, d27d6c3cc3), so r13_hold_fy2026_v3 on 2.15.17 changes only the
index leaf, which no 2.15.17 formula reads.

What this module does. Every leaf in HOLD_NODES takes, for 2026-10-01 to 2026-12-31
only, its own 2.15.17 value on 2026-09-30 (the FY2026 value). In 2.15.17 those are the
leaves whose value changes at 2026-10-01 as part of the FY2027 schedule:
- max_allotment.main and .additional (FY2027 memo values)
- min_allotment.published_adjustment (FY2027: +$1 in the 48 states and D.C., so that
  round(8% x $298) + 1 = $25 on the held maximum; FY2026 value 0 gives the $24 USDA
  published for FY2026)
- income.deductions.standard, excess_shelter_expense.cap, excess_shelter_expense.
  homeless.deduction (FY2027 memo values)
- income.deductions.utility.single.* and utility.limited.main (uprated by the SNAP
  index, whose 2026-10-01 entry is the June 2026 CPI-U actual, policyengine-us#9090,
  f28aa73eff, 2026-07-20)
- income.deductions.utility.limited.by_household_size.amount (Arizona's FY2027 LUA,
  $154 / $208 from 2026-10-01, added in 9164f90305 on 2026-08-31 from the DES manual;
  a FY2027 utility allowance, which the convention holds; publication date not
  verifiable here, and holding it moves no benchmark output)
- asset_test.limit (FY2027 elderly/disabled limit $4,750, FY2027 memo; FY2026 $4,500)
- gov.usda.snap.uprating (the leaf the 1.755.4 convention held; no 2.15.17 formula
  reads it directly, so holding it changes nothing else)
It also lifts gov.usda.snap.max_allotment.cap for October-December 2026. 2.15.17 first
applies that cap from 2026-10-01 (snap_max_allotment.formula_2026_10_01) at amounts
first published in the FY2027 memo; the FY2026 table has none, and 2.15.17 applies
none in FY2026. The cap binds only at 18+ members, so lifting it moves no benchmark
output.

Not held: the poverty guideline (2.15.17 already uses the 2026 HHS guideline, $15,960
+ $5,680, from 2026-10-01, as the convention specifies); ABAWD waiver timelines
(Alaska's good-faith window ending 2026-11-01, county waiver lists), which are work
rules, not the FY2026 schedule; every other parameter and every other date.

Each leaf's pre-October and post-December values are left exactly as 2.15.17 has them;
the module is idempotent (2.15.17 applies a reform twice while building the system).

The SNAP engine fixes the board regenerated on 1.755.4 are already in 2.15.17 and are
not re-applied: r26 and r27 (policyengine-us#9318, merge 5d88007d90, 2026-08-25; net
income further rounded to cents before half-up by #9587, fa27adbffc), r28 and r31
(policyengine-us#9162, merge 3c41c31457, 2026-07-28; income standards for households
over eight refined by #9587), r33 (policyengine-us#9586, d9e801df41, 2026-09-24).
Re-applying the five 1.755.4 modules on top of this one moves none of the 1,984 outputs.

Validation (2026-09-28, sweep_latest.py -> out/latest_c_snap_hold_fy2026.csv): across the
whole 102,807-leaf parameter tree the module changes 359 leaves, only on dates from
2026-10-01 to 2026-12-31. It changes 17 outputs against raw 2.15.17, all SNAP, and
reproduces 12 of the 13 SNAP outputs the convention set on the board; scenario_066 stays
at 0 because 2.15.17's SNAP work rules read weekly_hours_worked_before_lsr (default 0
since policyengine-us#9261), not the prompt's stated hours, which is independent of this
convention.
"""

from policyengine_core.periods import instant
from policyengine_core.reforms import Reform

try:  # 2.15.17: policyengine_us/tools/parameters.py, used by backdate_parameters
    from policyengine_us.tools.parameters import FIRST_MODELED_YEAR
except ImportError:  # pragma: no cover
    FIRST_MODELED_YEAR = 2015

FIX_ID = "latest_c_snap_hold_fy2026"
DESCRIPTION = (
    "Hold the FY2026 SNAP schedule (maximum and minimum allotments, deductions, shelter "
    "caps, utility allowances, asset limits; no 18+ cap) for October-December 2026 on "
    "policyengine-us 2.15.17."
)

START = instant("2026-10-01")
STOP = instant("2026-12-31")
FY2026_LAST_DAY = "2026-09-30"

HOLD_NODES = (
    "gov.usda.snap.uprating",
    "gov.usda.snap.max_allotment.main",
    "gov.usda.snap.max_allotment.additional",
    "gov.usda.snap.min_allotment.published_adjustment",
    "gov.usda.snap.income.deductions.standard",
    "gov.usda.snap.income.deductions.excess_shelter_expense.cap",
    "gov.usda.snap.income.deductions.excess_shelter_expense.homeless.deduction",
    "gov.usda.snap.income.deductions.utility.single",
    "gov.usda.snap.income.deductions.utility.limited.main",
    "gov.usda.snap.income.deductions.utility.limited.by_household_size.amount",
    "gov.usda.snap.asset_test.limit",
)
LIFT_NODES = ("gov.usda.snap.max_allotment.cap",)


def _node(parameters, path):
    node = parameters
    for part in path.split("."):
        node = node.children[part]
    return node


def _leaves(node):
    if hasattr(node, "values_list"):
        yield node
        return
    for child in node.get_descendants():
        if hasattr(child, "values_list"):
            yield child


def _hold_leaf(leaf):
    value = leaf(FY2026_LAST_DAY)
    if value is None:
        raise ValueError(f"{leaf.name} has no FY2026 value to hold")
    leaf.update(start=START, stop=STOP, value=value)


def _lift_leaf(leaf):
    earliest = leaf.values_list[-1]
    if instant(earliest.instant_str) >= START:
        # First application, before backdate_parameters: give the dates before
        # October 2026 the value backdating would give them (the leaf's first
        # value), so that only October-December 2026 change.
        leaf.update(
            start=instant(f"{FIRST_MODELED_YEAR}-01-01"),
            stop=instant(FY2026_LAST_DAY),
            value=earliest.value,
        )
    leaf.update(start=START, stop=STOP, value=float("inf"))


def make_reform(hold_nodes=HOLD_NODES, lift_nodes=LIFT_NODES):
    def _modify(parameters):
        for path in hold_nodes:
            for leaf in _leaves(_node(parameters, path)):
                _hold_leaf(leaf)
        for path in lift_nodes:
            for leaf in _leaves(_node(parameters, path)):
                _lift_leaf(leaf)
        return parameters

    class _reform(Reform):
        def apply(self):
            self.modify_parameters(_modify)

    return _reform


reform = make_reform()
