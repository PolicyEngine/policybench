"""c_mo_published_2026 on policyengine-us 2.15.17: Missouri's published 2026 brackets.

Rule (reference sidecar, 2026-09-22): Missouri's 2026 income tax brackets are those
the Department of Revenue published in its 2026 withholding formula (dated 2025-11-21),
before the 2026-07-03 reference freeze, not the engine's CPI projections.
https://dor.mo.gov/forms/Withholding%20Formula_2026.pdf (annual table, p. 2)
2025: https://dor.mo.gov/forms/2025%20Tax%20Chart_2025.pdf

Port of r19_mo_convention.py. What 2.15.17 carries: 2026 thresholds are still uprated
projections (1,342.76 ... 9,399.29), identical to 1.755.4's; 2025 thresholds equal the
published 2025 chart already. All thresholds are set as in r19.

Public-pension cap: r19 repaired the 2025 cap to $47,633 and re-pinned the 2026 cap to
the engine's own 2026 value, because 1.755.4 applied reforms before uprating and a 2025
edit would have moved the 2026 projection. 2.15.17 applies a reform after its uprating
pass (policyengine_us/system.py), so the 2025 edit cannot move 2026; the re-pin (which
imported the baseline system) is dropped. The 2026 cap stays 2.15.17's value
($49,308.72), as in r19, which claims no 2026 convention value for it. No MO benchmark
household has public pensions.
"""

from policyengine_core.reforms import Reform

FIX_ID = "latest_c_mo_published_2026"
DESCRIPTION = "Missouri income-tax thresholds published before 2026-07-03 (2.15.17)."

THRESHOLDS_2025 = (0, 1313, 2626, 3939, 5252, 6565, 7878, 9191, float("inf"))
THRESHOLDS_2026 = (0, 1348, 2696, 4044, 5392, 6740, 8088, 9436, float("inf"))


def _convention(parameters):
    scale = parameters.gov.states.mo.tax.income.rates
    assert len(scale.brackets) == len(THRESHOLDS_2026)
    for year, thresholds in ((2025, THRESHOLDS_2025), (2026, THRESHOLDS_2026)):
        for bracket, value in zip(scale.brackets, thresholds):
            bracket.threshold.update(period=str(year), value=value)
    pension = parameters.gov.states.mo.tax.income.deductions.social_security_and_public_pension
    pension.mo_max_social_security_benefit.update(period="2025", value=47633)
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_convention)
