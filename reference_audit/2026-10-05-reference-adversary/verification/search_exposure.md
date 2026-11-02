# Search results from blocked sources

Written by `scripts/search_exposure.py`, which runs the current `claude_transcript_audit` over every transcript. WebSearch has no deny rule, so its results reach the judge; the audit now rejects an output whose search results list a URL on a blocked domain (policybench.org, www.policybench.org, policyengine.org, www.policyengine.org, github.com, raw.githubusercontent.com) or name PolicyEngine or PolicyBench.

| Run | Transcripts | Searches | With blocked_domains | Flagged transcripts | Flagged cases | Exposed searches |
|---|---:|---:|---:|---:|---:|---:|
| `runs/claude` | 104 | 517 | 0 | 13 | 10 | 28 |
| `runs/claude-rejudge` | 20 | 175 | 160 | 0 | 0 | 0 |

Exposed searches in `runs/claude` by blocked source (a search can expose more than one):

| Source | Exposed searches |
|---|---:|
| github.com/PolicyEngine | 12 |
| github.com/TheAxiomFoundation | 15 |
| github.com/capable78638974979473297813001-pixel | 1 |
| text names policyengine | 12 |
| www.policyengine.org | 1 |

## Flagged transcripts in `runs/claude`

| Case | Stage | Query | Exposed |
|---|---|---|---|
| us__scenario_013__snap | stage1 | "NA Expanded Categorical Eligibility Standard (200%" FPL | https://github.com/TheAxiomFoundation/rulespec-us/issues/1460 |
| us__scenario_013__snap | stage1 | Arizona Nutrition Assistance expanded categorical eligibility 200% "March 1, 2026" OR "March 2026" | https://github.com/TheAxiomFoundation/rulespec-us/issues/1460 |
| us__scenario_013__snap | stage1 | "185% of Federal Poverty Level (Expanded Categorical Eligibility)" Arizona CNAP archived | https://github.com/TheAxiomFoundation/rulespec-us/issues/1460 |
| us__scenario_013__snap | stage1 | "Expanded categorically eligible" "200% of the current" FPL AZTECS budgetary unit | https://github.com/TheAxiomFoundation/rulespec-us/issues/1460 |
| us__scenario_013__snap | stage2 | Arizona SNAP expanded categorical eligibility 200% federal poverty level March 2026 | https://github.com/TheAxiomFoundation/rulespec-us/issues/1460 |
| us__scenario_013__snap | stage2 | dbmefaapolicy.azdes.gov expanded categorical eligibility 200% change log effective March 1, 2026 | https://github.com/TheAxiomFoundation/rulespec-us/issues/1460 |
| us__scenario_014__state_income_tax_before_refundable_credits | stage1 | wvlegislature.gov SB 392 2026 enrolled personal income tax rates 11-21-4 | https://www.policyengine.org/us/wv-sb392-tax-cut, https://www.policyengine.org/us/bill-tracker/WV/wv-sb392 |
| us__scenario_023__state_refundable_credits | stage1 | FTB 3514 instructions "California AGI" line 16 "Is line" earned income look up table smaller amount CalEITC worksheet | https://github.com/PolicyEngine/policyengine-us/issues/9816, https://github.com/PolicyEngine/policyengine-taxsim/issues/1307, text names policyengine |
| us__scenario_023__state_refundable_credits | stage1 | CalEITC worksheet "Enter your California AGI" "Is line 4 less than" | https://github.com/PolicyEngine/policyengine-taxsim/issues/1307, https://github.com/PolicyEngine/policyengine-us/issues/9816, text names policyengine |
| us__scenario_023__state_refundable_credits | stage1 | "2025" CalEITC table no qualifying children "22,501" "22,550" | https://github.com/PolicyEngine/policyengine-taxsim/issues/1328, https://github.com/PolicyEngine/policyengine-taxsim/issues/1307, text names policyengine |
| us__scenario_023__state_refundable_credits | stage1 | CalEITC no qualifying children phaseout percentage recalculated 2022 "0.92%" OR "1.08%" OR "1.07" credit percentage 5.43% | https://github.com/PolicyEngine/policyengine-taxsim/issues/1328, text names policyengine |
| us__scenario_023__state_refundable_credits | stage1 | 2025 California Earned Income Tax Credit Booklet worksheet "line 3" "less than $4,661" | https://github.com/PolicyEngine/policyengine-taxsim/issues/1307, text names policyengine |
| us__scenario_023__state_refundable_credits | stage2 | 2025 CalEITC table no qualifying children 22,501 22,550 credit FTB 3514 | https://github.com/PolicyEngine/policyengine-taxsim/issues/1307, https://github.com/PolicyEngine/policyengine-taxsim/issues/1328, text names policyengine |
| us__scenario_030__snap | stage1 | fns.usda.gov SNAP FY2026 COLA memo PDF "minimum allotment" 48 states standard deduction 209 | https://github.com/TheAxiomFoundation/rulespec-us/issues/1394 |
| us__scenario_043__state_refundable_credits | stage1 | Colorado TABOR state sales tax refund tax year 2025 amounts by adjusted gross income single filers | https://github.com/PolicyEngine/policyengine-taxsim/issues/1274, text names policyengine |
| us__scenario_043__state_refundable_credits | stage2 | Colorado 2025 tax year state sales tax refund amounts single filer $19 AGI $52,000 | https://github.com/PolicyEngine/policyengine-taxsim/issues/1274, text names policyengine |
| us__scenario_045__state_refundable_credits | stage1 | MI-1040CR total household resources "health insurance premiums" deduct line instructions 2025 | https://github.com/PolicyEngine/policyengine-us/pull/9790, text names policyengine |
| us__scenario_066__state_refundable_credits | stage1 | Virginia refundable earned income tax credit 20 percent 2026 Form 760 instructions | https://github.com/PolicyEngine/policyengine-taxsim/issues/1212, text names policyengine |
| us__scenario_073__snap | stage2 | fns.usda.gov SNAP FY 2027 COLA memo minimum benefit 48 States | https://github.com/TheAxiomFoundation/rulespec-us/issues/1394 |
| us__scenario_079__snap | stage1 | Arizona SNAP "standard medical deduction" amount 2025 2026 | https://github.com/TheAxiomFoundation/rulespec-us/issues/1461 |
| us__scenario_079__snap | stage1 | FNS SNAP FY 2026 COLA memo maximum allotments $546 two person standard deduction $209 | https://github.com/TheAxiomFoundation/rulespec-us/issues/1394, https://github.com/PolicyEngine/policyengine-us/issues/9483, https://github.com/TheAxiomFoundation/rulespec-us/issues/1393, text names policyengine |
| us__scenario_079__snap | stage1 | Arizona DES FAA5 "standard medical deduction" $145 nutrition assistance | https://github.com/TheAxiomFoundation/rulespec-us/issues/1461 |
| us__scenario_079__snap | stage1 | SNAP State Options Report standard medical deduction states Arizona fns.usda.gov | https://github.com/TheAxiomFoundation/rulespec-us/issues/1461 |
| us__scenario_079__snap | stage1 | "State Options Report" SNAP 17th edition "standard medical deduction" Arizona amount | https://github.com/TheAxiomFoundation/rulespec-us/issues/1461 |
| us__scenario_079__snap | stage1 | des.az.gov nutrition assistance medical expense deduction "$145" "$180" | https://github.com/TheAxiomFoundation/rulespec-us/issues/1461 |
| us__scenario_079__snap | stage1 | dbmefaapolicy.azdes.gov "Standard Medical Deduction" NA medical expenses | https://github.com/TheAxiomFoundation/rulespec-us/issues/1461 |
| us__scenario_115__state_income_tax_before_refundable_credits | stage1 | Alabama age 65 retirement income exclusion $6,000 Act 2022-292 section 40-18-19 definition retirement income | https://github.com/PolicyEngine/policyengine-us/issues/9552, text names policyengine |
| us__scenario_115__state_income_tax_before_refundable_credits | stage1 | nfc.usda.gov TAXES Alabama State Income Tax Withholding 2026 bulletin | https://github.com/capable78638974979473297813001-pixel/payroll-tax-engine-/issues/67, https://github.com/capable78638974979473297813001-pixel/payroll-tax-engine-/issues/45 |

`runs/claude-rejudge`: 0 flagged transcripts.

## Re-judged cases

Each re-judged stage-1 prompt differs from the original in one line, the source rule, which now asks for blocked_domains on every search.

| Case | Exposed (original) | Stage 1: original | Stage 1: re-judged | Verdict: original | Verdict: re-judged |
|---|---|---|---|---|---|
| us__scenario_013__snap | stage1, stage2 | reference, 240 (medium) | neither, 288 (medium) | reference_holds (medium) | reference_holds (medium) |
| us__scenario_014__state_income_tax_before_refundable_credits | stage1 | reference, 3092.2 (high) | reference, 3092.2 (high) | reference_holds (high) | reference_holds (high) |
| us__scenario_023__state_refundable_credits | stage1, stage2 | reference, 95 (medium) | reference, 95 (medium) | reference_holds (medium) | reference_holds (medium) |
| us__scenario_030__snap | stage1 | reference, 288 (high) | reference, 288 (medium) | reference_holds (high) | reference_holds (medium) |
| us__scenario_043__state_refundable_credits | stage1, stage2 | consensus, 0 (high) | consensus, 0 (high) | reference_wrong (high) | reference_wrong (high) |
| us__scenario_045__state_refundable_credits | stage1 | reference, 760.78 (high) | reference, 760.78 (high) | reference_holds (high) | reference_holds (high) |
| us__scenario_066__state_refundable_credits | stage1 | reference, 8 (high) | reference, 7.96 (high) | reference_holds (high) | reference_holds (high) |
| us__scenario_073__snap | stage2 | reference, 288 (high) | reference, 288 (high) | reference_holds (high) | reference_holds (high) |
| us__scenario_079__snap | stage1 | reference, 2376 (high) | reference, 2376 (medium) | reference_holds (high) | reference_holds (medium) |
| us__scenario_115__state_income_tax_before_refundable_credits | stage1 | reference, 4.68 (medium) | reference, 4.68 (high) | reference_holds (medium) | reference_holds (high) |

Verdict unchanged in 10 of 10 re-judged cases.
