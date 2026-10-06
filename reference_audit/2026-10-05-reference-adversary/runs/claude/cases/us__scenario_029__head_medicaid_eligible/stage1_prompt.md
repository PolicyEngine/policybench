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
STATE: OK
OUTPUT: head_medicaid_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only head_medicaid_eligible):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: OK
- tax year: 2026

Head:
- age: 21
- bank account assets: $4,250
- financial assistance: $50,000
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $50
- other health insurance premiums: $50
- other medical expenses: $2,000
- over-the-counter health expenses: $150
- pre-subsidy rent: $6,614
- stock assets: $50,735
- taxable interest income: $312

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

ENGINE REFERENCE VALUE: 1 (eligible)
MODELS: 46 gave a usable answer; 27 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 19 models (0 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Oklahoma expanded Medicaid; adults 19-64 are eligible up to 138% FPL based on MAGI. Head's MAGI includes $50,000 of financial assistance (counted as income in PolicyEngine's Medicaid income calculation) plus $312 taxable interest, totaling about $50,312, far above 138% of the one-person FPL (~$21,600 in 2026). Even excluding financial assistance, the $50,000 support places countable resources/income far above thresholds for other pathways; as an adult aged 21 with income above 138% FPL, Head is not eligible for Medicaid. value = 0
- claude-haiku-4.5: answered 0
  explanation: Head is 21 years old in Oklahoma for tax year 2026. Oklahoma did not expand Medicaid under the ACA, so Medicaid eligibility is limited to specific categories. For a 21-year-old with no dependent children, no disability, and not pregnant, and with employment-based insurance coverage, Head does not meet the categorical requirements for Medicaid in Oklahoma. Additionally, total household countable assets (bank account $4,250 + stock assets $50,735 = $54,985) exceed Oklahoma's asset limits for Medicaid eligibility. Head is not eligible for Medicaid. value = 0
- claude-opus-4.7: answered 0
  explanation: Head is 21, single adult in Oklahoma. OK expanded Medicaid covers adults up to 138% FPL (~$21,597 for household of 1 in 2026). Head has $50,000 financial assistance plus $312 interest income, far exceeding the income limit. Not eligible. value = 0
- claude-opus-4.8: answered 0
  explanation: Head is age 21, single adult with no dependents. Oklahoma adult Medicaid eligibility uses MAGI-based income. Taxable interest of $312 is well under the limit, suggesting income-based eligibility. However, Oklahoma's adult expansion Medicaid considers MAGI income; the $50,000 financial assistance is not counted as MAGI income, but the head has employer-sponsored insurance and substantial assets. Under MAGI rules assets are not counted, so eligibility turns on income, which is very low ($312 interest), placing them under the expansion threshold (138% FPL). But PolicyEngine treats this as eligible based on low MAGI income. Reconsidering: with only $312 countable MAGI income, the head falls below 138% FPL and Oklahoma expanded Medicaid, so they are eligible. value = 0
- claude-opus-5: answered 0
  explanation: Income of $50,000 plus interest far exceeds Oklahoma's adult Medicaid expansion limit of 138% FPL (~$21,600 for one person). value = 0
- claude-sonnet-4.6: answered 0
  explanation: Medicaid eligibility in Oklahoma for adults without dependents (expansion not adopted by OK until 2021, but now in effect) is based on Modified Adjusted Gross Income (MAGI) at or below 133% of the Federal Poverty Level (FPL). The Head is a 21-year-old single adult with no dependents listed. Their income includes $50,000 in financial assistance and $312 in taxable interest income, totaling approximately $50,312 in countable income. For 2026, 133% of FPL for a single individual is approximately $20,783 (based on ~$15,625 × 1.33). The Head's MAGI of ~$50,312 far exceeds 133% FPL. Additionally, the Head has employer-sponsored insurance, which may further affect eligibility. The Head is not eligible for Medicaid due to income exceeding the threshold. value = 0
- claude-sonnet-5: answered 0
  explanation: Head is a 21-year-old childless adult in Oklahoma with $312 taxable interest but $50,000 in financial assistance counted as income, far above the Medicaid expansion income limit (138% FPL). Oklahoma did expand Medicaid, but with countable income this high (well above ~$21,000 for a household of one), Head exceeds the income eligibility threshold and is also not otherwise categorically eligible (not pregnant, disabled, or a parent/caretaker). Therefore Head is not eligible for Medicaid. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: The $50,000 financial assistance counts as income well above 138% FPL for a single adult in Oklahoma, so not Medicaid-eligible. value = 0
- deepseek-v4-pro: answered 0
  explanation: Under ACA MAGI rules, household income ($50,312) exceeds 138% of the FPL for a single adult (estimated $21,597). Head is not eligible. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: Income is above the Medicaid eligibility threshold for a single adult in Oklahoma. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Head is not eligible for Medicaid under PolicyEngine rules. value = 0
- glm-5.2: answered 0
  explanation: Oklahoma Medicaid expansion covers adults up to 138% FPL (approximately $22,000 for a single person in 2026). The household has financial assistance of $50,000 plus $312 in taxable interest income, totaling $50,312, which far exceeds the eligibility threshold. Additionally, the head has employer-sponsored insurance. value = 0
- glm-5.3: answered 0
  explanation: Income above Oklahoma MAGI limits and ESI available. value = 0
- gpt-5.4-nano: answered 0
  explanation: No Medicaid-eligibility facts (e.g., disability, pregnancy, dependent child, or other qualifying status) are provided under PolicyEngine rules, so Head Medicaid eligibility is estimated as not eligible; value = 0
- gpt-5.5: answered 0
  explanation: For Oklahoma adult Medicaid under PolicyEngine rules, a 21-year-old adult in a one-person household must meet the MAGI income limit; the listed $50,000 financial assistance plus $312 taxable interest exceeds the expansion adult limit, so Head is not eligible; value = 0
- gpt-5.6-luna: answered 0
  explanation: Head is age 21 but household income of $50,000 exceeds the Oklahoma adult Medicaid expansion income limit, so Head is not Medicaid eligible. value = 0
- minimax-m3: answered 0
  explanation: In Oklahoma, a 21-year-old adult with no children and income/assets well above the Medicaid limit is not eligible. Head also has employer-sponsored insurance. value = 0
- qwen-3.7-max: answered 0
  explanation: Oklahoma expanded Medicaid under the ACA to adults with income up to 138% of the Federal Poverty Level. For a one-person household in 2026, 138% of FPL is approximately $21,000. The head's countable income ($50,000 financial assistance + $312 interest = $50,312) far exceeds this threshold, making them ineligible for Medicaid. value = 0
- qwen3.8-max: answered 0
  explanation: No qualifying income, disability, pregnancy, or other eligibility basis is listed for the 21-year-old head. value = 0