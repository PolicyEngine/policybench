"""Missouri's published 2026 income-tax brackets, frozen-law audit.

Source: https://dor.mo.gov/forms/Withholding%20Formula_2026.pdf (annual table).
The DOR forms index dates the 2026 formula 2025-11-21; the same brackets
were republished by USDA NFC on 2026-05-14, before the 2026-07-03 freeze:
https://help.nfc.usda.gov/bulletins/2026/1773783048.htm
2025: https://dor.mo.gov/forms/2025%20Tax%20Chart_2025.pdf (2025-12-23).

All brackets are shared by every filing status. Zero and infinity are
unchanged but explicitly set, including their projected 2025 entries.
The unrelated projected public-pension cap is documented in the report;
its 2026 publication date remains unverified, so this module does not
claim a 2026 convention value for it. The sourced 2025 cap is repaired to
$47,633 only for 2025. Neither MO household has public pensions.
"""

from policyengine_core.reforms import Reform
from policyengine_us.system import system as _baseline_system

FIX_ID = "r19_mo_convention"
DESCRIPTION = "Use Missouri income-tax thresholds published before 2026-07-03."

# CountryTaxBenefitSystem applies reforms before and after uprating. Preserve
# the frozen 2026 cap explicitly so the 2025-only repair cannot change its forecast.
BASELINE_2026_PENSION_CAP = float(
    _baseline_system.parameters("2026-01-01").gov.states.mo.tax.income.deductions
    .social_security_and_public_pension.mo_max_social_security_benefit
)

THRESHOLDS_2025 = (0, 1313, 2626, 3939, 5252, 6565, 7878, 9191, float("inf"))
THRESHOLDS_2026 = (0, 1348, 2696, 4044, 5392, 6740, 8088, 9436, float("inf"))


def _convention(parameters):
    scale = parameters.gov.states.mo.tax.income.rates
    for year, thresholds in ((2025, THRESHOLDS_2025), (2026, THRESHOLDS_2026)):
        for bracket, value in zip(scale.brackets, thresholds):
            bracket.threshold.update(period=str(year), value=value)
    pension = parameters.gov.states.mo.tax.income.deductions.social_security_and_public_pension
    pension.mo_max_social_security_benefit.update(period="2025", value=47633)
    pension.mo_max_social_security_benefit.update(
        period="2026", value=BASELINE_2026_PENSION_CAP
    )
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_convention)
