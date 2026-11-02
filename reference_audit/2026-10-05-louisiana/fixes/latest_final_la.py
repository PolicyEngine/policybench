"""latest_final plus the Louisiana standard deduction convention (DRAFT).

The system a release would build the references with if Max adopts c_la_published_2026:
``reference_audit/2026-09-28/fixes/latest_final.py`` (the nine pre-freeze-law conventions
and the Maryland output-scope adapter), then ``latest_c_la_published_2026``. The Louisiana
module touches only gov.states.la.tax.income.deductions.standard.amount, which no
latest_final part touches, so order does not matter.

latest_final is loaded from the 2026-09-28 directory, together with the IRS sales tax
table its IRS module reads, so the committed modules there stay byte-identical.
"""

import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

from policyengine_core.reforms import Reform

FIX_ID = "latest_final_la"
DESCRIPTION = "latest_final plus the Louisiana 2026 published standard deduction (draft)"
HERE = Path(__file__).resolve().parent
AUDIT = HERE.parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _latest_final():
    target = Path(tempfile.mkdtemp(prefix="latest_final_la_"))
    for path in (AUDIT / "2026-09-28/fixes").glob("*.py"):
        shutil.copy2(path, target / path.name)
    shutil.copy2(AUDIT / "2026-09-22/fixes/r19_irs_sales_tax_2025.json", target)
    return _load("latest_final", target / "latest_final.py").reform


LATEST_FINAL = _latest_final()
LOUISIANA = _load("latest_c_la_published_2026", HERE / "latest_c_la_published_2026.py").reform


class reform(Reform):
    def apply(self):
        LATEST_FINAL.apply(self)
        LOUISIANA.apply(self)
