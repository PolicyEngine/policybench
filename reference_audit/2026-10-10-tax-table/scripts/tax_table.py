"""The Tax Table of 26 U.S.C. 3, constructed from a section 1 rate schedule.

Section 3(a)(1) imposes, "in lieu of the tax imposed by section 1", a tax
"determined under tables ... prescribed by the Secretary", whose amounts "shall be
computed on the basis of the rates prescribed by section 1". The Form 1040
instructions prescribe the table for taxable income under $100,000 (line 16, and
the two capital gain worksheets for each amount they look up).

No document read for this audit states how the IRS fills the table. The rule here
is inferred from the published tables and then checked against every cell of them
(tests/test_tax_table_audit.py): the tax on the midpoint of the income band at the
schedule's rates, rounded to a whole dollar with a half rounding up. Bands are
$5, $10 and $10 wide below $25, $25 wide to $3,000 and $50 wide to $100,000.

All arithmetic is in integers. Thresholds are whole dollars and rates whole
percents, so a midpoint is a whole number of half dollars and the tax on it a
whole number of half cents: no float decides a rounding tie.

SCHEDULES holds the two years' rate schedules as the revenue procedures print
them (thresholds and rates below; the base amounts in BASE_AMOUNTS are the
procedures' own, which the tests rebuild from the thresholds and rates):
  2025  Rev. Proc. 2024-40, section 3.01, Tables 1 to 4
  2026  Rev. Proc. 2025-32, section 4.01, Tables 1 to 4
"""

from __future__ import annotations

CEILING = 100_000
STATUSES = ("single", "joint", "separate", "head_of_household")
# The Tax Table has four columns; a qualifying surviving spouse uses the joint
# one ("This column must also be used by a qualifying surviving spouse").
COLUMN_FOR_FILING_STATUS = {
    "SINGLE": "single",
    "JOINT": "joint",
    "SEPARATE": "separate",
    "HEAD_OF_HOUSEHOLD": "head_of_household",
    "SURVIVING_SPOUSE": "joint",
}
RATES = (10, 12, 22, 24, 32, 35, 37)
# The upper threshold of each bracket but the last, in dollars.
SCHEDULES = {
    2025: {
        "joint": (23_850, 96_950, 206_700, 394_600, 501_050, 751_600),
        "head_of_household": (17_000, 64_850, 103_350, 197_300, 250_500, 626_350),
        "single": (11_925, 48_475, 103_350, 197_300, 250_525, 626_350),
        "separate": (11_925, 48_475, 103_350, 197_300, 250_525, 375_800),
    },
    2026: {
        "joint": (24_800, 100_800, 211_400, 403_550, 512_450, 768_700),
        "head_of_household": (17_700, 67_450, 105_700, 201_750, 256_200, 640_600),
        "single": (12_400, 50_400, 105_700, 201_775, 256_225, 640_600),
        "separate": (12_400, 50_400, 105_700, 201_775, 256_225, 384_350),
    },
}
# "$X plus r% of the excess over $T": the X the revenue procedure prints for each
# bracket above the first, in cents.
BASE_AMOUNTS = {
    2025: {
        "joint": (238_500, 1_115_700, 3_530_200, 8_039_800, 11_446_200, 20_215_450),
        "head_of_household": (
            170_000,
            744_200,
            1_591_200,
            3_846_000,
            5_548_400,
            18_703_150,
        ),
        "single": (119_250, 557_850, 1_765_100, 4_019_900, 5_723_100, 18_876_975),
        "separate": (119_250, 557_850, 1_765_100, 4_019_900, 5_723_100, 10_107_725),
    },
    2026: {
        "joint": (248_000, 1_160_000, 3_593_200, 8_204_800, 11_689_600, 20_658_350),
        "head_of_household": (
            177_000,
            774_000,
            1_615_500,
            3_920_700,
            5_663_100,
            19_117_100,
        ),
        "single": (124_000, 580_000, 1_796_600, 4_102_400, 5_844_800, 19_297_925),
        "separate": (124_000, 580_000, 1_796_600, 4_102_400, 5_844_800, 10_329_175),
    },
}


def band(taxable_income: float) -> tuple[int, int]:
    """The Tax Table band [at least, but less than) holding an amount under $100,000."""
    if not 0 <= taxable_income < CEILING:
        raise ValueError(f"the Tax Table covers 0 to under {CEILING}: {taxable_income}")
    if taxable_income < 5:
        return 0, 5
    if taxable_income < 15:
        return 5, 15
    if taxable_income < 25:
        return 15, 25
    width = 25 if taxable_income < 3_000 else 50
    lower = int(taxable_income // width) * width
    return lower, lower + width


def bands() -> list[tuple[int, int]]:
    """Every band of the Tax Table, in order."""
    out = [(0, 5), (5, 15), (15, 25)]
    out += [(lower, lower + 25) for lower in range(25, 3_000, 25)]
    out += [(lower, lower + 50) for lower in range(3_000, CEILING, 50)]
    return out


def _half_cents(half_dollars: int, thresholds: tuple[int, ...]) -> int:
    """Schedule tax, in half cents, on an amount given in half dollars."""
    total = 0
    bottom = 0
    for rate, top in zip(RATES, (*thresholds, None)):
        upper = half_dollars if top is None else min(half_dollars, 2 * top)
        if upper > bottom:
            total += rate * (upper - bottom)
        if top is None or half_dollars <= 2 * top:
            break
        bottom = 2 * top
    return total


def schedule_tax_cents(taxable_income_cents: int, status: str, year: int) -> int:
    """Rate schedule tax in cents on a whole number of cents, half a cent rounding up."""
    thresholds = SCHEDULES[year][status]
    total = 0  # in units of a hundredth of a cent
    bottom = 0
    for rate, top in zip(RATES, (*thresholds, None)):
        upper = (
            taxable_income_cents
            if top is None
            else min(taxable_income_cents, 100 * top)
        )
        if upper > bottom:
            total += rate * (upper - bottom)
        if top is None or taxable_income_cents <= 100 * top:
            break
        bottom = 100 * top
    return (total + 50) // 100


def schedule_tax(taxable_income: float, status: str, year: int) -> float:
    """Rate schedule tax in dollars (the references' convention), to the cent."""
    return schedule_tax_cents(round(taxable_income * 100), status, year) / 100


def table_tax(taxable_income: float, status: str, year: int) -> int:
    """The constructed Tax Table amount for taxable income under $100,000."""
    lower, upper = band(taxable_income)
    # The midpoint is (lower + upper) / 2 dollars, so lower + upper half dollars.
    half_cents = _half_cents(lower + upper, SCHEDULES[year][status])
    return (half_cents + 100) // 200


def line_16_tax(taxable_income: float, status: str, year: int) -> float:
    """Tax by the instructions' method: the table under $100,000, else the worksheet.

    The Tax Computation Worksheet multiplies the amount by the bracket's rate and
    subtracts a fixed amount, which is the rate schedule exactly.
    """
    if taxable_income < CEILING:
        return float(table_tax(taxable_income, status, year))
    return schedule_tax(taxable_income, status, year)


def marginal_rate(taxable_income: float, status: str, year: int) -> float:
    """The schedule's rate on the next dollar of taxable income."""
    for rate, top in zip(RATES, (*SCHEDULES[year][status], None)):
        if top is None or taxable_income < top:
            return rate / 100
    raise AssertionError("unreachable")


def constructed_table(year: int) -> list[dict]:
    """Every row of the constructed Tax Table for a year."""
    return [
        {
            "at_least": lower,
            "less_than": upper,
            **{status: table_tax(lower, status, year) for status in STATUSES},
        }
        for lower, upper in bands()
    ]
