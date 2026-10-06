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
STATE: NY
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: NY
- tax year: 2026

Head:
- age: 74
- bank account assets: $70
- home mortgage interest: $5,551
- is blind
- is disabled
- is a surviving spouse
- other medical expenses: $29
- real estate taxes: $1,634
- Social Security retirement income: $2,800
- unreimbursed employee business expenses: $122

Tax unit:
- first home mortgage balance: $82,237
- first home mortgage interest: $5,551

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

ENGINE REFERENCE VALUE: $375.00
MODELS: 46 gave a usable answer; 12 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 24 models (0 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Head is a 74-year-old surviving spouse in NY with only $2,800 Social Security income (fully exempt) and no earned income, children, dependents, or child care expenses, so no EITC, Empire State child credit, or child/dependent care credit apply. NY AGI is $0 and NY tax liability is $0; the household has no rent and homeowners with these facts do not qualify for a real property tax circuit breaker credit payment here, yielding no refundable NY credits. value = 0
- claude-haiku-4.5: answered 0
  explanation: New York State does not offer a general refundable individual income tax credit. While New York has various tax credits (such as the Empire State Earned Income Tax Credit for certain lower-income working families), this household's income sources consist only of Social Security retirement income ($2,800) with minor business expenses. Social Security income is not subject to New York State income tax, and no refundable credits apply to this household's tax situation. value = 0
- claude-opus-4.8: answered 0
  explanation: Head has only $2,800 Social Security retirement income, which is exempt from NY taxable income, resulting in no taxable income and no liability against which NY refundable credits (e.g., real property tax credit, EITC) would generate a refund; with no qualifying earned income or refundable credit conditions met, total state refundable credits = 0. value = 0
- claude-opus-5: answered 0
  explanation: NY refundable credits (e.g., real property tax credit) require qualifying gross income/rent-tax conditions; with $0 taxable NY income and no reported rent, PolicyEngine yields no refundable credit amount. value = 0
- claude-sonnet-5: answered 0
  explanation: This household's only income is $2,800 in Social Security retirement benefits, which is not taxable and produces no NY tax liability. New York's main refundable credits (Earned Income Credit, Empire State Child Credit) require earned income or qualifying children, neither of which apply here (single elderly head with no earned income, no dependents). The NY real property tax credit / circuit breaker for seniors is very small and generally phases out or is negligible given the low household size and no rent paid, and with mortgage interest itemization there is no indication of qualifying rent paid. Given no earned income, no children, and no rent, there are no refundable state credits generated, so total state refundable credits = value = 0.
- deepseek-v4-flash-0731: answered 0
  explanation: No state refundable credits apply given the zero state tax liability and no qualifying credits. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household does not meet the eligibility requirements for NY state refundable tax credits. value = 0
- gemini-3.5-flash: answered 0
  explanation: The household does not qualify for any state refundable credits such as the Empire State Child Credit or state EITC due to a lack of earned income and dependents. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: The head qualifies for no state refundable tax credits, resulting in $0. value = 0
- gemini-3.6-flash: answered 0
  explanation: The household does not qualify for any refundable New York state income tax credits. value = 0
- gemini-3.7-flash: answered 0
  explanation: With no earned income or qualifying dependents, the household qualifies for $0 in state refundable credits. value = 0
- gemini-3.8-flash: answered 0
  explanation: The household does not qualify for the Empire State Child Credit, NY EITC, or other state refundable credits. value = 0
- glm-5.3: answered 0
  explanation: No NY refundable credits apply (e.g., NY EITC requires earned income, which is $0). value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable New York income tax credits are triggered by the listed facts. value = 0
- gpt-5.4-nano: answered 0
  explanation: No refundable New York income tax credits (e.g., refundable portion of certain credits) are indicated by the provided facts, so total state refundable credits are 0. value = 0
- gpt-5.6-luna: answered 0
  explanation: No New York refundable income-tax credit is generated by the reported Social Security-only income and household facts; value = 0
- grok-4.3: answered 0
  explanation: No qualifying credits for NY state refundable amounts. value = 0
- grok-build-0.1: answered 0
  explanation: NY's main refundable credit is the EITC, which is a percentage of the federal EITC ($0 here). No qualifying children for other credits like Empire State Child Credit. value = 0
- inkling: answered 0
  explanation: No applicable NY refundable credits (e.g., EITC, child/dependent credits, or property tax credits that apply here) are present for this household. value = 0
- kimi-k2.6: answered 0
  explanation: The household has no listed children or qualifying dependents, no listed earned income, no listed college tuition expenses, no listed childcare expenses, and no indicators for any other NY refundable credits (e.g., EITC requires earned income; Empire State Child Credit requires qualifying child; college tuition credit requires tuition payments). Therefore, total refundable state individual income tax credits are zero. value = 0
- minimax-m3: answered 0
  explanation: No NY state refundable credits apply because there is no NY tax liability and no qualifying children or other conditions triggering credits. value = 0
- ox-alpha: answered 0
  explanation: NY refundable credits such as the NY EITC (requires federal EITC/earned income) or refundable CDCC (requires child care expenses and earnings) do not apply with $0 earned income and no dependents. value = 0
- qwen-3.7-max: answered 0
  explanation: With no NY taxable income and no listed eligibility factors for refundable credits (e.g., no earned income for EITC, no qualifying children for child credits), no NY refundable credits apply. value = 0
- qwen3.8-max: answered 0
  explanation: No New York refundable credit applies given the household's income, age, and absence of qualifying dependents or earned income. value = 0