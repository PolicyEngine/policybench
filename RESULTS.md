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

## Full v2 runbook

Use a dated batch directory and keep model outputs per country and model so
interrupted runs can resume independently.

```bash
RUN_DIR=results/full_batch_v2_20260425

policybench ground-truth -n 1000 --seed 42 --country us --program-set v2_headline \
  -o "$RUN_DIR/us/ground_truth.csv" \
  --scenario-manifest-output "$RUN_DIR/us/scenarios.csv"

policybench ground-truth -n 1000 --seed 42 --country uk --program-set v2_headline \
  -o "$RUN_DIR/uk/ground_truth.csv" \
  --scenario-manifest-output "$RUN_DIR/uk/scenarios.csv"

for country in us uk; do
  for model in claude-opus-4.6 claude-sonnet-4.6 claude-haiku-4.5 \
    grok-4.20 grok-4.1-fast gpt-5.4 gpt-5.4-mini gpt-5.4-nano \
    gemini-3.1-pro-preview gemini-3-flash-preview \
    gemini-3.1-flash-lite-preview; do
    python scripts/run_full_model_chunks.py \
      --run-dir "$RUN_DIR" \
      --country "$country" \
      --model "$model" \
      --program-set v2_headline \
      --chunk-size 50 \
      --parallel 4
  done
done

python scripts/export_full_run.py --run-dir "$RUN_DIR"
```

For first-pass cost control, run the same commands with `-n 100` in a separate
scratch directory before launching the 1,000-household batch.

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
