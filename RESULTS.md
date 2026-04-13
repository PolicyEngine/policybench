# PolicyBench Results

PolicyBench is a no-tools benchmark. Ad hoc local outputs should live under
`results/local/` after a benchmark run. Published leaderboard claims should
instead point to frozen batch directories or `results/paper_exports/`.

## Run

```bash
policybench ground-truth -n 100 --seed 42
policybench eval-no-tools -n 100 --seed 42
policybench analyze --output-dir results/local/analysis
```

## Artifacts

- `results/local/ground_truth.csv`
- `results/local/no_tools/predictions.csv`
- `results/local/analysis/metrics.csv`
- `results/local/analysis/summary_by_model.csv`
- `results/local/analysis/summary_by_variable.csv`
- `results/local/analysis/report.md`

## Methodology

See the [full paper](docs/) and [benchmark code](policybench/) for complete methodology. Reference outputs are computed via [PolicyEngine-US](https://github.com/PolicyEngine/policyengine-us). LLM responses are cached for reproducibility.

---
*[PolicyEngine](https://policyengine.org) · [PolicyBench](https://policybench.org)*
