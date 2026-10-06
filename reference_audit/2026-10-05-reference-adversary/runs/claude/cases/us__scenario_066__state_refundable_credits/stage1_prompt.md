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
STATE: VA
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: VA
- tax year: 2026

Head:
- age: 40
- gross wages and salaries: $520
- bank account assets: $14,000
- has other means tested health coverage at interview
- hourly wage: $32
- usual weekly hours worked: 40
- is paid hourly
- over-the-counter health expenses: $100
- pre-subsidy rent: $5,160

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

ENGINE REFERENCE VALUE: $7.96 (engine output 7.955999851226807)
MODELS: 46 gave a usable answer; 12 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 25 models (1 of them among the benchmark's top-ranked models)
- claude-haiku-4.5: answered 0
  explanation: Virginia does not have state-level refundable income tax credits for individuals. The Earned Income Credit (EIC) is a federal-only credit. Virginia offers the Earned Income Credit subtraction (non-refundable) and other non-refundable credits, but no refundable credits for tax year 2026. The household's annual gross wages of $520 (based on $32/hour × 40 hours/week) is extremely low, but without state refundable credits available, the refundable credit amount is zero. value = 0
- claude-opus-4.7: answered 0
  explanation: Virginia's main refundable credit is the refundable Earned Income Tax Credit (EITC), but with only $520 of wages and no qualifying children, the federal EITC for a 40-year-old single filer is essentially zero (below the minimum earned income threshold for meaningful credit), making VA's 15% refundable portion also effectively $0. No other VA refundable credits apply. value = 0
- claude-opus-4.8: answered 0
  explanation: Virginia's main refundable individual income tax credit is the refundable Earned Income Tax Credit, available to those eligible for the federal EITC. With only $520 in annual wages and $14,000 in bank assets, the household's federal EITC would be minimal, and Virginia's refundable EITC is 15% of the federal EITC. Given the very low earnings and the standard deduction eliminating tax liability, the refundable state credit amount rounds to negligible/zero. value = 0
- claude-opus-5: answered 0
  explanation: Virginia's low-income credit/EITC option is nonrefundable-limited here and tax is 0; no refundable state credits. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Virginia has a limited set of refundable state income tax credits. For tax year 2026, the household head has gross wages of only $520, which is far below the standard deduction ($8,000 for single filers in Virginia). Virginia taxable income would be $0 after the standard deduction, resulting in $0 Virginia income tax liability. Virginia's main refundable credit is the Earned Income Tax Credit (EITC), which is a percentage of the federal EITC. With annual wages of only $520 and no dependents, the federal EITC for a single filer with no children requires earned income above ~$600 to generate any credit, and at $520 the federal EITC would be $0 (below the phase-in threshold for childless filers). Therefore, the Virginia refundable EITC credit is also $0. No other applicable refundable Virginia credits apply to this household. value = 0
- claude-sonnet-5: answered 0
  explanation: Virginia does not offer a refundable state EITC by default (the state credit is nonrefundable unless the low-income taxpayer credit or refundable EITC option is elected); given the household's very low reported wage income ($520) and no indication of election of the refundable EITC option, no refundable state credit amount applies. value = 0
- deepseek-v4-pro: answered 0
  explanation: Virginia's earned income credit is nonrefundable, so no state refundable credits apply. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: There are no applicable state-level refundable credits for this household configuration. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Virginia has no refundable individual income tax credits for this profile. value = 0
- glm-5.2: answered 0
  explanation: Virginia does not have refundable state income tax credits applicable to this household, which has no tax liability. value = 0
- glm-5.3: answered 0
  explanation: Virginia offers no refundable income tax credits to this household (the Virginia EITC is nonrefundable and the state tax liability is $0 anyway). value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable Virginia income tax credits are triggered by the provided facts, so state refundable credits are zero; value = 0
- gpt-5.4-nano: answered 0
  explanation: No state refundable income tax credits are assumed for this income level under the given facts. value = 0
- gpt-5.6-luna: answered 0
  explanation: No Virginia refundable individual income tax credit applies to this single adult with $520 of wages and no dependents; value = 0
- gpt-5.6-terra: answered 0
  explanation: No Virginia refundable credit is available from the listed facts for this childless household. value = 0
- gpt-6-sol: answered 0
  explanation: No refundable Virginia income tax credit applies to this childless filer at the reported earnings; value = 0
- grok-4.3: answered 0
  explanation: No state refundable credits apply with zero tax liability. value = 0
- grok-4.5: answered 0
  explanation: No Virginia refundable credits apply to this single adult with $520 income. value = 0
- grok-4.7: answered 0
  explanation: Virginia’s 15% refundable EITC election expired before tax year 2026, and the remaining EITC is nonrefundable and unusable against $0 tax. No other refundable Virginia credits apply, so refundable state credits are $0. value = 0
- grok-build-0.1: answered 0
  explanation: Virginia does not offer refundable state income tax credits applicable to this household's situation, such as no state EITC. value = 0
- kimi-k2.6: answered 0
  explanation: Based on the reported household facts, this single filer with no dependents and zero state tax liability qualifies for no refundable Virginia individual income tax credits. The total refundable credits are therefore zero. value = 0
- kimi-k3: answered 0
  explanation: Virginia's refundable EITC (15% of the federal credit) applied only to tax years 2022 through 2025 and is not available for tax year 2026; no other refundable Virginia income tax credits apply. value = 0
- minimax-m3: answered 0
  explanation: No refundable Virginia state income tax credits apply to this household. value = 0
- qwen-3.7-max: answered 0
  explanation: Virginia's refundable credits (such as the Earned Income Tax Credit) require tax liability or specific eligibility. The head has $520 in gross wages and $0 tax liability. Virginia does not have a refundable EITC that provides payments exceeding liability for this income level in 2026 with no qualifying children listed. No other refundable credits apply based on listed facts. value = 0
- qwen3.8-max: answered 0
  explanation: No Virginia refundable individual income tax credits apply to a single-person household with $520 of wages and no qualifying children. value = 0.0