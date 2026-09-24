#!/bin/sh
# Run one fix sweep: run_one.sh <fix name>
# PB_WORKTREE names the branch checkout whose policybench code the sweep imports
# (2026-09-22/23: policybench-wt/opus55; 2026-09-24: policybench-wt/r33-20260922b).
WT="${PB_WORKTREE:-/Users/maxghenis/PolicyEngine/policybench-wt/r33-20260922b}"
cd /Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/sweep || exit 1
PYTHONPATH="$WT" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  ../.venv-pe1755/bin/python sweep.py --fix "fixes/$1.py" --out "out/$1.csv" > "out/$1.log" 2>&1
echo "$1 rc=$? $(tail -1 "out/$1.log")"
