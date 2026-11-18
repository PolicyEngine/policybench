"""Offer the PolicyBench calculator over the Model Context Protocol.

    python -m policybench_calculator.mcp_server --arm pe3 [--board DIR]
        [--transport stdio|http] [--port 8765] [--workers 2]

The server has one tool, ``calculate_household``, with the name, description
and input schema the tool pilot gives a model as a function tool for the same
arm (``core.calculate_tool_schema``), and it answers a call with the text the
pilot returns for it (``json.dumps`` of the result). A call runs as the
pilot's does: validated by ``core.normalize_request`` under the arm's
features, then on the board's pinned policyengine-us and convention reform in
a worker process under a timeout (``core.ToolPool``). The server refuses to
start unless the installed policyengine-us is the board's.

What a client reads besides the tool:

- the tool's description states the engine, as the function tool's does;
- the server's name, version (this package's) and description (which names
  the engine) in the protocol's server information;
- the resource ``policybench://calculator/provenance``: the installed engine,
  the board and its pinned reform, the arm's features and the sha256 of the
  tool schema, in the form the pilot's household records keep it
  (``calculate_tool_sha256``).

Two things differ from the function tool by the protocol's nature. The
arguments arrive as a JSON object, so text that is not one never reaches the
server (:mod:`policybench_calculator.mcp_client` answers it as the validator
would). And the pilot's limits on a household (8 tool turns, 4 calculations a
turn) belong to its conversation loop, not to the calculator, so the server
does not apply them.

The http transport listens on 127.0.0.1 only and has no authentication: it is
for a client on this machine. Nothing here is meant to face the internet.

Needs the ``mcp`` extra (``pip install policybench[mcp]``).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable

from policybench_calculator import core

SERVER_NAME = "policybench-calculator"
SERVER_TITLE = "PolicyBench household calculator"
PROVENANCE_URI = "policybench://calculator/provenance"
DEFAULT_ARM = "pe3"
DEFAULT_PORT = 8765
DEFAULT_WORKERS = 2
LOOPBACK = "127.0.0.1"


def _quiet_worker(conn, fix_path: str, reform: bool, board: str | None = None) -> None:
    """The pilot's worker with its standard output pointed at standard error.

    Under the stdio transport the server's standard output is the wire, and a
    worker inherits it; anything the engine printed there would corrupt the
    protocol."""
    os.dup2(2, 1)
    core._worker_main(conn, fix_path, reform, board)


def result_text(result: dict) -> str:
    """A result as the pilot returns it to a model (its ``add_tool_result``)."""
    return json.dumps(result)


class Calculator:
    """One arm's calculator: the tool as a model is shown it, and the workers
    that run it.

    ``start`` builds the worker pool in the background (an engine worker takes
    about a minute to start), so a client can list the tool at once; a call
    waits for the pool.
    """

    def __init__(
        self,
        features: frozenset,
        board: Path = core.SNAPSHOT,
        workers: int = DEFAULT_WORKERS,
        timeout: float = core.TOOL_TIMEOUT_SECONDS,
        worker_target: Callable | None = None,
        check_engine: bool = True,
    ):
        self.features = core.frame_features(tuple(sorted(features)))
        self.board = Path(board)
        if check_engine:
            core._require_engine(self.board)
        self.engine = core.board_engine(self.board)
        self.workers = workers
        self.timeout = timeout
        self._worker_target = worker_target or _quiet_worker
        # The texts state the board's engine, as the pilot's run command sets it.
        with core.stating_engine(self.engine):
            self.schema = core.calculate_tool_schema(features=self.features)
        self._pool: core.ToolPool | None = None
        self._failure: BaseException | None = None
        self._ready = threading.Event()
        self._starting: threading.Thread | None = None

    @property
    def tool(self) -> dict:
        """The tool's name, description and input schema."""
        return self.schema["function"]

    @property
    def schema_sha256(self) -> str:
        """The schema's hash as the pilot's household records keep it
        (``profile_treatment``: sorted keys)."""
        return hashlib.sha256(
            json.dumps(self.schema, sort_keys=True).encode()
        ).hexdigest()

    def provenance(self) -> dict:
        try:
            package = importlib.metadata.version("policybench")
        except importlib.metadata.PackageNotFoundError:
            package = None
        versions = core._versions()
        return {
            "server": SERVER_NAME,
            "policybench": package,
            "policyengine-us": versions["policyengine-us"],
            "policyengine-core": versions["policyengine-core"],
            "board": str(self.board),
            "board_engine": f"policyengine-us {self.engine}",
            "fix_module": str(core.FIX_MODULE.relative_to(core.ROOT)),
            "fix_module_sha256": core._sha256(core.FIX_MODULE),
            "tool": self.tool["name"],
            "tool_features": sorted(self.features),
            "calculate_tool_sha256": self.schema_sha256,
            "tool_timeout_seconds": self.timeout,
            "workers": self.workers,
        }

    def start(self) -> None:
        """Start the workers in the background; returns at once."""
        if self._starting is not None:
            return

        def build() -> None:
            try:
                self._pool = core.ToolPool(
                    size=self.workers,
                    timeout=self.timeout,
                    worker_target=self._worker_target,
                    board=self.board,
                    tool_features=self.features,
                )
            except BaseException as error:  # reported to every waiting call
                self._failure = error
            finally:
                self._ready.set()

        self._starting = threading.Thread(target=build, daemon=True)
        self._starting.start()

    def wait_ready(self, timeout: float | None = None) -> None:
        """Block until the workers are up; raise what stopped them."""
        self.start()
        if not self._ready.wait(timeout):
            raise RuntimeError("the calculator's workers did not start in time")
        if self._failure is not None:
            raise RuntimeError(
                f"the calculator's workers did not start: {self._failure}"
            ) from self._failure

    def call(self, arguments: Any) -> tuple[dict, float]:
        """Run one call: the result and the seconds it took, as the pilot's
        ``ToolPool.call`` returns them."""
        self.wait_ready(core.WORKER_START_TIMEOUT_SECONDS)
        return self._pool.call(arguments)

    def counters(self) -> dict:
        return self._pool.counters() if self._pool is not None else {}

    def close(self) -> None:
        if self._starting is not None:
            self._ready.wait(core.WORKER_START_TIMEOUT_SECONDS)
        if self._pool is not None:
            self._pool.close()
            self._pool = None


def build_server(calculator: Calculator):
    """The MCP server for a calculator (the SDK's low-level ``Server``, which
    sends the schema as written and applies no validation of its own)."""
    import anyio
    from mcp import MCPError, types
    from mcp.server import Server

    tool = types.Tool(
        name=calculator.tool["name"],
        description=calculator.tool["description"],
        input_schema=calculator.tool["parameters"],
    )
    provenance = types.Resource(
        uri=PROVENANCE_URI,
        name="provenance",
        description=(
            "The engine this calculator runs, the board whose conventions it "
            "follows, and the tool's features and schema hash."
        ),
        mime_type="application/json",
    )

    async def list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[tool])

    async def call_tool(ctx, params) -> types.CallToolResult:
        if params.name != tool.name:
            raise MCPError(
                code=types.INVALID_PARAMS, message=f"Unknown tool: {params.name}"
            )
        arguments = {} if params.arguments is None else params.arguments
        result, _ = await anyio.to_thread.run_sync(calculator.call, arguments)
        if result.get("error") == core.POOL_UNAVAILABLE:
            # Infrastructure, not an answer: the pilot stops the household
            # rather than show a model this result, so it is a protocol error.
            raise MCPError(code=types.INTERNAL_ERROR, message=result["message"])
        # Every other result, a validation or engine error included, is the
        # answer a model reads, exactly as the function tool returns it.
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=result_text(result))]
        )

    async def list_resources(ctx, params) -> types.ListResourcesResult:
        return types.ListResourcesResult(resources=[provenance])

    async def read_resource(ctx, params) -> types.ReadResourceResult:
        if str(params.uri) != PROVENANCE_URI:
            raise MCPError(
                code=types.INVALID_PARAMS, message=f"Unknown resource: {params.uri}"
            )
        return types.ReadResourceResult(
            contents=[
                types.TextResourceContents(
                    uri=PROVENANCE_URI,
                    mime_type="application/json",
                    text=json.dumps(calculator.provenance(), indent=2),
                )
            ]
        )

    return Server(
        SERVER_NAME,
        version=calculator.provenance()["policybench"] or "",
        title=SERVER_TITLE,
        description=(
            f"calculate_household on policyengine-us {calculator.engine} with "
            "the PolicyBench reference conventions."
        ),
        # The schema has no header parameters, so there is nothing for the
        # HTTP transport to check a call against.
        get_tool_input_schema=lambda name: None,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        on_list_resources=list_resources,
        on_read_resource=read_resource,
    )


async def serve_stdio(calculator: Calculator) -> None:
    from mcp.server.stdio import stdio_server

    server = build_server(calculator)
    calculator.start()
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )
    finally:
        calculator.close()


async def serve_http(calculator: Calculator, port: int = DEFAULT_PORT) -> None:
    """Streamable HTTP at http://127.0.0.1:<port>/mcp, once the workers are up
    (so an open port means a calculator that can answer)."""
    import anyio
    import uvicorn

    app = build_server(calculator).streamable_http_app(host=LOOPBACK)
    await anyio.to_thread.run_sync(calculator.wait_ready)
    try:
        await uvicorn.Server(
            uvicorn.Config(app, host=LOOPBACK, port=port, log_level="warning")
        ).serve()
    finally:
        calculator.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="policybench-calculator-mcp",
        description="Serve the PolicyBench calculator over MCP.",
    )
    parser.add_argument(
        "--arm",
        default=DEFAULT_ARM,
        help=(
            "the tool pilot arm whose calculator to serve: pe, pe2, pe3, or pe: "
            f"plus features joined by + ({', '.join(core.TOOL_FEATURES)})"
        ),
    )
    parser.add_argument(
        "--board",
        type=Path,
        default=core.SNAPSHOT,
        help="the board whose engine and conventions to run (default: the frozen one)",
    )
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument(
        "--timeout",
        type=float,
        default=core.TOOL_TIMEOUT_SECONDS,
        help="seconds a calculation may take (the pilot's is the default)",
    )
    args = parser.parse_args(argv)
    features = core.arm_features(args.arm)
    if features is None:
        raise SystemExit(f"arm {args.arm!r} has no calculator")
    try:
        import anyio
        import mcp  # noqa: F401
    except ImportError as error:
        raise SystemExit(
            "the MCP server needs the mcp extra: pip install 'policybench[mcp]'"
        ) from error
    calculator = Calculator(
        features, board=args.board, workers=args.workers, timeout=args.timeout
    )
    if args.transport == "http":
        anyio.run(serve_http, calculator, args.port)
    else:
        anyio.run(serve_stdio, calculator)


if __name__ == "__main__":
    main()
