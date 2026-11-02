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
STATE: ID
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: ID
- tax year: 2026

Head:
- age: 45
- gross wages and salaries: $160,000
- bank account assets: $163,500
- child support received: $9,600
- employer sponsored insurance premiums: $6,480
- has employer-sponsored insurance
- hourly wage: $96
- usual weekly hours worked: 26
- other medical expenses: $1,000
- over-the-counter health expenses: $500
- rental income: $4,000
- stock assets: $19,000
- taxable interest income: $220
- unadjusted basis of qualified property: $49,921

Child 1:
- age: 13
- has employer-sponsored insurance
- over-the-counter health expenses: $200

Child 2:
- age: 8
- has employer-sponsored insurance
- other medical expenses: $2,000
- over-the-counter health expenses: $200

Tax unit:
- first home mortgage balance: $420,000

Benefit inputs:
- pre-subsidy childcare expenses: $1,000

Household inputs:
- household vehicles value: $69,100

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

ENGINE REFERENCE VALUE: $465.00
MODELS: 45 gave a usable answer; 7 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 18 models (0 of them among the benchmark's top-ranked models)
- claude-haiku-4.5: answered 0
  explanation: Idaho does not have state-level refundable individual income tax credits for tax year 2026. The household has substantial income ($160,000 in wages plus $9,600 child support plus $4,000 rental income plus $220 interest), and while they may qualify for federal credits, Idaho's tax code does not provide refundable state credits that would apply to this household's situation. value = 0
- claude-opus-4.8: answered 0
  explanation: Idaho's primary refundable individual income tax credit is the Grocery Credit. However, for 2026 with this household income level ($160,000 wages plus other income), the grocery credit in Idaho is a nonrefundable credit that reduces tax liability and only becomes refundable in limited circumstances; modeling the standard refundable state credits yields no qualifying refundable amount here given no low-income or specially refundable credits apply. value = 0
- claude-opus-5: answered 0
  explanation: Idaho's grocery credit and child credits are nonrefundable/not modeled as refundable at this income; no refundable state credits apply. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Idaho has no broadly available refundable individual income tax credits for tax year 2026. Idaho's main credits (such as the grocery credit) are nonrefundable. The household does not qualify for any Idaho refundable credits based on the provided facts (no Idaho earned income credit or other refundable credit applies). value = 0
- claude-sonnet-5: answered 0
  explanation: Idaho does not offer a general refundable individual income tax credit for this household's profile; with $160,000+ in wages plus other income, the household's income is far too high for Idaho's limited refundable credits (e.g., grocery credit is nonrefundable offset against tax but Idaho's grocery credit is actually refundable - however at this income level no other refundable credits apply and grocery credit is a small per-person credit already reflected elsewhere). No qualifying refundable state credit applies here, so state_refundable_credits = 0. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: No state refundable credits apply for this income level in Idaho. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: Idaho does not have refundable state income tax credits applicable to this household's income level and configuration. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Total refundable state individual income tax credits are $0. value = 0
- gemini-3.6-flash: answered 0
  explanation: The household does not qualify for refundable Idaho state tax credits. value = 0
- gemini-3.8-flash: answered 0
  explanation: No refundable state income tax credits apply in PolicyEngine for Idaho. value = 0
- gpt-5.4-mini: answered 0
  explanation: No Idaho refundable income tax credits are indicated from the provided facts. value = 0
- gpt-5.4-nano: answered 0
  explanation: With income far above typical Idaho refundable credit thresholds and no eligibility indicators supplied, refundable state credits are estimated at 0; value = 0
- gpt-5.6-luna: answered 0
  explanation: No refundable Idaho individual income tax credit applies to this household; value = 0
- grok-4.3: answered 0
  explanation: No state refundable credits applicable. value = 0
- grok-build-0.1: answered 0
  explanation: Idaho grocery credit and any other refundable credits are fully phased out at this income level. value = 0
- minimax-m3: answered 0
  explanation: Idaho refundable credits (e.g., grocery credit) are minimal at this income level and not triggered by listed facts. value = 0
- qwen-3.7-max: answered 0
  explanation: Idaho does not offer refundable income tax credits that apply to this household's situation. The household has no earned income credit eligibility, no qualifying refundable credits based on the listed facts. value = 0
- qwen3.8-max: answered 0
  explanation: No Idaho refundable credits apply to this household. value = 0

STAGE 1 RESULT (frozen; sha256 54c6459ab474c6cd75a448f74919abc27b5efad2cc129304e7ea0d5462260f90):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "One could argue that only the part of the grocery credit above Idaho tax liability is \"refundable.\" That part is $0 here, because this household's Idaho tax far exceeds $465. But the statute makes the whole credit refundable: the unused balance is paid out as a refund. The definition asks for refundable credits, not refunds in excess of liability, so the full $465 counts. The receipt-based credit of up to $250 per person does not apply, because no food sales tax receipts are listed.",
  "citations": [
    {
      "pinpoint": "\u00a7 63-3024A(1)",
      "pre_freeze": true,
      "published": "2025-03",
      "quote": "For tax year 2025 and each year thereafter, the credit is one hundred fifty-five dollars ($155).",
      "source": "Idaho Code \u00a7 63-3024A, Food Tax Credits and Refunds (am. 2025, ch. 56, sec. 1)",
      "url": "https://legislature.idaho.gov/statutesrules/idstat/title63/t63ch30/sect63-3024a/"
    },
    {
      "pinpoint": "\u00a7 63-3024A(1), refund of unused credit",
      "pre_freeze": true,
      "published": "2025-03",
      "quote": "If taxes due are less than the total credit allowed, the taxpayer shall be paid a refund equal to the balance of the unused credit.",
      "source": "Idaho Code \u00a7 63-3024A, Food Tax Credits and Refunds",
      "url": "https://legislature.idaho.gov/statutesrules/idstat/title63/t63ch30/sect63-3024a/"
    },
    {
      "pinpoint": "\u00a7 63-3024A(1), persons covered",
      "pre_freeze": true,
      "published": "2025-03",
      "quote": "a credit against taxes due under the Idaho income tax act for the taxpayer, the taxpayer's spouse, and each dependent",
      "source": "Idaho Code \u00a7 63-3024A, Food Tax Credits and Refunds",
      "url": "https://legislature.idaho.gov/statutesrules/idstat/title63/t63ch30/sect63-3024a/"
    },
    {
      "pinpoint": "Credit amount",
      "pre_freeze": true,
      "published": "2026-02-19",
      "quote": "$155 per person or up to $250 if you submit receipts for sales tax paid for food",
      "source": "Idaho State Tax Commission, Idaho Food Tax Credit page",
      "url": "https://tax.idaho.gov/taxes/income-tax/individual-income/popular-credits-and-deductions/idaho-grocery-credit/"
    },
    {
      "pinpoint": "\u00a7 63-3029L",
      "pre_freeze": null,
      "published": "unknown",
      "quote": "two hundred five dollars ($205)",
      "source": "Idaho Code \u00a7 63-3029L, Child Tax Credit",
      "url": "https://legislature.idaho.gov/statutesrules/idstat/title63/t63ch30/sect63-3029l/"
    },
    {
      "pinpoint": "Bill status history",
      "pre_freeze": true,
      "published": "2026-02-12",
      "quote": "Reported Printed; Filed in the Office of the Chief Clerk",
      "source": "Idaho Legislature, 2026 House Bill 633",
      "url": "https://legislature.idaho.gov/sessioninfo/2026/legislation/h0633/"
    }
  ],
  "computation": "1. Idaho's food tax credit (grocery credit) under Idaho Code \u00a7 63-3024A is allowed for the taxpayer, the spouse and each dependent. As amended by 2025 ch. 56 (HB 231), the credit is $155 per person \"for tax year 2025 and each year thereafter.\" That law was in force before the 2026-07-03 freeze, so it covers tax year 2026.\n2. The credit is refundable. The statute says: \"If taxes due are less than the total credit allowed, the taxpayer shall be paid a refund equal to the balance of the unused credit.\"\n3. The credit has no income limit. It is only prorated for months of SNAP receipt or incarceration, and denied for unlawful residence. None of these facts is listed, so all are false. The household would not qualify for SNAP anyway, with over $170k of income.\n4. The household is a single head with 2 dependent children, all Idaho residents. That makes 3 people \u00d7 $155 = $465.\n5. A receipt-based credit of up to $250 per person is available, but no food purchase receipts or sales tax amounts are listed, so they are treated as 0 and the standard $155 applies.\n6. No other refundable Idaho credit applies:\n   - The Idaho child tax credit (\u00a7 63-3029L, $205 per child) is expressly nonrefundable. It would also sunset for years beginning on or after 2026-01-01 unless extended. Either way, it does not count as a refundable credit.\n   - Idaho treats child care through a deduction, not a refundable credit.\n   - The Parental Choice credit needs qualifying education expenses, and none are listed.\n7. 2026 HB 633, which would have repealed the grocery credit and exempted food from sales tax, was only introduced and printed (2/11\u20132/12/2026). It was not enacted.\n\nTotal refundable state credits = $465.",
  "confidence": "high",
  "definition_reading": "I read the output as the sum of all refundable Idaho individual income tax credits for the household's one tax unit: a single head of household with two dependent children. In Idaho, the only refundable credit these facts trigger is the food tax (grocery) credit under \u00a7 63-3024A. It is $155 for each of the 3 people, or $465. The credit has no income phase-out, so the consensus view that it phases out at high income is wrong.",
  "independent_answer": 465,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine calculated state refundable credits of $465 for this Idaho household in 2026. The entire amount comes from Idaho's refundable grocery credit (id_refundable_credits), as all other states' refundable credit programs yielded zero. The grocery credit is based on a per-entity base amount of $155 for each of the three household members (the head of household and two children), totaling $465. Each household member qualified for all 12 months of the tax year, resulting in 36 total qualifying months across the household. No other state refundable credits applied to this benchmark household.
----- END ENGINE DERIVATION -----