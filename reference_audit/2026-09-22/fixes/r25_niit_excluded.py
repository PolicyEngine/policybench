"""r25: read "federal income tax before refundable credits" as excluding the NIIT.

The prompt defines the output as "federal individual income tax after nonrefundable
credits and before refundable credits". policyengine-us 1.755.4's
income_tax_before_refundable_credits adds net_investment_income_tax (IRC 1411, chapter
2A) to income_tax_before_credits. On Form 1040 the NIIT enters on Schedule 2, Part II
("Other taxes"), after line 22 ("tax after nonrefundable credits"), beside
self-employment tax, which the benchmark scores as a separate output. So a careful
reader can take the definition either way. This module encodes the reading that
excludes the NIIT by setting its 2026 rate to zero.
"""

from __future__ import annotations

from policyengine_core.periods import instant
from policyengine_core.reforms import Reform

FIX_ID = "r25_niit_excluded"


class _NiitExcluded(Reform):
    def apply(self):
        def modify(parameters):
            parameters.gov.irs.investment.net_investment_income_tax.rate.update(
                start=instant("2026-01-01"), stop=instant("2026-12-31"), value=0
            )
            return parameters

        self.modify_parameters(modify)


reform = _NiitExcluded
