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
STATE: TX
OUTPUT: snap (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: annual SNAP (food stamps) benefit amount

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only snap):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: TX
- tax year: 2026

Head:
- age: 23
- gross wages and salaries: $13,000
- bank account assets: $190
- educational assistance: $5,000
- financial assistance: $12,000
- hourly wage: $8
- usual weekly hours worked: 35
- is paid hourly
- is pregnant
- other medical expenses: $8,000
- over-the-counter health expenses: $500

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

ENGINE REFERENCE VALUE: $288.00
MODELS: 45 gave a usable answer; 0 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 33 models (2 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: SNAP counts earned income ($13,000 wages = ~$1,083/month) plus unearned income; financial assistance of $12,000 (~$1,000/month) counts as unearned income, while educational assistance is generally excluded. Gross monthly income ≈ $2,083, which exceeds the 130% FPL gross income limit for a 1-person household (~$1,696/month in FY2026). With no elderly/disabled member, the household fails the gross income test and is ineligible for SNAP, so annual benefit is $0. value = 0
- claude-fable-5.1: answered 0
  explanation: One-person household with monthly earned income $1,083 and $1,000/month financial assistance counted as unearned income. Net income after $209 standard deduction and 20% earned income deduction (~$1,658) exceeds the 1-person net income limit (~$1,305) and 30% of net income exceeds the $298 maximum allotment; no medical deduction since not elderly/disabled. value = 0
- claude-haiku-4.5: answered 0
  explanation: The household head is 23 years old and employed with gross annual wages of $13,000. She works 35 usual weekly hours, which exceeds the 20 hours per week requirement that would trigger work registration requirements for ABAWD (Able-Bodied Adult Without Dependents) under SNAP rules. While she is pregnant, being a pregnant individual does not automatically qualify for SNAP exemptions from work requirements if currently employed and earning sufficient income. With gross wages of $13,000 annually, the household's gross income would need to be tested against the 130% federal poverty line for SNAP eligibility. For 2026, the 130% poverty line for a single-person household is approximately $1,868 monthly or $22,424 annually. At $13,000 gross income with allowable deductions, the household likely exceeds this threshold when considering standard deductions and earned income deductions available under SNAP rules. The other income sources listed (educational assistance of $5,000 and financial assistance of $12,000) are non-countable or countable depending on their source, but in either case, the total gross income of $30,000 substantially exceeds SNAP income limits. Therefore, the household does not qualify for SNAP benefits. value = 0
- claude-opus-4.7: answered 0
  explanation: TX SNAP household of 1 (pregnant head counts as 1 person; unborn doesn't add to size for SNAP). Gross income: $13,000 wages/year = $1,083/mo. Educational assistance ($5,000) excluded. Financial assistance treated as unearned: $12,000/yr = $1,000/mo. Total gross monthly ~$2,083. Earned income deduction 20% of $1,083 = $217, net earned $866. Standard deduction (FY2026, HH of 1) ~$209. Net income before shelter: $866+$1,000-$209 = $1,657. No rent/utilities listed, so no shelter deduction. Medical deduction only for elderly/disabled (head is 23, not disabled) - not applicable. Net income $1,657/mo. Net income limit for HH of 1 ~$1,255 — exceeds limit, but gross income $2,083 is under 130% gross limit $1,632? Actually $2,083 > $1,632 gross limit for HH of 1, so ineligible. However, TX uses BBCE at 165% FPL (~$2,072) — still over. Household appears ineligible. value = 0
- claude-sonnet-4.6: answered 0
  explanation: SNAP eligibility and benefit calculation for a single-person household in Texas for 2026. The head is a 23-year-old pregnant individual, which categorically exempts her from SNAP's able-bodied adult without dependents (ABAWD) work requirements, and pregnancy is a household composition factor that may affect deductions.

Step 1 – Countable Income:
- Gross wages: $13,000
- Educational assistance: $5,000 (amounts used for education-related expenses are excluded; since no expenses are listed beyond medical, we treat this as excluded under SNAP rules for educational assistance used for tuition/fees/required educational expenses)
- Financial assistance: $12,000 — this is likely unearned income (e.g., from a family member or organization). Under SNAP, most financial assistance from non-government sources counts as income unless it is a loan. We treat it as countable unearned income.

Countable gross income:
- Earned: $13,000/year
- Unearned: $12,000/year
- Educational assistance: excluded (used for education costs)
- Total gross income: $25,000/year = $2,083.33/month

Step 2 – Gross Income Test (130% FPL for 1 person in 2026):
130% FPL for 1 person ≈ $1,580/month (using 2025 FPL of $15,060 × 1.30 = $19,578/year = $1,631.50/month; for 2026, FPL is expected to be approximately $15,650, so 130% ≈ $20,345/year ≈ $1,695/month).
Gross income of $2,083/month exceeds 130% FPL → household would normally fail gross income test.

However, households containing a pregnant person are categorically eligible in many states, but Texas does NOT have broad-based categorical eligibility (BBCE) that waives income limits. Texas uses standard SNAP rules. Therefore, the pregnant individual must still pass the gross income and net income tests.

Since gross income ($2,083/month) exceeds 130% FPL (~$1,695/month), the household fails the gross income test and is NOT eligible for SNAP.

Wait — re-examining the financial assistance of $12,000. If this is a non-recurring lump sum or a loan, it may be  [... 1557 more characters cut]
- deepseek-v4-flash-0731: answered 0
  explanation: Monthly gross income counting wages ($13,000), financial assistance ($12,000), and educational assistance ($5,000) is $2,500, above the Texas SNAP gross income limit of 130% FPL for a one-person household (~$1,743/month), so the household is ineligible. value = 0
- deepseek-v4-pro: answered 0
  explanation: Gross income $30,000 exceeds 130% FPL for a single-person household ($19,578), ineligible. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: SNAP counts the $13,000 wages plus $5,000 educational assistance and $12,000 financial assistance; the resulting monthly net-income contribution exceeds the one-person maximum SNAP allotment, producing $0 benefit. value = 0
- gemini-3-flash-preview: answered 0
  explanation: For SNAP in Texas, a pregnant woman is typically treated as a household of one until the child is born. The household's gross annual income of $25,000 ($13,000 wages + $12,000 financial assistance) exceeds the gross income limit for a one-person household (130% of the Federal Poverty Level, approximately $19,000-$20,000). value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: The household's total gross income, including wages and financial assistance, exceeds the SNAP gross income limit of 130% of the federal poverty level for a household of 1. Unborn children do not increase the SNAP household size. value = 0
- gemini-3.5-flash: answered 0
  explanation: Combining wages of $13,000 and financial assistance of $12,000 results in gross income of $25,000, which exceeds the Texas SNAP gross income limit (165% of the FPL for a household of 1, which is approximately $24,849 in 2026). value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: The household's income and assets result in 0 SNAP benefits. value = 0
- gemini-3.6-flash: answered 0
  explanation: The household's monthly income exceeds the net income limits to receive a positive SNAP benefit allotment. value = 0
- gemini-3.7-flash: answered 0
  explanation: Household net income exceeds the threshold to qualify for a positive SNAP allotment for a household of 1. value = 0
- gemini-3.8-flash: answered 0
  explanation: Including regular financial assistance in unearned income, Head's net income exceeds the maximum allowable threshold to receive a positive SNAP allotment, resulting in an annual benefit of $0. value = 0
- glm-5.3: answered 0
  explanation: The $12,000 counted unearned financial assistance combined with $13,000 gross wages yields income far above SNAP gross and net limits for a one-person Texas household, so annual SNAP is $0. value = 0
- gpt-5.4-nano: answered 0
  explanation: With only a single head earning $13,000 and with no household size or other needs specified beyond the facts, estimated SNAP benefit is 0 under the provided policy quantities; value = 0
- gpt-5.5: answered 0
  explanation: For SNAP, the one-person Texas household has $13,000 of annual wages plus $12,000 of financial assistance counted as income; after the earned-income and standard deductions, countable net income is high enough that 30% of net income exceeds the one-person maximum SNAP allotment, so no annual SNAP benefit is payable. value = 0
- gpt-5.6-luna: answered 0
  explanation: The household's listed annual assistance and wage resources place countable monthly income above the applicable one-person SNAP gross-income limit, producing no SNAP benefit. value = 0
- gpt-5.6-sol: answered 0
  explanation: The $13,000 of wages plus $12,000 of financial assistance places this one-person SNAP household above the applicable Texas gross-income limit; educational assistance is excluded, but the household still does not qualify. value = 0
- gpt-5.6-terra: answered 0
  explanation: Countable wages and regular financial assistance total 25000, exceeding the one-person SNAP gross-income limit; value = 0
- gpt-6-astra: answered 0
  explanation: Reported earnings and assistance exceed applicable SNAP income limits, with no shelter deduction or qualifying elderly or disabled medical deduction established. value = 0
- gpt-6-luna: answered 0
  explanation: Counting the listed $12,000 financial assistance as unearned income, the household has no reported shelter costs and its net-income-based 30% contribution exceeds the maximum one-person monthly allotment, leaving no SNAP benefit. value = 0
- gpt-6.1-sol: answered 0
  explanation: Wages and recurring financial assistance leave countable income too high for a positive one-person SNAP allotment, even after earned-income and standard deductions; value = 0
- grok-4.3: answered 0
  explanation: Assets and income result in zero annual SNAP benefit under rules. value = 0
- grok-4.5: answered 0
  explanation: Countable gross income of wages plus financial assistance equals $25,000, exceeding the 130% FPL gross-income limit for a size-1 household, so the unit is ineligible. value = 0
- grok-4.6: answered 0
  explanation: Household size is 1 (unborn child is not counted for SNAP). Countable income includes wages plus the listed financial assistance (and potentially unused educational assistance), totaling well above both the 130 percent FPL regular gross-income test and Texas BBCE 165 percent FPL limit for 2026, so the unit is ineligible. value = 0
- grok-4.7: answered 0
  explanation: SNAP countable income is $13,000 wages plus $12,000 financial assistance; educational assistance is excluded. After the 20% earned-income deduction and standard deduction, net income is about $19,900, above 100% of FPL for one person, so the household fails the net income test. Medical costs are not deductible because she is not elderly or disabled, and rent is zero. value = 0
- grok-build-0.1: answered 0
  explanation: Gross income of $13,000 wages plus $12,000 financial assistance totals $25,000, exceeding the 2026 SNAP gross income limit of approximately $20,800 (130% FPL for household of 1). Educational assistance is excluded from SNAP income. No benefit. value = 0
- inkling: answered 0
  explanation: Counting wages ($13,000), financial assistance ($12,000), and educational assistance ($5,000), gross income exceeds 130% FPL for the household, so SNAP is ineligible with $0 benefit. value = 0
- kimi-k3: answered 0
  explanation: Wages plus recurring financial assistance average $2,083.33 per month, above the one-person SNAP gross-income limit, so the annual SNAP allotment is $0. value = 0
- minimax-m3: answered 0
  explanation: A pregnant 23-year-old with no children listed and gross income of $13,000. SNAP requires a household of size ≥ 2 for a pregnant individual to qualify in some states, but with only one person listed, household size is 1. Net income below the poverty line and assets $190 (well under $2,000 limit), but the household composition is unclear. Given only one person, SNAP benefit is likely $0 or minimal. Under federal rules, a pregnant individual counts as 2 for SNAP, but with only one member listed, treat as household size 1. Maximum SNAP for 1 in 2026 is ~$2,130. After 20% deduction on $13,000 gross = $10,400 net, which exceeds the income limit of ~$1,255/month for 1. So SNAP = $0. value = 0
- ox-alpha: answered 0
  explanation: Gross countable income of $13,000 wages plus $12,000 financial assistance (countable unearned cash income) totals $25,000/year, exceeding the SNAP gross-income limit of about 130% of the federal poverty level for a household of 1 (~$20,350/year for FY2026), so the household is ineligible. value = 0

Cluster 2: 1,208, given by 3 models (3 of them among the benchmark's top-ranked models)
- claude-opus-5.5: answered 1,208
  explanation: Assumes the financial and educational assistance are not counted as SNAP income. Monthly earnings are $1,083.33. Subtract the 20% earned income deduction and the $209 standard deduction to get net income of about $657.67. With no shelter costs, the benefit is $298 − 0.3 × 657.67 ≈ $100.70 per month, about $1,208 per year. value = 1208
- claude-sonnet-5.5: answered 1,208
  explanation: One-person household with monthly earned income of about $1,083. I counted wages only and treated the assistance amounts as excluded. After the 20% earned-income deduction (about $217) and the standard deduction (about $209), net income is about $658. Monthly benefit is about $298 max allotment minus 30% of net income, roughly $101, or about $1,208 per year. value = 1208
- gpt-6-sol: answered 1,208.4
  explanation: For one person, the 2026 monthly maximum of 298 minus 30% of monthly wages after the 20% earned-income and 209 standard deductions produces annual SNAP of 1208.4; value = 1208.4