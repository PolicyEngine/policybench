# Brief: repin the GPT-6.1 Sol driver to release 20260929 as merged, then run `prepare`

Work in place in `/Users/maxghenis/PolicyEngine/policybench-wt/gpt61sol-driver` (branch `gpt61sol-driver`). Read the repo `CLAUDE.md`, `docs/gpt61sol/brief_driver.md` and `docs/gpt61sol/design.md` first.

The driver (`scripts/finish_gpt61sol.py`, `scripts/freeze_gpt61sol.py` and their tests) was built against PR #182's head `f7ced3b3`. After review, #182 changed before it merged:
- It excluded `scenario_023 head_medicaid_eligible` as an audit exclusion. That makes 56 exclusions (28 engine defect, 28 unlisted input) and 1,928 scored outputs.
- It rewrote the reference sidecar's reasons.
- It hardened `finish_adds0928.py`, adding `check_exclusions` and `audit_exclusions` in `reference_audit/2026-09-28/final_actions.json`.
- It merged main's #181 (provenance computed once per run).

It merged as `d616e67c` on origin/main, and release `dashboard-data-20260929` is now latest. The payload sha256 is `a5cb9989d78cb18d040fec2f1f5d0775df15b9b917ae99d883d8701b7fa480a7` (123,362,946 bytes).

## Do

1. **Merge.** Run `git fetch origin && git merge origin/main`. Resolve any conflicts; the driver files are new, so there should be few.
2. **Repin every base constant to the merged release, computing each value from the files now committed:**
   - `BASE_COMMIT = "d616e67c33b6f80dabf5cb7329f069f9a1de069d"`;
   - `BASE_SHA256`;
   - the reference-file hash table;
   - the counts: 45 base models, 56 exclusions, 1,928 scored, 1,984 outputs.

   Remove the "#182 head" placeholder comment. The no-reference-revision rule stays: the committed references must equal release 20260929's, byte for byte.

   The audit seed's prompts must still re-render byte-identically from the committed snapshot. The 023 case's prompt may have changed, since its adjudication and case note changed; handle this deliberately. A case whose prompt changed is re-judged. Re-check the grounding pin as well.
3. **Tests.** Update every test pin with a recomputed value, never a copied one. Run `tests/test_finish_gpt61sol.py`, `tests/test_freeze_gpt61sol.py`, `tests/test_finish_adds0928.py`, then `pytest -q -m "not slow"`, `ruff check .` and `ruff format --check .`. Only `tests/test_paper_results.py::test_frozen_roster_has_45_display_names_and_release_dates` may fail, because GPT-6.1 Sol is registered but not yet frozen.
4. **Commit** coherently. Each message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
5. **Run `prepare` on the real data**, exactly as `docs/gpt61sol/design.md` documents:
   - runs root `/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609` (the run is `gpt61sol/run`: 100/100, model gpt-6.1-sol);
   - audit seed `/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/results/local/adds0928-v3/audit`;
   - grounding `/Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit/grounding.csv`;
   - stage dir `results/local/gpt61sol-v1` in this worktree.

   Do NOT run `judge`, `triage`, `export` or the freeze.

   Report:
   - how many cases need judging (new, and re-judged because a prompt changed), with a few examples;
   - how many carry over;
   - GPT-6.1 Sol's staged exact rate and rank from the early export, if the driver produces one.

## Rules

- Python: `/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/.venv/bin/python`, run with `OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD`.
- Run heavy steps serially.
- Deletion: never delete anything you did not create in this task. Never `rm -rf` a shared directory or a glob. Put scratch files in a fresh `mktemp -d` and delete only that.
- Do not push, open PRs, upload, or call any model or provider API.
- **Final answer:**
  - every pin, old → new, with its source;
  - the commits;
  - the test and ruff results, verbatim;
  - the prepare report;
  - `git status`, which must be clean except for the git-ignored stage.
