"""r02: apply the IRC 219(g) active-participant phase-out to the traditional IRA deduction.

Defect in policyengine-us 1.755.4
---------------------------------
`gov.irs.ald.deductions` (2026-01-01 list) names `traditional_ira_contributions`
directly as an above-the-line deduction. That variable is
`traditional_ira_contributions_desired * ira_contribution_scale`, which applies
only the combined 219(b)(1)(A) / 408A(c)(2) dollar cap. Nothing in the package
tests active participation or 219(g); the whole contribution is deducted at any
income. (Issue #8388 / PR #8416 left 219(g) "out of scope"; no follow-up exists.)

Law encoded (tax year 2026)
---------------------------
* IRC 219(g)(1): if the individual or the individual's spouse is an active
  participant, the dollar limitations in 219(b)(1)(A) and 219(c)(1)(A) are
  reduced (not below zero) by the amount in 219(g)(2).
* 219(g)(2)(A): reduction = limitation x (MAGI - applicable dollar amount) /
  $10,000 ($20,000 on a joint return).
* 219(g)(2)(B): no limitation is reduced below $200 unless it is reduced to zero.
* 219(g)(2)(C): an amount determined under (g)(2) that is not a multiple of $10
  is rounded to the next lowest $10 (Pub. 590-A Worksheet 1-2 line 4 states the
  same thing as rounding the remaining limit UP to the next $10).
* 219(g)(3)(A): MAGI is AGI determined after sections 86 and 469 and without
  regard to sections 85(c), 135, 137, 221 and 911 or the 219 deduction itself.
  Engine terms: gross income with full unemployment compensation (85(c)
  disregarded; `unemployment_compensation` instead of the AGI-dependent
  `taxable_unemployment_compensation`), plus taxable Social Security figured
  WITHOUT the IRA deduction (Pub. 590-A Appendix B, Worksheet 1 lines 1-17), minus
  every 2026 ALD except the IRA deduction, `student_loan_interest_ald` (221),
  `us_bonds_for_higher_ed` (135) and `qualified_adoption_assistance_expense`
  (137). The engine has no 911 exclusion. 931/933 items stay subtracted because
  219(g)(3)(A) does not add them back (Pub. 590-A Worksheet 1-1 lines 1-6).
* 219(g)(3)(B), 219(g)(7), 219(g)(8), and IRS Notice 2025-67 (IR-2025-111,
  Nov. 13, 2025), 2026 amounts:
    - active participant, joint return or qualifying widow(er): $129,000-$149,000
    - active participant, single or head of household: $81,000-$91,000
    - active participant, married filing separately: $0-$10,000 (not indexed)
    - not an active participant, spouse is (219(g)(7)), joint: $242,000-$252,000
  Width is $20,000 for an active participant on a joint (or QSS, per Notice
  2025-67 and Pub. 590-A Worksheet 1-2's 35%/40% multipliers) return, and
  $10,000 otherwise (219(g)(2)(A)(ii), 219(g)(7)(B)).
* 219(g)(4): spouses who file separately and live apart all year are not treated
  as married; the engine flag `cohabitating_spouses` (default False) marks the
  lived-together case.
* 219(g)(5): an active participant includes a participant in a 401(a) plan, a
  403(b) annuity contract, a SEP (408(k)) and a SIMPLE (408(p)). Pub. 590-A: a
  person is covered by a defined contribution plan for a year in which "amounts
  are contributed or allocated to your account"; the Form W-2 box 13
  instructions say the same for employee contributions. Treated as active
  participation here: any positive `traditional_401k_contributions`,
  `roth_401k_contributions`, `traditional_403b_contributions` or
  `roth_403b_contributions` (elective deferrals, pre-tax or designated Roth, are
  contributions added to the participant's 401(a)/403(b) account), provided the
  person has wages or self-employment earnings to defer from (under a 401(k)
  arrangement the employee elects to have the employer contribute instead of
  paying cash, 401(k)(2)(A), and 415(c)(1)(B) caps annual additions at 100% of
  compensation; the engine does not cap deferrals at compensation), or any positive `self_employed_pension_contributions` (the
  engine's SEP/SIMPLE/Keogh input, already capped at SE income). The deferral
  variables are the engine's post-402(g)-limit values, positive exactly when the
  desired input is positive. No other engine input identifies plan coverage, so
  employer-only contributions and defined-benefit coverage cannot be seen.
  REQUIRE_COMPENSATION_FOR_DEFERRALS = False gives the "engine inputs only"
  reading; in the 100 PolicyBench households it changes only scenario_003.

Changes
-------
1. New Person variable `traditional_ira_deduction` = min(traditional IRA
   contributions, the 219(g)-reduced deductible amount). The deductible amount
   before reduction is the 219(b)(5) dollar limit plus catch-up, computed from
   the same parameters and formula as the engine's `ira_contribution_limit`, so
   the separate stale-2026-limit issue (engine $7,000/$1,000 vs. law
   $7,500/$1,100, fixed in r01) is NOT changed by this fix.
2. `gov.irs.ald.deductions` (2026 onward): `traditional_ira_contributions` ->
   `traditional_ira_deduction`. Every reader of the list follows: AGI,
   adjusted_gross_income_person, Section 86 MAGI (which correctly includes the
   219 deduction), the 221 MAGI, taxable_uc_agi, Medicaid AGI.
3. State lists that name the old variable as a deduction are kept consistent:
   - MA `gov.states.ma.tax.income.ald.disallowed` also disallows the new
     variable, so MA behavior is unchanged (M.G.L. c.62 s.2(d)(1)(F)).
   - MS `gov.states.ms.tax.income.adjustments.adjustments` (line 50) uses the new
     variable: the 2025 MS resident instructions (Form 80-100, line 50) allow IRA
     payments only "to the extent contributions are deductible for federal
     income tax purposes".
   `traditional_ira_contributions` itself is unchanged, so readers that need
   contributions (saver's credit under 25B/219(e), MN/UT household-income
   add-backs, PR, CRFB contrib, Riverside GR) are untouched.
"""

from __future__ import annotations

from policyengine_core.parameters import ParameterNode
from policyengine_core.periods import instant
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *  # noqa: F401,F403

FIX_ID = "r02_ira_219g"
DESCRIPTION = (
    "IRC 219(g) active-participant phase-out of the traditional IRA deduction "
    "(2026 ranges from Notice 2025-67; MAGI per 219(g)(3)(A) with Section 86 "
    "benefits figured before the IRA deduction per Pub. 590-A App. B; reduction "
    "rounded down to $10, $200 floor). Active participant = any 401(k)/403(b) "
    "elective deferral (traditional or Roth) by a person with wages or SE "
    "earnings, or any SEP/SIMPLE/Keogh contribution."
)

START = "2026-01-01"
OLD = "traditional_ira_contributions"
NEW = "traditional_ira_deduction"

# ALDs 219(g)(3)(A)(ii) disregards: the 219 deduction itself, 221, 135, 137.
MAGI_DISREGARDED_ALDS = (
    OLD,
    NEW,
    "student_loan_interest_ald",
    "us_bonds_for_higher_ed",
    "qualified_adoption_assistance_expense",
)

ELECTIVE_DEFERRALS = [
    "traditional_401k_contributions",
    "roth_401k_contributions",
    "traditional_403b_contributions",
    "roth_403b_contributions",
]
# Earned-income sources an elective deferral can come out of: wages, or
# 401(c)(2) self-employment earnings for a self-employed 401(k).
SE_EARNINGS_SOURCES = [
    "self_employment_income",
    "sstb_self_employment_income",
    "farm_operations_income",
    "partnership_self_employment_net_earnings",
]
# Set False to reproduce the "engine inputs only" reading (deferral inputs
# count even when the person has no compensation to defer).
REQUIRE_COMPENSATION_FOR_DEFERRALS = True

_FS = ("SINGLE", "JOINT", "SEPARATE", "HEAD_OF_HOUSEHOLD", "SURVIVING_SPOUSE")


def _by_fs(values_2025: dict, values_2026: dict) -> dict:
    return {
        fs: {"values": {"2025-01-01": values_2025[fs], "2026-01-01": values_2026[fs]}}
        for fs in _FS
    }


# IRS Notice 2025-67 section on 219(g) (2025 values from Notice 2024-80 as
# restated in Notice 2025-67 "increased from" clauses and Pub. 590-A (2025)
# Worksheet 1-2).
PARAMETER_DATA = {
    "description": "IRC 219(g) active-participant phase-out (sandbox fix r02).",
    # Applicable dollar amount when the contributor is an active participant.
    "covered_start": _by_fs(
        dict(SINGLE=79_000, HEAD_OF_HOUSEHOLD=79_000, JOINT=126_000,
             SURVIVING_SPOUSE=126_000, SEPARATE=0),
        dict(SINGLE=81_000, HEAD_OF_HOUSEHOLD=81_000, JOINT=129_000,
             SURVIVING_SPOUSE=129_000, SEPARATE=0),
    ),
    # 219(g)(2)(A)(ii): $20,000 on a joint return (QSS per Notice 2025-67 and
    # Pub. 590-A Worksheet 1-2), $10,000 otherwise.
    "covered_width": _by_fs(
        dict(SINGLE=10_000, HEAD_OF_HOUSEHOLD=10_000, JOINT=20_000,
             SURVIVING_SPOUSE=20_000, SEPARATE=10_000),
        dict(SINGLE=10_000, HEAD_OF_HOUSEHOLD=10_000, JOINT=20_000,
             SURVIVING_SPOUSE=20_000, SEPARATE=10_000),
    ),
    # 219(g)(7)(A): contributor not active, spouse active (joint return).
    "spouse_covered_start": {"values": {"2025-01-01": 236_000, "2026-01-01": 242_000}},
    # 219(g)(7)(B).
    "spouse_covered_width": {"values": {"2025-01-01": 10_000, "2026-01-01": 10_000}},
    # 219(g)(3)(B)(iii): MFS (lived with spouse), not indexed.
    "separate_start": {"values": {"2025-01-01": 0, "2026-01-01": 0}},
    "separate_width": {"values": {"2025-01-01": 10_000, "2026-01-01": 10_000}},
    # 219(g)(2)(C) and (B).
    "rounding": {"values": {"2025-01-01": 10}},
    "floor": {"values": {"2025-01-01": 200}},
}


class ira_active_participant(Variable):
    value_type = bool
    entity = Person
    label = "Active participant in an employer plan for IRC 219(g)"
    definition_period = YEAR
    reference = "https://www.law.cornell.edu/uscode/text/26/219#g_5"

    def formula(person, period, parameters):
        deferrals = add(person, period, ELECTIVE_DEFERRALS) > 0
        if REQUIRE_COMPENSATION_FOR_DEFERRALS:
            # A 401(k) deferral is pay the employee elects to have contributed
            # instead of received in cash (401(k)(2)(A)), and 415(c)(1)(B) caps
            # annual additions at 100% of compensation. With no wages or
            # self-employment earnings nothing can be deferred, no amount
            # reaches the account, and the person is not an active participant
            # through that input (the engine does not cap deferrals at
            # compensation; irs_employment_income floors at 0).
            wages = max_(0, person("employment_income", period))
            se = max_(0, add(person, period, SE_EARNINGS_SOURCES))
            deferrals = deferrals & ((wages + se) > 0)
        # self_employed_pension_contributions is already capped at
        # self-employment income by the engine (415(c) limit variable).
        sep = person("self_employed_pension_contributions", period) > 0
        return deferrals | sep


class ira_219g_taxable_social_security(Variable):
    """Section 86 taxable benefits figured without the IRA deduction.

    Pub. 590-A Appendix B, Worksheet 1 lines 1-17. Same inputs and thresholds as
    the engine's taxable_ss_magi / tax_unit_taxable_social_security, except that
    the IRA deduction is not subtracted (it is what is being computed).
    """

    value_type = float
    entity = TaxUnit
    label = "Taxable Social Security for 219(g) MAGI (before the IRA deduction)"
    unit = USD
    definition_period = YEAR
    reference = "https://www.law.cornell.edu/uscode/text/26/219#g_3_A"

    def formula(tax_unit, period, parameters):
        irs = parameters(period).gov.irs
        p = irs.social_security.taxability
        # taxable_ss_magi, with the IRA deduction removed from the ALDs.
        sources = [
            s
            for s in irs.gross_income.sources
            if s not in ["taxable_social_security", "taxable_unemployment_compensation"]
        ]
        if "taxable_unemployment_compensation" in irs.gross_income.sources:
            sources.append("unemployment_compensation")
        sources.append("tax_exempt_interest_income")
        person = tax_unit.members
        not_dependent = ~person("is_tax_unit_dependent", period)
        gross = 0
        for source in sources:
            gross += not_dependent * max_(0, add(person, period, [source]))
        gross = tax_unit.sum(gross)
        revoked = p.income.revoked_deductions
        deductions = [
            d
            for d in irs.ald.deductions
            if d not in revoked and d not in (OLD, NEW)
        ]
        ss_magi = max_(0, gross - add(tax_unit, period, deductions))
        # tax_unit_taxable_social_security, with that MAGI.
        gross_ss = tax_unit("tax_unit_social_security_for_taxability", period)
        combined = ss_magi + p.combined_income_ss_fraction * gross_ss
        filing_status = tax_unit("filing_status", period)
        separate = filing_status == filing_status.possible_values.SEPARATE
        cohabitating = tax_unit("cohabitating_spouses", period)
        base = where(
            separate & cohabitating,
            p.threshold.base.separate_cohabitating,
            p.threshold.base.main[filing_status],
        )
        adjusted_base = where(
            separate & cohabitating,
            p.threshold.adjusted_base.separate_cohabitating,
            p.threshold.adjusted_base.main[filing_status],
        )
        excess = max_(0, combined - base)
        over_adjusted = max_(0, combined - adjusted_base)
        tier1 = min_(p.rate.base.benefit_cap * gross_ss, p.rate.base.excess * excess)
        bracket = min_(tier1, p.rate.additional.bracket * (adjusted_base - base))
        tier2 = min_(
            p.rate.additional.excess * over_adjusted + bracket,
            p.rate.additional.benefit_cap * gross_ss,
        )
        return select(
            [combined < base, combined < adjusted_base], [0, tier1], default=tier2
        )


class ira_219g_magi(Variable):
    value_type = float
    entity = TaxUnit
    label = "Modified AGI for the IRC 219(g) IRA deduction phase-out"
    unit = USD
    definition_period = YEAR
    reference = "https://www.law.cornell.edu/uscode/text/26/219#g_3_A"

    def formula(tax_unit, period, parameters):
        irs = parameters(period).gov.irs
        sources = [
            s
            for s in irs.gross_income.sources
            if s not in ["taxable_social_security", "taxable_unemployment_compensation"]
        ]
        if "taxable_unemployment_compensation" in irs.gross_income.sources:
            # 219(g)(3)(A)(ii): without regard to 85(c).
            sources.append("unemployment_compensation")
        person = tax_unit.members
        not_dependent = ~person("is_tax_unit_dependent", period)
        gross = 0
        for source in sources:
            gross += not_dependent * max_(0, add(person, period, [source]))
        gross = tax_unit.sum(gross)
        # 219(g)(3)(A)(i): after section 86 (benefits figured before the IRA
        # deduction, Pub. 590-A App. B Worksheet 1 line 17).
        gross += tax_unit("ira_219g_taxable_social_security", period)
        deductions = [d for d in irs.ald.deductions if d not in MAGI_DISREGARDED_ALDS]
        magi = gross - add(tax_unit, period, deductions)
        if parameters(period).gov.contrib.ubi_center.basic_income.taxable:
            magi += add(tax_unit, period, ["basic_income"])
        return magi


class ira_219g_deductible_limit(Variable):
    value_type = float
    entity = Person
    label = "Traditional IRA deductible amount after the IRC 219(g) reduction"
    unit = USD
    definition_period = YEAR
    reference = "https://www.law.cornell.edu/uscode/text/26/219#g"

    def formula(person, period, parameters):
        p = parameters(period).gov.irs.ald.ira_219g
        # The dollar limitation 219(g)(1) reduces: the 219(b)(1)(A) deductible
        # amount (219(b)(5)(A) plus the 219(b)(5)(B) catch-up), computed from
        # the same parameters and formula as the engine's ira_contribution_limit
        # (identical to it in 1.755.4). Read from parameters rather than from
        # ira_contribution_limit so that, if another fix adds the 219(b)(1)(B)
        # compensation cap to ira_contribution_limit, 219(g) still reduces only
        # the dollar amount, as the statute says; compensation stays a separate
        # cap already embedded in traditional_ira_contributions.
        rc = parameters(period).gov.irs.gross_income.retirement_contributions
        catch_up_eligible = person("age", period) >= rc.catch_up.age_threshold
        limit = rc.limit.ira + where(catch_up_eligible, rc.catch_up.limit.ira, 0)
        tax_unit = person.tax_unit
        filing_status = tax_unit("filing_status", period)
        fs = filing_status.possible_values
        joint = filing_status == fs.JOINT
        separate = filing_status == fs.SEPARATE
        # 219(g)(4): MFS spouses who lived apart all year are not treated as
        # married (single range, spouse's participation disregarded).
        separate_married = separate & tax_unit("cohabitating_spouses", period)
        separate_apart = separate & ~separate_married
        self_active = person("ira_active_participant", period)
        is_head = person("is_tax_unit_head", period)
        is_spouse = person("is_tax_unit_spouse", period)
        head_active = tax_unit.any(is_head & self_active)
        spouse_active = tax_unit.any(is_spouse & self_active)
        other_active = where(is_head, spouse_active, where(is_spouse, head_active, False))
        # 219(g)(7) applies to a married contributor who is not active but
        # whose spouse is. (For MFS the engine keeps the spouse in another tax
        # unit, so this branch can only fire on a joint return here.)
        spouse_route = ~self_active & other_active & (joint | separate_married)
        covered = self_active | spouse_route
        # 219(g)(3)(B): applicable dollar amount; (2)(A)(ii) width.
        self_start = where(
            separate_married,
            p.separate_start,
            where(separate_apart, p.covered_start.SINGLE, p.covered_start[filing_status]),
        )
        self_width = where(
            separate_married,
            p.separate_width,
            where(separate_apart, p.covered_width.SINGLE, p.covered_width[filing_status]),
        )
        start = where(
            self_active,
            self_start,
            where(separate_married, p.separate_start, p.spouse_covered_start),
        )
        width = where(
            self_active,
            self_width,
            where(separate_married, p.separate_width, p.spouse_covered_width),
        )
        magi = tax_unit("ira_219g_magi", period)
        excess = max_(0, magi - start)
        full_phase_out = excess >= width
        raw_reduction = limit * min_(1, excess / width)
        # 219(g)(2)(C): round the reduction down to the next lowest $10.
        reduction = np.floor(np.round(raw_reduction, 6) / p.rounding) * p.rounding
        reduced = max_(0, limit - reduction)
        reduced = where(full_phase_out, 0, reduced)
        # 219(g)(2)(B): $200 floor unless the limitation is reduced to zero.
        reduced = where((reduced > 0) & (reduced < p.floor), p.floor, reduced)
        return where(covered, reduced, limit)


class traditional_ira_deduction(Variable):
    value_type = float
    entity = Person
    label = "Traditional IRA deduction (IRC 219, with the 219(g) phase-out)"
    unit = USD
    definition_period = YEAR
    reference = "https://www.law.cornell.edu/uscode/text/26/219"

    def formula(person, period, parameters):
        contributions = person(OLD, period)
        return min_(contributions, person("ira_219g_deductible_limit", period))


def _swap_from(node, start: str, transform) -> None:
    """Apply transform to the list in force at `start` and every later dated value."""
    entries = sorted(node.values_list, key=lambda e: e.instant_str)
    starts = [e.instant_str for e in entries]
    if start not in starts:
        # Split the entry in force at `start` so that a value begins there.
        later = [s for s in starts if s > start]
        stop = instant(later[0]).offset(-1, "day") if later else None
        node.update(start=instant(start), stop=stop, value=list(node(start)))
        entries = sorted(node.values_list, key=lambda e: e.instant_str)
        starts = [e.instant_str for e in entries]
    for i, entry in enumerate(entries):
        if entry.instant_str < start:
            continue
        stop = instant(starts[i + 1]).offset(-1, "day") if i + 1 < len(entries) else None
        node.update(start=instant(entry.instant_str), stop=stop, value=transform(list(entry.value)))


def modify_parameters(parameters):
    if "ira_219g" not in parameters.gov.irs.ald.children:
        parameters.gov.irs.ald.add_child(
            "ira_219g", ParameterNode("gov.irs.ald.ira_219g", data=PARAMETER_DATA)
        )
    _swap_from(
        parameters.gov.irs.ald.deductions,
        START,
        lambda v: [NEW if x == OLD else x for x in v],
    )
    _swap_from(
        parameters.gov.states.ma.tax.income.ald.disallowed,
        START,
        lambda v: v + [NEW] if NEW not in v else v,
    )
    _swap_from(
        parameters.gov.states.ms.tax.income.adjustments.adjustments,
        START,
        lambda v: [NEW if x == OLD else x for x in v],
    )
    return parameters


REFORM_VARIABLES = [
    ira_active_participant,
    ira_219g_taxable_social_security,
    ira_219g_magi,
    ira_219g_deductible_limit,
    traditional_ira_deduction,
]


class reform(Reform):
    def apply(self):
        for variable in REFORM_VARIABLES:
            self.update_variable(variable)
        self.modify_parameters(modify_parameters)
