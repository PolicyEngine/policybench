# Benchmark Runbook

This is the canonical procedure for paid no-tools benchmark runs. Treat
`results/local/` as scratch space; git history and release snapshots are the
archive, not superseded local files.

## 1. Pick a Run Directory

Use a dated, descriptive run directory and keep US and UK artifacts under it.

```bash
RUN_DIR=results/local/full_run_YYYYMMDD_policyengine_X_Y_Z
SEED=42
N=100
```

Before spending on model calls, run the test suite and confirm the intended
PolicyEngine version in `uv.lock`.

```bash
uv run pytest -q
```

## 2. Generate Reference Outputs

Generate the scenario manifest and PolicyEngine reference outputs once per
country. Do not regenerate scenarios after predictions start.

```bash
uv run python -m policybench.cli reference-outputs \
  --country us \
  --num-scenarios "$N" \
  --seed "$SEED" \
  --output "$RUN_DIR/us/reference_outputs.csv" \
  --scenario-manifest-output "$RUN_DIR/us/scenarios.csv"

uv run python -m policybench.cli reference-outputs \
  --country uk \
  --num-scenarios "$N" \
  --seed "$SEED" \
  --output "$RUN_DIR/uk/reference_outputs.csv" \
  --scenario-manifest-output "$RUN_DIR/uk/scenarios.csv"
```

If PolicyEngine rules change after paid model responses have been collected,
refresh only the reference outputs against the frozen scenario manifests. Do not
rerun or resample scenarios unless you also rerun model calls.

```bash
uv run python -m policybench.cli reference-outputs \
  --country us \
  --scenario-manifest "$RUN_DIR/us/scenarios.csv" \
  --scenario-manifest-output "$RUN_DIR/us/scenarios.csv" \
  --output "$RUN_DIR/us/reference_outputs.csv"
```

## 3. Run Claude Separately

Run Claude models serially. Claude calls need the main-thread wall timeout, and
the explained-output contract currently chunks Claude to one output per provider
request for reliability.

```bash
for country in us uk; do
  for model in claude-opus-4.8 claude-sonnet-4.6 claude-haiku-4.5; do
    uv run python -m policybench.cli eval-no-tools-chunked \
      --country "$country" \
      --scenario-manifest "$RUN_DIR/$country/scenarios.csv" \
      --output-dir "$RUN_DIR/$country" \
      --model "$model" \
      --chunk-size 5 \
      --parallel 1 \
      --model-parallel 1 \
      --chunk-attempts 1
  done
done
```

Do not raise `--parallel` or `--model-parallel` for Claude unless the timeout
implementation has been made thread-safe and tested.

## 4. Run Non-Claude Models by Provider

Run the remaining default models in provider groups. This is the preferred
parallelism boundary: it keeps provider-specific rate limits and failures
separate, while still allowing OpenAI, xAI, Gemini, and DeepSeek to run at the
same time.

```bash
# Terminal 1: xAI
for country in us uk; do
  uv run python -m policybench.cli eval-no-tools-chunked \
    --country "$country" \
    --scenario-manifest "$RUN_DIR/$country/scenarios.csv" \
    --output-dir "$RUN_DIR/$country" \
    --model grok-4.3 \
    --model grok-build-0.1 \
    --chunk-size 5 \
    --parallel 2 \
    --model-parallel 2 \
    --chunk-attempts 1
done

# Terminal 2: OpenAI
for country in us uk; do
  uv run python -m policybench.cli eval-no-tools-chunked \
    --country "$country" \
    --scenario-manifest "$RUN_DIR/$country/scenarios.csv" \
    --output-dir "$RUN_DIR/$country" \
    --model gpt-5.5 \
    --model gpt-5.4-mini \
    --model gpt-5.4-nano \
    --chunk-size 5 \
    --parallel 2 \
    --model-parallel 2 \
    --chunk-attempts 1
done

# Terminal 3: Gemini
for country in us uk; do
  uv run python -m policybench.cli eval-no-tools-chunked \
    --country "$country" \
    --scenario-manifest "$RUN_DIR/$country/scenarios.csv" \
    --output-dir "$RUN_DIR/$country" \
    --model gemini-3.1-pro-preview \
    --model gemini-3.5-flash \
    --model gemini-3-flash-preview \
    --model gemini-3.1-flash-lite \
    --chunk-size 5 \
    --parallel 1 \
    --model-parallel 2 \
    --chunk-attempts 1
done

# Terminal 4: DeepSeek
for country in us uk; do
  uv run python -m policybench.cli eval-no-tools-chunked \
    --country "$country" \
    --scenario-manifest "$RUN_DIR/$country/scenarios.csv" \
    --output-dir "$RUN_DIR/$country" \
    --model deepseek-v4-pro \
    --model deepseek-v4-flash \
    --chunk-size 5 \
    --parallel 1 \
    --model-parallel 2 \
    --chunk-attempts 1
done
```

If a provider begins rate-limiting or producing transport errors, reduce only
that provider group. For example, keep OpenAI and Gemini running while lowering
xAI to `--parallel 1 --model-parallel 1`.

The current default non-Claude model set is:

```bash
grok-4.3
grok-build-0.1
gpt-5.5
gpt-5.4-mini
gpt-5.4-nano
gemini-3.1-pro-preview
gemini-3.5-flash
gemini-3-flash-preview
gemini-3.1-flash-lite
deepseek-v4-pro
deepseek-v4-flash
```

The runner skips complete chunks and rewrites per-model merged CSVs on resume.
Provider transport, timeout, rate-limit, server, authentication, and
request-configuration errors are infrastructure failures; chunks containing
those errors remain incomplete and should be retried or rerun.

## 5. Retry Broken Full Responses

Before freezing a paid run, run bounded full-response retries for households
where a model violated the canonical response contract. The contract requires
one numeric answer and one nonempty explanation for every requested output.
Retries target the full `(country, model, household)` response, not individual
output rows, so the final file never mixes values from different attempts within
one model-household response.

```bash
uv run policybench retry-failed-responses \
  --country us \
  --source-predictions "$RUN_DIR/us/predictions.csv" \
  --scenario-manifest "$RUN_DIR/us/scenarios.csv" \
  --output-dir "$RUN_DIR/us/response_retries/round_1" \
  --chunk-size 5 \
  --parallel 2 \
  --model-parallel 2 \
  --chunk-attempts 1
```

For later rounds, pass the previous round's `merged_predictions.csv.gz` as
`--source-predictions` and write to a new round directory.

```bash
uv run policybench retry-failed-responses \
  --country us \
  --source-predictions "$RUN_DIR/us/response_retries/round_1/merged_predictions.csv.gz" \
  --scenario-manifest "$RUN_DIR/us/scenarios.csv" \
  --output-dir "$RUN_DIR/us/response_retries/round_2" \
  --chunk-size 5 \
  --parallel 2 \
  --model-parallel 2 \
  --chunk-attempts 1
```

Each retry directory writes:

- `target_units.csv`: full responses selected for retry.
- `original_failed_responses.csv.gz`: the original rows for those responses.
- `retry_predictions.csv`: raw retry rows returned by the models.
- `accepted_retry_units.csv`: responses that fully satisfied the contract.
- `rejected_retry_units.csv`: responses rejected and why.
- `accepted_retry_rows.csv.gz`: retry rows accepted into the merged file.
- `replaced_original_responses.csv.gz`: original rows replaced by accepted retries.
- `merged_predictions.csv.gz`: source predictions with accepted full responses replaced.

Use `--prepare-only` to estimate retry scope without model calls. Use repeated
`--model` flags for targeted later rounds when an earlier round shows that some
models have near-zero retry yield.

## 6. Merge and Export

After all per-model files exist, run one final merge pass per country. This
should skip all completed chunks and write the combined `predictions.csv`.

```bash
for country in us uk; do
  uv run python -m policybench.cli eval-no-tools-chunked \
    --country "$country" \
    --scenario-manifest "$RUN_DIR/$country/scenarios.csv" \
    --output-dir "$RUN_DIR/$country" \
    --chunk-size 5 \
    --parallel 1 \
    --model-parallel 1 \
    --chunk-attempts 1
done

uv run python -m policybench.cli export-full-run --run-dir "$RUN_DIR"
```

If a retry round is adopted for the public snapshot, point analysis and
`export-full-run` at the final `merged_predictions.csv.gz`, not the pre-retry
prediction file. Keep the retry directory with the frozen snapshot so readers
can inspect both the original failed responses and the accepted replacements.

Then run verification before committing or deploying.

```bash
uv run pytest -q
cd app
bun install --frozen-lockfile
bun run lint
bun test tests
bun run build
```

## 7. Progress and Cost Check

Use this during a run to inspect checkpoint coverage and estimated cost.

```bash
uv run python - <<'PY'
from pathlib import Path
import pandas as pd

run = Path("results/local/full_run_YYYYMMDD_policyengine_X_Y_Z/us")
for model_dir in sorted((run / "chunks").glob("*")):
    files = sorted(model_dir.glob("*.csv"))
    rows = missing = errors = 0
    cost = 0.0
    for path in files:
        frame = pd.read_csv(path)
        rows += len(frame)
        missing += int(frame["prediction"].isna().sum())
        if "error" in frame:
            errors += int(frame["error"].fillna("").astype(str).str.strip().ne("").sum())
        cost += float(frame.get("estimated_cost_usd", pd.Series(dtype=float)).fillna(0).sum())
    print(
        model_dir.name,
        f"{len(files)}/20 chunks",
        f"{rows} rows",
        f"{missing} missing",
        f"{errors} error rows",
        f"${cost:.2f}",
    )
PY
```
