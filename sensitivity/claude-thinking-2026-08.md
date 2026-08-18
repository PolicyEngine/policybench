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
`sensitivity-claude-{fable,opus,sonnet}-5-thinking-predictions.csv.gz`. The
manuscript's serving-configuration table documents the interaction. The next
board version moves every model to
`tool_choice: "auto"` so each provider's default reasoning posture engages
under a still-identical request shape — expedited, gated on roster-wide
probes confirming reliable tool calling under `auto`, and shipped as a
versioned re-run, never an edit to existing scores; the plan is
[policybench#139](https://github.com/PolicyEngine/policybench/issues/139).

## Where thinking helps (Claude Fable 5, per program)

Per-variable within-$1 rates, board (forced) vs `auto`. These are
unweighted leaf rates from the heatmap; the headline weights by dollar
magnitude, so these do not average to 86.9.

| program | board | auto | delta |
|---|---|---|---|
| federal_income_tax_before_refundable_credits | 52.0 | 69.0 | +17.0 |
| federal_refundable_credits | 86.0 | 95.0 | +9.0 |
| state_income_tax_before_refundable_credits | 55.0 | 64.0 | +9.0 |
| person_medicare_eligible | 88.7 | 96.6 | +7.9 |
| payroll_tax | 82.0 | 89.0 | +7.0 |
| state_refundable_credits | 80.0 | 84.0 | +4.0 |
| self_employment_tax | 97.0 | 99.0 | +2.0 |
| person_medicaid_eligible | 93.8 | 95.5 | +1.7 |
| snap | 77.0 | 78.0 | +1.0 |
| ssi | 96.0 | 97.0 | +1.0 |
| person_wic_eligible | 99.4 | 100.0 | +0.6 |
| local_income_tax | 100.0 | 100.0 | +0.0 |
| person_early_head_start_eligible | 100.0 | 100.0 | +0.0 |
| person_head_start_eligible | 100.0 | 100.0 | +0.0 |
| tanf | 99.0 | 99.0 | +0.0 |
| free_school_meals_eligible | 99.0 | 98.0 | -1.0 |
| person_chip_eligible | 98.9 | 97.2 | -1.7 |
| reduced_price_school_meals_eligible | 100.0 | 98.0 | -2.0 |

Thinking pays off on the hardest arithmetic: the two income-tax lines,
refundable credits, and payroll tax. Near-ceiling programs stay flat;
the three small negatives sit at noise scale for n=100-177. Per-variable
CSVs for all three models are attached to the `dashboard-data-20260805`
release as `sensitivity-claude-*-thinking-by-variable.csv.gz`.

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
