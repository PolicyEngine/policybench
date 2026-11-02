# Brief: fix the GPT-6.1 Sol driver review findings, then export

Work in place in `/Users/maxghenis/PolicyEngine/policybench-wt/gpt61sol-driver` (branch `gpt61sol-driver`). Read the repo `CLAUDE.md` and `docs/gpt61sol/design.md` first.

An independent Opus review requested changes; its full text is in `/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/gpt61sol/driver_review.md`. The reviewer had no shell, so verify every finding by running code before you change anything. The judge and triage job's report is in `.../gpt61sol/judge_report.md`, and its outputs are in the stage `results/local/gpt61sol-v1`. It may have left a committed or untracked `scripts/restate_gpt61sol_adjudications.py` and its test; review and keep them, fixing finding 7.

Python: `/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/.venv/bin/python`, run with `OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD`.

## Fix, each with a test that fails before the fix and passes after

1. **Major: the adjudication record must not rewrite decisions it has no reason to touch.**
   - Export binds `prompt-changes.json` in `release-ready.json`.
   - `verify_adjudication_record` (freeze) and triage require each committed entry's non-judge fields to stay byte-identical, key order included.
   - Judge fields may change only for case ids in the bound `changed ∪ added` lists. Use the `JUDGE_FIELDS` set from the restate script as the one definition.
   - Replace `test_triage_may_restate_a_rejudged_class` with a pair: a re-judged case may be restated, and a rewrite of an incumbent-only case is refused.
2. **Major: every judged verdict is bound to its own bytes.**
   - For every non-parse-only case, require `verdict.meta.json`'s `verdict_sha256` to equal the digest of `verdict.json`, and require `prompt_sha256` to be present and to match `prompt.md`.
   - Cases that carry over from the seed must also keep `verdict.json` byte-identical to the seed's. Bind the seed digests in `stage.json` at prepare.
   - Add a mutation test: edit a carried-over verdict and it must show as pending or refused.
3. **Minor: stamp `prompt_sha256` on the new Opus 5.5 verdicts.** Stamp it in the sidecar after each judge pass, or in the runner. Require it for every verdict that names GPT-6.1 Sol. Apply it to the 134 existing new verdicts, and check that each stamped hash matches `prompt.md` as it is now.
4. **Minor: the freeze's baseline for dropped adjudications** must come from git at `BASE_COMMIT` (`base_commit_blob`), not from the working-tree file the freeze overwrites.
5. **Minor: the freeze's `verify_receipt`** must also check `base_tag == BASE_TAG` and `base_sha256 == BASE_SHA256`.
6. **Minor: local-only tests.** Commit a small digest of the seed (case id, prompt sha256, verdict sha256 for each judged case) and test the committed digest against the real seed when it is present. Say in the design table which checks can run only on this machine.
7. **Minor: the restate script** must verify the new record in memory before it writes anything.

## Then

- Re-run `judge` (validation only; nothing should be pending) and `triage`, so the stage satisfies the stricter gates.
- Run `export`. Report GPT-6.1 Sol's exact rate and rank, and confirm the no-drift gate passed for all 45 incumbents.
- Stop before the freeze.

## Rules

- Checks: `pytest -q -m "not slow"` must pass, except the expected frozen-roster test, plus the two driver test files including the slow ones. `ruff check .` and `ruff format --check .` must pass.
- Commit coherently. Each message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never delete anything you did not create. Never `rm -rf` a shared directory or a glob.
- Do not push, open PRs, upload, or call a provider API. The judge's Claude CLI, which uses this lane's subscription, is allowed only if a verdict really must be redone.
- Final answer: per finding, the commit (or a rebuttal with evidence); the export result; the test results, verbatim; and `git status`.

## Also from the judge/triage report (`.../gpt61sol/judge_report.md`; read it in full)

8. **Judge independence.**
   - Nine of the 134 new judges read the adjudication decision records while judging: 039 federal, 039 state, 042 state, 049 federal, 056 snap, 076 state, 091 state, 110 federal and 112 snap. A tenth (117 state) searched the repo. Eight read the live policyengine-us checkout.
   - Harden `scripts/run_audit_claude.sh` so each judge runs:
     - from a fresh empty directory outside the repo;
     - with file, search, web and shell tools disallowed (check the installed `claude --help` for the exact flags);
     - on this lane's own credentials. It must never fall back to the desktop login: 22 kept verdicts billed the desktop account. Refuse to run if the lane's config dir is not set, and record the account the call used in the sidecar if the CLI reports it.
   - Add a test for the command line the script builds.
   - Then find every new verdict whose judge transcript shows a file read, search or shell call, not only the ten above. Re-judge each with the hardened runner, restate its adjudication with the restate script, and re-run triage.
   - Report which verdicts changed.
9. **Published wording.**
   - Idaho 007 state: the new judge explanation calls the $4,811 zero bracket a model error, but the release's Idaho convention sets $4,811. The report also names out-of-date decision wording in 008 state refundable credits, 056 snap, 057 ssi and 067 ssi.
   - No published case note or row annotation may state something the record contradicts.
   - Re-judging with the hardened runner may resolve 007. If not, or for the stale decision wording, add a narrow mechanism: a stage file listing wording-only amendments (case id, field, old text, new text, reason) for re-judged cases only. Export binds that file, and finding 1's gate allows exactly the listed changes and nothing else. Test it both ways.
   - Never change a decision's class, exclusion status or scoring.
10. **Two scored decisions the re-judge disputes.** 008 state refundable credits: the judge calls it later law, but New Jersey's law passed June 30, before the July 3 freeze. 056 state refundable credits: the judge calls it an engine defect, but the affirmation rules that out. The decisions stand. Confirm the published case notes for them read correctly.

Do items 8 and 9 before export. The judge's Claude CLI is allowed for the re-judges.
