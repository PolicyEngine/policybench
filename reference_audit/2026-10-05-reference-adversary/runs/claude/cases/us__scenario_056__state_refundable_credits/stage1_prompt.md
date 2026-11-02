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
STATE: NJ
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: NJ
- tax year: 2026

Head:
- age: 20
- alimony income: $1,499
- charitable cash donations: $1,428
- financial assistance: $12,000
- has employer-sponsored insurance
- home mortgage interest: $6,773
- is unmarried partner of household head
- real estate taxes: $11,949
- sstb self employment income before lsr: $4,340

Tax unit:
- first home mortgage balance: $100,341
- first home mortgage interest: $6,773
- health savings account deduction: $9,915

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

ENGINE REFERENCE VALUE: $265.60 (engine output 265.6000061035156)
MODELS: 45 gave a usable answer; 0 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 34 models (1 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: NJ refundable credits include the NJ EITC (40% of federal EITC), NJ CTC, and ANCHOR-related credits. The head is age 20, childless, and does not meet the federal EITC minimum age of 25 for workers without qualifying children, so federal and NJ EITC are 0. No children means no NJ Child Tax Credit or child/dependent care credit. No other refundable NJ credits apply. value = 0
- claude-haiku-4.5: answered 0
  explanation: New Jersey does not have a state-level earned income tax credit or other refundable income tax credits for tax year 2026. The household has alimony income, self-employment income, and various deductions, but none of these generate eligibility for NJ refundable credits. The financial assistance of $12,000 is not taxable income and does not create tax liability or credit eligibility. value = 0
- claude-opus-4.7: answered 0
  explanation: Head is 20 (under 21, no qualifying children mentioned), so not eligible for NJ EITC. No CDCC eligible expenses, no Child Tax Credit qualifying children. No other refundable NJ credits apply. value = 0
- claude-opus-4.8: answered 0
  explanation: NJ refundable credits (e.g. EITC) require qualifying earned income. The head's only earned income is SSTB self-employment of $4,340, but as an unmarried partner age 20 with no qualifying children, and with significant unearned income, no NJ refundable credit applies. value = 0
- claude-opus-5: answered 0
  explanation: NJ EITC requires federal EITC eligibility; head is under 25 with no children, and no other refundable NJ credits apply. value = 0
- claude-sonnet-4.6: answered 0
  explanation: New Jersey does not have a general refundable individual income tax credit that would apply to this household's situation. The taxpayer is a 20-year-old unmarried individual with self-employment income of $4,340 (SSTB), alimony income of $1,499, and financial assistance of $12,000. NJ's main refundable credits include the Earned Income Tax Credit (NJEITC) and the Child and Dependent Care Credit. The NJEITC requires federal EITC eligibility; this filer has no qualifying children and at age 20 does not meet the minimum age of 25 for the childless EITC (in 2026 the federal EITC for childless workers requires age 25–64, so this filer is ineligible). There are no qualifying dependents listed, so the Child and Dependent Care Credit does not apply. No other NJ refundable credits are applicable based on the household facts provided. Total refundable state credits = $0. value = 0
- claude-sonnet-5: answered 0
  explanation: NJ's main refundable credit is the NJ Earned Income Tax Credit, which requires a federal EITC-qualifying filer with earned income; here the head is a young unmarried partner (not filer's dependent status relevant) with self-employment income of $4,340 but is 20 years old and likely claimed as a dependent or not meeting EITC qualifying criteria, and no children are present to qualify for EITC without meeting the childless worker age requirement (25+). NJ also offers a Child Tax Credit (refundable) but no qualifying children are listed in the household. With no qualifying children and the head under age 25, no NJ EIC applies, and no other NJ refundable credits (e.g., Property Tax/Rent rebate is nonrefundable or credit-based but ANCHOR is a separate rebate program not modeled here) apply. Therefore total state refundable credits = 0. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: NJ's refundable Working Families Credit requires federal EITC eligibility, which the age-20 head lacks; no other NJ refundable income tax credits apply. value = 0
- deepseek-v4-pro: answered 0
  explanation: No refundable state credits apply. NJ EITC is based on federal EITC, which is $0. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: NJ EITC is 40% of federal EITC, but federal EITC is $0 due to age 20 and no children; no other refundable state credits. value = 0
- gemini-3-flash-preview: answered 0
  explanation: The household is not eligible for the New Jersey Earned Income Tax Credit because they do not qualify for the federal EITC, and there are no children in the household to qualify for other refundable credits. value = 0.0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: No state refundable credits apply to this income profile. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: The total refundable state individual income tax credits are $0.00. value = 0
- gemini-3.6-flash: answered 0
  explanation: With $0 federal EITC eligibility and no qualifying children, New Jersey refundable tax credits are $0. value = 0
- gemini-3.7-flash: answered 0
  explanation: Head is under age 21 and has no qualifying dependents, making them ineligible for NJ refundable credits. value = 0
- gemini-3.8-flash: answered 0
  explanation: Because Head does not qualify for the federal EITC and has no qualifying children under age 6, Head is not eligible for the New Jersey EITC or child tax credits. value = 0
- glm-5.2: answered 0
  explanation: The head is 20 years old with no qualifying children listed, making them ineligible for the federal Earned Income Tax Credit (EITC) which requires age 25-64 for childless adults. Consequently, they are also ineligible for the NJ EITC. No other refundable state credits apply. value = 0
- glm-5.3: answered 0
  explanation: NJ EITC follows federal childless EITC rules, which require ages 25-64 (NJ childless EITC requires 21+); at age 20 the head is not eligible, and no other refundable NJ credits apply. value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable New Jersey income tax credits are indicated by the provided facts, so refundable state credits are zero. value = 0
- gpt-5.4-nano: answered 0
  explanation: No refundable NJ credits can be inferred from the provided facts (no explicit low-income eligibility indicators for NJ refundable credits beyond what would be required, and no children specified). value = 0
- gpt-5.5: answered 0
  explanation: With no listed dependents and no positive New Jersey income tax liability, the household has no identified refundable New Jersey individual income tax credits. value = 0
- gpt-5.6-luna: answered 0
  explanation: No New Jersey refundable income-tax credit applies because there is no qualifying state EITC or other refundable credit; value = 0
- gpt-6-luna: answered 0
  explanation: No refundable New Jersey credit is supported: the Head does not qualify for the state EITC, and no other refundable credit is established by the facts. value = 0
- grok-4.3: answered 0
  explanation: No state refundable credits qualify. value = 0
- grok-4.5: answered 0
  explanation: No federal EITC generates a zero NJ EITC; no other refundable NJ credits apply. value = 0
- grok-4.6: answered 0
  explanation: No federal EITC means no NJ EITC, and no other refundable NJ individual income tax credits apply. value = 0
- grok-4.7: answered 0
  explanation: NJ EITC is a share of federal EITC, which is $0. There is no NJ child tax credit without a child, and the refundable $50 property-tax credit requires age 65+, blindness, or disability. value = 0
- grok-build-0.1: answered 0
  explanation: NJ EITC is 40% of federal EITC ($0 here). No other refundable state income tax credits apply when using the property tax deduction. value = 0
- inkling: answered 0
  explanation: NJ EITC is $0 because federal EITC is ineligible; no other NJ refundable credits (e.g., child-related) apply without dependents. value = 0
- kimi-k3: answered 0
  explanation: The New Jersey EITC equals 40% of the federal EITC, which is $0 (Head is 20, below the 25-64 childless-worker age range), and there is no qualifying child for the NJ child tax credit; the $50 NJ property-tax credit is nonrefundable and is not used. value = 0
- minimax-m3: answered 0
  explanation: No NJ refundable credits apply given the household composition; value = 0
- ox-alpha: answered 0
  explanation: The NJ EITC is a percentage of the federal EITC (which is $0 for this age-ineligible childless filer) and the NJ child tax credit requires a young dependent; with neither, refundable state credits are 0. value = 0
- qwen-3.7-max: answered 0
  explanation: NJ offers the Earned Income Tax Credit and Child Tax Credit as refundable credits. The head is age 20 with no listed children or dependents in the household. Without qualifying children or sufficient earned income characteristics for NJ EITC eligibility, no refundable credits apply. value = 0
- qwen3.8-max: answered 0
  explanation: No New Jersey refundable credits apply because the household has no qualifying children, no NJ tax liability, and no eligible income or credit conditions. value = 0