"""r06 v2: Wisconsin elected-path reporting with optimized joint pooling.

V2 correction
-------------
For a joint return with both spouses age 67+, line 16 has a pooled limit.
The original fix imposed proportional allocation between spouses, which can
unnecessarily reduce the separate line-17 subtractions. V2 allocates the pooled
subtraction first against income exceeding the existing line-17 entitlement.
The maximum preserved line-17 total is the lesser of that entitlement and
qualifying retirement income remaining after line 16. Single and non-pooled
paths retain the original arithmetic; no age, income base, or dollar parameter
is changed.

Root cause
----------
policyengine-us 1.755.4 models the 2025 Wis. Act 15 retirement income
subtraction (Wis. Stat. 71.05(6)(b)54m; Schedule SB line 16) only inside
``wi_income_tax``, which returns min(standard net tax, exclusion-path tax).
The benchmarked output ``state_income_tax_before_refundable_credits`` sums
``wi_income_tax_before_refundable_credits``, which is always the
no-subtraction path (max(0, wi_income_tax_before_credits -
wi_non_refundable_credits)). When the filer elects line 16, the benchmark
therefore reports a tax that appears on no return the filer would file, and
state_income_tax != before_refundable - refundable.

Rule encoded (tax year 2026)
----------------------------
1. Election (Wis. Stat. 71.05(6)(b)54m.a-d, created by 2025 Wis. Act 15,
   "for taxable years beginning after December 31, 2024", no sunset). A
   filer with a head or spouse aged 67+ may subtract up to $24,000 of
   qualified-plan and IRA distributions per individual ($48,000 for a joint
   return when both spouses are 67+); claiming it forfeits every s. 71.07
   credit (54m.d). The 2025 Schedule SB instructions, line 16, apply the
   forfeiture to Schedule CR and Form 1 lines 13-20 and 30-35, i.e. every
   nonrefundable and refundable credit the engine models, including the
   homestead credit (Form 1 line 33). The filer elects line 16 only when it
   strictly lowers net tax (tax after all credits); ties stay on the standard
   path. This is the engine's own comparison in ``wi_income_tax``.
2. Exclusion-path tax. Line 16 is a subtraction from federal AGI in computing
   Wisconsin adjusted gross income (Wis. Stat. 71.01(13) includes every
   s. 71.05(6) modification; Form 1 line 7 "Wisconsin income" = line 5 minus
   Schedule SB line 50). The sliding-scale standard deduction is keyed to
   Wisconsin AGI (Wis. Stat. 71.05(22)(dp)1; Form 1 line 8 is looked up on
   line 7), so it is recomputed on the post-subtraction income. This is the
   same correction upstream made after 1.755.4 in commit 35bbe1ba0c
   (PolicyEngine/policyengine-us#8817/#8818). The $5,000 retirement income
   subtraction (Wis. Stat. 71.05(6)(b)54, Schedule SB line 17) applies
   "except as provided under subd. 54m": the 2025 Schedule SB line 17
   worksheet line 4 removes amounts already subtracted on line 16, so the
   engine's line-17 amount for each person is capped at that person's
   remaining qualified-plan and IRA income after line 16. Exemptions and rates
   are unchanged. No credits of any kind are applied on this path.
3. Outputs on the elected path:
   wi_income_tax_before_refundable_credits = exclusion-path tax (no
   nonrefundable credits) and wi_refundable_credits = 0 when line 16 is
   elected; otherwise both keep the engine's standard-path values. The
   engine's wi_income_tax formula is untouched; with these two inputs it
   returns exactly the elected-path net tax, so state_income_tax again equals
   state_income_tax_before_refundable_credits - state_refundable_credits.

Left alone: wi_agi, wi_standard_deduction, wi_taxable_income,
wi_income_tax_before_credits and wi_non_refundable_credits stay the engine's
standard-path intermediates. The engine's line-17 base (pension only, not IRA
distributions) and its per-person line-16 eligibility are not changed.

Set EXCLUSION_TAX_MODE = "engine" to keep the 1.755.4 exclusion-path tax
(taxable income minus line 16, standard deduction not recomputed, no line-17
offset) and change only the election plumbing; used to show the two variants
agree on this bundle.
"""

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *  # noqa: F401,F403

FIX_ID = "r06_wi_act15_before_refundable_v2"
DESCRIPTION = (
    "Preserve the largest permitted line 17 subtraction under joint line 16 pooling. "
    "Wisconsin: report wi_income_tax_before_refundable_credits and "
    "wi_refundable_credits on the path the filer elects under Wis. Stat. "
    "71.05(6)(b)54m (Sch. SB line 16), with the exclusion-path tax computed "
    "on post-subtraction Wisconsin AGI (standard deduction per 71.05(22)(dp), "
    "line 17 net of line 16) and all credits forfeited (54m.d)."
)

EXCLUSION_TAX_MODE = "corrected"  # or "engine"


def _wi_rate_tax(tax_unit, period, parameters, taxable_income):
    fstatus = tax_unit("filing_status", period)
    statuses = fstatus.possible_values
    p = parameters(period).gov.states.wi.tax.income
    return select(
        [
            fstatus == statuses.SINGLE,
            fstatus == statuses.JOINT,
            fstatus == statuses.SURVIVING_SPOUSE,
            fstatus == statuses.SEPARATE,
            fstatus == statuses.HEAD_OF_HOUSEHOLD,
        ],
        [
            p.rates.single.calc(taxable_income),
            p.rates.joint.calc(taxable_income),
            p.rates.joint.calc(taxable_income),
            p.rates.separate.calc(taxable_income),
            p.rates.head_of_household.calc(taxable_income),
        ],
    )


def _wi_standard_deduction_at(tax_unit, period, parameters, wagi):
    # Same formula as 1.755.4 variables/.../wi_standard_deduction.py, evaluated
    # at a caller-supplied Wisconsin AGI.
    fstatus = tax_unit("filing_status", period)
    statuses = fstatus.possible_values
    deduction = parameters(period).gov.states.wi.tax.income.deductions
    max_amount = deduction.standard.max[fstatus]
    phase_out_amount = select(
        [
            fstatus == statuses.SINGLE,
            fstatus == statuses.JOINT,
            fstatus == statuses.SURVIVING_SPOUSE,
            fstatus == statuses.SEPARATE,
            fstatus == statuses.HEAD_OF_HOUSEHOLD,
        ],
        [
            deduction.standard.phase_out.single.calc(wagi),
            deduction.standard.phase_out.joint.calc(wagi),
            deduction.standard.phase_out.joint.calc(wagi),
            deduction.standard.phase_out.separate.calc(wagi),
            deduction.standard.phase_out.head_of_household.calc(wagi),
        ],
    )
    return max_(0, max_amount - phase_out_amount)


class wi_retirement_income_exclusion_line17_offset(Variable):
    value_type = float
    entity = TaxUnit
    label = "Wisconsin line 17 subtraction lost when line 16 is claimed"
    unit = USD
    definition_period = YEAR
    reference = (
        "https://docs.legis.wisconsin.gov/statutes/statutes/71/i/05/6/b/54",
        "https://www.revenue.wi.gov/TaxForms2025/2025-ScheduleSB-Inst.pdf#page=8",
    )
    defined_for = StateCode.WI

    def formula(tax_unit, period, parameters):
        # Line 17 worksheet line 4 includes line 16, so each person's line-17
        # amount is capped at their qualified-plan + IRA income left after
        # their share of line 16.
        p = parameters(period).gov.states.wi.tax.income.subtractions
        px = p.retirement_income.exclusion
        person = tax_unit.members
        age = person("age", period)
        pension = person("taxable_pension_income", period)
        ira = person("taxable_ira_distributions", period)

        # Line 16 total and eligibility match the existing engine. For joint
        # pooling, maximize remaining line 17 rather than imposing proportions.
        head_or_spouse_16 = person("is_tax_unit_head_or_spouse", period)
        eligible_16 = (age >= px.min_age) * head_or_spouse_16
        ret_16 = (pension + ira) * eligible_16
        filing_status = tax_unit("filing_status", period)
        pooled = (filing_status == filing_status.possible_values.JOINT) & (
            tax_unit.sum(eligible_16) >= 2
        )
        total_16 = tax_unit.sum(ret_16)
        pooled_amount = min_(px.max_amount.joint, total_16)
        # Non-pooled returns retain the original per-person allocation.
        line16_person = min_(px.max_amount.single, ret_16)

        # Engine's line 17 per person (wi_retirement_income_subtraction.py).
        psri = p.retirement_income
        head_or_spouse_17 = ~person("is_tax_unit_dependent", period)
        line17_person = min_(
            psri.max_amount, pension * (age >= psri.min_age) * head_or_spouse_17
        ) * tax_unit.project(
            tax_unit("wi_retirement_income_subtraction_agi_eligible", period)
        )
        remaining = max_(0, (pension + ira) * head_or_spouse_17 - line16_person)
        line17_on_path = min_(line17_person, remaining)
        nonpooled_offset = tax_unit.sum(line17_person - line17_on_path)

        # Schedule SB line 16 permits a pooled limit regardless of each
        # spouse's income. Line 17 is limited to each spouse's remaining
        # retirement income; no rule requires proportional line 16 allocation.
        # Allocate line 16 to income exceeding the existing line 17 entitlement
        # first. Its maximum retained total is min(existing entitlement,
        # retirement income left after line16). Preserve the engine's original
        # pension-only line17 scope and the non-pooled path.
        pooled_line17 = tax_unit.sum(line17_person * eligible_16)
        pooled_remaining = max_(0, total_16 - pooled_amount)
        pooled_offset = max_(0, pooled_line17 - pooled_remaining)
        return where(pooled, pooled_offset, nonpooled_offset)


class wi_retirement_income_exclusion_tax(Variable):
    value_type = float
    entity = TaxUnit
    label = "Wisconsin retirement income exclusion path tax"
    unit = USD
    definition_period = YEAR
    reference = (
        "https://docs.legis.wisconsin.gov/statutes/statutes/71/i/05/6/b/54m/a",
        "https://docs.legis.wisconsin.gov/statutes/statutes/71/i/01/13",
        "https://docs.legis.wisconsin.gov/statutes/statutes/71/i/05/22",
        "https://www.revenue.wi.gov/TaxForms2025/2025-ScheduleSB-Inst.pdf#page=7",
    )
    defined_for = StateCode.WI

    def formula(tax_unit, period, parameters):
        line16 = tax_unit("wi_retirement_income_exclusion_amount", period)
        if EXCLUSION_TAX_MODE == "engine":
            taxinc = max_(0, tax_unit("wi_taxable_income", period) - line16)
            return _wi_rate_tax(tax_unit, period, parameters, taxinc)
        offset = tax_unit("wi_retirement_income_exclusion_line17_offset", period)
        wagi = tax_unit("wi_agi", period) - line16 + offset
        sd = _wi_standard_deduction_at(tax_unit, period, parameters, wagi)
        exemption = tax_unit("wi_exemption", period)
        taxinc = max_(0, wagi - sd - exemption)
        return _wi_rate_tax(tax_unit, period, parameters, taxinc)


class wi_retirement_income_exclusion_elected(Variable):
    value_type = bool
    entity = TaxUnit
    label = "Wisconsin filer elects the Schedule SB line 16 subtraction"
    definition_period = YEAR
    reference = (
        "https://docs.legis.wisconsin.gov/statutes/statutes/71/i/05/6/b/54m/d",
        "https://www.revenue.wi.gov/TaxForms2025/2025-ScheduleSB-Inst.pdf#page=7",
    )
    defined_for = StateCode.WI

    def formula(tax_unit, period, parameters):
        p = parameters(period).gov.states.wi.tax.income
        if not p.subtractions.retirement_income.exclusion.in_effect:
            return tax_unit.filled_array(False)
        standard_before_refundable = max_(
            0,
            tax_unit("wi_income_tax_before_credits", period)
            - tax_unit("wi_non_refundable_credits", period),
        )
        standard_refundable = add(tax_unit, period, p.credits.refundable)
        standard_net = standard_before_refundable - standard_refundable
        exclusion_net = tax_unit("wi_retirement_income_exclusion_tax", period)
        line16 = tax_unit("wi_retirement_income_exclusion_amount", period)
        return (line16 > 0) & (exclusion_net < standard_net)


class wi_income_tax_before_refundable_credits(Variable):
    value_type = float
    entity = TaxUnit
    label = "Wisconsin income tax before refundable credits"
    unit = USD
    definition_period = YEAR
    reference = (
        "https://www.revenue.wi.gov/TaxForms2025/2025-Form1f.pdf",
        "https://docs.legis.wisconsin.gov/statutes/statutes/71/i/05/6/b/54m/a",
    )
    defined_for = StateCode.WI

    def formula(tax_unit, period, parameters):
        standard = max_(
            0,
            tax_unit("wi_income_tax_before_credits", period)
            - tax_unit("wi_non_refundable_credits", period),
        )
        elected = tax_unit("wi_retirement_income_exclusion_elected", period)
        exclusion_tax = tax_unit("wi_retirement_income_exclusion_tax", period)
        return where(elected, exclusion_tax, standard)


class wi_refundable_credits(Variable):
    value_type = float
    entity = TaxUnit
    label = "Wisconsin refundable credits"
    unit = USD
    definition_period = YEAR
    reference = (
        "https://www.revenue.wi.gov/TaxForms2025/2025-Form1f.pdf",
        "https://docs.legis.wisconsin.gov/statutes/statutes/71/i/05/6/b/54m/d",
    )
    defined_for = StateCode.WI

    def formula(tax_unit, period, parameters):
        p = parameters(period).gov.states.wi.tax.income.credits
        standard = add(tax_unit, period, p.refundable)
        elected = tax_unit("wi_retirement_income_exclusion_elected", period)
        return where(elected, 0, standard)


class reform(Reform):
    def apply(self):
        self.update_variable(wi_retirement_income_exclusion_line17_offset)
        self.update_variable(wi_retirement_income_exclusion_elected)
        self.update_variable(wi_retirement_income_exclusion_tax)
        self.update_variable(wi_income_tax_before_refundable_credits)
        self.update_variable(wi_refundable_credits)
