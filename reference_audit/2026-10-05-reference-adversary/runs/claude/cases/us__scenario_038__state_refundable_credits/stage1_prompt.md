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
STATE: LA
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: LA
- tax year: 2026

Head:
- age: 25
- gross wages and salaries: $7,468
- bank account assets: $500
- health insurance premiums excluding Medicare Part B: $100
- other health insurance premiums: $100
- other medical expenses: $1
- over-the-counter health expenses: $1
- self-employment income: $15,525

Spouse:
- age: 18
- other medical expenses: $1
- over-the-counter health expenses: $1

Child 1:
- age: 7
- other medical expenses: $1
- over-the-counter health expenses: $1

Child 2:
- age: 6
- other medical expenses: $1
- over-the-counter health expenses: $1

Tax unit:
- first home mortgage balance: $75,000

Household inputs:
- household vehicles value: $2,090

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

ENGINE REFERENCE VALUE: $365.80 (engine output 365.8000183105469)
MODELS: 45 gave a usable answer; 10 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 18 models (0 of them among the benchmark's top-ranked models)
- claude-haiku-4.5: answered 0
  explanation: Louisiana does not offer a state refundable earned income tax credit or other major refundable tax credits for this household. The household has federal income tax liability based on wages and self-employment income, but Louisiana's individual income tax credits available to this household composition are limited to non-refundable credits (such as child and dependent care credits, if applicable), which cannot exceed the tax liability. With gross wages of $7,468 and self-employment income of $15,525 (total income $22,993), the household may have a modest Louisiana tax liability after the standard deduction, but no refundable state credits apply that would generate a payment beyond the tax owed. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Louisiana does not have a state Earned Income Tax Credit or other broadly applicable refundable individual income tax credits for tax year 2026. The household's relevant income (wages ~$7,468 + self-employment ~$15,525) may generate a Louisiana income tax liability, but Louisiana's income tax credits (such as the dependent exemption credit) are non-refundable. Louisiana eliminated its refundable EITC and has no other refundable state income tax credits applicable to this household. Therefore, total refundable state individual income tax credits = $0. value = 0
- claude-sonnet-5: answered 0
  explanation: Louisiana does not offer a refundable state EITC or other refundable individual income tax credit that this household qualifies for under current LA tax law (LA's EITC is nonrefundable), and no other refundable state credits apply given the household's facts, so total state refundable credits = 0. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Louisiana has no applicable refundable state income tax credit for this household. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: Louisiana eliminated its state EITC and has no other refundable individual income tax credits. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: There are no applicable state-level refundable credits for this household in Louisiana. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Louisiana state refundable credits are 0. value = 0
- glm-5.2: answered 0
  explanation: Louisiana's state EITC is nonrefundable, and with $0 state income tax liability there are no refundable credits applicable. No other refundable Louisiana tax credits apply to this household. value = 0
- glm-5.3: answered 0
  explanation: Louisiana has no state income tax liability and no refundable state credits apply (the LA EITC and school-readiness credits are nonrefundable or require child care expenses). value = 0
- gpt-5.4-mini: answered 0
  explanation: No Louisiana refundable individual income tax credits apply from the facts provided, so refundable state tax credits are zero. value = 0
- gpt-5.4-nano: answered 0
  explanation: No positive Louisiana refundable credits are expected at this income level in this benchmark scenario. value = 0
- gpt-5.5: answered 0
  explanation: No Louisiana refundable state income tax credits are indicated by the household facts; listed credits or qualifying refundable-credit inputs are absent, so refundable state credits are zero. value = 0
- grok-4.3: answered 0
  explanation: No LA state refundable credits triggered by listed facts. value = 0
- grok-4.5: answered 0
  explanation: Louisiana provides no refundable credits that apply to this household (no state EITC or other refundable offsets). value = 0
- grok-4.6: answered 0
  explanation: Louisiana has no refundable EITC or other refundable individual income tax credits that apply to this filing unit. value = 0
- grok-build-0.1: answered 0
  explanation: Louisiana has no refundable state income tax credits applicable to this household with no qualifying expenses or EITC match. value = 0
- ox-alpha: answered 0
  explanation: With zero Louisiana taxable income and no qualifying activities (e.g., school-readiness child care), no refundable Louisiana income tax credits apply. value = 0
- qwen3.8-max: answered 0
  explanation: Louisiana does not provide refundable individual income tax credits applicable to this household, and no state refundable credit amount is indicated by the household facts. value = 0.0