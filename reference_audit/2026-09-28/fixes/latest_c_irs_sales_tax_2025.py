"""c_irs_sales_tax_2025 on policyengine-us 2.15.17: the IRS 2025 optional sales tax tables held for 2026.

Rule (reference sidecar, 2026-09-22): the optional state sales tax tables for 2026 are
the 2025 tables the IRS published in the 2025 Instructions for Schedule A (IRS directory
date 2025-12-18), the last published before the 2026-07-03 reference freeze.

Port of r19_irs_sales_tax_convention.py. What 2.15.17 carries (upstream
PolicyEngine/policyengine-us#9616, commit 3f029abf5b, 2026-09-27, "Correct the IRS
Optional State Sales Tax Table and add 2022-2025 values"):
  * 2025: the IRS 2025 table, cell for cell. All 51 x 6 x 19 = 5,814 cells of 2.15.17's
    2025 table equal r19_irs_sales_tax_2025.json (latest/port_state/p21517.json vs the
    JSON; asserted again below), so no 2025 update is needed.
  * 2026: "later years are uprated from 2025" by gov.irs.uprating (tax.yaml metadata),
    a projection, not an IRS publication. This module holds the 2025 cells for 2026.
2.15.17 also corrected the income-bracket rows and zeroes the local estimate in the ten
worksheet jurisdictions; those are formula/metadata fixes of pre-freeze instructions and
are left as 2.15.17 has them.
"""

import json
from pathlib import Path

from policyengine_core.reforms import Reform

FIX_ID = "latest_c_irs_sales_tax_2025"
DESCRIPTION = "IRS 2025 optional state sales tax tables held for 2026 (2.15.17 carries 2025 already)"
TABLES = json.loads(Path(__file__).with_name("r19_irs_sales_tax_2025.json").read_text())


def _convention(parameters):
    table = parameters.gov.irs.deductions.itemized.salt_and_real_estate.state_sales_tax_table.tax
    assert len(TABLES) == 51
    set_cells = 0
    for state, sizes in TABLES.items():
        assert state in table.children, state
        assert len(sizes) == 6
        for size, brackets in enumerate(sizes, 1):
            assert len(brackets) == 19
            for bracket, amount in enumerate(brackets, 1):
                parameter = table.children[state].children[str(size)].children[str(bracket)]
                # 2.15.17 already carries the published 2025 cell; stop if that drifts.
                assert abs(float(parameter("2025-01-01")) - amount) < 1e-9, (
                    state, size, bracket, parameter("2025-01-01"), amount)
                parameter.update(period="2026", value=amount)
                set_cells += 1
    assert set_cells == 5814
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_convention)
