Saving `scenario_039_review.md` was blocked by the read-only sandbox. No files were changed. The completed Markdown review follows.

**Independent review: scenario_039, Virginia, federal income tax, 2026**

**1. Independent computation**

I completed this computation before reading the model explanations, engine trace, or CPS mapping.

The initial reading treats the head as a demographic widow with no dependent, and the estate income as ordinary taxable income with no established qualified business income (QBI). The verdict below examines whether those interpretations are uniquely specified.

All form references are to **2025**. Inflation amounts are for **2026**, from Rev. Proc. 2025-32. I first calculate continuous-rate tax to compare A and B exactly, then address the required Tax Table separately.

An asterisk marks a statutory provision or supplementary form whose text was **not supplied on disk and remains unverified**. I reason from my knowledge and the supplied instructions where available. No network was used.

**Filing status: Single.**

IRC §2(a)(1) requires a spouse’s death during either of the preceding two tax years **and** a dependent son, daughter, stepson, or stepdaughter whose principal abode is the household maintained by the taxpayer. The taxpayer must furnish over half its upkeep. Section 2(a)(2) additionally requires no remarriage and eligibility to file jointly for the death year.

For 2026, the qualifying death years are **2024 or 2025**. No child is listed. Ordinary widowhood alone does not qualify. “Head” is a household label, not statutory head-of-household status under §2(b).

The form entry is the **unnumbered Filing Status section on Form 1040, page 1**. [IRC §2(a)–(b)](/Users/maxghenis/reviews/policybench-cells-039-025/law/usc26_2.txt:75); [Single filing instructions](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:682).

**Income and loss.**

Section 61(a)(14) includes income from an interest in an estate or trust. It establishes inclusion unless another provision excludes the income; it does not itself establish ordinary-income character.

| Item | Amount | Code; 2025 form treatment |
|---|---:|---|
| Wages, separately stated taxable interest, dividends and capital gains | $0.00 | Unlisted inputs; Form 1040 lines 1z, 2b, 3b, 7a |
| Estate income, initially treated as ordinary Schedule E income | $25,950.00 | §61(a)(14); Schedule 1 line 5 |
| Net business loss | −$6,260.03 | §§62(a)(1), 165(c)(1)*; Schedule 1 line 3 |
| Taxable IRA distributions | $26,800.00 | §408(d)(1)*; Form 1040 line 4b |
| Taxable private pension | $2,030.00 | §§61(a)(10), 72*; Form 1040 line 5b |
| Non-Social-Security income after business loss | **$48,519.97** | Sum above |
| Social Security received | $36,105.00 | §86; Form 1040 line 6a |

The net Schedule 1 additional-income amount is **$19,689.97**, carried from Schedule 1 line 10 to Form 1040 line 8. The loss is deducted once; it is not deducted again on Form 1040 line 10. Bank assets and vehicle value are not income. [IRC §61](/Users/maxghenis/reviews/policybench-cells-039-025/law/usc26_61.txt); [Schedule 1](/Users/maxghenis/reviews/policybench-cells-039-025/law/f1040s1.txt:19); [1040 income lines](/Users/maxghenis/reviews/policybench-cells-039-025/law/f1040.txt:53).

**Social Security Benefits Worksheet.**

IRC §86(a)(2), (b), and (c) determine taxable benefits. Every numbered worksheet line is shown below.

| Worksheet line | Calculation | Amount |
|---|---|---:|
| 1 | Benefits received | $36,105.00 |
| 2 | 50% of line 1 | $18,052.50 |
| 3 | Other taxable income, including net Schedule 1 income | $48,519.97 |
| 4 | Tax-exempt interest | $0.00 |
| 5 | Lines 2 + 3 + 4 | $66,572.47 |
| 6 | Specified Schedule 1 adjustments | $0.00 |
| 7 | Line 5 − line 6 | $66,572.47 |
| 8 | Single base amount | $25,000.00 |
| 9 | Line 7 − line 8 | $41,572.47 |
| 10 | Single threshold interval | $9,000.00 |
| 11 | Line 9 − line 10 | $32,572.47 |
| 12 | Smaller of lines 9 and 10 | $9,000.00 |
| 13 | Half of line 12 | $4,500.00 |
| 14 | Smaller of lines 2 and 13 | $4,500.00 |
| 15 | 85% of line 11 | $27,686.5995 |
| 16 | Lines 14 + 15 | $32,186.5995 |
| 17 | 85% of benefits | $30,689.25 |
| 18 | Smaller of lines 16 and 17 | **$30,689.25** |

Thus the cap controls. Exceeding $34,000 alone does not invariably make 85% of all benefits taxable. [IRC §86](/Users/maxghenis/reviews/policybench-cells-039-025/law/usc26_86.txt); [worksheet for Form 1040 lines 6a–6b](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:2062).

**Total income and AGI.**

Positive included amounts before the business loss total **$85,469.25**.

| Form 1040 line | Amount |
|---|---:|
| 6b: taxable Social Security | $30,689.25 |
| 8: net additional income | $19,689.97 |
| 9: total income, including IRA and pension | **$79,209.22** |
| 10: adjustments | $0.00 |
| 11a and 11b: AGI | **$79,209.22** |

Section 62* defines AGI. [Form 1040 lines 8–11a](/Users/maxghenis/reviews/policybench-cells-039-025/law/f1040.txt:79).

**Deductions.**

The 2026 Single standard deduction under §63(c)* is **$16,100**, entered on **Form 1040 line 12e**. At 61, with blindness unlisted and false, the additional standard deduction under §63(f)* is **$0**. [Rev. Proc. 2025-32 §4.14](/Users/maxghenis/reviews/policybench-cells-039-025/law/rp-25-32.txt:779).

Section 213(a) permits uncompensated medical expenses above 7.5% of AGI; §213(d)(1)(D) includes qualifying insurance premiums. Even treating every premium entry as separate, paid after tax and uncompensated:

- Expenses: $3,589 + $4,800 + $4,800 + $200 = **$13,389.00**.
- Floor: 7.5% × $79,209.22 = **$5,940.6915**.
- Maximum medical itemized deduction: **$7,448.3085**.

That is below $16,100. Overlap or pretax payment only reduces it. A mortgage **balance** does not supply deductible interest; unlisted interest and other itemized expenses are zero. Relevant entries: **Schedule A lines 1–4***, ultimately Form 1040 line 12e. [IRC §213](/Users/maxghenis/reviews/policybench-cells-039-025/law/usc26_213.txt).

The self-employed health-insurance deduction under §162(l)* is **$0**, independently because there is no business profit. The supplied worksheet also excludes months eligible for employer-sponsored coverage. Relevant entry: **Schedule 1 line 17**, feeding Form 1040 line 10. [Insurance deduction worksheet](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:6783).

The enhanced senior deduction under §151(c)* is **$0**: age 61 does not meet the age-65 requirement. Disability does not substitute for age. Relevant entries: **Schedule 1-A Part V**, total on line 38, feeding **Form 1040 line 13b**. Tips, overtime, qualified vehicle-loan interest and charitable contributions are unlisted, so those deductions are zero. [Senior instructions](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:7878); [line 13b instructions](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:2213).

**QBI deduction: $0.**

Section 199A(c)(1) requires qualifying business items. Generic estate income does not establish that condition. With no positive QBI established, the business loss produces no current deduction. If it qualifies as a business loss for §199A, **$6,260.03 carries forward** under §199A(c)(2).

The new $400 minimum does not apply: §199A(i)(2) requires at least $1,000 of aggregate active QBI. Relevant entry: **Form 1040 line 13a**, from Form 8995 or 8995-A*. [§199A(c)](/Users/maxghenis/reviews/policybench-cells-039-025/law/usc26_199A.txt:247); [§199A(i)](/Users/maxghenis/reviews/policybench-cells-039-025/law/usc26_199A.txt:793); [2026 effective date](/Users/maxghenis/reviews/policybench-cells-039-025/law/rp-25-32.txt:288); [1040 QBI instructions](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:2242).

**Taxable income and regular tax.**

Form 1040 line 14 deductions total **$16,100**. Line 15 taxable income is:

**$79,209.22 − $16,100 = $63,109.22.**

Using §1(j)(2)(C)* and the 2026 rates verified in Rev. Proc. §4.01, Table 3:

| Rate band | Tax |
|---|---:|
| 10% × $12,400 | $1,240.00 |
| 12% × ($50,400 − $12,400) | $4,560.00 |
| 22% × ($63,109.22 − $50,400) | $2,796.0284 |
| Continuous-rate regular tax | **$8,596.0284** |

Relevant entry: **Form 1040 line 16**. [2026 Single rates](/Users/maxghenis/reviews/policybench-cells-039-025/law/rp-25-32.txt:461); [1040 tax lines](/Users/maxghenis/reviews/policybench-cells-039-025/law/f1040.txt:96).

**Nonrefundable credits actually used: $0.**

| Credit | Reason for zero | Code; form entry |
|---|---|---|
| Elderly or disabled | Age 61 fails the age test. Disability does not establish retirement on permanent and total disability or qualifying taxable disability income. Even granting eligibility, nontaxable Social Security **$5,415.75** exceeds the $5,000 initial amount. Independently, the AGI reduction is **½ × ($79,209.22 − $7,500) = $35,854.61**. | §22(b), (c), (d), (e)(3); Schedule R*, Schedule 3 line 6d |
| Child / other dependent credit | No dependent listed | §24*; Form 1040 line 19 |
| Foreign tax credit | No foreign tax listed | §§27, 901*; Schedule 3 line 1 |
| Child/dependent care | No qualifying person or care expense | §21*; Schedule 3 line 2 |
| Nonrefundable education credits | No qualified education expenses | §25A*; Schedule 3 line 3 |
| Saver’s credit | No contributions; distributions are not contributions | §25B*; Schedule 3 line 4 |
| Energy, adoption, mortgage-interest, business, prior-year AMT, vehicle/refueling and other carryforward credits | No qualifying expenditure, certificate, activity or carryforward stated | Applicable §§25C, 25D, 23, 25, 38, 53, 30D, 25E, 30C*; Schedule 3 lines 5–6 |

The absent predicates resolve these amounts without assuming a 2025 credit remains available in 2026. [IRC §22](/Users/maxghenis/reviews/policybench-cells-039-025/law/usc26_22.txt); [Schedule 3 instructions](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:8273); [disabled-credit entry](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:8358).

Schedule 3 line 8 feeds Form 1040 line 20; line 21 totals nonrefundable credits. No refundable credit is subtracted.

**AMT: $0.**

Under §§55 and 56(b)(1)(E)*, adding back the standard deduction gives AMTI **$79,209.22**, below the 2026 Single exemption **$90,100**. No other adjustments or preferences are listed.

Relevant flow: **Form 6251 line 11 → Schedule 2 line 2 → Form 1040 line 17**. [Rev. Proc. §4.10](/Users/maxghenis/reviews/policybench-cells-039-025/law/rp-25-32.txt:692); [form-flow instructions](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:8040).

**NIIT: $0.**

Section 1411(a)(1) limits NIIT to MAGI exceeding the threshold. MAGI **$79,209.22** is below the Single threshold **$200,000**. NIIT is therefore zero even if all estate income is investment income. Qualified-plan and IRA distributions are excluded from investment income under §1411(c)(5).

Relevant flow: **Form 8960* → Schedule 2 line 12 → Form 1040 line 23**. [IRC §1411](/Users/maxghenis/reviews/policybench-cells-039-025/law/usc26_1411.txt); [NIIT instructions](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:8101).

Negative self-employment earnings produce **$0 self-employment tax** and **$0 half-tax deduction**, under §§1401–1402 and 164(f)*; Schedule 2 line 4 and Schedule 1 line 15. Age 61 also excludes the ordinary under-59½ IRA additional tax under §72(t)*.

The continuous-rate output is therefore **$8,596.0284**, or **$8,596.03**. With the prompt-rounded $6,260 loss, it is $8,596.035, or $8,596.04.

**2. Exact reconstruction of B**

The single changed decision is **Single → qualifying surviving spouse (QSS)**. It changes the standard deduction and tax brackets together.

It correctly leaves Social Security unchanged. Section 86(c) reserves $32,000/$44,000 thresholds for an actual **joint return**. QSS uses **$25,000/$34,000**, despite receiving joint rates and the joint standard deduction. Worksheet lines 8 and 10 expressly confirm this. [Social Security status thresholds](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:2085).

| Component | A: Single | B: QSS |
|---|---:|---:|
| Taxable Social Security | $30,689.25 | $30,689.25 |
| AGI | $79,209.22 | $79,209.22 |
| Standard deduction | $16,100.00 | $32,200.00 |
| Taxable income | $63,109.22 | $47,009.22 |
| Continuous-rate tax | **$8,596.0284** | **$5,145.1064** |
| Nonrefundable credits, AMT, NIIT | $0.00 | $0.00 |

B is exactly:

**$2,480 + 12% × ($47,009.22 − $24,800) = $5,145.1064.**

The difference is **$3,450.9220**. [2026 QSS rates](/Users/maxghenis/reviews/policybench-cells-039-025/law/rp-25-32.txt:420); [standard deduction](/Users/maxghenis/reviews/policybench-cells-039-025/law/rp-25-32.txt:787).

All six B models explicitly use surviving-spouse status: gpt-5.5, claude-sonnet-5.5, claude-fable-5.1, gpt-6-astra, claude-opus-5.5 and gpt-6.1-sol. Claude-sonnet-5.5 writes, “Filing status is surviving spouse, so the joint-rate standard deduction of $32,200 applies.” Fable and Opus expressly retain $25,000/$34,000 Social Security thresholds. Their $79,209.25 AGI uses the rounded prompt loss. [B explanations](/Users/maxghenis/reviews/policybench-cells-039-025/model_answers.md:68).

The engine requires a surviving-spouse head, **child dependents greater than zero**, and no marriage. Its trace records the flag true, children zero, eligibility false and Single status. [Eligibility rule](/Users/maxghenis/PolicyEngine/_pr_worktrees/pe-us-pb-cells-1010/policyengine_us/variables/household/demographic/tax_unit/surviving_spouse_eligible.py:14); [status selector](/Users/maxghenis/PolicyEngine/_pr_worktrees/pe-us-pb-cells-1010/policyengine_us/variables/household/demographic/tax_unit/filing_status.py:26); [trace](/Users/maxghenis/reviews/policybench-cells-039-025/main-75cdd801/scenario_039_trace_full.txt:159).

**3. Verdict: Scenario ambiguous**

**A is the correct continuous-rate calculation for an ordinary widow with no qualifying child receiving ordinary, non-QBI estate income. B is correct conditional QSS arithmetic. The literal household does not establish QSS eligibility, but the prompt also does not uniquely specify the estate-income definition needed to score A as the sole answer. I would exclude this output.**

**Strongest case for B.** “Surviving spouse” is the exact statutory term in §2(a). In a tax question, a careful reader can treat the affirmative statement as supplied eligibility, encompassing subsidiary conditions. The prompt never explains that the flag means only demographic widowhood.

**Why that does not establish B under the literal facts.** Section 2(a) requires a qualifying child. The one-person roster and prohibition on inferring household composition supply no child. Treating the label as statutory eligibility conflicts with that roster or implicitly supplies omitted conditions, including unresolved dependent-credit facts. B is therefore conditional arithmetic, not a demonstrated complete lawful return for this household. No rule awards QSS rates to every widow. [IRC §2(a)](/Users/maxghenis/reviews/policybench-cells-039-025/law/usc26_2.txt:79); [IRS eligibility conditions](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:785).

**Could the spouse have died in 2026?** That would contradict demographic widowhood being constant throughout the year and the prohibition on within-year status changes. It is also an unlisted event. Independently, §2(a)(1)(A) excludes current-year deaths from QSS.

Death-year joint filing can be available under §6013*, without a child. But that counterfactual uses joint Social Security thresholds and gives **$4,484.78834**, not B. [Death-year joint filing](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:630); [current-year death is not QSS](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:840).

**Could an unlisted child exist?** Temporary absence can preserve an existing child’s residence; it cannot create the missing child. The prompt prohibits inferring household composition. Only the technical interpretation of the affirmative status label could implicitly certify that condition. [Temporary-absence instructions](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:780).

The background supports demographic widowhood: the local CPS builder sets `is_surviving_spouse` from `person.A_MARITL == 4`, marital status widowed. This definition was not shown to models. The local clone may be behind current upstream; no network verification was performed. [CPS mapping](/Users/maxghenis/PolicyEngine/policyengine-us-data/policyengine_us_data/datasets/cps/cps.py:447).

**Strongest case for A.** The closed-world roster supports Single and no dependent credits. The zero/false defaults support declining unsupported preferential-income and QBI treatment. Section 61(a)(14) supports estate-income inclusion. If “estate income” means residual ordinary Schedule E income, A follows exactly.

**Why I reject unique scoring.** The engine defines that input specifically as **Schedule E Part III income carried to Schedule 1 line 5, covering K-1 boxes 5–8**, and explicitly assigns estate interest, dividends and capital gains to separate inputs. The prompt says only “estate income.” [Engine definition](/Users/maxghenis/PolicyEngine/_pr_worktrees/pe-us-pb-cells-1010/policyengine_us/variables/household/income/person/estate/estate_income.py:9).

Estate is a source, not necessarily an ordinary-income character. Section 662(b)* generally preserves distributed income’s character. The supplied instructions expressly acknowledge capital gains from estates and trusts. [1040 instructions](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:2131).

Holding Single status constant, two defensible definitions produce:

| Meaning of “estate income” | AGI | Taxable income | Continuous-rate tax |
|---|---:|---:|---:|
| Residual ordinary Schedule E income, no estate QBI established | $79,209.22 | $63,109.22 | **$8,596.0284** |
| Aggregate estate income consisting of qualified dividends or distributable standard long-term capital gain | $79,209.22 | $63,109.22 | **$6,259.9894** |

The second reading reclassifies the **existing $25,950**; it does not add income. The strongest objection is that the defaults might set preferential subamounts to zero. That reading is defensible, but it depends on an unstated schema making “estate income” a mutually exclusive residual category. The missing definition resolves the disagreement, and PolicyBench’s exclusion rule expressly covers missing definitions.

The principal exclusion ground is therefore **estate-income character and category scope**. The surviving-spouse label is an additional wording defect, but weaker grounds for treating B as an established lawful household liability.

**Confidence: 75% in exclusion; above 99% in the arithmetic and Single status for an ordinary widow with no qualifying child.** I would change the exclusion verdict if model-visible documentation or the certified record established residual ordinary Schedule E income, excluding preferential/exempt items and with no established estate QBI. Defining the spouse flag as demographic widowhood or supplying filing status would settle that wording issue. The Tax Table issue below would remain.

**4. Other defects and checks**

**Estate character independently changes the answer.**

For $25,950 of qualified dividends or distributable standard long-term gain, the 2026 Single zero-rate ceiling is **$49,450**:

- Ordinary taxable income: **$37,159.22**.
- Ordinary continuous-rate tax: **$4,211.1064**.
- Preferential income at 0%: **$12,290.78**.
- Preferential income at 15%: **$13,659.22**, producing **$2,048.883**.
- Total: **$6,259.9894**.

Relevant authority: §§1(h), 1(j)(5)*, Rev. Proc. §4.03; **Qualified Dividends and Capital Gain Tax Worksheet lines 1–18 and 22–25**. [2026 thresholds](/Users/maxghenis/reviews/policybench-cells-039-025/law/rp-25-32.txt:538); [worksheet](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:2455).

If the amount were distributed tax-exempt interest under §§103, 662(b)*, §86(b)(2)(B) adds it back to provisional income. Taxable Social Security remains **$30,689.25**, but AGI becomes **$53,259.22**, taxable income **$37,159.22**, and continuous-rate tax **$4,211.1064**.

These are conditional possibilities, not evidence of actual estate holdings. The word “income” does not justify excluding the amount as a principal inheritance under §102*.

**Estate income can be QBI, but is not automatically QBI.**

Section 199A(c)(3) requires qualifying business connection and excludes capital gains, dividends and nonbusiness interest. Section 199A(f)(1)(B) contemplates trusts and estates.

If all $25,950 were eligible business income, aggregate QBI would be **$19,689.97**, its deduction **$3,937.994**, taxable income **$59,171.226**, and Single continuous-rate tax **$7,729.66972**. Qualification is not established here. [§199A(c)(3)](/Users/maxghenis/reviews/policybench-cells-039-025/law/usc26_199A.txt:267); [estate provision](/Users/maxghenis/reviews/policybench-cells-039-025/law/usc26_199A.txt:473).

Commit fb9fa56871, #10027, correctly stopped automatically treating unspecified estate income as QBI. That correction is justified for the engine’s variable definition; it does not prove every estate receipt is ordinary and nonbusiness. [Qualification definition](/Users/maxghenis/PolicyEngine/_pr_worktrees/pe-us-pb-cells-1010/policyengine_us/variables/household/income/person/estate/estate_income_would_be_qualified.py:8).

**The loss, Social Security, disabled credit, deductions, AMT and NIIT do not explain B.**

The engine subtracts the loss from positive included income; the return nets it through Schedule 1. Both give **$79,209.22** AGI. No fact establishes a loss disallowance under §§465, 469 or 461(l)*. [Trace totals](/Users/maxghenis/reviews/policybench-cells-039-025/main-75cdd801/key_variables.txt:9).

The engine’s medical aggregation differs from the most generous prompt reading. Nevertheless, even adding its entire **$3,793.91** itemized-deduction total to the maximum medical deduction gives **$11,242.2185**, below $16,100. Premium treatment cannot change this output. [Medical trace](/Users/maxghenis/reviews/policybench-cells-039-025/main-75cdd801/scenario_039_trace_full.txt:4578); [deduction totals](/Users/maxghenis/reviews/policybench-cells-039-025/main-75cdd801/key_variables.txt:20).

**Independent exact-dollar defect: mandatory Tax Table.**

The supplied 2025 line 16 instructions say taxable income below $100,000 **must use the Tax Table**. A and B instead apply continuous rates to exact taxable income. IRC §§3–4* govern the tables, but their texts are absent. [Mandatory instruction](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:2384).

Applying the existing $50-band midpoint method to 2026 rates gives:

| Status | Taxable-income band | Midpoint | Midpoint rate tax | Projected table entry |
|---|---|---:|---:|---:|
| Single | $63,100–$63,150 | $63,125 | $8,599.50 | **$8,600** |
| QSS | $47,000–$47,050 | $47,025 | $5,147.00 | **$5,147** |

These are **projected entries**, not published 2026 amounts. The 2025 table demonstrates the band methodology. They remain unchanged using the rounded prompt loss. [Analogous 2025 band](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:5334); [rounding instructions](/Users/maxghenis/reviews/policybench-cells-039-025/law/i1040gi.txt:1319).

The projected Single result exceeds A by **$3.9716**, outside the $1 tolerance. Thus A is an exact continuous-rate reference, not a verified exact Form 1040 liability. This is an independent defect; the missing estate-income definition remains the basis for the **Scenario ambiguous** verdict.