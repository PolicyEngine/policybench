# Brief: the GPT-6.1 Sol additions driver

> Superseded base (2026-09-29): the values below are PR #182's head. #182 changed
> after review and merged as `d616e67c`; the driver now pins that release (56
> exclusions, 1,928 scored, payload `a5cb9989…`). See `design.md` and
> `brief_repin_prepare.md`.

Work in this worktree (branch `add-gpt-6.1-sol`, from the head of PolicyEngine/policybench#182). Read the repository's `CLAUDE.md` first. Then read `scripts/finish_adds0928.py`, `scripts/freeze_adds0928.py`, `tests/test_finish_adds0928.py`, the freeze script's tests, and `docs/adds0928/stage2_design.md`.

## What the release is

PolicyBench is adding one model, GPT-6.1 Sol (`gpt-6.1-sol`, registry key `gpt-6.1-sol`, run slug `gpt61sol`), to the 45-model board of release `dashboard-data-20260929`. That release is PR #182, which is being merged now. The references do not change. Every one of the 45 incumbents' `modelStats` must come out byte-identical.

The base (read these from this worktree; they equal #182's head):

| Item | Value |
|---|---|
| `app/src/data.artifact.json` tag | `dashboard-data-20260929` |
| Payload sha256 | `d146473d9bd7776638c59a0a20774dbe9026d8bcee0f2201e114146609ddf246` (123,324,948 bytes) |
| Models | 45 |
| Outputs | 1,984 (100 households); 1,929 scored, 55 excluded |
| `reference_outputs.csv` sha256 | `e8bbba8fd3e90f78e7c0e83df06227bc1c94563e92f7405fe12be853a30b2466` |
| `reference_outputs.csv.meta.json` | `5469664726adef3675f4cb4504021bd5c24c8acbfa00b21d943854cd84f14bda` |
| `reference_exclusions.json` | `ae28ade59705e6314f4d1b5fbd906ec58af0d503e39a59a7e13b597679676f67` |
| `scenarios.csv` | `71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a` |
| `scenarios.csv.meta.json` | `03a66e90b86e9bd0cc77f27520784bd581777762f749675dc716e24c1b8eaebb` |

Recompute every hash yourself from the files in `paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/`, and stop if any differs from this table.

## Deliverables

1. **`scripts/finish_gpt61sol.py`**, adapted from `finish_adds0928.py`, with the same steps (`prepare`, `judge`, `triage`, `export`) and the same `--early`/`--partial` rehearsal.
   - `MODELS = {"gpt61sol": "gpt-6.1-sol"}`, and 46 models after the fold.
   - `BASE_TAG = "dashboard-data-20260929"` with the sha above. Require 45 base models and 55 exclusions.
   - Keep `RELEASE_TAG` as one constant. Set it to `"dashboard-data-20260930"`. The lead may change it at freeze time, so nothing else may hard-code the tag.
   - **No reference revision.** Remove `reference_revision`, `replay_base_references` and the drift report.
     - Pin the five reference files above in a `BASE_REFERENCE_SHA256`-style table.
     - Require the committed files to match their pins in `resolve_base` and again in `export`.
     - Export must require zero incumbent `modelStats` drift: all 45, with nothing tolerated. Keep the Fable 5 historical-usage carry-over and the zero-cost Ox Alpha handling if the exporter still needs them; read why they exist in `stage2_design.md` and the code first.
   - **After the freeze,** the working-tree snapshot is the new release, so a re-export must read the base payload from git.
     - Keep `base_commit_blob` and `resolve_live_base`, with `BASE_COMMIT` pointing at the commit whose tree holds release 20260929.
     - Set `BASE_COMMIT = "f7ced3b37643ecfdb90ec383339d0244b7017bbb"` (#182's head) with the comment `# PR #182 head; the lead repoints this to its merge commit on main`. The lead will replace it after the merge.
   - Seed the audit from the 20260929 stage: `--audit-seed /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/results/local/adds0928-v3/audit`. Its grounding comes from wherever `finish_adds0928.py` read it; trace this through the code and the stage's `stage.json`, and document the exact prepare command in the design doc.
     - Carried-over verdicts must stay bound to their prompt sha256, as now.
     - Any case whose prompt changes because GPT-6.1 Sol's answer joins it must be re-judged.
     - The judge must cover all 46 models in a case.
2. **`scripts/freeze_gpt61sol.py`**, adapted from `freeze_adds0928.py`. `NEW_MODELS` is GPT-6.1 Sol only, and it keeps the treatment validation.
   - The reference sidecar, exclusions and adjudications must not change unless triage records an adjudication.
   - Drop the manifest pin catch-up for a reference revision; there is none.
3. **Tests.**
   - Add `tests/test_finish_gpt61sol.py` and a freeze test, adapted from the existing ones, with synthetic data where the originals use it.
   - Include: the 45-incumbent no-drift gate refuses any change; a reference file that misses its pin is refused; incomplete or stopped runs are refused; the wrong model in a run state is refused; `base_commit_blob` names a missing commit.
   - Where a property holds for all inputs, add a Hypothesis test. For example, the fold keeps every incumbent row byte-identical and adds exactly 1,984 rows for the new model with the reference key set. `hypothesis` is a dev dependency.
   - The existing `finish_adds0928`/`freeze_adds0928` tests must keep passing unchanged.
4. **`docs/gpt61sol/design.md`**, short:
   - what the release is and what the gates enforce;
   - the exact command sequence (prepare, judge, triage, export, freeze dry-run, freeze, paper render, `freeze_snapshot.py --rendered-only`), with the real paths:
     - runs root `/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609`;
     - run `gpt61sol/run`;
     - stage dir `results/local/gpt61sol-v1` in this worktree.

## Rules

- Do not run `prepare`, `judge`, `triage`, `export` or the freeze against real data. Do not touch `results/`, the snapshot, the references, the annotations or the payload pointer. The lead runs the pipeline once GPT-6.1 Sol's run finishes.
- Use the Python at `/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/.venv/bin/python`, which has policyengine-us 2.15.17 and hypothesis. Run with `OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD`, serially; the machine is shared.
- The frozen-roster test `tests/test_paper_results.py::test_frozen_roster_has_45_display_names_and_release_dates` fails on this branch until the refreeze. That is expected; leave it.
- Before you finish, run `ruff check .`, `ruff format --check .` and `pytest -q -m "not slow"`. Report every failure other than the one above.
- Make coherent commits, each message ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push, open PRs, upload anything, or call any model API.
- Final answer: the files you added and changed, the gates with the tests that pin each one, the exact pipeline commands, and the test results.
