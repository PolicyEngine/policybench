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
STATE: MI
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: MI
- tax year: 2026

Head:
- age: 44
- gross wages and salaries: $36,276
- bank account assets: $800
- child support expense: $5,200
- employer sponsored insurance premiums: $21,208
- has employer-sponsored insurance
- hourly wage: $21
- usual weekly hours worked: 40
- is paid hourly
- pre-subsidy rent: $10,560
- weeks unemployed: 8

Household inputs:
- household vehicles value: $16,400

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

ENGINE REFERENCE VALUE: $760.79 (engine output 760.7887573242188)
MODELS: 45 gave a usable answer; 4 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 18 models (0 of them among the benchmark's top-ranked models)
- claude-haiku-4.5: answered 0
  explanation: Michigan does not have a state earned income tax credit (EITC). Michigan has a home property tax credit and homestead property tax credit, but the household is renting (pre-subsidy rent of $10,560), not owning a home. Michigan does not have other significant refundable individual income tax credits for this household composition and income level. No state refundable credits apply. value = 0
- claude-opus-5: answered 0
  explanation: Michigan EITC is 30% of federal EITC, which is $0 here; home heating credit not modeled as income tax refundable credit, so total is $0. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Michigan's primary refundable state income tax credits include the Homestead Property Tax Credit and the Home Heating Credit. The household has no property tax listed and no heating costs listed, so neither applies. There is no mortgage interest deduction context here. Michigan also has the EITC (a percentage of the federal EITC), but the head has no qualifying children listed and is 44 years old. For 2026, a childless worker at age 44 with gross wages of $36,276 minus the child support paid ($5,200, not deductible for Michigan AGI purposes) — Michigan AGI is based on federal AGI. Federal AGI: $36,276 gross wages; employer-sponsored insurance premiums of $21,208 are pre-tax (excluded from gross wages already or treated as W-2 box 1 reduction). Taking wages at face value as $36,276. No qualifying children means the federal EITC for a childless filer at this income level ($36,276) exceeds the phase-out threshold for single filers (approximately $18,591 for 2025, adjusted for 2026), so federal EID would be $0 for this income level. Michigan EITC = 6% (2023 law restored to 30% phased in; for 2026 Michigan EITC is 30% of federal EITC). However, with no federal EITC (income too high for childless filer), Michigan EITC = $0. No other refundable Michigan credits apply given the unlisted inputs. Total refundable state credits = $0. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Michigan EITC is 30% of the federal EITC, which is $0, so the refundable Michigan credit is $0. No other refundable credits apply. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household does not qualify for additional Michigan refundable credits based on inputs provided. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: Since the federal EITC is $0, the Michigan EITC is also $0. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Total refundable state individual income tax credits equal 0. value = 0
- glm-5.2: answered 0
  explanation: Michigan's primary refundable tax credits include the Earned Income Tax Credit (EITC) and the Homestead Property Tax Credit. For tax year 2026, the Michigan EITC is 30% of the federal EITC. The head is a single filer with no children listed. For 2026, the federal EITC for a single filer with no qualifying children and income of $36,276 is 0. Therefore, the state EITC is 0. The Homestead Property Tax Credit is a refundable credit for low-income renters and homeowners. The head's total household resources are $36,276 and rent is $10,560. For renters, 20% of rent is considered property tax paid, which is $2,112. The credit is calculated as 60% of the property tax that exceeds 3.2% of total household resources. 3.2% of $36,276 is $1,160.83. The difference is $951.17. 60% of $951.17 is $570.70. However, the Homestead Property Tax Credit is completely phased out if total household resources exceed $64,000, which is not the case here. The refundable credit is $570.70. value = 0
- glm-5.3: answered 0
  explanation: The Michigan EITC is a percentage of the federal EITC, which is $0 here, and no other refundable Michigan credits apply. value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable Michigan income tax credits are identifiable from the provided household facts. value = 0
- gpt-5.4-nano: answered 0
  explanation: No Michigan refundable credit eligibility details (e.g., qualified dependent or other conditions) are provided, so total state refundable credits are 0. value = 0
- gpt-5.6-terra: answered 0
  explanation: No Michigan refundable credit applies to this childless household. value = 0
- grok-4.3: answered 0
  explanation: No state refundable credits qualify. value = 0
- grok-build-0.1: answered 0
  explanation: No state refundable income tax credits apply based on given facts for Michigan. value = 0
- inkling: answered 0
  explanation: Federal EITC is zero, so the Michigan 6% EITC is zero; the Homestead credit does not exceed the tax liability, so no refundable portion remains. value = 0
- minimax-m3: answered 0
  explanation: Michigan offers limited refundable credits and no household-level refundable credits apply given this household composition and the fact that no rent was actually paid beyond pre-subsidy rent listed. The Michigan homestead property tax credit may apply, but since the head is a renter and the credit is calculated based on rent paid exceeding a threshold, no refundable credit is triggered here, value = 0.
- qwen-3.7-max: answered 0
  explanation: The household has no eligible refundable Michigan state tax credits listed (no Earned Income Tax Credit specified at state level beyond federal match, no homestead property tax credit qualifying based on listed facts, and no other refundable credits). With no qualifying refundable credits, the total is 0. value = 0
- qwen3.8-max: answered 0
  explanation: No refundable state income tax credits apply. value = 0