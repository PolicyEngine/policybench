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
STATE: NY
OUTPUT: state_refundable_credits (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: total refundable state individual income tax credits

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only state_refundable_credits):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: NY
- tax year: 2026

Head:
- age: 74
- bank account assets: $70
- home mortgage interest: $5,551
- is blind
- is disabled
- is a surviving spouse
- other medical expenses: $29
- real estate taxes: $1,634
- Social Security retirement income: $2,800
- unreimbursed employee business expenses: $122

Tax unit:
- first home mortgage balance: $82,237
- first home mortgage interest: $5,551

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

ENGINE REFERENCE VALUE: $375.00
MODELS: 46 gave a usable answer; 12 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 24 models (0 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Head is a 74-year-old surviving spouse in NY with only $2,800 Social Security income (fully exempt) and no earned income, children, dependents, or child care expenses, so no EITC, Empire State child credit, or child/dependent care credit apply. NY AGI is $0 and NY tax liability is $0; the household has no rent and homeowners with these facts do not qualify for a real property tax circuit breaker credit payment here, yielding no refundable NY credits. value = 0
- claude-haiku-4.5: answered 0
  explanation: New York State does not offer a general refundable individual income tax credit. While New York has various tax credits (such as the Empire State Earned Income Tax Credit for certain lower-income working families), this household's income sources consist only of Social Security retirement income ($2,800) with minor business expenses. Social Security income is not subject to New York State income tax, and no refundable credits apply to this household's tax situation. value = 0
- claude-opus-4.8: answered 0
  explanation: Head has only $2,800 Social Security retirement income, which is exempt from NY taxable income, resulting in no taxable income and no liability against which NY refundable credits (e.g., real property tax credit, EITC) would generate a refund; with no qualifying earned income or refundable credit conditions met, total state refundable credits = 0. value = 0
- claude-opus-5: answered 0
  explanation: NY refundable credits (e.g., real property tax credit) require qualifying gross income/rent-tax conditions; with $0 taxable NY income and no reported rent, PolicyEngine yields no refundable credit amount. value = 0
- claude-sonnet-5: answered 0
  explanation: This household's only income is $2,800 in Social Security retirement benefits, which is not taxable and produces no NY tax liability. New York's main refundable credits (Earned Income Credit, Empire State Child Credit) require earned income or qualifying children, neither of which apply here (single elderly head with no earned income, no dependents). The NY real property tax credit / circuit breaker for seniors is very small and generally phases out or is negligible given the low household size and no rent paid, and with mortgage interest itemization there is no indication of qualifying rent paid. Given no earned income, no children, and no rent, there are no refundable state credits generated, so total state refundable credits = value = 0.
- deepseek-v4-flash-0731: answered 0
  explanation: No state refundable credits apply given the zero state tax liability and no qualifying credits. value = 0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household does not meet the eligibility requirements for NY state refundable tax credits. value = 0
- gemini-3.5-flash: answered 0
  explanation: The household does not qualify for any state refundable credits such as the Empire State Child Credit or state EITC due to a lack of earned income and dependents. value = 0.0
- gemini-3.5-flash-lite: answered 0
  explanation: The head qualifies for no state refundable tax credits, resulting in $0. value = 0
- gemini-3.6-flash: answered 0
  explanation: The household does not qualify for any refundable New York state income tax credits. value = 0
- gemini-3.7-flash: answered 0
  explanation: With no earned income or qualifying dependents, the household qualifies for $0 in state refundable credits. value = 0
- gemini-3.8-flash: answered 0
  explanation: The household does not qualify for the Empire State Child Credit, NY EITC, or other state refundable credits. value = 0
- glm-5.3: answered 0
  explanation: No NY refundable credits apply (e.g., NY EITC requires earned income, which is $0). value = 0
- gpt-5.4-mini: answered 0
  explanation: No refundable New York income tax credits are triggered by the listed facts. value = 0
- gpt-5.4-nano: answered 0
  explanation: No refundable New York income tax credits (e.g., refundable portion of certain credits) are indicated by the provided facts, so total state refundable credits are 0. value = 0
- gpt-5.6-luna: answered 0
  explanation: No New York refundable income-tax credit is generated by the reported Social Security-only income and household facts; value = 0
- grok-4.3: answered 0
  explanation: No qualifying credits for NY state refundable amounts. value = 0
- grok-build-0.1: answered 0
  explanation: NY's main refundable credit is the EITC, which is a percentage of the federal EITC ($0 here). No qualifying children for other credits like Empire State Child Credit. value = 0
- inkling: answered 0
  explanation: No applicable NY refundable credits (e.g., EITC, child/dependent credits, or property tax credits that apply here) are present for this household. value = 0
- kimi-k2.6: answered 0
  explanation: The household has no listed children or qualifying dependents, no listed earned income, no listed college tuition expenses, no listed childcare expenses, and no indicators for any other NY refundable credits (e.g., EITC requires earned income; Empire State Child Credit requires qualifying child; college tuition credit requires tuition payments). Therefore, total refundable state individual income tax credits are zero. value = 0
- minimax-m3: answered 0
  explanation: No NY state refundable credits apply because there is no NY tax liability and no qualifying children or other conditions triggering credits. value = 0
- ox-alpha: answered 0
  explanation: NY refundable credits such as the NY EITC (requires federal EITC/earned income) or refundable CDCC (requires child care expenses and earnings) do not apply with $0 earned income and no dependents. value = 0
- qwen-3.7-max: answered 0
  explanation: With no NY taxable income and no listed eligibility factors for refundable credits (e.g., no earned income for EITC, no qualifying children for child credits), no NY refundable credits apply. value = 0
- qwen3.8-max: answered 0
  explanation: No New York refundable credit applies given the household's income, age, and absence of qualifying dependents or earned income. value = 0

STAGE 1 RESULT (frozen; sha256 071251d027c3f7d3ecd15bba6441b43e74016ea9d2f1bd385b1cb0dbadc37af5):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "1) Home market value isn't listed. Under the prompt's convention it is $0, so the head meets the $85,000 limit. A reader who assumed a home with an $82,237 mortgage is worth more than $85,000 would deny the credit and get $0, but the prompt says not to infer unlisted assets. 2) Qualifying property taxes are reduced by any STAR school tax relief credit allowed under \u00a7606(eee). No STAR credit is listed, and the prompt says not to infer benefit receipt, so there is no reduction. If an Enhanced STAR credit of more than about $884 were assumed, the credit would fall below $375 (50% \u00d7 (1,634 \u2212 STAR)). 3) Under the pre-2025 household-gross-income rule, the $2,800 of Social Security would count as income. Based on my recollection of the old table, the cap would then be about $341, not $375. That rule doesn't apply to tax year 2026.",
  "citations": [
    {
      "pinpoint": "\u00a7606(e)(1)(A)(ii), qualified taxpayer, taxable years beginning on or after Jan. 1, 2025, with percentage table",
      "pre_freeze": true,
      "published": "in force for taxable years beginning on or after 2025-01-01",
      "quote": "For taxable years beginning on or after January first, two thousand twenty-five, 'qualified taxpayer' means a resident individual of the state who has occupied the same residence for six months or more of the taxable year, and has qualifying real property taxes ... in excess of the following percentages of federal adjusted gross income ... $3,000 or less 3 1/2",
      "source": "New York Tax Law \u00a7606(e) (Real property tax circuit breaker credit)",
      "url": "https://www.nysenate.gov/legislation/laws/TAX/606"
    },
    {
      "pinpoint": "\u00a7606(e)(1)(E)(ii), qualifying real property taxes (2025 on)",
      "pre_freeze": true,
      "published": "in force for taxable years beginning on or after 2025-01-01",
      "quote": "'qualifying real property taxes' means all real property taxes, special ad valorem levies and special assessments, exclusive of penalties and interest, levied on the residence of a qualified taxpayer and paid during the taxable year less any school tax relief credit allowed under subsection (eee)",
      "source": "New York Tax Law \u00a7606(e) (Real property tax circuit breaker credit)",
      "url": "https://www.nysenate.gov/legislation/laws/TAX/606"
    },
    {
      "pinpoint": "Eligibility, Homeowners, and credit amount sections",
      "pre_freeze": true,
      "published": "2025-11-18",
      "quote": "If you, your spouse (if married filing jointly), or a dependent claimed is 65 or older, the credit can be as much as $375. If your credit is more than the taxes you owe, you can claim a refund.",
      "source": "NYS Department of Taxation and Finance, Real property tax credit (web guidance)",
      "url": "https://www.tax.ny.gov/pit/credits/real_property_tax_credit.htm"
    },
    {
      "pinpoint": "Eligibility list",
      "pre_freeze": true,
      "published": "2025-11-18",
      "quote": "You are entitled to this refundable credit if: your federal adjusted gross income is $18,000 or less; you occupied the same New York residence for six months or more; ... the current market value of all real property you owned ... was $85,000 or less",
      "source": "NYS Department of Taxation and Finance, Real property tax credit (web guidance)",
      "url": "https://www.tax.ny.gov/pit/credits/real_property_tax_credit.htm"
    },
    {
      "pinpoint": "\u00a786(b)(1), \u00a786(c)(1)(A)",
      "pre_freeze": true,
      "published": "current through 2026",
      "quote": "except as otherwise provided in subparagraph (B) or (C), $25,000",
      "source": "26 U.S.C. \u00a786 (Social security and tier 1 railroad retirement benefits)",
      "url": "https://www.law.cornell.edu/uscode/text/26/86"
    }
  ],
  "computation": "1) Federal AGI. The only income is $2,800 of Social Security. With no dependent, the head files as single even though they are a surviving spouse. Under IRC \u00a786, provisional income is $0 + \u00bd \u00d7 $2,800 = $1,400. That is below the $25,000 base amount, so no Social Security is taxable and federal AGI is $0. Itemized amounts (mortgage interest, property tax, medical, employee business expenses) don't change AGI.\n2) NY real property tax credit (Tax Law \u00a7606(e); Form IT-214). For tax years from 2025 on, the statute measures income by federal AGI instead of household gross income. A qualified taxpayer is a resident who lived in the same residence for 6 months or more and whose qualifying property taxes exceed a share of federal AGI: 3.5% when AGI is $3,000 or less.\n3) Eligibility. Federal AGI of $0 is under $18,000. The head is a full-year NY resident who lives in the mortgaged home, can't be claimed as a dependent, and paid $1,634 of property tax, so the home isn't fully tax-exempt. Home market value isn't listed, so the prompt's convention treats it as $0, under the $85,000 limit. The head is 74, so the cap for 65 and older applies.\n4) Amount. Excess tax = $1,634 \u2212 3.5% \u00d7 $0 = $1,634. Half of that is $817 (the 50% rate comes from a secondary summary; I couldn't read the statute's paragraph (2)). The cap for 65 and older is $375, so the credit is $375. The cap holds unless the rate were below about 23%.\n5) Refund. NY tax is $0 because NY AGI is $0 and Social Security is excluded. The credit is refundable, so the full $375 is refunded.\n6) Other NY refundable credits are all $0. The Empire State child credit needs a child. The NY EITC needs earned income. The child and dependent care credit and the college tuition credit need expenses that aren't listed. The NYC school tax credit needs NYC residence, which isn't listed. The IT-229 real property tax relief credit was discontinued from tax year 2024.\nTotal = $375.\n2026 parameters: the 2026 IT-214 form and instructions weren't published before 2026-07-03. The statute's dollar amounts ($18,000 income limit, $85,000 value limit, $375 cap, percentage table) are fixed, not indexed. A secondary summary of the FY2027 budget (signed 2026-05-28) lists no change to this credit. So the rules for tax year 2025 also apply to 2026.",
  "confidence": "high",
  "definition_reading": "I read 'total refundable state individual income tax credits' as every refundable NY personal income tax credit for the head's single tax unit. Here that is only the real property tax credit on Form IT-214, a refundable credit under Tax Law \u00a7606(e). It equals $375, the cap for a filer 65 or older with federal AGI of $1,000 or less.",
  "independent_answer": 375,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine calculated state refundable credits of $375 for this New York resident by evaluating refundable credit programs across all 50 states and the District of Columbia. Since the household is located in New York (NY = True), only the ny_refundable_credits component was non-zero at $375, while all other state programs returned $0. This $375 credit derives entirely from New York's real property tax credit, which the household qualifies for based on three factors: the household member's age of 74, real estate taxes paid of $1,633.50, and New York residency. The real property tax credit is designed to provide relief to eligible taxpayers on their property tax burden, and PolicyEngine determined the household's benefit under this program to be $375 for the 2026 tax year.
----- END ENGINE DERIVATION -----