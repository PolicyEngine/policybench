"""The eight state and IRS published-law conventions on policyengine-us 2.15.17, applied together.

Composes, in this order, the reforms of:
  latest_c_ca_hold_2025, latest_c_irs_sales_tax_2025, latest_c_wi_published_2026,
  latest_c_id_hold_2025, latest_c_mn_published_2026, latest_c_md_2026,
  latest_c_mi_published_2026, latest_c_mo_published_2026.
Their parameter sets are disjoint (each touches only its own state's tree, or the IRS
sales tax table), so order does not matter. The SNAP convention (c_snap_hold_fy2026)
and the Maryland output-scope candidate (latest_md_local_output_scope.py) are not
included.
"""

import importlib.util
import sys
from pathlib import Path

from policyengine_core.reforms import Reform

FIX_ID = "latest_state_conventions"
DESCRIPTION = "CA, IRS sales tax, WI, ID, MN, MD, MI, MO published-law conventions on 2.15.17"
PARTS = (
    "latest_c_ca_hold_2025",
    "latest_c_irs_sales_tax_2025",
    "latest_c_wi_published_2026",
    "latest_c_id_hold_2025",
    "latest_c_mn_published_2026",
    "latest_c_md_2026",
    "latest_c_mi_published_2026",
    "latest_c_mo_published_2026",
)


def _load(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(f"latest_state_part_{name}", path)
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
