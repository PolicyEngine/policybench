# Brief: judge and triage the GPT-6.1 Sol stage

Work in place in `/Users/maxghenis/PolicyEngine/policybench-wt/gpt61sol-driver` (branch `gpt61sol-driver`, HEAD 229730ba). Read the repo `CLAUDE.md` and `docs/gpt61sol/design.md` first.

`prepare` has already run into `results/local/gpt61sol-v1`. It found 134 cases that need Opus 5.5, every one because GPT-6.1 Sol answered wrong and joined it; 540 carry over. You run in a Claude subscription lane, so judge calls bill this lane's account. Never use ANTHROPIC_API_KEY: unset it if it is set.

Setup:

```bash
PB_PY=/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/.venv/bin/python
PB_STAGE="$PWD/results/local/gpt61sol-v1"
export OPENBLAS_NUM_THREADS=1 PYTHONPATH="$PWD"
unset ANTHROPIC_API_KEY
```

## Steps

1. **Judge at width 4.**
   - Run `AUDIT_MODEL=claude-opus-5-5 AUDIT_PARALLEL=4 AUDIT_PYTHON="$PB_PY" bash scripts/run_audit_claude.sh "$PB_STAGE/audit"`. Read that script first to confirm the arguments.
   - Then run `"$PB_PY" scripts/finish_gpt61sol.py --stage-dir "$PB_STAGE" --step judge`. It validates every verdict: exact model coverage, a hash-bound sidecar showing the served model `claude-opus-5-5`, and no hedging. It retries whatever is missing or invalid, one at a time.
   - If the judge step exits after three passes, investigate and resume. Do not weaken validation.
2. **Triage:** `"$PB_PY" scripts/finish_gpt61sol.py --stage-dir "$PB_STAGE" --step triage`.
   - About 54 of the 134 re-judged cases have adjudication records, 46 of them scoring exclusions. If a re-judge changes an adjudicated case's class, restate the new class in its staged record (`$PB_STAGE/publish/us_full_run_20260612_policyengine_4_16_1_populace/annotations/us_adjudications.json`), exactly as `design.md` and the 20260929 records did: the current judge class goes in, the replaced class moves to `judge_previous`, dated from its sha256-bound sidecar.
   - Keep the judge's exact class. Never invent a class or a decision to unblock triage.
   - Report any `reference-flags.csv` row that asks for a new decision (a reference defect or a new exclusion) and STOP: an exclusion that moves has no path in this release.
3. **Stop after triage passes.** Do not run export or the freeze.

## Rules

- Run heavy steps serially, apart from the judge width above.
- Deletion: never delete anything you did not create in this task. Never `rm -rf` a shared directory or a glob.
- Don't push, don't open PRs, and don't upload anything.
- Commit nothing unless you change tracked files. Stage outputs are git-ignored.

**Final answer:**
- the judge counts: judged, retried, and the served-model tally from the sidecars;
- the class distribution of the 134 new verdicts;
- every adjudication record you restated, with its old and new class and why;
- the triage output, verbatim;
- any flags you stopped on.
