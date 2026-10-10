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

Cite the law you rely on as in stage 1: source, pinpoint, URL, date, pre_freeze and a short quote. The engine derivation is not a citation. Do not consult PolicyEngine or PolicyBench in any form: not policyengine.org, policybench.org, their GitHub repositories, their documentation, their package source, or any calculator built on them. Do not fetch anything from these domains: policybench.org, www.policybench.org, policyengine.org, www.policyengine.org, github.com, raw.githubusercontent.com. When your search tool accepts domains to exclude (blocked_domains), pass all of these domains on every search, so that no result comes from them: a search whose results list or name PolicyEngine or PolicyBench voids your answer. Do not rely on any calculator or estimate built by an AI model. A citation of any of these sources voids your answer.

Your verdict changes no score. A developer adjudicates every case you do not return as reference_holds.

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

STAGE 1 RESULT (frozen; sha256 3a05b091251233dc4c6e1fbe5b41339d7d08a21034906c61e544512aa7316cfa):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "The input labels \"financial assistance\" and \"educational assistance\" do not say what kind of income they are. (a) If the educational assistance were counted as well, for example because the head is not stated to be enrolled and 7 CFR 273.9(c)(3) ties the exclusion to enrollment, gross income would be $2,500/mo. That exceeds the 165% FPIL of $2,152, the household is ineligible, and the answer is $0, the consensus value. Texas TWH A-1322.1, however, exempts educational assistance \"regardless of the source\". (b) If the financial assistance were treated as non-countable, such as a loan or vendor payment, the benefit would be $298 \u2212 30% \u00d7 $657.67 \u2192 $100/mo, or about $1,208/yr (cluster 2). (c) Using the post-freeze FY2027 minimum of $25 for Oct\u2013Dec would give $291.",
  "citations": [
    {
      "pinpoint": "B-471",
      "pre_freeze": true,
      "published": "2015-10-01",
      "quote": "meets the resource criteria to be authorized to receive TANF Non-cash (TANF-NC) services ... has gross income less than or equal to 165 percent of the Federal Poverty Income Limit (FPIL) for its size.",
      "source": "Texas Works Handbook, B-471 Eligibility Criteria (Texas HHSC)",
      "url": "https://fhb.hhs.texas.gov/handbooks/texas-works-handbook/b-470-categorically-eligible-households"
    },
    {
      "pinpoint": "B-472 (Revision 26-1)",
      "pre_freeze": true,
      "published": "2026-01-01",
      "quote": "Categorically eligible households are not subject to the resource and gross or net income limits.",
      "source": "Texas Works Handbook, B-472 Special Treatment for Households Meeting Categorical Eligibility Criteria",
      "url": "https://fhb.hhs.texas.gov/handbooks/texas-works-handbook/b-470-categorically-eligible-households"
    },
    {
      "pinpoint": "A-1322.1 (Revision 15-4)",
      "pre_freeze": true,
      "published": "2015-10-01",
      "quote": "Educational assistance, including educational loans, scholarships, fellowships, grant monies, and work study, are exempt, regardless of the source.",
      "source": "Texas Works Handbook, A-1322.1 Educational Assistance",
      "url": "https://fhb.hhs.texas.gov/handbooks/texas-works-handbook/a-1320-types-income"
    },
    {
      "pinpoint": "A-1326.1 (Revision 18-1), SNAP",
      "pre_freeze": true,
      "published": "2018-01-01",
      "quote": "$300 or less per household in a federal fiscal quarter",
      "source": "Texas Works Handbook, A-1326.1 Cash Gifts and Contributions",
      "url": "https://fhb.hhs.texas.gov/handbooks/texas-works-handbook/a-1320-types-income"
    },
    {
      "pinpoint": "A-1341 net income test",
      "pre_freeze": true,
      "published": "2021-07-01",
      "quote": "This test applies to all households, except categorically eligible households.",
      "source": "Texas Works Handbook, A-1341 Income Limits",
      "url": "https://fhb.hhs.texas.gov/handbooks/texas-works-handbook/a-1340-income-limits"
    },
    {
      "pinpoint": "\u00a7273.9(a)",
      "pre_freeze": true,
      "published": "current text (provision long-standing)",
      "quote": "Households which are categorically eligible as defined in \u00a7 273.2(j)(2) or 273.2(j)(4) do not have to meet either the gross or net income eligibility standards.",
      "source": "7 CFR 273.9 Income and deductions",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.9"
    },
    {
      "pinpoint": "\u00a7273.10(e)(2)(ii)(C)",
      "pre_freeze": true,
      "published": "current text (provision long-standing)",
      "quote": "all eligible one-person and two-person households shall receive minimum monthly allotments equal to the minimum benefit.",
      "source": "7 CFR 273.10 Determining household eligibility and benefit levels",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.10"
    },
    {
      "pinpoint": "\u00a72017(a)",
      "pre_freeze": true,
      "published": "current text",
      "quote": "for households of one and two persons the minimum allotment shall be 8 percent of the cost of the thrifty food plan for a household containing 1 member",
      "source": "7 U.S.C. 2017(a) (Food and Nutrition Act of 2008 \u00a78(a))",
      "url": "https://www.law.cornell.edu/uscode/text/7/2017"
    },
    {
      "pinpoint": "Appendix A, effective October 2025",
      "pre_freeze": true,
      "published": "2025-10-01",
      "quote": "One and Two Person households that are categorically eligible will be eligible for at least $24, even if the tables do not show a benefit amount at their net income levels.",
      "source": "Georgia DFCS SNAP Manual, Appendix A SNAP Income Limits (FY2026 federal parameters)",
      "url": "https://pamms.dhs.ga.gov/dfcs/snap/appendix-a-food-stamp-income-limits/"
    },
    {
      "pinpoint": "C-1431 (Revision 26-4)",
      "pre_freeze": false,
      "published": "2026-10-01",
      "quote": "The shaded portions on the SNAP Allotment Chart (PDF) show monthly, not prorated, allotments available to categorically eligible households. This can be $1 or more.",
      "source": "Texas Works Handbook, C-1430 SNAP Allotment Charts",
      "url": "https://fhb.hhs.texas.gov/handbooks/texas-works-handbook/c-1430-snap-allotment-charts"
    }
  ],
  "computation": "One-person SNAP household. The pregnant head counts alone, because an unborn child is not a SNAP household member. Texas, using FY2026 parameters (Oct 1, 2025 \u2013 Sep 30, 2026), which were the latest published before the 2026-07-03 freeze.\n1) Income. Wages are $13,000/12 = $1,083.33/mo of earned income. Under Texas Works Handbook (TWH) A-1326.1, cash gifts and contributions count as unearned income for SNAP, so the $12,000 of financial assistance is $1,000/mo unearned. Under TWH A-1322.1, educational assistance is exempt \"regardless of the source\", so the $5,000 is excluded. Gross income is $2,083.33/mo.\n2) Eligibility through Texas broad-based categorical eligibility (TWH B-471). The household meets the TANF non-cash resource criteria, since $190 in the bank is under the $5,000 limit. Gross income must be at or below 165% of the federal poverty income limit (FPIL); for one person in FY2026 that is $2,152. $2,083.33 \u2264 $2,152, so the household is categorically eligible. Under TWH B-472 and 7 CFR 273.9(a), categorically eligible households are not subject to the 130% gross ($1,696) or 100% net ($1,305) income tests. No IPV or other disqualification is listed. The head is pregnant and works 35 hours a week, so no work rule bars her.\n3) Net income (7 CFR 273.10(e)(1)). The 20% earned income deduction is $216.67. The standard deduction for 1\u20133 persons is $209 for FY2026. There is no medical deduction because the head is not elderly or disabled (7 CFR 273.9(d)(3)). There is no shelter deduction because no rent or utilities are listed. Net income is $2,083.33 \u2212 $216.67 \u2212 $209 = $1,657.67.\n4) Formula benefit. 30% of $1,657.67 is $497.30, rounded up to $498. $298 \u2212 $498 < 0, so the formula gives $0.\n5) Minimum benefit. Under 7 U.S.C. 2017(a) and 7 CFR 273.10(e)(2)(ii)(C), eligible one- and two-person households receive the minimum benefit. That is 8% of $298 = $23.84, rounded to $24 for FY2026. State manuals confirm this applies to categorically eligible households even when the tables show no benefit at their net income. Texas C-1431 shades allotments of \"$1 or more\" available to categorically eligible households. The monthly benefit is $24.\n6) Annual: $24 \u00d7 12 = $288.\nNotes:\n- FY2027 values took effect Oct 1, 2026: a $25 minimum and a $217 standard deduction. They were published after the freeze (Texas chart Revision 26-4). Applying them for Oct\u2013Dec would give 9 \u00d7 $24 + 3 \u00d7 $25 = $291. Under the frozen law, $288.\n- If the financial assistance came from a nonprofit based on need, only $300/quarter would be excluded. Gross income would still be \u2264 $2,152 and the benefit would still be the $24 minimum.\n- The consensus answer of $0 mostly relied on the 130% gross test, which Texas broad-based categorical eligibility displaces. Or it counted the educational assistance, which Texas exempts.",
  "confidence": "medium",
  "definition_reading": "I read the output as the annual SNAP allotment for the single SNAP household made up of the pregnant head (household size 1) in Texas for calendar 2026. FY2026 federal parameters are used, as published before the freeze: $298 maximum, $209 standard deduction, $24 minimum, and $2,152 as the 165% FPIL for one person. The listed \"financial assistance\" is treated as countable cash contributions, and the \"educational assistance\" as exempt educational assistance.",
  "independent_answer": 288,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine computes an annual 2026 SNAP total of $288 for this one-person Texas household, the sum of twelve monthly allotments of $24. The household is eligible every month. Its $190 in bank assets pass the asset test, and it is categorically eligible through TANF non-cash eligibility. Monthly gross income is $2,083.33, including $1,083.33 of earned income, and monthly net income is $1,658. Gross and net income are 1.6 and 1.27 times the $1,304.17 poverty guideline from January through September, and 1.57 and 1.25 times $1,330 from October through December. Each month the expected contribution computed from net income is $498. That exceeds the $298 maximum allotment for a one-person household in the contiguous US, so the benefit is the $24 minimum allotment.
----- END ENGINE DERIVATION -----