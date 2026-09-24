"""c13v3_r26_r28_r33: r13_hold_fy2026_v3 plus r26 and r28 (engine floor on net income), to measure the defect on top of the SNAP convention, with r33 (policyengine-us#9586, merged 2026-09-24), which the references apply from release dashboard-data-20260922c."""
import importlib.util
from pathlib import Path

from policyengine_core.reforms import Reform

_HERE = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PARTS = [_load(n) for n in ['r13_hold_fy2026_v3', 'r26_snap_contribution_rounding', 'r28_snap_min_allotment_rounding', 'r33_snap_child_support_treatment']]
FIX_ID = 'c13v3_r26_r28_r33'
DESCRIPTION = 'r13_hold_fy2026_v3 plus r26 and r28 (engine floor on net income), with r33'


class reform(Reform):
    def apply(self):
        for part in _PARTS:
            part.reform.apply(self)
