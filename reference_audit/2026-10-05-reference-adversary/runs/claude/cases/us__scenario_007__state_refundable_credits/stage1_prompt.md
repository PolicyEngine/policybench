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
- age: 56
- bank account assets: $71,500
- employer sponsored insurance premiums: $6,309
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $2,080
- usual weekly hours worked: 50
- other health insurance premiums: $2,080
- other medical expenses: $150
- pre-subsidy rent: $18,353
- Social Security disability income: $19,285
- tax exempt private pension income: $284
- taxable private pension income: $35,280

Household inputs:
- household vehicles value: $2,660

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
MODELS: 45 gave a usable answer; 10 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 17 models (0 of them among the benchmark's top-ranked models)
- claude-haiku-4.5: answered 0
  explanation: Idaho does not have refundable state individual income tax credits. The state offers various tax credits such as the dependent exemption credit, residential energy credit, and others, but none are refundable credits that would result in a payment to the taxpayer when the credit exceeds tax liability. This household's Idaho state income tax credits, if any apply, would be non-refundable. value = 0
- claude-opus-4.8: answered 0
  explanation: Idaho's main refundable credit is the Grocery Credit, but it is nonrefundable when claimed on the income tax return (refundable only via separate filing) and Idaho has no other refundable individual income tax credits applicable here. This household has no qualifying children or other refundable Idaho credits, so total refundable state credits are zero. value = 0
- claude-opus-5: answered 0
  explanation: Idaho grocery credit is a refundable-style credit but is handled as a nonrefundable/other item, and no refundable Idaho credits apply to this single filer with no children; treating refundable state credits as zero. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Idaho's refundable state individual income tax credits for tax year 2026 include the Idaho Child Tax Credit and the Grocery Credit. The head is age 56 with no dependents listed, so no Child Tax Credit applies. The Idaho Grocery Credit is a refundable credit available to Idaho residents; however, the head receives Social Security disability income of $19,285. The Grocery Credit is available to residents who are not claimed as dependents, but the credit for those receiving Social Security is embedded in the credit structure. For 2026, Idaho's Grocery Credit is $120 per person (approximately). However, reviewing Idaho law: the Grocery Credit is $120 per exemption for taxpayers who do not receive Social Security benefits, and for those who DO receive Social Security, the credit is instead claimed against the Social Security income offset. Actually, under Idaho code, taxpayers who receive Social Security benefits receive the Grocery Credit as a refundable credit of $120. The head receives SSDI of $19,285, qualifying them for the Idaho Grocery Credit. For 2026, the Idaho Grocery Credit is $120 per person (the head, 1 person). There are no dependents. The credit amount is $120. However, since the head has SSDI income, they are entitled to the refundable grocery credit of $120. But Idaho's grocery credit for those on Social Security is refundable only if they have no tax liability, and it phases: for 2026, the credit is $120. With taxable private pension income of $35,280 and SSDI (which Idaho partially taxes), there will be tax liability, so the grocery credit of $120 offsets tax but may not be refundable beyond liability. Idaho's grocery credit is nonrefundable for those with tax liability. Given the head has substantial pension income ($35,280 taxable), Idaho taxable income will exceed zero and the grocery credit ($120) will be fully used as a nonrefundable credit against tax liability, yielding $0 in refundable state credits. value = 0
- claude-sonnet-5: answered 0
  explanation: Idaho does not offer a refundable state individual income tax credit that this household qualifies for (Idaho's state credits, such as the grocery credit, are nonrefundable against tax liability in this modeling, and no other refundable credits apply). value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Idaho's refundable grocery credit phases out entirely at this income level (single filer income far above the ~$22,500 phaseout threshold), so the refundable credit is $0. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household does not qualify for refundable state income tax credits in Idaho. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: State refundable credits are $0. value = 0
- glm-5.2: answered 0
  explanation: The household has $0 Idaho state income tax liability and no qualifying children for the Idaho Child Tax Credit. Idaho's grocery credit has been repealed, and no other refundable state individual income tax credits apply. value = 0
- gpt-5.4-mini: answered 0
  explanation: No Idaho refundable income tax credits are indicated for this household, value = 0
- gpt-5.4-nano: answered 0
  explanation: No qualifying conditions for refundable state credits are provided in the household facts, so refundable state credits are 0; value = 0
- gpt-5.6-terra: answered 0
  explanation: No refundable Idaho credit applies; income is above the phaseout for the Idaho grocery credit. value = 0
- grok-4.3: answered 0
  explanation: Idaho provides no refundable credits applicable to this household. value = 0.0
- grok-build-0.1: answered 0
  explanation: No state refundable income tax credits apply based on the given household facts and composition. value = 0
- minimax-m3: answered 0
  explanation: No state income tax in Idaho, no refundable state credits. value = 0
- qwen-3.7-max: answered 0
  explanation: Idaho does not have significant refundable income tax credits applicable to this household's situation, so state refundable credits total $0. value = 0
- qwen3.8-max: answered 0
  explanation: No Idaho refundable credits apply to this household based on the listed facts. value = 0.0