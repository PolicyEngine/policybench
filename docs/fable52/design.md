# Claude Fable 5.2 release mechanics

The release driver is `scripts/finish_fable52.py`; `scripts/freeze_fable52.py` freezes its bound stage. The release adds the `fable52/run` supervised run, display id `claude-fable-5.2` and provider id `claude-fable-5-2`, to release `dashboard-data-20261027`. It also applies Max's ruling d2180, which takes scenario_122's Minnesota `state_refundable_credits` out of scoring for every model. It installs no reference build. The board has 52 models, 1,984 requested outputs, 50 exclusions and 1,934 scored outputs per model. This document describes the release machinery. The lead writes every statement about the resulting scores, judgments and checks.

## Base and inputs

`BASE_COMMIT` is `875fe1f6f59f4d584b500ca193b60838d3bdf14c`, PR #247's squash merge. The run directory, annotations and `reference_audit/held_references.json` at main's `7ffbee7c`, and at this branch's head, equal that commit's bytes (`git diff --quiet`). The payload pin covers the published wrapper that holds `countries.us`; the compact snapshot stores that country payload inside `data.json.gz`, and the driver rebuilds the wrapper to check the pin.

| Input | SHA256 |
| --- | --- |
| Published base payload, 138,702,498 bytes | `67cb0d14ca93cefaeaf2678ef6e6f81aea1858bb7b23b1b61d24c46fe378021b` |
| Base `reference_outputs.csv`, on policyengine-us 2.60.0 | `eab09a0c184c14b0c33679d9ac132d6f1de720c439ac30685a67ca38655184cb` |
| Base reference sidecar | `55c17fe298f9ac09ff56b2187d1d314ede7d239e94924da6abb6e0ad2542260c` |
| Base exclusion record, 49 records | `91408c0f3d49e1984b436164a047f8cedc3e501feb2099ba0e7d2782ee8ac73d` |
| `scenarios.csv` | `71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a` |
| Scenario sidecar | `03a66e90b86e9bd0cc77f27520784bd581777762f749675dc716e24c1b8eaebb` |
| Base adjudications, 63 entries | `85db9ed6fff06bf01cf4c3d7af5e073bbbff0c68dd2e178c31da1ad919f14c8f` |
| Grounding | `b1e4a9bc74d762f410524a147efcda7d705c3afcfa3dc27f720fa60c54a7b55c` |
| `docs/fable52/seed_digest.csv`, 681 cases | `b9d72535deba713324d2c256a57437b06be2c9d3efd3bda723bddf0ac721dd3c` |
| `docs/fable52/proposed_exclusions.json`, d2180's record | `fb119fa83f6e399ecb58f88e574dd9b5269026a1373bf7ae4ebe85d65503d468` |
| The release's exclusion record, 50 records (`release_exclusions_sha256()`) | `7b965a303e809c095a80679ebe981a75354138963e4ee75d14e4a475b3ef90f0` |

The seed is `/Users/maxghenis/reviews/policybench-gpt-6-1-terra/worktree-results/stage/audit`; the `README.md` in `worktree-results` identifies it as release 20261027's judged audit. `seed_digest.csv` hashes each case's prompt and verdict. The driver binds that digest and refuses another seed or grounding. The run stays read-only at `/Users/maxghenis/PolicyEngine/policybench/results/local/fable52-runs/fable52/run`; `pin-inputs` writes its predictions and run-state hashes to `docs/fable52/input_pins.json`, which the lead commits before export and the freeze.

## Changes from Terra's driver

**What carries over.** The driver starts from `finish_terra.py`, so Terra's later fixes hold: the judge identity and per-case schema gates, the judge transcript and provenance gates, the by-model guards and the reader that opens only the bound combined `us/predictions.csv`, the export's scratch copy and its promotion of every bound file triage changed, the release-stage requirement (`require_release_stage`), the receipt's repository-input bindings and the seed binding. `MODELS` holds only `{"fable52": "claude-fable-5.2"}`. `RELEASE_TAG` has one definition in the driver, and the spec and the freeze must agree with it; the lead may change that constant and the spec's `release_tag` together at freeze time. Template v2 renders every new or re-opened case. Carried verdicts keep the template version their sidecars record and their exact seed bytes, and the driver refuses a verdict without a sidecar. `CARRIED_USAGE` keeps the published Fable 5 cost, tokens and latency in their original key order. PR #230's rule prices an uncosted row only when it recorded both prompt and completion tokens. PR #231's `live_calls`, `cache_hit_calls` and `live_elapsed_seconds` columns must survive the fold, and preparation restores every Claude Fable 5.2 cell from its source CSV after folding and checks every column as exact text.

**What goes with the install.** This release changes no engine, so the driver drops Terra's `install-references` step and the gates that served only it:

- loading and gating a reference build against the base: `load_build`, `upgrade_revision`, `upgrade_exclusion_records`, `declared_exclusions`, `reference_value_changes`, `explanation_changes`, the regeneration and fix-module gates and `builder_claim_problems`;
- rebuilding the reference narratives (`committed_build_sources`) and rendering the audit with the build's references (`render_audit_with`, `recorded_versions`);
- binding the installed build and gating it again: `references_record`, `bind_build_exclusions`, `install_references`, `verify_installed_references` and `verify_install_target`;
- the upgrade's cases and decisions: `upgraded_cases`, `upgrade_decisions`, `upgrade_wave`, `spec_regenerated`, `drop_regenerated_adjudications` and `verify_recorded_drops`;
- the upgrade's scope export on the base's references (`export_on_base_references`) and its check that confined incumbent changes to the four approved moves;
- the `--built`, `--explanations` and `--actions` options.

**What checks the base instead.** Where a Terra gate checked something the installed build made true, this driver checks the base's state:

- `verify_reference_pins`: the staged and committed reference outputs, their sidecar, the scenarios and their sidecar equal release 20261027's pins at every step. The exclusion record equals its pin until `install-exclusions` and the release's bytes after it, and the committed one becomes the release's once the freeze moves the pointer.
- `verify_base_engine`: the committed sidecar carries its pin, its last revision names policyengine-us 2.60.0, and `pyproject.toml` and `uv.lock` pin that release (`verify_engine_pins`, which Terra ran against its build's engine).
- `verify_publication_record`: the audit's publication check record (`publication_check` in `reference_audit/2026-10-22-engine-upgrade/verification/sweep_timing.json`) names policyengine-us 2.60.0, or a newer engine on which no scored output moved (`scored_differ` empty). It must also name release 20261027's three reference files, the committed builder at its pin, and each build file at the bytes of the committed `reference-build/`. Terra's `load_build` checked the same record against its build.
- `stage_upgrade`: a stage whose `stage.json` records `references_installed`, or that holds `reference-build/` or `reference-install.json`, came from another release's driver, and every step refuses it. It also runs the two checks above. Prepare runs them before it reads anything, and every later step runs them through `stage_upgrade`.

**The seed.** Terra's bind-seed bound the seed, before prepare, into the `reference-install.json` its install step wrote. This driver writes nothing before prepare. On a missing `stage.json`, bind-seed checks the seed against `seed_digest.csv` and the grounding against its pin and writes nothing (`check_seed`); prepare then checks and binds the seed in `stage.json` itself. On a stage prepared before prepare bound the seed, bind-seed binds it as Terra's did.

**The spec.** `load_spec` refuses any key outside the set this driver reads (`SPEC_KEYS`), so an install's `upgrade_adjudications` cannot sit in the spec unread. `adjudications_written_on` must be a real `YYYY-MM-DD` day on or after the ruling's and the ruled verdict's day, and no later than the day `adjudicate-exclusions` runs (`verify_written_days`). `triage_adjudications_written_on` must meet the same tests against the triage wave's day and its cases' verdicts, and the freeze reads it whenever the spec lists a triage decision. The record gate refuses the `[LEAD: …]` placeholder for either.

**The export's scope check.** Haiku 5.5's and Terra's exports held the incumbents with one check: put the base's exclusion record back in a scratch copy, export again, and every incumbent's `modelStats` must equal the base's byte for byte. This driver keeps that check. It adds a second one, `exclusion_scope_problems`, new code in this driver, which compares the release payload with that scope export. The two exports read one bundle and differ only in the exclusion record, so the check refuses any difference the release's added record does not explain:

- the excluded output's 52 cells, the new model's included, turn `scored` from true to false and gain `excludedReason` and `excludedInput`, the record's reason code and basis, in the payload's field order; every other field keeps its value and its place, and every other cell keeps its bytes;
- `referenceExclusions` adds exactly the record's entry, and every other entry keeps its bytes and its order;
- each model's `n` falls by one and its `nParsed` by the excluded cells that parsed; the fields `release_20261006.STABLE_STATS` names (condition, cost, tokens, latency and accuracy) keep their values, and the stats keep their field order;
- `heatmap` and `programStats` entries outside the output's group keep their bytes, and the group's entries keep their fields in their order and lose exactly its rows from `n` and `nParsed`;
- `failureModes`' program entries outside the output's group keep their bytes, and each household segment either keeps its bytes or loses exactly the excluded output's parsed rows;
- the sections `release_20261006.CHANGED_SECTIONS` leaves out (country, scenarios, PolicyEngine bundles and global weights) keep their bytes.

The release's record must add exactly the spec's ruled records to the base's. The check does not recompute the fields the exclusion moves: each model's scores, the order of `modelStats` that follows them, and the means in the group's `heatmap` and `programStats` entries. The exporter computes them from cells the check holds to the scope export's.

The check fails closed on three kinds of exclusion, none of which d2180 makes. Excluding its group's first scored row reorders the exporter's output groups, which moves the scenario prompts and the global weights. Excluding its group's last parsed answer on a nonzero reference drops the group's `programStats` `mape`, which skips zero references. Excluding an eligibility output moves `modelStats`' accuracy, one of the stable stats. d2180's output is a dollar amount with a $0 reference, and its group's first scored row comes before it, so it moves none of these; `test_the_ruled_record_keeps_the_exporters_group_order_and_mape` checks each fact on the committed references. On a mock board, `test_excluding_any_one_output_never_changes_another_outputs_hit` excludes each scored output in turn and finds that the check refuses an exclusion only when it reorders the groups, changes a group's `heatmap` or `programStats` fields, or touches an eligibility output. An exclusion that leaves a model no parsed answer in a group stops the export itself: the group's mean absolute error has no value, and the payload's JSON writer refuses it.

**The early rehearsal.** `--early` without `--partial` stages the release's exclusion record (`write_release_exclusions`) under a provisional `stage.json` that marks the stage early, so the rehearsal export scores what the release scores and passes the same pins and scope checks. Its scope export checks the dashboard schema without failure annotations, as the early stage's own payload does. No early or partial stage can become a release.

**Main since `875fe1f6`.**

- #251, #252 and #253 change `uv.lock`, and #253 adds pytest-xdist to the dev extra in `pyproject.toml`; both files keep the policyengine-us 2.60.0 pin. Export binds both as repository inputs, and the freeze and `--finalize` compare them, so neither may change between export and finalization.
- #254, #256 and #258 changed the notes and re-rendered the paper. `manifest.json`'s `rendered_paper_artifacts` changed, which the freeze's manifest rules permit. #258 renamed Populace to Microcosm in prose and code.
- #224 makes `apply_adjudications` leave recorded ceiling-exhaustion rows alone. Triage and the freeze both call it.
- #211 seals each release's tag at the commit that holds its board, and `publish_dashboard` uploads with `--latest=false`. The lead's publication follows it.
- #209 changes how `paper_results.py`, which the paper render reads, names the October upgrade's fixed outputs.
- #180, #183, #186 and #189 change how runs are made: the batch runner's repair merge, the supervisor's timeout backoff, how the supervisor records PolicyEngine provenance, and onboarding's probe of card-less models (`provisional_card`). The freeze's serving-configuration pin imports `eval_no_tools` and `model_cards`, but none of the functions these PRs change; no release script imports `policyengine_runtime`. #205 changes only the 2026-10-05 adversary audit's impact script.
- #259 adds Claude Fable 5.2's card, list price and release date. The run was made at the card's first commit, `0f9f1e78`; between it and #259's merge `c7ede86c`, only the card's notes changed under `policybench/`, and the treatment fingerprint the freeze compares (`policybench/supervisor.py`) holds no notes.

## The ruled exclusion

The mechanics follow release 20261010's (Claude Haiku 5.5's driver, `docs/haiku55/design.md`), which Terra's driver inherits as `install-exclusions` and `adjudicate-exclusions`.

**The record.** `docs/fable52/proposed_exclusions.json` holds it, in the newest record field order, that of the 2026-10-10 wave: `scenario_id`, `variable`, `reason_code` (`reference_depends_on_unlisted_input`), `unlisted_input`, `alternative_reading`, `frozen_value` (0.0), `alternative_value` (1921.0), `engine_version` (policyengine-us 2.60.0), `decided_on` (2026-11-01), `decided_by` (developer) and `note`. Each value comes from `reference_audit/2026-10-29-mn-renters-crp/`: the trace on policyengine-us 2.60.0 (`verification/trace_122_2_60_0.json`) gives $0 as built and $1,921 with a qualifying Certificate of Rent Paid, at a renter's credit household income of $65,346.18 under 2026's $79,330 first zero threshold and rent constituting property taxes of $4,800; the sweep (`verification/crp_sweep.json`) reproduces every scored Minnesota reference as built, and the certificate moves this output alone. The committed CSV's value for the output is 0.0.

**How the classes map.** `EXCLUSION_REASON_CODES` maps the reason code to the adjudicated source `prompt_ambiguity` and the reference verdict `unlisted_input`; the reference basis is the record's `unlisted_input`. The spec gives the subtype, `state_local_rule`: the certificate is a Minnesota rule, and the base's earlier state-rule unlisted inputs (the 2026-10-05 paid-leave payroll cells and the 2026-10-10 Indiana county cells) carry the same subtype.

**Installing it.** `build_release_exclusions` takes release 20261027's record from git and puts the new record after the earlier waves' records and before the audit's trailing scenario_023 record. It inserts the spec's `derivation_insert` sentence before the 2026-09-29 marker. The proposal file must be the bytes the spec pins and must hold exactly the ruled output, a 2026-11-01 developer record on policyengine-us 2.60.0. `install-exclusions` writes the result into the stage's `scoring/` and bundle copies and binds it in `stage.json` (`exclusions_installed`); its first run requires the stage to hold release 20261027's record. Judge prompts do not render exclusions. Every step after `install-exclusions` except bind-seed refuses a stage whose `stage.json` does not record `release_exclusions_sha256()`.

**Adjudicating it.** `adjudicate-exclusions` runs once, after the judge and the restate script. Scenario_122's output has no decision in the base's 63, so the step appends one entry in `release_20261006.ENTRY_FIELDS` order. Its judge fields come from the bound Opus 5.5 verdict of `us__scenario_122__state_refundable_credits` in this stage, and its decision fields from the spec and the record. The date conventions name the 2026-11-01 wave: "The 2026-11-01 wave's decision follows Max's ruling of 2026-11-01 (21:06 UTC) and was written on `adjudications_written_on` UTC." The step refuses a second run. Triage then holds the entry to what `exclusion_entry` builds (`ruled_adjudication_problems`), and refuses any other change outside the cases Claude Fable 5.2 re-opened. The freeze checks the record again.

To re-judge the case, or to add a triage decision after the step has run, put the staged record back to the base's and decide again:

```bash
git show 875fe1f6:annotations/$PB_RUN/us_adjudications.json \
  > "$PB_STAGE/publish/$PB_RUN/annotations/us_adjudications.json"
"$PB_PY" scripts/restate_gpt61sol_adjudications.py --stage-dir "$PB_STAGE" \
  --audit-seed "$PB_SEED"
"$PB_PY" scripts/finish_fable52.py --step adjudicate-exclusions --stage-dir "$PB_STAGE"
"$PB_PY" scripts/finish_fable52.py --step triage --stage-dir "$PB_STAGE"
```

**What the published rows show.** The excluded output's prediction cells stay in `scenarioPredictions` with `scored: false`, `excludedReason` and `excludedInput`, and `referenceExclusions` lists the record in the record's order. Every aggregate leaves the output out. The audit builds cases from wrong answers on every output, scored or excluded, so the output's judged case stays in the stage.

**Triage decisions.** Terra's open `triage_adjudications` path stays. The spec starts with none. If triage needs a developer decision, the lead adds the exact allowed entry with its `triage_decided_on` and `triage_adjudications_written_on` days to the spec, then decides again as above. An entry may affirm a flagged reference with its basis, or settle a developer-only row class on an unflagged case, and keeps the output scored. Wording corrections go through the stage's `wording-amendments.json`.

## Disclosures for the release note

The release note must carry two disclosures:

1. The board sends no reasoning-control parameter, so Claude Fable 5.2's row ran at the API's default effort, high, where Claude Opus 5.5's default is medium (the card's note in `policybench/model_cards.py`).
2. An Opus 5.5 agent built this driver. The session that carries the release runs on Claude Fable 5.2, so each reference, exclusion, adjudication or wording decision that could move the Claude Fable 5.2 row needs an independent review recorded beside it.

## Lead command sequence

These commands are for the lead, in `/Users/maxghenis/PolicyEngine/policybench-wt/fable52-release`. Nobody has run them while building the driver. Keep the run, seed and grounding read-only, and use a new stage directory. Provision the publication-check venv at the path below with the newest published policyengine-us before the check; keep the supplied `.venv` unchanged.

```bash
cd /Users/maxghenis/PolicyEngine/policybench-wt/fable52-release
export OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD"
PB_PY=/Users/maxghenis/PolicyEngine/policybench-wt/fable52-release/.venv/bin/python
PB_RUNS=/Users/maxghenis/PolicyEngine/policybench/results/local/fable52-runs
PB_SEED=/Users/maxghenis/reviews/policybench-gpt-6-1-terra/worktree-results/stage/audit
PB_GROUNDING=/Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit/grounding.csv
PB_STAGE=/Users/maxghenis/PolicyEngine/policybench-wt/fable52-release/results/local/fable52/stage
PB_AUDIT=/Users/maxghenis/PolicyEngine/policybench-wt/fable52-release/reference_audit/2026-10-22-engine-upgrade
PB_BUILD="$PB_AUDIT/reference-build"
PB_RUN=us_full_run_20260612_policyengine_4_16_1_populace
PB_CHECK_VENV=/Users/maxghenis/PolicyEngine/policybench-wt/fable52-release/results/local/fable52/publication-check-venv
PB_TAG=$("$PB_PY" -c 'import sys; sys.path.insert(0, "scripts"); import finish_fable52 as d; print(d.RELEASE_TAG)')

"$PB_PY" scripts/finish_fable52.py --step pin-inputs --runs-root "$PB_RUNS"
```

Commit `docs/fable52/input_pins.json`.

```bash
# Optional: check the seed and grounding against their pins; writes nothing.
"$PB_PY" scripts/finish_fable52.py --step bind-seed --stage-dir "$PB_STAGE" \
  --audit-seed "$PB_SEED" --grounding "$PB_GROUNDING"

"$PB_PY" scripts/finish_fable52.py --step prepare --runs-root "$PB_RUNS" \
  --stage-dir "$PB_STAGE" --audit-seed "$PB_SEED" --grounding "$PB_GROUNDING"
"$PB_PY" scripts/finish_fable52.py --step install-exclusions --stage-dir "$PB_STAGE"

# Supply the authorized isolated judge login to these commands.
export CLAUDE_CONFIG_DIR="$HOME/.policybench-judge/pb-judge-config"
"$PB_PY" scripts/finish_fable52.py --step judge --stage-dir "$PB_STAGE"
"$PB_PY" scripts/restate_gpt61sol_adjudications.py --stage-dir "$PB_STAGE" \
  --audit-seed "$PB_SEED"
```

The judge command requires the authorized `CLAUDE_CODE_OAUTH_TOKEN` and `AUDIT_ACCOUNT` values that `scripts/run_audit_claude.sh` expects. Export neither credential into a committed file. The restate script updates carried decisions' judge fields from the bound seed and current verdicts and keeps their decisions.

Set `adjudications_written_on` in `docs/fable52/spec.json` to the UTC day the next command runs. The step refuses a day after today's UTC date, and one before the day of the ruled case's verdict, which a re-opened case's re-judge sets; the freeze checks the verdict's day again. Then:

```bash
"$PB_PY" scripts/finish_fable52.py --step adjudicate-exclusions --stage-dir "$PB_STAGE"
"$PB_PY" scripts/finish_fable52.py --step triage --stage-dir "$PB_STAGE"
"$PB_PY" scripts/finish_fable52.py --step provenance --stage-dir "$PB_STAGE"
```

If triage stops, review the bound verdicts, `reference-flags.csv` and `unresolved-rows.csv`, record any permitted developer decision in the spec with its two days (`triage_decided_on`, and `triage_adjudications_written_on`, which must fall on or after that day and each of its cases' verdict days and no later than the day `adjudicate-exclusions` runs), and decide again as "Adjudicating it" shows. Commit the checked `docs/fable52/judge_provenance.json` with its generated note unedited, and the spec. Set `snapshot_date` in the spec before the freeze. Fill the completion record's placeholders and update the paper's release prose before rendering.

```bash
"$PB_PY" scripts/finish_fable52.py --step export --stage-dir "$PB_STAGE"
"$PB_PY" scripts/freeze_fable52.py --stage-dir "$PB_STAGE" --dry-run
"$PB_PY" scripts/freeze_fable52.py --stage-dir "$PB_STAGE"

"$PB_PY" "$PB_AUDIT/scripts/sweep_timing.py" check --build "$PB_BUILD" \
  --snapshot "$PB_BUILD" --check-venv "$PB_CHECK_VENV"

"$PB_PY" scripts/date_fable52_judge_verdicts.py --stage-dir "$PB_STAGE"

"$PB_PY" paper/render_paper.py
"$PB_PY" scripts/freeze_snapshot.py --rendered-only
"$PB_PY" scripts/freeze_fable52.py --stage-dir "$PB_STAGE" --finalize
```

**The publication check's snapshot.** `sweep_timing.py check` requires the build's three reference files to equal the `--snapshot` copies byte for byte. After the freeze, the run directory's exclusion record holds this release's 50 records and the build's holds 49, so the check refuses the run directory; pass the committed build itself, as above. The check counts outputs from the build's own record, so it counts scenario_122's output as scored: an engine that moves that output stops `--finalize` (`verify_publication_record` requires `scored_differ` empty), although this release excludes it. That gate stays strict: when it stops there, the lead stops too and queues a decision for Max under his latest-engine rule (`cos add-decision`), with no change to `verify_publication_record`. Read the check's CSV for the excluded outputs it moved; each keeps its decided value. The check reads PyPI, so only the lead runs it, after the freeze. Each run rewrites `sweep_timing.json`, and `--finalize` refuses a record that export bound unchanged, so it stops when the check did not run or stopped before it wrote, as it does when the check venv lacks the newest engine. It then gates the changed record again through `verify_publication_record`, which at finalize also requires the record's engine to be PyPI's newest at the check's read (`pypi.newest_at_read`) and that read to fall on or after the spec's `snapshot_date`: the 2026-10-29 check of 2.78.0 does not pass.

## By hand

- Commit `docs/fable52/input_pins.json` before export.
- Fill `adjudications_written_on` before `adjudicate-exclusions` and `snapshot_date` before the freeze.
- After the dating step, update `tests/test_adjudications.py`'s wave pins for the 2026-11-01 wave, as each earlier release's dating step has needed: `uncommitted == []` and `waves[-3:]` in `test_each_decision_records_the_verdict_it_reviewed_by_its_wave_release`. That test reads the ruled wave's sentence in its singular form ("decision ... was written") already. If the judge step re-opened `us__scenario_122__state_refundable_credits`, Opus 5.5 judged it after 2026-11-01, so the same test also needs that entry's `("2026-11-01", <its judged_on_utc>)` pair beside its `("2026-09-22", "2026-09-23")` exception, and its `later_than_wave` count rises by one. A carried-over verdict predates the wave and needs neither.
- The freeze's dry run ends with a "Dating step:" line that says whether the record the freeze commits holds a decision on a re-opened case. If it holds none, the dating step will stop with "no committed decision is on a re-opened case" after the freeze has written. So before the freeze runs, the lead rules on the relaxation saved at `/Users/maxghenis/reviews/policybench-fable-5-2/runs/driver-fix-r3/m14-p3-4-empty-restatements.patch` (round 2's patch, refreshed for the dry run's line) after an independent review; the same ruling applies if the dating step stops anyway. Nobody edits `scripts/date_fable52_judge_verdicts.py` before that ruling. The dating step reads `docs/fable52/judge_provenance.json` only as the bytes whose sha256 the stage's `release-ready.json` binds (export writes it, and the freeze and finalize keep it), so a record that changed after export stops the step.
- Seal the release tag at the commit that holds its board (#211).
- The release note carries the d2397 line staged in `/Users/maxghenis/reviews/policybench-gpt-6-1-terra/worktree-results/NEXT-RELEASE.md`, voice-gated with the rest of the note.
- After the release ships, run `cos acted-decision d2180 --ruling d9eafca7 "<release tag and PR>"` and `cos acted-decision d2397 --ruling 3f59364d "<release tag and PR>"`.

## Lead completion record

- **Result.** [LEAD: Claude Fable 5.2's share of answers right, rank of 52, bounded score, parse count, cost, latency, response window and snapshot date.]
- **Judge.** [LEAD: cases carried over, re-opened and new; who judged them, when and under which login; the verdict of `us__scenario_122__state_refundable_credits`.]
- **Restatement and adjudication.** [LEAD: entries the restate script restated; the day `adjudicate-exclusions` ran and the entry it wrote.]
- **Triage.** [LEAD: rows and cases read, flags, decisions and wording amendments.]
- **Export and freeze.** [LEAD: commits, times, payload hash and what each run validated or refused.]
- **Publication check.** [LEAD: engine, outcome for the 1,935 outputs the check scores, and the excluded outputs it moved.]
- **Judge evidence.** [LEAD: what the dating step wrote.]
- **Rendering and suites.** [LEAD: render, re-pin and finalize times; suite results.]
- **Independent reviews.** [LEAD: the review recorded beside each decision that could move the Claude Fable 5.2 row.]
- **Publication.** [LEAD: Max's approval and the publication date.]
