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
STATE: SC
OUTPUT: head_medicare_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether Head is eligible for Medicare (1 if yes, 0 if no)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only head_medicare_eligible):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: SC
- tax year: 2026

Head:
- age: 53
- gross wages and salaries: $25,665
- bank account assets: $630
- child support received: $1,200
- disability benefits: $13,044
- employer sponsored insurance premiums: $8,389
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $2,200
- is disabled
- other health insurance premiums: $2,200
- other medical expenses: $30,000
- over-the-counter health expenses: $400

Tax unit:
- first home mortgage balance: $310,000

Household inputs:
- household vehicles value: $2,359

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
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- free_school_meals_eligible: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)
- reduced_price_school_meals_eligible: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)

Use the `submit_outputs` function exactly once. Return an `outputs` object with every requested quantity keyed by variable name. Each requested key must map to an object with a numeric `value` and a non-empty, specific, concise `explanation`. Each explanation must support the numeric value submitted for the same variable in `outputs`. If an explanation mentions a final amount, that amount must match the corresponding `outputs` value. Do not write that you will use one value while submitting a different value. Do not include scratch work, abandoned calculations, or corrections. End each explanation with `value = X`, where X exactly matches the numeric `value` field. For 1/0 eligibility outputs, submit 1 only when the explanation says eligible or yes, and submit 0 only when it says not eligible or no. Use the exact variable names as keys inside `outputs`. Include every requested key exactly once in `outputs`, even if the value is 0. Put only numeric values in `value`, with no dollar signs, commas, or explanatory text. Do not rely on plain text for the final answers. If an answer is a currency amount, give the annual amount. If an answer is a rate, give a decimal (e.g. 0.25 for 25%).
----- END HOUSEHOLD PROMPT -----

ENGINE REFERENCE VALUE: 0 (not eligible)
MODELS: 46 gave a usable answer; 30 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 1, given by 16 models (2 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 1
  explanation: Head is age 53 (under 65) but is disabled and receives disability benefits ($13,044); under PolicyEngine rules, individuals receiving Social Security disability benefits qualify for Medicare before age 65, so Head is eligible. value = 1
- claude-opus-4.7: answered 1
  explanation: Head is disabled and receives disability benefits; SSDI recipients qualify for Medicare. value = 1
- claude-sonnet-4.6: answered 1
  explanation: Medicare eligibility before age 65 is available to individuals who have been entitled to Social Security Disability Insurance (SSDI) benefits for at least 24 months. The Head is listed as disabled and receiving disability benefits of $13,044 annually. Given that the Head is 53 years old and is marked as disabled with disability benefits, they qualify for Medicare based on disability status (assuming the standard 24-month waiting period has been met, as the facts describe a full tax-benefit year with disability status treated as constant). Therefore, the Head is eligible for Medicare. value = 1
- deepseek-v4-flash-0731: answered 1
  explanation: Head is disabled and receiving SSDI disability benefits, so is eligible for Medicare after the qualifying period. value = 1
- deepseek-v4-pro: answered 1
  explanation: As a disabled individual receiving SSDI benefits, the head qualifies for Medicare after the 24-month waiting period, which is assumed to have passed. value = 1
- deepseek-v4-pro-0813: answered 1
  explanation: The head is under 65 but disabled and receiving disability benefits, meeting Medicare disability eligibility. value = 1
- deepseek-v4.1-flash: answered 1
  explanation: Head is disabled and receives SSDI, making them eligible for Medicare. value = 1
- gemini-3-flash-preview: answered 1
  explanation: The Head is marked as disabled and receives disability benefits (SSDI), which standardly qualifies an individual for Medicare coverage after a two-year period. value = 1
- gemini-3.1-flash-lite-preview: answered 1
  explanation: Head is disabled and has met the waiting period requirements for SSDI/Medicare eligibility. value = 1
- gemini-3.1-pro-preview: answered 1
  explanation: The Head is disabled and receives Social Security disability benefits, which generally qualifies them for Medicare. value = 1
- gemini-3.5-flash: answered 1
  explanation: The head is disabled and receives disability benefits (SSDI), qualifying them for Medicare eligibility. value = 1
- gpt-5.6-luna: answered 1
  explanation: Head is reported as disabled, which qualifies for Medicare under the applicable disability eligibility rule; value = 1
- gpt-5.6-sol: answered 1
  explanation: The head is disabled and receives disability benefits, which makes the head eligible for Medicare under the disability pathway even though the head is under age 65. value = 1
- gpt-6-luna: answered 1
  explanation: The head is disabled and receives disability benefits, qualifying for Medicare under the disability eligibility pathway. value = 1
- gpt-6.1-sol: answered 1
  explanation: The head is eligible under the disability-based Medicare eligibility rule. value = 1
- grok-4.5: answered 1
  explanation: Head is disabled and receiving disability benefits consistent with SSDI, triggering Medicare eligibility after the statutory waiting period under PolicyEngine rules. value = 1