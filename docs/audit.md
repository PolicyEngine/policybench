# Failure audit (Codex-backed classifier)

The audit classifies every wrong `(scenario_id, variable)` case into the
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
`<country>_audit_case_annotations.csv`, extended beyond the legacy schema with a
free-text `rationale` and a `reference_suspect` flag so the classifier's
reasoning is preserved (the May 2026 audit collapsed to an all-`llm_error`
residual because its reasoning was never serialized).

## What the classifier sees

Per case: the output variable, the PolicyEngine reference value, how
PolicyEngine derived it (from `case_reference_explanations`), the exact question
the models were asked, and every wrong model's answer + explanation side by
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
