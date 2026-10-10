# Claude Haiku 5.5, the 2026-10-06 exclusions and the engine upgrade: design

## What the release is

This release does three things on top of release `dashboard-data-20261006`:

1. It adds Claude Haiku 5.5 (display id `claude-haiku-5.5`, provider id `claude-haiku-5-5`, run slug `haiku55`) as the board's 47th model.
2. It installs ten exclusions under Max's rulings of 2026-10-06: d1022 (eight outputs) and d994 (two Louisiana outputs). Each output leaves scoring for every model.
3. It moves the references from policyengine-us 2.15.17 to a newer release that fixes engine defects behind exclusions (Max, 2026-10-09: "yes i want to wait for hte fixed engine"). An excluded output whose defect the new engine fixes is regenerated and scored again. "The engine upgrade" describes this step.

The driver is `scripts/finish_haiku55.py`, adapted from `scripts/finish_gpt61sol.py`. The freeze is `scripts/freeze_haiku55.py`, adapted from `scripts/freeze_gpt61sol.py`. The inputs are in `docs/haiku55/`:

- `spec.json`: the rulings, the two pinned proposal files, the ten adjudications, the ruled outputs an engine upgrade regenerates (`regenerated_by_upgrade`) and the decisions on the outputs it newly excludes (`upgrade_adjudications`);
- `input_pins.json`: the finished run;
- `seed_digest.csv`: the audit seed.

The engine upgrade's builder, actions, evidence and corrected narratives are in `reference_audit/2026-10-09-engine-upgrade/`.

The stage is built in two parts. The first folds the model in and installs the ten records on release 20261006's references. `--step install-references` then installs a reference build on the new engine, and every later step holds the stage to that build. The table gives the first part's counts, which the driver enforces until a build is installed.

| | Release 20261006 | The stage before a build is installed |
|---|---|---|
| Models | 46 | 47 |
| Requested outputs per model | 1,984 | 1,984 |
| Exclusions | 64: 36 unlisted inputs, 28 engine defects | 74: 40 unlisted inputs, 32 engine defects, 2 later-published law |
| Scored outputs per model | 1,920 | 1,910 |
| Adjudications | 77, of which 64 exclude | 86, of which 74 exclude |

Sources: the base's exclusion and adjudication records at `BASE_COMMIT`, and the release's record as `build_release_exclusions` builds it. The ten new decisions are nine new entries plus scenario_051's existing entry, which is restated. The 86 holds when triage adds no other decision; it may add one only on a re-opened case, and only one that keeps the output scored.

An installed build changes these counts. It removes the exclusion records it regenerates, adds the records it newly excludes, and drops the decisions of the release 20261006 records it regenerates. The release's own counts are in the frozen exclusion record, the adjudication record and the reference sidecar's last `engine_upgrade` revision.

What never changes:

- the 100 households and the 1,984 requested outputs;
- `scenarios.csv` and its sidecar, which stay on their 20261006 pins at every step;
- every incumbent's predictions and serving row;
- the judge template (`policybench/audit.py`) and the grounding.

Without an installed build, these also keep their 20261006 bytes:

- every reference value: `reference_outputs.csv` and its sidecar stay on their 20261006 pins;
- every reference explanation: the freeze requires the staged `us_case_reference_explanations.csv` to be release 20261006's bytes from git;
- the 64 earlier exclusion records, in their order;
- every earlier adjudication's decision, except scenario_051's, which d994 restates.

An installed build changes them only as its revision lists ("The engine upgrade").

For the incumbents, only `modelStats` changes, and only as the exclusion records and the installed build explain. `build_payload` checks this. With release 20261006's exclusion record put back, every incumbent's entry must be release 20261006's, byte for byte (the scope check). With a build installed, the check also puts back release 20261006's references (`export_on_base_references`). `modelStats` holds only scores and usage (`score`, `exact`, `n`, `costUsd` and so on) and no audit text, so re-judged verdicts cannot move it. Fable 5's usage is still carried from the base (`CARRIED_USAGE`), as in the GPT-6.1 Sol release.

The new tag is `RELEASE_TAG` in `scripts/finish_haiku55.py`, and it is provisional. This note does not spell it out, just as `docs/gpt61sol/design.md` does not spell out its own tag. `spec.json`'s `release_tag` must match the tag (`release_spec`). The export receipt binds the tag, so run `--step export` again after any change to it. The snapshot date is the spec's `snapshot_date`.

## The base

The base is pinned in `scripts/finish_haiku55.py`. Each value below is the one git holds at `BASE_COMMIT`.

| Item | Value |
|---|---|
| Base tag, payload sha256 | `dashboard-data-20261006`, `aa34e5c9…d462` (127,225,036 bytes). The `data.json.gz` committed at `BASE_COMMIT` rewraps to it, and the pointer at that commit names it. |
| Models, outputs, exclusions, scored | 46, 1,984, 64 and 1,920 (every `modelStats` row has `n` 1,920) |
| `reference_outputs.csv` | `e8bbba8f…2466` |
| `reference_outputs.csv.meta.json` | `816fef53…1a4b` |
| `reference_exclusions.json` | `92741dfd…3815` |
| `scenarios.csv` | `71b16212…858a` |
| `scenarios.csv.meta.json` | `03a66e90…aebb` |
| `BASE_COMMIT` | `9ce4ade8…`, the squash merge of PR #202 on main (2026-10-09). |
| `SEED_RELEASE_COMMIT` | `8b4c0ca1…`, the merge of PR #187 (release 20260930). Its annotations rendered the seed's prompts. |
| Grounding | `b1e4a9bc…b55c`, the main clone's `results/local/unified_audit/grounding.csv` |
| Seed digest | `c780af63…8430` (`docs/haiku55/seed_digest.csv`, 674 judged cases) |

The seed is release 20261006's audit. That release carried release 20260930's audit over without re-rendering it. Both audits (`release-exclusions-batch/results/local/release-batch/dashboard-data-20261006-r3/audit` and `…/base-20260930/audit`) give the committed digest: 674 judged cases out of 986. `results/local/release-haiku55/seed-20261006` is a read-only copy whose `cases.jsonl` is the 20260930 audit's. The stage's `stage.json` binds that digest.

## The run and onboarding

Sources:
- `~/reviews/policybench-haiku-5-5/README.md` (the README);
- the card in `policybench/model_cards.py`;
- the run directories under `/Users/maxghenis/PolicyEngine/policybench/results/local/`.

- **Card.** PR #201 (head `2f58a357`, merged as `ed4f89a6`) added the card, the config entry, the price and the release date.
- **Contract.** The Models API lists `claude-haiku-5-5` with `created_at` 2026-10-07 and `max_tokens` 128,000. Unlike Sonnet 5.5 and Opus 5.5, this model accepts forced tool use. The board's rule is a forced answer tool unless the provider rejects it, so the card's `answer_contract` is `tool`.
- **Thinking.** A request with no thinking parameter returned a thinking block (119 of 123 output tokens). The forced-tool probe returned none. So the row answers without extended thinking, as Claude Opus 5's row does (the card's notes). The run's treatment fingerprint (`run_state.json`) records `answer_contract` `tool`, `tool_choice_mode` `forced` and `thinking.mode` `provider_default`.
- **Gauntlet.** The three-variable probe parsed 3/3 in 2 s. The full-scenario probe parsed 16/16 in 4 s. Both ran on the tool contract.
- **Board run.** The command was `policybench run --model claude-haiku-5.5 --max-workers 5 --budget-usd 25`, at `2f58a357`, on the frozen 100-household manifest.
  - It ran on 2026-10-08 from 21:41 to 21:47 UTC.
  - It finished 100 of 100 scenarios with 1,984 rows: no missing prediction, no missing explanation, no error row.
  - It cost $0.13. `run_state.json` records `spent_usd` 0.1274; the rows' `total_cost_usd` sums to $0.1299, with no estimated costs.
  - The median latency per household is 5.1 s: the median over households of the rows' summed `elapsed_seconds`, 5.11 s in the README.
  - The retry check (`response_retries/round_1`) found no unit to retry.
- **Pinned copy.** `haiku55-runs/haiku55/run` holds the run as it finished. `docs/haiku55/input_pins.json` pins its `predictions.csv` (`27a5e48f…8344`) and `run_state.json` (`42f82f50…bd4e`). Both equal `haiku55-stage/run`'s, and `stage.json` and `model-provenance.json` record the same predictions hash.
- **Sensitivity re-run.** A second run used `POLICYBENCH_TOOL_CHOICE=auto`, following `sensitivity/claude-thinking-2026-08.md` (`launch-auto-run.sh`, budget $10). Its purpose is to let the row carry the same auto chip as Opus 5 (README).
  - It ran from 21:42 to 21:52 UTC and finished 100 of 100 for $0.27. `haiku55-stage/auto-run/run_state.json` records `spent_usd` 0.2702 and `tool_choice_mode` `auto`.
  - It is not the board row.

## The judge plan

**What is re-judged.** `prepare` re-renders every case against the 47-model bundle and compares each prompt with the seed's. The stage's `prompt-changes.json` lists:
- 445 kept cases;
- 229 changed cases;
- 2 new cases.

So 231 cases are re-opened and need an Opus 5.5 verdict (`prepare.log`: "445 prompts unchanged, 229 changed and 2 new; 231 cases need Opus 5.5"). The stage's `audit/cases.jsonl` holds 988 cases: these 676, plus 312 parse-failure-only cases that no judge reads.

- All 231 re-opened cases list Claude Haiku 5.5 among their wrong models.
- The two new cases are outputs that only Claude Haiku 5.5 answers wrong: scenario_012 `child1_head_start_eligible` and scenario_067 `local_income_tax`.
- All ten ruled outputs are among the 229 changed cases, so each gets a new verdict in this stage for its adjudication to carry.
- Up to 47 models are wrong in one case, so a verdict must cover up to 47.

An installed build re-opens more cases. `install-references` renders the audit again with the build's references and explanations, sets aside every verdict whose prompt changes, and lists those cases as pending ("The engine upgrade"). These counts are the stage's before that step.

**The nine reworded cases.** A prompt renders the template, the reference value, the reference derivation (the case's reference explanation), the grounding, the question and each wrong model's answer and reasoning (`render_case_prompt`). It renders no exclusion, row annotation, case note or adjudication.

Release 20261006 reworded nine reference explanations after the seed was rendered: eight through its `annotation_rewrites.json` and scenario_031's through PR #197's `reference_audit/2026-10-05-medicaid-031-annotations/rewrites.json`. Its driver renders no prompt, so it carried the audit over unchanged. Those nine prompts therefore differ from the seed's whoever joins them.

`reworded_since_seed()` derives the nine from git by comparing `us_case_reference_explanations.csv` at `SEED_RELEASE_COMMIT` and at `BASE_COMMIT`. It refuses unless they are exactly `REWORDED_SINCE_SEED`:

- scenario_031 `head_medicaid_eligible`;
- `payroll_tax` for scenario_032, 043, 081 and 082;
- scenario_077 state income tax;
- scenario_081 federal income tax;
- scenario_114 federal and state income tax.

`check_prompt_changes` lets these nine change without the new model and refuses any other incumbent-only change. It also refuses if any of the nine fails to show a changed prompt. On this stage the allowance admits nothing extra. Claude Haiku 5.5 answers all nine wrong, so each is re-judged as a case it joins.

**Isolation.** Each judge runs through `scripts/run_audit_claude.sh`, as the GPT-6.1 Sol stage's isolated judges did:
- from an empty directory outside any git repository;
- with no tools and an allowlisted environment;
- with its transcript kept beside the verdict and checked.

The stage's runner log (`results/local/release-haiku55/judge-batch-1.log`) records `model=claude-opus-5-5 effort=xhigh parallel=2` on Claude Code 2.1.284. It also records a token login (`method` `oauth_token`, no account, no organization).

- The login is the `pb-judge` setup-token login, Max's opt-in of 2026-09-30. The runner is given the declared account `claude setup-token login (token sha256 6a6daf56361b), Max 2026-09-30`, and each sidecar records it. This login judged 42 of the GPT-6.1 Sol stage's isolated verdicts (group `isolated: setup-token 2` in `docs/gpt61sol/judge_provenance.json`).
- That login reached its weekly limit during this release's judging. The verdicts judged after that ran the same way on Subfleet lane claude-18's token, with the declared account `claude:max@axiom.org (subfleet lane claude-18)`. `PROVENANCE_GROUPS` maps each declared account to its group, and a verdict whose sidecar declares any other account has no group and is refused (`judge_provenance_record`).
- `CLAUDE_CONFIG_DIR` is `~/.policybench-judge/pb-judge-config`. The runner requires that it not be the desktop login's `~/.claude`. The desktop opt-in (`JUDGE_ALLOW_DESKTOP_LOGIN`) stays unset.
- `AUDIT_PARALLEL` is 2. `AUDIT_EFFORT` is unset, so each judge runs at the runner's default, `xhigh`. The driver's own `--step judge` runs one judge at a time (`AUDIT_PARALLEL=1` in `judge`).
- The first batch (`launch-judges-batch1.sh`, `AUDIT_ONLY` from `judge-batch-1.txt`) names 221 cases: the 231 re-opened cases minus the ten ruled ones. The ten need their verdicts before `adjudicate-exclusions`.

**Why the judge template does not change.** `policybench/audit.py` is the same blob (`0c947b1d`) at this branch's head, at `BASE_COMMIT`, at `SEED_RELEASE_COMMIT`, at release 20260929's `d616e67c`, on main, and at PR #200's head.

PR #200 removed the template's sentence saying earlier audits' bugs "were fixed before this run" (`bec3b244`). It then restored the sentence in the same PR (`738d6a69`), because removing it changes all 674 seed prompts. This driver carries a verdict over only when its prompt is the seed's byte for byte. Removing the sentence would therefore re-open every judged case or stop the fold. This branch takes only #200's evidence (`4a87c59c`). So the 445 carried verdicts and the 231 new ones all answer one template. The sentence's removal waits for a versioned judge template in a separate PR.

**Provenance record.** Export requires `docs/haiku55/judge_provenance.json` (`verify_judge_provenance`). It holds one entry per re-opened case, with:
- the staged verdict's and prompt's sha256;
- its group and its isolation;
- its sidecar's fields;
- no e-mail address.

`--step provenance` writes it from the stage's sidecars and checks it (`write_judge_provenance`). Run it after the last judge pass and commit the record before export. Its `counts` give the verdicts in each group.

**Earlier wording.** Triage rebuilds every row annotation and case note from three inputs: the verdicts, the staged adjudications and this stage's `wording-amendments.json`. An amendment may name only a re-opened case (`load_amendments`). Three records hold earlier corrections to that text:
- the committed `us_wording-amendments.json`: 394 amendments, of which 393 are in re-opened cases. The other one is scenario_067 SSI's reasoning, which the adjudication record keeps as committed;
- release 20261006's `annotation_rewrites.json`: 306 rewrites, all in re-opened cases (288 row annotations, 10 case notes, 8 explanations);
- PR #197's `rewrites.json`: 45 rewrites, all for scenario_031 `head_medicaid_eligible`, which is re-opened.

In the re-opened cases, the new verdicts' text replaces the corrected text. Review it against these corrections, and list in `$PB_STAGE/wording-amendments.json` any correction that is still needed. When the stage lists any amendment, the freeze commits the stage's list in place of release 20261006's record (`committed_amendments`).

## The ten exclusions

Sources:
- `docs/haiku55/spec.json`;
- `reference_audit/2026-10-05-reference-adversary/proposed_changes.json` (sha256 `3a6e5920…49bf`, as #200 merged it in 4db91b5f);
- `reference_audit/2026-10-05-louisiana/proposed_exclusions.json` (sha256 `a78120cd…2545`).

Values are rounded to cents; the records hold them in full. "Income tax" means the `…_income_tax_before_refundable_credits` output.

| Output | Ruling | Reason code (root cause) | Frozen | Alternative |
|---|---|---|---|---|
| scenario_018 (AZ) state income tax | d1022 | `reference_engine_defect` (`az_standard_deduction_indexing`) | 1,146.05 | 1,137.30 |
| scenario_025 (OH) state income tax | d1022 | `reference_engine_defect` (`oh_medical_deduction_premiums`) | 1,921.57 | 1,916.60 |
| scenario_043 (CO) state refundable credits | d1022 | `reference_engine_defect` (`co_sales_tax_refund_surplus`) | 19.00 | 0.00 |
| scenario_082 (NY) state refundable credits | d1022 | `reference_engine_defect` (`ny_cdcc_606_c2`) | 667.00 | 1,187.61 |
| scenario_093 (MO) federal income tax | d1022 | `reference_depends_on_unlisted_input` (`household_scope_dependent_returns`) | 8,628.99 | 11,848.99 |
| scenario_093 (MO) state income tax | d1022 | `reference_depends_on_unlisted_input` (same) | 3,388.25 | 4,528.08 |
| scenario_123 (PA) federal income tax | d1022 | `reference_depends_on_unlisted_input` (same) | 5,200.24 | 8,420.24 |
| scenario_123 (PA) state income tax | d1022 | `reference_depends_on_unlisted_input` (same) | 3,070.06 | 4,451.56 |
| scenario_051 (LA) state income tax | d994 | `reference_law_published_after_freeze` (`la_2026_standard_deduction_unpublished`) | 820.35 | 820.26 |
| scenario_077 (LA) state income tax | d994 | `reference_law_published_after_freeze` (same) | 305.14 | 305.05 |

Each record is dated 2026-10-06, decided by the developer and computed on policyengine-us 2.15.17. `spec_records` refuses any record that is not.

**The rulings** (`spec.json` `rulings`):

- d1022 excludes the reference adversary's four confirmed engine defects (verdict `CONFIRMED` in the proposal file).
  - These four are regenerated once a policyengine-us release fixes them. The spec's `regenerated_by_upgrade` names them with their upstream fixes (PolicyEngine/policyengine-us#9928, #10020, #9946 and #9948), and an installed build must regenerate exactly these four of the ten ("The engine upgrade").
  - d1022 also excludes the four outputs that rest on the dependent's own return, the one root cause the adversary left `AMBIGUOUS`. They stay excluded until d1029 settles the household scope for version 2.
  - The adversary's scenario_026 finding was refuted, and those references stand.
- d994 excludes the two Louisiana outputs. It keeps the published-amounts convention for every other reference: Idaho (076), SNAP (008, 038, 109) and Maryland (068) do not change.

**Why the Louisiana pair is later-published law.** These are the first two records with this reason code; release 20261006's 64 records use only the other two. Neither of the other codes fits:

- The prompt states every fact the computation uses, so no input is unlisted.
- The engine did not misapply the law. R.S. 47:294(B) multiplies 2025's $12,500 by the calendar-2025 CPI-U increase. PolicyEngine/policyengine-us#8411 computed $12,835 on 2026-05-24 from published CPI-U values ($12,500 × 324.054 / 315.605, rounded to the dollar). The records call that "a computation under the statute, not a forecast."

The statute sets no rounding rule and gives the Department no duty to publish the result:
- Before the 2026-07-03 freeze, Louisiana had published only its withholding and estimated-tax amount, $12,875, and said the amount allowed on 2026 returns would differ.
- Louisiana's first 2026 return amount, $12,838, came in Revenue Information Bulletin 26-019 on 2026-09-28, after the freeze.

So the reference rests on a figure that no Louisiana publication stated before the freeze, and the official figure came out after it. The alternative values are the references under $12,838.

The records' notes add evidence. The sweep reproduces all 1,928 references release 20260930 scored at $12,835 and moves only these two outputs. For each output, none of release 20260930's 46 models answered within $1 of the frozen value or of the value under $12,838. Under $12,500, 2025's amount, the values are $830.40 and $315.19, and 21 and 19 models answered within $1 of them.

**How the classes map.** `EXCLUSION_REASON_CODES` gives each reason code its adjudicated source and reference verdict. The spec gives the subtype, and `exclusion_entry` takes the reference basis from the record.

| Reason code | Adjudicated source | Reference verdict | Subtype | Reference basis |
|---|---|---|---|---|
| `reference_engine_defect` | `reference_engine_defect` | `engine_defect` | `taxable_income_or_deductions` (018, 025); `state_local_rule` (043, 082) | the record's `law` |
| `reference_depends_on_unlisted_input` | `prompt_ambiguity` | `unlisted_input` | `household_unit_or_filing_status` | the record's `unlisted_input` |
| `reference_law_published_after_freeze` | `reference_later_law` | `later_law` | `taxable_income_or_deductions` | the record's `published` |

**How they are installed.**
- `build_release_exclusions` takes release 20261006's record from git and adds the ten records, sorted by scenario and variable. They go after the earlier waves' records and before the audit's trailing scenario_023 record.
- It inserts the spec's `derivation_insert` sentence before the 2026-09-29 marker.
- Each proposal file must be the bytes the spec pins and must hold exactly the ruled outputs.
- `install-exclusions` writes the result into the stage's `scoring/` and bundle copies and rebinds it in `stage.json` (`exclusions_installed`). Judge prompts do not render exclusions, so the step can run before or after judging.
- The spec's `record_edits` then name each engine defect's upstream fix in the record's `upstream` field (PolicyEngine/policyengine-us#9928, #9946 and #9948, merged 2026-10-09; Ohio's #10020, open, with #9925 related), replacing the adversary's "to be filed". The installed record's sha256 is `release_exclusions_sha256()`, which `stage.json`'s `exclusions_installed` must match.

**How they are adjudicated.** `adjudicate-exclusions` runs after the judge and the restate script.

- Nine outputs get a new entry, in release 20261006's field order (`ENTRY_FIELDS`). Each carries its case's bound Opus 5.5 verdict from this stage.
- scenario_051 already has a decision: its reference was regenerated on 2026-09-22, and it was scored until this release. Its entry is restated in place:
  - the ruling's decision fields replace the old ones (`llm_error`/`thresholds_rates`/`regenerated` become `reference_later_law`/`taxable_income_or_deductions`/`later_law`);
  - `excluded_from_scoring` goes in after `adjudicator`;
  - the reasoning keeps the earlier text ahead of the ruling's.
- The record's date conventions name the 2026-10-06 wave and the day its decisions were written (`spec.json` `adjudications_written_on`).

Run the step once, after the last judge pass. A second run is refused. A new entry copies its case's verdict as it stands, and triage refuses any entry that no longer matches the bound verdict. After this step the restate script stops on the new entries, which name their current verdicts and carry no `judge_previous`. To re-judge a case later, put the staged `us_adjudications.json` back to release 20261006's, then run the restate script and this step again.

With a build installed, the step decides only the ruled outputs the build keeps excluded. It also decides the outputs the build newly excludes and drops the decisions of the release 20261006 records the build regenerated ("The engine upgrade").

## The engine upgrade

**The ruling.** Release 20261006's references were computed on policyengine-us 2.15.17. Max, 2026-10-09: "yes i want to wait for hte fixed engine" (`spec.json` `rulings`). The release moves the references to a newer policyengine-us release that fixes engine defects behind exclusions. An excluded output whose defect the new engine fixes is regenerated: its record is removed and it is scored again at the engine's value. Every other excluded output keeps the value it was decided on (rule 5).

**Which engine.** References come from the newest policyengine-us release when the reference sweep begins, and at publication PolicyBench checks that the newest release gives the same values (`ENGINE_RULE` in the builder). `reference_audit/2026-10-09-engine-upgrade/scripts/sweep_timing.py` records both:

- `sweep` reads PyPI and records each release's wheel upload time from the reference engine onward, the newest release at the read, and when the sweep wrote its first output. It refuses unless the reference engine was the newest release when the sweep began.
- `check` reads PyPI again before publication. It takes the reference build and refuses one that is not the release's: its sidecar must name the sweep's engine, pin its CSV and name the committed builder, its reference CSV, sidecar and exclusion record must be the committed snapshot's, and its `computed.csv` must give every scored reference, every value finite. When a newer release is out, `check` runs the check sweep itself, a first pass of this audit's builder in a venv holding that release (the builder refuses unless the venv holds it), then compares every output with the reference engine's, and counts scored and excluded outputs apart. Each input is pinned in the record by sha256. A newer release may move outputs that stay excluded. If it moves a scored output, `check` writes the record and exits non-zero, `engine_upgrade_timing_sentence` in `policybench/paper_results.py` refuses, so the paper does not render, and `tests/test_disclosures.py` fails.
- Both refuse a sweep whose output does not follow its engine: the wheel's upload, the install and the first output must come in that order. Both also check that the `policyengine_us` the venv imports is the release's wheel: its version, imported from the installed package, not an editable install, every package file at the hash the wheel's RECORD lists (sha256, sha384 or sha512), and no unrecorded importable file (module, sourceless bytecode or native extension) beside them. The check runs in the same process as the builder (`ENGINE_RUNNER`, through `run_on_engine`), launched with `-P` and a fresh, empty bytecode-cache prefix, so no stale bytecode or script-directory package can stand in for the verified source. `sweep_timing.py run` runs the reference build the same way, into a fresh out-dir with a fresh receipt, and refuses unless the builder writes a new `computed.csv`. The check refuses any symlink in the installed package, so installs must be copies (uv's default link modes; not `--link-mode=symlink`). The record keeps the check. A release whose wheels are all yanked is left out, and the record lists any such release newer than the reference engine.

Both write into `reference_audit/2026-10-09-engine-upgrade/verification/`.

**The build.** `reference_audit/2026-10-09-engine-upgrade/scripts/build_references_upgrade.py` reads release 20261006's references from git at `BASE_COMMIT`, recomputes all 1,984 outputs on the installed engine and writes four files: `reference_outputs.csv`, its sidecar, `reference_exclusions.json` and `reference_traces.json`. The sidecar keeps every earlier revision and gains one `engine_upgrade` revision. The builder takes an actions file in which every output that moves is decided:

| Action | What it decides | What the builder requires |
|---|---|---|
| `approved` | A scored output may move. | The engine gives the approved value within half a cent. |
| `regenerated_exclusions` | An excluded output with reason code `reference_engine_defect` is scored again. | The engine lands within the action's tolerance (at most $1; a flag must be equal) of the audited corrected value, which the action's `target` says how to know. `upstream` names the fix. |
| `new_exclusions` | A scored output that the new engine moves onto an input the prompt does not state leaves scoring. | A complete exclusion record, frozen at the engine's value, on the build's engine and day. |
| `excluded_rechecked` | An excluded output moves and stays excluded. | It keeps the value it was decided on. |
| `kept_exclusions_from_release` | The ruled outputs that stay excluded. | With the regenerated ruled outputs, they are exactly the spec's ten. |

The builder refuses an unexplained move, scored or excluded, and an action that does not describe what the engine does. `reference_audit/2026-10-09-engine-upgrade/actions_from_cells.py` drafts the actions from a first compute pass, with each regeneration's upstream fix taken from `upstreams.json` beside it. The builder refuses a draft, so a reviewer decides every action before the build.

**Regeneration targets.** A regenerated output must land on its audited corrected value. A target says how that value is known:

- `record`: the exclusion record's `alternative_value`. This is right when nothing else in the engine has moved the output since the record was decided.
- `fix_modules`: the value the record's audited fix modules (`reference_audit/2026-09-22/fixes`, at the bytes committed at `BASE_COMMIT`) give on a recent engine that still has the defect. A committed evidence file, written by the builder's evidence mode on that engine, holds the output there without and with the modules. The modules must move it beyond the tolerance there, which shows the defect was present. On the new engine the builder applies the modules again, and they must move the output by no more than the tolerance, which shows nothing is left to fix.

A fix module can load sibling files, and those run too. `policybench/fix_module_closure.py` finds them from the source: it follows `Path(__file__).with_name("<literal>")` and refuses a module that reaches local files any other way. The builder and the driver pin every module in the closure by sha256.

**Narratives.** `reference_audit/2026-10-09-engine-upgrade/scripts/narratives_upgrade.py` rewrites the reference explanation of each output the build changed and keeps every other row's bytes. The writer is the one every reference narrative uses (`policybench.case_reference_explanations`), given the build's engine trace and the change's recorded basis. A narrative must state the new reference value. `reference_audit/2026-10-09-engine-upgrade/hand_corrected_narratives.json` replaces the writer's text for the outputs it lists, and `hand_corrected_narratives.md` beside it gives the basis of each correction. With `--reuse-from`, an output whose writer inputs are the same as in an earlier build keeps that build's narrative, so its judge prompt and verdict survive a rebuild.

**Installing.** `--step install-references` takes the build, its explanations, its actions and the pinned grounding.

1. `load_build` gates the build against release 20261006 before anything is written:
   - the sidecar is release 20261006's with exactly one `engine_upgrade` revision added, from 2.15.17 to a newer engine (`upgrade_revision`);
   - the reference CSV differs from release 20261006's exactly in that revision's changed list (`reference_value_changes`);
   - the exclusion record is release 20261006's records, minus the regenerated ones, plus the kept ruled records, plus the records the actions newly exclude, and nothing else (`upgrade_exclusion_records`). The regenerated ruled records are exactly the spec's `regenerated_by_upgrade`;
   - each regeneration restates the one reviewed action that asks for it, with that action's tolerance, and its target holds when re-derived from the record or the committed evidence (`regeneration_action_problems`, `regeneration_target_problems`);
   - the traces cover every changed output, and the explanations differ from release 20261006's only on changed outputs (`explanation_changes`);
   - the actions name the build's engine, approve only listed moves and recheck exactly the excluded outputs the revision rechecks.
2. The audit the new references give is rendered in memory and held to `check_prompt_changes`' rule. A build that would re-open a case nothing explains is refused.
3. The build is kept verbatim in the stage's `reference-build/`. Its three reference files go into the scoring source and the bundle, and its explanations into the bundle's annotations. `stage.json` binds each file's sha256, the engine and the actions.
4. `prepare_audit` runs again in place. Every verdict whose prompt changes is set aside in `rejected-verdicts/` with its judge evidence, and every other verdict keeps its bytes. `prompt-changes.json` and `pending.json` are written anew.

Installing the same build again changes nothing. Another build replaces the first, and `stage.json` records the one it supersedes. A stage that never runs the step is staged on the 20261006 pins.

**After the install.** Every later step re-gates the installed build (`verify_installed_references`): the kept copy must be the bytes `stage.json` records, must still pass `load_build` against git and the spec, and the stage's files must be the build's.

- **Judging.** A case whose reference value or explanation the build changed may change or appear without the new model (`upgraded_cases`), and it is re-judged.
- **Adjudications.** `adjudicate-exclusions` decides the ruled outputs the build keeps excluded. It drops the decision of each release 20261006 record the build regenerated, as release 20260922c dropped scenario_045 SNAP's (#178), and records each drop in `stage.json` so that triage and the freeze hold the record to it (`drop_regenerated_adjudications`, `verify_recorded_drops`). It decides each output the build newly excludes from the spec's `upgrade_adjudications`, which must decide exactly those outputs (`upgrade_decisions`). Those decisions form their own wave, dated the revision's day, and the date conventions name the day they were written (`upgrade_adjudications_written_on`).
- **Triage decisions.** The spec may hold `triage_adjudications`: a developer's decision on a re-opened case whose verdict flags a reference the upgrade changed. Each affirms the reference, so the output stays scored. They are read only with a build installed. This release's spec holds none.
- **Scoring.** Every model is scored on 1,984 outputs less the build's exclusion records. The scope check puts back release 20261006's references and exclusion record together, and every incumbent's `modelStats` must then be release 20261006's (`export_on_base_references`).
- **The freeze.** `verify_upgrade` re-gates the build and the recorded drops, and requires the export receipt to bind every kept build file. The build's references, explanations and exclusion record are frozen byte for byte (`verify_references`, `verify_explanations`). `verify_fix_module_pins` in `scripts/freeze_snapshot.py` requires each fix module the revision pins to be the committed file at its path.
- **Judge evidence.** After the freeze, `scripts/date_haiku55_judge_verdicts.py` writes the verdict behind each committed decision on a re-opened case (`docs/haiku55/judge_verdicts_<day>.json`) and brings `reference_audit/2026-09-28/verification/judge_verdicts.json` up to this release.

## Commands

Run these from this checkout, one after another. The source paths are read-only.

```bash
export OPENBLAS_NUM_THREADS=1 PYTHONPATH="$PWD" PYTHONDONTWRITEBYTECODE=1
PB_PY="$PWD/.venv/bin/python"
PB_RUNS=/Users/maxghenis/PolicyEngine/policybench/results/local/haiku55-runs
PB_SEED="$PWD/results/local/release-haiku55/seed-20261006"
PB_GROUNDING=/Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit/grounding.csv
PB_STAGE="$PWD/results/local/release-haiku55/stage"
PB_RUN=us_full_run_20260612_policyengine_4_16_1_populace
PB_TAG=$("$PB_PY" -c 'import sys; sys.path.insert(0, "scripts"); import finish_haiku55 as d; print(d.RELEASE_TAG)')

# The run is $PB_RUNS/haiku55/run: completed == total == 100, stopped_reason
# null. Pin its files and commit docs/haiku55/input_pins.json before export
# (done in e3fde80d):
"$PB_PY" scripts/finish_haiku55.py --step pin-inputs --runs-root "$PB_RUNS"
"$PB_PY" scripts/finish_haiku55.py --step prepare \
  --runs-root "$PB_RUNS" --stage-dir "$PB_STAGE" \
  --audit-seed "$PB_SEED" --grounding "$PB_GROUNDING"
"$PB_PY" scripts/finish_haiku55.py --stage-dir "$PB_STAGE" --step install-exclusions
```

The judges bill a judge login only, never the desktop's. Run the runner directly to judge two at a time, or to name a batch with `AUDIT_ONLY`. This is the command of the stage's `launch-judges-batch1.sh`, without its log redirection:

```bash
env -i PATH="$PATH" HOME="$HOME" USER="$USER" LANG=en_US.UTF-8 \
  CLAUDE_CONFIG_DIR="$HOME/.policybench-judge/pb-judge-config" \
  CLAUDE_CODE_OAUTH_TOKEN="$(agent-secret get CLAUDE_CODE_OAUTH_TOKEN pb-judge)" \
  AUDIT_ACCOUNT="claude setup-token login (token sha256 6a6daf56361b), Max 2026-09-30" \
  AUDIT_MODEL=claude-opus-5-5 AUDIT_PARALLEL=2 AUDIT_PYTHON="$PB_PY" \
  AUDIT_ONLY="$(cat results/local/release-haiku55/judge-batch-1.txt)" \
  bash scripts/run_audit_claude.sh "$PB_STAGE/audit"
```

Leave `AUDIT_ONLY` out to judge every pending case, the ten ruled ones included. Then close the judging with the driver, with the same three login variables exported and `AUDIT_ONLY` unset. The driver validates every verdict, judges whatever is still pending one at a time, sets invalid and hedged verdicts aside in `rejected-verdicts/`, and repeats up to three times:

```bash
export CLAUDE_CONFIG_DIR="$HOME/.policybench-judge/pb-judge-config" \
  CLAUDE_CODE_OAUTH_TOKEN="$(agent-secret get CLAUDE_CODE_OAUTH_TOKEN pb-judge)" \
  AUDIT_ACCOUNT="claude setup-token login (token sha256 6a6daf56361b), Max 2026-09-30"
"$PB_PY" scripts/finish_haiku55.py --stage-dir "$PB_STAGE" --step judge
unset CLAUDE_CODE_OAUTH_TOKEN

# With an engine upgrade: build, write the narratives, install, then judge the
# cases the install re-opened (the same judge command, on the pending cases).
# $V is the policyengine-us version, $F a build directory holding a venv with
# that version, $U the audit directory.
U=reference_audit/2026-10-09-engine-upgrade
F_PY=(env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH="$PWD" "$F/venv/bin/python")
"${F_PY[@]}" "$U/scripts/build_references_upgrade.py" \
  --actions "$F/final_actions.json" --out-dir "$F/build"
"${F_PY[@]}" "$U/scripts/sweep_timing.py" sweep --engine "$V" --venv "$F/venv" \
  --first-output "$F/pass1/computed.csv"
ANTHROPIC_API_KEY="$(agent-secret get ANTHROPIC_API_KEY maxghenis)" \
  "${F_PY[@]}" "$U/scripts/narratives_upgrade.py" --references "$F/build" \
  --explanations "annotations/$PB_RUN/us_case_reference_explanations.csv" \
  --out "$F/us_case_reference_explanations.csv" \
  --hand-corrected "$U/hand_corrected_narratives.json"
"$PB_PY" scripts/finish_haiku55.py --stage-dir "$PB_STAGE" --step install-references \
  --built "$F/build" --explanations "$F/us_case_reference_explanations.csv" \
  --actions "$F/final_actions.json" --grounding "$PB_GROUNDING"

# Restate the adjudications of re-judged cases (writes only after checking).
# The script is the GPT-6.1 Sol release's, unchanged; the seed is 20261006's.
# It restates the 63 of release 20261006's 77 entries whose cases are re-opened,
# scenario_051 among them.
"$PB_PY" scripts/restate_gpt61sol_adjudications.py --stage-dir "$PB_STAGE" \
  --audit-seed "$PB_SEED"

# Needs adjudications_written_on in docs/haiku55/spec.json.
"$PB_PY" scripts/finish_haiku55.py --stage-dir "$PB_STAGE" --step adjudicate-exclusions
"$PB_PY" scripts/finish_haiku55.py --stage-dir "$PB_STAGE" --step triage
```

If triage stops, investigate `$PB_STAGE/reference-flags.csv` and `unresolved-rows.csv`.
- A new decision may decide only a case Claude Haiku 5.5 re-opened. Record it in `$PB_STAGE/publish/$PB_RUN/annotations/us_adjudications.json`, keeping the judge's exact class, then run `triage` again.
- The restate script restates a re-judged case's record, and `adjudicate-exclusions` writes a ruled output's. Neither is ever written by hand.
- Published wording is corrected only through `$PB_STAGE/wording-amendments.json`.
- No exclusion has a path in this release other than the ten and the ones an installed build's actions add. If another is needed, stop.

Write the provenance record and commit it, then export and freeze:

```bash
"$PB_PY" scripts/finish_haiku55.py --stage-dir "$PB_STAGE" --step provenance
"$PB_PY" scripts/finish_haiku55.py --stage-dir "$PB_STAGE" --step export
"$PB_PY" scripts/freeze_haiku55.py --stage-dir "$PB_STAGE" --dry-run
"$PB_PY" scripts/freeze_haiku55.py --stage-dir "$PB_STAGE"
"$PB_PY" scripts/date_haiku55_judge_verdicts.py --stage-dir "$PB_STAGE"
"$PB_PY" scripts/sensitivity_by_variable.py
"$PB_PY" scripts/rescore_sensitivity_summaries.py --release "$PB_TAG"
# With an engine upgrade, the publication check (add --check-venv, a venv
# holding PyPI's newest release, when that is not the reference engine; check
# runs the sweep on it):
"${F_PY[@]}" "$U/scripts/sweep_timing.py" check --build "$F/build"
# Update the note, paper prose, roster pins (47 models) and tests, then render
# and freeze again, which re-pins the rendered paper:
"$PB_PY" paper/render_paper.py
"$PB_PY" scripts/freeze_haiku55.py --stage-dir "$PB_STAGE"
```

`export` runs triage again. It then writes `data-board47.json` and a hash-bound `release-ready.json`.

The freeze is a local build and uploads nothing. Before it changes anything, `--dry-run` included, it checks:
- the receipt, the spec, the installed exclusions and the scored counts;
- the references and explanations;
- the verdicts, the provenance record, the adjudications and the annotations;
- the incumbents' predictions;
- the payload, which it rebuilds on a scratch copy.

It takes the snapshot date and the day the wave's decisions were written from the spec, and the tag from `RELEASE_TAG`. It then writes:
- the pointer, the version label and description, the snapshot and the annotations;
- the serving configuration, where the new row's evidence names `haiku55-runs/haiku55` (from the input pins);
- `$PB_STAGE/predictions.csv.gz`.

Then it checks what the freezer wrote (`verify_frozen`). The response window ends on the UTC day of the last recorded answer (`model_response_window`), here Claude Haiku 5.5's last one, at 2026-10-08 21:46:47 UTC. Release 20261006's window ended on 2026-09-29, so the window becomes 2026-06-12 (`MODEL_RESPONSE_START`) to 2026-10-08. The release assets are `predictions.csv.gz` and the staged payload, renamed to `dashboard-data.json`. Before uploading, check that the tag is still free.

The two sensitivity scripts rescore the five runs that `scripts/sensitivity_by_variable.py` lists (Fable 5, Opus 5, Sonnet 5 and Fable 5.1 with thinking, and Claude Haiku 5.5's `tool_choice` auto run) against the frozen board's scored outputs. They must run because the scored outputs change.

## What the gates enforce

Each gate refuses with `SystemExit` before anything is written outside the stage. Functions are in `scripts/finish_haiku55.py` unless a row says otherwise. Rows marked (freeze) name functions in `scripts/freeze_haiku55.py`.

F tests are in `tests/test_finish_haiku55.py`, Z tests in `tests/test_freeze_haiku55.py` and R tests in `tests/test_run_audit_claude.py`. The first table gives the gates of a stage without an installed build. The second gives the gates an engine upgrade adds, and says where an installed build changes a row of the first.

| Gate | Where | Pinned by |
|---|---|---|
| The run is complete: `completed == total > 0` as integers and no `stopped_reason`. The run state names `claude-haiku-5.5`, and `predictions.csv` is present. | `discover_new_models` | F `test_an_incomplete_or_stopped_run_is_refused`, `test_the_wrong_model_in_a_run_state_is_refused`, `test_a_missing_run_artifact_is_refused` |
| Claude Haiku 5.5's staged inputs are its pinned run. Export and the freeze read `docs/haiku55/input_pins.json` as committed at `HEAD` and refuse staged copies that differ. They re-check the prepare-time hashes in `stage.json` and `model-provenance.json`. They compare every column of its bundle rows with its run file, so its cost, tokens and latency are the run's. | `pin_inputs`, `committed_input_pins`, `verify_new_model_inputs`, `new_model_row_differences`, `export`, `freeze_haiku55.main` | F `test_pin_inputs_writes_the_finished_runs_file_hashes`, `test_the_input_pins_are_read_as_committed_at_head`, `test_the_committed_input_pins_are_the_finished_runs` (local), `test_export_writes_no_receipt_when_the_inputs_are_not_the_pinned_run`; Z `test_the_freeze_refuses_new_model_usage_edited_in_the_bundle`, `test_the_freeze_rechecks_the_prepare_time_hashes` |
| The base is 46 models, 1,984 outputs, 64 exclusions and 1,920 scored outputs, with the pinned payload and predictions, read from git at `BASE_COMMIT`. | `resolve_base`, `base_payload_from_commit`, `verify_base_predictions`, `base_exclusion_record` | F `test_the_git_base_must_rewrap_to_the_20261006_asset`, `test_the_base_commit_holds_release_20261006`, `test_the_base_exclusion_record_is_read_from_git_and_pinned` |
| The reference outputs, the scenarios and their two sidecars equal their 20261006 pins at every step. The exclusion record equals its 20261006 pin until `install-exclusions`. After that, export accepts in the bundle only the release's bytes. | `verify_reference_pins`, `resolve_base`, `release_exclusions_sha256`, `export` | F `test_a_reference_file_that_misses_its_pin_is_refused`, `test_export_accepts_only_the_release_exclusion_record` |
| The ten records are the ruled ones. Each proposal file is the bytes the spec pins and holds exactly the outputs its ruling names. There are ten, no two share an output, and each is a 2026-10-06 developer record on policyengine-us 2.15.17 with a known reason code. | `spec_records` | F `test_the_spec_names_each_ruling_and_its_outputs`, `test_a_proposal_file_off_its_pin_is_refused`, `test_a_record_outside_the_ruling_is_refused`, `test_two_proposals_cannot_rule_on_one_output` |
| The release's exclusion record is release 20261006's plus the ten. Every earlier record keeps its bytes and place, and the ten sit before the trailing scenario_023 record. No ruled output is already excluded. The derivation gains one sentence at its one marker. The loader accepts 74 records. | `build_release_exclusions`, `exclusions_text` | F `test_the_release_exclusions_are_the_base_plus_the_ten_ruled_records`, `test_the_ruled_records_come_out_in_one_order_whatever_the_files_order` (Hypothesis), `test_a_ruled_output_already_excluded_is_refused` |
| The installed record is the release's. The first install requires the stage to hold release 20261006's record. `adjudicate-exclusions`, triage and export refuse a stage whose `stage.json` does not record the release's hash. | `install_exclusions`, `main` | F `test_install_exclusions_rebinds_the_stage_and_is_idempotent`, `test_later_steps_refuse_a_stage_without_the_installed_exclusions` |
| Every judged verdict is bound to its own bytes. A case whose prompt is the seed's keeps the seed's verdict bytes; a failure there is refused, not re-judged. Every other verdict records the sha256 of the prompt it judged. The seed must match the committed digest. Every read of the seed re-derives kept, changed and added cases and refuses unless `prompt-changes.json` says the same. Invalid verdicts are set aside in `rejected-verdicts/`, never deleted. | `prepare_cases`, `bind_seed`, `load_seed`, `validate_verdicts`, `set_aside` | F `test_every_verdict_is_bound_to_its_own_bytes`, `test_a_carried_over_verdict_must_keep_the_seeds_bytes`, `test_prepare_refuses_a_seed_the_committed_digest_does_not_record`, `test_the_committed_seed_digest_is_the_pinned_one`, `test_the_committed_seed_digest_matches_the_real_seed` (local) |
| Only a case that Claude Haiku 5.5 joins, or one of the nine that release 20261006 reworded, may change or appear. The nine are derived from git and must be exactly the pinned set, and each must show a changed prompt. Any other incumbent-only change is refused, and so is a seed case that disappears. The staged predictions must bear out each re-opened case. | `check_prompt_changes`, `reworded_since_seed`, `verify_reopened_by_predictions` | F `test_an_incumbent_prompt_that_changes_is_refused`, `test_a_reworded_case_may_change_without_the_new_model`, `test_the_reworded_cases_are_exactly_those_git_shows`, `test_a_reworded_case_whose_prompt_did_not_change_is_refused`, `test_the_manifest_cannot_reopen_a_case_the_predictions_do_not` |
| The judge covers every wrong model in a case, up to all 47. A verdict that names Claude Haiku 5.5 needs hash-bound Opus 5.5 provenance and its prompt's sha256. | `validate_verdicts` | F `test_the_judge_must_cover_all_47_models_in_a_case`, `test_new_model_verdict_requires_bound_opus55_provenance` |
| The grounding is the pinned one. | `prepare_cases` (`GROUNDING_SHA256`) | F `test_prepare_refuses_a_grounding_other_than_the_pinned_one` |
| Each judge sees only its prompt and bills only the judge login. It runs in an empty directory outside git, with no tools, an allowlisted environment and one explicit effort. Its kept transcript must show nothing but the prompt and the structured answer. The login must not be the desktop's. | `scripts/run_audit_claude.sh` | R `test_each_judge_runs_isolated_on_the_lanes_login`, `test_the_runner_refuses_anything_but_the_lanes_own_login`, `test_every_judge_runs_at_one_explicit_effort`, `test_a_transcript_showing_more_than_the_prompt_is_rejected`, `test_account_data_anywhere_in_a_transcript_rejects_it_and_stops_the_run`, `test_a_login_that_cannot_judge_stops_the_run`, `test_audit_only_limits_the_run_to_the_named_cases` |
| The published judge provenance describes the staged new verdicts: each re-opened case once, with its hashes, its sidecar's fields, its isolation, and a transcript that passes the runner's checks, ported to Python. The R tests compare the runner with `finish_gpt61sol.py`'s port. This driver's port is the same code today (`account_data` through `withhold_addresses`), and an F test must keep it so. | `verify_judge_provenance`, `transcript_problems`, `export` | F `test_the_record_must_list_each_staged_new_verdict_once`, `test_each_entrys_fields_must_be_its_sidecars`, `test_this_drivers_transcript_gate_is_the_gpt61sol_drivers`; R `test_the_runner_and_the_driver_judge_transcripts_alike` |
| The decisions on the ten ruled outputs are exactly what `exclusion_entry` builds. A new decision is built from its case's bound verdict. scenario_051's is built from its 20261006 entry with the restated judge fields. The spec's classes must match each record's reason code, and the only existing decision among the ten must be the one the spec lists as restated. | `ruled_adjudication_problems`, `exclusion_entry`, `exclusion_adjudications`, `adjudicate_exclusions` | F `test_adjudicate_exclusions_appends_nine_entries_and_restates_scenario_051_in_place`, `test_triage_accepts_scenario_051_restated_then_ruled`, `test_a_ruled_entry_edited_by_hand_is_refused`, `test_adjudicate_exclusions_refuses_a_second_run`, `test_scenario_051s_ruling_moves_only_its_decision_fields`, `test_a_restated_decision_keeps_every_other_field_in_place` (Hypothesis) |
| Outside the ten, adjudications change only where Claude Haiku 5.5 re-opened a case. The baseline is release 20261006's record, read from git. A re-opened case may rewrite its judge fields as the restate script does, and its reasoning as a listed amendment says. No entry may be dropped or reordered, and a new entry may decide only a re-opened case. | `verify_adjudication_changes`, `verify_restatements`, `stage_adjudications`, `triage` | F `test_triage_lets_a_rejudged_case_restate_its_judge_fields`, `test_triage_refuses_any_other_change_to_a_recorded_decision`; Z `test_the_gate_allows_exactly_the_judge_fields_of_reopened_cases` (Hypothesis), `test_a_dropped_decision_is_refused` |
| The staged record's bytes are exactly its parsed content, and its note and schema are release 20261006's. Its date conventions are release 20261006's with the 2026-10-06 wave named once. | `verify_record_form`, `release_date_conventions` | F `test_the_date_conventions_name_the_2026_10_06_wave`, `test_the_wave_cannot_be_named_twice`, `test_triage_refuses_a_record_whose_bytes_hide_text` |
| The adjudications exclude exactly the 74 outputs that the installed record excludes. | `triage`, (freeze) `verify_adjudication_record` | F `test_the_adjudications_exclude_exactly_the_installed_exclusions` |
| Published wording changes only as `wording-amendments.json` lists, on re-opened cases, in a reasoning, a case note or one model's row annotation. | `load_amendments`, `stage_adjudications`, `amend_annotations` | F `test_triage_applies_exactly_the_listed_wording_amendments`; Z `test_a_listed_wording_amendment_is_allowed_and_nothing_else` |
| Every model is scored on 1,910 outputs. | `build_payload`, (freeze) `verify_scored_outputs` | F `test_every_model_is_scored_on_1910_outputs` |
| The scope check. With release 20261006's exclusion record put back, export of the staged bundle gives each of the 46 incumbents release 20261006's `modelStats` entry, byte for byte, key order included. A missing incumbent counts as drift. | `build_payload`, `incumbent_drift`, `release_20261006.export_payload` | F `test_the_scope_check_refuses_an_incumbent_change_the_ten_records_do_not_explain`, `test_incumbent_drift_is_exactly_the_changed_rows` (Hypothesis) |
| The export roster is exactly the 46 incumbents plus Claude Haiku 5.5. | `build_payload` | F `test_the_export_roster_must_be_the_incumbents_plus_the_addition` |
| After the freeze, a re-export reads the 20261006 payload from `BASE_COMMIT` and checks it against the base sha256. Any other pointer is refused. Once the live pointer names this release, the re-export accepts the frozen exclusion record. | `resolve_live_base`, `base_commit_blob`, `export` | F `test_a_re_export_after_the_freeze_reads_20261006_from_git`, `test_a_re_export_after_the_freeze_accepts_the_frozen_exclusion_record`, `test_any_other_pointer_is_refused` |
| The fold keeps every incumbent row and adds exactly 1,984 rows for the new model, with the reference key set. | `fold_board`, via `prepare_inputs` | F `test_the_fold_keeps_incumbent_rows_and_adds_1984_rows_for_the_addition` (Hypothesis) |
| The addition's treatment fingerprint matches the registry. | `validate_treatment` (in `freeze_adds0928.py`) | Z `test_the_registered_treatment_matches_the_run_and_a_drift_is_refused` |
| (freeze) The receipt names release 20261006 as its base (tag and payload sha256). It binds the payload, the tag and 47 models; the references and the installed exclusion record; the predictions, the adjudications, both annotation CSVs and the reference explanations; the run files, `model-provenance.json`, `prompt-changes.json` and `stage.json`; the amendments when the stage has them; and every judged case's verdict, sidecar and prompt, with its transcript where one exists. Evidence that changed after export is refused. | `export` writes it; `verify_receipt` checks it | Z `test_freeze_refuses_changed_or_unbound_evidence`, `test_the_receipt_must_bind_every_judged_case_and_both_annotation_csvs`, `test_the_default_tag_is_the_driver_release_tag` |
| (freeze) The spec names the release and the base this freeze builds: the tag, the base tag and the base sha256 the driver pins. It also gives a snapshot date and the day the wave's decisions were written. | `release_spec` | Z `test_the_freeze_refuses_a_spec_for_another_release_or_base`, `test_the_freeze_refuses_a_spec_without_its_dates` |
| (freeze) The stage scores on the release's exclusion record. The staged record must be `build_release_exclusions`' bytes, rebuilt from git and the spec. The receipt binds them, and `stage.json` records them as `install-exclusions` wrote them. The payload lists the 74 outputs in the record's order. | `verify_installed_exclusions`, `verify_scored_outputs` | Z `test_the_freeze_refuses_a_stage_without_the_installed_exclusions`, `test_the_payload_must_list_the_releases_exclusions_in_order` |
| (freeze) The reference outputs, the scenarios and their sidecars equal release 20261006's pins in the stage, in the committed snapshot and in the manifest. The staged exclusion record is the release's. Its committed copy and its manifest pin may be either release 20261006's or the release's, so a second freeze passes. The staged reference explanations are release 20261006's, from git. | `verify_references`, `verify_explanations` | Z `test_any_reference_value_revision_is_refused`, `test_a_second_freeze_finds_this_releases_exclusion_record`, `test_the_exclusion_record_is_release_20261006s_or_this_releases`, `test_a_reworded_explanation_is_refused` |
| (freeze) The staged payload is what export builds from the bound bundle. `build_payload`, with its scored-count and scope checks, runs on a scratch copy of the files the receipt binds, and its bytes must equal the staged payload's. | `rebuild_payload`, `build_payload`, `payload_text` | Z `test_the_freeze_refuses_a_payload_edited_after_export`, `test_the_rebuild_reads_only_the_bytes_the_receipt_binds`, `test_payload_differences_are_empty_exactly_when_the_bytes_match` (Hypothesis) |
| (freeze) Every verdict still passes the driver's gate against the bound seed, and the provenance record is the one export bound. The adjudication record passes the driver's gates again, against release 20261006's record in git. | `verify_verdicts`, `verify_judge_provenance`, `verify_adjudication_record` | Z `test_the_freeze_refuses_a_verdict_edited_after_export`, `test_the_freeze_refuses_a_dropped_adjudication_before_mutation`, `test_the_freeze_baseline_is_release_20261006_in_git_not_the_working_tree` |
| (freeze) The staged row annotations and case notes are what triage builds, in every column. | `verify_annotation_amendments`, `annotation_csv_text` | Z `test_the_freeze_refuses_any_column_triage_did_not_write` |
| (freeze) Every incumbent's prediction rows are release 20261006's, read from git. Every incumbent's serving row is release 20261006's, in every field. The new row's evidence is its run state and names the pinned run. | `freeze_haiku55.main`, `merge_serving`, `serving_problems`, `evidence_runs` | Z `test_the_freeze_reads_20261006_predictions_and_serving_from_git`, `test_an_incumbent_serving_row_that_changes_is_refused` |
| (freeze) The response window runs from the configured start to the UTC day of the last recorded answer. The freeze derives it before it writes anything. | `freeze_snapshot.model_response_window`, via `freeze_haiku55.main` | Z `test_the_freeze_refuses_what_the_freezer_wrote_outside_the_release` (its `window` case); `tests/test_model_response_window.py` |
| (freeze) What the freezer wrote is the release. The frozen references, exclusion record and annotations are the staged ones. The manifest differs from release 20261006's only under the listed paths, never at a pinned reference or the explanations. It states the snapshot date, 47 models, the response window, 74 exclusions, 1,910 scored outputs and the artifact. The live version's description counts the exclusions by engine. | `verify_frozen`, `manifest_problems`, `release_versions`, `verify_freezer_destinations` | Z `test_the_frozen_manifest_changes_only_where_the_release_may` (Hypothesis), `test_the_version_description_counts_the_releases_exclusions`, `test_release_versions_changes_nothing_when_applied_twice` |
| `RELEASE_TAG` is the only place the new tag is spelled out in the driver's scripts, its tests and this note. `spec.json` repeats it, and `release_spec` requires the two to agree. | `finish_haiku55.py`, (freeze) `release_spec` | F `test_the_release_tag_is_named_in_one_place` |

With an engine upgrade:

| Gate | Where | Pinned by |
|---|---|---|
| The build's sidecar is release 20261006's with exactly one `engine_upgrade` revision added, from 2.15.17 to a newer engine. Its CSV differs from release 20261006's exactly in the revision's changed list. | `load_build`, `upgrade_revision`, `reference_value_changes` | F `test_a_build_on_release_20261006_passes_every_gate`, `test_a_sidecar_that_is_not_20261006s_plus_one_upgrade_is_refused`, `test_a_real_builders_build_passes_the_drivers_gates` |
| Every scored move beyond $1 is approved, at the approved value within half a cent. | `load_build` | F `test_every_scored_move_beyond_a_dollar_needs_an_approval`, `test_an_approved_value_within_half_a_cent_passes` |
| The build's exclusion record is release 20261006's, less the regenerated records, plus the kept ruled records, plus the new ones. Only an engine defect is regenerated, and the regenerated ruled records are exactly the spec's. | `upgrade_exclusion_records`, `spec_regenerated` | F `test_the_release_record_is_exactly_base_less_regenerated_plus_kept_plus_new`, `test_only_an_engine_defect_can_be_regenerated`, `test_the_build_must_regenerate_exactly_the_specs_ruled_records`, `test_the_specs_regenerated_section_names_ruled_engine_defects` |
| A regeneration lands within its own tolerance of its audited target, and restates the one reviewed action that asks for it. The action's tolerance binds, not the revision's. | `regeneration_action_problems`, `regeneration_target_problems` | F `test_a_regeneration_lands_within_its_own_tolerance`, `test_the_actions_tolerance_binds_not_the_revisions`, `test_a_regeneration_must_restate_its_reviewed_action`, `test_a_regeneration_needs_exactly_one_action`, `test_a_regenerated_record_off_its_alternative_is_refused`, `test_module_inertness_uses_the_regenerations_tolerance` |
| A fix module's sibling files are found from its source, and a module that loads local files any other way is refused. | `policybench/fix_module_closure.py`, `committed_dependencies` | `tests/test_fix_module_closure.py`; F `test_a_target_module_whose_closure_cannot_be_established_is_refused` |
| An excluded output that stays excluded keeps the value it was decided on. One that moves is rechecked, with its reason. | `upgrade_exclusion_records`, `load_build` | F `test_a_rechecked_output_must_stay_excluded_at_its_value` |
| The explanations differ from release 20261006's only on changed outputs. | `explanation_changes` | F `test_explanations_must_differ_from_20261006s_only_on_changed_outputs` |
| The actions describe the build and are the ones it was built from. | `load_build`, `builder_claim_problems` | F `test_actions_that_do_not_describe_the_build_are_refused`, `test_actions_edited_after_the_build_are_refused` |
| The install re-opens only the cases whose prompts change, and refuses a build that would re-open any other. It refuses a tampered build, a stage off the base and another grounding, and writes nothing. | `install_references`, `classify_prompt_changes`, `verify_install_target` | F `test_install_references_reopens_only_the_cases_whose_prompts_change`, `test_the_upgrade_allowance_admits_only_the_cases_it_changed`, `test_install_references_refuses_a_tampered_build_and_writes_nothing`, `test_install_references_refuses_a_stage_off_the_base`, `test_install_references_refuses_another_grounding` |
| Every later step re-gates the installed build and takes the release's exclusion record from it. | `verify_installed_references`, `stage_upgrade` | F `test_later_steps_regate_the_installed_build`, `test_later_steps_take_the_releases_record_from_the_installed_build`, `test_export_holds_the_staged_references_to_the_installed_build`, `test_triage_holds_the_record_to_the_installed_upgrade` |
| The adjudications decide the kept ruled outputs and the outputs the build newly excludes, and drop exactly the regenerated records' decisions. The spec decides exactly the new exclusions, and their wave names the day it was written. | `adjudicate_exclusions`, `upgrade_decisions`, `drop_regenerated_adjudications`, `verify_recorded_drops` | F `test_adjudicate_exclusions_decides_the_kept_and_drops_the_regenerated`, `test_adjudicate_exclusions_refuses_a_record_deciding_a_regenerated_output`, `test_adjudicate_exclusions_decides_the_outputs_the_upgrade_excludes`, `test_the_spec_must_decide_exactly_the_upgrades_new_exclusions`, `test_the_upgrades_wave_needs_its_written_day`, `test_the_adjudication_gate_accepts_exactly_the_upgrades_drops`, `test_triage_requires_the_recorded_drops` |
| Every model is scored on 1,984 outputs less the build's exclusion records. With release 20261006's references and record put back, no incumbent's `modelStats` drifts. These replace the first table's rows on 1,910 outputs, on the 74 excluded outputs and on the scope check. | `build_payload`, `export_on_base_references` | F `test_with_an_upgrade_every_model_is_scored_on_1984_less_its_records`, `test_the_upgrade_scope_check_puts_back_the_base_references_and_record`, `test_the_upgrade_scope_check_refuses_incumbent_drift` |
| (freeze) The build's references, explanations and exclusion record are frozen byte for byte, in place of the first table's 20261006 pins. Scenarios stay release 20261006's. A dropped decision that the stage does not record is refused before anything is written. | `verify_upgrade`, `verify_references`, `verify_explanations` | Z `test_the_freeze_refuses_a_dropped_adjudication_before_mutation`, `test_a_dropped_decision_is_refused`, `test_without_an_upgrade_optional_arguments_preserve_existing_freeze_behavior`, `test_the_mock_setup_is_the_real_builders` |
| (freeze) Each fix module the revision pins is the committed file at its path. | `verify_fix_module_pins` (in `scripts/freeze_snapshot.py`) | `tests/test_snapshot_artifacts.py` `test_the_published_upgrades_pins_are_their_committed_bytes` |
| The reference engine was the newest release when the sweep began, and the publication check counts scored and excluded outputs apart. | `reference_audit/2026-10-09-engine-upgrade/scripts/sweep_timing.py` | `tests/test_sweep_timing.py` |

Some checks can run only on this machine, because they read the seed copy, the run directory or the main clone's grounding. These are marked (local). They should skip elsewhere, as the GPT-6.1 Sol release's do. Everywhere else, the committed seed digest and input pins stand in for them.

## Invariants

The tests state these as properties, alongside the example tests above.

1. **Scored count.** Without an installed build, every model is scored on 1,984 − 74 = 1,910 outputs. The 74 are the base's 64 plus the ten. With one, every model is scored on 1,984 less the build's exclusion records.
2. **Scope.** With the base's exclusion record substituted, every incumbent's `modelStats` is the base's, byte for byte. `incumbent_drift` returns exactly the incumbents whose serialized entry differs, and a missing incumbent counts as drift (Hypothesis).
3. **Exclusion record.** `build_release_exclusions(base, spec)` keeps every base record's bytes and order, adds ten records, and ends with the base's last record. Its output does not depend on the order of records inside a proposal file (Hypothesis).
4. **Installing twice changes nothing.** A second `install-exclusions` writes the same bytes and the same binding.
5. **A ruled decision moves only decision fields.** For any existing entry, `exclusion_entry` keeps every other field's value and place and sets the seven decision fields. It appends the ruling's reasoning to the entry's own. It refuses an entry that cannot hold all seven (Hypothesis). It is not idempotent, so `adjudicate-exclusions` refuses a second run.
6. **Date conventions.** `release_date_conventions` names the new wave once and refuses text that already names it.
7. **Adjudication scope.** Outside the ten ruled outputs, the gate accepts a staged record exactly when it differs from the base's only in re-opened cases' judge fields and listed reasoning amendments (Hypothesis).
8. **Carried verdicts.** Every kept case's verdict is the seed's, byte for byte. Every new verdict is bound to the prompt it judged.
9. **Response window.** The window's end is the UTC date of the latest `request_completed_at` in the staged predictions, and no recorded request falls outside the window.
10. **Installing a build twice changes nothing.** A second `install-references` of the same build writes the same bytes and the same binding, for any build (Hypothesis).
11. **The upgraded exclusion record.** It is the base's records less the regenerated ones, plus the kept ruled records, plus the new ones, with the base's order kept and its last record last.
12. **A regeneration lands.** A regenerated amount is within $1 of its target, and a regenerated flag equals it (Hypothesis). A regeneration's own tolerance binds where it is tighter.
13. **Excluded set.** With any set of dropped decisions, the adjudications exclude exactly the outputs the installed record excludes (Hypothesis).
14. **Closure.** For a module that loads siblings only by literal name, the closure is exactly those names, in source order (Hypothesis).
15. **Publication check.** A sweep compared with itself differs nowhere (Hypothesis).

## A reference flag answered during the engine-upgrade rehearsal

On the 2.37.2 rehearsal, an Opus 5.5 verdict on scenario_064 Wisconsin state income
tax (regenerated by policyengine-us #9801) flagged the reference. It hypothesized a $500
Wisconsin limit on net capital losses, under which the $18,235 net capital loss would
add $2,500 back to Wisconsin AGI. Claude Opus 5.5's answer applied that limit. The 2025
Wisconsin Schedule WD limits a net capital loss to the smaller of the loss, $3,000
($1,500 married filing separately) or Wisconsin ordinary income (line 28). policyengine-us
applies $3,000 from 2023
(`gov.states.wi.tax.income.additions.capital_loss.limit`), so the reference adds
nothing back and stands.

That verdict was set aside when the case's reference narrative was corrected
(`reference_audit/2026-10-09-engine-upgrade/hand_corrected_narratives.md`). The
case's current verdict raises no flag, so the release records no decision on it. The
spec's `triage_adjudications`, which `--step adjudicate-exclusions` applies when a
current verdict's flag needs one, is empty.
