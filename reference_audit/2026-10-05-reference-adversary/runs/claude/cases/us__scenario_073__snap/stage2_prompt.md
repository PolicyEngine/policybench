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
STATE: MI
OUTPUT: snap (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: annual SNAP (food stamps) benefit amount

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only snap):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: MI
- tax year: 2026

Head:
- age: 57
- bank account assets: $1,800
- employer sponsored insurance premiums: $5,789
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $2,600
- usual weekly hours worked: 40
- other health insurance premiums: $2,600
- over-the-counter health expenses: $100
- roth 401k contributions desired: $981
- roth ira contributions desired: $403
- Social Security disability income: $22,646
- stock assets: $1,800
- taxable private pension income: $3,108
- traditional 401k contributions desired: $5,557
- traditional ira contributions desired: $260

Tax unit:
- first home mortgage balance: $219,000

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

Cluster 1: 0, given by 37 models (5 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Single-person household, disabled (SSDI recipient). Gross income = $22,646 SSDI + $3,108 pension = $25,754/yr ≈ $2,146/mo. Michigan uses BBCE with a 200% FPL gross income test for most households; 200% FPL for 1 person is about $2,608/mo, so gross test is passed. However, the elderly/disabled net income test (100% FPL ≈ $1,304/mo) applies: net income = $2,146 − $199 standard deduction − 20% earned income deduction (none, all unearned) = $1,947; excess medical expenses over $35 (premiums $2,600/12 ≈ $217 + OTC $8 = $225; $225 − $35 = $190 deduction) reduce net to about $1,757/mo, still well above the ~$1,304 net limit. With net income exceeding the limit, benefit = max allotment − 0.3×net income is negative, so SNAP benefit is $0. value = 0
- claude-fable-5.1: answered 0
  explanation: Gross monthly income $2,146 (SSDI + pension). Disabled household so gross test waived, but net test applies: $2,146 - $209 standard deduction - excess medical deduction (($2,600 premiums + $100 OTC)/12 - $35 = $190) = $1,747, no shelter costs, which exceeds the 1-person net income limit of about $1,305. Ineligible. value = 0
- claude-haiku-4.5: answered 0
  explanation: The household head has annual income of $22,646 (Social Security Disability Income) plus $3,108 (taxable private pension income) = $25,754. In Michigan for 2026, SNAP eligibility typically requires income at or below 130% of the federal poverty line. For a single-person household, the 2026 poverty line is approximately $14,387, so 130% = $18,703. With income of $25,754 exceeding this limit, and liquid assets of $3,600 (bank account $1,800 + stock assets $1,800) exceeding the SNAP asset limit of $2,750 for a single individual, the household is not eligible for SNAP benefits. value = 0
- claude-opus-4.8: answered 0
  explanation: Michigan SNAP, household of 1, age 57. Gross income: Social Security disability $22,646 plus pension $3,108 = $25,754/year (~$2,146/month). For a 1-person household the FY2026 gross income limit (130% FPL) is roughly $1,696/month. The household's monthly gross income exceeds this limit. Although there is no elderly/disabled gross-income exemption issue here (head is disabled receiving SSDI, so household may bypass the gross test and use net income test and uncapped shelter deduction), net income after deductions still exceeds the net income limit (100% FPL ~$1,305/month): standard deduction (~$204) plus medical expenses over $35 and excess shelter deduction reduce income, but net income remains above the eligibility threshold for a 1-person household. Therefore no SNAP benefit. value = 0
- claude-opus-5.5: answered 0
  explanation: Monthly income is about $2,146. After the standard deduction (~$209) and the medical deduction (~$190), net income is about $1,747. That exceeds the 100% FPL net income limit of about $1,305 for this disabled one-person household, so SNAP is $0. value = 0
- claude-sonnet-4.6: answered 0
  explanation: SNAP eligibility requires gross income at or below 130% of the Federal Poverty Level (FPL) for most households, or net income at or below 100% FPL. The household has one person (age 57) with Social Security disability income of $22,646/year and taxable private pension income of $3,108/year, giving gross countable income of $25,754/year. For a 1-person household in 2026, 130% FPL is approximately $20,618/year ($1,585/month). The gross income of $25,754 exceeds this limit. While households with an elderly or disabled member are exempt from the gross income test, they must still pass the net income test (100% FPL ≈ $15,060/year for 1 person). Net income: $25,754 minus the standard deduction (~$204/month = $2,448/year) minus earned income deduction (no earned income) minus medical deduction for disability/elderly (out-of-pocket medical expenses above $35/month threshold: health insurance premiums of $2,600 + OTC health expenses of $100 = $2,700/year; minus employer-sponsored insurance premiums of $5,789 already paid pre-tax — however, the $2,600 listed as 'other health insurance premiums' and OTC $100 are out-of-pocket; deductible medical = $2,700 - $420 ($35×12) = $2,280/year) minus excess shelter deduction (mortgage interest on $219,000 balance; no rent listed; without more detail, assume no shelter deduction beyond standard). Net income ≈ $25,754 - $2,448 - $2,280 = $21,026/year ($1,752/month). 100% FPL for 1 person ≈ $1,255/month. Net income of $1,752/month exceeds the net income limit of $1,255/month. The household does not pass the net income test and is therefore ineligible for SNAP. Annual SNAP benefit = $0. value = 0
- claude-sonnet-5: answered 0
  explanation: Single household with gross monthly income of about $2,146 (SSDI $1,887 + pension $259) exceeds the SNAP 200% gross income limit test only marginally, but after standard deduction, medical expense deduction (elderly/disabled, premiums ~$217/mo + OTC), and mortgage-related shelter costs, net income remains high relative to a 1-person household's net income limit of $1,255/mo (2026 est.), resulting in a net income that eliminates any benefit due to the high unearned income level exceeding the maximum benefit offset (30% net income rule reduces benefit to $0). value = 0
- claude-sonnet-5.5: answered 0
  explanation: Countable income is about 2,146 a month. After the standard deduction and a medical deduction, net income is about 1,750 a month. No shelter costs are listed. This exceeds the roughly 100% FPL net income limit for elderly/disabled households, so the benefit is 0. value = 0
- deepseek-v4-pro: answered 0
  explanation: Gross income $25,754 exceeds 130% FPL for single (~$19,578), failing the gross income test. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Monthly cash income of about $2,146 (SSDI plus pension) exceeds the SNAP net income limit for a one-person household after deductions, so annual SNAP is $0. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: Gross income $25,754 and net income after deductions exceed SNAP limits, producing no benefit. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household's countable income exceeds the SNAP eligibility threshold for a one-person household. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: Because there are no shelter or utility expenses to claim as deductions, 30% of the household's net income exceeds the maximum allowable benefit. value = 0
- gemini-3.5-flash: answered 0
  explanation: The household's gross monthly income from SSDI ($1,887.17) and pension ($259.00) totals $2,146.17. Although exempt from the gross income limit due to disability, their calculated net income of $1,541.50 results in a SNAP allotment of $0 because 30% of their net income ($462.45) exceeds the maximum monthly benefit. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Household assets and income exceed SNAP limits or PolicyEngine calculates $0 SNAP benefits. value = 0
- gemini-3.7-flash: answered 0
  explanation: Household net income exceeds the maximum limit to receive positive SNAP benefits. value = 0
- gemini-3.8-flash: answered 0
  explanation: Head's net income exceeds the maximum net income eligibility threshold, and thirty percent of net income exceeds the maximum SNAP allotment, resulting in zero SNAP benefit. value = 0
- glm-5.2: answered 0
  explanation: The household has one disabled member (receiving SSDI of $22,646/yr) plus taxable pension income of $3,108/yr, totaling $25,754 in unearned income. As a disabled household, the gross income test is waived. Annual medical expenses of $11,089 yield a medical deduction of $10,669 (excess over $420/yr), and the standard deduction is $2,448. Net annual income = $25,754 - $2,448 - $10,669 = $12,637 ($1,053.08/mo). This passes the net income test (below ~100% FPL). However, the monthly SNAP benefit = max allotment (~$292) - 30% of net income (0.30 × $1,053.08 = $315.92) = -$23.92, which is at or below zero, so no benefit is paid. value = 0
- glm-5.3: answered 0
  explanation: Countable income of $3,108 pension plus $22,646 SSDI is about $25,754, well above the net income limit for a one-person SNAP household (about $15,060, roughly 100% of poverty), so annual SNAP benefit is 0. value = 0
- gpt-5.4-mini: answered 0
  explanation: Household income is well above SNAP eligibility limits for a one-person household, so no SNAP benefit is payable. value = 0
- gpt-5.4-nano: answered 0
  explanation: SNAP eligibility is not established from the provided facts; with no earned income details and no housing cost details or SNAP take-up indicators, the policy estimate yields 0. value = 0
- gpt-5.6-luna: answered 0
  explanation: With no qualifying elderly or disabled status listed, the household fails the applicable SNAP gross-income test on annual SSDI and pension income. value = 0
- gpt-5.6-sol: answered 0
  explanation: For a one-person household, the listed annual SSDI and pension income is too high to produce a positive SNAP allotment after the applicable deductions and benefit reduction. value = 0
- gpt-5.6-terra: answered 0
  explanation: Although the head receives disability income, counted income after standard and stated medical deductions still exceeds the amount that would yield a SNAP benefit for one person. value = 0
- gpt-6-luna: answered 0
  explanation: With no listed shelter expense, the household's countable income leaves no positive SNAP allotment after deductions. value = 0
- gpt-6-sol: answered 0
  explanation: Monthly disability and pension income totals about 2146, and no rent or other shelter costs are listed; calculated SNAP support is zero; value = 0
- grok-4.3: answered 0
  explanation: Household income from SSDI exceeds SNAP net income limit for household size of 1. value = 0
- grok-4.5: answered 0
  explanation: Disabled one-person household with countable assets under the higher limit is subject only to net-income test; after standard and excess medical deductions net income still produces a 30-percent reduction that fully offsets the maximum allotment so annual SNAP benefit is zero. value = 0
- grok-4.6: answered 0
  explanation: Annual countable income is $25,754 SSDI plus pension. With no listed shelter costs and no earned-income deduction, net income after the SNAP standard deduction leaves 30% of net income above the one-person maximum allotment, so the SNAP benefit is $0. value = 0
- grok-4.7: answered 0
  explanation: Gross income is $25,754. Countable out-of-pocket medical costs and the standard deduction do not bring net income to or below 100% of poverty, and no shelter costs are listed, so the annual SNAP benefit is zero. value = 0
- grok-build-0.1: answered 0
  explanation: Gross annual income $25,754. Monthly net income after ~$200 standard deduction and ~$672 excess medical deduction (from $8,489 premiums + OTC) is ~$1,274. 30% of net (~$382) exceeds 1-person max SNAP allotment (~$310), so annual benefit $0. value = 0
- kimi-k2.6: answered 0
  explanation: The one-person household has $25,754 in gross unearned income from SSDI and a taxable pension. After applicable SNAP deductions, net income remains high enough that 30% of net income exceeds the maximum allotment for a single-person household, leaving no benefit. value = 0
- kimi-k3: answered 0
  explanation: Monthly countable income is SSDI $22,646/12 = $1,887.17 plus pension $3,108/12 = $259, about $2,146, with $0 earnings. After the standard deduction, net income is about $1,942, which exceeds the 100%-FPL net limit for a one-person disabled household (about $1,304/month), and 30% of net income (about $583) exceeds the one-person maximum allotment (about $298), so the computed allotment is $0. value = 0
- minimax-m3: answered 0
  explanation: With $25,754 in annual income and $1,800 in countable assets, the household exceeds both the gross and net SNAP income limits for a single-person household. value = 0
- ox-alpha: answered 0
  explanation: One-person household with $25,754 annual gross income (~$2,146/month) from SSDI and pension. Even under Michigan's broad-based categorial eligibility net-income test, net income after only the ~$204 standard deduction (no shelter, care, or applicable medical deductions) is ~$1,942/month, exceeding the 100% FPL net limit (~$1,304/month), so the household is ineligible and benefits are $0. value = 0
- qwen-3.7-max: answered 0
  explanation: The head is 57, not elderly (60+) or disabled for SNAP purposes based on listed facts (SSDI indicates disability, but SNAP gross income test applies). Gross income includes SSDI ($22,646) and taxable private pension ($3,108) totaling $25,754. For a 1-person household in FY2026, the SNAP gross income limit (130% of FPL) is about $1,311/month ($15,732/year). Gross income of $25,754 exceeds the limit, so the household is not eligible for SNAP. value = 0
- qwen3.8-max: answered 0
  explanation: The household's countable resources include bank account assets of $1,800 and stock assets of $1,800, totaling $3,600, which exceeds the SNAP resource limit for this household. Therefore the household is not eligible for SNAP. value = 0

STAGE 1 RESULT (frozen; sha256 794fcb60bef84f72ce507623a79725cc92c5c7c339612644267c9b5d87953098):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "The inputs are unclear on which medical costs count: employer premiums of $5,789, two premium fields of $2,600 each, and $100 of over-the-counter costs. Under every reading the net income is high enough that 30% of it exceeds the $298 maximum, so the computed benefit is $0 either way. The answer turns on whether categorical eligibility waives the net income test. Under Michigan BEM 213 and 7 CFR 273.9(a) it does, because gross income ($2,146) is below 200% of poverty (about $2,608), and the $24 minimum then applies: $288 a year. Only a reading that wrongly applies the 100%-of-poverty net income test to this categorically eligible household gives the consensus $0. That reading fails when the narrow medical deduction leaves net income at about $1,747, above the roughly $1,305 limit. Under broader medical readings the net income test is passed anyway, and the $24 minimum applies with or without categorical eligibility. So I do not treat $0 as a reasonable reading of the law.",
  "citations": [
    {
      "pinpoint": "FAP \u2013 categorical eligibility; SDV groups above 200 percent",
      "pre_freeze": true,
      "published": "2026-02-01",
      "quote": "Groups which contain an SDV member and whose gross income is above 200 percent are not categorically eligible.",
      "source": "Michigan DHHS Bridges Eligibility Manual BEM 213, Categorical Eligibility (BPB 2026-003)",
      "url": "https://mdhhs-pres-prod.michigan.gov/olmweb/ex/BP/Public/BEM/213.pdf"
    },
    {
      "pinpoint": "\u00a7 273.9(a)",
      "pre_freeze": true,
      "published": "current CFR (in force for FY2026)",
      "quote": "Households which are categorically eligible as defined in \u00a7 273.2(j)(2) or 273.2(j)(4) do not have to meet either the gross or net income eligibility standards.",
      "source": "Code of Federal Regulations, 7 CFR 273.9 Income and deductions",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.9"
    },
    {
      "pinpoint": "\u00a7 273.10(e)(2)(ii)(A) and (C)",
      "pre_freeze": true,
      "published": "current CFR (in force for FY2026)",
      "quote": "all eligible one-person and two-person households shall receive minimum monthly allotments equal the minimum benefit. The minimum benefit is 8 percent of the maximum allotment for a household of one",
      "source": "Code of Federal Regulations, 7 CFR 273.10 Determining household eligibility and benefit levels",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.10"
    },
    {
      "pinpoint": "\u00a7 2017(a)",
      "pre_freeze": true,
      "published": "current U.S. Code",
      "quote": "the minimum allotment shall be 8 percent of the cost of the thrifty food plan for a household containing 1 member",
      "source": "7 U.S.C. 2017 (Food and Nutrition Act of 2008 \u00a7 8)",
      "url": "https://www.law.cornell.edu/uscode/text/7/2017"
    },
    {
      "pinpoint": "Minimum benefit; maximum allotments; standard deduction (48 States and DC)",
      "pre_freeze": true,
      "published": "2025-08 (effective 2025-10-01)",
      "quote": "The minimum benefit for the 48 States and D.C. will increase to $24.",
      "source": "USDA Food and Nutrition Service, SNAP Fiscal Year 2026 Cost-of-Living Adjustments memo",
      "url": "https://www.usda.gov/sites/default/files/guidance-documents/fns.snap-cola-fy26memo.pdf"
    }
  ],
  "computation": "Household: one person, age 57, Michigan, FY2026 SNAP year (Oct 1 2025\u2013Sep 30 2026, used for 2026).\n1) Gross monthly income = SSDI $22,646/12 ($1,887.17) + pension $3,108/12 ($259.00) = $2,146.17. There is no earned income.\n2) Michigan broad-based categorical eligibility (BEM 213, effective 2026-02-01). A food assistance group with gross income at or below 200% of poverty is categorically eligible. Only groups with a senior, disabled or disabled-veteran member whose gross income is ABOVE 200% must pass the net income and asset tests. 200% of the 2025 HHS poverty guideline for one person ($15,650/yr) is about $2,608/month. $2,146 is below that, so the household is categorically eligible. This holds whether or not SSDI receipt makes the head 'disabled'.\n3) Federal rule 7 CFR 273.9(a): categorically eligible households 'do not have to meet either the gross or net income eligibility standards.' The net income test (100% of poverty, about $1,305) that the consensus applied therefore does not bind. Assets ($3,600) are also irrelevant: there is no asset test for categorically eligible groups, and Michigan's limit for other disabled groups is higher anyway.\n4) Benefit computation (7 CFR 273.10(e)(2)(ii)(A)): FY2026 maximum allotment for one person is $298; the standard deduction is $209. The medical deduction is medical costs over $35 a month, for an elderly or disabled member.\n- Narrow medical reading (premiums $2,600 + OTC $100): deduction $190, net $1,747.17, 30% = $524.\n- ESI premiums added ($8,489/yr): deduction $672.42, net $1,264.75, 30% = $379.\n- Every premium field added ($11,089/yr): deduction $889.08, net $1,048.09, 30% = $314.\nNo shelter costs are listed (no rent and no mortgage payment), so there is no shelter deduction. In every case 30% of net income exceeds $298, so the computed allotment is $0.\n5) Minimum benefit (7 U.S.C. 2017(a); 7 CFR 273.10(e)(2)(ii)(C)): every eligible one- or two-person household receives the minimum, which is 8% of the one-person thrifty food plan. For FY2026 in the 48 states and DC that is $24. The household is eligible through step 2, so it gets $24 a month.\n6) Annual amount: $24 \u00d7 12 = $288.\nThe FY2026 figures ($298 maximum, $209 standard deduction, $24 minimum) were published by USDA FNS in its August 2025 cost-of-living memo, effective 2025-10-01, before the freeze. The FY2027 figures take effect 2026-10-01 and fall outside the FY2026 period used here. The work rules do not affect the result: the head is listed as working 40 hours a week and receives disability benefits.\nSource access: the Michigan manual PDFs (BEM 213, BEM 550, RFT 250) and the USDA FY2026 memo could not be opened directly; WebFetch returned unreadable binary PDF content or HTTP 403. Their quotes come from search-index excerpts of those official pages. The federal rules were read directly from Cornell LII.",
  "confidence": "high",
  "definition_reading": "'snap' is the annual SNAP allotment for the household's single SNAP unit: the head, a one-person household. It is the monthly allotment for FY2026 times 12. Take-up is assumed, so the household is assumed to receive the Michigan categorical-eligibility service and to apply.",
  "independent_answer": 288,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine computes an annual 2026 SNAP total of $288 for this single-adult Michigan household, the sum of twelve monthly benefits of $24. In every month the household is eligible: it passes the gross income test, its $3,600 in assets ($1,800 in a bank account and $1,800 in stock) pass the asset test, it has an elderly or disabled member, and it is categorically eligible through Michigan's TANF non-cash rules. Monthly gross income is $2,146.13 and net income is $1,755, giving an expected contribution of $527, which exceeds the $298 maximum allotment for one person in the contiguous US. The benefit therefore falls to the $24 minimum allotment. The poverty guideline is $1,304.17 from January through September and $1,330 from October through December, moving the gross income ratio from 1.65 to 1.61 without changing the $24 benefit.
----- END ENGINE DERIVATION -----