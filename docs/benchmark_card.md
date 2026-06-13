---
title: Benchmark Card
---

# Benchmark Card

This document fixes the intended interpretation of PolicyBench.

## What PolicyBench is

PolicyBench is a public no-tool benchmark for selected person- and
household-facing tax and benefit outputs from structured household facts.

The canonical task is:

1. show the model a household description
2. request the benchmark outputs for that household
3. score the model response against PolicyEngine reference outputs

PolicyBench measures a combined task:

- no-tool estimation
- policy-parameter recall
- structured multi-output response generation

It should not be described as a pure reasoning benchmark.

## What PolicyBench is not

PolicyBench is not:

- a production tax-and-benefit calculator
- a certification of tax-advice quality
- a general test of tool use
- an administrative-record benchmark

PolicyEngine outputs are benchmark reference outputs produced by
microsimulation, not administrative records.

## Canonical response contract

PolicyBench has one canonical evaluation mode.

`Benchmark runs`
- canonical leaderboard artifacts
- one structured response per household
- numeric answers for every requested output
- one required non-empty explanation for each output

Structured responses are collected through each provider's structured-output
channel: where the API supports function calling, models fill a single answer
schema (`submit_outputs`); otherwise they return the same fields in JSON mode.
This is an output format, not a capability — nothing executes, no result is
returned to the model, and each response is a single round trip. The benchmark
remains no-tool in every response transport.

The headline score uses the numeric answers only. Explanations are retained for
auditing, scenario exploration, and qualitative error analysis; they should not
be described as faithful reasoning traces.

Canonical runs require numeric answers and explanations for each requested
output. If future prompt-contract ablations omit explanations, they should be
labeled as ablations and not mixed into leaderboard claims.

CLI default outputs under `results/local/` are scratch artifacts, not canonical
leaderboard snapshots.

Operational paid runs should follow the repository runbook
([`docs/runbook.md`](runbook.md)): fixed scenario manifests, Claude models in
serial timeout-safe mode, non-Claude models in bounded parallel mode, and one
final merge/export pass.

## Output specification

Benchmark scope is defined in `policybench/benchmark_specs.json`. New CLI runs
default to `headline`.

`headline`
- headline scope for current runs
- includes person- or household-facing outputs that are directly interpretable
  as taxes, benefits, health-related support, or coverage eligibility
- excludes AGI-like intermediate tax bases and payroll subcomponents from the
  public ranking
- expands person-native coverage outputs to the people shown in the prompt and
  aggregates other lower-entity outputs to the household before scoring
- scores coverage eligibility as binary outputs in the main ranking
- uses PolicyEngine dollar-value proxies for coverage outputs only in the
  secondary household-equal impact score

Each output spec records the benchmark id, PolicyEngine variable, prompt text,
metric type, aggregation rule, role, output set, and sign in household net
income.

Output selection follows a net-income-oriented rule. The benchmark includes
direct tax, credit, benefit, health-support, and coverage outputs that can be
asked from household facts. It excludes intermediate tax bases, payroll
subcomponents, outputs needing unavailable history or local market data, and
outputs that are primarily take-up or imputation assignments. WIC is requested
as person-level eligibility, not as a dollar amount.

## Snapshot policy

The live site can change after new runs are added.

Paper tables and manuscript claims should be tied to a frozen export snapshot.
Each paper should report the exact export date, committed export artifact,
artifact hashes, source run labels, model set, household sample, output set, and
policy period used for manuscript claims. For the current cross-country release,
that means US tax year 2026 and UK fiscal year 2026-27.

The public scenario explorer exposes the household prompts, model outputs, and
reference outputs. The public leaderboard should therefore be treated as an
open-set benchmark with possible leakage from released cases into future model
behavior or benchmark-specific prompting. Future protected leaderboard claims
require a separate held-out or rotating evaluation set.

## Protected split

`policybench reference-outputs --private-fraction <f> --split-seed <n>`
reserves a deterministic subset of sampled households for a private
evaluation split. Public files keep their standard names, so every existing
consumer is unaffected; the private split goes to sibling
`reference_outputs-private.csv` / `scenarios-private.csv` files (with
`.meta.json` sidecars recording `split`, `private_fraction`, and
`split_seed`). Membership is a pure function of the scenario id and the split
seed, so regeneration reproduces the same partition regardless of sampling
order.

Discipline for private files:

- Never commit them, publish them, or pass them to dashboard exports. Only
  aggregate scores from the private split may be released.
- Run evaluations on the private split by passing the private manifest
  explicitly (`--scenario-manifest .../scenarios-private.csv`); the eval and
  analyze commands need no other changes.
- Activation is a snapshot decision: the current 2026-05-20 snapshot predates
  the split and remains fully public. The first snapshot that reports
  protected scores should state both splits' sizes and the split seed's
  custody (who can regenerate membership).
- Prompt canaries (unique strings embedded in private-split prompts to detect
  future training contamination) are planned for the same snapshot that
  activates the split, since adding them changes prompt text and therefore
  benchmark identity.

## Evaluation conditions

The benchmark currently has one condition, `no_tools`. That label is attached
at dashboard-export time (`build_dashboard_payload` in
`policybench/analysis.py`), not carried through run artifacts: prediction
CSVs have no condition column, and the eval loop does not parameterize it.
Adding a second condition (web search, tool-assisted) therefore requires
threading a `condition` field through run storage and analysis before the
export — tracked as part of the run-store cutover — rather than new UI work;
the site's types and leaderboard already filter on `condition`.

## Country data paths

### United States

The US benchmark uses households derived from PolicyEngine US Enhanced Current
Population Survey (CPS) and scores outputs against PolicyEngine US reference
outputs.

### United Kingdom

The current public UK path uses a calibrated transfer dataset rather than
restricted native UK survey microdata. It should be described as a public UK
transfer path for benchmarking, not as a replacement for enhanced Family
Resources Survey (FRS) microdata or as a population-representative UK household
sample.

## Naming discipline

Public prose should prefer:

- `reference outputs`
- `frozen snapshot`
- `public calibrated transfer dataset`
- separate country leaderboards

Public prose should avoid:

- unqualified `truth` language for reference outputs
- `current best model` without a dated snapshot
- `first public benchmark`
- collapsing country scores into a universal model ranking

## Minimum reporting standard

Every public writeup should state:

- the frozen export artifact and, when available, source run labels
- the frozen scenario manifests and reference-output artifacts, or a durable
  external artifact bundle containing them
- the scored outputs included
- the output set used
- whether the claim refers to the live site or a frozen paper snapshot
- whether UK results come from the public transfer dataset or a later artifact
- whether any cross-country comparison is descriptive or score-producing
- sensitivity checks for at least amount-only, binary-only, positive-reference
  cases, zero-reference cases, country-only rankings, and household-equal
  impact scores when available
