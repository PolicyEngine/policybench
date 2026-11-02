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
OUTPUT: free_school_meals_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only free_school_meals_eligible):
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
MODELS: 45 gave a usable answer; 22 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 23 models (3 of them among the benchmark's top-ranked models)
- claude-fable-5.1: answered 0
  explanation: Household income 42,664 is above 130% FPL for 3 (~34,645) and no categorical eligibility (no SNAP/TANF), so no free-meal support. value = 0
- claude-opus-5: answered 0
  explanation: Household income (~$42,664, about 170% FPL for a family of 3) exceeds the 130% FPL free meal threshold and the household is not categorically eligible via TANF/SNAP direct certification in this calculation. value = 0
- claude-opus-5.5: answered 0
  explanation: Income at about 160% of the poverty line exceeds the 130% free meal limit, so not eligible. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Free school meals (as opposed to reduced-price meals) in Minnesota through the National School Lunch Program require household income at or below 130% of the Federal Poverty Level (FPL). The household consists of 3 members (head age 50, spouse age 18, child age 6). For 2026, 130% FPL for a 3-person household is approximately $37,777. Household income includes gross wages of $29,000 and Social Security dependent benefits of $13,664, totaling $42,664. This exceeds the 130% FPL threshold of ~$37,777, so the household does not qualify for free school meals (only potentially reduced-price, which does not count as eligible here). value = 0
- claude-sonnet-5.5: answered 0
  explanation: Countable income of about 42,700 (wages plus Social Security) is above 130% of the FPL for 3 (about 34,600). Not eligible for free meals. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Household income (~157% FPL) exceeds the 130% FPL free-meal threshold, so no free meal support. value = 0
- deepseek-v4-pro: answered 0
  explanation: Income $42,664 > 130% FPL $35,326; not free-eligible. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: Household income $42,664 exceeds 130% FPL for 3 (~$35,750). value = 0
- gemini-3.8-flash: answered 0
  explanation: Household income of $42,664 exceeds 130% of the federal poverty line for a household of 3, making the child ineligible for federal free school meals, value = 0
- glm-5.2: answered 0
  explanation: Total household income for school meal purposes is $42,664 ($29,000 wages + $13,664 Social Security dependent benefits). This is above 130% of the 2026 federal poverty guideline for a household of 3, so the household is not eligible for free school meals. value = 0
- glm-5.3: answered 0
  explanation: Household income of $42,664 is about 153% of the federal poverty guideline, above the 130% cutoff for free school meals. value = 0
- gpt-5.4-nano: answered 0
  explanation: Free school meal eligibility is not provided and no categorical eligibility (e.g., SNAP/TANF receipt) is given; with SNAP/TANF outputs set to 0, the household is assumed not eligible for free meals; value = 0
- gpt-5.5: answered 0
  explanation: The household has a school-age child, but annual countable income of $42,664 is above the federal free-meal limit for a 3-person household and no categorical free-meal status is indicated, so free school meals are not eligible; value = 0
- gpt-5.6-luna: answered 0
  explanation: Household income is above the federal free-school-meal threshold for three people, so positive free-meal support is not returned; value = 0
- gpt-5.6-terra: answered 0
  explanation: Reported household income is above the modeled federal free school-meal income threshold and no direct-certification benefit is reported; value = 0
- gpt-6-luna: answered 0
  explanation: Estimated household income exceeds the free-meal income threshold for a three-person household; no free-meal support is expected. value = 0
- grok-4.5: answered 0
  explanation: Household money income of 42664 is approximately 156 percent of the projected 2026 FPL for three, above the 130 percent free-meal limit, so the household is not eligible for free school meals. value = 0
- grok-4.6: answered 0
  explanation: Household MAGI of about 156 percent of FPL exceeds the 130 percent free-meal limit and the unit is not SNAP/TANF categorically eligible, so PolicyEngine does not return positive free school meal support. value = 0
- grok-4.7: answered 0
  explanation: Gross income including Social Security is $42,664, about 156-160% FPL, which is above the 130% free-meal limit. SNAP and TANF are $0, so there is no categorical free-meal eligibility. The household is not eligible for free school meals. value = 0
- grok-build-0.1: answered 0
  explanation: Household gross income of $42,664 is approximately 156.7% of the 2026 FPL for a 3-person household (~$27,207), exceeding the 130% FPL threshold for free school meals. value = 0
- inkling: answered 0
  explanation: Household gross income (~$42,664 for 3) is above 130% FPL ($33,566), so they do not qualify for free school meals. value = 0
- kimi-k3: answered 0
  explanation: Under PolicyEngine's federal school-meal income test, household income is about 156% of poverty, above the 130% free-meal limit, so the household is not eligible for free-meal support. value = 0
- ox-alpha: answered 0
  explanation: Countable household income including the $13,664 Social Security benefit is $42,664, about 160% of the 3-person poverty line, above the 130% free-meal cutoff, and there is no SNAP/TANF categorical pathway. value = 0