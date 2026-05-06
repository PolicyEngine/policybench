"""Export full-run analysis and frontend payloads."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from policybench.analysis import (
    analyze_no_tools,
    build_dashboard_payload,
    build_global_dashboard_payload,
    build_scenario_prompt_map,
    export_analysis,
)


def load_predictions(country_dir: Path) -> pd.DataFrame:
    """Load a country run's predictions, preferring per-model CSVs when present."""
    by_model_dir = country_dir / "by_model"
    files = sorted(by_model_dir.glob("*.csv")) if by_model_dir.exists() else []
    predictions_path = country_dir / "predictions.csv"
    if files:
        predictions = pd.concat(
            (pd.read_csv(path) for path in files), ignore_index=True
        )
        predictions.to_csv(predictions_path, index=False)
        return predictions
    if predictions_path.exists():
        return pd.read_csv(predictions_path)
    raise FileNotFoundError(
        f"Expected at least one CSV in {by_model_dir} or {predictions_path}."
    )


def export_country(country_dir: Path) -> dict:
    """Write analysis artifacts and dashboard payload for one country run."""
    ground_truth_path = country_dir / "reference_outputs.csv"
    legacy_ground_truth_path = country_dir / "ground_truth.csv"
    scenarios_path = country_dir / "scenarios.csv"
    if not ground_truth_path.exists():
        if legacy_ground_truth_path.exists():
            ground_truth_path = legacy_ground_truth_path
        else:
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


def export_full_run(
    run_dir: str | Path,
    countries: Sequence[str] | None = None,
    app_data_output: str | Path = "app/src/data.json",
    skip_app_data: bool = False,
) -> dict:
    """Export per-country and combined frontend artifacts from a full run."""
    run_path = Path(run_dir)
    selected_countries = list(countries or ["us", "uk"])

    country_payloads = {
        country: export_country(run_path / country) for country in selected_countries
    }
    combined_payload = {
        "countries": country_payloads,
        "global": build_global_dashboard_payload(country_payloads),
    }

    run_payload_path = run_path / "data.json"
    run_payload_path.write_text(json.dumps(combined_payload), encoding="utf-8")
    print(f"Wrote {run_payload_path}")

    if not skip_app_data:
        app_data_path = Path(app_data_output)
        app_data_path.parent.mkdir(parents=True, exist_ok=True)
        app_data_path.write_text(json.dumps(combined_payload), encoding="utf-8")
        print(f"Wrote {app_data_path}")

    return combined_payload


def main() -> None:
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
    args = parser.parse_args()

    export_full_run(
        run_dir=args.run_dir,
        countries=args.countries,
        app_data_output=args.app_data_output,
        skip_app_data=args.skip_app_data,
    )


if __name__ == "__main__":
    main()
