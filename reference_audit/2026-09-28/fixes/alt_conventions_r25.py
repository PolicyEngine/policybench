"""Alternative reading for the r25 exclusion on policyengine-us 2.15.17 (not a fix module).

latest_conventions (all nine pre-freeze-law conventions) plus r25_niit_excluded (the reading of
federal_income_tax_before_refundable_credits that leaves out the IRC 1411 NIIT). Used only to
recompute the exclusion record's alternative_value on 2.15.17.
"""
import importlib.util
import sys
from pathlib import Path

from policyengine_core.reforms import Reform

FIXES = Path("/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/sweep/fixes")
FIX_ID = "latest_conventions_plus_r25_niit_excluded"
DESCRIPTION = "latest_conventions + r25_niit_excluded (the NIIT-excluded alternative reading) on 2.15.17"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"alt020_{name}", FIXES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.reform


PARTS = (_load("latest_conventions"), _load("r25_niit_excluded"))


class reform(Reform):
    def apply(self):
        for part in PARTS:
            part.apply(self)
