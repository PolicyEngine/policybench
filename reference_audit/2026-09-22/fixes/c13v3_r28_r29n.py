"""c13v3_r28_r29n: r13_hold_fy2026_v3 plus r28 and nearest-dollar net income with r26 rounding, to measure the defect on top of the SNAP convention."""
import importlib.util
from pathlib import Path

from policyengine_core.reforms import Reform

_HERE = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PARTS = [_load(n) for n in ['r13_hold_fy2026_v3', 'r28_snap_min_allotment_rounding', 'r29_snap_net_nearest']]
FIX_ID = 'c13v3_r28_r29n'
DESCRIPTION = 'r13_hold_fy2026_v3 plus r28 and nearest-dollar net income with r26 rounding'


class reform(Reform):
    def apply(self):
        for part in _PARTS:
            part.reform.apply(self)
