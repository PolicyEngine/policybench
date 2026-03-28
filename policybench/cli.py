"""CLI entry point for PolicyBench."""

import argparse
import sys
from pathlib import Path

from policybench.config import MODELS


def _ensure_parent_dir(output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)


def _parse_models(selected: list[str] | None) -> dict[str, str]:
    if not selected:
        return MODELS

    unknown = [name for name in selected if name not in MODELS]
    if unknown:
        raise SystemExit(
            f"Unknown model(s): {', '.join(sorted(unknown))}. "
            f"Valid choices: {', '.join(MODELS)}"
        )
    return {name: MODELS[name] for name in selected}


def _slice_scenarios(scenarios: list, start: int, end: int | None) -> list:
    if start < 0:
        raise SystemExit("--scenario-start must be >= 0")
    if end is not None and end < start:
        raise SystemExit("--scenario-end must be >= --scenario-start")
    return scenarios[start:end]


def main():
    parser = argparse.ArgumentParser(description="PolicyBench benchmark runner")
    subparsers = parser.add_subparsers(dest="command")

    # Ground truth
    gt_parser = subparsers.add_parser(
        "ground-truth", help="Generate ground truth from PolicyEngine-US"
    )
    gt_parser.add_argument("-o", "--output", default="results/ground_truth.csv")
    gt_parser.add_argument("-n", "--num-scenarios", type=int, default=100)
    gt_parser.add_argument("--seed", type=int, default=42)
    gt_parser.add_argument(
        "--scenario-manifest-output",
        default="results/scenarios.csv",
        help="CSV file for exported scenario metadata",
    )

    # Eval no tools
    nt_parser = subparsers.add_parser("eval-no-tools", help="Run AI-alone evaluation")
    nt_parser.add_argument("-o", "--output", default="results/no_tools/predictions.csv")
    nt_parser.add_argument("-n", "--num-scenarios", type=int, default=100)
    nt_parser.add_argument("--seed", type=int, default=42)
    nt_parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Restrict evaluation to one or more configured model names",
    )
    nt_parser.add_argument(
        "--scenario-start",
        type=int,
        default=0,
        help="Inclusive scenario index to start from",
    )
    nt_parser.add_argument(
        "--scenario-end",
        type=int,
        default=None,
        help="Exclusive scenario index to stop at",
    )

    # Eval no tools repeated
    ntr_parser = subparsers.add_parser(
        "eval-no-tools-repeated",
        help="Run repeated AI-alone evaluations on a fixed scenario set",
    )
    ntr_parser.add_argument(
        "-o",
        "--output-dir",
        default="results/no_tools/runs",
        help="Directory for per-run prediction CSVs",
    )
    ntr_parser.add_argument("-n", "--num-scenarios", type=int, default=100)
    ntr_parser.add_argument("--seed", type=int, default=42)
    ntr_parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Number of repeated benchmark runs on the same sampled households",
    )
    ntr_parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Restrict evaluation to one or more configured model names",
    )
    ntr_parser.add_argument(
        "--scenario-start",
        type=int,
        default=0,
        help="Inclusive scenario index to start from",
    )
    ntr_parser.add_argument(
        "--scenario-end",
        type=int,
        default=None,
        help="Exclusive scenario index to stop at",
    )

    # Analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyze AI-alone results")
    analyze_parser.add_argument("-g", "--ground-truth", default="results/ground_truth.csv")
    analyze_parser.add_argument(
        "-p", "--predictions", default="results/no_tools/predictions.csv"
    )
    analyze_parser.add_argument(
        "-s",
        "--scenario-manifest",
        default="results/scenarios.csv",
        help="CSV file with scenario metadata for dashboard export",
    )
    analyze_parser.add_argument(
        "-o",
        "--output-dir",
        default="results/analysis",
        help="Directory for exported analysis artifacts",
    )
    analyze_parser.add_argument(
        "--app-data-output",
        default="app/src/data.json",
        help="Frontend dashboard payload path",
    )
    analyze_parser.add_argument(
        "--runs-dir",
        default=None,
        help="Optional directory of repeated-run CSVs for stability analysis",
    )

    args = parser.parse_args()

    # Enable disk cache for all LLM calls
    if args.command in {"eval-no-tools", "eval-no-tools-repeated"}:
        from policybench.cache import enable_cache

        enable_cache()

    if args.command == "ground-truth":
        from policybench.ground_truth import calculate_ground_truth
        from policybench.scenarios import generate_scenarios, scenario_manifest

        scenarios = generate_scenarios(n=args.num_scenarios, seed=args.seed)
        df = calculate_ground_truth(scenarios)
        _ensure_parent_dir(args.output)
        df.to_csv(args.output, index=False)
        _ensure_parent_dir(args.scenario_manifest_output)
        scenario_manifest(scenarios).to_csv(args.scenario_manifest_output, index=False)
        print(f"Ground truth saved to {args.output}")
        print(f"Scenario manifest saved to {args.scenario_manifest_output}")

    elif args.command == "eval-no-tools":
        from policybench.eval_no_tools import run_no_tools_eval
        from policybench.scenarios import generate_scenarios

        scenarios = generate_scenarios(n=args.num_scenarios, seed=args.seed)
        scenarios = _slice_scenarios(scenarios, args.scenario_start, args.scenario_end)
        models = _parse_models(args.models)
        _ensure_parent_dir(args.output)
        df = run_no_tools_eval(scenarios, models=models, output_path=args.output)
        df.to_csv(args.output, index=False)
        print(f"No-tools predictions saved to {args.output}")

    elif args.command == "eval-no-tools-repeated":
        from policybench.eval_no_tools import run_repeated_no_tools_eval
        from policybench.scenarios import generate_scenarios

        scenarios = generate_scenarios(n=args.num_scenarios, seed=args.seed)
        scenarios = _slice_scenarios(scenarios, args.scenario_start, args.scenario_end)
        models = _parse_models(args.models)
        df = run_repeated_no_tools_eval(
            scenarios,
            repeats=args.repeats,
            output_dir=args.output_dir,
            models=models,
        )
        print(f"Repeated no-tools predictions saved to {args.output_dir}")
        print(f"Total rows: {len(df)}")

    elif args.command == "analyze":
        import pandas as pd

        from policybench.analysis import (
            analyze_no_tools,
            build_scenario_prompt_map,
            export_dashboard_data,
            export_analysis,
        )
        from policybench.eval_no_tools import load_repeated_predictions

        gt = pd.read_csv(args.ground_truth)
        no_tools = pd.read_csv(args.predictions)
        repeated_predictions = None
        if args.runs_dir:
            repeated_predictions = load_repeated_predictions(args.runs_dir)

        analysis = analyze_no_tools(
            gt,
            no_tools,
            repeated_predictions=repeated_predictions,
        )
        exported = export_analysis(analysis, args.output_dir)
        scenario_manifest_path = Path(args.scenario_manifest)
        if scenario_manifest_path.exists():
            scenarios = pd.read_csv(scenario_manifest_path)
            scenario_prompts = build_scenario_prompt_map(
                scenarios,
                gt["variable"].drop_duplicates().tolist(),
            )
            dashboard_path = export_dashboard_data(
                gt,
                no_tools,
                analysis,
                scenarios,
                args.app_data_output,
                scenario_prompts=scenario_prompts,
            )
            exported["dashboard_data"] = dashboard_path
        else:
            print(
                f"\nDashboard export skipped: scenario manifest not found at "
                f"{scenario_manifest_path}"
            )

        print("\n=== AI Alone Metrics ===")
        print(analysis["metrics"].to_string(index=False))
        print("\n=== Summary by Model ===")
        print(analysis["model_summary"].to_string(index=False))
        print("\n=== Summary by Variable ===")
        print(analysis["variable_summary"].to_string(index=False))
        if not analysis["run_stability"].empty:
            print("\n=== Run Stability ===")
            print(analysis["run_stability"].to_string(index=False))
        if not analysis["usage_summary"].empty:
            print("\n=== Usage Summary ===")
            print(analysis["usage_summary"].to_string(index=False))
        print("\n=== Exported Artifacts ===")
        for name, path in exported.items():
            print(f"{name}: {path}")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
