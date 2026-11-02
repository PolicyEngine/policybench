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