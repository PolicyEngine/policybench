"""r10: Wisconsin homestead credit household income omits nontaxable income that
Wis. Stat. 71.52(6) and the 2025 Schedule H count.

Engine (policyengine-us 1.755.4, unchanged on upstream/main 16832c046d):
wi_homestead_income = sum(gov.states.wi.tax.income.credits.homestead.income.sources)
- $500 x dependents, with sources = [adjusted_gross_income, tax_exempt_interest_income,
tax_exempt_social_security, tax_exempt_pension_income,
tax_exempt_unemployment_compensation, ssi, tanf]. Income that never reaches federal
AGI and is not on that list is dropped from household income.

Law. Wis. Stat. 71.52(5): household income is all income of household members, less
$500 per dependent. 71.52(6): "Income" is Wisconsin AGI plus, to the extent not
already in Wisconsin AGI, maintenance payments, support money, cash public
assistance, "the gross amount of any pension or annuity (including railroad
retirement benefits, all payments received under the federal social security act and
veterans disability pensions)", nontaxable interest, worker's compensation,
unemployment insurance, "the gross amount of 'loss of time' insurance",
"compensation and other cash benefits received from the United States for past or
present service in the armed forces", scholarship and fellowship gifts or income, and
other listed items. Exclusions are limited to gifts from natural persons, Title XX
reimbursements, relief in kind, and deferred/nonrecognized home-sale gains.
2025 Wisconsin Schedule H instructions (I-016i, revenue.wi.gov/TaxForms2025/
2025-ScheduleH-inst.pdf), which apply unchanged to 2026 claims:
  9d  "GROSS amount of ALL pensions and annuities ... Include veterans' pensions,
      disability payments ... and nontaxable IRA, SEP, SIMPLE, and qualified plan
      distributions. Both taxable and nontaxable amounts must be included"
      (rollovers and 1035 exchanges excepted)
  9h  nontaxable scholarship and fellowship income, educational grants
  9i  court-ordered child support, family maintenance; post-2018 alimony that is no
      longer taxable "must be included in household income on line 9i"
  11b workers' compensation, income continuation, and loss of time insurance

Fix. Append to the source list every engine variable that (a) is an income type the
statute and Schedule H count, (b) does not reach the engine's federal-AGI base or the
existing list (checked empirically: $10,000 of each moves adjusted_gross_income by 0),
and (c) is nonzero for at least one bundle household:

  survivor_benefits               71.52(6) pension/annuity, worker's comp, armed-forces
                                  benefits; Sch H 9d / 11b. (CPS SRVS_VAL: survivor
                                  pensions, railroad retirement, worker comp, annuities)
  workers_compensation            71.52(6) "worker's compensation"; Sch H 11b
  veterans_benefits               71.52(6) "veterans disability pensions", "compensation
                                  and other cash benefits ... for ... service in the
                                  armed forces"; Sch H 9d
  child_support_received          71.52(6) "support money"; Sch H 9i
  alimony_income                  71.52(6) "maintenance payments"; Sch H 9i note
  disability_benefits             71.52(6) "gross amount of 'loss of time' insurance";
                                  Sch H 9d "disability payments", 11b income continuation
  educational_assistance          71.52(6) "scholarship and fellowship gifts or income";
                                  Sch H 9h
  tax_exempt_retirement_distributions
                                  71.52(6) gross pension/annuity; Sch H 9d nontaxable IRA,
                                  SEP, SIMPLE, qualified plan distributions (the bundle
                                  has tax_exempt_ira_distributions)

Not added (see the structured result): financial_assistance (engine label "cash
financial assistance from outside the household"; 71.52(6) excludes gifts from natural
persons, so the prompt facts do not settle it), estate_income (taxable income that the
engine also drops from federal AGI; a federal-AGI defect, not a homestead one), and the
71.52(6) add-backs of excluded deferrals, IRA/Keogh deductions, depreciation and
disqualified losses (Sch H 9e, 9f, 11e-11j), which are deductions reversed rather than
income types. A work/ variant shows none of these moves any bundle output.

Only wi_homestead_income changes; its consumers are wi_homestead_eligible and
wi_homestead_credit. No parameter values change.
"""

from policyengine_core.periods import instant
from policyengine_core.reforms import Reform

FIX_ID = "r10_wi_homestead_income"
DESCRIPTION = (
    "WI homestead credit household income (Wis. Stat. 71.52(5)-(6), 2025 Schedule H "
    "lines 9d, 9h, 9i, 11b) adds survivor benefits, worker's compensation, veterans "
    "benefits, child support, alimony, disability benefits, scholarships/educational "
    "assistance and nontaxable retirement-account distributions that never reach AGI."
)

ADDED_SOURCES = [
    "survivor_benefits",
    "workers_compensation",
    "veterans_benefits",
    "child_support_received",
    "alimony_income",
    "disability_benefits",
    "educational_assistance",
    "tax_exempt_retirement_distributions",
]


class reform(Reform):
    def apply(self):
        def modify(parameters):
            node = parameters.gov.states.wi.tax.income.credits.homestead.income.sources
            current = list(node("2026-01-01"))
            node.update(
                start=instant("2021-01-01"),
                stop=instant("2100-12-31"),
                value=current + [s for s in ADDED_SOURCES if s not in current],
            )
            return parameters

        self.modify_parameters(modify)
