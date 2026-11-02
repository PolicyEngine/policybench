"""Alternative-value module (not a convention): latest_conventions + r02_ira_219g_v2 on 2.15.17.

Purpose: recompute, on policyengine-us 2.15.17, the "alternative_value" recorded in
reference_exclusions.json for outputs excluded under root cause r02_ira_219g (IRC 219(g)
active-participant phase-out of the traditional IRA deduction). Those alternative values
were computed on 1.755.4 on 2026-09-22 (r02_ira_219g_v2 with every convention and upstream
fix). This module is for the excluded outputs' recorded alternative values only. It is not
part of the scored reference: the outputs stay excluded while 2.15.17 still deducts
traditional IRA contributions without the 219(g) phase-out (gov.irs.ald.deductions 2026
list names `traditional_ira_contributions` directly; no 219(g) code anywhere in 2.15.17).

Composition: the nine pre-freeze-law conventions (latest_conventions.py) and the verified
r02 fix (r02_ira_219g_v2.py, which reuses r02_ira_219g.py's 2026 arithmetic). The r02 part
reads `gov.irs.gross_income.sources`, so on 2.15.17 its 219(g)(3)(A) MAGI includes
`salt_refund_income`, which PR #9422 (issue #9122) added to federal gross income.

Written for triage cluster excl_r02_ira_219g_federal, 2026-09-28.
"""

import importlib.util
import sys
from pathlib import Path

from policyengine_core.reforms import Reform

FIX_ID = "latest_alt_r02_ira_219g"
DESCRIPTION = (
    "Alternative values for r02-excluded outputs on 2.15.17: latest_conventions plus "
    "r02_ira_219g_v2 (IRC 219(g) phase-out, 2026 ranges from Notice 2025-67)"
)


def _load(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(f"latest_alt_r02_part_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CONVENTIONS = _load("latest_conventions")
R02 = _load("r02_ira_219g_v2")


class reform(Reform):
    def apply(self):
        CONVENTIONS.reform.apply(self)
        R02.reform.apply(self)
