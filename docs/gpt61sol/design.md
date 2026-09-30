# GPT-6.1 Sol addition: design

## What the release is

This release adds GPT-6.1 Sol (`gpt-6.1-sol`, run slug `gpt61sol`) to the
45-model board of release `dashboard-data-20260929` (PR #182, merged to main
as `d616e67c`). The new board has 46 models. The 100 households, the 1,984
requested outputs per model and the references do not change: 1,928 outputs
are scored and 56 are excluded (28 engine defects, 28 unlisted inputs).
There is no reference revision. Every incumbent's `modelStats` entry must come
out byte-identical to the 20260929 payload.

The base is pinned in `scripts/finish_gpt61sol.py`. Each value was
recomputed from the files committed at `d616e67c`. The payload and
predictions were also checked against the published release assets' digests.

| Item | Value |
|---|---|
| Base tag, payload sha256 | `dashboard-data-20260929`, `a5cb9989…80a7` (123,362,946 bytes; the committed `data.json.gz` rewraps to it) |
| Models, outputs, exclusions, scored | 45, 1,984, 56 and 1,928 |
| `reference_outputs.csv` | `e8bbba8f…2466` |
| `reference_outputs.csv.meta.json` | `816fef53…1a4b` |
| `reference_exclusions.json` | `bf4e6a24…81c2` |
| `scenarios.csv` | `71b16212…858a` |
| `scenarios.csv.meta.json` | `03a66e90…aebb` |
| `BASE_COMMIT` | `d616e67c…` (the merge of PR #182 on main) |

The new release's tag is `RELEASE_TAG` in `scripts/finish_gpt61sol.py`, and
nothing else names it. `freeze_gpt61sol.py --tag` defaults to it, and the
commands below read it into `$PB_TAG`. The export receipt binds the tag. If
you change `RELEASE_TAG`, run `--step export` again before you freeze.

## What the gates enforce

Each gate refuses with `SystemExit` before anything is written outside the
stage. Test names are in `tests/test_finish_gpt61sol.py` (F) and
`tests/test_freeze_gpt61sol.py` (Z).

| Gate | Where | Pinned by |
|---|---|---|
| The run is complete, with `completed == total > 0` as integers and no `stopped_reason`. The run state names `gpt-6.1-sol`. `predictions.csv` is present. | `discover_new_models` | F `test_an_incomplete_or_stopped_run_is_refused`, `test_the_wrong_model_in_a_run_state_is_refused`, `test_a_missing_run_artifact_is_refused` |
| The five reference files equal their 20260929 pins. `prepare` checks the committed copies first, then the staged copies. `export` checks both again. The freeze checks the staged copies, the committed copies and the manifest pins, and after it writes the snapshot it checks the frozen copies. | `verify_reference_pins`, `resolve_base`, `prepare_inputs`, `export`, `verify_references` | F `test_a_reference_file_that_misses_its_pin_is_refused`, `test_resolve_base_checks_the_committed_pins_before_anything_else`, `test_export_refuses_a_*_reference_off_its_pin`, `test_the_committed_references_match_their_pins`; Z `test_any_reference_revision_is_refused`, `test_the_freeze_refuses_a_revised_staged_reference_before_mutation` |
| The base is 45 models, 1,984 outputs, 56 exclusions and 1,928 scored outputs, with the pinned payload and predictions. | `resolve_base`, `base_payload_from_commit` | F `test_the_git_base_must_rewrap_to_the_20260929_asset`, `test_the_base_commit_holds_release_20260929`, `test_the_committed_references_match_their_pins` |
| No incumbent drift. For all 45 incumbents, the exported entry serialized by `json.dumps` must equal the base entry byte for byte, key order included. A missing incumbent counts as drift. No drift is tolerated. | `incumbent_drift`, `export` | F `test_the_no_drift_gate_refuses_any_change_to_any_incumbent` and `test_incumbent_drift_is_exactly_the_changed_rows` (both Hypothesis) |
| The export roster is exactly the 45 incumbents plus GPT-6.1 Sol. | `export` | F `test_the_export_roster_must_be_the_incumbents_plus_the_addition` |
| After the freeze, a re-export reads the 20260929 payload from `BASE_COMMIT` and checks it against the base sha256. Any other pointer is refused. A missing commit is named, and the error says to fetch full history. | `resolve_live_base`, `base_commit_blob` | F `test_a_re_export_after_the_freeze_reads_20260929_from_git`, `test_base_commit_blob_names_*`, `test_any_other_pointer_is_refused` |
| The fold keeps every incumbent row. It adds exactly 1,984 rows for the new model, with the reference key set. | `fold_board`, via `prepare_inputs` | F `test_the_fold_keeps_incumbent_rows_and_adds_1984_rows_for_the_addition` (Hypothesis; see its note on column types) |
| The addition's treatment fingerprint matches the registry. | `validate_treatment` (reused from `freeze_adds0928.py`) | Z `test_the_registered_treatment_matches_the_run_and_a_drift_is_refused` |
| Verdicts carried over from the seed stay bound to their prompt. When a prompt changes, `prepare_audit` drops its verdict. A sidecar that records a `prompt_sha256` must match the current `prompt.md`. The receipt pins every prompt alongside its verdict. | `prepare_audit`, `validate_verdicts`, `export` | F `test_a_verdict_stays_bound_to_its_prompt_sha256`, `test_a_case_the_new_model_joins_is_rejudged_and_the_rest_carry_over` |
| Only a case that GPT-6.1 Sol joins may change or appear. An incumbent-only prompt that differs from the seed's is refused, and so is a seed case that disappears. `prompt-changes.json` lists the kept, changed and added cases. | `check_prompt_changes` | F `test_an_incumbent_prompt_that_changes_is_refused`, `test_a_household_only_the_new_model_misses_becomes_a_new_case`, `test_check_prompt_changes_names_new_incumbent_only_cases`, `test_every_seed_prompt_rerenders_from_the_committed_snapshot` (slow) |
| The judge covers every wrong model in a case, up to all 46. A verdict that names GPT-6.1 Sol needs hash-bound Opus 5.5 provenance. | `validate_verdicts` | F `test_the_judge_must_cover_all_46_models_in_a_case`, `test_new_model_verdict_requires_bound_opus55_provenance` |
| The grounding is the one the 20260929 audit used. | `prepare_cases` (`GROUNDING_SHA256`) | F `test_prepare_refuses_a_grounding_other_than_the_pinned_one`, `test_the_pinned_grounding_is_the_one_the_20260929_stage_used` |
| The freeze refuses a receipt that does not bind the payload, the tag, 46 models, the references, the adjudications and the run state. It refuses evidence that changed after export. | `verify_receipt` | Z `test_freeze_refuses_changed_or_unbound_evidence`, `test_the_receipt_must_bind_*`, `test_the_default_tag_is_the_driver_release_tag` |
| Adjudications change only through a staged record. Triage must apply it and export must bind it. A record may add decisions or restate a re-judged class. It may not drop a decision or move the scoring exclusions. The committed record excludes exactly the 56 scoring exclusions and keeps every seed verdict's class. | `triage`, `verify_adjudication_record` | F `test_the_committed_adjudications_exclude_exactly_the_scoring_exclusions`, `test_the_committed_adjudications_keep_the_seed_judge_verdicts`; Z `test_triage_may_*`, `test_a_dropped_decision_is_refused`, `test_a_new_exclusion_is_refused`, `test_the_freeze_refuses_a_dropped_adjudication_before_mutation` |
| `RELEASE_TAG` is the only place the new tag is spelled out, in the driver's scripts, tests and this note. | `finish_gpt61sol.py` | F `test_the_release_tag_is_named_in_one_place` |

The exporter still needs the Fable 5 usage carry-over. Fable 5 ran through the
Anthropic batch adapter, and its committed rows carry no cost, token or latency
fields, so `export_full_run` reports `costUsd` $0 and omits the rest. The live
payload has $54.11, 3,850,174 tokens and 97.68 s. The driver copies those four
values from the base, and the drift gate then checks every field and the key
order. Ox Alpha's `costUsd` of $0.0 comes out of the exporter unchanged, so it
needs no special handling. The drift gate refuses it if it goes missing or
changes sign.

## Audit seed and grounding

The seed is the 20260929 stage's audit:
`/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/results/local/adds0928-v3/audit`.
It has 986 cases, 674 of them judged with prompts. It is exactly the audit
that release 20260929's export receipt binds. The stage's `release-ready.json`
(payload `a5cb9989…`) binds 2,024 audit files, and every one matches. The
stage's annotations equal the committed ones. `stage.json` does not record the
grounding. `finish_adds0928.py` takes it from `--grounding`, and the stage-2
commands passed `$PB_AUDIT/grounding.csv`, which is the main clone's
`results/local/unified_audit/grounding.csv` (sha256 `b1e4a9bc…b55c`).

I checked this read-only. Every grounded seed prompt carries that file's text:
184 of 184. `grounding.pre-r33b.csv` differs on `scenario_045` SNAP. After the
merge of #182 (`d616e67c`), I rendered the prompts again from the committed
snapshot with that grounding. All 674 seed prompts came out byte-identical, all
986 case ids matched, and `cases.jsonl` was byte-identical. The slow test
`test_every_seed_prompt_rerenders_from_the_committed_snapshot` repeats this
check.

#182's review excluded `scenario_023` `head_medicaid_eligible` as an audit
exclusion. It is listed in `reference_audit/2026-09-28/final_actions.json`;
its reference value did not move. The review also rewrote the case's
adjudication, row annotations and case note. None of them changes its prompt:

- A prompt renders the reference value, the reference explanation, the
  question, the grounding, and each wrong model's answer and reasoning.
- Row annotations reach only the manifest's `recorded_failure_sources`.
- Case notes and adjudications are not read at all.

So the case's prompt is still `339d113a…`, the `prompt_sha256` that its Opus
5.5 verdict is bound to. The verdict carries over unless GPT-6.1 Sol answers
the case wrong. In that case the prompt changes and the case is re-judged like
any other case the model joins. If the re-judge changes the class, restate it
in the case's adjudication record, which keeps `excluded_from_scoring` (see
below). So `prepare` re-judges exactly the cases GPT-6.1 Sol joins or opens,
and nothing else.

## Commands

Run these from this checkout, one after another. The source paths are read-only.

```bash
export OPENBLAS_NUM_THREADS=1 PYTHONPATH="$PWD" PYTHONDONTWRITEBYTECODE=1
PB_PY=/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/.venv/bin/python
PB_RUNS=/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609
PB_SEED=/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/results/local/adds0928-v3/audit
PB_GROUNDING=/Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit/grounding.csv
PB_STAGE="$PWD/results/local/gpt61sol-v1"
PB_RUN=us_full_run_20260612_policyengine_4_16_1_populace
PB_TAG=$("$PB_PY" -c 'import sys; sys.path.insert(0, "scripts"); import finish_gpt61sol as d; print(d.RELEASE_TAG)')

# The run is $PB_RUNS/gpt61sol/run: it must show completed == total == 100,
# stopped_reason null, and a combined predictions.csv.
"$PB_PY" scripts/finish_gpt61sol.py --step prepare \
  --runs-root "$PB_RUNS" --stage-dir "$PB_STAGE" \
  --audit-seed "$PB_SEED" --grounding "$PB_GROUNDING"

# Run inside a Claude subscription lane (see scripts/run_audit_claude.sh).
"$PB_PY" scripts/finish_gpt61sol.py --stage-dir "$PB_STAGE" --step judge

"$PB_PY" scripts/finish_gpt61sol.py --stage-dir "$PB_STAGE" --step triage
```

If triage stops, investigate `$PB_STAGE/reference-flags.csv` and
`unresolved-rows.csv`. Record reviewed decisions in
`$PB_STAGE/publish/$PB_RUN/annotations/us_adjudications.json`, keeping the
judge's exact class, then run `triage` again. If an adjudicated case is
re-judged because GPT-6.1 Sol joins it, restate the new judge class in its
record. An exclusion that moves has no path in this release: stop instead.

```bash
"$PB_PY" scripts/finish_gpt61sol.py --stage-dir "$PB_STAGE" --step export
"$PB_PY" scripts/freeze_gpt61sol.py --stage-dir "$PB_STAGE" --dry-run
"$PB_PY" scripts/freeze_gpt61sol.py --stage-dir "$PB_STAGE"
"$PB_PY" scripts/sensitivity_by_variable.py
"$PB_PY" scripts/rescore_sensitivity_summaries.py --release "$PB_TAG"
# Update the note, paper prose, roster pins (46 models) and tests, then:
"$PB_PY" paper/render_paper.py
"$PB_PY" scripts/freeze_snapshot.py --rendered-only
```

`export` writes `data-board46.json` and a hash-bound `release-ready.json`. The
freeze is a local build and uploads nothing. It writes the pointer, the version
label, the snapshot, the annotations, the serving configuration (the new row's
evidence is `adds202609/gpt61sol`) and `$PB_STAGE/predictions.csv.gz`. The
release assets are that file and the staged payload, renamed to
`dashboard-data.json`. Before uploading, check that the tag is still free.

Optional rehearsal while the run is in progress. It works on a scratch copy and
is marked PARTIAL; no receipt is ever written for it:

```bash
"$PB_PY" scripts/snapshot_gpt61sol.py --runs-root "$PB_RUNS" \
  --out-dir "$PWD/results/local/gpt61sol-partial-copy"
# In the copy only, set total = completed in gpt61sol/run/run_state.json, then:
"$PB_PY" scripts/finish_gpt61sol.py --runs-root "$PWD/results/local/gpt61sol-partial-copy" \
  --stage-dir "$PWD/results/local/gpt61sol-partial-stage" --early --partial
```
