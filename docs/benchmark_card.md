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
(Kimi K3, Qwen 3.8 Max, Claude Fable 5.1, Claude Opus 5.5, Claude Sonnet 5.5,
DeepSeek V4.1 Flash) or because the card selects JSON for the family (the older
Gemini and DeepSeek rows). The per-model transport
is in the snapshot's `model_serving_config.json`.
This is an output format, not a capability — nothing executes, no result is
returned to the model, and each response is a single round trip. The benchmark
remains no-tool in every response transport.

The headline score uses the numeric answers only. Explanations are retained for
auditing, scenario exploration, and qualitative error analysis; they should not
be described as faithful reasoning traces.

## Reference outputs

PolicyBench computes each scored US reference by running
`policyengine_us.Simulation` from policyengine-us 2.15.17, the newest release
when PolicyBench began sweeping the references on 2026-09-29 (uploaded 00:23
UTC). policyengine-us 2.17.0, the newest release at publication (uploaded
2026-09-29 12:21 UTC), gives the same value for all 1,984 outputs under the same
conventions and adapter. The 55 excluded outputs keep the values they were
decided on (52 computed with policyengine-us 1.755.4, 3 with 2.15.17), and
PolicyBench re-reviewed the 19 of them that move on 2.15.17; all 19 stay
excluded. The manifest also records policyengine.py 6.1.2 for provenance. Its
certified US bundle carries policyengine-us 2.2.1, and policyengine.py does not
load beside 2.15.17.

A scored reference follows from the stated facts and from law published before
the references were frozen on 2026-07-03. Where policyengine-us projects a 2026
amount with a price index, or carries one published after the freeze, the
reference takes the amount published before the freeze or, where none was, the
last one published. Nine publication conventions set those amounts, and each
changes parameter values only: SNAP's October to December months, for example,
hold the FY2026 figures rather than USDA's FY2027 figures of 2026-08-21.
policyengine-us 2.15.17 counts Maryland county income tax in its state income
tax; an adapter takes it out again, because PolicyBench's state income tax
output leaves local tax out.

Four changes between policyengine-us 1.755.4 and 2.15.17 each moved one scored
reference: New Jersey's child tax credit schedule for 2026 to 2028 (P.L.2026,
c.26, approved June 30, 2026), Arizona's broad-based categorical eligibility
limit for SNAP (200% of the poverty guideline from March 2026, up from 185%),
child support received counting as income for school meals (7 CFR
245.6(a)(5)(ii)), and the rounding of New York's Empire State child credit
phase-out. Three federal income tax outputs left scoring (below), and two state
income tax references moved by less than $1. The reference sidecar's
`engine_upgrade` revision lists every change, and `reference_audit/2026-09-28/`
records the investigation and the independent review behind each.

## Audit scope

The frozen US annotations cover 7,796 scored rows selected because their
legacy threshold score is below 1 (2,041 further annotated rows sit on the 55
excluded outputs and are description, not audit). This audit universe contains
7,792 of the snapshot's 7,792 exact-match misses and four exact hits. Another
2,027 scored rows have a bounded score below 100 but fall outside the
legacy-threshold selection and have no audit annotation. Three judge models
produced the verdicts, all of them board rows: GPT-5.6 Sol through the Codex
CLI for 303 cases, Claude Opus 5 through the Claude Code CLI for 132 cases the
September 5 additions joined, and Claude Opus 5.5 for 239 cases the September
22 and September 29 additions joined or a reference revision changed; the
manifest's audit_annotation_artifacts.judge_provenance block carries the tally.
Verdicts change no score. A judge verdict outside the final classes, and every
reference-suspect flag, is resolved by a recorded developer adjudication
(annotations/.../us_adjudications.json), which keeps the judge's
verdict (the case's current verdict.json; a flag an earlier judge run raised is
kept and says so) beside the decision and the reasoning. This snapshot carries
68: one for each excluded output, one for each flagged reference the
adjudication affirmed or replaced with a regenerated reference, and two for
cases whose misses the judge attributed to the reference applying later law;
the adjudication records them as model errors because that law predates the
freeze.

The September 22 audit implemented each defect it confirmed in policyengine-us
1.755.4 as a sandbox fix on that engine version and recomputed every
reference under it. Eight of those root causes were fixed in policyengine-us
after the references were frozen (#8839, #9162, #9301, #9313, #9318, #9363 and
#9586: capital gain distributions, New York's renter cap, the CalEITC's lookup
at adjusted gross income, the engine's SNAP rounding, and the SNAP child
support option, whose engine values carried the opposite meaning: the engine
excluded child support paid from gross income in Michigan, which deducts it
from net income). For the September 22 references, PolicyBench applied those
fixes on 1.755.4 to the 15 scored references they move; policyengine-us 2.15.17
contains all eight, so the references now take them from the engine. An output
one of them moves that an unfixed cause also moves stays excluded. The capital
gain fix as first built also applied Wisconsin's capital gain exclusion to the
distributions, which the upstream fix does not; that part is recorded as its
own defect, not fixed upstream.

Fifty-five outputs in 39 households are excluded from scoring for every model
(`reference_exclusions.json` beside the frozen references, pinned by the
manifest). Every output a defect not fixed upstream moves by more than a dollar
is excluded: 28 are recorded as engine-defect exclusions across the eleven such
root causes (among them the IRA deduction's compensation limit and phase-out,
estate income, and the heat-and-eat SNAP utility allowance that P.L. 119-21
ended for households without an elderly or disabled member), and an output
such a defect moves that was already excluded for an unstated input keeps that
record. On policyengine-us 2.15.17 each of these outputs keeps the value its
defect produced, or it moved and a re-review found the defect still present.
Twenty-seven depend on an input the prompt never states, such as the SSI
disability criterion, months of SSDI receipt, weekly hours worked, the type of
survivor benefits, who paid for the coverage behind a disability benefit,
whether an adult tax dependent is the filers' child, or whether a listed state
and local tax refund counts as income, which turns on whether the refunded tax
reduced federal tax in the year the household paid it (26 U.S.C. 111(a));
each was recomputed under the other reading a careful reader could take, and it
moved.
Exclusion is symmetric: rows that matched the frozen reference leave the score
with rows that did not, so every model is scored on 1,929 of its 1,984
requested outputs. The rows on those outputs stay annotated as description:
each carries its exclusion's class, except the 53 answers that never parsed,
which stay parse_contract_failure; no scored row carries a descriptive class.
The prompt states disability as one general fact
(any of the six Current Population Survey disability-difficulty items); SSI,
SNAP, Medicare and the tax code each apply their own determination, which no
benchmark person carries, so a disabled person's references take the
non-disabled path unless another listed fact establishes the determination
(manuscript section "Disability in the household facts"). Do not read a $0 SSI
reference for a disabled under-65 household member as a finding about that
person's SSI eligibility.

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
- Activation is a snapshot decision: the current 2026-09-29 snapshot scores
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

Each frozen row uses its recorded per-call cost: reconstructed from token counts
at the list price configured at request time, or the provider-reported charge
where no reconstruction was available. List-price overrides apply at request time, not retroactively to
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
