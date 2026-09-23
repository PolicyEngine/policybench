"""Alternative reading behind the 2026-09-05 SSI-disability exclusions.

The prompt lists a general "is disabled" fact and never SSI's disability
criterion (engine input meets_ssi_disability_criteria, which the certified
microdata never sets). The alternative reading sets that input for every person
the prompt lists as disabled. Situation patch only; applies to tax year 2026.
"""

import copy

FIX_ID = "u_ssi_disability_criteria"
DESCRIPTION = "Read 'is disabled' as meeting SSI's disability criterion."
YEAR = "2026"


def patch(situation, scenario):
    situation = copy.deepcopy(situation)
    for person in situation["people"].values():
        if person.get("is_disabled", {}).get(YEAR):
            person["meets_ssi_disability_criteria"] = {YEAR: True}
    return situation


reform = None
