# Independent review: PolicyBench scenario_039 (Virginia), federal income tax, tax year 2026

You are an independent tax reviewer. Work the problem from the law yourself before you look at anyone's answer. Do not edit any file except your output file. No network is needed: the legal sources are on disk.

## The question a benchmark asks

PolicyBench shows AI models a household and asks for tax outputs. Its reference answer comes from the PolicyEngine-US rules engine. For this household, several strong models agree with each other and disagree with the reference. Decide who is right.

The models saw exactly this (preface, household, question):

```
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: VA
- tax year: 2026

Head:
- age: 61
- bank account assets: $16,000
- employer sponsored insurance premiums: $3,589
- estate income: $25,950
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $4,800
- is disabled
- is a surviving spouse
- other health insurance premiums: $4,800
- other medical expenses: $200
- self-employment income: $-6,260
- Social Security retirement income: $36,105
- taxable IRA distributions: $26,800
- taxable private pension income: $2,030

Tax unit:
- first home mortgage balance: $47,500

Household inputs:
- household vehicles value: $5,184
```

Requested output: "federal individual income tax after nonrefundable credits and before refundable credits. This subtracts nonrefundable credits actually used [...]; it does not subtract EITC or refundable portions of credits."

The prompt rounds to whole dollars. The unrounded inputs are: estate income 25,950.00; self-employment income -6,260.03; Social Security 36,105.00; taxable IRA distributions 26,800.00; taxable pension 2,030.00. A model is scored correct when it is within $1 of the reference. The prompt never states a filing status for any household.

## Candidate answers

- A: $8,596.03. The reference (PolicyEngine-US). 4 of 47 models give this.
- B: about $5,145.11. 6 of 47 models, 5 of them among the 10 strongest.

All 47 answers with the models' own explanations: `model_answers.md` (section scenario_039).

## What to do

1. Compute the tax yourself, line by line, from the Internal Revenue Code and the forms: filing status, gross income, AGI, taxable Social Security (show the worksheet), deductions, qualified business income deduction, taxable income, tax, each nonrefundable credit you considered, AMT, net investment income tax. Cite the code section and the form line for each step. 2026 forms are not published, so cite the 2025 Form 1040 lines and the 2026 inflation amounts in Rev. Proc. 2025-32.
2. Reconstruct candidate B exactly: which single rule, applied differently, turns A into B? Confirm with the models' explanations.
3. Decide which reading the law supports. Argue the strongest case for B before you rule against it, and the strongest case for A before you rule against it. In particular: does the fact "is a surviving spouse", with no other person in the household, make the filer a "surviving spouse" under 26 U.S.C. 2(a)? Could the spouse have died in 2026, given the preface? Could a dependent child exist who is not listed?
4. Look for any other error in A, independent of B: the character of "estate income" (ordinary income, qualified dividends, capital gain, tax-exempt), whether it could be qualified business income, the self-employment loss, the Social Security computation, the credit for the elderly or disabled (the head is 61 and disabled), any deduction for the listed premiums, the senior deduction, AMT, NIIT.
5. Give one verdict, from these three:
   - **PolicyEngine correct**: A is what the law gives for the stated facts. Cite the law and the form lines.
   - **PolicyEngine wrong**: give the correct figure and the rule the engine misses.
   - **Scenario ambiguous**: name the input that is underspecified and show the two defensible readings. PolicyBench's own exclusion rule is: "An output is excluded from scoring for every model when its reference depends on an input or definition that the certified household data never carried and the prompt therefore never stated, and a careful reader could take the stated facts the other way."
   State your confidence and what would change your mind.

## Background the models did not see (use it for the verdict, not for step 1)

- The engine computed filing status itself; the benchmark does not pass one. Engine trace on policyengine-us main (commit 75cdd801, version 2.38.8): `main-75cdd801/key_variables.txt`, `main-75cdd801/scenario_039_trace.txt` (non-zero nodes) and `scenario_039_trace_full.txt`.
- The engine's rule for the status: `/Users/maxghenis/PolicyEngine/_pr_worktrees/pe-us-pb-cells-1010/policyengine_us/variables/household/demographic/tax_unit/surviving_spouse_eligible.py` and `filing_status.py` in the same folder.
- The household comes from the Current Population Survey. The data builder sets the flag from marital status "widowed": `/Users/maxghenis/PolicyEngine/policyengine-us-data/policyengine_us_data/datasets/cps/cps.py` line 447 (`cps["is_surviving_spouse"] = person.A_MARITL == 4`). That local clone may be behind upstream; say so if you rely on it.
- The fix that moved the reference from $1,345.51 to $8,596.03 is policyengine-us #10027 (commit fb9fa56871 in the worktree above): unspecified estate and trust income is gross income and is not qualified business income.

## Sources on disk (`law/`)

- `usc26_2.txt` (26 U.S.C. 2), `usc26_199A.txt` (26 U.S.C. 199A)
- `rp-25-32.txt` (Rev. Proc. 2025-32: 2026 rate tables in section 4.01, standard deduction in 4.14)
- `f1040.txt`, `f1040s1.txt` (2025 Form 1040 and Schedule 1), `i1040gi.txt` (2025 instructions: filing status, Social Security benefits worksheet)

If you need a provision that is not on disk, say which one and reason from what you know, marking it unverified.

## Output

Write your review to the output file as markdown: your own computation first, then the reconstruction of B, then the verdict with citations, then any other defect you found. Be exact with numbers. Do not soften a disagreement.
