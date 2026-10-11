"""Work both cells by hand, in exact decimal arithmetic, from the law's figures.

Every amount below is either a household fact from the prompt (to the cent, as
traces/*/scenario_*_situation.json holds it) or a figure quoted in
law/excerpts.md; each constant's comment names the passage. No engine is
loaded. The script writes
verification/hand_derivations.json; tests/test_held_references.py checks that
file against this script, the references against the release's payload, and
each consensus answer against the models' own answers.

  uv run python reference_audit/2026-10-10-held-references/scripts/hand_derivations.py
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
D = Decimal


def cents(value: Decimal) -> str:
    return str(value.quantize(D("0.01"), rounding=ROUND_HALF_UP))


# --- Federal figures for 2026 --------------------------------------------------
# Rev. Proc. 2025-32 s. 4.01: the rows of Table 3 (unmarried individuals) and
# Table 1 (joint returns and surviving spouses) that these incomes fall in.
# Each row is (over, not over, base tax, rate).
SINGLE_TABLE = [
    (D(12400), D(50400), D(1240), D("0.12")),
    (D(50400), D(105700), D(5800), D("0.22")),
]
JOINT_TABLE = [(D(24800), D(100800), D(2480), D("0.12"))]
# Rev. Proc. 2025-32 s. 4.14.
STANDARD_DEDUCTION = {"single": D(16100), "joint": D(32200)}
# Rev. Proc. 2025-32 s. 4.03, all other individuals: the maximum zero rate
# amount and the maximum 15 percent rate amount.
ZERO_RATE_CEILING_SINGLE, FIFTEEN_RATE_CEILING_SINGLE = D(49450), D(545500)
# 26 U.S.C. 86(c): base amount and adjusted base amount.
SS_BASE = {"other": (D(25000), D(34000)), "joint_return": (D(32000), D(44000))}


def rate_tax(taxable: Decimal, table: list) -> Decimal:
    (row,) = [row for row in table if row[0] < taxable <= row[1]]
    over, _, base, rate = row
    return base + rate * (taxable - over)


def taxable_social_security(benefits: Decimal, other: Decimal, kind: str) -> Decimal:
    """26 U.S.C. 86(a)(2): the provisional income here is above the adjusted base."""
    base, adjusted = SS_BASE[kind]
    half = benefits / 2
    provisional = other + half
    assert provisional > adjusted
    tier1 = min(half, (provisional - base) / 2)
    return min(
        D("0.85") * (provisional - adjusted) + min(tier1, (adjusted - base) / 2),
        D("0.85") * benefits,
    )


def va_039() -> dict:
    estate, loss = D("25950.00"), D("-6260.03")
    ira, pension, benefits = D("26800.00"), D("2030.00"), D("36105.00")
    other = estate + loss + ira + pension
    taxable_ss = taxable_social_security(benefits, other, "other")
    agi = other + taxable_ss
    taxable = agi - STANDARD_DEDUCTION["single"]
    reference = rate_tax(taxable, SINGLE_TABLE)

    # The six models: the same AGI, with the joint standard deduction and table.
    qss_taxable = agi - STANDARD_DEDUCTION["joint"]
    qss = rate_tax(qss_taxable, JOINT_TABLE)
    # As the models computed it, from the prompt's whole-dollar loss.
    agi_prompt = estate + D(-6260) + ira + pension + taxable_ss
    qss_prompt = rate_tax(agi_prompt - STANDARD_DEDUCTION["joint"], JOINT_TABLE)

    # Two more models: the joint return's Social Security thresholds as well.
    joint_ss = taxable_social_security(benefits, other, "joint_return")
    joint_all = rate_tax(other + joint_ss - STANDARD_DEDUCTION["joint"], JOINT_TABLE)

    # The reviewer's other reading: the estate income is qualified dividends or
    # long-term gain (26 U.S.C. 1(h)). Same filing status, AGI and taxable income.
    ordinary = taxable - estate
    at_zero = min(estate, max(ZERO_RATE_CEILING_SINGLE - ordinary, D(0)))
    assert taxable <= FIFTEEN_RATE_CEILING_SINGLE  # the rest is taxed at 15 percent
    preferential = rate_tax(ordinary, SINGLE_TABLE) + D("0.15") * (estate - at_zero)

    # The reviewer's Tax Table point: $50 bands taxed at the midpoint, to the dollar.
    band = (taxable // 50) * 50
    table_entry = rate_tax(band + 25, SINGLE_TABLE).quantize(D(1), rounding=ROUND_HALF_UP)

    # 26 U.S.C. 22(c)-(d): the initial amount less half of AGI above $7,500.
    elderly_disabled = max(D(5000) - (agi - D(7500)) / 2, D(0))

    return {
        "cell": "scenario_039 federal_income_tax_before_refundable_credits",
        "other_income": cents(other),
        "taxable_social_security": cents(taxable_ss),
        "adjusted_gross_income": cents(agi),
        "taxable_income": cents(taxable),
        "reference_by_hand": cents(reference),
        "consensus_qualifying_surviving_spouse": cents(qss),
        "consensus_qualifying_surviving_spouse_from_prompt_dollars": cents(qss_prompt),
        "joint_return_social_security_thresholds_too": cents(joint_all),
        "reviewer_estate_income_preferential": cents(preferential),
        "reviewer_tax_table_projection": str(table_entry),
        "elderly_or_disabled_credit": cents(elderly_disabled),
    }


# --- Ohio figures for 2026 -----------------------------------------------------
OH_BASE, OH_RATE, OH_THRESHOLD = D("332.00"), D("0.0275"), D(26050)  # R.C. 5747.02(A)(3)(c)
OH_BASE_2024 = D("360.69")  # R.C. 5747.02(A)(3)(a)
# R.C. 5747.02(A)(2): the 2026 rate on income up to the threshold. The engine's
# rate table carries the fixed amount as this rate times the threshold.
OH_ENGINE_BASE = OH_THRESHOLD * D("0.0127448")
OH_RETIREMENT_CREDIT = D(200)  # R.C. 5747.055(B), retirement income over $8,000
OH_FLOOR = D("0.075")  # R.C. 5747.01(A)(10)(b)


def oh_exemption(magi: Decimal) -> Decimal:
    """2025 IT 1040 booklet p. 17 amounts, frozen for 2026 by H.B. 96 s.
    757.120(A). R.C. 5747.025(A) allows none at $500,000 or more from 2026."""
    if magi >= 500000:
        return D(0)
    return D(2400) if magi <= 40000 else D(2150) if magi <= 80000 else D(1900)


def oh_tax(agi: Decimal, *, base: Decimal = OH_BASE) -> Decimal:
    taxable = agi - 2 * oh_exemption(agi)
    assert taxable > OH_THRESHOLD
    return base + OH_RATE * (taxable - OH_THRESHOLD) - OH_RETIREMENT_CREDIT


def oh_025() -> dict:
    wages, pension = D("62725.29"), D("32200.00")
    employer_premiums, premiums = D("21207.53"), D("6500.00")
    other_medical, over_the_counter = D("800.00"), D("50.00")
    federal_agi = wages + pension
    floor = OH_FLOOR * federal_agi

    def line_8(line_5: Decimal, agi: Decimal = federal_agi) -> Decimal:
        return max(line_5 - OH_FLOOR * agi, D(0))

    deduction = line_8(premiums + other_medical)
    reference = oh_tax(federal_agi - deduction)

    # The eight models: whole-dollar facts, no medical deduction, no $332.00.
    agi_prompt = D(62725) + D(32200)
    consensus = oh_tax(agi_prompt, base=D(0))

    return {
        "cell": "scenario_025 state_income_tax_before_refundable_credits",
        "federal_agi": cents(federal_agi),
        "medical_floor": cents(floor),
        "medical_deduction": cents(deduction),
        "ohio_agi": cents(federal_agi - deduction),
        "reference_by_hand": cents(reference),
        "engine_base_amount": str(OH_ENGINE_BASE),
        "reference_with_engine_base_amount": cents(
            oh_tax(federal_agi - deduction, base=OH_ENGINE_BASE)
        ),
        "consensus_no_base_amount_no_deduction": cents(consensus),
        "no_medical_deduction": cents(oh_tax(federal_agi)),
        "premiums_in_full_on_line_1_from_prompt_dollars": cents(
            oh_tax(agi_prompt - premiums)
        ),
        "base_amount_of_2024_from_prompt_dollars": cents(
            oh_tax(agi_prompt, base=OH_BASE_2024)
        ),
        "over_the_counter_counted": cents(
            oh_tax(federal_agi - line_8(premiums + other_medical + over_the_counter))
        ),
        "premiums_counted_twice": cents(
            oh_tax(federal_agi - line_8(2 * premiums + other_medical))
        ),
        # The reviewer's other reading: the head paid the $21,207.53 after tax.
        "reviewer_employer_premiums_paid_by_head_subsidized_plan": cents(
            oh_tax(federal_agi - line_8(employer_premiums + premiums + other_medical))
        ),
        "reviewer_employer_premiums_paid_by_head_from_prompt_dollars": cents(
            oh_tax(
                agi_prompt
                - line_8(D(21208) + premiums + other_medical, agi_prompt)
            )
        ),
        "reviewer_employer_premiums_paid_by_head_unsubsidized_plan": cents(
            oh_tax(federal_agi - (employer_premiums + premiums))
        ),
    }


def derivations() -> dict:
    return {"scenario_039": va_039(), "scenario_025": oh_025()}


def main() -> None:
    out = HERE / "verification" / "hand_derivations.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(derivations(), indent=2) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
