# Brief: independent review of the GPT-6.1 Sol release driver

Review, read-only, the release driver for adding GPT-6.1 Sol to PolicyBench release `dashboard-data-20260929` (45 models). The new release is additions-only: the references must not change, and all 45 incumbents' `modelStats` must come out byte-identical.

- Worktree: `/Users/maxghenis/PolicyEngine/policybench-wt/gpt61sol-driver`, branch `gpt61sol-driver`, HEAD 229730ba.
- Diff: `git diff origin/main..HEAD`. origin/main is d616e67c, release 20260929 as merged.
- Start by reading `docs/gpt61sol/design.md`, `scripts/finish_gpt61sol.py`, `scripts/freeze_gpt61sol.py`, `tests/test_finish_gpt61sol.py` and `tests/test_freeze_gpt61sol.py`.

Try to break it. Could any of these get through?
- a reference or exclusion change;
- incumbent drift;
- a stale or unbound judge verdict;
- a verdict from the wrong model or covering the wrong set of models;
- a dropped adjudication;
- a tag or roster mistake;
- a wrong pin: recompute every pin from the committed files;
- a test that cannot fail. Mutate the code in a temp copy (`mktemp -d` and `git worktree` or `git archive`), never in the worktree.

Python: `/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/.venv/bin/python`, with `OPENBLAS_NUM_THREADS=1 PYTHONPATH=<dir>`. The stage in `results/local/gpt61sol-v1` is live and another job is writing to it: read it, never write it.

First line of your answer: APPROVE or REQUEST CHANGES. Then list each finding with its severity (blocker, major or minor), its evidence (the commands and their output) and a fix.
