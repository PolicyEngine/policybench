# Failure audit (Codex-backed classifier)

The audit selects model-output rows whose legacy threshold score is below 1
and classifies each selected `(scenario_id, variable)` case into the
[`annotation_taxonomy`](../policybench/annotation_taxonomy.py) — separating
genuine model errors from prompt ambiguity, parse failures, and **candidate
PolicyEngine/data bugs** (a wrong *reference*, not a wrong model). It replaces
the earlier ad-hoc, session-orchestrated audit with a committed, resumable
pipeline.

The LLM step runs through the **Codex CLI**, so classification bills to a
ChatGPT plan rather than a metered API key. Everything else is deterministic
Python (`policybench/audit.py`).

## Pipeline

```bash
# 1. Assemble one prompt per wrong case (+ shared output schema + manifest).
uv run python -m policybench.cli audit-prepare \
  --country-dir results/<run>/us \
  --audit-dir   results/<run>/us/audit

# 2. Classify in bulk via Codex (ChatGPT plan). Resumable + parallel.
AUDIT_PARALLEL=4 AUDIT_REASONING_EFFORT=low \
  scripts/run_audit_codex.sh results/<run>/us/audit

# 3. Fold verdicts into annotation CSVs.
uv run python -m policybench.cli audit-collect \
  --country-dir results/<run>/us \
  --audit-dir   results/<run>/us/audit
```

`audit-collect` writes `<country>_audit_row_annotations.csv` and
`<country>_audit_case_annotations.csv`. They follow the legacy annotation
schema (the classifier's rationale lands in the `annotation` / `case_annotation`
columns) and add a `reference_suspect` flag — plus `reference_bug_hypothesis` at
the case level — so the classifier's reasoning is preserved (a prior audit
collapsed to an all-`llm_error` residual because its reasoning was never
serialized).

## What the classifier sees

Per case: the output variable, the PolicyEngine reference value, how
PolicyEngine derived it (from `case_reference_explanations`), the exact question
the models were asked, and each selected model's answer and explanation side by
side. It is told to default to `llm_error` and flag `reference_suspect` only
with concrete evidence — the same conservatism as the deterministic inferrer,
but with actual tax/benefit reasoning instead of keyword matching.

## Acting on suspect references

Cases with `reference_suspect=true` are candidate PolicyEngine or data bugs.
Verify each, fix upstream, file an issue, and re-run `reference-outputs` so the
frozen snapshot never scores models against a value the audit doubts. Only
genuine model errors (`llm_error`) should survive to a scored snapshot —
`policybench.annotation_validation` enforces this.

## Tuning

| env var | default | purpose |
|---|---|---|
| `AUDIT_PARALLEL` | 4 | concurrent Codex processes |
| `AUDIT_REASONING_EFFORT` | `low` | Codex reasoning effort (classification is shallow) |
| `AUDIT_MODEL` | Codex default | override the model (`-m`) |

Re-running the script is safe: a case is skipped once it has a verdict, so
interrupted runs resume and failures can be re-attempted by re-invoking.

# Reference adversary

The diagnosis judge above is built to explain misses, not to doubt references:
its prompt says to treat the reference and its derivation as correct, labels
engine facts authoritative, and allows doubt only through `reference_suspect`
with a concrete contradiction. On 2026-10-05 that design missed reference issues
a reading of the data found: Louisiana's 2026 standard deduction was
PolicyEngine's own CPI computation rather than a published amount; the
`payroll_tax` reference counted paid-leave employee shares that the employer
may, but need not, pass on, though the output asks for "mandatory employee state
payroll taxes"; and the income tax references left out a dependent's own return.
The reference adversary is a separate pass whose only job is to attack the
reference. Its verdicts never change a score.

## Pipeline

```bash
# 1. Consensus trigger: scored cells where a cluster of models shares a wrong
#    answer (>= 15 of the models, or >= 3 of the top 5).
uv run policybench consensus-flags \
  --payload paper/snapshot/20260501/runs/<run>/data.json.gz \
  --output <dir>/consensus_flags.json

# 2. One two-stage case per flagged cell, minus cells another audit owns.
uv run policybench adversary-prepare \
  --payload paper/snapshot/20260501/runs/<run>/data.json.gz \
  --flags <dir>/consensus_flags.json \
  --annotations-dir annotations/<run> \
  --skip-cells <dir>/covered_elsewhere.json \
  --adversary-dir <adv>

# 3. Judge inside a Subfleet lane (subscription billing, never an API key).
scripts/run_reference_adversary_claude.sh <adv>   # Claude lane
scripts/run_reference_adversary_codex.sh <adv>    # Codex lane

# 4. Verdict table and adjudication queue (one or more judges).
uv run policybench adversary-collect \
  --adversary-dir claude=<adv-claude> --adversary-dir codex=<adv-codex> \
  --output-dir <out>
```

`consensus-flags` records its parameters in the report. `--prototype`
reproduces the 2026-10-05 prototype (answers truncated to whole dollars,
eligibility outputs never flagged): 41 of the frozen run's 1,928 scored cells.
The defaults round answers to the nearest dollar, which merges answers such as
13,387.65 and 13,388, and compare eligibility outputs by mismatch: 61 cells. A
model whose own answer is within the tolerance of an amount reference counts as
exact and never toward a wrong cluster, even when its rounded key misses.

## Two stages

- **Stage 1, law first.** The judge sees the household prompt, the output's
  definition from `benchmark_specs.json`, the consensus answer with each
  member's model id, answer and explanation, and the reference value. It does
  not see the engine derivation. It works the answer from primary law
  (statutes, regulations, agency publications, forms and instructions), cites
  each rule with its publication date and whether it predates the 2026-07-03
  reference freeze, and says which answer the law supports.
  - The Claude runner gives it only web tools (no file access) and denies
    WebFetch on the PolicyBench, PolicyEngine and GitHub domains
    (`BLOCKED_DOMAINS`). WebSearch has no deny rule, so its results reach the
    judge. The prompt asks the judge to pass those domains as
    `blocked_domains` on every search. The transcript audit rejects an output
    whose search results list a blocked URL or name PolicyEngine or
    PolicyBench.
  - The Codex runner works from an empty directory and rejects a stage 1
    whose log shows a read of derivation-bearing paths. Codex's event log
    records a search's query but not its results, so this runner cannot
    check what a search returned; the prompt's request is its only guard
    there.
- **Stage 2, reconcile.** A fresh call gets the frozen stage-1 JSON (bound by
  its sha256) and only now the engine derivation. It returns a verdict:
  `reference_holds`, `reference_wrong`, `definition_mismatch` or
  `prompt_ambiguous`, with citations and a suggested adjudication.

## Where verdicts go

`adversary-collect` writes each judge's verdict table and
`adversary_adjudication_queue.csv`, in the case-notes schema with
`reference_suspect=true`. The queue holds every case with a verdict other than
`reference_holds`. It also holds every case whose verdict is inconsistent, such
as a holding verdict that drops stage 1's finding for the consensus without
naming a stage-1 error. Its rules:

- A verdict counts only with a sidecar bound to the current stage 1.
- A case without one is listed as missing, and the command then exits
  non-zero unless `--allow-missing` is given.
- Each `--adversary-dir` needs its own label (`LABEL=DIR`). A repeated label
  is refused, because one judge's verdicts would overwrite another's.
`policybench.reference_adversary.apply_adversary_flags` sets those flags on a
release's case notes, so `scripts/freeze_snapshot.py` refuses to freeze until
each carries a developer `reference_verdict` (`policybench.adjudications`):
the existing adjudication path. A change to a published reference or an
exclusion still needs a release and the maintainer's ruling.

## Definition and publication checks

Two engine-side checks run with the reference venv (policyengine-us 2.15.17
plus the reference conventions) and write under
`reference_audit/2026-10-05-reference-adversary/verification/`:

- `definition_conformance` lists the policyengine-us variables each output's
  reference sums and tests them against the qualifiers in the output's
  definition ("employee-side", "mandatory", "household", "excluding the ACA
  PTC", "excluding local income and payroll taxes").
- `publication_sources` lists every 2026 parameter value a scored reference
  reads and reports whether its metadata cites a government publication dated
  before the freeze, flagging computed or indexed values.
