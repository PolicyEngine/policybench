# Benchmark Runbook

This is the canonical procedure for paid no-tools benchmark runs. Treat
`results/local/` as scratch space; git history and release snapshots are the
archive, not superseded local files.

## 0. Launch long runs under launchd

A paid `policybench run` takes hours. Start it with `scripts/launch_run.sh`,
which installs a per-run launchd user agent, rather than with `nohup … &` from
a terminal or an agent session. The job then belongs to launchd, not to the
shell, terminal, or Claude Code session that started it: it keeps running when
that process group is torn down, it comes back after a reboot (`RunAtLoad`),
and if it is killed before finishing, launchd relaunches it and the supervisor
resumes from `run_state.json` and the per-scenario CSVs (`KeepAlive` on an
unfinished exit). A run that stops on purpose (budget stop, rounds exhausted,
every scenario complete) unloads itself.

```bash
export OPENROUTER_API_KEY=...            # provider credentials are copied into the job
scripts/launch_run.sh start --name glm53 --model glm-5.3 \
  --scenario-manifest paper/snapshot/20260501/us_scenarios.csv \
  --run-dir results/local/newmodels/glm53/run \
  --budget-usd 40 --max-workers 5

scripts/launch_run.sh status glm53       # launchd state, heartbeat summary, last log lines
scripts/launch_run.sh logs glm53         # supervisor.log and launchd.log from the run dir
scripts/launch_run.sh stop glm53         # SIGTERM, then SIGKILL, of the job's process group
scripts/launch_run.sh list
```

Run it from the checkout whose code you want to benchmark; that checkout
becomes `PYTHONPATH` and the supervisor executable defaults to its `.venv`
(or the main clone's `.venv` when run from a worktree). Add `--dry-run` to
print the plist instead of installing it. Variables named `*_API_KEY` or
`*_API_TOKEN`, or prefixed `ANTHROPIC_`, `OPENAI_`, `OPENROUTER_`, `GEMINI_`,
`GOOGLE_`, `XAI_`, `DEEPSEEK_`, `LITELLM_`, or `POLICYENGINE_`, are forwarded
into the job because launchd does not inherit a shell's environment; endpoint
overrides (`*_BASE_URL`, `*_API_BASE`) are not, since a Claude Code session
exports `ANTHROPIC_BASE_URL` for its own proxy. Pass anything else with
`--env NAME` or `--env NAME=VALUE`, or keep secrets in a mode-600 file and pass
`--env-file`. The plist itself is written mode 600 under
`~/Library/LaunchAgents/org.policyengine.policybench.<name>.plist`.

The supervisor's stdout and stderr append to `<run dir>/supervisor.log`
across relaunches; launchd's own output goes to `<run dir>/launchd.log`.
`.launchd_restarts` counts consecutive unfinished exits (the wrapper gives up
after `--max-restarts`, default 5, and writes `.launchd_gave_up`);
`.launchd_done` marks a finished run.

### What actually kills a run

Investigated on 2026-09-04, when two board runs launched with
`nohup caffeinate -i policybench run … & disown` from a Claude Code session
died with `stopped_reason: null` and an empty log:

- A **reboot** (`sysctl kern.boottime`; the Mac restarted at 10:14) killed the
  GLM-5.3 run. `pmset -g log` showed no sleep, which is what made the deaths
  look like session restarts. A launchd job with `RunAtLoad` resumes after a
  reboot; a `nohup` job does not.
- A **broad pattern kill** from another session,
  `for p in $(pgrep -f "codex-api|gpt-6-astra"); do kill -9 $p; done`, took
  out the GPT-6 Astra supervisor and its workers three minutes after launch:
  the model id is in every worker's command line and is shared with unrelated
  tooling that runs the same model. Never `pkill -f` a model id. Match the
  run directory instead (`pkill -f -- "--run-dir $RUN_DIR"`), or use
  `scripts/launch_run.sh stop`. launchd relaunches a job killed this way.
- The run's own `pkill -f "policybench run --model glm-5.3"` during a
  deliberate relaunch.

What does **not** kill a `nohup … & disown` child: the Bash tool call
returning, the session process exiting, or the session process receiving
SIGTERM or SIGKILL. All three were tested against the Claude Code binary; the
harness only signals the process group of a command that is still running,
timed out, or was aborted, and background tasks (`run_in_background`) of an
exiting agent. Children of a finished foreground command are not tracked.
Note that `caffeinate -i cmd` execs `cmd` in the original pid and forks a
helper, so `pkill -f` on the command line matches the helper too.

### Regression check

`scripts/check_run_survival.sh` (macOS only, no model calls) launches
`/bin/sleep` through the launcher next to a plain `nohup` control from a
throwaway process group, kills that whole group with SIGTERM and SIGKILL,
checks that the control died and the launchd job survived, SIGKILLs the job
and checks that launchd relaunched it, then stops it through the launcher and
checks that nothing is left. Run it after touching the launcher or the
wrapper. `tests/test_launch_run.py` covers the plist rendering, credential
forwarding, and the wrapper's exit-code policy without launchd, so it runs in
CI.

To confirm survival across a Claude Code session restart specifically, start
a run with the launcher from a session, restart or pause that session, and run
`scripts/launch_run.sh status <name>` from a new one: the launchd pid and the
`supervisor.log` mtime keep advancing.

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

```

If a provider begins rate-limiting or producing transport errors, reduce only
that provider group. For example, keep OpenAI and Gemini running while lowering
xAI to `--parallel 1 --model-parallel 1`.

The current default non-Claude model set is:

```bash
grok-4.3
grok-4.5
grok-build-0.1
gpt-5.6-sol
gpt-5.6-terra
gpt-5.6-luna
gpt-5.5
gpt-5.4-mini
gpt-5.4-nano
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

The runner skips complete chunks and rewrites per-model merged CSVs on resume.
Provider transport, timeout, rate-limit, server, authentication, and
request-configuration errors are infrastructure failures; chunks containing
those errors remain incomplete and should be retried or rerun.
Each evaluation CSV also has a `.spend.jsonl` call ledger. It records initial,
failed, and repair calls separately; the supervisor uses this sidecar for its
disk spend total and falls back to the legacy CSV total when no ledger exists.

## 4b. Batch Mode (Anthropic, OpenAI, Gemini)

`eval-no-tools-batch` runs the same evaluation through the provider's batch
API at ~50% of synchronous prices, with the provider handling parallelism.
Request bodies are identical to sync mode; results land in the same
`by_model/<model>.csv` schema, so retries, export, and the runstore work
unchanged. The harness has no batch adapter for xAI, DeepSeek, or
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
The per-model `batches/<model>.spend.jsonl` ledger retains every initial and
repair result and de-duplicates a resumed batch by its provider batch id and
custom id. Completed runs mirror it next to the per-model CSV so the combined
predictions ledger includes batch calls.

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
bun run test
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
