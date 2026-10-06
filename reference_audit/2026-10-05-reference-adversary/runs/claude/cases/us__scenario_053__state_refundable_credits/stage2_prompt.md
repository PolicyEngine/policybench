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
- age: 25
- gross wages and salaries: $66,969
- bank account assets: $3,660
- employer sponsored insurance premiums: $3,389
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $5,000
- hourly wage: $32
- usual weekly hours worked: 40
- is paid hourly
- other health insurance premiums: $5,000
- other medical expenses: $400
- over-the-counter health expenses: $150
- pre-subsidy rent: $37,200

Household inputs:
- auto loan balance: $19,000
- auto loan interest: $950
- household vehicles value: $7,410

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

ENGINE REFERENCE VALUE: $155.00
MODELS: 45 gave a usable answer; 7 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 20 models (0 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Idaho's main refundable credit is the grocery credit, but PolicyEngine models Idaho's grocery credit as nonrefundable/other credit treatment; the single filer with $66,969 wages has no children and exceeds income limits for any refundable state credits, so total refundable Idaho income tax credits are 0. value = 0
- claude-haiku-4.5: answered 0
  explanation: Idaho does not have a state earned income tax credit (EITC) or other refundable state income tax credits for 2026. The household head is a single taxpayer age 25 with gross wages of $66,969, placing them above any potential income thresholds for credits. Idaho's tax system does not provide refundable credits for this income level and filing status. value = 0
- claude-opus-4.7: answered 0
  explanation: Idaho's main refundable individual income tax credit is the Grocery Credit (typically $120/person), but it is generally claimed as a nonrefundable credit against tax with any excess refundable only for full-year residents who file specifically for it. However, single filer with $66,969 wages has Idaho tax liability well exceeding the grocery credit, so it offsets tax rather than being refunded. No other Idaho refundable credits apply (no dependents for CTC, no qualifying child care, etc.). value = 0
- claude-opus-4.8: answered 0
  explanation: Idaho has a grocery credit, but for a single filer with ~$67k wages and no dependents, the grocery credit ($120) is nonrefundable in effect via the income tax return offset; with no other refundable state credits applicable to this household, total refundable state credits = 0. value = 0
- claude-opus-5: answered 0
  explanation: Idaho grocery credit is the main credit and is applied against liability; no refundable state credits remain at this income. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Idaho does not have any refundable individual income tax credits for tax year 2026. Idaho's tax credits (such as the grocery credit) are nonrefundable. The household has no qualifying basis for any refundable state credit in Idaho. value = 0
- claude-sonnet-5: answered 0
  explanation: Idaho does not offer a refundable state individual income tax credit applicable to this household's situation (e.g., no grocery credit refund beyond offset, no EITC state supplement). Given the head's income level and lack of qualifying dependents, there are no refundable state credits owed. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: The Idaho refundable grocery credit is fully phased out at this AGI of $66,969. value = 0
- deepseek-v4-pro: answered 0
  explanation: No refundable Idaho credits apply (e.g., grocery credit has income limit). value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: No state refundable credits apply for this household profile. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: No state refundable credits apply. value = 0
- glm-5.2: answered 0
  explanation: Idaho does not provide refundable individual income tax credits for this household. No listed facts establish eligibility for any refundable Idaho tax credit, and Idaho's grocery credit is a nonrefundable credit. Therefore total refundable state income tax credits are 0.0. value = 0.0
- gpt-5.4-mini: answered 0
  explanation: No refundable Idaho income tax credits are indicated by the household facts, so the amount is zero. value = 0
- gpt-5.4-nano: answered 0
  explanation: No state refundable credits (e.g., refundable child-related credits) were indicated in the household facts, so refundable state credits estimated as 0 = value = 0
- gpt-5.6-luna: answered 0
  explanation: Income is too high for an Idaho grocery or other refundable individual income tax credit under the stated facts. value = 0
- grok-4.3: answered 0
  explanation: No state refundable credits apply. value = 0
- grok-build-0.1: answered 0
  explanation: No state refundable credits apply based on household facts. value = 0
- minimax-m3: answered 0
  explanation: No Idaho refundable credits apply based on listed facts (no children, no property tax credit eligibility without rent info beyond pre-subsidy). value = 0
- qwen-3.7-max: answered 0
  explanation: Idaho does not have a state Earned Income Tax Credit or Child Tax Credit. No refundable credits apply to this household based on the listed facts (no children, no other credit-qualifying conditions). value = 0
- qwen3.8-max: answered 0
  explanation: Idaho does not provide a state refundable income tax credit for this household based on the listed facts. value = 0

STAGE 1 RESULT (frozen; sha256 1559ce55eb3a5e537f78adbc740b3bca36078d07fe3aff62b0a82a91944e8fbc):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "One could argue that a refundable credit counts only to the extent it exceeds liability. On that reading the answer would be 0, because the head's Idaho tax is well above $155. Neither the definition nor the statute supports this. The credit is refundable by statute, and the companion output measures tax before refundable credits, so the credit has to be counted in full here. The consensus explanations rest on factual errors: that the grocery credit is nonrefundable or has an income limit. It has no income limit, and it is refundable for full-year residents.",
  "citations": [
    {
      "pinpoint": "\u00a7 63-3024A(1)",
      "pre_freeze": true,
      "published": "2025 (am. 2025, ch. 56, sec. 1, p. 267)",
      "quote": "For tax year 2025 and each year thereafter, the credit is one hundred fifty-five dollars ($155).",
      "source": "Idaho Code \u00a7 63-3024A, Food Tax Credits and Refunds",
      "url": "https://legislature.idaho.gov/statutesrules/idstat/title63/t63ch30/sect63-3024a/"
    },
    {
      "pinpoint": "\u00a7 63-3024A(1) refund provision",
      "pre_freeze": true,
      "published": "2025",
      "quote": "If taxes due are less than the total credit allowed, the taxpayer shall be paid a refund equal to the balance of the unused credit.",
      "source": "Idaho Code \u00a7 63-3024A, Food Tax Credits and Refunds",
      "url": "https://legislature.idaho.gov/statutesrules/idstat/title63/t63ch30/sect63-3024a/"
    },
    {
      "pinpoint": "\u00a7 63-3024A(5)",
      "pre_freeze": true,
      "published": "2025",
      "quote": "the credit or refund allowed under this section shall be in proportion to the number of months of the year in which no assistance was received.",
      "source": "Idaho Code \u00a7 63-3024A, Food Tax Credits and Refunds",
      "url": "https://legislature.idaho.gov/statutesrules/idstat/title63/t63ch30/sect63-3024a/"
    },
    {
      "pinpoint": "799.02 and priority list item (b)",
      "pre_freeze": null,
      "published": "unknown (rule in force)",
      "quote": "For part-year residents only, the grocery credit as authorized by Section 63-3024A, Idaho Code",
      "source": "IDAPA 35.01.01.799, Priority Order of Credits and Adjustments to Credits (Idaho State Tax Commission rule)",
      "url": "https://www.law.cornell.edu/regulations/idaho/IDAPA-35.01.01.799"
    },
    {
      "pinpoint": "Credit amount section",
      "pre_freeze": true,
      "published": "2026-02-19",
      "quote": "For most Idaho residents it's $155 per person or up to $250 if you submit receipts for sales tax paid for food.",
      "source": "Idaho State Tax Commission, Idaho Food Tax Credit web page",
      "url": "https://tax.idaho.gov/taxes/income-tax/individual-income/popular-credits-and-deductions/idaho-grocery-credit/"
    },
    {
      "pinpoint": "Food tax credit paragraph",
      "pre_freeze": true,
      "published": "2026-03-11",
      "quote": "The food tax credit (formerly known as the Grocery Credit) is now $155 per person.",
      "source": "Idaho State Tax Commission press release, What's new for 2025 income tax returns",
      "url": "https://tax.idaho.gov/pressrelease/whats-new-for-2025-income-tax-returns/"
    }
  ],
  "computation": "1. The household is one full-year Idaho resident filing single. The head is 25, earns $66,969 in wages and has no dependents. With that income the head must file an Idaho return.\n2. Idaho Code \u00a7 63-3024A(1) gives a resident who files a return a food tax credit (formerly called the grocery credit) for each personal exemption. The amount is $155 for \"tax year 2025 and each year thereafter.\" The 2025 amendment (2025 ch. 56, HB 231) was enacted in 2025, before the 2026-07-03 freeze, so the 2026 amount was published before the freeze. HB 605 (2026), a senior-only increase, was only filed and printed and never enacted. Even if enacted, it would not apply to a 25-year-old.\n3. The credit is refundable. Under \u00a7 63-3024A(1), \"If taxes due are less than the total credit allowed, the taxpayer shall be paid a refund equal to the balance of the unused credit.\" The Tax Commission also calls the credit refundable. IDAPA 35.01.01.799 lists the grocery credit as nonrefundable only \"for part-year residents,\" so for a full-year resident it is refundable.\n4. None of the limits apply:\n   - SNAP months: \u00a7 63-3024A(5) prorates the credit for months of food stamp receipt. No SNAP receipt is listed, and at $67k of income a single person is not SNAP-eligible anyway.\n   - Incarceration and unlawful residence are unlisted, so treated as false.\n   - There is no income cap.\n   - The receipts alternative (up to $250) is not available because no food sales tax receipts are given.\n5. The credit is 1 person \u00d7 $155 = $155.\n6. No other refundable credit applies. Idaho has no state EITC, its child tax credit is nonrefundable and there are no children. Total refundable state credits are $155.\n7. Whether the head's Idaho tax is large enough to absorb the credit does not affect its classification. A refundable credit is still a refundable credit when it reduces a tax balance, and the companion output state_income_tax_before_refundable_credits is measured before this credit.",
  "confidence": "high",
  "definition_reading": "\"Total refundable state individual income tax credits\" means the sum of every Idaho credit that is refundable by law, whether or not the filer's liability absorbs it. For a full-year Idaho resident, the \u00a7 63-3024A food tax credit is refundable: any excess over tax is paid out. Form 40 reports it with payments rather than with the nonrefundable credits. This household is one single filer with no dependents, so the total is that person's $155 food tax credit.",
  "independent_answer": 155,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
For this Idaho resident in 2026, PolicyEngine calculated total state refundable credits of $155. This amount comes entirely from Idaho's grocery credit (id_grocery_credit), which contributed the full $155. The grocery credit calculation determined that the household qualified for all 12 months of the tax year, with each month meeting the qualifying criteria. The base grocery credit amount (id_grocery_credit_base) was set at $155, and since the household qualified for the full year with no phase-out or reduction applied, this base amount became the final credit value. All other states' refundable credits returned zero, as the household resides in Idaho.
----- END ENGINE DERIVATION -----