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
STATE: VA
OUTPUT: head_medicare_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether Head is eligible for Medicare (1 if yes, 0 if no)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only head_medicare_eligible):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: VA
- tax year: 2026

Head:
- age: 61
- bank account assets: $16,000
- employer sponsored insurance premiums: $3,589
- estate income: $25,950
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $4,800
- is disabled
- is a surviving spouse
- other health insurance premiums: $4,800
- other medical expenses: $200
- self-employment income: $-6,260
- Social Security retirement income: $36,105
- taxable IRA distributions: $26,800
- taxable private pension income: $2,030

Tax unit:
- first home mortgage balance: $47,500

Household inputs:
- household vehicles value: $5,184

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

ENGINE REFERENCE VALUE: 0 (not eligible)
MODELS: 46 gave a usable answer; 27 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 1, given by 19 models (1 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 1
  explanation: Head is age 61 (under 65) but is disabled and receives Social Security benefits; disabled individuals receiving Social Security qualify for Medicare, so Head is eligible. value = 1
- claude-fable-5.1: answered 1
  explanation: Head is disabled and receives Social Security benefits, which qualifies for Medicare under PolicyEngine's disability pathway; eligible. value = 1
- claude-haiku-4.5: answered 1
  explanation: The Head is age 61 and is disabled. Under Social Security rules, individuals who are disabled are eligible for Medicare regardless of age, and typically become eligible at age 65. However, the Head's disability status qualifies them for Medicare. Additionally, the Head is receiving Social Security retirement income ($36,105), which indicates eligibility for Social Security benefits. In the United States, individuals who receive Social Security disability benefits or have reached age 65 are eligible for Medicare. Given the Head's age of 61 combined with disabled status, the Head is eligible for Medicare. value = 1
- claude-opus-4.7: answered 1
  explanation: Head is disabled, and disabled individuals qualify for Medicare regardless of age (typically after 24 months of SSDI). value = 1
- claude-opus-4.8: answered 1
  explanation: Head is 61 and disabled. Medicare eligibility extends to disabled individuals who qualify, in addition to those 65+. Given disabled status, eligible. value = 1
- claude-opus-5: answered 1
  explanation: Head is disabled, which PolicyEngine treats as Medicare-eligible despite being under age 65. value = 1
- claude-sonnet-4.6: answered 1
  explanation: Medicare eligibility is generally available to individuals age 65 or older, or to those who are disabled (receiving Social Security Disability Insurance for at least 24 months), or to surviving spouses meeting certain criteria. The Head is listed as disabled and a surviving spouse. Disabled individuals who have received Social Security disability benefits for 24 months qualify for Medicare regardless of age. Since the Head is listed as disabled, they are eligible for Medicare under the disability pathway. value = 1
- deepseek-v4.1-flash: answered 1
  explanation: Head is disabled, and PolicyEngine treats disabled individuals as Medicare eligible. value = 1
- gemini-3.1-flash-lite-preview: answered 1
  explanation: Head is age 61 and disabled, meeting requirements for Medicare eligibility. value = 1
- glm-5.2: answered 1
  explanation: Medicare eligibility includes individuals age 65 or older and certain individuals under 65 with qualifying disabilities. The head is 61 years old and is disabled, which is a qualifying condition for Medicare under PolicyEngine rules. Eligible. value = 1
- gpt-5.4-nano: answered 1
  explanation: The head is age 61, and Medicare eligibility is assumed yes under the policy rule for disabled individuals (coverage begins when disabled under qualifying rules), so head Medicare eligible is 1; value = 1
- gpt-5.6-luna: answered 1
  explanation: Head is disabled, which qualifies Head for Medicare under the applicable disability eligibility rule despite being under age 65. value = 1
- gpt-6-astra: answered 1
  explanation: The head is eligible through the stated disability under the modeled Medicare eligibility rules. value = 1
- gpt-6-luna: answered 1
  explanation: The head is listed as disabled; under the eligibility rules applied here, disability provides Medicare eligibility before age 65, so the head is eligible. value = 1
- gpt-6.1-sol: answered 1
  explanation: The head is eligible under PolicyEngine's disability-based Medicare eligibility rule despite being younger than 65. value = 1
- grok-4.3: answered 1
  explanation: Disabled and thus eligible for Medicare. value = 1
- grok-4.7: answered 1
  explanation: Head is under 65 but is disabled, and PolicyEngine treats disability as qualifying for Medicare, so Head is eligible. value = 1
- kimi-k3: answered 1
  explanation: Under PolicyEngine rules, Medicare eligibility applies to people age 65 or older or who are disabled; the head is disabled, so eligible. value = 1
- minimax-m3: answered 1
  explanation: The Head is age 61, which is below the standard Medicare age of 65, but is listed as disabled. After 24 months of SSDI the Head would qualify. The facts state the Head is disabled, so the Head is Medicare eligible, value = 1.