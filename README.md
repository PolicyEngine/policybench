# PolicyBench

How well can frontier models calculate tax and benefit outcomes without tools?

PolicyBench measures how well frontier AI models estimate selected household tax
and benefit outputs without tools.

For benchmark scope, snapshot policy, and terminology, see the
[benchmark card](docs/benchmark_card.md).

US benchmark scenarios are sampled from Enhanced CPS households and evaluated
under tax year 2026 rules with PolicyEngine-US. The public UK path uses a
UK-calibrated transfer dataset and PolicyEngine-UK reference outputs for fiscal
year 2026-27.

## Condition

1. **AI alone**: Models estimate tax/benefit values using only their training knowledge

## Benchmark scope

Benchmark outputs are defined in `policybench/benchmark_specs.json`. New CLI
runs default to `headline`, which focuses the main ranking on person- or
household-facing outputs that contribute to household net income. PolicyEngine
variables may be native to lower-level entities, but benchmark outputs are
either expanded to people shown in the prompt or aggregated to the household
before scoring. Coverage outputs are binary flags in the headline ranking; the
separate household-equal impact score uses PolicyEngine value proxies to give
those flags a dollar-scale weight. Intermediate tax bases and payroll
subcomponents are excluded from the headline ranking. WIC is requested as
person-level eligibility, not as a dollar amount.

## Programs evaluated

The current public release covers selected federal taxes, credits, benefits,
health-related support, coverage labels, and state-tax outputs in the US, plus
selected tax and transfer outputs in the UK. US federal income tax is scored as
a compact decomposition: tax after nonrefundable credits and before refundable
credits, plus refundable federal credits excluding the ACA Premium Tax Credit.
The ACA Premium Tax Credit is scored separately as a health-related output.

## Quick start

```bash
pip install -e ".[dev]"
pytest  # Run tests (mocked, no API calls)
```

## Benchmark run

```bash
# Generate reference outputs for 100 sampled households using headline outputs
policybench reference-outputs -n 100 --seed 42

# Run AI-alone evaluations on the exported scenario manifest.
# The standard response contract includes numeric answers and explanations.
policybench eval-no-tools -n 100 --seed 42

# For larger runs, use resumable per-model chunks.
policybench eval-no-tools-chunked \
  --scenario-manifest results/local/scenarios.csv \
  --output-dir results/local/no_tools_chunked \
  --country us \
  --chunk-size 10 \
  --parallel 2

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

`policybench reference-outputs` writes PolicyEngine reference outputs, not
administrative truth. It also writes `results/local/scenarios.csv`, and the eval
commands reuse that manifest by default instead of regenerating households from
the current source dataset. Prediction CSVs also get a `.meta.json` sidecar so
resumes only happen against the exact same manifest, model set, and program set.
`policybench ground-truth` remains as a compatibility alias.
