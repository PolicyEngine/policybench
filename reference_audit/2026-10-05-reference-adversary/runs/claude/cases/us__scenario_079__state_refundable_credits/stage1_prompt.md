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
STATE: AZ
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: AZ
- tax year: 2026

Head:
- age: 58
- has indian health service coverage at interview
- is blind
- is disabled
- other medical expenses: $432
- over-the-counter health expenses: $200
- Social Security disability income: $7,560

Spouse:
- age: 55
- bank account assets: $1,045
- has indian health service coverage at interview
- is blind
- is disabled
- over-the-counter health expenses: $100

Tax unit:
- first home mortgage balance: $455,000

Household inputs:
- auto loan balance: $8,500
- auto loan interest: $255
- household vehicles value: $18,200

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
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_medicaid_eligible: whether Spouse is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_chip_eligible: whether Spouse is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- spouse_medicare_eligible: whether Spouse is eligible for Medicare (1 if yes, 0 if no)
- free_school_meals_eligible: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)
- reduced_price_school_meals_eligible: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)

Use the `submit_outputs` function exactly once. Return an `outputs` object with every requested quantity keyed by variable name. Each requested key must map to an object with a numeric `value` and a non-empty, specific, concise `explanation`. Each explanation must support the numeric value submitted for the same variable in `outputs`. If an explanation mentions a final amount, that amount must match the corresponding `outputs` value. Do not write that you will use one value while submitting a different value. Do not include scratch work, abandoned calculations, or corrections. End each explanation with `value = X`, where X exactly matches the numeric `value` field. For 1/0 eligibility outputs, submit 1 only when the explanation says eligible or yes, and submit 0 only when it says not eligible or no. Use the exact variable names as keys inside `outputs`. Include every requested key exactly once in `outputs`, even if the value is 0. Put only numeric values in `value`, with no dollar signs, commas, or explanatory text. Do not rely on plain text for the final answers. If an answer is a currency amount, give the annual amount. If an answer is a rate, give a decimal (e.g. 0.25 for 25%).
----- END HOUSEHOLD PROMPT -----

ENGINE REFERENCE VALUE: $50.00
MODELS: 46 gave a usable answer; 7 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 38 models (5 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Arizona's main refundable credits (family income tax credit is nonrefundable; increased excise tax credit requires filing with income, and this couple has only $7,560 nontaxable SSDI and no earned income). With no earnings, AZ has no refundable EITC-style credit for them, and the household does not qualify for any refundable AZ credit, so total refundable state credits are $0. value = 0
- claude-haiku-4.5: answered 0
  explanation: Arizona does not have a state-level refundable individual income tax credit program. The household has no income subject to Arizona individual income tax (only Social Security disability income of $7,560, which is not subject to state income tax). Therefore, there are no state refundable credits available. value = 0
- claude-opus-4.8: answered 0
  explanation: AZ refundable individual income tax credits require qualifying income or eligibility. The household's only income is $7,560 in Social Security disability income, which is not taxable for AZ purposes, leaving no AZ taxable income and no basis for refundable credits like the AZ family income tax credit (which requires taxable wages) or the increased excise tax credit (requires income tax filing thresholds not met here). value = 0
- claude-opus-5: answered 0
  explanation: No earnings or qualifying dependents; AZ refundable credits are 0. value = 0
- claude-opus-5.5: answered 0
  explanation: No Arizona refundable credit applies to this household. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Arizona has very limited refundable state income tax credits. The household's income consists solely of Social Security disability income ($7,560), which is fully exempt from Arizona income tax. With no Arizona taxable income and no wages or earned income, the household does not qualify for any Arizona refundable credits (such as the Affordable Income Tax Credit or other refundable credits). Arizona's main credits (e.g., family income tax credit, increased excise tax credit) are non-refundable or have specific eligibility requirements not met here. There is no Arizona refundable credit applicable to this household's situation. value = 0
- claude-sonnet-5: answered 0
  explanation: Arizona does not offer a refundable individual income tax credit applicable to this household's circumstances (no Property Tax Credit eligibility due to age/SSI status, no other refundable state credits apply). value = 0
- claude-sonnet-5.5: answered 0
  explanation: There is no tax liability and no qualifying refundable state credit. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: No state refundable credits apply with zero income and no qualifying children. value = 0
- deepseek-v4-pro: answered 0
  explanation: No state refundable credits apply to this household (e.g., no dependent children, no applicable property tax credits). value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: No Arizona refundable state income tax credits apply to this household. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: No Arizona refundable credits apply given zero state income tax liability. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: No state refundable credits apply based on the reported income and demographics. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: The household does not qualify for any state refundable credits. value = 0
- gemini-3.5-flash: answered 0
  explanation: The household does not qualify for any refundable Arizona state tax credits. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: With no state income tax liability or qualifying earnings, there are no state refundable credits. value = 0
- gemini-3.6-flash: answered 0
  explanation: The household qualifies for no refundable Arizona state tax credits. value = 0
- gemini-3.7-flash: answered 0
  explanation: The household does not qualify for refundable state tax credits in Arizona. value = 0
- gemini-3.8-flash: answered 0
  explanation: Under PolicyEngine rules for Arizona, childless married couples with no wage income have no refundable state tax credits. value = 0
- glm-5.2: answered 0
  explanation: Arizona has no broadly available refundable individual income tax credits applicable to this household given zero taxable income and no qualifying listed refundable credits. value = 0
- glm-5.3: answered 0
  explanation: Arizona's refundable family tax credit depends on federal EITC, which is zero here; there are no other refundable Arizona credits. value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable Arizona income tax credits are triggered by the listed facts, so the amount is 0; value = 0
- gpt-5.4-nano: answered 0
  explanation: No state refundable credits are supported by the provided facts (no qualifying earned income/children/etc. listed), so state_refundable_credits is 0. value = 0
- gpt-5.6-luna: answered 0
  explanation: No Arizona refundable individual income tax credit is available without qualifying tax liability, earned income, or qualifying children; value = 0
- gpt-5.6-sol: answered 0
  explanation: The household has no reported facts generating an Arizona refundable individual income tax credit; value = 0
- gpt-5.6-terra: answered 0
  explanation: No Arizona refundable credit applies because there are no qualifying earnings, children, or other stated qualifying circumstances. value = 0
- gpt-6-luna: answered 0
  explanation: No taxable income, dependents, or other facts support a refundable Arizona individual income-tax credit; amount is zero. value = 0
- gpt-6-sol: answered 0
  explanation: With no qualifying earnings or dependent children, no Arizona refundable tax credit applies; value = 0
- grok-4.3: answered 0
  explanation: No state tax liability or qualifying credits. value = 0
- grok-4.5: answered 0
  explanation: No qualifying children or other Arizona refundable credit bases exist with zero tax liability. value = 0
- grok-build-0.1: answered 0
  explanation: Arizona has a state Earned Income Tax Credit equal to a percentage of the federal EITC, but since federal EITC is $0, the state EITC is $0. No other refundable state credits apply. value = 0
- inkling: answered 0
  explanation: With zero state tax liability and no applicable refundable state credits for this household, the amount is 0. value = 0
- kimi-k2.6: answered 0
  explanation: Arizona refundable credits such as the property tax refund require listed rent or property tax payments, and other refundable credits require earned income or other listed qualifying inputs. None of these are reported, so no refundable credits are generated. value = 0
- kimi-k3: answered 0
  explanation: Arizona offers no refundable income tax credits applicable to this childless household with zero tax liability. value = 0
- minimax-m3: answered 0
  explanation: Arizona has no state income tax and therefore no refundable state income tax credits. value = 0
- ox-alpha: answered 0
  explanation: Arizona's refundable property-tax credit requires age 65+, which neither spouse meets, and no other refundable AZ credit applies at $0 liability. value = 0
- qwen-3.7-max: answered 0
  explanation: The household has no Arizona taxable income and no qualifying dependents. No refundable state individual income tax credits apply. value = 0
- qwen3.8-max: answered 0
  explanation: No Arizona refundable credits apply under these facts. value = 0.0