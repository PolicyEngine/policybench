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
STATE: AZ
OUTPUT: snap (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: annual SNAP (food stamps) benefit amount

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only snap):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: AZ
- tax year: 2026

Head:
- age: 80
- bank account assets: $58,700
- health insurance premiums excluding Medicare Part B: $298
- is disabled
- non-qualified dividend income: $16
- non sch d capital gains: $72
- other health insurance premiums: $298
- over-the-counter health expenses: $200
- Social Security retirement income: $23,736
- taxable private pension income: $6,720

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

ENGINE REFERENCE VALUE: $240.00
MODELS: 46 gave a usable answer; 0 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 46 models (5 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Elderly/disabled 1-person household in AZ, FY2026. Gross monthly income: Social Security $23,736/12 = $1,978 + pension $6,720/12 = $560 + dividends/capital gains ~$7 = ~$2,545. Elderly/disabled units face only the net income test (100% FPL ~$1,305/mo for 1). Deductions: standard deduction ~$209, medical expense deduction: annual health premiums $298+$298 plus OTC $200 = $796/yr = ~$66/mo, minus $35 excess threshold = ~$31. Net income ~$2,545 - $209 - $31 = ~$2,305, far above the ~$1,305 net income limit, so ineligible. Also, assets of $58,700 exceed the elderly/disabled resource limit (~$4,500), confirming ineligibility. value = 0
- claude-fable-5.1: answered 0
  explanation: Monthly gross income = (23,736 + 6,720)/12 = 2,538. Elderly/disabled household: after ~209 standard deduction and small excess medical deduction (498/yr premiums+OTC → ~6.5/month over $35), net income ≈ 2,322, far above the 1-person net income limit (~1,305, 100% FPL). No shelter costs listed. Ineligible. value = 0
- claude-haiku-4.5: answered 0
  explanation: An 80-year-old head with Social Security income of $23,736 and taxable pension income of $6,720 totaling $30,456 gross income exceeds Arizona's SNAP income limit for a single-person household ($1,755/month or $21,060 annually in 2026 for 130% of federal poverty level). Additionally, with $58,700 in bank account assets, the household exceeds the $2,500 asset limit for SNAP eligibility. The household is ineligible for SNAP benefits. value = 0
- claude-opus-4.7: answered 0
  explanation: Household is a single elderly/disabled person in AZ. Gross income: SS $23,736 + pension $6,720 + dividends $16 + capital gains $72 = $30,544/yr (~$2,545/mo). Elderly/disabled households bypass gross income test but must pass net income test. Net income after standard deduction (~$217), medical deduction (medical expenses $596 premiums + $200 OTC = $796, minus $35 threshold = $761), and no shelter deduction (no rent reported): approx $2,545 - $217 - $63 = ~$2,265/mo net. This exceeds the 100% FPL net income limit for 1-person (~$1,255/mo). Not eligible. value = 0
- claude-opus-4.8: answered 0
  explanation: Household is a single elderly person with countable bank assets of $58,700, far exceeding the SNAP resource limit (about $4,500 for households with an elderly/disabled member). Excess resources disqualify the household from SNAP. value = 0
- claude-opus-5: answered 0
  explanation: Household is elderly/disabled so it faces no gross income test, but countable resources of $58,700 in bank assets far exceed the SNAP asset limit, making the household ineligible. value = 0
- claude-opus-5.5: answered 0
  explanation: Countable income is about $2,545 per month. After the standard and small medical deductions, net income is about $2,330, which exceeds 100% of the poverty line (about $1,304). No shelter costs are listed. value = 0
- claude-sonnet-4.6: answered 0
  explanation: SNAP eligibility requires gross monthly income at or below 130% of the federal poverty level (FPL) for most households, or a net income test at or below 100% FPL. For a 1-person household in 2026, the gross monthly income limit is approximately $1,580 (130% FPL). The head's monthly income includes Social Security retirement ($23,736/12 = $1,978) plus taxable private pension ($6,720/12 = $560), totaling approximately $2,538/month in gross income. This exceeds the 130% FPL gross income limit. While elderly/disabled households (age 60+ or disabled) are exempt from the gross income test and only need to pass the net income test (100% FPL ≈ $1,215/month for 1 person), the net income calculation also likely exceeds the limit. Net income starts at $2,538/month. The earned income deduction doesn't apply (no earned income). The standard deduction for a 1-person household is approximately $204/month. Medical deduction for elderly/disabled: out-of-pocket medical expenses above $35/month threshold — health insurance premiums ($298/month) + OTC health ($200/12 ≈ $17/month) = $315/month; excess over $35 = $280/month deductible. Net income ≈ $2,538 - $204 - $280 = $2,054/month, which still exceeds the 100% FPL net income limit of ~$1,215/month. Additionally, SNAP has an asset/resource limit; for households with an elderly or disabled member the limit is $4,500 (2026 estimated), and the bank account assets of $58,700 far exceed this limit. Therefore, the household is not eligible for SNAP due to both excess resources and excess net income. value = 0
- claude-sonnet-5: answered 0
  explanation: Single elderly/disabled household with gross income: SS $23,736 + pension $6,720 + dividends $16 + capital gains $72 = $30,544/year (~$2,545/month), far above the 200% FPL gross income limit for a household of 1 (~$2,510/month in 2026) and asset limit of $4,250 for households with an elderly/disabled member is exceeded by $58,700 in bank assets, making the household categorically ineligible for SNAP. value = 0
- claude-sonnet-5.5: answered 0
  explanation: Monthly income of about $2,545 (mostly Social Security and pension) less the standard deduction and a tiny medical deduction gives net income of about $2,330. That is far above the level where the benefit reaches zero (max allotment about $298 minus 30% of net income), so the benefit is 0. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Household bank assets of $58,700 far exceed the SNAP countable asset limit for a household with an elderly/disabled member, so the household is not eligible for SNAP. value = 0
- deepseek-v4-pro: answered 0
  explanation: SNAP eligibility for elderly/disabled requires countable assets ≤ $4,250; head's bank account assets of $58,700 exceed the limit, so benefit is $0. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: The single elderly/disabled household's monthly gross income is about $2,545; after SNAP deductions this exceeds the net income limit for one person, and the $58,700 bank assets also exceed the SNAP elderly/disabled resource limit. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: Social Security and pension income total $30,456, exceeding SNAP net income limits even with elderly/disabled deductions, and assets of $58,700 exceed the SNAP asset limit. SNAP benefit is 0. value = 0
- gemini-3-flash-preview: answered 0
  explanation: The household's total gross monthly income is approximately $2,545 ($23,736 SS + $6,720 pension + $16 dividends + $72 CG divided by 12). This exceeds Arizona's gross income limit for a one-person household, which is 185% of the Federal Poverty Level (approximately $2,321 per month in 2026). Furthermore, the net income calculation (minus standard and medical deductions) would still exceed the threshold to receive a positive benefit. value = 0.0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household's assets of $58,700 exceed the SNAP resource limit for a household of one, and their income exceeds the net income eligibility test. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: The household's total income, including Social Security, exceeds the net income limits for elderly individuals. value = 0
- gemini-3.5-flash: answered 0
  explanation: The household's total gross income of $30,544 exceeds the Broad-Based Categorical Eligibility threshold (185% of the Federal Poverty Level) for Arizona, meaning they are subject to the standard asset test. Since their bank account assets of $58,700 exceed the resource limit of $4,250 for elderly/disabled households, they are not eligible for SNAP. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: The household's income and asset levels (including bank account assets) exceed SNAP eligibility thresholds. value = 0
- gemini-3.6-flash: answered 0
  explanation: Total gross household income exceeds the Arizona SNAP eligibility threshold. value = 0
- gemini-3.7-flash: answered 0
  explanation: The household's total income exceeds the net income limit for SNAP eligibility and net countable income after deductions reduces the benefit calculation to zero. value = 0
- gemini-3.8-flash: answered 0
  explanation: Gross income of $30,544 exceeds Arizona's broad-based categorical eligibility limit (185% FPL), and bank account assets of $58,700 exceed the federal SNAP asset limit for elderly households, resulting in value = 0.
- glm-5.2: answered 0
  explanation: The household has an annual gross income of $30,544 from Social Security, pension, dividends, and capital gains. For a one-person household with an elderly/disabled member, the net income limit for SNAP is approximately 100% of the Federal Poverty Level (around $15,000 annually). The household's income exceeds this limit, making them ineligible for SNAP. value = 0
- glm-5.3: answered 0
  explanation: Countable net income for SNAP is 27,012 (full Social Security 23,736 + pension 6,720 + dividends 88 less the standard deduction 1,824 and the excess medical deduction 498), exceeding the 2026 SNAP gross and net income limits for a one-person senior household, so SNAP is 0 value = 0
- gpt-5.4-mini: answered 0
  explanation: Household countable income from Social Security and pension income is too high for SNAP under the facts provided, so no benefit is payable. value = 0
- gpt-5.4-nano: answered 0
  explanation: No SNAP-eligible income/asset scenario inputs are provided that would allow positive SNAP benefit estimation under PolicyEngine rules as specified here; value = 0.
- gpt-5.5: answered 0
  explanation: The one-person elderly/disabled SNAP household has $58,700 in bank assets, above the SNAP elderly/disabled resource limit, so it is not eligible for SNAP benefits; value = 0
- gpt-5.6-luna: answered 0
  explanation: The one-person elderly household has no eligible SNAP benefit after applying its income and allowable deductions; the resulting allotment is zero. value = 0
- gpt-5.6-sol: answered 0
  explanation: The one-person household's monthly Social Security and pension income is too high to produce a positive SNAP allotment after the applicable deductions, and no housing costs are listed. value = 0
- gpt-5.6-terra: answered 0
  explanation: Countable monthly income after the available elderly/disabled deductions remains above the SNAP net-income limit for a one-person household. value = 0
- gpt-6-astra: answered 0
  explanation: Income exceeds Arizona's categorical-eligibility income limit, and bank assets exceed the regular SNAP resource limit for an elderly or disabled household; value = 0
- gpt-6-luna: answered 0
  explanation: Countable monthly income remains too high for a positive SNAP allotment after applicable deductions, so annual SNAP benefits are zero. value = 0
- gpt-6-sol: answered 0
  explanation: Monthly Social Security and pension income exceeds the amount that would produce a SNAP allotment for one person after the listed deductions; value = 0
- gpt-6.1-sol: answered 0
  explanation: Income exceeds Arizona's expanded categorical eligibility limit, and $58,700 in bank assets exceeds the regular elderly or disabled household resource limit; value = 0
- grok-4.3: answered 0
  explanation: Income and assets exceed SNAP eligibility limits. value = 0.0
- grok-4.5: answered 0
  explanation: Countable net income for the elderly one-person household exceeds the 100% FPL net-income limit after standard and medical deductions with zero shelter costs, so SNAP is zero. value = 0
- grok-4.6: answered 0
  explanation: Annual cash income of about $30,544 leaves monthly net income above the one-person SNAP net-income limit even after the elderly/disabled medical deduction, and bank assets of $58,700 exceed the elderly/disabled SNAP resource limit. value = 0
- grok-4.7: answered 0
  explanation: Annual gross income is about $30,544. After the SNAP standard deduction and a small excess medical deduction, net income still produces a zero benefit because 30 percent of net income exceeds the one-person maximum allotment. value = 0
- grok-build-0.1: answered 0
  explanation: Bank account assets of 58700 exceed the 4250 SNAP resource limit for a household containing an elderly or disabled person. value = 0
- inkling: answered 0
  explanation: Household of one age 80/disabled has gross monthly income of about $2,545. After the standard deduction (~$204/mo) and medical deduction (~$31/mo), net income is about $2,310/mo, well above the 100% FPL net limit (~$1,255/mo) with no listed shelter costs, so no SNAP benefit. value = 0
- kimi-k2.6: answered 0
  explanation: The household head is elderly and disabled with $58,700 in bank account assets, far exceeding the federal SNAP resource limit for elderly or disabled households. Countable annual unearned income from Social Security retirement and pension alone totals $30,456, and even after estimated standard and excess medical deductions, net income remains well above 100% of the federal poverty level. No rent or utility costs are listed. The household is ineligible. value = 0
- kimi-k3: answered 0
  explanation: Monthly income is about $2,545.33. Even if all listed health costs were deductible, net income would remain about $2,305 per month after the standard and medical deductions, above the one-person SNAP net-income limit; the mortgage balance is not a listed monthly shelter expense; value = 0
- minimax-m3: answered 0
  explanation: Head is 80 with ~$30,544 gross income plus $58,700 bank assets; SNAP eligibility requires low income and limited assets; the income and assets exceed SNAP thresholds for an elderly household, so SNAP = value = 0.
- ox-alpha: answered 0
  explanation: Monthly gross income is about $2,545 ($30,544/12). Even as an elderly/disabled household exempt from the gross-income test and after the standard deduction and a small medical expense deduction, net income (~$2,310) far exceeds the 100%-FPL net income limit (~$1,300 for a 1-person household), so no SNAP benefit is payable. value = 0
- qwen-3.7-max: answered 0
  explanation: The household includes an 80-year-old disabled head with $23,736 in Social Security retirement income and $6,720 in taxable pension income, totaling $30,456 in annual gross income. For a 1-person household in FY2026, the SNAP gross income limit (130% of FPL) is approximately $19,578 annually. The household's gross income of $30,456 exceeds this limit, making the household ineligible for SNAP. value = 0.0
- qwen3.8-max: answered 0
  explanation: The household consists of a single member aged 80. Under SNAP rules, all household members age 60 or older are categorically ineligible for SNAP, so the household receives no SNAP benefit. value = 0