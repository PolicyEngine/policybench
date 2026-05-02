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
truth. `policybench ground-truth` remains as a compatibility alias.

## Full runbook

Use a dated batch directory and keep model outputs per country and model so
interrupted runs can resume independently.

```bash
RUN_DIR=results/full_batch_20260501

policybench reference-outputs -n 1000 --seed 42 --country us --program-set headline \
  -o "$RUN_DIR/us/reference_outputs.csv" \
  --scenario-manifest-output "$RUN_DIR/us/scenarios.csv"

policybench reference-outputs -n 1000 --seed 42 --country uk --program-set headline \
  -o "$RUN_DIR/uk/reference_outputs.csv" \
  --scenario-manifest-output "$RUN_DIR/uk/scenarios.csv"

for country in us uk; do
  for model in claude-opus-4.7 claude-sonnet-4.6 claude-haiku-4.5 \
    grok-4.3 grok-4.20 grok-4.1-fast gpt-5.5 gpt-5.4-mini gpt-5.4-nano \
    gemini-3.1-pro-preview gemini-3-flash-preview \
    gemini-3.1-flash-lite-preview; do
    policybench eval-no-tools-chunked \
      --scenario-manifest "$RUN_DIR/$country/scenarios.csv" \
      --output-dir "$RUN_DIR/$country/no_tools_chunked" \
      --country "$country" \
      --model "$model" \
      --program-set headline \
      --chunk-size 50 \
      --parallel 4
  done
done

for country in us uk; do
  mkdir -p "$RUN_DIR/$country/by_model"
  cp "$RUN_DIR/$country/no_tools_chunked/by_model/"*.csv "$RUN_DIR/$country/by_model/"
done

python scripts/export_full_run.py --run-dir "$RUN_DIR"
```

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
