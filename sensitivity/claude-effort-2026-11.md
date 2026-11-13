# Claude effort sensitivity (November 2026)

PolicyBench sends no reasoning setting to any model, so each board row runs at
its provider's default. [Anthropic's effort
documentation](https://platform.claude.com/docs/en/build-with-claude/effort),
which PolicyBench read on 2026-11-12, gives that default as high for Claude
Fable 5.2 and medium for Claude Opus 5.5; the board rows' "high" and "medium"
below are those documented defaults. PolicyBench ran each of the two models
once more at the other's default, so that the two models can also be compared
at one effort level. This sensitivity changes no board row.

## What PolicyBench ran

Two runs on 2026-11-12, each over the board's 100 households and prompts:

- Claude Opus 5.5 at effort high (its board row runs at medium);
- Claude Fable 5.2 at effort medium (its board row runs at high).

Each run kept its board row's serving card: the answer as a JSON object, a
600-second timeout, a starting output budget of 16,384 tokens that doubles, up
to 128,000, when an answer stops at the budget, and the board's retry rule.
The request differs from the board's by Anthropic's `output_config.effort`
field, which the harness sends for one named model when
`POLICYBENCH_REASONING_EFFORT_OVERRIDE` is set, and by the
`anthropic-beta: effort-2025-11-24` header, which the client library, litellm
1.95.0, adds to each request carrying that field. A matched effort label does
not mean matched tokens or cost; the cost table below gives both for each row.

Before the runs, PolicyBench sent one probe request per model with the effort
field, to check that the API accepts it, on the frozen manifest's first
household and one output. Claude Opus 5.5 at high ran from 22:40:08 to
22:40:14 UTC on 2026-11-12 and cost $0.01; Claude Fable 5.2 at medium ran from
22:40:33 to 22:40:39 UTC and cost $0.03; $0.05 together. The API accepted
both. The probes' answers entered no score. PolicyBench's records show the
effort each run sent, in the run's treatment record; they hold no response
field that reports the effort Anthropic applied, and Anthropic's effort
documentation names none.

The session that operated release dashboard-data-20261111, which runs on
Claude Fable 5.2, wrote the plan and started both runs. A Claude Opus 5.5
agent wrote the option that sends the effort and the scripts, sent the two
probes and ran the scoring. GPT-6.1 Sol, an OpenAI model, read the plan, the
code change and a draft of this note before publication, as a bundle of those
files rather than the repository, and asked for changes. PolicyBench made
these: each run resolves the effort once and uses that one value for its
record and for every request; a request keeps any other `output_config`
members; an empty or malformed setting stops the run; the snapshot freeze and
the board exports refuse to run while the variable is set; the probes and
every other departure from the plan are recorded; and this note no longer
words a difference as an effect of effort. Sol also asked for paired
comparisons of the bounded score; the comparisons stay on the headline
measure, as the plan's record notes.

## The plan's rules

PolicyBench wrote the plan before the first call.
[`claude-effort-2026-11-plan.md`](claude-effort-2026-11-plan.md) gives its
rules word for word and, after them, a record of the runs that lists every
departure from the plan. Its rules:

- one run per arm over all 100 households;
- a household that ends in a provider error or no parsed answer is retried
  only as the board's run rule retries it, and no household is rerun or
  dropped for its result;
- a spend cap of $45 of API credit across both arms, each arm starting with
  $22.50;
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
difference of the rounded scores above. The four comparisons are on this
headline measure; the bounded score above is one figure per row, with no
interval.

| comparison | households | difference | 95% interval | first higher, second higher, tied |
|---|---|---|---|---|
| 1. Claude Fable 5.2, medium minus high (board row) | 100 | +1.6 | +0.3 to +3.1 | 14, 9, 77 |
| 2. Claude Opus 5.5, high minus medium (board row) | 100 | +0.2 | -0.9 to +1.3 | 8, 7, 85 |
| 3. At medium: Claude Fable 5.2 minus Claude Opus 5.5 (board row) | 100 | -0.5 | -1.5 to +0.5 | 10, 15, 75 |
| 4. At high: Claude Fable 5.2 (board row) minus Claude Opus 5.5 | 100 | -2.3 | -3.9 to -0.8 | 8, 21, 71 |

At medium, Claude Fable 5.2 scores 0.5 points below Claude Opus 5.5. At high,
Claude Fable 5.2 scores 2.3 points below Claude Opus 5.5. Claude Fable 5.2 at
medium scores 1.6 points above its board row at high; Claude Opus 5.5 at high
scores 0.2 points above its board row at medium. The 95% interval lies above
zero for comparison 1, includes zero for comparisons 2 and 3, and lies below
zero for comparison 4. The intervals resample households, not runs; see
Limits.

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
at medium), $21.77 together, and the probes $0.05: $21.82 against the $45 cap.
Neither run reached its $22.50 cap.

## Limits

- Each arm is one run. The intervals resample households; they do not measure
  how far a second run of the same arm would move.
- The comparisons rest on 100 households.
- The scored set and the references are release dashboard-data-20261111's.
- The runs behind each comparison were made on different dates: the Claude
  Opus 5.5 board row on 2026-09-22, the Claude Fable 5.2 board row on
  2026-11-09, and both effort runs on 2026-11-12.
- The board rows' effort labels are Anthropic's documented defaults, read on
  2026-11-12: the board rows sent no effort, and no record shows the default
  in force when Claude Opus 5.5's board row ran.
- Claude Opus 5.5's board row ran when the repository's lockfile pinned
  litellm 1.88.1, and Claude Fable 5.2's when it pinned 1.95.0; both effort
  runs used litellm 1.95.0. The plan's record lists the runs' other
  differences in code and environment.

## Status

The board is unchanged: every row keeps its provider-default request, and
these runs sit beside it as a labeled sensitivity.

Both runs used the option as committed in `921a7886`: each run's launch log
records a hash of the harness code equal to that commit's. After the runs,
PolicyBench tightened the option's guards, in the commits after `921a7886`;
the plan's record lists the changes. The data under `sensitivity/data/` are
from the runs made before that change, and nothing was rerun. Under each run's
settings (an empty cache, `LITELLM_DROP_PARAMS` unset, a valid value), the
tightened option sends the same requests: PolicyBench checked offline, for all
100 households of both runs, that each first request's HTTP body and headers
are unchanged and that the repair, doubled-budget and explanation requests
differ only by a cache namespace litellm does not send.

The runs' predictions and per-program rates are committed under
`sensitivity/data/` as
`sensitivity-claude-opus-5-5-effort-high-predictions.csv.gz`,
`sensitivity-claude-opus-5-5-effort-high-by-variable.csv.gz`,
`sensitivity-claude-fable-5-2-effort-medium-predictions.csv.gz` and
`sensitivity-claude-fable-5-2-effort-medium-by-variable.csv.gz`, pinned in
`sensitivity/data/claude-effort-2026-11.json`.
`tests/test_effort_sensitivity_evidence.py` recomputes this page's scores,
intervals, costs, output tokens, latencies and run dates from those files and
the frozen snapshot. The request counts, the probes' figures and the litellm
versions come from the summary's `run_records`, `board_run_records`, `probes`
and `client_library` blocks, which PolicyBench wrote from each run's spend
ledger, the probe records and the repository's lockfile history; the
repository holds neither the ledgers nor the probe records. The test checks
the request counts against the answered-call counts in the predictions
wherever those exist; Claude Opus 5.5's board row records none.

## Reproducing

```
POLICYBENCH_CACHE_DIR=results/local/claude-effort/opus55-high/cache \
POLICYBENCH_REASONING_EFFORT_OVERRIDE=claude-opus-5-5=high \
  python -m policybench.cli run --model claude-opus-5.5 \
  --scenario-manifest paper/snapshot/20260501/us_scenarios.csv \
  --run-dir results/local/claude-effort/opus55-high/run \
  --budget-usd 22.5 --max-workers 5
POLICYBENCH_CACHE_DIR=results/local/claude-effort/fable52-medium/cache \
POLICYBENCH_REASONING_EFFORT_OVERRIDE=claude-fable-5-2=medium \
  python -m policybench.cli run --model claude-fable-5.2 \
  --scenario-manifest paper/snapshot/20260501/us_scenarios.csv \
  --run-dir results/local/claude-effort/fable52-medium/run \
  --budget-usd 22.5 --max-workers 5
python scripts/effort_sensitivity.py --run-root results/local/claude-effort \
  --board-run claude-fable-5.2=FABLE_BOARD_RUN_DIR \
  --board-run claude-opus-5.5=OPUS_BOARD_RUN_DIR
```

Each run starts with an empty cache directory of its own, as the effort runs
did. `--board-run` names the run folder each board row was frozen from; the
script checks its predictions against the hash the snapshot's serving config
records and reads only its spend ledgers. The script also takes `--probe` for
each probe record; the probe records are not published, and no score uses
them.