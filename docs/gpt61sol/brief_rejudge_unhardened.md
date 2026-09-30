# Brief: re-judge the unhardened GPT-6.1 Sol verdicts with the hardened runner, then export again

Work in place in `/Users/maxghenis/PolicyEngine/policybench-wt/gpt61sol-driver` (branch `gpt61sol-driver`, HEAD e221b4ce). Read the repo `CLAUDE.md` and `docs/gpt61sol/design.md` first.

The previous fix job committed the review fixes and hardened `scripts/run_audit_claude.sh`: each judge now runs from an empty directory outside the repo, with tools disallowed, on the lane login only. It then re-judged 17 verdicts and exported. It was cancelled before it could write its report, but the worktree is clean and the stage `results/local/gpt61sol-v1` holds its export.

Of the 134 new verdicts in the stage, 117 still come from the old, unhardened runner: their sidecars have no `judge_isolation`, and `prompt_sha256_source` says the prompt binding was stamped from the transcript. A separate audit found that each of those 117 judge sessions ran inside the repo, with an injected workflow-authoring skill message in context. PolicyBench will publish every new verdict with one clean provenance, so re-judge all 117.

Python: `/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/.venv/bin/python`, run with `OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD`. Unset ANTHROPIC_API_KEY; judges must bill this lane's login only.

## Steps

1. List the 117 new verdicts whose sidecars lack `judge_isolation`, and check the count.
   - Do NOT touch carried-over verdicts. In particular, another session owns and will re-judge 086 federal_refundable_credits, 045 snap, 014 federal_refundable_credits, 015 federal_refundable_credits and 015 head_medicaid_eligible.
   - Move each of the 117 old verdicts aside into `rejected-verdicts/`, following the fix job's pattern.
2. Re-judge them with the hardened runner at width 4. Then run `--step judge`. Every new verdict must pass validation, with `judge_isolation` present, `claude-opus-5-5` served, `prompt_sha256` bound, and no hedging.
3. Check isolation from the transcripts: none of the 134 judge sessions may show a tool call or an injected skill or git-status message. Report what you checked.
4. Restate the adjudication records for re-judged cases that have one, with `scripts/restate_gpt61sol_adjudications.py`.
5. Re-check `wording-amendments.json` against the new text.
   - Each amendment must still apply exactly once and still be true.
   - Drop any a re-judge made unnecessary.
   - Add any that the new judge text requires. The Idaho 007 state rule applies: no published text may call the release's $4,811 convention a model error.
   - Never change a class, an exclusion or a score.
6. Run `--step triage`, then `--step export`. Report:
   - GPT-6.1 Sol's exact rate and rank;
   - that the no-drift gate passed for all 45 incumbents;
   - the class distribution of the 134 new verdicts, old against new, with counts of changed classes and changed flags;
   - any triage flag. If a flag needs a new decision, STOP and report it.
7. Stop before the freeze.

## Rules

- Checks: `pytest -q -m "not slow"` must pass, except the expected frozen-roster test, plus the two driver test files including the slow ones. `ruff check .` and `ruff format --check .` must pass.
- Commit tracked changes coherently. Each message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never delete anything you did not create. Never `rm -rf` a shared directory or a glob.
- Do not push, open PRs or upload.
- Write the final report to the `-o` path as you go. The previous job was cancelled before it wrote one.
