"""Call the calculator's MCP server the way the tool pilot calls its own pool.

``McpToolCall`` is a ``tool_call`` for ``tool_pilot_argon.run_household``: a
callable from a model's arguments to ``(result, seconds)``, as
``core.ToolPool.call`` is. It keeps one MCP session open in a background
thread, so the pilot's synchronous loop can use it unchanged, and it is what
the tests use to check that the server answers a call as the pool does.

The protocol carries arguments as a JSON object. A model's arguments that are
not one (text that is not JSON, or JSON that is not an object) cannot be sent,
so they are answered here with the validator's own refusal, which it makes
before it reads anything else.

Needs the ``mcp`` extra (``pip install policybench[mcp]``).
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

from policybench_calculator import core

OPEN_TIMEOUT_SECONDS = 120.0


def as_object(arguments: Any) -> dict | None:
    """The arguments as the JSON object the protocol carries, or None when
    they are not one."""
    if isinstance(arguments, dict):
        return arguments
    if not isinstance(arguments, str):
        return None
    if len(arguments) > 2 * core.MAX_SITUATION_CHARS:
        return None
    try:
        parsed = json.loads(arguments)
    except (ValueError, RecursionError):
        return None
    return parsed if isinstance(parsed, dict) else None


class McpToolCall:
    """A session with a calculator MCP server, callable as the pilot's
    ``tool_call``.

    ``server`` is what the SDK's ``Client`` takes: a Streamable HTTP URL, an
    ``mcp.StdioServerParameters`` to launch, or (in tests) a server object.
    ``mode`` is the ``Client``'s: "auto", or "legacy" for the handshake a
    2025-era client makes.
    """

    def __init__(
        self,
        server: Any,
        mode: str = "auto",
        call_timeout: float | None = None,
    ):
        self._server = server
        self._mode = mode
        # A call may wait for a worker to start and then for the calculation.
        self._call_timeout = (
            core.WORKER_START_TIMEOUT_SECONDS + 2 * core.TOOL_TIMEOUT_SECONDS
            if call_timeout is None
            else call_timeout
        )
        self._client = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop: asyncio.Event | None = None
        self._failure: BaseException | None = None
        self._opened = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._opened.wait(OPEN_TIMEOUT_SECONDS):
            raise RuntimeError("the MCP session did not open in time")
        if self._failure is not None:
            raise RuntimeError(
                f"the MCP session did not open: {self._failure}"
            ) from self._failure

    def _run(self) -> None:
        async def session() -> None:
            from mcp import Client

            async with Client(self._server, mode=self._mode) as client:
                self._client = client
                self._loop = asyncio.get_running_loop()
                self._stop = asyncio.Event()
                self._opened.set()
                await self._stop.wait()

        try:
            asyncio.run(session())
        except BaseException as error:  # reported to the opener or the next call
            self._failure = error
        finally:
            self._opened.set()

    def _await(self, coroutine):
        if self._failure is not None or self._loop is None:
            coroutine.close()
            raise RuntimeError(f"the MCP session is closed: {self._failure}")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result(self._call_timeout)

    def __enter__(self) -> "McpToolCall":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._loop is not None and self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(timeout=30)

    @property
    def protocol_version(self) -> str:
        return self._client.protocol_version

    def tool(self) -> dict:
        """The calculator as the server lists it, in the shape of the pilot's
        own schema's ``function``: name, description and parameters."""
        listed = self._await(self._client.list_tools()).tools
        tools = [tool for tool in listed if tool.name == core.TOOL_NAME]
        if len(tools) != 1:
            raise RuntimeError(
                f"the server lists {[tool.name for tool in listed]}, not one "
                f"{core.TOOL_NAME}"
            )
        return {
            "name": tools[0].name,
            "description": tools[0].description,
            "parameters": tools[0].input_schema,
        }

    def provenance(self) -> dict:
        from policybench_calculator.mcp_server import PROVENANCE_URI

        contents = self._await(self._client.read_resource(PROVENANCE_URI)).contents
        return json.loads(contents[0].text)

    def __call__(self, arguments: Any) -> tuple[dict, float]:
        started = time.perf_counter()
        sent = as_object(arguments)
        if sent is None:
            # The validator's refusal: it is made before the registry or the
            # features are read, so no engine is needed to give it.
            _, refusal = core.normalize_request(arguments, {})
            return refusal, time.perf_counter() - started
        try:
            reply = self._await(self._client.call_tool(core.TOOL_NAME, sent))
            texts = [block.text for block in reply.content if block.type == "text"]
            if reply.is_error or len(texts) != 1:
                raise RuntimeError(f"unexpected tool result: {reply!r}"[:500])
            result = json.loads(texts[0])
        except Exception as error:
            # The server or the session failed: infrastructure, as a pool with
            # no worker is, so the pilot stops the household and can rerun it.
            result = {
                "error": core.POOL_UNAVAILABLE,
                "message": f"the calculator's MCP server failed: {error}"[
                    : core.MAX_MESSAGE_CHARS
                ],
            }
        return result, time.perf_counter() - started
