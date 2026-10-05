# Medicare Part B premium in medical expenses, October 5, 2026

This directory audits the Medicare Part B premium that PolicyBench's US references count as a medical expense. It proposes one exclusion, scenario_114's Virginia income tax, and drafts a fallback record for scenario_114's federal income tax. It changes no reference. Adopting the record changes published scores, so it waits for Max's ruling, alongside the state income tax withholding proposal in PolicyEngine/policybench#191 (decision d963), so that one release can carry both.

## The mechanism

These files hold for policyengine-us 2.15.17, the version that built the published references, as installed in the reference venv (`results/local/adds202609/triage/.venv-pe21517`). The conventions module `latest_final` (`../2026-09-28/fixes/`) touches none of them.

- `medical_expense_health_insurance_premiums` (`variables/household/expense/health/`) returns `health_insurance_premiums` when that input is nonzero. Otherwise it returns `health_insurance_premiums_without_medicare_part_b + medicare_part_b_premium * medicare_enrolled`. `health_insurance_premiums` has no formula, and no household sets it.
- `medicare_enrolled` adds `takes_up_medicare_if_eligible`, whose default is true, for everyone `is_medicare_eligible` covers. That variable covers age 65 and over, or Social Security disability benefits with at least 24 months of `months_receiving_social_security_disability`. So the engine treats every eligible person as enrolled.
- `medicare_part_b_premium` is `gross_medicare_part_b_premium` less `msp_part_b_premium_coverage` (Medicare Savings Program), floored at 0.
  - The gross premium is `base_part_b_premium` plus an income-related amount. The base premium is the CMS standard premium times 12: $202.90 × 12 = $2,434.80 for 2026.
  - The income-related amount reads `medicare_irmaa_magi_two_years_prior`. Its formula computes AGI plus tax-exempt interest for 2024. No household sets any 2024 income, so it is 0 and no income-related amount applies.
- These variables consume the premium through `medical_expense_health_insurance_premiums`:
  - `itemized_medical_expenses`. It feeds the federal medical expense deduction (`medical_expense_deduction`, 26 U.S.C. 213(a): expenses above 7.5% of AGI) and the state deductions built on it. Examples are Virginia's itemized deductions (which start from the federal itemized deductions), Alabama's, New Jersey's, Kansas's, New York's and Arizona's.
  - `snap_allowable_medical_expenses`, the SNAP excess medical deduction for elderly or disabled members.
  - `medicaid_medically_needy_medical_expenses`.
  - `oh_insured_unreimbursed_medical_care_expense_amount`, which counts premiums for Medicare-eligible people only.
  - `mt_medical_expense_deduction_indiv`, `hud_medical_expenses` and `pa_ccw_medical_expenses`.
- `medicare_part_b_premium` also enters the SPM unit's premiums and Washington's senior property tax exemption income; no output reads either. Enrollment also gates:
  - the Part A premium and Part D income-related surcharge (SPM only);
  - MSP coverage;
  - `medicare_cost`, the impact weight of the Medicare eligibility outputs;
  - the ACA "at interview" coverage list and CHIP's disqualifying-coverage list.

  The ACA premium tax credit treats Medicare eligibility as disqualifying (`ineligible_coverage` lists `is_medicare_eligible`), so enrollment, which it also reads through the "at interview" list, adds nothing. No output reads the credit: it is not in the federal refundable-credit output.

## The prompts

No PolicyBench household sets `medicare_enrolled`, `takes_up_medicare_if_eligible`, `medicare_part_b_premium` or `health_insurance_premiums`, so no prompt states Medicare enrollment or a Part B premium. `policybench/scenarios.py` would also hide the first two: `medicare_enrolled` is in `EXCLUDED_INPUT_VARIABLES`, and `takes_up_` is an excluded prefix. The prompt's rules (`policybench/prompts.py`, `TASK_PREFACE`, unchanged since before the June run) say:

- "Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false."
- "Assume tax filing and program take-up when required."
- "Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage."

The take-up sentence is the strongest case for the frozen reading: a reader may take a 69-year-old with Social Security retirement income to be enrolled in Part B and paying the standard premium. Three things point the other way:

- The benchmark sets take-up only for the programs its household data list. `DEFAULT_TAKEUP_INPUTS` covers Medicaid, SSI, the ACA credit, the DC property tax credit, the EITC, SNAP and tax filing, not Medicare; the engine's own default supplies Medicare enrollment.
- The Medicare request asks only whether a person is eligible.
- The more specific rules treat unlisted numbers as 0 and forbid inferring expenses or health coverage.

So a careful reader could take the facts either way, which is the case `reference_depends_on_unlisted_input` covers. The drafted records state both sides.

Sixty-one people in 53 households carry `health_insurance_premiums_without_medicare_part_b`, which the prompt labels "health insurance premiums excluding Medicare Part B". That line states the person's other premiums; it states no Part B amount. Ten of the 30 households charged the premium carry it, always on a charged person (12 of the 35). The label can itself suggest Medicare coverage. In scenario_073, Inkling answered that the head is Medicare-eligible partly because of "the presence of Medicare Part B premium exclusions in the health premiums". No output in those 10 households turns on the premium (below).

scenario_114's prompt has no premium or coverage line. It lists a single head, age 69, with Social Security retirement income, $10,000 of other medical expenses and $2,000 of over-the-counter health expenses. The engine leaves over-the-counter purchases out of itemized medical expenses.

## Method

1. **Sweep.** `scripts/sweep_part_b.py` rebuilds every household with `Scenario.to_pe_household` and computes every output and impact weight on policyengine-us 2.15.17 with `latest_final`, the system that built the references. Its baseline reproduces all 1,928 scored references. It then reruns every household under four readings:
   - `no_part_b`: each person's `medicare_part_b_premium` is 0 (the prompt's unlisted-number rule; enrollment unchanged);
   - `not_enrolled`: each person's `takes_up_medicare_if_eligible` is false, which removes every channel that reads enrollment (the rule against inferring health coverage);
   - `not_enrolled_direct`: each person's `medicare_enrolled` is false, a differential check on `not_enrolled`; the two agree on every output;
   - `irmaa_from_2026_income`: the income-related amount read on the household's 2026 MAGI instead of the unset 2024 MAGI, a check on the premium's size.

   For each household with a Medicare-eligible person it records each person's Medicare variables and a propagation trace. The trace lists every engine variable, at every 2026 period the simulation computed, whose value differs between the reference and the `no_part_b` or `not_enrolled` simulation. Households where an output moves also run on a grid: the Part B readings crossed with the four readings of the state income tax in SALT from #191 (withholding estimate, liability at a fixed point, none paid, none paid without the local sales tax estimate). Outputs: `verification/sweep_part_b.csv` (every output and impact weight under every reading), `verification/sweep_part_b_summary.json`, `verification/sweep_part_b_households.json` and `verification/sweep_part_b.log`.
2. **Explain.** `scripts/explain_households.py` writes `verification/part_b_households.csv`. Each of the 33 Medicare households gets a row with the premium, the federal itemization election and medical deduction with and without it, its federal, state and SNAP outputs, and the state variables its trace shows moving.
3. **Propose.** `scripts/propose_exclusions.py` writes `proposed_exclusions.json`. It holds a `reference_depends_on_unlisted_input` record, in the format of the frozen run's `reference_exclusions.json`, for every scored output that `no_part_b` moves by more than the $1 exact-match tolerance. An output #191 already proposes to exclude gets a standalone record under `conditional_on_salt_decision` instead, to install only if #191's record is not adopted. The script also writes `verification/model_answers.csv`, which tags every model's answer on the moved outputs with the readings it lands within $1 of. It reads #191's records from `verification/inputs/pr191_proposed_exclusions.json`, a copy of #191's `reference_audit/2026-10-05/proposed_exclusions.json` at head 8af912a0 that the script checks against its sha256, so this directory does not depend on #191's branch.
4. **Impact.** `scripts/leaderboard_impact.py` copies the frozen run to scratch directories and never writes the snapshot. It scores each copy with `python -m policybench.cli analyze`, the command the freeze runs. The unchanged copy reproduces every compared value of the published payload. It then scores three cases:
   - this audit's two records alone, as if #191 is not adopted;
   - #191's three records alone, which reproduces #191's figures exactly;
   - #191's three plus this audit's Virginia record.

   Each case also recomputes the legacy household impact summary, `impact_summary_by_model.csv`. The freeze writes it beside the analyze output with `scripts/freeze_snapshot.household_impact_summary_by_model`, and the snapshot manifest pins it. The unchanged copy reproduces the frozen file. Outputs: `verification/leaderboard_impact.json`, `leaderboard_impact_models.csv`, `leaderboard_impact_marginal.csv` and `leaderboard_impact.log`.
5. **Verify.** Four independent reviewers checked the work in a Claude Code workflow on 2026-10-05, each in its own scratch directory:
   - **Mechanism.** One read the engine source, built a static graph of every reader of the premium, recomputed scenario_114 to the cent from engine intermediates, and reran all 100 households.
   - **Differential.** One reran the no-premium sweep two other ways: a parameter reform setting the 2026 base premium to 0, and a structural reform cutting `medical_expense_health_insurance_premiums` to its non-Medicare branch. Both were bit-identical to `no_part_b` on all 1,984 outputs.
   - **Prompts and answers.** One rendered all 100 prompts, matched them to the frozen payload, read the matching models' explanations, and judged the record against the exclusion rule.
   - **Completeness.** One looked for missed channels and script bugs, validated the records against the loader, and checked every quoted number.

   Their reports are in `verification/independent_reviews.json`; their scratch paths are not kept. The reviewers raised three should-fix points, all fixed here: the records now state the take-up argument and its answer, the ACA sentence now names both tests, and the stale-weight finding below is narrowed. An adversarial review on a Subfleet review lane is in `verification/reviews/`.

## What moves

- **Who is charged.** 39 people in 33 households are Medicare-eligible, all of them by age. The engine charges the premium to 35 people in 30 households. The Medicare Savings Program pays it for the other 4 people, in scenario_001, scenario_043 and scenario_118.
- **What moves.** Under `no_part_b`, `not_enrolled` and `not_enrolled_direct`, exactly two outputs move by more than $1, both in scenario_114, and both are scored.
- **What does not.** No SNAP or eligibility output in any Medicare household changes by any amount under any reading. `irmaa_from_2026_income` moves no output.

| Output | Reference | No Part B premium | Status |
|---|---:|---:|---|
| scenario_114 federal income tax before refundable credits | 10,729.61 | 11,265.27 | scored; #191 proposes to exclude it for the withholding estimate |
| scenario_114 Virginia income tax before refundable credits | 3,514.15 | 3,654.15 | scored; proposed here |

The household itemizes. Its federal medical expense deduction is $12,434.80 of expenses less 7.5% of $106,572.56 AGI: $4,441.86 with the premium and $2,007.06 without it. The $2,434.80 difference is taxed at 22% federally ($535.66). Virginia's itemized deductions start from the federal ones, so it is also taxed at Virginia's 5.75% ($140.00). Virginia follows the federal election (`va_deductions` reads `tax_unit_itemizes`).

### Why the other 29 households do not move

From `verification/part_b_households.csv`:

- **Below the floor.** In 7 households (000, 022, 033, 042, 055, 120, 122), medical expenses stay below 7.5% of AGI with or without the premium. 022 and 120 itemize, but their medical deduction is $0 either way.
- **Standard deduction.** In 21 households (002, 013, 021, 027, 031, 040, 044, 048, 059, 060, 062, 071, 085, 092, 095, 098, 104, 107, 108, 111 and 115), the deduction moves but the household takes the federal standard deduction under both readings.
- **Itemizes only with the premium.** scenario_072 itemizes with the premium and takes the standard deduction without it. Its federal income tax is $0 either way.
- **State variables.** State variables move in 13 households, all but one of them tax variables; 085's is Pennsylvania's child care medical expense. Every state output stays the same:
  - $0 in AZ (013, 040), MO (021), CA (031), KS (044), OH (048, 107), NY (071, 104), AL (092) and NJ (095). In NJ, `nj_main_income_tax` moves by $26.35.
  - $4.68 in AL (115), which takes Alabama's standard deduction either way.
- **SNAP.** SNAP's excess medical deduction moves in every household charged the premium. In 27 of them SNAP is $0 under both readings. In 013, 027 and 108, the expected contribution exceeds the maximum allotment under both, so SNAP pays the $24 monthly minimum either way.
- **Medicaid.** No Medicaid eligibility output turns on the premium. In particular, scenario_031's Medicaid reference (eligible) is the same under every reading (see "Related findings").

### scenario_114 under both unlisted inputs

#191 shows that the federal SALT deduction's state income tax part is also an unlisted input. The two inputs interact through the itemization election:

| Part B premium | SALT state income tax | Federal | Virginia | Itemizes |
|---|---|---:|---:|---|
| modeled | withholding estimate (reference) | 10,729.61 | 3,514.15 | yes |
| modeled | liability | 11,137.31 | 3,514.15 | yes |
| modeled | none paid | 11,758.09 | 3,514.15 | yes |
| modeled | none paid, no local sales tax | 11,783.48 | 3,514.15 | yes |
| none | withholding estimate | 11,265.27 | 3,654.15 | yes |
| none | liability | 11,642.16 | 3,654.15 | yes |
| none | none paid | 11,969.80 | 4,127.67 | no |
| none | none paid, no local sales tax | 11,969.80 | 4,127.67 | no |

`not_enrolled` gives the same values as "none" in every row.

No model answered within $1 of either frozen reference. Model answers land on the other readings (`verification/model_answers.csv`):

- **Virginia.** GPT-6 Astra ($3,654.16) and GPT-6.1 Sol ($3,654.66) are within $1 of the value without the premium.
- **Federal, liability.** GPT-6.1 Sol ($11,642.09) and GPT-6 Astra ($11,642.20) are within $1 of the value without the premium under the liability.
- **Federal, literal.** Kimi K3 ($11,969.85) and GPT-5.6 Sol ($11,970.00) are within $1 of the literal reading: no premium and no state income tax paid.

## Proposed records

- **scenario_114 Virginia income tax.** One record in `proposed_exclusions.json` (`exclusions`): frozen $3,514.15, alternative $3,654.15. Its note gives the values under #191's readings.
- **scenario_114 federal income tax.** #191 proposes to exclude this output for the withholding estimate, and the loader refuses two records for one output. #191's record already quotes the values without the premium ($11,265.27, $11,642.16 and $11,969.80).
  - If d963 adopts #191's record, a release adds the Part B input to that record's `unlisted_input` text; the exact words are in `proposed_exclusions.json`.
  - If #191's record is not adopted, the output still rests on the Part B premium. `conditional_on_salt_decision` holds a standalone record for it: frozen $10,729.61, alternative $11,265.27.

## Leaderboard impact

From `verification/leaderboard_impact.json`. Scored outputs per model are 1,928 today.

| Case | Records added | Scored outputs | Exact-rate change, all models | GPT-6 Sol exact | Always-zero exact |
|---|---:|---:|---|---:|---:|
| published | 0 | 1,928 | | 95.00% | 69.98% |
| this audit alone (if #191 is not adopted) | 2 | 1,926 | +0.18 to +0.26 points | 95.27% | 70.14% |
| #191 alone | 3 | 1,925 | +0.42 to +0.61 points | 95.61% | 70.39% |
| #191 and the Virginia record | 4 | 1,924 | +0.47 to +0.69 points | 95.69% | 70.44% |

- **This audit alone.** No exact or bounded-score rank changes. One within-1% pair swaps: Claude Opus 4.8 and MiniMax M3 (#39/#40). Exact match rises from 61.6% to 62.4% for federal income tax and from 64.3% to 65.1% for state income tax.
- **#191 and the Virginia record.** The rank changes are #191's:
  - exact: Claude Sonnet 5.5 passes GPT-6 Luna for fourth;
  - within 1%: three adjacent pairs swap;
  - bounded score: three adjacent pairs swap, plus Grok 4.3 and Gemini 3.1 Flash Lite Preview (#35/#36).

  On top of #191's records, the Virginia record adds 0.05 to 0.08 points to every model's exact rate and changes no exact rank.

Every model missed both scenario_114 outputs, so excluding them raises every model's rate.

The legacy household impact summary (`impact_summary_by_model.csv`) moves too. In every case, Claude Sonnet 4.6 and Claude Opus 4.7 swap at #24/#25 on `mean_impact_score`; no other model changes rank there. #191's README does not report this file.

## Related findings

- **Stale impact weights.** The published `reference_outputs.csv` carries impact weights for 90 eligibility outputs that differ from those 2.15.17 computes. They comprise 39 Medicare, 37 Medicaid, 9 school-meal and 5 WIC outputs. For example, `head_medicare_eligible` is $5,285.20 published and $12,065.20 on 2.15.17, a gap of $6,780.00. The references' 2026-09-29 rebuild (`../2026-09-28/scripts/build_references_latest.py`) rewrote the `value` column only.

  `leaderboard_impact.py --weights-check` scores a copy with 2.15.17's weights:
  - No value in the analyze payload changes. That payload holds the dashboard's model, program, heatmap, weight and failure-mode figures.
  - The legacy household impact summary reads the row weights, so it changes. Every model's `mean_impact_score` rises by 0.0012 to 0.0128, and 10 of 46 models change rank (five adjacent pairs swap).
  - Nothing in the app, the paper or the package reads that file; the freeze writes it and the manifest pins it.

  A separate task covers the fix.
- **Enrollment changes only weights.** `not_enrolled` sets `medicare_cost`, the impact weight of the 39 Medicare eligibility outputs, to 0. It changes no output.
- **scenario_031's Medicaid annotations name the wrong mechanism.** They explain the reference (eligible, through California's optional senior-or-disabled pathway) by subtracting the Part B premium from income, and 43 row annotations fault models for not doing so.
  - On 2.15.17, `medicaid_optional_senior_or_disabled_countable_income` subtracts no premium. It applies SSI income rules with California's $230 monthly disregard: $23,853.47 less $2,760.00 is $21,093.47, under the $22,024.80 limit (138% of the 2026 poverty guideline).
  - The values are the same under every reading here, so the reference is unaffected. The annotation text needs correcting; a separate task covers it.
- **scenario_114's case notes.** The federal note lists "missing the Part B premium" among model errors. The Virginia note says the medical deduction includes the $2,000 of over-the-counter expenses, which the engine leaves out. A release adopting the records rewords both.
- **#191's README rounding.** With its records, #191 gives GPT-6 Sol's exact rate as 95.62% and the always-zero baseline as 70.40%. Its own outputs give 95.6146 and 70.3946, and this audit's #191-alone case reproduces both, so they round to 95.61% and 70.39%.

## What a release adopting the records must also do

Two sets of counts follow, one if d963 adopts #191's three records and one if it does not.

1. **Adjudications.** Add a developer adjudication (`excluded_from_scoring: true`, `adjudicated_failure_source: prompt_ambiguity`) to `annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json` for each record. Without them, `scripts/freeze_snapshot.py`'s `reference_exclusions_block` stops the freeze.
2. **Annotation rows.** Relabel the excluded outputs' `llm_error` rows to `prompt_ambiguity`, as for every other exclusion (`tests/test_paper_results.py` checks this):
   - scenario_114 Virginia: 45 rows;
   - scenario_114 federal: 45 rows, if the standalone record is used.

   Reword the two case notes above.
3. **Pinned counts.** Each output carries 46 model rows, and none is an exact match.

   | Count | With #191 adopted | Without #191 |
   |---|---|---|
   | exclusions | 59 → 60 | 56 → 58 |
   | unlisted-input exclusions | 31 → 32 | 28 → 30 |
   | households with an exclusion | stays 40 | 39 → 40 |
   | scored outputs per model | 1,925 → 1,924 | 1,928 → 1,926 |
   | 2.15.17-era records | 7 → 8 | 4 → 6 |
   | adjudications | 72 → 73 | 69 → 71 |
   | audited rows | 7,722 → 7,676 | 7,860 → 7,768 |
   | exact-match misses | 7,718 → 7,672 | 7,856 → 7,764 |

4. **Paper.** Add the Medicare enrollment and Part B premium input to the paper's unlisted-input list and sweep narrative, and re-render the abstract and tables.
5. **Legacy impact summary.** The freeze regenerates `impact_summary_by_model.csv` from the scored reference; its pin in the snapshot manifest changes with the records (see "Leaderboard impact").
