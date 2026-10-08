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

Cite the law you rely on as in stage 1: source, pinpoint, URL, date, pre_freeze and a short quote. The engine derivation is not a citation. Do not consult PolicyEngine or PolicyBench in any form: not policyengine.org, policybench.org, their GitHub repositories, their documentation, their package source, or any calculator built on them. Do not fetch anything from these domains: policybench.org, www.policybench.org, policyengine.org, www.policyengine.org, github.com, raw.githubusercontent.com. When your search tool accepts domains to exclude (blocked_domains), pass all of these domains on every search, so that no result comes from them: a search whose results list or name PolicyEngine or PolicyBench voids your answer. Do not rely on any calculator or estimate built by an AI model. A citation of any of these sources voids your answer.

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

STAGE 1 RESULT (frozen; sha256 a8d5ec5a5dbc0e99176c603fc1d68e70a3861952d0757fee0f12836a6de0be22):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "The prompt does not say who paid the $21,208 in employer-sponsored insurance premiums. Suppose they were the head's own after-tax premiums. Then they would come out of total household resources: THR = $15,068, and the homestead credit = 0.6 \u00d7 (2,428.80 \u2212 482.18) = $1,167.97. Under that reading the Home Heating Credit might add about $76.62 ($604 \u2212 3.5% \u00d7 $15,068), if it counts and heat is not included in rent. That would make the answer about $1,168 to $1,245, which is neither the reference nor the consensus. Treasury excludes premiums paid by an employer or through pre-tax payroll, and the prompt gives no fact that they were paid after tax, so I did not apply this reading. Under no reading is the consensus value of 0 correct.",
  "citations": [
    {
      "pinpoint": "Sec. 520 (renter credit; refund of excess)",
      "pre_freeze": true,
      "published": "current as amended (in force for TY2026)",
      "quote": "A person who rents or leases a homestead may claim a similar credit computed under this section and section 522 based upon ... 23% of the gross rent paid for tax years after the 2017 tax year.",
      "source": "Michigan Income Tax Act of 1967, MCL 206.520",
      "url": "https://legislature.mi.gov/Laws/MCL?objectName=MCL-206-520"
    },
    {
      "pinpoint": "Sec. 520 (payment of excess credit)",
      "pre_freeze": true,
      "published": "current as amended",
      "quote": "If the credit claimed under this section and section 522 exceeds the tax liability for the tax year or if there is no tax liability for the tax year, the amount of the claim not used as an offset against the tax liability shall, after examination and review, be approved for payment, without interest, to the claimant.",
      "source": "Michigan Income Tax Act of 1967, MCL 206.520",
      "url": "https://legislature.mi.gov/documents/mcl/pdf/mcl-206-520-amended.pdf"
    },
    {
      "pinpoint": "Sec. 522(1)(a)",
      "pre_freeze": true,
      "published": "current as amended (2023 PA 4)",
      "quote": "60% of the amount by which the property taxes on the homestead, or the credit for rental of the homestead for the tax year, exceeds ... 3.2% of the claimant's total household resources for the 2018 tax year and each tax year after 2018.",
      "source": "Michigan Income Tax Act of 1967, MCL 206.522",
      "url": "https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-206-522"
    },
    {
      "pinpoint": "Tax-year credit limits",
      "pre_freeze": true,
      "published": "2025-12 (TY2025 guidance)",
      "quote": "The maximum credit limit is $1,900, the total household resources limit is $71,500, phase-out begins when total household resources exceed $62,500",
      "source": "Michigan Department of Treasury, 2025 Homestead Property Tax Credit Information",
      "url": "https://www.michigan.gov/taxes/iit/tax-guidance/credits-exemptions/hptc/tax-year-credit-information/2025"
    },
    {
      "pinpoint": "Non-deductible premiums",
      "pre_freeze": null,
      "published": "undated Treasury guidance",
      "quote": "premiums paid by an employer with pre-tax contributions are not deductible",
      "source": "Michigan Department of Treasury, Health Insurance Premiums and Total Household Resources",
      "url": "https://www.michigan.gov/taxes/property/homestead-property-tax-credit-claim-mi-1040cr-adjustment-or-denial-homeowners-checklist/health-insurance-premiums-and-total-household-resources"
    },
    {
      "pinpoint": "0-1 exemptions row",
      "pre_freeze": true,
      "published": "TY2025 (published late 2025/early 2026)",
      "quote": "For 0-1 exemptions, the standard allowance is $604 and the income ceiling is $17,243.",
      "source": "Michigan Department of Treasury, TABLE A: 2025 Home Heating Credit (MI-1040CR-7) Standard Allowance",
      "url": "https://www.michigan.gov/taxes/iit/tax-guidance/credits-exemptions/home-heating-credit/table-a-home-heating-credit-mi-1040cr-7-standard-allowance"
    }
  ],
  "computation": "1) Michigan EITC: it is 30% of the federal EITC. The federal EITC is $0 for a single filer with no qualifying children and $36,276 in wages, because that income is above the phase-out range. Paying child support does not create a qualifying child. So Michigan EITC = 0.\n2) Homestead Property Tax Credit (MI-1040CR) under MCL 206.520 and 206.522. It is a credit against Michigan income tax. Any part above the tax liability is paid to the claimant, so it is a refundable state income tax credit.\n- Renters: 23% of gross rent counts as property tax (MCL 206.520, tax years after 2017). 0.23 \u00d7 $10,560 = $2,428.80.\n- Total household resources (THR) = AGI plus excluded income. Wages are $36,276. No other income is listed, and unemployment compensation is 0 because no amount is listed.\n- Health insurance premiums reduce THR only if the claimant paid them after tax. Treasury says premiums paid by an employer or through pre-tax payroll contributions do not count. The prompt does not say the head paid the $21,208 after tax, so under the 'unlisted = false' rule no deduction applies. THR = $36,276.\n- Rate for claimants who are not seniors: 60% of the amount by which the rent-based tax exceeds 3.2% of THR (MCL 206.522, 2018 and later). 3.2% \u00d7 $36,276 = $1,160.83. $2,428.80 \u2212 $1,160.83 = $1,267.97. 60% \u00d7 $1,267.97 = $760.78. Rounding each line to whole dollars as the form does gives (2,429 \u2212 1,161) \u00d7 0.6 = $760.80, about $761.\n- Limits: the 2025 maximum credit is $1,900, the phase-out starts above $62,500 of THR, and no credit is allowed above $71,500. The 2026 indexed values had not been published before 2026-07-03; Treasury still listed only the 2025 values. They only rise with inflation, so neither limit binds here. The taxable-value cap applies only to homeowners.\n3) Home Heating Credit (MI-1040CR-7): the 2025 income ceiling for 0\u20131 exemptions is $17,243. THR of $36,276 is above it, so the credit is $0. No heating costs are listed either.\nTotal state refundable credits \u2248 $760.78. The engine's $760.79 matches within rounding.",
  "confidence": "high",
  "definition_reading": "'Total refundable state individual income tax credits' covers the head's single Michigan return. It includes the Homestead Property Tax Credit, which is a credit against Michigan income tax whose excess is paid out. It also includes the Michigan EITC ($0 here) and, read broadly, the Home Heating Credit ($0 here). The renter's homestead credit is about $760.78.",
  "independent_answer": 760.78,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
For this Michigan resident with approximately $36,276 in household income, PolicyEngine calculated $760.79 in state refundable credits, which consists entirely of the Michigan Homestead Property Tax Credit. The household qualified for this credit based on having household resources of $36,275.59, which fell below the eligibility threshold. The credit calculation began with countable property tax of $2,428.80 (derived from annual rent of $10,560), from which PolicyEngine applied a household resource exemption of $1,267.98, resulting in an allowable homestead property tax credit of $760.79. All other states' refundable credits were zero, as the household resides in Michigan and does not qualify for credits in other jurisdictions.
----- END ENGINE DERIVATION -----