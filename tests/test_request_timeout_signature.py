"""Which worker-log text counts as a provider request timeout.

The supervisor steps concurrency down when too many scenarios time out, and
it learns that from each worker's log. The log lines below were captured on
2026-09-28 from real ``policybench.cli eval-no-tools`` worker subprocesses
(litellm 1.88.1) run against a local mock provider: a stalled request, a
response trickled past the SIGALRM wall timeout, HTTP 408/500/504/401
replies, and litellm's import-time model-cost-map fetch pointed at a stalled,
refusing or 504-ing server. Only ports and output paths were shortened.
"""

from __future__ import annotations

import random
import time
import traceback

import litellm
import pytest

from policybench.eval_no_tools import (
    WALL_TIMEOUT_MESSAGE,
    RequestWallTimeoutError,
    _format_error,
    _run_request_with_wall_timeout,
    log_shows_request_timeout,
)

COST_MAP_FETCH_TIMED_OUT = (
    "\x1b[92m18:41:22 - LiteLLM:WARNING\x1b[0m: get_model_cost_map.py:271 - "
    "LiteLLM: Failed to fetch remote model cost map from "
    "http://127.0.0.1:61362/model_prices.json: timed out. "
    "Falling back to local backup."
)
COST_MAP_FETCH_GATEWAY_TIMEOUT = (
    "\x1b[92m18:47:21 - LiteLLM:WARNING\x1b[0m: get_model_cost_map.py:271 - "
    "LiteLLM: Failed to fetch remote model cost map from "
    "http://127.0.0.1:61916/model_prices.json: Server error "
    "'504 Gateway Timeout' for url 'http://127.0.0.1:61916/model_prices.json'\n"
    "For more information check: "
    "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/504. "
    "Falling back to local backup."
)
COST_MAP_FETCH_REFUSED = (
    "\x1b[92m18:47:21 - LiteLLM:WARNING\x1b[0m: get_model_cost_map.py:271 - "
    "LiteLLM: Failed to fetch remote model cost map from "
    "http://127.0.0.1:61917/model_prices.json: [Errno 61] Connection refused. "
    "Falling back to local backup."
)
PROVIDER_LIST = "\x1b[1;31mProvider List: https://docs.litellm.ai/docs/providers\x1b[0m"

# The whole log of a worker whose cost-map fetch timed out and whose request
# then succeeded: the case that used to count as a timeout.
COMPLETED_WORKER_LOG_AFTER_COST_MAP_TIMEOUT = (
    COST_MAP_FETCH_TIMED_OUT
    + "\n"
    + f"\n{PROVIDER_LIST}\n\n" * 18
    + "No-tools predictions saved to run/scenarios/scenario_000.csv\n"
)

REQUEST_TIMEOUT_LINES = {
    "retry after a stalled Responses request": (
        "  Retry 1: litellm.Timeout: Timeout Error: OpenAIException - litellm.Ti... 2s"
    ),
    "retry after a stalled chat request": (
        "  Retry 1: litellm.Timeout: Timeout Error: DeepseekException - litellm.... 2s"
    ),
    "worker ERROR line after retries": (
        "  ERROR [gpt-5.4-mini] scenario_000: Timeout: litellm.Timeout: Timeout "
        "Error: OpenAIException - litellm.Timeout: Connection timed out after "
        "2 seconds."
    ),
    "traceback of a stalled request": (
        "litellm.exceptions.Timeout: litellm.Timeout: Connection timed out after "
        "2 seconds."
    ),
    "wall timeout fired inside a socket read": (
        "httpcore.ReadTimeout: Provider request exceeded 34.0s wall-clock timeout"
    ),
    "provider HTTP 408": (
        "  ERROR [gpt-5.4-mini] scenario_000: Timeout: litellm.Timeout: Timeout "
        'Error: OpenAIException - {"error": {"message": "mock status 408", '
        '"type": "mock_error", "code": "408"}}'
    ),
    "provider HTTP 504": (
        "litellm.exceptions.Timeout: litellm.Timeout: Timeout Error: "
        'OpenAIException - {"error": {"message": "mock status 504", '
        '"type": "mock_error", "code": "504"}}'
    ),
}

NON_TIMEOUT_LINES = {
    "cost-map fetch timed out": COST_MAP_FETCH_TIMED_OUT,
    "cost-map fetch got a 504": COST_MAP_FETCH_GATEWAY_TIMEOUT,
    "cost-map fetch refused": COST_MAP_FETCH_REFUSED,
    "litellm provider list": PROVIDER_LIST,
    "litellm debug hint": (
        "LiteLLM.Info: If you need to debug this error, use `litellm._turn_on_debug()'."
    ),
    "litellm feedback banner": (
        "\x1b[1;31mGive Feedback / Get Help: "
        "https://github.com/BerriAI/litellm/issues/new\x1b[0m"
    ),
    "provider HTTP 401": (
        "  ERROR [gpt-5.4-mini] scenario_000: AuthenticationError: "
        "litellm.AuthenticationError: AuthenticationError: OpenAIException - "
        '{"error": {"message": "mock status 401", "type": "mock_error", '
        '"code": "401"}}'
    ),
    "provider HTTP 500": (
        "litellm.exceptions.InternalServerError: litellm.InternalServerError: "
        'InternalServerError: DeepseekException - {"error": {"message": '
        '"mock status 500", "type": "mock_error", "code": "500"}}'
    ),
    "saved predictions": "No-tools predictions saved to run/scenarios/x.csv",
}


@pytest.mark.parametrize(
    "line", REQUEST_TIMEOUT_LINES.values(), ids=list(REQUEST_TIMEOUT_LINES)
)
def test_real_request_timeout_lines_count(line):
    assert log_shows_request_timeout(line)


@pytest.mark.parametrize(
    "line", NON_TIMEOUT_LINES.values(), ids=list(NON_TIMEOUT_LINES)
)
def test_lines_without_a_request_timeout_do_not_count(line):
    assert not log_shows_request_timeout(line)


def test_completed_worker_after_a_cost_map_timeout_is_not_timed_out():
    log = COMPLETED_WORKER_LOG_AFTER_COST_MAP_TIMEOUT
    # The old substring test fired on this log.
    assert "timed out" in log
    assert not log_shows_request_timeout(log)


# -- the signatures follow the exceptions that produce them ----------------


def _litellm_timeout() -> litellm.Timeout:
    return litellm.Timeout(
        message="Connection timed out after 2 seconds.",
        model="gpt-5.4-mini",
        llm_provider="openai",
    )


def test_litellm_timeout_is_recognized_however_the_worker_prints_it():
    error = _litellm_timeout()
    # The request loop's retry line keeps only the first 60 characters.
    assert log_shows_request_timeout(f"  Retry 1: {error!r:.60s}... 2s")
    assert log_shows_request_timeout(
        f"  ERROR [gpt-5.4-mini] scenario_000: {_format_error(error)}"
    )
    assert log_shows_request_timeout(
        "".join(traceback.format_exception(type(error), error, None))
    )


def test_wall_timeout_is_recognized_raw_and_rewrapped(monkeypatch):
    monkeypatch.setattr(
        "policybench.eval_no_tools.REQUEST_WALL_TIMEOUT_GRACE_SECONDS", 0
    )
    monkeypatch.setattr("policybench.eval_no_tools.REQUEST_WALL_TIMEOUT_MULTIPLIER", 1)

    def slow_request(**_kwargs):
        time.sleep(1)

    with pytest.raises(RequestWallTimeoutError) as caught:
        _run_request_with_wall_timeout(slow_request, {"timeout": 0.05})
    error = caught.value
    assert str(error) == WALL_TIMEOUT_MESSAGE.format(seconds=0.05)
    # Raised outside a socket read, the class name reaches the ERROR line.
    assert log_shows_request_timeout(
        f"  ERROR [m] scenario_000: {_format_error(error)}"
    )
    # Inside a read, httpcore re-raises it under its own class with the same
    # message, which the traceback keeps.
    assert log_shows_request_timeout(f"httpcore.ReadTimeout: {error}")


# -- properties -------------------------------------------------------------

LABELED_LINES = [(line, True) for line in REQUEST_TIMEOUT_LINES.values()] + [
    (line, False) for line in NON_TIMEOUT_LINES.values()
]
COST_MAP_ERRORS = (
    "timed out",
    "The read operation timed out",
    "_ssl.c:1011: The handshake operation timed out",
    "[Errno 60] Operation timed out",
    "[Errno 61] Connection refused",
    "Server error '504 Gateway Timeout' for url 'https://example.test/map.json'",
    "Client error '408 Request Timeout' for url 'https://example.test/map.json'",
    "ReadTimeout",
    "ConnectTimeout: Timeout",
)
CASES = 400


def _cost_map_failure_line(rng: random.Random) -> str:
    host = rng.choice(("127.0.0.1:5000", "raw.githubusercontent.com", "proxy.test"))
    return (
        "LiteLLM: Failed to fetch remote model cost map from "
        f"https://{host}/model_prices_{rng.randrange(10**6)}.json: "
        f"{rng.choice(COST_MAP_ERRORS)}. Falling back to local backup."
    )


def _sample_log(rng: random.Random) -> tuple[list[str], bool]:
    picked = rng.sample(LABELED_LINES, rng.randrange(len(LABELED_LINES) + 1))
    return [line for line, _ in picked], any(label for _, label in picked)


def test_a_log_counts_exactly_when_one_of_its_lines_is_a_timeout():
    """Differential check against the per-line labels, over random logs."""
    rng = random.Random(20260928)
    for _ in range(CASES):
        lines, expected = _sample_log(rng)
        assert log_shows_request_timeout("\n".join(lines)) is expected


def test_cost_map_fetch_failures_never_change_the_verdict():
    rng = random.Random(1)
    for _ in range(CASES):
        lines, expected = _sample_log(rng)
        noisy = list(lines)
        for _ in range(rng.randrange(1, 4)):
            noisy.insert(rng.randrange(len(noisy) + 1), _cost_map_failure_line(rng))
        assert log_shows_request_timeout("\n".join(noisy)) is expected


def test_more_log_never_undoes_a_timeout():
    rng = random.Random(2)
    for _ in range(CASES):
        lines, _ = _sample_log(rng)
        timeout_line = rng.choice(list(REQUEST_TIMEOUT_LINES.values()))
        lines.insert(rng.randrange(len(lines) + 1), timeout_line)
        extra = [rng.choice(LABELED_LINES)[0] for _ in range(rng.randrange(4))]
        assert log_shows_request_timeout("\n".join(lines + extra))
