# Claude thinking sensitivity (August 2026)

The leaderboard's canonical condition sends every model the identical
whole-scenario prompt and forces the answer tool call
(`tool_choice: {type: "tool", name: "submit_outputs"}`), with no
reasoning-control parameters for any provider. A reader reviewing the run
artifacts noticed that every Claude row logged zero reasoning tokens while
the other reasoning-by-default providers spent most of their tokens on
reasoning.

Two findings, verified live against the harness's own request builder:

1. **Forcing the tool suppresses Claude's thinking in practice.** The same
   Claude Opus 5 request three ways: forced tool with no thinking parameter
   produced no thinking blocks (611 completion tokens); `tool_choice:
   "auto"` produced thinking blocks (2,370 tokens) and still ended in the
   tool call; forced tool with thinking explicitly set to `adaptive` again
   produced none. Anthropic's documentation permits forced tool use with
   adaptive thinking — the request is valid — but the model answers
   directly. Other providers reason regardless of tool forcing, so under
   the canonical condition the thinking-by-default Claude models (Claude
   Fable 5, Claude Opus 5, Claude Sonnet 5) effectively ran without
   thinking. The Claude 4.x models default to no thinking on any request
   shape, so their rows reflect provider defaults faithfully.
2. **The usage CSVs would have hidden it regardless.** The harness records
   usage through litellm, which does not populate reasoning-token fields
   for Anthropic even when thinking blocks are present.

## Sensitivity runs

All three thinking-by-default Claude models over the full benchmark — all
100 households, identical prompt, identical parse pipeline — with
`tool_choice: "auto"` instead of forced (via the
`POLICYBENCH_TOOL_CHOICE=auto` escape hatch in
`policybench/eval_no_tools.py`). Claude Fable 5 and Claude Sonnet 5 run
chunked (one output per request) on the leaderboard, so their sensitivity
runs also use the canonical whole-scenario request
(`POLICYBENCH_CHUNK_OVERRIDE=none`); their deltas therefore combine two
shape changes, while Claude Opus 5's isolates thinking alone.

| | board exact | thinking exact | delta | would rank | cost/hh | median s/hh | parsed |
|---|---|---|---|---|---|---|---|
| Claude Fable 5 | 79.9 (#8) | **86.9** | +7.0 | **#2** | $0.541 → $0.323 | 54 | 1,984/1,984 |
| Claude Opus 5 | 79.8 (#9) | **85.6** | +5.8 | #3 | $0.067 → $0.152 | 51 | 1,984/1,984 |
| Claude Sonnet 5 | 69.4 (#27) | **80.2** | +10.8 | #8 | $0.086 | 64 | 1,928/1,984 |

Under `auto`, Fable 5 and Opus 5 chose to call the answer tool on every
response; Sonnet 5 failed to produce a parseable tool call on 56 of its
1,984 answers, which score as misses inside its 80.2. Fable 5's
sensitivity run also costs less than its leaderboard run: whole-scenario
requests drop its per-household spend from $0.541 to $0.323 even with
thinking on.

## Status

The leaderboard is unchanged: the frozen board holds every model to the
identical request, and this run sits beside it as a labeled sensitivity,
not in it. Each run's predictions are attached to the
`dashboard-data-20260805` release as
`sensitivity-claude-{fable,opus,sonnet}-5-thinking-predictions.csv.gz`. The manuscript's
serving-configuration table will document the interaction at its next
refreeze. The next board version moves every model to
`tool_choice: "auto"` so each provider's default reasoning posture engages
under a still-identical request shape — expedited, gated on roster-wide
probes confirming reliable tool calling under `auto`, and shipped as a
versioned re-run, never an edit to existing scores; the plan is
[policybench#139](https://github.com/PolicyEngine/policybench/issues/139).

## Reproducing

```
POLICYBENCH_TOOL_CHOICE=auto python -m policybench.cli run \
  --model claude-opus-5 \
  --scenario-manifest paper/snapshot/20260501/us_scenarios.csv \
  --run-dir results/local/opus5_thinking/run \
  --budget-usd 40 --max-workers 6
```

The three-request probe that isolated the mechanism builds the harness's
exact request via `_chat_completion_request_kwargs` and varies only
`tool_choice` and the `thinking` parameter.
