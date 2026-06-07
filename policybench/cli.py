"""CLI entry point for PolicyBench."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from policybench.config import (
    COUNTRY_PROGRAMS,
    DEFAULT_PROGRAM_SET,
    MODELS,
    PROGRAMS,
    get_programs,
)


def _ensure_parent_dir(output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)


def _write_metadata(output_path: str, metadata: dict) -> None:
    Path(f"{output_path}.meta.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )


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


def _parse_programs(
    selected: list[str] | None, allowed: list[str] | None = None
) -> list[str]:
    allowed_programs = PROGRAMS if allowed is None else allowed
    if not selected:
        return allowed_programs

    unknown = [name for name in selected if name not in allowed_programs]
    if unknown:
        raise SystemExit(
            f"Unknown program(s): {', '.join(sorted(unknown))}. "
            f"Valid choices: {', '.join(allowed_programs)}"
        )
    return selected


def _slice_scenarios(scenarios: list, start: int, end: int | None) -> list:
    if start < 0:
        raise SystemExit("--scenario-start must be >= 0")
    if end is not None and end < start:
        raise SystemExit("--scenario-end must be >= --scenario-start")
    return scenarios[start:end]


def _load_eval_scenarios(args) -> list:
    from policybench.scenarios import generate_scenarios, load_scenarios_from_manifest

    if getattr(args, "regenerate_scenarios", False):
        excluded_household_ids = None
        if args.exclude_scenario_manifest:
            from policybench.scenarios import load_excluded_household_ids

            excluded_household_ids = load_excluded_household_ids(
                args.exclude_scenario_manifest
            )
        return generate_scenarios(
            n=args.num_scenarios,
            seed=args.seed,
            excluded_household_ids=excluded_household_ids,
            country=args.country,
        )

    manifest_path = Path(args.scenario_manifest)
    if not manifest_path.exists():
        raise SystemExit(
            "Scenario manifest not found at "
            f"{manifest_path}. Run `policybench reference-outputs` first or pass "
            "`--regenerate-scenarios` for an ad hoc sample."
        )

    scenarios = load_scenarios_from_manifest(manifest_path)
    if len(scenarios) != args.num_scenarios:
        raise SystemExit(
            f"Scenario manifest contains {len(scenarios)} scenarios but "
            f"`--num-scenarios` is {args.num_scenarios}. Use the manifest size "
            "or regenerate scenarios explicitly."
        )
    if any(scenario.country != args.country for scenario in scenarios):
        raise SystemExit(
            "Scenario manifest country does not match the requested "
            f"`--country={args.country}`."
        )
    return scenarios


def _load_reference_scenarios(args) -> tuple[list, str | None]:
    from policybench.scenarios import generate_scenarios, load_scenarios_from_manifest

    if args.scenario_manifest:
        scenarios = load_scenarios_from_manifest(args.scenario_manifest)
        if any(scenario.country != args.country for scenario in scenarios):
            raise SystemExit(
                "Scenario manifest country does not match the requested "
                f"`--country={args.country}`."
            )
        return scenarios, args.scenario_manifest

    excluded_household_ids = None
    if args.exclude_scenario_manifest:
        from policybench.scenarios import load_excluded_household_ids

        excluded_household_ids = load_excluded_household_ids(
            args.exclude_scenario_manifest
        )
    scenarios = generate_scenarios(
        n=args.num_scenarios,
        seed=args.seed,
        excluded_household_ids=excluded_household_ids,
        country=args.country,
    )
    return scenarios, None


def main():
    parser = argparse.ArgumentParser(description="PolicyBench benchmark runner")
    subparsers = parser.add_subparsers(dest="command")

    # PolicyEngine reference outputs
    gt_parser = subparsers.add_parser(
        "reference-outputs",
        help="Generate PolicyEngine reference outputs",
    )
    gt_parser.add_argument(
        "-o", "--output", default="results/local/reference_outputs.csv"
    )
    gt_parser.add_argument("-n", "--num-scenarios", type=int, default=100)
    gt_parser.add_argument("--seed", type=int, default=42)
    gt_parser.add_argument(
        "--country",
        choices=sorted(COUNTRY_PROGRAMS),
        default="us",
        help="Benchmark country to sample and score",
    )
    gt_parser.add_argument(
        "--scenario-manifest-output",
        default="results/local/scenarios.csv",
        help="CSV file for exported scenario metadata (local scratch path)",
    )
    gt_parser.add_argument(
        "--scenario-manifest",
        default=None,
        help=(
            "Existing scenario manifest to recompute reference outputs for. "
            "When provided, households are not resampled."
        ),
    )
    gt_parser.add_argument(
        "--program",
        action="append",
        dest="programs",
        help=(
            "Restrict reference-output generation to one or more configured "
            "program names"
        ),
    )
    gt_parser.add_argument(
        "--program-set",
        default=DEFAULT_PROGRAM_SET,
        help="Benchmark output set to use. Defaults to headline.",
    )
    gt_parser.add_argument(
        "--exclude-scenario-manifest",
        default=None,
        help="Existing scenario manifest whose sampled households should be excluded",
    )

    # Eval no tools
    nt_parser = subparsers.add_parser("eval-no-tools", help="Run AI-alone evaluation")
    nt_parser.add_argument(
        "-o",
        "--output",
        default="results/local/no_tools/predictions.csv",
    )
    nt_parser.add_argument("-n", "--num-scenarios", type=int, default=100)
    nt_parser.add_argument("--seed", type=int, default=42)
    nt_parser.add_argument(
        "--country",
        choices=sorted(COUNTRY_PROGRAMS),
        default="us",
        help="Benchmark country to sample and score",
    )
    nt_parser.add_argument(
        "--scenario-manifest",
        default="results/local/scenarios.csv",
        help="CSV file with serialized scenarios exported by `reference-outputs`",
    )
    nt_parser.add_argument(
        "--regenerate-scenarios",
        action="store_true",
        help=(
            "Ignore the saved manifest and resample households from the "
            "current source dataset"
        ),
    )
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
    nt_parser.add_argument(
        "--program",
        action="append",
        dest="programs",
        help="Restrict evaluation to one or more configured program names",
    )
    nt_parser.add_argument(
        "--program-set",
        default=DEFAULT_PROGRAM_SET,
        help="Benchmark output set to use. Defaults to headline.",
    )
    nt_parser.add_argument(
        "--no-explanations",
        action="store_true",
        help=(
            "Ablation only: request numeric answers without the standard "
            "per-output explanations"
        ),
    )
    nt_parser.add_argument(
        "--single-output",
        action="store_true",
        help=(
            "Evaluate one configured output per request "
            "instead of one batch per household"
        ),
    )
    nt_parser.add_argument(
        "--exclude-scenario-manifest",
        default=None,
        help="Existing scenario manifest whose sampled households should be excluded",
    )

    # Eval no tools repeated
    ntr_parser = subparsers.add_parser(
        "eval-no-tools-repeated",
        help="Run repeated AI-alone evaluations on a fixed scenario set",
    )
    ntr_parser.add_argument(
        "-o",
        "--output-dir",
        default="results/local/no_tools/runs",
        help="Directory for per-run prediction CSVs",
    )
    ntr_parser.add_argument("-n", "--num-scenarios", type=int, default=100)
    ntr_parser.add_argument("--seed", type=int, default=42)
    ntr_parser.add_argument(
        "--country",
        choices=sorted(COUNTRY_PROGRAMS),
        default="us",
        help="Benchmark country to sample and score",
    )
    ntr_parser.add_argument(
        "--scenario-manifest",
        default="results/local/scenarios.csv",
        help="CSV file with serialized scenarios exported by `reference-outputs`",
    )
    ntr_parser.add_argument(
        "--regenerate-scenarios",
        action="store_true",
        help=(
            "Ignore the saved manifest and resample households from the "
            "current source dataset"
        ),
    )
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
    ntr_parser.add_argument(
        "--program",
        action="append",
        dest="programs",
        help="Restrict evaluation to one or more configured program names",
    )
    ntr_parser.add_argument(
        "--program-set",
        default=DEFAULT_PROGRAM_SET,
        help="Benchmark output set to use. Defaults to headline.",
    )
    ntr_parser.add_argument(
        "--no-explanations",
        action="store_true",
        help=(
            "Ablation only: request numeric answers without the standard "
            "per-output explanations"
        ),
    )
    ntr_parser.add_argument(
        "--single-output",
        action="store_true",
        help=(
            "Evaluate one configured output per request "
            "instead of one batch per household"
        ),
    )
    ntr_parser.add_argument(
        "--exclude-scenario-manifest",
        default=None,
        help="Existing scenario manifest whose sampled households should be excluded",
    )

    # Chunked eval no tools
    chunked_parser = subparsers.add_parser(
        "eval-no-tools-chunked",
        help="Run resumable chunked AI-alone evaluation against a saved manifest",
    )
    chunked_parser.add_argument(
        "-s",
        "--scenario-manifest",
        default="results/local/scenarios.csv",
        help="CSV file with serialized scenarios exported by `reference-outputs`",
    )
    chunked_parser.add_argument(
        "-o",
        "--output-dir",
        default="results/local/no_tools_chunked",
        help="Directory for chunks and merged per-model prediction CSVs",
    )
    chunked_parser.add_argument(
        "--country",
        choices=sorted(COUNTRY_PROGRAMS),
        required=True,
        help="Benchmark country to evaluate",
    )
    chunked_parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Restrict evaluation to one or more configured model names",
    )
    chunked_parser.add_argument(
        "--program-set",
        default=DEFAULT_PROGRAM_SET,
        help="Benchmark output set to use. Defaults to headline.",
    )
    chunked_parser.add_argument(
        "--chunk-size",
        type=int,
        default=50,
        help="Number of scenarios per chunk",
    )
    chunked_parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help=(
            "Concurrent chunks per model. Keep at 1 for Claude/Anthropic "
            "models so local wall timeouts run on the main thread."
        ),
    )
    chunked_parser.add_argument(
        "--model-parallel",
        type=int,
        default=1,
        help="Concurrent models to evaluate",
    )
    chunked_parser.add_argument(
        "--chunk-attempts",
        type=int,
        default=1,
        help="Attempts per model/scenario chunk before failing",
    )
    chunked_parser.add_argument(
        "--no-explanations",
        action="store_true",
        help=(
            "Ablation only: request numeric answers without the standard "
            "per-output explanations"
        ),
    )
    chunked_parser.add_argument(
        "--single-output",
        action="store_true",
        help=(
            "Evaluate one configured output per request "
            "instead of one batch per household"
        ),
    )

    # Export full run
    export_parser = subparsers.add_parser(
        "export-full-run",
        help="Export full-run analysis and frontend payloads",
    )
    export_parser.add_argument(
        "--run-dir",
        required=True,
        help="Full-run directory containing country subdirectories",
    )
    export_parser.add_argument(
        "--country",
        action="append",
        dest="countries",
        default=None,
        help="Country code to export. Repeat to export multiple countries.",
    )
    export_parser.add_argument(
        "--app-data-output",
        default="app/src/data.json",
        help="Path for the combined frontend payload",
    )
    export_parser.add_argument(
        "--skip-app-data",
        action="store_true",
        help="Only write the combined payload under the run directory",
    )

    # Population weights
    weight_parser = subparsers.add_parser(
        "population-weights",
        help="Regenerate full-population output weights",
    )
    weight_parser.add_argument(
        "-o",
        "--output",
        default="policybench/population_weights.json",
        help="Path for the generated population-weight artifact",
    )
    weight_parser.add_argument(
        "--country",
        action="append",
        dest="countries",
        choices=sorted(COUNTRY_PROGRAMS),
        default=None,
        help="Country to regenerate. Repeat to include multiple countries.",
    )
    weight_parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Tax year. Defaults to the configured benchmark tax year.",
    )

    # Compare prompt modes
    compare_parser = subparsers.add_parser(
        "compare-prompt-modes",
        help="Compare multi-output and single-output benchmark runs",
    )
    compare_parser.add_argument(
        "--reference-outputs",
        dest="reference_outputs",
        required=True,
    )
    compare_parser.add_argument("--multi-predictions", required=True)
    compare_parser.add_argument("--single-predictions", required=True)
    compare_parser.add_argument("--output-dir", required=True)

    # Retry failed full responses
    retry_parser = subparsers.add_parser(
        "retry-failed-responses",
        help=(
            "Retry full country-model-household responses with missing "
            "predictions or explanations"
        ),
    )
    retry_parser.add_argument(
        "--country",
        choices=sorted(COUNTRY_PROGRAMS),
        required=True,
    )
    retry_parser.add_argument("--source-predictions", required=True)
    retry_parser.add_argument("--scenario-manifest", required=True)
    retry_parser.add_argument("--output-dir", required=True)
    retry_parser.add_argument(
        "--program-set",
        default=DEFAULT_PROGRAM_SET,
        help="Benchmark output set to use. Defaults to headline.",
    )
    retry_parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Restrict retry targets to one or more configured model names",
    )
    retry_parser.add_argument(
        "--chunk-size",
        type=int,
        default=10,
        help="Number of retry scenarios per chunk",
    )
    retry_parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Concurrent chunks per non-Claude model",
    )
    retry_parser.add_argument(
        "--model-parallel",
        type=int,
        default=1,
        help="Concurrent non-Claude models to retry",
    )
    retry_parser.add_argument(
        "--chunk-attempts",
        type=int,
        default=1,
        help="Attempts per retry chunk before failing",
    )
    retry_parser.add_argument(
        "--no-explanations",
        action="store_true",
        help="Ignore explanation completeness when selecting and accepting retries",
    )
    retry_parser.add_argument(
        "--max-responses",
        type=int,
        default=None,
        help="Only target the first N broken full responses, for smoke tests",
    )
    retry_parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Write retry manifests and original failed rows without model calls",
    )
    retry_parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Allow LiteLLM disk-cache replay during retry calls",
    )

    # Repair failed rows
    row_repair_parser = subparsers.add_parser(
        "repair-failed-rows",
        help=(
            "Repair individual output rows with missing parsed values or explanations"
        ),
    )
    row_repair_parser.add_argument(
        "--country",
        choices=sorted(COUNTRY_PROGRAMS),
        required=True,
    )
    row_repair_parser.add_argument("--source-predictions", required=True)
    row_repair_parser.add_argument("--scenario-manifest", required=True)
    row_repair_parser.add_argument("--output-dir", required=True)
    row_repair_parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Restrict repair targets to one or more configured model names",
    )
    row_repair_parser.add_argument(
        "--attempts-per-row",
        type=int,
        default=3,
        help="Attempts per missing row before leaving it unrepaired",
    )
    row_repair_parser.add_argument(
        "--parallel",
        type=int,
        default=4,
        help="Concurrent non-Claude row repairs",
    )
    row_repair_parser.add_argument(
        "--no-explanations",
        action="store_true",
        help="Ignore explanation completeness when selecting and accepting repairs",
    )
    row_repair_parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Only target the first N broken rows, for smoke tests",
    )
    row_repair_parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Write repair targets without model calls",
    )
    row_repair_parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Allow LiteLLM disk-cache replay during row-repair calls",
    )

    # Analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyze AI-alone results")
    analyze_parser.add_argument(
        "-g",
        "--reference-outputs",
        dest="ground_truth",
        default="results/local/reference_outputs.csv",
        help="CSV file with PolicyEngine reference outputs.",
    )
    analyze_parser.add_argument(
        "-p", "--predictions", default="results/local/no_tools/predictions.csv"
    )
    analyze_parser.add_argument(
        "-s",
        "--scenario-manifest",
        default="results/local/scenarios.csv",
        help="CSV file with scenario metadata for dashboard export",
    )
    analyze_parser.add_argument(
        "-o",
        "--output-dir",
        default="results/local/analysis",
        help="Directory for exported local analysis artifacts",
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

    # Enable disk cache for ordinary eval calls. Contract-failure retry/repair
    # commands bypass cache by default, otherwise they can replay the same bad
    # provider response indefinitely.
    if args.command in {
        "eval-no-tools",
        "eval-no-tools-repeated",
        "eval-no-tools-chunked",
    } or (
        args.command in {"retry-failed-responses", "repair-failed-rows"}
        and args.use_cache
    ):
        from policybench.cache import enable_cache

        enable_cache()

    if args.command == "reference-outputs":
        from policybench.ground_truth import calculate_ground_truth
        from policybench.policyengine_runtime import runtime_metadata_for_country
        from policybench.scenarios import (
            get_uk_dataset_path,
            remove_unsupported_us_inputs,
            scenario_manifest,
        )

        scenarios, scenario_manifest_input = _load_reference_scenarios(args)
        programs = _parse_programs(
            args.programs,
            get_programs(args.country, args.program_set),
        )
        calculation_scenarios, dropped_removed_inputs = (
            remove_unsupported_us_inputs(scenarios)
            if args.country == "us"
            else (scenarios, [])
        )
        df = calculate_ground_truth(calculation_scenarios, programs=programs)
        _ensure_parent_dir(args.output)
        df.to_csv(args.output, index=False)
        _ensure_parent_dir(args.scenario_manifest_output)
        scenario_manifest(scenarios).to_csv(args.scenario_manifest_output, index=False)
        source_dataset_path = get_uk_dataset_path() if args.country == "uk" else None
        metadata = {
            "metadata_version": 1,
            "task": "reference_outputs",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "country": args.country,
            "num_scenarios": len(scenarios),
            "requested_num_scenarios": args.num_scenarios,
            "seed": args.seed,
            "program_set": args.program_set,
            "programs": sorted(programs),
            "output": args.output,
            "scenario_manifest_output": args.scenario_manifest_output,
            "scenario_manifest_input": scenario_manifest_input,
            **runtime_metadata_for_country(
                args.country,
                source_dataset_path=source_dataset_path,
            ),
        }
        if dropped_removed_inputs:
            metadata["local_compatibility_adjustment"] = {
                "dropped_removed_inputs": dropped_removed_inputs,
                "reason": (
                    "The frozen scenario manifest includes input variables that "
                    "the installed PolicyEngine-US no longer defines."
                ),
            }
        _write_metadata(args.output, metadata)
        _write_metadata(
            args.scenario_manifest_output,
            {
                **metadata,
                "task": "scenario_manifest",
            },
        )
        print(f"PolicyEngine reference outputs saved to {args.output}")
        print(f"Scenario manifest saved to {args.scenario_manifest_output}")

    elif args.command == "eval-no-tools":
        from policybench.eval_no_tools import (
            run_no_tools_eval,
            run_no_tools_single_output_eval,
        )

        scenarios = _load_eval_scenarios(args)
        scenarios = _slice_scenarios(scenarios, args.scenario_start, args.scenario_end)
        models = _parse_models(args.models)
        programs = _parse_programs(
            args.programs,
            get_programs(args.country, args.program_set),
        )
        _ensure_parent_dir(args.output)
        runner = (
            run_no_tools_single_output_eval if args.single_output else run_no_tools_eval
        )
        try:
            df = runner(
                scenarios,
                models=models,
                programs=programs,
                output_path=args.output,
                include_explanations=not args.no_explanations,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        df.to_csv(args.output, index=False)
        print(f"No-tools predictions saved to {args.output}")

    elif args.command == "eval-no-tools-repeated":
        from policybench.eval_no_tools import run_repeated_no_tools_eval

        scenarios = _load_eval_scenarios(args)
        scenarios = _slice_scenarios(scenarios, args.scenario_start, args.scenario_end)
        models = _parse_models(args.models)
        programs = _parse_programs(
            args.programs,
            get_programs(args.country, args.program_set),
        )
        try:
            df = run_repeated_no_tools_eval(
                scenarios,
                repeats=args.repeats,
                output_dir=args.output_dir,
                models=models,
                programs=programs,
                include_explanations=not args.no_explanations,
                single_output=args.single_output,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"Repeated no-tools predictions saved to {args.output_dir}")
        print(f"Total rows: {len(df)}")

    elif args.command == "eval-no-tools-chunked":
        from policybench.chunked_eval import run_chunked_eval

        try:
            output = run_chunked_eval(
                scenario_manifest=args.scenario_manifest,
                output_dir=args.output_dir,
                country=args.country,
                models=list(_parse_models(args.models)),
                program_set=args.program_set,
                chunk_size=args.chunk_size,
                parallel=args.parallel,
                model_parallel=args.model_parallel,
                chunk_attempts=args.chunk_attempts,
                include_explanations=not args.no_explanations,
                single_output=args.single_output,
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
        print(f"Chunked no-tools predictions saved to {output}")

    elif args.command == "export-full-run":
        from policybench.full_run_export import export_full_run

        try:
            export_full_run(
                run_dir=args.run_dir,
                countries=args.countries,
                app_data_output=args.app_data_output,
                skip_app_data=args.skip_app_data,
            )
        except FileNotFoundError as exc:
            raise SystemExit(str(exc)) from exc

    elif args.command == "population-weights":
        from policybench.config import TAX_YEAR
        from policybench.population_weights import write_population_weight_payload

        year = TAX_YEAR if args.year is None else args.year
        output = write_population_weight_payload(
            args.output,
            countries=args.countries,
            year=year,
        )
        print(f"Population weights saved to {output}")

    elif args.command == "compare-prompt-modes":
        from policybench.prompt_mode_comparison import compare_prompt_modes

        compare_prompt_modes(
            reference_outputs=args.reference_outputs,
            multi_predictions=args.multi_predictions,
            single_predictions=args.single_predictions,
            output_dir=args.output_dir,
        )

    elif args.command == "retry-failed-responses":
        from policybench.retry_eval import run_retry_round

        outputs = run_retry_round(
            country=args.country,
            source_predictions=args.source_predictions,
            scenario_manifest=args.scenario_manifest,
            output_dir=args.output_dir,
            program_set=args.program_set,
            chunk_size=args.chunk_size,
            parallel=args.parallel,
            model_parallel=args.model_parallel,
            chunk_attempts=args.chunk_attempts,
            require_explanations=not args.no_explanations,
            models=args.models,
            max_responses=args.max_responses,
            prepare_only=args.prepare_only,
        )
        print("\n=== Retry outputs ===")
        for name, path in outputs.items():
            print(f"{name}: {path}")

    elif args.command == "repair-failed-rows":
        from policybench.row_repair import run_row_repair_round

        outputs = run_row_repair_round(
            country=args.country,
            source_predictions=args.source_predictions,
            scenario_manifest=args.scenario_manifest,
            output_dir=args.output_dir,
            attempts_per_row=args.attempts_per_row,
            parallel=args.parallel,
            require_explanations=not args.no_explanations,
            models=args.models,
            max_rows=args.max_rows,
            prepare_only=args.prepare_only,
        )
        print("\n=== Row repair outputs ===")
        for name, path in outputs.items():
            print(f"{name}: {path}")

    elif args.command == "analyze":
        import pandas as pd

        from policybench.analysis import (
            analyze_no_tools,
            build_scenario_prompt_map,
            export_analysis,
            export_dashboard_data,
        )
        from policybench.eval_no_tools import load_repeated_predictions

        gt = pd.read_csv(args.ground_truth)
        no_tools = pd.read_csv(args.predictions)
        repeated_predictions = None
        if args.runs_dir:
            repeated_predictions = load_repeated_predictions(args.runs_dir)

        scenario_manifest_path = Path(args.scenario_manifest)
        scenarios = None
        if scenario_manifest_path.exists():
            scenarios = pd.read_csv(scenario_manifest_path)

        analysis = analyze_no_tools(
            gt,
            no_tools,
            scenarios=scenarios,
            repeated_predictions=repeated_predictions,
        )
        exported = export_analysis(analysis, args.output_dir)
        if scenarios is not None:
            manifest_ids = set(scenarios["scenario_id"])
            gt_ids = set(gt["scenario_id"])
            prediction_ids = set(no_tools["scenario_id"])
            if not gt_ids.issubset(manifest_ids):
                missing = ", ".join(sorted(gt_ids - manifest_ids)[:5])
                raise SystemExit(
                    "Reference-output file contains scenario ids not present in the "
                    f"scenario manifest: {missing}"
                )
            if not prediction_ids.issubset(manifest_ids):
                missing = ", ".join(sorted(prediction_ids - manifest_ids)[:5])
                raise SystemExit(
                    "Prediction file contains scenario ids not present in the "
                    f"scenario manifest: {missing}"
                )
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
