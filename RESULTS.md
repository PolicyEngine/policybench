# PolicyBench Results

PolicyBench is a no-tools benchmark. Ad hoc local outputs should live under
`results/local/` after a benchmark run. Published leaderboard claims should
instead point to dated batch directories or to a committed dashboard export
such as `app/src/data.json`.

## Run

```bash
policybench reference-outputs -n 100 --seed 42
policybench eval-no-tools -n 100 --seed 42
policybench analyze --output-dir results/local/analysis
```

The first command writes PolicyEngine reference outputs, not administrative
truth.

## Full runbook

Use the canonical paid-run procedure in [docs/runbook.md](docs/runbook.md). It
keeps provider groups isolated, uses smaller resumable chunks, and tracks the
current default model roster from `policybench.config.MODELS`.

For first-pass cost control, run the same commands with `-n 100` in a separate
scratch directory before launching the 1,000-household batch.

## Artifacts

- `results/local/reference_outputs.csv`
- `results/local/no_tools/predictions.csv`
- `results/local/analysis/metrics.csv`
- `results/local/analysis/summary_by_model.csv`
- `results/local/analysis/summary_by_variable.csv`
- `results/local/analysis/impact_summary_by_model.csv`
- `results/local/analysis/usage_summary.csv`
- `results/local/analysis/report.md`

## Methodology

See the [full paper](docs/) and [benchmark code](policybench/) for complete methodology. Reference outputs are computed via [PolicyEngine-US](https://github.com/PolicyEngine/policyengine-us) and [PolicyEngine-UK](https://github.com/PolicyEngine/policyengine-uk); the public UK scenarios use PolicyBench's calibrated transfer dataset. LLM responses are cached for reproducibility.

---
*[PolicyEngine](https://policyengine.org) · [PolicyBench](https://policybench.org)*
