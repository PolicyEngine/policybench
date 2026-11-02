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
STATE: MN
OUTPUT: reduced_price_school_meals_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only reduced_price_school_meals_eligible):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: MN
- tax year: 2026

Head:
- age: 50
- gross wages and salaries: $29,000
- bank account assets: $11,300
- hourly wage: $16
- usual weekly hours worked: 36
- is paid hourly
- other medical expenses: $50
- over-the-counter health expenses: $200
- Social Security dependent benefits: $13,664

Spouse:
- age: 18
- over-the-counter health expenses: $100

Child 1:
- age: 6
- over-the-counter health expenses: $100

Benefit inputs:
- spm unit energy subsidy: $50

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
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_medicaid_eligible: whether Spouse is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_medicaid_eligible: whether Child 1 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_chip_eligible: whether Spouse is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_chip_eligible: whether Child 1 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- spouse_medicare_eligible: whether Spouse is eligible for Medicare (1 if yes, 0 if no)
- child1_medicare_eligible: whether Child 1 is eligible for Medicare (1 if yes, 0 if no)
- free_school_meals_eligible: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)
- reduced_price_school_meals_eligible: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)
- child1_head_start_eligible: whether Child 1 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child1_early_head_start_eligible: whether Child 1 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)

Use the `submit_outputs` function exactly once. Return an `outputs` object with every requested quantity keyed by variable name. Each requested key must map to an object with a numeric `value` and a non-empty, specific, concise `explanation`. Each explanation must support the numeric value submitted for the same variable in `outputs`. If an explanation mentions a final amount, that amount must match the corresponding `outputs` value. Do not write that you will use one value while submitting a different value. Do not include scratch work, abandoned calculations, or corrections. End each explanation with `value = X`, where X exactly matches the numeric `value` field. For 1/0 eligibility outputs, submit 1 only when the explanation says eligible or yes, and submit 0 only when it says not eligible or no. Use the exact variable names as keys inside `outputs`. Include every requested key exactly once in `outputs`, even if the value is 0. Put only numeric values in `value`, with no dollar signs, commas, or explanatory text. Do not rely on plain text for the final answers. If an answer is a currency amount, give the annual amount. If an answer is a rate, give a decimal (e.g. 0.25 for 25%).
----- END HOUSEHOLD PROMPT -----

ENGINE REFERENCE VALUE: 0 (not eligible)
MODELS: 45 gave a usable answer; 20 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 1, given by 25 models (3 of them among the benchmark's top-ranked models)
- claude-fable-5.1: answered 1
  explanation: Income 42,664 is between 130% and 185% FPL for 3 (~49,302) with a school-age child, so reduced-price meal support is positive; yes. value = 1
- claude-haiku-4.5: answered 1
  explanation: The household has gross income of $42,664 (head's wages of $29,000 plus Social Security dependent benefits of $13,664). With a household size of 4 (head, spouse, and 2 children), the household's income-to-poverty ratio is well below the reduced-price meals eligibility threshold of 185% of federal poverty level. For 2026, the federal poverty guideline for a family of 4 is approximately $27,750, and 185% of that is approximately $51,337. Since the household's income of $42,664 is below this threshold, the household qualifies for reduced-price school meal support. value = 1
- claude-opus-4.7: answered 1
  explanation: Household income: $29,000 wages + $13,664 SS = $42,664. For a family of 3 in 2026, reduced-price meal threshold is ~185% FPL (~$48,000), so household qualifies for reduced-price... but free meal threshold is 130% FPL (~$33,700), and $42,664 exceeds this, so they fall in reduced-price range. However, with SS benefits counted, income $42,664 for family of 3 is below 185% FPL (~$49,000 for 2026), so reduced-price eligible. Wait - actually $42,664 is above 130% FPL ($33,700) and below 185% FPL, qualifying for reduced-price meals. value = 1
- claude-opus-4.8: answered 1
  explanation: School meal eligibility is based on income relative to federal poverty guidelines. Household has 3 people. Countable income includes wages $29,000 plus Social Security dependent benefits $13,664 = $42,664. Reduced-price meals require income between 130% and 185% of poverty. For a 3-person household, 185% of poverty (~$48,000) exceeds $42,664 while 130% (~$33,800) is below it, so income falls in the reduced-price band. The 6-year-old child qualifies for reduced-price school meals. value = 1
- claude-opus-5: answered 1
  explanation: Household income at roughly 170% FPL is between 130% and 185% FPL, so the school-age child qualifies for reduced-price meals. value = 1
- claude-opus-5.5: answered 1
  explanation: Income at about 160% of the poverty line is between 130% and 185%, so eligible for reduced-price meals. value = 1
- claude-sonnet-4.6: answered 1
  explanation: Reduced-price school meals (as opposed to free meals) are available to households with income between 130% and 185% of the federal poverty level (FPL). The household's gross income includes wages of $29,000 plus Social Security dependent benefits of $13,664, totaling $42,664. For a household of 3 (head, spouse, child), the 2026 FPL is approximately $24,860. 185% of FPL ≈ $46,000, and 130% of FPL ≈ $32,318. The household income of $42,664 falls between 130% and 185% of FPL, which would normally indicate reduced-price eligibility. However, the spouse is 18 years old and the child is 6. The National School Lunch Program reduced-price benefit applies to school-age children. Child 1 (age 6) is school-age. PolicyEngine's reduced-price school meals calculation uses the SPM unit income. With total income of $42,664 and an SPM unit energy subsidy of $50, the countable income is around $42,664. At 185% FPL for a family of 3 (~$46,000), the household is under the 185% threshold, placing it in reduced-price territory (above 130% FPL ~$32,318). This would suggest reduced-price eligibility. However, PolicyEngine also considers whether the benefit is positive after accounting for free meal eligibility thresholds. Since income exceeds 130% FPL, the household does not qualify for free meals but could qualify for reduced-price meals. PolicyEngine should return a positive reduced-price school meal benefit for Child 1. But reviewing more carefully: the household income of $42,664 vs 185% FPL for 3 persons (~$46,000 in 2026) is below 185%, so reduced-price eligibility applies. Yet PolicyEngine may classify this differently based on exact FPL figures and program rules. Given income of $42,664 is between 130% and 185% FPL for a 3-person household, Child 1 (age 6) should be eligible for reduced-price meals, yielding a positive annual benefit. However, upon careful reconsideration, the 2026 FPL for 3 persons is approximately $25,820 (2024 base ~$24,860 with inflation adjustments). 185% of $ [... 238 more characters cut]
- claude-sonnet-5.5: answered 1
  explanation: Countable income of about 42,700 is above 130% but below 185% of the FPL for 3 (about 49,300). Eligible for reduced-price meals. value = 1
- deepseek-v4-flash-0731: answered 1
  explanation: Household income (~157% FPL) is above 130% but at or below 185% FPL, so the child is eligible for reduced-price school meals. value = 1
- deepseek-v4-pro: answered 1
  explanation: Income $42,664 < 185% FPL $50,272; eligible for reduced-price meals. value = 1
- deepseek-v4.1-flash: answered 1
  explanation: Household income $42,664 is below 185% FPL for 3 (~$50,875) and above 130% FPL. Eligible. value = 1
- gemini-3.8-flash: answered 1
  explanation: Household income of $42,664 is between 130% and 185% of the federal poverty line for a household of 3, qualifying Child 1 for reduced-price school meals, value = 1
- glm-5.2: answered 1
  explanation: Total household income is $42,664. This is below 185% of the 2026 federal poverty guideline for a household of 3 but above 130%, so the household is eligible for reduced-price school meals. value = 1
- glm-5.3: answered 1
  explanation: Household income of $42,664 is about 153% of the federal poverty guideline, which is within the 130-185% band for reduced-price school meals, so the household qualifies for reduced-price meal support. value = 1
- gpt-5.5: answered 1
  explanation: The household has a school-age child and annual countable income of $42,664 is below the federal reduced-price meal limit for a 3-person household while above the free-meal limit, so reduced-price school meals are eligible; value = 1
- gpt-5.6-luna: answered 1
  explanation: Household income is below the federal reduced-price school-meal threshold for three people, so positive reduced-price support is returned; value = 1
- gpt-5.6-terra: answered 1
  explanation: Reported household income is within the modeled reduced-price school-meal income range for a three-person household; value = 1
- gpt-6-luna: answered 1
  explanation: Estimated household income is within the reduced-price meal range for a three-person household; reduced-price meal support is expected. value = 1
- grok-4.5: answered 1
  explanation: Household money income of 42664 is approximately 156 percent of the projected 2026 FPL for three, below the 185 percent reduced-price limit, so the household is eligible for reduced-price school meals. value = 1
- grok-4.6: answered 1
  explanation: Household MAGI of about 156 percent of FPL lies between 130 and 185 percent of FPL, so PolicyEngine returns positive reduced-price school meal support for the school-age child. value = 1
- grok-4.7: answered 1
  explanation: Gross income of $42,664 is above 130% FPL and below 185% FPL for a household of three, and Child 1 is school age. PolicyEngine therefore returns positive reduced-price school meal support, so the household is eligible for reduced-price school meals. value = 1
- grok-build-0.1: answered 1
  explanation: Household gross income of $42,664 is approximately 156.7% of the 2026 FPL for a 3-person household (~$27,207), below the 185% FPL threshold for reduced-price school meals. value = 1
- inkling: answered 1
  explanation: Household income (~$42,664) falls between 130% and 185% FPL ($33,566 to $47,767) for 3 people, making them eligible for reduced-price school meals. value = 1
- kimi-k3: answered 1
  explanation: Household income is about 156% of poverty, between the 130% free-meal and 185% reduced-price-meal limits, and Child 1 is school age, so the household is eligible. value = 1
- ox-alpha: answered 1
  explanation: Household income of $42,664 (~160% of the 3-person poverty line) is at or below the 185% cutoff for reduced-price meals for the school-age child. value = 1