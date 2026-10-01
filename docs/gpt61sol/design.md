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
stage. Test names are in `tests/test_finish_gpt61sol.py` (F),
`tests/test_freeze_gpt61sol.py` (Z) and `tests/test_run_audit_claude.py` (R).
Tests marked (local) need release 20260929's audit or its grounding on this
machine and skip anywhere else; see the note under the table.

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
| Every judged verdict is bound to its own bytes: its sidecar carries the verdict's sha256. A case whose prompt is the seed's carries its seed verdict over and must keep the seed's verdict bytes; any failure there is refused, not re-judged. Every other verdict must record the sha256 of the prompt it judged; the runner records it, and `scripts/stamp_gpt61sol_prompt_bindings.py` stamped the stage's first 134 re-judges only where each judge's own transcript shows `prompt.md`'s exact text. `prepare` binds the seed in `stage.json`, and `--step bind-seed` binds it for a stage prepared before that; the seed must match `docs/gpt61sol/seed_digest.csv` (each judged case's prompt and verdict sha256), whose bytes `SEED_DIGEST_SHA256` pins. Every read of the seed (`load_seed`, and so judge, triage, the freeze and `rejudged_cases`) re-derives kept, changed and added from the stage's prompts and refuses unless `prompt-changes.json` says the same, so a kept prompt that drifts or a case moved between the lists stops every step. When a prompt changes, `prepare_audit` drops its verdict. Invalid verdicts are set aside in `rejected-verdicts/`, never deleted. | `prepare_cases`, `bind_seed`, `load_seed`, `validate_verdicts`, `set_aside` | F `test_every_verdict_is_bound_to_its_own_bytes`, `test_a_carried_over_verdict_must_keep_the_seeds_bytes`, `test_an_edited_carried_over_verdict_is_refused_after_prepare`, `test_unchanged_incumbent_case_keeps_its_existing_judge`, `test_a_verdict_stays_bound_to_its_prompt_sha256`, `test_prepare_refuses_a_seed_the_committed_digest_does_not_record`, `test_load_seed_refuses_a_stage_without_a_binding_or_with_another`, `test_bind_seed_*`, `test_a_case_the_new_model_joins_is_rejudged_and_the_rest_carry_over`, `test_the_committed_seed_digest_is_the_pinned_one`, `test_the_committed_seed_digest_matches_the_real_seed` (local); `tests/test_stamp_gpt61sol_prompt_bindings.py` |
| Only a case that GPT-6.1 Sol joins may change or appear. An incumbent-only prompt that differs from the seed's is refused, and so is a seed case that disappears. `prompt-changes.json` lists the kept, changed and added cases. The manifest's claim is re-scored on every read of the seed: with `wrong_prediction_rows` over the staged predictions and references, a changed or added case must list GPT-6.1 Sol among its wrong models exactly when its prediction is wrong, and any other case it gets wrong must be parse-failure-only, so a kept case needs its prediction right. | `check_prompt_changes`, `verify_reopened_by_predictions` | F `test_an_incumbent_prompt_that_changes_is_refused`, `test_the_manifest_cannot_reopen_a_case_the_predictions_do_not`, `test_a_household_only_the_new_model_misses_becomes_a_new_case`, `test_check_prompt_changes_names_new_incumbent_only_cases`, `test_every_seed_prompt_rerenders_from_the_committed_snapshot` (slow) |
| The judge covers every wrong model in a case, up to all 46. A verdict that names GPT-6.1 Sol needs hash-bound Opus 5.5 provenance and its prompt's sha256. | `validate_verdicts` | F `test_the_judge_must_cover_all_46_models_in_a_case`, `test_new_model_verdict_requires_bound_opus55_provenance` |
| Each judge sees only its prompt and bills only the lane. It runs from a fresh empty directory outside any git repository, with every built-in tool removed (`--tools ""`) and the file, search, web and shell tools also denied by name, no MCP servers, skills, CLAUDE.md files or user settings (`--setting-sources project,local`), and an allowlisted environment (no API key, base URL, provider switch or keychain override reaches any claude call). Every judge runs at one explicit effort, `AUDIT_EFFORT` (default `xhigh`, the effort every turn of the stage's 17 first hardened re-judges recorded), by `--effort` and by environment; the caller's `CLAUDE_CODE_EFFORT_LEVEL` never reaches it. Its transcript is kept beside the verdict, and a verdict whose transcript shows any tool call but the structured answer, an unlisted context attachment, a session context that is not empty (an account e-mail, an organization or git status), a turn at another effort, an advisor model, or a working directory inside a git repository is rejected. The runner refuses to start unless `CLAUDE_CONFIG_DIR` names a directory other than the desktop login's `~/.claude` (by file identity) and `claude auth status`, run the same way, reports a first-party subscription login: the lane's token when one is set (then `AUDIT_ACCOUNT` must name the account, which a token login does not report), or a home login that is not the desktop's account. The one exception is Max's explicit opt-in of 2026-09-30, `JUDGE_ALLOW_DESKTOP_LOGIN=1`: the judges then run on the desktop's own claude.ai login with `CLAUDE_CONFIG_DIR` unset (the CLI finds that login only under its default directory), with no lane token and no `AUDIT_ACCOUNT`, and every sidecar declares `desktop login (JUDGE_ALLOW_DESKTOP_LOGIN, Max 2026-09-30)`; the rest of the isolation is unchanged. A judge the API refuses is logged with the CLI's error. A login that cannot judge stops the run (no further judge starts and the runner exits 1): the API refusing the login (HTTP 401, 403 or 429), or a transcript showing the login putting account context in the judge's context. Claude Code 2.1.284 adds the account e-mail (`session_context.userEmail`) and a `credential_org` record for any claude.ai login, the desktop's included, so on that version only a token login yields a clean verdict; the 2026-09-30 desktop trial's transcript shows both, and its login was refused 403 `oauth_not_allowed_for_organization`. Each sidecar records the login, the declared account, the effort level and the isolation. | `scripts/run_audit_claude.sh` | R `test_each_judge_runs_isolated_on_the_lanes_login`, `test_the_sidecar_binds_the_prompt_and_records_the_login`, `test_the_runner_refuses_anything_but_the_lanes_own_login`, `test_every_judge_runs_at_one_explicit_effort`, `test_the_desktop_opt_in_runs_on_the_desktop_login_and_records_it`, `test_the_desktop_opt_in_allows_the_desktops_own_login_only`, `test_a_verdict_from_a_judge_that_called_a_tool_is_rejected`, `test_a_transcript_showing_more_than_the_prompt_is_rejected`, `test_a_login_that_cannot_judge_stops_the_run`, `test_a_login_that_puts_account_context_in_the_judge_stops_the_run`, `test_a_scratch_directory_inside_a_git_repository_is_refused` |
| The published judge provenance, `docs/gpt61sol/judge_provenance.json`, describes the staged new verdicts. It lists every case GPT-6.1 Sol re-opened, each once, with the staged verdict's and prompt's sha256. Its `isolated` flag must match the sidecar: only the hardened runner writes `judge_isolation`. An isolated verdict's `claude.transcript.jsonl` must pass the runner's transcript checks, ported to Python with the source cited. Every call must be StructuredOutput, and exactly one may be accepted; any other is one the schema refused. No attachment may fall outside the runner's list, which rules out a skill listing and `credential_org`. The session context must be empty, the working directory outside git, every turn at the sidecar's effort, and no advisor model. Export refuses a disagreeing record before it writes anything. The receipt binds the record's sha256 and every staged transcript. | `verify_judge_provenance`, `transcript_problems`, `export` | F `test_a_verdict_whose_isolation_disagrees_with_the_record_is_refused`, `test_an_isolated_verdict_whose_transcript_fails_the_runners_checks_is_refused`, `test_the_record_must_list_each_staged_new_verdict_once`, `test_an_answer_the_schema_refused_and_the_judge_gave_again_passes`, `test_the_runners_attachment_allowlist_is_the_gates`, `test_export_writes_no_receipt_when_the_record_disagrees` |
| The grounding is the one the 20260929 audit used. | `prepare_cases` (`GROUNDING_SHA256`) | F `test_prepare_refuses_a_grounding_other_than_the_pinned_one`, `test_the_pinned_grounding_is_the_one_the_20260929_stage_used` (local) |
| The freeze refuses a receipt that does not name release 20260929 as its base (tag and payload sha256), or does not bind the payload, the tag, 46 models, the references, the adjudications, the run state, `prompt-changes.json`, `stage.json` and, when the stage has them, the wording amendments. It refuses evidence that changed after export. | `verify_receipt` | Z `test_freeze_refuses_changed_or_unbound_evidence`, `test_the_receipt_must_bind_*`, `test_wording_amendments_present_in_the_stage_must_be_bound`, `test_the_default_tag_is_the_driver_release_tag` |
| Adjudications change only where GPT-6.1 Sol re-opened a case. The baseline is release 20260929's record read from git at `BASE_COMMIT`, never the working-tree copy the freeze overwrites. Every committed entry keeps every field byte for byte, key order and entry order included, except that a case in `prompt-changes.json`'s changed or added lists may rewrite its judge fields (`JUDGE_FIELDS` in `scripts/restate_gpt61sol_adjudications.py`, the one definition) and its reasoning exactly as a listed wording amendment says. Rewritten judge fields must be the restate script's: the case's current bound Opus 5.5 verdict as judge, dated by its sidecar, with 20260929's `judge_previous` plus one item, the verdict 20260929's entry names (its seed verdict's judge, classes, flag and day, as the sha256-bound sidecar records them). The file's bytes must be exactly its parsed content in the committed form, with 20260929's note, schema and date conventions. A new entry may decide only a re-opened case; none may be dropped; the scoring exclusions stay the 56. Triage checks this in memory before it writes, and the freeze checks it again. The committed record excludes exactly the 56 and keeps every seed verdict's class. | `verify_adjudication_changes`, `stage_adjudications`, `triage`, `verify_adjudication_record` | F `test_triage_lets_a_rejudged_case_restate_its_judge_fields`, `test_triage_refuses_any_other_change_to_a_recorded_decision`, `test_triage_refuses_a_judge_rewrite_of_an_incumbent_only_case`, `test_the_committed_adjudications_exclude_exactly_the_scoring_exclusions`, `test_every_committed_adjudication_decides_a_case_the_seed_judged`, `test_the_committed_adjudications_keep_the_seed_judge_verdicts`, `test_each_20260929_entry_names_its_seed_verdict_as_its_sidecar_records_it` (local); Z `test_judge_fields_written_by_hand_are_refused`, `test_a_rejudged_case_may_be_restated`, `test_a_rewrite_of_an_incumbent_only_case_is_refused`, `test_triage_may_add_a_decision_that_keeps_the_output_scored`, `test_a_dropped_decision_is_refused`, `test_a_new_exclusion_is_refused`, `test_the_freeze_refuses_a_dropped_adjudication_before_mutation`, `test_the_freeze_baseline_is_release_20260929_in_git_not_the_working_tree` |
| Published wording changes only as `<stage>/wording-amendments.json` lists: case id, field, old text, new text and reason. The case must be re-opened. The field must be an entry's `reasoning`, the case note (`case_annotation`) or one model's row annotation (`annotation`, which names the `model`), so no amendment can touch a class, an exclusion or a score. The old text must occur exactly once. Triage applies the list in order (a later amendment may rewrite words an earlier one wrote, and the freeze chains them the same way); every case note must still carry its exact adjudication sentence. The freeze checks each case-note and row amendment is in the staged CSVs and commits the list beside the record. | `load_amendments`, `stage_adjudications`, `amend_annotations`, `verify_annotation_amendments`, `freeze_amendments` | Z `test_a_listed_wording_amendment_is_allowed_and_nothing_else`, `test_load_amendments_*`, `test_an_amendment_must_find_its_old_text_exactly_once`; F `test_triage_applies_exactly_the_listed_wording_amendments`, `test_triage_refuses_an_amendment_it_cannot_apply_exactly` |
| `RELEASE_TAG` is the only place the new tag is spelled out, in the driver's scripts, tests and this note. | `finish_gpt61sol.py` | F `test_the_release_tag_is_named_in_one_place` |

What the stage's amendments correct. The judge's prompt presents each
output's frozen reference as correct, but an excluded output keeps its frozen
value, which can rest on an engine projection that a publication convention
replaces, or on an engine defect. The app frames an excluded output's row with
"This audit note compares the answer with the frozen reference, which carries
the engine defect described above" (or "which assumes one reading of the
unlisted input described above"), and it does not display case notes. The
331 amendments in `wording-amendments.json` for the GPT-6.1 Sol stage change,
in re-opened cases only:
- text that calls an answer an error when a convention the caveat does not
  name makes it right (Idaho's held $4,811 zero bracket, SNAP's FY2026
  schedule held for October to December, California's 2025 amounts, the IRS
  2025 sales tax tables), and text that gives the engine's projection as the
  rule or the correct figure;
- text that states an engine defect as the law or as a reading of an input
  (Idaho's premium subtraction, New Jersey's worker contributions, the IRA
  active-participant phase-out, the heat-and-eat allowance behind 100 SNAP),
  and rows whose answer is the exclusion's corrected value;
- every row of the scored 118 state credits that states New York's repealed
  household-gross-income rule, and decision reasoning a re-judge made stale
  (008 state credits, 056 SNAP, 067 SSI).
They leave to the caveat the rows that compare an answer with the frozen
reference in an engine-defect or unlisted-input case, including rows whose
answer takes the other reading of an unlisted input. Each amendment was
checked against the record by an independent reviewer.

Checks that run only on this machine, because they read release 20260929's
audit (`adds0928-stage2/.../adds0928-v3/audit`) or the main clone's grounding:
`test_the_pinned_grounding_is_the_one_the_20260929_stage_used`,
`test_the_committed_adjudications_keep_the_seed_judge_verdicts`,
`test_the_committed_seed_digest_matches_the_real_seed` and the slow
`test_every_seed_prompt_rerenders_from_the_committed_snapshot`. They skip
elsewhere, so CI cannot fail them. What stands in for the seed everywhere
else is the committed digest: `test_the_committed_seed_digest_is_the_pinned_one`
and `test_every_committed_adjudication_decides_a_case_the_seed_judged` run
anywhere, and `prepare`, `bind-seed` and every later step check the seed and
the stage's binding against it.

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
184 of 184. `grounding.pre-r33b.csv` differs on `scenario_045` SNAP.
`docs/gpt61sol/seed_digest.csv` records the seed: the case id and the sha256
of the prompt and of the verdict for each of its 674 judged cases. After the
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

# A stage prepared before prepare bound the seed (this one) binds it once:
"$PB_PY" scripts/finish_gpt61sol.py --stage-dir "$PB_STAGE" --step bind-seed \
  --audit-seed "$PB_SEED"

# The judges bill the lane's own login only (see scripts/run_audit_claude.sh).
# A keychain-token lane points CLAUDE_CONFIG_DIR at an empty directory kept for
# the lane and passes its token; a home lane points it at its home.
export CLAUDE_CONFIG_DIR=<lane config dir> CLAUDE_CODE_OAUTH_TOKEN=<lane token> \
  AUDIT_ACCOUNT=<lane account>
# Or, by Max's opt-in of 2026-09-30 only, on the desktop's own claude.ai login
# (CLAUDE_CONFIG_DIR, CLAUDE_CODE_OAUTH_TOKEN and AUDIT_ACCOUNT all unset):
#   export JUDGE_ALLOW_DESKTOP_LOGIN=1
"$PB_PY" scripts/finish_gpt61sol.py --stage-dir "$PB_STAGE" --step judge

# Restate the adjudications of re-judged cases (writes only after checking).
"$PB_PY" scripts/restate_gpt61sol_adjudications.py --stage-dir "$PB_STAGE" \
  --audit-seed "$PB_SEED"

"$PB_PY" scripts/finish_gpt61sol.py --stage-dir "$PB_STAGE" --step triage
```

If triage stops, investigate `$PB_STAGE/reference-flags.csv` and
`unresolved-rows.csv`. A new decision may only decide a case GPT-6.1 Sol
re-opened: record it in
`$PB_STAGE/publish/$PB_RUN/annotations/us_adjudications.json`, keeping the
judge's exact class, then run `triage` again. A re-judged case's record is
restated by the restate script, never by hand. Published wording a re-judge
made wrong (a case note, a row annotation or a decision's reasoning that the
record contradicts) is corrected only through `$PB_STAGE/wording-amendments.json`,
which triage applies. An exclusion that moves has no path in this release:
stop instead.

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
