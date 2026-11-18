"""A calculator MCP server on a fake engine, for the transport tests.

    python tests/calculator_mcp_fake.py stdio ARM
    python tests/calculator_mcp_fake.py http ARM PORT

The validator is the real one; only the engine is faked, so the tests need no
policyengine-us and a call's result is a fixed function of its request.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from policybench_calculator import core  # noqa: E402
from policybench_calculator.mcp_server import (  # noqa: E402
    Calculator,
    serve_http,
    serve_stdio,
)

TIMEOUT_SECONDS = 60.0
V = core.VariableInfo
REGISTRY = {
    "age": V("person", "int", "age", "year"),
    "employment_income": V("person", "float", "employment income", "year"),
    "is_tax_unit_head": V("person", "bool", "head", "year"),
    "is_tax_unit_spouse": V("person", "bool", "spouse", "year"),
    "snap": V("spm_unit", "float", "SNAP", "month", computed=True),
    "state_code": V("household", "Enum", "state", "year", ("CA", "LA")),
    "hours_worked_last_week": V("person", "float", "hours", "year"),
    "weekly_hours_worked_before_lsr": V("person", "float", "hours", "year"),
}


def fake_result(request: dict) -> dict:
    """A result in the engine's shape, fixed by the request alone."""
    out = {
        "results": {
            name: {
                "entity": REGISTRY[name].entity,
                "label": REGISTRY[name].label,
                "period": request["period"],
                "values": {"first": len(name) + 0.25, "second": None},
            }
            for name in request["variables"]
        }
    }
    if "notes" in request:
        out["notes"] = list(request["notes"])
    if request.get("explain"):
        out["explanations"] = {
            name: {"steps": [f"{name} ({request['period']}) = 1.0"], "parameters": []}
            for name in request["explain"]
        }
    return out


# The labels the prompts show three of these facts under. A worker reads them
# from this table, not from the benchmark's own (core.prompt_labels), which
# loads the engine's data to list the promptable inputs.
LABELS = {
    "gross wages and salaries": "employment_income",
    "usual weekly hours worked": "hours_worked_last_week",
    "state": "state_code",
}


def _labels() -> dict:
    return {
        core._label_key(label): frozenset({(name, False)})
        for label, name in LABELS.items()
    }


def worker(conn, fix_path, reform, board=None):
    """The pilot's worker loop (core._worker_main) without the engine."""
    core.prompt_labels = _labels
    conn.send(("ready", None))
    while True:
        try:
            args = conn.recv()
        except EOFError:
            return
        if args is None:
            return
        request, error = core.worker_request(args, REGISTRY)
        conn.send(("ok", error if error is not None else fake_result(request)))


def dead_worker(conn, fix_path, reform, board=None):
    """A worker that never reports ready."""
    conn.close()


def calculator(arm: str) -> Calculator:
    return Calculator(
        core.arm_features(arm),
        workers=1,
        timeout=TIMEOUT_SECONDS,
        worker_target=worker,
        check_engine=False,
    )


if __name__ == "__main__":
    import anyio

    transport, arm = sys.argv[1], sys.argv[2]
    if transport == "http":
        anyio.run(serve_http, calculator(arm), int(sys.argv[3]))
    else:
        anyio.run(serve_stdio, calculator(arm))
