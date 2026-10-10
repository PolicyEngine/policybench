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
- age: 23
- gross wages and salaries: $100,195
- bank account assets: $127,030
- charitable cash donations: $700
- employer sponsored insurance premiums: $21,208
- has employer-sponsored insurance
- hourly wage: $50
- usual weekly hours worked: 35
- long-term capital gains: $-33,000
- non-qualified dividend income: $7,056
- other medical expenses: $666
- over-the-counter health expenses: $300
- qualified dividend income: $13,424
- real estate taxes: $9,217
- roth 401k contributions desired: $32
- roth ira contributions desired: $13
- state and local tax refund income: $68
- short-term capital gains: $2,289
- stock assets: $564,000
- taxable interest income: $100
- traditional 401k contributions desired: $181
- traditional ira contributions desired: $8

Child 1:
- age: 1
- has employer-sponsored insurance
- other medical expenses: $666
- over-the-counter health expenses: $333

Benefit inputs:
- pre-subsidy childcare expenses: $9,600

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
- child1_wic_eligible: whether Child 1 is eligible for WIC (1 if yes, 0 if no)
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_medicaid_eligible: whether Child 1 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_chip_eligible: whether Child 1 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- child1_medicare_eligible: whether Child 1 is eligible for Medicare (1 if yes, 0 if no)
- free_school_meals_eligible: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)
- reduced_price_school_meals_eligible: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)
- child1_head_start_eligible: whether Child 1 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child1_early_head_start_eligible: whether Child 1 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)

Use the `submit_outputs` function exactly once. Return an `outputs` object with every requested quantity keyed by variable name. Each requested key must map to an object with a numeric `value` and a non-empty, specific, concise `explanation`. Each explanation must support the numeric value submitted for the same variable in `outputs`. If an explanation mentions a final amount, that amount must match the corresponding `outputs` value. Do not write that you will use one value while submitting a different value. Do not include scratch work, abandoned calculations, or corrections. End each explanation with `value = X`, where X exactly matches the numeric `value` field. For 1/0 eligibility outputs, submit 1 only when the explanation says eligible or yes, and submit 0 only when it says not eligible or no. Use the exact variable names as keys inside `outputs`. Include every requested key exactly once in `outputs`, even if the value is 0. Put only numeric values in `value`, with no dollar signs, commas, or explanatory text. Do not rely on plain text for the final answers. If an answer is a currency amount, give the annual amount. If an answer is a rate, give a decimal (e.g. 0.25 for 25%).
----- END HOUSEHOLD PROMPT -----

ENGINE REFERENCE VALUE: $667.00
MODELS: 44 gave a usable answer; 0 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 18 models (1 of them among the benchmark's top-ranked models)
- claude-haiku-4.5: answered 0
  explanation: New York does not have a state-level refundable earned income credit or child tax credit equivalent to federal refundable credits. The household's income level ($100,195 in wages plus investment income) exceeds New York's dependent exemption and child-dependent credit income thresholds, and the head is age 23 without qualifying for the property tax circuit breaker or other state refundable credits based on the provided facts. value = 0
- claude-opus-4.8: answered 0
  explanation: NY refundable credits (EITC, Empire State Child Credit, Child and Dependent Care Credit) phase out at this income level. With gross wages of ~$100,195 plus substantial investment income (dividends ~$20,480, interest, capital gains), the household far exceeds NY EITC income limits and has disqualifying investment income. The Empire State Child Credit phases out for high-income filers, and the dependent care credit is non-refundable for higher AGI. No refundable state credits apply. value = 0
- claude-opus-5: answered 0
  explanation: Income too high for NY EITC, Empire State Child Credit, or NY child care credit refunds at this income level. value = 0
- claude-sonnet-5: answered 0
  explanation: NY has a household income around $92k AGI (wages $100,195 minus 401k/IRA deferrals, plus investment income) with a young child, but NY's refundable credits (Empire State Child Credit, NYC school tax credit, EITC) phase out or require income below thresholds not met here. Given the high wage income (~$100k) and net capital gains loss offsetting only $3k, the household's NY AGI is too high to qualify for the state's refundable Empire State Child Credit or NY EITC, and no other refundable state credits apply. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: NY EITC equals 30% of the federal EITC, which is $0 at this income, and there are no other applicable refundable NY credits. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: The Empire State Child Credit is not available for a child under age 4, and the NY earned income credit is zero because the federal EITC is zero, so total refundable state credits are $0. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Total refundable state individual income tax credits are 0. value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable New York income tax credits are indicated by the provided facts, so refundable state credits are zero. value = 0
- gpt-5.4-nano: answered 0
  explanation: No NY refundable credits were assumed given the high wage level and no explicit refundable-credit eligibility inputs (e.g., no NY EITC-specific qualifying pattern indicated). value = 0
- gpt-5.6-terra: answered 0
  explanation: The household's income is above eligibility for refundable New York income-tax credits, and the child is below the Empire State child-credit age range. value = 0
- gpt-6-sol: answered 0
  explanation: At this income, the household does not qualify for a refundable NY child credit or earned-income credit, and its dependent-care credit is nonrefundable; value = 0
- grok-4.3: answered 0
  explanation: No qualifying state refundable credits. value = 0
- grok-4.5: answered 0
  explanation: Empire State child credit is zero because federal CTC is fully phased out; NY EITC is zero because federal EITC is zero; no other refundable NY credits apply. value = 0
- grok-build-0.1: answered 0
  explanation: No state refundable credits such as state EITC apply as federal EITC is zero and no other qualifying credits. value = 0
- inkling: answered 0
  explanation: No state refundable credits apply; the NY child care credit is fully used against tax liability and NY EITC is $0 because federal EITC is $0. value = 0
- minimax-m3: answered 0
  explanation: With NY state tax liability near $0 before refundable credits, the Empire State Child Credit (refundable portion) may apply but the household income exceeds its range; no NY refundable credits apply. value = 0
- ox-alpha: answered 0
  explanation: The refundable NY Empire State Child Credit ($1,000 for a child under 4) is fully phased out: with a 5% reduction of NY AGI above the $75,000 threshold (HOH), the $42,662 excess eliminates the credit at ~$118k AGI, leaving $0. value = 0
- qwen-3.7-max: answered 0
  explanation: No refundable state credits are applicable. The household income exceeds limits for NY earned income credit, and no other refundable credits apply based on the listed facts. value = 0.0