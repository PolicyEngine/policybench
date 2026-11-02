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
STATE: SC
OUTPUT: snap (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: annual SNAP (food stamps) benefit amount

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only snap):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: SC
- tax year: 2026

Head:
- age: 53
- gross wages and salaries: $25,665
- bank account assets: $630
- child support received: $1,200
- disability benefits: $13,044
- employer sponsored insurance premiums: $8,389
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $2,200
- is disabled
- other health insurance premiums: $2,200
- other medical expenses: $30,000
- over-the-counter health expenses: $400

Tax unit:
- first home mortgage balance: $310,000

Household inputs:
- household vehicles value: $2,359

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

ENGINE REFERENCE VALUE: $0.00
MODELS: 45 gave a usable answer; 16 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 3,576, given by 9 models (4 of them among the benchmark's top-ranked models)
- claude-fable-5.1: answered 3,576
  explanation: Disabled 1-person household: no gross income test, assets ($630 bank) under $4,500 limit. Monthly gross $3,326 less 20% earned deduction ($428), standard deduction ($209), and excess medical deduction (~$3,381 after $35) yields net income 0, so full max allotment $298/month × 12 = 3,576. value = 3576
- claude-sonnet-5.5: answered 3,576
  explanation: Disabled one-person household. Net income is about 0 after the 20% earned income deduction, standard deduction and a large medical deduction (about $32,600 a year of expenses less $35 a month). Assets are minimal. The benefit is roughly the maximum allotment of $298 a month, or $3,576 a year. value = 3576
- gpt-5.5: answered 3,576
  explanation: For a one-person disabled SNAP household, countable income is reduced by the earned-income, standard, and large allowable medical-expense deductions; the resulting net income is low enough for the maximum 2026 allotment of 298 per month, or 3576 annually; value = 3576
- gpt-5.6-sol: answered 3,576
  explanation: The disabled one-person household may deduct qualifying medical costs; the large annual medical expenses reduce SNAP net income to zero, producing the 2026 one-person maximum of $298 per month. value = 3576
- gpt-5.6-terra: answered 3,576
  explanation: As a disabled one-person SNAP household, the substantial allowable medical expenses reduce net income to zero; the resulting annual maximum contiguous-state benefit is $298 per month; value = 3576
- gpt-6-luna: answered 3,576
  explanation: The household is eligible for the one-person maximum SNAP benefit of $298 monthly; allowable medical deductions reduce net income to zero. value = 3576
- gpt-6-sol: answered 3,576
  explanation: The disabled one-person household's substantial allowable medical expenses reduce SNAP net income to zero; the 2026 maximum of 298 per month applies for 12 months; value = 3576
- inkling: answered 3,576
  explanation: Disabled 1-person household; after 20% earned-income, standard, and large out-of-pocket medical deductions, net SNAP income is $0, yielding the max FY2026 monthly allotment of $298 × 12 = $3,576. value = 3576
- kimi-k3: answered 3,576
  explanation: Countable SNAP income is 25665 wages + 13044 disability benefits + 1200 child support = 39909 per year, or 3325.75 per month. Because Head is disabled, the 20 percent earned deduction and uncapped medical deduction apply; listed medical costs are at least 34400 per year from 30000 other medical plus the two 2200 health-premium amounts, so after the 35 monthly medical disregard and the standard deduction net SNAP income is 0. Even counting the vehicle, assets are 630 + 2359 = 2989, below the 3000 resource limit, and the one-person maximum allotment is 298 per month. value = 3576

STAGE 1 RESULT (frozen; sha256 1e580d655092156ea2fde85e80e9aed370af96feec2baecafc09f3688582dd22):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "If \"is disabled\" plus \"disability benefits\" is read as qualifying SNAP disability (for example, assuming the benefits are Social Security disability), the gross test is waived and the uncapped medical deduction applies. Counting $30,000 other medical plus the $2,200 household-paid premiums gives net income of about $41/month and an allotment of $285, or $3,420/yr. Adding the $400 OTC costs if practitioner-approved gives $295/month, or $3,540/yr. Only if the $8,389 employer-sponsored insurance premiums are also treated as paid by Head does net income reach $0, giving $298 \u00d7 12 = $3,576 (the consensus). The prompt suggests those premiums are not out-of-pocket, because \"health insurance premiums excluding Medicare Part B\" totals only $2,200. Separately, Head's wages (~$2,139/month) exceed the 2026 SSDI earnings limit (~$1,690/month, not confirmed on ssa.gov), which makes Social Security disability receipt unlikely. FY2027 amounts for Oct\u2013Dec 2026 were not published before the freeze.",
  "citations": [
    {
      "pinpoint": "\u00a7 2012(j)",
      "pre_freeze": true,
      "published": "current code (in force 2026)",
      "quote": "'Elderly or disabled member' means a member of a household who\u2014 (1) is sixty years of age or older; ... (3) receives disability or blindness payments under title I, II, X, XIV, or XVI of the Social Security Act ... or receives disability retirement benefits from a governmental agency because of a disability considered permanent under section 221(i)",
      "source": "7 U.S.C. 2012 (Food and Nutrition Act of 2008, definitions)",
      "url": "https://www.law.cornell.edu/uscode/text/7/2012"
    },
    {
      "pinpoint": "Definition of 'Elderly or disabled member', paras (1)-(2)",
      "pre_freeze": true,
      "published": "current CFR (in force 2026)",
      "quote": "(2) Receives supplemental security income benefits under title XVI of the Social Security Act or disability or blindness payments under titles I, II, X, XIV, or XVI of the Social Security Act",
      "source": "7 CFR 271.2 (USDA FNS SNAP definitions)",
      "url": "https://www.law.cornell.edu/cfr/text/7/271.2"
    },
    {
      "pinpoint": "\u00a7 273.9(a) introductory text",
      "pre_freeze": true,
      "published": "current CFR (in force 2026)",
      "quote": "Households which do not contain an elderly or disabled member shall meet both the net income eligibility standards and the gross income eligibility standards for SNAP.",
      "source": "7 CFR 273.9 (Income and deductions)",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.9"
    },
    {
      "pinpoint": "\u00a7 273.9(d)(3) Excess medical deduction",
      "pre_freeze": true,
      "published": "current CFR (in force 2026)",
      "quote": "That portion of medical expenses in excess of $35 per month, excluding special diets, incurred by any household member who is elderly or disabled",
      "source": "7 CFR 273.9 (Income and deductions)",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.9"
    },
    {
      "pinpoint": "\u00a7 273.10(e)(2)(ii)(A)",
      "pre_freeze": true,
      "published": "current CFR (in force 2026)",
      "quote": "the household's monthly allotment shall be equal to the maximum SNAP allotment for the household's size reduced by 30 percent of the household's net monthly income",
      "source": "7 CFR 273.10 (Determining household eligibility and benefit levels)",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.10"
    },
    {
      "pinpoint": "Maximum allotments and deductions, 48 States and DC",
      "pre_freeze": true,
      "published": "2025 (effective 2025-10-01)",
      "quote": "The standard deduction for household sizes 1 through 3 increased to $209 a month for the 48 States and D.C.",
      "source": "USDA FNS, SNAP FY 2026 Cost-of-Living Adjustments memo (fetch returned 403; figures taken from search-result text quoting the memo)",
      "url": "https://www.usda.gov/sites/default/files/guidance-documents/fns.snap-cola-fy26memo.pdf"
    },
    {
      "pinpoint": "Gross income limits, household of 1, effective Oct 1, 2025",
      "pre_freeze": true,
      "published": "2025-10-01 (effective date per search result)",
      "quote": "1 person: $1,696 gross monthly income, $298 maximum monthly allotment",
      "source": "South Carolina DSS SNAP income guidance (fetched page did not show the FY2026 table; FY2026 figures from search snippet)",
      "url": "https://dss.sc.gov/news/update-to-snap-income-reminder/"
    }
  ],
  "computation": "1) Monthly gross income: wages 25,665/12 = 2,138.75. Disability benefits 13,044/12 = 1,087. Child support received 1,200/12 = 100; support payments are unearned income under 7 CFR 273.9(b). Total gross = 3,325.75/month.\n2) Elderly or disabled member: 7 U.S.C. 2012(j) and 7 CFR 271.2 define this by age 60+ or by receipt of specific benefits: SSI; Social Security Act Title I/II/X/XIV/XVI disability payments; permanent governmental disability retirement; VA total disability; RRA disability annuity; disability-based Medicaid or general assistance. The head is 53. The prompt lists generic \"disability benefits\" with no source and says not to infer unlisted benefit receipt, so none of the qualifying benefit receipts is established. A general \"is disabled\" status does not meet the SNAP definition. Result: no elderly or disabled member.\n3) Gross test: under 7 CFR 273.9(a), households without an elderly or disabled member must meet both the gross and net standards. The FY2026 (10/1/2025) one-person gross limit is $1,696 (130% FPL). South Carolina's BBCE removes the asset test but does not raise the 130% gross limit; this comes from secondary sources, as the official SC DSS documents could not be read. 3,325.75 > 1,696, so the household is ineligible.\n4) Net test, for completeness: the medical deduction is limited to elderly or disabled members (7 CFR 273.9(d)(3)). Net = 3,325.75 \u2212 427.75 (20% earned income) \u2212 209 (FY2026 standard deduction for 1\u20133 persons) = 2,689. This exceeds the $1,305 net limit; no shelter costs are listed.\n5) SNAP = $0/year.\nPeriod note: FY2026 values cover Jan\u2013Sep 2026. FY2027 COLA values for Oct\u2013Dec 2026 were not published before the 2026-07-03 freeze (the COLA is issued around August). This does not change $0.\nAlternative, if the head is treated as SNAP-disabled: no gross test. Medical = (30,000 + 2,200 premiums)/12 \u2212 35 = 2,648.33. Net = 3,325.75 \u2212 427.75 \u2212 209 \u2212 2,648.33 = 40.67. 30% = 12.20, rounded up to 13 (7 CFR 273.10(e)(2)(ii)(A)). Allotment = 298 \u2212 13 = 285/month = $3,420/yr. Adding $400 OTC (only if practitioner-approved): net 7.33, allotment 295, $3,540/yr. Adding the $8,389 ESI premiums as out-of-pocket as well: net 0, allotment 298, $3,576/yr (the consensus).",
  "confidence": "medium",
  "definition_reading": "Annual SNAP benefit for the single-person SC household (Head only), summed over calendar 2026 and assuming take-up. The deciding question is whether Head is an \"elderly or disabled member\" under 7 U.S.C. 2012(j) and 7 CFR 271.2. That definition requires age 60+ or receipt of specific SSA, VA, RRA, governmental-retirement or Medicaid disability benefits. The prompt lists only a generic \"disability benefits\" amount and an \"is disabled\" flag, and forbids inferring unlisted benefit receipt. So Head is not shown to be a SNAP-disabled member, the 130% gross income test applies ($3,325.75 vs $1,696), and the benefit is $0.",
  "independent_answer": 0,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine calculated a SNAP (Supplemental Nutrition Assistance Program) benefit of $0 for this single-adult household in South Carolina with an annual income of approximately $39,909. Although the model determined that the household would take up SNAP benefits if eligible (takes_up_snap_if_eligible = True), the household's income level exceeds the gross income limit for SNAP eligibility in 2026, resulting in no benefit entitlement. The repeated computation nodes in the trace reflect PolicyEngine's systematic evaluation across different benefit calculation pathways, all converging on the same zero-benefit outcome due to the income threshold constraint.
----- END ENGINE DERIVATION -----