# Claude effort sensitivity (November 2026)

PolicyBench sends no reasoning setting to any model, so each board row runs at
its provider's default. Anthropic's default effort is high for Claude Fable
5.2 and medium for Claude Opus 5.5. PolicyBench ran each of the two models
once more at the other's default, so that the two models can also be compared
at one effort level. This sensitivity changes no board row.

## What PolicyBench ran

Two runs on 2026-11-12, each over the board's 100 households and prompts:

- Claude Opus 5.5 at effort high (its board row runs at medium);
- Claude Fable 5.2 at effort medium (its board row runs at high).

Each run kept its board row's serving card: the answer as a JSON object, a
600-second timeout, a starting output budget of 16,384 tokens that doubles, up
to 128,000, when an answer stops at the budget, and the board's retry rule.
The one change is Anthropic's `output_config.effort` field on each request,
which the harness sends for one named model when
`POLICYBENCH_REASONING_EFFORT_OVERRIDE` is set. The client library, litellm,
also adds Anthropic's effort beta header to those requests. Before the runs,
PolicyBench sent one request per model with the effort field, and the API
accepted both. Anthropic's response does not report the effort it applied.

## The plan's rules

PolicyBench fixed the plan before the first call and changed nothing after it:

- one run per arm over all 100 households;
- a household that ends in a provider error or no parsed answer is retried
  only as the board's run rule retries it, and no household is rerun or
  dropped for its result;
- at most $45 of API spend across both runs and the probes, with $22.50 per
  run to start;
- the four comparisons below, all reported whatever they show, each paired by
  household: PolicyBench resamples the households 10,000 times with seed 42
  and takes the 2.5th and 97.5th percentiles of the resampled mean difference
  as the 95% interval;
- scores on release dashboard-data-20261111's references and scored set.

## Results

Scores are on the 1,934 outputs the board scores; the outputs
`reference_exclusions.json` lists are excluded for every row, as on the board.
"Answers right" is the board's headline: PolicyBench counts a dollar amount as
right when it falls within $1 of the reference PolicyEngine computes, and an
eligibility answer as right when it matches, and weights each answer by
household impact. The bounded score gives partial credit for amounts close to
the reference. Both runs completed all 100 households.

| | effort | answers right | within 1% | bounded score | parsed |
|---|---|---|---|---|---|
| Claude Fable 5.2 (board row) | high | 92.0 | 93.7 | 97.8 | 1,934/1,934 |
| Claude Fable 5.2 | medium | 93.6 | 95.2 | 98.0 | 1,934/1,934 |
| Claude Opus 5.5 (board row) | medium | 94.1 | 95.5 | 97.9 | 1,934/1,934 |
| Claude Opus 5.5 | high | 94.2 | 95.0 | 98.1 | 1,934/1,934 |

Each difference below is first minus second, in points of answers right, from
the unrounded per-household scores, so a difference can differ by 0.1 from the
difference of the rounded scores above.

| comparison | households | difference | 95% interval | first higher, second higher, tied |
|---|---|---|---|---|
| 1. Claude Fable 5.2, medium minus high (board row) | 100 | +1.6 | +0.3 to +3.1 | 14, 9, 77 |
| 2. Claude Opus 5.5, high minus medium (board row) | 100 | +0.2 | -0.9 to +1.3 | 8, 7, 85 |
| 3. At medium: Claude Fable 5.2 minus Claude Opus 5.5 (board row) | 100 | -0.5 | -1.5 to +0.5 | 10, 15, 75 |
| 4. At high: Claude Fable 5.2 (board row) minus Claude Opus 5.5 | 100 | -2.3 | -3.9 to -0.8 | 8, 21, 71 |

At medium, Claude Fable 5.2 scores 0.5 points below Claude Opus 5.5. At high,
Claude Fable 5.2 scores 2.3 points below Claude Opus 5.5. Claude Fable 5.2
gains 1.6 points from high to medium; Claude Opus 5.5 gains 0.2 points from
medium to high. The 95% interval lies above zero for comparison 1, includes
zero for comparisons 2 and 3, and lies below zero for comparison 4.

## Cost and calls

Cost is priced as the board prices it, from each call's recorded cost.
Requests count every provider request in the run's spend ledger, failed
attempts included; a second request is the harness's retry within a household
under the board's run rule.

| | effort | cost | per household | output tokens | median seconds per household | requests | households with a second request | outputs not parsed |
|---|---|---|---|---|---|---|---|---|
| Claude Fable 5.2 (board row) | high | $31.69 | $0.317 | 747,522 | 47.7 | 106 | 6 | 0 |
| Claude Fable 5.2 | medium | $13.25 | $0.133 | 289,612 | 23.7 | 100 | 0 | 0 |
| Claude Opus 5.5 (board row) | medium | $6.75 | $0.067 | 295,728 | 24.0 | 100 | 0 | 0 |
| Claude Opus 5.5 | high | $8.52 | $0.085 | 383,834 | 28.8 | 102 | 2 | 0 |

Claude Fable 5.2's board row made a second request for 6 households, each
after an answer stopped at the 16,384-token budget, with the budget doubled.
Claude Opus 5.5 at high made a second request for 2 households: 1 after a
provider error, and 1 after an answer stopped at the 16,384-token budget, with
the budget doubled. Claude Fable 5.2 at medium and Claude Opus 5.5's board row
needed one request for every household.

The two runs cost $8.52 (Claude Opus 5.5 at high) and $13.25 (Claude Fable 5.2
at medium), $21.77 together. Neither run reached its $22.50 cap.

## Limits

- Each arm is one run. The intervals resample households; they do not measure
  how far a second run of the same arm would move.
- The comparisons rest on 100 households.
- The scored set and the references are release dashboard-data-20261111's.
- The runs behind each comparison were made on different dates: the Claude
  Opus 5.5 board row on 2026-09-22, the Claude Fable 5.2 board row on
  2026-11-09, and both effort runs on 2026-11-12.

## Status

The board is unchanged: every row keeps its provider-default request, and
these runs sit beside it as a labeled sensitivity. The runs' predictions and
per-program rates are committed under `sensitivity/data/` as
`sensitivity-claude-opus-5-5-effort-high-predictions.csv.gz`,
`sensitivity-claude-opus-5-5-effort-high-by-variable.csv.gz`,
`sensitivity-claude-fable-5-2-effort-medium-predictions.csv.gz` and
`sensitivity-claude-fable-5-2-effort-medium-by-variable.csv.gz`, pinned in
`sensitivity/data/claude-effort-2026-11.json`.
`tests/test_effort_sensitivity_evidence.py` recomputes every figure on this
page from those files and the frozen snapshot. The request counts come from
each run's spend ledger, which the summary records; the test checks them
against the answered-call counts in the predictions, which the Claude Opus 5.5
board row's predictions do not record.

## Reproducing

```
POLICYBENCH_REASONING_EFFORT_OVERRIDE=claude-opus-5-5=high \
  python -m policybench.cli run --model claude-opus-5.5 \
  --scenario-manifest paper/snapshot/20260501/us_scenarios.csv \
  --run-dir results/local/claude-effort/opus55-high/run \
  --budget-usd 22.5 --max-workers 5
POLICYBENCH_REASONING_EFFORT_OVERRIDE=claude-fable-5-2=medium \
  python -m policybench.cli run --model claude-fable-5.2 \
  --scenario-manifest paper/snapshot/20260501/us_scenarios.csv \
  --run-dir results/local/claude-effort/fable52-medium/run \
  --budget-usd 22.5 --max-workers 5
python scripts/effort_sensitivity.py --run-root results/local/claude-effort \
  --board-run claude-fable-5.2=FABLE_BOARD_RUN_DIR \
  --board-run claude-opus-5.5=OPUS_BOARD_RUN_DIR
```

`--board-run` names the run folder each board row was frozen from; the script
checks its predictions against the hash the snapshot's serving config records
and reads only its spend ledgers.