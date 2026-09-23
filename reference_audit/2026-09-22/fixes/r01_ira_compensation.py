"""r01_ira_compensation: IRA compensation limit, spousal IRA rule, head/spouse-only
traditional IRA deduction, and the 2026 IRA dollar limits (policyengine-us 1.755.4).

Defect (engine_defect): 1.755.4 caps IRA contributions only at the dollar limit
(ira_contribution_limit = limit.ira + catch-up). It never applies the compensation
limit of IRC 219(b)(1)(B), and the tax unit's above-the-line deduction
(`adds = gov.irs.ald.deductions`) sums traditional_ira_contributions over every
member of the tax unit, dependents included.

Rules encoded (tax year 2026), each read this session on law.cornell.edu/uscode/text/26/219
and IRS Publication 590-A (2025 edition, irs.gov/publications/p590a):

1. 219(b)(1): the IRA limit is the lesser of (A) the deductible amount and
   (B) the compensation includible in the individual's gross income.
   408A(c)(2) makes the same 219(b)(1) limit (less traditional contributions)
   the Roth IRA limit, so the cap applies to the combined traditional + Roth
   amount. The engine's existing proportional scaling (ira_contribution_scale)
   then allocates the combined limit between traditional and Roth.
2. 219(f)(1) compensation = wages includible in gross income (Pub 590-A: the
   amount properly shown in W-2 box 1; engine: irs_employment_income, i.e.
   employment_income less pre-tax 401(k)/403(b)/health/HSA payroll deductions)
   plus earned income under 401(c)(2) (Pub 590-A: net earnings from self-
   employment reduced by the deductible part of SE tax and the deduction for
   SE retirement plan contributions). Pub 590-A: a net SE loss is not
   subtracted from wages, so SE earnings are floored at 0. Pensions, annuities,
   IRA distributions, Social Security, interest, dividends, capital gains and
   rents are not compensation. The engine does not include alimony_income in
   IRS gross income, so the 219(f)(1) pre-2019 alimony rule adds nothing here.
3. 219(c) (Kay Bailey Hutchison spousal IRA): on a joint return, an individual
   whose compensation is less than the spouse's uses own compensation plus the
   spouse's compensation reduced by the spouse's IRA deduction, designated
   nondeductible contributions and Roth IRA contributions
   (219(c)(1)(B)(ii)(I)-(III)), i.e. the spouse's total IRA contributions.
4. 219(a): the deduction is for the individual's own contributions. On a return
   the deduction belongs to the filer and, on a joint return, the spouse; a
   dependent's contributions are deducted (if at all) on the dependent's own
   return, never on the parents' return. traditional_ira_contributions is
   zeroed for anyone who is not the tax-unit head or spouse.
5. 219(b)(5)(A)/(B) dollar amounts for 2026 from IRS Notice 2025-67 ("2026
   Amounts Relating to Retirement Plans and IRAs"; irs.gov/pub/irs-drop/n-25-67.pdf,
   text read this session): deductible amount increased from $7,000 to $7,500;
   the 219(b)(5)(B)(ii) age-50 catch-up increased from $1,000 to $1,100
   (indexed since 2024 by 219(b)(5)(C)(iii), added by SECURE 2.0). IRS news
   release IR-2025-111 (Nov. 13, 2025) states the same two figures. 1.755.4
   projects $7,000 and $1,000 for 2026.

Out of scope and left untouched: the 219(g) active-participant phase-out (r02),
the 408A(c)(3) Roth income phase-out, and the 401(c)(2)(A)(i) material-services
test (assumed met for Schedule C/F and partnership SE earnings).
"""

from policyengine_core.periods import period as make_period
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *

FIX_ID = "r01_ira_compensation"
DESCRIPTION = (
    "Cap combined traditional+Roth IRA contributions at 219(f)(1) compensation "
    "(219(b)(1)(B), 408A(c)(2)) with the 219(c) spousal rule; deduct traditional "
    "IRA contributions only for the tax-unit head and spouse (219(a)); set the "
    "2026 IRA dollar limit to $7,500 and catch-up to $1,100 (Notice 2025-67)."
)

SE_EARNINGS_SOURCES = [
    # Same 1402(a) sources the engine uses in taxable_self_employment_income.
    "self_employment_income",
    "sstb_self_employment_income",
    "farm_operations_income",
    "partnership_self_employment_net_earnings",
]


class ira_compensation(Variable):
    value_type = float
    entity = Person
    label = "Compensation for IRA contribution limits"
    unit = USD
    documentation = (
        "IRC 219(f)(1) compensation: wages includible in gross income plus "
        "401(c)(2) earned income from self-employment (net earnings less the "
        "deductible part of SE tax and SE retirement plan deductions), with a "
        "net SE loss not offsetting wages (IRS Pub. 590-A)."
    )
    definition_period = YEAR
    reference = (
        "https://www.law.cornell.edu/uscode/text/26/219#f_1",
        "https://www.law.cornell.edu/uscode/text/26/401#c_2",
        "https://www.irs.gov/publications/p590a",
    )

    def formula(person, period, parameters):
        wages = person("irs_employment_income", period)
        se_earnings = (
            add(person, period, SE_EARNINGS_SOURCES)
            - person("self_employment_tax_ald_person", period)
            - person("self_employed_pension_contribution_ald_person", period)
        )
        return wages + max_(0, se_earnings)


def _dollar_limit(person, period, parameters):
    p = parameters(period).gov.irs.gross_income.retirement_contributions
    catch_up_eligible = person("age", period) >= p.catch_up.age_threshold
    return p.limit.ira + where(catch_up_eligible, p.catch_up.limit.ira, 0)


def _make_ira_contribution_limit(spousal_rule: bool = True):
    class ira_contribution_limit(Variable):
        value_type = float
        entity = Person
        label = "IRA contribution limit"
        unit = USD
        documentation = (
            "Combined traditional and Roth IRA limit: the lesser of the "
            "219(b)(5) deductible amount (with the age-50 catch-up) and "
            "219(f)(1) compensation, with the 219(c) spousal rule on joint "
            "returns (219(b)(1), 219(c), 408A(c)(2))."
        )
        definition_period = YEAR
        reference = (
            "https://www.law.cornell.edu/uscode/text/26/219#b_1",
            "https://www.law.cornell.edu/uscode/text/26/219#c",
            "https://www.law.cornell.edu/uscode/text/26/408A#c_2",
        )

        def formula(person, period, parameters):
            dollar = _dollar_limit(person, period, parameters)
            comp = person("ira_compensation", period)
            if not spousal_rule:
                return min_(dollar, comp)
            head_or_spouse = person("is_tax_unit_head_or_spouse", period)
            joint = person.tax_unit("tax_unit_is_joint", period)
            # The spouse's compensation (head and spouse only).
            unit_comp = person.tax_unit.sum(comp * head_or_spouse)
            spouse_comp = where(head_or_spouse, unit_comp - comp, 0)
            # 219(c)(2): applies on a joint return to the spouse with less
            # compensation. The other spouse is limited by own compensation,
            # so the other spouse's total IRA contributions are
            # min(desired traditional + Roth, dollar, own compensation).
            desired = add(
                person,
                period,
                [
                    "traditional_ira_contributions_desired",
                    "roth_ira_contributions_desired",
                ],
            )
            own_contribution = min_(desired, min_(dollar, comp))
            unit_contribution = person.tax_unit.sum(own_contribution * head_or_spouse)
            spouse_contribution = where(
                head_or_spouse, unit_contribution - own_contribution, 0
            )
            spousal = joint & head_or_spouse & (comp < spouse_comp)
            # 219(c)(1)(B): own compensation plus the spouse's compensation
            # reduced by the spouse's deduction, nondeductible and Roth
            # contributions.
            spousal_comp = comp + max_(spouse_comp - spouse_contribution, 0)
            return min_(dollar, where(spousal, spousal_comp, comp))

    return ira_contribution_limit


def _make_traditional_ira_contributions(dependent_mask: bool = True):
    class traditional_ira_contributions(Variable):
        value_type = float
        entity = Person
        label = "Traditional IRA contributions"
        unit = USD
        documentation = (
            "Traditional IRA contributions deductible on this tax unit's "
            "return: desired contributions scaled to the combined IRA limit "
            "(dollar and compensation), for the tax-unit head and spouse only "
            "(219(a))."
        )
        definition_period = YEAR
        reference = (
            "https://www.law.cornell.edu/uscode/text/26/219#a",
            "https://www.law.cornell.edu/uscode/text/26/219#b",
        )

        def formula(person, period, parameters):
            desired = person("traditional_ira_contributions_desired", period)
            scale = person("ira_contribution_scale", period)
            if not dependent_mask:
                return desired * scale
            head_or_spouse = person("is_tax_unit_head_or_spouse", period)
            return desired * scale * head_or_spouse

    return traditional_ira_contributions


def _set_2026_dollar_limits(parameters):
    # IRS Notice 2025-67: 219(b)(5)(A) $7,500; 219(b)(5)(B)(ii) $1,100 for 2026.
    rc = parameters.gov.irs.gross_income.retirement_contributions
    year_2026 = make_period("year:2026-01-01:1")
    rc.limit.ira.update(period=year_2026, value=7_500)
    rc.catch_up.limit.ira.update(period=year_2026, value=1_100)
    return parameters


def build_reform(
    dollar_limits: bool = True,
    compensation_cap: bool = True,
    spousal_rule: bool = True,
    dependent_mask: bool = True,
):
    """Build the fix, or a component of it for attribution runs."""

    class r01_ira_compensation_reform(Reform):
        def apply(self):
            if dollar_limits:
                self.modify_parameters(_set_2026_dollar_limits)
            if compensation_cap:
                self.update_variable(ira_compensation)
                self.update_variable(_make_ira_contribution_limit(spousal_rule))
            if dependent_mask:
                self.update_variable(_make_traditional_ira_contributions(True))

    return r01_ira_compensation_reform


reform = build_reform()
