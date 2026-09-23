"""c13v3_upstream_plus_r30: the SNAP convention, the upstream SNAP fixes and r30, for the SNAP sensitivity of r30."""
import importlib.util
from pathlib import Path

from policyengine_core.reforms import Reform

_HERE = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PARTS = [_load(n) for n in ['r13_hold_fy2026_v3', 'r26_snap_contribution_rounding', 'r27_snap_net_income_rounding', 'r28_snap_min_allotment_rounding', 'r31_snap_income_limit_rounding', 'r30_snap_heat_and_eat_sua']]
FIX_ID = 'c13v3_upstream_plus_r30'
DESCRIPTION = 'c13v3_plus_upstream_snap plus r30_snap_heat_and_eat_sua'


class reform(Reform):
    def apply(self):
        for part in _PARTS:
            part.reform.apply(self)
