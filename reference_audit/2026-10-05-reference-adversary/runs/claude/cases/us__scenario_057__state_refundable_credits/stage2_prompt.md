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
STATE: LA
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: LA
- tax year: 2026

Head:
- age: 43
- bank account assets: $912
- disability benefits: $14
- is blind
- is disabled
- over-the-counter health expenses: $20
- sstb self employment income before lsr: $10,400

Spouse:
- age: 20
- disability benefits: $24
- is disabled
- over-the-counter health expenses: $20

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
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_medicaid_eligible: whether Spouse is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_chip_eligible: whether Spouse is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- spouse_medicare_eligible: whether Spouse is eligible for Medicare (1 if yes, 0 if no)
- free_school_meals_eligible: whether PolicyEngine returns positive annual free school meal support for the household (1 if yes, 0 if no; reduced-price meals do not count as 1)
- reduced_price_school_meals_eligible: whether PolicyEngine returns positive annual reduced-price school meal support for the household (1 if yes, 0 if no; free meals do not count as 1)

Use the `submit_outputs` function exactly once. Return an `outputs` object with every requested quantity keyed by variable name. Each requested key must map to an object with a numeric `value` and a non-empty, specific, concise `explanation`. Each explanation must support the numeric value submitted for the same variable in `outputs`. If an explanation mentions a final amount, that amount must match the corresponding `outputs` value. Do not write that you will use one value while submitting a different value. Do not include scratch work, abandoned calculations, or corrections. End each explanation with `value = X`, where X exactly matches the numeric `value` field. For 1/0 eligibility outputs, submit 1 only when the explanation says eligible or yes, and submit 0 only when it says not eligible or no. Use the exact variable names as keys inside `outputs`. Include every requested key exactly once in `outputs`, even if the value is 0. Put only numeric values in `value`, with no dollar signs, commas, or explanatory text. Do not rely on plain text for the final answers. If an answer is a currency amount, give the annual amount. If an answer is a rate, give a decimal (e.g. 0.25 for 25%).
----- END HOUSEHOLD PROMPT -----

ENGINE REFERENCE VALUE: $33.20 (engine output 33.20000076293945)
MODELS: 45 gave a usable answer; 15 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 25 models (1 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Louisiana's refundable individual income tax credits (e.g., school readiness credit, refundable child care credit for low income, inventory tax credit) do not apply: the household has no children, no child care expenses, and no qualifying inventory taxes. Self-employment income of $10,400 with no wages does not generate any LA refundable credit; LA has no state EITC match for filers without a federal EITC-qualifying situation with earned income only from self-employment—actually LA does have a 5% EITC match, but with married filing jointly, no children, and net self-employment earnings around $9,600, the federal EITC for childless couples is small; however, the head is a disabled/blind adult aged 43 which keeps them in the 25-64 eligible range, so a small federal EITC could exist. Given the instruction to not infer unlisted inputs and the microsimulation result, total refundable state credits = 0. value = 0
- claude-haiku-4.5: answered 0
  explanation: Louisiana does not have significant refundable state income tax credits for individuals in the general filing population. While Louisiana offers various tax credits, most are nonrefundable. The household has minimal income after self-employment taxes and standard deductions, and no eligible dependents or circumstances that would generate refundable state credits under LA tax law. value = 0
- claude-opus-4.7: answered 0
  explanation: Louisiana refundable credits (e.g., school readiness, earned income, child care) require qualifying children or related expenses. This household has no children, no childcare expenses, and no earned income qualifying for LA EITC beyond minimal self-employment. No refundable LA credits apply. value = 0
- claude-opus-4.8: answered 0
  explanation: Louisiana refundable individual income tax credits primarily include the refundable Child Care Credit, School Readiness Credit, and Earned Income Credit. This household has no qualifying children, no child care expenses, and self-employment income of $10,400 (head) which after self-employment tax deduction yields little to no LA EITC since LA EITC is 5% of federal EITC for childless filers; with two adults and only $10,400 net SE income, federal/state EITC for a married couple with no children is minimal and the refundable state credits round to zero given no children or care expenses. value = 0
- claude-opus-5: answered 0
  explanation: Louisiana has no refundable EITC-type credit applicable here (state EITC applies only with qualifying earned-income credit at federal level and the LA EITC is 5% of federal EITC but is nonrefundable/limited; no refundable credits computed for this household). value = 0
- claude-sonnet-4.6: answered 0
  explanation: Louisiana has a nonrefundable personal income tax credit structure. For tax year 2026, Louisiana does not offer refundable state individual income tax credits applicable to this household's situation. The household has self-employment income of $10,400 (SSTB) for the head, with disability benefits of $14 (head) and $24 (spouse), but disability benefits are generally not taxable for Louisiana purposes and the self-employment income is modest. Louisiana's income tax credits (such as the personal exemption credit and dependent credits) are nonrefundable. There are no Louisiana refundable credits (e.g., no state EITC, no refundable child tax credit) available for this household in 2026. Therefore, total refundable state individual income tax credits = $0. value = 0
- claude-sonnet-5: answered 0
  explanation: Louisiana does not offer a refundable state earned income tax credit or other refundable individual income tax credit that this household's income and demographic profile (self-employment income of $10,400, disability status, no dependents) would qualify for under LA tax law. Louisiana's EITC-like credit and other credits are generally nonrefundable or the household lacks qualifying dependents/income needed to trigger the available refundable credits, so the estimated refundable state credit total is 0. value = 0
- claude-sonnet-5.5: answered 0
  explanation: No refundable Louisiana credit applies to this household. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Federal EITC is $0, so Louisiana's refundable EITC-based credit is also $0 and no other refundable state credit applies. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: No state refundable credits are applicable. value = 0
- gemini-3.5-flash: answered 0
  explanation: The household does not qualify for any refundable state income tax credits in Louisiana. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: The household has no state refundable tax credits in Louisiana. value = 0
- glm-5.2: answered 0
  explanation: The household is ineligible for the Louisiana Earned Income Tax Credit because the spouse is under age 25, and no other refundable state income tax credits apply to these facts. value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable Louisiana income tax credits are triggered by the listed facts. value = 0
- gpt-5.4-nano: answered 0
  explanation: No refundable LA state credits (per provided facts) are indicated, so submitted as 0. value = 0
- gpt-5.6-luna: answered 0
  explanation: No qualifying Louisiana refundable individual income tax credit applies to this two-adult household without children; value = 0
- gpt-5.6-terra: answered 0
  explanation: No Louisiana refundable credit eligibility is indicated by the household facts. value = 0
- grok-4.3: answered 0
  explanation: No state refundable credits apply or qualify for this household. value = 0
- grok-4.5: answered 0
  explanation: Louisiana provides no refundable income-tax credits that apply to this household. value = 0
- grok-build-0.1: answered 0
  explanation: Louisiana does not provide refundable state income tax credits applicable to this household's situation. value = 0
- inkling: answered 0
  explanation: Federal EITC is $0, so Louisiana's state EITC (5% of federal) is $0, and there are no other refundable state credits for this household. value = 0
- minimax-m3: answered 0
  explanation: Louisiana has no state individual income tax and therefore no refundable state income tax credits. value = 0
- ox-alpha: answered 0
  explanation: No refundable Louisiana income tax credits apply to this household with zero liability and no qualifying expenses or children. value = 0
- qwen-3.7-max: answered 0
  explanation: Louisiana does not have a state individual income tax, so there are no refundable state individual income tax credits. value = 0
- qwen3.8-max: answered 0
  explanation: No Louisiana refundable credits apply based on the listed household facts. value = 0

STAGE 1 RESULT (frozen; sha256 7447b99c161f0ef12dd7cbe69da1b4a48b838da4be0ea146013029a4d374dd00):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "No reading of the definition gives a different number. Whether the full credit counts or only the amount above tax owed makes no difference, because Louisiana tax before credits is $0 (AGI is below the $25,000 joint standard deduction). Different ways of computing self-employment earned income (with or without the 92.35% factor) and whether the $38 of disability benefits is taxable also make no difference: earned income is above the $8,680 plateau and AGI is below the $18,140 phase-out threshold in every case. The models answering $0 appear to have believed Louisiana has no refundable EITC, or that the 20-year-old spouse disqualifies the couple. Under \u00a732(c)(1)(A)(ii) only one spouse must be 25\u201364.",
  "citations": [
    {
      "pinpoint": "\u00a7297.8(A)(2) and (B)",
      "pre_freeze": true,
      "published": "2021-06-23",
      "quote": "five percent of the federal earned income tax credit for which the individual is eligible for the taxable year under Section 32 of the Internal Revenue Code ... such excess tax credit shall constitute an overpayment from the current collections of the taxes imposed under this Part",
      "source": "Louisiana Revised Statutes 47:297.8, Earned income tax credit",
      "url": "https://www.legis.la.gov/legis/Law.aspx?d=453085"
    },
    {
      "pinpoint": "Section 4.06, Earned Income Credit table, No Qualifying Children column",
      "pre_freeze": true,
      "published": "2025-11-03",
      "quote": "For taxable years beginning in 2026, the following amounts are used to determine the earned income credit under \u00a7 32(b). ... Earned Income Amount $8,680 ... Maximum Amount of Credit $664 ... Threshold Phaseout Amount (Married Filing Jointly) $18,140",
      "source": "IRS Rev. Proc. 2025-32 (Internal Revenue Bulletin 2025-45)",
      "url": "https://www.irs.gov/irb/2025-45_IRB"
    },
    {
      "pinpoint": "\u00a732(c)(1)(A)(ii)(II)",
      "pre_freeze": true,
      "published": "current code (as amended through 2025)",
      "quote": "such individual (or, if the individual is married, either the individual or the individual's spouse) has attained age 25 but not attained age 65 before the close of the taxable year",
      "source": "26 U.S.C. \u00a7 32",
      "url": "https://www.law.cornell.edu/uscode/text/26/32"
    },
    {
      "pinpoint": "\u00a732(c)(2)(A)",
      "pre_freeze": true,
      "published": "current code (as amended through 2025)",
      "quote": "plus the amount of the taxpayer's net earnings from self-employment for the taxable year (within the meaning of section 1402(a)), but such net earnings shall be determined with regard to the deduction allowed to the taxpayer by section 164(f)",
      "source": "26 U.S.C. \u00a7 32",
      "url": "https://www.law.cornell.edu/uscode/text/26/32"
    },
    {
      "pinpoint": "\u00a7293 standard deduction definition",
      "pre_freeze": true,
      "published": "2024-12-04",
      "quote": "For Married-Joint Return filers ... 200% of the dollar amount provided for Single Individuals ($12,500)",
      "source": "Louisiana Revised Statutes 47:293 (as amended by Acts 2024, 3rd Ex. Sess., No. 11)",
      "url": "https://www.legis.la.gov/Legis/Law.aspx?d=101760"
    }
  ],
  "computation": "1) Federal EITC (IRC \u00a732), joint return with no qualifying children. Age test (\u00a732(c)(1)(A)(ii)(II)): for a married filer, either spouse may meet the 25\u201364 age range. The head is 43, so the couple qualifies even though the spouse is 20. 2) Earned income (\u00a732(c)(2)(A)): net self-employment earnings reduced by the \u00a7164(f) deduction for half of SE tax. SE tax = 10,400 \u00d7 0.9235 \u00d7 0.153 = 1,469.47; half = 734.73. Earned income \u2248 10,400 \u2212 734.73 = 9,665.27. Under the stricter \u00a71402(a)(12) reading it is \u2248 8,869.66. Both are above the 2026 earned income amount of $8,680 (Rev. Proc. 2025-32 \u00a74.06). So the phase-in is complete: 7.65% \u00d7 8,680 = $664, the 2026 maximum for no children. 3) AGI \u2248 $9,665, or up to \u2248 $9,703 if the $38 of disability benefits were taxable. That is below the $18,140 joint-return phase-out threshold, so there is no reduction. Investment income is $0, below the $12,200 limit. Federal EITC = $664. 4) Louisiana EIC (R.S. 47:297.8(A)(2)): 5% of the federal EITC for tax years 2019\u20132030. 0.05 \u00d7 664 = $33.20. 5) Refundability (R.S. 47:297.8(B)): any credit above tax liability is an overpayment and is refunded. Louisiana AGI \u2248 $9,700 is below the $25,000 joint standard deduction (R.S. 47:293, Act 11 of 2024 3rd Ex. Sess.; $12,500 single \u00d7 200%, CPI-indexed from 2026). So Louisiana tax is $0 and the full $33.20 is refunded. 6) The other Louisiana refundable credits (school readiness, refundable child care, etc.) require children or expenses that are not listed, so they are $0. Total Louisiana refundable credits = $33.20. All 2026 parameters used (Rev. Proc. 2025-32, released October 2025) were published before 2026-07-03. HB 133 (2025 RS), which would have raised the credit to 10%, stayed pending in House Ways and Means. The statute's history ends with Acts 2021, No. 453.",
  "confidence": "high",
  "definition_reading": "I read the definition as the sum of all refundable Louisiana individual income tax credits on the couple's single joint return. For this household, the only one is the Louisiana Earned Income Credit (5% of the federal EITC), which R.S. 47:297.8(B) makes refundable. The household has no children and no child care or other qualifying expenses, so no other Louisiana refundable credit applies.",
  "independent_answer": 33.2,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine calculated state refundable credits of $33.20 for this Louisiana household by aggregating refundable tax credits across all 50 states and DC. Since the household is located in Louisiana (LA = True), only the Louisiana refundable credits component was non-zero. Louisiana's refundable credits of $33.20 derive entirely from the Louisiana Earned Income Tax Credit (EITC), which is calculated as 5% of the federal EITC. With a federal EITC of $664, the state EITC equals $33.20 (5% × $664), and this amount comprises the household's total state refundable credits for the 2026 tax year.
----- END ENGINE DERIVATION -----