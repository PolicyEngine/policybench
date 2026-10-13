# Release dashboard-data-20261013b: re-judge five carried-over verdicts

## What the release is

A 2026-09-30 audit bound every published judge verdict to the transcript that produced it ([the report](../judge_isolation_2026-09-30/REPORT.md)). Five verdicts cannot be presented as independent of the decisions published beside them. Every release since has carried them over unchanged; in release `dashboard-data-20261013` they still have the verdict and prompt hashes the audit recorded.

| Case | Why it is re-judged |
|---|---|
| `086 federal_refundable_credits` | Its 2026-09-05 judge launched a Workflow whose agents searched the repo and read this case's earlier published case note and row annotations. |
| `045 snap` | Its 2026-09-24 judge ran in a git checkout. The checkout's git status, injected into the judge's context, named this case's r33 exclusion and fix. |
| `014 federal_refundable_credits`, `015 federal_refundable_credits`, `015 head_medicaid_eligible` | No transcript holds the published verdict's text. |

This release re-judges those five on judge template v2 with the isolated runner and changes nothing else:

- No model, answer, reference, exclusion or adjudication changes.
- Every section of the payload except `scenarioPredictions` is byte-identical to release 20261013's. That includes every model's statistics, the program statistics and the heatmap.
- Inside `scenarioPredictions`, only the five cases' annotation fields change.
- No decision, exclusion or wording amendment rests on any of the five, so the release rules nothing.

The driver is `scripts/release_20261013b.py`, modelled on `scripts/release_20261006.py`, the last release with no new model.

## The base and the seed

| Item | Value |
|---|---|
| Base tag, payload sha256 | `dashboard-data-20261013`, `aef5dc73…7477` (130,988,798 bytes) |
| `BASE_COMMIT` | `bc305793…`, the squash merge of PR #217 on main (2026-10-13) |
| Models, exclusions, adjudications | 48, 49 and 61, all unchanged |
| Grounding | `b1e4a9bc…b55c`, the one release 20261013's prompts were rendered with |

The bundle (references, exclusions, predictions and annotations) is read from git at `BASE_COMMIT`, so no archived stage is needed.

The audit seed is release 20261013's judged tree of 677 cases. Its stage was removed with its worktree; the tree was kept at `~/reviews/policybench-muse-wonder/stage-audit-20261013`. `prepare` accepts a seed only if each case's prompt and verdict hash to what the base commit records. That record is `docs/musewonder/seed_digest.csv`, overlaid with the 151 cases `docs/musewonder/judge_provenance.json` lists as re-judged.

## Judge template v2

The five published verdicts were judged on template v1. A re-opened case renders on v2 (PR #210), which drops v1's claim that the reference pipeline survived an adversarial review. `prepare` sets the five verdicts and their v1 prompts aside and renders the five through `policybench.audit.prepare_audit` with `template_version=2`. It then requires each new prompt to be the old one with only the header replaced, so the case each judge reads is the case its replaced verdict judged.

## Judging

Each of the five is judged by Claude Opus 5.5 through `scripts/run_audit_claude.sh`. The runner starts each judge in an empty directory outside any git repository, with no tools, an allowlisted environment, no user settings and a token login, at effort xhigh.

The login is `pb-judge`, the setup-token login Max opted into for judging on 2026-09-30. Releases 20261010 and 20261013 used the same login. Its config directory is `~/.policybench-judge/pb-judge-config`; it is never the desktop login. `docs/release_20261013b/judge_provenance.json` records each verdict's hashes, account group, effort, template version and time, in the form of `docs/musewonder/judge_provenance.json`.

## Wording review

The five verdicts write 26 published texts: five case notes and 21 model annotations. An independent reviewer (Claude Opus 5.5, with no part in the release) read each against its case's prompt and against policyengine-us 2.41.0's code and parameters, and reported every statement the record contradicts. Each reported correction was then checked again against the engine. For scenario_015's Medicaid pathway that check was a calculation of the household: PolicyEngine does not count the head as disabled, because earnings exceed SSI's substantial gainful activity limit; its income test passes; and its asset test fails.

Nine corrections are applied as listed wording amendments (`docs/release_20261013b/wording_amendments.json`), each with the text it replaces, the replacement and the evidence:

- four in scenario_015's Medicaid case note and one in a model annotation there, which described Indiana's disability pathway and the engine's handling of it loosely or as a general fact about PolicyEngine;
- one each in a scenario_045 SNAP annotation and a scenario_086 annotation, which misreported what the model's reasoning said;
- one each in the scenario_086 and scenario_015 federal refundable credits case notes, which overstated a count and a rule's scope.

One reported point is left as written: SNAP's "about 232% of the guideline" holds for January to September and is 227% from October, and both fail both limits.

`collect` applies each amendment only if its old text occurs exactly once in a re-judged case's note or annotation. An amendment cannot name another case, a class or a flag. The committed record `annotations/.../us_wording-amendments.json` is release 20261013's with these nine appended.

## What the gates enforce

Each step refuses with `SystemExit` before it writes anything outside the stage. Tests are in `tests/test_release_20261013b.py`.

| Gate | Where |
|---|---|
| The base commit's pointer and payload are release 20261013's. | `prepare`, `base_payload` |
| The seed is release 20261013's judged tree, case for case. Each of the five has the verdict and prompt the audit examined. | `prepare`, `base_seed` |
| No decision, exclusion or wording amendment rests on any of the five. | `prepare` |
| The five verdicts, their sidecars, logs and v1 prompts are set aside in `replaced-verdicts/<case>/published/` with the reason, never deleted. `stage.json` pins everything set aside, and every later step re-checks it. | `set_aside`, `load_stage` |
| Rendering the five on v2 changes no other case: the staged `cases.jsonl` and `schema.json` are the seed's, and every carried verdict, sidecar and prompt keeps its bytes. | `prepare`, `validate` |
| Each new verdict satisfies the schema and names exactly its case's wrong models. Its sidecar binds the verdict and the v2 prompt and records Opus 5.5 (requested and reported), a judging time, the isolated runner, a token login and a declared account. No text is hedged. | `case_problems` |
| Each new verdict's transcript passes the current release driver's checks (`finish_musewonder.transcript_problems`): one user message that is exactly the prompt, one accepted structured answer that is exactly the verdict, no tool call, no account data, an empty session context and no git working directory. Every event must also carry the sidecar's session id. | `case_problems`, `session_problems` |
| A verdict that fails is set aside with the reasons and the case is judged again, up to three rounds. A round the runner ends without a new verdict stops the step, because the login cannot judge. | `judge` |
| A re-judge that flags the reference, or leaves a scored row outside `llm_error`, `parse_contract_failure` and `budget_exhausted_at_ceiling`, stops `collect`. That is a new reference question for Max. | `collect` |
| A wording amendment names one of the five cases and its case note or one model's annotation, and replaces text found exactly once there. The committed amendments record is release 20261013's with this release's appended. | `load_amendments`, `apply_amendments`, `committed_amendments` |
| The annotation files are release 20261013's committed bytes with only the five cases' records replaced. Records compare as text, field by field. Within the five, no record is added, dropped or reordered, and only the columns a verdict decides may change. The annotations directory holds exactly the expected files. | `splice_annotations`, `annotation_changes`, `verify_annotations` |
| Two exports of the stage give the same bytes. Every payload section but `scenarioPredictions` equals the base's. Inside it, only the five cases' `annotation`, `failureSource`, `failureSubtype`, `caseAnnotation`, `caseFailureSources` and `caseFailureSubtypes` differ. | `export`, `verify_payload`, `allowed_path` |
| The receipt binds the payload, the base, the judge provenance, the next seed digest, every export input and each re-judge's verdict, sidecar, prompt and transcript. The freeze refuses a receipt that binds less, or anything changed since export. | `export`, `verify_receipt` |
| Before it writes, the freeze requires the working tree to be release 20261013's in the manifest, the pointer, the version registry, the serving configuration, the frozen references and predictions, and every annotation file. | `freeze` |
| After it writes, the annotations directory holds exactly the committed files, the serving configuration, version registry, references, exclusions and predictions are unchanged, and the manifest differs from release 20261013's only in the two annotation hashes, the judge provenance, the dashboard artifact, the payload's two hashes and the rendered paper. | `freeze`, `manifest_problems` |

## Commands

```bash
export OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
PB_STAGE=results/local/release-20261013b

.venv/bin/python scripts/release_20261013b.py prepare --stage "$PB_STAGE" \
  --audit-seed ~/reviews/policybench-muse-wonder/stage-audit-20261013 \
  --grounding /Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit/grounding.csv

CLAUDE_CONFIG_DIR="$HOME/.policybench-judge/pb-judge-config" \
  CLAUDE_CODE_OAUTH_TOKEN="$(agent-secret get CLAUDE_CODE_OAUTH_TOKEN pb-judge)" \
  AUDIT_ACCOUNT="claude setup-token login (token sha256 6a6daf56361b), Max 2026-09-30" \
  .venv/bin/python scripts/release_20261013b.py judge --stage "$PB_STAGE"

.venv/bin/python scripts/release_20261013b.py collect --stage "$PB_STAGE"
.venv/bin/python scripts/release_20261013b.py export --stage "$PB_STAGE"
.venv/bin/python scripts/release_20261013b.py freeze --stage "$PB_STAGE" --dry-run
.venv/bin/python scripts/release_20261013b.py freeze --stage "$PB_STAGE"
```

`collect` applies `docs/release_20261013b/wording_amendments.json`. It also writes `docs/release_20261013b/judge_provenance.json` and `docs/release_20261013b/seed_digest.csv`, the prompt and verdict hashes of all 677 judged cases in this release's tree. The next release takes that tree as its audit seed.

The freeze is a local build and uploads nothing. The release assets are `<stage>/predictions.csv.gz` and the staged payload renamed to `dashboard-data.json`, under tag `dashboard-data-20261013b`. After review and green CI, create the release, verify the downloaded sha256 against the pointer, and then merge.
