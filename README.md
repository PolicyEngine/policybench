# PolicyBench

How well can frontier models calculate tax and benefit outcomes without tools?

PolicyBench measures how well frontier AI models estimate selected household tax
and benefit outputs without tools.

For benchmark scope, snapshot policy, and terminology, see the
[benchmark card](docs/benchmark_card.md).

US benchmark scenarios are sampled from Enhanced CPS households and evaluated
under 2025 policy rules with PolicyEngine-US. The public UK path uses a
UK-calibrated transfer dataset and PolicyEngine-UK reference outputs.

## Condition

1. **AI alone**: Models estimate tax/benefit values using only their training knowledge

## Benchmark scope

Benchmark outputs are defined in `policybench/benchmark_specs.json`. New CLI
runs default to `v2_headline`, which focuses the main ranking on person- or
household-facing outputs that contribute to household net income. Intermediate
tax bases move to supplementary diagnostics. PolicyEngine variables may be
native to lower-level entities, but v2 headline outputs are either expanded to
people shown in the prompt or aggregated to the household before scoring.
Coverage outputs are binary flags and are weighted using PolicyEngine value
proxies. Payroll component diagnostics live in `v2_supplementary`, not in the
headline ranking.

Old public-snapshot result files, where retained, live under
`results/temporary_legacy_v1_results/` and are not supported by active
benchmark code.

## Programs evaluated

The current public release covers selected federal taxes, credits, benefits,
coverage labels, and state-tax outputs in the US, plus selected tax and
transfer outputs in the UK.

## Quick start

```bash
pip install -e ".[dev]"
pytest  # Run tests (mocked, no API calls)
```

## Benchmark run

```bash
# Generate reference outputs for 100 sampled households using v2_headline
policybench ground-truth -n 100 --seed 42

# Run AI-alone evaluations on the exported scenario manifest
policybench eval-no-tools -n 100 --seed 42

# Analyze local results and export local artifacts
policybench analyze --output-dir results/local/analysis
```

## Repeated runs

```bash
# Optional: run the same benchmark multiple times on the saved scenario manifest
policybench eval-no-tools-repeated -n 100 --seed 42 --repeats 3 -o results/local/no_tools/runs

# Analyze the canonical point estimate plus across-run stability
policybench analyze --runs-dir results/local/no_tools/runs --output-dir results/local/analysis
```

`policybench ground-truth` writes `results/local/scenarios.csv`, and the eval
commands reuse that manifest by default instead of regenerating households from
the current source dataset. Prediction CSVs also get a `.meta.json` sidecar so
resumes only happen against the exact same manifest, model set, and program set.
