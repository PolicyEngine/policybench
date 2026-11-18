"""Replay recorded calls through the harness's calculator and the package's.

``scripts/replay_calculator_calls.py`` reads the tool pilot's household
records and checks that both copies read and answer every recorded call
alike. The development households are not public, so their records are not in
the repository: the last test here reads them from folders named by
``POLICYBENCH_RECORDED_RUNS`` and ``POLICYBENCH_RECORDED_BOARD`` and skips
without them. The tests before it check the script itself on records written
here, with a fake engine.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "tests")]

import replay_calculator_calls as replay  # noqa: E402
import tool_pilot_argon as pilot  # noqa: E402

from policybench_calculator import core  # noqa: E402

VARIABLES = {
    "age": ("person", "int", "age", "year"),
    "employment_income": ("person", "float", "employment income", "year"),
    "snap": ("spm_unit", "float", "SNAP", "month", None, True),
    "state_code": ("household", "Enum", "state", "year", ("CA", "LA")),
}
REGISTRIES = {
    module: {name: module.VariableInfo(*fields) for name, fields in VARIABLES.items()}
    for module in (pilot, core)
}
SITUATION = {
    "people": {"head": {"age": 40, "employment_income": 30000}},
    "households": {"home": {"members": ["head"], "state_code": "CA"}},
}
ACCEPTED = json.dumps({"situation": SITUATION, "variables": ["snap"]})
REFUSED = json.dumps({"situation": SITUATION, "variables": ["telepathy"]})
WRITTEN = json.dumps(
    {"situation": {"people": {"head": {"Age": 40}}}, "variables": ["age"]}
)


class FakeSimulation:
    def __init__(self, tax_benefit_system, situation):
        self.populations = {
            "person": SimpleNamespace(ids=list(situation["people"])),
            "spm_unit": SimpleNamespace(ids=["spm"]),
        }

    def calculate(self, name, period):
        return [1234.567] if name == "snap" else [40.0]


def _answer(arm: str, arguments) -> dict:
    features = pilot.arm_features(arm)
    message = pilot.tool_call_frame(features, arguments) if features else arguments
    request, error = pilot.worker_request(message, REGISTRIES[pilot])
    if request is None:
        return error
    return pilot.execute_request(None, REGISTRIES[pilot], request, FakeSimulation)


def _record(folder: Path, name: str, arm: str, calls: list[tuple]) -> None:
    features = pilot.arm_features(arm)
    record = {
        "scenario_id": name,
        "arm": arm,
        "turns": [
            {
                "calls": [
                    {"name": pilot.TOOL_NAME, "arguments": arguments, "result": result}
                    for arguments, result in calls
                ]
                + [{"name": "submit_outputs", "arguments": "{}", "result": None}]
            }
        ],
    }
    if arm != "pe":
        # A version 1 record written before records kept their features has
        # none; an arm without the calculator records None.
        record["tool_features"] = None if features is None else sorted(features)
    (folder / "households").mkdir(parents=True, exist_ok=True)
    (folder / "households" / f"{name}.json").write_text(json.dumps(record))


@pytest.fixture
def runs(tmp_path):
    """Two run folders: version 1 calls, one of them recorded as a timeout and
    one with a result no engine here gives; and names-feature calls."""
    timeout = {"error": "timeout", "message": "the calculation exceeded 60 seconds"}
    stale = {"results": {"snap": {"values": {"spm": 1.0}}}}
    _record(
        tmp_path / "runs/model-a/pe/mctest",
        "mt_000",
        "pe",
        [
            (ACCEPTED, _answer("pe", ACCEPTED)),
            (ACCEPTED, _answer("pe", ACCEPTED)),
            (REFUSED, _answer("pe", REFUSED)),
            (WRITTEN, timeout),
        ],
    )
    _record(
        tmp_path / "runs/model-a/pe/mctest",
        "mt_001",
        "pe",
        [(ACCEPTED, timeout), ("{not json", _answer("pe", "{not json"))],
    )
    _record(
        tmp_path / "runs/model-b/abl-add-names/mctest",
        "mt_000",
        "pe:names",
        [(WRITTEN, _answer("pe:names", WRITTEN)), (ACCEPTED, stale)],
    )
    _record(tmp_path / "runs/model-b/none/mctest", "mt_000", "none", [])
    return tmp_path / "runs"


def _replay(runs, out, **options):
    return replay.replay(
        runs,
        pilot.SNAPSHOT,
        out,
        log=lambda text: None,
        engine_for_tests=(None, REGISTRIES, FakeSimulation),
        **options,
    )


def test_the_replay_counts_each_call_and_passes_the_gate(runs, tmp_path):
    summary = _replay(runs, tmp_path / "out")
    assert summary["gate_failures"] == 0
    overall = summary["overall"]
    # Six distinct calls: four under version 1 (the accepted one, made three
    # times, counts once) and two under the names feature.
    assert overall["distinct_calls"] == overall["replayed"] == 6
    assert overall["recorded_calls"] == 8
    assert overall["accepted"] == 3 and overall["refused"] == 3
    assert overall["recorded_match"] == 4
    assert overall["recorded_infrastructure"] == 1
    assert overall["recorded_differs"] == 1
    assert overall["sendable"] == 5 and overall["object_reading_differs"] == 0
    assert summary["folders"] == {
        "model-a/pe/mctest": {
            "calls": 6,
            "accepted": 3,
            "refused": 3,
            "recorded_match": 5,
            "recorded_infrastructure": 1,
            "reading_differs": 0,
            "result_differs": 0,
        },
        "model-b/abl-add-names/mctest": {
            "calls": 2,
            "accepted": 2,
            "recorded_match": 1,
            "recorded_differs": 1,
            "reading_differs": 0,
            "result_differs": 0,
        },
    }
    assert json.loads((tmp_path / "out/summary.json").read_text()) == summary


def test_a_rerun_resumes_from_its_progress_file(runs, tmp_path):
    first = _replay(runs, tmp_path / "out", limit=2)
    assert first["overall"]["replayed"] == 2
    assert first["gate_failures"] == 4, "calls not yet replayed fail the gate"
    lines = (tmp_path / "out/progress.jsonl").read_text().splitlines()
    assert len(lines) == 2
    second = _replay(runs, tmp_path / "out")
    assert second["overall"]["replayed"] == 6 and second["gate_failures"] == 0
    resumed = (tmp_path / "out/progress.jsonl").read_text().splitlines()
    assert resumed[:2] == lines and len(resumed) == 6


def test_a_copy_that_answers_differently_fails_the_gate(runs, tmp_path, monkeypatch):
    def rounds_differently(system, registry, request, simulation_cls=None):
        result = pilot.execute_request(system, registry, request, simulation_cls)
        for entry in result["results"].values():
            entry["values"] = {k: round(v) for k, v in entry["values"].items()}
        return result

    monkeypatch.setattr(core, "execute_request", rounds_differently)
    summary = _replay(runs, tmp_path / "out")
    assert summary["overall"]["result_differs"] == 3
    assert summary["gate_failures"] == 3


def test_the_command_exits_1_when_the_gate_fails(monkeypatch, capsys):
    arguments = ["--runs", "runs", "--board", "board", "--out", "out"]
    for failures in (0, 2):
        monkeypatch.setattr(
            replay,
            "replay",
            lambda *args, failures=failures: {
                "overall": {"distinct_calls": 5},
                "gate_failures": failures,
            },
        )
        assert replay.main(arguments) == (1 if failures else 0)
    assert "gate failures: 2" in capsys.readouterr().out


def test_the_mcp_path_sends_each_sendable_call_through_a_server(
    runs, tmp_path, monkeypatch
):
    """With --mcp every call the protocol can carry also goes through an MCP
    server, one per feature set, and a different answer fails the gate. The
    server launched here is the fake-engine one, whose results differ from
    this test's fake engine by design: so the refusals, which come from the
    validator alone, must match, and every accepted call must be caught."""
    from mcp import StdioServerParameters

    launched = []

    def fake_server(board, features):
        arm = "pe:" + "+".join(sorted(features)) if features else "pe"
        launched.append(arm)
        return StdioServerParameters(
            command=sys.executable,
            args=[str(ROOT / "tests/calculator_mcp_fake.py"), "stdio", arm],
            env=dict(os.environ),
        )

    monkeypatch.setattr(replay, "_server_parameters", fake_server)
    summary = _replay(runs, tmp_path / "out", over_mcp=True)
    overall = summary["overall"]
    assert sorted(launched) == ["pe", "pe:names"]
    assert overall["mcp_checked"] == overall["sendable"] == 5
    assert overall["mcp_differs"] == overall["accepted"] == 3
    assert summary["gate_failures"] == 3
    lines = [
        json.loads(text)
        for text in (tmp_path / "out/progress.jsonl").read_text().splitlines()
    ]
    sent = [line for line in lines if line["sendable"]]
    unsent = [line for line in lines if not line["sendable"]]
    assert len(sent) == 5 and len(unsent) == 1
    assert "same_over_mcp" not in unsent[0]
    assert all(line["same_over_mcp"] for line in sent if not line["accepted"])
    assert not any(line["same_over_mcp"] for line in sent if line["accepted"])
    assert all("answer" not in line for line in lines)


def test_the_real_server_is_launched_on_the_board_with_the_calls_features():
    board = pilot.SNAPSHOT
    for features, arm in (
        (frozenset(), "pe"),
        (frozenset({"names", "flat"}), "pe:flat+names"),
        (frozenset(pilot.TOOL_FEATURES), "pe:" + "+".join(sorted(pilot.TOOL_FEATURES))),
    ):
        parameters = replay._server_parameters(board, features)
        assert parameters.command == sys.executable
        assert parameters.args[:2] == ["-m", "policybench_calculator.mcp_server"]
        assert parameters.args[2:] == [
            *("--arm", arm, "--board", str(board), "--workers", "1")
        ]
        assert core.arm_features(arm) == features
        assert parameters.cwd == str(ROOT)


def test_a_record_whose_features_are_not_its_arms_is_refused(runs):
    path = runs / "model-b/abl-add-names/mctest/households/mt_000.json"
    record = json.loads(path.read_text())
    record["tool_features"] = ["flat"]
    path.write_text(json.dumps(record))
    with pytest.raises(SystemExit, match="ran with features"):
        replay.recorded_calls(runs)


def test_recorded_infrastructure_results_are_told_apart():
    assert replay.is_infrastructure({"error": "timeout", "message": "..."})
    assert replay.is_infrastructure({"error": "not_run", "message": "..."})
    assert replay.is_infrastructure({"error": pilot.POOL_UNAVAILABLE})
    assert replay.is_infrastructure(
        {"error": "engine", "message": "tool worker failed: "}
    )
    assert replay.is_infrastructure(None)
    assert not replay.is_infrastructure({"error": "engine", "message": "ValueError: x"})
    assert not replay.is_infrastructure({"error": "validation", "problems": []})
    assert not replay.is_infrastructure({"results": {}})


@pytest.mark.slow
def test_the_recorded_development_calls_replay_alike(tmp_path):
    """Every call the development runs recorded, on the board's engine."""
    runs = os.environ.get("POLICYBENCH_RECORDED_RUNS")
    board = os.environ.get("POLICYBENCH_RECORDED_BOARD")
    if not (runs and board):
        pytest.skip("set POLICYBENCH_RECORDED_RUNS and POLICYBENCH_RECORDED_BOARD")
    if pilot._versions()["policyengine-us"] != pilot.board_engine(Path(board)):
        pytest.skip("the installed policyengine-us is not the board's")
    out = Path(os.environ.get("POLICYBENCH_REPLAY_OUT") or tmp_path / "replay")
    summary = replay.replay(Path(runs), Path(board), out)
    assert summary["overall"]["distinct_calls"] > 0
    assert summary["gate_failures"] == 0, summary["overall"]
