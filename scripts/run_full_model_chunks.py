#!/usr/bin/env python3
"""Run one or more full-batch model evaluations in resumable chunks."""

from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from policybench.config import DEFAULT_PROGRAM_SET, MODELS, get_programs
from policybench.scenarios import load_scenarios_from_manifest
from policybench.spec import expand_programs_for_scenario


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--country", choices=["us", "uk"], required=True)
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        required=True,
        help="Configured model name. Repeat to run several models sequentially.",
    )
    parser.add_argument("--program-set", default=DEFAULT_PROGRAM_SET)
    parser.add_argument("--chunk-size", type=int, default=50)
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--include-explanations", action="store_true")
    parser.add_argument("--single-output", action="store_true")
    return parser.parse_args()


def expected_rows(
    *,
    scenario_program_counts: list[int],
) -> int:
    return sum(scenario_program_counts)


def chunk_is_complete(
    path: Path,
    *,
    scenario_program_counts: list[int],
) -> bool:
    if not path.exists():
        return False
    try:
        frame = pd.read_csv(path)
    except Exception:
        return False
    if len(frame) != expected_rows(scenario_program_counts=scenario_program_counts):
        return False
    if "prediction" in frame.columns and frame["prediction"].isna().any():
        return False
    if "error" in frame.columns and frame["error"].fillna("").str.strip().ne("").any():
        return False
    return True


def run_chunk(
    *,
    country: str,
    model: str,
    program_set: str,
    manifest: Path,
    scenario_count: int,
    output: Path,
    start: int,
    end: int,
    include_explanations: bool,
    single_output: bool,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "policybench.cli",
        "eval-no-tools",
        "--num-scenarios",
        str(scenario_count),
        "--country",
        country,
        "--program-set",
        program_set,
        "--scenario-manifest",
        str(manifest),
        "--scenario-start",
        str(start),
        "--scenario-end",
        str(end),
        "--model",
        model,
        "-o",
        str(output),
    ]
    if include_explanations:
        cmd.append("--include-explanations")
    if single_output:
        cmd.append("--single-output")

    subprocess.run(cmd, check=True)


def merge_chunks(
    *,
    model: str,
    chunk_paths: list[Path],
    output_path: Path,
) -> None:
    frames = [pd.read_csv(path) for path in chunk_paths]
    merged = pd.concat(frames, ignore_index=True)
    duplicate_count = merged.duplicated(["model", "scenario_id", "variable"]).sum()
    if duplicate_count:
        raise ValueError(f"{model} has {duplicate_count} duplicate output rows.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)
    print(f"Wrote {output_path} ({len(merged):,} rows)")


def run_model(args: argparse.Namespace, model: str) -> None:
    if model not in MODELS:
        valid = ", ".join(sorted(MODELS))
        raise ValueError(f"Unknown model '{model}'. Valid models: {valid}.")

    run_dir = Path(args.run_dir)
    country_dir = run_dir / args.country
    manifest = country_dir / "scenarios.csv"
    if not manifest.exists():
        raise FileNotFoundError(f"Missing scenario manifest: {manifest}")

    manifest_frame = pd.read_csv(manifest)
    scenarios = load_scenarios_from_manifest(manifest)
    scenario_count = len(manifest_frame)
    programs = get_programs(args.country, args.program_set)
    scenario_program_counts = [
        len(expand_programs_for_scenario(programs, scenario)) for scenario in scenarios
    ]
    chunks = [
        (start, min(start + args.chunk_size, scenario_count))
        for start in range(0, scenario_count, args.chunk_size)
    ]
    chunk_dir = country_dir / "chunks" / model
    chunk_paths = [
        chunk_dir / f"s{start:04d}_{end:04d}.csv" for start, end in chunks
    ]

    pending = [
        (start, end, path)
        for (start, end), path in zip(chunks, chunk_paths)
        if not chunk_is_complete(
            path,
            scenario_program_counts=scenario_program_counts[start:end],
        )
    ]

    print(
        f"{args.country} {model}: {scenario_count} scenarios, "
        f"{len(chunks)} chunks, {len(pending)} pending"
    )

    if pending:
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = [
                executor.submit(
                    run_chunk,
                    country=args.country,
                    model=model,
                    program_set=args.program_set,
                    manifest=manifest,
                    scenario_count=scenario_count,
                    output=path,
                    start=start,
                    end=end,
                    include_explanations=args.include_explanations,
                    single_output=args.single_output,
                )
                for start, end, path in pending
            ]
            for future in as_completed(futures):
                future.result()

    incomplete = [
        path
        for (start, end), path in zip(chunks, chunk_paths)
        if not chunk_is_complete(
            path,
            scenario_program_counts=scenario_program_counts[start:end],
        )
    ]
    if incomplete:
        raise RuntimeError(
            f"{model} has {len(incomplete)} incomplete chunk(s); first: {incomplete[0]}"
        )

    merge_chunks(
        model=model,
        chunk_paths=chunk_paths,
        output_path=country_dir / "by_model" / f"{model}.csv",
    )


def main() -> None:
    args = parse_args()
    if args.chunk_size <= 0:
        raise ValueError("--chunk-size must be positive.")
    if args.parallel <= 0:
        raise ValueError("--parallel must be positive.")

    for model in args.models:
        run_model(args, model)


if __name__ == "__main__":
    main()
