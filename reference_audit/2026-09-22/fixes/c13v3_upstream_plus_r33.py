"""c13v3_upstream_plus_r33: the SNAP convention, the upstream SNAP fixes and r33, to measure r33 against the SNAP value actually published."""
import importlib.util
from pathlib import Path

from policyengine_core.reforms import Reform

_HERE = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PARTS = [_load(n) for n in ['r13_hold_fy2026_v3', 'r26_snap_contribution_rounding', 'r27_snap_net_income_rounding', 'r28_snap_min_allotment_rounding', 'r31_snap_income_limit_rounding', 'r33_snap_child_support_treatment']]
FIX_ID = 'c13v3_upstream_plus_r33'
DESCRIPTION = 'c13v3_plus_upstream_snap plus r33_snap_child_support_treatment'


class reform(Reform):
    def apply(self):
        for part in _PARTS:
            part.reform.apply(self)
