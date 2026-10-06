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
OUTPUT: state_income_tax_before_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: state individual income tax after nonrefundable credits and before refundable credits, excluding local income and payroll taxes

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_income_tax_before_refundable_credits):
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

ENGINE REFERENCE VALUE: $12.78 (engine output 12.776718139648438)
MODELS: 44 gave a usable answer; 1 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 23 models (0 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: CA AGI: wages $17,443 minus traditional 401k $2,778 = $14,665 wages, plus taxable 403(b) distributions $8,000, minus traditional IRA deduction $130 = ~$22,535. CA standard deduction for single (~$5,700 in 2026) leaves taxable income ~$16,800; tax at 1-2% brackets is roughly $200, which is fully offset by the CA personal exemption credit (~$154) and renter's credit ($60) plus rounding; with income this low, remaining CA tax after nonrefundable credits is effectively 0. value = 0
- claude-haiku-4.5: answered 0
  explanation: California's standard deduction for 2026 is $5,202 for a single filer. Gross wages and salaries of $17,443 minus the standard deduction of $5,202 equals $12,241 in California taxable income. However, California's California Earned Income Tax Credit (CalEITC) provides a nonrefundable tax credit. With gross income of $17,443 and filing status single with zero dependents, the taxpayer qualifies for CalEITC with a credit amount that more than offsets the tax liability from the $12,241 in taxable income. The state income tax before refundable credits (after nonrefundable credits like CalEITC) results in $0 tax liability. value = 0
- claude-opus-4.7: answered 0
  explanation: CA AGI approx = wages $17,443 + 403(b) distribution $8,000 - traditional 401k $2,778 - traditional IRA $130 ≈ $22,535. CA standard deduction (single 2026) ~$5,540. Taxable income ~$17,000, tax ~$170 at 1-2% brackets. CA nonrefundable personal exemption credit (~$149) plus disabled-related considerations reduce tax. After the personal exemption credit, tax before refundable credits is approximately $0. value = 0
- claude-opus-4.8: answered 0
  explanation: CA AGI: wages $17,443 + taxable 403(b) distributions $8,000 = $25,443, minus traditional 401k $2,778 and traditional IRA $130 = $22,535. CA standard deduction (single) ~$5,540 leaves taxable income ~$16,995. Tax at CA rates (1% up to ~$10,756, 2% above) is roughly $108+$125 = ~$233 gross. CA personal exemption credit (~$149) reduces this. However, taxpayer's income qualifies; after exemption credit the tax is reduced but not fully eliminated by standard credits. Given low income and the personal exemption credit plus rounding, CA income tax after nonrefundable credits is effectively $0. value = 0
- claude-opus-5: answered 0
  explanation: CA AGI ≈ $22,535 less standard deduction (~$5,800) leaves ~$16,700; tax at 1%/2% brackets ≈ $200, fully offset by the CA personal exemption credit (~$150) and remaining liability eliminated; PolicyEngine yields no positive liability after nonrefundable credits. value = 0
- claude-sonnet-4.6: answered 0
  explanation: For California 2026, we calculate the taxable income and resulting tax. The head's income sources are: gross wages $17,443 and taxable 403(b) distributions $8,000, totaling $25,443 gross income. Pre-tax deductions reduce AGI: traditional 401k contributions $2,778 (reduces federal AGI but CA follows federal treatment for 401k deferrals). CA AGI = $25,443 - $2,778 = $22,665. CA does not conform to Roth 401k or Roth IRA deductions (Roth contributions are after-tax). Traditional IRA contribution of $130 is deductible for CA as well (CA conforms to IRA deductions). CA AGI = $22,665 - $130 = $22,535. CA Standard Deduction for single filer in 2026: CA standard deduction is $5,540 (2025 is ~$5,540 indexed; using ~$5,540 for 2026). CA taxable income = $22,535 - $5,540 = $16,995. CA income tax on $16,995 for single filer: CA 2025/2026 brackets for single: 1% on first $10,756; 2% on $10,756–$25,499. Tax = $10,756 × 1% + ($16,995 - $10,756) × 2% = $107.56 + $6,239 × 2% = $107.56 + $124.78 = $232.34. CA nonrefundable personal exemption credit for single: ~$144 (2025 value indexed; approximately $144–$149 for 2026). CA also has a credit for the disabled: an additional exemption credit of ~$144 for a blind/disabled person. Total exemption credits ≈ $144 + $144 = $288. Tax after nonrefundable credits = $232.34 - $288 = -$55.66, which floors at $0. Therefore, state income tax before refundable credits = $0. value = 0
- claude-sonnet-5: answered 0
  explanation: CA gross income: wages $17,443 + taxable 403(b) distribution $8,000 = $25,443. Adjustments: traditional 401k $2,778 pretax reduces wages for CA AGI (CA conforms to federal 401k exclusion), so CA wages = 17,443-2,778=14,665; plus 403(b) distribution 8,000 = 22,665 AGI. Traditional IRA deduction $130 reduces further to 22,535. CA standard deduction for single filer 2026 ~ $5,540, leaving taxable income ~$16,995. Applying CA's low tax brackets (1%-2%) yields tax of roughly $250-$300 before credits, but CA's nonrefundable personal exemption credit (~$149) and the disability-related credits, along with the American Opportunity education credit (federal only, not CA), reduce this further. Additionally, CA's Nonrefundable renter's credit and standard/personal exemption credits offset the small tax liability, bringing state income tax before refundable credits down to $0 after applying the standard personal exemption credit which exceeds the computed tax liability given the low taxable income. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: California taxable income uses the same AGI of $14,446 less the CA single standard deduction (~$5,540) = $8,906, taxed at 1% = $89.06, which is fully offset by the personal exemption credit (~$144), leaving state income tax before refundable credits of 0. value = 0
- deepseek-v4-pro: answered 0
  explanation: CA AGI = $14,446, standard deduction = $5,363, taxable income = $9,083. Tax = 1% * $9,083 = $90.83. Personal exemption credit = $148 (nonrefundable) reduces tax to $0. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: California standard deduction for single filers exceeds AGI. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: California state income tax on the small amount of taxable income is fully offset by the state personal exemption credit. value = 0
- gemini-3.5-flash: answered 0
  explanation: CA taxable income of $8,846 results in a state tax of $88, which is fully offset by CA non-refundable credits including the personal exemption credit and renter's credit. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: California state income tax before refundable credits is $0. value = 0
- gemini-3.7-flash: answered 0
  explanation: After the California standard deduction and personal exemption credits, California state income tax before refundable credits is $0. value = 0
- gpt-5.4-mini: answered 0
  explanation: California tax on the household’s income is wiped out by the standard deduction/personal exemption and available credits at this income level, leaving no state income tax before refundable credits. value = 0
- gpt-5.6-luna: answered 0
  explanation: Estimated California income tax after the personal exemption and applicable renter credit is fully offset, leaving no state income tax before refundable credits. value = 0
- gpt-5.6-terra: answered 0
  explanation: California income tax on the low taxable income is fully offset by available nonrefundable personal-exemption and renter credits. value = 0
- gpt-6.1-sol: answered 0
  explanation: California's single standard deduction and personal exemption credit eliminate the estimated state income tax on adjusted gross income of $14,446. value = 0
- grok-4.3: answered 0
  explanation: CA standard deduction and low income result in zero state tax before credits. value = 0
- grok-4.6: answered 0
  explanation: CA AGI of $22,535 less an itemized medical deduction of about $7,499 leaves taxable income near $15,000 and pre-credit tax of about $190, which is fully offset by the personal exemption credit and the $60 nonrefundable renter's credit. value = 0
- inkling: answered 0
  explanation: California taxable income is roughly $8,720 (AGI ~$14,446 minus CA standard deduction ~$5,726), producing about $87 in tax that is fully offset by the personal exemption credit (~$149), leaving $0. value = 0
- qwen-3.7-max: answered 0
  explanation: Federal AGI: $17,443 wages + $8,000 taxable 403(b) distributions = $25,443 (traditional 401k/IRA contributions are assumed through employer or deductible). California taxable income after standard deduction ($11,784 for head of household with dependent) = $25,443 - $11,784 = $13,659. CA tax on $13,659: first $10,483 at progressive rates up to ~$231.71, then ($13,659 - $10,483) = $3,176 × 6% = $190.56, total ~$422.27. With $0 nonrefundable credits, tax before refundable credits = $422.27. However, given the household has a disabled head with low income and student status, applying the California renter credit (nonrefundable, up to $60) and other personal exemption credits ($144 for head + $144 for disabled = $288), the tax after nonrefundable credits = $422.27 - $288 = $134.27. Wait — personal exemption credits are nonrefundable in CA. CA personal exemption credit = $144 (single/head) + $144 (disabled) = $288. Tax = $422.27 - $288 = $134.27. But reconsidering: standard deduction for single filer in CA 2026 ~ $5,994. Taxable income = $25,443 - $5,994 = $19,449. Tax brackets (single): 1% up to $10,412 = $104.12, 2% $10,412-$24,684 on $9,037 = $180.74, total = $284.86. After personal exemption credits ($144 + $144 = $288): $284.86 - $288 = $0 (floored at 0 since nonrefundable). So state income tax before refundable credits = 0. Actually with no dependents, filing as single: personal exemption = $144 + $144 (disabled) = $288. Tax = $284.86, minus $288 = 0, but since these are nonrefundable credits, the floor is $0. The refundable renter credit of $60 and EITC would be refundable credits. So state_income_tax_before_refundable_credits = 0. Let me recalculate properly: AGI = $25,443. CA standard deduction (single, 2026 est) ~ $6,000. Taxable income = $19,443. CA tax (single brackets): 1% on first ~$10,400 = $104, 2% on $10,400-$19,443 ($9,043) = $180.86. Total tax = $284.86. Personal exemption credit = $144 (single) + $144 (disabled) = $288. Tax after nonrefundable credits  [... 40 more characters cut]
- qwen3.8-max: answered 0
  explanation: California income tax is zero after the standard deduction and nonrefundable credits at this income level. value = 0