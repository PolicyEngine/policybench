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
STATE: MT
OUTPUT: tanf (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: annual Temporary Assistance for Needy Families (TANF) benefit amount

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only tanf):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: MT
- tax year: 2026

Head:
- age: 46
- gross wages and salaries: $5,915
- bank account assets: $2,800
- employer sponsored insurance premiums: $20,644
- fsla overtime premium: $710
- has employer-sponsored insurance
- health insurance premiums excluding Medicare Part B: $564
- hourly wage: $2
- usual weekly hours worked: 55
- is disabled
- other health insurance premiums: $564
- other medical expenses: $500
- over-the-counter health expenses: $480
- roth 401k contributions desired: $681
- roth ira contributions desired: $280
- traditional 401k contributions desired: $3,859
- traditional ira contributions desired: $180

Child 1:
- age: 6
- has employer-sponsored insurance

Child 2:
- age: 5
- other medical expenses: $500

Household inputs:
- household vehicles value: $1,981

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

ENGINE REFERENCE VALUE: $6,064.96 (engine output 6,064.958984375)
MODELS: 45 gave a usable answer; 0 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 24 models (1 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Montana TANF eligibility uses countable earned income with a disregard. Head's gross wages are $5,915/year (~$493/month). Montana's TANF gross income test for a family of 3 is very low (GMI standard ~$824/month for family of 3), but the earned income disregard and net income test compare to a benefit standard of ~$588/month. After the earned income disregard ($200 + 25% of remainder), countable income (~$220/month) is below the payment standard, so the family qualifies. Monthly benefit = payment standard (~$588) minus countable income (~$220) ≈ $368/month. However, Montana's TANF calculation applies a benefit standard of 33% of poverty; for a 3-person family in 2026 the monthly payment standard is about $633. With countable earnings of ~$493 gross reduced by the disregard, benefit ≈ payment standard minus countable income. Estimated annual benefit ≈ $0 given the household's earnings exceed Montana's very low net income/benefit standards after disregards under the simulated rules. value = 0
- claude-fable-5.1: answered 0
  explanation: Montana TANF cash assistance is not modeled/awarded for this household in the benchmark; no TANF benefit computed. value = 0
- claude-haiku-4.5: answered 0
  explanation: The household's gross annual wages and salaries total $5,915, which exceeds Montana's TANF income limits for a household of 4 people (head and 2 children). Additionally, bank account assets of $2,800 exceed the typical TANF asset limit of $2,000 for a family of 4 in Montana. The household is therefore ineligible for TANF benefits. value = 0
- claude-opus-4.7: answered 0
  explanation: Montana TANF has strict income, asset, and work requirements. With head working 55 hours/week and household assets, plus need to assess countable income, Montana TANF typically requires very low income. However, gross wages are only $5,915 which is low. Montana TANF max for family of 3 is roughly $588/month but requires meeting work participation and other criteria. Given the head is disabled and earnings are minimal, but without explicit TANF application/receipt indicated and considering standard modeling assumes take-up, the household likely does not qualify due to vehicle/asset limits being met but income test against the very low Montana payment standard after earned income disregards likely results in $0. Conservatively, value = 0
- claude-opus-5: answered 0
  explanation: Montana TANF in PolicyEngine generally yields no benefit for this household given modeled eligibility rules and earnings; value = 0
- claude-sonnet-4.6: answered 0
  explanation: Montana's TANF program (FAIM/Families Achieving Independence in Montana) requires a dependent child under 18 in the household and a parent or caretaker relative. The household has two children (ages 6 and 5) and the head is age 46 and disabled. Montana TANF has an asset limit (roughly $1,000 in countable liquid assets) and an income test. The head has bank account assets of $2,800, which exceeds Montana's TANF asset limit of approximately $1,000 in countable liquid assets (vehicles up to $5,000 are excluded, so the $1,981 vehicle is excluded). Because countable liquid assets ($2,800) exceed the asset limit, the household is ineligible for TANF. value = 0
- claude-sonnet-5.5: answered 0
  explanation: Low-confidence estimate. I assumed no TANF benefit is modeled for Montana in this setup, so the amount is 0. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: Household countable resources (bank assets $2,800 plus vehicle value $1,981 = $4,781) exceed Montana's TANF resource limit, so the household is ineligible for Montana TANF cash assistance. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Montana TANF payment standard for household size 3 is $555/month. Countable monthly earnings = 0.75 x ($5,915/12 - $200) = $219.69; monthly TANF = $555 - $219.69 = $335.31; annual = $4,023.75. value = 4023.75
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household does not meet the specific state requirements for TANF support. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: Given the receipt of SSI and general program limits, no TANF benefit is modeled here. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: TANF benefit amount is 0. value = 0
- gemini-3.7-flash: answered 0
  explanation: Household income is below Montana TANF income limits and qualifies for cash assistance. value = 4824
- gemini-3.8-flash: answered 0
  explanation: Montana TANF is not modeled in PolicyEngine; value = 0
- glm-5.2: answered 0
  explanation: Montana TANF eligibility requires meeting income and asset limits. The household has gross wages of $5,915 plus overtime premium of $710, totaling $6,625 annual income. Montana's TANF payment standard for a household of 3 is approximately $603/month or $7,236/year, and the income limit is based on a percentage of the standard. However, Montana TANF also has an asset limit of $3,000 for households. The household has bank account assets of $2,800 and a vehicle valued at $1,981. Montana excludes one vehicle per adult, but the combined countable assets may exceed limits. More critically, Montana's TANF program requires that countable income be below the payment standard. With earned income of $6,625 and limited deductions, the household's countable income exceeds the TANF payment standard for a family of 3. The head is not working sufficient hours to meet work requirements and the income/assets combined make them ineligible. value = 0
- glm-5.3: answered 0
  explanation: Montana's TANF program (FAIM) is not modeled with a positive benefit for this household under PolicyEngine rules, so the modeled annual TANF amount is zero. value = 0
- gpt-5.4-mini: answered 0
  explanation: Montana TANF is not indicated as payable from the provided facts, so annual TANF is zero. value = 0
- gpt-5.4-nano: answered 0
  explanation: No TANF-qualifying circumstances or eligibility triggers are provided beyond general household facts, so TANF amount is zero. value = 0
- gpt-5.6-terra: answered 0
  explanation: Countable SSI and wage income are estimated to eliminate a Montana TANF cash payment; value = 0
- grok-4.3: answered 0
  explanation: No TANF amount calculated from listed inputs. value = 0
- minimax-m3: answered 0
  explanation: Montana TANF (Temporary Assistance for Montana Families) has strict eligibility requirements. Household with earned income of $5,915 and assets of $2,800, and given the very low gross income vs. TANF eligibility limits, may qualify, but Montana's program has time limits and work requirements. Assuming standard TANF calculation: benefit amount for family of 3 in MT with very low income would be modest but non-zero. However, given the question's parameters and standard calculation, annual TANF benefit ≈ 0 (Montana TANF benefits are very low, ~$50-$200/month, and may be reduced to 0 with earned income). value = 0
- ox-alpha: answered 0
  explanation: Montana TANF income limits are exceeded: Head's SSI (~$780/month unearned) plus countable earnings (~$201/month after disregards) far exceed the Montana payment standard (~$614/month for a family of 3), making the household ineligible. value = 0
- qwen-3.7-max: answered 0
  explanation: Head’s gross annual income of $5,915 plus FLSA overtime premium of $710 yields total earned income of $6,625. For a 3-person household in Montana in 2026, the TANF income limit is approximately $6,600–$7,200 annually (depending on exact state standards). While income may be near the limit, Head works 55 hours per week, exceeding typical TANF work participation requirements, and the household has bank assets of $2,800 (likely within the asset limit). However, with countable income potentially at or above the Montana TANF payment standard for a 3-person household, the benefit calculation yields $0. value = 0
- qwen3.8-max: answered 0
  explanation: Household income is too high for TANF eligibility in Montana under 2026 modeled rules. value = 0

STAGE 1 RESULT (frozen; sha256 751d814849a6733445487aa62a2ad7171751baa894ede3a79224d48d8ceb4ff2):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "Small differences only. If the monthly grant is truncated to whole dollars, the answer is $6,060 instead of $6,063.75. If the payment standard is computed unrounded (0.35 \u00d7 $24,860 / 12 = $725.08), it is about $6,064.75. The reference of $6,064.96 is within that range. No reasonable reading gives $0: the vehicle is excluded and the countable $2,800 is under the $3,000 limit, the head is not an SSI recipient because their resources exceed $2,000, and income is far below the GMI and benefit standards.",
  "citations": [
    {
      "pinpoint": "ARM 37.78.401(1) and (4) (vehicles)",
      "pre_freeze": true,
      "published": "2009-07-01",
      "quote": "If the total value of the filing unit's countable resources exceeds $3,000, the filing unit is ineligible for assistance. ... one vehicle regardless of its value",
      "source": "Administrative Rules of Montana 37.78.401, TANF resource limits (via Cornell LII)",
      "url": "https://www.law.cornell.edu/regulations/montana/Mont-Admin-r-37.78.401"
    },
    {
      "pinpoint": "ARM 37.78.406(2)(a)-(b)",
      "pre_freeze": true,
      "published": "2008-06-13",
      "quote": "$200 of monthly earnings for each wage earner ... 25% of the remaining earned income after the disregards in (2)(a) have been applied",
      "source": "Administrative Rules of Montana 37.78.406, TANF Cash Assistance; Income Disregards and Income Deeming (via Cornell LII)",
      "url": "https://www.law.cornell.edu/regulations/montana/Mont-Admin-r-37.78.406"
    },
    {
      "pinpoint": "ARM 37.78.420 (method of computing payment)",
      "pre_freeze": true,
      "published": "2011-01-28",
      "quote": "The household's net countable income is subtracted from the payment standard to determine the amount of the payment for the TANF case assistance unit.",
      "source": "Administrative Rules of Montana 37.78.420, TANF Assistance Standards; Methods of Computing Amount of Monthly Benefit Payment (via Cornell LII)",
      "url": "https://www.law.cornell.edu/regulations/montana/Mont-Admin-r-37.78.420"
    },
    {
      "pinpoint": "Income limits table, family size 3; resource limit",
      "pre_freeze": true,
      "published": "2023-07-01",
      "quote": "3 | $1,465 | $792 | $725 ... Countable resources must be less than $3,000.",
      "source": "Montana DPHHS, Temporary Assistance for Needy Families (TANF) program page",
      "url": "https://dphhs.mt.gov/HCSD/tanf"
    },
    {
      "pinpoint": "TANF 001, effective 07/01/25 (payment standards 35% of 2023 FPL)",
      "pre_freeze": true,
      "published": "2025-07-01",
      "quote": "TANF 001: Monthly Income Standards ... Effective: 07/01/25",
      "source": "Montana DPHHS TANF Policy Manual index (TANF 001 Monthly Income Standards)",
      "url": "https://dphhs.mt.gov/hcsd/Manuals/TANFpolicymanual"
    },
    {
      "pinpoint": "\u00a7416.1205",
      "pre_freeze": true,
      "published": "1989-01-01",
      "quote": "$2,000",
      "source": "20 CFR 416.1205 (SSI resource limit)",
      "url": "https://www.law.cornell.edu/cfr/text/20/416.1205"
    }
  ],
  "computation": "Assistance unit: the head (46, disabled) and two dependent children aged 6 and 5, so the unit size is 3. The head does not get SSI: the $2,800 bank balance is above the $2,000 SSI resource limit (20 CFR 416.1205). The head therefore stays in the TANF unit.\n\nResource test (ARM 37.78.401): one vehicle is excluded \"regardless of its value,\" so the $1,981 vehicle does not count. Countable resources are the $2,800 in the bank, which is under the $3,000 limit. Pass.\n\nIncome: gross monthly earnings are $5,915 / 12 = $492.92. The prompt says the $5,915 already includes overtime, and there is no unearned income.\n\nGross monthly income (GMI) test: TANF 001 (effective 07/01/25, still current at the freeze date) sets GMI for a household of 3 at $1,465. $492.92 is under it. Pass.\n\nEarned income disregards (ARM 37.78.406(2)):\n- Subtract $200: $492.92 \u2212 $200 = $292.92.\n- Subtract 25% of the remainder ($73.23): net countable income = $219.69.\n- No child-care disregard applies, because no child-care expenses are listed.\n\nBenefit standard test: the benefit standard is 30% of the 2023 FPL, which is $622 for 3. $219.69 is under it. Eligible.\n\nPayment (ARM 37.78.420): payment = payment standard \u2212 net countable income. The payment standard for 3 is 35% of the 2023 FPL ($24,860 \u00d7 0.35 / 12 \u2248 $725). $725 \u2212 $219.69 = $505.31 a month, or $6,063.75 a year. If the grant is truncated to whole dollars, it is $505 \u00d7 12 = $6,060.\n\n2026 parameters: Montana did not re-index the cash standards to the 2025 or 2026 FPL. The TANF 001 version effective 07/01/25, published before the freeze, keeps the payment standards based on the 2023 FPL ($725 for 3), and the manual index still lists 07/01/25 as the current version. The SNAP and other figures in that table, which use the 2025 FPL, do not affect TANF cash.\n\nWork requirements and time limits do not reduce the amount, given the take-up assumption. The result is about $6,064 a year, which matches the reference of $6,064.96 to within about $1. The difference is rounding or how the standard is computed. The consensus answer of 0 is not supported: assets are below the limit once the vehicle is excluded, and income is far below every test.",
  "confidence": "high",
  "definition_reading": "I read the output as the annual Montana TANF cash payment (FAIM / TANF Cash Assistance) for the single assistance unit made up of the head and two children, with take-up assumed. Under the prompt's rules, gross wages are $5,915 a year, and there is no child-care expense and no SSI receipt. The household meets the resource test because one vehicle is excluded, and it meets both income tests. The amount is (payment standard of $725 for 3 \u2212 net countable earnings of $219.69) \u00d7 12.",
  "independent_answer": 6063.75,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine calculated a Temporary Assistance for Needy Families (TANF) benefit of $6,064.96 for this Montana head-of-household with 2 children and annual income of approximately $5,915. The calculation determined the household's eligibility for TANF based on Montana's income limits and family composition, then applied the state's benefit formula to arrive at the annual payment amount. With a household income well below Montana's TANF income thresholds and two dependent children qualifying for assistance, the household received the computed benefit reflecting the state's maximum or near-maximum assistance level for a family of this size. This annual benefit amount of $6,064.96 represents the total TANF support PolicyEngine determined the household would receive under 2026 Montana policy rules.
----- END ENGINE DERIVATION -----