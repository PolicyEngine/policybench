# scenario_031 Medicaid annotations, October 5, 2026

This directory corrects the published audit text for one output: scenario_031's `head_medicaid_eligible` (California, single head age 67). The case note, the reference explanation and all 43 row annotations explained the reference (eligible) by subtracting a Medicare Part B premium from countable income. The reference system subtracts no premium. It applies California's $230 monthly income disregard instead.

The rewrite changes text only. No reference, exclusion, failure class or score changes, and the frozen run directory is untouched.

The finding came from the Medicare Part B audit (`../2026-10-05-medicare-part-b/`, PolicyEngine/policybench#193).

## What the engine does

These files hold for policyengine-us 2.15.17 as installed in the reference venv (`results/local/adds202609/triage/.venv-pe21517`). The reference system is that version plus `latest_final` (`../2026-09-28/fixes/`), on the household `Scenario.to_pe_household` builds. `scripts/engine_values.py` recomputes every figure below on that system and asserts each relation the new text states.

- **Category.** `medicaid_category` is `SENIOR_OR_DISABLED`.
  - `is_optional_senior_or_disabled_for_medicaid` requires three things: `is_ssi_aged_blind_disabled`, the income test and the asset test.
  - `is_ssi_aged` is age 65 or older (`gov.ssa.ssi.eligibility.aged_threshold`), so age 67 meets the first condition. No SSI receipt or disability is needed.
  - The adult expansion group does not apply. `is_adult_for_medicaid_nfc` requires age 19 to 64 (`categories.adult.age_range`) and no `is_medicare_eligible`.
  - In `variables/gov/hhs/medicaid` that is the only formula that bars on Medicare eligibility. `medicaid_work_requirement_eligible` reads it as an exemption. `is_medicaid_eligible` itself is a category other than `NONE` plus immigration-status eligibility.
  - No immigration status is listed, so the default, `CITIZEN`, applies.
- **Income.** `medicaid_optional_senior_or_disabled_countable_income` (`variables/gov/hhs/medicaid/income/`) adds three amounts:
  - `ssi_marital_unearned_income`;
  - income deemed from an ineligible parent;
  - in-kind support and maintenance.

  The last two are 0 here, as is the income deemed from an ineligible spouse, which the formula adds after the disregard. SSI unearned income (`gov.ssa.ssi.income.sources.unearned`) includes `social_security`, `pension_income` and `retirement_distributions`. For this head that is $9,445.47 + $13,608 + $800 = $23,853.47. Social Security counts in full, and nothing is subtracted for the $1,165 of alimony paid.
- **Disregard.** The formula reads `gov.hhs.medicaid.eligibility.categories.senior_or_disabled.income.disregard.individual[state]`. For CA that is $230 a month. `_apply_medicaid_optional_senior_or_disabled_exclusions` passes it to `_apply_ssi_exclusions` as `general_exclusion`. That function uses SSI's $20 general exclusion only when no `general_exclusion` is given, so the $230 replaces the $20; it is not added to it. Countable income = $23,853.47 − 12 × $230 = $21,093.47.
- **Limit.** `medicaid_optional_senior_or_disabled_income_limit` is `income.limit.individual['CA']` (1.38) times the poverty guideline for one person: 1.38 × $15,960 (2026) = $22,024.80. `is_optional_senior_or_disabled_income_eligible` passes when income is at or below the limit. Countable income is $931.33 under it.
- **Assets.** `ssi_countable_resources` adds bank, stock and bond assets, $4,200 here. `assets.limit.individual['CA']` is $130,000 for 2026, and the test is assets below the limit.
- **Part B.** The engine treats the head as enrolled in Medicare and models a $2,434.80 Part B premium, but countable income does not read it. With `medicare_part_b_premium` at 0, or `takes_up_medicare_if_eligible` false, countable income is still $21,093.47 and the head is still eligible (`verification/engine_values.json`, readings `no_part_b` and `not_enrolled`).

| | Annual | Monthly |
|---|---:|---:|
| SSI unearned income | $23,853.47 | $1,987.79 |
| less California's disregard | $2,760.00 | $230.00 |
| countable income | $21,093.47 | $1,757.79 |
| limit (138% of $15,960) | $22,024.80 | $1,835.40 |

Gross income is $1,828.67 over the limit, and income less only SSI's $20 exclusion ($23,613.47) is still over it. A model that counted income under SSI rules but skipped California's disregard therefore fails the income test.

The old text compared about $21,400 (gross less the Part B premium) with "about $21,600". That figure is 138% of the 2025 guideline ($15,650); the engine uses the 2026 guideline.

## Where the old mechanism came from

The judge's prompt for this case stated the wrong mechanism twice.

- **The grounding line.** The grounding row for this case in `results/local/unified_audit/grounding.csv` (untracked; `GROUNDING_SHA256` in `scripts/finish_gpt61sol.py` pins it) describes the category as "a non-MAGI pathway whose income counting deducts health insurance premiums (including Medicare Part B) from countable income". No other case's grounding carries that phrase.
- **The reference explanation.** The old explanation said that countable income "is calculated by deducting health insurance premiums, including Medicare Part B".

Both are in the prompt of the verdict behind the published text (`results/local/gpt61sol-stage/gpt61sol-v1/audit/cases/us__scenario_031__head_medicaid_eligible/prompt.md`, lines 25 and 29). That verdict was an isolated, tool-less Opus 5.5 run (`docs/gpt61sol/judge_provenance.json`), so the prompt was all it saw. This rewrite corrects the reference explanation. A future audit stage should also regenerate that grounding line; this directory does not touch the untracked file, because a driver pins its hash.

## What changed

`rewrites.json` holds 45 wording-only rewrites. Each replaces a field's whole old text with its whole new text:

- the case note (`us_case_notes.csv`);
- the reference explanation (`us_case_reference_explanations.csv`);
- the 43 row annotations (`us_audit_row_annotations.csv`).

`scripts/apply_rewrites.py` applies them and re-pins the three files' sha256 in `paper/snapshot/20260501/manifest.json` (`audit_annotation_artifacts.files`). It refuses a row that is missing or not unique, or a field that holds neither the old nor the new text. The CSVs round-trip byte for byte, so nothing else in them changes. With `--check` it writes nothing and confirms every rewrite is in force. `tests/test_annotation_rewrites.py` keeps the ledger in force, so a release that rebuilds these files from an older base cannot silently restore the old text.

Every row stays a model error. `failure_source` (`llm_error`), `failure_subtype` and `reference_suspect` are unchanged; every model answered 0 against a reference of 1. The subtypes were re-checked against the corrected mechanism:

- **29 rows, `taxable_income_or_deductions`.** These models miscounted income. 17 compared income with no exclusion or disregard with the limit, 2 applied only SSI's $20 exclusion, 2 cited an exclusion of unstated size, and 8 asserted without figures that income was too high. Skipping California's disregard is still an income-counting error. Corpus practice puts countable-income errors on Medicaid rows in this subtype (97 rows, these 29 included); one Medicaid row uses `state_local_rule`.
- **4 rows, `thresholds_rates`.** Wrong threshold: 100% of the guideline, or an SSI income limit.
- **3 rows, `asset_resource`.** SSI's $2,000 resource limit, or another asset error.
- **7 rows, `categorical_eligibility`.** These models missed that age alone gives the head a category.

These counts equal the recorded subtype counts (`verification/row_review.json`, `tally`).

## What did not change

- **The frozen run.** The run directory `paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/`, including `data.json.gz`, is untouched. The published payload (release `dashboard-data-20260930`) keeps the old text until a data release re-exports it.
- **Scores.** `scripts/payload_diff.py` rebuilds the payload from the frozen run with `export_country`, once with the annotations at `origin/main` and once with this tree's. The two differ in 132 paths, all in the scenario_031 `head_medicaid_eligible` cell, and only in its text fields:
  - `annotation`, 43;
  - `caseAnnotation`, 43;
  - `referenceExplanation`, 46.

  No score, model statistic or other cell changes (`verification/payload_diff.json`). The base rebuild reproduces the frozen payload except claude-fable-5's usage fields, which the release drivers carry from the published payload (`CARRIED_USAGE`).

## How the text was checked

1. `scripts/engine_values.py` recomputed the engine values on the reference system and asserted each relation (`verification/engine_values.json`).
2. A Claude Code workflow drafted each row from the model's frozen response (`predictions.csv.gz`), against a fact sheet limited to what step 1 verified. A separate agent then checked every claim in each draft. It read the model's response itself, quoted the words each claim rests on, and corrected the draft. A final critic checked the rows against each other and against the case note and explanation. The record, with each row's evidence and the edits made after review, is `verification/row_review.json`.
3. An independent Subfleet review checked the result (`verification/independent_review.md`).

## Related findings, not changed here

- **scenario_114.** Both of its income tax outputs are proposed for exclusion (#191, #193). The engine check of its two case notes and their rows is posted on #193 for the release that adopts those records, rather than rewritten here:
  - **Virginia note.** Group (4) blames models for leaving out the $2,000 of over-the-counter expenses or applying the 0.5%-of-AGI charitable floor. The reference itself does both. The gap is the $2,434.80 Part B premium the engine counts in the medical deduction. Eleven Virginia rows repeat the error.
  - **Federal note.** Group (3) ("missing the Part B premium") is right about the engine but rests on that unlisted premium.
- **Over-the-counter expenses elsewhere.** Seven case notes and rows in scenarios 016, 075 and 121 count over-the-counter expenses in the itemized medical deduction. `itemized_medical_expenses` adds only `medical_expense_health_insurance_premiums` and `other_medical_expenses`. No stated conclusion changes. Split into a separate task.
- **Structured value and explanation trailer.** On this output, claude-opus-4.8 and claude-sonnet-4.6 submitted 1 in the tool call, but their explanations end "value = 0", and the frozen prediction is 0. `eval_no_tools.py` now treats a valid structured value as canonical. Whether the frozen rows should be re-parsed is a scoring question, split into a separate task. The row text here describes the explanations as written.
