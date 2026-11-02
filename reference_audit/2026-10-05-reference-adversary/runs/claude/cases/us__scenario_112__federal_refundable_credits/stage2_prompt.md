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
STATE: TX
OUTPUT: federal_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable federal income tax credits, including EITC and refundable portions of credits such as refundable CTC when applicable; exclude the ACA Premium Tax Credit

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only federal_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: TX
- tax year: 2026

Head:
- age: 31
- gross wages and salaries: $5,923
- bank account assets: $10
- employer sponsored insurance premiums: $8,389
- farm rent income: $1,920
- financial assistance: $13,000
- has employer-sponsored insurance
- long-term capital gains: $-9,944
- over-the-counter health expenses: $1
- unadjusted basis of qualified property: $54,381

Household inputs:
- household vehicles value: $11,838

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

ENGINE REFERENCE VALUE: $453.10 (engine output 453.0960083007813)
MODELS: 46 gave a usable answer; 25 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 15 models (0 of them among the benchmark's top-ranked models)
- claude-haiku-4.5: answered 0
  explanation: The household has gross wages of $5,923 and farm rent income of $1,920, totaling $7,843 in gross income before adjustments. With employer-sponsored insurance premiums of $8,389 and a long-term capital loss of $9,944, the household has a net loss position. After applying the capital loss limitation and standard deduction, the household's taxable income is negative, resulting in no federal income tax liability. With no tax liability and income below EITC and Child Tax Credit thresholds (no children or dependents are listed), no refundable federal credits are available. value = 0
- claude-opus-4.8: answered 0
  explanation: Head is single, age 31, no qualifying children, so no refundable CTC. EITC for childless workers requires the worker not be a dependent; earned income is $5,923 wages. However, the long-term capital loss (-$9,944) plus farm rent ($1,920) and wages results in very low/negative AGI. Investment income is not over the limit. For a childless worker, EITC phases in then out; but with negative net income overall and capital losses, refundable credits compute to essentially zero given the income mix. No qualifying children means no refundable CTC. value = 0
- claude-sonnet-5: answered 0
  explanation: Head has no qualifying children, is 31 years old, and has net self-employment/farm income plus a capital loss resulting in low earned income (~$7,843 wages+farm rent). EITC for a childless filer phases in but at this income level (~$7,843) with no children, the EITC amount would be around $600-700, however the large capital loss (-$9,944) reduces AGI below zero, and investment income limits/disqualification factors combined with the very small earned income base make the credit effectively negligible. No qualifying children means no refundable CTC. Given the complexity and offsetting factors, estimated refundable credit rounds to $0. value = 0
- deepseek-v4-pro: answered 0
  explanation: No qualifying children for the Child Tax Credit, and earned income is effectively zero because employer-sponsored insurance premiums ($8,389) exceed wages ($5,923), reducing earned income to $0 for EITC purposes. Thus, EITC is $0 and total refundable credits are $0. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household does not meet the earned income threshold or eligibility requirements for EITC or refundable CTC given the income levels. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: With pre-tax employer-sponsored insurance premiums fully offsetting gross wages, the household has zero earned income for the Earned Income Tax Credit and has no qualifying children for other credits. value = 0
- gemini-3.5-flash: answered 0
  explanation: The head has $0 in earned income after deducting pre-tax health insurance premiums from gross wages, making them ineligible for the Earned Income Tax Credit (EITC). There are no qualifying children for the Child Tax Credit. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: Federal refundable credits are 0 for the head in tax year 2026. value = 0
- gemini-3.7-flash: answered 0
  explanation: The household has no qualifying children and zero taxable earned income after pre-tax health deductions, resulting in $0 in refundable tax credits. value = 0
- glm-5.3: answered 0
  explanation: The head has no qualifying children, so the only possible refundable credit is the childless EITC. Earned income is $5,923, giving a phase-in credit of about 7.65% x $5,923 = $453, but the higher of earned income and modified AGI ($17,843) is well into the childless EITC phase-out range, reducing the credit to zero. No other refundable credits apply. value = 0
- gpt-5.4-mini: answered 0
  explanation: With no qualifying dependent children and no refundable federal credit indicated by the provided facts, refundable federal credits are zero. value = 0
- gpt-5.4-nano: answered 0
  explanation: No refundable federal credits (EITC/ACTC/other refundable credits) are specified or inferable from the provided facts (no children, no ACA premium tax credit); thus refundable federal income tax credits are $0. value = 0
- grok-4.3: answered 0
  explanation: No qualifying children or earned income sufficient for EITC or other refundable credits. value = 0
- minimax-m3: answered 0
  explanation: With very low income (MAGI approximately $5,923-$8,389 for ACA), EITC for a household with no qualifying children at this income is minimal or zero, and refundable CTC requires children. Head is single (no spouse) with no children listed, so refundable credits are negligible. Total federal refundable credits = value = 0.
- qwen3.8-max: answered 0
  explanation: No refundable federal credits apply under these household facts. value = 0

STAGE 1 RESULT (frozen; sha256 3d171f4929c64eef30836aadd9e4423230b8eb278f66868d585b16c8dd8b6f13):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "Several consensus models read the $8,389 of 'employer sponsored insurance premiums' as pre-tax \u00a7125 salary reductions. On that reading, Box-1 wages would be zero, earned income zero, and the EITC $0. The prompt does not support this: it gives wages as gross, says not to infer unlisted facts, and the premiums are larger than wages, so they could not all come out of pay. Another model added the $13,000 of financial assistance to AGI. That income is not taxable, and even if it were included, the EITC would be about $130, not $0. If the IRS EIC Table were used instead of the statutory formula, the answer would be $453 rather than $453.10.",
  "citations": [
    {
      "pinpoint": "Section on \u00a732(b) earned income credit table for 2026; \u00a732(i) excessive investment income",
      "pre_freeze": true,
      "published": "2025-11-03",
      "quote": "No Qualifying Children: Earned Income Amount $8,680; Maximum Amount of Credit $664; Threshold Phaseout Amount (All other filing statuses) $10,860; Completed Phaseout Amount $19,540; investment income ... cannot exceed $12,200",
      "source": "Rev. Proc. 2025-32 (Internal Revenue Bulletin 2025-45)",
      "url": "https://www.irs.gov/irb/2025-45_IRB"
    },
    {
      "pinpoint": "\u00a732(a)(1)",
      "pre_freeze": true,
      "published": "current code (in force for 2026)",
      "quote": "there shall be allowed as a credit against the tax imposed by this subtitle for the taxable year an amount equal to the credit percentage of so much of the taxpayer's earned income for the taxable year as does not exceed the earned income amount.",
      "source": "26 U.S. Code \u00a7 32",
      "url": "https://www.law.cornell.edu/uscode/text/26/32"
    },
    {
      "pinpoint": "\u00a732(a)(2)(B)",
      "pre_freeze": true,
      "published": "current code (in force for 2026)",
      "quote": "the phaseout percentage of so much of the adjusted gross income (or, if greater, the earned income) of the taxpayer for the taxable year as exceeds the phaseout amount.",
      "source": "26 U.S. Code \u00a7 32",
      "url": "https://www.law.cornell.edu/uscode/text/26/32"
    },
    {
      "pinpoint": "\u00a732(c)(2)(A)(i)",
      "pre_freeze": true,
      "published": "current code (in force for 2026)",
      "quote": "wages, salaries, tips, and other employee compensation, but only if such amounts are includible in gross income for the taxable year",
      "source": "26 U.S. Code \u00a7 32",
      "url": "https://www.law.cornell.edu/uscode/text/26/32"
    },
    {
      "pinpoint": "\u00a732(i)(2)(C)-(D)",
      "pre_freeze": true,
      "published": "current code (in force for 2026)",
      "quote": "the capital gain net income (as defined in section 1222) of the taxpayer for such taxable year",
      "source": "26 U.S. Code \u00a7 32",
      "url": "https://www.law.cornell.edu/uscode/text/26/32"
    },
    {
      "pinpoint": "\u00a71211(b)",
      "pre_freeze": true,
      "published": "current code (in force for 2026)",
      "quote": "plus (if such losses exceed such gains) the lower of\u2014 (1) $3,000 ($1,500 in the case of a married individual filing a separate return), or (2) the excess of such losses over such gains.",
      "source": "26 U.S. Code \u00a7 1211",
      "url": "https://www.law.cornell.edu/uscode/text/26/1211"
    },
    {
      "pinpoint": "\u00a76401(b)(1)",
      "pre_freeze": true,
      "published": "current code (in force for 2026)",
      "quote": "If the amount allowable as credits under subpart C of part IV of subchapter A of chapter 1 (relating to refundable credits) exceeds the tax imposed by subtitle A ... the amount of such excess shall be considered an overpayment.",
      "source": "26 U.S. Code \u00a7 6401",
      "url": "https://www.law.cornell.edu/uscode/text/26/6401"
    }
  ],
  "computation": "1) Filing status and children: the Head files as single and has no qualifying children, so there is no CTC/ACTC. The Head is not a student, so there is no refundable AOTC. The ACA Premium Tax Credit is excluded by the definition, and no other refundable credit applies. The only candidate is the EITC for a worker without a qualifying child.\n2) EITC eligibility, IRC \u00a732(c)(1)(A)(ii): the Head is 31, which falls between 25 and 65. Unlisted facts are treated as false, so the Head is not someone else's dependent. A US principal residence is assumed.\n3) Earned income, \u00a732(c)(2)(A)(i): wages of $5,923. The prompt gives these as gross wages. It does not say the $8,389 of ESI premiums were paid pre-tax through a \u00a7125 plan, and the premiums are larger than total wages, so I did not treat them as reducing wages. Farm rent is rental income, not earnings from self-employment.\n4) AGI: wages of $5,923 plus farm rent of $1,920 gives $7,843. The net long-term capital loss of $9,944 is limited to $3,000 by \u00a71211(b), so AGI is $4,843. The $13,000 of financial assistance is not taxable income.\n5) Investment income test, \u00a732(i): disqualified income is $1,920 of net rent plus $0 capital gain net income, for $1,920. The 2026 limit is $12,200, so the test is passed.\n6) 2026 parameters, Rev. Proc. 2025-32 (published before the 2026-07-03 freeze): earned income amount $8,680, maximum credit $664, single phaseout threshold $10,860. The credit rate is 7.65% under \u00a732(b).\n7) Phase-in: 7.65% \u00d7 $5,923 = $453.10. Phaseout: the greater of AGI ($4,843) and earned income ($5,923) is $5,923. That is below $10,860, so there is no reduction.\n8) EITC = $453.10. Under \u00a76401(b) it is refundable. Total federal refundable credits = $453.10. Using the IRS EIC Table's $50 brackets instead would give $453.",
  "confidence": "high",
  "definition_reading": "This is a single-person household with one tax unit: the Head, filing single. The output is the sum of the federal refundable credits on that return, excluding the PTC. With no children and no education expenses, the only refundable credit is the childless-worker EITC, and all of it is refundable.",
  "independent_answer": 453.1,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
For this Texas single filer in 2026 with a household income of approximately -$2,101, PolicyEngine calculated federal refundable credits of $453.10. The entire amount derives from the Earned Income Tax Credit (EITC), which is the only refundable credit component with a non-zero value in this case. The other potential refundable credits—refundable American Opportunity Credit, refundable Child Tax Credit, Recovery Rebate Credit, and refundable payroll tax credit—all contributed $0 to the total, either because the household does not qualify for them or does not meet their respective eligibility thresholds. The negative household income figure suggests the presence of business losses or other deductions that reduced the household's net income below zero, yet the EITC calculation still yielded a modest refundable credit of $453.10.
----- END ENGINE DERIVATION -----