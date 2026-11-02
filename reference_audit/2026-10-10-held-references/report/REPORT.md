# PolicyBench cells VA 039 and OH 025: who is right

2026-10-10. Both references are correct. In each cell the models' consensus applies a rule the law does not give them.

| Cell | Reference | Models' consensus | Verdict | Rule that differs |
|---|---:|---:|---|---|
| scenario_039 VA, federal income tax | $8,596.03 | $5,145.11 (6 models) | PolicyEngine correct | Filing status. The six models file the head as a qualifying surviving spouse. 26 U.S.C. 2(a)(1)(B) requires a dependent child living in the home, and the household has one person. |
| scenario_025 OH, state income tax | $1,916.61 | $1,589.56 (8 models) | PolicyEngine correct | The 2026 rate schedule. R.C. 5747.02(A)(3)(c) is "$332.00 plus 2.75% of the amount in excess of $26,050". The eight models drop the $332.00. They also take no medical deduction (worth $4.97). |

Neither cell needs a policyengine-us change, so there is no pull request and no hub hand-off. One engine gap outside both cells is filed as PolicyEngine/policyengine-us#10059 (last section).

## How this was checked

- Inputs: `scenarios.csv` in PolicyBench main (5a8164a0), sha256 71b16212…, identical in all 29 worktrees that carry it. The path in the request (`policybench-wt/sweep-pe2353`) no longer exists.
- Engine: policyengine-us upstream main at 75cdd8019e (version 2.38.8, policyengine-core 3.33.0), installed from a clean worktree. It contains #10027 (fb9fa56871), #10020 (abb68e377b), #10032 and #10034. The situations are built as `policybench.scenarios.Scenario.to_pe_household` builds them (`trace_cells.py`).
- Both references reproduce: $8,596.03 and $1,916.61. Traces: `main-75cdd801/` (`key_variables.txt`, `*_trace.txt`, `*_trace_full.txt`, `*_situation.json`).
- Model answers and explanations: `model_answers.md`, from the release's `predictions.csv.gz` (47 models).
- Law: read this session from the sources saved in `law/`. 2026 returns are not published, so form lines are the 2025 forms' and 2026 amounts come from Rev. Proc. 2025-32 and the Ohio Revised Code.
- Independent review: two GPT-6.1 Sol reviews, one per cell, briefed with the facts and the law but not with these verdicts (`brief_va039.md`, `brief_oh025.md`; results in `review_va039.md`, `review_oh025.md`). Both reproduce the arithmetic and reject the models' consensus. Each would still exclude its cell, on a ground the consensus does not raise. See "Independent review" below.

## VA 039: federal income tax before refundable credits

### What the models saw

One person: age 61, "is disabled", "is a surviving spouse", estate income $25,950, self-employment income -$6,260, Social Security retirement income $36,105, taxable IRA distributions $26,800, taxable private pension income $2,030, plus premiums and assets that do not move the answer. No other household member. The prompt states no filing status for any household; the engine and the models each derive it.

### The engine on upstream main

| Step | Value |
|---|---:|
| Filing status | Single (`surviving_spouse_eligible` false: no child dependent) |
| Estate income | 25,950.00 |
| Taxable IRA distributions | 26,800.00 |
| Taxable pension | 2,030.00 |
| Taxable Social Security | 30,689.25 |
| Self-employment loss | -6,260.03 |
| Adjusted gross income | 79,209.22 |
| Standard deduction | 16,100.00 |
| Itemized deductions (not used) | 3,793.91 |
| Qualified business income deduction | 0 (QBI is -6,260.03; estate income is not QBI) |
| Taxable income | 63,109.22 |
| Tax at ordinary rates | 8,596.03 |
| Capital gains tax, AMT, net investment income tax | 0 |
| Nonrefundable credits (elderly or disabled, saver's, others) | 0 |
| **Income tax before refundable credits** | **8,596.03** |

### By hand

1. **Filing status: single.** 26 U.S.C. 2(a)(1) defines "surviving spouse" for the rate tables as a taxpayer (A) whose spouse died in one of the two preceding tax years and (B) who maintains a home that is the principal place of abode of a dependent son, stepson, daughter or stepdaughter. The 2025 Form 1040 instructions say the same: a filer widowed before the year files Single, "But if you have a child, you may be able to use the qualifying surviving spouse filing status", and the Qualifying Surviving Spouse test requires a child or stepchild who lived in the home. The household has no child. The preface also rules out a death in 2026 (status facts are constant all year), so a joint return for the year of death is not available either.
2. **Gross income.** Estate income is gross income (26 U.S.C. 61(a)(14)); Schedule E Part III to Schedule 1 line 5. The self-employment loss is Schedule 1 line 3. Schedule 1 line 10 to Form 1040 line 8: 25,950.00 - 6,260.03 = 19,689.97. IRA distributions, line 4b: 26,800. Pensions, line 5b: 2,030.
3. **Social Security, lines 6a and 6b (26 U.S.C. 86).** Other income 48,519.97 plus half of benefits 18,052.50 gives 66,572.47. That is above the $34,000 adjusted base amount, so the taxable part is the lesser of 85% of benefits (30,689.25) and 0.85 x (66,572.47 - 34,000) + 4,500 = 32,186.60. Taxable: 30,689.25.
4. **AGI, line 11a:** 26,800 + 2,030 + 30,689.25 + 19,689.97 = 79,209.22.
5. **Standard deduction, line 12e:** $16,100 for an unmarried individual in 2026 (Rev. Proc. 2025-32, section 4.14). No additional amount: the head is 61 and not blind. No senior deduction (under 65).
6. **QBI deduction, line 13a:** 0. The only business item is a loss, which carries forward (26 U.S.C. 199A(c)(2)).
7. **Taxable income, line 15:** 63,109.22.
8. **Tax, line 16** (Rev. Proc. 2025-32, section 4.01, Table 3): 5,800 + 22% x (63,109.22 - 50,400) = **8,596.03**.
9. **Credits and other taxes.** The credit for the elderly or the disabled starts from at most $5,000 for a single filer and falls by half of AGI above $7,500 (26 U.S.C. 22(c) and (d)), so it is zero at this AGI. The net investment income tax starts at $200,000 of modified AGI (26 U.S.C. 1411(b)). The engine computes no self-employment tax, no alternative minimum tax and no additional tax on early distributions.

### The calculation behind $5,145.11

The six models use the same AGI and switch only the filing status: standard deduction $32,200 and the joint table (Rev. Proc. 2025-32, Table 1).

- Taxable income 79,209.25 - 32,200 = 47,009.25.
- Tax 2,480 + 12% x (47,009.25 - 24,800) = **5,145.11**.

Their explanations say so: "Filed as surviving spouse, which uses the joint brackets and joint standard deduction" (Claude Opus 5.5). None of the six mentions the dependent-child test. Two of the four models that match the reference state it: "surviving spouse with no dependent child cannot use qualifying-surviving-spouse status" (Kimi K3).

Two more models (GPT-5.6 Sol and GPT-5.6 Luna, about $4,485) make the same status error and also use the joint return's Social Security thresholds: taxable benefits 25,186.60, taxable income 41,506.57, tax 4,484.79.

### Verdict: PolicyEngine correct

The reference does not rest on an unlisted input. Whether the spouse died in 2024, 2025 or earlier is unknown, but the answer is Single either way because no child lives in the home.

One thing for PolicyBench to weigh. The prompt label "is a surviving spouse" is the Code's own name for the status that gets the joint table, and that is what misleads the six models. In the data the flag is only marital status. policyengine-us-data sets it as `A_MARITL == 4` (`cps.py` line 1212 on main), Microcosm does the same (`relationship_inputs.py` line 181 on main), and the Census codebook labels code 4 "Widowed". I did not find the June build commit (5da5a95) that produced the benchmark's data, so this is the mapping in both builders today. The engine adds the child test itself (`surviving_spouse_eligible.py`). A label such as "is widowed" would test the same law without the collision. Under the exclusion rule as written I read this cell as scored: a careful reader has the fact that settles it.

## OH 025: state income tax before refundable credits

### What the models saw

Married couple, no dependents. Head, 61: no wages, "has employer-sponsored insurance", "employer sponsored insurance premiums: $21,208", "health insurance premiums excluding Medicare Part B: $6,500", "other health insurance premiums: $6,500", "other medical expenses: $800", "over-the-counter health expenses: $50". Spouse, 57: wages $62,725, taxable private pension income $32,200, "has employer-sponsored insurance".

### The engine on upstream main

| Step | Value |
|---|---:|
| Federal AGI | 94,925.30 |
| Worksheet line 1 (premiums, not eligible for Medicare or an employer plan) | 0 |
| Worksheet line 3 (premiums, eligible for an employer plan) | 6,500.00 |
| Worksheet line 4 (other medical care) | 800.00 |
| Line 5 less 7.5% of federal AGI (7,119.40) = line 8 | 180.60 |
| Ohio AGI | 94,744.70 |
| Personal exemptions (2 x $1,900) | 3,800.00 |
| Ohio taxable nonbusiness income | 90,944.70 |
| Tax before nonrefundable credits | 2,116.61 |
| Retirement income credit | 200.00 |
| Joint filing credit | 0 (the head has no qualifying income) |
| **Income tax before refundable credits** | **1,916.61** |

### By hand

1. **Federal AGI, IT 1040 line 1:** 62,725.29 + 32,200.00 = 94,925.29.
2. **Medical deduction, Schedule of Adjustments line 44 (R.C. 5747.01(A)(10)).**
   - Division (a) deducts medical care insurance premiums in full, but not for a taxpayer "eligible to participate in any subsidized health plan maintained by any employer of the taxpayer or of the taxpayer's spouse". Both spouses have employer coverage, so worksheet line 1 is 0.
   - Division (b) deducts medical care the taxpayer paid, "to the extent not otherwise deducted or excluded" from federal AGI, above 7.5% of federal AGI. Division (c) takes the meaning of medical care from 26 U.S.C. 213, which includes insurance. The worksheet puts these premiums on line 3, and the Department's FAQ says the same of after-tax premiums paid by someone with an employer plan (questions 8 and 9).
   - Line 3: 6,500. Line 4: 800. The engine leaves out the $50 of over-the-counter expenses, in Ohio and in the federal itemized deduction: 26 U.S.C. 213(b) counts a medicine or drug only if it is prescribed or is insulin. Counting the $50 would give $1,915.23. Line 5: 7,300. Line 7: 7.5% x 94,925.29 = 7,119.40. Line 8: 180.60.
   - The $21,208 is the employer's payment (the engine documents the input as "Annual employer-paid health insurance premiums"). The taxpayer did not pay it, and it is excluded from income. The prompt supports this on its own: it gives the head's health insurance premiums, excluding Medicare Part B, as $6,500 in total, so the $21,208 cannot also be premiums the head paid.
3. **Ohio AGI, line 3:** 94,744.69.
4. **Exemptions, line 4 (R.C. 5747.025):** modified AGI above $80,000, so $1,900 each: 3,800. The 2025 booklet (p. 17) shows the amounts; H.B. 96 section 757.120(A) bars the Tax Commissioner from adjusting them, or the $26,050 threshold, "in 2025 or 2026". The Legislative Service Commission's as-enacted analysis lists that section and does not mark it vetoed.
5. **Taxable nonbusiness income, line 7:** 90,944.69.
6. **Tax, line 8a (R.C. 5747.02(A)(3)(c)):** "For taxable years beginning in 2026 and thereafter, $332.00 plus 2.75% of the amount in excess of $26,050." 332.00 + 2.75% x 64,894.69 = 2,116.60.
7. **Credits.** Retirement income credit, R.C. 5747.055(B): $200 for retirement income over $8,000 when modified AGI less exemptions is under $100,000 (it is 90,944.69). Joint filing credit, R.C. 5747.05(E)(1): each spouse needs at least $500 of qualifying income, and the head has none. The $20 exemption credit and the senior citizen credit do not apply.
8. **Result:** 2,116.60 - 200 = **1,916.60**. The engine gives 1,916.61 because it carries the base amount as 1.27448% x 26,050 = 332.002 (`rates.yaml`). That is the rate R.C. 5747.02(A)(2) sets for 2026, and (A)(5) derives the base amount from it.

### The calculation behind $1,589.56

- Ohio AGI 94,925 with no medical deduction, less 3,800 = 91,125.
- Tax 2.75% x (91,125 - 26,050) = 1,789.56, with no base amount.
- Less the $200 retirement income credit = **1,589.56**.

Claude Opus 5.5 writes the assumption down: "assuming no base amount is added to the 2026 schedule". The difference from the reference is 332.00 (the base amount) less 4.97 (2.75% of the 180.60 deduction they do not take) = 327.04.

Other answers reconstruct the same way:

| Answer | Reading | Check |
|---:|---|---|
| 1,921.57 (old reference; no model) | Base amount, no medical deduction | 332 + 2.75% x 65,075.29 - 200 |
| 1,742.81 (GPT-6.1 Sol) | Base amount; the $6,500 deducted in full on line 1 | 332 + 2.75% x 58,575 - 200 |
| 1,319.63 (GPT-6 Astra) | Base amount; the $21,208 counted as paid by the taxpayer; exemptions fall to $2,150 each | 332 + 2.75% x 43,186.38 - 200 |
| 1,950.25 (GPT-5.6 Sol) | The 2024 base amount, $360.69 | 360.69 + 2.75% x 65,075 - 200 |

### Verdict: PolicyEngine correct

The consensus is wrong on the statute's text. The 2.75% "flat tax" still carries a fixed $332.00 once income passes $26,050.

Two prompt labels are loose, and neither supports the consensus:

- "employer sponsored insurance premiums: $21,208" does not say who paid. One model counted it as the taxpayer's expense ($1,319.63). That reading contradicts the prompt's own total of $6,500 for the head's premiums. PolicyBench already tracks relabeling the input as employer-paid (PolicyEngine/policybench#165).
- The same $6,500 appears under two labels (the total and its component). The engine counts it once. Counting it twice would give $1,737.85; no group of models does.

The medical deduction itself follows from the listed facts. Federal AGI, as the engine and every model compute it, excludes none of the $6,500, so division (b)'s condition is met. The premiums are also listed on the head, who has no wages to take a pre-tax payroll deduction from.

## Independent review

Two GPT-6.1 Sol reviewers worked each cell from the law before seeing any answer. They were not told these verdicts.

**Where they agree with this report.** Every number: $8,596.03 and $5,145.11 for Virginia, $1,916.60 and $1,589.56 for Ohio, and each reconstruction above. Single is the filing status for a widow with no qualifying child ("above 99%"). Ohio's 2026 schedule carries the $332.00, the threshold and exemptions are frozen, and none of that was vetoed. Neither consensus answer is supported by the law.

**Where they differ.** Each reviewer's verdict is "scenario ambiguous", for a reason unrelated to the consensus:

| Cell | Reviewer's ground | Value under the other reading | Why this report does not adopt it |
|---|---|---:|---|
| VA 039 | "Estate income" does not state its character. If it were qualified dividends or long-term gain, the same $25,950 would be taxed at preferential rates. (75% confidence in excluding.) | $6,259.99 | The preface sets every unlisted numeric input to 0, and qualified dividends are a separate input. The engine defines the input as Schedule E Part III income, with dividends and gains in other inputs. PolicyBench's 2026-09-22 audit read it the same way (`reference_audit/2026-09-22/verification/v1_r03.md`), and the corrected value it recorded then is today's reference. No model reads the income as preferential. |
| OH 025 | "Employer sponsored insurance premiums: $21,208" does not state who paid. Read as paid by the head after tax, it is deductible. | $1,319.65, or $1,145.86 if the plan is also unsubsidized | The prompt gives the head's total premiums as $6,500, which leaves the $21,208 out. PolicyBench's 2026-10-06 verification weighed this reading (its R4) and called it inconsistent with that total; decision d1022 then set $1,916.60 as the value to regenerate to (`reference_audit/2026-10-05-reference-adversary/verification/independent/oh_025.md`). |

Both grounds are real wording gaps, and both were weighed in PolicyBench's earlier audits before these outputs returned to scoring. Whether either should now exclude a cell is a scoring-rule call for PolicyBench, not a question about the engine. It does not change the verdict on the models' consensus.

The Virginia reviewer raised one more point that reaches every federal cell, not this one alone: the Form 1040 instructions send filers with taxable income under $100,000 to the Tax Table, which would give $8,600 here (the midpoint of a $50 band, in whole dollars), where the reference applies the rate schedule exactly. No 2026 Tax Table exists yet.

## Engine observations that do not move either cell

- **Surviving-spouse status never expires.** The engine gives the status to any widowed head with a child dependent, with no limit to the two tax years after the death (26 U.S.C. 2(a)(1)(A)). The data has no date of death. Reproduction: 2026, head 45 with $60,000 of wages and a child of 10, files as surviving spouse ($640 of tax) where head of household gives $1,748. Filed as PolicyEngine/policyengine-us#10059 (https://github.com/PolicyEngine/policyengine-us/issues/10059), with a chip offered for the fix.
- **Ohio's employer-plan test is a proxy.** `oh_employer_subsidized_health_plan_eligible` treats having or being offered employer coverage as eligibility for a subsidized plan. The statute's test is that the employer pays some of the cost. The two differ only for an employer plan the employer pays nothing toward. Here the employer pays $21,208, so the result is the same. #10020's commit message states the rule in these terms.
- **Ohio's retirement income credit does not check that the pension was received "on account of retirement"** (R.C. 5747.055(A)(1)). The engine's own comment notes it.
