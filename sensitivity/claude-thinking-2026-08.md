# Claude thinking sensitivity (August 2026)

The leaderboard's canonical condition sends every model the same household
facts and requested outputs and forces the answer tool call
(`tool_choice: {type: "tool", name: "submit_outputs"}`) for every row on the
tool contract, with no reasoning-control parameters
for any provider. Ten models answer in one- or three-output subsets per
request. Rows whose model card or its family default selects JSON answer as a
JSON object. For most of them the card records that the provider rejects a
forced tool call; the cards of DeepSeek V4 Pro and GLM-5.2 select JSON without
recording a rejection, and the older Gemini rows answer as JSON by the Gemini
family default. The per-model treatment is the manuscript's
serving-configuration table. Claude Fable 5.1, a JSON-transport row, and
Claude Haiku 5.5, a forced-tool row onboarded in October, each have their own
re-run (see their sections below). A
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

All ranks are on the 47-model board (2026-10-09). Scores are on the
1,915 outputs the board scores; the 69 outputs `reference_exclusions.json`
lists (engine defects, references that depend on an input the prompt never
states, and references that rest on an amount a state published after the
freeze) are excluded for every model, sensitivity runs included. On
all 1,984 outputs the thinking runs scored 87.0, 85.8 and 80.3.

| | board exact | thinking exact | delta | would rank | cost/hh | median s/hh | parsed |
|---|---|---|---|---|---|---|---|
| Claude Fable 5 | 85.1 (#21) | **93.2** | +8.0 | **#5** | $0.541 → $0.323 | 54 | 1,984/1,984 |
| Claude Opus 5 | 85.5 (#20) | **91.6** | +6.0 | #10 | $0.067 → $0.152 | 51 | 1,984/1,984 |
| Claude Sonnet 5 | 74.0 (#45) | **86.3** | +12.3 | #20 | $0.086 | 64 | 1,928/1,984 |

In this table and the tables below, deltas are differences of the
unrounded scores, so a delta can differ by 0.1 from the difference of the
rounded scores shown; the per-program tables subtract the rounded rates.
Each would-rank places the unrounded score on the board, so a score that
rounds level with a board row's can rank on either side of it: Claude Opus
5's 91.551 rounds level with Kimi K3's 91.629 and ranks below it.

Under `auto`, Fable 5 and Opus 5 chose to call the answer tool on every
response; Sonnet 5 failed to produce a parseable tool call on 56 of its
1,984 answers; the 55 on scored outputs count as misses inside its 86.3. Fable 5's
sensitivity run also costs less than its leaderboard run: whole-scenario
requests drop its per-household spend from $0.541 to $0.323 even with
thinking on.

## Status

The leaderboard is unchanged: the frozen board holds every model to the
request shape its model card records, and this run sits beside it as a
labeled sensitivity, not in it. Each run's predictions are committed under
`sensitivity/data/` (and attached to the `dashboard-data-20260805` release)
as `sensitivity-claude-{fable,opus,sonnet}-5-thinking-predictions.csv.gz`. The
manuscript's serving-configuration table documents the interaction. The next
board version moves every model to
`tool_choice: "auto"` so each provider's default reasoning posture engages
under the recorded request shapes — expedited, gated on roster-wide
probes confirming reliable tool calling under `auto`, and shipped as a
versioned re-run, never an edit to existing scores; the plan is
[policybench#139](https://github.com/PolicyEngine/policybench/issues/139).

## Where thinking helps (Claude Fable 5, per program)

Per-variable within-$1 rates, board (forced) vs `auto`, on the 1,915
scored outputs. These are unweighted leaf rates from the heatmap; the
headline weights by dollar magnitude, so these do not average to 93.2.

| program | board | auto | delta |
|---|---|---|---|
| federal_income_tax_before_refundable_credits | 61.5 | 83.3 | +21.8 |
| state_income_tax_before_refundable_credits | 65.1 | 78.3 | +13.2 |
| federal_refundable_credits | 87.8 | 96.9 | +9.1 |
| person_medicare_eligible | 91.3 | 99.4 | +8.1 |
| payroll_tax | 86.3 | 93.7 | +7.4 |
| state_refundable_credits | 83.7 | 87.8 | +4.1 |
| snap | 83.9 | 87.1 | +3.2 |
| ssi | 96.9 | 100.0 | +3.1 |
| self_employment_tax | 97.0 | 99.0 | +2.0 |
| person_medicaid_eligible | 94.8 | 96.5 | +1.7 |
| person_wic_eligible | 99.4 | 100.0 | +0.6 |
| local_income_tax | 100.0 | 100.0 | +0.0 |
| person_early_head_start_eligible | 100.0 | 100.0 | +0.0 |
| person_head_start_eligible | 100.0 | 100.0 | +0.0 |
| reduced_price_school_meals_eligible | 99.0 | 99.0 | +0.0 |
| tanf | 99.0 | 99.0 | +0.0 |
| free_school_meals_eligible | 99.0 | 98.0 | -1.0 |
| person_chip_eligible | 98.9 | 97.2 | -1.7 |

Thinking pays off on the hardest arithmetic: the two income-tax lines,
refundable credits, and payroll tax. Near-ceiling programs stay flat;
the two small negatives sit at noise scale for n=100-177. Per-variable
CSVs for all three models are committed under `sensitivity/data/` as
`sensitivity-claude-*-thinking-by-variable.csv.gz`, regenerated on the
scored outputs by `scripts/sensitivity_by_variable.py` and pinned in
`sensitivity/data/claude-thinking-2026-08.json`; the copies attached to the
`dashboard-data-20260805` release predate the exclusion and score all 1,984.

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
reason. The ranks are on the 47-model board (2026-10-09).

| | board exact | auto exact | delta | would rank | cost/hh | median s/hh | parsed |
|---|---|---|---|---|---|---|---|
| Claude Fable 5.1 | 92.4 (#7) | **93.5** | +1.2 | #5 | $0.257 → $0.348 | 49 → 53 | 1,984/1,984 |

The two rows sit 1.2 points apart, and no program moves more than three
points between them (table below). Read against Claude Fable 5, the
picture matches August: Fable 5.1's JSON board row (92.4) is 7.2 points
above Fable 5's forced-tool board row (85.1) and 0.8 below Fable 5's
`auto` run (93.2); Fable 5.1's own `auto` run (93.5) is 0.4 above Fable
5's under the identical request. Scores are on the 1,915 scored outputs;
on all 1,984 the auto run scored 88.2. The model called the answer tool on every
one of its 1,984 answers under `auto`.

Per-variable within-$1 rates for Claude Fable 5.1, board (JSON) vs `auto`
(tool declared); unweighted leaf rates on the scored outputs, as above.

| program | board (JSON) | auto (tool declared) | delta |
|---|---|---|---|
| federal_income_tax_before_refundable_credits | 83.3 | 85.9 | +2.6 |
| state_income_tax_before_refundable_credits | 77.1 | 79.5 | +2.4 |
| person_medicare_eligible | 96.5 | 98.3 | +1.8 |
| free_school_meals_eligible | 98.0 | 99.0 | +1.0 |
| reduced_price_school_meals_eligible | 99.0 | 100.0 | +1.0 |
| ssi | 99.0 | 100.0 | +1.0 |
| person_medicaid_eligible | 97.1 | 97.7 | +0.6 |
| local_income_tax | 100.0 | 100.0 | +0.0 |
| payroll_tax | 92.6 | 92.6 | +0.0 |
| person_early_head_start_eligible | 100.0 | 100.0 | +0.0 |
| person_head_start_eligible | 100.0 | 100.0 | +0.0 |
| person_wic_eligible | 100.0 | 100.0 | +0.0 |
| self_employment_tax | 100.0 | 100.0 | +0.0 |
| snap | 88.2 | 88.2 | +0.0 |
| tanf | 99.0 | 99.0 | +0.0 |
| federal_refundable_credits | 99.0 | 98.0 | -1.0 |
| state_refundable_credits | 91.8 | 90.8 | -1.0 |
| person_chip_eligible | 97.2 | 96.0 | -1.2 |

The run's predictions and per-variable rates are committed under
`sensitivity/data/` as `sensitivity-claude-fable-5-1-thinking-predictions.csv.gz`
and `sensitivity-claude-fable-5-1-thinking-by-variable.csv.gz` (pinned in
`claude-fable-5-1-thinking.json`; the rates are on the scored outputs). The
copies attached to the `dashboard-data-20260901c` release predate the
exclusion.

## Claude Haiku 5.5 (October 2026)

Claude Haiku 5.5, onboarded on October 8, 2026, the day after its release,
reasons by default like the Claude 5 models above: a request with no
thinking parameter returned a thinking block. Unlike Claude Sonnet 5.5 and
Claude Opus 5.5, its API accepts forced tool use, so its board row takes
the board's forced answer tool, and the forced-tool probe returned no
thinking block: the row answers without extended thinking, as Claude Opus
5's does (its model card's notes). Its sensitivity run is the August
condition: the answer tool declared with `tool_choice: "auto"`, over the
whole scenario, as the board row also requests it. The ranks are on the
47-model board (2026-10-09).

| | board exact | auto exact | delta | would rank | cost/hh | median s/hh | parsed |
|---|---|---|---|---|---|---|---|
| Claude Haiku 5.5 | 80.9 (#37) | **90.4** | +9.4 | #11 | $0.0013 → $0.0027 | 5.1 → 17.4 | 1,984/1,984 |

The model called the answer tool on every one of its 1,984 answers under
`auto`. Its median household used 3,743 completion tokens against the board
row's 1,199 and took 17.4 seconds against 5.1, as when thinking engages;
litellm reports no reasoning tokens for Anthropic (above), so the run does
not count them separately. Scores are on the 1,915 scored outputs; on all
1,984 the auto run scored 85.0. Among the Claude rows only Claude Sonnet 5
gains more under `auto`. Most of the gain is in payroll tax and federal
income tax; SNAP, state refundable credits and CHIP eligibility fall by two
to three and a half points.

Per-variable within-$1 rates for Claude Haiku 5.5, board (forced tool) vs
`auto`; unweighted leaf rates on the scored outputs, as above.

| program | board (forced tool) | auto (tool declared) | delta |
|---|---|---|---|
| payroll_tax | 68.4 | 93.7 | +25.3 |
| federal_income_tax_before_refundable_credits | 59.0 | 82.1 | +23.1 |
| person_head_start_eligible | 89.5 | 94.7 | +5.2 |
| federal_refundable_credits | 88.8 | 93.9 | +5.1 |
| self_employment_tax | 96.0 | 100.0 | +4.0 |
| person_medicaid_eligible | 89.6 | 92.5 | +2.9 |
| person_medicare_eligible | 97.1 | 100.0 | +2.9 |
| local_income_tax | 98.0 | 100.0 | +2.0 |
| person_wic_eligible | 97.7 | 98.9 | +1.2 |
| state_income_tax_before_refundable_credits | 67.5 | 68.7 | +1.2 |
| ssi | 97.9 | 99.0 | +1.1 |
| free_school_meals_eligible | 99.0 | 99.0 | +0.0 |
| person_early_head_start_eligible | 100.0 | 100.0 | +0.0 |
| reduced_price_school_meals_eligible | 100.0 | 100.0 | +0.0 |
| tanf | 99.0 | 99.0 | +0.0 |
| snap | 86.0 | 83.9 | -2.1 |
| state_refundable_credits | 82.7 | 80.6 | -2.1 |
| person_chip_eligible | 98.3 | 94.9 | -3.4 |

The run's predictions and per-variable rates are committed under
`sensitivity/data/` as `sensitivity-claude-haiku-5-5-thinking-predictions.csv.gz`
and `sensitivity-claude-haiku-5-5-thinking-by-variable.csv.gz` (pinned in
`claude-haiku-5-5-thinking.json`; the rates are on the scored outputs).

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
