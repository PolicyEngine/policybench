# PolicyBench

How well can frontier models calculate tax and benefit outcomes without tools?

PolicyBench measures how well frontier AI models estimate selected household tax
and benefit outputs without tools.

For benchmark scope, snapshot policy, and terminology, see the
[benchmark card](https://github.com/PolicyEngine/policybench/blob/main/docs/benchmark_card.md).

Current public benchmark scenarios are sampled from the certified PolicyEngine
Microcosm US dataset and evaluated under tax year 2026 rules with
PolicyEngine-US.

## Condition

1. **AI alone**: Models estimate tax/benefit values using only their training knowledge

Models return answers by filling a structured answer schema, transmitted over
the provider's function-calling or JSON-mode channel. That channel is purely an
output format: nothing executes, no information flows back to the model, and
each response is a single round trip, so the condition stays no-tool regardless
of transport.

## Benchmark scope

Benchmark outputs are defined in `policybench/benchmark_specs.json`. New CLI
runs default to `headline`, which focuses the main ranking on person- or
household-facing outputs that contribute to household net income. PolicyEngine
variables may be native to lower-level entities, but benchmark outputs are
either expanded to people shown in the prompt or aggregated to the household
before scoring. Coverage outputs are binary flags in the headline ranking; the
secondary weighted views use PolicyEngine value proxies to give those flags a
dollar-scale weight. Intermediate tax bases and payroll subcomponents are
excluded from the headline ranking. WIC is requested as person-level
eligibility, not as a dollar amount.

## Programs evaluated

The current public release covers selected federal taxes, credits, benefits,
coverage labels, and state-tax outputs in the US. US federal income tax is scored
as a compact decomposition: tax after nonrefundable credits and before
refundable credits, plus refundable federal credits excluding the ACA Premium Tax
Credit. The June 2026 Microcosm source run requested ACA Premium Tax Credit
responses, but they are excluded from the canonical scored leaderboard because
explanation audits showed prompt ambiguity without plan-specific Marketplace
information.

## Quick start

```bash
pip install policybench
policybench --help
```

For repository development, clone the full Git repository before running tests:

```bash
pip install -e ".[dev]"
pytest
```

Verify the dashboard with its bundled data prepared automatically:

```bash
cd app
bun run lint
bun run test
bun run build
```

## Paper and documentation site

The manuscript in `paper/` renders with Quarto. Its Python environment is the
`docs` extra, which holds only the Jupyter kernel and notebook runner that
Quarto's Jupyter engine drives (ipykernel, nbclient, nbformat). See
[`paper/README.md`](paper/README.md) for the other prerequisites.

```bash
uv sync --extra docs
uv run python paper/render_paper.py
```

The operational-docs site in `docs/` builds with Jupyter Book 2, which
`docs/requirements.txt` declares outside `uv.lock`. Build it in a throwaway
environment (Jupyter Book needs Node.js 18, 20 or 22+):

```bash
cd docs
uv run --no-project --with-requirements requirements.txt jupyter book build --html
```

The output lands in `docs/_build/` (gitignored). jupyter-book stays out of the
`docs` extra on purpose: it pulls in jupyter-server, nbconvert, bleach, mistune
and their dependencies, none of which the paper render uses, and every package
in `uv.lock` is in Dependabot's scan whichever extra it belongs to.

## Benchmark run

For paid/public runs, follow the concrete
[benchmark runbook](https://github.com/PolicyEngine/policybench/blob/main/docs/runbook.md).
The short version is: generate fixed reference-output manifests first, run
Claude models serially, run non-Claude models in parallel, then do a final merge
and export pass.

```bash
# Generate reference outputs for 100 sampled households using headline outputs
policybench reference-outputs -n 100 --seed 42

# Run AI-alone evaluations on the exported scenario manifest.
# The standard response contract includes numeric answers and explanations.
policybench eval-no-tools -n 100 --seed 42

# For larger runs, use resumable per-model chunks.
policybench eval-no-tools-chunked \
  --scenario-manifest results/local/scenarios.csv \
  --output-dir results/local/no_tools_chunked \
  --country us \
  --chunk-size 10 \
  --parallel 1

# Non-Claude models can be run with higher concurrency after a smoke test.
# Claude models must use --parallel 1 and --model-parallel 1.

# Analyze local results and export local artifacts
policybench analyze --output-dir results/local/analysis
```

## Response-contract retries

For paid runs, retry broken full responses before freezing a snapshot:

```bash
policybench retry-failed-responses \
  --country us \
  --source-predictions results/local/full_run/us/predictions.csv \
  --scenario-manifest results/local/full_run/us/scenarios.csv \
  --output-dir results/local/full_run/us/response_retries/round_1
```

This retries whole model-household responses with missing numeric answers,
missing explanations, or infrastructure errors. Accepted retries replace the
entire original response; partial retry responses are rejected and the original
rows are preserved.

## Repeated runs

```bash
# Optional: run the same benchmark multiple times on the saved scenario manifest
policybench eval-no-tools-repeated -n 100 --seed 42 --repeats 3 -o results/local/no_tools/runs

# Analyze the canonical point estimate plus across-run stability
policybench analyze --runs-dir results/local/no_tools/runs --output-dir results/local/analysis
```

Each repeat asks the models again. The command keeps the LiteLLM disk cache on,
but each repeat looks up and stores its answers under its own cache namespace
(`repeat=run_000`, `repeat=run_001`, ...), so no repeat looks up another
repeat's answers, or those of an `eval-no-tools` run. The namespace is set on
the cache of the whole Python process, which the command has to itself; code
that calls `run_repeated_no_tools_eval` must run no other evaluation in the
same process meanwhile.

Running the command again reuses what each repeat already has. Into the same
output directory, a repeat resumes from its CSV before it consults the cache.
The batch runner keeps each household for which the file has a row for every
requested output, with no infrastructure error (and an explanation column when
explanations are on), even if some of those rows hold no parsed answer; it asks
again for the other households. With `--single-output` it keeps every row
without an infrastructure error, provided the file has `model`, `scenario_id`,
`variable` and `prediction` columns, and an explanation column when
explanations are on; otherwise it keeps none. Into a new output directory with
the same cache directory, a repeat looks for its answers under its own
namespace and asks the model for those the cache does not find. A household's
first-round requests (its first request, or each explanation chunk) are the
same every time, so the cache finds their answers when LiteLLM computes the
same key for the rebuilt request's lookup as for the original's store (not so
for a `gemini/` tool request unless the harness pins its key) and the entry is
still there (LiteLLM's disk cache drops the oldest entries past 1 GiB). A
repair or explanation-only request is built from the answers before it, so the
cache finds its answer only when the rebuilt request comes out the same. To
draw a new, independent set of repeats, use a new output directory and point
`POLICYBENCH_CACHE_DIR` at a new directory.

After each repeat the command prints how many provider responses and cache
replays the repeat's rows record and, when it kept rows from an existing file,
how many of those the kept rows recorded when they were written.

Before its first request and after each repeat, the command checks every CSV
file in the output directory, whoever wrote it (`analyze --runs-dir` reads them
all). Each answered row records a response id (`provider_response_id`: the
first of its request group, which is a household, or one of its outputs with
`--single-output`; the provider's id, or one LiteLLM generated when the
provider gave none), and a cache replay returns the stored response with its
id, so two files holding the same model and response id hold one answer twice.
The command then stops with an error naming the files. It also stops at a file
with answered rows but no response id (written before the column was added, or
cut short by an interrupted write), which it cannot check, and at a file it
cannot read. Use a new output directory then. The check sees only each group's
first id, so a household whose first explanation chunk got no response in one
file could share later chunks with another file unseen.

`policybench reference-outputs` writes PolicyEngine reference outputs, not
administrative truth. It also writes `results/local/scenarios.csv`, and the eval
commands reuse that manifest by default instead of regenerating households from
the current source dataset. Prediction CSVs also get a `.meta.json` sidecar so
resumes only happen against the exact same manifest, model set, and program set.
