---
title: Benchmark Card
---

# Benchmark Card

This document fixes the intended interpretation of PolicyBench.

## What PolicyBench is

PolicyBench is a public no-tool benchmark for selected household-level tax and
benefit outputs from structured household facts.

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
- an administrative ground-truth benchmark

PolicyEngine outputs are benchmark reference outputs produced by
microsimulation, not administrative truth.

## Canonical benchmark vs diagnostics

PolicyBench has two evaluation modes.

`Benchmark runs`
- canonical leaderboard artifacts
- one structured response per household
- no explanations required

`Diagnostic runs`
- smaller sidecar samples
- used for qualitative analysis
- not part of leaderboard scoring

Diagnostic runs should not be mixed into leaderboard claims.

CLI default outputs under `results/local/` are scratch artifacts, not canonical
leaderboard snapshots.

## Output specification

Benchmark scope is defined in `policybench/benchmark_specs.json`. New CLI runs
default to `v2_headline`; `v1` must be selected explicitly when reproducing the
current public snapshot.

`v1`
- legacy public scope used by the current frozen site and paper exports
- includes tax bases, tax liabilities, credits, benefits, and household boolean
  labels in one headline score

`v2_headline`
- rebuilt headline scope for new runs
- includes signed household net-income components that are directly interpretable
  as taxes, benefits, or coverage eligibility
- excludes AGI-like intermediate tax bases from the main ranking
- scores coverage eligibility as binary outputs while weighting them with
  PolicyEngine dollar-value proxies

`v2_supplementary`
- diagnostic outputs that are useful but not part of the rebuilt headline
  ranking
- includes intermediate tax-base outputs, credit components, and household
  eligibility labels

Each output spec records the benchmark id, PolicyEngine variable, prompt text,
metric type, aggregation rule, role, output set, and sign in household net
income.

## Snapshot policy

The live site can change after new runs are added.

Paper tables and manuscript claims should be tied to a frozen export snapshot in:

- [benchmark_snapshot.json](/Users/maxghenis/PolicyEngine/policybench/results/paper_exports/benchmark_snapshot.json)

That file records:

- source run directories
- export time
- top models in the frozen export
- the rule that paper exports are snapshots rather than live rankings

## Country data paths

### United States

The US benchmark uses households derived from PolicyEngine US Enhanced CPS and
scores outputs against PolicyEngine US reference outputs.

### United Kingdom

The current public UK path uses a calibrated transfer dataset rather than
restricted native UK survey microdata. It should be described as a public UK
transfer path for benchmarking, not as a replacement for enhanced FRS.

## Naming discipline

Public prose should prefer:

- `reference outputs`
- `frozen snapshot`
- `public calibrated transfer dataset`

Public prose should avoid:

- `ground truth`
- `current best model` without a dated snapshot
- `first public benchmark`

## Minimum reporting standard

Every public writeup should state:

- the frozen run directories used
- the scored outputs included
- the benchmark spec and output set used
- whether the claim refers to the live site or a frozen paper snapshot
- whether UK results come from the public transfer dataset or a later artifact
