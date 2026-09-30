# Brief: finish the GPT-6.1 Sol stage after the re-judge (restate, amendments, triage, export)

Work in place in `/Users/maxghenis/PolicyEngine/policybench-wt/gpt61sol-driver` (branch `gpt61sol-driver`). Read the repo `CLAUDE.md`, `docs/gpt61sol/design.md`, `docs/gpt61sol/brief_rejudge_unhardened.md` and the progress log `/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/gpt61sol/rejudge_report.md`.

State: all 134 new verdicts in `results/local/gpt61sol-v1` now come from the hardened runner.
- 17 ran on subfleet lane claude-10.
- The trial, `us__scenario_000__federal_income_tax_before_refundable_credits`, ran on Max's first setup-token login.
- The other 116 ran on his second setup-token login. Its sidecars declare `claude setup-token login (token sha256 6a6daf56361b), Max 2026-09-30`.

The old verdicts are in `rejected-verdicts/`.

If the runner stopped early on a usage limit, some to-do cases have no verdict. Check the tail of `.../gpt61sol/rejudge_run2.log` and the count of present verdicts. In that case:
- Restore those cases' old verdicts from `rejected-verdicts/`. Take the entry whose `reason.txt` is the unhardened-judge reason with today's timestamp.
- Record exactly which verdicts are old and which are new.
- Continue. Max agreed to ship a disclosed mix rather than wait.

Python: `/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/.venv/bin/python`, run with `OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD`. Make no judge calls. The judging is done, and this brief needs no model calls.

## Steps

1. **Validate.** Every present verdict must pass the driver's `validate_verdicts`. Every new one must carry `judge_isolation`, with `judge_effort` xhigh, Opus 5.5 served, and `prompt_sha256` bound. Read at least 10 of the new transcripts (`claude.transcript.jsonl` beside each verdict). Each must show exactly one tool call, `StructuredOutput`, and no userEmail, credential_org, skill or git context.
2. **Restate** the adjudication records of re-judged cases that have one, with `scripts/restate_gpt61sol_adjudications.py`.
3. **Rebuild the wording amendments** for the re-judged cases in `wording-amendments.json`: 288 in 11 cases (005, 007, 053 and 099 state income tax; 008 payroll tax; 008 state refundable credits; 020 federal income tax; 023, 080 and 100 snap; 067 ssi).
   - Apply the same rules that made them: `docs/gpt61sol/design.md`, the amendment policy, and `finish_gpt61sol.py load_amendments`.
   - Each amendment must match its new text exactly once and must be true.
   - Drop the ones the new text makes unnecessary. Add any the new text needs. No published case note or row annotation may state something the record contradicts. For Idaho 007, no text may call the release's $4,811 convention a model error.
   - Never change a class, an exclusion or a score.
   - Report the before and after counts per case.
4. **Triage:** `--step triage`. If a flag needs a new decision, STOP and report it.
5. **Export:** `--step export`. Report:
   - GPT-6.1 Sol's exact rate and rank;
   - the no-drift result for all 45 incumbents;
   - the new payload sha256;
   - old against new class distribution for the 134, with the number of changed classes and changed flags.
6. **Checks.** Run `pytest -q -m "not slow"`; only the frozen-roster test may fail. Run the two driver test files including the slow tests, and `tests/test_run_audit_claude.py`. Run `ruff check .` and `ruff format --check .`.
7. **Commit** tracked changes coherently. Each message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Append each step's result to the progress log as you go.

## Rules

- Never delete anything you did not create. Never `rm -rf` a shared directory or a glob.
- Don't push, open PRs or upload.
- Stop before the freeze.
- Final answer: everything asked for in steps 1–6, and `git status`.
