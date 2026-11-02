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
STATE: OK
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: OK
- tax year: 2026

Head:
- age: 21
- bank account assets: $4,250
- financial assistance: $50,000
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $50
- other health insurance premiums: $50
- other medical expenses: $2,000
- over-the-counter health expenses: $150
- pre-subsidy rent: $6,614
- stock assets: $50,735
- taxable interest income: $312

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

ENGINE REFERENCE VALUE: $40.00
MODELS: 46 gave a usable answer; 2 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 44 models (5 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Oklahoma refundable credits include the sales tax relief credit ($40/exemption for filers with gross income under $20,000, or $50,000 with dependents/elderly/disabled) and the refundable EITC. The head's income is only $312 taxable interest, but the $50,000 financial assistance counts toward the gross household income test for the sales tax relief credit, exceeding the $20,000 limit for a single filer with no dependents, so no sales tax credit. With no earned income, the OK EITC (5% of federal EITC) is $0. Thus total refundable OK credits are $0. value = 0
- claude-haiku-4.5: answered 0
  explanation: Oklahoma does not have state refundable income tax credits for individual filers. The household has income from taxable interest ($312) and financial assistance that would not qualify for typical refundable credits. Oklahoma offers limited tax credits, and none are structured as refundable credits for general income. value = 0
- claude-opus-4.7: answered 0
  explanation: Oklahoma refundable credits include the Sales Tax Relief Credit and refundable EITC. The Sales Tax Relief Credit requires income below ~$20,000 (or higher with dependents/disability). Head has only $312 interest income, but also has $50,000 financial assistance and substantial assets ($50,735 stock + $4,250 bank). With no earned income, no EITC applies. The $50,000 financial assistance likely counts as income disqualifying Sales Tax Relief Credit (threshold $20,000 single). No other refundable OK credits apply. value = 0
- claude-opus-4.8: answered 0
  explanation: Oklahoma refundable credits (sales tax relief credit, EITC) require qualifying conditions. The single 21-year-old head has only $312 taxable interest income and no earned income, so no state EITC applies. The sales tax relief credit requires meeting income thresholds and is generally tied to filing; with no earned income and substantial assets/financial assistance, no refundable state credits accrue. value = 0
- claude-opus-5: answered 0
  explanation: No earned income or qualifying dependents for Oklahoma refundable credits (EITC, sales tax relief thresholds not met with take-up modeled as zero). value = 0
- claude-opus-5.5: answered 0
  explanation: There is no earned income or dependents to generate Oklahoma refundable credits. value = 0
- claude-sonnet-4.6: answered 0
  explanation: Oklahoma has a limited set of refundable state income tax credits. For tax year 2026, the primary refundable credits available in Oklahoma include the Earned Income Credit (a percentage of the federal EITC) and certain other credits. The head is a single filer, age 21, with no wages or self-employment income listed (only taxable interest income of $312 and financial assistance of $50,000, which is treated as a non-taxable scholarship/grant for tax purposes). Without earned income (wages or self-employment), the taxpayer does not qualify for the Oklahoma Earned Income Credit. No other refundable Oklahoma state credits appear applicable given the listed household facts (no childcare expenses, no child tax credit base, etc.). Therefore, total refundable state individual income tax credits = $0. value = 0
- claude-sonnet-5: answered 0
  explanation: Oklahoma does not offer a refundable state earned income credit (OK's EITC is nonrefundable) or other general refundable individual income tax credit that this household would qualify for based on the facts given (single 21-year-old with no earned income, no dependents, no disability/elderly credit qualification). No refundable state credit amount applies, so value = 0.
- claude-sonnet-5.5: answered 0
  explanation: No refundable Oklahoma credits apply at this income level. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: No Oklahoma refundable income tax credits apply given zero tax and no qualifying conditions. value = 0
- deepseek-v4-pro: answered 0
  explanation: Oklahoma's refundable EITC is 5% of the federal EITC, which is $0 because head has no earned income. No other state refundable credits apply. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Oklahoma's refundable credits are not triggered here, including its EITC based on the $0 federal EITC, so total state refundable credits are $0. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: No earned income and no federal EITC, so Oklahoma refundable credits are $0. value = 0
- gemini-3-flash-preview: answered 0
  explanation: The household's total gross income of $50,312 (including $50,000 in financial assistance) exceeds the $20,000 income limit for the Oklahoma Sales Tax Relief Credit, and no other refundable state credits apply. value = 0.0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: No state-level refundable tax credits apply for this household. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: Oklahoma's Sales Tax Relief Credit considers total income including financial assistance. Because total income exceeds the $20,000 threshold for single filers, the credit is $0. value = 0
- gemini-3.5-flash: answered 0
  explanation: The household does not qualify for any state refundable credits in Oklahoma. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: The state refundable credits are $0.00. value = 0
- gemini-3.6-flash: answered 0
  explanation: The head does not meet the eligibility requirements for the Oklahoma Sales Tax Relief Credit because they are under age 65, not disabled, and have no dependents. value = 0
- gemini-3.7-flash: answered 0
  explanation: The household does not qualify for any refundable Oklahoma state tax credits. value = 0
- gemini-3.8-flash: answered 0
  explanation: The household qualifies for no refundable Oklahoma tax credits (such as OK EITC, since federal EITC is $0). value = 0
- glm-5.2: answered 0
  explanation: Oklahoma does not offer any refundable state individual income tax credits for this household. value = 0
- glm-5.3: answered 0
  explanation: No refundable OK credits. value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable Oklahoma income tax credits are supported by the provided household facts; value = 0
- gpt-5.4-nano: answered 0
  explanation: No information is provided indicating eligibility for refundable state income tax credits, so refundable state credits are estimated at zero; value = 0
- gpt-5.5: answered 0
  explanation: No facts indicate eligibility for an Oklahoma refundable individual income tax credit; with no qualifying earned income or other listed refundable-credit basis, refundable state credits are zero. value = 0
- gpt-5.6-luna: answered 0
  explanation: No Oklahoma refundable income-tax credit is available because there is no qualifying earned income or stated qualifying dependent. value = 0
- gpt-5.6-sol: answered 0
  explanation: With no earned income, dependents, or other facts supporting an Oklahoma refundable credit, no refundable state credit applies. value = 0
- gpt-5.6-terra: answered 0
  explanation: No listed facts establish eligibility for an Oklahoma refundable income-tax credit. value = 0
- gpt-6-astra: answered 0
  explanation: There is no earned income for Oklahoma's EITC, and household income including financial assistance exceeds the sales-tax-relief income limit; value = 0
- gpt-6-luna: answered 0
  explanation: No refundable Oklahoma individual income tax credit applies to this single adult with no qualifying children or earned income. value = 0
- gpt-6-sol: answered 0
  explanation: No earnings, qualifying children, or other facts establish eligibility for an Oklahoma refundable income tax credit. value = 0
- grok-4.3: answered 0
  explanation: No Oklahoma refundable credits qualify without earned income, dependents, or specific expenses not listed. value = 0.0
- grok-4.5: answered 0
  explanation: No qualifying children or other basis for Oklahoma refundable credits with this income and composition. value = 0
- grok-4.6: answered 0
  explanation: No Oklahoma refundable credits apply: no children or earned income, and $50,000 financial assistance plus investment assets put the household over sales-tax relief income rules. value = 0
- grok-4.7: answered 0
  explanation: No Oklahoma refundable income tax credit applies. Gross household resources, including $50,000 of financial assistance, exceed sales-tax relief limits, and there is no state EITC. value = 0
- grok-build-0.1: answered 0
  explanation: No refundable state income tax credits apply to this household. value = 0
- inkling: answered 0
  explanation: No qualifying dependents, no earned income for state EITC, and income/assets do not produce a refundable Oklahoma low-income credit in this case. value = 0
- kimi-k2.6: answered 0
  explanation: The taxpayer has zero Oklahoma income tax liability and no earned income, is under age 65 with no disability or dependents indicated (unlisted statuses default to false), and does not meet the qualifying conditions for Oklahoma refundable credits such as the Sales Tax Relief Credit or earned-income-based credits. Thus total refundable state credits equal zero. value = 0
- kimi-k3: answered 0
  explanation: No Oklahoma refundable income-tax credit applies: there is no earned income for a refundable earned-income credit, and the $50000 financial assistance puts gross household income over the sales-tax-relief limit for an under-65 household with no dependents or disability. value = 0
- minimax-m3: answered 0
  explanation: Oklahoma has no state income tax, so no refundable state credits apply. value = 0
- ox-alpha: answered 0
  explanation: Oklahoma refundable credits (Earned Income Credit at 5% of federal EITC and Sales Tax Relief Credit) require earned income/eligibility the household lacks, so refundable state credits total $0. value = 0
- qwen-3.7-max: answered 0
  explanation: The household has no earned income, no qualifying children, and no other listed characteristics that would qualify for Oklahoma refundable tax credits such as the state Earned Income Tax Credit or child-related credits. value = 0.0
- qwen3.8-max: answered 0
  explanation: No refundable Oklahoma income tax credits are indicated by the household facts. value = 0

STAGE 1 RESULT (frozen; sha256 6cacc1cbc1edd6e83e396fe2c5a348f68eea0ba1504af7269af933c3ef5fb1da):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "The prompt does not say what \"financial assistance\" is. If it means public assistance payments, school grants or scholarships, or \"support money,\" Form 538-S counts it, gross household income becomes $50,312, and the credit is $0 (the consensus answer). If it were TANF, the head would be ineligible outright. Those readings conflict with the prompt's rules that benefit receipt may not be inferred and that student status defaults to false. They are also weaker than reading it as voluntary private help, which the regulation excludes as a gift. Separately, I could not open the OTC's 2026 legislative summary PDF, so I could not directly confirm that no 2026 law changed the $40 amount or the $20,000 limit.",
  "citations": [
    {
      "pinpoint": "Definition of Gross Household Income",
      "pre_freeze": true,
      "published": "2008-07-01",
      "quote": "\"Gross Household Income\" does not include gifts, or income that is considered deferred.",
      "source": "Oklahoma Administrative Code 710:50-15-96, Sales tax relief credit (Oklahoma Tax Commission)",
      "url": "https://www.law.cornell.edu/regulations/oklahoma/OAC-710-50-15-96"
    },
    {
      "pinpoint": "Income limits, tax year 2005 and subsequent years",
      "pre_freeze": true,
      "published": "2008-07-01",
      "quote": "For those taxpayers that can claim no allowable personal exemption other than themselves or their spouse, Gross Household Income cannot exceed Twenty Thousand Dollars ($20,000.00).",
      "source": "Oklahoma Administrative Code 710:50-15-96, Sales tax relief credit (Oklahoma Tax Commission)",
      "url": "https://www.law.cornell.edu/regulations/oklahoma/OAC-710-50-15-96"
    },
    {
      "pinpoint": "Credit amount",
      "pre_freeze": true,
      "published": "2008-07-01",
      "quote": "The credit is forty dollars ($40.00) multiplied by the number of allowable personal exemptions",
      "source": "Oklahoma Administrative Code 710:50-15-96, Sales tax relief credit (Oklahoma Tax Commission)",
      "url": "https://www.law.cornell.edu/regulations/oklahoma/OAC-710-50-15-96"
    },
    {
      "pinpoint": "Instructions, total gross household income",
      "pre_freeze": true,
      "published": "2025",
      "quote": "includes, but is not limited to, public assistance payments, support money (example: child support), workmen's compensation, school grants or scholarships",
      "source": "Oklahoma Tax Commission, Form 538-S Claim for Credit/Refund of Sales Tax (2025), instructions (text taken from a search-result excerpt; the PDF would not open)",
      "url": "https://oklahoma.gov/content/dam/ok/en/tax/documents/forms/individuals/current/538-S.pdf"
    },
    {
      "pinpoint": "Summary of HB 2764",
      "pre_freeze": true,
      "published": "2025",
      "quote": "Reduces the top personal income tax rate from 4.75% to 4.5% beginning in tax year 2026",
      "source": "Oklahoma State Senate press release on HB 2764 (2025 tax plan)",
      "url": "https://oksenate.gov/press-releases/oklahoma-legislature-sends-comprehensive-tax-cuts-and-modernization-plan-governor"
    },
    {
      "pinpoint": "Overview",
      "pre_freeze": true,
      "published": "2025-12-18",
      "quote": "a rebate of $40 per household member",
      "source": "Oklahoma Policy Institute, Sales Tax Relief Credit (secondary source, used only to check the 2026 amount)",
      "url": "https://okpolicy.org/sales-tax-relief-credit/"
    }
  ],
  "computation": "1) Which Oklahoma credits are refundable: the Sales Tax Relief Credit (68 O.S. \u00a7 5011, claimed on Form 538-S) and the Oklahoma earned income credit, which is 5% of the federal EITC.\n2) Earned income credit: the head has no wages or self-employment income, so the federal EITC is $0. A 21-year-old with no child also falls below the age-25 minimum for the federal childless EITC. 5% \u00d7 $0 = $0.\n3) Sales Tax Relief Credit eligibility (OAC 710:50-15-96): the head lives in Oklahoma all year. Facts left unlisted default to false, so the head did not receive TANF, is not an inmate, is not an alien with temporary status, and is not anyone else's dependent. The head is 21, has no dependents and no disability, so the lower limit applies: gross household income cannot exceed $20,000.\n4) Gross household income: the regulation defines it as \"the gross income of every type received by all persons occupying the same household,\" taxable or not, and says it \"does not include gifts, or income that is considered deferred.\" Taxable interest of $312 counts. Bank and stock balances are assets, not income. The prompt does not call the $50,000 \"financial assistance\" a public benefit, a scholarship or support owed under a legal obligation. Benefit receipt may not be inferred, and student status defaults to false. In income surveys, \"financial assistance\" normally means voluntary help from relatives or friends outside the household, which is a gift. Gifts are excluded, so gross household income is $312, well under $20,000.\n5) Credit = $40 \u00d7 allowable personal exemptions = $40 \u00d7 1 (single filer) = $40.\n6) Is the rule still in force for 2026: the $40 amount and the $20,000/$50,000 limits have applied since tax year 2005. HB 2764 (2025) changed only income tax rates and brackets for 2026. SB 72 (2025, which would raise the credit to $200) and SB 227 (which would repeal it) were bills; I found no sign either was enacted. The Oklahoma Policy Institute page, updated 2025-12-18, still describes the credit as $40 with $20,000/$50,000 limits. I could not open the OTC's 2026 legislative summary PDF, so I could not confirm directly that no 2026 law changed the credit.\nTotal Oklahoma refundable credits = $40 + $0 = $40.",
  "confidence": "medium",
  "definition_reading": "The household is one person filing one Oklahoma resident return. I read \"total refundable state individual income tax credits\" as all refundable Oklahoma credits on that return: the Sales Tax Relief Credit (Form 538-S) plus the refundable earned income credit. The EITC is $0. The Sales Tax Relief Credit is $40 for one exemption, because the $50,000 \"financial assistance\" is read as private help, which is a gift and excluded from gross household income.",
  "independent_answer": 40,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine calculated state refundable credits of $40 for this Oklahoma resident. The computation aggregates refundable credits across all 50 states and DC, with only Oklahoma contributing a non-zero amount. Oklahoma's refundable tax credit (ok_stc) was determined to be $40 based on the household's gross income of $312, a tax unit size of 1, and the head of household being age 21, which meets the age eligibility requirement (greater_age_head_spouse = 21). All other states returned zero refundable credits, resulting in the total state refundable credits value of $40.
----- END ENGINE DERIVATION -----