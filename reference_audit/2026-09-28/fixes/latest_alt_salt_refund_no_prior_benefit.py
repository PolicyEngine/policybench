"""Alternative reading (not a reference fix, not a hold): the listed SALT refund is not income.

Written for triage cluster salt_refund_gross_income_9122, 2026-09-28, on policyengine-us
2.15.17 plus every pre-freeze-law convention (latest_conventions.py).

What 2.15.17 does. Upstream #9122 (commit 316e7832a1, 2026-09-08; merged as #9422,
e990b4a6f8, 2026-09-16) added `salt_refund_income` to gov.irs.gross_income.sources and
documented the input as "Taxable state and local income tax refunds, credits, or offsets
reported on Form 1040, Schedule 1, line 1". 1.755.4 (the board) never counted the input in
federal gross income. The prompt shows it as "state and local tax refund income: $X",
without the word "taxable" and with no prior-year facts.

Why an alternative reading exists. 26 U.S.C. 111(a) (text last amended by Pub. L. 99-514,
1986) excludes a recovery "to the extent such amount did not reduce the amount of tax
imposed". The 2025 Form 1040 instructions (cover dated Feb 25, 2026), Schedule 1 line 1:
"None of your refund is taxable if, in the year you paid the tax, you either (a) didn't
itemize deductions, or (b) elected to deduct state and local general sales taxes instead of
state and local income taxes." Pub. 525 (2025), "Deductions not itemized", says the same,
and Rev. Rul. 2019-11 (2019-17 I.R.B., 2019-04-22) limits the taxable part further under the
SALT cap. Whether the household itemized, and deducted income tax, in the prior year is an
unlisted status fact; the prompt says to treat unlisted status inputs as false. Read that
way, none of the refund is gross income.

Implementation. The patch sets every listed `salt_refund_income` to 0, so the refund is in
neither federal gross income nor any state base or subtraction (the state subtractions of
the refund that 2.15.17 applies then have nothing to remove, which is the state result of a
refund that never entered federal AGI). The reform is latest_conventions unchanged.
"""

import copy
import importlib.util
import sys
from pathlib import Path

from policyengine_core.reforms import Reform

FIX_ID = "latest_alt_salt_refund_no_prior_benefit"
DESCRIPTION = (
    "latest_conventions with every listed salt_refund_income read as not income (IRC 111: no "
    "prior-year tax benefit); recomputes an alternative_value, not a reference"
)
FIELD = "salt_refund_income"


def _load(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(f"alt_salt_refund_part_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CONVENTIONS = _load("latest_conventions").reform


def _zero(value):
    if isinstance(value, dict):
        return {period: 0.0 for period in value}
    return 0.0


def patch(situation, scenario):
    situation = copy.deepcopy(situation)
    for person in situation.get("people", {}).values():
        if FIELD in person:
            person[FIELD] = _zero(person[FIELD])
    return situation


class reform(Reform):
    def apply(self):
        CONVENTIONS.apply(self)
