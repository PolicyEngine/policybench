# Tax Table or rate schedule in the federal income tax references, October 10, 2026

This directory audits one convention behind every federal income tax reference in PolicyBench: the references apply the section 1 rate schedule exactly, where the Form 1040 instructions send a filer with taxable income under $100,000 to the Tax Table. It changes no reference, exclusion, score, payload, card, paper or snapshot. Which convention PolicyBench uses is Max's call, queued as decision d1263.

Release audited: dashboard-data-20261010 (commit 5a8164a0), 47 models, references from policyengine-us 2.38.6.

## Findings

- **The law.** The Tax Table is the tax the statute imposes, in place of the schedule tax, on a filer who does not itemize and is under the ceiling (26 U.S.C. 3(a)(1)). The same paragraph requires its amounts to be "computed on the basis of the rates prescribed by section 1". The instructions set the ceiling at $100,000 and send line 16 and the capital gain worksheets' look-ups to the table under it, for itemizers too.
- **2026.** No 2026 Tax Table dated or posted before the 2026-07-03 freeze was found. The earliest found is the IRS's early release draft, dated Aug 28, 2026 and posted 09/16/2026. Archived copies of the IRS's draft listing up to the freeze day show none, though they do not cover every day. The final table is not published. The 2026 rate schedule was announced on October 9, 2025 (Rev. Proc. 2025-32).
- **The construction.** No document read says how the IRS fills the table. The rule inferred here (the schedule's tax on the band's midpoint, rounded to a dollar, a half rounding up) reproduces all 8,248 amounts of the published 2025 table and all 8,248 of the 2026 draft. Values built with it are labelled constructed: they equal the IRS's draft, and the IRS has published no final 2026 table.
- **The engine.** policyengine-us 2.38.6 has no Tax Table logic. It applies the schedule in two variables, `income_tax_main_rates` and `tax_on_taxable_income_at_main_rates`.
- **What moves.** Of the 84 scored federal income tax references, the table changes 30 and moves 21 by more than the $1 tolerance, by -$2.96 to +$3.97. It also moves two scored federal refundable credit references. No scored state output changes.
- **What models answer.** On the 21 moved cells, 173 of 987 answers are within $1 of the schedule value and 18 within $1 of the table value; 16 of those 18 are within $1 of both. Two answers match the table alone, and neither explanation mentions a table. Of 4,700 federal income tax explanations, 6 use the words "tax table", and none of those six answers is within $1 of either value.
- **Scores.** Accepting either value raises two models' exact rates by 0.21 and 0.23 points and swaps ranks 35 and 36. Moving the references to table values lowers 21 models by up to 3.25 points and changes 17 ranks.

## The decision is what the output means

The evidence settles what a return shows and what the references compute. It does not settle which of the two the benchmark's output is. Three readings are open:

1. **The tax on the return.** The amount a filed 2026 return shows. For a return under $100,000 that is the table amount, so 21 scored federal references and 2 scored refundable credit references are off by more than $1. Option (c) follows, or (b) while the IRS's 2026 table is a draft.
2. **The tax computed from the section 1 rates, to the cent.** The references are right as they stand, and the definition has to be stated. Option (a) follows.
3. **What a careful reader could compute from law published before the freeze.** Both values are defensible, and (b) or exclusion follows.

## Recommendation

Reading 2: keep the rate schedule, and state the definition in the benchmark card, the paper and the v2 prompt (PolicyEngine/policybench#165). These are judgments about what the benchmark should measure. They are not findings of law.

1. The schedule needs no convention beyond the published rates. The table adds three: its bands, the midpoint rule, which no document read states, and whether the looked-up amount is rounded. The earliest 2026 table found postdates the freeze and is a draft.
2. PolicyBench's amounts are computations to the cent, with a $1 tolerance. A return is not one: the filer may round every amount on it to whole dollars.
3. It changes no score.

Its cost should be stated with it. On the current release the prompt does not say which computation is wanted, the instruction to use the table is mandatory for these returns, and an answer that follows it is scored a miss on 21 federal cells. Two answers are within $1 of the table value alone today.

How the models answer shows which reading the current prompt draws out. It does not show which reading is correct. 173 of the 987 answers on the 21 cells match the schedule value, and 2 match the table value alone.

The case for each other option:

- **(b) Accept either value.** The current prompt leaves the convention open, and a reader who follows the form's instructions gives the table value. Accepting both marks neither reading wrong, whether or not any model gives the table value today. It needs a second accepted value in both scorers and the payload. Two models' rates rise, and ranks 35 and 36 swap.
- **(c) Table values.** If the output is the return's tax, section 3 and the instructions are the strongest ground there is, and the constructed values equal the IRS's draft in every amount. It rests on a draft and on a rule inferred from the tables, it needs a ruling on rounding, and it lowers 21 models' rates by up to 3.25 points.
- **Exclusion.** PolicyBench's usual treatment of a reference a careful reader could take two ways. It removes the 23 outputs the table moves by more than $1. It leaves the 9 the table changes by less, on which no answer's exact match differs between the two values. Every model's rate rises, and 24 ranks change.

If the schedule is kept, one thing is worth watching on later boards. A model whose answers match the table value alone on several of these cells is reading the question as the return's tax. The most any model has today is one.

## The law

Read on 2026-10-10. `law/excerpts.md` has the passages and `law/sources.json` each document's address, dates and sha256. `scripts/law_sources.py` found all 41 excerpts verbatim in the saved documents (`law/excerpts_check.json`).

- **26 U.S.C. 3(a)(1).** "In lieu of the tax imposed by section 1", a tax "determined under tables ... prescribed by the Secretary" is imposed on an individual who does not itemize and whose taxable income does not exceed the ceiling amount. Section 3(a)(2) lets the Secretary set the ceiling, at $20,000 or more. Section 3(a)(3) lets the Secretary extend the table to itemizers. Section 3(c) treats the table tax as tax imposed by section 1. The section was last amended in 1986. Pub. L. 119-21 does not touch it.
- **The instructions.** The 2025 Instructions for Form 1040, line 16: "If your taxable income is less than $100,000, you must use the Tax Table". At $100,000 or more the Tax Computation Worksheet applies, which is the schedule exactly. The instruction does not distinguish itemizers. Five other methods replace it for some returns: Form 8615, the Schedule D Tax Worksheet, the Qualified Dividends and Capital Gain Tax Worksheet, Schedule J and the Foreign Earned Income Tax Worksheet.
- **The worksheets.** The Qualified Dividends and Capital Gain Tax Worksheet looks up two amounts (lines 22 and 24), the Schedule D Tax Worksheet two (lines 44 and 46), and the Foreign Earned Income Tax Worksheet's line 5 one more. Each look-up uses the Tax Table when its amount is under $100,000. Form 8615 and Schedule J were not read.
- **Rounding.** Whole-dollar amounts are the filer's option (26 U.S.C. 6102(b); "You can round off cents to whole dollars"). A filer who rounds must round every amount.
- **The regulation.** 26 CFR 1.3-1 still describes the elective table of the early 1970s and says nothing about today's.
- **2026 rates.** Rev. Proc. 2025-32, section 4.01, gives the 2026 rate tables under section 1(j)(2). The IRS announced it on October 9, 2025 (IR-2025-103). Pub. L. 119-21, section 70101, removed that subsection's 2025 end date. The 2026 Form 1040-ES, which IRS.gov lists as posted 02/13/2026, figures estimated tax "by using the 2026 Tax Rate Schedules". It is a form for estimated payments and does not settle the tax on a return.
- **The 2026 table.** None dated or posted before the freeze was found. What the search covered:
  - On 2026-10-10, IRS.gov lists Publication 1040 at its 2025 revision (posted 01/15/2026), and `irs.gov/pub/irs-pdf/i1040gi.pdf` serves the 2025 instructions. So no final 2026 table is published.
  - The earliest 2026 table found is the IRS's early release draft of Publication 1040 (2026). Its cover is dated Aug 28, 2026, IRS.gov lists it as posted 09/16/2026, and every page is marked "DRAFT—NOT FOR FILING". It keeps the $100,000 ceiling.
  - The Internet Archive holds 14 copies of pages of the IRS's draft listing captured from 2026-05-20 to 08:09 UTC on 2026-07-03. They show 251 drafts posted from 03/23/2026 to 07/01/2026. None is a Publication 1040, the Instructions for Form 1040 or a tax table (`law/draft_listing_history.json`).

  The search does not cover a draft posted before 03/23/2026, or on a day whose listing page was not archived (06/09/2026 is one), and replaced since.

So the table is the law's tax for a non-itemizer under the ceiling, and the instructions' rule for line 16 and the worksheet look-ups of any return under it. No scored reference turns on the itemizer question: none of the 33 scored returns the table applies to itemizes.

PolicyBench's rule is that a scored reference follows from law published before the freeze. No 2026 table from before the freeze was found, and its amounts are a function of rates that were published by then. Whether that makes the schedule or the table the answer under the rule is part of the decision.

## The engine

Read in policyengine-us 2.38.6 as installed from `uv.lock`.

- `tax_at_main_rates` (`variables/gov/irs/tax/federal_income/before_credits/tax_at_main_rates.py`) sums each bracket's rate times the amount in it.
- `income_tax_main_rates` applies it to taxable income less the gains and dividends taxed at capital gain rates. That is line 16 for a return without them, and line 22 or 44 of the worksheets.
- `tax_on_taxable_income_at_main_rates` applies it to all taxable income (lines 24 and 46). `capital_gains_tax` caps the tax on the gains at the difference.
- `regular_tax_before_credits` adds `income_tax_main_rates` and `capital_gains_tax`.
- The words "tax table" appear in the federal income tax code once, in a variable's documentation text. No formula looks anything up.
- The engine has no Form 8615 tax and no Schedule J income averaging: no file under its federal variables or parameters names Form 8615, Schedule J or income averaging. (Its alternative minimum tax exemption has a rule for children subject to the kiddie tax, which is a different computation.) It does model the foreign earned income exclusion, which no benchmark household claims.

The sweep checks that the engine's 2026 brackets equal Rev. Proc. 2025-32's. It covers the computations the engine represents, not every method a return could use.

## Method

1. **Construct.** `scripts/tax_table.py` builds the table from a rate schedule in integer arithmetic. `scripts/parse_irs_tax_table.py` reads the IRS's tables out of Publication 1040 into `law/irs_tax_table_2025.csv` and `law/irs_tax_table_2026_draft.csv`.
2. **Sweep.** `scripts/sweep_tax_table.py` recomputes all 1,984 outputs for the 100 households on the release's reference system: policyengine-us 2.38.6 with the pre-freeze conventions and the Maryland adapter, through the reference builder's own `compute_outputs`. Its baseline reproduces all 1,926 scored references. It then reruns every household with the two formulas above copied and their look-up swapped:
   - `schedule_copy`: the look-up left as the schedule. Every output is bit-identical to the baseline, so the copies are the engine's formulas.
   - `table`: the constructed 2026 table for an amount under $100,000.
   - `table_whole_dollar`: a sensitivity. The same, with each looked-up amount rounded to a whole dollar first, and the worksheet applied to the rounded amount at $100,000 or more. Nothing else on the return is rounded.

   Everything downstream is the engine's: the capital gain cap, the alternative minimum tax, the limit on nonrefundable credits, the refundable credits and each state's tax. Outputs: `verification/sweep_tax_table.csv`, `tax_units.csv` and `sweep_summary.json`.
3. **Score.** `scripts/leaderboard_impact.py` scores the frozen run, read from git at the release commit, under the conventions below. Outputs: `verification/federal_cells.csv`, `model_answers.csv`, `model_counts.csv`, `leaderboard_impact_models.csv` and `leaderboard_impact.json`.
4. **States.** `scripts/state_tax_tables.py` checks which states prescribe a table (below). It recomputes nothing.

## What moves

Every household is one federal return in the engine. Of the 100 returns, 49 have no taxable income, 38 have some under $100,000 and 13 have $100,000 or more.

| Federal income tax references | All | Scored |
|---|---:|---:|
| Total | 100 | 84 |
| No taxable income | 49 | 45 |
| Taxable income of $100,000 or more (the worksheet is the schedule) | 13 | 6 |
| Taxable income under $100,000 (the table applies) | 38 | 33 |
| Changed by the table | 35 | 30 |
| Moved by more than $1 | 26 | 21 |
| Changed by $1 or less | 9 | 9 |

Three scored references do not change although the table applies: in scenario_026, scenario_028 and scenario_119, nonrefundable credits use up the whole regular tax under either convention, so the output is $0 both ways.

Among the 30 scored references that change, the table is higher in 20 and lower in 10. The differences run from -$2.96 to +$3.97, with a median of +$1.14 and a mean absolute difference of $1.60. By size: 9 of $1 or less, 11 over $1 and up to $2, 8 over $2 and up to $3, and 2 over $3. A difference can be at most $6.00 under the ceiling: half of a $50 band at 22%, plus the half dollar of rounding.

The 21 scored references that move by more than $1 (a dagger marks a return that goes through a capital gain worksheet):

| Household | Filing status | Amount looked up | Band | Schedule value | Constructed table value | Difference |
|---|---|---:|---|---:|---:|---:|
| scenario_042 (WI) | single † | 21,749.71 | 21,700–21,750 | 2,361.96 | 2,359.00 | -2.96 |
| scenario_082 (NY) | head of household † | 79,387.12 | 79,350–79,400 | 9,579.77 | 9,577.60 | -2.17 |
| scenario_018 (AZ) | single | 45,492.09 | 45,450–45,500 | 5,211.05 | 5,209.00 | -2.05 |
| scenario_000 (TX) | single | 26,287.11 | 26,250–26,300 | 2,906.45 | 2,905.00 | -1.45 |
| scenario_068 (MD) | single | 17,983.53 | 17,950–18,000 | 1,910.02 | 1,909.00 | -1.02 |
| scenario_091 (WI) | single † | 14,316.66 | 14,300–14,350 | 1,350.00 | 1,351.00 | +1.00 |
| scenario_046 (OK) | joint | 44,964.29 | 44,950–45,000 | 499.71 | 501.00 | +1.29 |
| scenario_089 (NC) | joint | 60,964.27 | 60,950–61,000 | 6,819.71 | 6,821.00 | +1.29 |
| scenario_007 (ID) | single | 32,964.12 | 32,950–33,000 | 3,707.70 | 3,709.00 | +1.30 |
| scenario_086 (GA) | head of household | 48,412.90 | 48,400–48,450 | 3,255.55 | 3,257.00 | +1.45 |
| scenario_064 (WI) | joint | 67,812.12 | 67,800–67,850 | 4,441.46 | 4,443.00 | +1.54 |
| scenario_037 (NC) | single | 15,810.43 | 15,800–15,850 | 1,649.25 | 1,651.00 | +1.75 |
| scenario_015 (IN) | single | 26,809.38 | 26,800–26,850 | 2,969.13 | 2,971.00 | +1.87 |
| scenario_053 (ID) | single | 50,868.68 | 50,850–50,900 | 5,903.11 | 5,905.00 | +1.89 |
| scenario_077 (LA) | single | 6,906.18 | 6,900–6,950 | 690.62 | 693.00 | +2.38 |
| scenario_067 (IN) | joint | 55,102.00 | 55,100–55,150 | 5,616.24 | 5,619.00 | +2.76 |
| scenario_102 (NC) | joint | 55,000.80 | 55,000–55,050 | 6,104.10 | 6,107.00 | +2.90 |
| scenario_051 (LA) | single † | 23,900.00 | 23,900–23,950 | 2,620.00 | 2,623.00 | +3.00 |
| scenario_009 (NC) | joint | 73,700.00 | 73,700–73,750 | 8,348.00 | 8,351.00 | +3.00 |
| scenario_075 (FL) | single † | 86,960.37 | 86,950–87,000 | 14,777.15 | 14,780.86 | +3.72 |
| scenario_039 (VA) | single | 63,109.22 | 63,100–63,150 | 8,596.03 | 8,600.00 | +3.97 |

scenario_091's schedule value is $1,349.9988, so its difference is $1.0012. A table value carries cents where the return subtracts a credit or adds capital gain tax that does (scenario_075, scenario_082). `verification/federal_cells.csv` has every reference. For each looked-up amount it gives the constructed table tax beside the IRS draft's, which are equal in every row.

The table also changes five excluded federal income tax outputs, by $2.01 to $5.43: scenario_022, scenario_033, scenario_093, scenario_114 and scenario_123. Two of them, scenario_022 and scenario_114, are the only returns under the ceiling that itemize.

### Outputs that inherit it

| Output | Schedule | Table | Difference | Status |
|---|---:|---:|---:|---|
| scenario_026 (NC) federal refundable credits | 2,013.49 | 2,011.00 | -2.49 | scored |
| scenario_028 (PA) federal refundable credits | 3,274.93 | 3,273.13 | -1.80 | scored |
| scenario_119 (VA) federal refundable credits | 2,854.01 | 2,853.23 | -0.77 | excluded |
| scenario_093 (MO) state income tax | 3,388.2456 | 3,388.2407 | -0.005 | excluded |

In the first three the regular tax rises under the table, nonrefundable credits absorb the rise, and the refundable credits fall by the same amount. Missouri deducts a share of federal income tax (`mo_federal_income_tax_deduction` reads `income_tax`), which is how scenario_093's federal change reaches its state tax. State formulas in ten states read a federal income tax variable (AL, CA, IA, LA, MO, MT, NE, NM, OK and OR). No scored state output changes by any amount in this release, and no other output of any kind changes.

In all, the table changes 32 scored outputs (30 federal income tax, 2 refundable credits) and moves 23 of them by more than $1.

### Rounding the looked-up amount: a sensitivity

A filer who rounds the return looks up a whole-dollar amount. The sweep's `table_whole_dollar` variant rounds only that amount, so it is a sensitivity of the look-up and not a whole-dollar return, which rounds every amount. It moves one scored reference by more than $1. scenario_042's amount is $21,749.71, which rounds to $21,750 and into the next band: $2,365 against $2,359. Five scored references with $100,000 or more of taxable income change by at most 14 cents, because the worksheet is applied to the rounded amount. So the table convention is itself two conventions on scenario_042, $6 apart.

## What the models answered

On the 21 scored federal cells that move by more than $1, each of the 47 models gave one answer (987 answers):

| Answer is within $1 of | Answers |
|---|---:|
| the schedule value only | 157 |
| both values | 16 |
| the table value only | 2 |
| neither | 812 |

- The two table-only answers are DeepSeek V4 Pro's $1,351.00 on scenario_091, $1.0012 from the schedule value, and Claude Opus 5.5's $9,578.20 on scenario_082. Neither explanation mentions a table.
- 21 models have at least one schedule-only match (GPT-6 Sol 16, Kimi K3 14). 25 models match neither value on any of the 21 cells.
- 626 of the 987 answers are whole dollars.
- Of all 4,700 federal income tax explanations in the release, 6 contain "tax table", from three models. Four are Claude Haiku 4.5's, two of which go on to list bracket thresholds ("2026 HoH tax tables: 10% up to $20,550"). Gemini 3.1 Flash Lite Preview's says "Calculated based on 2026 tax tables" and gives no method. Claude Sonnet 5's, on scenario_000, cites "slight rounding to standard IRS tax tables" for an answer of $3,204, about $298 from the schedule value and $299 from the table value. None of the six answers is within $1 of either value.

`verification/model_answers.csv` has every answer on the 32 changed outputs and `model_counts.csv` the count for each model.

## Leaderboard impact

The headline is the household-equal, population-weighted exact rate. From `verification/leaderboard_impact.json`:

| Convention | Scored outputs | Exact-rate change, all models | Models gaining / losing | Exact ranks changed | GPT-6 Sol |
|---|---:|---|---|---:|---:|
| (a) rate schedule (published) | 1,926 | | | | 95.58% |
| (b) accept either value | 1,926 | 0 to +0.23 points | 2 / 0 | 2 | 95.58% |
| (c) table values as the reference | 1,926 | -3.25 to +0.21 points | 1 / 21 | 17 | 92.33% |
| for comparison: stop scoring the 23 moved outputs | 1,903 | +1.05 to +4.22 points | 47 / 0 | 24 | 96.64% |

- **(b) Either.** Claude Opus 5.5 rises from 94.41% to 94.64% and DeepSeek V4 Pro from 79.69% to 79.90%, which takes it past Gemini 3.1 Flash Lite Preview for 35th. No other model's rate changes.
- **(c) Table.** The 21 models with a schedule match lose 0.20 to 3.25 points. GPT-6 Sol loses the most, Kimi K3 2.86 and Claude Opus 5.5 2.32. DeepSeek V4 Pro gains 0.21. The first eight ranks hold. Grok 4.7, which matches neither value on any of the 21 cells, rises from 14th to 9th. Within-1% rates move by at most 0.21 points and bounded scores by at most 0.003.
- **Exclusion** is PolicyBench's usual remedy for a reference a careful reader could take two ways, so it is scored for comparison. It removes the 23 outputs the table moves by more than $1. Most are cells the leading models match on the schedule, which is why it changes the most ranks. The 9 outputs the table changes by $1 or less stay scored: on all 423 answers to them, the exact match is the same against either value.

The first ten models (all 47 are in `verification/leaderboard_impact_models.csv`):

| Model | (a) schedule | (b) either | (c) table | Matches on the 21 cells: schedule / table / both / neither |
|---|---:|---:|---:|---|
| GPT-6 Sol | 95.58 | 95.58 | 92.33 | 16 / 0 / 0 / 5 |
| Claude Opus 5.5 | 94.41 | 94.64 | 92.10 | 12 / 1 / 1 / 7 |
| GPT-5.6 Sol | 93.49 | 93.49 | 91.01 | 12 / 0 / 3 / 6 |
| Claude Sonnet 5.5 | 92.16 | 92.16 | 90.07 | 10 / 0 / 2 / 9 |
| GPT-6 Luna | 91.97 | 91.97 | 89.94 | 10 / 0 / 3 / 8 |
| GPT-6 Astra | 91.94 | 91.94 | 89.40 | 12 / 0 / 0 / 9 |
| Claude Fable 5.1 | 91.27 | 91.27 | 89.38 | 9 / 0 / 0 / 12 |
| Kimi K3 | 90.97 | 90.97 | 88.11 | 14 / 0 / 1 / 6 |
| GPT-6.1 Sol | 90.35 | 90.35 | 88.02 | 11 / 0 / 0 / 10 |
| GPT-5.6 Luna | 89.16 | 89.16 | 87.30 | 9 / 0 / 0 / 12 |

Under (b) and (c) every scored output the table changes takes part, 32 in all. The legacy household impact summary (`impact_summary_by_model.csv`) is not recomputed here.

### Two scorers

Each convention is scored twice, and the two must agree for every model:

- **The repo's scorer.** `python -m policybench.cli analyze`, the command the freeze runs, scores (a), (c) and the exclusion case. The unchanged copy reproduces every compared value of the published payload. `policybench.analysis.weighted_hit_rate_scores_by_model` scores all four. For (b) each model is scored against the accepted value nearer its own answer, which is the same rule for an exact match. The function and the command give identical rates.
- **An independent re-aggregation.** `scripts/independent_scorer.py` reads the run's files itself and imports nothing from `policybench`.

The largest gap between them is 2.8e-14 points.

## States: a scoped follow-up

Not audited. `scripts/state_tax_tables.py` records which states' resident instructions prescribe a tax table and how many references sit there (`verification/state_tax_tables.json`). A Subfleet research lane read the instructions; the script then fetched each document and found every quotation in it. Band widths are as the lane read them and were not rechecked.

All 31 scored state income tax references with a nonzero value sit in 21 states.

- **A table is prescribed in 12:** CA, NJ, MD, NY, VA, OK, MN, AL, CT, WI, AR and WV. They hold 16 of the 31 references.
- **The instructions make it mandatory in 8** (CA, MD, NY, OK, MN, AL, WI and WV), which hold 11. It is optional in VA and CT, and in AR unless the filer itemizes. New Jersey's two sources word it differently.
- **Ceilings** are $100,000 of taxable income in most. Minnesota's is $86,800, New York's is $65,000 of taxable income with adjusted gross income of $107,650 or less, and Connecticut's is $102,000 of adjusted gross income. Virginia's table runs to $98,356.
- **No table in 9:** NC, IN, AZ, MI, PA and IL tax at a flat rate, GA at a flat rate rounded to the dollar, and OH and ID from a schedule or worksheet.

The documents read are each state's 2025 instructions or forms, with two exceptions: New Jersey's table is labelled 2018 and posted as the current one, and Pennsylvania's rate is from an undated page of its revenue department. No state's 2026 table was looked for.

For the 16 references in the table states, nothing here establishes whether the state's table applies to the return or what it would change. That is the follow-up question, and the answer to the federal question should decide the states' too.

## Invariants and tests

`tests/test_tax_table_audit.py` states and checks them.

For the constructed table, at every taxable income under $100,000, filing status column and year (2025 and 2026), by property test:

- it is a whole, non-negative number of dollars, and zero at zero;
- it never falls as taxable income rises, and is constant inside a band;
- it is the schedule's tax at the band's midpoint, a half dollar rounding up;
- it is within half a band-width times the band's top marginal rate, plus the half dollar of rounding, of the schedule's tax on the income itself, and so within one band-width times that rate;
- the joint column is at most the head of household column, which is at most the single column, and the separate column equals the single one;
- at $100,000 or more the instructions' method is the schedule exactly.

Differential tests:

- the constructed 2025 table equals the IRS's published table in all 8,248 amounts, and the constructed 2026 table equals the IRS's draft in all 8,248;
- no other simple rule does: the tax at the band's lower or upper bound, or the midpoint tax with a half rounded down, rounded to even or truncated, each misses more than 1,000 amounts;
- the revenue procedures' printed base amounts follow from their thresholds and rates;
- the independent scorer agrees with the repo's scorer on generated runs with exclusions, missing answers and a second accepted value, and accepting a second value never lowers a rate;
- the recorded sweep's schedule tax and table tax on each return equal `scripts/tax_table.py`'s, and the recorded rates under (a) equal the published payload's.

`manifest.json` pins the release's inputs and every file here except this README, the manifest itself and the logs of the test and mutation runs. A test rebuilds it. `verification/mutants_tax_table.txt` records a mutation run: each of 34 deliberate faults in the construction, the table parser, the sweep's look-up and the independent scorer fails a test.

The first mutation run of this audit, which was not kept, left two faults standing: a 39% top rate and a parser that read past the table. `scripts/top_rate_detection.py` reproduces the first. With the income generator the test first used, a random property test misses that fault in 13 of 40 seeded runs, because few draws reach the top bracket; with the generator it uses now, in none (`verification/top_rate_detection.json`). A test of each bracket's printed formula and a parser test with rows after the table now hold both.

## What each option would take

None of this is done here.

- **Keep the schedule and say so.** A sentence in the benchmark card's reference section and the paper's method: federal income tax references apply the section 1 rate schedule to taxable income to the cent, at every income, and not the Tax Table. A matching line in the v2 prompt's output definitions. No score changes.
- **Accept either value.** A second accepted value for 32 scored outputs: a new field beside the reference, both scorers (`policybench/analysis.py` and the app's), the payload schema, and the card and paper. Two models' rates change. The whole-dollar variant of scenario_042 would need a ruling as a third value or not.
- **Move to table values.** Regenerate 32 scored references and re-review the five excluded federal outputs the table moves. Decide the rounding of the looked-up amount. Hold the engine's two formulas in a reference adapter until policyengine-us carries a table, and file that upstream. Re-run the annotations of every row whose exact match flips. The values would rest on a table the IRS has published only as a draft.

Related: decision d1252 asks whether to keep scoring scenario_039's federal income tax. Its reference is $8,596.03 on the schedule and $8,600 on the table.

## Files

- `law/`: the excerpts, the sources, the excerpt check, the archived draft listings' record, both IRS Tax Tables as CSV, and the state claims.
- `scripts/`: `tax_table.py` (the construction), `parse_irs_tax_table.py`, `law_sources.py`, `release.py` (the frozen run, read from git), `sweep_tax_table.py`, `independent_scorer.py`, `leaderboard_impact.py`, `state_tax_tables.py`, `mutants_tax_table.py`, `top_rate_detection.py` and `build_manifest.py`.
- `verification/`: the sweep, the per-return detail, the cells, the answers, the scores, the state check, and the test and mutation runs.
- `manifest.json`: the sha256 of the release's inputs and of every file above but this README and the two run logs.
