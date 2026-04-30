"""Chunked, resumable orchestration for no-tools model evaluations."""

from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from policybench.config import DEFAULT_PROGRAM_SET, MODELS, get_programs
from policybench.scenarios import load_scenarios_from_manifest
from policybench.spec import expand_programs_for_scenario


@dataclass(frozen=True)
class ScenarioChunk:
    start: int
    end: int
    path: Path


def expected_rows(*, scenario_program_counts: list[int]) -> int:
    return sum(scenario_program_counts)


def chunk_is_complete(
    path: Path,
    *,
    scenario_program_counts: list[int],
    require_explanations: bool = True,
) -> bool:
    if not path.exists():
        return False
    try:
        frame = pd.read_csv(path)
    except (
        OSError,
        UnicodeDecodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ):
        return False
    if len(frame) != expected_rows(scenario_program_counts=scenario_program_counts):
        return False
    if "prediction" not in frame.columns or frame["prediction"].isna().any():
        return False
    if require_explanations:
        if "explanation" not in frame.columns:
            return False
        if frame["explanation"].fillna("").astype(str).str.strip().eq("").any():
            return False
    if "error" in frame.columns and frame["error"].fillna("").str.strip().ne("").any():
        return False
    return True


def chunk_scenario_ranges(
    *,
    scenario_count: int,
    chunk_size: int,
    chunk_dir: Path,
) -> list[ScenarioChunk]:
    chunks = []
    for start in range(0, scenario_count, chunk_size):
        end = min(start + chunk_size, scenario_count)
        chunks.append(
            ScenarioChunk(
                start=start,
                end=end,
                path=chunk_dir / f"s{start:04d}_{end:04d}.csv",
            )
        )
    return chunks


def run_chunk(
    *,
    country: str,
    model: str,
    program_set: str,
    scenario_manifest: Path,
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
        str(scenario_manifest),
        "--scenario-start",
        str(start),
        "--scenario-end",
        str(end),
        "--model",
        model,
        "-o",
        str(output),
    ]
    if not include_explanations:
        cmd.append("--no-explanations")
    if single_output:
        cmd.append("--single-output")

    subprocess.run(cmd, check=True)


def run_chunk_with_retries(
    *,
    country: str,
    model: str,
    program_set: str,
    scenario_manifest: Path,
    scenario_count: int,
    output: Path,
    start: int,
    end: int,
    include_explanations: bool,
    single_output: bool,
    scenario_program_counts: list[int],
    attempts: int = 1,
) -> None:
    if attempts <= 0:
        raise ValueError("attempts must be positive.")

    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            run_chunk(
                country=country,
                model=model,
                program_set=program_set,
                scenario_manifest=scenario_manifest,
                scenario_count=scenario_count,
                output=output,
                start=start,
                end=end,
                include_explanations=include_explanations,
                single_output=single_output,
            )
        except subprocess.CalledProcessError as exc:
            last_error = exc
        else:
            if chunk_is_complete(
                output,
                scenario_program_counts=scenario_program_counts,
                require_explanations=include_explanations,
            ):
                return
            last_error = RuntimeError(f"Incomplete chunk output: {output}")

        if attempt < attempts:
            print(f"{model} chunk {start}:{end} failed attempt {attempt}; retrying")

    if last_error is not None:
        raise last_error


def incomplete_chunks(
    *,
    chunks: list[ScenarioChunk],
    scenario_program_counts: list[int],
    require_explanations: bool,
) -> list[ScenarioChunk]:
    return [
        chunk
        for chunk in chunks
        if not chunk_is_complete(
            chunk.path,
            scenario_program_counts=scenario_program_counts[chunk.start : chunk.end],
            require_explanations=require_explanations,
        )
    ]


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


def merge_model_outputs(*, model_output_paths: list[Path], output_path: Path) -> Path:
    frames = [pd.read_csv(path) for path in model_output_paths]
    merged = pd.concat(frames, ignore_index=True)
    duplicate_count = merged.duplicated(["model", "scenario_id", "variable"]).sum()
    if duplicate_count:
        raise ValueError(f"Combined output has {duplicate_count} duplicate rows.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)
    print(f"Wrote {output_path} ({len(merged):,} rows)")
    return output_path


def run_model_chunks(
    *,
    scenario_manifest: str | Path,
    output_dir: str | Path,
    country: str,
    model: str,
    program_set: str = DEFAULT_PROGRAM_SET,
    chunk_size: int = 50,
    parallel: int = 4,
    chunk_attempts: int = 1,
    include_explanations: bool = True,
    single_output: bool = False,
) -> Path:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    if parallel <= 0:
        raise ValueError("parallel must be positive.")
    if chunk_attempts <= 0:
        raise ValueError("chunk_attempts must be positive.")
    if model not in MODELS:
        valid = ", ".join(sorted(MODELS))
        raise ValueError(f"Unknown model '{model}'. Valid models: {valid}.")

    manifest = Path(scenario_manifest)
    output_dir = Path(output_dir)
    if not manifest.exists():
        raise FileNotFoundError(f"Missing scenario manifest: {manifest}")

    scenarios = load_scenarios_from_manifest(manifest)
    scenario_count = len(scenarios)
    programs = get_programs(country, program_set)
    scenario_program_counts = [
        len(expand_programs_for_scenario(programs, scenario)) for scenario in scenarios
    ]
    chunk_dir = output_dir / "chunks" / model
    chunks = chunk_scenario_ranges(
        scenario_count=scenario_count,
        chunk_size=chunk_size,
        chunk_dir=chunk_dir,
    )
    pending = incomplete_chunks(
        chunks=chunks,
        scenario_program_counts=scenario_program_counts,
        require_explanations=include_explanations,
    )

    print(
        f"{country} {model}: {scenario_count} scenarios, "
        f"{len(chunks)} chunks, {len(pending)} pending"
    )

    if pending:
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = [
                executor.submit(
                    run_chunk_with_retries,
                    country=country,
                    model=model,
                    program_set=program_set,
                    scenario_manifest=manifest,
                    scenario_count=scenario_count,
                    output=chunk.path,
                    start=chunk.start,
                    end=chunk.end,
                    include_explanations=include_explanations,
                    single_output=single_output,
                    scenario_program_counts=scenario_program_counts[
                        chunk.start : chunk.end
                    ],
                    attempts=chunk_attempts,
                )
                for chunk in pending
            ]
            for future in as_completed(futures):
                future.result()

    incomplete = incomplete_chunks(
        chunks=chunks,
        scenario_program_counts=scenario_program_counts,
        require_explanations=include_explanations,
    )
    if incomplete:
        raise RuntimeError(
            f"{model} has {len(incomplete)} incomplete chunk(s); "
            f"first: {incomplete[0].path}"
        )

    output_path = output_dir / "by_model" / f"{model}.csv"
    merge_chunks(
        model=model,
        chunk_paths=[chunk.path for chunk in chunks],
        output_path=output_path,
    )
    return output_path


def run_chunked_eval(
    *,
    scenario_manifest: str | Path,
    output_dir: str | Path,
    country: str,
    models: list[str],
    program_set: str = DEFAULT_PROGRAM_SET,
    chunk_size: int = 50,
    parallel: int = 4,
    model_parallel: int = 1,
    chunk_attempts: int = 1,
    include_explanations: bool = True,
    single_output: bool = False,
) -> Path:
    if model_parallel <= 0:
        raise ValueError("model_parallel must be positive.")

    def run_one_model(model: str) -> Path:
        return run_model_chunks(
            scenario_manifest=scenario_manifest,
            output_dir=output_dir,
            country=country,
            model=model,
            program_set=program_set,
            chunk_size=chunk_size,
            parallel=parallel,
            chunk_attempts=chunk_attempts,
            include_explanations=include_explanations,
            single_output=single_output,
        )

    if model_parallel == 1:
        model_outputs = [run_one_model(model) for model in models]
    else:
        output_by_model: dict[str, Path] = {}
        with ThreadPoolExecutor(max_workers=model_parallel) as executor:
            futures = {
                executor.submit(run_one_model, model): model
                for model in models
            }
            for future in as_completed(futures):
                model = futures[future]
                output_by_model[model] = future.result()
        model_outputs = [output_by_model[model] for model in models]

    return merge_model_outputs(
        model_output_paths=model_outputs,
        output_path=Path(output_dir) / "predictions.csv",
    )
