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
STATE: ID
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: ID
- tax year: 2026

Head:
- age: 25
- gross wages and salaries: $66,969
- bank account assets: $3,660
- employer sponsored insurance premiums: $3,389
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $5,000
- hourly wage: $32
- usual weekly hours worked: 40
- is paid hourly
- other health insurance premiums: $5,000
- other medical expenses: $400
- over-the-counter health expenses: $150
- pre-subsidy rent: $37,200

Household inputs:
- auto loan balance: $19,000
- auto loan interest: $950
- household vehicles value: $7,410

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

ENGINE REFERENCE VALUE: $155.00
MODELS: 45 gave a usable answer; 7 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 20 models (0 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Idaho's main refundable credit is the grocery credit, but PolicyEngine models Idaho's grocery credit as nonrefundable/other credit treatment; the single filer with $66,969 wages has no children and exceeds income limits for any refundable state credits, so total refundable Idaho income tax credits are 0. value = 0
- claude-haiku-4.5: answered 0
  explanation: Idaho does not have a state earned income tax credit (EITC) or other refundable state income tax credits for 2026. The household head is a single taxpayer age 25 with gross wages of $66,969, placing them above any potential income thresholds for credits. Idaho's tax system does not provide refundable credits for this income level and filing status. value = 0
- claude-opus-4.7: answered 0
  explanation: Idaho's main refundable individual income tax credit is the Grocery Credit (typically $120/person), but it is generally claimed as a nonrefundable credit against tax with any excess refundable only for full-year residents who file specifically for it. However, single filer with $66,969 wages has Idaho tax liability well exceeding the grocery credit, so it offsets tax rather than being refunded. No other Idaho refundable credits apply (no dependents for CTC, no qualifying child care, etc.). value = 0
- claude-opus-4.8: answered 0
  explanation: Idaho has a grocery credit, but for a single filer with ~$67k wages and no dependents, the grocery credit ($120) is nonrefundable in effect via the income tax return offset; with no other refundable state credits applicable to this household, total refundable state credits = 0. value = 0
- claude-opus-5: answered 0
  explanation: Idaho grocery credit is the main credit and is applied against liability; no refundable state credits remain at this income. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Idaho does not have any refundable individual income tax credits for tax year 2026. Idaho's tax credits (such as the grocery credit) are nonrefundable. The household has no qualifying basis for any refundable state credit in Idaho. value = 0
- claude-sonnet-5: answered 0
  explanation: Idaho does not offer a refundable state individual income tax credit applicable to this household's situation (e.g., no grocery credit refund beyond offset, no EITC state supplement). Given the head's income level and lack of qualifying dependents, there are no refundable state credits owed. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: The Idaho refundable grocery credit is fully phased out at this AGI of $66,969. value = 0
- deepseek-v4-pro: answered 0
  explanation: No refundable Idaho credits apply (e.g., grocery credit has income limit). value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: No state refundable credits apply for this household profile. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: No state refundable credits apply. value = 0
- glm-5.2: answered 0
  explanation: Idaho does not provide refundable individual income tax credits for this household. No listed facts establish eligibility for any refundable Idaho tax credit, and Idaho's grocery credit is a nonrefundable credit. Therefore total refundable state income tax credits are 0.0. value = 0.0
- gpt-5.4-mini: answered 0
  explanation: No refundable Idaho income tax credits are indicated by the household facts, so the amount is zero. value = 0
- gpt-5.4-nano: answered 0
  explanation: No state refundable credits (e.g., refundable child-related credits) were indicated in the household facts, so refundable state credits estimated as 0 = value = 0
- gpt-5.6-luna: answered 0
  explanation: Income is too high for an Idaho grocery or other refundable individual income tax credit under the stated facts. value = 0
- grok-4.3: answered 0
  explanation: No state refundable credits apply. value = 0
- grok-build-0.1: answered 0
  explanation: No state refundable credits apply based on household facts. value = 0
- minimax-m3: answered 0
  explanation: No Idaho refundable credits apply based on listed facts (no children, no property tax credit eligibility without rent info beyond pre-subsidy). value = 0
- qwen-3.7-max: answered 0
  explanation: Idaho does not have a state Earned Income Tax Credit or Child Tax Credit. No refundable credits apply to this household based on the listed facts (no children, no other credit-qualifying conditions). value = 0
- qwen3.8-max: answered 0
  explanation: Idaho does not provide a state refundable income tax credit for this household based on the listed facts. value = 0