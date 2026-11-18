"""The calculator's MCP server: the pilot's tool, and the pilot's answers.

The server must list the tool a model is given as a function tool for the
same arm (name, description, input schema) and answer every call with the
text the pilot returns for it, over each transport and both protocol eras the
SDK serves. The engine is faked (tests/calculator_mcp_fake.py), so a result is
a fixed function of the validated request; the validator and the worker pool
are the real ones.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "tests")]

import calculator_mcp_fake as fake  # noqa: E402
import tool_pilot_argon as pilot  # noqa: E402

from policybench_calculator import core, mcp_client, mcp_server  # noqa: E402

FAKE_SERVER = ROOT / "tests/calculator_mcp_fake.py"
needs_mcp = pytest.mark.skipif(
    importlib.util.find_spec("mcp") is None, reason="needs the mcp extra"
)

FLAT_HOUSEHOLD = {
    "state": "CA",
    "people": [
        {"role": "head", "facts": {"age": 40, "gross wages and salaries": 30000}},
        {"role": "dependent", "facts": {"age": 8}},
    ],
}
SITUATION = {
    "people": {"head": {"age": 40, "employment_income": 30000}, "kid": {"age": 8}},
    "households": {"home": {"members": ["head", "kid"], "state_code": "CA"}},
}
# Calls as a model writes them, by the arm that takes their shape: accepted,
# accepted with notes, explained, and refused in the validator's several ways.
CALLS = {
    "pe3": [
        {"household": FLAT_HOUSEHOLD, "variables": ["snap", "age"]},
        {"household": json.dumps(FLAT_HOUSEHOLD), "variables": ["snap"]},
        {
            "household": FLAT_HOUSEHOLD,
            "variables": ["snap"],
            "explain": ["snap"],
            "detail": "full",
            "period": "2026-01",
        },
        {"household": FLAT_HOUSEHOLD, "variables": ["telepathy"]},
        {"household": {"people": []}, "variables": ["snap"]},
        {"situation": SITUATION, "variables": ["snap"]},
        {"household": "{not json", "variables": ["snap"]},
        {},
    ],
    "pe": [
        {"situation": SITUATION, "variables": ["snap", "age"]},
        {"situation": json.dumps(SITUATION), "variables": ["snap"], "period": "2026"},
        {"situation": SITUATION, "variables": ["snap"], "explain": ["snap"]},
        {"situation": {"people": {"head": {"Age": 40}}}, "variables": ["age"]},
        {"household": FLAT_HOUSEHOLD, "variables": ["snap"]},
        {},
    ],
}
# Arguments the protocol cannot carry: not a JSON object.
UNSENDABLE = ["{not json", "[1, 2]", "", ["snap"], "x" * 400_001]


_ANSWERS: dict[tuple, str] = {}


def _pilot_answers(arm: str, calls) -> list[str]:
    """What the pilot returns a model for each call: its own pool's result,
    as its add_tool_result writes it. Each answer is computed once."""
    keys = [(arm, json.dumps(arguments)) for arguments in calls]
    if any(key not in _ANSWERS for key in keys):
        pool = pilot.ToolPool(
            size=1,
            timeout=fake.TIMEOUT_SECONDS,
            worker_target=fake.worker,
            tool_features=pilot.arm_features(arm),
        )
        try:
            for key, arguments in zip(keys, calls):
                if key not in _ANSWERS:
                    _ANSWERS[key] = json.dumps(pool.call(arguments)[0])
        finally:
            pool.close()
    return [_ANSWERS[key] for key in keys]


def _pilot_tool(arm: str, engine: str) -> dict:
    with pilot.stating_engine(engine):
        return pilot.calculate_tool_schema(features=pilot.arm_features(arm))["function"]


@pytest.mark.parametrize("arm", ["pe", "pe2", "pe3", "web+pe3", "pe:flat+names"])
def test_the_calculator_offers_the_pilots_tool(arm):
    calculator = fake.calculator(arm)
    assert calculator.engine == pilot.board_engine()
    assert calculator.tool == _pilot_tool(arm, calculator.engine)
    assert f"policyengine-us {calculator.engine}" in calculator.tool["description"]
    # The hash a household record of the pilot keeps for this arm's tool.
    profile = pilot.ModelProfile("m", "gpt-x", "chat", "tool", arm=arm)
    with pilot.stating_engine(calculator.engine):
        recorded = pilot.profile_treatment(profile)
    assert calculator.schema_sha256 == recorded["calculate_tool_sha256"]
    assert sorted(calculator.features) == recorded["tool_features"]


def test_a_calculator_states_its_boards_engine_whatever_else_is_stated():
    with core.stating_engine("9.9.9"):
        calculator = fake.calculator("pe3")
        assert "9.9.9" in core.calculate_tool_schema(1)["function"]["description"]
    assert "9.9.9" not in calculator.tool["description"]
    assert f"policyengine-us {pilot.board_engine()}" in calculator.tool["description"]
    assert core._STATED_ENGINE == {"version": core.REFERENCE_ENGINE}


@pytest.mark.parametrize("arm", sorted(CALLS))
def test_a_calculators_answer_is_the_pilots(arm):
    calculator = fake.calculator(arm)
    calculator.start()
    try:
        answers = [
            mcp_server.result_text(calculator.call(arguments)[0])
            for arguments in CALLS[arm]
        ]
        assert calculator.counters() == {"timeouts": 0, "crashes": 0, "lost": 0}
    finally:
        calculator.close()
    assert answers == _pilot_answers(arm, CALLS[arm])
    accepted = [text for text in answers if '"results"' in text]
    assert 2 <= len(accepted) < len(answers), "both outcomes are covered"


def test_the_calculator_refuses_an_engine_other_than_the_boards(monkeypatch):
    monkeypatch.setattr(
        core,
        "_versions",
        lambda: {"policyengine-us": "0.0.1", "policyengine-core": "0"},
    )
    with pytest.raises(SystemExit, match="policyengine-us 0.0.1 is installed"):
        mcp_server.Calculator(core.arm_features("pe3"), worker_target=fake.worker)


def test_a_calculator_whose_workers_do_not_start_says_so():
    calculator = mcp_server.Calculator(
        core.arm_features("pe"),
        workers=1,
        worker_target=fake.dead_worker,
        check_engine=False,
    )
    with pytest.raises(RuntimeError, match="workers did not start"):
        calculator.call({})
    calculator.close()


def test_the_provenance_names_the_engine_the_board_and_the_tool():
    calculator = fake.calculator("pe3")
    provenance = calculator.provenance()
    assert provenance["board_engine"] == f"policyengine-us {pilot.board_engine()}"
    assert provenance["policyengine-us"] == pilot._versions()["policyengine-us"]
    assert provenance["fix_module_sha256"] == pilot.FIX_MODULE_SHA256
    assert provenance["tool"] == pilot.TOOL_NAME
    assert provenance["tool_features"] == sorted(pilot.TOOL_FEATURES)
    assert provenance["calculate_tool_sha256"] == calculator.schema_sha256
    assert json.loads(json.dumps(provenance)) == provenance


def test_the_command_refuses_an_arm_without_a_calculator():
    for arm, message in (
        ("web", "has no calculator"),
        ("none", "has no calculator"),
        ("pe:telepathy", "unknown tool features"),
        ("pe:concise", "concise feature needs explain"),
    ):
        with pytest.raises(SystemExit, match=message):
            mcp_server.main(["--arm", arm])


def test_arguments_that_are_not_an_object_get_the_validators_refusal():
    """The protocol cannot carry them, so the client answers as the pilot's
    worker would have: the same refusal, whatever the arm's features."""
    assert [mcp_client.as_object(arguments) for arguments in UNSENDABLE] == [None] * 5
    assert mcp_client.as_object(None) is None
    assert mcp_client.as_object('{"variables": []}') == {"variables": []}
    assert mcp_client.as_object({"a": 1}) == {"a": 1}
    refusals = [
        json.dumps(core.normalize_request(arguments, {})[1]) for arguments in UNSENDABLE
    ]
    for arm in ("pe", "pe3"):
        assert refusals == _pilot_answers(arm, UNSENDABLE)
    # No arguments at all (None) get the same refusal from a pool that frames
    # its messages, as every arm with a feature does. The pilot's version 1
    # pool sends arguments bare, and a bare None is its worker's stop signal,
    # so there the pilot reports a failed worker instead; the client does not
    # copy that.
    nothing = json.dumps(core.normalize_request(None, {})[1])
    assert [nothing] == _pilot_answers("pe3", [None])
    assert "tool worker failed" in _pilot_answers("pe", [None])[0]


# ---------------------------------------------------------------------------
# Over the protocol.
# ---------------------------------------------------------------------------


def _text(result) -> str:
    assert result.is_error is False
    assert result.structured_content is None
    (block,) = result.content
    assert block.type == "text"
    return block.text


def _listed(tools) -> dict:
    (tool,) = tools
    assert tool.output_schema is None
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.input_schema,
    }


@needs_mcp
@pytest.mark.parametrize("arm", sorted(CALLS))
def test_the_server_lists_the_pilots_tool_and_gives_the_pilots_answers(arm):
    import anyio
    from mcp import Client, MCPError

    calculator = fake.calculator(arm)
    server = mcp_server.build_server(calculator)
    seen = {}

    async def session():
        async with Client(server, raise_exceptions=True) as client:
            seen["tool"] = _listed((await client.list_tools()).tools)
            seen["answers"] = [
                _text(await client.call_tool(pilot.TOOL_NAME, arguments))
                for arguments in CALLS[arm]
            ]
            seen["no arguments"] = _text(await client.call_tool(pilot.TOOL_NAME))
            with pytest.raises(MCPError, match="Unknown tool"):
                await client.call_tool("submit_outputs", {})
            (resource,) = (await client.list_resources()).resources
            assert resource.uri == mcp_server.PROVENANCE_URI
            (contents,) = (await client.read_resource(resource.uri)).contents
            seen["provenance"] = json.loads(contents.text)
            seen["server"] = client.server_info

    calculator.start()
    try:
        anyio.run(session)
    finally:
        calculator.close()
    assert seen["tool"] == _pilot_tool(arm, calculator.engine)
    assert seen["answers"] == _pilot_answers(arm, CALLS[arm])
    assert seen["no arguments"] == _pilot_answers(arm, [{}])[0]
    assert seen["provenance"] == calculator.provenance()
    assert seen["server"].name == mcp_server.SERVER_NAME
    assert calculator.engine in seen["server"].description


@needs_mcp
def test_a_pool_with_no_worker_is_a_protocol_error_not_an_answer(monkeypatch):
    import anyio
    from mcp import Client, MCPError

    calculator = fake.calculator("pe")
    unavailable = {
        "error": core.POOL_UNAVAILABLE,
        "message": "no tool worker is available",
    }
    monkeypatch.setattr(calculator, "call", lambda arguments: (unavailable, 0.0))

    async def session():
        async with Client(mcp_server.build_server(calculator)) as client:
            with pytest.raises(MCPError, match="no tool worker is available"):
                await client.call_tool(pilot.TOOL_NAME, CALLS["pe"][0])

    anyio.run(session)
    with mcp_client.McpToolCall(mcp_server.build_server(calculator)) as tool_call:
        result, _ = tool_call(CALLS["pe"][0])
    assert result["error"] == pilot.POOL_UNAVAILABLE


def _launch(arm: str):
    from mcp import StdioServerParameters

    return StdioServerParameters(
        command=sys.executable,
        args=[str(FAKE_SERVER), "stdio", arm],
        env=dict(os.environ),
    )


@needs_mcp
def test_over_stdio_the_handshake_era_reads_the_same_tool_and_answers():
    """A 2025-era client (initialize, then tools/list and tools/call) over the
    stdio transport, with the server in its own process."""
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    arm, seen = "pe3", {}

    async def session():
        async with stdio_client(_launch(arm)) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as client:
                seen["version"] = (await client.initialize()).protocol_version
                seen["tool"] = _listed((await client.list_tools()).tools)
                seen["answers"] = [
                    _text(await client.call_tool(pilot.TOOL_NAME, arguments))
                    for arguments in CALLS[arm]
                ]

    anyio.run(session)
    assert seen["version"] == "2025-11-25"
    assert seen["tool"] == _pilot_tool(arm, pilot.board_engine())
    assert seen["answers"] == _pilot_answers(arm, CALLS[arm])


@pytest.fixture
def http_server():
    """The fake-engine server over Streamable HTTP on a free local port."""
    with socket.socket() as probe:
        probe.bind((mcp_server.LOOPBACK, 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, str(FAKE_SERVER), "http", "pe3", str(port)],
        env=dict(os.environ),
    )
    try:
        deadline = time.monotonic() + 120
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"the server exited with {process.returncode}")
            try:
                socket.create_connection((mcp_server.LOOPBACK, port), 0.5).close()
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError("the server did not open its port") from None
                time.sleep(0.2)
        yield f"http://{mcp_server.LOOPBACK}:{port}/mcp"
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()


@needs_mcp
def test_over_http_both_protocol_eras_read_the_same_tool_and_answers(http_server):
    import anyio
    from mcp import Client, ClientSession
    from mcp.client.streamable_http import streamable_http_client

    arm, seen = "pe3", {}

    async def modern():
        async with Client(http_server) as client:
            seen["modern version"] = client.protocol_version
            seen["modern tool"] = _listed((await client.list_tools()).tools)
            seen["modern answers"] = [
                _text(await client.call_tool(pilot.TOOL_NAME, arguments))
                for arguments in CALLS[arm]
            ]

    async def handshake():
        async with streamable_http_client(http_server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as client:
                seen["handshake version"] = (await client.initialize()).protocol_version
                seen["handshake tool"] = _listed((await client.list_tools()).tools)
                seen["handshake answers"] = [
                    _text(await client.call_tool(pilot.TOOL_NAME, arguments))
                    for arguments in CALLS[arm]
                ]

    anyio.run(modern)
    anyio.run(handshake)
    assert seen["modern version"] == "2026-07-28"
    assert seen["handshake version"] == "2025-11-25"
    tool, answers = (
        _pilot_tool(arm, pilot.board_engine()),
        _pilot_answers(arm, CALLS[arm]),
    )
    assert seen["modern tool"] == seen["handshake tool"] == tool
    assert seen["modern answers"] == seen["handshake answers"] == answers


@needs_mcp
@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_the_client_is_a_tool_call_for_the_pilots_loop(mode):
    """McpToolCall has ToolPool.call's shape, and gives its results: for
    arguments written as an object, as JSON text, and as text the protocol
    cannot carry."""
    arm = "pe3"
    calls = [
        *CALLS[arm],
        *[json.dumps(arguments) for arguments in CALLS[arm]],
        *UNSENDABLE,
        None,
    ]
    with mcp_client.McpToolCall(_launch(arm), mode=mode) as tool_call:
        assert tool_call.tool() == _pilot_tool(arm, pilot.board_engine())
        assert tool_call.provenance()["tool_features"] == sorted(pilot.TOOL_FEATURES)
        results = [tool_call(arguments) for arguments in calls]
        version = tool_call.protocol_version
    assert version == ("2025-11-25" if mode == "legacy" else "2026-07-28")
    assert all(isinstance(seconds, float) and seconds >= 0 for _, seconds in results)
    assert [json.dumps(result) for result, _ in results] == _pilot_answers(arm, calls)


def test_the_schema_hash_is_the_sorted_dumps_sha256():
    calculator = fake.calculator("pe")
    assert (
        calculator.schema_sha256
        == hashlib.sha256(
            json.dumps(calculator.schema, sort_keys=True).encode()
        ).hexdigest()
    )
