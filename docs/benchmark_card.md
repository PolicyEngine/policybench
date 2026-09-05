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
- structured responses: whole-scenario, or one- or three-output subsets for the models recorded in the snapshot's `model_serving_config.json`
- numeric answers for every requested output
- one required non-empty explanation for each output

Structured responses are collected through the transport each model card
records: a forced answer-schema tool call (`submit_outputs`) where the card
selects the tool transport and the provider accepts a forced call, or the same
fields returned as a JSON object — because the provider rejects a forced tool
(Kimi K3, Qwen 3.8 Max, Claude Fable 5.1) or because the card selects JSON
for the family (the older Gemini and DeepSeek rows). The per-model transport
is in the snapshot's `model_serving_config.json`.
This is an output format, not a capability — nothing executes, no result is
returned to the model, and each response is a single round trip. The benchmark
remains no-tool in every response transport.

The headline score uses the numeric answers only. Explanations are retained for
auditing, scenario exploration, and qualitative error analysis; they should not
be described as faithful reasoning traces.

## Audit scope

The frozen US annotations cover 8,783 scored rows selected because their
legacy threshold score is below 1 (293 further annotated rows sit on the eleven
excluded outputs and are description, not audit). This audit universe contains
8,780 of the snapshot's 8,780 exact-match misses and three exact hits. Another
1,605 scored rows have a bounded score below 100 but fall outside the legacy-threshold selection
and have no audit annotation. Two judge models produced the verdicts, both of
them board rows: GPT-5.6 Sol through the Codex CLI for 318 cases, and Claude
Opus 5 through the Claude Code CLI for the 350 cases a September 2026 addition
joined; the manifest's audit_annotation_artifacts.judge_provenance block
carries the tally. Verdicts change no score. A judge verdict outside the final
classes is resolved by a recorded developer adjudication
(annotations/.../us_adjudications.json: one case in this snapshot, the judge's
prompt-ambiguity reading of scenario_064 SSI adjudicated to llm_error with the
reasoning attached).

Eleven outputs in ten households are excluded from scoring for every model
(`reference_exclusions.json` beside the frozen references, pinned by the
manifest): their reference depends on an engine input the certified household
data never carried and the prompt therefore never listed. The SSI disability
criterion is false for every person in the June 2026 build, and months of SSDI
receipt is never carried and never promptable. Each excluded reference was
recomputed with policyengine-us 1.755.4 under the reading a careful reader could
take of the stated `is disabled` or SSDI-income fact, and it moved. Exclusion is
symmetric: rows that matched the frozen reference leave the score with rows that
did not, so every model is scored on 1,973 of its 1,984 requested outputs. The
rows on those outputs stay annotated with the class `prompt_ambiguity` as
description; no scored row carries that class. Do not read a $0 SSI reference
for a disabled under-65 household member as a finding about that person's SSI
eligibility.

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
policy period used for manuscript claims. For the current US release, that means
US tax year 2026.

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
- Activation is a snapshot decision: the current 2026-09-05 snapshot scores
  100 public households whose scenario manifest was generated on 2026-06-12
  from a 125-household request split with seed 1042. It does not report
  protected scores. The first snapshot that reports protected scores should
  state both splits' sizes and the split seed's custody (who can regenerate
  membership).
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

## Cost basis

Each frozen row uses its recorded per-call cost: provider-reported where the
provider returns one, otherwise reconstructed at the configured list price at
request time. List-price overrides apply at request time, not retroactively to
recorded costs. Models without per-call costs use the frozen release-metadata
cost. Published model costs retain these recorded totals rather than repricing
past calls at today's rates.

## Country data paths

### United States

The US benchmark uses households sampled from the certified PolicyEngine
populace dataset and scores outputs against PolicyEngine US reference outputs.

### United Kingdom

The repository retains legacy UK-calibrated transfer-path support, but the
current public release is US-only. If UK results are revived, describe that path
as a public UK transfer path for benchmarking, not as a replacement for enhanced
Family Resources Survey (FRS) microdata or as a population-representative UK
household sample.

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
