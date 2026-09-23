#!/bin/sh
# Run one fix sweep: run_one.sh <fix name>
cd /Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/sweep || exit 1
PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/opus55 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  ../.venv-pe1755/bin/python sweep.py --fix "fixes/$1.py" --out "out/$1.csv" > "out/$1.log" 2>&1
echo "$1 rc=$? $(tail -1 "out/$1.log")"
