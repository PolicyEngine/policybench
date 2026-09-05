# Claude thinking sensitivity (August 2026)

The leaderboard's canonical condition sends every model the same household
facts and requested outputs and forces the answer tool call
(`tool_choice: {type: "tool", name: "submit_outputs"}`) for every row whose
model card selects the tool contract, with no reasoning-control parameters
for any provider. Ten models answer in one- or three-output subsets per
request, and rows on the JSON contract answer as a JSON object, either
because the provider rejects a forced tool or because the model card selects
JSON for that family (older Gemini and DeepSeek rows); the per-model
treatment is the manuscript's serving-configuration table, and Claude Fable
5.1 is the newest JSON-transport row (see its section below). A
reader reviewing the run artifacts noticed that every Claude row logged zero reasoning tokens while
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

All ranks are on the 39-model board (2026-09-05). Scores are on the
1,973 outputs the board scores; eleven outputs whose reference depends on
an input the data never carried are excluded for every model, sensitivity
runs included (`reference_exclusions.json`). On all 1,984 outputs the
thinking runs scored 86.9, 85.6 and 80.2.

| | board exact | thinking exact | delta | would rank | cost/hh | median s/hh | parsed |
|---|---|---|---|---|---|---|---|
| Claude Fable 5 | 80.4 (#13) | **87.5** | +7.1 | **#3** | $0.541 → $0.323 | 54 | 1,984/1,984 |
| Claude Opus 5 | 80.3 (#14) | **86.2** | +5.9 | #5 | $0.067 → $0.152 | 51 | 1,984/1,984 |
| Claude Sonnet 5 | 69.9 (#37) | **80.8** | +10.9 | #13 | $0.086 | 64 | 1,928/1,984 |

Under `auto`, Fable 5 and Opus 5 chose to call the answer tool on every
response; Sonnet 5 failed to produce a parseable tool call on 56 of its
1,984 answers, which score as misses inside its 80.8. Fable 5's
sensitivity run also costs less than its leaderboard run: whole-scenario
requests drop its per-household spend from $0.541 to $0.323 even with
thinking on.

## Status

The leaderboard is unchanged: the frozen board holds every model to the
request shape its model card records, and this run sits beside it as a
labeled sensitivity, not in it. Each run's predictions are attached to the
`dashboard-data-20260805` release as
`sensitivity-claude-{fable,opus,sonnet}-5-thinking-predictions.csv.gz`. The
manuscript's serving-configuration table documents the interaction. The next
board version moves every model to
`tool_choice: "auto"` so each provider's default reasoning posture engages
under the recorded request shapes — expedited, gated on roster-wide
probes confirming reliable tool calling under `auto`, and shipped as a
versioned re-run, never an edit to existing scores; the plan is
[policybench#139](https://github.com/PolicyEngine/policybench/issues/139).

## Where thinking helps (Claude Fable 5, per program)

Per-variable within-$1 rates, board (forced) vs `auto`. These are
unweighted leaf rates from the heatmap; the headline weights by dollar
magnitude, so these do not average to 87.5.

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

## Claude Fable 5.1 (September 2026)

Claude Fable 5.1, released September 1, 2026, closes the interaction from
the API side. It rejects forced tool use with a 400 (`tool_choice` of type
`tool` or `any`), and Anthropic's documentation gives the reason this page
found in August: thinking is always on for the model, and a forced call
would skip it. The leaderboard therefore cannot send it the forced-tool
request. Its board row runs the JSON contract, the accommodation Kimi K3
and Qwen 3.8 Max already have; under litellm that request carries the
prompt alone (`response_format: json_object` maps to no Anthropic
parameter), so the board row reasons at the API default.

The sensitivity run for this model isolates request shape under thinking
rather than thinking itself: the answer tool declared with `tool_choice:
"auto"` (`POLICYBENCH_CONTRACT_OVERRIDE=tool` together with
`POLICYBENCH_TOOL_CHOICE=auto`), against the JSON board row. Both rows
reason. The ranks are on the 39-model board (2026-09-05).

| | board exact | auto exact | delta | would rank | cost/hh | median s/hh | parsed |
|---|---|---|---|---|---|---|---|
| Claude Fable 5.1 | 86.9 (#3) | **88.2** | +1.2 | #2 | $0.257 → $0.348 | 49 → 53 | 1,984/1,984 |

The two rows sit 1.2 points apart, and no program moves more than three
points between them (table below). Read against Claude Fable 5, the
picture matches August: Fable 5.1's JSON board row (86.9) is 6.5 points
above Fable 5's forced-tool board row (80.4) and 0.6 below Fable 5's
`auto` run (87.5); Fable 5.1's own `auto` run (88.2) is 0.6 above Fable
5's under the identical request. Scores are on the 1,973 scored outputs;
on all 1,984 the auto run scored 87.5. The model called the answer tool on every
one of its 1,984 answers under `auto`.

Per-variable within-$1 rates for Claude Fable 5.1, board (JSON) vs `auto`
(tool declared); unweighted leaf rates, as above.

| program | board (JSON) | auto (tool declared) | delta |
|---|---|---|---|
| federal_income_tax_before_refundable_credits | 69.0 | 72.0 | +3.0 |
| person_medicare_eligible | 93.8 | 95.5 | +1.7 |
| free_school_meals_eligible | 98.0 | 99.0 | +1.0 |
| reduced_price_school_meals_eligible | 98.0 | 99.0 | +1.0 |
| ssi | 96.0 | 97.0 | +1.0 |
| state_income_tax_before_refundable_credits | 63.0 | 64.0 | +1.0 |
| person_medicaid_eligible | 96.6 | 97.2 | +0.6 |
| local_income_tax | 100.0 | 100.0 | +0.0 |
| payroll_tax | 88.0 | 88.0 | +0.0 |
| person_early_head_start_eligible | 100.0 | 100.0 | +0.0 |
| person_head_start_eligible | 100.0 | 100.0 | +0.0 |
| person_wic_eligible | 100.0 | 100.0 | +0.0 |
| self_employment_tax | 100.0 | 100.0 | +0.0 |
| snap | 79.0 | 79.0 | +0.0 |
| tanf | 99.0 | 99.0 | +0.0 |
| federal_refundable_credits | 97.0 | 96.0 | -1.0 |
| state_refundable_credits | 89.0 | 88.0 | -1.0 |
| person_chip_eligible | 97.2 | 96.0 | -1.1 |

The run's predictions and per-variable rates are attached to the
`dashboard-data-20260901c` release as
`sensitivity-claude-fable-5-1-thinking-predictions.csv.gz` and
`sensitivity-claude-fable-5-1-thinking-by-variable.csv.gz`.

## Reproducing

```
POLICYBENCH_TOOL_CHOICE=auto python -m policybench.cli run \
  --model claude-opus-5 \
  --scenario-manifest paper/snapshot/20260501/us_scenarios.csv \
  --run-dir results/local/opus5_thinking/run \
  --budget-usd 40 --max-workers 6
```

For a JSON-contract model such as Claude Fable 5.1, add
`POLICYBENCH_CONTRACT_OVERRIDE=tool` so the answer tool is declared for
`auto` to act on.

The three-request probe that isolated the mechanism builds the harness's
exact request via `_chat_completion_request_kwargs` and varies only
`tool_choice` and the `thinking` parameter.
