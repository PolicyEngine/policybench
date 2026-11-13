# Car loan interest and the vehicle loan interest deduction, November 11, 2026

Twenty-three US prompts list "auto loan interest" among the household's inputs. None says whether the loan qualifies for the federal deduction for qualified passenger vehicle loan interest, and the references treat it as not qualifying. This directory measures how the board of release dashboard-data-20261111 would change if the cells this question moves were dropped, and in an engine sensitivity that counts all stated auto loan interest as qualifying. The release changes nothing on this question.

## The question

If each household's stated auto loan interest counted as qualified passenger vehicle loan interest, which scored outputs would move beyond the exact-match tolerance, and how would each model's share of answers right and rank change?

## What the prompt says

`policybench/prompts.py` labels the input "auto loan interest" (line 81) and lists it with the household's other inputs under "Household inputs" (lines 533-545), as a whole-dollar amount (line 438). For scenario_003 the block reads:

```
Household inputs:
- auto loan balance: $47,000
- auto loan interest: $500
- household vehicles value: $1,610
```

Every prompt opens with the same rules (`TASK_PREFACE`, lines 15-28), which include: "Treat any unlisted numeric input as 0 and any other unlisted household fact, boolean, or status input as false. Assume tax filing and program take-up when required. Do not infer unlisted income, expenses, assets, benefit receipt, rent, or health coverage." No prompt says whether the loan or the vehicle meets the deduction's requirements.

## What the engine reads

Paths are relative to the installed policyengine-us 2.60.0 package, the engine that computed the references.

- `variables/household/expense/vehicle/auto_loan_interest.py`, lines 4-10: `auto_loan_interest`, a household input labeled "auto loan interest expense", with no formula. The reference build sets it from the household's stated amount. No variable, parameter or reform in 2.60.0 reads it.
- `variables/household/expense/vehicle/qualified_passenger_vehicle_loan_interest.py`, lines 4-20: `qualified_passenger_vehicle_loan_interest`, a household input with no formula, documented (lines 9-13) as "Interest on loans that meet the federal qualified passenger vehicle loan interest requirements, including qualifying vehicle and loan requirements." No PolicyBench household sets it, so it is 0.
- `variables/gov/irs/income/taxable_income/deductions/auto_loan_interest/auto_loan_interest_deduction.py`, lines 16-39: `auto_loan_interest_deduction` adds `qualified_passenger_vehicle_loan_interest` and nothing else (lines 17-21) and caps it at $10,000 (line 23; `parameters/gov/irs/deductions/auto_loan_interest/cap.yaml`). It looks up a phase-out start by the tax unit's filing status (lines 25 and 28) and reduces the capped amount, not below zero, by $200 for each $1,000, or part of $1,000, by which modified adjusted gross income exceeds that start (lines 32-39; `phase_out/step.yaml`, `phase_out/increment.yaml`). `phase_out/start.yaml` (lines 13-22) sets the start at $100,000 for single, separate and head-of-household filers and at $200,000 for joint filers and for surviving spouses. Line 29 cites 26 U.S.C. 163(h)(4).
- The statute, 26 U.S.C. 163(h)(4)(C)(ii)(I), added by Public Law 119-21, section 70203(a), reduces the deduction once modified adjusted gross income exceeds "$100,000 ($200,000 in the case of a joint return)". A surviving spouse's return is not a joint return, so the engine's $200,000 start for surviving spouses differs from the statute's text, which gives them $100,000. For single, separate, head-of-household and joint filers the engine's starts match the text.
- The deduction lowers federal taxable income whether or not the household itemizes (`parameters/gov/irs/deductions/deductions_if_itemizing.yaml`, line 15; `deductions_if_not_itemizing.yaml`, line 24). Idaho (`parameters/gov/states/id/tax/income/deductions/qualified_business_income_and_federal_schedule_1a_deductions.yaml`, line 10) and Indiana (`variables/gov/states/in/tax/income/deductions/obbba_conformity/in_auto_loan_interest_deduction.py`, line 15) also read it.

So the references compute the deduction as $0 for every household.

## Method

`scripts/compute_outputs.py` computes every US output twice on policyengine-us 2.60.0, with the reference build's own recipe (`reference_audit/2026-10-22-engine-upgrade/scripts/build_references_upgrade.py`, `compute_outputs`): the conventions in `reference_audit/2026-09-28/fixes/latest_final.py`, households built by `reference_audit/2026-09-28/scripts/sweep.py`, and the frozen snapshot's households and output list.

- **As built:** the households as the references were built. This pass reproduces all 1,934 scored references to the cent and equals the 2.60.0 build's `reference-build/computed.csv` on all 1,984 outputs.
- **Alternative:** an engine sensitivity. The same, after copying each household's stated `auto_loan_interest` into `qualified_passenger_vehicle_loan_interest`, so that all stated auto loan interest counts as qualifying. Households that state no auto loan interest do not change.

An output moves when the two passes differ by more than $1 (for a 0/1 flag, by any change), the paper's exact-match tolerance. `scripts/score.py` scores the frozen predictions of all 52 models with the board's own scoring functions. PolicyBench counts a dollar amount as right when it falls within $1 of the reference and an eligibility answer as right when it matches, and it weights each answer by household impact. Rank 1 is the highest share; equal shares would share a rank.

- **(a) The release as scored.** Every model on the release's 1,934 scored outputs against their references. This board equals the frozen board for all 52 models.
- **(b) The 11 cells dropped.** The 11 scored outputs that move leave scoring for every model, as an exclusion record removes an output, and the board scores the remaining 1,923.
- **(c) An engine sensitivity.** The same 1,934 outputs, with each of the 11 moved outputs scored against the value the engine computes when all stated auto loan interest counts as qualifying, instead of its reference. It is not a board under an established legal reading: no prompt says whether any loan qualifies, and the sensitivity counts every stated amount in full.

The 50 outputs the release already excludes stay excluded in all three boards.

## What moves

Twenty-one households state auto loan interest above zero, and two state a negative amount, which the deduction's floor turns into $0. In nine of the 21 no output moves: six have no federal taxable income as built, and in three the phase-out removes the whole deduction. In scenario_101 the phase-out leaves $1,000 of the stated $1,400.

Fifteen outputs move beyond the tolerance: 11 scored and 4 that the release already excludes for other reasons. One more output, scenario_093's state income tax (excluded), changes by $0.28. Amounts are in dollars; the change is the alternative minus the as-built value, and the last two columns count the 52 models whose answer matches each value.

| Household | State | Filing status | Stated interest | Output | Reference | As built | Alternative | Change | Scored | Models matching reference | Models matching alternative |
|---|---|---|---:|---|---:|---:|---:|---:|---|---:|---:|
| scenario_002 | WA | joint | 1,816.47 | `federal_income_tax_before_refundable_credits` | 0.00 | 1,890.30 | 1,708.65 | -181.65 | no (excluded) | - | - |
| scenario_003 | TX | joint | 500.00 | `federal_income_tax_before_refundable_credits` | 22,400.65 | 22,400.65 | 22,290.65 | -110.00 | yes | 12 | 3 |
| scenario_018 | AZ | single | 1,625.30 | `federal_income_tax_before_refundable_credits` | 5,211.05 | 5,211.05 | 5,016.01 | -195.04 | yes | 9 | 1 |
| scenario_026 | NC | joint | 378.06 | `federal_refundable_credits` | 2,013.49 | 2,013.49 | 2,058.86 | +45.37 | yes | 8 | 4 |
| scenario_028 | PA | head of household | 980.00 | `federal_refundable_credits` | 3,274.93 | 3,274.93 | 3,392.53 | +117.60 | yes | 5 | 1 |
| scenario_033 | SD | joint | 1,225.00 | `federal_income_tax_before_refundable_credits` | 3,818.15 | 3,818.15 | 3,671.15 | -147.00 | no (excluded) | - | - |
| scenario_053 | ID | single | 950.00 | `federal_income_tax_before_refundable_credits` | 5,903.11 | 5,903.11 | 5,742.24 | -160.87 | yes | 13 | 2 |
| scenario_053 | ID | single | 950.00 | `state_income_tax_before_refundable_credits` | 2,186.06 | 2,186.06 | 2,135.71 | -50.35 | yes | 0 | 0 |
| scenario_067 | IN | joint | 1,844.70 | `federal_income_tax_before_refundable_credits` | 5,616.24 | 5,616.24 | 5,394.88 | -221.36 | yes | 9 | 4 |
| scenario_067 | IN | joint | 1,844.70 | `local_income_tax` | 1,348.83 | 1,348.83 | 1,319.32 | -29.52 | no (excluded) | - | - |
| scenario_067 | IN | joint | 1,844.70 | `state_income_tax_before_refundable_credits` | 2,486.91 | 2,486.91 | 2,432.49 | -54.42 | yes | 12 | 0 |
| scenario_086 | GA | head of household | 274.80 | `federal_income_tax_before_refundable_credits` | 3,255.55 | 3,255.55 | 3,222.57 | -32.98 | yes | 4 | 3 |
| scenario_093 | MO | joint | 1,000.00 | `federal_income_tax_before_refundable_credits` | 8,628.99 | 8,628.99 | 8,508.99 | -120.00 | no (excluded) | - | - |
| scenario_099 | CA | joint | 1,575.00 | `federal_income_tax_before_refundable_credits` | 10,711.48 | 10,711.48 | 10,364.98 | -346.50 | yes | 1 | 0 |
| scenario_101 | TX | single | 1,400.00 | `federal_income_tax_before_refundable_credits` | 13,418.60 | 13,418.60 | 13,198.60 | -220.00 | yes | 8 | 4 |

The as-built value equals the reference on every scored output. Scenario_002's federal income tax is excluded and keeps the value it was decided on.

Across the 11 scored outputs, 81 model answers match the reference and 22 match the alternative; no answer matches both. Twenty-five models match at least one of the two values. `verification/model_matches.csv` gives each model's counts.

## The three scoreboards

Share of answers right (percent) and rank for the twelve models that lead the release as scored. (a) is the release as scored; (b) drops the 11 moved cells for every model; (c) is the engine sensitivity that counts all stated auto loan interest as qualifying, not a board under an established legal reading.

| Model | (a) share | (a) rank | (b) share | (b) rank | (c) share | (c) rank |
|---|---:|---:|---:|---:|---:|---:|
| GPT-6 Sol | 95.155 | 1 | 95.648 | 1 | 94.132 | 1 |
| Claude Opus 5.5 | 94.070 | 2 | 95.076 | 2 | 93.736 | 2 |
| GPT-6.1 Terra | 93.143 | 3 | 93.834 | 3 | 92.301 | 4 |
| GPT-5.6 Sol | 93.079 | 4 | 93.548 | 4 | 92.083 | 5 |
| Claude Fable 5.2 | 91.950 | 5 | 93.388 | 5 | 92.956 | 3 |
| GPT-6 Astra | 91.728 | 6 | 92.162 | 8 | 90.802 | 8 |
| Claude Sonnet 5.5 | 91.666 | 7 | 92.301 | 6 | 90.989 | 7 |
| GPT-6 Luna | 91.501 | 8 | 92.039 | 9 | 90.496 | 9 |
| Claude Fable 5.1 | 90.840 | 9 | 92.246 | 7 | 91.543 | 6 |
| Kimi K3 | 90.530 | 10 | 91.465 | 10 | 90.321 | 10 |
| GPT-6.1 Sol | 90.165 | 11 | 90.537 | 12 | 89.030 | 12 |
| Muse Wonder | 90.048 | 12 | 91.281 | 11 | 89.784 | 11 |

[`verification/scoreboards.md`](verification/scoreboards.md) lists all 52 models, and `verification/scoreboards.csv` holds the same at full precision. With the 11 cells dropped (b), every model's share rises, by 0.372 to 1.504 points, and 14 ranks change. In the engine sensitivity (c), 4 shares rise, 21 fall and 27 stay the same, and 17 ranks change. No rank changes by more than three places in either.

## What PolicyBench does in this release

Nothing. Release dashboard-data-20261111 changes no reference and no scored output on this question: the board is scoreboard (a). The question stays open, together with the other open questions of the release's wording review, which [`docs/fable52/wording_review.md`](../../docs/fable52/wording_review.md) records; PolicyBench has set no date for deciding them.

## Limits

- The alternative counts each household's whole stated amount as qualified interest. It does not model a loan that qualifies in part, or a reading that differs by household.
- The counts of answers that match the alternative value do not show which models applied the deduction: an answer can equal that value for another reason, and this audit does not read the models' explanations.
- This audit does not trace why federal refundable credits rise in scenario_026 and scenario_028, or the state-tax effects beyond naming the Idaho and Indiana code that reads the deduction; it does not read the state tax code for Georgia, North Carolina, Pennsylvania, California, Missouri, South Dakota, Texas and Washington. Arizona's subtraction list also names the deduction (`parameters/gov/states/az/tax/income/subtractions/subtractions.yaml`, line 29), yet scenario_018's Arizona income tax does not change under the alternative; this audit does not trace why. Those values need tracing before anyone uses them to decide the question.
- The engine starts the phase-out at $200,000 for surviving spouses, where the statute's text gives that start to joint returns only. None of the 23 households that state auto loan interest files as a surviving spouse in the engine (of the 21 with an amount above zero, 11 file jointly, 8 as single and 2 as heads of household), so the difference changes no deduction and none of the 15 moved cells.
- The audit runs on policyengine-us 2.60.0, the engine of the references, and on no later release.

## Files

- `scripts/compute_outputs.py`: the engine run, as built and with the alternative. It writes `verification/computed.csv` (both values for all 1,984 outputs), `verification/traces.json` (intermediate values for the 23 households that state auto loan interest) and `verification/engine_run.json` (engine versions and the sha256 of each input).
- `scripts/score.py`: no engine. It checks the as-built pass against the references and the 2.60.0 build, and scoreboard (a) against the frozen board, and stops with an error before it writes the scoreboards if either differs. It writes `verification/moved_cells.csv`, `households.csv`, `changes_within_tolerance.csv`, `baseline_not_reproduced.csv` (the 18 excluded outputs whose decided values the engine does not reproduce), `model_matches.csv`, `scoreboards.csv`, `scoreboards.md`, `headline.json` and `summary.txt`.
- `tests/test_car_loan_sensitivity.py` checks that (a) equals the frozen board, that the moved cells, board (b) with the 11 cells dropped, the engine sensitivity (c) and the match counts follow from the committed tables and the frozen predictions, and that `headline.json` agrees with the tables.

## Rerunning

From the repository root, with `PYTHONPATH` at the root and policyengine-us 2.60.0 installed:

```bash
.venv/bin/python reference_audit/2026-11-11-car-loan-interest/scripts/compute_outputs.py
.venv/bin/python reference_audit/2026-11-11-car-loan-interest/scripts/score.py
.venv/bin/python -m pytest tests/test_car_loan_sensitivity.py
```

The engine run takes about a minute; the scoring and the test take a few seconds each.
