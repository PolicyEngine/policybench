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
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: MI
- tax year: 2026

Head:
- age: 44
- gross wages and salaries: $36,276
- bank account assets: $800
- child support expense: $5,200
- employer sponsored insurance premiums: $21,208
- has employer-sponsored insurance
- hourly wage: $21
- usual weekly hours worked: 40
- is paid hourly
- pre-subsidy rent: $10,560
- weeks unemployed: 8

Household inputs:
- household vehicles value: $16,400

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

ENGINE REFERENCE VALUE: $760.79 (engine output 760.7887573242188)
MODELS: 45 gave a usable answer; 4 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 18 models (0 of them among the benchmark's top-ranked models)
- claude-haiku-4.5: answered 0
  explanation: Michigan does not have a state earned income tax credit (EITC). Michigan has a home property tax credit and homestead property tax credit, but the household is renting (pre-subsidy rent of $10,560), not owning a home. Michigan does not have other significant refundable individual income tax credits for this household composition and income level. No state refundable credits apply. value = 0
- claude-opus-5: answered 0
  explanation: Michigan EITC is 30% of federal EITC, which is $0 here; home heating credit not modeled as income tax refundable credit, so total is $0. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Michigan's primary refundable state income tax credits include the Homestead Property Tax Credit and the Home Heating Credit. The household has no property tax listed and no heating costs listed, so neither applies. There is no mortgage interest deduction context here. Michigan also has the EITC (a percentage of the federal EITC), but the head has no qualifying children listed and is 44 years old. For 2026, a childless worker at age 44 with gross wages of $36,276 minus the child support paid ($5,200, not deductible for Michigan AGI purposes) — Michigan AGI is based on federal AGI. Federal AGI: $36,276 gross wages; employer-sponsored insurance premiums of $21,208 are pre-tax (excluded from gross wages already or treated as W-2 box 1 reduction). Taking wages at face value as $36,276. No qualifying children means the federal EITC for a childless filer at this income level ($36,276) exceeds the phase-out threshold for single filers (approximately $18,591 for 2025, adjusted for 2026), so federal EID would be $0 for this income level. Michigan EITC = 6% (2023 law restored to 30% phased in; for 2026 Michigan EITC is 30% of federal EITC). However, with no federal EITC (income too high for childless filer), Michigan EITC = $0. No other refundable Michigan credits apply given the unlisted inputs. Total refundable state credits = $0. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Michigan EITC is 30% of the federal EITC, which is $0, so the refundable Michigan credit is $0. No other refundable credits apply. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household does not qualify for additional Michigan refundable credits based on inputs provided. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: Since the federal EITC is $0, the Michigan EITC is also $0. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Total refundable state individual income tax credits equal 0. value = 0
- glm-5.2: answered 0
  explanation: Michigan's primary refundable tax credits include the Earned Income Tax Credit (EITC) and the Homestead Property Tax Credit. For tax year 2026, the Michigan EITC is 30% of the federal EITC. The head is a single filer with no children listed. For 2026, the federal EITC for a single filer with no qualifying children and income of $36,276 is 0. Therefore, the state EITC is 0. The Homestead Property Tax Credit is a refundable credit for low-income renters and homeowners. The head's total household resources are $36,276 and rent is $10,560. For renters, 20% of rent is considered property tax paid, which is $2,112. The credit is calculated as 60% of the property tax that exceeds 3.2% of total household resources. 3.2% of $36,276 is $1,160.83. The difference is $951.17. 60% of $951.17 is $570.70. However, the Homestead Property Tax Credit is completely phased out if total household resources exceed $64,000, which is not the case here. The refundable credit is $570.70. value = 0
- glm-5.3: answered 0
  explanation: The Michigan EITC is a percentage of the federal EITC, which is $0 here, and no other refundable Michigan credits apply. value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable Michigan income tax credits are identifiable from the provided household facts. value = 0
- gpt-5.4-nano: answered 0
  explanation: No Michigan refundable credit eligibility details (e.g., qualified dependent or other conditions) are provided, so total state refundable credits are 0. value = 0
- gpt-5.6-terra: answered 0
  explanation: No Michigan refundable credit applies to this childless household. value = 0
- grok-4.3: answered 0
  explanation: No state refundable credits qualify. value = 0
- grok-build-0.1: answered 0
  explanation: No state refundable income tax credits apply based on given facts for Michigan. value = 0
- inkling: answered 0
  explanation: Federal EITC is zero, so the Michigan 6% EITC is zero; the Homestead credit does not exceed the tax liability, so no refundable portion remains. value = 0
- minimax-m3: answered 0
  explanation: Michigan offers limited refundable credits and no household-level refundable credits apply given this household composition and the fact that no rent was actually paid beyond pre-subsidy rent listed. The Michigan homestead property tax credit may apply, but since the head is a renter and the credit is calculated based on rent paid exceeding a threshold, no refundable credit is triggered here, value = 0.
- qwen-3.7-max: answered 0
  explanation: The household has no eligible refundable Michigan state tax credits listed (no Earned Income Tax Credit specified at state level beyond federal match, no homestead property tax credit qualifying based on listed facts, and no other refundable credits). With no qualifying refundable credits, the total is 0. value = 0
- qwen3.8-max: answered 0
  explanation: No refundable state income tax credits apply. value = 0

STAGE 1 RESULT (frozen; sha256 e65a83fe452c2de61da4a0d6cc34903140191ac29b1ca2b1db5041a42bdda378):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "The $21,208 'employer sponsored insurance premiums' could be read as premiums the Head paid out of pocket after tax. MCL 206.510 lets a person deduct premiums they paid from THR. Under that reading THR = $36,276 \u2212 $21,208 = $15,068 and the credit = 0.60 \u00d7 ($2,428.80 \u2212 $482.18) = $1,167.97. This reading is weak: the label points to the employer plan, employer contributions and pre-tax payroll premiums are not deductible, and the prompt says not to infer expenses. Neither reading gives the consensus answer of $0. Whole-dollar rounding on the form gives about $761 instead of $760.78.",
  "citations": [
    {
      "pinpoint": "\u00a7206.520(2)",
      "pre_freeze": true,
      "published": "2016-03-18",
      "quote": "23% of the gross rent paid for tax years after the 2017 tax year",
      "source": "Michigan Compiled Laws, Income Tax Act of 1967, MCL 206.520",
      "url": "https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-206-520"
    },
    {
      "pinpoint": "\u00a7206.520(3)",
      "pre_freeze": true,
      "published": "2016-03-18",
      "quote": "If the credit claimed under this section and section 522 exceeds the tax liability for the tax year or if there is no tax liability for the tax year, the amount of the claim not used as an offset against the tax liability shall, after examination and review, be approved for payment, without interest, to the claimant.",
      "source": "Michigan Compiled Laws, MCL 206.520",
      "url": "https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-206-520"
    },
    {
      "pinpoint": "\u00a7206.522(1)",
      "pre_freeze": true,
      "published": "2016-03-18",
      "quote": "60% of the amount by which the property taxes on the homestead, or the credit for rental of the homestead for the tax year, exceeds ... 3.2% of the claimant's total household resources for the 2018 tax year and each tax year after 2018",
      "source": "Michigan Compiled Laws, MCL 206.522",
      "url": "https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-206-522"
    },
    {
      "pinpoint": "\u00a7206.510(1)-(2)",
      "pre_freeze": true,
      "published": "2012-01-01",
      "quote": "the sum of federal adjusted gross income as defined in the internal revenue code plus all income specifically excluded or exempt from the computations of the federal adjusted gross income ... Contributions by an employer to life, accident, or health insurance plans.",
      "source": "Michigan Compiled Laws, MCL 206.510",
      "url": "https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-206-510"
    },
    {
      "pinpoint": "\u00a7206.508 (definition of total household resources)",
      "pre_freeze": true,
      "published": "2019-01-01",
      "quote": "all income received by all persons of a household in a tax year while members of a household",
      "source": "Michigan Compiled Laws, MCL 206.508",
      "url": "https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-206-508"
    },
    {
      "pinpoint": "Line 31 (health insurance premiums); Line 34 (3.2%); eligibility ($71,500 THR limit)",
      "pre_freeze": true,
      "published": "2026-01",
      "quote": "do not include amounts paid through pre-tax payroll deductions",
      "source": "Michigan Department of Treasury, 2025 MI-1040CR Instructions",
      "url": "https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/IIT/TY2025/MI-1040CR-Instr.pdf"
    },
    {
      "pinpoint": "\u00a7206.272(1)",
      "pre_freeze": true,
      "published": "2023-03-07",
      "quote": "For tax years that begin after December 31, 2022, 30%.",
      "source": "Michigan Compiled Laws, MCL 206.272 (Michigan earned income tax credit)",
      "url": "https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-206-272"
    }
  ],
  "computation": "Filer: a single renter in Michigan, age 44 (not a senior), with no dependents.\n\n1. Michigan EITC (MCL 206.272) is 30% of the federal EITC. The federal EITC is $0. A worker with no qualifying children loses the whole credit at about $19,540 of earned income in 2026, and wages here are $36,276. So the Michigan EITC is $0.\n\n2. Homestead property tax credit for renters (MCL 206.520 and 206.522):\n   a. Rent counted as property tax is 23% of gross rent: 0.23 \u00d7 $10,560 = $2,428.80. No subsidy is listed, so the 10% subsidized-housing rate does not apply.\n   b. Total household resources (THR) = federal AGI plus income excluded from AGI (MCL 206.508 and 206.510).\n      - Wages are $36,276 and there is no other income.\n      - Child support paid is not a deduction.\n      - Employer contributions to health plans are excluded from income (MCL 206.510(2)).\n      - The form's line for premiums the claimant paid does not cover pre-tax payroll deductions.\n      - The prompt does not say the $21,208 'employer sponsored insurance premiums' were paid by the Head after tax. Following the no-inference rule, nothing is deducted, so THR = $36,276.\n   c. The 3.2% floor: 0.032 \u00d7 $36,276 = $1,160.83.\n   d. The excess is $2,428.80 \u2212 $1,160.83 = $1,267.97. A non-senior gets 60%: 0.60 \u00d7 $1,267.968 = $760.78.\n   e. THR of $36,276 is far below the phase-out range ($62,500\u2013$71,500 in 2025). The credit is far below the cap ($1,900 in 2025).\n   f. The 2026 indexed cap and THR limit had not been published before 2026-07-03; only the 2025 values had. Neither would bind here.\n   g. The credit is refundable: any amount above tax liability is paid to the claimant (MCL 206.520(3)).\n   h. If you round each line to whole dollars as the form does: $2,429 \u2212 $1,161 = $1,268, and \u00d7 0.60 = $760.80, about $761.\n\n3. Home heating credit: the household's income is far above the income ceiling for one exemption, so it is $0.\n\nTotal refundable Michigan credits \u2248 $760.78. This matches the reference of $760.79; the gap is only floating-point rounding.",
  "confidence": "high",
  "definition_reading": "'Total refundable state individual income tax credits' means every Michigan credit claimed through the income tax system whose excess over liability is paid out. That covers the Michigan EITC (MCL 206.272), the homestead property tax credit (MCL 206.520(3)) and, if it applies, the home heating credit. There is one tax unit: the Head filing single. The homestead property tax credit for a renter is $760.78. The EITC and home heating credit are $0.",
  "independent_answer": 760.78,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
For this Michigan resident with approximately $36,276 in household income, PolicyEngine calculated $760.79 in state refundable credits, which consists entirely of the Michigan Homestead Property Tax Credit. The household qualified for this credit based on having household resources of $36,275.59, which fell below the eligibility threshold. The credit calculation began with countable property tax of $2,428.80 (derived from annual rent of $10,560), from which PolicyEngine applied a household resource exemption of $1,267.98, resulting in an allowable homestead property tax credit of $760.79. All other states' refundable credits were zero, as the household resides in Michigan and does not qualify for credits in other jurisdictions.
----- END ENGINE DERIVATION -----