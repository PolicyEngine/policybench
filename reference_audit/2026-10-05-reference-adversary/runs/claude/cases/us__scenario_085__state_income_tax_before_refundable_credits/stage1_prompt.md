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
- age: 67
- bank account assets: $133,000
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $300
- usual weekly hours worked: 40
- other health insurance premiums: $300
- other medical expenses: $3,400
- over-the-counter health expenses: $200
- roth 401k contributions desired: $1
- roth ira contributions desired: $1
- Social Security survivor benefits: $27,426
- taxable 401(k) distributions: $1,560
- taxable interest income: $1,675
- taxable IRA distributions: $7,568
- taxable private pension income: $20,720
- traditional 401k contributions desired: $8
- traditional ira contributions desired: $0

Tax unit:
- first home mortgage balance: $132,000

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

ENGINE REFERENCE VALUE: $0.00
MODELS: 46 gave a usable answer; 12 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 51, given by 27 models (3 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 51.42
  explanation: PA taxes wages/interest at 3.07% flat but exempts Social Security, and retirement income (pension, IRA, 401k distributions) for those 59.5+; head is 67 so pension/IRA/401k distributions are exempt. Head has no listed wages (usual hours but no wage income listed, treated as 0). Taxable PA income = interest $1,675. Tax = 1,675 * 0.0307 = 51.42. No PA tax forgiveness applies since eligibility income including Social Security ($27,426) and pensions exceeds limits. value = 51.42
- claude-fable-5.1: answered 51.42
  explanation: Pennsylvania exempts Social Security, pensions, IRA and 401(k) distributions for a retiree over 59.5; only taxable interest of 1,675 is taxed at the 3.07% flat rate = 51.42. Total eligibility income far exceeds PA tax forgiveness limits, so no forgiveness credit. value = 51.42
- claude-opus-4.7: answered 51.45
  explanation: PA taxes interest at 3.07%. Wages=0, no SS, no pensions, no retirement distributions (PA exempts these for retirees age 59½+). Taxable interest = $1,675. PA tax = $1,675 × 0.0307 = $51.4225. value = 51.45
- claude-opus-4.8: answered 51.42
  explanation: PA taxes income at flat 3.07%. PA does not tax Social Security, pension, IRA, or 401(k) retirement distributions for taxpayers, nor Social Security survivor benefits. Taxable interest income of $1,675 is PA taxable. 1675 * 0.0307 = 51.4225, rounded to 51.42. value = 51.42
- claude-opus-5.5: answered 51.42
  explanation: Pennsylvania exempts Social Security and retirement distributions received after retirement age. Only interest of $1,675 is taxed at 3.07%. This assumes eligibility income, which may include retirement income, exceeds the tax-forgiveness limit; that treatment is uncertain. value = 51.42
- claude-sonnet-4.6: answered 51
  explanation: Pennsylvania imposes a flat 3.07% income tax, but PA exempts Social Security benefits, retirement income (401k distributions, IRA distributions, and private pension income) for taxpayers age 60 and older. The head is age 67, so all retirement/pension/IRA/401k distributions and Social Security survivor benefits are fully exempt. The remaining taxable income is: taxable interest income $1,675 + (wages, if any — none listed so $0) = $1,675. However, PA also allows deductions for certain items. Traditional 401k contributions desired = $8 (negligible). Net PA taxable income = $1,675. PA tax = $1,675 × 3.07% = $51.42. However, PA does not have a standard deduction or personal exemption, so $1,675 × 0.0307 = $51.42. Rounding to nearest dollar = $51. PA has no nonrefundable credits applicable here (no children, no special credits noted). Therefore state income tax before refundable credits = $51. value = 51
- deepseek-v4-flash-0731: answered 51
  explanation: PA taxes only PA-taxable income at 3.07%; retirement distributions, pensions, and Social Security are excluded, leaving taxable interest of 1,675. Tax = 0.0307 × 1,675 = 51.42. value = 51
- deepseek-v4-pro-0813: answered 51
  explanation: Pennsylvania excludes Social Security and qualified retirement/pension distributions but taxes interest at 3.07%: $1,675 x 0.0307 = $51.42, rounded to $51. No PA nonrefundable credits apply. value = 51
- deepseek-v4.1-flash: answered 51.4225
  explanation: PA exempts Social Security and retirement income for age 59.5+. Taxable interest = 1,675. PA tax = 1,675 * 3.07% = 51.4225. value = 51.4225
- gemini-3-flash-preview: answered 51.42
  explanation: Pennsylvania taxes interest income at a flat rate of 3.07% ($1,675 * 0.0307 = $51.42). Retirement distributions (pension, IRA, 401k) for an individual over 59.5 years of age and Social Security benefits are not taxable in Pennsylvania. value = 51.42
- gemini-3.5-flash: answered 51
  explanation: Pennsylvania has a flat income tax rate of 3.07%. For a 67-year-old, Social Security and retirement benefits (pensions, IRA, and 401k distributions) are exempt from PA state income tax. Only the taxable interest income of $1,675 is taxed, yielding $1,675 * 3.07% = $51. value = 51.0
- gemini-3.6-flash: answered 51.42
  explanation: In Pennsylvania, Social Security benefits, pension income, IRA distributions, and 401(k) distributions received after reaching age 59.5 are exempt from state income tax. Only taxable interest income of $1,675 is subject to Pennsylvania's 3.07% flat tax rate, resulting in $51.42 of tax liability. value = 51.42
- gemini-3.7-flash: answered 51.42
  explanation: In Pennsylvania, retirement distributions and Social Security benefits are exempt from state income tax for seniors. Only taxable interest of $1,675 is subject to the 3.07% PA income tax rate, yielding $51.42. value = 51.42
- gemini-3.8-flash: answered 51.42
  explanation: Pennsylvania exempts Social Security benefits and retirement/pension distributions after age 59.5, leaving only $1,675 in taxable interest income taxed at PA's flat rate of 3.07%, yielding $51.42; value = 51.42
- glm-5.2: answered 51.42
  explanation: PA has a flat income tax rate of 3.07%. PA exempts Social Security benefits and, for individuals age 59.5+, exempts retirement income including 401(k) distributions ($1,560), IRA distributions ($7,568), and private pension income ($20,720). The head is age 67. The only PA-taxable income is taxable interest of $1,675. No PA deductions apply for 401(k) contributions since PA does not allow pre-tax treatment. State tax before refundable credits = $1,675 × 0.0307 = $51.42. value = 51.42
- gpt-5.5: answered 51
  explanation: Pennsylvania exempts Social Security and qualifying retirement distributions for this age-67 filer, leaving $1,675 of taxable interest subject to the 3.07% PA tax; $1,675 × 0.0307 = $51.42, rounded to $51, with no nonrefundable credits applied. value = 51
- gpt-5.6-luna: answered 51.4225
  explanation: Pennsylvania excludes the listed Social Security, pension, IRA, and qualified 401(k) retirement income; taxable interest of 1,675 is taxed at 3.07%, producing 51.4225. value = 51.4225
- gpt-5.6-terra: answered 51.42
  explanation: Pennsylvania excludes this age-67 taxpayer's retirement distributions and Social Security from taxable income; the listed taxable interest of $1,675 is taxed at 3.07%, yielding $51.42. value = 51.42
- gpt-6-astra: answered 51.42
  explanation: Pennsylvania excludes Social Security and qualifying retirement distributions at age 67. Taxable interest of $1,675 is taxed at 3.07%, and total household income precludes tax forgiveness; value = 51.42
- gpt-6-luna: answered 51
  explanation: Pennsylvania generally excludes eligible retirement distributions and Social Security for a resident age 67; the $1,675 taxable interest is taxed at 3.07%, or about $51. value = 51
- gpt-6-sol: answered 51.42
  explanation: Pennsylvania exempts the listed Social Security and retirement distributions; 3.07% tax on 1675 taxable interest is 51.42; value = 51.42
- gpt-6.1-sol: answered 51.42
  explanation: Pennsylvania excludes Social Security and retirement distributions for this retirement-age head. Taxable interest of $1,675 is taxed at 3.07%, with no applicable nonrefundable credit; value = 51.42
- grok-4.3: answered 51
  explanation: PA flat tax applies only to taxable interest income of 1675. value = 51
- grok-4.7: answered 51
  explanation: Pennsylvania exempts retirement and Social Security income, applies its 3.07% rate only to 1675 of interest, and the rounded tax is 51. value = 51
- grok-build-0.1: answered 51
  explanation: Pennsylvania taxes only the 1675 in taxable interest income at the 3.07% flat rate, resulting in 51; retirement distributions, Social Security, and pensions are not taxable in PA. value = 51
- kimi-k2.6: answered 51.42
  explanation: Pennsylvania taxes interest, compensation, and business profits at a flat 3.07% rate but excludes eligible retirement distributions, pension income, and Social Security benefits for taxpayers age 59.5 or older. With wages and self-employment income unlisted (treated as 0), the only Pennsylvania taxable income is the $1,675 in taxable interest. The tax is $1,675 × 0.0307 = $51.42, and no nonrefundable credits apply. value = 51.42
- kimi-k3: answered 51.42
  explanation: PA taxable income is the listed interest of 1675; Social Security and age-eligible retirement distributions are not PA-taxable, and PA tax forgiveness is unavailable at this much higher eligibility income. 1675 at 3.07% rounds to 51.42. value = 51.42