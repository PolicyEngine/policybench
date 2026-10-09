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
STATE: NC
OUTPUT: child3_medicaid_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether Child 3 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only child3_medicaid_eligible):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: NC
- tax year: 2026

Head:
- age: 48
- employer sponsored insurance premiums: $21,208
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $1,020
- other health insurance premiums: $1,020
- other medical expenses: $400
- over-the-counter health expenses: $100

Spouse:
- age: 45
- gross wages and salaries: $85,209
- bank account assets: $1,330
- fsla overtime premium: $7,746
- has employer-sponsored insurance
- hourly wage: $33
- usual weekly hours worked: 50
- other medical expenses: $200
- over-the-counter health expenses: $350
- roth 401k contributions desired: $490
- roth ira contributions desired: $201
- stock assets: $84,353
- traditional 401k contributions desired: $2,778
- traditional ira contributions desired: $130

Child 1:
- age: 11
- has employer-sponsored insurance
- other medical expenses: $250
- over-the-counter health expenses: $250

Child 2:
- age: 11
- has employer-sponsored insurance
- other medical expenses: $250
- over-the-counter health expenses: $250

Child 3:
- age: 9
- has employer-sponsored insurance
- other medical expenses: $250
- over-the-counter health expenses: $250

Tax unit:
- first home mortgage balance: $108,000

Household inputs:
- auto loan balance: $17,529
- auto loan interest: $378
- household vehicles value: $10,230

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
- child3_wic_eligible: whether Child 3 is eligible for WIC (1 if yes, 0 if no)
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_medicaid_eligible: whether Spouse is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_medicaid_eligible: whether Child 1 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_medicaid_eligible: whether Child 2 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child3_medicaid_eligible: whether Child 3 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_chip_eligible: whether Spouse is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_chip_eligible: whether Child 1 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_chip_eligible: whether Child 2 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child3_chip_eligible: whether Child 3 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- spouse_medicare_eligible: whether Spouse is eligible for Medicare (1 if yes, 0 if no)
- child1_medicare_eligible: whether Child 1 is eligible for Medicare (1 if yes, 0 if no)
- child2_medicare_eligible: whether Child 2 is eligible for Medicare (1 if yes, 0 if no)
- child3_medicare_eligible: whether Child 3 is eligible for Medicare (1 if yes, 0 if no)
- free_school_meals_eligible: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)
- reduced_price_school_meals_eligible: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)
- child1_head_start_eligible: whether Child 1 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child2_head_start_eligible: whether Child 2 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child3_head_start_eligible: whether Child 3 is eligible for Head Start for preschool-age children, not Early Head Start (1 if yes, 0 if no)
- child1_early_head_start_eligible: whether Child 1 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)
- child2_early_head_start_eligible: whether Child 2 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)
- child3_early_head_start_eligible: whether Child 3 is eligible for Early Head Start as a child under this benchmark output (1 if yes, 0 if no)

Use the `submit_outputs` function exactly once. Return an `outputs` object with every requested quantity keyed by variable name. Each requested key must map to an object with a numeric `value` and a non-empty, specific, concise `explanation`. Each explanation must support the numeric value submitted for the same variable in `outputs`. If an explanation mentions a final amount, that amount must match the corresponding `outputs` value. Do not write that you will use one value while submitting a different value. Do not include scratch work, abandoned calculations, or corrections. End each explanation with `value = X`, where X exactly matches the numeric `value` field. For 1/0 eligibility outputs, submit 1 only when the explanation says eligible or yes, and submit 0 only when it says not eligible or no. Use the exact variable names as keys inside `outputs`. Include every requested key exactly once in `outputs`, even if the value is 0. Put only numeric values in `value`, with no dollar signs, commas, or explanatory text. Do not rely on plain text for the final answers. If an answer is a currency amount, give the annual amount. If an answer is a rate, give a decimal (e.g. 0.25 for 25%).
----- END HOUSEHOLD PROMPT -----

ENGINE REFERENCE VALUE: 1 (eligible)
MODELS: 45 gave a usable answer; 1 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 44 models (5 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: NC Medicaid for children ages 6-18 uses an income limit of about 138% FPL (with MAGI 5% disregard) on Medicaid; income above that up to ~211% FPL falls to CHIP, not Medicaid. Household MAGI is roughly $85,209 wages minus $2,908 pre-tax retirement contributions ≈ $82,301 for a family of 5, which is about 197% of the 2025 FPL ($37,650 for 5), well above the ~138% FPL Medicaid threshold for a 9-year-old. Child 3 is therefore not eligible for Medicaid (would instead be CHIP-eligible). value = 0
- claude-fable-5.1: answered 0
  explanation: Income ~213% FPL exceeds NC Medicaid child (age 6-18) limit of 133% FPL; not eligible. value = 0
- claude-haiku-4.5: answered 0
  explanation: Child 3 is age 9 and lives in North Carolina. Under NC Medicaid rules for 2026, the income limit for a child in a family of 5 (head, spouse, and three children) is 207% of the federal poverty level, which is approximately $56,232 annual income. The household's modified adjusted gross income is approximately $82,431 (spouse's wages of $85,209 minus above-the-line deductions including traditional 401k contributions of $2,778 and traditional IRA contributions of $130). This exceeds the Medicaid income limit, making Child 3 ineligible for Medicaid. Additionally, Child 3 already has employer-sponsored insurance coverage, which is the reason for lack of enrollment rather than eligibility, but eligibility is still determined by the income threshold. The household income exceeds the limit for Medicaid eligibility for children in NC. value = 0
- claude-opus-4.7: answered 0
  explanation: NC Medicaid for a child age 9 in a household of 5 uses an income limit around 211% FPL. Spouse's wages of $85,209 far exceed this threshold (~$66,000 for a family of 5), so Child 3 is not income-eligible. value = 0
- claude-opus-4.8: answered 0
  explanation: Child 3 is age 9. North Carolina Medicaid income limit for children ages 6-18 is 133% of the federal poverty line (plus a 5% disregard). Household of 5 with single earner income of ~$85,209 gross wages. The 2026 FPL for a household of 5 is roughly $39,440; 133% is about $52,455. The household income of ~$85,000 far exceeds this threshold for the child Medicaid category. However, children may still qualify for CHIP (NC Health Choice) up to 211% FPL (~$83,200), and $85,209 slightly exceeds that. Given PolicyEngine treats Medicaid eligibility for children using income tests, this child's family income exceeds the children's Medicaid/CHIP thresholds. value = 0
- claude-opus-5: answered 0
  explanation: Income ~260% FPL exceeds NC children's Medicaid limit for age 9. value = 0
- claude-opus-5.5: answered 0
  explanation: Income is about 219% of FPL, above the child Medicaid limit, so not eligible. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Child 3 is age 9 and has employer-sponsored insurance (ESI). Under PolicyEngine's Medicaid eligibility rules, a child who is covered by employer-sponsored insurance is treated as having access to qualifying coverage and is therefore not eligible for Medicaid. Additionally, the household income (spouse gross wages of $85,209) must be evaluated against NC Medicaid income limits for children. NC Medicaid covers children up to age 19 at 210% FPL (Medicaid) or up to 211–300% FPL under NC Health Choice (CHIP). For a household of 5 in 2026, the federal poverty level is approximately $36,580, so 210% FPL ≈ $76,818. The household's gross wages of $85,209 exceed this threshold. While CHIP extends coverage up to ~300% FPL (~$109,740), PolicyEngine's Medicaid-specific eligibility (not CHIP) would find the child ineligible based on income exceeding the Medicaid threshold and the presence of ESI. Under PolicyEngine's strict Medicaid rules, Child 3 is not eligible. value = 0
- claude-sonnet-5: answered 0
  explanation: Household income is spouse's wages $85,209 plus overtime, for a family of 5 in NC. NC Medicaid for children ages 6-18 is limited to about 138% FPL, and children under 6 up to 210% FPL; for a family of 5, 138% FPL (2026) is roughly $50,000-$52,000, well below the household's gross income of over $92,000. This far exceeds NC Medicaid/CHIP income thresholds for a 9-year-old child, so Child 3 is not Medicaid eligible. value = 0
- claude-sonnet-5.5: answered 0
  explanation: Not eligible: income of about 82k exceeds the child Medicaid limit of 133% FPL. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Children's income limit (210% FPL) is below household income. value = 0
- deepseek-v4-pro: answered 0
  explanation: Family MAGI of $82,301 exceeds 133% FPL ($51,205), above the Medicaid eligibility threshold for children in North Carolina. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Household MAGI of 82,301 exceeds NC Medicaid child income limits for the household size of 5. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: Income $85,209 exceeds NC Medicaid child limit of 210% FPL. value = 0
- gemini-3-flash-preview: answered 0
  explanation: Child 3's household MAGI of $61,093 exceeds the 133% Federal Poverty Level threshold ($46,736) for child Medicaid for those aged 6-18 in North Carolina. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: Household income is above the threshold for Medicaid eligibility for this child. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: The household MAGI of $82,301 exceeds the 133% FPL Medicaid limit for older children; they instead qualify for CHIP. value = 0
- gemini-3.5-flash: answered 0
  explanation: Child 3 is not eligible for Medicaid because the household's income of $61,093 exceeds the 133% FPL threshold for children. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Child 3 is not eligible for Medicaid under PolicyEngine rules for NC in 2026. value = 0
- gemini-3.6-flash: answered 0
  explanation: Child 3's household income exceeds the income limit for Medicaid in North Carolina. value = 0
- gemini-3.7-flash: answered 0
  explanation: Child 3 is not eligible for Medicaid as household income exceeds eligibility limits; value = 0
- gemini-3.8-flash: answered 0
  explanation: Child 3 is not eligible for Medicaid because household income exceeds North Carolina Medicaid limits for children. value = 0
- glm-5.2: answered 0
  explanation: Child 3 is age 9 in a 5-person household with total gross wages of $85,209. The 2026 FPL for a 5-person household is approximately $40,000, placing household income at roughly 213% FPL. NC Medicaid for children 6-18 covers up to 133% FPL, and NC CHIP covers up to 210% FPL. Household income exceeds 210% FPL, and the child has employer-sponsored insurance. Child 3 is not eligible for Medicaid. value = 0
- glm-5.3: answered 0
  explanation: Household income of $85,209 exceeds the NC children's Medicaid income limit (about 211% of poverty) for a family of 5, so Child 3 is not eligible. value = 0
- gpt-5.4-mini: answered 0
  explanation: Child 3 is a school-age child in a household with earnings above the benchmark Medicaid threshold, so not eligible. value = 0
- gpt-5.4-nano: answered 0
  explanation: Child Medicaid eligibility not indicated given household income level implied by wages and no special-status facts; therefore not eligible. Child 3 Medicaid eligibility value = 0.
- gpt-5.5: answered 0
  explanation: Child 3 is age 9 in NC, but the household's annual earnings of about $85,209 before limited pretax deductions are well above the NC child Medicaid income limit for a 5-person household, so Child 3 is not eligible; employer coverage does not change this income result. value = 0
- gpt-5.6-luna: answered 0
  explanation: Child 3 is not Medicaid eligible because household income exceeds the estimated North Carolina child Medicaid threshold; value = 0
- gpt-5.6-sol: answered 0
  explanation: Child 3 is not eligible because household MAGI exceeds North Carolina's Medicaid income limit for a 9-year-old; value = 0
- gpt-5.6-terra: answered 0
  explanation: Household income is above the North Carolina child Medicaid limit for Child 3; value = 0
- gpt-6-luna: answered 0
  explanation: Child 3 is age 9 and household income exceeds the applicable North Carolina Medicaid income limit for this age; not eligible; value = 0
- gpt-6-sol: answered 0
  explanation: Child 3 is not eligible for Medicaid because household income exceeds the child Medicaid limit; value = 0
- gpt-6.1-sol: answered 0
  explanation: Child 3 is not eligible because household MAGI of $82,301 exceeds the applicable North Carolina child income limit for five people. value = 0
- grok-4.3: answered 0
  explanation: Income above NC Medicaid threshold for family of 5 and ESI present, so not eligible. value = 0
- grok-4.5: answered 0
  explanation: Child 3 age 9 MAGI exceeds NC Medicaid limit of 133% FPL for children 6-18. value = 0
- grok-4.6: answered 0
  explanation: Child 3 is age 9; MAGI $74,555 exceeds NC Medicaid’s 133% FPL limit for children 6–18, so Child 3 is not eligible for Medicaid. value = 0
- grok-4.7: answered 0
  explanation: Child 3 is age 9 and household MAGI is above North Carolina's Medicaid limit for children ages 6-18, so Child 3 is not eligible for Medicaid. value = 0
- grok-build-0.1: answered 0
  explanation: Household income ~240% FPL exceeds NC Medicaid limit for children (~133% FPL base). value = 0
- inkling: answered 0
  explanation: Child 3 (age 9) exceeds the 133% FPL Medicaid income limit for ages 6–18 and is insured through employer-sponsored coverage. value = 0
- kimi-k3: answered 0
  explanation: NC child (6-18) Medicaid MAGI limit ~133% FPL (138% with disregard); household MAGI ~226% FPL for 5 exceeds it. value = 0
- minimax-m3: answered 0
  explanation: Child 3 is age 9 with household income well above NC Medicaid for Children limits, so not eligible. value = 0
- ox-alpha: answered 0
  explanation: At age 9, Child 3 falls in NC's 6-18 Medicaid group limited to about 133% FPL; household income (~198% FPL) exceeds it. value = 0
- qwen-3.7-max: answered 0
  explanation: Child 3 is age 9 in NC in 2026. NC Medicaid eligibility for children ages 6-18 is up to 133% of FPL. The household has 5 members; 2026 FPL for a 5-person household is approximately $33,700 (133% ≈ $44,821). The spouse earns $85,209 in gross wages, which far exceeds the 133% FPL threshold. The children have employer-sponsored insurance. Income is well above the Medicaid limit, so Child 3 is not eligible. value = 0
- qwen3.8-max: answered 0
  explanation: Household income is too high for child Medicaid eligibility. value = 0

STAGE 1 RESULT (frozen; sha256 5dd081c65e11cdd3c59daf956d55c16deb1ab0a2392c342e2346f9a48b2f883e):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "The definition says \"under PolicyEngine rules.\" If that is read as income limits only, ignoring the child's employer coverage, the answer could change: MAGI of $82,301 against the 2026 poverty line ($38,680) is 212.8% FPL, or 207.8% after the 5% disregard. That is within 211%, giving 1, the reference value. Even on that reading, NC moves to the new poverty line only on April 1 (G.S. 108A-54.3A(b)). Using the 2025 line ($37,650) for January\u2013March gives 213.6% after the disregard, which fails, so an income-only reading gives 1 for April\u2013December and 0 for January\u2013March. I also could not read NC SPA NC-23-0009 directly to confirm that the 133\u2013211% band for ages 6\u201318 uses the optional targeted low-income children group (435.229). I inferred it from the federal caps in 435.118 and 435.222 and from CMS's \"new Medicaid eligibility group for certain children\" summary.",
  "citations": [
    {
      "pinpoint": "(a)(3); (b)",
      "pre_freeze": true,
      "published": "version effective until 2026-10-01, as amended through S.L. 2026-1",
      "quote": "Children through the age of 18 with family incomes equal to or less than two hundred eleven percent (211%) of the federal poverty guidelines.",
      "source": "N.C. Gen. Stat. \u00a7 108A-54.3A (Eligibility categories and income thresholds)",
      "url": "https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/BySection/Chapter_108A/GS_108A-54.3A.html"
    },
    {
      "pinpoint": "(b) and introductory clause of (a)",
      "pre_freeze": true,
      "published": "version effective until 2026-10-01",
      "quote": "The applicable federal poverty guidelines for the eligibility categories in subsection (a) of this section shall be updated annually on April 1 immediately following publication of the federal poverty guidelines.",
      "source": "N.C. Gen. Stat. \u00a7 108A-54.3A",
      "url": "https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/BySection/Chapter_108A/GS_108A-54.3A.html"
    },
    {
      "pinpoint": "Table, household of 5",
      "pre_freeze": true,
      "published": "2026-01-15",
      "quote": "5 | $38,680",
      "source": "HHS ASPE, 2026 Poverty Guidelines (48 contiguous states)",
      "url": "https://aspe.hhs.gov/topics/poverty-economic-mobility/poverty-guidelines"
    },
    {
      "pinpoint": "(d)(4)",
      "pre_freeze": true,
      "published": "current CFR",
      "quote": "a state must subtract an amount equivalent to 5 percentage points of the Federal poverty level for the applicable family size only to determine the eligibility of an individual for medical assistance under the eligibility group with the highest income standard",
      "source": "42 CFR 435.603 (MAGI-based methodologies)",
      "url": "https://www.law.cornell.edu/cfr/text/42/435.603"
    },
    {
      "pinpoint": "(c)(2)",
      "pre_freeze": true,
      "published": "current CFR",
      "quote": "The maximum income standard for each age group is the higher of ... 133 percent FPL ... [or] the highest effective income level ... under the Medicaid State plan ... as of March 23, 2010 or December 31, 2013",
      "source": "42 CFR 435.118 (Infants and children under age 19)",
      "url": "https://www.law.cornell.edu/cfr/text/42/435.118"
    },
    {
      "pinpoint": "(b), (c)(3)",
      "pre_freeze": true,
      "published": "current CFR",
      "quote": "The agency may provide Medicaid to individuals under age 19 ... who meet the definition of an optional targeted low-income child in \u00a7 435.4",
      "source": "42 CFR 435.229 (Optional targeted low-income children)",
      "url": "https://www.law.cornell.edu/cfr/text/42/435.229"
    },
    {
      "pinpoint": "(c)",
      "pre_freeze": true,
      "published": "current CFR",
      "quote": "The income standard established under this section may not exceed the higher of the State's AFDC payment standard in effect as of July 16, 1996, or the State's highest effective income level",
      "source": "42 CFR 435.222 (Reasonable classifications of individuals under 21)",
      "url": "https://www.law.cornell.edu/cfr/text/42/435.222"
    },
    {
      "pinpoint": "(b)(1)(C)",
      "pre_freeze": true,
      "published": "current U.S. Code",
      "quote": "who is not found to be eligible for medical assistance under subchapter XIX or, subject to paragraph (5), covered under a group health plan or under health insurance coverage",
      "source": "42 U.S.C. 1397jj (SSA \u00a7 2110)",
      "url": "https://www.law.cornell.edu/uscode/text/42/1397jj"
    },
    {
      "pinpoint": "(u)(2)(B)",
      "pre_freeze": true,
      "published": "current U.S. Code",
      "quote": "a targeted low-income child as defined in section 1397jj(b)(1) of this title (determined without regard to that portion of subparagraph (C) of such section concerning eligibility for medical assistance under this subchapter)",
      "source": "42 U.S.C. 1396d (SSA \u00a7 1905)",
      "url": "https://www.law.cornell.edu/uscode/text/42/1396d"
    },
    {
      "pinpoint": "Summary",
      "pre_freeze": true,
      "published": "2023-07-31",
      "quote": "adopt a new Medicaid eligibility group for certain children under age 19; and align the income standard for all children under age 19 at 211 percent of the federal poverty level",
      "source": "CMS, Medicaid SPA NC-23-0009 summary",
      "url": "https://www.medicaid.gov/medicaid-spa/2023-07-31/151086"
    },
    {
      "pinpoint": "North Carolina row",
      "pre_freeze": true,
      "published": "2023-12-01",
      "quote": "North Carolina | 211% | 211% | 211% | N/A",
      "source": "CMS, Medicaid, CHIP & BHP Eligibility Levels",
      "url": "https://www.medicaid.gov/medicaid/national-medicaid-chip-program-information/medicaid-childrens-health-insurance-program-basic-health-program-eligibility-levels"
    }
  ],
  "computation": "1) Household MAGI (42 CFR 435.603(e), via IRC 36B(d)(2)(B)): the spouse's wages are $85,209 (overtime included). Traditional 401(k) deferrals of $2,778 are left out of gross income. The traditional IRA deduction of $130 is above the line; at about $82k joint MAGI it falls below the 2026 phase-out for an active participant. Roth contributions do not reduce income. The OBBBA qualified-overtime deduction (IRC 225) is taken below the line, so it does not change AGI or MAGI. The head has no earnings, and nothing says the head's employer-insurance premiums are taken pre-tax from the spouse's wages, so I do not infer that. MAGI = 85,209 - 2,778 - 130 = $82,301. Household size is 5.\n\n2) Poverty line: the HHS 2026 guideline for 5 people is $38,680 (published 2026-01-15, before the freeze). Under G.S. 108A-54.3A(b), NC adopts the new guidelines on April 1. So January\u2013March 2026 uses the 2025 figure of $37,650, and April\u2013December uses $38,680. 82,301 / 38,680 = 212.8% FPL; 82,301 / 37,650 = 218.6% FPL.\n\n3) Income standard: G.S. 108A-54.3A(a)(3) covers children through age 18 up to 211% FPL. CMS lists NC children ages 6\u201318 at 211%. The 5% disregard (42 CFR 435.603(d)(4)) applies to the group with the highest standard, so the effective cutoff is 216%. On income alone the child qualifies from April to December (212.8 - 5 = 207.8% \u2264 211%) but not from January to March (218.6 - 5 = 213.6% > 211%).\n\n4) Eligibility group: the regular children's group (42 CFR 435.118(c)(2)) is capped at the higher of 133% FPL or the state's Medicaid level as of 2010/2013. NC's level for ages 6\u201318 was 133%. The reasonable-classification group (435.222(c)) has a similar cap. The only Medicaid group that can reach 211% for ages 6\u201318 is the optional targeted low-income children group (435.229(c)(3)). Its cap counts the CHIP-plan level, which was NC Health Choice at 200%, or 211% after MAGI conversion. CMS describes SPA NC-23-0009 as adopting \"a new Medicaid eligibility group for certain children under age 19,\" which fits this group. I could not read the SPA itself, so this step is an inference.\n\n5) Insurance condition: an optional targeted low-income child must be a targeted low-income child under 42 U.S.C. 1397jj(b)(1). Part (C) of that definition requires that the child not be \"covered under a group health plan or under health insurance coverage\" (42 U.S.C. 1396d(u)(2)(B); 42 CFR 435.4). Child 3 \"has employer-sponsored insurance\" all year, so Child 3 is not an optional targeted low-income child. The state-employee exception in 1397jj(b)(5) doesn't apply because it isn't listed, so it counts as false.\n\n6) The 133% group then decides the case: 212.8% FPL is far above 133% (138% with the disregard). Child 3 is not Medicaid-eligible, and NC has no separate CHIP. Result = 0.",
  "confidence": "medium",
  "definition_reading": "This is a person-level flag for Child 3, a 9-year-old in a 5-person tax unit in NC in 2026. The question is whether the child meets the rules for any NC Medicaid group, including the CHIP-funded Medicaid expansion, since NC has no separate CHIP. Enrollment doesn't matter. The stated fact that Child 3 \"has employer-sponsored insurance\" counts as actual group health coverage for the whole year.",
  "independent_answer": 0,
  "law_supports": "consensus"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine determined that child3, a 9-year-old in North Carolina, is eligible for Medicaid under the older child category. The household's Modified Adjusted Gross Income (MAGI) was calculated at 2.13 times the Federal Poverty Level, which falls within North Carolina's Medicaid income limits for children in this age group. Under the older child eligibility category that applies to children aged 6 through 18, the state's income threshold permits eligibility at this MAGI level. The engine's output of `is_medicaid_eligible = True` for child3 reflects this qualification based on both the applicable age category and the household's income relative to the federal poverty guideline.
----- END ENGINE DERIVATION -----