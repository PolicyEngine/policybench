# Claude effort sensitivity: the plan (November 2026)

PolicyBench wrote this plan before the first call of the sensitivity in
[`claude-effort-2026-11.md`](claude-effort-2026-11.md). The sections below are
the plan's text, copied word for word from its file; the file's opening
paragraph, an internal record of the decision to run the sensitivity, is left
out. The record after the plan was written after the runs.

## Why

PolicyBench sends no reasoning setting, so each row runs at its provider's default. Claude Fable 5.2's default effort is high and Claude Opus 5.5's is medium. The sensitivity shows what each model scores at the other's default. It changes no board row.

## Arms

- A: Claude Opus 5.5 with effort high.
- B: Claude Fable 5.2 with effort medium.

Everything else is each model's board row as served: the board's 100 households and prompts from the frozen snapshot, the row's serving card (answer as a JSON object, timeout, starting output budget and its doubling rule, ceiling), and no other parameter. The effort value is the only difference from the board condition.

## Run rules

- One run per arm, 100 households each.
- A household that ends in a provider error or no parsed answer is retried only as the board's own run rule retries it. Nothing is rerun because of its result. No household is dropped for its result.
- Spend cap: $45 of API credit across both arms. Each arm starts with $22.50. If one arm ends under its share and the other stopped at its cap, the stopped arm resumes with what is left of the $45. If the cap still stops an arm, the note reports how many households each arm completed and makes every comparison on the households both sides of that comparison completed.
- Calls go through `claude-credits exec` (expiring API credit).

## Scoring

The board's own functions on release dashboard-data-20261111's references and scored set (1,934 scored outputs): the headline share of answers right (an amount within $1, a yes-or-no output exactly, weighted as the board weights) and the bounded score.

## Comparisons reported (all of them, whatever they show)

Paired by household, with the bootstrap method and seed of `prelim/compare_fable52.py`:

1. Claude Fable 5.2 at medium against its board row (high).
2. Claude Opus 5.5 at high against its board row (medium).
3. At medium: Claude Fable 5.2 (arm B) against Claude Opus 5.5 (board row).
4. At high: Claude Fable 5.2 (board row) against Claude Opus 5.5 (arm A).

Also per arm: cost, output tokens, median latency, second calls, parse failures.

## Publication

A sensitivity note in `sensitivity/` with its data under `sensitivity/data/`, in the form of `sensitivity/claude-thinking-2026-08.md`, linked from the release note. It states the plan, the four comparisons with intervals, and the limits (one run per arm; 100 households; the scored set and references are the release's).

## Review

GPT-6.1 Sol, another lab's model, reads this plan, the code change that sends the effort value, and the note before publication. Its verdict is recorded beside the note's record.

## Record after the runs (2026-11-13)

PolicyBench wrote this record on 2026-11-13, after both runs and their
scoring. Times are UTC.

**Order of events.** The plan's file was created on 2026-11-12 at 22:24:20 and
last changed at 22:24:31, by the file system's record; it then held 3,475
bytes with sha256
`fe00158d7616d8b32b2fd34f62cd67cb0278b78e5f139d009481b52d848dd7e6` (the
private file, whose opening paragraph the published copy leaves out).
PolicyBench sent the two probes from 22:40:08 to 22:40:14 (Claude Opus 5.5 at
high) and from 22:40:33 to 22:40:39 (Claude Fable 5.2 at medium). Both runs
were launched at 22:44:37. Their state files record a start at 22:44:51 and a
last update at 22:59:54 (Claude Opus 5.5 at high) and 22:56:31 (Claude Fable
5.2 at medium). The scoring had finished by 23:03. Every repository commit of
this sensitivity comes after the runs: the option, the scripts, the data and
the note were first committed in `921a7886`, at 23:11:13. The order above
therefore rests on PolicyBench's own files and logs (the plan file's times,
the probe records, the runs' state files and launch logs, and the work log),
not on the repository's history. Each run's launch log records a hash of the
harness code (`policybench/*.py`) at its start and at its exit; both equal the
hash of that code in `921a7886`.

**Departures from the plan.**

1. Probes. The plan names none. To check that the API accepts the effort
   field, PolicyBench sent one request per model before the runs: the frozen
   manifest's first household, one output (`snap`), the request the harness
   builds, no cache. Priced as the board prices calls, they cost $0.01 (Claude
   Opus 5.5) and $0.03 (Claude Fable 5.2), $0.05 together. Their answers
   entered no score.
2. Spend cap. The plan caps spend at "$45 of API credit across both arms".
   PolicyBench counted the probes against it too. The runs spent $8.52 (Claude
   Opus 5.5 at high) and $13.25 (Claude Fable 5.2 at medium), $21.82 with the
   probes. Neither run used up its $22.50, so neither resumed. Each
   `claude-credits exec` launch (two probes, two runs) also made that tool's
   own one-token check request, which PolicyBench's records do not hold.
3. The request. The plan says "The effort value is the only difference from
   the board condition." litellm 1.95.0 also adds the
   `anthropic-beta: effort-2025-11-24` header to each request that carries
   `output_config.effort` for these models. The board's requests carry
   neither.
4. Code and environment. The runs ran the repository at `5f4b0a3f` with the
   option added, uncommitted, and committed unchanged in `921a7886`, on
   litellm 1.95.0. They set `LITELLM_LOCAL_MODEL_COST_MAP=True` and ran under
   an import guard that keeps the harness from loading modules from another
   copy of the repository; the board runs did neither. Like Claude Fable 5.2's
   board run, they called the API through `claude-credits exec`, as the plan
   says; Claude Opus 5.5's board run was not launched through it. Claude Fable
   5.2's board row ran on 2026-11-09 when the repository's lockfile pinned
   litellm 1.95.0, and Claude Opus 5.5's on 2026-09-22 when it pinned litellm
   1.88.1.
5. Request counts. The plan asks, per arm, for "second calls, parse failures".
   The note gives, for all four rows, each run's requests and the households
   with a second request, from its spend ledger and with failed requests
   included; the board rows' come from the run folders they were frozen from.
   The summary data record these counts. The repository does not hold the
   ledgers.
6. Measures compared. The plan's scoring names the headline and the bounded
   score. The four paired comparisons, with their intervals, are on the
   headline only; the bounded score is one figure per row, with no interval.
   The note also gives each row's share within 1%, as a descriptive figure.
7. The note's form. The plan asks for the form of
   `sensitivity/claude-thinking-2026-08.md`. The note leaves out that note's
   would-rank column, a choice made before the scoring, and its per-program
   tables, a choice made after it; both omissions apply to both runs. The
   per-program rates are committed as data files.
8. Guards tightened after the runs. After the runs, PolicyBench changed the
   option so that: the effort is resolved once, and the run's record and every
   request use that one value; a request keeps any other `output_config`
   members; an empty or malformed value, a level litellm refuses for these
   models (`xhigh`, `max`), or litellm's `drop_params` stops the run; each
   effort request has its own disk-cache namespace, so the cache cannot replay
   a board answer for it or its answer for a board request; and the snapshot
   freeze, every release freezer's treatment check and the board exports
   refuse to run while the variable is set. Under each run's settings (an
   empty cache, `LITELLM_DROP_PARAMS` unset, a valid value), the changed
   option builds the same requests: an offline check over all 100 households
   of both runs found each first request's HTTP body and headers unchanged,
   and the repair, doubled-budget and explanation requests changed only by a
   cache namespace that litellm does not send.

**Rules kept.** Each run covered all 100 households once. No household was
rerun or dropped for its result. Claude Opus 5.5 at high made a second request
for 2 households under the board's run rule, one after a provider error and
one after an answer stopped at the output budget. All four comparisons are
reported.

**Review.** GPT-6.1 Sol, an OpenAI model, read the plan, the code change and a
draft of the note before publication, as a bundle of those files rather than
the repository. Its verdict on that bundle, which also held the rest of the
release, was "agree with changes". The note says which changes PolicyBench
made.
