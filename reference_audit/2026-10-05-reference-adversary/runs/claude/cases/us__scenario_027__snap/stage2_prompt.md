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
STATE: CT
OUTPUT: snap (an annual dollar amount)
OUTPUT DEFINITION, as the models saw it: annual SNAP (food stamps) benefit amount

HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several outputs, and this case concerns only snap):
----- BEGIN HOUSEHOLD PROMPT -----
Estimate the requested tax and benefit outputs using only the household facts below. All listed people live together and are in one household group for tax and benefit calculations. All listed facts describe the full tax-benefit year. Treat demographic, work, student, disability, housing, health coverage, and household-composition facts as constant throughout the tax-benefit year, with no within-year income volatility or status changes. Gross wage and salary amounts are annual totals, including any overtime pay; hourly wage is a straight-time rate when listed. Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage.

Household:
- state: CT
- tax year: 2026

Head:
- age: 68
- bank account assets: $48,000
- other medical expenses: $500
- over-the-counter health expenses: $100
- Social Security disability income: $30,160
- taxable interest income: $275

Spouse:
- age: 39
- is blind
- is disabled
- over-the-counter health expenses: $50

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

ENGINE REFERENCE VALUE: $288.00
MODELS: 45 gave a usable answer; 1 matched the reference.

CONSENSUS ANSWERS (clusters of models agreeing on a value other than the reference):

Cluster 1: 0, given by 38 models (4 of them among the benchmark's top-ranked models)
- claude-fable-5: answered 0
  explanation: Household of 2 in CT (BBCE state, gross income limit 200% FPL ≈ $42,760/yr for 2, no asset test). Gross income = $30,160 SSDI + $275 interest = $30,435/yr ($2,536/mo), which passes the gross test. Both members are elderly (68) or disabled, so only the net income test applies. Net income: $2,536 gross − standard deduction (~$205) − excess medical deduction for elderly/disabled member ($500+$100 = $600/yr = $50/mo, less than $35 threshold excess... $50−$35=$15 excess allowed? Actually $600/12=$50; excess over $35 = $15 deduction) = about $2,316/mo net. With no shelter costs reported, no excess shelter deduction. Net income limit (100% FPL for 2 ≈ $1,782/mo) is exceeded, so household fails the net income test and receives no benefit. value = 0
- claude-fable-5.1: answered 0
  explanation: Elderly/disabled 2-person household: gross monthly income about 2,536 (SSDI 2,513 + interest 23); after standard deduction (209) and small excess medical deduction (~19), net income ≈ 2,308 exceeds the 100% FPL net limit of about 1,763 for 2 persons, and with no shelter costs there is no shelter deduction. Ineligible. value = 0
- claude-haiku-4.5: answered 0
  explanation: The household's combined Social Security disability income of $30,160 exceeds Connecticut's SNAP income limit for a 2-person household in 2026. SNAP eligibility requires gross monthly income below approximately 130% of the federal poverty line (around $2,900 for a 2-person household). The household's monthly income from SSDI alone is approximately $2,513, which exceeds standard SNAP limits. Additionally, with bank account assets of $48,000, the household exceeds SNAP's asset limits of $2,250 for households without elderly or disabled members, or $3,500 for households with elderly or disabled members (though the head is 68 and spouse is disabled, standard assets limits still apply in Connecticut SNAP). The household is not eligible for SNAP; value = 0
- claude-opus-4.7: answered 0
  explanation: Household has $48,000 in bank assets, which exceeds the SNAP asset limit for CT (even the elderly/disabled limit of ~$4,500 in 2026). Therefore not eligible. value = 0
- claude-opus-4.8: answered 0
  explanation: Household of 2 in CT (2026). Head age 68 and spouse disabled means household qualifies for elderly/disabled SNAP rules (no gross income test, but net income test and possible asset test apply). However, bank account assets of $48,000 far exceed the SNAP resource limit (about $4,500 for households with an elderly/disabled member). Exceeding the resource limit makes the household ineligible for SNAP, yielding no benefit. value = 0
- claude-opus-5: answered 0
  explanation: Countable monthly income of about $2,536 (Social Security $2,513 plus interest) far exceeds the SNAP net income limit for a two-person household, so no benefit. value = 0
- claude-opus-5.5: answered 0
  explanation: Monthly gross income is about $2,536. Subtracting the standard deduction and a small medical deduction leaves net income of about $2,308. This exceeds the roughly $1,763 net income limit for a household of 2, and there are no shelter costs to reduce it. value = 0
- claude-sonnet-4.6: answered 0
  explanation: For SNAP eligibility in Connecticut (2026), the household consists of a 68-year-old head and a 39-year-old blind/disabled spouse. Income includes Social Security disability income (SSDI) of $30,160 and taxable interest of $275, totaling $30,435 gross annual income ($2,536.25/month). For SNAP purposes, SSDI counts as unearned income. The household has two members, one of whom is disabled (spouse is blind and disabled, head receives SSDI). For a 2-person household with a disabled member, the net income limit is 100% of the federal poverty level (FPL). For FY2026, the 48-contiguous-states 2-person FPL monthly net income limit is approximately $1,732/month. Gross income limit (200% FPL for households with elderly/disabled) = ~$3,464/month. Gross income of $2,536.25/month passes the gross test. For net income: apply the 20% earned income deduction (no earned income here), the standard deduction for a 2-person household (~$198/month in 2026), and the medical expense deduction for elderly/disabled members. Medical expenses: head has $500 other medical + $100 OTC = $600/year; spouse has $50 OTC = $50/year; total = $650/year = $54.17/month. Medical deduction = expenses over $35 threshold = $54.17 - $35 = $19.17/month. Assets: bank account = $48,000. For households with an elderly or disabled member, the asset limit is $4,500 (2026 estimated). The household's bank assets of $48,000 exceed the $4,500 asset limit for households with elderly/disabled members. Therefore, the household is INELIGIBLE for SNAP due to excess assets. Annual SNAP benefit = $0. value = 0
- claude-sonnet-5: answered 0
  explanation: Household assets of $48,000 exceed the SNAP asset limit of $4,250 for households with an elderly/disabled member (2 people, one age 68, one disabled), making the household categorically ineligible for SNAP based on resource limits. value = 0
- deepseek-v4-flash-0731: answered 0
  explanation: The household's $48,000 countable bank assets exceed the SNAP asset limit of $4,250 for a household with an elderly/disabled member, making it ineligible. value = 0
- deepseek-v4-pro: answered 0
  explanation: Monthly gross income $2,536.25 is within 200% FPL for 2, but net income after SNAP deductions ($2,300) exceeds 100% FPL ($1,703/month), so no monthly benefit; SNAP = $0. value = 0
- deepseek-v4-pro-0813: answered 0
  explanation: Monthly gross income of about $2,536 from SSDI and interest, minus allowable deductions, still exceeds the SNAP net income limit for a two-person household, yielding no benefit. value = 0
- deepseek-v4.1-flash: answered 0
  explanation: Gross monthly income is $2,536. After standard deduction ($204) and medical deduction ($19), net monthly income is $2,313, which exceeds the 100% FPL limit for a household of 2 ($1,762.50), so SNAP benefit is 0. value = 0
- gemini-3-flash-preview: answered 0
  explanation: The household's gross monthly income of $2,536.25 passes the 200% FPL Broad-Based Categorical Eligibility threshold for Connecticut, but the benefit calculation (Max Allotment minus 30% of Net Income) results in zero because the net income (gross minus standard and medical deductions) is too high. value = 0.0
- gemini-3.1-flash-lite-preview: answered 0
  explanation: The household's assets of $48,000 exceed the SNAP eligibility resource limit for most households. value = 0
- gemini-3.1-pro-preview: answered 0
  explanation: Although the household meets categorical eligibility criteria, 30% of their net countable income exceeds the maximum SNAP benefit for a two-person household, resulting in no SNAP award. value = 0
- gemini-3.5-flash-lite: answered 0
  explanation: Household income and asset levels result in zero SNAP benefit under PolicyEngine rules. value = 0
- gemini-3.8-flash: answered 0
  explanation: Household bank assets of $48,000 exceed asset limits, and 30% of net income exceeds the maximum allotment, resulting in a SNAP benefit of 0. value = 0
- glm-5.3: answered 0
  explanation: Monthly unearned income is about $2,536 ($30,160 SSDI plus $275 interest). After the standard deduction and the small medical deduction ($650 annual expenses minus the $35/month floor), net monthly income (~$2,300) makes 30% exceed the 2-person maximum allotment (~$536), yielding a zero benefit. value = 0
- gpt-5.4-mini: answered 0
  explanation: The household has substantial Social Security disability income and $48,000 in bank assets, making it ineligible for SNAP under typical asset and income rules. value = 0
- gpt-5.4-nano: answered 0
  explanation: SNAP eligibility and amount depend on additional inputs (e.g., countable earned income, household size details, shelter costs, and other income/expenses). With only Social Security disability income and taxable interest and no shelter/rent inputs provided, this estimate is 0 under the given limited facts. value = 0
- gpt-5.5: answered 0
  explanation: Annual countable income is $30,160 Social Security disability plus $275 interest, and with no listed shelter costs the elderly/disabled household’s net income remains above the SNAP limit/benefit phaseout for a 2-person household, so no annual SNAP benefit is payable. value = 0
- gpt-5.6-luna: answered 0
  explanation: Although the household has no children, its countable monthly income from Social Security disability benefits and interest remains above the SNAP benefit-income calculation after the standard and allowable medical deductions, producing no annual allotment. value = 0
- gpt-5.6-sol: answered 0
  explanation: Annual Social Security and interest income of $30435, with no housing cost and only $650 of listed annual medical expenses, leaves SNAP net income above the applicable two-person limit. value = 0
- gpt-5.6-terra: answered 0
  explanation: The household's $48,000 in bank assets exceeds the SNAP resource limit applicable to an elderly or disabled household. value = 0
- gpt-6-luna: answered 0
  explanation: The household has no shelter costs reported; after applicable income deductions, its countable income remains too high for a positive SNAP allotment, so annual SNAP is $0; value = 0
- gpt-6-sol: answered 0
  explanation: Monthly Social Security income of about 2513 exceeds the two-person SNAP net-income limit even after the applicable standard and reported medical deductions; value = 0
- gpt-6.1-sol: answered 0
  explanation: Countable Social Security and interest income, after applicable standard and medical deductions, produces a benefit reduction exceeding the two-person SNAP maximum. value = 0
- grok-4.3: answered 0
  explanation: Household assets exceed typical SNAP limits and income may not qualify after SSDI. value = 0
- grok-4.5: answered 0
  explanation: Household bank assets of $48,000 exceed the SNAP resource limit for an elderly/disabled household (approximately $4,500), rendering the unit ineligible regardless of income. value = 0
- grok-4.6: answered 0
  explanation: Annual countable income is $30,435. After the SNAP standard deduction and a small excess medical deduction, 30 percent of net income exceeds the two-person maximum allotment, so the SNAP benefit is $0. value = 0
- grok-build-0.1: answered 0
  explanation: Net income of approximately $30,000 after standard and medical deductions far exceeds the maximum SNAP allotment for a household of 2 (around $6,420 annually), resulting in $0 benefit. value = 0
- inkling: answered 0
  explanation: The household includes elderly/disabled members, but monthly net income (~$2,317 after standard and medical deductions) exceeds 100% FPL for two (~$1,762/month). No children are present. So not eligible. value = 0
- kimi-k2.6: answered 0
  explanation: The two-person household has approximately $30,435 in annual unearned income ($30,160 Social Security disability plus $275 interest) and no listed rent or utilities. SNAP allows a standard deduction and an excess medical deduction of about $230 annually for the elderly and disabled members, but without shelter costs net income remains far above the 100-percent-FPL net income limit for a household of two, making the household ineligible. value = 0
- kimi-k3: answered 0
  explanation: Monthly income is 2536.25; after the standard deduction and small excess medical deduction it remains above the two-person SNAP net income limit, with no rent or shelter costs listed. value = 0
- minimax-m3: answered 0
  explanation: Household of 2 with both elderly/disabled. Gross annual income of $30,435 (SSDI + interest) exceeds the 200% FPL gross income limit of approximately $30,120 for a household of 2. Bank assets of $48,000 also exceed the $4,250 asset limit for elderly/disabled households. SNAP benefit is $0. value = 0
- ox-alpha: answered 0
  explanation: Monthly gross income of about $2,536 minus the standard deduction and a small elderly/disabled medical deduction leaves net income near $2,310, which fails the net-income test against the poverty guideline and makes 30% of net income exceed the two-person maximum allotment, so benefits are zero. value = 0
- qwen-3.7-max: answered 0
  explanation: The household has two members: one age 68 on SSDI and one age 39 who is disabled. Both members have countable income that exceeds SNAP limits when considering SSDI as unearned income. The head's SSDI of $30,160 and taxable interest of $275 result in total monthly unearned income of approximately $2,536, which exceeds the SNAP gross and net income limits for a 2-person household. Additionally, bank account assets of $48,000 exceed SNAP resource limits for this household composition. value = 0

STAGE 1 RESULT (frozen; sha256 9012ff4a26b4b17f9d9bebd77515b5e661d547b3ce427efa658989288d1d67bb):
----- BEGIN STAGE 1 RESULT -----
{
  "ambiguity": "A 2016 CT Office of Legislative Research report and some third-party sites describe CT categorical eligibility as also requiring net income at or below 100% FPL; I saw that report's wording only in search snippets because the legislature site failed a certificate check. If CT's BBCE really imposed such a net test, the household (net \u2248 $2,308 vs. FY2026 net limit \u2248 $1,763) would fall back to regular rules. The elderly/disabled asset limit ($4,500) would then disqualify it on its $48,000 of savings, giving $0. CT's own UPM P-5520.35 ('do not subject the unit to any income tests') and the FNS BBCE chart (all households, 200% gross, no asset limit, no net test) contradict that reading, so I treat $288 as the answer the law supports.",
  "citations": [
    {
      "pinpoint": "\u00a7273.10(e)(2)(ii)(C)",
      "pre_freeze": true,
      "published": "in force before 2025 (exact amendment date not shown)",
      "quote": "Except during an initial month, all eligible one-person and two-person households shall receive minimum monthly allotments equal to the minimum benefit. The minimum benefit is 8 percent of the maximum allotment for a household of one, rounded to the nearest whole dollar.",
      "source": "7 CFR 273.10 (Determining household eligibility and benefit levels), Code of Federal Regulations",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.10"
    },
    {
      "pinpoint": "\u00a7273.10(e)(2)(iii) lead-in",
      "pre_freeze": true,
      "published": "in force before 2025",
      "quote": "For an eligible household with three or more members which is entitled to no benefits",
      "source": "7 CFR 273.10, Code of Federal Regulations",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.10"
    },
    {
      "pinpoint": "\u00a7273.9(a)",
      "pre_freeze": true,
      "published": "in force before 2025",
      "quote": "Households which are categorically eligible as defined in \u00a7 273.2(j)(2) or 273.2(j)(4) do not have to meet either the gross or net income eligibility standards.",
      "source": "7 CFR 273.9 (Income and deductions), Code of Federal Regulations",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.9"
    },
    {
      "pinpoint": "\u00a7273.9(d)(3)",
      "pre_freeze": true,
      "published": "in force before 2025",
      "quote": "That portion of medical expenses in excess of $35 per month, excluding special diets, incurred by any household member who is elderly or disabled",
      "source": "7 CFR 273.9 (Income and deductions), Code of Federal Regulations",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.9"
    },
    {
      "pinpoint": "\u00a7273.8(a)",
      "pre_freeze": true,
      "published": "in force before 2025",
      "quote": "Households which are categorically eligible as defined in \u00a7 273.2(j)(2) or 273.2(j)(4) do not have to meet the resource limits or definitions in this section.",
      "source": "7 CFR 273.8 (Resource eligibility standards), Code of Federal Regulations",
      "url": "https://www.law.cornell.edu/cfr/text/7/273.8"
    },
    {
      "pinpoint": "P-5520.35 (Transmittal UP-11-09)",
      "pre_freeze": true,
      "published": "2011-10-01",
      "quote": "When the unit is categorically eligible, do not subject the unit to any income tests.",
      "source": "Connecticut Department of Social Services, Uniform Policy Manual",
      "url": "https://portal.ct.gov/dss/-/media/departments-and-agencies/dss/upms/upm5---treatment-of-income-income-eligibility/5520_35p.doc?rev=e912d64ac7e747afa4e64e163becd6e7"
    },
    {
      "pinpoint": "Minimum benefit; maximum allotments; standard deduction (read via search excerpt; page returned 403)",
      "pre_freeze": true,
      "published": "2025-08-13",
      "quote": "The minimum benefit for the 48 States and D.C. will increase to $24.",
      "source": "USDA Food and Nutrition Service, SNAP FY 2026 Cost-of-Living Adjustments memo",
      "url": "https://www.fns.usda.gov/snap/allotment/cola/fy26"
    },
    {
      "pinpoint": "Connecticut row (read via search result excerpt)",
      "pre_freeze": true,
      "published": "2026-06",
      "quote": "all households are eligible (Help for People in Need brochure), with no limit on assets and a 200% gross income limit",
      "source": "USDA Food and Nutrition Service, Broad-Based Categorical Eligibility States Chart",
      "url": "https://fna-bwbufwdzbabpezgc.z01.azurefd.us/sites/default/files/resource-files/BBCE-States-Chart-June2026.pdf"
    },
    {
      "pinpoint": "Income table, household size 2",
      "pre_freeze": false,
      "published": "2026-10-01",
      "quote": "This is the official guidance as of October 1, 2026.",
      "source": "Connecticut Department of Social Services, SNAP Eligibility page",
      "url": "https://portal.ct.gov/dss/snap/supplemental-nutrition-assistance-program---snap/eligibility"
    },
    {
      "pinpoint": "505 Categorical and Broad Based Categorical Eligibility (BBCE)",
      "pre_freeze": null,
      "published": "unknown",
      "quote": "All one (1) and two (2) person BBCE households are eligible for the current minimum SNAP benefit.",
      "source": "North Dakota Department of Health and Human Services, SNAP Policy Manual",
      "url": "https://www.nd.gov/dhs/policymanuals/SNAP/Content/505%20Categorical%20and%20Broad%20Based%20Categorical%20Eligibility%20(BBCE).htm?TocPath=500+Non-Financial+Eligiblity+%7C_____5"
    }
  ],
  "computation": "1) SNAP household: head (68) and spouse (39, blind/disabled) are spouses living together, so they form one 2-person household. Both members are elderly or disabled.\n2) Gross countable income: SSDI $30,160 + interest $275 = $30,435/yr = $2,536.25/mo of unearned income. There are no earned income, rent or utility costs, and none may be inferred.\n3) Categorical eligibility: CT runs broad-based categorical eligibility (BBCE) for all households through the TANF/MOE-funded 'Help for People in Need' brochure, with a 200% FPL gross income limit and no asset limit (FNS BBCE States Chart, June 2026; CT DSS lists $3,607/mo for size 2 from Oct 1, 2026). The FY2026 200% FPL limit for 2 is 2 \u00d7 $21,150 / 12 \u2248 $3,525/mo. $2,536 is below that, so the household is categorically eligible.\n   - Resource limits do not apply (7 CFR 273.8(a)), so the $48,000 bank balance does not disqualify.\n   - Gross and net income standards do not apply (7 CFR 273.9(a); CT UPM P-5520.35: 'do not subject the unit to any income tests').\n4) Net income (7 CFR 273.10(e)(1)): $2,536.25 \u2212 FY2026 standard deduction $209 (sizes 1\u20133, 48 states/DC) \u2212 excess medical deduction (7 CFR 273.9(d)(3)). Medical: $500 + $100 + $50 = $650/yr = $54.17/mo; minus $35 = $19.17. Net \u2248 $2,308.08/mo. With no shelter costs there is no shelter deduction.\n5) Allotment formula (7 CFR 273.10(e)(2)(ii)(A)): $546 (FY2026 maximum for 2) \u2212 0.3 \u00d7 $2,308 ($692) = negative, so $0 by formula.\n6) Minimum benefit (7 CFR 273.10(e)(2)(ii)(C)): 'all eligible one-person and two-person households shall receive minimum monthly allotments equal to the minimum benefit' = 8% of the 1-person maximum ($298 \u00d7 0.08 = $23.84 \u2192 $24; FNS FY2026 COLA: minimum benefit $24). The zero-benefit denial/suspension rule in 273.10(e)(2)(iii) covers only households of three or more. So the benefit is $24/mo.\n7) Annual: $24 \u00d7 12 = $288.\n- FY2027 values (Oct\u2013Dec 2026) were published in August 2026, after the 2026-07-03 freeze. Only the FY2026 COLA (memo dated Aug 13, 2025) existed before the freeze.\n- Even under FY2027, CT DSS shows a 1-person maximum of $306; 8% = $24.48, which rounds to $24, so the annual figure is unchanged.\n- The consensus $0 rests on applying an asset test or net income test that BBCE waives, or on ignoring the minimum benefit for 1\u20132 person households.",
  "confidence": "high",
  "definition_reading": "I read 'snap' as the annual SNAP allotment for the one SNAP household formed by the two spouses (head 68 on SSDI; spouse 39, blind and disabled), summed over the 12 months of 2026 and assuming take-up. The household is BBCE categorically eligible in CT (gross income under 200% FPL), so neither the asset test nor the net income test applies. Its formula benefit is $0, but as an eligible 2-person household it gets the $24/month minimum: $288/yr.",
  "independent_answer": 288,
  "law_supports": "reference"
}
----- END STAGE 1 RESULT -----

ENGINE DERIVATION OF THE REFERENCE:
----- BEGIN ENGINE DERIVATION -----
PolicyEngine computes an annual 2026 SNAP total of $288 for this Connecticut couple, the sum of twelve monthly benefits of $24. The household is eligible in every month: it has an elderly or disabled member, its monthly gross income of $2,536.25 passes the gross income test, and it is categorically eligible through Connecticut's TANF non-cash rules, with gross income at 1.44 times the $1,762.50 monthly poverty guideline from January through September and 1.41 times the $1,803.33 guideline from October through December, net income at 1.2 and 1.17 times, and $48,000 in assets passing the asset test. Monthly net income of $2,118 sets an expected contribution of $636, which exceeds the $546 maximum allotment for a two-person household, so the $24 minimum allotment applies each month.
----- END ENGINE DERIVATION -----