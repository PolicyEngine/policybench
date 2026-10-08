# Release dashboard-data-20261006: checkpoint draft (2026-10-06)

This is the workspace copy of the updated checkpoint. The central checkpoint at `~/chief-of-staff/state/policybench/CHECKPOINT-release-20261006.md` is outside this session's writable roots and has not been edited. Fill the final review, upload, PR, merge, production and cleanup results before copying this text there in an authorized environment.

## Workspace and Git state

- Assigned workspace: `/Users/maxghenis/PolicyEngine/policybench-wt/release-exclusions-batch`; branch `release-exclusions-batch`; use its `.venv` (Python 3.12.14).
- Resumed from `da8b4400d2f31bb9a26a6d34b4abc6bfb7691717`. The preserved salvage ref is `refs/subfleet-salvage/release-exclusions-batch-20261006T112718Z-a1`.
- Effective Git metadata is inside the workspace at `results/local/release-batch/git-metadata`. Its branch head and `refs/remotes/origin/release-exclusions-batch` are both `72a8a7d22847ac85aac022fc6fb98a9bad8d7d66` at this checkpoint.
- The original `.git` file still points to `/Users/maxghenis/PolicyEngine/policybench/.git/worktrees/release-exclusions-batch`. That central metadata is read-only here and still reports head `da8b4400d2f31bb9a26a6d34b4abc6bfb7691717`. A plain Git command therefore reports the old head. Use the workspace metadata for every Git operation; do not reset to the original pointer's head.

```sh
export GIT_DIR=/Users/maxghenis/PolicyEngine/policybench-wt/release-exclusions-batch/results/local/release-batch/git-metadata
export GIT_WORK_TREE=/Users/maxghenis/PolicyEngine/policybench-wt/release-exclusions-batch
```

The original external metadata and the central memory/checkpoint files have not been modified. Commits on the effective branch preserve the existing history.

## Completed steps 1–3

1. **Annotation rewrites:** `da8b4400` records the ledger and evidence. `docs/release_20261006/annotation_rewrites.json` contains 306 field rewrites across SALT, scenario_114, payroll and Louisiana, with four evidence files under `rewrite_evidence/`. Their score-related flags, values and classifications stay unchanged. Ledger SHA-256: `f268f8274445e1581ebc1ab4a8af48521d14418052c9fe5684a3f6aec0320836`.
2. **Fresh freeze and sensitivity:** `b959edbe` explicitly records d994 in the spec; `5435bab4` freezes the fresh export and sensitivity evidence. The fresh stage is `results/local/release-batch/dashboard-data-20261006-resume-da8b4400`. Trial-generated files were restored before prepare/export/freeze. The export has 46 models, 64 exclusions and 77 adjudications; eight outputs leave scoring for every model. The snapshot label stays `Snapshot 2026-09-30`.
3. **Content:** Preserved pin, paper and documentation edits were carried forward. `72a8a7d2` pins the October 6 release note to draft v2 contract PR #173, covers the eight excluded outputs and missing prompt facts, and documents the d994 hold. The note is `app/src/notes/2026-10-06-policybench-stops-scoring-eight-tax-outputs.json`. Its focused test passed: `docs/release_20261006/validation/release-note-test.txt`.

Fresh payload: `data-board46.json`, 127,218,158 bytes, SHA-256 `1780d2ec37f90b654265f8c7a191ba57f5ec5c4d28624bf9d2e2de8a48d2f871`. Intended tag: `dashboard-data-20261006`. Base: `dashboard-data-20260930`, commit `8b4c0ca146bb6f66deba6ce24009d49d70d92df2`, payload SHA-256 `d1cae7456cf91ab6fa04644a4d5d570e359522386a7c52f9645d5923bfc11258`.

Expected effects are reproduced in `docs/release_20261006/validation/effects.json`: GPT-6 Sol 95.003499→95.827859; Claude Opus 5.5 93.697490→95.051769; Claude Sonnet 5.5 #4 at 93.253086; GPT-6 Luna #5 at 93.020680. Every model gains 0.667874–1.354279 points, with 1,928→1,920 scored outputs. A different publication result must be explained before publishing.

## Current step 4: render and tests

- `ruff check .`, `ruff format --check .` and app lint passed; see `validation/static-checks.json` and the accompanying text logs.
- Paper rendering is running with an absolute `PYTHONPATH`. Quarto 1.9.36 is copied under `results/local/release-batch/runtime/quarto` so Darwin state/cache writes remain inside the workspace. Its runtime-only NotebookClient startup timeout is 600 seconds because cold kernel startup exceeded the installed 60-second default on the loaded host. These changes affect startup and writable paths, not cell execution or render options. Hashes and details are in `validation/render-environment.json`.
- The current render log has reached `Starting python3 kernel...Done` and execution of `index.quarto_ipynb`; successful HTML/PDF completion is not yet claimed. Follow `validation/render.txt`.
- Full pytest and Bun validation remain in progress. Partial/interrupted Python logs under `results/local/release-batch/` are diagnostic records, not passing full-suite evidence. `validation/bun-tests.txt` is an in-progress log until its final totals and exit status are recorded.
- After rendering succeeds, run `scripts/freeze_snapshot.py --rendered-only`, then retain completed pytest/Bun result files for the independent reviewer.

## Decisions and remaining work

- Authority remains Max's d963, d974, d972 and d831, and Louisiana's $12,835 ruling. Louisiana wording-only case-note edits may ship.
- **PR #192's documentation sentence remains HELD under d994.** As written it changes five scored references: Idaho scenario_076; SNAP scenario_008/038/109; Maryland scenario_068 under the IRS reading. The fresh release retains those references and the existing convention.
- Finish step 4, then independent review via `subfleet run --task review --tier standard`; cite the completed test result files because read-only review lanes have no shell. Address every finding and obtain approval of the exact head.
- `subfleet status` has timed out in the daemon's expensive capacity path, but `subfleet runs --last 1 --json` succeeded. Use a workspace prompt file (`-p`), report path (`-o`) and stable request ID. Monitor with `runs --request-id`; an unanswered submit is retried idempotently with a 60-second deadline.
- Upload the payload with `gh release create dashboard-data-20261006 --latest=false`, download it and verify the full SHA-256 above.
- Open the PR, wait for `gh pr checks` exit 0 and `MERGEABLE`, and merge with `--squash --match-head-commit` only for the head the reviewer approved. Then mark the release latest and verify production scores, 1,920 outputs per model and the release note.
- Close folded PRs #188/#191/#192/#193/#194/#197 with pointers, retaining the d994 hold in #192; comment on #190 and #196. Judge-isolation-20260930b remains outside this release; note its new base in the handoff.
- Fill final tag/upload verification, PR URL, approved head, merge commit, production evidence and cleanup results here and in the memory draft before updating the central files.
