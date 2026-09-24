"""c13v3_r28_r29c_r33: r13_hold_fy2026_v3 plus r28 and cents-kept net income with r26 rounding, to measure the defect on top of the SNAP convention, with r33 (policyengine-us#9586, merged 2026-09-24), which the references apply from release dashboard-data-20260922c."""
import importlib.util
from pathlib import Path

from policyengine_core.reforms import Reform

_HERE = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PARTS = [_load(n) for n in ['r13_hold_fy2026_v3', 'r28_snap_min_allotment_rounding', 'r29_snap_net_cents', 'r33_snap_child_support_treatment']]
FIX_ID = 'c13v3_r28_r29c_r33'
DESCRIPTION = 'r13_hold_fy2026_v3 plus r28 and cents-kept net income with r26 rounding, with r33'


class reform(Reform):
    def apply(self):
        for part in _PARTS:
            part.reform.apply(self)
