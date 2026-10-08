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
STATE: AL
OUTPUT: state_income_tax_before_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: state individual income tax after nonrefundable credits and before refundable credits, excluding local income and payroll taxes

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_income_tax_before_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: AL
- tax year: 2026

Head:
- age: 77
- bank account assets: $1
- is disabled
- other medical expenses: $150
- over-the-counter health expenses: $100
- Social Security retirement income: $18,708
- tax-exempt interest income: $4,734
- unreimbursed employee business expenses: $297

Tax unit:
- first home mortgage balance: $1,000

Household inputs:
- household vehicles value: $8,370

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

ENGINE REFERENCE VALUE: $4.68 (engine output 4.679999828338623)
MODELS: 46 gave a usable answer; 1 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 45 models (5 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Alabama fully exempts Social Security benefits, and tax-exempt interest is not taxable. The head's only income sources ($18,708 Social Security and $4,734 tax-exempt interest) are excluded from Alabama taxable income, leaving zero AL AGI and zero tax. value = 0
- claude-fable-5.1: answered 0
  explanation: Alabama fully exempts Social Security benefits and tax-exempt interest is not taxable; Alabama taxable income is 0, so state tax is 0. value = 0
- claude-haiku-4.5: answered 0
  explanation: In Alabama for 2026, the individual has Social Security retirement income of $18,708, tax-exempt interest income of $4,734, and unreimbursed employee business expenses of $297. Social Security income is not subject to federal income tax in this case (since only a portion would be included and here the calculation results in no taxable portion). Tax-exempt interest is excluded from taxable income. Alabama allows standard deductions and exemptions for retirees. With the combination of the standard deduction, elderly exemptions (age 77), and the nature of the income, the taxable income to Alabama results in no state income tax liability after applying available nonrefundable credits. value = 0.0
- claude-opus-4.7: answered 0
  explanation: Alabama does not tax Social Security retirement income, and tax-exempt interest is also not taxed. Head has no other taxable income. Therefore Alabama taxable income is $0 and state income tax before refundable credits is $0. value = 0
- claude-opus-4.8: answered 0
  explanation: Alabama does not tax Social Security benefits, and Social Security retirement income ($18,708) plus tax-exempt interest ($4,734) are not part of Alabama taxable income. With no taxable wages or other taxable income, Alabama AGI is $0, leaving no state income tax liability. value = 0
- claude-opus-5: answered 0
  explanation: Alabama exempts Social Security benefits and taxes no tax-exempt interest; Alabama taxable income is 0. value = 0
- claude-opus-5.5: answered 0
  explanation: Alabama exempts Social Security income. With no other taxable income, Alabama taxable income is $0. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Alabama state income tax for 2026: The head is a 77-year-old disabled single filer. Alabama exempts Social Security income entirely. The only income items are Social Security retirement income ($18,708) and tax-exempt interest ($4,734), both of which are excluded from Alabama taxable income. Social Security benefits are fully exempt from Alabama income tax, and tax-exempt interest is not included in Alabama gross income. With no taxable income, gross Alabama income tax is $0. No nonrefundable credits are needed. State income tax before refundable credits = $0. value = 0
- claude-sonnet-5: answered 0
  explanation: Alabama does not tax Social Security retirement income, and the household's only income sources are Social Security benefits ($18,708) and tax-exempt interest ($4,734), neither of which is subject to Alabama state income tax. With no taxable income under Alabama law, the state individual income tax before refundable credits is $0. value = 0
- claude-sonnet-5.5: answered 0
  explanation: Alabama does not tax Social Security benefits. Federal AGI is 0, so there is no state taxable income. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Alabama exempts Social Security retirement benefits from income tax and tax-exempt interest is excluded; with no other taxable income and standard/elderly deductions exceeding any includable amount, state taxable income is $0, so tax before credits = $0. value = 0
- deepseek-v4-pro: answered 0
  explanation: Alabama exempts Social Security from state income tax, and tax-exempt interest is also not taxed. With no other income, state taxable income is $0. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Alabama excludes Social Security from income; even treating the tax-exempt interest as Alabama income, the single filer age 65+ standard deduction ($4,500) plus Alabama personal exemption ($1,500) exceeds Alabama AGI, leaving no taxable income. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: Alabama excludes Social Security benefits and federal tax-exempt interest from taxable income; after standard deduction and personal exemption, taxable income is zero. value = 0
- gemini-3-flash-preview: answered 0
  explanation: Alabama does not tax Social Security benefits, and the head's other income ($4,734) is below Alabama's total standard deduction and personal exemption amount (which is at least $5,000 for a single filer over 65). value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: In Alabama, Social Security income is exempt from state income tax, and the taxable income is below the threshold for state tax liability. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: Alabama exempts Social Security benefits from state income tax, leaving no taxable income. value = 0
- gemini-3.5-flash: answered 0
  explanation: Alabama does not tax Social Security benefits, and tax-exempt interest is also excluded, resulting in a state taxable income of $0.00. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: State taxable income is below the threshold for Alabama state income tax. value = 0
- gemini-3.6-flash: answered 0
  explanation: Alabama exempts Social Security benefits from state income tax, resulting in zero taxable state income and $0 state income tax before refundable credits. value = 0
- gemini-3.7-flash: answered 0
  explanation: Alabama exempts Social Security benefits and Head has no other taxable income, resulting in $0 state income tax. value = 0
- gemini-3.8-flash: answered 0
  explanation: Alabama exempts Social Security retirement income, leaving no taxable income, so state income tax before refundable credits is $0. value = 0
- glm-5.2: answered 0
  explanation: The household's only income is Social Security retirement income ($18,708) and tax-exempt interest income ($4,734). Alabama exempts Social Security benefits and federally tax-exempt interest from state income tax. Thus, Alabama adjusted gross income is $0, resulting in no state income tax liability before refundable credits. value = 0.0
- glm-5.3: answered 0
  explanation: Alabama fully exempts Social Security benefits, and the tax-exempt interest is not included in the Alabama AGI base, so Alabama taxable income (before the standard deduction and personal exemption) is $0 and Alabama income tax is $0; value = 0
- gpt-5.4-mini: answered 0
  explanation: Alabama income tax is zero here because only Social Security and tax-exempt interest are reported, with no taxable wages or other Alabama-taxable income. value = 0
- gpt-5.4-nano: answered 0
  explanation: Alabama income tax after nonrefundable credits is 0 because taxable income after deductions is effectively 0 for the given Social Security and interest amounts under the simplified policy-based calculation; value = 0
- gpt-5.5: answered 0
  explanation: Alabama exempts Social Security retirement benefits, and no taxable Alabama income is listed after applying available personal/standard deductions, so state income tax before refundable credits is zero. value = 0
- gpt-5.6-luna: answered 0
  explanation: Alabama taxable income is zero because the household has no taxable federal income and the reported Social Security and tax-exempt interest do not produce Alabama taxable income here. value = 0
- gpt-5.6-sol: answered 0
  explanation: Alabama exempts Social Security retirement benefits, and the reported tax-exempt interest does not produce Alabama taxable income under the modeled facts; value = 0
- gpt-6-astra: answered 0
  explanation: Alabama excludes Social Security retirement benefits, and no state-taxable income is established by the listed facts. value = 0
- gpt-6-luna: answered 0
  explanation: Alabama excludes Social Security benefits from taxable income, and no other taxable income is reported; state income tax after nonrefundable credits is 0. value = 0
- gpt-6-sol: answered 0
  explanation: Alabama excludes Social Security benefits, and the listed tax-exempt interest does not produce taxable state income, value = 0
- gpt-6.1-sol: answered 0
  explanation: Alabama exempts Social Security benefits, and the reported tax-exempt interest produces no taxable income here; value = 0
- grok-4.3: answered 0
  explanation: Alabama does not tax Social Security benefits and no other taxable income so state income tax before credits is $0. value = 0
- grok-4.5: answered 0
  explanation: Alabama does not tax Social Security benefits; federal AGI is $0 and even if tax-exempt interest is added the amount is fully offset by Alabama personal exemptions and standard deduction for a single filer age 65+, yielding $0 Alabama tax after nonrefundable credits. value = 0
- grok-4.6: answered 0
  explanation: Alabama does not tax Social Security retirement benefits. With federal AGI of $0 and no other Alabama-taxable wages or business income listed, Alabama taxable income is $0 after the standard deduction and personal exemption, so state tax after nonrefundable credits is $0. value = 0
- grok-4.7: answered 0
  explanation: Alabama fully exempts Social Security. Federal AGI is $0, and no out-of-state municipal-bond amount is identified, so Alabama AGI is $0 and income tax after nonrefundable credits is $0. value = 0
- grok-build-0.1: answered 0
  explanation: Alabama exempts Social Security benefits from taxation; with no other taxable income and sufficient exemptions/deductions for the low tax-exempt interest (if included), Alabama state income tax before refundable credits is zero. value = 0
- inkling: answered 0
  explanation: Alabama starts with federal AGI ($0); Social Security is exempt; even if tax-exempt interest is added back, the standard deduction and personal exemption reduce Alabama taxable income to $0, so state tax is $0. value = 0
- kimi-k2.6: answered 0
  explanation: Alabama does not tax Social Security retirement income. The head's income consists solely of $18,708 in Social Security retirement income and $4,734 in tax-exempt interest, neither of which is taxable under Alabama law. With no taxable income, no state income tax is due before refundable credits. value = 0
- kimi-k3: answered 0
  explanation: Alabama does not tax Social Security. Even if tax-exempt interest is added back, the low-income single standard deduction plus the $1,500 personal exemption is at least $5,500, exceeding $4,734, so Alabama taxable income is $0 and no nonrefundable credit is used. value = 0
- minimax-m3: answered 0
  explanation: Alabama has no state income tax. value = 0
- ox-alpha: answered 0
  explanation: Alabama exempts Social Security benefits and federally tax-exempt interest, so state AGI is $0 and no state income tax is owed. value = 0
- qwen-3.7-max: answered 0
  explanation: Alabama taxes Social Security income but exempts it for most retirees; the head's only taxable income sources are Social Security ($18,708, exempt in AL) and tax-exempt interest ($4,734, not taxable). With no Alabama-taxable income, the state income tax before refundable credits is 0. value = 0
- qwen3.8-max: answered 0
  explanation: Alabama taxable income after the standard deduction is $0, so Alabama income tax before refundable credits is $0. value = 0.0