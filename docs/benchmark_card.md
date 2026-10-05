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
selects the tool transport, or the same fields returned as a JSON object where
it selects JSON. For most JSON rows the card records that the provider rejects
a forced tool call: Claude Fable 5.1, Claude Opus 5.5, Claude Sonnet 5.5,
DeepSeek V4.1 Flash (whose card says the same of the V4 rows), Kimi K2.6, Kimi
K3, Qwen 3.7 Max and Qwen 3.8 Max. The cards of DeepSeek V4 Pro and GLM-5.2
select JSON without recording a rejection, and the older Gemini rows answer as
JSON by the Gemini family default. The per-model transport is in the
snapshot's `model_serving_config.json`.
This is an output format, not a capability — nothing executes, no result is
returned to the model, and each response is a single round trip. The benchmark
remains no-tool in every response transport.

The headline score uses the numeric answers only. Explanations are retained for
auditing, scenario exploration, and qualitative error analysis; they should not
be described as faithful reasoning traces.

## Reference outputs

PolicyBench computes each scored US reference by running
`policyengine_us.Simulation` from policyengine-us 2.38.6, the newest release
when PolicyBench began sweeping the references on 2026-10-10 (uploaded 05:39
UTC). policyengine-us 2.38.6 was still the newest release when PolicyBench
checked PyPI on 2026-10-10 at 06:53 UTC. The 58 excluded outputs keep the
values they were decided on (38 computed with policyengine-us 1.755.4, 18 with
2.15.17, 2 with 2.38.6), and PolicyBench re-reviewed the 17 of them that move on
2.38.6; all 17 stay excluded. The manifest also records policyengine.py 6.1.2
for provenance. Its certified US bundle carries policyengine-us 2.2.1, and
policyengine.py does not load beside 2.38.6.

A scored reference follows from the stated facts and from law published before
PolicyBench froze the references on 2026-07-03. Where policyengine-us projects
a 2026 amount with a price index, or carries one published after the freeze,
the reference takes the amount published before the freeze or, where none was,
the last one published. Nine publication conventions set those amounts, and each
changes parameter values only: SNAP's October to December months, for example,
hold the FY2026 figures rather than USDA's FY2027 figures of 2026-08-21.

PolicyBench first moved the references off the engine version that froze them
on 2026-09-29, to policyengine-us 2.15.17, the newest release when it began
sweeping the references that day (uploaded 00:23 UTC). policyengine-us 2.15.17
counts Maryland county income tax in its state income tax; an adapter takes it
out again, because PolicyBench's state income tax output leaves local tax out,
and every later build keeps the adapter. policyengine-us 2.17.0, the newest
release when PolicyBench checked PyPI on 2026-09-29 at 14:58 UTC, gave the same
value as 2.15.17 for all 1,984 outputs under the same conventions and adapter.

Four changes between policyengine-us 1.755.4 and 2.15.17 each moved one scored
reference: New Jersey's child tax credit schedule for 2026 to 2028 (P.L.2026,
c.26, approved June 30, 2026), Arizona's broad-based categorical eligibility
limit for SNAP (200% of the poverty guideline from March 2026, up from 185%),
child support received counting as income for school meals (7 CFR
245.6(a)(5)(ii)), and the rounding of New York's Empire State child credit
phase-out. Three federal income tax outputs left scoring (below), and two state
income tax references moved by less than $1. The reference sidecar's
2026-09-29 `engine_upgrade` revision lists every change, and
`reference_audit/2026-09-28/` records the investigation and the independent
review behind each.

On 2026-10-10 PolicyBench moved the references again, from 2.15.17 to 2.38.6, a
release that fixes engine defects behind excluded outputs, and recomputed every
output under the same conventions and adapter. The new version fixes the
defects behind 18 outputs. Release 20261006 excluded 14 of them, which return to
scoring; the other four are the 2026-10-06 defects below, which stay scored.
Each lands within $1 of its audited corrected value, and the sidecar's
2026-10-10 revision names the upstream fix behind it: the IRA deduction's
compensation limit and a dependent's contributions (#10032, #9801; three
outputs), the IRA deduction's active-participant phase-out (#10032; four
outputs), the IRA deduction's active-participant phase-out and California's
itemized deduction conformity (#10032, #10034), the IRA deduction's
active-participant phase-out and estate income in gross income (#10032,
#10027; two outputs), California's itemized deduction conformity (#10034),
estate income in gross income (#10027, #9633; two outputs), New Jersey's worker
unemployment and workforce contributions (#10031), Arizona's standard deduction
indexing (#9928), Ohio's medical deduction for health insurance premiums
(#10020), Colorado's 2026 sales tax refund (#9946) and New York's 2026 child and
dependent care credit (#9948). The move changes one scored reference beyond the
$1 tolerance: policyengine-us now counts Idaho's $10 permanent building fund
tax (Idaho Code 63-3082) in state income tax (#9810). It also moves two Indiana
households' local income tax onto a county the prompt does not state, and
PolicyBench excluded both outputs. One more output, a California household's
state income tax, lands on its recorded corrected value but stays excluded: the
release's judge found that its reference rests on a further defect, California's
non-conformity to the federal educator expense deduction (FTB Instructions for
Schedule CA (540), Section C, line 11), which policyengine-us 2.38.6 still
allows. `reference_audit/2026-10-09-engine-upgrade/` holds the builder, its
evidence and the reviewed actions.

## Audit scope

The frozen US annotations cover 8,001 scored rows selected because their
legacy threshold score is below 1 (2,212 further annotated rows sit on the 58
excluded outputs and are description, not audit). This audit universe contains
7,997 of the snapshot's 7,997 exact-match misses and four exact hits. Another
2,138 scored rows have a bounded score below 100 but fall outside the
legacy-threshold selection and have no audit annotation. Three judge models
produced the verdicts, all of them board rows: GPT-5.6 Sol through the Codex
CLI for 269 cases, Claude Opus 5 through the Claude Code CLI for the 94 cases
the September 5 additions joined that no later judge re-judged, and Claude Opus
5.5 for 314 cases the September 22, September 29, September 30 and October 9
additions joined or a reference revision changed; the
manifest's audit_annotation_artifacts.judge_provenance block carries the tally.
Verdicts change no score. A judge verdict outside the final classes, and every
reference-suspect flag, is resolved by a recorded developer adjudication
(annotations/.../us_adjudications.json), which keeps the judge's
verdict (the case's current verdict.json; a flag an earlier judge run raised is
kept and says so) beside the decision and the reasoning. This snapshot carries
70: one for each excluded output, one for each flagged reference the
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

Fifty-eight outputs in 42 households are excluded from scoring for every model
(`reference_exclusions.json` beside the frozen references, pinned by the
manifest). The September 22 audit recomputed every reference on
policyengine-us 1.755.4 under each defect's sandbox fix and excluded every
output a defect not fixed upstream moved by more than a dollar. Of those
records, 14 remain as engine-defect exclusions. Nine rest on the five root
causes policyengine-us 2.38.6 does not fix (among them Idaho's subtraction for
health insurance premiums, elective deferrals in the earned income behind the
EITC, and the heat-and-eat SNAP utility allowance that P.L. 119-21 ended for
households without an elderly or disabled member). policyengine-us 2.38.6
computes four of them at their corrected values; they stay excluded because
each also moves under an input the prompt does not state. policyengine-us
2.38.6 computes one more at its recorded corrected value, but its reference
rests on a further engine defect, found on 2.38.6 and not fixed there, so it
stays excluded. An output such a defect moves that was
already excluded for an unstated input keeps that record. On each later
engine these outputs keep the value they were decided on: the engine gives the
same value, or it moved and a re-review found the exclusion still holds.
Forty-two depend on an input the prompt never states, such as whether a
person meets SSI's definition of disability, months of SSDI receipt, weekly
hours worked, the type of survivor benefits, who paid for the coverage behind a
disability benefit, whether an adult tax dependent is the filers' child,
whether a listed state and local tax refund counts as income, which turns on
whether the refunded tax reduced federal tax in the year the household paid it
(26 U.S.C. 111(a)), the state income tax withheld or paid during 2026, which
the federal state and local tax deduction takes as its state income tax part
and policyengine-us estimates from federal adjusted gross income, Medicare
enrollment and a Part B premium, which policyengine-us assumes for every
Medicare-eligible person and counts as a medical expense, whether the
employer deducts the employee share of a state paid-leave or disability
premium that the law lets it deduct but does not require, whether a household's
income tax covers only the head and spouse's return or every return its members
must file, or the county of residence, which decides Indiana's county income
tax; each was recomputed under the other reading a careful reader could take,
on the engine version that produced its reference, and it moved. The other two
are Louisiana households' state income tax, whose reference rests on a standard
deduction amount Louisiana published after the freeze. One of the forty-two, a California household head's Medicaid eligibility, moved
only once the engine read SSI's definition of disability where the law does.
The head's income is above the limit for the adult expansion group, so only a
disability pathway leads to Medi-Cal, and California's Working Disabled Program
requires SSI's definition of disability (42 CFR 435.540(a)). policyengine-us
2.15.17 tests the general disability flag instead and gives 1 under either
reading; with the program's test reading SSI's definition of disability, the
head qualifies only by meeting it.
Exclusion is symmetric: rows that matched the frozen reference leave the score
with rows that did not, so every model is scored on 1,926 of its 1,984
requested outputs. The rows on those outputs stay annotated as description:
each carries its exclusion's class, except the 48 answers that never parsed,
which stay parse_contract_failure; no scored row carries a descriptive class.
The prompt states disability as one general fact
(any of the six Current Population Survey disability-difficulty items); SSI,
SNAP, Medicare and the tax code each apply their own determination, which no
benchmark person carries, so a disabled person's references take the
non-disabled path unless another listed fact establishes the determination
(manuscript section "Disability in the household facts"). Do not read a $0 SSI
reference for a disabled under-65 household member as a finding about that
person's SSI eligibility.

On policyengine-us 2.15.17, PolicyBench re-ran four of the September 22 sweeps
behind these exclusions over every output: the IRA deduction limit fix, the net
investment income tax definition, and the readings for mortgage residence and
40 unlisted weekly hours. It ran a new sweep for the state and local tax refund
reading. Set against the same 2.15.17 calculation without its fix or reading,
no sweep moves a scored output by more than the $1 exact-match tolerance, and
three scored outputs move by less. The other ten defect fixes and the other
readings (SSI's definition of disability, months of SSDI receipt, survivor
benefits, disability coverage, adult dependents and Massachusetts bank
interest) ran on 1.755.4 only. The engine-upgrade review covered the outputs
the upgrade moved, and through them it flagged the California Medicaid output
above, which the reading of SSI's definition of disability does not move on
2.15.17 because the engine's Working Disabled Program test reads the general
disability flag. An output that one of those fixes or readings would move on
2.15.17, but did not move on 1.755.4, could still be scored.

On 2026-10-05 a review of release dashboard-data-20260930 swept every output on
policyengine-us 2.15.17 under readings of three inputs no prompt states: the
state income tax in the federal state and local tax deduction, which
policyengine-us fills with a formula estimate of withholding on federal
adjusted gross income (`reference_audit/2026-10-05/`); Medicare enrollment and
the Part B premium, which policyengine-us assumes for every Medicare-eligible
person (`reference_audit/2026-10-05-medicare-part-b/`); and whether the
employer deducts an employee share of a state paid-leave or disability premium
that the law lets it deduct but does not require
(`reference_audit/2026-10-05-payroll/`). Each sweep's baseline reproduces all
1,928 references that release scored. Beyond the $1 tolerance the sweeps move
eight scored outputs, which PolicyBench excluded: the federal income tax of
three households, one household's Virginia income tax, and the payroll tax of
four households in Minnesota, Colorado, Massachusetts and New York. They also
move two federal income tax outputs that were already excluded, and no output
that is still scored by any amount. No judge had flagged the eight.

On 2026-10-06 PolicyBench ruled to exclude ten more outputs. Eight came from
a reference adversary (`reference_audit/2026-10-05-reference-adversary/`), which
flags the scored outputs where many models, or several of the strongest, agree
on an answer the reference does not give. A judge that cannot yet see the
engine's derivation works each flagged output from primary law, and only then
reconciles its answer with the derivation. The adversary flagged 61 outputs and
ran 52, the other nine belonging to other audits, and it held 45 references. An
independent check of its seven other verdicts confirmed four as engine defects
(Arizona's 2026 standard deduction left unindexed, Ohio's medical deduction for
health insurance premiums, Colorado's 2026 sales tax refund, and New York's
2026 child and dependent care credit), refuted two (the Medicaid eligibility of
two children in a North Carolina household, whose references stand), and found
the seventh to be a question of definition: where a dependent must file their
own return, the output definitions do not say whether the household's income
tax includes it, which reaches four outputs in a Pennsylvania and a Missouri
household. The other two are the Louisiana outputs above
(`reference_audit/2026-10-05-louisiana/`). The 2026-10-10 engine move fixed
the four defects, so those four outputs stay scored; the other six are
excluded.

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
- Activation is a snapshot decision: the current 2026-10-10 snapshot scores
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

The UK path samples households from the public calibrated transfer dataset in
`PolicyEngine/policyengine-uk-data` (`enhanced_cps_2025.h5`, pinned to commit
`6b1f80e` and its sha256). Those records are PolicyEngine US households
re-weighted to UK targets, not UK survey records, and they carry no State
Pension: every pension-age person in the sample has none, and the prompt says
so by listing none. Since October 2026 the path works as follows.

- **Reference-period inputs.** The artifact stores the 2025 survey year.
  PolicyEngine UK uprates stored incomes, rents and savings when it calculates
  2026-27, so the prompt shows the uprated 2026-27 amounts the reference uses.
- **References from the prompted facts.** Each UK reference is a PolicyEngine
  UK household simulation of exactly the facts the prompt lists, one simulation
  per household, as on the US path. Facts the source record holds and the
  prompt omits (for example Universal Credit deductions, or the seeded draw
  that marks some 2026 health-element claimants as new) cannot move a
  reference. `calculate_uk_transfer_microsimulation_values` recomputes the
  outputs from the full records as a cross-check.
- **Derived facts stated.** Where PolicyEngine UK derives a fact that changes
  an output, the prompt states it: each person's sex and date of birth (State
  Pension age and the Pension Credit savings credit cutoff), the education
  status of anyone aged 16 to 19 (qualifying young person rules), and an
  adult's limited capability for work and work-related activity for Universal
  Credit, held since before 6 April 2026.
- **Engine-version guards.** Reference generation stops if the artifact stores
  a variable the installed PolicyEngine UK does not define, or if a derived
  fact the prompt states is renamed, so a model release cannot silently drop
  an input from the reference while it still reaches the prompt.

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
