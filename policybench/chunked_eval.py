"""Chunked, resumable orchestration for no-tools model evaluations.

Each chunk runs in its own ``python -m policybench.cli eval-no-tools``
subprocess, whose resume sidecar records ``policyengine_bundles``. An
invocation computes those bundles once, in a fresh interpreter, into
``<output_dir>/policyengine_provenance.json`` and hands the file to its chunk
workers through ``POLICYBENCH_POLICYENGINE_PROVENANCE`` (see
:class:`PolicyEngineProvenanceHandoff`), so a worker that only calls an LLM
does not import policyengine.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from policybench.config import DEFAULT_PROGRAM_SET, MODELS, get_programs
from policybench.eval_no_tools import _scenario_countries, is_infrastructure_error_text
from policybench.policyengine_runtime import (
    POLICYENGINE_PROVENANCE_ENV,
    POLICYENGINE_PROVENANCE_FILENAME,
    read_written_policyengine_bundles,
    run_policyengine_provenance_writer,
)
from policybench.scenarios import load_scenarios_from_manifest
from policybench.spec import expand_programs_for_scenario
from policybench.spend_ledger import (
    read_spend_ledger,
    replace_spend_ledger,
    spend_ledger_path,
)

SERIAL_ONLY_MODEL_PREFIXES = ("claude-",)


@dataclass(frozen=True)
class ScenarioChunk:
    start: int
    end: int
    path: Path


class PolicyEngineProvenanceHandoff:
    """PolicyEngine provenance computed at most once for an invocation's chunks.

    The first :meth:`worker_env` call writes
    ``<output_dir>/policyengine_provenance.json`` from a fresh interpreter, as
    the supervisor does for its run; every call returns the environment for a
    chunk worker, pointing at the file once it was written and read back.
    Workers reuse the file only when its fingerprint equals their own and
    compute the bundles themselves otherwise, as they did before the file
    existed. Nothing is written until a chunk needs to run, so a pass that
    only merges finished chunks does not import policyengine.

    Unlike the supervisor, an earlier file is not deleted before writing,
    because the runbook runs several invocations on one output dir at once.
    The writer replaces it atomically, and this invocation hands it on only
    after its own writer succeeded. Another invocation can still replace or
    remove the file while this one's workers run (a writer whose own check
    fails removes it); a worker that then finds it missing or written for a
    different environment computes the bundles itself.
    """

    def __init__(self, output_dir: str | Path, *, python: str | None = None):
        self.path = (Path(output_dir) / POLICYENGINE_PROVENANCE_FILENAME).resolve()
        # The interpreter run_chunk starts; the fingerprint records it.
        self.python = python or sys.executable
        self.countries: list[str] | None = None
        self.bundles: dict | None = None
        self._lock = threading.Lock()

    def worker_env(self, countries: Iterable[str]) -> dict[str, str]:
        """Environment for chunk workers whose scenarios cover ``countries``.

        Thread-safe: model threads share one handoff, and the first caller
        writes the file while the others wait for it.
        """
        wanted = sorted({country.lower() for country in countries})
        # Only a file this invocation wrote may reach its workers.
        env = {
            key: value
            for key, value in os.environ.items()
            if key != POLICYENGINE_PROVENANCE_ENV
        }
        with self._lock:
            if self.countries is None:
                self.countries = wanted
                self.bundles = self._write(wanted, dict(env))
                if self.bundles is None:
                    print(
                        "PolicyEngine provenance not handed off; chunk workers "
                        "compute it themselves."
                    )
                else:
                    print(f"PolicyEngine provenance for chunk workers: {self.path}")
        if self.bundles is not None and wanted == self.countries:
            env[POLICYENGINE_PROVENANCE_ENV] = str(self.path)
        return env

    def _write(self, countries: list[str], env: dict[str, str]) -> dict | None:
        # Each worker computes its chunk's countries in a fresh process, and
        # which branch records the US bundle can depend on what the same
        # process looked up first, so, as for supervised runs, only
        # single-country chunks are handed a file. eval-no-tools rejects a
        # manifest whose scenarios differ from --country, so every chunk of a
        # runnable invocation is single-country.
        if len(countries) != 1:
            return None
        if not run_policyengine_provenance_writer(
            self.python, self.path, countries, env
        ):
            return None
        return read_written_policyengine_bundles(self.path, countries)


def expected_rows(*, scenario_program_counts: list[int]) -> int:
    return sum(scenario_program_counts)


def model_requires_serial_execution(model: str) -> bool:
    """Return whether model calls must run on the main thread."""
    return model.startswith(SERIAL_ONLY_MODEL_PREFIXES)


def chunk_is_complete(
    path: Path,
    *,
    scenario_program_counts: list[int],
    require_explanations: bool = True,
) -> bool:
    """Return whether a chunk wrote the expected rows.

    Missing predictions and missing explanations are valid benchmark outcomes
    when they come from model output/contract failures. Provider transport
    failures remain incomplete so the orchestration layer can retry/resume.
    """
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
    required_columns = {"model", "scenario_id", "variable", "prediction"}
    if not required_columns.issubset(frame.columns):
        return False
    if require_explanations and "explanation" not in frame.columns:
        return False
    if "error" in frame.columns:
        errors = frame["error"].fillna("").astype(str)
        if errors.map(is_infrastructure_error_text).any():
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
    env: dict[str, str] | None = None,
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

    subprocess.run(cmd, check=True, env=env)


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
    env: dict[str, str] | None = None,
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
                env=env,
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
    _merge_spend_ledgers(chunk_paths, output_path)
    print(f"Wrote {output_path} ({len(merged):,} rows)")


def _merge_spend_ledgers(input_paths: list[Path], output_path: Path) -> None:
    records = [
        record
        for path in input_paths
        for record in read_spend_ledger(spend_ledger_path(path))
    ]
    replace_spend_ledger(spend_ledger_path(output_path), records)


def merge_model_outputs(*, model_output_paths: list[Path], output_path: Path) -> Path:
    frames = [pd.read_csv(path) for path in model_output_paths]
    merged = pd.concat(frames, ignore_index=True)
    duplicate_count = merged.duplicated(["model", "scenario_id", "variable"]).sum()
    if duplicate_count:
        raise ValueError(f"Combined output has {duplicate_count} duplicate rows.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)
    _merge_spend_ledgers(model_output_paths, output_path)
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
    provenance: PolicyEngineProvenanceHandoff | None = None,
) -> Path:
    """Run a model's pending chunks, then merge its chunks into one CSV.

    ``provenance`` is shared by every model of one invocation; without one,
    this call hands its own chunk workers a file in ``output_dir``.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    if parallel <= 0:
        raise ValueError("parallel must be positive.")
    if chunk_attempts <= 0:
        raise ValueError("chunk_attempts must be positive.")
    if model not in MODELS:
        valid = ", ".join(sorted(MODELS))
        raise ValueError(f"Unknown model '{model}'. Valid models: {valid}.")
    if model_requires_serial_execution(model) and parallel != 1:
        raise ValueError(
            f"{model} must run with --parallel 1. Its provider calls need the "
            "main-thread wall timeout; run Claude models separately from "
            "parallel non-Claude models."
        )

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
    worker_env = None
    if pending:
        if provenance is None:
            provenance = PolicyEngineProvenanceHandoff(output_dir)
        worker_env = provenance.worker_env(_scenario_countries(scenarios))

    if pending and parallel == 1:
        for chunk in pending:
            run_chunk_with_retries(
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
                env=worker_env,
            )
    elif pending:
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
                    env=worker_env,
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
    serial_models = [
        model for model in models if model_requires_serial_execution(model)
    ]
    if serial_models and model_parallel != 1:
        raise ValueError(
            "Claude models must run with --model-parallel 1 so provider calls "
            "stay on the main thread for wall-timeout enforcement. Run these "
            f"models separately: {', '.join(serial_models)}."
        )
    provenance = PolicyEngineProvenanceHandoff(output_dir)

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
            provenance=provenance,
        )

    if model_parallel == 1:
        model_outputs = [run_one_model(model) for model in models]
    else:
        output_by_model: dict[str, Path] = {}
        with ThreadPoolExecutor(max_workers=model_parallel) as executor:
            futures = {executor.submit(run_one_model, model): model for model in models}
            for future in as_completed(futures):
                model = futures[future]
                output_by_model[model] = future.result()
        model_outputs = [output_by_model[model] for model in models]

    return merge_model_outputs(
        model_output_paths=model_outputs,
        output_path=Path(output_dir) / "predictions.csv",
    )
