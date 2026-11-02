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
STATE: MN
OUTPUT: spouse_medicaid_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether Spouse is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only spouse_medicaid_eligible):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: MN
- tax year: 2026

Head:
- age: 50
- gross wages and salaries: $29,000
- bank account assets: $11,300
- hourly wage: $16
- usual weekly hours worked: 36
- is paid hourly
- other medical expenses: $50
- over-the-counter health expenses: $200
- Social Security dependent benefits: $13,664

Spouse:
- age: 18
- over-the-counter health expenses: $100

Child 1:
- age: 6
- over-the-counter health expenses: $100

Benefit inputs:
- spm unit energy subsidy: $50

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
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_medicaid_eligible: whether Spouse is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_medicaid_eligible: whether Child 1 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_chip_eligible: whether Spouse is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_chip_eligible: whether Child 1 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- spouse_medicare_eligible: whether Spouse is eligible for Medicare (1 if yes, 0 if no)
- child1_medicare_eligible: whether Child 1 is eligible for Medicare (1 if yes, 0 if no)
- free_school_meals_eligible: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)
- reduced_price_school_meals_eligible: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)
- child1_head_start_eligible: whether Child 1 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child1_early_head_start_eligible: whether Child 1 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)

Use the `submit_outputs` function exactly once. Return an `outputs` object with every requested quantity keyed by variable name. Each requested key must map to an object with a numeric `value` and a non-empty, specific, concise `explanation`. Each explanation must support the numeric value submitted for the same variable in `outputs`. If an explanation mentions a final amount, that amount must match the corresponding `outputs` value. Do not write that you will use one value while submitting a different value. Do not include scratch work, abandoned calculations, or corrections. End each explanation with `value = X`, where X exactly matches the numeric `value` field. For 1/0 eligibility outputs, submit 1 only when the explanation says eligible or yes, and submit 0 only when it says not eligible or no. Use the exact variable names as keys inside `outputs`. Include every requested key exactly once in `outputs`, even if the value is 0. Put only numeric values in `value`, with no dollar signs, commas, or explanatory text. Do not rely on plain text for the final answers. If an answer is a currency amount, give the annual amount. If an answer is a rate, give a decimal (e.g. 0.25 for 25%).
----- END HOUSEHOLD PROMPT -----

ENGINE REFERENCE VALUE: 1 (eligible)
MODELS: 45 gave a usable answer; 29 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 16 models (1 of them among the benchmark's top-ranked models)
- claude-opus-5: answered 0
  explanation: Spouse's household MAGI exceeds the 138% FPL adult Medicaid threshold for a family of 3 in Minnesota. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Spouse is an adult whose household MAGI (~157% FPL) exceeds the 138% FPL Medicaid expansion limit, so not eligible. value = 0
- deepseek-v4-pro: answered 0
  explanation: Same income limit exceeded. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: The spouse is age 18, and household MAGI is below Minnesota's under-19 child Medical Assistance limit, so the spouse is Medicaid-eligible. value = 1
- deepseek-v4.1-flash: answered 0
  explanation: MAGI income $42,664 exceeds 138% FPL for 3 (~$37,950). value = 0
- gemini-3.6-flash: answered 0
  explanation: Household MAGI exceeds the 138% FPL limit for adult Medicaid expansion in Minnesota. value = 0
- gemini-3.7-flash: answered 0
  explanation: Household MAGI exceeds the 138% FPL Medicaid expansion limit for adults in Minnesota, value = 0
- gemini-3.8-flash: answered 0
  explanation: Household income of about 155% FPL exceeds the adult Medicaid expansion limit of 138% FPL, value = 0
- glm-5.2: answered 0
  explanation: Using the same household income of $42,664 (wages $29,000 + Social Security dependent benefits $13,664) and household size 3, the estimated 138% FPL threshold for 2026 is approximately $37,812. Household income exceeds this threshold, so Spouse is not eligible for Medicaid. value = 0
- glm-5.3: answered 0
  explanation: As a parent/caretaker in a household with MAGI about 153% of poverty, the spouse is above Minnesota's parent Medical Assistance limit (~138% plus disregards) and is not Medicaid-eligible. value = 0
- gpt-5.4-mini: answered 0
  explanation: Spouse is age 18 and no qualifying low-income adult category is established from the provided facts, so not eligible. value = 0
- gpt-5.4-nano: answered 0
  explanation: Spouse age 18 with no disability/pregnancy/SSI/TANF indicators is not eligible under the given PolicyEngine rules; value = 0
- gpt-5.5: answered 0
  explanation: Spouse is age 18 and, using the household income of $29,000 wages plus $13,664 Social Security dependent benefits, household income exceeds the applicable Minnesota Medicaid income limit under PolicyEngine rules, so Spouse is not eligible. value = 0
- gpt-5.6-luna: answered 0
  explanation: Spouse's household income is above the Minnesota adult Medicaid income limit, so Spouse is not eligible; value = 0
- gpt-6-luna: answered 0
  explanation: Spouse's household income, including wages and Social Security benefits, is estimated above Minnesota's adult Medicaid income limit. value = 0
- qwen3.8-max: answered 0
  explanation: Spouse is not eligible for Medicaid under the household's income and characteristics. value = 0