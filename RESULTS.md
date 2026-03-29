# PolicyBench Results

PolicyBench is a no-tools benchmark. Generated outputs live in `results/analysis/` after a benchmark run.

## Run

```bash
policybench ground-truth -n 100 --seed 42
policybench eval-no-tools -n 100 --seed 42
policybench analyze --output-dir results/analysis
```

## Artifacts

- `results/ground_truth.csv`
- `results/no_tools/predictions.csv`
- `results/analysis/metrics.csv`
- `results/analysis/summary_by_model.csv`
- `results/analysis/summary_by_variable.csv`
- `results/analysis/report.md`

## Methodology

See the [full paper](docs/) and [benchmark code](policybench/) for complete methodology. Ground truth is computed via [PolicyEngine-US](https://github.com/PolicyEngine/policyengine-us). LLM responses are cached for reproducibility.

---
*[PolicyEngine](https://policyengine.org) · [PolicyBench](https://policybench.org)*
