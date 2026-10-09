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
STATE: LA
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: LA
- tax year: 2026

Head:
- age: 43
- bank account assets: $912
- disability benefits: $14
- is blind
- is disabled
- over-the-counter health expenses: $20
- sstb self employment income before lsr: $10,400

Spouse:
- age: 20
- disability benefits: $24
- is disabled
- over-the-counter health expenses: $20

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
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_medicaid_eligible: whether Spouse is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_chip_eligible: whether Spouse is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- spouse_medicare_eligible: whether Spouse is eligible for Medicare (1 if yes, 0 if no)
- free_school_meals_eligible: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)
- reduced_price_school_meals_eligible: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)

Use the `submit_outputs` function exactly once. Return an `outputs` object with every requested quantity keyed by variable name. Each requested key must map to an object with a numeric `value` and a non-empty, specific, concise `explanation`. Each explanation must support the numeric value submitted for the same variable in `outputs`. If an explanation mentions a final amount, that amount must match the corresponding `outputs` value. Do not write that you will use one value while submitting a different value. Do not include scratch work, abandoned calculations, or corrections. End each explanation with `value = X`, where X exactly matches the numeric `value` field. For 1/0 eligibility outputs, submit 1 only when the explanation says eligible or yes, and submit 0 only when it says not eligible or no. Use the exact variable names as keys inside `outputs`. Include every requested key exactly once in `outputs`, even if the value is 0. Put only numeric values in `value`, with no dollar signs, commas, or explanatory text. Do not rely on plain text for the final answers. If an answer is a currency amount, give the annual amount. If an answer is a rate, give a decimal (e.g. 0.25 for 25%).
----- END HOUSEHOLD PROMPT -----

ENGINE REFERENCE VALUE: $33.20 (engine output 33.20000076293945)
MODELS: 45 gave a usable answer; 15 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 25 models (1 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Louisiana's refundable individual income tax credits (e.g., school readiness credit, refundable child care credit for low income, inventory tax credit) do not apply: the household has no children, no child care expenses, and no qualifying inventory taxes. Self-employment income of $10,400 with no wages does not generate any LA refundable credit; LA has no state EITC match for filers without a federal EITC-qualifying situation with earned income only from self-employment—actually LA does have a 5% EITC match, but with married filing jointly, no children, and net self-employment earnings around $9,600, the federal EITC for childless couples is small; however, the head is a disabled/blind adult aged 43 which keeps them in the 25-64 eligible range, so a small federal EITC could exist. Given the instruction to not infer unlisted inputs and the microsimulation result, total refundable state credits = 0. value = 0
- claude-haiku-4.5: answered 0
  explanation: Louisiana does not have significant refundable state income tax credits for individuals in the general filing population. While Louisiana offers various tax credits, most are nonrefundable. The household has minimal income after self-employment taxes and standard deductions, and no eligible dependents or circumstances that would generate refundable state credits under LA tax law. value = 0
- claude-opus-4.7: answered 0
  explanation: Louisiana refundable credits (e.g., school readiness, earned income, child care) require qualifying children or related expenses. This household has no children, no childcare expenses, and no earned income qualifying for LA EITC beyond minimal self-employment. No refundable LA credits apply. value = 0
- claude-opus-4.8: answered 0
  explanation: Louisiana refundable individual income tax credits primarily include the refundable Child Care Credit, School Readiness Credit, and Earned Income Credit. This household has no qualifying children, no child care expenses, and self-employment income of $10,400 (head) which after self-employment tax deduction yields little to no LA EITC since LA EITC is 5% of federal EITC for childless filers; with two adults and only $10,400 net SE income, federal/state EITC for a married couple with no children is minimal and the refundable state credits round to zero given no children or care expenses. value = 0
- claude-opus-5: answered 0
  explanation: Louisiana has no refundable EITC-type credit applicable here (state EITC applies only with qualifying earned-income credit at federal level and the LA EITC is 5% of federal EITC but is nonrefundable/limited; no refundable credits computed for this household). value = 0
- claude-sonnet-4.6: answered 0
  explanation: Louisiana has a nonrefundable personal income tax credit structure. For tax year 2026, Louisiana does not offer refundable state individual income tax credits applicable to this household's situation. The household has self-employment income of $10,400 (SSTB) for the head, with disability benefits of $14 (head) and $24 (spouse), but disability benefits are generally not taxable for Louisiana purposes and the self-employment income is modest. Louisiana's income tax credits (such as the personal exemption credit and dependent credits) are nonrefundable. There are no Louisiana refundable credits (e.g., no state EITC, no refundable child tax credit) available for this household in 2026. Therefore, total refundable state individual income tax credits = $0. value = 0
- claude-sonnet-5: answered 0
  explanation: Louisiana does not offer a refundable state earned income tax credit or other refundable individual income tax credit that this household's income and demographic profile (self-employment income of $10,400, disability status, no dependents) would qualify for under LA tax law. Louisiana's EITC-like credit and other credits are generally nonrefundable or the household lacks qualifying dependents/income needed to trigger the available refundable credits, so the estimated refundable state credit total is 0. value = 0
- claude-sonnet-5.5: answered 0
  explanation: No refundable Louisiana credit applies to this household. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Federal EITC is $0, so Louisiana's refundable EITC-based credit is also $0 and no other refundable state credit applies. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: No state refundable credits are applicable. value = 0
- gemini-3.5-flash: answered 0
  explanation: The household does not qualify for any refundable state income tax credits in Louisiana. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: The household has no state refundable tax credits in Louisiana. value = 0
- glm-5.2: answered 0
  explanation: The household is ineligible for the Louisiana Earned Income Tax Credit because the spouse is under age 25, and no other refundable state income tax credits apply to these facts. value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable Louisiana income tax credits are triggered by the listed facts. value = 0
- gpt-5.4-nano: answered 0
  explanation: No refundable LA state credits (per provided facts) are indicated, so submitted as 0. value = 0
- gpt-5.6-luna: answered 0
  explanation: No qualifying Louisiana refundable individual income tax credit applies to this two-adult household without children; value = 0
- gpt-5.6-terra: answered 0
  explanation: No Louisiana refundable credit eligibility is indicated by the household facts. value = 0
- grok-4.3: answered 0
  explanation: No state refundable credits apply or qualify for this household. value = 0
- grok-4.5: answered 0
  explanation: Louisiana provides no refundable income-tax credits that apply to this household. value = 0
- grok-build-0.1: answered 0
  explanation: Louisiana does not provide refundable state income tax credits applicable to this household's situation. value = 0
- inkling: answered 0
  explanation: Federal EITC is $0, so Louisiana's state EITC (5% of federal) is $0, and there are no other refundable state credits for this household. value = 0
- minimax-m3: answered 0
  explanation: Louisiana has no state individual income tax and therefore no refundable state income tax credits. value = 0
- ox-alpha: answered 0
  explanation: No refundable Louisiana income tax credits apply to this household with zero liability and no qualifying expenses or children. value = 0
- qwen-3.7-max: answered 0
  explanation: Louisiana does not have a state individual income tax, so there are no refundable state individual income tax credits. value = 0
- qwen3.8-max: answered 0
  explanation: No Louisiana refundable credits apply based on the listed household facts. value = 0