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
  for model in claude-fable-5 claude-opus-4.8 claude-opus-4.7 \
    claude-sonnet-5 claude-sonnet-4.6 claude-haiku-4.5; do
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
separate, while still allowing independent provider groups to run at the same
time.

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
# STOP: run the GPT-5.6 onboarding/smoke gate below before its first full run.
for country in us uk; do
  uv run python -m policybench.cli eval-no-tools-chunked \
    --country "$country" \
    --scenario-manifest "$RUN_DIR/$country/scenarios.csv" \
    --output-dir "$RUN_DIR/$country" \
    --model gpt-5.6-sol \
    --model gpt-5.6-terra \
    --model gpt-5.6-luna \
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
    --model gemini-3.1-flash-lite-preview \
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
    --parallel 2 \
    --model-parallel 2 \
    --chunk-attempts 1
done

# Terminal 5: models served through OpenRouter
for country in us uk; do
  uv run python -m policybench.cli eval-no-tools-chunked \
    --country "$country" \
    --scenario-manifest "$RUN_DIR/$country/scenarios.csv" \
    --output-dir "$RUN_DIR/$country" \
    --model kimi-k2.6 \
    --model glm-5.2 \
    --model minimax-m3 \
    --model qwen-3.7-max \
    --chunk-size 5 \
    --parallel 1 \
    --model-parallel 2 \
    --chunk-attempts 1
done

# Terminal 6: Meta Model API (requires MODEL_API_KEY)
# STOP: run the Muse onboarding/smoke gate below before its first full run.
for country in us uk; do
  uv run python -m policybench.cli eval-no-tools-chunked \
    --country "$country" \
    --scenario-manifest "$RUN_DIR/$country/scenarios.csv" \
    --output-dir "$RUN_DIR/$country" \
    --model muse-spark-1.1 \
    --chunk-size 5 \
    --parallel 2 \
    --model-parallel 1 \
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
gpt-5.6-sol
gpt-5.6-terra
gpt-5.6-luna
gpt-5.5
gpt-5.4-mini
gpt-5.4-nano
muse-spark-1.1
gemini-3.1-pro-preview
gemini-3.5-flash
gemini-3-flash-preview
gemini-3.1-flash-lite-preview
deepseek-v4-pro
deepseek-v4-flash
kimi-k2.6
glm-5.2
minimax-m3
qwen-3.7-max
```

OpenAI made [GPT-5.6 generally available](https://openai.com/index/gpt-5-6/)
across ChatGPT, Codex, and the API on 2026-07-09, with a global rollout over 24
hours. Because these models are new to the PolicyBench harness, run the serving
gauntlet and a two-scenario smoke for each model before committing to a paid
full run:

```bash
for model in gpt-5.6-sol gpt-5.6-terra gpt-5.6-luna; do
  uv run policybench onboard \
    --model-id "$model" \
    --scenario-manifest "$RUN_DIR/us/scenarios.csv" \
    --report-output "$RUN_DIR/us/${model}-onboarding.md"

  uv run policybench eval-no-tools \
    --country us \
    --scenario-manifest "$RUN_DIR/us/scenarios.csv" \
    --num-scenarios "$N" \
    --model "$model" \
    --scenario-end 2 \
    --output "$RUN_DIR/us/${model}-smoke.csv"
done
```

The bare `gpt-5.6` alias resolves to Sol and must not be added as a separate
benchmark row. GPT-5.6 Pro is a product/request mode rather than a separate API
model id, so it is also not a separate benchmark row.

Meta released [Muse Spark 1.1](https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/)
and the Meta Model API in public preview on 2026-07-09. The official model id
is `muse-spark-1.1`; PolicyBench routes it to `https://api.meta.ai/v1` with the
dedicated `MODEL_API_KEY`. Do not reuse `OPENAI_API_KEY` even though Meta's API
is OpenAI-compatible. Meta currently supports only automatic tool choice, so
the model card deliberately uses PolicyBench's JSON answer contract.

Before a paid run, onboard the full LiteLLM id and smoke the display alias:

```bash
uv run policybench onboard \
  --model-id openai/muse-spark-1.1 \
  --scenario-manifest "$RUN_DIR/us/scenarios.csv" \
  --report-output "$RUN_DIR/us/muse-spark-1.1-onboarding.md"

uv run policybench eval-no-tools \
  --country us \
  --scenario-manifest "$RUN_DIR/us/scenarios.csv" \
  --num-scenarios "$N" \
  --model muse-spark-1.1 \
  --scenario-end 2 \
  --output "$RUN_DIR/us/muse-spark-1.1-smoke.csv"
```

The runner skips complete chunks and rewrites per-model merged CSVs on resume.
Provider transport, timeout, rate-limit, server, authentication, and
request-configuration errors are infrastructure failures; chunks containing
those errors remain incomplete and should be retried or rerun.

## 4b. Batch Mode (Anthropic, OpenAI, Gemini)

`eval-no-tools-batch` runs the same evaluation through the provider's batch
API at ~50% of synchronous prices, with the provider handling parallelism.
Request bodies are identical to sync mode; results land in the same
`by_model/<model>.csv` schema, so retries, export, and the runstore work
unchanged. The harness has no batch adapter for xAI, DeepSeek, Meta, or
OpenRouter-routed models — keep using the chunked runner for them. OpenAI's
Batch API also rejected the GPT-5.6 family as unsupported on 2026-07-09; use
the resumable sync supervisor until OpenAI enables those ids for Batch.

```bash
uv run policybench eval-no-tools-batch \
  --country us \
  --scenario-manifest "$RUN_DIR/us/scenarios.csv" \
  --output-dir "$RUN_DIR/us" \
  --model claude-fable-5 --model claude-sonnet-5 \
  --poll-seconds 30
```

Batch ids persist under `$RUN_DIR/us/batches/`; rerunning the command
resumes polling instead of resubmitting. Contract violations are re-requested
in bounded repair rounds as follow-up batches. Two reporting differences,
both deliberate: latency columns are left empty (batch round-trips include
provider queue time, which is not model latency), and cost columns are
reconstructed at standard synchronous rates so the leaderboard basis stays
comparable while actual spend is roughly half.

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

## 5b. Repair Individual Broken Rows

Full-response retries (Section 5) replace an entire `(country, model,
household)` response. Some individual output rows can still be missing a parsed
value or explanation after retries converge. `repair-failed-rows` targets those
rows in isolation and leaves the rest of each response untouched. The
manuscript's Appendix A reports the yield from this step, so it is part of
reproducing the frozen snapshot.

```bash
uv run policybench repair-failed-rows \
  --country us \
  --source-predictions "$RUN_DIR/us/response_retries/round_1/merged_predictions.csv.gz" \
  --scenario-manifest "$RUN_DIR/us/scenarios.csv" \
  --output-dir "$RUN_DIR/us/row_repairs/round_1" \
  --attempts-per-row 3 \
  --parallel 4
```

Pass `--source-predictions` the latest merged file — the Section 5 response-retry
output if that ran, otherwise the per-model `predictions.csv`. Use
`--prepare-only` to count broken rows without model calls, `--max-rows` for smoke
tests, and repeated `--model` flags to restrict targets. Each round writes
`target_rows.csv`, `row_repair_attempts.csv`,
`accepted_row_repair_rows.csv.gz`, and `merged_predictions.csv.gz`; point the
Section 6 export at the final `merged_predictions.csv.gz`.

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
