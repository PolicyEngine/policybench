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
STATE: CA
OUTPUT: free_school_meals_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only free_school_meals_eligible):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: CA
- tax year: 2026

Head:
- age: 42
- gross wages and salaries: $85,000
- employer sponsored insurance premiums: $18,708
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $2,500
- hourly wage: $42
- usual weekly hours worked: 40
- is paid hourly
- other health insurance premiums: $2,500
- other medical expenses: $2,000
- over-the-counter health expenses: $500
- roth 401k contributions desired: $272
- roth ira contributions desired: $112
- taxable interest income: $500
- traditional 401k contributions desired: $1,544
- traditional ira contributions desired: $72

Spouse:
- age: 41
- gross wages and salaries: $80,000
- bank account assets: $28,035
- charitable cash donations: $11,933
- charitable non-cash donations: $688
- educator expense: $338
- employer sponsored insurance premiums: $5,889
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $2,500
- hourly wage: $31
- usual weekly hours worked: 50
- long-term capital gains: $-7,018
- non-qualified dividend income: $16
- other health insurance premiums: $2,500
- other medical expenses: $2,000
- over-the-counter health expenses: $500
- pre-subsidy rent: $26,400
- qualified dividend income: $128
- real estate taxes: $8,654
- roth 401k contributions desired: $272
- roth ira contributions desired: $112
- short-term capital gains: $540
- stock assets: $2,230,000
- taxable interest income: $510
- traditional 401k contributions desired: $1,544
- traditional ira contributions desired: $72
- unreimbursed employee business expenses: $1,263

Child 1:
- age: 9
- has employer-sponsored insurance
- other medical expenses: $500
- over-the-counter health expenses: $200

Child 2:
- age: 4
- has employer-sponsored insurance
- other medical expenses: $500
- over-the-counter health expenses: $200

Benefit inputs:
- pre-subsidy childcare expenses: $12,740

Household inputs:
- auto loan balance: $42,000
- auto loan interest: $1,575
- household vehicles value: $21,965

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
- child1_wic_eligible: whether Child 1 is eligible for WIC (1 if yes, 0 if no)
- child2_wic_eligible: whether Child 2 is eligible for WIC (1 if yes, 0 if no)
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_medicaid_eligible: whether Spouse is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_medicaid_eligible: whether Child 1 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_medicaid_eligible: whether Child 2 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_chip_eligible: whether Spouse is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_chip_eligible: whether Child 1 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_chip_eligible: whether Child 2 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- spouse_medicare_eligible: whether Spouse is eligible for Medicare (1 if yes, 0 if no)
- child1_medicare_eligible: whether Child 1 is eligible for Medicare (1 if yes, 0 if no)
- child2_medicare_eligible: whether Child 2 is eligible for Medicare (1 if yes, 0 if no)
- free_school_meals_eligible: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)
- reduced_price_school_meals_eligible: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)
- child1_head_start_eligible: whether Child 1 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child2_head_start_eligible: whether Child 2 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child1_early_head_start_eligible: whether Child 1 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)
- child2_early_head_start_eligible: whether Child 2 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)

Use the `submit_outputs` function exactly once. Return an `outputs` object with every requested quantity keyed by variable name. Each requested key must map to an object with a numeric `value` and a non-empty, specific, concise `explanation`. Each explanation must support the numeric value submitted for the same variable in `outputs`. If an explanation mentions a final amount, that amount must match the corresponding `outputs` value. Do not write that you will use one value while submitting a different value. Do not include scratch work, abandoned calculations, or corrections. End each explanation with `value = X`, where X exactly matches the numeric `value` field. For 1/0 eligibility outputs, submit 1 only when the explanation says eligible or yes, and submit 0 only when it says not eligible or no. Use the exact variable names as keys inside `outputs`. Include every requested key exactly once in `outputs`, even if the value is 0. Put only numeric values in `value`, with no dollar signs, commas, or explanatory text. Do not rely on plain text for the final answers. If an answer is a currency amount, give the annual amount. If an answer is a rate, give a decimal (e.g. 0.25 for 25%).
----- END HOUSEHOLD PROMPT -----

ENGINE REFERENCE VALUE: 1 (eligible)
MODELS: 45 gave a usable answer; 8 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 37 models (3 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Household gross income is about $166,694 (wages $165,000 plus interest, dividends, net capital gains) for a family of 4. Free school meals require income at or below 130% of the federal poverty line (~$41,800 for 4 in 2026); this household is far above that threshold, and even the 185% reduced-price cutoff, so not eligible. value = 0
- claude-fable-5.1: answered 0
  explanation: Household income exceeds 130% FPL and no categorical eligibility; no free meals. value = 0
- claude-haiku-4.5: answered 0
  explanation: The household has two children ages 9 and 4 eligible for school meals programs. For the 2026 tax year in California, eligibility for free school meals is based on household income relative to 130% of the federal poverty line. The household has combined gross wages of $165,000 plus $1,694 in investment income (interest, dividends, and capital gains), totaling approximately $166,694 in gross income. With two school-age children, the household income substantially exceeds 130% of the federal poverty line for a household of 4, making them ineligible for free school meals. The household's significant asset holdings ($2,230,000 in stocks, $28,035 in bank accounts) further support ineligibility based on income and asset limits. value = 0
- claude-opus-4.7: answered 0
  explanation: Household income ($165,000 wages plus investment income) far exceeds the 185% FPL threshold for free school meals for a family of 4 in CA. value = 0
- claude-opus-4.8: answered 0
  explanation: Free school meals eligibility is based on household income relative to the federal poverty level (typically 130% FPL for free meals). This household has combined wages of $165,000 plus investment income, far exceeding the income threshold for a family of four. Therefore no free school meal support is provided. value = 0
- claude-opus-5: answered 0
  explanation: Household income far above 130% FPL and no categorical eligibility. value = 0
- claude-opus-5.5: answered 0
  explanation: Not eligible: income exceeds 130% FPL. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Free school meals (National School Lunch Program free meals) require household income at or below 130% of the federal poverty level. This household has combined gross wages of $165,000 plus additional investment income, far exceeding 130% FPL for a family of 4 (approximately $42,900 in 2026). The household is not eligible for free school meals. value = 0
- claude-sonnet-5: answered 0
  explanation: Household gross income is $165,000 (head $85,000 + spouse $80,000) plus investment income, for a family of 4 in CA. This far exceeds the federal free/reduced-price meal eligibility threshold (185%/130% of poverty line for a family of 4, roughly $57,720/$40,560 in 2026), so the household is not eligible for free school meals. value = 0
- claude-sonnet-5.5: answered 0
  explanation: Not eligible: income of about $165k is far above the free meal threshold of 130% of FPL. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Income far exceeds 130% FPL free-meal limit. value = 0
- deepseek-v4-pro: answered 0
  explanation: Income > 130% FPL. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Household income exceeds 130% FPL, so no free school meal support. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: Income exceeds 130% FPL for free meals. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: Household income exceeds the threshold for free school meals. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: Household income exceeds 130% of the federal poverty line, making the children ineligible for free school meals. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: Household income exceeds the threshold for free school meals. value = 0
- gemini-3.6-flash: answered 0
  explanation: Household income exceeds the eligibility threshold for free school meals. value = 0
- gemini-3.7-flash: answered 0
  explanation: Household income exceeds 130% of the federal poverty guidelines for free school meals. value = 0
- gemini-3.8-flash: answered 0
  explanation: Household income exceeds the income threshold for free school meals, value = 0
- glm-5.2: answered 0
  explanation: The household's adjusted gross income is approximately $156,588, which exceeds 130% of the federal poverty level for a household of 4. Therefore, they are not eligible for free school meals. value = 0
- glm-5.3: answered 0
  explanation: Free school meals require income at or below 130% of poverty (~$43,000 for a family of 4); this household's ~$160,000 income is far above, so no free school meal support, value = 0
- gpt-5.4-mini: answered 0
  explanation: Household income is far above free school meal eligibility thresholds, so no free meal benefit is expected. value = 0
- gpt-5.4-nano: answered 0
  explanation: Free school meal eligibility is not indicated by provided facts; with household wage income likely above thresholds, PolicyEngine returns not eligible, so free_school_meals_eligible = 0. value = 0
- gpt-5.5: answered 0
  explanation: The household’s annual income is far above the federal free school meal limit (130% of poverty) for a four-person household and no categorical eligibility is listed, so PolicyEngine would not return positive free school meal support; not eligible, value = 0
- gpt-5.6-luna: answered 0
  explanation: Household income is above the free-school-meal threshold, so PolicyEngine would not return positive free meal support; value = 0
- gpt-5.6-terra: answered 0
  explanation: Household income is far above the free school-meal income threshold. value = 0
- gpt-6-luna: answered 0
  explanation: Household income exceeds the federal free school-meal income threshold; PolicyEngine would return no positive free-meal support; value = 0
- grok-4.3: answered 0
  explanation: High income makes household ineligible for free school meals. value = 0
- grok-4.5: answered 0
  explanation: Household income far exceeds 130% FPL free-meal threshold and no categorical eligibility; PolicyEngine returns 0 free meal value; value = 0
- grok-4.7: answered 0
  explanation: Income far exceeds the 130% of poverty free-meal limit, and the household is not categorically certified through SNAP, TANF, or Medicaid. Not eligible. value = 0
- grok-build-0.1: answered 0
  explanation: The household is not eligible for free school meals because income far exceeds 130% FPL (about $43,000 for family of 4). value = 0
- kimi-k2.6: answered 0
  explanation: Household gross income from reported wages, interest, dividends, and capital gains is well above 130% of the 2026 federal poverty guideline for a four-person household, and no categorical eligibility factors such as SNAP, TANF, or foster care are present. PolicyEngine therefore returns no annual free school meal support. value = 0
- minimax-m3: answered 0
  explanation: Household income far exceeds free school meal income limits. value = 0.
- ox-alpha: answered 0
  explanation: Free meal eligibility requires income at or below 130% FPL (~$43k for a family of four); household income of about $160k far exceeds it, so PolicyEngine returns no positive free school meal support. value = 0
- qwen-3.7-max: answered 0
  explanation: The household income of approximately $165,000 in gross wages plus other income far exceeds the 130% Federal Poverty Level threshold required for free school meals eligibility for a household of 4 in California. value = 0
- qwen3.8-max: answered 0
  explanation: Household income is above the free school meal income threshold. value = 0