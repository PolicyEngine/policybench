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
OUTPUT: head_wic_eligible (an eligibility flag, 1 or 0)
OUTPUT DEFINITION, as the models saw it: whether Head is eligible for WIC (1 if yes, 0 if no)

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only head_wic_eligible):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: NC
- tax year: 2026

Head:
- age: 40
- bank account assets: $14,000
- over-the-counter health expenses: $200
- receives wic
- sstb self employment income before lsr: $17,100

Child 1:
- age: 10

Child 2:
- age: 2
- has employer-sponsored insurance
- other medical expenses: $400
- over-the-counter health expenses: $25

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
- child1_wic_eligible: whether Child 1 is eligible for WIC (1 if yes, 0 if no)
- child2_wic_eligible: whether Child 2 is eligible for WIC (1 if yes, 0 if no)
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_medicaid_eligible: whether Child 1 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_medicaid_eligible: whether Child 2 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_chip_eligible: whether Child 1 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_chip_eligible: whether Child 2 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
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

ENGINE REFERENCE VALUE: 0 (not eligible)
MODELS: 46 gave a usable answer; 30 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 1, given by 16 models (1 of them among the benchmark's top-ranked models)
- claude-haiku-4.5: answered 1
  explanation: The head of household is 40 years old and currently receives WIC. To assess eligibility, WIC typically requires that at least one child in the household be under age 5. The household includes Child 2 who is age 2, which satisfies the age requirement for a child in the household. The head's SSTB self-employment income before LSR is $17,100. North Carolina WIC income limits for 2026 for a family of 3 are approximately 185% of the federal poverty line (approximately $43,070 for a household of 3). The household income of $17,100 is well below this threshold. The head has $14,000 in liquid assets, which is within typical asset limits. The head is already receiving WIC and meets the eligibility criteria: presence of an eligible child under 5, income below the threshold, and acceptable asset levels. value = 1
- claude-opus-4.7: answered 1
  explanation: Head has a child under age 5 (Child 2 is age 2) in the household, making her a qualifying caretaker. Income is modest enough to qualify. value = 1
- claude-opus-4.8: answered 1
  explanation: Head is a 40-year-old in a household with young children (ages 10 and 2), and WIC eligibility requires categorical status (pregnant, postpartum, breastfeeding, infant, or child under 5) plus income limits. The household has a child under 5, and WIC has adjunctive/income eligibility tied to low income; with modest self-employment income (~$17,100) and a household of three, income falls under the WIC income threshold. Head receives WIC, confirming eligibility. value = 1
- claude-opus-5: answered 1
  explanation: Head reports receiving WIC and household income is below 185% FPL, so head is categorically eligible (as a postpartum/breastfeeding-type participant per stated receipt). value = 1
- claude-sonnet-5: answered 1
  explanation: Head has a child under age 5 (child 2, age 2) in the household, making her a categorically eligible caretaker/family member for WIC, and self-employment income of $17,100 falls below NC's WIC income eligibility threshold (185% FPL) for a household of this size; she is also already noted as receiving WIC, confirming adjunct eligibility. value = 1
- deepseek-v4-flash-0731: answered 1
  explanation: Head already receives WIC and is income-eligible as a member of a 3-person household below 185% FPL. value = 1
- deepseek-v4-pro: answered 1
  explanation: Head receives WIC, so eligible. value = 1
- deepseek-v4-pro-0813: answered 1
  explanation: Head is listed as receiving WIC, and household income is below WIC income limits. value = 1
- gemini-3-flash-preview: answered 1
  explanation: The Head is listed as receiving WIC benefits, confirming their eligibility for the program. value = 1
- gemini-3.7-flash: answered 1
  explanation: Head is explicitly reported as receiving WIC and is income-eligible, value = 1
- gpt-5.4-mini: answered 1
  explanation: Head is pregnant/postpartum not stated, but WIC for the adult female/head is marked as received and the household has a young child, so head is treated as eligible. value = 1
- gpt-5.4-nano: answered 1
  explanation: The household fact explicitly says Head receives WIC, so Head is eligible for WIC; value = 1
- gpt-5.6-terra: answered 1
  explanation: Head is stated to receive WIC and is eligible. value = 1
- gpt-6-luna: answered 1
  explanation: Head is explicitly reported as receiving WIC, so Head is treated as WIC eligible. value = 1
- grok-4.3: answered 1
  explanation: Head already receives WIC, confirming eligibility. value = 1
- qwen3.8-max: answered 1
  explanation: The head is pregnant, postpartum, or breastfeeding for WIC purposes and has income below the WIC limit, so the head is eligible. value = 1

STAGE 1 RESULT (frozen; sha256 ed644fadb28b2c136e30197d61c7fce239a5d87f1d88fb144fc1d427a0ce4711):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "There is one other reading. If \"receives wic\" is taken as proof that the Head is a certified WIC participant, then the Head would have to be pregnant, postpartum or breastfeeding, which gives 1 (the consensus). That reading requires inferring a status the prompt does not list. The prompt forbids this: unlisted statuses are false and benefit receipt must not be inferred from. The age-2 youngest child also rules out postpartum or breastfeeding status. The fact more naturally describes WIC received on behalf of Child 2. The law therefore supports 0.",
  "citations": [
    {
      "pinpoint": "\u00a7 1786(d)(1)",
      "pre_freeze": true,
      "published": "in force before 2026; long-standing statutory text",
      "quote": "Participation in the program under this section shall be limited to pregnant, postpartum, and breastfeeding women, infants, and children from low-income families who are determined by a competent professional authority to be at nutritional risk.",
      "source": "42 U.S. Code \u00a7 1786 (Special supplemental nutrition program for women, infants, and children)",
      "url": "https://www.law.cornell.edu/uscode/text/42/1786"
    },
    {
      "pinpoint": "\u00a7 1786(b) definitions (postpartum women; breastfeeding women; children)",
      "pre_freeze": true,
      "published": "in force before 2026; long-standing statutory text",
      "quote": "Postpartum women means women up to six months after termination of pregnancy.",
      "source": "42 U.S. Code \u00a7 1786 (Special supplemental nutrition program for women, infants, and children)",
      "url": "https://www.law.cornell.edu/uscode/text/42/1786"
    },
    {
      "pinpoint": "\u00a7 246.7(c)(1)",
      "pre_freeze": true,
      "published": "in force before 2026",
      "quote": "To qualify for the Program, infants, children, and pregnant, postpartum, and breastfeeding women must: Reside within the jurisdiction of the State ... Meet the income criteria ... Meet the nutritional risk criteria",
      "source": "7 CFR 246.7 Certification of participants (USDA FNS WIC regulations)",
      "url": "https://www.law.cornell.edu/cfr/text/7/246.7"
    },
    {
      "pinpoint": "Eligibility requirements, criterion 1 (categorical)",
      "pre_freeze": null,
      "published": "undated web page",
      "quote": "Be pregnant, postpartum (up to 6 months after pregnancy), breastfeeding (up to one year postpartum), an infant, or a child up to age five.",
      "source": "NC Department of Health and Human Services, Apply for WIC",
      "url": "https://www.ncdhhs.gov/divisions/child-and-family-well-being/community-nutrition-services-section/wic/apply-wic"
    }
  ],
  "computation": "1. The only people who can get WIC are pregnant, postpartum and breastfeeding women, infants, and children under 5. Source: 42 U.S.C. 1786(d)(1) and 7 CFR 246.7(c)(1). North Carolina uses the same categories as its first eligibility test.\n2. The Head is 40, so they are not an infant or a child.\n3. The prompt does not say the Head is pregnant, postpartum or breastfeeding. By the prompt's rules, an unlisted status counts as false.\n4. The family's youngest child (Child 2) is 2. Postpartum status lasts only 6 months after a pregnancy ends, and breastfeeding status lasts up to 1 year postpartum (42 U.S.C. 1786(b)). So no listed child could make the Head postpartum or breastfeeding, even if we allowed that inference.\n5. Because the Head is in no eligible category, the income test does not matter. For the record, the income test is met: income of $17,100 is below 185% of the poverty line for a household of 3.\n6. The fact \"receives wic\" records that the benefit was received. Under the law, receiving WIC does not make someone categorically eligible. Medicaid, SNAP and TANF receipt can satisfy the income test automatically, but no rule lets WIC receipt satisfy the category test. The fact is consistent with WIC going to the family through Child 2, who is 2 and qualifies as a child. The prompt also says not to infer an unlisted status such as pregnancy from that fact.\n7. Result: the Head is not eligible for WIC, so head_wic_eligible = 0. The categories are set in statute and do not change by year, so no 2026 figure was needed.",
  "confidence": "high",
  "definition_reading": "\"Whether Head is eligible for WIC\" asks whether the Head, as an individual, meets WIC's requirements. The first requirement is being in an eligible category: pregnant, postpartum, breastfeeding, infant, or child under 5. The Head is a 40-year-old adult with none of those statuses listed, so the Head is not eligible. Receiving WIC is a benefit-receipt fact, not an eligibility category.",
  "independent_answer": 0,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine determined that the head of household is not WIC eligible (False), while one of the two children in the household is WIC eligible (True). The WIC (Women, Infants, and Children) program eligibility assessment evaluated each household member individually based on age, income, and categorical requirements. With a household income of approximately $0, the income threshold was satisfied for potential beneficiaries. The eligibility result of [False, False, True] indicates that only one child met all WIC eligibility criteria—likely due to age requirements, as WIC serves pregnant women, postpartum women, infants, and children up to age 5, while the head of household and one child did not qualify under these categorical restrictions.
----- END ENGINE DERIVATION -----