import random
import statistics
import csv
import os

# from concurrent.futures import ProcessPoolExecutor, as_completed  # optional concurrency
from typing import List

from policybench import config
from policybench.households import generate_scenarios
from policybench.policyengine_api import compute_ground_truth
from policybench.llm_estimator import estimate_program_value


def run_benchmark():
    """Run a multi-scenario, multi-model, multi-program benchmark, storing results to CSV."""
    random.seed(config.RANDOM_SEED)

    if not os.path.exists("benchmark_results"):
        os.mkdir("benchmark_results")

    # Create random scenarios
    scenarios = generate_scenarios(num_scenarios=5, year=2025)

    output_csv = os.path.join("benchmark_results", "benchmark_output.csv")
    headers = [
        "program",
        "model",
        "scenario_index",
        "ground_truth",
        "llm_estimates",
        "llm_raw_responses",
        "mse",
        "avg_abs_error",
        "std_dev",
        "num_valid_runs",
    ]

    with open(output_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        # Possibly run concurrency logic here if USE_CONCURRENCY:
        # if config.USE_CONCURRENCY:
        #     with ProcessPoolExecutor(max_workers=config.MAX_PARALLEL_JOBS) as executor:
        #         futures = []
        #         ...
        # else:
        #     (sequential loop as below)

        for program in config.PROGRAMS:
            for scenario_idx, scenario in enumerate(scenarios):
                ground_truth = compute_ground_truth(program, scenario)
                for model_name in config.MODELS:
                    # Each call returns a list of (parsed_val, raw_text)
                    run_outputs = estimate_program_value(
                        program=program,
                        scenario=scenario,
                        model_name=model_name,
                        n_runs=config.NUM_RUNS_PER_SCENARIO,
                    )

                    # separate into numeric and raw
                    numeric_values = []
                    raw_texts = []
                    for val, txt in run_outputs:
                        raw_texts.append(
                            str(txt)[:200]
                        )  # store up to 200 chars for debug
                        if val is not None:
                            numeric_values.append(val)

                    if len(numeric_values) == 0:
                        row = [
                            program,
                            model_name,
                            scenario_idx,
                            f"{ground_truth:.2f}",
                            "all_failed",
                            ";".join(raw_texts),
                            "NA",
                            "NA",
                            "NA",
                            0,
                        ]
                        writer.writerow(row)
                        print(
                            f"{program} | {model_name} | scenario#{scenario_idx} => all parse failures. "
                            f"Ground truth={ground_truth:.2f}"
                        )
                        continue

                    # Stats
                    squared_errors = [(v - ground_truth) ** 2 for v in numeric_values]
                    mse = statistics.mean(squared_errors)
                    abs_errors = [abs(v - ground_truth) for v in numeric_values]
                    avg_abs_err = statistics.mean(abs_errors)
                    std_dev = (
                        statistics.pstdev(numeric_values)
                        if len(numeric_values) > 1
                        else 0
                    )

                    row = [
                        program,
                        model_name,
                        scenario_idx,
                        f"{ground_truth:.2f}",
                        ";".join(str(x) for x in numeric_values),
                        ";".join(raw_texts),
                        f"{mse:.2f}",
                        f"{avg_abs_err:.2f}",
                        f"{std_dev:.2f}",
                        len(numeric_values),
                    ]
                    writer.writerow(row)

                    print(
                        f"{program.upper()} | {model_name} | scenario#{scenario_idx} => "
                        f"MSE={mse:.2f}, avgAbsErr={avg_abs_err:.2f}, validRuns={len(numeric_values)}, "
                        f"groundTruth={ground_truth:.2f}"
                    )

    print(f"\nBenchmark complete! Results written to {output_csv}.\n")


# If you wish, you can add concurrency with function calls, etc.
# But the main approach above should suffice for now.
