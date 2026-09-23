"""r08: EITC / ACTC earned income must exclude wages that are not includible in gross income.

Law
---
IRC 32(c)(2)(A)(i) defines EITC earned income as "wages, salaries, tips, and
other employee compensation, but only if such amounts are includible in gross
income for the taxable year" (clause added by EGTRRA, Pub. L. 107-16, sec.
303(b), effective for tax years beginning after 2001; unchanged in the current
Cornell LII text).  A traditional 401(k)/403(b) elective deferral is excluded
from gross income by IRC 402(e)(3) (up to the 402(g) limit, which the engine
already applies through elective_deferral_contribution_scale), and cafeteria-plan
health premiums / HSA payroll contributions are excluded by IRC 125 / 106.
The IRS EIC worksheet (Form 1040 instructions, Step 5 line 1) and the Schedule
8812 Earned Income Worksheet (line 1a) both start from Form 1040 line 1z, i.e.
W-2 box 1, which omits those amounts.

IRC 24(d)(1)(B)(i) computes the refundable CTC (ACTC) phase-in on "earned
income (within the meaning of section 32)", so the ACTC follows the same base.
In policyengine-us 1.755.4 that happens automatically:
ctc_phase_in_relevant_earnings reads eitc_earned_income.

State credits built on the same definition
-----------------------------------------
State EITCs that are a percentage of the federal EITC (MT, VA, NY, WI, CO, ...)
move downstream with no further change.  State credits that recompute a
federal-style EITC read filer_adjusted_earnings instead, which in 1.755.4 is
also built from gross employment_income:
  - California CalEITC and Young Child Tax Credit.  R&TC 17052(c)(4)(A) keeps
    the IRC 32(c)(2)(A)(i) "includible in gross income" clause and adds "and
    only if such amounts are subject to withholding pursuant to Division 6 ...
    of the Unemployment Insurance Code"; FTB 3514 (2025) line 13 takes W-2 box
    16 California wages.  EDD DE 231TP lists employee 401(k) contributions as
    "Not subject" to PIT withholding and "Not reportable" as PIT wages when not
    includible in California gross income (CUIC 13009(i)(1), 13009(q),
    13009.5).  R&TC 17052.1 (YCTC) uses the same earned income.
  - the state_eitc_helpers federal-style EITC (CO ITIN / under-25 branches, IL,
    IN, DC with qualifying child), IN decoupled, MN WFC, OK frozen-2020 federal
    EITC, WA WFTC: each mirrors the IRC 32 computation.
For 2026 filer_adjusted_earnings uses federal box-1 wages outside CA;
CA uses state-taxable wages, retaining payroll HSA contributions.  Its only other
consumer, the AMT kiddie-tax exemption cap (IRC 59(j), earned income per IRC
911(d)(2)), is not an EITC/ACTC base; amt_exemption is re-pointed at the
original gross sum so the AMT is left exactly as it was.

Everything else is unchanged: the self-employment terms, the SE-tax ALD, the
per-person zero floor, and the person-level earned_income variable (used by the
CDCC, IRA limits, benefit programs, ...).
"""

# Independent verifier corrections: constrain this sandbox to 2026; retain
# California-taxable payroll HSA contributions in state earned income.
# Sources: FTB 3514 line 13 (W-2 box 16), EDD DE 231EB p. 3 HSA row:
# https://www.ftb.ca.gov/forms/2025/2025-3514-booklet.html
# https://edd.ca.gov/siteassets/files/pdf_pub_ctr/de231eb.pdf
from policyengine_us.variables.gov.irs.credits.earned_income.eitc_earned_income import eitc_earned_income as baseline_eitc
from policyengine_us.variables.gov.irs.income.filer_adjusted_earnings import filer_adjusted_earnings as baseline_filer
from policyengine_us.variables.gov.irs.tax.federal_income.alternative_minimum_tax.exemption.amt_exemption import amt_exemption as baseline_amt
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *  # noqa: F401,F403

FIX_ID = "r08_eitc_earned_income_deferrals_v2"
DESCRIPTION = (
    "2026 EITC/ACTC and federal-style state credit earnings exclude qualifying "
    "pre-tax payroll contributions under IRC 32(c)(2)(A)(i), 24(d)(1)(B)(i), "
    "and 402(e)(3). California earnings retain payroll HSA contributions, "
    "which are state-taxable wages under R&TC 17052(c)(4)(A) and EDD DE 231EB."
)


class eitc_earned_income(Variable):
    value_type = float
    entity = TaxUnit
    label = "Earned income for the EITC"
    unit = USD
    definition_period = YEAR
    reference = (
        "https://www.law.cornell.edu/uscode/text/26/32#c_2",
        "https://www.law.cornell.edu/uscode/text/26/402#e_3",
        "https://www.irs.gov/instructions/i1040gi",
    )

    def formula(tax_unit, period, parameters):
        if period.start.year != 2026:
            return baseline_eitc.formula(tax_unit, period, parameters)
        earned_income_sources = [
            # IRC 32(c)(2)(A)(i): wages only if includible in gross income,
            # i.e. W-2 box 1 (employment_income less pre_tax_contributions).
            "irs_employment_income",
            "self_employment_income",
            "sstb_self_employment_income",
            "farm_operations_income",
            "partnership_self_employment_net_earnings",
        ]
        gross_earned_income = sum(
            tax_unit_non_dep_sum(source, tax_unit, period)
            for source in earned_income_sources
        )
        self_employment_tax_ald = tax_unit_non_dep_sum(
            "self_employment_tax_ald_person", tax_unit, period
        )
        return max_(0, gross_earned_income - self_employment_tax_ald)


class filer_adjusted_earnings(Variable):
    value_type = float
    entity = TaxUnit
    definition_period = YEAR
    label = "Filer earned income adjusted for self-employment tax"
    unit = USD

    def formula(tax_unit, period, parameters):
        if period.start.year != 2026:
            return baseline_filer.formula(tax_unit, period, parameters)
        # Same as 1.755.4 (sum over non-dependents of adjusted_earnings) except
        # that wages excluded from gross income (pre_tax_contributions, as
        # already subtracted in irs_employment_income) are removed first.
        person = tax_unit.members
        p = parameters(period).gov.irs.ald.misc
        se_adjustment = (
            (1 - p.self_emp_tax_adj)
            * p.employer_share
            * person("self_employment_tax", period)
        )
        excluded_wages = person("employment_income", period) - person(
            "irs_employment_income", period
        )
        # Federal box 1 excludes payroll HSA; California box 16 does not.
        # Compute the CA exclusion directly so the existing wage zero floor
        # also behaves correctly when claimed payroll deductions exceed wages.
        ca_exclusions = add(person, period, [
            "traditional_401k_contributions",
            "traditional_403b_contributions",
            "pre_tax_health_insurance_premiums",
        ])
        ca_wages = max_(0, person("employment_income", period) - ca_exclusions)
        excluded_wages = where(
            person.household("state_code", period) == StateCode.CA,
            person("employment_income", period) - ca_wages,
            excluded_wages,
        )
        adjusted = max_(
            0, person("earned_income", period) - excluded_wages - se_adjustment
        )
        is_dependent = person("is_tax_unit_dependent", period)
        return tax_unit.sum(adjusted * ~is_dependent)


class amt_exemption(Variable):
    value_type = float
    entity = TaxUnit
    definition_period = YEAR
    label = "Alternative Minimum Tax exemption"
    unit = USD
    documentation = (
        "AMT exemption amount after phase-out and kiddie tax adjustments. "
        "Form 6251, Line 5."
    )
    reference = [
        "https://www.law.cornell.edu/uscode/text/26/55#d",
        "https://www.irs.gov/instructions/i6251",
    ]

    def formula(tax_unit, period, parameters):
        if period.start.year != 2026:
            return baseline_amt.formula(tax_unit, period, parameters)
        # Verbatim 1.755.4 formula, except the kiddie-tax cap reads the
        # original gross adjusted-earnings sum so this fix leaves the AMT
        # unchanged.
        p = parameters(period).gov.irs.income.amt
        phase_out = p.exemption.phase_out
        filing_status = tax_unit("filing_status", period)
        amt_income = tax_unit("amt_income", period)
        base_exemption_amount = p.exemption.amount[filing_status]
        income_excess = max_(0, amt_income - phase_out.start[filing_status])
        exemption_phase_out = phase_out.rate * income_excess
        reduced_exemption_amount = max_(
            0,
            base_exemption_amount - exemption_phase_out,
        )
        kiddie_tax_applies = tax_unit("amt_kiddie_tax_applies", period)
        adj_earnings = tax_unit_non_dep_sum("adjusted_earnings", tax_unit, period)
        child_amount = p.exemption.child.amount
        exemption_cap = where(
            kiddie_tax_applies,
            adj_earnings + child_amount,
            np.inf,
        )
        return min_(reduced_exemption_amount, exemption_cap)


class reform(Reform):
    def apply(self):
        self.update_variable(eitc_earned_income)
        self.update_variable(filer_adjusted_earnings)
        self.update_variable(amt_exemption)
