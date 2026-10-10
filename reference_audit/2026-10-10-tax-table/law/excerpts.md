# Law read: citations and excerpts

These are the passages the findings rest on, read on 2026-10-10. The whole documents are not in this repository; `sources.json` lists each one with its address, its sha256 and the dates it carries. The two Tax Tables are the exception: `irs_tax_table_2025.csv` and `irs_tax_table_2026_draft.csv` hold every amount of each, because the tests compare against them.

Each excerpt is verbatim. `scripts/law_sources.py` checks every block quote below against the text extraction named in the comment above it, after removing line-break hyphens and collapsing white space, and records the result in `excerpts_check.json`. A worksheet line is given without its dot leaders.

## The statute

### 26 U.S.C. 3(a) to (c): the Tax Table tax is imposed in place of the section 1 tax

<!-- source: govinfo_usc26_3.txt -->
> In lieu of the tax imposed by section 1, there is hereby imposed for each taxable year on the taxable income of every individual—
> (A) who does not itemize his deductions for the taxable year, and
> (B) whose taxable income for such taxable year does not exceed the ceiling amount,
> a tax determined under tables, applicable to such taxable year, which shall be prescribed by the Secretary and which shall be in such form as he determines appropriate. In the table so prescribed, the amounts of the tax shall be computed on the basis of the rates prescribed by section 1.

<!-- source: govinfo_usc26_3.txt -->
> For purposes of paragraph (1), the term "ceiling amount" means, with respect to any taxpayer, the amount (not less than $20,000) determined by the Secretary for the tax rate category in which such taxpayer falls.

<!-- source: govinfo_usc26_3.txt -->
> The Secretary may provide that this section shall apply also for any taxable year to individuals who itemize their deductions. Any tables prescribed under the preceding sentence shall be on the basis of taxable income.

<!-- source: govinfo_usc26_3.txt -->
> For purposes of this title, the tax imposed by this section shall be treated as tax imposed by section 1.

The section was last amended by Pub. L. 99–514 (1986); its source credit ends there:

<!-- source: govinfo_usc26_3.txt -->
> Pub. L. 99–514, title I, §§102(b), 141(b)(1), Oct. 22, 1986, 100 Stat. 2102, 2117.)

Section 4, which held the rules for the elective tax table of the 1954 Code, is repealed:

<!-- source: govinfo_usc26_4.txt -->
> [§4. Repealed. Pub. L. 94–455, title V, §501(b)(1), Oct. 4, 1976, 90 Stat. 1558]

### 26 U.S.C. 1: the rate schedule, and how capital gain rates refer to it

<!-- source: govinfo_usc26_1.txt -->
> Not later than December 15 of 1993, and each subsequent calendar year, the Secretary shall prescribe tables which shall apply in lieu of the tables contained in subsections (a), (b), (c), (d), and (e) with respect to taxable years beginning in the succeeding calendar year.

Those are the rate schedules, which the revenue procedure below gives for 2026. They are not the Tax Table of section 3.

<!-- source: govinfo_usc26_1.txt -->
> If a taxpayer has a net capital gain for any taxable year, the tax imposed by this section for such taxable year shall not exceed the sum of—
> (A) a tax computed at the rates and in the same manner as if this subsection had not been enacted on the greater of—
> (i) taxable income reduced by the net capital gain; or

The edition read (United States Code, 2024 Edition, the most recent on govinfo.gov on 2026-10-10) predates Pub. L. 119–21. Its section 1(j) still ends with 2025:

<!-- source: govinfo_usc26_1.txt -->
> In the case of a taxable year beginning after December 31, 2017, and before January 1, 2026—

Pub. L. 119–21 removed the end date, so the section 1(j) tables govern 2026:

<!-- source: plaw119-21.txt -->
> (a) In General.-- <<NOTE: 26 USC 1.>> Section 1(j) is amended--
> (1) in paragraph (1), by striking ``, and before January 1, 2026'', and

It does not amend section 3 (no amendment to "Section 3(a)" or to "tax tables for individuals" appears in its text).

### 26 U.S.C. 6102: whole-dollar amounts are the filer's option

<!-- source: govinfo_usc26_6102.txt -->
> Any person making a return, statement, or other document shall be allowed, under regulations prescribed by the Secretary, to make such return, statement, or other document without regard to subsection (a).

<!-- source: govinfo_usc26_6102.txt -->
> The provisions of subsections (a) and (b) shall not be applicable to items which must be taken into account in making the computations necessary to determine the amount required to be shown on a form, but shall be applicable only to such final amount.

### 26 CFR 1.3-1: the regulation still describes the pre-1977 elective table

<!-- source: ecfr_1.3-1.txt -->
> For taxable years beginning after December 31, 1970 an individual whose adjusted gross income is less than $10,000 (or a husband and wife filing a joint return whose combined adjusted gross income is less than $10,000) may elect to pay the tax imposed by section 3 as amended in place of the tax imposed by section 1 as amended.

It says nothing about today's table, its ceiling or how its amounts are computed. The prescription in force is the instructions'.

## The 2026 rates

### Rev. Proc. 2025-32, section 4.01 (PDF dated 2025-10-17)

<!-- source: rp-25-32.raw.txt -->
> .01 Tax Rate Tables. For taxable years beginning in 2026, the tax rate tables under § 1 are as follows:

<!-- source: rp-25-32.raw.txt -->
> TABLE 3 - Section 1(j)(2)(C) – Unmarried Individuals (other than Surviving Spouses and Heads of Households)

The four individual tables, as read (thresholds; rates of 10, 12, 22, 24, 32, 35 and 37 percent):

| Table | Brackets end at |
|---|---|
| 1, married filing jointly and surviving spouses | $24,800; $100,800; $211,400; $403,550; $512,450; $768,700 |
| 2, heads of households | $17,700; $67,450; $105,700; $201,750; $256,200; $640,600 |
| 3, unmarried individuals | $12,400; $50,400; $105,700; $201,775; $256,225; $640,600 |
| 4, married filing separately | $12,400; $50,400; $105,700; $201,775; $256,225; $384,350 |

`scripts/law_sources.py` reads these amounts out of the extraction and compares them with `scripts/tax_table.py`; so does it for the 2025 tables of Rev. Proc. 2024-40, section 3.01 (PDF dated 2024-10-22).

The IRS announced the procedure on October 9, 2025:

<!-- source: irs_news_2026_adjustments.txt -->
> IR-2025-103, Oct. 9, 2025

### 2026 Form 1040-ES: a 2026 computation the IRS published before the freeze, for estimated tax

IRS.gov lists the form as posted 02/13/2026 (its PDF is dated 2026-02-12):

<!-- source: irs_forms_1040es.txt -->
> Form 1040-ES Estimated Tax For Individuals 2026 02/13/2026

It figures estimated tax, not the tax on a return, and says so:

<!-- source: f1040es.raw.txt -->
> Tax. Figure your tax on the amount on line 3 by using the 2026 Tax Rate Schedules.

<!-- source: f1040es.raw.txt -->
> Caution: Don’t use these Tax Rate Schedules to figure your 2025 taxes. Use only to figure your 2026 estimated taxes.

## The instructions: who must use the Tax Table

### 2025 Instructions for Form 1040, line 16 (PDF dated 2026-02-25, the current revision)

<!-- source: i1040gi.raw.txt -->
> Tax Table or Tax Computation Worksheet. If your taxable income is less than $100,000, you must use the Tax Table, later in these instructions, to figure your tax. Be sure you use the correct column. If your taxable income is $100,000 or more, use the Tax Computation Worksheet right after the Tax Table.

<!-- source: i1040gi.raw.txt -->
> However, don’t use the Tax Table or Tax Computation Worksheet to figure your tax if any of the following applies.

Five methods follow. Each is named here by its opening words:

<!-- source: i1040gi.raw.txt -->
> Form 8615. Form 8615 must generally be used to figure the tax on your unearned income over $2,700 if you are under age 18, and in certain situations if you are older.

<!-- source: i1040gi.raw.txt -->
> Schedule D Tax Worksheet. Use the Schedule D Tax Worksheet in the Instructions for Schedule D to figure the amount to enter on Form 1040 or 1040-SR, line 16, if:

<!-- source: i1040gi.raw.txt -->
> Qualified Dividends and Capital Gain Tax Worksheet. Use the Qualified Dividends and Capital Gain Tax Worksheet, later, to figure your tax if you don’t have to use the Schedule D Tax Worksheet and if any of the following applies.

<!-- source: i1040gi.raw.txt -->
> Schedule J. If you had income from farming or fishing, your tax may be less if you choose to figure it using income averaging on Schedule J.

<!-- source: i1040gi.raw.txt -->
> Foreign Earned Income Tax Worksheet. If you claimed the foreign earned income exclusion, housing exclusion, or housing deduction on Form 2555, you must figure your tax using the Foreign Earned Income Tax Worksheet.

The two capital gain worksheets and the foreign earned income worksheet send their own look-ups back to the Tax Table (below). Form 8615 and Schedule J were not read for this audit, and policyengine-us 2.38.6 computes neither: its federal code has no Form 8615 tax and no income averaging.

The instruction draws no line between filers who itemize and filers who do not.

### The Tax Table's own example and footnote

<!-- source: i1040gi.raw.txt -->
> Example. A married couple is filing a joint return. Their taxable income on Form 1040, line 15, is $25,300. First, they find the $25,300-25,350 taxable income line. Next, they find the column for married filing jointly and read down the column. The amount shown where the taxable income line and filing status column meet is $2,562. This is the tax amount they should enter in the entry space on Form 1040, line 16.

<!-- source: i1040gi.raw.txt -->
> This column must also be used by a qualifying surviving spouse.

### Qualified Dividends and Capital Gain Tax Worksheet, lines 22 and 24

<!-- source: i1040gi.raw.txt -->
> Figure the tax on the amount on line 5. If the amount on line 5 is less than $100,000, use the Tax Table to figure the tax. If the amount on line 5 is $100,000 or more, use the Tax Computation Worksheet

<!-- source: i1040gi.raw.txt -->
> Figure the tax on the amount on line 1. If the amount on line 1 is less than $100,000, use the Tax Table to figure the tax. If the amount on line 1 is $100,000 or more, use the Tax Computation Worksheet

### Schedule D Tax Worksheet, lines 44 and 46 (2025 Instructions for Schedule D, PDF dated 2025-12-11)

<!-- source: i1040sd.raw.txt -->
> Figure the tax on the amount on line 21. If the amount on line 21 is less than $100,000, use the Tax Table to figure the tax. If the amount on line 21 is $100,000 or more, use the Tax Computation Worksheet

<!-- source: i1040sd.raw.txt -->
> Figure the tax on the amount on line 1. If the amount on line 1 is less than $100,000, use the Tax Table to figure the tax. If the amount on line 1 is $100,000 or more, use the Tax Computation Worksheet

### Foreign Earned Income Tax Worksheet, line 5

<!-- source: i1040gi.raw.txt -->
> Figure the tax on the amount on line 2c. If the amount on line 2c is less than $100,000, use the Tax Table to figure this tax. If the amount on line 2c is $100,000 or more, use the Tax Computation Worksheet

No benchmark household claims the exclusion.

### Tax Computation Worksheet (the method at $100,000 or more)

<!-- source: i1040gi.raw.txt -->
> Section A—Use if your filing status is Single. Complete the row below that applies to you.

Each row multiplies the amount by the bracket's rate and subtracts a fixed amount, which is the rate schedule exactly. For 2025 the first single row is "At least $100,000 but not over $103,350", times 22%, less $5,086.00.

### Rounding

<!-- source: i1040gi.raw.txt -->
> You can round off cents to whole dollars on your return and schedules. If you do round to whole dollars, you must round all amounts. To round, drop amounts under 50 cents and increase amounts from 50 to 99 cents to the next dollar.

## The 2026 Tax Table

No 2026 Tax Table dated or posted before PolicyBench froze its references on 2026-07-03 was found. That is a statement about a search, which covered:

- **The final table.** On 2026-10-10, IRS.gov's listing of current forms and publications gives Publication 1040 at its 2025 revision, and the address `irs.gov/pub/irs-pdf/i1040gi.pdf` serves the 2025 Instructions for Form 1040. The address `irs.gov/pub/irs-dft/i1040gi--dft.pdf` holds the 2025 instructions' own draft cover.

<!-- source: irs_forms_p1040.txt -->
> Publication 1040 Tax and Earned Income Credit Tables 2025 01/15/2026

- **The draft.** The earliest 2026 table found is the IRS's early release draft of Publication 1040 (2026), "Tax and Earned Income Credit Tables". Its cover carries the date Aug 28, 2026 (the PDF was created that day and modified 2026-09-16), and IRS.gov/DraftForms lists it as posted 09/16/2026. Every page is marked as a draft.
- **The draft listing before the freeze.** The Internet Archive holds copies of IRS.gov's draft listing, which shows 25 drafts to a page with the newest posting first. Fourteen copies captured from 2026-05-20 to 2026-07-03, the last at 08:09 UTC on the freeze day, show 251 distinct drafts posted from 03/23/2026 to 07/01/2026. None is a Publication 1040, the Instructions for Form 1040 or a tax table. Four copies captured from 2026-07-24 to 2026-09-10 show none either. `draft_listing_history.json` has each capture's address, sha256 and range of posting dates.

What the search does not cover: a draft posted before 03/23/2026, or on a day whose listing page was not archived (06/09/2026 is one), and replaced since. The listing shows a draft once, at its latest posting.

<!-- source: p1040_dft.raw.txt -->
> Caution: DRAFT—NOT FOR FILING

<!-- source: p1040_dft.raw.txt -->
> This is an early release draft of an IRS tax form, instructions, or publication, which the IRS is providing for your information. Do not file draft forms.

<!-- source: p1040_dft.raw.txt -->
> Drafts of instructions and publications usually have some additional changes before their final release.

<!-- source: p1040_dft.raw.txt -->
> Example. A married couple is filing a joint return. Their taxable income on Form 1040, line 15, is $25,300. First, they find the $25,300–25,350 taxable income line. Next, they find the column for married filing jointly and read down the column. The amount shown where the taxable income line and filing status column meet is $2,543.

The draft keeps the $100,000 ceiling: its 2026 Tax Computation Worksheet begins each section at "At least $100,000", and its single row subtracts $5,288.00 at 22%, which is Rev. Proc. 2025-32's Table 3 ($5,800 plus 22% of the excess over $50,400).

<!-- source: irs_drafts_1040.txt -->
> Publication 1040 Tax and Earned Income Credit Tables 2026 09/16/2026

## What no document read states

None of the documents above was found to say how the IRS computes a Tax Table amount. The line 16 instructions, the Tax Table's heading, example and footnote, and the Tax Computation Worksheet were read, and every extraction was searched for "midpoint", "mid-point" and "middle": the 2025 instructions, both Publications 1040, the Schedule D instructions, Form 1040-ES and both revenue procedures. The only hits are "middle initial" on Form 1040-ES's payment vouchers. A description in other words, somewhere unread, would not have been caught. Section 3(a)(1) requires only that the amounts be "computed on the basis of the rates prescribed by section 1". The rule in `scripts/tax_table.py` (the tax on the band's midpoint, rounded to a dollar, a half rounding up) is inferred, and it reproduces all 8,248 amounts of the 2025 table and all 8,248 of the 2026 draft.
