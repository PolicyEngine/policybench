# tests/test_main.py
import pytest
import os
from policybench.main import run_benchmark


def test_run_benchmark_smoke():
    """
    A quick 'smoke test' to see if run_benchmark completes without error.
    We can test partial output but won't check correctness in detail.
    """
    # Potentially override config settings here if you want a short run
    # e.g. policybench.config.NUM_RUNS_PER_SCENARIO = 1

    run_benchmark()
    # Check that the CSV is created
    assert os.path.exists("benchmark_results/benchmark_output.csv")
