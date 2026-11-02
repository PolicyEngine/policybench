You are a reference adversary for a US tax-and-benefit benchmark. Each benchmark question gives a household and asks for policy quantities for tax year 2026. A microsimulation engine produced the reference answer. On the question below, a cluster of AI models answering from memory, without tools, agreed on an answer other than the reference.

This is stage 2 of 2: reconciliation. In stage 1, a judge who had not seen how the engine derived the reference worked the question from primary law. Its result appears below exactly as it was recorded, with its sha256. Stage 1 is frozen and you may not revise it. If the engine derivation or the law shows that stage 1 erred (it misread a fact, missed or misapplied a rule, or used the wrong year's amount), say so in stage1_error and name the error. Do not silently change course: if your independent_answer, or your view of which answer the law supports, differs from stage 1's, stage1_error must say why. Use "" for stage1_error only when stage 1 stands.

Only now do you see how the engine derived the reference. The derivation is a short narrative that a language model wrote from the engine's computation trace for this household; it can misdescribe a step, but the reference value is the engine's own output. Compare each step with the law and with the output definition, and decide:
- reference_holds: the reference is what the law and the output definition give on the stated facts.
- reference_wrong: the engine misapplies the law on the stated facts, or uses an amount or rule the law had not published (for example a 2026 amount the engine projected itself where no agency had published one before 2026-07-03).
- definition_mismatch: the engine computes something other than what the output definition describes (it includes or leaves out people, returns, taxes, credits or benefits that the definition covers or excludes).
- prompt_ambiguous: the stated facts or the definition genuinely admit more than one answer (for example the answer turns on an input the prompt does not list).

engine_step_at_issue names the derivation step that departs from the law or the definition; use "" when the reference holds.

suggested_adjudication:
- affirmed: the reference holds.
- regenerated: the reference should be recomputed under a stated convention or a corrected input; the output stays scored.
- engine_defect: the engine misapplies the law on the stated facts.
- unlisted_input: the answer turns on an input the prompt does not list.
- later_law: the reference rests on law or an amount published after 2026-07-03, or never published.
- definition_exclusion: the engine's quantity does not match the output definition, so the output should be excluded.
- none: you suggest nothing.
Pair them this way: reference_holds with affirmed; reference_wrong with engine_defect, later_law or regenerated; definition_mismatch with definition_exclusion or regenerated; prompt_ambiguous with unlisted_input or definition_exclusion. "none" goes with any verdict.

reference_value is the engine reference below. consensus_value is the consensus answer you weighed (null if none applies).

Cite the law you rely on as in stage 1: source, pinpoint, URL, date, pre_freeze and a short quote. The engine derivation is not a citation. Do not consult PolicyEngine or PolicyBench in any form: not policyengine.org, policybench.org, their GitHub repositories, their documentation, their package source, or any calculator built on them. Do not fetch anything from these domains: policybench.org, www.policybench.org, policyengine.org, www.policyengine.org, github.com, raw.githubusercontent.com. Do not rely on any calculator or estimate built by an AI model. A citation of any of these sources voids your answer.

Your verdict changes no score. A developer adjudicates every case you do not return as reference_holds.

Return only the JSON object the schema asks for.

TAX YEAR: 2026    REFERENCE LAW FROZEN: 2026-07-03
STATE: NC
OUTPUT: child1_medicaid_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether Child 1 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only child1_medicaid_eligible):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: NC
- tax year: 2026

Head:
- age: 48
- employer sponsored insurance premiums: $21,208
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $1,020
- other health insurance premiums: $1,020
- other medical expenses: $400
- over-the-counter health expenses: $100

Spouse:
- age: 45
- gross wages and salaries: $85,209
- bank account assets: $1,330
- fsla overtime premium: $7,746
- has employer-sponsored insurance
- hourly wage: $33
- usual weekly hours worked: 50
- other medical expenses: $200
- over-the-counter health expenses: $350
- roth 401k contributions desired: $490
- roth ira contributions desired: $201
- stock assets: $84,353
- traditional 401k contributions desired: $2,778
- traditional ira contributions desired: $130

Child 1:
- age: 11
- has employer-sponsored insurance
- other medical expenses: $250
- over-the-counter health expenses: $250

Child 2:
- age: 11
- has employer-sponsored insurance
- other medical expenses: $250
- over-the-counter health expenses: $250

Child 3:
- age: 9
- has employer-sponsored insurance
- other medical expenses: $250
- over-the-counter health expenses: $250

Tax unit:
- first home mortgage balance: $108,000

Household inputs:
- auto loan balance: $17,529
- auto loan interest: $378
- household vehicles value: $10,230

Provide the following policy quantities for this household:
- federal_income_tax_before_refundable_credits: federal individual income tax after nonrefundable credits and before refundable credits. This subtracts nonrefundable credits actually used, including CDCC and the nonrefundable portion of CTC or other credits when applicable; it does not subtract EITC or refundable portions of credits such as refundable CTC
- federal_refundable_credits: total refundable federal income tax credits, including EITC and refundable portions of credits such as refundable CTC when applicable; exclude the ACA Premium Tax Credit
- payroll_tax: annual household employee-side payroll tax: employee Social Security tax, employee Medicare tax, Additional Medicare Tax, and mandatory employee state payroll taxes. Exclude employer payroll taxes, FUTA, employer unemployment-insurance taxes, and self-employment tax
- self_employment_tax: annual self-employment tax liability, excluding employee payroll taxes and Additional Medicare Tax
- state_income_tax_before_refundable_credits: state individual income tax after nonrefundable credits and before refundable credits, excluding local income and payroll taxes
- state_refundable_credits: total refundable state individual income tax credits
- local_income_tax: annual local income, wage, and earnings tax liability in the separate local-income-tax output: NYC income tax, Philadelphia wage tax, Kansas City earnings tax, and St. Louis earnings tax where applicable
- snap: annual SNAP (food stamps) benefit amount
- ssi: annual Supplemental Security Income (SSI) amount
- tanf: annual Temporary Assistance for Needy Families (TANF) benefit amount
- head_wic_eligible: whether Head is eligible for WIC (1 if yes, 0 if no)
- spouse_wic_eligible: whether Spouse is eligible for WIC (1 if yes, 0 if no)
- child1_wic_eligible: whether Child 1 is eligible for WIC (1 if yes, 0 if no)
- child2_wic_eligible: whether Child 2 is eligible for WIC (1 if yes, 0 if no)
- child3_wic_eligible: whether Child 3 is eligible for WIC (1 if yes, 0 if no)
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_medicaid_eligible: whether Spouse is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_medicaid_eligible: whether Child 1 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_medicaid_eligible: whether Child 2 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child3_medicaid_eligible: whether Child 3 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_chip_eligible: whether Spouse is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_chip_eligible: whether Child 1 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_chip_eligible: whether Child 2 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child3_chip_eligible: whether Child 3 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- spouse_medicare_eligible: whether Spouse is eligible for Medicare (1 if yes, 0 if no)
- child1_medicare_eligible: whether Child 1 is eligible for Medicare (1 if yes, 0 if no)
- child2_medicare_eligible: whether Child 2 is eligible for Medicare (1 if yes, 0 if no)
- child3_medicare_eligible: whether Child 3 is eligible for Medicare (1 if yes, 0 if no)
- free_school_meals_eligible: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)
- reduced_price_school_meals_eligible: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)
- child1_head_start_eligible: whether Child 1 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child2_head_start_eligible: whether Child 2 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child3_head_start_eligible: whether Child 3 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child1_early_head_start_eligible: whether Child 1 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)
- child2_early_head_start_eligible: whether Child 2 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)
- child3_early_head_start_eligible: whether Child 3 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)

Use the `submit_outputs` function exactly once. Return an `outputs` object with every requested quantity keyed by variable name. Each requested key must map to an object with a numeric `value` and a non-empty, specific, concise `explanation`. Each explanation must support the numeric value submitted for the same variable in `outputs`. If an explanation mentions a final amount, that amount must match the corresponding `outputs` value. Do not write that you will use one value while submitting a different value. Do not include scratch work, abandoned calculations, or corrections. End each explanation with `value = X`, where X exactly matches the numeric `value` field. For 1/0 eligibility outputs, submit 1 only when the explanation says eligible or yes, and submit 0 only when it says not eligible or no. Use the exact variable names as keys inside `outputs`. Include every requested key exactly once in `outputs`, even if the value is 0. Put only numeric values in `value`, with no dollar signs, commas, or explanatory text. Do not rely on plain text for the final answers. If an answer is a currency amount, give the annual amount. If an answer is a rate, give a decimal (e.g. 0.25 for 25%).
----- END HOUSEHOLD PROMPT -----

ENGINE REFERENCE VALUE: 1 (eligible)
MODELS: 45 gave a usable answer; 1 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 44 models (5 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: NC Medicaid for children ages 6-18 uses an income limit of about 133% FPL (plus 5% disregard, ~138% FPL). Household of 5 has 2026 FPL near $37,650, so the limit is roughly $52,000. Spouse's MAGI-countable wages of $85,209 (less $2,908 pre-tax retirement contributions, ~$82,300) far exceed 138% FPL, so Child 1 is not income-eligible for Medicaid. value = 0
- claude-fable-5.1: answered 0
  explanation: Income ~213% FPL exceeds NC Medicaid child (age 6-18) limit of 133% FPL; not eligible. value = 0
- claude-haiku-4.5: answered 0
  explanation: Child 1 is age 11 and the household has gross income of $85,209 (spouse's wages) plus the head's income. North Carolina's Medicaid eligibility for children is typically limited to households at or below 200% of the federal poverty line. For 2026, the federal poverty line for a household of 5 is approximately $27,465, making the 200% threshold around $54,930. The household income of $85,209 exceeds this threshold. Additionally, Child 1 has employer-sponsored insurance through the household, which further indicates the family does not qualify for Medicaid. Child 1 is not eligible for Medicaid, value = 0
- claude-opus-4.7: answered 0
  explanation: NC Medicaid for children ages 6-18 has income limit around 138% FPL. Household of 5 FPL ~$37,650; 138% ~$51,957. Spouse's wages of $85,209 far exceed this threshold, so Child 1 is not eligible. value = 0
- claude-opus-4.8: answered 0
  explanation: NC Medicaid for children ages 6-18 has an income limit around 138% FPL. The household of 5 has spouse wages of $85,209, far exceeding the ~138% FPL threshold (~$45,000) for a family of 5. Child 1 (age 11) is not income-eligible for Medicaid. value = 0
- claude-opus-5: answered 0
  explanation: Income ~260% FPL exceeds NC children's Medicaid limit (211% FPL for ages 6-18). value = 0
- claude-opus-5.5: answered 0
  explanation: Income is about 219% of FPL, above the child Medicaid limit, so not eligible. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Child 1 is age 11 and has employer-sponsored insurance (ESI). Under PolicyEngine's Medicaid eligibility rules, a child who already has employer-sponsored insurance coverage is treated as having access to qualifying coverage and is therefore not eligible for Medicaid. Since Child 1 has ESI, they do not meet the uninsured/uninsured-equivalent requirement for Medicaid eligibility. value = 0
- claude-sonnet-5: answered 0
  explanation: Household income is spouse's wages ($85,209) plus overtime, far above NC Medicaid/CHIP income limits for a family of 5 (roughly 211% FPL for children's Medicaid, about $67,000 for a family of 5 in 2026). With gross income near $93,000, the family exceeds NC's Medicaid/CHIP threshold for children, so Child 1 is not eligible. value = 0
- claude-sonnet-5.5: answered 0
  explanation: Not eligible: income of about 82k exceeds the child Medicaid limit of 133% FPL. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Children's income limit (210% FPL ~77k) is below household income ~93k. value = 0
- deepseek-v4-pro: answered 0
  explanation: Family MAGI of $82,301 exceeds 133% FPL ($51,205), above the Medicaid eligibility threshold for children in North Carolina. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Household MAGI of 82,301 exceeds NC Medicaid/CHIP child Medicaid income limits for the household size of 5. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: Income $85,209 exceeds NC Medicaid child limit of 210% FPL. value = 0
- gemini-3-flash-preview: answered 0
  explanation: Child 1 is 11 years old. In North Carolina, the Medicaid limit for children of this age is approximately 147% of the Federal Poverty Level (FPL). The household MAGI of $61,093 exceeds this limit (approximately $51,655 for a family of 5). value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: Household income is above the threshold for Medicaid eligibility for this child. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: The household MAGI of $82,301 exceeds the 133% FPL Medicaid limit for older children; they instead qualify for CHIP. value = 0
- gemini-3.5-flash: answered 0
  explanation: Child 1 is not eligible for Medicaid because the household's income of $61,093 exceeds the 133% FPL threshold for children. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Child 1 is not eligible for Medicaid under PolicyEngine rules for NC in 2026. value = 0
- gemini-3.6-flash: answered 0
  explanation: Child 1's household income exceeds the income limit for Medicaid in North Carolina. value = 0
- gemini-3.7-flash: answered 0
  explanation: Child 1 is not eligible for Medicaid as household income exceeds eligibility limits; value = 0
- gemini-3.8-flash: answered 0
  explanation: Child 1 is not eligible for Medicaid because household income exceeds North Carolina Medicaid limits for children. value = 0
- glm-5.2: answered 0
  explanation: Child 1 has employer-sponsored insurance, making them not eligible for Medicaid under PolicyEngine rules. value = 0
- glm-5.3: answered 0
  explanation: Household income of $85,209 exceeds the NC children's Medicaid income limit (about 211% of poverty) for a family of 5, so Child 1 is not eligible. value = 0
- gpt-5.4-mini: answered 0
  explanation: Child 1 is a school-age child in a household with earnings above the benchmark Medicaid threshold, so not eligible. value = 0
- gpt-5.4-nano: answered 0
  explanation: Child Medicaid eligibility not indicated given household income level implied by wages and no special-status facts; therefore not eligible. Child 1 Medicaid eligibility value = 0.
- gpt-5.5: answered 0
  explanation: Child 1 is age 11 in North Carolina, but the household's annual income is above the Medicaid/CHIP income limit applied to school-age children in PolicyEngine for a five-person household, so Child 1 is not eligible; value = 0
- gpt-5.6-luna: answered 0
  explanation: Child 1 is not Medicaid eligible because household income exceeds the estimated North Carolina child Medicaid threshold; value = 0
- gpt-5.6-sol: answered 0
  explanation: Child 1 is not eligible because household MAGI exceeds North Carolina's Medicaid income limit for an 11-year-old; value = 0
- gpt-5.6-terra: answered 0
  explanation: Household income is above the North Carolina child Medicaid limit for Child 1; value = 0
- gpt-6-luna: answered 0
  explanation: Child 1 is age 11 and household income exceeds the applicable North Carolina Medicaid income limit for this age; not eligible; value = 0
- gpt-6-sol: answered 0
  explanation: Child 1 is not eligible for Medicaid because household income exceeds the child Medicaid limit; value = 0
- gpt-6.1-sol: answered 0
  explanation: Child 1 is not eligible because household MAGI of $82,301 exceeds the applicable North Carolina child income limit for five people. value = 0
- grok-4.3: answered 0
  explanation: Income above NC Medicaid threshold for family of 5 and ESI present, so not eligible. value = 0
- grok-4.5: answered 0
  explanation: Child 1 age 11 MAGI exceeds NC Medicaid limit of 133% FPL for children 6-18. value = 0
- grok-4.6: answered 0
  explanation: Child 1 is age 11; NC Medicaid for children 6–18 stops at 133% FPL (about $51,000), and MAGI $74,555 is above that, so Child 1 is not eligible for Medicaid. value = 0
- grok-4.7: answered 0
  explanation: Child 1 is age 11. North Carolina Medicaid for children ages 6-18 stops at about 138% FPL, and household MAGI is above that limit, so Child 1 is not eligible for Medicaid. value = 0
- grok-build-0.1: answered 0
  explanation: Household income ~240% FPL exceeds NC Medicaid limit for children (~133% FPL base). value = 0
- inkling: answered 0
  explanation: Child 1 (age 11) Medicaid for ages 6–18 is limited to 133% FPL (~$50,000); household income exceeds this, and CHIP requires being uninsured. value = 0
- kimi-k3: answered 0
  explanation: For NC children ages 6-18 the Medicaid MAGI limit is about 133% FPL (138% with the 5% disregard); household MAGI ~226% FPL for 5 exceeds it. value = 0
- minimax-m3: answered 0
  explanation: Child 1 is age 11 with household income well above NC Medicaid for Children limits, so not eligible. value = 0
- ox-alpha: answered 0
  explanation: At ages 11, the children fall in NC's 6-18 Medicaid group limited to about 133% FPL; household income (~198% FPL) exceeds it. value = 0
- qwen-3.7-max: answered 0
  explanation: Child 1 is 11 years old. While children have higher Medicaid income limits than adults (approximately 266% of FPL for ages 6-18 in NC, about $103,500 for a household of 5 in 2026), the household income of $85,209 is within this range. However, Child 1 has employer-sponsored insurance, which disqualifies them from Medicaid eligibility in most cases. value = 0
- qwen3.8-max: answered 0
  explanation: Household income is too high for child Medicaid eligibility. value = 0

STAGE 1 RESULT (frozen; sha256 af3c07aeb23144f52957ae2409576639c44cad366375bcaa6e61cd2d3da7d5b2):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "The answer depends on whether having ESI blocks NC's 211% coverage for ages 6\u201318. The second reading follows NC's statute, G.S. 108A-54.3A(3), and the NCDHHS eligibility chart, both of which set the 211% limit for all children through age 18 with no condition about being uninsured. On that reading, MAGI of $82,301 is 212.8% of the 2026 FPL; after the 5-point disregard it is 207.8%, within 211%, so the answer is 1 (the reference), at least from April 2026. For January\u2013March, NC's 2025 FPL ($37,650) puts income above even the 216% line. The definition's 'under PolicyEngine rules' could also matter: if the engine checks only income against 211% plus the disregard and ignores the child's ESI, it returns 1. I could not read verbatim the SPA text naming the new group as 42 CFR 435.229. I am relying on CMS's summary ('a new Medicaid eligibility group for certain children') and on the federal definition of that group, so the uninsured requirement is an inference about which group NC uses, not something quoted from the SPA.",
  "citations": [
    {
      "pinpoint": "2026 guidelines table, 48 contiguous states, household of 5",
      "pre_freeze": true,
      "published": "2026-01-15",
      "quote": "5 | $38,680",
      "source": "HHS ASPE, 2026 Poverty Guidelines (Annual Update of the HHS Poverty Guidelines, 91 FR, Jan. 2026)",
      "url": "https://aspe.hhs.gov/topics/poverty-economic-mobility/poverty-guidelines"
    },
    {
      "pinpoint": "Children ages 0 through 18 income chart, family size 5",
      "pre_freeze": null,
      "published": "2026 (page last modified 2026-09-17; figures based on 2026 FPL)",
      "quote": "A child ages 0 through 18 may be eligible if the family income is $2,807/month or less ... Family size 5: $6,802/month",
      "source": "NC Medicaid (NCDHHS), Eligibility page",
      "url": "https://medicaid.ncdhhs.gov/eligibility"
    },
    {
      "pinpoint": "(3)",
      "pre_freeze": true,
      "published": "as amended through S.L. 2026-1",
      "quote": "Children through the age of 18 with family incomes equal to or less than two hundred eleven percent (211%) of the federal poverty guidelines.",
      "source": "N.C. Gen. Stat. \u00a7 108A-54.3A",
      "url": "https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/BySection/Chapter_108A/GS_108A-54.3A.html"
    },
    {
      "pinpoint": "SPA description; effective 2023-04-01, approved 2023-07-28",
      "pre_freeze": true,
      "published": "2023-07-28",
      "quote": "adopt a new Medicaid eligibility group for certain children under age 19 ... align the income standard for all children under age 19 at 211 percent of the federal poverty level",
      "source": "CMS, Medicaid SPA NC-23-0009 summary",
      "url": "https://www.medicaid.gov/medicaid-spa/2023-07-31/151086"
    },
    {
      "pinpoint": "\u00a7 435.229(b)",
      "pre_freeze": true,
      "published": "2016-11-30",
      "quote": "The agency may provide Medicaid to individuals under age 19 ... who meet the definition of an optional targeted low-income child in \u00a7 435.4",
      "source": "42 CFR 435.229 Optional targeted low-income children",
      "url": "https://www.law.cornell.edu/cfr/text/42/435.229"
    },
    {
      "pinpoint": "\u00a7 457.310(b)(2)(ii)",
      "pre_freeze": true,
      "published": "current eCFR",
      "quote": "Covered under a group health plan or under health insurance coverage, as defined in section 2791 of the Public Health Service Act",
      "source": "42 CFR 457.310 Targeted low-income child (incorporated by 42 CFR 435.4 definition of optional targeted low-income child)",
      "url": "https://www.law.cornell.edu/cfr/text/42/457.310"
    },
    {
      "pinpoint": "\u00a7 435.603(d)(4)",
      "pre_freeze": true,
      "published": "current eCFR",
      "quote": "a state must subtract an amount equivalent to 5 percentage points of the Federal poverty level for the applicable family size only to determine the eligibility of an individual for medical assistance under the eligibility group with the highest income standard",
      "source": "42 CFR 435.603 Application of MAGI-based methodologies",
      "url": "https://www.law.cornell.edu/cfr/text/42/435.603"
    },
    {
      "pinpoint": "North Carolina row, Medicaid ages 6-18",
      "pre_freeze": true,
      "published": "table as of 2023-12-01",
      "quote": "Children Medicaid Ages 6-18 | 211% ... Children Separate CHIP | N/A",
      "source": "CMS, Medicaid, CHIP & BHP Eligibility Levels table",
      "url": "https://www.medicaid.gov/medicaid/national-medicaid-chip-program-information/medicaid-childrens-health-insurance-program-basic-health-program-eligibility-levels"
    }
  ],
  "computation": "Steps:\n1. Household MAGI. Under 42 CFR 435.603(f), Child 1 is a tax dependent, so the household is the parents' five-person household. The only income is the spouse's gross wages of $85,209. The $2,778 traditional 401(k) deferral is excluded from wages (IRC 402(g)). The $130 traditional IRA contribution is deductible above the line under \u00a7219, because AGI is far below the phase-out for a spouse covered by a workplace plan. AGI and MAGI = 85,209 \u2212 2,778 \u2212 130 = $82,301. Roth contributions don't reduce MAGI. The overtime deduction is below the line, so it doesn't change AGI. Nothing says the head's $21,208 ESI premium was paid pre-tax out of wages, and the prompt says not to infer it, so it isn't deducted.\n2. FPL. The 2026 HHS guideline for a household of 5 is $38,680 (published January 2026, before the freeze). MAGI is 82,301 / 38,680 = 212.8% FPL, or $6,858/month.\n3. NC income limit. NC covers children through age 18 up to 211% FPL: $6,802/month for a household of 5, which is 2.11 \u00d7 38,680 / 12. Income is above that line. Under 42 CFR 435.603(d)(4), a 5-point FPL disregard ($1,934) applies, but only for the eligibility group with the highest income standard the child can qualify for. 212.8% \u2212 5 = 207.8%, which is within 211%. So on income alone, an uninsured child would qualify. That is how the reference value of 1 comes out.\n   - Timing caveat: NC switches to the new FPL on April 1. For January\u2013March 2026 the 2025 FPL ($37,650) applies; 216% of that is $81,324, which is below $82,301. So even an uninsured child would be eligible only from April.\n4. Which group covers ages 6\u201318 between 133% and 211%. This band is the former NC Health Choice population, moved to Medicaid on April 1, 2023 under SPA NC-23-0009. CMS describes that SPA as adopting \"a new Medicaid eligibility group for certain children under age 19\". That matches the optional targeted low-income children group (42 CFR 435.229), which I could not read verbatim in the SPA PDF. That group covers only children who meet the 435.4 definition, which brings in 457.310(b)(2): the child must not be \"Covered under a group health plan or under health insurance coverage.\" Child 1 has employer-sponsored insurance all year, so Child 1 is not in this group.\n5. The highest group left for an insured 11-year-old is the mandatory 435.118 group for ages 6\u201318 at 133% FPL (138% with the disregard). Income of about 208\u2013213% FPL is above that.\n6. Result: Child 1 is not eligible for NC Medicaid, so the answer is 0. Most models reached 0 by applying a 133% limit to the whole 6\u201318 age group, which is wrong for an uninsured child. The answer is still right here because Child 1 has ESI.\nAll 2026 amounts used (FPL $38,680 and NC's $6,802/month) were published before 2026-07-03.",
  "confidence": "medium",
  "definition_reading": "The flag asks whether Child 1 (age 11, NC) is eligible for Medicaid during 2026, not whether Child 1 is enrolled. Eligibility depends on the parents' five-person MAGI household and on Child 1's stated health coverage. The prompt says Child 1 has employer-sponsored insurance and that coverage facts hold all year, so Child 1 is covered by a group health plan for the whole year. That rules out NC's 133\u2013211% Medicaid-expansion CHIP group for ages 6\u201318, which is limited to uninsured optional targeted low-income children. The 133% group is the only one left, and income of about 208\u2013213% FPL is above it.",
  "independent_answer": 0,
  "law_supports": "consensus"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine determined that child1, an 11-year-old in North Carolina, is eligible for Medicaid under the older child category. The household's Modified Adjusted Gross Income (MAGI) was calculated at 2.13 times the Federal Poverty Level, which falls within North Carolina's Medicaid income limits for children in this age group. Under the older child eligibility category that applies to children aged 6 through 18, the state's income threshold permits eligibility at this MAGI level. Consequently, PolicyEngine assigned child1 an is_medicaid_eligible value of True, reflecting that the household meets both the categorical and income requirements for Medicaid coverage.
----- END ENGINE DERIVATION -----