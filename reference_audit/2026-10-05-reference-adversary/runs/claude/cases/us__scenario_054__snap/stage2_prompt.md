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
OUTPUT: snap (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: annual SNAP (food stamps) benefit amount

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only snap):
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

ENGINE REFERENCE VALUE: $6,060.00
MODELS: 46 gave a usable answer; 2 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 6,068, given by 6 models (3 of them among the benchmark's top-ranked models)
- claude-fable-5.1: answered 6,068.4
  explanation: Household of 3, monthly gross income $1,425 (under 130% FPL). Deductions: 20% earned income ($285) and standard deduction ($209) → net income $931. Benefit = $785 max allotment − 30% × 931 = $505.70/month × 12. value = 6068.4
- claude-opus-5.5: answered 6,068.4
  explanation: Monthly income is $1,425. Subtracting the 20% earned income deduction ($285) and the $209 standard deduction leaves net income of $931. The benefit is $785 max allotment minus 30% of $931, which is $505.70 per month, or $6,068.40 per year. No shelter costs were listed. value = 6068.4
- claude-sonnet-5.5: answered 6,068
  explanation: Gross monthly income is 1,425. Net income is 931 after the 20% earned income deduction (285) and the standard deduction (about 209). No shelter costs are listed, so there is no shelter deduction. Monthly benefit = 785 (3-person maximum allotment) − 30% × 931 = about 505.7. Annual = about 6,068. value = 6068
- gpt-6-astra: answered 6,068.4
  explanation: North Carolina categorical eligibility removes the asset test. Using a $785 monthly maximum, $209 standard deduction, and 20% earned-income deduction gives 12 × [785 − 0.30 × (1425 × 0.80 − 209)]; value = 6068.4
- gpt-6-luna: answered 6,068
  explanation: Estimated monthly SNAP is about $505.70: the FY2026 three-person maximum of about $785 less 30% of estimated net monthly income of $931 after the earned-income and standard deductions; annualized. value = 6068
- ox-alpha: answered 6,068.4
  explanation: Monthly gross income $1,425 ($17,100/12) passes NC's 130% FPL gross-income test (~$2,887). Net income = $1,425 − $285 (20% earned income deduction) − $209 (standard deduction, size 3) = $931. Monthly allotment = $785 (FY2026 max for 3) − 30% × $931 ($279.30) = $505.70, so annual SNAP = $505.70 × 12 = $6,068.40. value = 6068.4

STAGE 1 RESULT (frozen; sha256 3735ca7353c9699e9405b686e4b3e821d34438bfd4ce3c56a110518114618ce5):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "If calendar 2026 is computed month by month with the law actually in force, October\u2013December 2026 fall under the FY2027 COLA ($808 maximum for 3, $217 standard deduction). That COLA was published about 2026-08-21, after the freeze. That reading gives 9\u00d7$505 + 3\u00d7$531 = $6,138, which matches neither the reference nor the consensus. No reading supports the consensus $6,068.40, because 7 CFR 273.10(e)(2)(ii)(A) requires whole-dollar rounding either way.",
  "citations": [
    {
      "pinpoint": "\u00a7273.10(e)(2)(ii)(A)",
      "pre_freeze": true,
      "published": "in force; longstanding",
      "quote": "If 30 percent of the household's net income ends in cents, the State agency shall round in one of the following ways: (1) The State agency shall round the 30 percent of net income up to the nearest higher dollar; or (2) ... the State agency shall round the allotment down to the nearest lower dollar.",
      "source": "7 CFR 273.10 (Code of Federal Regulations, USDA FNS SNAP regulations)",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.10"
    },
    {
      "pinpoint": "\u00a7273.10(e)(1)(i)",
      "pre_freeze": true,
      "published": "in force; longstanding",
      "quote": "Multiply the total gross monthly earned income by 20 percent and subtract that amount from the total gross income",
      "source": "7 CFR 273.10 (Code of Federal Regulations)",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.10"
    },
    {
      "pinpoint": "Maximum allotments and standard deduction tables (48 States & DC); read via search-result summary because the PDF returned 403",
      "pre_freeze": true,
      "published": "2025 (effective 2025-10-01)",
      "quote": "the standard deduction for household sizes 1 through 3 is $209 a month ... maximum allotment for a household size of 3 in the 48 States and D.C. is $785",
      "source": "USDA FNS, SNAP \u2014 Fiscal Year 2026 Cost-of-Living Adjustments memo",
      "url": "https://www.usda.gov/sites/default/files/guidance-documents/fns.snap-cola-fy26memo.pdf"
    },
    {
      "pinpoint": "Expanded (200%) categorical eligibility criteria; resource test; read via search-result summary because the PDF would not parse",
      "pre_freeze": true,
      "published": "2024-10",
      "quote": "the income of the household is at or below the 200% maximum allowable gross income limit ... the household automatically passes the resource test",
      "source": "NC DHHS Food and Nutrition Services Manual, FNS 220 Categorical Eligibility",
      "url": "https://policies.ncdhhs.gov/wp-content/uploads/FNS-220-Categorical-Eligibility-10.2024.pdf"
    },
    {
      "pinpoint": "Self-employment, allowable costs of doing business (315.28); read via search-result summary",
      "pre_freeze": null,
      "published": "unknown",
      "quote": "Deductions from self-employment income must be allowable (reasonable to the cost of doing business).",
      "source": "NC DHHS Food and Nutrition Services Manual, FNS 315 Special Budgeting Income (self-employment)",
      "url": "https://policies.ncdhhs.gov/wp-content/uploads/fns-315-special-budgeting-income.pdf"
    },
    {
      "pinpoint": "Maximum allotment for size 3; standard deduction for sizes 1\u20133 (read via secondary summary)",
      "pre_freeze": false,
      "published": "2026-08-21 (effective 2026-10-01)",
      "quote": "The standard deduction for household sizes 1 through 3 will increase to $217 ... 3 $808",
      "source": "USDA FNA, SNAP \u2014 Fiscal Year 2027 Cost-of-Living Adjustments memo",
      "url": "https://www.usda.gov/sites/default/files/guidance-documents/fna.snap-cola2027.pdf"
    }
  ],
  "computation": "1) SNAP household = Head (40) + Child 1 (10) + Child 2 (2) = 3 people, all living together.\n2) Income: The only income is $17,100 of self-employment income. NC subtracts only actual allowable business costs (FNS 315), and none are listed, so countable gross = $17,100/12 = $1,425/month. WIC is not counted as income.\n3) Eligibility: NC expanded (200% FPL) categorical eligibility lets the household pass the resource test automatically, so the $14,000 bank balance is disregarded. $1,425 is under 200% FPL and also under the 130% gross limit for 3 (about $2,888 in FY2026).\n4) Net income (7 CFR 273.10(e)(1)(i)): the 20% earned-income deduction is $285, leaving $1,140. The FY2026 standard deduction for 1\u20133 people is $209, leaving $931. There is no medical deduction because no one is elderly or disabled, so the children's medical/OTC costs and Head's OTC costs don't count. There is no dependent-care or child-support deduction and no shelter or utility deduction, because no rent or utilities are listed.\n5) Allotment (7 CFR 273.10(e)(2)(ii)(A)): the FY2026 maximum for 3 people is $785. 30% \u00d7 $931 = $279.30. Under option (1) it rounds up to $280, so 785 \u2212 280 = $505. Under option (2), 785 \u2212 279.30 = $505.70 rounds down to $505. Either way the benefit is $505/month.\n6) Annual: $505 \u00d7 12 = $6,060.\nThe consensus figure of $6,068.40 skips the mandatory whole-dollar rounding.\nPublication timing: The FY2026 COLA (max $785, standard deduction $209, effective 10/1/2025\u20139/30/2026) was published before the 2026-07-03 freeze. The FY2027 COLA (max $808, standard deduction $217 for 1\u20133 people, effective 10/1/2026) is dated about 2026-08-21, after the freeze. Before the freeze, only FY2026 amounts had been published. Applying FY2027 to Oct\u2013Dec 2026: net income = 1425 \u2212 285 \u2212 217 = 923; 30% = 276.90, rounded to 277; 808 \u2212 277 = $531. Calendar-year total = 9\u00d7505 + 3\u00d7531 = $6,138.",
  "confidence": "high",
  "definition_reading": "The output is the annual SNAP allotment for the single 3-person SNAP household (Head plus two children): the monthly allotment under federal rules as NC applies them, times 12. I used the parameters published as of the 2026-07-03 freeze (FY2026 COLA) for all 12 months. All three people are in one SNAP household, so only one benefit is covered.",
  "independent_answer": 6060,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine computes annual SNAP of $6,060 for this three-person North Carolina household as the sum of twelve monthly allotments of $505 each, January through December. The head's $17,100 of self-employment income counts as $1,425 a month of gross earned income. Deductions total $494 a month: a $209 standard deduction plus a $285 earned income deduction, leaving net income of $931. The household passes the gross and net income tests and is categorically eligible through TANF non-cash eligibility, with gross income at 64% and net income at 42% of the monthly poverty guideline of $2,220.83 in January through September (63% and 41% of $2,276.67 in October through December) and $14,000 in assets passing the asset test. Each month the $785 maximum allotment minus a $280 expected contribution gives $505.
----- END ENGINE DERIVATION -----