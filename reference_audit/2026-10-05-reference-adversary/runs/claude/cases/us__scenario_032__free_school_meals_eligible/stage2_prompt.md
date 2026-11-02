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
STATE: MN
OUTPUT: free_school_meals_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only free_school_meals_eligible):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: MN
- tax year: 2026

Head:
- age: 50
- gross wages and salaries: $29,000
- bank account assets: $11,300
- hourly wage: $16
- usual weekly hours worked: 36
- is paid hourly
- other medical expenses: $50
- over-the-counter health expenses: $200
- Social Security dependent benefits: $13,664

Spouse:
- age: 18
- over-the-counter health expenses: $100

Child 1:
- age: 6
- over-the-counter health expenses: $100

Benefit inputs:
- spm unit energy subsidy: $50

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
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_medicaid_eligible: whether Spouse is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_medicaid_eligible: whether Child 1 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_chip_eligible: whether Spouse is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_chip_eligible: whether Child 1 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- spouse_medicare_eligible: whether Spouse is eligible for Medicare (1 if yes, 0 if no)
- child1_medicare_eligible: whether Child 1 is eligible for Medicare (1 if yes, 0 if no)
- free_school_meals_eligible: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)
- reduced_price_school_meals_eligible: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)
- child1_head_start_eligible: whether Child 1 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child1_early_head_start_eligible: whether Child 1 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)

Use the `submit_outputs` function exactly once. Return an `outputs` object with every requested quantity keyed by variable name. Each requested key must map to an object with a numeric `value` and a non-empty, specific, concise `explanation`. Each explanation must support the numeric value submitted for the same variable in `outputs`. If an explanation mentions a final amount, that amount must match the corresponding `outputs` value. Do not write that you will use one value while submitting a different value. Do not include scratch work, abandoned calculations, or corrections. End each explanation with `value = X`, where X exactly matches the numeric `value` field. For 1/0 eligibility outputs, submit 1 only when the explanation says eligible or yes, and submit 0 only when it says not eligible or no. Use the exact variable names as keys inside `outputs`. Include every requested key exactly once in `outputs`, even if the value is 0. Put only numeric values in `value`, with no dollar signs, commas, or explanatory text. Do not rely on plain text for the final answers. If an answer is a currency amount, give the annual amount. If an answer is a rate, give a decimal (e.g. 0.25 for 25%).
----- END HOUSEHOLD PROMPT -----

ENGINE REFERENCE VALUE: 1 (eligible)
MODELS: 45 gave a usable answer; 22 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 23 models (3 of them among the benchmark's top-ranked models)
- claude-fable-5.1: answered 0
  explanation: Household income 42,664 is above 130% FPL for 3 (~34,645) and no categorical eligibility (no SNAP/TANF), so no free-meal support. value = 0
- claude-opus-5: answered 0
  explanation: Household income (~$42,664, about 170% FPL for a family of 3) exceeds the 130% FPL free meal threshold and the household is not categorically eligible via TANF/SNAP direct certification in this calculation. value = 0
- claude-opus-5.5: answered 0
  explanation: Income at about 160% of the poverty line exceeds the 130% free meal limit, so not eligible. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Free school meals (as opposed to reduced-price meals) in Minnesota through the National School Lunch Program require household income at or below 130% of the Federal Poverty Level (FPL). The household consists of 3 members (head age 50, spouse age 18, child age 6). For 2026, 130% FPL for a 3-person household is approximately $37,777. Household income includes gross wages of $29,000 and Social Security dependent benefits of $13,664, totaling $42,664. This exceeds the 130% FPL threshold of ~$37,777, so the household does not qualify for free school meals (only potentially reduced-price, which does not count as eligible here). value = 0
- claude-sonnet-5.5: answered 0
  explanation: Countable income of about 42,700 (wages plus Social Security) is above 130% of the FPL for 3 (about 34,600). Not eligible for free meals. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Household income (~157% FPL) exceeds the 130% FPL free-meal threshold, so no free meal support. value = 0
- deepseek-v4-pro: answered 0
  explanation: Income $42,664 > 130% FPL $35,326; not free-eligible. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: Household income $42,664 exceeds 130% FPL for 3 (~$35,750). value = 0
- gemini-3.8-flash: answered 0
  explanation: Household income of $42,664 exceeds 130% of the federal poverty line for a household of 3, making the child ineligible for federal free school meals, value = 0
- glm-5.2: answered 0
  explanation: Total household income for school meal purposes is $42,664 ($29,000 wages + $13,664 Social Security dependent benefits). This is above 130% of the 2026 federal poverty guideline for a household of 3, so the household is not eligible for free school meals. value = 0
- glm-5.3: answered 0
  explanation: Household income of $42,664 is about 153% of the federal poverty guideline, above the 130% cutoff for free school meals. value = 0
- gpt-5.4-nano: answered 0
  explanation: Free school meal eligibility is not provided and no categorical eligibility (e.g., SNAP/TANF receipt) is given; with SNAP/TANF outputs set to 0, the household is assumed not eligible for free meals; value = 0
- gpt-5.5: answered 0
  explanation: The household has a school-age child, but annual countable income of $42,664 is above the federal free-meal limit for a 3-person household and no categorical free-meal status is indicated, so free school meals are not eligible; value = 0
- gpt-5.6-luna: answered 0
  explanation: Household income is above the federal free-school-meal threshold for three people, so positive free-meal support is not returned; value = 0
- gpt-5.6-terra: answered 0
  explanation: Reported household income is above the modeled federal free school-meal income threshold and no direct-certification benefit is reported; value = 0
- gpt-6-luna: answered 0
  explanation: Estimated household income exceeds the free-meal income threshold for a three-person household; no free-meal support is expected. value = 0
- grok-4.5: answered 0
  explanation: Household money income of 42664 is approximately 156 percent of the projected 2026 FPL for three, above the 130 percent free-meal limit, so the household is not eligible for free school meals. value = 0
- grok-4.6: answered 0
  explanation: Household MAGI of about 156 percent of FPL exceeds the 130 percent free-meal limit and the unit is not SNAP/TANF categorically eligible, so PolicyEngine does not return positive free school meal support. value = 0
- grok-4.7: answered 0
  explanation: Gross income including Social Security is $42,664, about 156-160% FPL, which is above the 130% free-meal limit. SNAP and TANF are $0, so there is no categorical free-meal eligibility. The household is not eligible for free school meals. value = 0
- grok-build-0.1: answered 0
  explanation: Household gross income of $42,664 is approximately 156.7% of the 2026 FPL for a 3-person household (~$27,207), exceeding the 130% FPL threshold for free school meals. value = 0
- inkling: answered 0
  explanation: Household gross income (~$42,664 for 3) is above 130% FPL ($33,566), so they do not qualify for free school meals. value = 0
- kimi-k3: answered 0
  explanation: Under PolicyEngine's federal school-meal income test, household income is about 156% of poverty, above the 130% free-meal limit, so the household is not eligible for free-meal support. value = 0
- ox-alpha: answered 0
  explanation: Countable household income including the $13,664 Social Security benefit is $42,664, about 160% of the 3-person poverty line, above the 130% free-meal cutoff, and there is no SNAP/TANF categorical pathway. value = 0

STAGE 1 RESULT (frozen; sha256 0f47256b9a41d0d8e764801949862c7dcded61873361c9d21c187c64f12a0ab1):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "There are two other readings. First, the output could mean only the federal NSLP free-meal tier: income at or below 130% of the poverty line, or categorical eligibility through SNAP, TANF or FDPIR receipt. On that reading the household, at about 156% of the poverty line with no SNAP or TANF, is federally reduced-price only and the answer is 0, the consensus value. But the definition asks about free meal support the household actually receives, and Minnesota law makes the meal free to the student, so I think the federal-tier-only reading is the weaker one. Second, the prompt never says the child is enrolled in school, and Minnesota's compulsory attendance age is 7. Every model treated the 6-year-old as a school-age student, and I do the same. If the child were treated as not enrolled, the answer would be 0 under either reading.",
  "citations": [
    {
      "pinpoint": "Subd. 1c(d)(2)",
      "pre_freeze": true,
      "published": "2025 (as amended by 1Sp2025 c 10 art 9 ss 1-4)",
      "quote": "provide to all students at no cost up to two federally reimbursable meals per school day, with a maximum of one free breakfast and one free lunch.",
      "source": "Minnesota Statutes \u00a7 124D.111 (2025 Minnesota Statutes), Free school meals program",
      "url": "https://www.revisor.mn.gov/statutes/cite/124D.111"
    },
    {
      "pinpoint": "Subd. 1c(b)",
      "pre_freeze": true,
      "published": "2025 (as amended by 1Sp2025 c 10 art 9 ss 1-4)",
      "quote": "must participate in the free school meals program.",
      "source": "Minnesota Statutes \u00a7 124D.111 (2025 Minnesota Statutes)",
      "url": "https://www.revisor.mn.gov/statutes/cite/124D.111"
    },
    {
      "pinpoint": "Subd. 1d",
      "pre_freeze": true,
      "published": "2025",
      "quote": "the difference between the applicable federal reimbursement rate at that school site for a free meal ... and the actual federal reimbursement received by the participating school.",
      "source": "Minnesota Statutes \u00a7 124D.111 (2025 Minnesota Statutes), Free school meals program aid amount",
      "url": "https://www.revisor.mn.gov/statutes/cite/124D.111"
    },
    {
      "pinpoint": "Supplementary information / income eligibility chart",
      "pre_freeze": true,
      "published": "2026-04-09",
      "quote": "The Department's guidelines for free meals and milk, and reduced price meals were obtained by multiplying the year 2026 Federal income poverty guidelines by 1.30 and 1.85, respectively, and by rounding the result upward to the next whole dollar.",
      "source": "USDA FNS, Child Nutrition Programs: Income Eligibility Guidelines (July 1, 2026 - June 30, 2027), Federal Register doc. 2026-06842",
      "url": "https://www.federalregister.gov/documents/full_text/xml/2026/04/09/2026-06842.xml"
    },
    {
      "pinpoint": "Income eligibility chart, 48 contiguous states, household size 3",
      "pre_freeze": true,
      "published": "2025-03-13",
      "quote": "Free Meals (130%): $34,645 ... Reduced Price Meals (185%): $49,303 (household of 3)",
      "source": "USDA FNS, Child Nutrition Programs: Income Eligibility Guidelines (July 1, 2025 - June 30, 2026), Federal Register doc. 2025-03821",
      "url": "https://www.federalregister.gov/documents/full_text/xml/2025/03/13/2025-03821.xml"
    },
    {
      "pinpoint": "48 contiguous states table, household of 3",
      "pre_freeze": true,
      "published": "2026-01-15",
      "quote": "3 ... $27,320",
      "source": "HHS, Annual Update of the HHS Poverty Guidelines (2026)",
      "url": "https://aspe.hhs.gov/topics/poverty-economic-mobility/poverty-guidelines"
    }
  ],
  "computation": "1) Household size for school meals is 3: the head, the spouse and the 6-year-old child. Countable gross income is $29,000 in wages plus $13,664 in Social Security, for $42,664.\n2) Federal NSLP income test: free meals are capped at 130% of the poverty guideline and reduced-price meals at 185%. The FNS guidelines are the poverty guideline times 1.30 or 1.85, rounded up. For SY2025-26 (2025 guideline), the household-of-3 limits are $34,645 (free) and $49,303 (reduced). For SY2026-27, the 2026 HHS guideline for 3 is $27,320, so the limits are $35,516 and $50,542. $42,664 is about 156% of the 2026 guideline. That is above the free limit and below the reduced-price limit, so on the federal income test alone the child falls in the reduced-price category.\n3) Federal categorical (direct-certification) route: none applies. No SNAP, TANF or FDPIR receipt is listed. SNAP works out to $0: monthly gross is about $3,555; after the $209 standard deduction and the 20% earned-income deduction, net income is about $2,863; 30% of that (about $859) exceeds the $785 maximum allotment for 3, and there is no rent. MFIP/TANF fails because the $11,300 in assets exceeds MFIP's $10,000 limit, and income is also high.\n4) Minnesota law decides the answer. Minn. Stat. \u00a7 124D.111, subd. 1c, requires every school in the National School Lunch Program to join the state free school meals program, or the federal Community Eligibility Provision (CEP) if it qualifies. Participating schools must \"provide to all students at no cost\" one breakfast and one lunch per school day. Under subd. 1d, the state pays the gap between the federal free rate and the federal reimbursement the school actually receives, so a child in the reduced-price or paid category still eats free. The 2025 version (amended 1Sp2025 c 10) keeps this. A 2025 bill (HF 2201) would have capped free lunch at 500% of the poverty line; I found no record that it passed. Even under that cap, this household at about 156% would still get free meals.\n5) The 6-year-old is school-age, so the household receives positive free school meal support in tax year 2026, in both SY2025-26 and SY2026-27. Result: 1.",
  "confidence": "high",
  "definition_reading": "I read the output as whether the household receives free (no-cost) school meals for its school-age child in Minnesota during 2026, counting the free tier and not reduced-price. Minn. Stat. \u00a7 124D.111, subd. 1c, requires NSLP schools to serve breakfast and lunch to all students at no cost. So the 6-year-old receives free meals and the output is 1, even though the federal income test alone (about 156% of the poverty line) would place the child in the reduced-price tier.",
  "independent_answer": 1,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine determined that this Minnesota household qualifies for free school meals through the state's universal free school meals program, resulting in an annual benefit value of $1,130.96. The household's school_meal_tier was set to FREE based on two qualifying pathways: first, the household's income of $42,664 represents 1.56 times the federal poverty guideline (school_meal_fpg_ratio), which exceeds the typical free meals threshold, but second and decisively, Minnesota has a universal free school meals program (state_has_universal_free_school_meals = True) that extends eligibility beyond income-based criteria. The benefit amount was calculated by multiplying the school_meal_daily_subsidy of $7.15 by the school_meal_paid_daily_subsidy of $0.87 and the number of school days, applied only to the one child in the household who is enrolled in K-12 school (is_in_k12_school shows True for one entity). This yields the total annual free school meals benefit of $1,130.96 for the household.
----- END ENGINE DERIVATION -----