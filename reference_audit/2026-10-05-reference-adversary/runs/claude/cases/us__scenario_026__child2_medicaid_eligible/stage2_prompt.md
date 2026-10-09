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
OUTPUT: child2_medicaid_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether Child 2 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only child2_medicaid_eligible):
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
  explanation: NC child Medicaid income limit for ages 6-18 is about 211% FPL (MAGI). Household of 5 has countable income of roughly $85,209 wages minus $2,778 pre-tax 401k and $130 IRA = ~$82,301, about 219% of the 2026 5-person FPL (~$37,600-$37,900), which exceeds the ~211% FPL child Medicaid threshold, so Child 2 is not eligible. value = 0
- claude-fable-5.1: answered 0
  explanation: Income ~213% FPL exceeds NC Medicaid child (age 6-18) limit of 133% FPL; not eligible. value = 0
- claude-haiku-4.5: answered 0
  explanation: Child 2 is age 11 and the household has employer-sponsored insurance coverage for this child. The household's relevant income for Medicaid eligibility must be assessed. The spouse's gross wages are $85,209 annually. With two wage earners in the household (head and spouse), combined household income exceeds the North Carolina Medicaid eligibility thresholds for children. Additionally, Child 2 already has employer-sponsored health insurance available through the household. Under North Carolina Medicaid rules for 2026, children with household income exceeding the applicable threshold are not eligible for Medicaid, particularly when employer-sponsored coverage is available. Child 2 is not eligible for Medicaid. value = 0
- claude-opus-4.7: answered 0
  explanation: NC Medicaid for children under 19 has an income limit around 215% FPL. Household size 5, 2026 FPL ~$36,580, 215% ~$78,647. Spouse wages $85,209 minus traditional 401k $2,778 = MAGI ~$82,431, which exceeds 215% FPL for size 5. However, NC uses higher threshold for children ages 6-18 at 138% FPL... actually NC covers children under 19 up to 211% FPL. $82,431 > 211% of $36,580 ($77,184), so not Medicaid eligible but CHIP eligible. Medicaid specifically: not eligible. Reconsidering: PolicyEngine NC child Medicaid threshold for ages 6-18 is 133% FPL ($48,651), income exceeds this. value = 0
- claude-opus-4.8: answered 0
  explanation: Child 2 is age 11. Household has one earner with wages of $85,209. NC Medicaid for children ages 6-18 has an income limit around 138% of the federal poverty line. For a household of 5, the 2026 FPL is roughly $36,580, so 138% is about $50,480. However, NC offers CHIP/Medicaid for children up to higher thresholds, but the relevant Medicaid income limit for ages 6-18 is 138% FPL. The MAGI of about $85,000 substantially exceeds 138% FPL for a family of 5, so the child would not qualify for Medicaid. Reconsidering: NC children's Medicaid (Health Choice) covers up to higher percentages; for ages 6-18 the Medicaid limit is 138% FPL and CHIP extends to 211%. At ~$85,000, the income exceeds even 211% of FPL for a family of 5 (~$77,200), so Child 2 is not Medicaid eligible. value = 0
- claude-opus-5: answered 0
  explanation: Income ~260% FPL exceeds NC children's Medicaid limit for age 11. value = 0
- claude-opus-5.5: answered 0
  explanation: Income is about 219% of FPL, above the child Medicaid limit, so not eligible. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Child 2 is age 11 and has employer-sponsored insurance (ESI). Under PolicyEngine's Medicaid eligibility rules, a child who has access to and is covered by employer-sponsored insurance is not eligible for Medicaid. Since Child 2 is listed as having employer-sponsored insurance, they do not meet the uninsured/uncovered requirement for Medicaid eligibility. value = 0
- claude-sonnet-5: answered 0
  explanation: Household income is spouse's wages ~$85,209 plus overtime, for a family of 5 in NC. NC's Medicaid income limit for a child aged 6-18 is about 216% of FPL (~$67,000 for a family of 5 in 2026), which this household's income exceeds. Therefore Child 2 (age 11) is not eligible for Medicaid. value = 0
- claude-sonnet-5.5: answered 0
  explanation: Not eligible: income of about 82k exceeds the child Medicaid limit of 133% FPL. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Children's income limit (210% FPL) is below household income. value = 0
- deepseek-v4-pro: answered 0
  explanation: Family MAGI of $82,301 exceeds 133% FPL ($51,205), above the Medicaid eligibility threshold for children in North Carolina. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Household MAGI of 82,301 exceeds NC Medicaid child income limits for the household size of 5. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: Income $85,209 exceeds NC Medicaid child limit of 210% FPL. value = 0
- gemini-3-flash-preview: answered 0
  explanation: For a household of five in North Carolina, the MAGI of approximately $61,093 (Gross $85,209 minus pre-tax deductions for insurance and retirement) exceeds the child Medicaid limit for ages 6-18, which is 133% of the Federal Poverty Level ($46,736). value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: Household income is above the threshold for Medicaid eligibility for this child. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: The household MAGI of $82,301 exceeds the 133% FPL Medicaid limit for older children; they instead qualify for CHIP. value = 0
- gemini-3.5-flash: answered 0
  explanation: Child 2 is not eligible for Medicaid because the household's income of $61,093 exceeds the 133% FPL threshold for children. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Child 2 is not eligible for Medicaid under PolicyEngine rules for NC in 2026. value = 0
- gemini-3.6-flash: answered 0
  explanation: Child 2's household income exceeds the income limit for Medicaid in North Carolina. value = 0
- gemini-3.7-flash: answered 0
  explanation: Child 2 is not eligible for Medicaid as household income exceeds eligibility limits; value = 0
- gemini-3.8-flash: answered 0
  explanation: Child 2 is not eligible for Medicaid because household income exceeds North Carolina Medicaid limits for children. value = 0
- glm-5.2: answered 0
  explanation: Child 2 is age 11 in a 5-person household with total gross wages of $85,209. The 2026 FPL for a 5-person household is approximately $40,000, placing household income at roughly 213% FPL. NC Medicaid for children 6-18 covers up to 133% FPL, and NC CHIP (Health Choice) covers up to 210% FPL. Household income exceeds 210% FPL, and the child has employer-sponsored insurance. Child 2 is not eligible for Medicaid. value = 0
- glm-5.3: answered 0
  explanation: Household income of $85,209 exceeds the NC children's Medicaid income limit (about 211% of poverty) for a family of 5, so Child 2 is not eligible. value = 0
- gpt-5.4-mini: answered 0
  explanation: Child 2 is a school-age child in a household with earnings above the benchmark Medicaid threshold, so not eligible. value = 0
- gpt-5.4-nano: answered 0
  explanation: Child Medicaid eligibility not indicated given household income level implied by wages and no special-status facts; therefore not eligible. Child 2 Medicaid eligibility value = 0.
- gpt-5.5: answered 0
  explanation: Child 2 is age 11 in NC, but the household's annual earnings of about $85,209 before limited pretax deductions are well above the NC child Medicaid income limit for a 5-person household, so Child 2 is not eligible; employer coverage does not change this income result. value = 0
- gpt-5.6-luna: answered 0
  explanation: Child 2 is not Medicaid eligible because household income exceeds the estimated North Carolina child Medicaid threshold; value = 0
- gpt-5.6-sol: answered 0
  explanation: Child 2 is not eligible because household MAGI exceeds North Carolina's Medicaid income limit for an 11-year-old; value = 0
- gpt-5.6-terra: answered 0
  explanation: Household income is above the North Carolina child Medicaid limit for Child 2; value = 0
- gpt-6-luna: answered 0
  explanation: Child 2 is age 11 and household income exceeds the applicable North Carolina Medicaid income limit for this age; not eligible; value = 0
- gpt-6-sol: answered 0
  explanation: Child 2 is not eligible for Medicaid because household income exceeds the child Medicaid limit; value = 0
- gpt-6.1-sol: answered 0
  explanation: Child 2 is not eligible because household MAGI of $82,301 exceeds the applicable North Carolina child income limit for five people. value = 0
- grok-4.3: answered 0
  explanation: Income above NC Medicaid threshold for family of 5 and ESI present, so not eligible. value = 0
- grok-4.5: answered 0
  explanation: Child 2 age 11 MAGI exceeds NC Medicaid limit of 133% FPL for children 6-18. value = 0
- grok-4.6: answered 0
  explanation: Child 2 is age 11; MAGI $74,555 exceeds NC Medicaid’s 133% FPL limit for children 6–18, so Child 2 is not eligible for Medicaid. value = 0
- grok-4.7: answered 0
  explanation: Child 2 is age 11 and household MAGI is above North Carolina's Medicaid limit for children ages 6-18, so Child 2 is not eligible for Medicaid. value = 0
- grok-build-0.1: answered 0
  explanation: Household income ~240% FPL exceeds NC Medicaid limit for children (~133% FPL base). value = 0
- inkling: answered 0
  explanation: Child 2 (age 11) is above the 133% FPL Medicaid limit for ages 6–18 and has employer-sponsored insurance, so not CHIP-eligible either. value = 0
- kimi-k3: answered 0
  explanation: NC child (6-18) Medicaid MAGI limit ~133% FPL (138% with disregard); household MAGI ~226% FPL for 5 is above it. value = 0
- minimax-m3: answered 0
  explanation: Child 2 is age 11 with household income well above NC Medicaid for Children limits, so not eligible. value = 0
- ox-alpha: answered 0
  explanation: At ages 11, the children fall in NC's 6-18 Medicaid group limited to about 133% FPL; household income (~198% FPL) exceeds it. value = 0
- qwen-3.7-max: answered 0
  explanation: Child 2 is age 11 in NC in 2026. NC Medicaid eligibility for children ages 6-18 is up to 133% of FPL. The household has 5 members; 2026 FPL for a 5-person household is approximately $33,700 (133% ≈ $44,821). The spouse earns $85,209 in gross wages, which far exceeds the 133% FPL threshold. The children have employer-sponsored insurance. Income is well above the Medicaid limit, so Child 2 is not eligible. value = 0
- qwen3.8-max: answered 0
  explanation: Household income is too high for child Medicaid eligibility. value = 0

STAGE 1 RESULT (frozen; sha256 7a076f0216c1a23a931387f5cfe62182987e66e638af01d45834552d6ef268ce):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "\"Under PolicyEngine rules\" could be read as meaning a simplified model that applies NC's 211% child limit without the uninsured condition. Under that reading, MAGI of $82,301 is 212.8% of the 2026 FPL, or 207.8% after the 5-point disregard. That is within 211%, giving 1 (the reference). The law makes the 133\u2013211% group depend on the child having no group health coverage, so the stated employer-sponsored insurance gives 0. I could not extract the text of NC's 2023 SPA or eligibility manual, which were PDFs. That NC uses 42 CFR 435.229 for this group is inferred from the 435.118 income cap, the CMS description \"new Medicaid eligibility group for certain children,\" and search summaries of NC's 2026 CHIP compliance supplement, which describe an uninsured requirement for 133\u2013211% FPL.",
  "citations": [
    {
      "pinpoint": "\u00a7435.229(b)",
      "pre_freeze": true,
      "published": "2016-11-30",
      "quote": "The agency may provide Medicaid to individuals under age 19 ... who meet the definition of an optional targeted low-income child in \u00a7 435.4",
      "source": "42 CFR 435.229 Optional targeted low-income children",
      "url": "https://www.law.cornell.edu/cfr/text/42/435.229"
    },
    {
      "pinpoint": "\"Optional targeted low-income child\" (2) No other coverage",
      "pre_freeze": true,
      "published": "2016-11-30",
      "quote": "An optional targeted low-income child is not covered under a group health plan or health insurance coverage",
      "source": "42 CFR 435.4 Definitions",
      "url": "https://www.law.cornell.edu/cfr/text/42/435.4"
    },
    {
      "pinpoint": "(b)(1)(C)",
      "pre_freeze": true,
      "published": "current codification",
      "quote": "is not found to be eligible for medical assistance under subchapter XIX or, subject to paragraph (5), covered under a group health plan or under health insurance coverage",
      "source": "42 U.S.C. 1397jj (SSA \u00a72110)",
      "url": "https://www.law.cornell.edu/uscode/text/42/1397jj"
    },
    {
      "pinpoint": "(u)(2)(B)",
      "pre_freeze": true,
      "published": "current codification",
      "quote": "a targeted low-income child as defined in section 1397jj(b)(1) of this title (determined without regard to that portion of subparagraph (C) of such section concerning eligibility for medical assistance under this subchapter)",
      "source": "42 U.S.C. 1396d (SSA \u00a71905)",
      "url": "https://www.law.cornell.edu/uscode/text/42/1396d"
    },
    {
      "pinpoint": "\u00a7435.118(c) maximum income standard, age 6-18",
      "pre_freeze": true,
      "published": "2012-03-23",
      "quote": "the higher of\u2014(i) 133 percent FPL; (ii) The highest effective income level for each age group in effect under the Medicaid State plan ... as of March 23, 2010 or December 31, 2013",
      "source": "42 CFR 435.118 Infants and children under age 19",
      "url": "https://www.law.cornell.edu/cfr/text/42/435.118"
    },
    {
      "pinpoint": "\u00a7435.603(d)(4)",
      "pre_freeze": true,
      "published": "2012-03-23",
      "quote": "a state must subtract an amount equivalent to 5 percentage points of the Federal poverty level for the applicable family size only to determine the eligibility of an individual ... under the eligibility group with the highest income standard",
      "source": "42 CFR 435.603 Application of MAGI",
      "url": "https://www.law.cornell.edu/cfr/text/42/435.603"
    },
    {
      "pinpoint": "item (3)",
      "pre_freeze": true,
      "published": "as amended through S.L. 2026-1",
      "quote": "Children through the age of 18 with family incomes equal to or less than two hundred eleven percent (211%) of the federal poverty guidelines.",
      "source": "N.C. Gen. Stat. 108A-54.3A",
      "url": "https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/BySection/Chapter_108A/GS_108A-54.3A.html"
    },
    {
      "pinpoint": "Overview",
      "pre_freeze": true,
      "published": "2023-07-28 (effective 2023-04-01)",
      "quote": "transition its separate NC Health Choice Children's Health Insurance Program to the NC Medicaid Program; adopt a new Medicaid eligibility group for certain children under age 19; and align the income standard for all children under age 19 at 211 percent",
      "source": "CMS Medicaid SPA NC-23-0009 summary",
      "url": "https://www.medicaid.gov/medicaid-spa/2023-07-31/151086"
    },
    {
      "pinpoint": "2026 guidelines table, 5 persons",
      "pre_freeze": true,
      "published": "2026-01-15",
      "quote": "$38,680",
      "source": "HHS ASPE Poverty Guidelines (2026, 48 states & DC; Federal Register 2026-01-15)",
      "url": "https://aspe.hhs.gov/topics/poverty-economic-mobility/poverty-guidelines"
    },
    {
      "pinpoint": "Children ages 0 through 18, family of 5",
      "pre_freeze": null,
      "published": "2026 (exact date not shown)",
      "quote": "A child ages 0 through 18 may be eligible if the family income is $6,802/month or less.",
      "source": "NC Medicaid Eligibility page (NCDHHS)",
      "url": "https://medicaid.ncdhhs.gov/eligibility"
    }
  ],
  "computation": "1) MAGI household for Child 2 (age 11): parents file jointly and claim 3 children, so household size is 5 (42 CFR 435.603(f)). 2) MAGI: spouse wages $85,209 minus traditional 401(k) $2,778 (excluded from W-2 wages) minus traditional IRA deduction $130 (fully deductible because joint income is far below the active-participant phase-out) = $82,301. The overtime-premium deduction under OBBBA is not an above-the-line deduction, so it does not lower AGI or MAGI. I did not assume the head's $21,208 ESI premium is paid pre-tax: the head has no wages, and the prompt says not to infer. No other income is listed. 3) 2026 HHS poverty guideline for 5 people (published 2026-01-15, before the freeze) is $38,680. $82,301 / $38,680 = 212.8% FPL. NC's posted 211% limit for a family of 5 is $6,802 a month. The household's MAGI is $6,858 a month. 4) NC statute G.S. 108A-54.3A(3) covers children through age 18 up to 211% FPL. Under federal law, the only Medicaid group NC can use for ages 6\u201318 above 133% is 42 CFR 435.229, the optional targeted low-income child (OTLIC) group (SSA 1902(a)(10)(A)(ii)(XIV)). That is because 435.118 caps ages 6\u201318 at the higher of 133% or the state's 2010/2013 level, and NC's level was below 133%. CMS approved NC SPA 23-0009, effective 2023-04-01, to adopt \"a new Medicaid eligibility group for certain children under age 19\" at 211%. Under 42 CFR 435.4 and 42 U.S.C. 1396d(u)(2)(B) / 1397jj(b)(1)(C), an OTLIC must not be covered under a group health plan. The prompt states that Child 2 has employer-sponsored insurance, so Child 2 is not an OTLIC. 5) The highest group left for an insured child is 435.118, at 133% FPL. With the 5-point disregard (435.603(d)(4)), the limit is 138%, or $53,378. MAGI of 212.8% exceeds it, so Child 2 is not eligible. The answer stays 0 even if the ESI premium were pre-tax (MAGI $61,093, 158% FPL) or the overtime premium were deducted (192.7%). 6) For contrast, if Child 2 were uninsured: 212.8% \u2212 5 = 207.8%, which is within 211%, so eligible from April 2026 under the 2026 FPL. Under the 2025 FPL used for January\u2013March ($37,650), it is 218.6% \u2212 5 = 213.6%, which is over the limit. So the reference value of 1 follows only if the uninsured condition is ignored.",
  "confidence": "medium",
  "definition_reading": "I read the output as whether Child 2 (age 11, NC, MAGI household of 5) meets the eligibility rules of any NC Medicaid group, including CHIP-funded Medicaid-expansion groups, regardless of enrollment. Coverage at 133\u2013211% FPL for ages 6\u201318 is the optional targeted low-income child group, which requires that the child not be covered by a group health plan. The prompt states that Child 2 has employer-sponsored insurance. The only other group is the 133% (138% with the disregard) group, and income is far above it. So Child 2 is not eligible.",
  "independent_answer": 0,
  "law_supports": "consensus"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine determined that child2, an 11-year-old in North Carolina, is eligible for Medicaid under the older child category. The household's Modified Adjusted Gross Income (MAGI) was calculated at 2.13 times the Federal Poverty Level, which falls within North Carolina's Medicaid income limits for children in this age group. Under the OLDER_CHILD eligibility category that applies to this household member, the income threshold permits eligibility at this MAGI level. Consequently, PolicyEngine assigned an is_medicaid_eligible value of True for child2, reflecting that the household meets both the categorical and income requirements for Medicaid coverage in 2026.
----- END ENGINE DERIVATION -----