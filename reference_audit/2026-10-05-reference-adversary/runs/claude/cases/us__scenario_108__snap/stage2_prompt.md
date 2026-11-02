You are a reference adversary for a US tax-and-benefit benchmark. Each benchmark question gives a household and asks for policy quantities for tax year 2026. A microsimulation engine produced the reference answer. On the question below, a cluster of AI models answering from memory, without tools, agreed on an answer other than the reference.

This is stage 2 of 2: reconciliation. In stage 1, a judge who had not seen how the engine derived the reference worked the question from primary law. Its result appears below exactly as it was recorded, with its sha256. Stage 1 is frozen and you may not revise it. If the engine derivation or the law shows that stage 1 erred (it misread a fact, missed or misapplied a rule, or used the wrong year's amount), say so in stage1_error and name the error. Do not silently change course: if your independent_answer, or your view of which answer the law supports, differs from stage 1's, stage1_error must say why. Use "" for stage1_error only when stage 1 stands.

Only now do you see how the engine derived the reference. The derivation is a short narrative that a language model wrote from the engine's computation trace for this household; it can misdescribe a step, but the reference value is the engine's own output. Compare each step with the law and with the output definition, and decide:
- reference_holds: the reference is what the law and the output definition give on the stated facts.
- reference_wrong: the engine misapplies the law on the stated facts, or uses an amount or rule the law had not published (for example a 2026 amount the engine projected itself where no agency had published one before 2026-07-03).
- definition_mismatch: the engine computes something other than what the output definition describes (it includes or leaves out people, returns, taxes, credits or benefits that the definition covers or excludes).
- prompt_ambiguous: the stated facts or the definition genuinely admit more than one answer (for example the answer turns on an input the prompt does not list).

engine_step_at_issue names the derivation step that departs from the law or the definition; use "" when the reference holds.

suggested_adjudication:
- affirmed: the reference holds.
- regenerated: the reference should be recomputed under a stated convention or a corrected input; the output stays scored.
- engine_defect: the engine misapplies the law on the stated facts.
- unlisted_input: the answer turns on an input the prompt does not list.
- later_law: the reference rests on law or an amount published after 2026-07-03, or never published.
- definition_exclusion: the engine's quantity does not match the output definition, so the output should be excluded.
- none: you suggest nothing.
Pair them this way: reference_holds with affirmed; reference_wrong with engine_defect, later_law or regenerated; definition_mismatch with definition_exclusion or regenerated; prompt_ambiguous with unlisted_input or definition_exclusion. "none" goes with any verdict.

reference_value is the engine reference below. consensus_value is the consensus answer you weighed (null if none applies).

Cite the law you rely on as in stage 1: source, pinpoint, URL, date, pre_freeze and a short quote. The engine derivation is not a citation. Do not consult PolicyEngine or PolicyBench in any form: not policyengine.org, policybench.org, their GitHub repositories, their documentation, their package source, or any calculator built on them. Do not fetch anything from these domains: policybench.org, www.policybench.org, policyengine.org, www.policyengine.org, github.com, raw.githubusercontent.com. Do not rely on any calculator or estimate built by an AI model. A citation of any of these sources voids your answer.

Your verdict changes no score. A developer adjudicates every case you do not return as reference_holds.

Return only the JSON object the schema asks for.

TAX YEAR: 2026    REFERENCE LAW FROZEN: 2026-07-03
STATE: WI
OUTPUT: snap (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: annual SNAP (food stamps) benefit amount

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only snap):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: WI
- tax year: 2026

Head:
- age: 85
- gross wages and salaries: $7,656
- bank account assets: $270
- has indian health service coverage at interview
- is disabled
- is a surviving spouse
- other medical expenses: $500
- over-the-counter health expenses: $300
- pre-subsidy rent: $7,200
- Social Security survivor benefits: $12,934
- survivor benefits: $10,392

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
MODELS: 46 gave a usable answer; 3 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 36 models (4 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Household of 1 elderly/disabled person in WI, 2026. Gross income: wages $7,656 + Social Security survivor $12,934 + other survivor benefits $10,392 = $30,982/yr ≈ $2,582/mo. Elderly/disabled households have no gross income test but must pass the net income test (100% FPL, ~$1,305/mo for 1 person in FY2026). Deductions: standard deduction ~$205, earned income deduction 20% of $638 = $128, excess medical (($500+$300)/12 = $67 − $35 = $32). Adjusted income ≈ $2,582 − 205 − 128 − 32 = $2,217. Excess shelter deduction (uncapped for elderly/disabled): rent $600/mo − half of $2,217 ($1,109) = 0 shelter deduction. Net income ≈ $2,217, well above the ~$1,305 net income limit, so the household is not eligible for SNAP. value = 0
- claude-fable-5.1: answered 0
  explanation: Gross income 2,582/mo; elderly/disabled so no gross test, but net income after 20% earned deduction (128), standard deduction (209), and excess medical (~32) is about 2,214/mo with no excess shelter deduction (rent 600 < half of net income), exceeding the 1-person net limit (~1,305/mo). Ineligible. value = 0
- claude-haiku-4.5: answered 0
  explanation: This household is not eligible for SNAP benefits in Wisconsin. The household's countable monthly income exceeds the SNAP income limit. Monthly income is calculated as: gross wages ($7,656/12 = $638) + Social Security survivor benefits ($12,934/12 = $1,078) + other survivor benefits ($10,392/12 = $866) = $2,582 gross monthly income. After standard deductions and other adjustments applied in Wisconsin, the countable income exceeds 130% of the federal poverty line for a single person ($1,385/month in 2026), making the household ineligible. value = 0
- claude-sonnet-4.6: answered 0
  explanation: For SNAP eligibility in 2026, we assess gross income against 130% of the Federal Poverty Level (FPL) for a 1-person household (aged 85, so elderly/disabled rules apply — 200% gross test doesn't apply in WI for categorically eligible households, but let's use standard elderly/disabled rules). The head is elderly (85) and disabled, so the household is subject to the elderly/disabled net income test (100% FPL net) rather than the 130% gross test, but must still pass the gross income test of 200% FPL under broad-based categorical eligibility or 130% FPL under standard rules. WI does not have broad-based categorical eligibility that eliminates the gross income test for elderly/disabled households.

Annual gross income: Gross wages $7,656 + Social Security survivor benefits $12,934 + survivor benefits $10,392 = $30,982. Note: For SNAP, Social Security benefits count as unearned income. The 'survivor benefits' of $10,392 appear to be a separate benefit (possibly pension/annuity survivor benefits). Total countable income = $7,656 + $12,934 + $10,392 = $30,982/year = $2,582/month.

For a 1-person household in 2026, 130% FPL ≈ $1,632/month. The gross income of $2,582/month exceeds 130% FPL ($1,632/month). For elderly/disabled households, the gross income test does not apply — only the net income test at 100% FPL applies.

Net income calculation: Gross income $2,582/month. Earned income deduction: 20% of wages = 20% × $638 = $128. Income after earned income deduction = $2,582 − $128 = $2,454. Standard deduction for 1-person household (2026) ≈ $198/month. Income after standard deduction = $2,454 − $198 = $2,256. Medical deduction for elderly/disabled: out-of-pocket medical expenses over $35/month. Medical expenses: other medical $500/year + OTC health $300/year = $800/year = $67/month. Deductible amount = $67 − $35 = $32/month. Income after medical deduction = $2,256 − $32 = $2,224. Excess shelter deduction: rent $7,200/year = $600/month. 50% of income after other deductions =  [... 321 more characters cut]
- claude-sonnet-5.5: answered 0
  explanation: The household has an elderly and disabled member, so only the net income test applies. Net income after the earned income, standard and medical deductions is about $1,350 a month or more. Rent of $600 a month is below half of income, so there is no excess shelter deduction. Net income is above the 100% FPL limit, so the household is ineligible. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Monthly gross income ≈ $2,582 (wages $638, SS survivor $1,078, survivor benefits $866); after 20% earned-income, standard, and medical deductions, net income ≈ $2,184/month, above the 100% FPL net-income limit for a 1-person household, so SNAP benefit is $0. value = 0
- deepseek-v4-pro: answered 0
  explanation: Elderly/disabled household net income $2,222.56/month exceeds maximum SNAP benefit, resulting in negative benefit. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: After earned-income, standard, and medical-expense deductions, 30% of net monthly income exceeds the one-person maximum SNAP allotment, so the benefit is zero; value = 0.
- deepseek-v4.1-flash: answered 0
  explanation: SNAP net income after deductions exceeds 100% FPL for elderly/disabled household; income too high. value = 0
- gemini-3-flash-preview: answered 0
  explanation: The household's gross monthly income of $2,581.83 exceeds the typical SNAP eligibility limits for a one-person household, and 30% of their net income exceeds the maximum monthly allotment. value = 0.0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: Household income exceeds the eligibility threshold for SNAP benefits. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: The household's total gross and net income exceed the limits for the Supplemental Nutrition Assistance Program (SNAP). value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: Household income and resources result in zero SNAP benefit under PolicyEngine rules. value = 0
- gemini-3.6-flash: answered 0
  explanation: Household monthly gross income ($2,581.83) exceeds SNAP limits, and net income reduces expected benefits to $0. value = 0
- gemini-3.7-flash: answered 0
  explanation: Household net income exceeds the maximum allowable threshold, resulting in a SNAP benefit of value = 0
- gemini-3.8-flash: answered 0
  explanation: Head's monthly income of approximately $2,582 results in a net income where 30% exceeds the maximum monthly SNAP allotment for a single individual. value = 0
- glm-5.2: answered 0
  explanation: The household has one member (age 85, disabled) with annual gross income of $7,656 wages + $12,934 Social Security survivor benefits + $10,392 survivor benefits = $30,982. Monthly gross income is approximately $2,582. After standard deduction (~$227/mo), 20% earned income deduction ($128/mo), and medical expense deduction ($32/mo), net monthly income is approximately $2,196. Rent is $600/mo but does not exceed 50% of net income, so the shelter deduction is $0. The SNAP benefit formula yields max allotment (~$300) minus 30% of net income (~$659), which is negative, resulting in $0. value = 0
- glm-5.3: answered 0
  explanation: Net monthly income after the standard deduction, 20% earned income deduction, and capped shelter deduction is far above the ~100% FPL limit (~$16,550/year for one person) for an elderly/disabled one-person household, so SNAP benefits are zero. value = 0
- gpt-5.4-nano: answered 0
  explanation: SNAP eligibility and benefit amount are not estimated positively from the provided facts given the household’s income and no additional details about allowable deductions beyond basic medical/OTC and rent; thus SNAP is estimated as 0. value = 0
- gpt-5.5: answered 0
  explanation: For a one-person elderly/disabled SNAP household, monthly income from wages and survivor/Social Security benefits is above the amount that could produce a positive allotment after the standard, earned-income, medical, and shelter deductions; the computed SNAP benefit is therefore zero. value = 0
- gpt-5.6-sol: answered 0
  explanation: After the earned-income, standard, medical, and shelter calculations, countable net monthly income remains above the one-person elderly or disabled SNAP limit; value = 0
- gpt-5.6-terra: answered 0
  explanation: Countable monthly income exceeds the one-person elderly or disabled household SNAP net-income limit after listed deductions; value = 0
- gpt-6-luna: answered 0
  explanation: The household's monthly wages and survivor income exceed the SNAP net-income limit after standard, earned-income, medical, and rent-related deductions, so annual SNAP is zero. value = 0
- gpt-6-sol: answered 0
  explanation: The combined monthly wages and survivor benefits, after applicable SNAP deductions, leave net income too high for a one-person SNAP allotment. value = 0
- grok-4.3: answered 0
  explanation: Household income exceeds SNAP limits for one person after deductions. value = 0
- grok-4.5: answered 0
  explanation: Elderly/disabled household net income after deductions (~$28,000) far exceeds 100% FPL (~$16,000), so SNAP benefit is zero. value = 0
- grok-4.6: answered 0
  explanation: Annual gross income 30982 is far above 130% FPL. As elderly/disabled the gross test can be waived, but net income after 20% earned, standard, excess-medical, and shelter deductions remains well above 100% FPL, so SNAP is 0. value = 0
- grok-4.7: answered 0
  explanation: After the earned-income deduction, standard deduction, and small excess medical deduction, net income from wages and survivor benefits remains well above the one-person SNAP net income limit, so SNAP is zero. value = 0
- grok-build-0.1: answered 0
  explanation: For 1-person elderly/disabled household, net income after 20% earned deduction, standard deduction, medical deduction (66.67-35 monthly), and shelter (0 as rent below half adjusted income) is ~2218 monthly, exceeding ~1305 net income limit (100% FPL). Gross test waived but net fails. value = 0
- inkling: answered 0
  explanation: As an elderly/disabled one-person household, gross income is ~$2,582/month; after standard/earned-income/medical deductions, net income is ~$2,225/month, exceeding 100% FPL (~$1,300/month), so SNAP is $0. value = 0
- kimi-k2.6: answered 0
  explanation: Net SNAP income after allowable deductions for a one-person elderly/disabled household exceeds the 100% FPL net-income limit, resulting in ineligibility. value = 0
- kimi-k3: answered 0
  explanation: One-person elderly/disabled household, so no gross-income test and the $270 bank balance is within asset limits. Monthly countable income is about wages $638 + Social Security survivor $1,077.83 + survivor pension $866 = $2,581.83. After the standard deduction, the 20% earned-income deduction, and a small medical deduction (expenses above $35/month), there is no excess-shelter deduction because $600 rent is below 50% of adjusted income; net income is about $2,214/month, and 30% of that (about $664) far exceeds the one-person maximum allotment, so the benefit is $0. value = 0
- minimax-m3: answered 0
  explanation: Household of 1 elderly/disabled. Gross monthly income $2,581.83 exceeds 130% poverty gross limit (~$2,010). Net income test: after $204 standard deduction, $31.67 excess medical, net income ≈ $2,346/month, exceeds 100% poverty net limit (~$1,180). Not SNAP eligible. value = 0
- ox-alpha: answered 0
  explanation: Gross monthly household income is about $2,582 ($7,656 wages + $23,326 annual benefits divided over 12 months) for a one-person elderly/disabled household, exceeding even the elevated 165% FPL gross income test (about $2,150 per month), so the household is ineligible and receives no SNAP benefit. value = 0
- qwen-3.7-max: answered 0
  explanation: The household of one person age 85 in Wisconsin qualifies for SNAP. Countable income: Gross wages $7,656 minus 20% earned income deduction ($1,531.20) minus standard deduction ($2,196 for 1-person household in FY2026) gives negative, so $0 countable earned. Social Security $12,934 + survivor benefits $10,392 = $23,326 unearned income. After standard deduction $2,196, net unearned income = $21,130. Monthly unearned = $1,760.83. Medical deduction: total medical expenses ($500 + $300 = $800) minus $35/month ($420/year) = $380 allowed, or $31.67/month. Adjusted monthly income = $1,760.83 - $31.67 = $1,729.16. Rent $600/month, utility allowance ~$400/month, shelter = $1,000. Shelter deduction capped at $672/month (FY2026 max). Net monthly income = $1,729.16 - $672 = $1,057.16. 30% of net = $317.15. Max SNAP for 1 person = $292/month (FY2026). Since 30% contribution exceeds max, SNAP would be minimum. However, recalculating with elderly simplified method: countable income after deductions, monthly income ~$1,729, net after shelter deduction ($672 max) = $1,057, 30% = $317 > $292 max, so SNAP = $0. But with proper medical deduction and all expenses: shelter $1,000, income $1,729.16, excess shelter = $1,000 - $864.58 (half of income) = $135.42, net income = $1,729.16 - $135.42 = $1,593.74, 30% = $478 > $292. Revising: the household has high unearned income relative to SNAP limits, resulting in minimal or zero benefit. Applying correctly: total annual income $12,934 + $10,392 + $7,656 = $30,982. Monthly gross = $2,581.83. After earned income deduction ($1,531.20 annual or $127.60/month), standard deduction ($183/month), monthly adjusted earned = $638 - $127.60 = $510.40. Monthly unearned = $1,943.83. Total adjusted = $510.40 + $1,943.83 - $183 = $2,271.23. Medical deduction: ($800 - $420)/12 = $31.67/month. Net adjusted = $2,239.56. Shelter $1,000/month, half net = $1,119.78, excess shelter = $0 (capped). Net income = $2,239.56. 30% = $671.87 > $292 max. SNAP = $0. Final rec [... 92 more characters cut]
- qwen3.8-max: answered 0
  explanation: Household countable income exceeds the SNAP limit for a one-person household, so the household is not eligible for SNAP benefits. value = 0.0

STAGE 1 RESULT (frozen; sha256 0cdda79e68a4f69a7be79eea209fc5908594ab2631e2903c88bb439606195164):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "There is one timing question. Calendar 2026 includes Oct\u2013Dec 2026, which falls in FY2027. USDA's FY2027 COLA raised the minimum benefit to $25, but it was published after the 2026-07-03 freeze. Using it would give 9 \u00d7 $24 + 3 \u00d7 $25 = $291 instead of $288. Under the frozen law, which only had the FY2026 $24 minimum, the answer is $288. A reader who ignored BBCE and applied only the regular EBD net-income test (100% FPL, $1,305) would get $0, but Wisconsin's handbook applies BBCE to EBD units at or below 200% FPL, so that reading is not supported.",
  "citations": [
    {
      "pinpoint": "4.2.1, BBCE and EBD over 200% FPL (current Release 26-02)",
      "pre_freeze": false,
      "published": "2026-08-12",
      "quote": "Most food units are considered broad-based categorically eligible if their gross monthly income is at or below 200% FPL",
      "source": "FoodShare Wisconsin Handbook (WI DHS), 4.2.1 Categorical and Broad-Based Categorical Eligibility",
      "url": "https://www.emhandbooks.wisconsin.gov/fsh/policy_files/4/42/4.2.1.htm"
    },
    {
      "pinpoint": "4.2.1, one- and two-person minimum allotment",
      "pre_freeze": true,
      "published": "2022-12-05",
      "quote": "Except during an initial month, all eligible one- and two-person food units shall receive the minimum $23 allotment when the gross income is below 200% FPL and the net adjusted income exceeds the net income limit.",
      "source": "FoodShare Wisconsin Handbook (WI DHS), 22-03 Version of 4.2.1 Categorical Eligibility",
      "url": "https://www.emhandbooks.wisconsin.gov/fsh/history/22-03/22-03_4.2.1.htm"
    },
    {
      "pinpoint": "4.2.1, EBD food units over 200% FPL",
      "pre_freeze": true,
      "published": "2023-08-14",
      "quote": "Food units that include an elderly, blind or disabled (EBD) member with gross income over 200% of the FPL must be tested for FoodShare using the regular SNAP rules.",
      "source": "FoodShare Wisconsin Handbook (WI DHS), 23-02 Version of 4.2.1 Categorical Eligibility",
      "url": "https://www.emhandbooks.wisconsin.gov/fsh/history/23-02/23-02_4.2.1.htm"
    },
    {
      "pinpoint": "7.1.1.4 Minimum Allotment (Release 26-01)",
      "pre_freeze": true,
      "published": "2026-04-15",
      "quote": "Categorically eligible assistance groups that include one or two persons are eligible for a minimum $24 allotment, except for the initial prorated benefit which cannot be less than $10.",
      "source": "FoodShare Wisconsin Handbook (WI DHS), 7.1.1 Allotments",
      "url": "https://www.emhandbooks.wisconsin.gov/fsh/policy_files/7/7.1.1.htm"
    },
    {
      "pinpoint": "8.1.1 table, household size 1, effective Oct 1 2025\u2013Sep 30 2026 (page updated Release 25-03)",
      "pre_freeze": true,
      "published": "2025-12-10",
      "quote": "The minimum allotment for one- and two-person assistance groups is $24.",
      "source": "FoodShare Wisconsin Handbook (WI DHS), 8.1.1 Income Limits",
      "url": "https://www.emhandbooks.wisconsin.gov/fsh/policy_files/8/81/8.1.1.htm"
    },
    {
      "pinpoint": "8.1.3, standard deduction 1-3 persons, medical, HSUA (Release 25-03, eff. Oct 1 2025)",
      "pre_freeze": true,
      "published": "2025-12-10",
      "quote": "Standard Deduction (1-3 persons): $209 ... Medical Allowance Threshold: Expenses over $35 ... Heating/Standard Utility Allowance: $553",
      "source": "FoodShare Wisconsin Handbook (WI DHS), 8.1.3 Deductions",
      "url": "https://www.emhandbooks.wisconsin.gov/fsh/policy_files/8/81/8.1.3.htm"
    },
    {
      "pinpoint": "1.1.4, income tests",
      "pre_freeze": false,
      "published": "2026-08-12",
      "quote": "Food units that are not categorically eligible must pass the 100% FPL net income test based on FoodShare assistance group size.",
      "source": "FoodShare Wisconsin Handbook (WI DHS), 1.1.4 Eligibility Overview",
      "url": "https://www.emhandbooks.wisconsin.gov/fsh/policy_files/1/11/1.1.4.htm"
    },
    {
      "pinpoint": "\u00a72017(a), minimum allotment for 1- and 2-member households",
      "pre_freeze": true,
      "published": "current code",
      "quote": "8 percent of the cost of the thrifty food plan for a household containing 1 member, as determined by the Secretary under section 2012 of this title, rounded to the nearest whole dollar increment.",
      "source": "7 U.S.C. 2017(a) (Food and Nutrition Act of 2008, sec. 8(a))",
      "url": "https://www.law.cornell.edu/uscode/text/7/2017"
    },
    {
      "pinpoint": "\u00a7273.10(e)(2)(ii)(C)",
      "pre_freeze": true,
      "published": "current regulation",
      "quote": "all eligible one-person and two-person households shall receive minimum monthly allotments equal to the minimum benefit.",
      "source": "7 CFR 273.10 Determining household eligibility and benefit levels",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.10"
    },
    {
      "pinpoint": "FY2027 minimum benefit and 1-person maximum",
      "pre_freeze": false,
      "published": "2026-09-02",
      "quote": "increase from $24 to $25 per month",
      "source": "Newsweek (secondary report of USDA FY2027 SNAP COLA)",
      "url": "https://www.newsweek.com/snap-benefits-are-increasing-october-1-new-payment-amounts-revealed-12393704"
    }
  ],
  "computation": "1) SNAP household: one person, age 85 and disabled, so this is an elderly/disabled (EBD) household in Wisconsin FoodShare.\n2) Monthly gross income:\n   - Wages: $7,656 / 12 = $638.00\n   - SS survivor benefits: $12,934 / 12 = $1,077.83\n   - Other survivor benefits, counted as unearned income: $10,392 / 12 = $866.00\n   - Total: $2,581.83 per month.\n3) Broad-based categorical eligibility (BBCE). WI FSH 4.2.1 makes most food units categorically eligible when gross income is at or below 200% FPL. The FY2026 200% limit for one person (WI FSH 8.1.1, Oct 1 2025 \u2013 Sep 30 2026) is $2,610. Since $2,581.83 \u2264 $2,610, the household is BBCE with no net income test and no asset test. For Oct\u2013Dec 2026, the 2026 HHS guideline of $15,960 (published Jan 2026) gives 200% = $2,660 per month, so the household still qualifies.\n4) Benefit formula (7 CFR 273.10(e); WI FSH 8.1.3 FY2026 values):\n   - Earned income deduction: 20% \u00d7 $638 = $127.60\n   - Standard deduction (1\u20133 persons): $209\n   - Excess medical: ($500 + $300) / 12 = $66.67, minus $35 = $31.67\n   - Adjusted income: $2,581.83 \u2212 $127.60 \u2212 $209 \u2212 $31.67 = $2,213.56\n   - Excess shelter: rent $600 minus half of adjusted income ($1,106.78) gives $0. No utility cost is listed, so no SUA is applied. Even with WI's $553 HSUA, the excess shelter would only be about $46, which changes nothing.\n   - Net income: about $2,213.56; 30% of it is about $664.\n   - Maximum allotment for one person in FY2026 is $298. $298 \u2212 $664 is below zero, so the computed benefit is $0.\n5) Minimum benefit. Under 7 U.S.C. 2017(a) and 7 CFR 273.10(e)(2)(ii)(C), eligible one- and two-person households get the minimum benefit. WI FSH 7.1.1.4 (Release 26-01, 4/15/2026) says categorically eligible one- or two-person groups get a $24 minimum, and WI FSH 8.1.1 (FY2026) also gives $24. Because the household is eligible through BBCE, it gets $24 per month instead of $0.\n6) Annual amount: $24 \u00d7 12 = $288.\n\nWhy the consensus of 0 is wrong: it treats the household only under regular EBD rules (net income \u2264 100% FPL, $1,305, which it fails). It misses that gross income is just under Wisconsin's 200% FPL BBCE limit, which removes the net income test and triggers the one-person minimum benefit.\n\nParameter timing: FY2026 values (max $298, minimum $24, standard deduction $209, 200% FPL $2,610) were published in Aug 2025 and Dec 2025, before the freeze. FY2027 COLA values (max $306, minimum $25, effective Oct 1 2026) were not published until after 2026-07-03, so they were not part of the frozen law.",
  "confidence": "high",
  "definition_reading": "This is the annual SNAP (FoodShare) benefit for the household's single SNAP unit, the 85-year-old disabled head, summed over the 12 months of 2026. Every month the household is eligible through Wisconsin's broad-based categorical eligibility because gross income ($2,581.83) is at or below 200% FPL. Its computed benefit is $0, so as a one-person household it gets the $24 minimum: $24 \u00d7 12 = $288.",
  "independent_answer": 288,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine computes an annual 2026 SNAP total of $288 for this one-person Wisconsin household, the sum of twelve monthly allotments of $24, January through December, with the household assumed to take up the benefit. It passes the gross income test, with monthly gross income of $2,581.83 and an elderly or disabled member, passes the asset test with $270 in assets, and is categorically eligible through Wisconsin's TANF non-cash rules. Its monthly net income is $2,036, giving an expected contribution of $611, which exceeds the $298 maximum allotment for one person in the contiguous US. The benefit therefore falls to the $24 minimum allotment in every month. The poverty guideline in the eligibility tests is $1,304.17 from January through September and $1,330 from October through December, which does not change the monthly amount.
----- END ENGINE DERIVATION -----