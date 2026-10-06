# Release dashboard-data-20261006

This release applies Max's rulings of 2026-10-05 to release `dashboard-data-20260930`. No model, answer, reference value or serving row changes. The board snapshot stays "Snapshot 2026-09-30".

| Ruling | Change | Evidence |
|---|---|---|
| d963 | Exclude federal income tax before refundable credits for scenario_022 (CA), scenario_081 (MA) and scenario_114 (VA). Their SALT deduction rests on policyengine-us's formula estimate of state income tax withheld, which no prompt states. | `reference_audit/2026-10-05/` (PR #191) |
| d974 | Exclude scenario_114's Virginia income tax before refundable credits. Its medical deduction counts a modeled Medicare Part B premium, which no prompt states. | `reference_audit/2026-10-05-medicare-part-b/` (PR #193) |
| d972 | Exclude payroll_tax for scenario_032 (MN), 043 (CO), 081 (MA) and 082 (NY). Each counts the employee share of a state paid-leave premium that the employer may deduct but need not. Do not regenerate. | `reference_audit/2026-10-05-payroll/` (PR #194) |
| d831 | Date the model response window from the last answer: 2026-06-12 to 2026-09-29. | `scripts/freeze_snapshot.py` `model_response_window` (PR #188) |
| Louisiana (PR #192) | Keep scenario_051 and scenario_077 at the $12,835 deduction. | `reference_audit/2026-10-05-louisiana/` |

PR #197's rewrites of scenario_031's Medicaid annotations ship with this release's re-export.

PR #192's documentation sentence is held under d994. Applied as written, it would change five scored references held under the 2026-09-22 conventions:
- Idaho's zero-rate threshold (scenario_076);
- SNAP's FY2027 standard deduction for households of four or more (scenario_008, scenario_038 and scenario_109);
- Maryland's 2026 return deduction under the IRS reading (scenario_068).

This release retains the existing convention and every reference value. The wording-only Louisiana case-note rewrites ship; the held sentence requires a separate methodology decision.

## Inputs

- `spec.json`. It holds:
  - the base (tag, commit 8b4c0ca1, payload sha256 and bytes);
  - the three proposal files and the outputs each ruling names;
  - four edits to records, each with its source;
  - the rule and derivation text;
  - the eight adjudications' subtypes and reasoning;
  - the judge-evidence waves.
- `annotation_rewrites.json`: whole-field rewrites of annotation text, as in #197's `rewrites.json`. Each holds a row's whole old and whole new text. They are applied before the adjudications, which append their sentence to the excluded case notes.
- The base: release 20260930's archived stage (`results/local/release-batch/base-20260930`), which the driver only reads, and git at the base commit.

## Commands

```
WT=$PWD; PY=$WT/.venv/bin/python; export OPENBLAS_NUM_THREADS=1
$PY scripts/release_20261006.py prepare --base-stage results/local/release-batch/base-20260930 --stage results/local/release-batch/dashboard-data-20261006
$PY scripts/release_20261006.py export --stage results/local/release-batch/dashboard-data-20261006
$PY scripts/release_20261006.py freeze --stage results/local/release-batch/dashboard-data-20261006 --dry-run
$PY scripts/release_20261006.py freeze --stage results/local/release-batch/dashboard-data-20261006
PYTHONPATH=$WT $PY scripts/sensitivity_by_variable.py
PYTHONPATH=$WT $PY scripts/rescore_sensitivity_summaries.py --release dashboard-data-20261006
PYTHONPATH=$WT $PY paper/render_paper.py
$PY scripts/freeze_snapshot.py --rendered-only
```

`prepare` also rewrites `reference_audit/2026-09-28/verification/judge_verdicts.json`, the judge evidence the adjudication tests read.

## Gates

**prepare**
- The base stage's payload is release 20260930's.
- Its references, predictions, exclusions and annotations equal the base commit's.
- The committed annotations are release 20260930's plus #197's ledger, and the working tree is HEAD's.
- The proposal files hold exactly the ruled outputs. Each record is a 2026-10-05 developer unlisted-input record on policyengine-us 2.15.17.
- No ruled output is already excluded or adjudicated. Each edit fits exactly once.
- The adjudications and exclusions name the same outputs.
- Every adjudication keeps its case's sha256-bound verdict.
- The annotation files differ from release 20260930's only in the eight cases' classes and the reworded outputs' text.

**export**
- Two exports of the stage give the same bytes.
- The payload has release 20260930's sections, roster and stable model fields: condition, cost, tokens, latency and accuracy.
- Every model is scored on the same 1,920 outputs.
- The exclusions are the base's plus the eight.
- Each changed cell field is one the release allows.
- **Scope check:** with release 20260930's exclusion record substituted, the staged bundle reproduces release 20260930's modelStats, programStats, heatmap and globalWeights exactly. So every score change comes from the eight records.

**freeze**
- The receipt binds the payload, spec, rewrites, evidence and every staged input.
- The response window is derived from the predictions, before anything is written.
- The working tree is HEAD in every file the freeze touches.
- Afterwards, these are release 20260930's byte for byte:
  - the references, the scenarios and their sidecars;
  - the predictions;
  - the serving configuration.
- The annotations and exclusions are the staged ones.
- The manifest changes only in the paths `MANIFEST_CHANGES` lists.

## Invariants (tests/test_release_20261006.py)

1. The frozen exclusion record is `build_exclusions(release 20260930's record, spec)`, byte for byte: the base records unchanged except the four edits, plus the eight ruled records before the audit's trailing scenario_023 record.
2. The adjudication record is release 20260930's plus eight entries. Each keeps the judge verdict the evidence file binds, and its reference basis is its record's unlisted input.
3. The committed annotation files rebuild byte for byte from release 20260930's: #197's ledger, then the release rewrites, then every adjudication.
4. References and predictions are release 20260930's.
5. Every model is scored on 1,920 outputs.
6. An independent re-aggregation of the payload's own rows reproduces every model's published exact rate. With the eight outputs scored again, it reproduces release 20260930's.
7. Properties (Hypothesis):
   - rewrites move only their own fields, and applying them twice changes nothing;
   - a rewrite of text the field does not hold is refused;
   - manifest leaf paths are empty exactly when two manifests are equal, and symmetric;
   - a change under an allowed prefix is never a problem;
   - the version description counts the records it is given.

## Publish order

1. Freeze, render, run the tests.
2. Check that the tag is free.
3. `gh release create dashboard-data-20261006 --target main --latest=false`, with `dashboard-data.json` (the staged `data-board46.json`) and `predictions.csv.gz` (the staged gzip, byte-identical to the frozen one). Download the asset and compare its sha256 with `app/src/data.artifact.json`.
4. Open the PR. CI's app job and Vercel download the asset.
5. Wait for green CI and an independent review, then squash-merge with `--match-head-commit`.
6. `gh release edit dashboard-data-20261006 --latest`. Then `gh api repos/PolicyEngine/policybench/releases/latest` must name it.
7. Check prod on policybench.org:
   - the snapshot chip and "46 Models";
   - the leaderboard scores and "1,920" scored outputs;
   - the excluded-outputs sentence;
   - /paper's response window (September 29);
   - the release note's page.
