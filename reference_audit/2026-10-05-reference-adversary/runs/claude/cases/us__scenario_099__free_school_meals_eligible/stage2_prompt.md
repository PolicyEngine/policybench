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
STATE: CA
OUTPUT: free_school_meals_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only free_school_meals_eligible):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: CA
- tax year: 2026

Head:
- age: 42
- gross wages and salaries: $85,000
- employer sponsored insurance premiums: $18,708
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $2,500
- hourly wage: $42
- usual weekly hours worked: 40
- is paid hourly
- other health insurance premiums: $2,500
- other medical expenses: $2,000
- over-the-counter health expenses: $500
- roth 401k contributions desired: $272
- roth ira contributions desired: $112
- taxable interest income: $500
- traditional 401k contributions desired: $1,544
- traditional ira contributions desired: $72

Spouse:
- age: 41
- gross wages and salaries: $80,000
- bank account assets: $28,035
- charitable cash donations: $11,933
- charitable non-cash donations: $688
- educator expense: $338
- employer sponsored insurance premiums: $5,889
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $2,500
- hourly wage: $31
- usual weekly hours worked: 50
- long-term capital gains: $-7,018
- non-qualified dividend income: $16
- other health insurance premiums: $2,500
- other medical expenses: $2,000
- over-the-counter health expenses: $500
- pre-subsidy rent: $26,400
- qualified dividend income: $128
- real estate taxes: $8,654
- roth 401k contributions desired: $272
- roth ira contributions desired: $112
- short-term capital gains: $540
- stock assets: $2,230,000
- taxable interest income: $510
- traditional 401k contributions desired: $1,544
- traditional ira contributions desired: $72
- unreimbursed employee business expenses: $1,263

Child 1:
- age: 9
- has employer-sponsored insurance
- other medical expenses: $500
- over-the-counter health expenses: $200

Child 2:
- age: 4
- has employer-sponsored insurance
- other medical expenses: $500
- over-the-counter health expenses: $200

Benefit inputs:
- pre-subsidy childcare expenses: $12,740

Household inputs:
- auto loan balance: $42,000
- auto loan interest: $1,575
- household vehicles value: $21,965

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
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_medicaid_eligible: whether Spouse is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_medicaid_eligible: whether Child 1 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_medicaid_eligible: whether Child 2 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_chip_eligible: whether Spouse is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_chip_eligible: whether Child 1 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_chip_eligible: whether Child 2 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- spouse_medicare_eligible: whether Spouse is eligible for Medicare (1 if yes, 0 if no)
- child1_medicare_eligible: whether Child 1 is eligible for Medicare (1 if yes, 0 if no)
- child2_medicare_eligible: whether Child 2 is eligible for Medicare (1 if yes, 0 if no)
- free_school_meals_eligible: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)
- reduced_price_school_meals_eligible: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)
- child1_head_start_eligible: whether Child 1 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child2_head_start_eligible: whether Child 2 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child1_early_head_start_eligible: whether Child 1 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)
- child2_early_head_start_eligible: whether Child 2 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)

Use the `submit_outputs` function exactly once. Return an `outputs` object with every requested quantity keyed by variable name. Each requested key must map to an object with a numeric `value` and a non-empty, specific, concise `explanation`. Each explanation must support the numeric value submitted for the same variable in `outputs`. If an explanation mentions a final amount, that amount must match the corresponding `outputs` value. Do not write that you will use one value while submitting a different value. Do not include scratch work, abandoned calculations, or corrections. End each explanation with `value = X`, where X exactly matches the numeric `value` field. For 1/0 eligibility outputs, submit 1 only when the explanation says eligible or yes, and submit 0 only when it says not eligible or no. Use the exact variable names as keys inside `outputs`. Include every requested key exactly once in `outputs`, even if the value is 0. Put only numeric values in `value`, with no dollar signs, commas, or explanatory text. Do not rely on plain text for the final answers. If an answer is a currency amount, give the annual amount. If an answer is a rate, give a decimal (e.g. 0.25 for 25%).
----- END HOUSEHOLD PROMPT -----

ENGINE REFERENCE VALUE: 1 (eligible)
MODELS: 45 gave a usable answer; 8 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 37 models (3 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Household gross income is about $166,694 (wages $165,000 plus interest, dividends, net capital gains) for a family of 4. Free school meals require income at or below 130% of the federal poverty line (~$41,800 for 4 in 2026); this household is far above that threshold, and even the 185% reduced-price cutoff, so not eligible. value = 0
- claude-fable-5.1: answered 0
  explanation: Household income exceeds 130% FPL and no categorical eligibility; no free meals. value = 0
- claude-haiku-4.5: answered 0
  explanation: The household has two children ages 9 and 4 eligible for school meals programs. For the 2026 tax year in California, eligibility for free school meals is based on household income relative to 130% of the federal poverty line. The household has combined gross wages of $165,000 plus $1,694 in investment income (interest, dividends, and capital gains), totaling approximately $166,694 in gross income. With two school-age children, the household income substantially exceeds 130% of the federal poverty line for a household of 4, making them ineligible for free school meals. The household's significant asset holdings ($2,230,000 in stocks, $28,035 in bank accounts) further support ineligibility based on income and asset limits. value = 0
- claude-opus-4.7: answered 0
  explanation: Household income ($165,000 wages plus investment income) far exceeds the 185% FPL threshold for free school meals for a family of 4 in CA. value = 0
- claude-opus-4.8: answered 0
  explanation: Free school meals eligibility is based on household income relative to the federal poverty level (typically 130% FPL for free meals). This household has combined wages of $165,000 plus investment income, far exceeding the income threshold for a family of four. Therefore no free school meal support is provided. value = 0
- claude-opus-5: answered 0
  explanation: Household income far above 130% FPL and no categorical eligibility. value = 0
- claude-opus-5.5: answered 0
  explanation: Not eligible: income exceeds 130% FPL. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Free school meals (National School Lunch Program free meals) require household income at or below 130% of the federal poverty level. This household has combined gross wages of $165,000 plus additional investment income, far exceeding 130% FPL for a family of 4 (approximately $42,900 in 2026). The household is not eligible for free school meals. value = 0
- claude-sonnet-5: answered 0
  explanation: Household gross income is $165,000 (head $85,000 + spouse $80,000) plus investment income, for a family of 4 in CA. This far exceeds the federal free/reduced-price meal eligibility threshold (185%/130% of poverty line for a family of 4, roughly $57,720/$40,560 in 2026), so the household is not eligible for free school meals. value = 0
- claude-sonnet-5.5: answered 0
  explanation: Not eligible: income of about $165k is far above the free meal threshold of 130% of FPL. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Income far exceeds 130% FPL free-meal limit. value = 0
- deepseek-v4-pro: answered 0
  explanation: Income > 130% FPL. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Household income exceeds 130% FPL, so no free school meal support. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: Income exceeds 130% FPL for free meals. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: Household income exceeds the threshold for free school meals. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: Household income exceeds 130% of the federal poverty line, making the children ineligible for free school meals. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: Household income exceeds the threshold for free school meals. value = 0
- gemini-3.6-flash: answered 0
  explanation: Household income exceeds the eligibility threshold for free school meals. value = 0
- gemini-3.7-flash: answered 0
  explanation: Household income exceeds 130% of the federal poverty guidelines for free school meals. value = 0
- gemini-3.8-flash: answered 0
  explanation: Household income exceeds the income threshold for free school meals, value = 0
- glm-5.2: answered 0
  explanation: The household's adjusted gross income is approximately $156,588, which exceeds 130% of the federal poverty level for a household of 4. Therefore, they are not eligible for free school meals. value = 0
- glm-5.3: answered 0
  explanation: Free school meals require income at or below 130% of poverty (~$43,000 for a family of 4); this household's ~$160,000 income is far above, so no free school meal support, value = 0
- gpt-5.4-mini: answered 0
  explanation: Household income is far above free school meal eligibility thresholds, so no free meal benefit is expected. value = 0
- gpt-5.4-nano: answered 0
  explanation: Free school meal eligibility is not indicated by provided facts; with household wage income likely above thresholds, PolicyEngine returns not eligible, so free_school_meals_eligible = 0. value = 0
- gpt-5.5: answered 0
  explanation: The household’s annual income is far above the federal free school meal limit (130% of poverty) for a four-person household and no categorical eligibility is listed, so PolicyEngine would not return positive free school meal support; not eligible, value = 0
- gpt-5.6-luna: answered 0
  explanation: Household income is above the free-school-meal threshold, so PolicyEngine would not return positive free meal support; value = 0
- gpt-5.6-terra: answered 0
  explanation: Household income is far above the free school-meal income threshold. value = 0
- gpt-6-luna: answered 0
  explanation: Household income exceeds the federal free school-meal income threshold; PolicyEngine would return no positive free-meal support; value = 0
- grok-4.3: answered 0
  explanation: High income makes household ineligible for free school meals. value = 0
- grok-4.5: answered 0
  explanation: Household income far exceeds 130% FPL free-meal threshold and no categorical eligibility; PolicyEngine returns 0 free meal value; value = 0
- grok-4.7: answered 0
  explanation: Income far exceeds the 130% of poverty free-meal limit, and the household is not categorically certified through SNAP, TANF, or Medicaid. Not eligible. value = 0
- grok-build-0.1: answered 0
  explanation: The household is not eligible for free school meals because income far exceeds 130% FPL (about $43,000 for family of 4). value = 0
- kimi-k2.6: answered 0
  explanation: Household gross income from reported wages, interest, dividends, and capital gains is well above 130% of the 2026 federal poverty guideline for a four-person household, and no categorical eligibility factors such as SNAP, TANF, or foster care are present. PolicyEngine therefore returns no annual free school meal support. value = 0
- minimax-m3: answered 0
  explanation: Household income far exceeds free school meal income limits. value = 0.
- ox-alpha: answered 0
  explanation: Free meal eligibility requires income at or below 130% FPL (~$43k for a family of four); household income of about $160k far exceeds it, so PolicyEngine returns no positive free school meal support. value = 0
- qwen-3.7-max: answered 0
  explanation: The household income of approximately $165,000 in gross wages plus other income far exceeds the 130% Federal Poverty Level threshold required for free school meals eligibility for a household of 4 in California. value = 0
- qwen3.8-max: answered 0
  explanation: Household income is above the free school meal income threshold. value = 0

STAGE 1 RESULT (frozen; sha256 0969296e5cc9bdab38ae028b8498935ffdf2516686f4caffa30d14e13b37734e):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "There is a second reading: the flag could mean the federal NSLP/SBP certification tier, meaning whether the household's income (\u2264130% of the poverty guidelines) or categorical status qualifies it as 'free' under 7 CFR 245. The 'reduced-price meals do not count' wording points toward that tier framing. On that reading the household's roughly $166.7k income makes it 'paid', and the answer is 0, the consensus answer. A smaller fact question also exists: the prompt never says the 9-year-old attends a public school. If school enrollment were treated as an unlisted status and therefore false, the answer would also be 0. But age 9 is compulsory school age, and the models did not rely on that point.",
  "citations": [
    {
      "pinpoint": "\u00a749501.5(a)",
      "pre_freeze": true,
      "published": "Current as of 2026-01-01 (operative from school year 2022-23)",
      "quote": "shall make available a nutritionally adequate breakfast and a nutritionally adequate lunch free of charge and with adequate time to eat ... a maximum of one free breakfast meal and one free lunch meal",
      "source": "California Education Code \u00a749501.5 (via FindLaw codes mirror)",
      "url": "https://codes.findlaw.com/ca/education-code/edc-sect-49501-5/"
    },
    {
      "pinpoint": "Universal Meals requirements paragraph",
      "pre_freeze": null,
      "published": "Page last reviewed 2026-09-16; the underlying statute has been operative since 2022-23",
      "quote": "provide two meals free of charge (breakfast and lunch) during each school day to students requesting a meal, regardless of their free or reduced-price meal eligibility",
      "source": "California Department of Education, California Universal Meals",
      "url": "https://www.cde.ca.gov/ls/nu/sn/cauniversalmeals.asp"
    },
    {
      "pinpoint": "Guidelines text, July 1, 2026\u2013June 30, 2027",
      "pre_freeze": true,
      "published": "2026-04-09",
      "quote": "The Department's guidelines for free meals and milk, and reduced price meals were obtained by multiplying the year 2026 Federal income poverty guidelines by 1.30 and 1.85, respectively",
      "source": "USDA Food and Nutrition Service, Child Nutrition Programs: Income Eligibility Guidelines (Federal Register Doc. 2026-06842)",
      "url": "https://www.federalregister.gov/documents/full_text/xml/2026/04/09/2026-06842.xml"
    }
  ],
  "computation": "1) Federal income test (NSLP/SBP). Free meals require household income at or below 130% of the poverty guidelines. Reduced-price meals require income at or below 185%. Source: Child Nutrition Programs Income Eligibility Guidelines, 91 FR, published 2026-04-09, covering 7/1/2026\u20136/30/2027. This household has $165,000 in wages plus about $1,694 of interest, dividends and net capital gain, for about $166.7k. That is far above both cutoffs for a family of 4 (130% of the 2026 guideline is roughly $43k). No categorical eligibility applies: SNAP, TANF and foster status are not listed and are treated as false. So on the federal means test, the children fall in the 'paid' category and are not certified free. This is the consensus reasoning.\n2) California state law. Education Code \u00a749501.5(a) has applied since the 2022-23 school year and was current as of 2026-01-01. It requires every school district, county office and charter school serving TK\u201312 to provide a free breakfast and a free lunch each school day to any pupil who requests one, regardless of federal free or reduced-price eligibility. Both school years that overlap tax year 2026 (2025-26 and 2026-27) are covered.\n3) Applying it to this household. Child 1 is 9, which is compulsory school age in grades 3\u20134. The prompt lists no private or home school, so I assume a CA public school. That child is therefore entitled to two free meals every school day. Child 2 is 4 and may also be TK-eligible, but one child is enough. The household gets positive annual free school meal support, and the support is free meals, not reduced-price ones. The answer is 1.\n4) Amounts. No 2026 amount is decisive. The 2026-27 federal guidelines were published 2026-04-09, before the freeze, and income is far above them in any case. The CA universal-meal mandate depends on no income threshold.",
  "confidence": "high",
  "definition_reading": "I read the output as asking whether the household's children receive free (not reduced-price) school meals during 2026. Under California's Universal Meals Program (Ed Code \u00a749501.5), the 9-year-old, as a public-school pupil, gets a free breakfast and a free lunch every school day whatever the family's income. So the household has positive free school meal support, and the flag is 1. The federal 130%/185% income test does not decide the answer for a CA public-school student.",
  "independent_answer": 1,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine determined that this California household qualifies for free school meals with a total annual benefit value of $1,130.96. The household's school_meal_tier was set to FREE (tier 0) because California has a universal free school meals program, which provides free meals to all enrolled students regardless of income. The household's school_meal_fpg_ratio of 5.03 (calculated from countable income of $166,154 divided by the federal poverty guideline of $33,000 for a family of four) exceeds the categorical eligibility threshold, but this is superseded by the state's universal program. PolicyEngine calculated the benefit by applying the school_meal_daily_subsidy of $7.15 per meal to one child in K-12 school (as indicated by the is_in_k12_school array), yielding the net annual subsidy of $1,130.96.
----- END ENGINE DERIVATION -----