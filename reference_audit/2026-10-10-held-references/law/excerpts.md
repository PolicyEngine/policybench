# Law relied on: citations and short excerpts

These are the passages the two verdicts rest on. The whole documents are not in this repository. `sources.json` lists each document the 2026-10-10 session saved, with its address, its sha256 and what was checked again on the same day for this record. Excerpts are verbatim apart from line breaks, with two exceptions. A row of a two-column table is written on one line, with a colon between the columns in the rate tables. A worksheet line is given without its dot leaders.

How the excerpts were checked: 54 of the 64 quoted lines are exact substrings of the saved text extractions, after collapsing white space. The other ten are the five Rev. Proc. table rows, the worksheet's line 4, and the four passages from the Form 1040 instructions, which the extraction sets in three interleaved columns (lines 683–688, 791–795, 839–841 and 2384–2387 of `i1040gi.txt`). Those ten were read against the extraction by eye.

2026 returns and instructions are not yet published. Form lines are the 2025 forms', and 2026 amounts come from Rev. Proc. 2025-32 and the Ohio Revised Code.

## Virginia scenario_039, federal income tax

### 26 U.S.C. 2(a)(1): who is a surviving spouse (decisive)

> (a) Definition of surviving spouse
> (1) In general
> For purposes of section 1, the term “surviving spouse” means a taxpayer—
> (A) whose spouse died during either of his two taxable years immediately preceding the taxable year, and
> (B) who maintains as his home a household which constitutes for the taxable year the principal place of abode (as a member of such household) of a dependent (i) who (within the meaning of section 152, determined without regard to subsections (b)(1), (b)(2), and (d)(1)(B) thereof) is a son, stepson, daughter, or stepdaughter of the taxpayer, and (ii) with respect to whom the taxpayer is entitled to a deduction for the taxable year under section 151.

The household is one person, so (B) fails whatever the year of death.

### 2025 Form 1040 instructions, Filing Status

Under Single:

> You were widowed before January 1, 2025, and didn’t remarry before the end of 2025. But if you have a child, you may be able to use the qualifying surviving spouse filing status.

Under Qualifying Surviving Spouse, the first condition, and the note on a death in the tax year:

> Your spouse died in 2023 or 2024 and you didn’t remarry before the end of 2025.

> If your spouse died in 2025, you can't file as qualifying surviving spouse.

### 26 U.S.C. 61(a)(14): estate income is gross income

> (14) Income from an interest in an estate or trust.

### 26 U.S.C. 86: taxable Social Security benefits

> (2) Additional amount
> In the case of a taxpayer with respect to whom the amount determined under subsection (b)(1)(A) exceeds the adjusted base amount, the amount included in gross income under this section shall be equal to the lesser of—
> (A) the sum of—
> (i) 85 percent of such excess, plus
> (ii) the lesser of the amount determined under paragraph (1) or an amount equal to one-half of the difference between the adjusted base amount and the base amount of the taxpayer, or
> (B) 85 percent of the social security benefits received during the taxable year.

> (1) Base amount
> The term “base amount” means—
> (A) except as otherwise provided in this paragraph, $25,000,
> (B) $32,000 in the case of a joint return, and

> (2) Adjusted base amount
> The term “adjusted base amount” means—
> (A) except as otherwise provided in this paragraph, $34,000,
> (B) $44,000 in the case of a joint return, and

### Rev. Proc. 2025-32: 2026 amounts

Section 4.01, Table 3, Unmarried Individuals (other than Surviving Spouses and Heads of Households):

> Over $12,400 but not over $50,400: $1,240 plus 12% of the excess over $12,400
> Over $50,400 but not over $105,700: $5,800 plus 22% of the excess over $50,400

Section 4.01, Table 1, Married Individuals Filing Joint Returns and Surviving Spouses:

> Over $24,800 but not over $100,800: $2,480 plus 12% of the excess over $24,800

Section 4.14(1), standard deduction:

> Married Individuals Filing Joint Returns and Surviving Spouses (§ 1(j)(2)(A)) $32,200
> Unmarried Individuals (other than Surviving Spouses and Heads of Households) (§ 1(j)(2)(C)) $16,100

Section 4.03, maximum zero rate amount (used only for the reviewer's preferential reading):

> All Other Individuals $49,450 $545,500

### 26 U.S.C. 199A(c)(2): a business loss carries forward

> (2) Carryover of losses
> If the net amount of qualified income, gain, deduction, and loss with respect to qualified trades or businesses of the taxpayer for any taxable year is less than zero, such amount shall be treated as a loss from a qualified trade or business in the succeeding taxable year.

### 26 U.S.C. 22(c)(2)(A)(i) and (d): credit for the elderly or disabled

> (i) $5,000 in the case of a single individual, or a joint return where only one spouse is a qualified individual,

> (d) Adjusted gross income limitation
> If the adjusted gross income of the taxpayer exceeds—
> (1) $7,500 in the case of a single individual,
> (2) $10,000 in the case of a joint return, or
> (3) $5,000 in the case of a married individual filing a separate return,
> the section 22 amount shall be reduced by one-half of the excess of the adjusted gross income over $7,500, $10,000, or $5,000, as the case may be.

### 26 U.S.C. 1411(b): net investment income tax threshold

> (3) in any other case, $200,000.

### 2025 Form 1040 instructions, line 16 (the reviewer's Tax Table point)

> If your taxable income is less than $100,000, you must use the Tax Table, later in these instructions, to figure your tax.

## Ohio scenario_025, state income tax

### R.C. 5747.02(A)(3): the 2026 schedule (decisive)

Effective September 30, 2025 (H.B. 96, 136th General Assembly).

> If the balance thus obtained is equal to or less than twenty-six thousand fifty dollars, no tax shall be imposed on that balance. If the balance thus obtained is greater than twenty-six thousand fifty dollars, the tax is hereby levied as follows:

> (c) For taxable years beginning in 2026 and thereafter, $332.00 plus 2.75% of the amount in excess of $26,050.

Division (A)(2) gives the rate behind the fixed amount, which is how the engine carries it (1.27448% × $26,050 = $332.002):

> 1.27448% for taxable years beginning in 2026 and thereafter.

### R.C. 5747.01(A)(10): the medical deduction

Effective March 5, 2026.

> (10)(a) Deduct, to the extent not otherwise allowable as a deduction or exclusion in computing federal or Ohio adjusted gross income for the taxable year, the amount the taxpayer paid during the taxable year for medical care insurance and qualified long-term care insurance for the taxpayer, the taxpayer's spouse, and dependents. No deduction for medical care insurance under division (A)(10)(a) of this section shall be allowed either to any taxpayer who is eligible to participate in any subsidized health plan maintained by any employer of the taxpayer or of the taxpayer's spouse, or to any taxpayer who is entitled to, or on application would be entitled to, benefits under part A of Title XVIII of the "Social Security Act," 49 Stat. 620 (1935), 42 U.S.C. 301, as amended. For the purposes of division (A)(10)(a) of this section, "subsidized health plan" means a health plan for which the employer pays any portion of the plan's cost.

> (b) Deduct, to the extent not otherwise deducted or excluded in computing federal or Ohio adjusted gross income during the taxable year, the amount the taxpayer paid during the taxable year, not compensated for by any insurance or otherwise, for medical care of the taxpayer, the taxpayer's spouse, and dependents, to the extent the expenses exceed seven and one-half per cent of the taxpayer's federal adjusted gross income.

> (c) For purposes of division (A)(10) of this section, "medical care" has the meaning given in section 213 of the Internal Revenue Code, subject to the special rules, limitations, and exclusions set forth therein

### 26 U.S.C. 213(b) and (d)(1)(D): what medical care includes

> (b) Limitation with respect to medicine and drugs
> An amount paid during the taxable year for medicine or a drug shall be taken into account under subsection (a) only if such medicine or drug is a prescribed drug or is insulin.

> (D) for insurance (including amounts paid as premiums under part B of title XVIII of the Social Security Act, relating to supplementary medical insurance for the aged) covering medical care referred to in subparagraphs (A) and (B)

### 2025 Ohio IT 1040 booklet, Unreimbursed Medical Care Expenses Worksheet (p. 41)

> 3. Enter amounts paid for unreimbursed dental, vision, and health insurance premiums during any portion of the year in which you were eligible for Medicare or an employer-paid health care plan through your or your spouse’s employer

> 4. Enter amounts paid for medical care during the year (exclude insurance premiums).

> 7. Line 6 times 7.5% (0.075)

> 8. Line 5 minus line 7. If less than zero, enter zero

The Department of Taxation's FAQ on these lines (questions 8 and 9) is quoted in `reference_audit/2026-10-05-reference-adversary/verification/independent/oh_025.md`, which fetched it on 2026-10-06. The 2026-10-10 session saved no copy of the FAQ, and this record did not fetch it again.

### R.C. 5747.025(A)(3) and the 2025 booklet (p. 17): exemptions

The statute's base amount for modified adjusted gross income above $80,000:

> (3) One thousand eight hundred fifty dollars if the taxpayer's modified adjusted gross income for the taxable year as shown on an individual or joint annual return is greater than eighty thousand dollars.

Division (C) keeps an adjusted amount in force until the next adjustment:

> The adjusted amount applies to taxable years beginning in the calendar year in which the adjustment is made and to taxable years beginning in each ensuing calendar year until a calendar year in which a new adjustment is made pursuant to this division.

The amounts in force for 2025, from the booklet's exemption table. Section 757.120(A) below allows no adjustment in 2025 or 2026, so they are the 2026 amounts too:

> $40,001 – $80,000 $2,150
> $80,001 - $749,999 $1,900

### H.B. 96 (136th General Assembly), Section 757.120(A): no indexing in 2025 or 2026

> SECTION 757.120. (A) The Tax Commissioner shall not make adjustments in 2025 or 2026 to the income amounts in divisions (A)(2) and (3) of section 5747.02 of the Revised Code, as otherwise required by division (A)(5) of that section, or make adjustments in 2025 or 2026 to the personal exemption amounts prescribed in division (A) of section 5747.025 of the Revised Code, as otherwise required by divisions (B) and (C) of that section.

### Legislative Service Commission, H.B. 96 Final Analysis (p. 456)

> More than $26,050 $332 plus 2.75% of the amount over $26,050

> Continuing law requires the Tax Commissioner to adjust the income tax brackets and personal exemption amounts for inflation on an annual basis. The act suspends these adjustments for taxable years 2025 and 2026.

The analysis marks vetoed provisions "(VETOED)". Neither passage carries that mark.

### R.C. 5747.055(A)(1) and (B): retirement income credit

> (1) In the case of an individual, are received by the individual on account of retirement and are included in the individual's adjusted gross income;

> (B) A credit shall be allowed against a taxpayer's aggregate tax liability under section 5747.02 of the Revised Code for taxpayers who received retirement income during the taxable year and whose modified adjusted gross income for the taxable year, less applicable exemptions under section 5747.025 of the Revised Code, as shown on an individual or joint annual return is less than one hundred thousand dollars.

> Over $8,000 $ 200

### R.C. 5747.05(E)(1): joint filing credit

> (E)(1) On a joint return filed by a husband and wife, each of whom had adjusted gross income of at least five hundred dollars, exclusive of interest, dividends and distributions, royalties, rent, and capital gains, a credit
