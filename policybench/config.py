# policybench/config.py

NUM_RUNS_PER_SCENARIO = 10
PROGRAMS = ["eitc", "snap"]
MODELS = ["gpt-4o-mini", "gemini-1.5-flash"]

USE_CONCURRENCY = False  # if True, can run in parallel
MAX_PARALLEL_JOBS = 4
RANDOM_SEED = 42
