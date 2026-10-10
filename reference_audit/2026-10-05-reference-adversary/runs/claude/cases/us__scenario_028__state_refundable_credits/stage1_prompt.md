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
STATE: PA
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: PA
- tax year: 2026

Head:
- age: 45
- gross wages and salaries: $60,000
- bank account assets: $1,924
- child support received: $1,267
- has employer-sponsored insurance
- hourly wage: $29
- usual weekly hours worked: 40
- other medical expenses: $50
- over-the-counter health expenses: $25
- taxable interest income: $10

Child 1:
- age: 10
- has employer-sponsored insurance
- other medical expenses: $50
- over-the-counter health expenses: $15

Child 2:
- age: 10
- has employer-sponsored insurance
- other medical expenses: $50
- over-the-counter health expenses: $15

Child 3:
- age: 10
- has employer-sponsored insurance
- other medical expenses: $50
- over-the-counter health expenses: $15

Tax unit:
- first home mortgage balance: $247,000
- second home mortgage balance: $80,426

Household inputs:
- auto loan balance: $13,000
- auto loan interest: $980
- household vehicles value: $16,100

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
- child2_wic_eligible: whether Child 2 is eligible for WIC (1 if yes, 0 if no)
- child3_wic_eligible: whether Child 3 is eligible for WIC (1 if yes, 0 if no)
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_medicaid_eligible: whether Child 1 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_medicaid_eligible: whether Child 2 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child3_medicaid_eligible: whether Child 3 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_chip_eligible: whether Child 1 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_chip_eligible: whether Child 2 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child3_chip_eligible: whether Child 3 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- child1_medicare_eligible: whether Child 1 is eligible for Medicare (1 if yes, 0 if no)
- child2_medicare_eligible: whether Child 2 is eligible for Medicare (1 if yes, 0 if no)
- child3_medicare_eligible: whether Child 3 is eligible for Medicare (1 if yes, 0 if no)
- free_school_meals_eligible: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)
- reduced_price_school_meals_eligible: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)
- child1_head_start_eligible: whether Child 1 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child2_head_start_eligible: whether Child 2 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child3_head_start_eligible: whether Child 3 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child1_early_head_start_eligible: whether Child 1 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)
- child2_early_head_start_eligible: whether Child 2 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)
- child3_early_head_start_eligible: whether Child 3 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)

Use the `submit_outputs` function exactly once. Return an `outputs` object with every requested quantity keyed by variable name. Each requested key must map to an object with a numeric `value` and a non-empty, specific, concise `explanation`. Each explanation must support the numeric value submitted for the same variable in `outputs`. If an explanation mentions a final amount, that amount must match the corresponding `outputs` value. Do not write that you will use one value while submitting a different value. Do not include scratch work, abandoned calculations, or corrections. End each explanation with `value = X`, where X exactly matches the numeric `value` field. For 1/0 eligibility outputs, submit 1 only when the explanation says eligible or yes, and submit 0 only when it says not eligible or no. Use the exact variable names as keys inside `outputs`. Include every requested key exactly once in `outputs`, even if the value is 0. Put only numeric values in `value`, with no dollar signs, commas, or explanatory text. Do not rely on plain text for the final answers. If an answer is a currency amount, give the annual amount. If an answer is a rate, give a decimal (e.g. 0.25 for 25%).
----- END HOUSEHOLD PROMPT -----

ENGINE REFERENCE VALUE: $62.41 (engine output 62.41279220581055)
MODELS: 45 gave a usable answer; 3 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 41 models (3 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Pennsylvania has a flat 3.07% income tax and no refundable individual income tax credits like a state EITC or CTC; the only relief is the nonrefundable tax forgiveness program, and this household's $60,010 taxable income exceeds forgiveness eligibility anyway. value = 0
- claude-fable-5.1: answered 0
  explanation: PA offers no applicable refundable credits (no child care expenses for the PA CDCC). value = 0
- claude-haiku-4.5: answered 0
  explanation: Pennsylvania does not have refundable state individual income tax credits. PA offers various tax credits such as the PA Child and Dependent Care Credit and Earned Income Tax Credit, but Pennsylvania's earned income tax credit (PA EIC) is non-refundable. The household's income and household composition do not qualify for any special refundable credits under PA tax law. value = 0
- claude-opus-4.7: answered 0
  explanation: PA has no refundable state income tax credits applicable here. The head's income ($60,000 wages) is too high for PA's Tax Forgiveness credit (which for a single filer with 3 dependents phases out well below this level). No other refundable PA credits apply. value = 0
- claude-opus-4.8: answered 0
  explanation: Pennsylvania's main refundable state income tax credit mechanism is the Tax Forgiveness program (special tax forgiveness), which reduces or eliminates PA tax liability but is structured as a forgiveness/reduction of tax owed rather than a refundable cash credit beyond tax. With $60,000 wages plus interest, eligibility income far exceeds the Tax Forgiveness thresholds for a family this size, so no forgiveness applies. PA has no other refundable individual income tax credits applicable to this household. value = 0
- claude-opus-5: answered 0
  explanation: PA has no applicable refundable income tax credits for this household. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Pennsylvania does not have a state Earned Income Tax Credit or other broadly available refundable individual income tax credits. PA's flat income tax (3.07%) does not include refundable credits for this household's situation (single filer, age 45, with wages and three dependents). No PA refundable credits apply to this household. value = 0
- claude-sonnet-5: answered 0
  explanation: Pennsylvania does not offer a refundable state individual income tax credit comparable to a state EITC; its main relief is the non-refundable Tax Forgiveness (SP) credit, which phases out fully at this household's income level ($60,000+ wages plus interest and child support for a family of 5 exceeds PA's Tax Forgiveness income thresholds, so no forgiveness credit applies) and PA has no other refundable credits. Thus total state refundable credits = 0, value = 0.
- claude-sonnet-5.5: answered 0
  explanation: No PA refundable credit applies. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Pennsylvania provides no refundable income tax credits for this household at this income level. value = 0
- deepseek-v4-pro: answered 0
  explanation: Income $60,010 exceeds PA Tax Forgiveness thresholds for family of 4. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Pennsylvania provides no refundable income tax credit for this household; value = 0
- deepseek-v4.1-flash: answered 0
  explanation: PA does not offer refundable individual income tax credits. value = 0
- gemini-3-flash-preview: answered 0
  explanation: Pennsylvania did not have any refundable state individual income tax credits applicable to this household's income level and profile for the 2026 tax year. value = 0.0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: No state-level refundable tax credits are applicable for this household. value = 0.0
- gemini-3.1-pro-preview: answered 0
  explanation: The household does not have eligible childcare expenses for the PA Child and Dependent Care Enhancement Tax Credit and does not qualify for other state refundable credits. value = 0
- gemini-3.5-flash: answered 0
  explanation: Pennsylvania does not offer any refundable state income tax credits that this household is eligible for. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: No state refundable tax credits are available for this household profile, value = 0
- gemini-3.6-flash: answered 0
  explanation: The household does not qualify for state refundable tax credits in Pennsylvania. value = 0
- gemini-3.7-flash: answered 0
  explanation: Household does not qualify for refundable Pennsylvania tax credits; value = 0
- gemini-3.8-flash: answered 0
  explanation: The household is not eligible for any refundable state income tax credits in Pennsylvania. value = 0
- glm-5.3: answered 0
  explanation: Pennsylvania offers no refundable individual income tax credits to this household (the property tax/rent rebate requires age 65 or disability), so refundable state credits are $0. value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable Pennsylvania income tax credits are indicated by the household facts. value = 0
- gpt-5.4-nano: answered 0
  explanation: No refundable state-credit eligibility indicators (e.g., income low enough for major refundable credits) are provided; refundable state credits estimated at 0. value = 0
- gpt-5.5: answered 0
  explanation: No refundable Pennsylvania individual income tax credit is supported by the facts provided; there are no listed child care expenses or other qualifying refundable-credit inputs. value = 0
- gpt-5.6-luna: answered 0
  explanation: No refundable Pennsylvania individual income tax credit applies to the reported household facts. value = 0
- gpt-5.6-sol: answered 0
  explanation: No Pennsylvania refundable individual income-tax credit applies to the listed facts; value = 0
- gpt-5.6-terra: answered 0
  explanation: No Pennsylvania refundable credit applies at this income or from the listed facts. value = 0
- gpt-6-sol: answered 0
  explanation: No Pennsylvania refundable income tax credit is indicated for this household, value = 0
- grok-4.3: answered 0
  explanation: No state refundable credits. value = 0
- grok-4.5: answered 0
  explanation: No refundable PA personal-income-tax credits apply. value = 0
- grok-4.6: answered 0
  explanation: Pennsylvania has no refundable individual income tax credits that apply to this household. value = 0
- grok-4.7: answered 0
  explanation: Pennsylvania has no refundable earned income or child credit that this household can claim, and Tax Forgiveness is nonrefundable and income-ineligible. value = 0
- grok-build-0.1: answered 0
  explanation: PA has no state refundable tax credits applicable here, such as no state EITC. value = 0
- inkling: answered 0
  explanation: Pennsylvania does not provide a refundable state income tax credit that applies here (Tax Forgiveness is nonrefundable and income is too high). value = 0
- kimi-k2.6: answered 0
  explanation: The household’s income of roughly $60,010 far exceeds Pennsylvania’s Tax Forgiveness eligibility limits for a family of four, and no other refundable state income tax credits apply. value = 0
- kimi-k3: answered 0
  explanation: Pennsylvania has no refundable state income tax credits (no state EITC or similar refundable credit). value = 0
- minimax-m3: answered 0
  explanation: PA has limited refundable income tax credits and none apply based on listed facts. value = 0
- ox-alpha: answered 0
  explanation: Pennsylvania provides no refundable income tax credits applicable to this household; tax forgiveness is not available at $60,010 eligibility income. value = 0
- qwen-3.7-max: answered 0
  explanation: Pennsylvania does not offer a refundable Earned Income Tax Credit or a refundable Child Tax Credit at the state level. No other refundable PA state tax credits apply to this household based on the listed facts. value = 0
- qwen3.8-max: answered 0
  explanation: No Pennsylvania refundable credits apply to this household. value = 0