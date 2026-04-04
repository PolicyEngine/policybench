#!/usr/bin/env python3
"""Run Grok 4.20 explanation backfills on saved diagnostic scenario manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from policybench.config import UK_PROGRAMS, US_PROGRAMS
import policybench.eval_no_tools as eval_no_tools
from policybench.scenarios import scenario_from_dict


DEFAULTS = {
    "us": {
        "manifest": Path(
            "/Users/maxghenis/PolicyEngine/policybench/results/diagnostics_20260329_100/scenarios.csv"
        ),
        "output": Path(
            "/Users/maxghenis/PolicyEngine/policybench/results/diagnostics_20260329_100/grok-4.20.csv"
        ),
        "programs": US_PROGRAMS,
    },
    "uk": {
        "manifest": Path(
            "/Users/maxghenis/PolicyEngine/policybench/results/uk_diagnostics_20260329_100/scenarios.csv"
        ),
        "output": Path(
            "/Users/maxghenis/PolicyEngine/policybench/results/uk_diagnostics_20260329_100/grok-4.20.csv"
        ),
        "programs": UK_PROGRAMS,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("country", choices=sorted(DEFAULTS))
    parser.add_argument("--scenario-start", type=int, default=0)
    parser.add_argument("--scenario-end", type=int)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    defaults = DEFAULTS[args.country]

    manifest = defaults["manifest"]
    output = Path(args.output) if args.output else defaults["output"]
    programs = defaults["programs"]

    frame = pd.read_csv(manifest)
    sliced = frame.iloc[args.scenario_start : args.scenario_end]
    scenarios = [scenario_from_dict(json.loads(text)) for text in sliced["scenario_json"]]

    # This helper is only used for backfills, so frequent checkpoints are useful.
    eval_no_tools.CHECKPOINT_EVERY_ROWS = 1
    eval_no_tools.run_no_tools_eval(
        scenarios,
        models={"grok-4.20": "xai/grok-4.20-reasoning"},
        programs=programs,
        output_path=str(output),
        include_explanations=True,
    )
    print(f"{args.country.upper()} grok diagnostics done: {output}")


if __name__ == "__main__":
    main()
