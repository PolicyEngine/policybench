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
STATE: NC
OUTPUT: federal_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable federal income tax credits, including EITC and refundable portions of credits such as refundable CTC when applicable; exclude the ACA Premium Tax Credit

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only federal_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: NC
- tax year: 2026

Head:
- age: 48
- employer sponsored insurance premiums: $21,208
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $1,020
- other health insurance premiums: $1,020
- other medical expenses: $400
- over-the-counter health expenses: $100

Spouse:
- age: 45
- gross wages and salaries: $85,209
- bank account assets: $1,330
- fsla overtime premium: $7,746
- has employer-sponsored insurance
- hourly wage: $33
- usual weekly hours worked: 50
- other medical expenses: $200
- over-the-counter health expenses: $350
- roth 401k contributions desired: $490
- roth ira contributions desired: $201
- stock assets: $84,353
- traditional 401k contributions desired: $2,778
- traditional ira contributions desired: $130

Child 1:
- age: 11
- has employer-sponsored insurance
- other medical expenses: $250
- over-the-counter health expenses: $250

Child 2:
- age: 11
- has employer-sponsored insurance
- other medical expenses: $250
- over-the-counter health expenses: $250

Child 3:
- age: 9
- has employer-sponsored insurance
- other medical expenses: $250
- over-the-counter health expenses: $250

Tax unit:
- first home mortgage balance: $108,000

Household inputs:
- auto loan balance: $17,529
- auto loan interest: $378
- household vehicles value: $10,230

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
- child3_wic_eligible: whether Child 3 is eligible for WIC (1 if yes, 0 if no)
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_medicaid_eligible: whether Spouse is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_medicaid_eligible: whether Child 1 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_medicaid_eligible: whether Child 2 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child3_medicaid_eligible: whether Child 3 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_chip_eligible: whether Spouse is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_chip_eligible: whether Child 1 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_chip_eligible: whether Child 2 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child3_chip_eligible: whether Child 3 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- spouse_medicare_eligible: whether Spouse is eligible for Medicare (1 if yes, 0 if no)
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

ENGINE REFERENCE VALUE: $2,013.49 (engine output 2,013.4892578125)
MODELS: 45 gave a usable answer; 7 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 20 models (0 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: MFJ couple with 3 qualifying children under 17. Spouse wages $85,209 less traditional 401k $2,778 gives AGI ~$82,431 (plus small IRA deduction), well above EITC MFJ 3-child limit (~$70k), so EITC = 0. Under 2026 law (OBBBA), CTC is $2,200 per child with refundable portion up to ~$1,700, but their federal income tax liability before credits (taxable income ~$50k after ~$32k standard deduction, tax ~$5,500) exceeds the nonrefundable CTC needed, so the full $6,600 CTC is used nonrefundably and no additional (refundable) child tax credit is paid. No other refundable credits apply. value = 0
- claude-opus-4.7: answered 0
  explanation: MFJ with AGI ~$82,300 (wages $85,209 minus traditional 401k $2,778). Too high for EITC with 3 kids (limit ~$66k). CTC: 3 qualifying children under 17 = $6,000 nonrefundable CTC, fully absorbed by tax liability (standard deduction $31,500, taxable income ~$50,800, tax ~$5,600, fully offset by nonrefundable CTC, so no refundable ACTC needed). No other refundable credits. value = 0
- claude-opus-4.8: answered 0
  explanation: MFJ with 3 children, AGI ~$82,000 (wages $85,209 less traditional 401k/IRA contributions). EITC fully phased out at this income level for MFJ with 3 kids (limit ~$66,800). Tax liability is high enough that the $6,000 CTC ($2,000 x 3) is fully nonrefundable, leaving no additional child tax credit. Thus refundable federal credits are zero. value = 0
- claude-sonnet-5: answered 0
  explanation: Household AGI is roughly $85,209 wages + $7,746 overtime minus retirement deferrals (~$2,778+$490 401k, $130+$201 IRA) minus above-the-line adjustments, leaving AGI around $89,000. With 3 qualifying children, the Child Tax Credit (up to $2,000/child, refundable portion ACTC capped at $1,700/child) is fully non-refundable since regular tax liability at this income level exceeds the $6,000 total CTC, so the credit is absorbed by the nonrefundable CTC rather than the refundable ACTC. Income is far above EITC phase-out limits for a family with children (EITC max threshold ~$59,000 for 3 kids), so EITC = $0. No other refundable credits apply. Therefore total federal refundable credits = 0. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: No EITC (income far above phaseout) and the full 6,000 child tax credit is used against tax, leaving no refundable CTC or other refundable credits. value = 0
- deepseek-v4-pro: answered 0
  explanation: No refundable credits apply. EITC phases out completely at this income level ($82,301 earned income). The nonrefundable CTC fully offsets tax before a refund is needed, so Additional Child Tax Credit is $0. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: EITC is 0 because income exceeds phaseout; refundable/Additional CTC is 0 because the full 3,000 CTC is used nonrefundably. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: No refundable tax credits apply at this income level. value = 0.0
- gemini-3.1-pro-preview: answered 0
  explanation: Since the $3,000 Child Tax Credit completely applies against the tax liability and the household's AGI of $82,301 exceeds the Earned Income Tax Credit phaseout limit for 2026, there are no refundable credits. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Total refundable federal income tax credits are 0. value = 0
- gemini-3.6-flash: answered 0
  explanation: Total refundable federal income tax credits for the household. value = 0.0
- gemini-3.7-flash: answered 0
  explanation: Household has no refundable credits as income exceeds EITC limits and nonrefundable CTC covers tax; value = 0
- gemini-3.8-flash: answered 0
  explanation: Because the nonrefundable child tax credit is fully absorbed against pre-credit tax liability and income exceeds the phaseout limit for the EITC, refundable credits equal $0. value = 0
- gpt-5.4-mini: answered 0
  explanation: Income is too high for EITC with three children and the children are over age 6 for refundable-only effects already reflected at zero; no refundable federal credit remains. value = 0
- gpt-5.4-nano: answered 0
  explanation: Assuming no eligibility for refundable credits (e.g., EITC or refundable portions of other credits) given the household’s income level from wage/salary totals; ACA premium tax credit excluded by definition. Estimated refundable federal income tax credits total is value = 0.
- gpt-5.5: answered 0
  explanation: Income is too high for EITC, and using current-law post-2025 child credit rules the $1,000 child credits are nonrefundable and fully used against tax, leaving no refundable federal credits, value = 0
- grok-4.3: answered 0
  explanation: No EITC or refundable CTC qualification at this income level. value = 0
- grok-4.5: answered 0
  explanation: Tax liability before credits exceeds the 3000 CTC so no refundable ACTC remains; EITC phases out fully before AGI of 82301 for MFJ with three children; no other refundable credits apply. value = 0
- grok-build-0.1: answered 0
  explanation: EITC is $0 as earned income $90,047 exceeds 2026 MFJ phaseout end (~$67,000) for 3+ children. ACTC is $0 because federal tax before credits $5,937 exceeds total CTC $3,000 (no excess for refundable portion). value = 0
- minimax-m3: answered 0
  explanation: With household income well above EITC limits for a family of 5, EITC is $0, and additional CTC is also $0. value = 0

Cluster 2: 2,059, given by 3 models (3 of them among the benchmark's top-ranked models)
- claude-sonnet-5.5: answered 2,058.76
  explanation: The unused CTC of 6,600 - 4,541.24 = 2,058.76 is refundable as ACTC. It is under the per-child refundable cap and the 15% earned-income test. EITC is 0 because earned income of 85k is above the 3-child phase-out. value = 2058.76
- gpt-5.6-sol: answered 2,058.76
  explanation: The remaining unused portion of the 6600 child tax credit is refundable under the additional child tax credit rules, with no EITC at this income; value = 2058.76
- gpt-6-sol: answered 2,058.76
  explanation: Federal tax of 4541.24 before the child tax credit uses that much of the 6600 credit; the remaining 2058.76 is refundable, with no EITC; value = 2058.76