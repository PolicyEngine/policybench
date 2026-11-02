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
STATE: CT
OUTPUT: snap (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: annual SNAP (food stamps) benefit amount

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only snap):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: CT
- tax year: 2026

Head:
- age: 68
- bank account assets: $48,000
- other medical expenses: $500
- over-the-counter health expenses: $100
- Social Security disability income: $30,160
- taxable interest income: $275

Spouse:
- age: 39
- is blind
- is disabled
- over-the-counter health expenses: $50

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

ENGINE REFERENCE VALUE: $288.00
MODELS: 45 gave a usable answer; 1 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 38 models (4 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Household of 2 in CT (BBCE state, gross income limit 200% FPL ≈ $42,760/yr for 2, no asset test). Gross income = $30,160 SSDI + $275 interest = $30,435/yr ($2,536/mo), which passes the gross test. Both members are elderly (68) or disabled, so only the net income test applies. Net income: $2,536 gross − standard deduction (~$205) − excess medical deduction for elderly/disabled member ($500+$100 = $600/yr = $50/mo, less than $35 threshold excess... $50−$35=$15 excess allowed? Actually $600/12=$50; excess over $35 = $15 deduction) = about $2,316/mo net. With no shelter costs reported, no excess shelter deduction. Net income limit (100% FPL for 2 ≈ $1,782/mo) is exceeded, so household fails the net income test and receives no benefit. value = 0
- claude-fable-5.1: answered 0
  explanation: Elderly/disabled 2-person household: gross monthly income about 2,536 (SSDI 2,513 + interest 23); after standard deduction (209) and small excess medical deduction (~19), net income ≈ 2,308 exceeds the 100% FPL net limit of about 1,763 for 2 persons, and with no shelter costs there is no shelter deduction. Ineligible. value = 0
- claude-haiku-4.5: answered 0
  explanation: The household's combined Social Security disability income of $30,160 exceeds Connecticut's SNAP income limit for a 2-person household in 2026. SNAP eligibility requires gross monthly income below approximately 130% of the federal poverty line (around $2,900 for a 2-person household). The household's monthly income from SSDI alone is approximately $2,513, which exceeds standard SNAP limits. Additionally, with bank account assets of $48,000, the household exceeds SNAP's asset limits of $2,250 for households without elderly or disabled members, or $3,500 for households with elderly or disabled members (though the head is 68 and spouse is disabled, standard assets limits still apply in Connecticut SNAP). The household is not eligible for SNAP; value = 0
- claude-opus-4.7: answered 0
  explanation: Household has $48,000 in bank assets, which exceeds the SNAP asset limit for CT (even the elderly/disabled limit of ~$4,500 in 2026). Therefore not eligible. value = 0
- claude-opus-4.8: answered 0
  explanation: Household of 2 in CT (2026). Head age 68 and spouse disabled means household qualifies for elderly/disabled SNAP rules (no gross income test, but net income test and possible asset test apply). However, bank account assets of $48,000 far exceed the SNAP resource limit (about $4,500 for households with an elderly/disabled member). Exceeding the resource limit makes the household ineligible for SNAP, yielding no benefit. value = 0
- claude-opus-5: answered 0
  explanation: Countable monthly income of about $2,536 (Social Security $2,513 plus interest) far exceeds the SNAP net income limit for a two-person household, so no benefit. value = 0
- claude-opus-5.5: answered 0
  explanation: Monthly gross income is about $2,536. Subtracting the standard deduction and a small medical deduction leaves net income of about $2,308. This exceeds the roughly $1,763 net income limit for a household of 2, and there are no shelter costs to reduce it. value = 0
- claude-sonnet-4.6: answered 0
  explanation: For SNAP eligibility in Connecticut (2026), the household consists of a 68-year-old head and a 39-year-old blind/disabled spouse. Income includes Social Security disability income (SSDI) of $30,160 and taxable interest of $275, totaling $30,435 gross annual income ($2,536.25/month). For SNAP purposes, SSDI counts as unearned income. The household has two members, one of whom is disabled (spouse is blind and disabled, head receives SSDI). For a 2-person household with a disabled member, the net income limit is 100% of the federal poverty level (FPL). For FY2026, the 48-contiguous-states 2-person FPL monthly net income limit is approximately $1,732/month. Gross income limit (200% FPL for households with elderly/disabled) = ~$3,464/month. Gross income of $2,536.25/month passes the gross test. For net income: apply the 20% earned income deduction (no earned income here), the standard deduction for a 2-person household (~$198/month in 2026), and the medical expense deduction for elderly/disabled members. Medical expenses: head has $500 other medical + $100 OTC = $600/year; spouse has $50 OTC = $50/year; total = $650/year = $54.17/month. Medical deduction = expenses over $35 threshold = $54.17 - $35 = $19.17/month. Assets: bank account = $48,000. For households with an elderly or disabled member, the asset limit is $4,500 (2026 estimated). The household's bank assets of $48,000 exceed the $4,500 asset limit for households with elderly/disabled members. Therefore, the household is INELIGIBLE for SNAP due to excess assets. Annual SNAP benefit = $0. value = 0
- claude-sonnet-5: answered 0
  explanation: Household assets of $48,000 exceed the SNAP asset limit of $4,250 for households with an elderly/disabled member (2 people, one age 68, one disabled), making the household categorically ineligible for SNAP based on resource limits. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: The household's $48,000 countable bank assets exceed the SNAP asset limit of $4,250 for a household with an elderly/disabled member, making it ineligible. value = 0
- deepseek-v4-pro: answered 0
  explanation: Monthly gross income $2,536.25 is within 200% FPL for 2, but net income after SNAP deductions ($2,300) exceeds 100% FPL ($1,703/month), so no monthly benefit; SNAP = $0. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Monthly gross income of about $2,536 from SSDI and interest, minus allowable deductions, still exceeds the SNAP net income limit for a two-person household, yielding no benefit. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: Gross monthly income is $2,536. After standard deduction ($204) and medical deduction ($19), net monthly income is $2,313, which exceeds the 100% FPL limit for a household of 2 ($1,762.50), so SNAP benefit is 0. value = 0
- gemini-3-flash-preview: answered 0
  explanation: The household's gross monthly income of $2,536.25 passes the 200% FPL Broad-Based Categorical Eligibility threshold for Connecticut, but the benefit calculation (Max Allotment minus 30% of Net Income) results in zero because the net income (gross minus standard and medical deductions) is too high. value = 0.0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household's assets of $48,000 exceed the SNAP eligibility resource limit for most households. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: Although the household meets categorical eligibility criteria, 30% of their net countable income exceeds the maximum SNAP benefit for a two-person household, resulting in no SNAP award. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Household income and asset levels result in zero SNAP benefit under PolicyEngine rules. value = 0
- gemini-3.8-flash: answered 0
  explanation: Household bank assets of $48,000 exceed asset limits, and 30% of net income exceeds the maximum allotment, resulting in a SNAP benefit of 0. value = 0
- glm-5.3: answered 0
  explanation: Monthly unearned income is about $2,536 ($30,160 SSDI plus $275 interest). After the standard deduction and the small medical deduction ($650 annual expenses minus the $35/month floor), net monthly income (~$2,300) makes 30% exceed the 2-person maximum allotment (~$536), yielding a zero benefit. value = 0
- gpt-5.4-mini: answered 0
  explanation: The household has substantial Social Security disability income and $48,000 in bank assets, making it ineligible for SNAP under typical asset and income rules. value = 0
- gpt-5.4-nano: answered 0
  explanation: SNAP eligibility and amount depend on additional inputs (e.g., countable earned income, household size details, shelter costs, and other income/expenses). With only Social Security disability income and taxable interest and no shelter/rent inputs provided, this estimate is 0 under the given limited facts. value = 0
- gpt-5.5: answered 0
  explanation: Annual countable income is $30,160 Social Security disability plus $275 interest, and with no listed shelter costs the elderly/disabled household’s net income remains above the SNAP limit/benefit phaseout for a 2-person household, so no annual SNAP benefit is payable. value = 0
- gpt-5.6-luna: answered 0
  explanation: Although the household has no children, its countable monthly income from Social Security disability benefits and interest remains above the SNAP benefit-income calculation after the standard and allowable medical deductions, producing no annual allotment. value = 0
- gpt-5.6-sol: answered 0
  explanation: Annual Social Security and interest income of $30435, with no housing cost and only $650 of listed annual medical expenses, leaves SNAP net income above the applicable two-person limit. value = 0
- gpt-5.6-terra: answered 0
  explanation: The household's $48,000 in bank assets exceeds the SNAP resource limit applicable to an elderly or disabled household. value = 0
- gpt-6-luna: answered 0
  explanation: The household has no shelter costs reported; after applicable income deductions, its countable income remains too high for a positive SNAP allotment, so annual SNAP is $0; value = 0
- gpt-6-sol: answered 0
  explanation: Monthly Social Security income of about 2513 exceeds the two-person SNAP net-income limit even after the applicable standard and reported medical deductions; value = 0
- gpt-6.1-sol: answered 0
  explanation: Countable Social Security and interest income, after applicable standard and medical deductions, produces a benefit reduction exceeding the two-person SNAP maximum. value = 0
- grok-4.3: answered 0
  explanation: Household assets exceed typical SNAP limits and income may not qualify after SSDI. value = 0
- grok-4.5: answered 0
  explanation: Household bank assets of $48,000 exceed the SNAP resource limit for an elderly/disabled household (approximately $4,500), rendering the unit ineligible regardless of income. value = 0
- grok-4.6: answered 0
  explanation: Annual countable income is $30,435. After the SNAP standard deduction and a small excess medical deduction, 30 percent of net income exceeds the two-person maximum allotment, so the SNAP benefit is $0. value = 0
- grok-build-0.1: answered 0
  explanation: Net income of approximately $30,000 after standard and medical deductions far exceeds the maximum SNAP allotment for a household of 2 (around $6,420 annually), resulting in $0 benefit. value = 0
- inkling: answered 0
  explanation: The household includes elderly/disabled members, but monthly net income (~$2,317 after standard and medical deductions) exceeds 100% FPL for two (~$1,762/month). No children are present. So not eligible. value = 0
- kimi-k2.6: answered 0
  explanation: The two-person household has approximately $30,435 in annual unearned income ($30,160 Social Security disability plus $275 interest) and no listed rent or utilities. SNAP allows a standard deduction and an excess medical deduction of about $230 annually for the elderly and disabled members, but without shelter costs net income remains far above the 100-percent-FPL net income limit for a household of two, making the household ineligible. value = 0
- kimi-k3: answered 0
  explanation: Monthly income is 2536.25; after the standard deduction and small excess medical deduction it remains above the two-person SNAP net income limit, with no rent or shelter costs listed. value = 0
- minimax-m3: answered 0
  explanation: Household of 2 with both elderly/disabled. Gross annual income of $30,435 (SSDI + interest) exceeds the 200% FPL gross income limit of approximately $30,120 for a household of 2. Bank assets of $48,000 also exceed the $4,250 asset limit for elderly/disabled households. SNAP benefit is $0. value = 0
- ox-alpha: answered 0
  explanation: Monthly gross income of about $2,536 minus the standard deduction and a small elderly/disabled medical deduction leaves net income near $2,310, which fails the net-income test against the poverty guideline and makes 30% of net income exceed the two-person maximum allotment, so benefits are zero. value = 0
- qwen-3.7-max: answered 0
  explanation: The household has two members: one age 68 on SSDI and one age 39 who is disabled. Both members have countable income that exceeds SNAP limits when considering SSDI as unearned income. The head's SSDI of $30,160 and taxable interest of $275 result in total monthly unearned income of approximately $2,536, which exceeds the SNAP gross and net income limits for a 2-person household. Additionally, bank account assets of $48,000 exceed SNAP resource limits for this household composition. value = 0