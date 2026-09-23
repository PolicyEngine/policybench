"""2026 estate-income inclusion plus the unlisted-QBI-status-false reading.

IRC 199A(c)(3) and Treasury Regulation 1.199A-6(d) require qualifying
trade-or-business items. A generic estate-income label does not establish
that status. Preserve an explicitly supplied qualification status and all
other years. This is an input interpretation, not a universal legal default.
"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "r03_estate_income_base_v2", Path(__file__).with_name("r03_estate_income_v2.py")
)
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

FIX_ID = "r03_estate_income__qbi_false_v2"
DESCRIPTION = "2026 estate income inclusion; set only unlisted estate QBI status false."
reform = _base.reform


def patch(situation, scenario):
    if scenario.year != 2026:
        return situation
    for person in situation["people"].values():
        if "2026" not in person.get("estate_income", {}):
            continue
        # Each scenario uses annual string keys. Preserve explicit values.
        qualification = person.setdefault("estate_income_would_be_qualified", {})
        qualification.setdefault("2026", False)
    return situation
