"""Replay recorded calculate_household calls through the harness's calculator
and the package's, and check that they answer alike.

    python scripts/replay_calculator_calls.py --runs DIR --board DIR --out DIR
        [--glob '*/*/mctest/households/*.json'] [--limit N] [--mcp]

``--runs`` holds the tool pilot's run folders; each household record under it
(``--glob``) keeps every call a model made: its arguments as written and the
result it was given. ``--board`` is the household set those runs used, whose
engine must be the installed one. For each distinct call (an arm's features
and the arguments' text) the script:

1. reads it with the harness's validator and the package's
   (``worker_request``, framed with the features as the pool frames it), and
   compares the two readings;
2. runs an accepted request on one shared engine through the harness's
   ``execute_request`` and the package's, and compares the two results;
3. compares the package's result with the result the run recorded. A recorded
   timeout, a call past the per-turn limit or a lost worker is infrastructure
   and is counted apart;
4. reads the arguments again as the JSON object an MCP client sends, and
   compares that reading with the first (``--mcp`` also sends every such call
   through the package's MCP server over stdio and compares the answer's
   text).

Steps 1, 2 and 4 are the gate: any difference exits 1. Step 3 is reported per
run folder, because the records come from several commits of the harness.

The development households are not public, so the records stay outside the
repository and this script writes nothing of theirs: ``--out`` gets
``progress.jsonl`` (one line of comparisons per distinct call, keyed by a
hash and appended as the call finishes, so a rerun resumes) and
``summary.json`` (counts only).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

import tool_pilot_argon as pilot  # noqa: E402

from policybench_calculator import core  # noqa: E402
from policybench_calculator.mcp_client import as_object  # noqa: E402

DEFAULT_GLOB = "*/*/mctest/households/*.json"
# Results a run recorded for a call the engine never answered.
INFRASTRUCTURE_ERRORS = ("timeout", "not_run", pilot.POOL_UNAVAILABLE)


def call_key(features: frozenset, arguments) -> str:
    text = json.dumps([sorted(features), arguments], sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def is_infrastructure(result) -> bool:
    if not isinstance(result, dict):
        return True
    if result.get("error") in INFRASTRUCTURE_ERRORS:
        return True
    return result.get("error") == "engine" and str(
        result.get("message", "")
    ).startswith("tool worker failed")


def recorded_calls(runs: Path, pattern: str = DEFAULT_GLOB) -> dict[str, dict]:
    """Every distinct calculator call under a runs folder: its features and
    arguments, the distinct results recorded for it, and where it was made."""
    calls: dict[str, dict] = {}
    for path in sorted(runs.glob(pattern)):
        record = json.loads(path.read_text())
        features = pilot.arm_features(record.get("arm"))
        if features is None:
            continue
        kept = record.get("tool_features")
        if kept is not None and sorted(features) != kept:
            raise SystemExit(f"{path}: arm {record['arm']} ran with features {kept}")
        folder = str(path.parent.parent.relative_to(runs))
        for turn in record.get("turns", []):
            for call in turn.get("calls", []):
                if call.get("name") != pilot.TOOL_NAME:
                    continue
                key = call_key(features, call.get("arguments"))
                entry = calls.setdefault(
                    key,
                    {
                        "features": features,
                        "arguments": call.get("arguments"),
                        "results": [],
                        "folders": Counter(),
                    },
                )
                entry["folders"][folder] += 1
                text = json.dumps(call.get("result"))
                if text not in entry["results"]:
                    entry["results"].append(text)
    return calls


def _framed(module, features: frozenset, arguments):
    """The message a pool sends its worker (ToolPool.call)."""
    return module.tool_call_frame(features, arguments) if features else arguments


def replay_one(
    system, registries: dict, entry: dict, simulation_cls=None
) -> tuple[dict, str]:
    """One distinct call through both copies (see the module docstring): the
    comparisons, and the package's answer text."""
    features, arguments = entry["features"], entry["arguments"]
    started = time.perf_counter()
    answers, readings, accepted = {}, {}, {}
    for module in (pilot, core):
        request, error = module.worker_request(
            _framed(module, features, arguments), registries[module]
        )
        readings[module] = json.dumps([request, error])
        accepted[module] = request is not None
        answers[module] = json.dumps(
            module.execute_request(system, registries[module], request, simulation_cls)
            if request is not None
            else error
        )
    line = {
        "accepted": accepted[core],
        "same_reading": readings[pilot] == readings[core],
        "same_result": answers[pilot] == answers[core],
    }
    recorded = entry["results"]
    answered = [text for text in recorded if not is_infrastructure(json.loads(text))]
    if answers[core] in recorded:
        line["recorded"] = "match"
    elif not answered:
        line["recorded"] = "infrastructure"
    else:
        line["recorded"] = "differs"
    sent = as_object(arguments)
    line["sendable"] = sent is not None
    if sent is not None and not isinstance(arguments, dict):
        request, error = core.worker_request(
            _framed(core, features, sent), registries[core]
        )
        line["same_as_object"] = json.dumps([request, error]) == readings[core]
    line["seconds"] = round(time.perf_counter() - started, 3)
    return line, answers[core]


def summarize(calls: dict[str, dict], lines: dict[str, dict]) -> dict:
    """Counts only: by run folder (each recorded call) and overall (each
    distinct call)."""
    folders: dict[str, Counter] = {}
    for key, entry in calls.items():
        line = lines.get(key)
        for folder, count in entry["folders"].items():
            tally = folders.setdefault(folder, Counter())
            tally["calls"] += count
            if line is None:
                tally["not_replayed"] += count
                continue
            tally["accepted" if line["accepted"] else "refused"] += count
            tally[f"recorded_{line['recorded']}"] += count
            tally["reading_differs"] += count * (not line["same_reading"])
            tally["result_differs"] += count * (not line["same_result"])
    done = [lines[key] for key in calls if key in lines]
    overall = Counter(
        distinct_calls=len(calls),
        replayed=len(done),
        recorded_calls=sum(sum(e["folders"].values()) for e in calls.values()),
    )
    for line in done:
        overall["accepted" if line["accepted"] else "refused"] += 1
        overall[f"recorded_{line['recorded']}"] += 1
        overall["reading_differs"] += not line["same_reading"]
        overall["result_differs"] += not line["same_result"]
        overall["sendable"] += line["sendable"]
        overall["object_reading_differs"] += line.get("same_as_object") is False
        overall["mcp_checked"] += "same_over_mcp" in line
        overall["mcp_differs"] += line.get("same_over_mcp") is False
    return {
        "overall": dict(overall),
        "folders": {name: dict(tally) for name, tally in sorted(folders.items())},
    }


def gate_failures(summary: dict) -> int:
    overall = summary["overall"]
    return sum(
        overall.get(name, 0)
        for name in (
            "reading_differs",
            "result_differs",
            "object_reading_differs",
            "mcp_differs",
        )
    ) + (overall["distinct_calls"] - overall["replayed"])


def replay(
    runs: Path,
    board: Path,
    out: Path,
    pattern: str = DEFAULT_GLOB,
    limit: int | None = None,
    over_mcp: bool = False,
    log=print,
    engine_for_tests: tuple | None = None,
) -> dict:
    """Replay every distinct call (see the module docstring); returns the
    summary it writes. ``engine_for_tests`` is (system, registries,
    simulation class) in place of the board's installed engine."""
    if engine_for_tests is None:
        pilot._require_engine(board)
    engine = pilot.board_engine(board)
    pilot.set_stated_engine(engine)
    core.set_stated_engine(engine)
    calls = recorded_calls(runs, pattern)
    out.mkdir(parents=True, exist_ok=True)
    progress = out / "progress.jsonl"
    lines: dict[str, dict] = {}
    if progress.exists():
        for text in progress.read_text().splitlines():
            line = json.loads(text)
            lines[line["key"]] = line
    todo = [key for key in calls if key not in lines][:limit]
    log(f"{len(calls)} distinct calls, {len(lines)} done before, {len(todo)} to replay")
    if todo:
        if engine_for_tests is not None:
            system, registries, simulation_cls = engine_for_tests
        else:
            simulation_cls = None
            system = pilot.build_tool_system(reform=True, snapshot=board)
            registries = {
                pilot: pilot.build_registry(system),
                core: core.build_registry(system),
            }
        if {n: vars(v) for n, v in registries[pilot].items()} != {
            n: vars(v) for n, v in registries[core].items()
        }:
            raise SystemExit("the two copies build different registries")
        sessions: dict[frozenset, object] = {}
        try:
            with progress.open("a") as handle:
                for index, key in enumerate(todo, start=1):
                    entry = calls[key]
                    line, answer = replay_one(system, registries, entry, simulation_cls)
                    line = {"key": key, **line}
                    if over_mcp and line["sendable"]:
                        line["same_over_mcp"] = (
                            _over_mcp(sessions, board, entry) == answer
                        )
                    lines[key] = line
                    handle.write(json.dumps(line) + "\n")
                    handle.flush()
                    if index % 100 == 0 or index == len(todo):
                        log(f"{index}/{len(todo)} replayed")
        finally:
            for session in sessions.values():
                session.close()
    summary = {
        "runs": str(runs),
        "glob": pattern,
        "board": str(board),
        "engine": f"policyengine-us {engine}",
        "harness_sha256": pilot._sha256(Path(pilot.__file__)),
        "core_sha256": pilot._sha256(Path(core.__file__)),
        **summarize(calls, lines),
    }
    summary["gate_failures"] = gate_failures(summary)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _server_parameters(board: Path, features: frozenset):
    """How to launch the package's MCP server for one feature set over stdio,
    on the board's engine, with one worker."""
    from mcp import StdioServerParameters

    arm = "pe:" + "+".join(sorted(features)) if features else "pe"
    return StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "policybench_calculator.mcp_server",
            *("--arm", arm, "--board", str(board), "--workers", "1"),
        ],
        cwd=str(ROOT),
        env=dict(os.environ),
    )


def _over_mcp(sessions: dict, board: Path, entry: dict) -> str:
    """The text the package's MCP server answers the call with: one server per
    feature set, kept open for the run."""
    from policybench_calculator.mcp_client import McpToolCall

    features = entry["features"]
    if features not in sessions:
        sessions[features] = McpToolCall(_server_parameters(board, features))
    return json.dumps(sessions[features](entry["arguments"])[0])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--glob", default=DEFAULT_GLOB)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--mcp", action="store_true")
    args = parser.parse_args(argv)
    summary = replay(args.runs, args.board, args.out, args.glob, args.limit, args.mcp)
    print(json.dumps(summary["overall"], indent=2))
    print(f"gate failures: {summary['gate_failures']}")
    return 1 if summary["gate_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
