"""cwi_plus_r04_r32: cwi_plus_r04 plus r32_wi_capital_gain_distributions, to measure r32 on top of it."""
import importlib.util
from pathlib import Path

from policyengine_core.reforms import Reform

_HERE = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PARTS = [_load(n) for n in ['r19_wi_convention', 'r04_capital_gain_distributions', 'r32_wi_capital_gain_distributions']]
FIX_ID = 'cwi_plus_r04_r32'
DESCRIPTION = 'r19_wi_convention plus r04_capital_gain_distributions plus r32_wi_capital_gain_distributions'


class reform(Reform):
    def apply(self):
        for part in _PARTS:
            part.reform.apply(self)
