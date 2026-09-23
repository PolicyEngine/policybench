"""Use the latest published IRS optional sales-tax table at the July 3 freeze.

The IRS directory dates the 2025 Schedule A instructions December 18, 2025
(the PDF is dated December 8); exact first-publication day is unverified. No 2026 edition was found as of September 22, 2026.
Use all 5,814 state/family-size/income cells from the published 2025 edition
for both 2025 and the held 2026 convention. The companion JSON is extracted
from pages 13-17; absent-state tables are zero under worksheet line 1.

Sources:
https://www.irs.gov/pub/irs-pdf/i1040sca.pdf
https://www.irs.gov/downloads/irs-pdf?order=uri&page=24&sort=asc

Only parameter values change. The existing local_sales_tax = .2 * state_sales_tax
proxy remains in place; this audit does not establish any household's local rate.
"""

import json
from pathlib import Path

from policyengine_core.reforms import Reform

FIX_ID = "r19_irs_sales_tax_convention"
DESCRIPTION = "Published 2025 optional state sales-tax tables held for the 2026 freeze"
TABLES = json.loads(Path(__file__).with_name("r19_irs_sales_tax_2025.json").read_text())


def _convention(parameters):
    table = parameters.gov.irs.deductions.itemized.salt_and_real_estate.state_sales_tax_table.tax
    assert len(TABLES) == 51
    for state, sizes in TABLES.items():
        # CountryTaxBenefitSystem applies the reform both before and after
        # homogenization. Four zero-table states are absent from raw YAML;
        # homogenization fills them, and the second application sets them.
        if state not in table.children:
            assert state in {"DE", "MT", "NH", "OR"}
            continue
        assert len(sizes) == 6
        for size, brackets in enumerate(sizes, 1):
            assert len(brackets) == 19
            for bracket, amount in enumerate(brackets, 1):
                parameter = table.children[state].children[str(size)].children[str(bracket)]
                parameter.update(period="2025", value=amount)
                parameter.update(period="2026", value=amount)
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_convention)
