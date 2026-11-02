# September 28 stage 2 preparation

Prepared in the assigned workspace only. No judge calls, worker changes,
publication, release upload, push, or merge were performed.

## Design and deliverables

- `scripts/finish_adds0928.py`: separate prepare/fold, Opus 5.5 judge, triage,
  and strict export steps. All outputs stay under a scratch stage directory.
- `scripts/snapshot_adds0928.py`: copy completed scenario CSVs without reading
  live supervisor state; produce explicitly synthetic rehearsal state.
- `scripts/freeze_adds0928.py`: local release-build adapter, gated on a strict
  export receipt and complete serving evidence. Not executed during preparation.
- `docs/adds0928/stage2_design.md`: design, risks, exact rehearsal commands,
  and the complete fold → judge → triage → export → release-build sequence.
- `tests/test_finish_adds0928.py`: completion, isolation, coverage, provenance,
  adjudication, receipt, export, and snapshot-copy regression tests.

The base is the committed September 22c snapshot: 42 models, 1,984 requested
outputs per model, 52 exclusions, and 1,932 scored outputs. Its country payload
recombines to live SHA256
`01e7e72b3a6bdd2d3178ba32625ff769d5b81dc07541af6ea8da2c852774ddcc`.
The new release is planned as `dashboard-data-20260929`, with 45 models.

Audit cases use the historical legacy-threshold miss selector, grouping all
wrong models by household/output. A new answer changes the prompt and invalidates
its copied verdict. Unchanged verdicts survive; missing-output-only cases need
no paid judge. New-model cases require schema-valid, complete verdicts with
hash-bound requested/reported `claude-opus-5-5` provenance. Reference flags and
nonfinal scored diagnoses block export until evidence-backed adjudication.

## PARTIAL rehearsal

The immutable CSV snapshot contains the following observations. Each rank below
compares one addition with the 42 incumbents on exactly that addition's copied
households, using the board's population-weighted household exact-match metric.
These are **PARTIAL rehearsal results**, not a released 45-model ranking.

| Model | Copied households | Scored outputs | Exact match | Rank among 43 |
|---|---:|---:|---:|---:|
| Claude Sonnet 5.5 | 100 | 1,932 | 91.454010% | 4 |
| Grok 4.7 | 49 | 973 | 86.537884% | 12 |
| DeepSeek V4.1 Flash | 95 | 1,836 | 87.457366% | 13 |

Sonnet has 100 valid household CSVs in this copy, but the CSV-only procedure
does not read or certify its actual supervisor completion state or treatment.
Completion order is not necessarily representative, so the smaller cohorts do
not estimate final ranks.

The staged **45-model PARTIAL payload** uses the 49 households completed by
all three additions (992 requested outputs, 19 exclusions, 973 scored outputs):

| Model | Exact match on common cohort | Rank among 45 |
|---|---:|---:|
| Claude Sonnet 5.5 | 91.650727% | 4 |
| Grok 4.7 | 86.537884% | 13 |
| DeepSeek V4.1 Flash | 86.318837% | 15 |

The `--early --partial` command exited 0. The standard exporter and nonstrict
dashboard-schema gate passed. Output:
`results/local/adds0928-rehearsal/stage/PARTIAL-data-board45.json`.
There is no `release-ready.json`; no paid audit was executed.

The ordinary `--early` invocation exited 1 with:

```text
refusing incomplete additions: grok47: 49/100, stopped_reason=None; dsflash41: 95/100, stopped_reason=None
```

Only the scratch states were temporarily changed to `total=completed`, retaining
`synthetic_partial=true`. The rehearsal then used `--early --partial`.
The source-copy states were restored to `total=100` afterward; the stage keeps
its explicitly synthetic input copies and hashes for reproducibility.
Production mode additionally requires all 100 households, exact output-key
coverage and actual matching treatment fingerprints. Partial/early stages can
never resume into a release stage or obtain `release-ready.json`.

Scratch evidence is under `results/local/adds0928-rehearsal/`: source copies in
`completed-csvs`, per-file hashes alongside those copies, `refusal.log`,
`dry-run.log`, and staged artifacts under `stage/`. Full original CSV transcripts
remain in the copies; PARTIAL scoring omits the unused repeated `raw_response`
column to reduce memory use on the shared machine.

## Breakages and remaining release work

- Fixed stale 39-model/September 5 driver constants by pinning September 22c
  predictions, references, exclusions and live payload identity.
- Fixed the snapshot-copy assumption that filenames are household IDs:
  `scenario_006.csv` can contain `scenario_007`; filenames are queue indices.
- Fixed country-payload recombination and canonical JSON serialization required
  by the freezer. Its preflight now rejects incompatible bytes before mutation.
- Added key coverage checks beyond row counts, strict all-three completion,
  scratch/source overlap protection, complete verdict coverage and Opus metadata
  validation, and immutable evidence hashes across export and freeze.
- Added preservation of current judge classes in adjudications, matching
  exclusion decisions, and regenerated case counts. Full exports must preserve
  every incumbent model statistic, including Fable 5's historical batch usage.
- All three registrations, price overrides and response-cost/token fields are
  present. Provider-reported cost fields are blank; recorded costs are reconstructed
  from usage and prices. No model metadata or new-model cost-field blocker was found.
- The existing freezer omitted these three supervised runs. The adapter requires
  their copied states and fingerprints and preserves incumbent serving evidence.
  Actual new-run fingerprints remain unverified in this CSV-only rehearsal.
- DeepSeek responses report only `deepseek-flash`, with observed fingerprint
  `aeb56401ca74e127821c4f9126dcb669`; they do not independently report V4.1.
  Preserve the dated onboarding/provider-list evidence, response IDs, aliases,
  fingerprints and timestamps. Do not claim immutable response-version proof.
- Keep the registered Grok release date, September 21: the September 2 value
  in the older context is API-object creation, not public launch.
- The final note, manuscript prose, frozen roster pins, paper rendering and app
  checks require the completed, judged 45-model payload. This prep does not
  refreeze or change any published snapshot/pointer relative to the registration
  branch. The existing paper roster/metadata test is expected to need refreezing.

## Validation

The targeted suite passed **207 tests**, including all 57 new driver/freezer
tests and the existing fold, audit, adjudication, reference provenance, model
card, judge provenance and cost/latency tests:

```bash
OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" \
  /Users/maxghenis/PolicyEngine/policybench/.venv/bin/python -m pytest -q \
  tests/test_finish_adds0928.py tests/test_fold_board.py tests/test_audit.py \
  tests/test_adjudications.py tests/test_reference_provenance.py \
  tests/test_model_cards.py tests/test_judge_provenance.py tests/test_cost_latency.py
```

Ruff formatting/checks passed for the three scripts and new test file.
The actual paid judge and full release build remain unexecuted, as required for
this preparation. Python 3.14 from the existing environment satisfies the
project's `>=3.10` requirement; imports use this workspace's code.

The separately run
`tests/test_paper_results.py::test_frozen_roster_has_42_display_names_and_release_dates`
failed as expected: `MODEL_DISPLAY_NAMES` includes the three registered additions,
while the untouched frozen snapshot contains 42 models. This inherited mismatch
must be resolved by the final 45-model refreeze, not by changing the prep snapshot.
Its log is `results/local/adds0928-rehearsal/paper-roster.log`.

## Git handoff

The initial checkout was clean at `c7aaffe9bc6f`. The required registration base
is `05f472a`, the head of `add-claude-sonnet-5.5`.

The managed sandbox denied creation of the linked worktree's `index.lock`
because its Git directory is in the caller's repository, outside the assigned
workspace. No approval mechanism is available. An independent Git directory
inside `results/local/stage2-history.git` holds the local `adds-0928-stage2`
branch based on `05f472a`; its object store reads existing objects without
writing the caller's repository. A commit bundle is supplied for recovery.

Driver, design and tests commit: **`3a339d0`**,
`Prepare stage two for the September 28 model additions`.
The report is a separate coherent follow-up commit. The bundle is
`results/local/adds0928-stage2.bundle` and contains both commits with `05f472a`
as its prerequisite.

To inspect that branch within this workspace:

```bash
git --git-dir=results/local/stage2-history.git --work-tree=. log -3 --oneline
git --git-dir=results/local/stage2-history.git --work-tree=. status --short
```

No files were written to the requested external chief-of-staff state paths;
the design and this report are committed here instead.

## Exact sequence once all three runs reach 100/100

Run from this assigned workspace. Check the remote pointer still names the
September 22c base before starting. All three runs must have `completed=total=100`
and null `stopped_reason`; the driver verifies these and copies their inputs.
Use a fresh stage directory, and run every heavy step sequentially.

```bash
export OPENBLAS_NUM_THREADS=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD"
export GIT_DIR="$PWD/results/local/stage2-history.git"
export GIT_WORK_TREE="$PWD"
PB_PY=/Users/maxghenis/PolicyEngine/policybench/.venv/bin/python
PB_SOURCE=/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609
PB_AUDIT=/Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit
PB_STAGE="$PWD/results/local/adds0928-final"
PB_RUN=us_full_run_20260612_policyengine_4_16_1_populace

gh api 'repos/PolicyEngine/policybench/contents/app/src/data.artifact.json?ref=main' \
  --jq '.content | @base64d'

# Fold, copy the audit, and prepare changed cases without making judge calls.
"$PB_PY" scripts/finish_adds0928.py --step prepare \
  --runs-root "$PB_SOURCE" --stage-dir "$PB_STAGE" \
  --audit-seed "$PB_AUDIT/audit" --grounding "$PB_AUDIT/grounding.csv"

# Run this command inside the selected Claude subscription lane.
"$PB_PY" scripts/finish_adds0928.py --stage-dir "$PB_STAGE" --step judge

"$PB_PY" scripts/finish_adds0928.py --stage-dir "$PB_STAGE" --step triage
```

If triage stops, inspect `$PB_STAGE/reference-flags.csv` and
`$PB_STAGE/unresolved-rows.csv`. Investigate and record evidence-backed decisions
in `$PB_STAGE/publish/$PB_RUN/annotations/us_adjudications.json`, preserving the
current judge's exact verdict, then rerun `triage`. A newly changed reference or
exclusion requires a reviewed reference revision; this additive driver refuses
such drift. Do not continue past a failed gate.

```bash
"$PB_PY" scripts/finish_adds0928.py --stage-dir "$PB_STAGE" --step export
"$PB_PY" scripts/freeze_adds0928.py --stage-dir "$PB_STAGE" --dry-run
"$PB_PY" scripts/freeze_adds0928.py --stage-dir "$PB_STAGE"
"$PB_PY" scripts/sensitivity_by_variable.py
"$PB_PY" scripts/rescore_sensitivity_summaries.py \
  --release dashboard-data-20260929
```

At this point, write the September 28 note from the final results and update the
paper, benchmark card, methodology/model-count prose, release-specific test
pins, and alias/treatment disclosures. This editorial step depends on actual
final scores and any investigated flags. Preserve historical notes' own pins.
Then run:

```bash
"$PB_PY" paper/render_paper.py
"$PB_PY" scripts/freeze_snapshot.py --rendered-only
"$PB_PY" -m ruff format .
"$PB_PY" -m ruff check .
"$PB_PY" -m ruff format --check .
"$PB_PY" -m pytest -q
bun install --cwd app --frozen-lockfile
(cd app && bun run test)
(cd app && bun run lint)
(cd app && bun run build)
git diff --check
```

Review and commit the resulting local release build. These commands stop before
upload, push or merge. In an ordinary checkout recovered from the bundle, omit
the two workspace-local `GIT_DIR`/`GIT_WORK_TREE` exports and use its normal Git
metadata. See the design note for the copy-only rehearsal and full risk analysis.
