"""Alternative reading behind the 2026-09-05 Medicare exclusions.

The prompt lists Social Security disability income but never how many months it
has been received (engine input months_receiving_social_security_disability,
integer-typed, never carried by the data). The alternative reading gives every
person with listed SSDI income 24 months of receipt, the Medicare threshold.
Situation patch only; applies to tax year 2026.
"""

import copy

FIX_ID = "u_ssdi_months"
DESCRIPTION = "Read listed SSDI income as 24 or more months of receipt."
YEAR = "2026"


def patch(situation, scenario):
    situation = copy.deepcopy(situation)
    for person in situation["people"].values():
        if person.get("social_security_disability", {}).get(YEAR, 0) > 0:
            person["months_receiving_social_security_disability"] = {YEAR: 24}
    return situation


reform = None
