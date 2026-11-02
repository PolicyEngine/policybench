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
- age: 56
- bank account assets: $71,500
- employer sponsored insurance premiums: $6,309
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $2,080
- usual weekly hours worked: 50
- other health insurance premiums: $2,080
- other medical expenses: $150
- pre-subsidy rent: $18,353
- Social Security disability income: $19,285
- tax exempt private pension income: $284
- taxable private pension income: $35,280

Household inputs:
- household vehicles value: $2,660

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
MODELS: 45 gave a usable answer; 10 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 17 models (0 of them among the benchmark's top-ranked models)
- claude-haiku-4.5: answered 0
  explanation: Idaho does not have refundable state individual income tax credits. The state offers various tax credits such as the dependent exemption credit, residential energy credit, and others, but none are refundable credits that would result in a payment to the taxpayer when the credit exceeds tax liability. This household's Idaho state income tax credits, if any apply, would be non-refundable. value = 0
- claude-opus-4.8: answered 0
  explanation: Idaho's main refundable credit is the Grocery Credit, but it is nonrefundable when claimed on the income tax return (refundable only via separate filing) and Idaho has no other refundable individual income tax credits applicable here. This household has no qualifying children or other refundable Idaho credits, so total refundable state credits are zero. value = 0
- claude-opus-5: answered 0
  explanation: Idaho grocery credit is a refundable-style credit but is handled as a nonrefundable/other item, and no refundable Idaho credits apply to this single filer with no children; treating refundable state credits as zero. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Idaho's refundable state individual income tax credits for tax year 2026 include the Idaho Child Tax Credit and the Grocery Credit. The head is age 56 with no dependents listed, so no Child Tax Credit applies. The Idaho Grocery Credit is a refundable credit available to Idaho residents; however, the head receives Social Security disability income of $19,285. The Grocery Credit is available to residents who are not claimed as dependents, but the credit for those receiving Social Security is embedded in the credit structure. For 2026, Idaho's Grocery Credit is $120 per person (approximately). However, reviewing Idaho law: the Grocery Credit is $120 per exemption for taxpayers who do not receive Social Security benefits, and for those who DO receive Social Security, the credit is instead claimed against the Social Security income offset. Actually, under Idaho code, taxpayers who receive Social Security benefits receive the Grocery Credit as a refundable credit of $120. The head receives SSDI of $19,285, qualifying them for the Idaho Grocery Credit. For 2026, the Idaho Grocery Credit is $120 per person (the head, 1 person). There are no dependents. The credit amount is $120. However, since the head has SSDI income, they are entitled to the refundable grocery credit of $120. But Idaho's grocery credit for those on Social Security is refundable only if they have no tax liability, and it phases: for 2026, the credit is $120. With taxable private pension income of $35,280 and SSDI (which Idaho partially taxes), there will be tax liability, so the grocery credit of $120 offsets tax but may not be refundable beyond liability. Idaho's grocery credit is nonrefundable for those with tax liability. Given the head has substantial pension income ($35,280 taxable), Idaho taxable income will exceed zero and the grocery credit ($120) will be fully used as a nonrefundable credit against tax liability, yielding $0 in refundable state credits. value = 0
- claude-sonnet-5: answered 0
  explanation: Idaho does not offer a refundable state individual income tax credit that this household qualifies for (Idaho's state credits, such as the grocery credit, are nonrefundable against tax liability in this modeling, and no other refundable credits apply). value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Idaho's refundable grocery credit phases out entirely at this income level (single filer income far above the ~$22,500 phaseout threshold), so the refundable credit is $0. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household does not qualify for refundable state income tax credits in Idaho. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: State refundable credits are $0. value = 0
- glm-5.2: answered 0
  explanation: The household has $0 Idaho state income tax liability and no qualifying children for the Idaho Child Tax Credit. Idaho's grocery credit has been repealed, and no other refundable state individual income tax credits apply. value = 0
- gpt-5.4-mini: answered 0
  explanation: No Idaho refundable income tax credits are indicated for this household, value = 0
- gpt-5.4-nano: answered 0
  explanation: No qualifying conditions for refundable state credits are provided in the household facts, so refundable state credits are 0; value = 0
- gpt-5.6-terra: answered 0
  explanation: No refundable Idaho credit applies; income is above the phaseout for the Idaho grocery credit. value = 0
- grok-4.3: answered 0
  explanation: Idaho provides no refundable credits applicable to this household. value = 0.0
- grok-build-0.1: answered 0
  explanation: No state refundable income tax credits apply based on the given household facts and composition. value = 0
- minimax-m3: answered 0
  explanation: No state income tax in Idaho, no refundable state credits. value = 0
- qwen-3.7-max: answered 0
  explanation: Idaho does not have significant refundable income tax credits applicable to this household's situation, so state refundable credits total $0. value = 0
- qwen3.8-max: answered 0
  explanation: No Idaho refundable credits apply to this household based on the listed facts. value = 0.0

STAGE 1 RESULT (frozen; sha256 447741f848b94f9503c1d238fb4707ebfaec1e22cb484441e823d39316199e8b):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "A second reading would count only the part of the credit paid out beyond tax liability, not the part used to offset tax. That reading is not a natural meaning of 'total refundable credits'. It could give a value below $155, but the models' $0 answers rest on legal mistakes (that the credit is nonrefundable, repealed or phased out), not on this reading. The 'PolicyEngine rules' wording does not appear in this output's definition.",
  "citations": [
    {
      "pinpoint": "\u00a7 63-3024A(1)",
      "pre_freeze": true,
      "published": "2025",
      "quote": "For tax year 2025 and each year thereafter, the credit is one hundred fifty-five dollars ($155).",
      "source": "Idaho Code \u00a7 63-3024A, Food tax credits and refunds (as amended 2025, ch. 56, \u00a7 1 \u2014 HB 231)",
      "url": "https://legislature.idaho.gov/statutesrules/idstat/title63/t63ch30/sect63-3024a/"
    },
    {
      "pinpoint": "\u00a7 63-3024A(1) (refund of unused credit)",
      "pre_freeze": true,
      "published": "2025",
      "quote": "If taxes due are less than the total credit allowed, the taxpayer shall be paid a refund equal to the balance of the unused credit.",
      "source": "Idaho Code \u00a7 63-3024A, Food tax credits and refunds",
      "url": "https://legislature.idaho.gov/statutesrules/idstat/title63/t63ch30/sect63-3024a/"
    },
    {
      "pinpoint": "\u00a7 63-3024A (food stamp proration)",
      "pre_freeze": true,
      "published": "2025",
      "quote": "the credit or refund allowed under this section shall be in proportion to the number of months of the year in which no assistance was received",
      "source": "Idaho Code \u00a7 63-3024A, Food tax credits and refunds",
      "url": "https://legislature.idaho.gov/statutesrules/idstat/title63/t63ch30/sect63-3024a/"
    },
    {
      "pinpoint": "Credit amount section",
      "pre_freeze": true,
      "published": "2026-02-19",
      "quote": "For most Idaho residents it's $155 per person or up to $250 if you submit receipts for sales tax paid for food.",
      "source": "Idaho State Tax Commission, Idaho Food Tax Credit",
      "url": "https://tax.idaho.gov/taxes/income-tax/individual-income/popular-credits-and-deductions/idaho-grocery-credit/"
    },
    {
      "pinpoint": "Bill history",
      "pre_freeze": true,
      "published": "2026-02-09",
      "quote": "Reported Printed; Filed in the Office of the Chief Clerk",
      "source": "Idaho Legislature, House Bill 605 (2026) bill status",
      "url": "https://legislature.idaho.gov/sessioninfo/2026/legislation/H0605/"
    }
  ],
  "computation": "1) Idaho Code 63-3024A(1) gives each resident individual a food tax credit (formerly the 'grocery credit') for the taxpayer, spouse and each dependent claimed. For tax year 2025 and each year after, it is $155 per person. HB 231 (2025) raised it from $120 and dropped the separate higher amount for people 65 or older. 2) The credit is refundable: 'If taxes due are less than the total credit allowed, the taxpayer shall be paid a refund equal to the balance of the unused credit.' 3) The household is one Idaho resident filer (head, age 56) with no spouse or dependents, so the credit is 1 \u00d7 $155 = $155. 4) The credit is prorated for months with food stamp (SNAP) receipt or incarceration. Neither applies. Nothing about incarceration is listed. The head is not SNAP-eligible: gross income is about $54,849 a year (SSDI $19,285 + pensions $35,564), about $4,571 a month. Net income after the standard, medical and shelter deductions is roughly $3,600 a month, far above the 100% FPL net limit of about $1,305. Bank assets of $71,500 also exceed Idaho's SNAP asset limit. So no SNAP and no proration. 5) No 2026 change applies. 2026 HB 605 would only have raised the credit for seniors. Its last action was printing and filing (Feb. 9, 2026), so it did not pass, and the head is 56 regardless. 6) No other Idaho refundable individual credit applies: Idaho's child tax credit is nonrefundable, and there are no children. Total refundable state credits = $155. Whether the $155 offsets tax or is paid as a refund, it is still a refundable credit.",
  "confidence": "high",
  "definition_reading": "'Total refundable state individual income tax credits' for Idaho covers the refundable food tax credit under Idaho Code 63-3024A. It is $155 per person, and here it covers only the single resident filer. It is counted in full whether it offsets tax or is refunded, because by statute the whole credit is refundable.",
  "independent_answer": 155,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
For this Idaho resident in 2026, PolicyEngine calculated state refundable credits of $155, which derives entirely from the Idaho Grocery Credit. The household qualified for all 12 months of the tax year, with each month meeting the qualifying criteria for the grocery credit program. The base grocery credit amount was determined to be $155, and since the household had no disqualifying factors and met all eligibility requirements throughout the year, this full base amount was awarded as a refundable credit. All other states' refundable credit programs returned zero values, as the household resides in Idaho and does not qualify for credits in other jurisdictions.
----- END ENGINE DERIVATION -----