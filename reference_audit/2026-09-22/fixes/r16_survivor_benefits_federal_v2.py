"""r16: count survivor_benefits (non-Social Security survivor benefits) in federal gross income.

Defect
------
policyengine-us 1.755.4 defines survivor_benefits
(variables/household/income/person/general/survivor_benefits.py) as a bare input,
"Survivor benefits other than Social Security survivor benefits", with no formula.
No IRS income parameter lists it: gov.irs.gross_income.sources
(parameters/gov/irs/gross_income/sources.yaml) holds taxable_pension_income,
taxable_retirement_distributions, etc., but not survivor_benefits. So the amount
never reaches irs_gross_income, adjusted_gross_income, the IRC 86 provisional
income in taxable_ss_magi, the OBBBA senior-deduction MAGI, Medicaid's
medicaid_irs_gross_income, or any state tax that starts from federal AGI. The
engine does count it as unearned income for SNAP, SSI, TANF, WIC, HUD and school
meals, and as a household benefit (gov.household.household_benefits).

Rule encoded (the "taxable survivor pension/annuity" reading)
-------------------------------------------------------------
IRC 61(a)(8), (10) include annuities and pensions in gross income; IRC 72 taxes
annuity payments less the exclusion ratio; IRC 402(a) taxes qualified-plan
distributions to the distributee, including a beneficiary. IRS Pub. 575 (for
2025 returns, fetched 2026-09-22 from irs.gov/pub/irs-pdf/p575.pdf), "Survivors
and Beneficiaries": "Benefits paid to you as a survivor under a joint and
survivor annuity must be included in your gross income"; a survivor of an
employee excludes only the part of each payment that recovers the employee's
investment in the contract. IRS Pub. 525 (for 2025 returns), "Survivor
Benefits": "In most cases, payments made by or for an employer because of an
employee's death must be included in income."

This is an alternative factual reading, not a default legal presumption. The
prompt gives neither payer nor cost basis. Assume a survivor annuity from a
noncontributory employer plan (or one whose cost was fully recovered), so the
full amount is taxable. A qualified public-safety survivor annuity can instead
be wholly exempt under IRC 101(h), even if VA benefits are excluded by the
source dataset definition. Those payer facts were not shown in the prompt. The fix appends survivor_benefits to
gov.irs.gross_income.sources. irs_gross_income, taxable_ss_magi,
dependent_gross_income, medicaid_irs_gross_income, taxable_uc_agi and the ALD
MAGI helpers all iterate over that list, so every federal-AGI consumer picks it
up the same way it picks up taxable_pension_income. Nothing else changes:
survivor_benefits stays where it already is in the benefit-program income lists,
and the WI homestead income source list is left alone (r10 handles that).

The opposite reading is also lawful for some payers, which is why the taxability
is an unlisted fact rather than an engine error on stated facts:
  * VA Dependency and Indemnity Compensation and other VA survivor benefits are
    exempt: 38 U.S.C. 5301(a); Pub. 525 "Veterans' benefits".
  * Workers' compensation survivor benefits are exempt: IRC 104(a)(1); Treas.
    Reg. 1.104-1(b); Pub. 525 ("The exemption also applies to your survivors").
  * Survivor annuities for public safety officers killed in the line of duty are
    exempt: IRC 101(h).
  * Life-insurance death proceeds are exempt: IRC 101(a) (installments taxable
    only on the interest element, IRC 101(d)).

Not done here: states that build gross income from their own source lists
(AL, AR, IA, MS, OK, PR, MT elderly credit) would still miss survivor_benefits;
no benchmark household with survivor_benefits lives in those states. State
pension/retirement subtractions keyed to taxable_pension_income (e.g. the WI
67+ retirement income exclusion) do not see survivor_benefits under this fix;
see verify/work/r16_trace.py for the input-move sensitivity that routes the
amount through taxable_private_pension_income instead. In the current bundle
that sensitivity leaves the two moved benchmark outputs unchanged. This
module is only validated for the 2026 benchmark households, not as a general
implementation of every survivor-benefit category. The scenario_108 homestead
credit movement overlaps r10 and does not require federal taxability ambiguity.
"""

from __future__ import annotations

from policyengine_core.periods import instant
from policyengine_core.reforms import Reform

FIX_ID = "r16_survivor_benefits_federal_v2"
DESCRIPTION = (
    "Treat survivor_benefits (non-Social Security survivor benefits) as a fully "
    "taxable pension/annuity for federal purposes by appending it to "
    "gov.irs.gross_income.sources (IRC 61(a)(8), (10), 72, 402(a); IRS Pub. 575 "
    "Survivors and Beneficiaries). Flows to AGI, IRC 86 provisional income and "
    "every state tax that starts from federal AGI."
)

SOURCE = "survivor_benefits"


class _SurvivorBenefitsInGrossIncome(Reform):
    def apply(self):
        def modify(parameters):
            node = parameters.gov.irs.gross_income.sources
            current = list(node("2026-01-01"))
            if SOURCE not in current:
                node.update(
                    start=instant("2026-01-01"),
                    stop=instant("2026-12-31"),
                    value=current + [SOURCE],
                )
            return parameters

        self.modify_parameters(modify)


reform = _SurvivorBenefitsInGrossIncome
