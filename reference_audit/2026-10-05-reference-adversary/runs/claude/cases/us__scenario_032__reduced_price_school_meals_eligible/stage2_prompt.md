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
OUTPUT: reduced_price_school_meals_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only reduced_price_school_meals_eligible):
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

ENGINE REFERENCE VALUE: 0 (not eligible)
MODELS: 45 gave a usable answer; 20 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 1, given by 25 models (3 of them among the benchmark's top-ranked models)
- claude-fable-5.1: answered 1
  explanation: Income 42,664 is between 130% and 185% FPL for 3 (~49,302) with a school-age child, so reduced-price meal support is positive; yes. value = 1
- claude-haiku-4.5: answered 1
  explanation: The household has gross income of $42,664 (head's wages of $29,000 plus Social Security dependent benefits of $13,664). With a household size of 4 (head, spouse, and 2 children), the household's income-to-poverty ratio is well below the reduced-price meals eligibility threshold of 185% of federal poverty level. For 2026, the federal poverty guideline for a family of 4 is approximately $27,750, and 185% of that is approximately $51,337. Since the household's income of $42,664 is below this threshold, the household qualifies for reduced-price school meal support. value = 1
- claude-opus-4.7: answered 1
  explanation: Household income: $29,000 wages + $13,664 SS = $42,664. For a family of 3 in 2026, reduced-price meal threshold is ~185% FPL (~$48,000), so household qualifies for reduced-price... but free meal threshold is 130% FPL (~$33,700), and $42,664 exceeds this, so they fall in reduced-price range. However, with SS benefits counted, income $42,664 for family of 3 is below 185% FPL (~$49,000 for 2026), so reduced-price eligible. Wait - actually $42,664 is above 130% FPL ($33,700) and below 185% FPL, qualifying for reduced-price meals. value = 1
- claude-opus-4.8: answered 1
  explanation: School meal eligibility is based on income relative to federal poverty guidelines. Household has 3 people. Countable income includes wages $29,000 plus Social Security dependent benefits $13,664 = $42,664. Reduced-price meals require income between 130% and 185% of poverty. For a 3-person household, 185% of poverty (~$48,000) exceeds $42,664 while 130% (~$33,800) is below it, so income falls in the reduced-price band. The 6-year-old child qualifies for reduced-price school meals. value = 1
- claude-opus-5: answered 1
  explanation: Household income at roughly 170% FPL is between 130% and 185% FPL, so the school-age child qualifies for reduced-price meals. value = 1
- claude-opus-5.5: answered 1
  explanation: Income at about 160% of the poverty line is between 130% and 185%, so eligible for reduced-price meals. value = 1
- claude-sonnet-4.6: answered 1
  explanation: Reduced-price school meals (as opposed to free meals) are available to households with income between 130% and 185% of the federal poverty level (FPL). The household's gross income includes wages of $29,000 plus Social Security dependent benefits of $13,664, totaling $42,664. For a household of 3 (head, spouse, child), the 2026 FPL is approximately $24,860. 185% of FPL ≈ $46,000, and 130% of FPL ≈ $32,318. The household income of $42,664 falls between 130% and 185% of FPL, which would normally indicate reduced-price eligibility. However, the spouse is 18 years old and the child is 6. The National School Lunch Program reduced-price benefit applies to school-age children. Child 1 (age 6) is school-age. PolicyEngine's reduced-price school meals calculation uses the SPM unit income. With total income of $42,664 and an SPM unit energy subsidy of $50, the countable income is around $42,664. At 185% FPL for a family of 3 (~$46,000), the household is under the 185% threshold, placing it in reduced-price territory (above 130% FPL ~$32,318). This would suggest reduced-price eligibility. However, PolicyEngine also considers whether the benefit is positive after accounting for free meal eligibility thresholds. Since income exceeds 130% FPL, the household does not qualify for free meals but could qualify for reduced-price meals. PolicyEngine should return a positive reduced-price school meal benefit for Child 1. But reviewing more carefully: the household income of $42,664 vs 185% FPL for 3 persons (~$46,000 in 2026) is below 185%, so reduced-price eligibility applies. Yet PolicyEngine may classify this differently based on exact FPL figures and program rules. Given income of $42,664 is between 130% and 185% FPL for a 3-person household, Child 1 (age 6) should be eligible for reduced-price meals, yielding a positive annual benefit. However, upon careful reconsideration, the 2026 FPL for 3 persons is approximately $25,820 (2024 base ~$24,860 with inflation adjustments). 185% of $ [... 238 more characters cut]
- claude-sonnet-5.5: answered 1
  explanation: Countable income of about 42,700 is above 130% but below 185% of the FPL for 3 (about 49,300). Eligible for reduced-price meals. value = 1
- deepseek-v4-flash-0731: answered 1
  explanation: Household income (~157% FPL) is above 130% but at or below 185% FPL, so the child is eligible for reduced-price school meals. value = 1
- deepseek-v4-pro: answered 1
  explanation: Income $42,664 < 185% FPL $50,272; eligible for reduced-price meals. value = 1
- deepseek-v4.1-flash: answered 1
  explanation: Household income $42,664 is below 185% FPL for 3 (~$50,875) and above 130% FPL. Eligible. value = 1
- gemini-3.8-flash: answered 1
  explanation: Household income of $42,664 is between 130% and 185% of the federal poverty line for a household of 3, qualifying Child 1 for reduced-price school meals, value = 1
- glm-5.2: answered 1
  explanation: Total household income is $42,664. This is below 185% of the 2026 federal poverty guideline for a household of 3 but above 130%, so the household is eligible for reduced-price school meals. value = 1
- glm-5.3: answered 1
  explanation: Household income of $42,664 is about 153% of the federal poverty guideline, which is within the 130-185% band for reduced-price school meals, so the household qualifies for reduced-price meal support. value = 1
- gpt-5.5: answered 1
  explanation: The household has a school-age child and annual countable income of $42,664 is below the federal reduced-price meal limit for a 3-person household while above the free-meal limit, so reduced-price school meals are eligible; value = 1
- gpt-5.6-luna: answered 1
  explanation: Household income is below the federal reduced-price school-meal threshold for three people, so positive reduced-price support is returned; value = 1
- gpt-5.6-terra: answered 1
  explanation: Reported household income is within the modeled reduced-price school-meal income range for a three-person household; value = 1
- gpt-6-luna: answered 1
  explanation: Estimated household income is within the reduced-price meal range for a three-person household; reduced-price meal support is expected. value = 1
- grok-4.5: answered 1
  explanation: Household money income of 42664 is approximately 156 percent of the projected 2026 FPL for three, below the 185 percent reduced-price limit, so the household is eligible for reduced-price school meals. value = 1
- grok-4.6: answered 1
  explanation: Household MAGI of about 156 percent of FPL lies between 130 and 185 percent of FPL, so PolicyEngine returns positive reduced-price school meal support for the school-age child. value = 1
- grok-4.7: answered 1
  explanation: Gross income of $42,664 is above 130% FPL and below 185% FPL for a household of three, and Child 1 is school age. PolicyEngine therefore returns positive reduced-price school meal support, so the household is eligible for reduced-price school meals. value = 1
- grok-build-0.1: answered 1
  explanation: Household gross income of $42,664 is approximately 156.7% of the 2026 FPL for a 3-person household (~$27,207), below the 185% FPL threshold for reduced-price school meals. value = 1
- inkling: answered 1
  explanation: Household income (~$42,664) falls between 130% and 185% FPL ($33,566 to $47,767) for 3 people, making them eligible for reduced-price school meals. value = 1
- kimi-k3: answered 1
  explanation: Household income is about 156% of poverty, between the 130% free-meal and 185% reduced-price-meal limits, and Child 1 is school age, so the household is eligible. value = 1
- ox-alpha: answered 1
  explanation: Household income of $42,664 (~160% of the 3-person poverty line) is at or below the 185% cutoff for reduced-price meals for the school-age child. value = 1

STAGE 1 RESULT (frozen; sha256 760f7b7ee1f6af0ed1c513ac3213767f324ac9d50b102ae6f8452d3a75fe2b2f):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "A second reasonable reading treats the output as the federal NSLP/SBP income tier, which matches the variable name 'reduced_price_school_meals_eligible'. Under that reading the answer is 1: income of $42,664 is between 130% ($35,516) and 185% ($50,542) of the 2026 FPG for 3, and Minnesota schools still collect applications and claim this child as reduced-price for federal reimbursement. The 25 consensus models used this reading and ignored Minnesota's universal free meals. Whether a PolicyEngine-specific model of Minnesota's universal free meals is what drives the engine's 0 cannot be checked from the law. Separately, if the child were treated as not attending school (no attendance input was listed), the answer would be 0 under either reading.",
  "citations": [
    {
      "pinpoint": "Subd. 1c(b), (d)(2)",
      "pre_freeze": true,
      "published": "2025",
      "quote": "provide to all students at no cost up to two federally reimbursable meals per school day, with a maximum of one free breakfast and one free lunch.",
      "source": "Minnesota Statutes 2025, section 124D.111 (School meals policy; Free school meals program)",
      "url": "https://www.revisor.mn.gov/statutes/cite/124D.111"
    },
    {
      "pinpoint": "Subd. 1d (Free school meals program aid amount)",
      "pre_freeze": true,
      "published": "2025",
      "quote": "The state aid equals the difference between the applicable federal reimbursement rate at that school site for a free meal, as determined annually by the United States Department of Agriculture, and the actual federal reimbursement received by the participating school for the breakfast or lunch served to the student.",
      "source": "Minnesota Statutes 2025, section 124D.111",
      "url": "https://www.revisor.mn.gov/statutes/cite/124D.111"
    },
    {
      "pinpoint": "Definitions of 'Free meal' and 'Reduced price meal'",
      "pre_freeze": true,
      "published": "current regulation (long-standing)",
      "quote": "Free meal means a meal for which neither the child nor any member of his family pays or is required to work in the school or in the school's food service.",
      "source": "7 CFR 245.2 (Determining Eligibility for Free and Reduced Price Meals and Free Milk in Schools \u2014 Definitions)",
      "url": "https://www.law.cornell.edu/cfr/text/7/245.2"
    },
    {
      "pinpoint": "Guidelines paragraph and income definition; effective July 1, 2026\u2013June 30, 2027",
      "pre_freeze": true,
      "published": "2026-04-09",
      "quote": "The Department's guidelines for free meals and milk, and reduced price meals were obtained by multiplying the year 2026 Federal income poverty guidelines by 1.30 and 1.85, respectively, and by rounding the result upward to the next whole dollar.",
      "source": "USDA FNS, Child Nutrition Programs: Income Eligibility Guidelines, Federal Register Doc. 2026-06842 (91 FR 17932)",
      "url": "https://www.federalregister.gov/documents/full_text/text/2026/04/09/2026-06842.txt"
    },
    {
      "pinpoint": "Definition of income, item (4)",
      "pre_freeze": true,
      "published": "2026-04-09",
      "quote": "\"Income,\" as used here, means income before any deductions such as income taxes, Social Security taxes, or insurance premiums ... (4) Social Security",
      "source": "USDA FNS, Child Nutrition Programs: Income Eligibility Guidelines, Federal Register Doc. 2026-06842",
      "url": "https://www.federalregister.gov/documents/full_text/text/2026/04/09/2026-06842.txt"
    },
    {
      "pinpoint": "48 contiguous states table, household size 3 ($27,320)",
      "pre_freeze": true,
      "published": "2026-01-15",
      "quote": "For families/households with more than 8 persons, add $5,680 for each additional person.",
      "source": "HHS ASPE, 2026 Poverty Guidelines",
      "url": "https://aspe.hhs.gov/topics/poverty-economic-mobility/poverty-guidelines"
    },
    {
      "pinpoint": "Income guidelines and application paragraphs",
      "pre_freeze": false,
      "published": "2026-08-17",
      "quote": "schools must still collect Applications for Educational Benefits to determine eligibility categories and receive the correct federal and state reimbursements.",
      "source": "Minnesota Department of Education, 'USDA Announces New Income Guidelines for Free and Reduced-Price Benefits Eligibility' (GovDelivery bulletin)",
      "url": "https://content.govdelivery.com/accounts/MNMDE/bulletins/42447e2"
    }
  ],
  "computation": "1) Household size is 3: the head, the 18-year-old spouse and the 6-year-old child. Income for school meals is gross cash income before deductions and expressly includes \"Social Security\" (FR notice 2026-06842). Income = $29,000 wages + $13,664 Social Security dependent benefits = $42,664, or about $3,555 a month. The $50 energy subsidy is LIHEAP-type aid and is not counted; counting it would give $42,714 and change nothing.\n2) The 2026 HHS poverty guideline for 3 in the 48 states is $27,320 (ASPE, Jan 15, 2026). Under the 2026-27 IEGs (\u00d71.30 and \u00d71.85, rounded up), the free limit is $35,516 and the reduced-price limit is $50,542. The household is at about 156% of FPG. The 2025-26 IEGs, which cover Jan\u2013Jun 2026, are based on the $26,650 guideline and give $34,645 and $49,303, so the result is the same band. Monthly, MDE's limits for a household of 3 work out to about $2,960 (free) and $4,212 (reduced-price), and $3,555 falls between them.\n3) No categorical route to free meals: SNAP comes to $0. Under Minnesota's broad-based categorical eligibility the household passes the 165% FPG gross test, but net income is about $3,555 \u2212 $483 earned-income deduction \u2212 $209 standard deduction \u2248 $2,863 with no excess shelter cost. 30% of that is about $859, which is more than the $785 maximum allotment for 3, and the minimum benefit applies only to households of 1\u20132. There is no TANF/MFIP either. So under federal NSLP/SBP rules the child is certified in the REDUCED-PRICE tier, which is what the consensus applied.\n4) Minnesota law is the deciding step. Minn. Stat. 124D.111 subd. 1c makes every NSLP school join the state free school meals program and \"provide to all students at no cost\" one breakfast and one lunch a day. Subd. 1d has the state pay the gap between the federal free rate and the federal reimbursement actually received, so for a reduced-price-certified child the state covers the reduced-price copay. Under 7 CFR 245.2, a meal \"for which neither the child nor any member of his family pays\" is a free meal. The program was in force for SY 2025-26 and 2026-27 (2025 Minnesota Statutes; MDE 2026 bulletins).\nSo the meal support this household actually receives in 2026 is free meals, with the reduced-price tier existing only as a federal reimbursement category. The definition says \"free meals do not count as 1\", so reduced-price support = 0.",
  "confidence": "medium",
  "definition_reading": "I read 'positive annual reduced-price school meal support for the household (free meals do not count as 1)' as the meal benefit the household actually receives. The 6-year-old is presumed to attend a Minnesota public school that participates in NSLP. Federally the household's income (~156% FPG) puts the child in the reduced-price tier. But Minn. Stat. 124D.111 requires every participating school to serve all students breakfast and lunch at no cost, with the state paying the reduced-price copay. Those meals are 'free meals' under 7 CFR 245.2, so the household's support is free meals and reduced-price support is 0.",
  "independent_answer": 0,
  "law_supports": "both_readings"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine determined that this Minnesota household is not eligible for reduced-price school meals (reduced_price_school_meals_eligible = 0.0) because the household qualifies for the superior free meals tier instead. With a household income of approximately $42,664, the family's income-to-poverty ratio (school_meal_fpg_ratio) is 1.56, placing them above the reduced-price income threshold but within Minnesota's universal free school meals program. Since the state provides universal free meals to all students regardless of income, the household receives the school_meal_tier classification of FREE, which supersedes reduced-price eligibility. Consequently, the household receives a net school meal subsidy of $1,130.96 annually through the free meals program rather than the reduced-price option.
----- END ENGINE DERIVATION -----