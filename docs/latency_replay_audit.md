# Latency replay audit (frozen US run, October 2026)

This audit explains every household in the frozen US run whose recorded latency
sums to about zero, and every model whose latency is missing. It then says how
the published figures treat them. The run is
`paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace`
as of release dashboard-data-20261014, with 50 models and 100 households each.
The household-level evidence is `latency_replay_audit/households.csv`, written by
`scripts/audit_latency_replays.py`.

## How latency is recorded

The harness times each provider call. A household that needs several calls
(one or three outputs per request, a repair after an incomplete answer, or a
re-request with a larger completion budget) makes them one after another, as
`run_single_no_tools` does for chunks. Their times are summed, and the sum is
divided equally among the household's rows (`elapsed_seconds / batch_size`
in `policybench/eval_no_tools.py`; all three lines date from 2026-05-01, before
every board run). A household's latency is therefore the sum over its rows. The
timer wraps the provider call, so whatever happens inside that call counts.
When the harness itself retries a failed request, it restarts the timer and
keeps only the attempt that succeeded; the failed attempts and the backoff
between them are not counted (the retry loop in `_request_predictions_once`, the
same in the July code).
`analysis.household_latency_seconds` computes that sum.
`analysis.model_cost_latency` publishes the median across households as
`latencySeconds`. A household whose rows carry no time is left out of the
median rather than counted as zero.

The harness also caches provider responses on disk (`policybench/cache.py`,
litellm's disk cache namespaced by the prompt contract version). A request
identical to an earlier one is answered from the cache. The timer measures the
lookup, a few hundredths of a second, and the row records it as if it were the
call.

## Two models have no latency in the board rows

**GPT-5.5** ran through OpenAI's batch API. All 716 of its board response ids
come from one batch (`batch_6a49d188…`, submitted 2026-07-05 03:37 UTC and
completed 11 minutes later; `results/local/gpt55_default_run_20260706`). Batch
rows leave `elapsed_seconds` and both request timestamps empty by design,
because a batch round trip includes queue time (`policybench/batch_eval.py`).
Its cost is reconstructed from token counts at standard synchronous rates.

**Claude Fable 5** ran synchronously from 2026-07-01 22:26 to 2026-07-02 01:53
UTC. The batch adapter (`batch_eval.py`, #88) first landed at 10:03 UTC on
2026-07-02, and the original rows record a per-call request time, which batch
rows never carry. Those rows, with raw responses, tokens, costs and timings,
are the `claude-fable-5-predictions.csv.gz` asset of release
dashboard-data-20260701. The board rows were rebuilt from that release on
2026-07-02 (57d26f1c) without the usage, timing and raw-response columns. Their
predictions and explanations equal the original rows'. The published
`costUsd` ($54.11), `totalTokens` (3,850,174) and `latencySeconds` (97.68 s)
come from the original rows exactly. The release drivers carry them forward as
`CARRIED_USAGE`, and 6cb7b488 restored them after a rebuild had zeroed them.
Three of the original households (scenario_044, scenario_114 and scenario_115)
sum to under a second. No cache or ledger from that run survives to show
whether they were replays. Without them the median is 97.71 s.

The snapshot manifest, the release drivers' comments and the paper used to say
that Fable 5 was "served through the Anthropic batch adapter" or that its usage
was "recorded at the run level". Neither was true, and both are corrected.

## Replayed households

A household counts as replayed when its first recorded response existed
before the household's request began. The evidence is any of the following:

- **Disk cache.** The response's id sits in a litellm cache entry stored more
  than a minute before the request (`.policybench_cache` in the main checkout,
  121,648 entries).
- **OpenRouter id.** OpenRouter ids are `gen-<unix seconds>-…`, and the time
  is more than a minute before the request. On all 962 live households that
  carry one, it falls within 23 seconds of `request_started_at`, and within 10
  seconds on 99% of them.
- **OpenAI id.** An OpenAI Responses id embeds its creation time in hex, after
  litellm's base64 wrapper is removed. On all 694 live households that carry
  one, it falls within 4 seconds.
- **Spend ledger.** The board run's spend ledger records `cache_hit: true` for
  the call.
- **Smoke.** The same response id was served live in the model's onboarding
  smoke.

A full replay sums to under a second: every call in the household came from
the cache. Every full replay in the run sums to under 0.12 s, while the fastest
live household takes 1.75 s (Gemini 3.5 Flash-Lite), so the one-second line
(`analysis.REPLAYED_HOUSEHOLD_SECONDS`) separates them cleanly. A partial replay
sums to a second or more. Its first recorded call was a replay, and a later
call (another chunk, a repair, or a re-request with a larger completion budget)
went to the provider. Its time leaves out the replayed call's original
duration. In GLM-5.3's scenario_007, for example, the ledger shows the replayed
16,384-token call, then live calls at 32,768 and 65,536 tokens.

| Model | Full | Partial | Where the replayed responses came from | Published median (s) | Without sub-second households (s) |
|---|---|---|---|---|---|
| Qwen3.7-max | 93 | 1 | earlier passes of its run | 0.009 | 917.9 (7 households) |
| GLM-5.2 | 80 | 1 | its JSON-contract smoke (scenario_000 and scenario_001); earlier passes of its run | 0.007 | 384.8 (20 households) |
| Kimi K2.6 | 75 | 4 | its JSON-contract smoke (scenario_000 and scenario_001); earlier passes of its run | 0.033 | 1,194.2 (25 households) |
| MiniMax M3 | 53 | 1 | earlier passes of its run | 0.003 | 10.7 (47 households) |
| Claude Sonnet 5 | 9 | 2 | its smoke (scenario_000); two restarted chunks (8 full, 2 partial) | 63.9 | 64.8 |
| Muse Spark 1.3 | 4 | 0 | its onboarding smoke | 40.6 | 41.1 |
| Claude Haiku 5.5 | 2 | 0 | its onboarding smoke | 5.1 | 5.1 |
| Claude Opus 5.5 | 2 | 0 | its onboarding smoke | 24.0 | 24.0 |
| Muse Wonder | 2 | 0 | its onboarding smoke | 26.1 | 26.5 |
| DeepSeek V4 Pro | 2 | 0 | requests about an hour before its run; no file survives | 169.9 | 172.4 |
| GPT-5.6 Luna | 2 | 0 | requests 5 minutes before its run; no file survives | 14.4 | 14.5 |
| GPT-5.6 Sol | 2 | 0 | requests 7 minutes before its run; no file survives | 36.3 | 36.4 |
| GPT-5.6 Terra | 2 | 0 | requests 6 to 7 minutes before its run; no file survives | 18.9 | 19.1 |
| GLM-5.3 | 0 | 18 | earlier rounds of its supervised run | 134.2 | 134.2 |
| GLM-5.3-Flash (preview) | 0 | 4 | earlier rounds of its supervised run | 241.7 | 241.7 |
| Kimi K3 | 0 | 2 | earlier in its run | 1,023.3 | 1,023.3 |

That is 328 full and 33 partial replays across 16 models. Two more households
sum to under a second with no surviving evidence either way: Grok 4.3's
scenario_000 (0.022 s) and Claude Haiku 4.5's scenario_009 (0.026 s). Both
were already that way in the June 13-model board. Those runs predate per-call
timestamps and spend ledgers, and their cache does not survive. Without them
the two medians move from 22.13 to 22.21 s and from 47.67 to 47.69 s.

The 0.05-second line used before this audit missed four replays: Kimi K2.6's
scenario_008, scenario_026 and scenario_064 (0.056 to 0.068 s) and Claude Haiku
5.5's scenario_001 (0.118 s). The board ledger records `cache_hit: true` for
the last one.

### The four open-weight models: a multi-pass run

Kimi K2.6, GLM-5.2, MiniMax M3 and Qwen3.7-max were added on 2026-07-05 to 07.
The run notes (`results/local/openweight_run_20260705.md`) record that
concurrent long-lived requests exhausted the OpenRouter key's connections, so
whole households errored and wrote no rows. `results/local/rerun_openweight.sh`
and `results/local/grind_model.sh` then re-ran each model's full range several
times. Each pass deletes the part files and re-requests every household, and the
cache answered the households earlier passes had completed. The board rows are
each model's final pass. The notes record MiniMax M3's first pass at 53 of 100
households, and 53 of its households are full replays. They record Qwen3.7-max
at 93/100 in the round before its last, and 93 of its households are full
replays. Kimi K2.6's
scenario_109 shows a partial replay at work. In earlier rounds its first call
succeeded and was cached, and the household then failed on an explanation
repair that timed out at 300 s (`part_84_100.grind*.log`). In the final pass
its first call was replayed and its later calls reached the provider, so the
household records 777 s next to the replayed first call's id.

For these four models the households left after removing replays are the ones
earlier passes failed on, many of them after timeouts and retries. Their
medians (10.7 to 1,194 s) are not estimates of the model's latency. For
OpenRouter responses, the cache's store time minus the id's creation time
approximates a call's duration. It agrees with the recorded time to a median of
0.5 s on live households. It times only the first call, though, the one whose
id the rows keep, so it falls far short wherever a household made several
calls. Applied to the replays it gives medians
of about 133 s (Qwen3.7-max), 117 s (GLM-5.2), 294 s (Kimi K2.6) and 10 s
(MiniMax M3). Qwen3.7-max, GLM-5.2 and Kimi K2.6 were served three outputs
per request, so their households make several calls and the first one is only
part of each household's time. It is a different quantity, and nothing
publishes it.

## What the published figures do with them

- **`modelStats.latencySeconds` in the dashboard data** (release asset
  `dashboard-data.json`, the same values as the frozen `data.json.gz`) is the
  median of household sums with replays counted as calls. Every value
  reproduces from the frozen predictions except Fable 5's, which is carried
  from its original rows. For the four open-weight models it publishes 0.003 to
  0.033 seconds, which is cache-lookup time and not latency. For the eleven
  other models with sub-second households it publishes medians lowered by up
  to 2.5 s (DeepSeek V4 Pro). Partial replays lower medians further, by an
  unknown amount.
  GPT-5.5 has no `latencySeconds`.
- **The leaderboard** shows no latency: the column was dropped on 2026-07-05
  (#100), and `latencySeconds` is not rendered anywhere in the app.
- **The paper's cost-and-latency table** treats a sub-second or missing
  median as unmeasured and falls back to `modelStats`. The four open-weight
  models and GPT-5.5 therefore show a dash, and Fable 5 shows its carried
  98 s. The paragraph under the table used to attribute the dashes to "batch or
  asynchronous dispatch whose logged times reflect submission rather than
  generation". That fits no model in the board: GPT-5.5's batch rows log no
  time at all, and the four sub-second models ran synchronously. The paragraph
  and caption now give the real causes, computed from the frozen data
  (`PaperResults.latency_dash_models` and its neighbours). The table values
  are unchanged. Without sub-second households, Claude Sonnet 5 would read 65 s
  rather than 64 s, DeepSeek V4 Pro 172 s rather than 170 s and GPT-5.6 Luna
  15 s rather than 14 s.
- **`costUsd`.** A replayed row's cost is computed when the row is written,
  from the replayed response itself (`_extract_usage_metadata`). Where a token
  reconstruction exists, its token counts are priced at the list prices
  configured then; otherwise it is the provider's charge embedded in the
  response. Spend ledgers record each cache hit's spend as $0 and that computed
  cost as `cached_response_cost_usd`, and on all ten ledger-era full replays
  (Muse Spark 1.3, Muse Wonder, Claude Opus 5.5 and Claude Haiku 5.5) the board
  household's cost equals it. That shows the row carries the computed value,
  not that it matches what the original call was billed. For OpenRouter models
  priced by the provider's charge, the cached response carries the original
  charge: on 43 of MiniMax M3's full replays the row cost equals the cost
  embedded in the cached response. A household's published cost
  therefore counts each of its responses once, whether or not the board run
  paid for it, and leaves out spend on attempts that did not make the board,
  such as the open-weight models' failed passes. That matches the paper's
  description ("each call's recorded total"), so no cost figure misleads
  because of replays. Fable 5's `costUsd` is computed from its original rows,
  so its NaN board rows do not reach it. `model_cost_latency` itself returns
  $0 for a model whose rows carry no tokens when a price override exists, as
  Fable 5's do. The release drivers overwrite that with the carried value, so
  nothing published shows it.
- **GLM-5.3-Flash (preview)** (artifact key `ox-alpha`) records a
  provider-reported charge of $0.00 on all 1,984 rows. The leaderboard prints
  $0.000 per household and the paper prints a dash, which the caption now
  explains. This is unrelated to replays.

## Changing the published numbers

Changing `latencySeconds` changes published numbers, so it is a methodology
choice for Max, queued as a decision. This audit changes only disclosures,
comments, and the tests that tie them to the data. The options:

- **A. Keep the numbers.** This PR discloses them. The dashboard data keeps
  0.003 to 0.033 s for the four open-weight models.
- **B. Leave replays out of the median (recommended).** `model_cost_latency`
  would take the median over households that sum to a second or more. It would
  publish no latency when more than half a model's households are replays.
  Away from an exact tie, that is the rule the paper's dash already applies
  (`test_a_median_under_a_second_means_most_households_replayed`); at exactly
  half, the paper's median can fall on either side of a second. The four
  open-weight models would lose `latencySeconds`. Eleven other medians would
  rise by 0.02 to 2.5 s. In the paper table, Claude Sonnet 5 would read 65 s
  instead of 64 s, DeepSeek V4 Pro 172 s instead of 170 s and GPT-5.6 Luna 15 s
  instead of 14 s, and nothing else would change after rounding. Partial
  replays would stay as disclosed lower bounds, because finding them needs
  response-id times or the caches, not just household times.
- **C. Reconstruct the replayed calls' durations** from cache store time minus
  OpenRouter creation time. That gives about 133, 117, 294 and 10 s for the four
  models, but it times only the call that succeeded, not the retries the
  harness timer includes.
- **D. Re-time the four models.** Re-send their replayed households live with
  the cache off, for latency only, leaving their predictions alone. The full
  replays' recorded cost suggests about $47 (Kimi K2.6 $28.38, Qwen3.7-max
  $11.99, GLM-5.2 $6.23, MiniMax M3 $0.36). The timings would come
  from a later date than the board's answers.

## Reproducing

```bash
uv run python scripts/audit_latency_replays.py \
  --cache-dir .policybench_cache \
  --ledger-root results/local \
  --ledger-root ~/reviews
```

The cache, ledgers and smoke files exist only on the machine that ran the
board. The id-time evidence and every sub-second household can be recomputed
from the frozen predictions alone, and `tests/test_latency_replay_audit.py`
does so.
