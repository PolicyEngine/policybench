You are a reference adversary for a US tax-and-benefit benchmark. Each benchmark question gives a household and asks for policy quantities for tax year 2026. A microsimulation engine produced the reference answer. On the question below, a cluster of AI models answering from memory, without tools, agreed on an answer other than the reference. Agreement among models proves nothing, and neither does the engine. Your job is to find out what the law gives.

This is stage 1 of 2. In this stage you work the answer out yourself from primary law, before you see anything about how the engine computed its value.

How to work:
1. Use web search and web fetch to find and read primary law in force for tax year 2026: statutes, regulations, official agency publications, and official forms and their instructions. Prefer the issuing government's own site.
2. Apply the household prompt's conventions exactly as the models were told them: treat any unlisted numeric input as 0 and any other unlisted fact, boolean or status as false; assume tax filing and program take-up when required; do not infer unlisted income, expenses, assets, benefit receipt, rent or health coverage.
3. Read the output definition literally. It decides which people, tax units, returns, taxes, credits or benefits the number covers. Where it lists components, decide for each candidate amount whether the definition includes it. Where the household holds more than one tax unit or return, decide from the definition which of them the number covers.
4. Cite every rule you rely on: the source, a pinpoint (section, line, table or page), the URL you read, the publication or effective date, and a short verbatim quote. The reference's law was frozen on 2026-07-03: set pre_freeze to true if the source was published before that date, false if after, and null if you cannot tell. If an amount for 2026 (a standard deduction, bracket, threshold, rate base or allotment) had not been published before 2026-07-03, say so in computation and say what had been published.
5. Do not consult PolicyEngine or PolicyBench in any form: not policyengine.org, policybench.org, their GitHub repositories, their documentation, their package source, or any calculator built on them. Do not fetch anything from these domains: policybench.org, www.policybench.org, policyengine.org, www.policyengine.org, github.com, raw.githubusercontent.com. When your search tool accepts domains to exclude (blocked_domains), pass all of these domains on every search, so that no result comes from them: a search whose results list or name PolicyEngine or PolicyBench voids your answer. Do not rely on any calculator or estimate built by an AI model. A citation of any of these sources voids your answer.
6. Say which answer the law supports: "reference", "consensus", "neither", or "both_readings" (the reference under one reasonable reading of the definition or the facts, the consensus under another).
7. In definition_reading, say how you read the output definition for this household. In ambiguity, describe any second reading that the definition or the household prompt genuinely admits, and the answer it gives; use "" if there is none.
8. independent_answer is your own number (1 or 0 for an eligibility output). Use null only when the stated facts and the law leave it genuinely undetermined, and say why in ambiguity.

Some output definitions mention PolicyEngine (for example "eligible for Medicaid under PolicyEngine rules"). Work those from the law as well; if the mention could change the answer, say so in ambiguity.

Return only the JSON object the schema asks for.

TAX YEAR: 2026    REFERENCE LAW FROZEN: 2026-07-03
STATE: CO
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: CO
- tax year: 2026

Head:
- age: 66
- gross wages and salaries: $4,088
- bank account assets: $2,800
- employer sponsored insurance premiums: $8,389
- has employer-sponsored insurance
- hourly wage: $2
- usual weekly hours worked: 40
- other medical expenses: $4,500
- over-the-counter health expenses: $500
- roth 401k contributions desired: $3
- roth ira contributions desired: $1
- tax exempt private pension income: $7
- taxable private pension income: $553
- traditional 401k contributions desired: $15
- traditional ira contributions desired: $1

Tax unit:
- first home mortgage balance: $43,000

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

ENGINE REFERENCE VALUE: $19.00
MODELS: 46 gave a usable answer; 0 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 39 models (5 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Colorado 2026 refundable credits considered: CO EITC (federal EITC-based). Head is 66, over the age-64 cap for childless federal EITC... actually federal childless EITC requires age 25-64, so head is ineligible for federal EITC and thus CO EITC = 0. No children, so no CO child tax credit or family affordability credit. Income is too low to trigger other credits and no qualifying expenses (no childcare) exist. Total refundable state credits value = 0
- claude-haiku-4.5: answered 0
  explanation: Colorado does not have state-level refundable tax credits for individuals. While Colorado offers various tax credits (such as the dependent exemption credit, earned income tax credit, and others), the primary refundable credit would be the federal Earned Income Tax Credit. At the state level, Colorado's credits are generally non-refundable or produce only non-refundable amounts against state income tax liability. This household has limited income and would have minimal Colorado state tax liability, but no refundable state credits apply in 2026. value = 0
- claude-opus-4.8: answered 0
  explanation: Colorado refundable individual income tax credits (e.g., state EITC, TABOR-related refundable credits) require qualifying earned income and filing conditions. With very low wages ($4,088), pension income, and no qualifying children or other refundable-credit triggers given, no refundable state credits apply. value = 0
- claude-opus-5.5: answered 0
  explanation: There is no federal EITC, so there is no Colorado EITC. With no children, the Colorado CTC and family affordability credit do not apply. A 2026 TABOR sales tax refund is not assumed here, which is a possible source of error. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Colorado's main refundable state income tax credits include the Colorado Earned Income Tax Credit (CO EITC) and the Colorado Child Tax Credit. For 2026, the CO EITC is a percentage of the federal EITC. The head is age 66 with gross wages of $4,088. For federal EITC purposes, there are no qualifying children listed, and for childless EITC the age limit is 25–64 (for tax year 2026, reverting from the temporary expansion). At age 66, the head exceeds the upper age limit of 64 for the childless federal EITC, so no federal EITC is available, and therefore no CO EITC. No children are listed, so the Colorado Child Tax Credit does not apply. No other Colorado refundable credits are applicable based on the household facts provided. Total refundable state credits = $0. value = 0
- claude-sonnet-5.5: answered 0
  explanation: No Colorado refundable credit applies to this household. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Colorado EITC requires federal EITC eligibility, which is unavailable at age 66, and no child-related refundable credits apply; no other Colorado refundable credit is available. value = 0
- deepseek-v4-pro: answered 0
  explanation: No qualifying children for state EITC (federal EITC is $0) and no other refundable credits apply. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: No Colorado refundable credits apply to this single senior household with no qualifying children. value = 0.0
- deepseek-v4.1-flash: answered 0
  explanation: No federal EITC, so Colorado EITC is $0; no other refundable credits. value = 0
- gemini-3-flash-preview: answered 0
  explanation: The household does not qualify for any state refundable credits such as the Colorado EITC (since they do not qualify for the federal EITC) or child-related credits. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household does not meet requirements for Colorado state refundable credits based on income and composition. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: The household has no qualifying expenses reported for the Colorado PTC rebate, resulting in zero state refundable credits. value = 0
- gemini-3.5-flash: answered 0
  explanation: The household does not qualify for any state refundable credits because they do not qualify for the federal Earned Income Tax Credit. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: Total refundable state individual income tax credits are $0.00. value = 0
- gemini-3.6-flash: answered 0
  explanation: Head qualifies for $0 in Colorado refundable income tax credits. value = 0
- gemini-3.7-flash: answered 0
  explanation: The household has no qualifying children and zero federal EITC, resulting in $0 in Colorado refundable credits. value = 0
- gemini-3.8-flash: answered 0
  explanation: Head does not qualify for the federal EITC or state CTC, resulting in zero Colorado refundable tax credits: value = 0
- glm-5.2: answered 0
  explanation: The head is 66 years old, which makes them ineligible for the federal Earned Income Tax Credit (EITC) for filers without qualifying children (which requires being under age 65), so the Colorado EITC is $0. No other refundable state credits apply. value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable Colorado income tax credits are triggered by the reported facts, so refundable state credits are zero. value = 0
- gpt-5.4-nano: answered 0
  explanation: No refundable state credits (e.g., credits requiring earned income or qualifying children) are expected with the provided facts; value = 0
- gpt-5.5: answered 0
  explanation: No facts establish eligibility for a refundable Colorado income tax credit such as child-based, earned-income, property/rent/heat, or other refundable credits, so refundable state credits are estimated as zero. value = 0
- gpt-5.6-luna: answered 0
  explanation: No qualifying Colorado refundable income-tax credit applies to this household; value = 0
- gpt-5.6-sol: answered 0
  explanation: The household has no federal EITC amount supporting a Colorado EITC and no listed expenses or dependents supporting another refundable Colorado credit; value = 0
- gpt-5.6-terra: answered 0
  explanation: No qualifying Colorado refundable credit is supported by the listed facts; value = 0
- gpt-6-luna: answered 0
  explanation: No Colorado refundable income-tax credit is supported by the reported facts; the Head has no qualifying child and is not eligible for the childless EITC at age 66. value = 0
- gpt-6-sol: answered 0
  explanation: No qualifying dependents or reported housing costs establish a Colorado refundable credit; value = 0
- gpt-6.1-sol: answered 0
  explanation: No qualifying children, age-eligible earned-income credit, or qualifying property-tax, rent, or heating payments are reported. value = 0
- grok-4.3: answered 0
  explanation: No qualifying state refundable credits. value = 0
- grok-4.5: answered 0
  explanation: No federal EITC to match with Colorado EITC; no children or other qualifying circumstances for Colorado refundable credits. value = 0
- grok-4.6: answered 0
  explanation: Colorado EITC is a percentage of federal EITC, which is $0. No property tax or rent is listed, so the senior PTC rebate is $0. value = 0
- grok-4.7: answered 0
  explanation: Colorado EITC is a percentage of federal EITC, which is zero. There are no children for the Colorado CTC, and no listed rent, property tax, or heat expense for a senior rebate. value = 0
- inkling: answered 0
  explanation: No Colorado child tax credit dependents; federal EITC is $0 due to age, so the state EITC is also $0. value = 0
- kimi-k2.6: answered 0
  explanation: No refundable Colorado income tax credits are indicated by the listed facts. The head is age 66 with no dependents or qualifying expenses, so no state EITC or other refundable credits are generated. value = 0
- kimi-k3: answered 0
  explanation: No federal EITC or CTC exists to base Colorado refundable credits on, and no qualifying child, child-care expense, or other Colorado refundable income tax credit is indicated. value = 0
- minimax-m3: answered 0
  explanation: No Colorado refundable credits apply with this income level and no qualifying children or other eligibility factors. value = 0
- ox-alpha: answered 0
  explanation: Colorado's refundable credits track federal ones: the CO EITC is a percentage of federal EITC ($0 because Head is 66 and childless), the CO CTC requires qualifying children ($0), and no sales-tax (TABOR) refund applies for this tax year under the stated assumptions, totaling $0. value = 0
- qwen-3.7-max: answered 0
  explanation: No Colorado refundable credits apply. The household has no qualifying children for the Colorado Child Tax Credit, no earned income large enough to trigger a meaningful state EITC, and no other qualifying characteristics for refundable credits listed in the facts. value = 0
- qwen3.8-max: answered 0
  explanation: With no Colorado tax liability and no applicable refundable state credits indicated by the facts, the refundable credit amount is zero. value = 0.0