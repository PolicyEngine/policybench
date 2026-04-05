#!/usr/bin/env python3
"""Run a model against a saved PolicyBench scenario manifest.

This is intended for resumable backfills on an existing benchmark sample.
It reads `scenario_json` from a saved manifest instead of generating a new sample.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import policybench.eval_no_tools as eval_no_tools
from policybench.config import MODELS, get_programs
from policybench.scenarios import scenario_from_dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--country", choices=["us", "uk"], required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--scenario-start", type=int, default=0)
    parser.add_argument("--scenario-end", type=int)
    parser.add_argument("--include-explanations", action="store_true")
    parser.add_argument("--checkpoint-every", type=int)
    parser.add_argument(
        "--single-output",
        action="store_true",
        help=(
            "Evaluate one requested variable per model call "
            "instead of one batch per household"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_path = Path(args.manifest)
    output_path = Path(args.output)

    if args.model not in MODELS:
        valid = ", ".join(sorted(MODELS))
        raise ValueError(f"Unknown model '{args.model}'. Valid models: {valid}")

    manifest = pd.read_csv(manifest_path)
    if "scenario_json" not in manifest.columns:
        raise ValueError(f"{manifest_path} is missing required column 'scenario_json'")

    sliced = manifest.iloc[args.scenario_start : args.scenario_end]
    scenarios = [
        scenario_from_dict(json.loads(text)) for text in sliced["scenario_json"]
    ]

    print(
        f"Running {args.model} on {len(scenarios)} scenarios "
        f"from {manifest_path} -> {output_path}"
    )
    if scenarios:
        print(f"Scenario range: {scenarios[0].id} to {scenarios[-1].id}")
    if args.checkpoint_every is not None:
        eval_no_tools.CHECKPOINT_EVERY_ROWS = args.checkpoint_every
        print(f"Checkpoint every {args.checkpoint_every} completed scenarios")

    runner = (
        eval_no_tools.run_no_tools_single_output_eval
        if args.single_output
        else eval_no_tools.run_no_tools_eval
    )
    runner(
        scenarios,
        models={args.model: MODELS[args.model]},
        programs=get_programs(args.country),
        output_path=str(output_path),
        include_explanations=args.include_explanations,
    )
    print("Done")


if __name__ == "__main__":
    main()
