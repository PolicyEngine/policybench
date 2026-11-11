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

DeepSeek retired V4 Flash on 2026-09-10, when it released V4.1 Flash
([news](https://api-docs.deepseek.com/news/news260910)). The
`deepseek-v4-flash` name now routes to V4.1 Flash, and `deepseek-v4-pro` had
already moved to the August V4 Pro release, so neither row can be re-run under
its name. V4.1 Flash is the `deepseek-v4.1-flash` row, which calls
DeepSeek's current name `deepseek-flash`.

Google deprecated `gemini-3.5-flash` and `gemini-3.7-flash` on 2026-10-08
([changelog](https://ai.google.dev/gemini-api/docs/changelog)). Requests under
those names now route to `gemini-3.6-flash` and `gemini-3.8-flash`, which are
rows of their own, so neither row can be re-run under its name. A synchronous
re-run or row repair would not show the re-route: litellm (1.88.x, 1.95.0)
sets the response model to the requested name, which PolicyBench records as
`provider_resolved_model`, and ignores Gemini's `modelVersion`. The Gemini
batch path, which calls google-genai directly, does record `modelVersion`.

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

A model with no card in `policybench/model_cards.py` is probed under the
thinking-class card the gauntlet derives (`thinking_budget=True`: a 16,384-token
completion budget and, by default, a 300-second timeout). That card is
registered only while the probes run, so there is no need to write a
provisional card before onboarding. Without it, GPT-6.1 Sol fell through to the
harness's card-less default of 384 tokens for three outputs, and the gauntlet
reported it not scorable. A model that already has a card is probed under that
card. The report names the card the probes ran under and gives each probe's
budget and timeout.

The timeout comes from that card too, so a card-less `xai/` id gets 300 seconds
where the family heuristic gave it 420, and `POLICYBENCH_XAI_REQUEST_TIMEOUT_SECONDS`
no longer applies to its probes. A probe that times out is reported as an
environment error (ABORTED), not as a serving fact. A model that needs more than
the thinking-class defaults still needs a hand-written card with a larger
`completion_token_cap` or `request_timeout_seconds` before its gauntlet, as Kimi
K3, Qwen 3.8 Max and Grok 4.7 did. Board models that run without a card are
probed under the provisional card as well. For Grok 4.3, Grok Build 0.1, GPT-5.4
mini and nano, and Claude Opus 4.7 and 4.8, that differs from their board
treatment.

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
A single-country supervised run (`policybench run`) writes
`policyengine_provenance.json` to its run directory at start, from a one-off
Python process. The file holds the PolicyEngine bundle provenance that every
scenario sidecar records, plus a fingerprint of the installed PolicyEngine
packages. Workers read it through `POLICYBENCH_POLICYENGINE_PROVENANCE`
instead of computing it, and the supervisor checks each worker's
sidecar against the copy it read back. A worker whose environment no longer
matches the fingerprint computes the provenance itself, as every worker did
before; `run_state.json` counts those workers in
`policyengine_provenance_recomputed`. When no file was written (a
mixed-country manifest, or a failed write), `run_state.json` shows
`policyengine_provenance: null` and every worker computes it.

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

## 8. Call provenance

The harness caches provider responses on disk (`policybench/cache.py`). A
request identical to an earlier one returns the cached response, and the
timer measures the lookup, a few hundredths of a second, as if it were the
call. Each prediction row therefore records where its responses came from:

| Column | Meaning |
| --- | --- |
| `live_calls` | responses behind the row that the provider answered |
| `cache_hit_calls` | responses behind the row that the disk cache replayed |
| `live_elapsed_seconds` | the live calls' share of `elapsed_seconds` |

The counts cover the request group whose time the row's `elapsed_seconds`
apportions: the whole household for `run_no_tools_eval` (every chunk, repair
round, budget escalation and explanation repair), the one output for
single-output runs and row repairs, and the one request for batch rows.
Every row of a group repeats them, so never sum them across rows.
`live_elapsed_seconds` is divided among the rows like `elapsed_seconds`, so a
household's live time is the sum over its rows. A replay adds its lookup time
to `elapsed_seconds` and nothing to `live_elapsed_seconds`. Failed attempts
are not counted here; the spend ledger records them.

Batch rows have `cache_hit_calls` 0 (batch requests never read the disk
cache), `live_calls` 1 when a response answered them, and no live time, like
their empty `elapsed_seconds`. Rows written before these columns existed,
including the frozen board's, leave all three empty, and a supervised run
resumed across the change accepts those scenario files. A row-repair merge
that applies an older repair, written without the columns, empties them on
the row it replaces rather than keep the replaced request's values.

The values hold these invariants, which `tests/test_call_provenance.py`
checks with property-based tests that drive the real request path, failed
requests included, against the calls actually made and the spend ledger's
records of them:

- the counts are non-negative integers;
- `0 <= live_elapsed_seconds <= elapsed_seconds`, and both are empty together;
- a row whose responses were all replays has `live_calls` 0 and
  `live_elapsed_seconds` exactly 0;
- a row with no replays has `live_elapsed_seconds` equal to `elapsed_seconds`.

`call_provenance.household_call_provenance` classifies each household as `live`,
`partial_replay`, `full_replay`, `no_response` or `unknown` (rows that
predate the columns), with its summed live time. No published figure uses it:
`latencySeconds` still takes the median of each household's
`elapsed_seconds`, replays included.

## 8b. Reasoning tokens

`reasoning_tokens` holds a count of the tokens a response spent on reasoning:
the provider's own count wherever its usage reports one. The harness computes
no cost from it.

| Rows | Where the count comes from |
| --- | --- |
| Claude, sync | Anthropic's `usage.output_tokens_details.thinking_tokens` |
| Claude, batch | the same field on the Message Batches entry |
| Other providers | the count their usage reports, as litellm or the batch adapter passes it on |

Anthropic counts thinking inside `output_tokens`, so a Claude row's count
never exceeds its `completion_tokens`. The SDK describes the count as a
re-tokenization of the raw reasoning, delimiter tokens included, which can
differ from the model's exact count by a few tokens. Other providers' counts
carry no such bound: in release 20261027's snapshot (51 models), kimi-k2.6
and deepseek-v4-flash-0731 record more reasoning than completion tokens on
some rows.

litellm 1.95.0 never reads Anthropic's field. It counts reasoning by
tokenizing the thinking text a response returns, and a Claude response can
return a thinking block with empty text, which litellm counts as 0. So
`eval_no_tools.py` wraps litellm's Anthropic usage builder and copies the
provider's count onto the usage object, and `batch_eval.py` reads it from the
SDK's usage.

For Claude rows:

- a count that is a whole number in `[0, output_tokens]` lands on the row
  exactly; the harness records any other count as empty and never clamps one;
- a response with no count records what it did before the change: litellm's
  own count on the sync path, nothing on the batch path;
- a row sums the counts its responses reported (chunks, repair rounds) and
  splits the sum over its outputs, as it does `completion_tokens`;
- a disk-cache replay records what the live call recorded. An entry cached
  before the change holds no provider count, so its replay records litellm's
  count, and a run resumed across the change mixes both kinds of row.

Before the change (#261, November 2026), a sync Claude row held litellm's
count of the thinking text its responses returned, and a batch Claude row held
nothing. A 0 or an empty cell on such a row does not show that the model
skipped reasoning: read it as "not counted". That covers every Claude row
collected before #261 merged, whichever release publishes it. In release
20261027's snapshot, ten Claude models record 0 on every row, and Claude
Fable 5 records no usage.
`tests/test_anthropic_thinking_tokens.py` checks these invariants against two
recorded responses.

## 9. Publish a release

A release is a GitHub release `dashboard-data-YYYYMMDD[a-z]` that holds
`dashboard-data.json` and `predictions.csv.gz`, plus the PR whose committed
pointer, `app/src/data.artifact.json`, names it. The release has to exist
before its PR merges, because CI's app job and Vercel download the asset that
the PR's pointer names. GitHub therefore creates the tag on main as it stands
before the merge, which holds the previous release's board. The Seal release
workflow (`.github/workflows/seal-release.yml`) moves the tag to the release
PR's merge commit when the PR merges.

1. Freeze and render the release, then run the tests.
2. Check that the tag is free: `gh release view <tag>` must fail,
   `git ls-remote origin refs/tags/<tag>` must print nothing, and
   `git log --oneline -S '"<tag>"' origin/main -- app/src/data.artifact.json`
   must print nothing. A tag can exist without a release, as
   `dashboard-data-20260705b` does, and main may have named a tag whose
   release is gone.
3. Create the release with its assets, not marked Latest:
   `gh release create <tag> --latest=false --title <tag> --notes "…" <assets>`.
   `policybench publish-dashboard --tag <tag>` does the same for the payload
   alone. Download the asset and compare its sha256 with the pointer.
4. Open the PR. CI's app job and Vercel download the asset.
5. Squash-merge after green CI and an independent review.
6. The Seal release workflow runs on the merge. It moves the tag to the
   merge commit, checks that GitHub's tag names it, and marks the release
   Latest. Check that the run passed and that
   `git ls-remote origin refs/tags/<tag>` prints the merge commit. If the run
   failed, run `uv run policybench seal-release --landed-after --apply --latest`
   on an up-to-date main.
7. Check prod on policybench.org.

The workflow runs on every push to main. Each run reads main as it is when
the run starts, not the commit of the push that started it. It seals every
release that a first-parent commit of main names after `SEALING_STARTS_AFTER`
in `policybench/release_tags.py` (the merge of release 20261027), so a run
GitHub cancels in favour of a newer one loses nothing. The run refuses to
start if that commit is not on main's first-parent line. It never moves the
tag of a release main named by then. When main points back at one of those
releases with the bytes it named by then, and the release's tag still names a
commit from before sealing began, the run passes over it. Otherwise someone
reused the release's name, replaced its asset or deleted its tag: the run
moves nothing for it and fails, naming the tag. Check the release. If someone
deleted its tag, push the tag back at the commit it named
(`git push origin <commit>:refs/tags/<tag>`). An older clone may still have
that commit (`git rev-parse <tag>^{commit}`); if none does, use the release's
board commit from the table below. If main now names other bytes under the
name, or the tag names a commit from after sealing began, seal it by hand with
`uv run policybench seal-release --tag <tag> --apply`. Later runs then pass
over it. Before and after each move the run reads the release's asset digest
again, and it refuses the move, or reports it, when the asset changed; the
next run plans that tag again. A move GitHub refuses does not stop the
others; the run fails after trying them all. It marks Latest the release main
serves when the run starts, unless that release's own move failed. A release
that lands during a run gets the run for its own push, which starts after
this one ends and marks it Latest.

GitHub has been reported to refuse a tag pushed with `GITHUB_TOKEN` when the
tagged commit's `.github/workflows/` differs from that of every branch head
([community discussion 151442](https://github.com/orgs/community/discussions/151442)).
The workflow moves tags through the REST API, which may meet the same check.
A run that starts right after a release merges moves that release's tag to
main's head, where the two match. A tag the run moves to an older commit, for
a release an earlier run failed to seal, may not match. If a run fails this
way, seal the release by hand with the command in step 6, using a token with
the `workflow` scope.

### Which commit holds a release's board

A release's board commit is the first commit on main's first-parent line
whose pointer names the release's tag and the sha256 of the asset the release
holds now. For a release PR, that is its squash commit. Two commands find it:

```bash
uv run policybench release-commit dashboard-data-20261010
uv run policybench seal-release --all
```

`release-commit` prints the board commit; it reads the asset's sha256 from
GitHub, or from `--sha256`. `seal-release --all` lists every tag, the commit
it names and its board commit, and moves nothing without `--apply`.

A sealed tag names its board commit, so `git checkout <tag>` gives the
release's tree. A clone that fetched a tag before the tag moved keeps the old
commit until `git fetch --tags --force`.

### Releases cut before sealing

The tags from `dashboard-data-20260520` through `dashboard-data-20261027`
predate the workflow. Each names main as it stood before the release PR
merged, or an older commit when other PRs merged between the upload and the
merge. `git checkout <tag>` therefore gives an earlier release's board. Until
those tags are re-pointed with `uv run policybench seal-release --all --apply`,
use the board commit in this table. The asset sha256 is the first 12
characters of the `dashboard-data.json` digest that GitHub records for the
release.

| Release | Board commit | Asset sha256 | PR |
|---|---|---|---|
| `dashboard-data-20260520` | `370949527a7f` | `4686fe4c74c4` | [#65](https://github.com/PolicyEngine/policybench/pull/65) |
| `dashboard-data-20260614` | `e45637138c86` | `460f261649aa` | [#74](https://github.com/PolicyEngine/policybench/pull/74) |
| `dashboard-data-20260616` | `f0ad009cb278` | `497c6c34f3e7` | [#76](https://github.com/PolicyEngine/policybench/pull/76) |
| `dashboard-data-20260625` | `c24ec1dce8de` | `72d4b524fb6d` | none (pushed to main) |
| `dashboard-data-20260701` | `e9e91df49785` | `17016aafbe13` | [#82](https://github.com/PolicyEngine/policybench/pull/82) |
| `dashboard-data-20260702` | `57d26f1c1d3d` | `bea82b7ea984` | [#86](https://github.com/PolicyEngine/policybench/pull/86) |
| `dashboard-data-20260702b` | `547ab24c8694` | `7b26f03fb77c` | [#90](https://github.com/PolicyEngine/policybench/pull/90) |
| `dashboard-data-20260705` | `84dff0663ad9` | `7d43a0321561` | [#103](https://github.com/PolicyEngine/policybench/pull/103) |
| `dashboard-data-20260707` | `3d479beed942` | `2a4d0c7be63e` | [#109](https://github.com/PolicyEngine/policybench/pull/109) |
| `dashboard-data-20260707b` | `d286462dca05` | `a9b8bee0802e` | [#112](https://github.com/PolicyEngine/policybench/pull/112) |
| `dashboard-data-20260707c` | `5db2fdeb7b8e` | `0860f8ebab38` | [#113](https://github.com/PolicyEngine/policybench/pull/113) |
| `dashboard-data-20260708` | `a65c273de6fb` | `d95e19a2f461` | [#115](https://github.com/PolicyEngine/policybench/pull/115) |
| `dashboard-data-20260709b` | `8f3c44cb6e11` | `cdb99bfb3e51` | [#116](https://github.com/PolicyEngine/policybench/pull/116) |
| `dashboard-data-20260710` | `776baef69fc7` | `fd77509de201` | [#120](https://github.com/PolicyEngine/policybench/pull/120) |
| `dashboard-data-20260719` | `1cc4388063a2` | `ca8b2f6e237b` | [#125](https://github.com/PolicyEngine/policybench/pull/125) |
| `dashboard-data-20260721` | `e693f997f788` | `00846e2c5b0d` | [#130](https://github.com/PolicyEngine/policybench/pull/130) |
| `dashboard-data-20260724` | `6773cbda4c4e` | `38453b0225be` | [#132](https://github.com/PolicyEngine/policybench/pull/132) |
| `dashboard-data-20260805` | `4a85a09fe88f` | `5463a5d13281` | [#136](https://github.com/PolicyEngine/policybench/pull/136) |
| `dashboard-data-20260817` | `e00a9fa49d9e` | `a71de04ab9b3` | [#153](https://github.com/PolicyEngine/policybench/pull/153) |
| `dashboard-data-20260822` | `9fa402b67ca3` | `b883ec669d51` | [#156](https://github.com/PolicyEngine/policybench/pull/156) |
| `dashboard-data-20260901c` | `28e41e80a726` | `ee342fc3a756` | [#160](https://github.com/PolicyEngine/policybench/pull/160) |
| `dashboard-data-20260905c` | `7db59dab0014` | `838bb3757db3` | [#164](https://github.com/PolicyEngine/policybench/pull/164) |
| `dashboard-data-20260922` | `56844e2fa795` | `f91ec845cba7` | [#174](https://github.com/PolicyEngine/policybench/pull/174) |
| `dashboard-data-20260922b` | `ba886b4cfa69` | `b1c4ee340a01` | [#177](https://github.com/PolicyEngine/policybench/pull/177) |
| `dashboard-data-20260922c` | `cb312fd775b3` | `01e7e72b3a6b` | [#178](https://github.com/PolicyEngine/policybench/pull/178) |
| `dashboard-data-20260929` | `d616e67c33b6` | `a5cb9989d78c` | [#182](https://github.com/PolicyEngine/policybench/pull/182) |
| `dashboard-data-20260930` | `8b4c0ca146bb` | `d1cae7456cf9` | [#187](https://github.com/PolicyEngine/policybench/pull/187) |
| `dashboard-data-20261006` | `9ce4ade83829` | `aa34e5c9ea92` | [#202](https://github.com/PolicyEngine/policybench/pull/202) |
| `dashboard-data-20261010` | `5a8164a001ef` | `f834478e6519` | [#208](https://github.com/PolicyEngine/policybench/pull/208) |
| `dashboard-data-20261013` | `bc305793c527` | `aef5dc73a764` | [#217](https://github.com/PolicyEngine/policybench/pull/217) |
| `dashboard-data-20261013b` | `2cb77a17739a` | `0a4b754a4ce3` | [#218](https://github.com/PolicyEngine/policybench/pull/218) |
| `dashboard-data-20261014` | `bf845cbe4e92` | `22db9a9c0525` | [#221](https://github.com/PolicyEngine/policybench/pull/221) |
| `dashboard-data-20261027` | `875fe1f6f59f` | `67cb0d14ca93` | [#247](https://github.com/PolicyEngine/policybench/pull/247) |

`dashboard-data-20260705`'s asset was replaced twice after the release first
reached main. Main's pointer named three sha256s under that tag, at
`d623916b`, `bf82497f` and `84dff066`. The board commit is the last of these,
because it names the bytes the release holds now.

Six tags have no board commit, and `seal-release --all` leaves them alone:

- `dashboard-data-20260709`, `-20260901`, `-20260901b`, `-20260905` and
  `-20260905b` never reached main. A later tag replaced each before its PR
  merged.
- `dashboard-data-20260705b` reached main at `6cb7b488`, but GitHub has no
  release under that tag, so its asset does not download.
