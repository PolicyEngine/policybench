# September 28 additions: stage 2 design

This note and the drivers live in the assigned checkout. The requested external
state-note path is outside the job's writable workspace. No worker checkout,
live run directory, release asset or production pointer is changed by staging.

## Base and fold

Use `dashboard-data-20260922c`, SHA-256
`01e7e72b3a6bdd2d3178ba32625ff769d5b81dc07541af6ea8da2c852774ddcc`:
42 models, 100 households, 1,984 requested outputs per model, 52 exclusions and
1,932 scored outputs. The committed snapshot under
`paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/`
contains the base predictions, reference outputs and their provenance sidecar,
exclusions, scenarios and frozen country payload. Recombining that payload must
match the live release hash. Use the checkout's matching annotations and
`us_adjudications.json`; never use the old driver's 39-model September 5 base
or its mutable `reference_v12` scratch directory.

[PR #178](https://github.com/PolicyEngine/policybench/pull/178), merged as
`cb312fd775b36af644b10803c076a0d0efc79f2e`, establishes this base. Its difference
from 20260922b was the regenerated Michigan `scenario_045` SNAP reference of
$0 after the upstream child-support fix; it restored that output to scoring.
There are 26 regenerated references. The dated 20260922c release name preserves
the September 22 snapshot; this new addition uses `dashboard-data-20260929` and
the September 28 snapshot date.

`scripts/finish_adds0928.py` generalizes `finish_opus55.py` and
`judge_stages.py`. It requires all three named supervised runs, each with
`completed == total > 0`, `stopped_reason is None`, and predictions present.
The production fold additionally requires complete reference-key coverage,
known model metadata, costs and treatment provenance. Copies of inputs and all
subsequent outputs stay under `--stage-dir`. `fold_board` combines predictions;
the official exporter scores against the copied, unchanged references and
exclusions. All 42 incumbent `modelStats` must stay identical. Fable 5's historical
batch usage must survive export, as must zero-cost Ox Alpha usage.

`--early` skips judging and cannot produce a release-ready receipt. Normal
`--early` refuses partial runs. The explicit `--early --partial` rehearsal uses
synthetic completion state in copied scenarios only, scores the common completed
household cohort for the 45-model comparison, and also reports each addition
against the 42 incumbents on that addition's own completed cohort. Every such
score and payload is marked **PARTIAL**, and publication is blocked.

Reproduce the CSV-only rehearsal in new scratch directories:

```bash
export OPENBLAS_NUM_THREADS=1
PB_SOURCE=/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609
PB_COPY="$PWD/results/local/adds0928-partial-copy"
PB_EARLY_STAGE="$PWD/results/local/adds0928-partial-stage"
uv run python scripts/snapshot_adds0928.py \
  --runs-root "$PB_SOURCE" --out-dir "$PB_COPY"

# Expected nonzero exit: the synthetic copied states still have total=100.
uv run python scripts/finish_adds0928.py \
  --runs-root "$PB_COPY" --stage-dir "$PB_EARLY_STAGE" --early

# Temporarily change only the copied states; restore them even if export fails.
uv run python - "$PB_COPY" "$PB_EARLY_STAGE" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

paths = sorted(Path(sys.argv[1]).glob("*/run/run_state.json"))
original = {path: path.read_bytes() for path in paths}
try:
    for path in paths:
        state = json.loads(original[path])
        assert state["synthetic_partial"]
        state["total"] = state["completed"]
        path.write_text(json.dumps(state, indent=2) + "\n")
    subprocess.run([
        sys.executable, "scripts/finish_adds0928.py",
        "--runs-root", sys.argv[1], "--stage-dir", sys.argv[2],
        "--early", "--partial",
    ], check=True)
finally:
    for path, content in original.items():
        path.write_bytes(content)
PY
```

## Audit and triage

The unit of audit is `(country, scenario_id, variable)`, grouping every wrong
model's answer and explanation for that output. `prepare_audit` adds the household
facts, reference value, reference derivation and existing grounding. When a new
model joins a case, the rendered prompt changes and its old verdict and provenance
sidecar are invalidated. Unchanged prompts retain verdicts. New wrong outputs
become new case directories. Cases containing only missing/unparseable answers
are classified deterministically without a judge call.

The existing audit selects `threshold_score_single_prediction < 1`, including
excluded reference outputs for explanatory coverage. This is the historical
legacy-threshold miss set, not every headline exact-match miss. Scoring itself
uses the 1,932 nonexcluded outputs and population-weighted household exact rates.

Copy the historical unified audit into the stage, preserving valid verdicts and
hash-bound metadata. Use `scripts/run_audit_claude.sh` with
`AUDIT_MODEL=claude-opus-5-5`, `AUDIT_PARALLEL=1`, and an explicitly selected
Claude subscription lane. It invokes Claude without tools, validates the full
verdict schema, and records requested/reported model, CLI version, timestamp,
session and verdict hash. On September 22, lane admission failure meant Opus 5.5
native Workflow subagents supplied verdicts through `judge_stages.py write`;
that was the same prepare/validate/collect contract, not another judge model.

Missing and hedged verdicts are rejudged with a bounded retry count. A standing
`reference_suspect` flag is an investigation, not a retry target. `--step triage`
collects fresh row annotations and case notes, including new wrong-model counts,
applies the staged adjudications, and stops on unresolved cases. Investigators
must check the stated facts, primary authority and engine trace, independently
review the conclusion, and write the evidence and original judge class to the
staged adjudication record. An affirmed reference clears the flag with its
reason; an engine defect fixed upstream is regenerated; an unfixed formula
defect or necessary unlisted input is excluded for every model. Apply the existing
published-law/held-value conventions; do not silently change the scoring universe.

The historical `triage/build_records.py`, `regen_references.py`,
`make_on_convention.py`, `package_audit.py` and sweeps produced the September 22
reference revisions. Their committed, reproducible equivalents live under
`reference_audit/2026-09-22/`. They are evidence and templates; rerunning their
hardcoded historical paths is not part of an additive release. A newly confirmed
reference change requires a separately reviewed revision and fresh incumbent
comparisons. The additive release helper deliberately refuses changed references.

## Commands after all three runs complete

Run from this checkout, sequentially. The source paths below are read-only. The
stage must be new for `prepare`; subsequent commands resume that same stage.

```bash
export OPENBLAS_NUM_THREADS=1
export PYTHONPATH="$PWD"
export PYTHONDONTWRITEBYTECODE=1
# This managed workspace needs its local Git metadata for correct registry pins.
# An ordinary checkout restored from the bundle uses its normal Git metadata.
if [ -d results/local/stage2-history.git ]; then
  export GIT_DIR="$PWD/results/local/stage2-history.git"
  export GIT_WORK_TREE="$PWD"
fi
PB_RUN=us_full_run_20260612_policyengine_4_16_1_populace
PB_SOURCE=/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609
PB_AUDIT_SOURCE=/Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit
PB_STAGE="$PWD/results/local/adds0928-final"

# Stop and revise the base if this pointer no longer names September 22c.
gh api 'repos/PolicyEngine/policybench/contents/app/src/data.artifact.json?ref=main' \
  --jq '.content | @base64d'

uv run python scripts/finish_adds0928.py \
  --runs-root "$PB_SOURCE" --stage-dir "$PB_STAGE" \
  --audit-seed "$PB_AUDIT_SOURCE/audit" \
  --grounding "$PB_AUDIT_SOURCE/grounding.csv" --step prepare

# Execute this step inside the selected Claude subscription lane.
AUDIT_MODEL=claude-opus-5-5 AUDIT_PARALLEL=1 \
  uv run python scripts/finish_adds0928.py --stage-dir "$PB_STAGE" --step judge

uv run python scripts/finish_adds0928.py --stage-dir "$PB_STAGE" --step triage
```

If triage stops, investigate the staged `reference-flags.csv` and
`unresolved-rows.csv`; record reviewed resolutions in
`$PB_STAGE/publish/$PB_RUN/annotations/us_adjudications.json`, preserving the judge's
actual verdict. Then rerun `triage`. Do not invent adjudications to unblock export.

```bash
uv run python scripts/finish_adds0928.py --stage-dir "$PB_STAGE" --step export
uv run python scripts/freeze_adds0928.py --stage-dir "$PB_STAGE" --dry-run
uv run python scripts/freeze_adds0928.py --stage-dir "$PB_STAGE"
uv run python scripts/sensitivity_by_variable.py
uv run python scripts/rescore_sensitivity_summaries.py \
  --release dashboard-data-20260929
```

`export` writes the strict 45-model payload and a hash-bound `release-ready.json`.
`freeze_adds0928.py` is a **local build**, with no upload code. It checks that
receipt, unchanged references and incumbent predictions, complete 100/100 input
copies, and staged adjudications. It configures the existing freezer in process,
pins the staged audit provenance, preserves incumbent frozen serving evidence,
and requires copied run-state evidence for the additions. It updates the local
pointer/version label, freezes the compact snapshot and annotations, caches the
payload for offline app builds, and creates deterministic `predictions.csv.gz`
beside the staged payload. It does not invoke historical `publish_opus55.py`,
whose hardcoded scratch paths would write outside this workspace even in dry-run.

Before rendering, write a new September 28 note from final recomputed results;
update the paper source, benchmark card, methodology/model-count prose and tests,
serving-sensitivity prose, and release-specific fact pins. Keep historical notes'
own release pins and findings. Account for Sonnet's JSON/adaptive thinking
treatment and DeepSeek's moving alias. The roster count is 45; scored output and
exclusion counts stay 1,932/52 unless separately reviewed triage changes them.

```bash
uv run python paper/render_paper.py
uv run python scripts/freeze_snapshot.py --rendered-only
uv run ruff format scripts/finish_adds0928.py scripts/freeze_adds0928.py
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
bun install --cwd app --frozen-lockfile
(cd app && bun run test)
(cd app && bun run lint)
(cd app && bun run build)
git diff --check
```

Review the generated diff and commit coherent changes on the assigned branch.
The two future release assets are `dashboard-data.json` (the staged payload,
renamed at upload time) and `predictions.csv.gz`. This job stops before upload,
push, merge or production publication. Recheck release-tag availability before
any later publication; choose a fresh suffix if the intended tag was taken.

## Risks and gates

- A partial cohort's score and rank cannot estimate a final rank without
  uncertainty; completion order need not be representative. Synthetic state is
  rehearsal evidence only. No release receipt is created for it.
- The DeepSeek `deepseek-flash` alias can change. Retain per-response reported
  model/version evidence and response timestamps; an alias alone does not prove
  V4.1 Flash. If responses report only that alias, preserve the dated onboarding
  and provider-model-list evidence, disclose the limit, and obtain a substantive
  provenance review before release. Do not relabel the alias as an observed
  immutable version or rewrite historical V4 board rows.
- Costs can be present yet mispriced. Verify new model registry, dates, input,
  output/cache prices and response usage against the registered treatments.
- Card defaults can differ from the actual run fingerprint (notably Sonnet's
  JSON contract and Grok's 1,800-second timeout). Do not edit running workers or
  relabel old responses. The freezer must use actual copied treatment evidence.
- Copy the audit, grounding, exclusions and reference sidecar together. Stale
  case notes undercount wrong models; absent exclusions silently change scores;
  a `by_model` directory in the export bundle can hide incumbent predictions.
- Judge flags may require real reference work. Rejudging an already adjudicated
  case can change its judge class; preserve the new exact judge class alongside
  the independently justified adjudication. Never permit incumbent score drift
  merely to finish an additive release.
- Local release building intentionally changes tracked snapshot/pointer files;
  preparation and partial dry runs do not. Large payloads, dataframe exports and
  paper builds run serially with `OPENBLAS_NUM_THREADS=1` on the shared machine.
