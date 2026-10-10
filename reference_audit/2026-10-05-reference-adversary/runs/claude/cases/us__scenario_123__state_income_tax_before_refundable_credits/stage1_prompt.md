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
OUTPUT: state_income_tax_before_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: state individual income tax after nonrefundable credits and before refundable credits, excluding local income and payroll taxes

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_income_tax_before_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: PA
- tax year: 2026

Head:
- age: 39
- gross wages and salaries: $100,000
- bank account assets: $10,278
- charitable cash donations: $16,100
- hourly wage: $35
- usual weekly hours worked: 55
- other medical expenses: $800
- over-the-counter health expenses: $50
- real estate taxes: $2,457
- taxable interest income: $1

Spouse:
- age: 39
- other medical expenses: $800
- over-the-counter health expenses: $50
- taxable interest income: $1

Child 1:
- age: 16
- gross wages and salaries: $45,000
- hourly wage: $23
- usual weekly hours worked: 38
- is paid hourly
- other medical expenses: $400
- over-the-counter health expenses: $50

Tax unit:
- first home mortgage balance: $420,000

Household inputs:
- household vehicles value: $45,747

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

ENGINE REFERENCE VALUE: $3,070.06 (engine output 3,070.061279296875)
MODELS: 46 gave a usable answer; 0 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 4,452, given by 32 models (5 of them among the benchmark's top-ranked models)
- claude-fable-5.1: answered 4,451.56
  explanation: Pennsylvania flat 3.07% tax on taxable compensation and interest: 145,002 * 0.0307 = 4,451.56. Income far exceeds PA tax forgiveness eligibility limits, so no reduction. value = 4451.56
- claude-opus-4.7: answered 4,452.08
  explanation: PA flat income tax rate is 3.07%. Taxable compensation: Head $100,000 + Child $45,000 = $145,000. Taxable interest: $1 + $1 = $2. Total PA taxable income = $145,002. Tax = $145,002 × 0.0307 = $4,451.56. PA does not allow itemized deductions or standard deduction; charitable contributions and mortgage interest are not deductible. No nonrefundable credits apply. value = 4452.08
- claude-opus-5: answered 4,451.56
  explanation: PA flat 3.07% on compensation and interest: (100,000 + 2) × 0.0307 ≈ 3,070 for head/spouse plus 45,000 × 0.0307 = 1,381.50 for child = about 4,451.56. No PA tax forgiveness at this income. value = 4451.56
- claude-opus-5.5: answered 4,451.56
  explanation: PA applies a flat 3.07% to $145,002 of compensation plus interest. Income is too high for tax forgiveness. value = 4451.56
- claude-sonnet-4.6: answered 4,451.56
  explanation: Pennsylvania imposes a flat 3.07% income tax on taxable income. PA does not allow federal itemized deductions, standard deductions, or personal exemptions. PA taxes wages, interest, and net income from operations. Taxable income for the head: $100,000 wages + $1 interest = $100,001. Taxable income for the spouse: $1 interest = $1. Child 1 (age 16) files separately in PA but is part of the same tax unit; however, for PA purposes each person's income is taxed separately. Child 1: $45,000 wages. Total PA taxable income for the household tax unit = $100,001 + $1 + $45,000 = $145,002. PA does not allow deductions for charitable donations, mortgage interest, real estate taxes, or medical expenses. PA tax = $145,002 × 3.07% = $4,451.56. However, reviewing the filing: In PA, a married couple files jointly. The child's income is not included on the parents' return — the child files their own PA return. Joint return income: $100,001 (head wages + interest) + $1 (spouse interest) = $100,002. PA tax on joint return = $100,002 × 0.0307 = $3,070.06. Child's PA tax = $45,000 × 0.0307 = $1,381.50. But the question asks for the tax unit as defined (head, spouse, child together). Since all are listed in one tax unit, I include all income: $145,002 × 0.0307 = $4,451.56. PA has no nonrefundable credits applicable here (no dependent care credit, no child tax credit at state level that would reduce tax before refundable credits in PA). PA does have a Tax Forgiveness Credit (Special Tax Forgiveness) which is a nonrefundable credit for low-income filers, but with $145,002 in income this household does not qualify. Therefore, state income tax before refundable credits = $145,002 × 0.0307 = $4,451.56. Recalculating precisely: $145,002 × 0.0307 = $145,002 × 0.03 + $145,002 × 0.0007 = $4,350.06 + $101.50 = $4,451.56. value = 4451.56
- claude-sonnet-5.5: answered 4,451.56
  explanation: PA flat 3.07% rate. Parents' unit: 100,002 × 3.07% = 3,070.06. Child's separate unit: 45,000 × 3.07% = 1,381.50. Total 4,451.56. No tax forgiveness applies at these incomes. value = 4451.56
- deepseek-v4-flash-0731: answered 4,451.56
  explanation: Pennsylvania flat income tax of 3.07% on taxable wages and interest of $145,002 = $4,451.56; no PA refundable credits apply. value = 4451.56
- deepseek-v4-pro: answered 4,451.5
  explanation: Pennsylvania imposes a flat 3.07% tax on gross compensation. Head: $100,000 × 3.07% = $3,070. Child 1: $45,000 × 3.07% = $1,381.50. Spouse: $0. No nonrefundable credits reduce this amount. Total = $4,451.50. value = 4451.50
- deepseek-v4-pro-0813: answered 4,451.56
  explanation: Pennsylvania flat 3.07% tax on $145,002 of wages and taxable interest equals $4,451.56; no nonrefundable credits apply. value = 4451.56
- gemini-3-flash-preview: answered 4,451.56
  explanation: Pennsylvania individual income tax is a flat 3.07% of taxable income with no standard deduction. Total household taxable income is $145,002 ($100,001 for Head, $1 for Spouse, and $45,000 for Child 1). $145,002 * 0.0307 = $4,451.56. value = 4451.56
- gemini-3.1-pro-preview: answered 4,451.56
  explanation: Pennsylvania has a flat income tax rate of 3.07%, which applies to the total household taxable income of $145,002 (wages and interest). value = 4451.56
- gemini-3.5-flash: answered 4,452
  explanation: Pennsylvania has a flat income tax rate of 3.07% with no standard deduction or personal exemptions. For the Head/Spouse joint filing, taxable income is $100,002, yielding $3,070 in tax. For Child 1, taxable income is $45,000, yielding $1,382 in tax. The total state income tax is $4,452.0. value = 4452.0
- gemini-3.6-flash: answered 4,451.56
  explanation: PA state income tax of 3.07% applied to total household taxable income of $145,002, value = 4451.56
- gemini-3.7-flash: answered 4,451.56
  explanation: Pennsylvania state income tax is 3.07% on total taxable income of $145,002, yielding $4,451.56, value = 4451.56
- gemini-3.8-flash: answered 4,451.56
  explanation: Pennsylvania flat income tax of 3.07% applies to PA taxable compensation ($145,000) plus taxable interest ($2), totaling $145,002, yielding $4,451.56 in tax liability. value = 4451.56
- glm-5.2: answered 4,451.56
  explanation: Pennsylvania has a flat personal income tax rate of 3.07%. The head and spouse file jointly with taxable income of $100,000 (wages) + $2 (interest) = $100,002, yielding $100,002 × 0.0307 = $3,070.06. Child 1, age 16, files separately with $45,000 in wages, yielding $45,000 × 0.0307 = $1,381.50. PA does not allow standard or itemized deductions (including charitable contributions or real estate taxes). No applicable nonrefundable credits apply. Total state income tax = $3,070.06 + $1,381.50 = $4,451.56. value = 4451.56
- glm-5.3: answered 4,451.56
  explanation: Pennsylvania flat 3.07% tax on the household's taxable compensation and interest: $100,000 + $45,000 + $2 = $145,002 x 0.0307 = $4,451.56. PA does not allow charitable or standard deductions, and PA tax forgiveness does not apply at this income level. value = 4451.56
- gpt-5.5: answered 4,451.56
  explanation: Pennsylvania taxes compensation and taxable interest at 3.07%; taxable PA income is $100,000 + $45,000 + $2 = $145,002, giving $145,002 × 0.0307 = $4,451.56, with no nonrefundable Tax Forgiveness credit at this income level. value = 4451.56
- gpt-5.6-sol: answered 4,451.56
  explanation: Pennsylvania applies its 3.07% flat income-tax rate to 145002 of wages and taxable interest, with no applicable tax-forgiveness credit at this income, value = 4451.56
- gpt-5.6-terra: answered 4,451.56
  explanation: Pennsylvania's 3.07% individual income tax applies to the household's $145,002 of reported wages and taxable interest, with no applicable credit. value = 4451.56
- gpt-6-astra: answered 4,451.56
  explanation: Pennsylvania taxes $145,002 of household wages and interest at 3.07%, with no applicable deduction or nonrefundable credit; value = 4451.56
- gpt-6-luna: answered 4,451.56
  explanation: Pennsylvania’s 3.07% income tax on the parents’ $100,002 income and the child’s separate $45,000 wage income totals $4,451.56; no state nonrefundable credit is indicated. value = 4451.56
- gpt-6-sol: answered 4,451.56
  explanation: Pennsylvania taxes 145000 of wages and 2 of interest at 3.07%, rounded to cents; value = 4451.56
- gpt-6.1-sol: answered 4,451.56
  explanation: Pennsylvania taxes $145,000 of wages and $2 of interest at 3.07%, with no applicable nonrefundable credit or tax forgiveness; value = 4451.56
- grok-4.5: answered 4,452
  explanation: PA flat 3.07% PIT on combined taxable compensation and interest of $145002 with no applicable nonrefundable credits at this income. value = 4452
- grok-4.6: answered 4,452
  explanation: Pennsylvania PIT is a flat 3.07 percent on compensation plus taxable interest with no standard deduction, personal exemptions, or itemized deductions for charity or property tax. Taxable income is therefore 145002 and tax is 4451.56, rounded to 4452. Income far exceeds PA tax-forgiveness limits so that credit is zero. value = 4452
- grok-4.7: answered 4,451.56
  explanation: Pennsylvania taxes compensation and interest at a flat 3.07%. Taxable income is $145,002, so tax is 145002 × 0.0307 = $4,451.56. Income is far above PA Tax Forgiveness limits, and no other nonrefundable state credits apply. value = 4451.56
- grok-build-0.1: answered 4,452
  explanation: PA flat 3.07% tax on $145002 total wages and interest (head $100001, spouse $1, child $45000). 145002 x 0.0307 = 4451.56 rounded to 4452. value = 4452
- inkling: answered 4,451.56
  explanation: Pennsylvania applies a flat 3.07% tax to about $145,002 of taxable wages and interest across both filing units ($100,002 for parents and $45,000 for Child 1). Tax equals $4,451.56 with no nonrefundable state credits used. value = 4451.56
- kimi-k3: answered 4,451.56
  explanation: Pennsylvania taxes compensation and interest at a flat 3.07% with no standard deduction or federal itemized deductions; taxable income is 145002, giving 4451.5614 before credits. value = 4451.56
- ox-alpha: answered 4,451.56
  explanation: PA flat 3.07% tax on total taxable income of $145,002 (wages $145,000 + interest $2; PA allows no deduction for charity, medical costs, or property tax) = $4,451.56; PA Tax Forgiveness is unavailable at this income level. value = 4451.56
- qwen-3.7-max: answered 4,451.57
  explanation: PA has a flat 3.07% income tax rate with no standard deduction or personal exemptions. Taxable income includes wages ($100,000 head + $45,000 child 1 = $145,000) and interest ($1 head + $1 spouse = $2), totaling $145,002. PA does not allow deductions for charitable contributions, real estate taxes, or medical expenses. Tax = $145,002 × 0.0307 = $4,451.57. No nonrefundable credits apply, so state income tax before refundable credits is $4,451.57. value = 4451.57