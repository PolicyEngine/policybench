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
- age: 80
- bank account assets: $58,700
- health insurance premiums excluding Medicare Part B: $298
- is disabled
- non-qualified dividend income: $16
- non sch d capital gains: $72
- other health insurance premiums: $298
- over-the-counter health expenses: $200
- Social Security retirement income: $23,736
- taxable private pension income: $6,720

Tax unit:
- first home mortgage balance: $43,000

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

ENGINE REFERENCE VALUE: $25.00
MODELS: 46 gave a usable answer; 10 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 35 models (4 of them among the benchmark's top-ranked models)
- claude-haiku-4.5: answered 0
  explanation: Arizona does not offer refundable individual income tax credits to taxpayers. The household has Social Security retirement income, taxable pension income, and dividend/capital gains income, but Arizona's tax code does not provide refundable credits at the state level for individual income tax purposes. value = 0
- claude-opus-4.7: answered 0
  explanation: Arizona's main refundable credits (e.g., Family Income Tax Credit, Property Tax Credit) require either dependents, rent paid, or property tax paid—none reported here. Head has no qualifying expenses for other refundable AZ credits. value = 0
- claude-opus-4.8: answered 0
  explanation: Arizona refundable individual income tax credits (e.g., the increased excise tax credit, family income tax credit, property tax credit) require either low income or qualifying property tax/rent payments. This head has Social Security ($23,736, largely non-taxable in AZ), pension income ($6,720), and minor investment income, with no qualifying rent or property tax facts and no dependents. AZ taxable income is very low and no refundable credit conditions are met. value = 0
- claude-opus-5: answered 0
  explanation: Arizona refundable credits (e.g., family income tax credit / increased excise tax credit) yield no amount for a single filer with no dependents and no tax liability under PolicyEngine. value = 0
- claude-sonnet-5: answered 0
  explanation: Arizona does not offer a refundable state individual income tax credit applicable to this household's circumstances (no dependents, no qualifying refundable credit triggers such as the AZ family income tax credit threshold being met with a refundable component); Arizona's credits (e.g., property tax credit) are nonrefundable or require different qualifying conditions not met here. value = 0
- claude-sonnet-5.5: answered 0
  explanation: No AZ refundable credit applies. No rent or property tax is listed for the property tax credit, and there are no dependents for the family credit. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: No qualifying refundable Arizona credits apply given zero state tax liability and no dependents. value = 0
- deepseek-v4-pro: answered 0
  explanation: Head has no dependents or other qualifications for Arizona refundable credits, so $0. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: No Arizona refundable tax credit applies because there are no dependents, donations, or qualifying property tax or rent facts in the household. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: No earned income, so Arizona refundable credits such as the EITC are 0. value = 0
- gemini-3-flash-preview: answered 0
  explanation: The household does not qualify for any refundable state tax credits in Arizona based on the provided facts. value = 0.0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household has no state-specific refundable tax credits. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: The household does not qualify for any state refundable credits. value = 0
- gemini-3.5-flash: answered 0
  explanation: The household does not qualify for any refundable state income tax credits in Arizona. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: Arizona has no major refundable individual income tax credits for which the head qualifies, and state refundable credits are zero. value = 0
- gemini-3.6-flash: answered 0
  explanation: The household income exceeds limits for Arizona refundable tax credits, resulting in $0. value = 0
- glm-5.2: answered 0
  explanation: Arizona has no refundable state individual income tax credits available to this household based on the provided facts. state_refundable_credits = 0. value = 0
- glm-5.3: answered 0
  explanation: No refundable state credits apply in Arizona for this household value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable Arizona income tax credits are triggered by the facts provided. value = 0
- gpt-5.4-nano: answered 0
  explanation: No qualifying state refundable credits are indicated by the provided facts (no additional inputs suggesting eligibility such as qualifying dependents/earned income beyond what is given); value = 0.
- gpt-5.6-luna: answered 0
  explanation: No qualifying Arizona refundable individual income-tax credit is supported by the reported household facts. value = 0
- gpt-5.6-sol: answered 0
  explanation: No Arizona refundable credit is supported because no qualifying property tax, rent, dependents, or other credit-generating facts are listed. value = 0
- gpt-5.6-terra: answered 0
  explanation: No Arizona refundable credit eligibility is indicated for this one-person elderly household. value = 0
- gpt-6-luna: answered 0
  explanation: No refundable Arizona individual income tax credit is supported by the reported household facts. value = 0
- gpt-6-sol: answered 0
  explanation: No qualifying earnings, dependents, or expenses establish a refundable Arizona income tax credit; value = 0
- grok-4.3: answered 0
  explanation: No eligibility for Arizona refundable credits like the Working Poor Tax Credit due to income sources. value = 0.0
- grok-4.5: answered 0
  explanation: No property taxes or other qualifying expenses are listed so Arizona refundable credits including the property-tax credit equal zero. value = 0
- grok-build-0.1: answered 0
  explanation: No state refundable credits are applicable given the household composition and income level. value = 0
- inkling: answered 0
  explanation: No Arizona refundable credits apply to this household with zero taxable income and no qualifying dependents or program take-up listed. value = 0
- kimi-k2.6: answered 0
  explanation: The household has no earned income and no unlisted payments or qualifying expenses that would generate Arizona refundable credits such as a refundable EITC or property tax credits. Therefore total refundable state credits equal zero. value = 0
- kimi-k3: answered 0
  explanation: Household income is $30,544, above Arizona's $25,000 limit for a single filer's refundable increased excise tax credit. No property-tax-credit expense is listed and no other Arizona refundable credit applies; value = 0
- minimax-m3: answered 0
  explanation: No dependents and no qualifying refundable AZ credits apply; state refundable credits = value = 0.
- ox-alpha: answered 0
  explanation: Household income of about $30,544 vastly exceeds the income limits for Arizona's refundable property tax refund/credit (roughly $4,000 for a single senior), so no refundable state credits apply. value = 0
- qwen-3.7-max: answered 0
  explanation: The household has no qualifying children (head is age 80 with no other household members listed), no earned income from wages or self-employment, and no other listed facts that would qualify for Arizona refundable tax credits such as the Arizona Earned Income Tax Credit or family tax credit. With no qualifying income or dependents, no refundable credits apply. value = 0
- qwen3.8-max: answered 0
  explanation: No Arizona refundable credits are indicated by the household facts, and there is no Arizona tax liability to offset. value = 0