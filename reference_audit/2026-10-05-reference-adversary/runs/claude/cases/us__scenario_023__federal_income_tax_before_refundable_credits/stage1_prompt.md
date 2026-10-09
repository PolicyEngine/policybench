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
OUTPUT: federal_income_tax_before_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: federal individual income tax after nonrefundable credits and before refundable credits. This subtracts nonrefundable credits actually used, including CDCC and the nonrefundable portion of CTC or other credits when applicable; it does not subtract EITC or refundable portions of credits such as refundable CTC

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only federal_income_tax_before_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: CA
- tax year: 2026

Head:
- age: 28
- gross wages and salaries: $17,443
- attends eligible educational institution for american opportunity credit
- bank account assets: $130
- employer sponsored insurance premiums: $8,089
- has american opportunity credit 1098 t or exception
- has american opportunity credit institution ein
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $300
- hourly wage: $14
- usual weekly hours worked: 24
- is disabled
- is enrolled at least half time for american opportunity credit
- is paid hourly
- is pursuing credential for american opportunity credit
- other health insurance premiums: $300
- other medical expenses: $500
- over-the-counter health expenses: $500
- pre-subsidy rent: $24,000
- roth 401k contributions desired: $490
- roth ira contributions desired: $201
- taxable 403(b) distributions: $8,000
- traditional 401k contributions desired: $2,778
- traditional ira contributions desired: $130

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

ENGINE REFERENCE VALUE: $643.43 (engine output 643.43359375)
MODELS: 44 gave a usable answer; 5 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 28 models (4 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Wages $17,443 minus pre-tax traditional 401k $2,778 gives $14,665 taxable wages; plus $8,000 taxable 403(b) distributions = $22,665 gross income. Traditional IRA deduction $130 lowers AGI to $22,535. 2026 single standard deduction (~$16,100) leaves taxable income ~$6,435, tax ~$644 at 10%. Nonrefundable portion of the American Opportunity Credit (60% of up to $2,500, plus tuition assumed 0 here still qualifies via enrollment; even a modest AOTC nonrefundable share) and the Saver's Credit (50% of eligible retirement contributions up to $2,000 = $1,000, since AGI is below the 50% threshold) offset the full tentative tax, reducing income tax after nonrefundable credits to $0. value = 0
- claude-fable-5.1: answered 0
  explanation: AGI = 17,443 wages - 2,778 traditional 401k + 8,000 taxable 403(b) - 130 IRA deduction = 22,535. Less 2026 single standard deduction 16,100 gives taxable income 6,435; tax at 10% = 643.5. Nonrefundable Saver's Credit (50% rate at this AGI, $2,000 contribution cap = $1,000) exceeds liability; AOTC is 0 with no tuition expenses; elderly/disabled credit phases out to 0. Tax after nonrefundable credits = 0. value = 0
- claude-haiku-4.5: answered 0
  explanation: Gross wages: $17,443. Standard deduction for single filer (2026): $14,600. Taxable income before above-the-line deductions: $17,443. Traditional 401(k) contribution: $2,778. Traditional IRA contribution: $130. Total above-the-line deductions: $2,908. Income subject to tax: $17,443 - $2,908 - $14,600 = -$65. Negative taxable income results in zero federal income tax. The American Opportunity Credit would provide up to $2,500 in nonrefundable credit value, but with zero tax liability before refundable credits, no nonrefundable credits can be applied. Federal income tax before refundable credits = $0, value = 0
- claude-opus-4.7: answered 0
  explanation: Wages $17,443 minus traditional 401k $2,778 = $14,665 W-2 wages. Plus 403(b) distribution $8,000 = $22,665. Minus traditional IRA $130 = AGI $22,535. Standard deduction (single 2026) ~$16,100. Taxable income ~$6,435. Tax at 10% ~$644. American Opportunity Credit nonrefundable portion (60% of $2,500 = $1,500) fully offsets the tax, reducing federal income tax after nonrefundable credits to 0. value = 0
- claude-opus-4.8: answered 0
  explanation: Single filer, 2026. Gross income: wages $17,443 + taxable 403(b) distributions $8,000 = $25,443. Above-the-line deductions: traditional 401k $2,778 and traditional IRA $130, reducing AGI to about $22,535. Standard deduction (~$16,100 for single in 2026) brings taxable income to ~$6,435. Tax on this in the 10% bracket is ~$644. The American Opportunity Credit nonrefundable portion (40% refundable, 60% nonrefundable) fully offsets this small tax liability, since the head is a half-time degree-seeking student with qualified 1098-T expenses and the maximum AOTC is up to $2,500. The nonrefundable portion alone exceeds the ~$644 tax, reducing federal income tax after nonrefundable credits to 0. value = 0
- claude-opus-5: answered 0
  explanation: AGI: wages $17,443 minus traditional 401k $2,778 = $14,665 taxable wages, plus $8,000 taxable 403(b) distributions, minus traditional IRA deduction $130 = about $22,535. Single standard deduction 2026 (~$16,100) leaves taxable income ~$6,435, tax ~$644 at 10%. American Opportunity Credit nonrefundable portion (up to $1,500) offsets the entire liability. value = 0
- claude-opus-5.5: answered 0
  explanation: AGI is $22,535: wages $17,443 minus traditional 401(k) $2,778, plus 403(b) distributions $8,000, minus traditional IRA $130. Taxable income is $22,535 minus the $16,100 standard deduction, or $6,435, taxed at 10% for $643.50. The saver's credit is 50% of $2,000 of contributions, or $1,000. This assumes the 403(b) distributions do not reduce eligible contributions. It is capped at the $643.50 of tax, leaving no tax. The American Opportunity Credit is $0 because no qualified tuition is listed. value = 0
- claude-sonnet-5: answered 0
  explanation: Gross wages $17,443 plus taxable 403(b) distribution $8,000 = $26,443 total income. Traditional 401k contribution $2,778 reduces AGI. Standard deduction for single filer 2026 (~$16,100) exceeds taxable income after adjustments, and remaining taxable income is further offset by the American Opportunity Credit (nonrefundable portion) which zeroes out any residual tax liability. Taxable income after standard deduction is near $0, and any small tax liability is fully offset by the nonrefundable portion of the AOTC, resulting in $0 federal income tax before refundable credits. value = 0
- claude-sonnet-5.5: answered 0
  explanation: Single filer. Wages 17,443 less 2,778 traditional 401(k) = 14,665. Add 8,000 taxable 403(b) distribution and subtract the 130 IRA deduction: AGI ≈ 22,535. After the ~16,100 standard deduction, taxable income ≈ 6,435 and tax ≈ 644. The saver's credit is at the 50% rate (AGI under ~24,250) on the $2,000 maximum eligible contributions, so it is about 1,000. It is limited to the tax owed and wipes it out. No American Opportunity Credit because no qualified expenses are listed. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Wages for income tax after pre-tax 401k ($2,778) and pre-tax employer-sponsored health insurance ($8,089) are $6,576; plus taxable 403(b) distribution of $8,000 minus traditional IRA deduction of $130 gives AGI of $14,446. This is below the 2026 single standard deduction (~$15,750), so taxable income is 0 and tax before refundable credits is 0. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: AGI is 17,443 - 2,778 + 8,000 - 130 = 22,535. Standard deduction 15,750 gives taxable income 6,785. Tax before credits is 678.5. Saver's credit of 1,000 (50% of 2,000 contributions) reduces tax to 0. value = 0
- gemini-3-flash-preview: answered 0
  explanation: With an Adjusted Gross Income (AGI) of $22,535 (gross wages of $17,443 and taxable distributions of $8,000, less $2,908 in traditional 401k/IRA contributions), and estimated 2026 standard deduction and personal exemptions totaling approximately $14,000, taxable income is roughly $8,535. The resulting tax at the 10% bracket is approximately $853.50. However, the Head's retirement contributions qualify for the Saver's Credit at a 50% rate ($1,000), which fully offsets the tax liability before refundable credits. value = 0.0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: After deductions, taxable income is 0. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: Adjusted Gross Income (AGI) is low enough that the standard deduction and the nonrefundable Retirement Savings Contributions Credit (Saver's Credit) completely offset any tax liability. value = 0
- gemini-3.5-flash: answered 0
  explanation: With an Adjusted Gross Income (AGI) of $14,446, the federal income tax before credits of approximately $110 is fully offset by the non-refundable Saver's Credit. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Federal income tax before refundable credits is $0 after standard deduction and nonrefundable credits for the 2026 tax year. value = 0
- gemini-3.7-flash: answered 0
  explanation: The taxpayer's adjusted gross income after allowable pre-tax deductions and standard deduction results in zero taxable income, yielding a federal income tax before refundable credits of $0. value = 0
- gpt-5.4-mini: answered 0
  explanation: With $17,443 of wages and $8,000 of taxable 403(b) distributions, the household’s federal taxable income is still offset by the standard deduction and the head’s AOTC-related nonrefundable credit can fully eliminate any small remaining income tax; no federal income tax remains before refundable credits. value = 0
- gpt-6-luna: answered 0
  explanation: Estimated taxable income after the standard deduction is low, and the nonrefundable retirement-saver credit from the listed contributions is sufficient to offset the remaining federal income tax; value = 0
- gpt-6-sol: answered 0
  explanation: The nonrefundable retirement-savings credit offsets the modest federal tax on income remaining after deductions; value = 0
- gpt-6.1-sol: answered 0
  explanation: Estimated adjusted gross income is $14,446 after pretax employer-plan premiums and deductible retirement contributions, including the $8,000 distribution. The single standard deduction eliminates taxable income; disability exempts the distribution from the early-distribution penalty. value = 0
- grok-4.3: answered 0
  explanation: Low taxable income after deductions and credits for single filer with wages under standard deduction threshold yields zero tax liability before refundables. value = 0
- grok-4.6: answered 0
  explanation: Single AGI is $22,535 after the $2,778 traditional 401k deferral, $8,000 taxable 403(b) distribution, and $130 IRA deduction. 2026 taxable income after the standard deduction and personal exemption is about $8,900, for roughly $890 of tax that is fully offset by a $1,000 nonrefundable saver's credit on the retirement contributions. value = 0
- inkling: answered 0
  explanation: AGI is about $14,446 after subtracting pre-tax 401(k), employer health premiums, and the traditional IRA deduction; taxable income falls to $0 after the $16,100 standard deduction. The Saver’s Credit and any education credits can only offset tax to $0, leaving no tax liability before refundable credits. value = 0
- minimax-m3: answered 0
  explanation: Wages $17,443 minus traditional 401k $2,778 = $14,665 taxable wages; plus $8,000 403(b) distribution minus $130 traditional IRA = $22,535 AGI. Standard deduction ~$15,400 yields taxable income ~$7,135, taxed at 10% = $713.50. AOTC nonrefundable portion ($1,500) is limited to tax liability, fully using $713.50. Federal income tax before refundable credits = $0. value = 0
- ox-alpha: answered 0
  explanation: AGI = wages $17,443 − $2,778 traditional 401(k) − $130 traditional IRA + $8,000 taxable 403(b) = $22,535. After the ~$16,100 single standard deduction, taxable income is ~$6,435, taxed at 10% ≈ $644. The nonrefundable saver's credit (50% rate at this AGI × $2,000 cap on $2,908 contributions) = $1,000, which fully offsets the tax; AOC is $0 since no qualified tuition expenses are reported. Tax after nonrefundable credits floors at zero. value = 0
- qwen-3.7-max: answered 0
  explanation: Head is 28 with gross wages of $17,443 and taxable 403(b) distributions of $8,000. Total gross income = $17,443 + $8,000 = $25,443. Traditional 401(k) contributions of $2,778 reduce AGI: $25,443 - $2,778 = $22,665. Standard deduction for single filer in 2026 is approximately $15,750. Taxable income = $22,665 - $15,750 = $6,915. Federal tax before credits (10% bracket) = $691.50. Traditional IRA contribution of $130 may be deductible, reducing taxable income further to ~$6,785 and tax to ~$678.50. No CDCC (no qualifying child). Nonrefundable education credit (American Opportunity Credit): up to $2,500 available; since tax liability is only ~$678.50, the nonrefundable portion reduces liability to $0. value = 0.0
- qwen3.8-max: answered 0
  explanation: Income is too low for regular federal income tax after the standard deduction, and the American Opportunity Credit is nonrefundable here; no additional child tax credit is available for this childless household. value = 0