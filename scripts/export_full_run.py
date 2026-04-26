#!/usr/bin/env python3
"""Export full-run analysis and frontend payloads.

Expected layout:

    results/full_batch_v2_YYYYMMDD/
      us/
        ground_truth.csv
        scenarios.csv
        by_model/*.csv  # or predictions.csv
      uk/
        ground_truth.csv
        scenarios.csv
        by_model/*.csv  # or predictions.csv

The script writes per-country analysis, per-country dashboard payloads, a
combined run-level data.json, and optionally the app's data.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from policybench.analysis import (
    analyze_no_tools,
    build_dashboard_payload,
    build_global_dashboard_payload,
    build_scenario_prompt_map,
    export_analysis,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Full-run directory containing country subdirectories.",
    )
    parser.add_argument(
        "--country",
        action="append",
        dest="countries",
        default=None,
        help="Country code to export. Repeat to export multiple countries.",
    )
    parser.add_argument(
        "--app-data-output",
        default="app/src/data.json",
        help="Path for the combined frontend payload.",
    )
    parser.add_argument(
        "--skip-app-data",
        action="store_true",
        help="Only write the combined payload under the run directory.",
    )
    return parser.parse_args()


def load_predictions(country_dir: Path) -> pd.DataFrame:
    predictions_path = country_dir / "predictions.csv"
    if predictions_path.exists():
        return pd.read_csv(predictions_path)

    by_model_dir = country_dir / "by_model"
    files = sorted(by_model_dir.glob("*.csv")) if by_model_dir.exists() else []
    if not files:
        raise FileNotFoundError(
            f"Expected {predictions_path} or at least one CSV in {by_model_dir}."
        )

    predictions = pd.concat((pd.read_csv(path) for path in files), ignore_index=True)
    predictions.to_csv(predictions_path, index=False)
    return predictions


def export_country(country_dir: Path) -> dict:
    ground_truth_path = country_dir / "ground_truth.csv"
    scenarios_path = country_dir / "scenarios.csv"
    if not ground_truth_path.exists():
        raise FileNotFoundError(f"Missing {ground_truth_path}.")
    if not scenarios_path.exists():
        raise FileNotFoundError(f"Missing {scenarios_path}.")

    ground_truth = pd.read_csv(ground_truth_path)
    predictions = load_predictions(country_dir)
    scenarios = pd.read_csv(scenarios_path)

    analysis = analyze_no_tools(ground_truth, predictions)
    export_analysis(analysis, country_dir / "analysis")

    scenario_prompts = build_scenario_prompt_map(
        scenarios,
        ground_truth["variable"].drop_duplicates().tolist(),
    )
    payload = build_dashboard_payload(
        ground_truth,
        predictions,
        analysis,
        scenarios,
        scenario_prompts=scenario_prompts,
    )
    (country_dir / "data.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload


def main() -> None:
    args = parse_args()
    run_dir = Path(args.run_dir)
    countries = args.countries or ["us", "uk"]

    country_payloads = {
        country: export_country(run_dir / country) for country in countries
    }
    combined_payload = {
        "countries": country_payloads,
        "global": build_global_dashboard_payload(country_payloads),
    }

    run_payload_path = run_dir / "data.json"
    run_payload_path.write_text(json.dumps(combined_payload), encoding="utf-8")
    print(f"Wrote {run_payload_path}")

    if not args.skip_app_data:
        app_data_output = Path(args.app_data_output)
        app_data_output.parent.mkdir(parents=True, exist_ok=True)
        app_data_output.write_text(json.dumps(combined_payload), encoding="utf-8")
        print(f"Wrote {app_data_output}")


if __name__ == "__main__":
    main()
