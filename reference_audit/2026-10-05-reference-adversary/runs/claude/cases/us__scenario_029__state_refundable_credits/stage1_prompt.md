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
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
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

ENGINE REFERENCE VALUE: $40.00
MODELS: 46 gave a usable answer; 2 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 44 models (5 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Oklahoma refundable credits include the sales tax relief credit ($40/exemption for filers with gross income under $20,000, or $50,000 with dependents/elderly/disabled) and the refundable EITC. The head's income is only $312 taxable interest, but the $50,000 financial assistance counts toward the gross household income test for the sales tax relief credit, exceeding the $20,000 limit for a single filer with no dependents, so no sales tax credit. With no earned income, the OK EITC (5% of federal EITC) is $0. Thus total refundable OK credits are $0. value = 0
- claude-haiku-4.5: answered 0
  explanation: Oklahoma does not have state refundable income tax credits for individual filers. The household has income from taxable interest ($312) and financial assistance that would not qualify for typical refundable credits. Oklahoma offers limited tax credits, and none are structured as refundable credits for general income. value = 0
- claude-opus-4.7: answered 0
  explanation: Oklahoma refundable credits include the Sales Tax Relief Credit and refundable EITC. The Sales Tax Relief Credit requires income below ~$20,000 (or higher with dependents/disability). Head has only $312 interest income, but also has $50,000 financial assistance and substantial assets ($50,735 stock + $4,250 bank). With no earned income, no EITC applies. The $50,000 financial assistance likely counts as income disqualifying Sales Tax Relief Credit (threshold $20,000 single). No other refundable OK credits apply. value = 0
- claude-opus-4.8: answered 0
  explanation: Oklahoma refundable credits (sales tax relief credit, EITC) require qualifying conditions. The single 21-year-old head has only $312 taxable interest income and no earned income, so no state EITC applies. The sales tax relief credit requires meeting income thresholds and is generally tied to filing; with no earned income and substantial assets/financial assistance, no refundable state credits accrue. value = 0
- claude-opus-5: answered 0
  explanation: No earned income or qualifying dependents for Oklahoma refundable credits (EITC, sales tax relief thresholds not met with take-up modeled as zero). value = 0
- claude-opus-5.5: answered 0
  explanation: There is no earned income or dependents to generate Oklahoma refundable credits. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Oklahoma has a limited set of refundable state income tax credits. For tax year 2026, the primary refundable credits available in Oklahoma include the Earned Income Credit (a percentage of the federal EITC) and certain other credits. The head is a single filer, age 21, with no wages or self-employment income listed (only taxable interest income of $312 and financial assistance of $50,000, which is treated as a non-taxable scholarship/grant for tax purposes). Without earned income (wages or self-employment), the taxpayer does not qualify for the Oklahoma Earned Income Credit. No other refundable Oklahoma state credits appear applicable given the listed household facts (no childcare expenses, no child tax credit base, etc.). Therefore, total refundable state individual income tax credits = $0. value = 0
- claude-sonnet-5: answered 0
  explanation: Oklahoma does not offer a refundable state earned income credit (OK's EITC is nonrefundable) or other general refundable individual income tax credit that this household would qualify for based on the facts given (single 21-year-old with no earned income, no dependents, no disability/elderly credit qualification). No refundable state credit amount applies, so value = 0.
- claude-sonnet-5.5: answered 0
  explanation: No refundable Oklahoma credits apply at this income level. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: No Oklahoma refundable income tax credits apply given zero tax and no qualifying conditions. value = 0
- deepseek-v4-pro: answered 0
  explanation: Oklahoma's refundable EITC is 5% of the federal EITC, which is $0 because head has no earned income. No other state refundable credits apply. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Oklahoma's refundable credits are not triggered here, including its EITC based on the $0 federal EITC, so total state refundable credits are $0. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: No earned income and no federal EITC, so Oklahoma refundable credits are $0. value = 0
- gemini-3-flash-preview: answered 0
  explanation: The household's total gross income of $50,312 (including $50,000 in financial assistance) exceeds the $20,000 income limit for the Oklahoma Sales Tax Relief Credit, and no other refundable state credits apply. value = 0.0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: No state-level refundable tax credits apply for this household. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: Oklahoma's Sales Tax Relief Credit considers total income including financial assistance. Because total income exceeds the $20,000 threshold for single filers, the credit is $0. value = 0
- gemini-3.5-flash: answered 0
  explanation: The household does not qualify for any state refundable credits in Oklahoma. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: The state refundable credits are $0.00. value = 0
- gemini-3.6-flash: answered 0
  explanation: The head does not meet the eligibility requirements for the Oklahoma Sales Tax Relief Credit because they are under age 65, not disabled, and have no dependents. value = 0
- gemini-3.7-flash: answered 0
  explanation: The household does not qualify for any refundable Oklahoma state tax credits. value = 0
- gemini-3.8-flash: answered 0
  explanation: The household qualifies for no refundable Oklahoma tax credits (such as OK EITC, since federal EITC is $0). value = 0
- glm-5.2: answered 0
  explanation: Oklahoma does not offer any refundable state individual income tax credits for this household. value = 0
- glm-5.3: answered 0
  explanation: No refundable OK credits. value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable Oklahoma income tax credits are supported by the provided household facts; value = 0
- gpt-5.4-nano: answered 0
  explanation: No information is provided indicating eligibility for refundable state income tax credits, so refundable state credits are estimated at zero; value = 0
- gpt-5.5: answered 0
  explanation: No facts indicate eligibility for an Oklahoma refundable individual income tax credit; with no qualifying earned income or other listed refundable-credit basis, refundable state credits are zero. value = 0
- gpt-5.6-luna: answered 0
  explanation: No Oklahoma refundable income-tax credit is available because there is no qualifying earned income or stated qualifying dependent. value = 0
- gpt-5.6-sol: answered 0
  explanation: With no earned income, dependents, or other facts supporting an Oklahoma refundable credit, no refundable state credit applies. value = 0
- gpt-5.6-terra: answered 0
  explanation: No listed facts establish eligibility for an Oklahoma refundable income-tax credit. value = 0
- gpt-6-astra: answered 0
  explanation: There is no earned income for Oklahoma's EITC, and household income including financial assistance exceeds the sales-tax-relief income limit; value = 0
- gpt-6-luna: answered 0
  explanation: No refundable Oklahoma individual income tax credit applies to this single adult with no qualifying children or earned income. value = 0
- gpt-6-sol: answered 0
  explanation: No earnings, qualifying children, or other facts establish eligibility for an Oklahoma refundable income tax credit. value = 0
- grok-4.3: answered 0
  explanation: No Oklahoma refundable credits qualify without earned income, dependents, or specific expenses not listed. value = 0.0
- grok-4.5: answered 0
  explanation: No qualifying children or other basis for Oklahoma refundable credits with this income and composition. value = 0
- grok-4.6: answered 0
  explanation: No Oklahoma refundable credits apply: no children or earned income, and $50,000 financial assistance plus investment assets put the household over sales-tax relief income rules. value = 0
- grok-4.7: answered 0
  explanation: No Oklahoma refundable income tax credit applies. Gross household resources, including $50,000 of financial assistance, exceed sales-tax relief limits, and there is no state EITC. value = 0
- grok-build-0.1: answered 0
  explanation: No refundable state income tax credits apply to this household. value = 0
- inkling: answered 0
  explanation: No qualifying dependents, no earned income for state EITC, and income/assets do not produce a refundable Oklahoma low-income credit in this case. value = 0
- kimi-k2.6: answered 0
  explanation: The taxpayer has zero Oklahoma income tax liability and no earned income, is under age 65 with no disability or dependents indicated (unlisted statuses default to false), and does not meet the qualifying conditions for Oklahoma refundable credits such as the Sales Tax Relief Credit or earned-income-based credits. Thus total refundable state credits equal zero. value = 0
- kimi-k3: answered 0
  explanation: No Oklahoma refundable income-tax credit applies: there is no earned income for a refundable earned-income credit, and the $50000 financial assistance puts gross household income over the sales-tax-relief limit for an under-65 household with no dependents or disability. value = 0
- minimax-m3: answered 0
  explanation: Oklahoma has no state income tax, so no refundable state credits apply. value = 0
- ox-alpha: answered 0
  explanation: Oklahoma refundable credits (Earned Income Credit at 5% of federal EITC and Sales Tax Relief Credit) require earned income/eligibility the household lacks, so refundable state credits total $0. value = 0
- qwen-3.7-max: answered 0
  explanation: The household has no earned income, no qualifying children, and no other listed characteristics that would qualify for Oklahoma refundable tax credits such as the state Earned Income Tax Credit or child-related credits. value = 0.0
- qwen3.8-max: answered 0
  explanation: No refundable Oklahoma income tax credits are indicated by the household facts. value = 0