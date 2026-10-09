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
STATE: TX
OUTPUT: federal_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable federal income tax credits, including EITC and refundable portions of credits such as refundable CTC when applicable; exclude the ACA Premium Tax Credit

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only federal_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: TX
- tax year: 2026

Head:
- age: 31
- gross wages and salaries: $5,923
- bank account assets: $10
- employer sponsored insurance premiums: $8,389
- farm rent income: $1,920
- financial assistance: $13,000
- has employer-sponsored insurance
- long-term capital gains: $-9,944
- over-the-counter health expenses: $1
- unadjusted basis of qualified property: $54,381

Household inputs:
- household vehicles value: $11,838

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

ENGINE REFERENCE VALUE: $453.10 (engine output 453.0960083007813)
MODELS: 46 gave a usable answer; 25 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 15 models (0 of them among the benchmark's top-ranked models)
- claude-haiku-4.5: answered 0
  explanation: The household has gross wages of $5,923 and farm rent income of $1,920, totaling $7,843 in gross income before adjustments. With employer-sponsored insurance premiums of $8,389 and a long-term capital loss of $9,944, the household has a net loss position. After applying the capital loss limitation and standard deduction, the household's taxable income is negative, resulting in no federal income tax liability. With no tax liability and income below EITC and Child Tax Credit thresholds (no children or dependents are listed), no refundable federal credits are available. value = 0
- claude-opus-4.8: answered 0
  explanation: Head is single, age 31, no qualifying children, so no refundable CTC. EITC for childless workers requires the worker not be a dependent; earned income is $5,923 wages. However, the long-term capital loss (-$9,944) plus farm rent ($1,920) and wages results in very low/negative AGI. Investment income is not over the limit. For a childless worker, EITC phases in then out; but with negative net income overall and capital losses, refundable credits compute to essentially zero given the income mix. No qualifying children means no refundable CTC. value = 0
- claude-sonnet-5: answered 0
  explanation: Head has no qualifying children, is 31 years old, and has net self-employment/farm income plus a capital loss resulting in low earned income (~$7,843 wages+farm rent). EITC for a childless filer phases in but at this income level (~$7,843) with no children, the EITC amount would be around $600-700, however the large capital loss (-$9,944) reduces AGI below zero, and investment income limits/disqualification factors combined with the very small earned income base make the credit effectively negligible. No qualifying children means no refundable CTC. Given the complexity and offsetting factors, estimated refundable credit rounds to $0. value = 0
- deepseek-v4-pro: answered 0
  explanation: No qualifying children for the Child Tax Credit, and earned income is effectively zero because employer-sponsored insurance premiums ($8,389) exceed wages ($5,923), reducing earned income to $0 for EITC purposes. Thus, EITC is $0 and total refundable credits are $0. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household does not meet the earned income threshold or eligibility requirements for EITC or refundable CTC given the income levels. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: With pre-tax employer-sponsored insurance premiums fully offsetting gross wages, the household has zero earned income for the Earned Income Tax Credit and has no qualifying children for other credits. value = 0
- gemini-3.5-flash: answered 0
  explanation: The head has $0 in earned income after deducting pre-tax health insurance premiums from gross wages, making them ineligible for the Earned Income Tax Credit (EITC). There are no qualifying children for the Child Tax Credit. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: Federal refundable credits are 0 for the head in tax year 2026. value = 0
- gemini-3.7-flash: answered 0
  explanation: The household has no qualifying children and zero taxable earned income after pre-tax health deductions, resulting in $0 in refundable tax credits. value = 0
- glm-5.3: answered 0
  explanation: The head has no qualifying children, so the only possible refundable credit is the childless EITC. Earned income is $5,923, giving a phase-in credit of about 7.65% x $5,923 = $453, but the higher of earned income and modified AGI ($17,843) is well into the childless EITC phase-out range, reducing the credit to zero. No other refundable credits apply. value = 0
- gpt-5.4-mini: answered 0
  explanation: With no qualifying dependent children and no refundable federal credit indicated by the provided facts, refundable federal credits are zero. value = 0
- gpt-5.4-nano: answered 0
  explanation: No refundable federal credits (EITC/ACTC/other refundable credits) are specified or inferable from the provided facts (no children, no ACA premium tax credit); thus refundable federal income tax credits are $0. value = 0
- grok-4.3: answered 0
  explanation: No qualifying children or earned income sufficient for EITC or other refundable credits. value = 0
- minimax-m3: answered 0
  explanation: With very low income (MAGI approximately $5,923-$8,389 for ACA), EITC for a household with no qualifying children at this income is minimal or zero, and refundable CTC requires children. Head is single (no spouse) with no children listed, so refundable credits are negligible. Total federal refundable credits = value = 0.
- qwen3.8-max: answered 0
  explanation: No refundable federal credits apply under these household facts. value = 0