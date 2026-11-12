# Errata for the judge's texts in release dashboard-data-20261111

For each cell (one household and one output) that some model answered wrong, the judge, Claude Opus 5.5, writes a case note and a sentence for each wrong row. Release dashboard-data-20261111 publishes the judge's texts as written. This page lists the statements in the 122 re-judged cells that readers found wrong and checkers upheld. The readers and the checkers all ran on Claude Opus 5.5, the judge's own model.

Six readers marked 50 statements as false or unsupported in cells where the reference stands ([review record](wording_review.md)). The checkers then took each of the 50 in turn. They located the text in the frozen data, checked the correction against a primary source or PolicyBench's decision record, and checked that no score depends on it.

- They upheld 36 findings, two of them only in part; the parts they did not uphold have no entry. The 36 give the 105 entries below, in 31 cells; one finding can cover several rows.
- They did not uphold 6: the judge's text is right, or the objection is to a word and not to the law.
- They moved 8 to the open questions in the review record, because the corrected statement could put a reference in doubt or make an answer right.

The page does not cover the second read, in which readers running GPT-6.1 Sol marked 86 findings at the same level in the 559 cells Claude Fable 5.2 answered right: no checker has verified those, and they are not listed here, nor are the lesser wording findings of either read.

No entry changes a score. Each entry gives where the text sits (the case note, the note's hypothesis field, or a model's row), the text as published, the correction, a source, and why scoring is unaffected. The texts stay as published in this release.

## Entries

### `scenario_000 federal_income_tax_before_refundable_credits`

- **Where:** row for Gemini 3.5 Flash
  - **Text:** "OBBBA made the higher standard deduction ($16,100 + $2,050 aged), the $6,000 senior deduction and the 12% bracket permanent."
  - **Correction:** The $6,000 senior deduction is temporary, not permanent: 26 U.S.C. 151(d)(5)(C), added by P.L. 119-21, allows it only for taxable years beginning before January 1, 2029 (2025 through 2028). It does apply for 2026.
  - **Source:** https://www.law.cornell.edu/uscode/text/26/151
  - **Scoring:** The reference and the row's class stand: the deduction applies in 2026 either way, and the answer is wrong because it itemized, took a personal exemption and used a 15% bracket from pre-2018 law.

### `scenario_005 state_income_tax_before_refundable_credits`

- **Where:** row for GPT-6 Astra
  - **Text:** "kept the prior-year bracket schedule instead of indexing to 2026"
  - **Correction:** The reference uses California's 2025 tax rate schedule. California indexes its 2026 brackets by June 2026 price data, published after PolicyBench froze its references on 2026-07-03, so the reference holds the 2025 amounts FTB published (Cal. Rev. & Tax. Code 17041(h)); using the 2025 schedule is not an error.
  - **Source:** https://www.ftb.ca.gov/forms/2025/2025-540-tax-rate-schedules.pdf; convention c_ca_hold_2025 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json
  - **Scoring:** The reference and the row's class stand: the answer is wrong because the model subtracted the employer-sponsored insurance premiums from wages, putting CA AGI at $520,901 instead of $538,928, and took a $222 exemption credit instead of $114.

- **Where:** row for GPT-6.1 Sol
  - **Text:** "kept the latest prior-year bracket schedule unindexed for 2026"
  - **Correction:** The reference uses California's 2025 tax rate schedule. California indexes its 2026 brackets by June 2026 price data, published after PolicyBench froze its references on 2026-07-03, so the reference holds the 2025 amounts FTB published (Cal. Rev. & Tax. Code 17041(h)); using the 2025 schedule is not an error.
  - **Source:** https://www.ftb.ca.gov/forms/2025/2025-540-tax-rate-schedules.pdf; convention c_ca_hold_2025 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json
  - **Scoring:** The reference and the row's class stand: the answer is wrong because the model subtracted the employer-sponsored insurance premiums from wages, putting CA AGI at $520,901 instead of $538,928, and took a $222 exemption credit instead of $114.

- **Where:** row for MiniMax M3
  - **Text:** "the federal $10,000 SALT cap"
  - **Correction:** For tax year 2026 the federal cap on the state and local tax deduction is $40,400, reduced by 30% of modified AGI above $505,000 but never below $10,000 (26 U.S.C. 164(b)(6)-(7), as amended by P.L. 119-21), which is about $28,977 for this joint return. California applies no such cap.
  - **Source:** https://www.law.cornell.edu/uscode/text/26/164
  - **Scoring:** The reference and the row's class stand: the answer of $0 is wrong because the model imputed mortgage interest that was not listed and concluded no tax was due on $518,408 of California taxable income.

### `scenario_008 payroll_tax`

- **Where:** row for Qwen 3.7 Max
  - **Text:** "It used 2024 rates that set employee TDI and FLI to 0%"
  - **Correction:** New Jersey's 2024 worker rates set TDI to 0% but FLI to 0.09%, so 2024 rates do not set both to 0%. For 2026 the worker rates are 0.19% for TDI and 0.23% for FLI (New Jersey Department of Labor and Workforce Development).
  - **Source:** https://www.nj.gov/labor/ea/employer-services/rate-info/index.shtml
  - **Scoring:** The reference and the row's class stand: the answer is wrong because it left out the 2026 TDI (0.19%), FLI (0.23%) and workforce-fund (0.0425%) contributions.

### `scenario_008 snap`

- **Where:** row for Claude Fable 5
  - **Text:** "using FY2025 figures ($258 standard deduction, $1,756 maximum)"
  - **Correction:** $1,756 was the FY2025 maximum allotment for eight people, but $258 was not an FY2025 standard deduction: for fiscal year 2025 (October 2024 to September 2025) the standard deduction for a household of six or more in the 48 states and DC was $291 (USDA SNAP FY2025 cost-of-living adjustments, 7 CFR 273.9(d)(1)).
  - **Source:** https://dhs.maryland.gov/documents/FIA/Action%20Transmittals-AT%20-%20Information%20Memo-IM/AT-IM2025/25-05%20AT%20Revised%20SNAP%20Mass%20Changes%20for%20October%202024.pdf (restates the USDA FY2025 table; USDA's own page: https://www.fns.usda.gov/snap/fy-2025-cola)
  - **Scoring:** The reference and the row's class stand: the reference uses the FY2026 figures ($299 and $1,789), and the answer is wrong because the model replaced its computation with an unexplained $687 a month estimate.

### `scenario_014 state_income_tax_before_refundable_credits`

- **Where:** rows for Claude Fable 5.2 and GPT-6 Sol
  - **Text:** "2026 trigger cut"
  - **Correction:** The 2026 rates of 2.11% to 4.58% were not a revenue-trigger cut: West Virginia's SB 392 (2026) enacted them directly as W. Va. Code 11-21-4j for taxable years beginning on or after January 1, 2026, and its revenue-trigger reductions (W. Va. Code 11-21-4h) apply only from 2027.
  - **Source:** https://www.wvlegislature.gov/Bill_Text_HTML/2026_SESSIONS/RS/bills/sb392%20sub1%20enr.pdf
  - **Scoring:** The reference and the rows' class stand: both answers are wrong because they applied the 2025 schedule (2.22% to 4.82%) instead of the 2026 one.

### `scenario_022 federal_income_tax_before_refundable_credits`

- **Where:** case note
  - **Text:** "The correct path is to itemize $29,736: SALT of $14,888, which is property tax plus about $6,059 of estimated CA income tax"
  - **Correction:** The prompt lists no California income tax withheld or paid during 2026, and 26 U.S.C. 164(a)(3) allows state income tax in the year it is paid, so this part of SALT is not given. The $6,059 is the engine's formula estimate of California withholding on the whole federal AGI, not an estimate of California income tax; read as the household paying its 2026 California tax (the engine's $2,505.87) during the year, the deduction is smaller and the tax is $11,895.23.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (decision of 2026-10-05 on this cell); paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json
  - **Scoring:** No score moves: the output is excluded from scoring for every model because its reference depends on this unlisted input.

- **Where:** row for Claude Fable 5.1
  - **Text:** "added an invented $2,000 charitable deduction for non-itemizers"
  - **Correction:** The deduction is not invented: from 2026, 26 U.S.C. 170(p), as amended by P.L. 119-21 section 70424, lets a taxpayer who does not itemize deduct up to $1,000 of cash gifts ($2,000 on a joint return). It does not apply here, because the head files single and itemizes, and a qualifying-surviving-spouse return would not be a joint return.
  - **Source:** https://www.law.cornell.edu/uscode/text/26/170
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the row's other stated errors (qualifying-surviving-spouse status and joint brackets without a dependent child, and the unphased senior deduction) stand.

- **Where:** row for GPT-6 Sol
  - **Text:** "understates CA income tax in SALT by about $3,300"
  - **Correction:** The shortfall is measured against the engine's formula estimate of California withholding on federal AGI ($6,059), an amount the prompt does not give: it lists no California income tax withheld or paid during 2026 (26 U.S.C. 164(a)(3)). The household's California tax as the engine computes it is $2,505.87.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (decision of 2026-10-05 on this cell); paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the row's other stated error, the missing $910 QBI deduction, stands.

- **Where:** row for Kimi K3
  - **Text:** "instead of about $6,059"
  - **Correction:** The $6,059 is not an established amount: the prompt lists no California income tax withheld or paid during 2026 (26 U.S.C. 164(a)(3) allows it in the year paid), and $6,059 is the engine's formula estimate of withholding on federal AGI. The household's California tax as the engine computes it is $2,505.87.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (decision of 2026-10-05 on this cell); paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the row's other stated errors (no QBI deduction and no 0.5% floor on charity) stand.

- **Where:** rows for DeepSeek V4 Pro and Grok 4.6
  - **Text:** "(about $6,059 is correct)"
  - **Correction:** No amount is established as correct: the prompt lists no California income tax withheld or paid during 2026 (26 U.S.C. 164(a)(3) allows it in the year paid). The $6,059 is the engine's formula estimate of California withholding on federal AGI; the household's California tax as the engine computes it is $2,505.87.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (decision of 2026-10-05 on this cell); paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and each row's other stated errors (pre-2018 law and the missing senior and QBI deductions; off bracket thresholds) stand.

### `scenario_023 snap`

- **Where:** case note
  - **Text:** "$298 − $262.80 = $35.20 a month"
  - **Correction:** 30% of the $876.51 net income is $262.95, not $262.80, and SNAP benefits come out in whole dollars: the state rounds 30% of net income up to the next dollar or rounds the allotment down (7 CFR 273.10(e)(2)(ii)(A)), which gives $34 a month when net income is rounded to $877 (7 CFR 273.10(e)(1)(ii)), or $35 if cents are kept, not $35.20.
  - **Source:** https://www.law.cornell.edu/cfr/text/7/273.10
  - **Scoring:** The output is excluded from scoring for every model because the reference depends on an unstated disability fact, so no score moves.

- **Where:** case note
  - **Text:** "$48.18 a month for the last 3 months (higher maximum allotment), or $461.34 in total"
  - **Correction:** PolicyBench holds October to December 2026 at USDA's FY2026 SNAP figures, the last published before the 2026-07-03 reference freeze, so the $298 maximum applies in all twelve months and no higher allotment applies in the last three; with net income rounded to the dollar this reading gives $34 a month, $408 for the year. The $461.34 is the frozen engine's value, kept for this output because the output is excluded.
  - **Source:** docs/benchmark_card.md (publication conventions) and reference_audit/2026-09-22/root_causes.json (c_snap_hold_fy2026)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; no model answered within $1 of $408 (or of $420, the figure if cents are kept).

- **Where:** row for GLM-5.3-Flash (preview)
  - **Text:** "It also annualized a flat $298 maximum allotment and missed the higher $304.68 maximum in the last three months, which raises those months to $48.18."
  - **Correction:** Using the $298 maximum in all twelve months is right: PolicyBench holds October to December 2026 at USDA's FY2026 figures, the last published before the 2026-07-03 reference freeze, and $304.68 is the frozen engine's projection, not a USDA maximum allotment.
  - **Source:** docs/benchmark_card.md (publication conventions) and reference_audit/2026-09-22/root_causes.json (c_snap_hold_fy2026)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the answer ($402) is off for the reason the row's first sentence gives, the FY2025 standard deduction.

- **Where:** row for Kimi K3
  - **Text:** "for $461.34 a year"
  - **Correction:** $461.34 is the frozen engine's value, which uses a projected higher allotment for October to December and unrounded benefits; under PolicyBench's convention of holding October to December 2026 at USDA's FY2026 figures, and with SNAP's whole-dollar rounding (7 CFR 273.10(e)(2)(ii)(A)), this reading gives $34 a month with net income rounded to the dollar, $408 a year.
  - **Source:** docs/benchmark_card.md (publication conventions); reference_audit/2026-09-22/root_causes.json (c_snap_hold_fy2026); https://www.law.cornell.edu/cfr/text/7/273.10
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the model returned no answer.

- **Where:** rows for Claude Fable 5, Claude Fable 5.2, Claude Haiku 4.5, Claude Haiku 5.5, Claude Opus 5, Claude Sonnet 5, Claude Sonnet 5.5, DeepSeek V4 Pro 0813, Gemini 3 Flash Preview, Gemini 3.1 Flash Lite Preview, Gemini 3.5 Flash, Gemini 3.5 Flash Lite, Gemini 3.6 Flash, Gemini 4 Argon, GLM-5.3, GPT-5.4 mini, GPT-5.4 nano, GPT-5.6 Sol, GPT-5.6 Terra, GPT-6 Sol, GPT-6.1 Terra, Grok 4.3, Inkling, Kimi K2.6, MiniMax M3, Muse Wonder, Qwen 3.7 Max and Qwen 3.8 Max
  - **Text:** "$35.20"
  - **Correction:** Each of these rows gives $35.20 a month as the benefit, but SNAP benefits come out in whole dollars (7 CFR 273.10(e)(2)(ii)(A)): on the $876.51 net income this reading gives $34 a month with net income rounded to $877, or $35 if cents are kept.
  - **Source:** https://www.law.cornell.edu/cfr/text/7/273.10
  - **Scoring:** The output is excluded from scoring for every model, so no score moves.

### `scenario_023 ssi`

- **Where:** case note
  - **Text:** "Both models that gave numbers read the generic 'is disabled' flag as automatic SSI eligibility"
  - **Correction:** Reading the disability input as meeting SSI's disability test is not itself an error here: the prompt does not settle whether the head meets SSI's definition of disability, and PolicyBench's decision for this household holds that a careful reader could take the facts either way. SSI is $0 under either reading, because the head's countable income, including the $8,000 403(b) distribution, exceeds the federal benefit rate.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_023 snap, decided 2026-09-05)
  - **Scoring:** The reference ($0) and each row's llm_error class stand: both answers are wrong because of income errors, one leaving out the $8,000 403(b) distribution and the other using the combined federal and California payment level.

- **Where:** row for Claude Fable 5.2
  - **Text:** "The model treated the 'is disabled' input as automatically meeting SSI's disability category."
  - **Correction:** That reading is not itself an error: the prompt does not settle whether the head meets SSI's definition of disability, and PolicyBench's decision for this household holds that a careful reader could take the facts either way. SSI is $0 under either reading, because countable income including the 403(b) distribution exceeds the federal benefit rate.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_023 snap, decided 2026-09-05)
  - **Scoring:** The reference ($0) and the row's llm_error class stand: the answer is wrong because the model left the $8,000 403(b) distribution out of unearned income.

- **Where:** row for GLM-5.2
  - **Text:** "The model said 'the head is disabled and eligible for SSI' based only on the generic disability flag."
  - **Correction:** That reading is not itself an error: the prompt does not settle whether the head meets SSI's definition of disability, and PolicyBench's decision for this household holds that a careful reader could take the facts either way. SSI is $0 under either reading, because countable income exceeds the federal benefit rate.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_023 snap, decided 2026-09-05)
  - **Scoring:** The reference ($0) and the row's llm_error class stand: the answer is wrong because the model used the combined federal and California payment level for the federal SSI output and applied the $20 general exclusion twice.

### `scenario_023 state_refundable_credits`

- **Where:** case note
  - **Text:** "earned income ($17,442.65 in wages)"
  - **Correction:** Earned income for the CalEITC counts wages only if they are includible in gross income (26 U.S.C. 32(c)(2)(A)(i), as adopted by Cal. Rev. & Tax. Code 17052(c)(4)), and a traditional 401(k) deferral is not (26 U.S.C. 402(e)(3), adopted by Cal. Rev. & Tax. Code 17501), so earned income here is about $14,664. The phase-out still runs on AGI of $22,534.34, which is greater.
  - **Source:** https://www.law.cornell.edu/uscode/text/26/32 ; https://california.public.law/codes/revenue_and_taxation_code_section_17052
  - **Scoring:** No score moves: AGI exceeds earned income under either figure, so the phase-out base and the $95.15 reference stand.

- **Where:** row for Claude Fable 5
  - **Text:** "The model cut earned income to $14,665 by subtracting the 401(k) deferral"
  - **Correction:** Subtracting the deferral was right: CalEITC earned income counts wages only if includible in gross income (26 U.S.C. 32(c)(2)(A)(i), adopted by Cal. Rev. & Tax. Code 17052(c)(4)), and a traditional 401(k) deferral is not (26 U.S.C. 402(e)(3)), so earned income is about $14,664.
  - **Source:** https://www.law.cornell.edu/uscode/text/26/32 ; https://california.public.law/codes/revenue_and_taxation_code_section_17052
  - **Scoring:** The reference and the row's class stand: the answer is wrong because $402 exceeds the childless maximum and the model never ran the phase-out on AGI of $22,534.

- **Where:** row for DeepSeek V4 Flash 0731
  - **Text:** "Earned income is $17,443"
  - **Correction:** Earned income for the CalEITC is about $14,664: wages count only if includible in gross income (26 U.S.C. 32(c)(2)(A)(i), adopted by Cal. Rev. & Tax. Code 17052(c)(4)), and the 401(k) deferral is excluded (26 U.S.C. 402(e)(3)).
  - **Source:** https://www.law.cornell.edu/uscode/text/26/32 ; https://california.public.law/codes/revenue_and_taxation_code_section_17052
  - **Scoring:** The reference and the row's class stand: the answer is wrong because it sits near the maximum credit, while AGI of $22,534, which exceeds either earned-income figure, puts the filer deep in the phase-out.

### `scenario_025 state_income_tax_before_refundable_credits`

- **Where:** row for Grok Build 0.1
  - **Text:** "the 2026 schedule is $332 plus 2.75% up to $100,000"
  - **Correction:** For 2026 Ohio taxes all nonbusiness income over $26,050 at $332 plus 2.75% of the excess, with no break at $100,000 (R.C. 5747.02 as amended by H.B. 96 of 2025); the $100,000 break applied only in 2025.
  - **Source:** https://www.lsc.ohio.gov/assets/legislation/136/hb96/en0/files/hb96-tax-bill-analysis-as-enacted-136th-general-assembly.pdf
  - **Scoring:** The reference and the row's class stand: taxable income is below $100,000 either way, and the answer is wrong because of the $2,650 exemptions, the invented 3.5% bracket and the missing $200 retirement income credit.

### `scenario_028 child3_chip_eligible`

- **Where:** row for Qwen 3.7 Max
  - **Text:** "Both claims are wrong."
  - **Correction:** Under Pennsylvania law only the first claim is wrong: Pennsylvania's CHIP has no upper income limit, because children in families above 314% of the poverty line can enroll in Full-Cost CHIP. The output asks for eligibility under PolicyEngine's rules, which apply a 319% cap (314% plus the 5-point disregard), the limit for the free and low-cost tiers; in that frame the second claim is wrong too. Every tier excludes a child covered by a group health plan.
  - **Source:** https://www.pa.gov/content/dam/copapwp-pagov/en/dhs/documents/chip/eligibility-and-benefits/documents/chip-enrollment-and-benefits-handbook.pdf
  - **Scoring:** The reference and the row's class stand: the household's income passes under either reading, and the answer is wrong because Child 3's employer-sponsored insurance bars every tier of CHIP.

### `scenario_028 free_school_meals_eligible`

- **Where:** case note
  - **Text:** "income (1.82 times the poverty guideline, the reduced-price tier)"
  - **Correction:** Counting the $1,267 of child support, which school meal applications count as income (7 CFR 245.6(a)(5)(ii)), the household's $61,277 is 1.86 times the 2026 poverty guideline for four ($33,000) and above the 185% reduced-price limit of $61,050 for the 2026-27 school year, so it is in the paid tier, not the reduced-price tier; 1.82 is the ratio without the child support.
  - **Source:** https://www.pa.gov/agencies/education/newsroom/new-eligibility-guidelines-for-free-and-reduced-school-meals-announced-for-the-2026-27-school-year ; https://www.law.cornell.edu/cfr/text/7/245.6
  - **Scoring:** The reference and the rows' class stand: the output rests on Pennsylvania's universal free breakfast, not the lunch tier, and every answer of 0 is wrong because the model did not apply it.

- **Where:** row for Claude Fable 5.2
  - **Text:** "Income is actually 1.82 times FPL (reduced-price lunch)"
  - **Correction:** Counting the $1,267 of child support (7 CFR 245.6(a)(5)(ii)), income is $61,277, 1.86 times the 2026 poverty guideline for four and above the $61,050 reduced-price limit for 2026-27, so lunch is in the paid tier; 1.82 is the ratio without the child support.
  - **Source:** https://www.pa.gov/agencies/education/newsroom/new-eligibility-guidelines-for-free-and-reduced-school-meals-announced-for-the-2026-27-school-year ; https://www.law.cornell.edu/cfr/text/7/245.6
  - **Scoring:** The reference and the row's class stand: the answer of 0 is wrong because the model did not apply Pennsylvania's universal free breakfast.

- **Where:** row for Claude Opus 4.7
  - **Text:** "wrongly put the household above the reduced-price limit; its income is actually 1.82 times FPL"
  - **Correction:** The household is above the reduced-price limit: counting the $1,267 of child support (7 CFR 245.6(a)(5)(ii)), income is $61,277, 1.86 times the 2026 poverty guideline for four, above the 185% limit of $61,050 for 2026-27; 1.82 is the ratio without the child support.
  - **Source:** https://www.pa.gov/agencies/education/newsroom/new-eligibility-guidelines-for-free-and-reduced-school-meals-announced-for-the-2026-27-school-year ; https://www.law.cornell.edu/cfr/text/7/245.6
  - **Scoring:** The reference and the row's class stand: the answer of 0 is wrong because the model did not apply Pennsylvania's universal free breakfast, as the row's last sentence says.

- **Where:** row for Claude Opus 4.8
  - **Text:** "wrongly said income also exceeds the 185% reduced-price limit, when income is 1.82 times FPL"
  - **Correction:** Income does exceed the reduced-price limit: counting the $1,267 of child support (7 CFR 245.6(a)(5)(ii)), it is $61,277, 1.86 times the 2026 poverty guideline for four, above the 185% limit of $61,050 for 2026-27; 1.82 is the ratio without the child support.
  - **Source:** https://www.pa.gov/agencies/education/newsroom/new-eligibility-guidelines-for-free-and-reduced-school-meals-announced-for-the-2026-27-school-year ; https://www.law.cornell.edu/cfr/text/7/245.6
  - **Scoring:** The reference and the row's class stand: the answer of 0 is wrong because the model did not apply Pennsylvania's universal free breakfast, as the row's last sentence says.

### `scenario_032 state_refundable_credits`

- **Where:** case note
  - **Text:** "an indexed child credit of about $1,823 plus the capped working-family part of about $365"
  - **Correction:** For 2026 the child credit is $1,800 per child (Minn. Stat. 290.0661, subd. 3, as indexed by the Department of Revenue) and the working-family part is 4% of earned income up to $9,690, or $387.60 (Minn. Stat. 290.0671, subd. 1). The reference of $2,187.60 is $1,800 + $387.60, not an across-the-board 4.17% increase on $2,100.
  - **Source:** https://www.revenue.state.mn.us/sites/default/files/2025-12/inflation-adjusted-amounts-2026.pdf
  - **Scoring:** The reference and the case's class stand: $1,800 + $387.60 = $2,187.60, and no model's answer equals it.

- **Where:** case note
  - **Text:** "the indexed joint threshold of about $36,460"
  - **Correction:** The 2026 joint phase-out threshold for the Child and Working Family Credit is $38,770 (Minn. Stat. 290.0661, subd. 4, as indexed by the Department of Revenue); AGI of $30,916 is below it, so no phase-out applies.
  - **Source:** https://www.revenue.state.mn.us/sites/default/files/2025-12/inflation-adjusted-amounts-2026.pdf
  - **Scoring:** The reference and the case's class stand: no phase-out applies under either threshold.

- **Where:** rows for Claude Fable 5, Claude Fable 5.1, Claude Fable 5.2, Claude Opus 4.7, Claude Opus 4.8, Claude Opus 5.5, Claude Sonnet 4.6, Claude Sonnet 5.5, DeepSeek V4 Flash 0731, DeepSeek V4 Pro, DeepSeek V4 Pro 0813, DeepSeek V4.1 Flash, Gemini 3 Flash Preview, Gemini 3.1 Pro Preview, Gemini 3.5 Flash, Gemini 3.5 Flash Lite, Gemini 3.6 Flash, Gemini 3.7 Flash, Gemini 3.8 Flash, Gemini 4 Argon, GLM-5.2, GPT-5.5, GPT-5.6 Luna, GPT-5.6 Sol, GPT-5.6 Terra, GPT-6 Astra, GPT-6 Luna, GPT-6 Sol, GPT-6.1 Sol, GPT-6.1 Terra, Grok 4.5, Grok 4.6, Grok 4.7, Grok Build 0.1, Inkling, Kimi K3, Muse Spark 1.3, Muse Wonder, GLM-5.3-Flash (preview), Qwen 3.7 Max and Qwen 3.8 Max
  - **Text:** "$365"
  - **Correction:** The 2026 working-family part is 4% of earned income up to $9,690, so its maximum is $387.60, not about $365 (Minn. Stat. 290.0671, subd. 1, as indexed by the Department of Revenue).
  - **Source:** https://www.revenue.state.mn.us/sites/default/files/2025-12/inflation-adjusted-amounts-2026.pdf
  - **Scoring:** The reference and each row's class stand: each answer is still off $2,187.60 for the reason the rest of its row gives.

- **Where:** rows for Claude Fable 5.1, Claude Fable 5.2, Claude Opus 4.7, Claude Opus 4.8, Claude Opus 5.5, Claude Sonnet 4.6, Claude Sonnet 5.5, DeepSeek V4 Pro, DeepSeek V4 Pro 0813, DeepSeek V4.1 Flash, Gemini 3.1 Pro Preview, Gemini 3.5 Flash, Gemini 3.5 Flash Lite, Gemini 3.6 Flash, Gemini 3.7 Flash, Gemini 3.8 Flash, Gemini 4 Argon, GLM-5.2, GPT-5.5, GPT-5.6 Sol, GPT-6 Astra, GPT-6 Luna, GPT-6 Sol, GPT-6.1 Sol, Grok 4.3, Grok 4.5, Grok 4.6, Grok Build 0.1, Kimi K3, Muse Spark 1.3, Muse Wonder, Qwen 3.7 Max and Qwen 3.8 Max
  - **Text:** "$1,823"
  - **Correction:** The 2026 Minnesota child credit is $1,800 per child, not about $1,823 (Minn. Stat. 290.0661, subd. 3, as indexed by the Department of Revenue).
  - **Source:** https://www.revenue.state.mn.us/sites/default/files/2025-12/inflation-adjusted-amounts-2026.pdf
  - **Scoring:** The reference and each row's class stand: each answer is still off $2,187.60 for the reason the rest of its row gives.

- **Where:** rows for Claude Fable 5.2, GPT-6 Astra and GPT-6.1 Sol
  - **Text:** "instead of about $365"
  - **Correction:** The model's working-family amount was right: for 2026 that part is 4% of earned income up to $9,690, or $387.60 (Minn. Stat. 290.0671, subd. 1, as indexed by the Department of Revenue). The model's only error was the child credit, which is $1,800 for 2026, not $1,750.
  - **Source:** https://www.revenue.state.mn.us/sites/default/files/2025-12/inflation-adjusted-amounts-2026.pdf
  - **Scoring:** The reference and each row's class stand: each answer is short of $2,187.60 because the model used a $1,750 child credit instead of $1,800.

- **Where:** rows for Claude Opus 5, Gemini 3 Flash Preview, GLM-5.3 and GLM-5.3-Flash (preview)
  - **Text:** "$36,460"
  - **Correction:** The 2026 joint phase-out threshold is $38,770, not about $36,460 (Minn. Stat. 290.0661, subd. 4, as indexed by the Department of Revenue); AGI of $30,916 is below either figure.
  - **Source:** https://www.revenue.state.mn.us/sites/default/files/2025-12/inflation-adjusted-amounts-2026.pdf
  - **Scoring:** The reference and each row's class stand: no phase-out applies at $30,916, so each row's charge that the model applied one still holds.

### `scenario_033 federal_income_tax_before_refundable_credits`

- **Where:** case note
  - **Text:** "or dropping the $243 refund"
  - **Correction:** Leaving out the $243 state tax refund is a reading the facts allow, not an unsupported deduction: under 26 U.S.C. 111(a) a refund of a deducted tax is income only to the extent the earlier deduction reduced federal tax, and the prompt does not say whether it did. Read that way, the tax is $3,788.99.
  - **Source:** https://www.law.cornell.edu/uscode/text/26/111 ; annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (decision of 2026-09-29 on this cell)
  - **Scoring:** No score moves: the output is excluded from scoring for every model because its reference depends on this unlisted fact.

- **Where:** row for Claude Fable 5
  - **Text:** "It left the $243 state tax refund out of gross income"
  - **Correction:** Leaving out the refund is not an error the facts establish: under 26 U.S.C. 111(a) a refund of a deducted tax is income only to the extent the earlier deduction reduced federal tax, and the prompt does not say whether it did. Read that way, the tax is $3,788.99, the figure the model itself computed.
  - **Source:** https://www.law.cornell.edu/uscode/text/26/111 ; annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (decision of 2026-09-29 on this cell)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the row's other stated error stands: the model reported $3,699, which contradicts its own $3,789.

- **Where:** rows for Claude Opus 4.7 and Grok 4.7
  - **Text:** "left out the $243 state refund"
  - **Correction:** Leaving out the refund is not an error the facts establish: under 26 U.S.C. 111(a) a refund of a deducted tax is income only to the extent the earlier deduction reduced federal tax, and the prompt does not say whether it did.
  - **Source:** https://www.law.cornell.edu/uscode/text/26/111 ; annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (decision of 2026-09-29 on this cell)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and each row's other stated error, a wrong top for the 10% bracket, stands.

- **Where:** rows for Claude Sonnet 5, Gemini 3 Flash Preview, Gemini 3.5 Flash, Gemini 3.6 Flash and Gemini 3.7 Flash
  - **Text:** "left out the $243 refund"
  - **Correction:** Leaving out the refund is not an error the facts establish: under 26 U.S.C. 111(a) a refund of a deducted tax is income only to the extent the earlier deduction reduced federal tax, and the prompt does not say whether it did.
  - **Source:** https://www.law.cornell.edu/uscode/text/26/111 ; annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (decision of 2026-09-29 on this cell)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and each row's other stated errors (pre-2018 law, a wrong standard deduction or a missing senior deduction) stand.

### `scenario_043 snap`

- **Where:** case note
  - **Text:** "so every month pays the one-person contiguous-states maximum allotment of $298"
  - **Correction:** USDA raised the one-person maximum allotment in the 48 states and DC to $306 from October 1, 2026, in its fiscal year 2027 adjustment published August 21, 2026. The reference keeps $298 for October through December because PolicyBench uses only amounts published before it froze its references on 2026-07-03.
  - **Source:** https://www.fns.usda.gov/snap/allotment/cola ; convention c_snap_hold_fy2026 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json
  - **Scoring:** The reference ($3,576) stands under PolicyBench's freeze rule, and no model's answer becomes right under it. Grok Build 0.1 and Inkling answered $3,600, which equals the year's total in law (nine months at $298 and three at $306), by rounding the maximum to about $300 a month; under the freeze rule both are scored wrong.

- **Where:** row for Claude Fable 5.2
  - **Text:** "but the one-person maximum stays at $298 in those months"
  - **Correction:** In law the one-person maximum rose to $306 from October 1, 2026 (USDA's fiscal year 2027 adjustment, published August 21, 2026), so an October-to-December increase is not itself an error. The reference keeps $298 in those months because PolicyBench uses only amounts published before its 2026-07-03 reference freeze.
  - **Source:** https://www.fns.usda.gov/snap/allotment/cola ; convention c_snap_hold_fy2026 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json
  - **Scoring:** The reference and the row's class stand: under the freeze rule every month takes $298, and the model's $304 for October to December is neither that nor USDA's published $306.

- **Where:** row for DeepSeek V4 Pro
  - **Text:** "For tax year 2026 the one-person maximum is $298 a month"
  - **Correction:** The one-person maximum is $298 from January through September 2026 and $306 from October 1, 2026 (USDA's fiscal year 2027 adjustment, published August 21, 2026). The reference uses $298 in every month because PolicyBench uses only amounts published before its 2026-07-03 reference freeze.
  - **Source:** https://www.fns.usda.gov/snap/allotment/cola ; convention c_snap_hold_fy2026 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json
  - **Scoring:** The reference and the row's class stand: the answer is wrong because the model used the fiscal year 2025 maximum of $292.

- **Where:** row for Gemini 3 Flash Preview
  - **Text:** "The one-person maximum for 2026 is $298"
  - **Correction:** The one-person maximum is $298 from January through September 2026 and $306 from October 1, 2026 (USDA's fiscal year 2027 adjustment, published August 21, 2026). The reference uses $298 in every month because PolicyBench uses only amounts published before its 2026-07-03 reference freeze.
  - **Source:** https://www.fns.usda.gov/snap/allotment/cola ; convention c_snap_hold_fy2026 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json
  - **Scoring:** The reference and the row's class stand: the answer ($3,504) is wrong because the model applied the fiscal year 2025 maximum of $292.

- **Where:** row for Gemini 3.1 Pro Preview
  - **Text:** "The 2026 figure is $298"
  - **Correction:** The one-person maximum is $298 from January through September 2026 and $306 from October 1, 2026 (USDA's fiscal year 2027 adjustment, published August 21, 2026). The reference uses $298 in every month because PolicyBench uses only amounts published before its 2026-07-03 reference freeze.
  - **Source:** https://www.fns.usda.gov/snap/allotment/cola ; convention c_snap_hold_fy2026 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json
  - **Scoring:** The reference and the row's class stand: the answer ($3,492) is wrong because the model used the fiscal year 2024 maximum of $291.

- **Where:** row for Gemini 3.8 Flash
  - **Text:** "For 2026 the one-person maximum is $298"
  - **Correction:** The one-person maximum is $298 from January through September 2026 and $306 from October 1, 2026 (USDA's fiscal year 2027 adjustment, published August 21, 2026). The reference uses $298 in every month because PolicyBench uses only amounts published before its 2026-07-03 reference freeze.
  - **Source:** https://www.fns.usda.gov/snap/allotment/cola ; convention c_snap_hold_fy2026 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json
  - **Scoring:** The reference and the row's class stand: the answer ($3,504) is wrong because the model used the fiscal year 2025 maximum of $292.

- **Where:** row for Grok 4.6
  - **Text:** "The one-person maximum applicable throughout 2026 is $298"
  - **Correction:** The one-person maximum is $298 from January through September 2026 and $306 from October 1, 2026 (USDA's fiscal year 2027 adjustment, published August 21, 2026). The reference uses $298 in every month because PolicyBench uses only amounts published before its 2026-07-03 reference freeze.
  - **Source:** https://www.fns.usda.gov/snap/allotment/cola ; convention c_snap_hold_fy2026 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json
  - **Scoring:** The reference and the row's class stand: the answer is wrong because the model used the outdated $292 maximum.

- **Where:** rows for DeepSeek V4 Pro 0813, Gemini 3.6 Flash, Gemini 3.7 Flash, Gemini 4 Argon, Grok 4.5 and Muse Spark 1.3
  - **Text:** "The 2026 one-person maximum is $298"
  - **Correction:** The one-person maximum is $298 from January through September 2026 and $306 from October 1, 2026 (USDA's fiscal year 2027 adjustment, published August 21, 2026). The reference uses $298 in every month because PolicyBench uses only amounts published before its 2026-07-03 reference freeze.
  - **Source:** https://www.fns.usda.gov/snap/allotment/cola ; convention c_snap_hold_fy2026 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json
  - **Scoring:** The reference and each row's class stand: each answer ($3,504) is wrong because the model used the fiscal year 2025 maximum of $292.

### `scenario_051 state_income_tax_before_refundable_credits`

- **Where:** case note
  - **Text:** "For 2026 the deduction is $12,835"
  - **Correction:** Louisiana's first published 2026 standard deduction for single filers is $12,838 (Louisiana Department of Revenue, Revenue Information Bulletin 26-019, 2026-09-28, under La. R.S. 47:294(B)), which gives a tax of $820.26; $12,835 is PolicyEngine's own inflation computation, which the frozen reference of $820.35 uses.
  - **Source:** https://dam.ldr.la.gov/lawspolicies/RIB%2026-019.pdf ; paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_051 state income tax; decision of 2026-10-06)
  - **Scoring:** The output is excluded from scoring for every model because its reference rests on an amount Louisiana published after the reference freeze, so no score moves.

- **Where:** rows for Claude Fable 5, Claude Fable 5.1, Claude Fable 5.2, Claude Haiku 4.5, Claude Haiku 5.5, Claude Opus 4.7, Claude Opus 4.8, Claude Opus 5, Claude Opus 5.5, Claude Sonnet 4.6, Claude Sonnet 5, Claude Sonnet 5.5, DeepSeek V4 Flash 0731, DeepSeek V4 Pro, DeepSeek V4 Pro 0813, DeepSeek V4.1 Flash, Gemini 3 Flash Preview, Gemini 3.1 Flash Lite Preview, Gemini 3.1 Pro Preview, Gemini 3.5 Flash, Gemini 3.5 Flash Lite, Gemini 3.6 Flash, Gemini 3.7 Flash, Gemini 3.8 Flash, Gemini 4 Argon, GLM-5.2, GLM-5.3, GPT-5.4 mini, GPT-5.4 nano, GPT-5.5, GPT-5.6 Luna, GPT-5.6 Sol, GPT-5.6 Terra, GPT-6 Astra, GPT-6 Luna, GPT-6 Sol, GPT-6.1 Sol, GPT-6.1 Terra, Grok 4.3, Grok 4.5, Grok 4.6, Grok 4.7, Grok Build 0.1, Inkling, Kimi K3, MiniMax M3, Muse Spark 1.3, Muse Wonder, GLM-5.3-Flash (preview), Qwen 3.7 Max and Qwen 3.8 Max
  - **Text:** "$12,835"
  - **Correction:** Each of these rows gives $12,835 as Louisiana's 2026 standard deduction, but Louisiana's first published 2026 amount for single filers is $12,838 (Revenue Information Bulletin 26-019, 2026-09-28, under La. R.S. 47:294(B)), which gives a tax of $820.26; $12,835 is PolicyEngine's own inflation computation, used by the frozen reference of $820.35.
  - **Source:** https://dam.ldr.la.gov/lawspolicies/RIB%2026-019.pdf ; paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_051 state income tax; decision of 2026-10-06)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; no model answered within $1 of $820.26 either. Claude Fable 5.2's $819.15 equals the exclusion record's value under $12,875, the withholding amount Louisiana published before the freeze, which Louisiana said would differ from the amount allowed on 2026 returns; 25 answers come within $1 of its $830.40 under 2025's $12,500, the last return amount Louisiana published before the freeze.

### `scenario_057 snap`

- **Where:** case note; rows for Claude Haiku 5.5, Gemini 3.1 Flash Lite Preview, Gemini 3.6 Flash, GLM-5.2, Kimi K2.6 and Qwen 3.8 Max
  - **Text:** "$232.74/mo for Oct–Dec" (Gemini 3.6 Flash: "$232.74 for Oct–Dec"; Claude Haiku 5.5: "$232.74/mo (Oct–Dec)")
  - **Correction:** PolicyBench holds SNAP's October to December 2026 figures at USDA's FY2026 schedule, the last published before the 2026-07-03 reference freeze, so the two-person maximum allotment is $546 in every month and this reading of the household gives $219 a month all year, or $2,628. The $232.74 comes from the frozen engine's projected $558.24 maximum and an unrounded contribution, which 7 CFR 273.10(e)(2)(ii)(A) does not allow.
  - **Source:** docs/benchmark_card.md (publication conventions) and reference_audit/2026-09-22/root_causes.json (c_snap_hold_fy2026; r26_snap_contribution_rounding); https://www.law.cornell.edu/cfr/text/7/273.10
  - **Scoring:** The output is excluded from scoring for every model because the reference depends on an unstated disability fact, so no score moves; no model answered within $1 of $2,628.

- **Where:** rows for Claude Fable 5.1, Claude Fable 5.2, Claude Opus 5.5, Gemini 4 Argon, GPT-5.6 Sol, GPT-6 Astra, GPT-6 Sol, Grok 4.7 and Kimi K3
  - **Text:** "$558.24" (each row faults the model for using the $546 maximum, or a flat $6,552 a year, in October to December; GPT-6 Astra's row: "It also used a flat $6,552 annual maximum.")
  - **Correction:** Using $546 in every month, $6,552 a year, is right under PolicyBench's convention, which holds SNAP's October to December 2026 figures at USDA's FY2026 schedule, the last published before the 2026-07-03 reference freeze; $558.24 is the frozen engine's projection, not a USDA maximum allotment.
  - **Source:** docs/benchmark_card.md (publication conventions) and reference_audit/2026-09-22/root_causes.json (c_snap_hold_fy2026)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; these rows counted eligible-couple SSI, the alternative reading the exclusion records as open.

### `scenario_064 federal_income_tax_before_refundable_credits`

- **Where:** row for DeepSeek V4 Pro 0813
  - **Text:** "all with a $400,000 phaseout threshold"
  - **Correction:** Only the credits phase out above $400,000 on a joint return (26 U.S.C. 24(b)(1), (h)(3)). The standard deduction has no income phase-out (26 U.S.C. 63(c)), and the overtime deduction phases out above $300,000 of modified AGI on a joint return (26 U.S.C. 225(b)(2)).
  - **Source:** https://www.law.cornell.edu/uscode/text/26/225 ; https://www.law.cornell.edu/uscode/text/26/24 ; https://www.law.cornell.edu/uscode/text/26/63
  - **Scoring:** The reference and the row's class stand: this household's AGI of $114,421 is below every threshold, and the answer is wrong because the model applied pre-TCJA rules, with personal exemptions and a $1,000 child credit phasing out at $110,000.

### `scenario_064 state_income_tax_before_refundable_credits`

- **Where:** case note (reference hypothesis)
  - **Text:** "Wisconsin Schedule WD and DOR Publication 103 cap the net capital loss deduction against ordinary income at $500 ($250 married filing separately)"
  - **Correction:** For taxable years beginning after December 31, 2022, Wis. Stat. 71.05(10)(c)2. lets a net capital loss offset ordinary income up to $3,000 ($1,500 for a married person filing separately); the $500 limit in subd. 1. applies only to earlier years. For 2026 Wisconsin therefore allows the same $3,000 as the federal return, and no add-back is due.
  - **Source:** https://docs.legis.wisconsin.gov/statutes/statutes/71/i/05/10/c ; annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (decision of 2026-10-14 on this cell)
  - **Scoring:** The reference and the rows' classes stand: the developer decision affirms the reference's $3,000 capital-loss deduction, and rows that added back $2,500 remain errors.

### `scenario_077 state_income_tax_before_refundable_credits`

- **Where:** case note
  - **Text:** "that deduction is inflation-indexed to $12,835 for 2026"
  - **Correction:** Louisiana's published 2026 single standard deduction is $12,838 ($12,500 raised by the 2.7% CPI-U change under La. R.S. 47:294), per Revenue Information Bulletin 26-019 of September 28, 2026; $12,835 is the engine's own CPI-U computation, which the frozen reference uses. Under $12,838 the tax is $305.05.
  - **Source:** https://dam.ldr.la.gov/lawspolicies/RIB%2026-019.pdf ; annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (decision of 2026-10-06 on this cell)
  - **Scoring:** No score moves: the output is excluded from scoring for every model because Louisiana published its 2026 amount after the reference froze.

- **Where:** row for Claude Fable 5.2
  - **Text:** "instead of the actual 2026 figure of $12,835"
  - **Correction:** Louisiana's published 2026 single standard deduction is $12,838 (Revenue Information Bulletin 26-019, under La. R.S. 47:294); $12,835 is the engine's CPI-U computation, which the frozen reference uses.
  - **Source:** https://dam.ldr.la.gov/lawspolicies/RIB%2026-019.pdf ; paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_077 state income tax; decision of 2026-10-06)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the answer misses under the published amount too ($303.93 against $305.05). It is within a cent of the $303.94 the exclusion record gives under $12,875, the withholding amount Louisiana published before the freeze, which Louisiana said would differ from the amount allowed on 2026 returns.

- **Where:** row for GPT-6 Astra
  - **Text:** "instead of the actual 2026 amount of $12,835"
  - **Correction:** Louisiana's published 2026 single standard deduction is $12,838 (Revenue Information Bulletin 26-019, under La. R.S. 47:294); $12,835 is the engine's CPI-U computation, which the frozen reference uses.
  - **Source:** https://dam.ldr.la.gov/lawspolicies/RIB%2026-019.pdf ; paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_077 state income tax; decision of 2026-10-06)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the answer misses under the published amount too ($303.93 against $305.05). It is within a cent of the $303.94 the exclusion record gives under $12,875, the withholding amount Louisiana published before the freeze, which Louisiana said would differ from the amount allowed on 2026 returns.

- **Where:** rows for Claude Fable 5.1, Claude Fable 5, Claude Opus 5.5, Claude Opus 5, Claude Opus 4.8, Claude Opus 4.7, Claude Sonnet 5.5, Claude Sonnet 5, Claude Sonnet 4.6, Claude Haiku 5.5, Claude Haiku 4.5, Grok 4.3, Grok 4.5, Grok 4.6, Grok 4.7, GLM-5.3-Flash (preview), Grok Build 0.1, GPT-6 Sol, GPT-6.1 Sol, GPT-6.1 Terra, GPT-6 Luna, GPT-5.6 Sol, GPT-5.6 Terra, GPT-5.6 Luna, GPT-5.5, GPT-5.4 mini, GPT-5.4 nano, Gemini 4 Argon, Gemini 3.1 Pro Preview, Gemini 3.6 Flash, Gemini 3.7 Flash, Gemini 3.5 Flash, Gemini 3.5 Flash Lite, Gemini 3 Flash Preview, Gemini 3.1 Flash Lite Preview, DeepSeek V4 Pro 0813, DeepSeek V4 Pro, DeepSeek V4.1 Flash, DeepSeek V4 Flash 0731, Kimi K3, Kimi K2.6, GLM-5.3, GLM-5.2, MiniMax M3, Inkling, Qwen 3.8 Max, Qwen 3.7 Max, Muse Wonder and Muse Spark 1.3
  - **Text:** "$12,835"
  - **Correction:** Louisiana's published 2026 single standard deduction is $12,838 (Revenue Information Bulletin 26-019, under La. R.S. 47:294); $12,835 is the engine's CPI-U computation, which the frozen reference uses, and the tax under $12,838 is $305.05.
  - **Source:** https://dam.ldr.la.gov/lawspolicies/RIB%2026-019.pdf ; paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_077 state income tax; decision of 2026-10-06)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and no answer in these rows comes within $1 of $305.05 either. Twenty-three of these answers come within $1 of the $315.19 the exclusion record gives under 2025's $12,500, the last return amount Louisiana published before the freeze.

### `scenario_078 state_income_tax_before_refundable_credits`

- **Where:** rows for Claude Haiku 4.5 and Claude Opus 4.8
  - **Text:** "the federal $10,000 SALT cap"
  - **Correction:** For 2026 the federal limit on the state and local tax deduction is $40,400 for this single filer (it phases down by 30% of modified AGI above $505,000, but not below $10,000), under 26 U.S.C. 164(b)(7) as amended by P.L. 119-21; $10,000 was the limit for 2018 to 2024. The household's $26,460 of property tax is under the 2026 limit, so it is deductible in full either way.
  - **Source:** https://www.law.cornell.edu/uscode/text/26/164
  - **Scoring:** The reference and the rows' class stand: the answers are wrong because the models took a standard deduction or cut the property tax deduction to fit a $10,000 cap that does not apply in 2026.

### `scenario_079 snap`

- **Where:** case note
  - **Text:** "which replaces the $26 actual excess ($61 − $35)"
  - **Correction:** The $61 includes $25 a month of over-the-counter costs, which count as a SNAP medical expense only when a licensed practitioner or other qualified health professional approves them (7 CFR 273.9(d)(3)), a fact the household's description does not state; the reference leaves them out, so the actual excess it replaces is $1 ($36 − $35). Arizona's $145 standard medical deduction applies either way.
  - **Source:** https://www.law.cornell.edu/cfr/text/7/273.9
  - **Scoring:** The reference and every row's class stand: the $145 standard medical deduction applies whether or not the over-the-counter costs count, so no answer moves.

- **Where:** row for Gemini 3.8 Flash
  - **Text:** "leaving out OTC costs"
  - **Correction:** Leaving out the over-the-counter costs matches the reference: SNAP counts over-the-counter medication only when a licensed practitioner or other qualified health professional approves it (7 CFR 273.9(d)(3)), which the facts do not state. The model's error was ignoring Arizona's $145 standard medical deduction.
  - **Source:** https://www.law.cornell.edu/cfr/text/7/273.9
  - **Scoring:** The reference and the row's class stand: the answer is wrong because the model ignored Arizona's $145 standard medical deduction and used $840 of SSI and a $536 maximum allotment.

- **Where:** row for Qwen 3.8 Max
  - **Text:** "that SSI cash-out applies only in California"
  - **Correction:** California ended its SSI cash-out on June 1, 2019 (Assembly Bill 1811 of 2018), so SSI recipients there can receive SNAP (CalFresh) as well; the cash-out does not apply in California in 2026 either.
  - **Source:** https://secure.ssa.gov/poms.nsf/lnx/0501801300SF ; https://cdss.ca.gov/inforesources/calfresh/supplemental-security-income
  - **Scoring:** The reference and the row's class stand: the answer of $0 is wrong because SSI receipt makes this Arizona household categorically eligible and its benefit is $198 a month.

### `scenario_086 state_income_tax_before_refundable_credits`

- **Where:** row for Grok Build 0.1
  - **Text:** "the 2024 rate of 5.49%"
  - **Correction:** Georgia's rate for 2024 was 5.39%, not 5.49%: HB 1015 (2024) replaced the 5.49% that earlier law had set, for all taxable years beginning on or after January 1, 2024 (O.C.G.A. 48-7-20(a.1)(1)). The rate for 2026 is 4.99% under HB 463 (2026).
  - **Source:** https://gov.georgia.gov/document/2024-signed-legislation/hb-1015/download
  - **Scoring:** The reference and the row's class stand: the answer is wrong because the model taxed 2026 income at 5.49% instead of 4.99%, with older deduction and exemption amounts.

### `scenario_093 federal_income_tax_before_refundable_credits`

- **Where:** case note
  - **Text:** "their $45,000 of wages stays off the parents' return with no separate return filed"
  - **Correction:** A dependent with $45,000 of wages must file their own federal return; the frozen reference counts only the parents' joint return, and whether this output should also include the dependent's return is the open question for which it is excluded from scoring (counting it gives $11,848.99).
  - **Source:** paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_093 federal income tax; decision of 2026-10-06)
  - **Scoring:** The output is excluded from scoring for every model because the prompt leaves open which returns it covers, so no score moves.

- **Where:** row for Claude Opus 4.7
  - **Text:** "but a permanently disabled child is a qualifying child at any age"
  - **Correction:** The household's facts say only that the 27-year-old is disabled, and even permanent and total disability removes only the qualifying-child age limit (26 U.S.C. 152(c)(3)(B)); a qualifying child of any age must still not have provided over half of their own support (26 U.S.C. 152(c)(1)(D)). The reference allows the $500 credit because the household lists the 27-year-old as a dependent, not because of an age rule.
  - **Source:** https://www.law.cornell.edu/uscode/text/26/152 (household facts: paper/snapshot/20260501/us_scenarios.csv, scenario_093)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the answer is also off because the model omitted the $500 credit for other dependents and used a $31,500 standard deduction and a $24,150 bracket edge instead of $32,200 and $24,800.

- **Where:** row for Claude Sonnet 5.5
  - **Text:** "A permanently disabled child is a qualifying child regardless of age or income"
  - **Correction:** The household's facts say only that the 27-year-old is disabled, and even permanent and total disability removes only the qualifying-child age limit (26 U.S.C. 152(c)(3)(B)); a qualifying child must still not have provided over half of their own support (26 U.S.C. 152(c)(1)(D)), though unlike a qualifying relative they face no gross-income test. The reference allows the $500 credit because the household lists the 27-year-old as a dependent, not because of an age rule.
  - **Source:** https://www.law.cornell.edu/uscode/text/26/152 (household facts: paper/snapshot/20260501/us_scenarios.csv, scenario_093) ; reference_audit/2026-11-11-car-loan-interest/README.md (auto loan interest)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the answer is also off because the model omitted the $500 credit for other dependents. The model also deducted the $1,000 of auto loan interest: the prompt does not say whether that loan qualifies for the deduction, and the reference treats it as not qualifying; allowing it gives $8,508.99, which the answer ($9,009) does not match either.

- **Where:** row for DeepSeek V4 Pro
  - **Text:** "who is claimed on the joint return and does not file one"
  - **Correction:** A dependent with $45,000 of wages must file their own federal return, as the decision on this case records; the frozen reference counts only the parents' joint return, and whether the output should include the dependent's return is the open question for which it is excluded from scoring.
  - **Source:** paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_093 federal income tax; decision of 2026-10-06)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the answer is also off because the model subtracted ESI premiums from wages and omitted the $500 credit for other dependents.

- **Where:** row for GLM-5.3
  - **Text:** "A permanently disabled child is a qualifying child at any age"
  - **Correction:** The household's facts say only that the 27-year-old is disabled, and even permanent and total disability removes only the qualifying-child age limit (26 U.S.C. 152(c)(3)(B)); a qualifying child of any age must still not have provided over half of their own support (26 U.S.C. 152(c)(1)(D)). The reference allows the $500 credit because the household lists the 27-year-old as a dependent, not because of an age rule.
  - **Source:** https://www.law.cornell.edu/uscode/text/26/152 (household facts: paper/snapshot/20260501/us_scenarios.csv, scenario_093)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the answer is also off because the model omitted the $500 credit for other dependents and deducted $3,000 of student-loan interest instead of the $2,500 cap.

- **Where:** rows for GPT-6 Sol and Muse Wonder
  - **Text:** "a separate return the claimed dependent does not file"
  - **Correction:** A dependent with $45,000 of wages must file their own federal return, as the decision on this case records; the frozen reference counts only the parents' joint return, and whether the output should include the dependent's return is the open question for which it is excluded from scoring.
  - **Source:** paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_093 federal income tax; decision of 2026-10-06)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; both answers also omit the $500 credit for other dependents, so neither matches the $11,848.99 that counting the dependent's return gives.

### `scenario_093 state_income_tax_before_refundable_credits`

- **Where:** case note
  - **Text:** "has $0 Missouri AGI, so the dependent's $45,000 of wages is not taxed"
  - **Correction:** The dependent's $45,000 of wages is taxable on the dependent's own federal and Missouri returns, which the dependent must file; the reference covers only the couple's return. PolicyBench's decision for this output records that the prompt does not say whether the output covers every return the household's members file, and excludes the output from scoring.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_093 state_income_tax_before_refundable_credits, decided 2026-10-06)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and no model's answer equals the couple-only $3,388.25 or the $4,528.08 that adds the dependent's own return.

- **Where:** row for Claude Fable 5.2
  - **Text:** "Only the head and spouse have Missouri AGI"
  - **Correction:** The dependent also has Missouri AGI: the $45,000 of wages is taxable on the dependent's own federal and Missouri returns, which the dependent must file. The reference covers only the couple's return, and PolicyBench excluded this output because the prompt does not say whether the output covers every return the household's members file.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_093 state_income_tax_before_refundable_credits, decided 2026-10-06)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the answer ($5,309.95) is wrong under either reading because the model put the dependent's wages on the couple's return.

- **Where:** row for Claude Opus 5
  - **Text:** "with $0 Missouri AGI and owes nothing"
  - **Correction:** The dependent's $45,000 of wages is taxable on the dependent's own federal and Missouri returns, which the dependent must file; the reference covers only the couple's return, and PolicyBench excluded this output because the prompt does not say whether the output covers every return the household's members file.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_093 state_income_tax_before_refundable_credits, decided 2026-10-06)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the answer ($4,180) matches neither the couple-only $3,388.25 nor the $4,528.08 that adds the dependent's own return.

- **Where:** rows for Claude Fable 5.1, Claude Opus 5.5, DeepSeek V4 Flash 0731, DeepSeek V4 Pro 0813, Gemini 3.1 Pro Preview, Gemini 3.5 Flash Lite, Gemini 3.8 Flash, Gemini 4 Argon, GPT-5.5, GPT-5.6 Luna, Kimi K3, GLM-5.3-Flash (preview) and Qwen 3.8 Max
  - **Text:** "MO AGI is $0"
  - **Correction:** The dependent's Missouri AGI is not $0: the $45,000 of wages is taxable on the dependent's own federal and Missouri returns, which the dependent must file. It stays off the couple's return, which is all the reference covers; PolicyBench excluded this output because the prompt does not say whether the output covers every return the household's members file.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_093 state_income_tax_before_refundable_credits, decided 2026-10-06)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and no listed answer equals the couple-only $3,388.25 or the $4,528.08 that adds the dependent's own return.

- **Where:** rows for DeepSeek V4 Pro, DeepSeek V4.1 Flash, Gemini 3 Flash Preview, Gemini 3.5 Flash, Gemini 3.7 Flash, GLM-5.2, GLM-5.3, GPT-6 Sol, Grok 4.5, Grok 4.6, Grok 4.7, Grok Build 0.1, Inkling and Muse Wonder
  - **Text:** "$0 MO AGI"
  - **Correction:** The dependent's Missouri AGI is not $0: the $45,000 of wages is taxable on the dependent's own federal and Missouri returns, which the dependent must file, so a separate tax on the dependent is a defensible reading. The reference covers only the couple's return, and PolicyBench excluded this output because the prompt does not say whether the output covers every return the household's members file.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_093 state_income_tax_before_refundable_credits, decided 2026-10-06)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and no listed answer equals the couple-only $3,388.25 or the $4,528.08 that adds the dependent's own return.

### `scenario_100 snap`

- **Where:** case note
  - **Text:** "The few models that did count TANF still missed the shelter deduction"
  - **Correction:** On the reading the reference takes, in which the head is not a SNAP-disabled member, the household has no excess shelter deduction: an energy assistance payment confers the standard utility allowance only on a household with an elderly or disabled member (7 U.S.C. 2014(e)(6)(C)(iv)(I), as amended by P.L. 119-21), and no rent or utility costs are listed. PolicyBench's decision for this output records the reference's $453.64 deduction as an engine defect and gives $6,924 on the stated facts.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_100 snap); https://www.law.cornell.edu/uscode/text/7/2014
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and no model's answer equals $6,924 or the other reading's $8,844.

- **Where:** case note
  - **Text:** "Most models left out the TANF income and the shelter deduction"
  - **Correction:** Leaving out the shelter deduction is not an error on the reading the reference takes: with no elderly or disabled member, the household's energy assistance gives it no standard utility allowance (7 U.S.C. 2014(e)(6)(C)(iv)(I), as amended by P.L. 119-21), and no rent or utility costs are listed. PolicyBench's decision for this output records the reference's $453.64 deduction as an engine defect.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_100 snap); https://www.law.cornell.edu/uscode/text/7/2014
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and leaving TANF income out is still an error on either reading.

- **Where:** row for Claude Fable 5.1
  - **Text:** "used a flat $785 for all 12 months"
  - **Correction:** Using $785 for all 12 months is not an error here: PolicyBench holds October through December 2026 at USDA's fiscal year 2026 schedule, because USDA published its fiscal year 2027 amounts on 2026-08-21, after the 2026-07-03 reference freeze.
  - **Source:** convention c_snap_hold_fy2026 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json; annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_100 snap)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the answer ($9,108) is wrong because the model left out the TANF income.

- **Where:** row for Claude Fable 5.2
  - **Text:** "It also ignored the higher allotment for October–December."
  - **Correction:** Using the same maximum allotment for all 12 months is not an error here: PolicyBench holds October through December 2026 at USDA's fiscal year 2026 schedule ($785 for three people), because USDA published its fiscal year 2027 amounts on 2026-08-21, after the 2026-07-03 reference freeze. The frozen reference for this excluded output still carries the engine's projected October-December increase because it was not regenerated.
  - **Source:** convention c_snap_hold_fy2026 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json; annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_100 snap)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the answer ($6,933.66) is not the $6,924 the decision gives on the stated facts, because the model did not round the monthly benefit to whole dollars.

- **Where:** row for Claude Haiku 4.5
  - **Text:** "and shelter deductions"
  - **Correction:** On the reading the reference takes, in which the head is not a SNAP-disabled member, the household has no excess shelter deduction: an energy assistance payment confers the standard utility allowance only on a household with an elderly or disabled member (7 U.S.C. 2014(e)(6)(C)(iv)(I), as amended by P.L. 119-21), and no rent or utility costs are listed. PolicyBench's decision for this output records the reference's deduction as an engine defect.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_100 snap); https://www.law.cornell.edu/uscode/text/7/2014
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the answer ($1,908) equals neither $6,924 nor the other reading's $8,844.

- **Where:** row for GLM-5.3-Flash (preview)
  - **Text:** "and the shelter deduction"
  - **Correction:** On the reading the reference takes, in which the head is not a SNAP-disabled member, the household has no excess shelter deduction: an energy assistance payment confers the standard utility allowance only on a household with an elderly or disabled member (7 U.S.C. 2014(e)(6)(C)(iv)(I), as amended by P.L. 119-21), and no rent or utility costs are listed. PolicyBench's decision for this output records the reference's deduction as an engine defect.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_100 snap); https://www.law.cornell.edu/uscode/text/7/2014
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the answer ($9,409) equals neither $6,924 nor the other reading's $8,844.

- **Where:** row for GPT-5.6 Luna
  - **Text:** "It also ignored the higher October–December allotment."
  - **Correction:** Using the same maximum allotment for all 12 months is not an error here: PolicyBench holds October through December 2026 at USDA's fiscal year 2026 schedule ($785 for three people), because USDA published its fiscal year 2027 amounts on 2026-08-21, after the 2026-07-03 reference freeze.
  - **Source:** convention c_snap_hold_fy2026 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json; annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_100 snap)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the answer ($9,420) is wrong because it pays the full maximum although TANF and earnings leave positive net income.

- **Where:** row for GPT-6 Luna
  - **Text:** "and $733.60 for October–December"
  - **Correction:** PolicyBench holds October through December 2026 at USDA's fiscal year 2026 schedule, the same $785 maximum as January through September, because USDA published its fiscal year 2027 amounts on 2026-08-21, after the 2026-07-03 reference freeze; a single monthly amount for all 12 months is not an error.
  - **Source:** convention c_snap_hold_fy2026 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json; annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_100 snap)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the answer ($8,531) is wrong because the model left out the TANF income.

- **Where:** row for Muse Spark 1.3
  - **Text:** "and the higher allotment for October–December"
  - **Correction:** PolicyBench holds October through December 2026 at USDA's fiscal year 2026 schedule, the same $785 maximum as January through September, because USDA published its fiscal year 2027 amounts on 2026-08-21, after the 2026-07-03 reference freeze.
  - **Source:** convention c_snap_hold_fy2026 in paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_outputs.csv.meta.json; annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_100 snap)
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the answer ($8,530.80) is wrong because the model left out the TANF income and used a $768 maximum.

- **Where:** rows for Claude Fable 5, Claude Fable 5.1, Claude Fable 5.2, Claude Opus 4.7, Claude Opus 4.8, Claude Opus 5, Claude Opus 5.5, Claude Sonnet 4.6, DeepSeek V4 Flash 0731, DeepSeek V4 Pro, DeepSeek V4 Pro 0813, DeepSeek V4.1 Flash, Gemini 3 Flash Preview, Gemini 3.1 Flash Lite Preview, Gemini 3.1 Pro Preview, Gemini 3.5 Flash, Gemini 3.6 Flash, Gemini 3.8 Flash, GLM-5.3, GPT-5.6 Terra, GPT-6 Luna, GPT-6 Sol, GPT-6.1 Sol, GPT-6.1 Terra, Grok 4.5, Grok 4.7, Inkling, MiniMax M3, Muse Spark 1.3 and Muse Wonder
  - **Text:** "$453.64"
  - **Correction:** On the reading the reference takes, in which the head is not a SNAP-disabled member, there is no $453.64 excess shelter deduction: an energy assistance payment confers the standard utility allowance only on a household with an elderly or disabled member (7 U.S.C. 2014(e)(6)(C)(iv)(I), as amended by P.L. 119-21), and no rent or utility costs are listed. PolicyBench's decision for this output records the deduction as an engine defect and gives $6,924 on the stated facts.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_100 snap); https://www.law.cornell.edu/uscode/text/7/2014
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and no listed answer equals $6,924 or the other reading's $8,844.

### `scenario_100 state_refundable_credits`

- **Where:** case note (reference hypothesis)
  - **Text:** "Montana's refundable child tax credit under HB 268 (2023) pays $1,200 for each child under 6"
  - **Correction:** Montana has no child tax credit: HB 268 (2023) never became law, because the House Appropriations Committee tabled it on February 23, 2023, and no later act created one. For 2026 the household's only Montana refundable credit is the earned income tax credit, 20% of the federal credit (Mont. Code Ann. 15-30-2318, as amended by HB 337 of 2025).
  - **Source:** https://archive.legmt.gov/bills/2023/Minutes/House/230223APH_Hm1.pdf ; annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (decision of 2026-11-11 on this cell)
  - **Scoring:** The reference and the rows' classes stand: the $164.46 reference is the Montana earned income credit alone, which the developer decision affirms.

### `scenario_112 snap`

- **Where:** case note
  - **Text:** "the one/two-person minimum allotment of $23.84/mo ($287.68 a year)"
  - **Correction:** Under 7 U.S.C. 2017(a) the minimum allotment for one- and two-person households is 8% of the one-person maximum rounded to the nearest whole dollar: 8% of the fiscal year 2026 maximum of $298 is $23.84, so the minimum is $24 a month. The frozen reference uses the engine's unrounded $23.84 for January to September and 8% of the engine's projected $304.68 maximum ($24.37) for October to December, which sum to $287.68; under PolicyBench's conventions the minimum is $24 in every month, $288 a year.
  - **Source:** https://www.law.cornell.edu/uscode/text/7/2017 ; reference_audit/2026-09-22/root_causes.json (c_snap_hold_fy2026; r28_snap_min_allotment_rounding)
  - **Scoring:** No score moves: the output is excluded from scoring for every model because its reference depends on unlisted work hours.

- **Where:** rows for Claude Fable 5.2, Claude Fable 5.1, Claude Fable 5, Claude Opus 5.5, Claude Opus 5, Claude Opus 4.8, Claude Opus 4.7, Claude Sonnet 5.5, Claude Sonnet 5, Claude Sonnet 4.6, Claude Haiku 5.5, Claude Haiku 4.5, Grok 4.3, Grok 4.5, Grok 4.6, Grok 4.7, GLM-5.3-Flash (preview), Grok Build 0.1, GPT-6 Astra, GPT-6 Sol, GPT-6.1 Sol, GPT-6.1 Terra, GPT-6 Luna, GPT-5.6 Sol, GPT-5.6 Terra, GPT-5.6 Luna, GPT-5.5, GPT-5.4 mini, GPT-5.4 nano, Gemini 4 Argon, Gemini 3.1 Pro Preview, Gemini 3.6 Flash, Gemini 3.8 Flash, Gemini 3.7 Flash, Gemini 3.5 Flash, Gemini 3.5 Flash Lite, Gemini 3 Flash Preview, Gemini 3.1 Flash Lite Preview, DeepSeek V4 Pro 0813, DeepSeek V4 Pro, DeepSeek V4.1 Flash, DeepSeek V4 Flash 0731, Kimi K3, Kimi K2.6, GLM-5.3, GLM-5.2, MiniMax M3, Inkling, Qwen 3.8 Max, Qwen 3.7 Max, Muse Wonder and Muse Spark 1.3
  - **Text:** "$23.84"
  - **Correction:** The fiscal year 2026 SNAP minimum allotment for a one-person household is $24 a month: 7 U.S.C. 2017(a) sets it at 8% of the one-person maximum ($298), rounded to the nearest whole dollar; $23.84 is the engine's unrounded figure.
  - **Source:** https://www.law.cornell.edu/uscode/text/7/2017
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and no answer in the cell is near twelve months of a $24 minimum.

### `scenario_118 snap`

- **Where:** case note
  - **Text:** "the uncapped elderly/disabled shelter costs are not just mortgage interest plus property tax ($598.75/month). They also include New York's standard utility allowance (SUA), which brings total shelter costs to about $1,013/month."
  - **Correction:** The frozen reference does not count the listed mortgage interest: its shelter costs of about $1,013 a month are the $136.17 of property tax plus New York's utility allowance. Counting the mortgage interest too, which SNAP does when the mortgaged home is the household's residence (7 CFR 273.9(d)(6)(ii)(A)), a fact the prompt does not state, is the alternative reading recorded for this case, and it gives the $298 maximum, $3,576 a year.
  - **Source:** paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_118 SNAP; decision of 2026-09-22)
  - **Scoring:** The output is excluded from scoring for every model because the reference depends on whether the mortgaged home is the household's residence, so no score moves.

- **Where:** case note
  - **Text:** "a $298 − $58.20 = $239.80 monthly allotment. Nine months at $239.80 plus three months at $248.58"
  - **Correction:** SNAP rounds 30% of net income up to the next dollar, or rounds the allotment down to the dollar (7 CFR 273.10(e)(2)(ii)(A)), so these figures give $239 a month, not $239.80; and PolicyBench holds October to December 2026 at USDA's FY2026 figures, the last published before the 2026-07-03 reference freeze, so those months have no higher $248.58 allotment. The $2,903.94 is the frozen engine's value, kept for this output because the output is excluded.
  - **Source:** https://www.law.cornell.edu/cfr/text/7/273.10 ; docs/benchmark_card.md (publication conventions) and reference_audit/2026-09-22/root_causes.json (c_snap_hold_fy2026)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves.

- **Where:** row for Claude Fable 5.1
  - **Text:** "Adding the SUA raises shelter costs to about $1,013"
  - **Correction:** Adding New York's utility allowance to the $599 of mortgage interest and property tax gives about $1,476, not $1,013; the frozen reference's $1,013 is the property tax plus the utility allowance without the mortgage interest, and counting the mortgage interest too is the alternative reading recorded for this case (7 CFR 273.9(d)(6)(ii)(A)), which gives the $298 maximum.
  - **Source:** paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_118 SNAP; decision of 2026-09-22)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the answer ($1,384) is wrong under either reading because the model left out the utility allowance.

- **Where:** row for Claude Fable 5.2
  - **Text:** "dropped the $462.58/month of mortgage interest and the NY SUA from shelter costs"
  - **Correction:** The frozen reference does not count the mortgage interest as a shelter cost, because the prompt does not say the mortgaged home is the household's residence (7 CFR 273.9(d)(6)(ii)(A)); its shelter costs of about $1,013 are the property tax plus New York's utility allowance. Counting the mortgage interest too is the alternative reading recorded for this case, which gives the $298 maximum.
  - **Source:** paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_118 SNAP; decision of 2026-09-22)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the answer ($678) is wrong under either reading because the model allowed no shelter deduction.

- **Where:** row for Claude Haiku 5.5
  - **Text:** "an uncapped excess shelter deduction (mortgage interest, property tax and NY SUA)"
  - **Correction:** The frozen reference's shelter deduction counts the property tax and New York's utility allowance but not the mortgage interest, because the prompt does not say the mortgaged home is the household's residence (7 CFR 273.9(d)(6)(ii)(A)); counting the mortgage interest too is the alternative reading recorded for this case, which gives the $298 maximum.
  - **Source:** paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_118 SNAP; decision of 2026-09-22)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the answer ($0) is wrong under either reading.

- **Where:** row for Claude Opus 5.5
  - **Text:** "With the SUA, shelter costs are about $1,013/month"
  - **Correction:** Adding New York's utility allowance to the model's mortgage interest and property tax gives about $1,476 a month, not $1,013; the frozen reference's $1,013 is the property tax plus the utility allowance without the mortgage interest, and counting the mortgage interest too is the alternative reading recorded for this case (7 CFR 273.9(d)(6)(ii)(A)), which gives the $298 maximum.
  - **Source:** paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_118 SNAP; decision of 2026-09-22)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the answer ($1,380) is wrong under either reading because the model left out the utility allowance.

- **Where:** row for DeepSeek V4 Flash 0731
  - **Text:** "the uncapped excess shelter deduction for mortgage interest, property tax and the SUA"
  - **Correction:** The frozen reference's shelter deduction counts the property tax and New York's utility allowance but not the mortgage interest, because the prompt does not say the mortgaged home is the household's residence (7 CFR 273.9(d)(6)(ii)(A)); counting the mortgage interest too is the alternative reading recorded for this case, which gives the $298 maximum.
  - **Source:** paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_118 SNAP; decision of 2026-09-22)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the answer ($3,380) is wrong under either reading.

- **Where:** row for GPT-6 Astra
  - **Text:** "SNAP counts them as shelter costs along with the NY SUA"
  - **Correction:** SNAP counts mortgage interest as a shelter cost only for the home the household occupies (7 CFR 273.9(d)(6)(ii)(A)), which the prompt does not state; the frozen reference counts the property tax and New York's utility allowance but not the mortgage interest, and counting it too is the alternative reading recorded for this case, which gives the $298 maximum.
  - **Source:** paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_118 SNAP; decision of 2026-09-22)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the answer ($678) is wrong under either reading because the model allowed no shelter deduction.

- **Where:** row for Gemini 3.7 Flash
  - **Text:** "Mortgage interest ($462.58) plus property tax ($136.17) plus the NY SUA come to about $1,013 of shelter costs"
  - **Correction:** Mortgage interest plus property tax is $598.75, so with New York's utility allowance the total is about $1,476, not $1,013. The frozen reference's $1,013 is the property tax plus the utility allowance without the mortgage interest; counting the mortgage interest too is the alternative reading recorded for this case (7 CFR 273.9(d)(6)(ii)(A)), which gives the $298 maximum.
  - **Source:** paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_118 SNAP; decision of 2026-09-22)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the answer ($69 a month) matches neither reading.

- **Where:** row for Kimi K3
  - **Text:** "Mortgage interest, property tax and the NY SUA give a $610.62 uncapped deduction"
  - **Correction:** The frozen reference's $610.62 deduction comes from the property tax and New York's utility allowance without the mortgage interest; counting the mortgage interest too, which SNAP does only for the home the household occupies (7 CFR 273.9(d)(6)(ii)(A)), a fact the prompt does not state, is the alternative reading recorded for this case, which gives the $298 maximum.
  - **Source:** paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_118 SNAP; decision of 2026-09-22)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the answer ($360) is wrong under either reading because the model allowed no shelter deduction.

- **Where:** row for Muse Spark 1.3
  - **Text:** "mortgage interest, property tax and the NY SUA are uncapped shelter costs"
  - **Correction:** The frozen reference counts the property tax and New York's utility allowance but not the mortgage interest, because SNAP counts mortgage interest only for the home the household occupies (7 CFR 273.9(d)(6)(ii)(A)) and the prompt does not say which home it is; counting it too is the alternative reading recorded for this case, which gives the $298 maximum.
  - **Source:** paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json (scenario_118 SNAP; decision of 2026-09-22)
  - **Scoring:** The output is excluded from scoring for every model, so no score moves; the answer ($347) is wrong under either reading because the model allowed no excess shelter deduction.

- **Where:** rows for Claude Fable 5, Claude Fable 5.1, Claude Fable 5.2, Claude Haiku 4.5, Claude Haiku 5.5, Claude Opus 4.7, Claude Opus 4.8, Claude Opus 5, Claude Opus 5.5, Claude Sonnet 4.6, Claude Sonnet 5, Claude Sonnet 5.5, DeepSeek V4 Flash 0731, DeepSeek V4 Pro, DeepSeek V4 Pro 0813, DeepSeek V4.1 Flash, Gemini 3 Flash Preview, Gemini 3.1 Flash Lite Preview, Gemini 3.1 Pro Preview, Gemini 3.5 Flash, Gemini 3.5 Flash Lite, Gemini 3.6 Flash, Gemini 3.7 Flash, Gemini 3.8 Flash, Gemini 4 Argon, GLM-5.2, GLM-5.3, GPT-5.4 mini, GPT-5.4 nano, GPT-5.5, GPT-5.6 Luna, GPT-5.6 Sol, GPT-5.6 Terra, GPT-6 Astra, GPT-6 Luna, GPT-6 Sol, GPT-6.1 Sol, GPT-6.1 Terra, Grok 4.3, Grok 4.5, Grok 4.6, Grok 4.7, Grok Build 0.1, Inkling, Kimi K2.6, Kimi K3, MiniMax M3, Muse Spark 1.3, Muse Wonder, GLM-5.3-Flash (preview), Qwen 3.7 Max and Qwen 3.8 Max
  - **Text:** "$239.80"
  - **Correction:** Each of these rows gives $239.80 a month as the benefit, but SNAP rounds 30% of net income up to the next dollar, or rounds the allotment down to the dollar (7 CFR 273.10(e)(2)(ii)(A)), so the reference's own figures ($194 of net income, the $298 maximum) give $239 a month; $239.80 is the frozen engine's unrounded figure.
  - **Source:** https://www.law.cornell.edu/cfr/text/7/273.10
  - **Scoring:** The output is excluded from scoring for every model, so no score moves.

### `scenario_120 federal_income_tax_before_refundable_credits`

- **Where:** case note
  - **Text:** "taxed the state refund"
  - **Correction:** Counting the $1,750 state tax refund as income is not by itself an error. Under 26 U.S.C. 111(a) a refund is income to the extent the earlier deduction of that tax reduced federal tax, and the prompt does not say whether it did, so PolicyBench treats this as information the prompt leaves out.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_117 federal_income_tax_before_refundable_credits, decided 2026-09-29); reference_audit/2026-09-28/README.md; https://www.law.cornell.edu/uscode/text/26/111
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and no answer that counted the refund equals any value the record gives with the refund counted ($40,423.18, $40,445.46 or $43,629.21, with or without the $163.40 NIIT).

- **Where:** row for Claude Opus 4.8
  - **Text:** "put the $1,750 state refund into AGI"
  - **Correction:** Putting the $1,750 state tax refund into AGI is not by itself an error. Under 26 U.S.C. 111(a) a refund is income to the extent the earlier deduction of that tax reduced federal tax, and the prompt does not say whether it did, so PolicyBench treats this as information the prompt leaves out.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_117 federal_income_tax_before_refundable_credits, decided 2026-09-29); reference_audit/2026-09-28/README.md; https://www.law.cornell.edu/uscode/text/26/111
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the answer ($41,051) is still wrong because the model capped SALT at $10,000 and skipped the charitable floor.

- **Where:** row for Claude Sonnet 5.5
  - **Text:** "included the $1,750 state refund"
  - **Correction:** Including the $1,750 state tax refund in AGI is not by itself an error. Under 26 U.S.C. 111(a) a refund is income to the extent the earlier deduction of that tax reduced federal tax, and the prompt does not say whether it did, so PolicyBench treats this as information the prompt leaves out.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_117 federal_income_tax_before_refundable_credits, decided 2026-09-29); reference_audit/2026-09-28/README.md; https://www.law.cornell.edu/uscode/text/26/111
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and the answer ($40,584) is still wrong because the model did not subtract the $617 traditional 401(k) deferral.

- **Where:** rows for Claude Fable 5.1 and Claude Opus 5.5
  - **Text:** "put the $1,750 state tax refund into AGI"
  - **Correction:** Putting the $1,750 state tax refund into AGI is not by itself an error. Under 26 U.S.C. 111(a) a refund is income to the extent the earlier deduction of that tax reduced federal tax, and the prompt does not say whether it did, so PolicyBench treats this as information the prompt leaves out.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_117 federal_income_tax_before_refundable_credits, decided 2026-09-29); reference_audit/2026-09-28/README.md; https://www.law.cornell.edu/uscode/text/26/111
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and neither answer ($40,385, $40,406) equals a value the record gives with the refund counted ($40,423.18, $40,445.46 or $43,629.21, with or without the $163.40 NIIT).

- **Where:** rows for Claude Fable 5.2, Claude Opus 4.7, DeepSeek V4 Flash 0731, DeepSeek V4.1 Flash, GPT-5.6 Sol, GPT-6 Luna, GPT-6 Sol and GLM-5.3-Flash (preview)
  - **Text:** "taxed the $1,750 state refund"
  - **Correction:** Counting the $1,750 state tax refund as income is not by itself an error. Under 26 U.S.C. 111(a) a refund is income to the extent the earlier deduction of that tax reduced federal tax, and the prompt does not say whether it did, so PolicyBench treats this as information the prompt leaves out.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_117 federal_income_tax_before_refundable_credits, decided 2026-09-29); reference_audit/2026-09-28/README.md; https://www.law.cornell.edu/uscode/text/26/111
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and none of these answers equals a value the record gives with the refund counted ($40,423.18, $40,445.46 or $43,629.21, with or without the $163.40 NIIT); each stays wrong for the other errors its row names.

- **Where:** rows for GLM-5.2 and Inkling
  - **Text:** "taxed the $1,750 refund"
  - **Correction:** Counting the $1,750 state tax refund as income is not by itself an error. Under 26 U.S.C. 111(a) a refund is income to the extent the earlier deduction of that tax reduced federal tax, and the prompt does not say whether it did, so PolicyBench treats this as information the prompt leaves out.
  - **Source:** annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json (scenario_117 federal_income_tax_before_refundable_credits, decided 2026-09-29); reference_audit/2026-09-28/README.md; https://www.law.cornell.edu/uscode/text/26/111
  - **Scoring:** No score moves: the output is excluded from scoring for every model, and neither answer ($44,077.10, $39,378) equals a value the record gives with the refund counted; both stay wrong for the other errors their rows name.

### `scenario_123 federal_income_tax_before_refundable_credits`

- **Where:** rows for Claude Fable 5.2, Claude Sonnet 5.5, GPT-6 Sol, Kimi K3, Muse Wonder and GLM-5.3-Flash (preview)
  - **Text:** "who is not flagged as paid hourly"
  - **Correction:** Being paid hourly is not the test: the deduction covers overtime pay required by section 7 of the Fair Labor Standards Act above the regular rate, which salaried non-exempt workers earn too (26 U.S.C. 225(c)(1)). The head gets no deduction because no overtime premium is listed and the stated wages equal straight-time pay for the hours worked.
  - **Source:** https://www.law.cornell.edu/uscode/text/26/225
  - **Scoring:** No score moves: this output is excluded from scoring for every model because the prompt leaves the return's scope open, and each model's overtime deduction is still unsupported because no overtime premium is listed.
