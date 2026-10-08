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
STATE: AZ
OUTPUT: snap (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: annual SNAP (food stamps) benefit amount

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only snap):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: AZ
- tax year: 2026

Head:
- age: 58
- has indian health service coverage at interview
- is blind
- is disabled
- other medical expenses: $432
- over-the-counter health expenses: $200
- Social Security disability income: $7,560

Spouse:
- age: 55
- bank account assets: $1,045
- has indian health service coverage at interview
- is blind
- is disabled
- over-the-counter health expenses: $100

Tax unit:
- first home mortgage balance: $455,000

Household inputs:
- auto loan balance: $8,500
- auto loan interest: $255
- household vehicles value: $18,200

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

ENGINE REFERENCE VALUE: $2,376.00
MODELS: 44 gave a usable answer; 0 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 1,956, given by 3 models (3 of them among the benchmark's top-ranked models)
- claude-opus-5.5: answered 1,956
  explanation: Gross income is SSDI plus SSI, $1,511 per month, and the household has an elderly/disabled member. Deductions are the $209 standard deduction and $26 of medical costs above $35 (about $61/month less $35). Net income is $1,276, so the benefit is $546 minus 30% of $1,276, about $163 per month. This is an estimate using the FY2026 two-person maximum allotment. value = 1956
- gpt-5.6-sol: answered 1,956
  explanation: For two disabled adults, monthly countable income after the standard and excess-medical deductions produces an estimated $163 monthly SNAP benefit, or $1,956 annually; value = 1956
- gpt-6-sol: answered 1,956
  explanation: For two disabled adults, monthly SSDI and estimated SSI total 1511; after a 209 standard deduction and 26 excess-medical deduction, the estimated 546 maximum less 30% of net income yields 163 monthly; value = 1956

STAGE 1 RESULT (frozen; sha256 b0a43c189e9ed419c2115df5f7153c29fca687dd41a1ac04924c9a1d60fe6564):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "The FY2026 parameters (max $546, standard deduction $209, AZ SMD $145) run only through Sep 30, 2026. If the FY2027 COLA (published August 2026, after the freeze: max $562, standard deduction $217) and Arizona's $160 SMD effective 10/1/2026 are applied to Oct\u2013Dec, the monthly benefit for those months is $221. The calendar-2026 total is then $2,445, matching neither the reference nor the consensus. If Arizona's SMD were ignored and only the actual excess medical expense ($26) deducted, the result is $163 a month, or $1,956 (the consensus). Arizona's published policy grants the SMD to all elderly or disabled households with medical costs between $35.01 and $180, so that reading is wrong.",
  "citations": [
    {
      "pinpoint": "\u00a7273.10(e)(1)(i) and (e)(2)(ii)(A)",
      "pre_freeze": true,
      "published": "current eCFR text (in force for 2026)",
      "quote": "the household's monthly allotment shall be equal to the maximum SNAP allotment for the household's size reduced by 30 percent of the household's net monthly income",
      "source": "7 CFR 273.10 (SNAP \u2013 Determining household eligibility and benefit levels)",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.10"
    },
    {
      "pinpoint": "\u00a7273.9(d)(3) excess medical deduction",
      "pre_freeze": true,
      "published": "current eCFR text (in force for 2026)",
      "quote": "That portion of medical expenses in excess of $35 per month",
      "source": "7 CFR 273.9 (SNAP \u2013 Income and deductions)",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.9"
    },
    {
      "pinpoint": "Standard deduction and maximum allotment tables, 48 States and D.C.",
      "pre_freeze": true,
      "published": "2025-08 (effective 2025-10-01)",
      "quote": "The standard deduction for household sizes 1 through 3 increased to $209 a month for the 48 States and D.C. ... 2 people: $546",
      "source": "USDA FNS, SNAP \u2013 Fiscal Year 2026 Cost-of-Living Adjustments memo",
      "url": "https://www.usda.gov/sites/default/files/guidance-documents/fns.snap-cola-fy26memo.pdf"
    },
    {
      "pinpoint": "Standard Medical Deduction (SMD) section",
      "pre_freeze": true,
      "published": "effective 2023-08-01",
      "quote": "Standard Medical Deduction (SMD) net amount is $145 ($180 minus $35 disregard)",
      "source": "Arizona DES, Elderly Simplified Application Project (ESAP) / Nutrition Assistance Standard Medical Deduction",
      "url": "https://des.az.gov/ESAP"
    },
    {
      "pinpoint": "Medical expense deduction FAQ",
      "pre_freeze": null,
      "published": "effective 2026-10-01 (publication date not shown)",
      "quote": "A standard medical deduction of $160 ($195 - $35) is allowed when your household medical expenses are from $35.01 to $195.",
      "source": "Arizona DES, Nutrition Assistance Frequently Asked Questions",
      "url": "https://des.az.gov/services/basic-needs/food/nutrition-assistance/faqs"
    },
    {
      "pinpoint": "Monthly maximum Federal amounts, 2026",
      "pre_freeze": true,
      "published": "2025-10-24",
      "quote": "$994 for an eligible individual, $1,491 for an eligible individual with an eligible spouse",
      "source": "Social Security Administration, SSI Federal Payment Amounts for 2026",
      "url": "https://www.ssa.gov/oact/cola/SSI.html"
    },
    {
      "pinpoint": "\u00a7416.1124(c)(12)",
      "pre_freeze": true,
      "published": "current eCFR text",
      "quote": "The first $20 of any unearned income in a month other than income in the form of in-kind support and maintenance",
      "source": "20 CFR 416.1124 (SSI \u2013 Unearned income we do not count)",
      "url": "https://www.law.cornell.edu/cfr/text/20/416.1124"
    },
    {
      "pinpoint": "Standard deduction; maximum allotments (48 States and D.C.)",
      "pre_freeze": false,
      "published": "2026-08 (effective 2026-10-01)",
      "quote": "The standard deduction for household sizes 1 through 3 will increase to $217 a month for the 48 States and D.C.",
      "source": "USDA FNS, SNAP \u2013 Fiscal Year 2027 Cost-of-Living Adjustments",
      "url": "https://www.usda.gov/sites/default/files/guidance-documents/fna.snap-cola2027.pdf"
    }
  ],
  "computation": "1) SSI, which SNAP counts as income. The head and spouse are both blind and disabled, so they are an SSI eligible couple. Countable resources are $1,045 of bank assets, under the $3,000 couple limit; the home and one vehicle are excluded. The head's SSDI is $7,560/12 = $630 a month of unearned income. The $20 general exclusion (20 CFR 416.1124(c)(12)) leaves $610 countable. The 2026 couple federal benefit rate is $1,491, so SSI = $1,491 \u2212 $610 = $881 a month. No Arizona state supplement applies to a couple living independently on the stated facts.\n\n2) SNAP gross income: $630 SSDI + $881 SSI = $1,511 a month. SSI and disability benefits are unearned income under 7 CFR 273.9(b)(2). Both members are disabled because they receive SSDI or SSI, so the household is exempt from the gross income test. It is also categorically eligible because every member receives SSI.\n\n3) Standard deduction: $209 for FY2026 (Oct 2025\u2013Sep 2026), household size 1\u20133, 48 states. This is from the FNS FY2026 COLA memo.\n\n4) Medical deduction for elderly or disabled members (7 CFR 273.9(d)(3); 273.10(e)(1)(i)): $432 + $200 + $100 = $732 a year, or $61 a month. Even without the over-the-counter items, $432 alone is $36 a month, still over $35. The actual excess over $35 is $26. Arizona, however, runs a Standard Medical Deduction (SMD). For households whose medical costs fall between $35.01 and $180, it allows a net $145 ($180 \u2212 $35), effective 8/1/2023 and still in force at the freeze. Medical deduction = $145.\n\n5) Shelter: no rent, mortgage payment, property tax or utility costs are listed, so the excess shelter deduction is $0. The mortgage balance alone is not an expense.\n\n6) Net income = $1,511 \u2212 $209 \u2212 $145 = $1,157. This is below the 100% FPL net limit for 2 people.\n\n7) Allotment (7 CFR 273.10(e)(2)(ii)(A)): 30% \u00d7 $1,157 = $347.10, rounded up to $348. $546 (FY2026 maximum for 2 people) \u2212 $348 = $198 a month. Rounding the allotment down instead gives the same result.\n\n8) Annual amount, using the parameters published before the 2026-07-03 freeze: $198 \u00d7 12 = $2,376. This matches the reference.\n\nPost-freeze note: FNS published the FY2027 COLA in August 2026, after the freeze. It sets the 2-person maximum at $562 and the 1\u20133 person standard deduction at $217, effective 10/1/2026. Arizona DES now lists an SMD of $160 ($195 \u2212 $35), effective 10/01/2026; its publication date is unknown. Neither change was published before the freeze; at the freeze, the published amounts were the FY2026 $546/$209 and the AZ SMD of $145. Applying the October changes to Oct\u2013Dec: net = $1,511 \u2212 $217 \u2212 $160 = $1,134; 30% = $340.20, rounded up to $341; $562 \u2212 $341 = $221 a month. The calendar year would then be 9 \u00d7 $198 + 3 \u00d7 $221 = $2,445.\n\nThe consensus figure of $1,956 ($163 a month) uses the actual $26 excess medical deduction. It misses Arizona's standard medical deduction.",
  "confidence": "medium",
  "definition_reading": "The answer is the annual SNAP (Arizona Nutrition Assistance) allotment for the single 2-person household (head and spouse), summed over the 12 months of 2026. SSI that the household is assumed to take up (as a couple, $881 a month) counts as unearned income. The medical deduction follows Arizona's standard medical deduction rule. No shelter or utility costs are inferred.",
  "independent_answer": 2376,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine computes an annual 2026 SNAP total of $2,376 for this Arizona couple, the sum of twelve monthly allotments of $198. Each month, gross income is $1,511, all unearned: $881 of SSI ($440.50 each) plus $630 of Social Security for the head. Deductions of $354, a $209 standard deduction plus a $145 excess medical expense deduction, leave net income of $1,157. Gross income is 86% of the $1,762.50 monthly poverty guideline January through September and 84% of $1,803.33 October through December, and the household passes the income tests, the asset test with $1,045.29 in assets, and categorical eligibility, which PolicyEngine checks against its SSI and TANF non-cash eligibility. The $546 maximum allotment minus a $348 expected contribution yields $198 every month, above the $24 minimum.
----- END ENGINE DERIVATION -----