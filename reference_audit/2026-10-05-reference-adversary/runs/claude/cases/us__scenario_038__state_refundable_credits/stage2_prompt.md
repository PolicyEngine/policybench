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
- age: 25
- gross wages and salaries: $7,468
- bank account assets: $500
- health insurance premiums excluding Medicare Part B: $100
- other health insurance premiums: $100
- other medical expenses: $1
- over-the-counter health expenses: $1
- self-employment income: $15,525

Spouse:
- age: 18
- other medical expenses: $1
- over-the-counter health expenses: $1

Child 1:
- age: 7
- other medical expenses: $1
- over-the-counter health expenses: $1

Child 2:
- age: 6
- other medical expenses: $1
- over-the-counter health expenses: $1

Tax unit:
- first home mortgage balance: $75,000

Household inputs:
- household vehicles value: $2,090

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
- head_medicaid_eligible: whether Head is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_medicaid_eligible: whether Spouse is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_medicaid_eligible: whether Child 1 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_medicaid_eligible: whether Child 2 is eligible for Medicaid under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_chip_eligible: whether Head is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- spouse_chip_eligible: whether Spouse is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child1_chip_eligible: whether Child 1 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- child2_chip_eligible: whether Child 2 is eligible for CHIP under PolicyEngine rules, not whether they are currently enrolled (1 if yes, 0 if no)
- head_medicare_eligible: whether Head is eligible for Medicare (1 if yes, 0 if no)
- spouse_medicare_eligible: whether Spouse is eligible for Medicare (1 if yes, 0 if no)
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

ENGINE REFERENCE VALUE: $365.80 (engine output 365.8000183105469)
MODELS: 45 gave a usable answer; 10 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 18 models (0 of them among the benchmark's top-ranked models)
- claude-haiku-4.5: answered 0
  explanation: Louisiana does not offer a state refundable earned income tax credit or other major refundable tax credits for this household. The household has federal income tax liability based on wages and self-employment income, but Louisiana's individual income tax credits available to this household composition are limited to non-refundable credits (such as child and dependent care credits, if applicable), which cannot exceed the tax liability. With gross wages of $7,468 and self-employment income of $15,525 (total income $22,993), the household may have a modest Louisiana tax liability after the standard deduction, but no refundable state credits apply that would generate a payment beyond the tax owed. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Louisiana does not have a state Earned Income Tax Credit or other broadly applicable refundable individual income tax credits for tax year 2026. The household's relevant income (wages ~$7,468 + self-employment ~$15,525) may generate a Louisiana income tax liability, but Louisiana's income tax credits (such as the dependent exemption credit) are non-refundable. Louisiana eliminated its refundable EITC and has no other refundable state income tax credits applicable to this household. Therefore, total refundable state individual income tax credits = $0. value = 0
- claude-sonnet-5: answered 0
  explanation: Louisiana does not offer a refundable state EITC or other refundable individual income tax credit that this household qualifies for under current LA tax law (LA's EITC is nonrefundable), and no other refundable state credits apply given the household's facts, so total state refundable credits = 0. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Louisiana has no applicable refundable state income tax credit for this household. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: Louisiana eliminated its state EITC and has no other refundable individual income tax credits. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: There are no applicable state-level refundable credits for this household in Louisiana. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Louisiana state refundable credits are 0. value = 0
- glm-5.2: answered 0
  explanation: Louisiana's state EITC is nonrefundable, and with $0 state income tax liability there are no refundable credits applicable. No other refundable Louisiana tax credits apply to this household. value = 0
- glm-5.3: answered 0
  explanation: Louisiana has no state income tax liability and no refundable state credits apply (the LA EITC and school-readiness credits are nonrefundable or require child care expenses). value = 0
- gpt-5.4-mini: answered 0
  explanation: No Louisiana refundable individual income tax credits apply from the facts provided, so refundable state tax credits are zero. value = 0
- gpt-5.4-nano: answered 0
  explanation: No positive Louisiana refundable credits are expected at this income level in this benchmark scenario. value = 0
- gpt-5.5: answered 0
  explanation: No Louisiana refundable state income tax credits are indicated by the household facts; listed credits or qualifying refundable-credit inputs are absent, so refundable state credits are zero. value = 0
- grok-4.3: answered 0
  explanation: No LA state refundable credits triggered by listed facts. value = 0
- grok-4.5: answered 0
  explanation: Louisiana provides no refundable credits that apply to this household (no state EITC or other refundable offsets). value = 0
- grok-4.6: answered 0
  explanation: Louisiana has no refundable EITC or other refundable individual income tax credits that apply to this filing unit. value = 0
- grok-build-0.1: answered 0
  explanation: Louisiana has no refundable state income tax credits applicable to this household with no qualifying expenses or EITC match. value = 0
- ox-alpha: answered 0
  explanation: With zero Louisiana taxable income and no qualifying activities (e.g., school-readiness child care), no refundable Louisiana income tax credits apply. value = 0
- qwen3.8-max: answered 0
  explanation: Louisiana does not provide refundable individual income tax credits applicable to this household, and no state refundable credit amount is indicated by the household facts. value = 0.0

STAGE 1 RESULT (frozen; sha256 3976cf19c5f638a46519dc666596f6e25bc0ecc0fbbef66129fa87e7c0d99fd6):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "There is no real second reading. The consensus answer of 0 assumes Louisiana has no refundable EITC or repealed it. That is wrong: the 2025 repeal bills (SB 149, HB 642) died in committee, and R.S. 47:297.8 still provides a refundable 5% credit through 2030. A small open point is whether earned income is computed after the half-self-employment-tax deduction. Either way, earned income is between $18,290 and $31,160, so the federal EITC is the $7,316 maximum and the result does not change.",
  "citations": [
    {
      "pinpoint": "R.S. 47:297.8(A)(2)",
      "pre_freeze": true,
      "published": "2021-06-23",
      "quote": "there shall be a credit against the tax imposed by this Chapter for individuals in an amount equal to five percent of the federal earned income tax credit for which the individual is eligible for the taxable year under Section 32 of the Internal Revenue Code.",
      "source": "Louisiana Revised Statutes, Title 47, \u00a7297.8 (Earned income tax credit)",
      "url": "https://www.legis.la.gov/legis/Law.aspx?d=453085"
    },
    {
      "pinpoint": "R.S. 47:297.8(B)",
      "pre_freeze": true,
      "published": "2021-06-23",
      "quote": "If the credit against Louisiana income tax for resident individuals exceeds the amount of such individual's tax liability for the taxable year, then such excess tax credit shall constitute an overpayment from the current collections of the taxes imposed under this Part.",
      "source": "Louisiana Revised Statutes, Title 47, \u00a7297.8 (Earned income tax credit)",
      "url": "https://www.legis.la.gov/legis/Law.aspx?d=453085"
    },
    {
      "pinpoint": "Section 4.06, Earned Income Credit table (two qualifying children)",
      "pre_freeze": true,
      "published": "2025-11-03",
      "quote": "The \"earned income amount\" is the amount of earned income at or above which the maximum amount of the earned income credit is allowed.",
      "source": "IRS Rev. Proc. 2025-32 (Internal Revenue Bulletin 2025-45)",
      "url": "https://www.irs.gov/irb/2025-45_IRB"
    },
    {
      "pinpoint": "\u00a732(c)(2)(A); \u00a732(b)(1)",
      "pre_freeze": true,
      "published": "current code",
      "quote": "such net earnings shall be determined with regard to the deduction allowed to the taxpayer by section 164(f).",
      "source": "26 U.S. Code \u00a732 (Earned income)",
      "url": "https://www.law.cornell.edu/uscode/text/26/32"
    },
    {
      "pinpoint": "Bill digest/status",
      "pre_freeze": true,
      "published": "2025-04-04",
      "quote": "repeals the earned income tax credit for taxable periods beginning on or after January 1, 2026",
      "source": "Louisiana Legislature, SB 149 (2025 Regular Session) bill record",
      "url": "https://legis.la.gov/Legis/ViewDocument.aspx?d=1404166"
    }
  ],
  "computation": "1. Federal EITC (IRC \u00a732), filing jointly with two qualifying children aged 7 and 6. The head is 25 and the spouse is 18; with qualifying children there is no minimum age. No investment income is listed, so it is treated as 0.\n   - Earned income (\u00a732(c)(2)(A)) is wages plus net self-employment earnings, reduced by the \u00a7164(f) deduction.\n   - Self-employment tax: 15,525 \u00d7 0.9235 = 14,337.34; \u00d7 15.3% = 2,193.61. Half of that is 1,096.81.\n   - Earned income = 7,468 + 15,525 \u2212 1,096.81 = 21,896.19. AGI is the same, 21,896.19.\n   - Rev. Proc. 2025-32 sets these 2026 figures for two children: earned income amount $18,290, maximum credit $7,316, joint-return phase-out threshold $31,160. (The rate is 40% under \u00a732(b), and 40% \u00d7 18,290 = 7,316.)\n   - Earned income of 21,896 is at least $18,290, and both AGI and earned income are below $31,160. So there is no phase-out and the federal EITC is $7,316.\n2. Louisiana EITC (R.S. 47:297.8(A)(2)): for tax years 2019 through 2030 the credit is 5% of the federal EITC. 5% \u00d7 7,316 = $365.80.\n3. Refundability: R.S. 47:297.8(B) treats any amount above the tax liability as an overpayment to be refunded, so the credit is refundable.\n4. Status of the law: the legislature's site lists Acts 2021, No. 453 as the last amendment. Two 2025 repeal bills, SB 149 and HB 642, stayed pending in committee and died. So the 5% refundable credit is in force for 2026.\n5. Other refundable Louisiana credits (the refundable child care credit and the school readiness credits) require child care expenses. None are listed, so they are 0.\n6. Total Louisiana refundable credits = $365.80.\n\nThe 2026 federal EITC parameters (Rev. Proc. 2025-32, Nov 2025) and the Louisiana statute were both published before the 2026-07-03 freeze.",
  "confidence": "high",
  "definition_reading": "This household is a single joint return of Louisiana residents. \"Total refundable state individual income tax credits\" covers every Louisiana income tax credit whose excess over liability is refunded. Here that is only the Louisiana EITC under R.S. 47:297.8: 5% of the federal EITC, refundable under subsection B. Refundable child care and school readiness credits are 0 because no child care expenses are listed.",
  "independent_answer": 365.8,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine calculated state refundable credits of $365.80 for this Louisiana household by evaluating refundable credit programs across all 50 states and the District of Columbia. Since the household is located in Louisiana (LA = True), only the Louisiana refundable credits were non-zero while all other states' programs returned $0. Louisiana's refundable credits consist entirely of the Louisiana Earned Income Tax Credit (LA EITC), which was computed at $365.80. This LA EITC value was derived from the federal EITC amount of $7,316, which PolicyEngine then applied Louisiana's state-level EITC formula to determine the final refundable credit amount of $365.80 for this joint-filing household with two children and approximately $22,992 in household income.
----- END ENGINE DERIVATION -----