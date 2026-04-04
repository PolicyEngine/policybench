#!/usr/bin/env python3
"""Generate and optionally run a single-output diagnostic sidecar."""

from __future__ import annotations

import argparse
from pathlib import Path

from policybench.analysis import (
    analyze_no_tools,
    build_scenario_prompt_map,
    export_analysis,
    export_dashboard_data,
)
from policybench.config import MODELS, get_programs
from policybench.eval_no_tools import run_no_tools_single_output_eval
from policybench.ground_truth import calculate_ground_truth
from policybench.scenarios import (
    generate_scenarios,
    load_excluded_household_ids,
    scenario_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", choices=["us", "uk"], required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("-n", "--num-scenarios", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Restrict evaluation to one or more configured model names",
    )
    parser.add_argument(
        "--exclude-scenario-manifest",
        action="append",
        default=[],
        help="Existing scenario manifest whose sampled households should be excluded",
    )
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="Only generate the scenario manifest and ground truth",
    )
    parser.add_argument(
        "--app-data-output",
        default=None,
        help="Optional dashboard payload path to export after analysis",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    excluded_household_ids: set[int] = set()
    for manifest_path in args.exclude_scenario_manifest:
        excluded_household_ids |= load_excluded_household_ids(manifest_path)

    programs = get_programs(args.country)
    scenarios = generate_scenarios(
        n=args.num_scenarios,
        seed=args.seed,
        excluded_household_ids=excluded_household_ids or None,
        country=args.country,
    )

    manifest_path = output_dir / "scenarios.csv"
    ground_truth_path = output_dir / "ground_truth.csv"
    predictions_path = output_dir / "predictions.csv"
    analysis_dir = output_dir / "analysis"

    manifest = scenario_manifest(scenarios)
    manifest.to_csv(manifest_path, index=False)

    ground_truth = calculate_ground_truth(scenarios, programs=programs)
    ground_truth.to_csv(ground_truth_path, index=False)

    print(f"Scenario manifest saved to {manifest_path}")
    print(f"Ground truth saved to {ground_truth_path}")

    if args.skip_eval:
        return

    model_names = args.models or sorted(MODELS)
    unknown_models = sorted(set(model_names) - set(MODELS))
    if unknown_models:
        valid = ", ".join(sorted(MODELS))
        raise ValueError(
            f"Unknown model(s): {', '.join(unknown_models)}. Valid models: {valid}"
        )

    predictions = run_no_tools_single_output_eval(
        scenarios,
        models={name: MODELS[name] for name in model_names},
        programs=programs,
        output_path=str(predictions_path),
        include_explanations=True,
    )
    print(f"Predictions saved to {predictions_path}")

    analysis = analyze_no_tools(ground_truth, predictions)
    exported = export_analysis(analysis, analysis_dir)
    scenario_prompts = build_scenario_prompt_map(
        manifest,
        ground_truth["variable"].drop_duplicates().tolist(),
    )
    if args.app_data_output:
        dashboard_path = export_dashboard_data(
            ground_truth,
            predictions,
            analysis,
            manifest,
            args.app_data_output,
            scenario_prompts=scenario_prompts,
        )
        exported["dashboard_data"] = dashboard_path

    print("Exported artifacts:")
    for name, path in exported.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
