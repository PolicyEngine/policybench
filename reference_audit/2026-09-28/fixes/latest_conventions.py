"""Every ported pre-freeze-law convention on policyengine-us 2.15.17, applied together.

The reference rule (reference sidecar; Max, 2026-09-28 "we should be using the latest pe
for this always!"): a scored reference follows from the stated facts and from law
published before the 2026-07-03 reference freeze. New references are therefore
policyengine-us 2.15.17 plus the conventions that hold pre-freeze law, and nothing else.

Composes, in this order, the reforms of the nine ported convention modules:
  latest_c_ca_hold_2025        (c_ca_hold_2025)
  latest_c_irs_sales_tax_2025  (c_irs_sales_tax_2025)
  latest_c_wi_published_2026   (c_wi_published_2026)
  latest_c_id_hold_2025        (c_id_hold_2025)
  latest_c_mn_published_2026   (c_mn_published_2026)
  latest_c_md_2026             (c_md_2026)
  latest_c_mi_published_2026   (c_mi_published_2026)
  latest_c_mo_published_2026   (c_mo_published_2026)
  latest_c_snap_hold_fy2026    (c_snap_hold_fy2026)
The same way the 1.755.4 combined modules (c13v3_plus_r33.py and relatives) and
latest_state_conventions.py compose: each part's Reform.apply runs against this reform.
The parts touch disjoint parameter leaves (checked on the full parameter tree by
triage/latest/compose/check_composition.py), so order does not matter.

Not included:
- latest_md_local_output_scope.py: an output-definition adapter (keeps Maryland county
  income tax out of state_income_tax_before_refundable_credits), not a pre-freeze-law
  convention; the port report leaves adopting it to the lead.
- A situation-builder mapping of stated weekly hours to weekly_hours_worked_before_lsr
  (scenario_066): an input mapping, not a convention.
- The 1.755.4 upstream-fix modules (r04, r09, r17, r26, r27, r28, r31, r33): the port
  reports found each already in 2.15.17.
"""

import importlib.util
import sys
from pathlib import Path

from policyengine_core.reforms import Reform

FIX_ID = "latest_conventions"
DESCRIPTION = (
    "All nine pre-freeze-law conventions on 2.15.17: CA, IRS sales tax, WI, ID, MN, MD, "
    "MI, MO published-law holds plus the FY2026 SNAP schedule hold"
)
PARTS = (
    "latest_c_ca_hold_2025",
    "latest_c_irs_sales_tax_2025",
    "latest_c_wi_published_2026",
    "latest_c_id_hold_2025",
    "latest_c_mn_published_2026",
    "latest_c_md_2026",
    "latest_c_mi_published_2026",
    "latest_c_mo_published_2026",
    "latest_c_snap_hold_fy2026",
)


def _load(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(f"latest_conventions_part_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULES = tuple(_load(name) for name in PARTS)
REFORMS = tuple(module.reform for module in MODULES)


class reform(Reform):
    def apply(self):
        for part in REFORMS:
            part.apply(self)
