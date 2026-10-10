You are a reference adversary for a US tax-and-benefit benchmark. Each benchmark question gives a household and asks for policy quantities for tax year 2026. A microsimulation engine produced the reference answer. On the question below, a cluster of AI models answering from memory, without tools, agreed on an answer other than the reference. Agreement among models proves nothing, and neither does the engine. Your job is to find out what the law gives.

This is stage 1 of 2. In this stage you work the answer out yourself from primary law, before you see anything about how the engine computed its value.

How to work:
1. Use web search and web fetch to find and read primary law in force for tax year 2026: statutes, regulations, official agency publications, and official forms and their instructions. Prefer the issuing government's own site.
2. Apply the household prompt's conventions exactly as the models were told them: treat any unlisted numeric input as 0 and any other unlisted fact, boolean or status as false; assume tax filing and program take-up when required; do not infer unlisted income, expenses, assets, benefit receipt, rent or health coverage.
3. Read the output definition literally. It decides which people, tax units, returns, taxes, credits or benefits the number covers. Where it lists components, decide for each candidate amount whether the definition includes it. Where the household holds more than one tax unit or return, decide from the definition which of them the number covers.
4. Cite every rule you rely on: the source, a pinpoint (section, line, table or page), the URL you read, the publication or effective date, and a short verbatim quote. The reference's law was frozen on 2026-07-03: set pre_freeze to true if the source was published before that date, false if after, and null if you cannot tell. If an amount for 2026 (a standard deduction, bracket, threshold, rate base or allotment) had not been published before 2026-07-03, say so in computation and say what had been published.
5. Do not consult PolicyEngine or PolicyBench in any form: not policyengine.org, policybench.org, their GitHub repositories, their documentation, their package source, or any calculator built on them. Do not fetch anything from these domains: policybench.org, www.policybench.org, policyengine.org, www.policyengine.org, github.com, raw.githubusercontent.com. Do not rely on any calculator or estimate built by an AI model. A citation of any of these sources voids your answer.
6. Say which answer the law supports: "reference", "consensus", "neither", or "both_readings" (the reference under one reasonable reading of the definition or the facts, the consensus under another).
7. In definition_reading, say how you read the output definition for this household. In ambiguity, describe any second reading that the definition or the household prompt genuinely admits, and the answer it gives; use "" if there is none.
8. independent_answer is your own number (1 or 0 for an eligibility output). Use null only when the stated facts and the law leave it genuinely undetermined, and say why in ambiguity.

Some output definitions mention PolicyEngine (for example "eligible for Medicaid under PolicyEngine rules"). Work those from the law as well; if the mention could change the answer, say so in ambiguity.

Return only the JSON object the schema asks for.

TAX YEAR: 2026    REFERENCE LAW FROZEN: 2026-07-03
STATE: PA
OUTPUT: child2_chip_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether Child 2 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only child2_chip_eligible):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: PA
- tax year: 2026

Head:
- age: 45
- gross wages and salaries: $60,000
- bank account assets: $1,924
- child support received: $1,267
- has employer-sponsored insurance
- hourly wage: $29
- usual weekly hours worked: 40
- other medical expenses: $50
- over-the-counter health expenses: $25
- taxable interest income: $10

Child 1:
- age: 10
- has employer-sponsored insurance
- other medical expenses: $50
- over-the-counter health expenses: $15

Child 2:
- age: 10
- has employer-sponsored insurance
- other medical expenses: $50
- over-the-counter health expenses: $15

Child 3:
- age: 10
- has employer-sponsored insurance
- other medical expenses: $50
- over-the-counter health expenses: $15

Tax unit:
- first home mortgage balance: $247,000
- second home mortgage balance: $80,426

Household inputs:
- auto loan balance: $13,000
- auto loan interest: $980
- household vehicles value: $16,100

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
- child1_wic_eligible: whether Child 1 is eligible for WIC (1 if yes, 0 if no)
- child2_wic_eligible: whether Child 2 is eligible for WIC (1 if yes, 0 if no)
- child3_wic_eligible: whether Child 3 is eligible for WIC (1 if yes, 0 if no)
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_medicaid_eligible: whether Child 1 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_medicaid_eligible: whether Child 2 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child3_medicaid_eligible: whether Child 3 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_chip_eligible: whether Child 1 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_chip_eligible: whether Child 2 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child3_chip_eligible: whether Child 3 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
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

ENGINE REFERENCE VALUE: 0 (not eligible)
MODELS: 45 gave a usable answer; 25 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 1, given by 20 models (2 of them among the benchmark's top-ranked models)
- claude-fable-5.1: answered 1
  explanation: Income ≈185% FPL is within PA CHIP limit (up to ~314% FPL) and above Medicaid; eligible. value = 1
- claude-opus-4.7: answered 1
  explanation: PA CHIP eligibility for a child under 19 is based on household income relative to FPL (up to ~314% FPL in PA), regardless of current ESI enrollment for PolicyEngine eligibility determination. Household of 4 with $60,000 income is roughly 192% FPL, well within PA CHIP income limits. Child 2 is age 10 and meets categorical requirements. value = 1
- claude-opus-4.8: answered 1
  explanation: PA CHIP eligibility for a child depends on household income relative to the CHIP income limit (up to ~314% FPL in PA). Household has 4 people with ~$60,000 in wages plus small interest and child support. The 2026 FPL for a household of 4 is roughly $32,150, so income is about 187% FPL, well under PA's CHIP threshold. Child 2 is age 10 and meets age requirements, so the child is CHIP-eligible regardless of current enrollment. value = 1
- claude-opus-5: answered 1
  explanation: Child under 19 with household income ~190% FPL, within PA CHIP income limits. value = 1
- claude-opus-5.5: answered 1
  explanation: Income is about 187% FPL, which is above the Medicaid limit and below PA CHIP's limit of about 314%, so eligible. value = 1
- claude-sonnet-5.5: answered 1
  explanation: Income of about 186% FPL is below the PA CHIP limit of about 314% FPL and above the Medicaid limit, so eligible. value = 1
- deepseek-v4-flash-0731: answered 1
  explanation: Household income is within PA's CHIP eligibility range (158-314% FPL) for children, so Child 2 is CHIP eligible. value = 1
- deepseek-v4.1-flash: answered 1
  explanation: Children age 10 with household income $60,010 below 300% FPL ($99,000) are CHIP eligible. value = 1
- gemini-3.6-flash: answered 1
  explanation: In Pennsylvania, children up to age 19 in a household of 4 with income below 314% FPL qualify for CHIP. Annual income of $60,010 is below the CHIP threshold, making Child 2 eligible. value = 1
- gemini-3.7-flash: answered 1
  explanation: Child 2 is under age 19 and household income is within Pennsylvania CHIP income eligibility limits; value = 1
- gemini-3.8-flash: answered 1
  explanation: Child 2 is under 19 and household income is within Pennsylvania CHIP income eligibility limits. value = 1
- glm-5.3: answered 1
  explanation: Child 2 is under 19 and, with household income of about 185% of the poverty line, is above the Medicaid children's threshold but within Pennsylvania's CHIP income limit, so eligible. value = 1
- gpt-5.6-luna: answered 1
  explanation: Child 2 is age 10 and household income is within Pennsylvania's higher CHIP income range, so the child is eligible. value = 1
- grok-4.6: answered 1
  explanation: Child 2 is age 10, not Medicaid-eligible, and household MAGI is below Pennsylvania CHIP limits (about 314 percent FPL), so Child 2 is eligible for CHIP. value = 1
- grok-4.7: answered 1
  explanation: Child 2 is 10, is not Medicaid-eligible, and household MAGI is below Pennsylvania's CHIP limit of 314% of FPL, so Child 2 is eligible for CHIP under income and age rules. value = 1
- kimi-k2.6: answered 1
  explanation: Child 2 is age 10, and the household's MAGI of $60,010 for a family of four falls below Pennsylvania's CHIP income limit of 314% of the federal poverty level, so Child 2 meets the eligibility rules. value = 1
- kimi-k3: answered 1
  explanation: Child 2 is under 19 with household income around 187% FPL: above PA's child Medicaid limit but below PA's ~319% FPL CHIP upper limit, so CHIP eligible (current ESI coverage does not negate eligibility). value = 1
- minimax-m3: answered 1
  explanation: Household income $61,277 is within PA CHIP range (138%-319% FPL ~$43,000-$99,500 for family of 4). Child 2 eligible for CHIP. value = 1
- ox-alpha: answered 1
  explanation: Child 2 is age 10 (under 19) in the same PA household with total counted income of $60,010 (~185% FPL for 4 people). This falls below Pennsylvania's CHIP income threshold, making the child eligible; current employer-sponsored coverage does not negate eligibility under PolicyEngine rules, and no asset tests apply. value = 1
- qwen3.8-max: answered 1
  explanation: Child 2 is within the Pennsylvania CHIP income range. value = 1