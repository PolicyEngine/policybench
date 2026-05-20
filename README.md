# PolicyBench

How well can frontier models calculate tax and benefit outcomes without tools?

PolicyBench measures how well frontier AI models estimate selected household tax
and benefit outputs without tools.

For benchmark scope, snapshot policy, and terminology, see the
[benchmark card](https://github.com/PolicyEngine/policybench/blob/main/docs/benchmark_card.md).

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
coverage labels, and state-tax outputs in the US, plus selected tax and transfer
outputs in the UK. US federal income tax is scored as a compact decomposition:
tax after nonrefundable credits and before refundable credits, plus refundable
federal credits excluding the ACA Premium Tax Credit. The May 2026 source run
requested ACA Premium Tax Credit responses, but they are excluded from the
canonical scored leaderboard because explanation audits showed prompt ambiguity
without plan-specific Marketplace information.

## Quick start

```bash
pip install policybench
policybench --help
```

For repository development, clone the full Git repository before running tests:

```bash
pip install -e ".[dev]"
pytest
```

## Benchmark run

For paid/public runs, follow the concrete
[benchmark runbook](https://github.com/PolicyEngine/policybench/blob/main/docs/runbook.md).
The short version is: generate fixed reference-output manifests first, run
Claude models serially, run non-Claude models in parallel, then do a final merge
and export pass.

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
  --parallel 1

# Non-Claude models can be run with higher concurrency after a smoke test.
# Claude models must use --parallel 1 and --model-parallel 1.

# Analyze local results and export local artifacts
policybench analyze --output-dir results/local/analysis
```

## Response-contract retries

For paid runs, retry broken full responses before freezing a snapshot:

```bash
policybench retry-failed-responses \
  --country us \
  --source-predictions results/local/full_run/us/predictions.csv \
  --scenario-manifest results/local/full_run/us/scenarios.csv \
  --output-dir results/local/full_run/us/response_retries/round_1
```

This retries whole model-household responses with missing numeric answers,
missing explanations, or infrastructure errors. Accepted retries replace the
entire original response; partial retry responses are rejected and the original
rows are preserved.

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
