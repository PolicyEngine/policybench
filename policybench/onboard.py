"""Onboarding gauntlet: probe a new model's serving stack, emit a ModelCard.

Everything that cost debugging cycles during the 2026-07 open-weight
expansion is a cheap, automatable probe:

1. Forced tool call at 3 variables — Moonshot and Alibaba reject
   ``tool_choice`` outright in thinking mode, and some marketplace hosts
   accept it then reason to the token ceiling without emitting the call.
2. JSON contract at 3 variables — the fallback contract.
3. The surviving contract at 16 variables (whole-scenario shape) — GLM
   reasoned to the ceiling here in both contracts; Kimi overflowed the JSON
   document with its reasoning stream. Failure ⇒ chunk at 3.
4. Latency and token appetite from the probes — models whose calls push the
   default timeout get a larger one on the card, and measured cost per call
   seeds the supervisor's budget projection.

The result is a suggested ``ModelCard`` plus a probe log. Total cost is a
few cents; run it before committing real money to a full benchmark.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field

from litellm import completion, responses

from policybench import eval_no_tools as harness
from policybench.model_cards import ModelCard

PROBE_FULL_VARIABLE_COUNT = 16
PROBE_TIMEOUT_SECONDS = 240
# A call whose completion tokens hit the ceiling without producing a
# parseable answer is the reason-to-the-ceiling signature.
CEILING_FRACTION = 0.95
# Probe latency above this fraction of the standard thinking-class timeout
# earns an extended timeout on the card.
SLOW_CALL_FRACTION = 0.5


# Error text marking failures that say nothing about the serving stack —
# probes hitting these abort the gauntlet instead of shaping the card.
ENVIRONMENT_ERROR_MARKERS = (
    "more credits",
    "insufficient credits",
    "insufficient_quota",
    "exceeded your current quota",
    "402",
    "authentication",
    "invalid api key",
    "api key not found",
    "notfounderror",
    "permissiondeniederror",
    "does not exist or you do not have access",
    "model not found",
    "permission denied",
)


@dataclass
class ProbeResult:
    name: str
    ok: bool
    seconds: float = 0.0
    completion_tokens: int | None = None
    finish_reason: str | None = None
    parsed: int = 0
    requested: int = 0
    error: str | None = None
    cost_usd: float | None = None

    @property
    def environment_error(self) -> bool:
        if not self.error:
            return False
        lowered = self.error.lower()
        return any(
            marker in lowered for marker in ENVIRONMENT_ERROR_MARKERS
        ) or harness.is_retryable_provider_error_text(self.error)


@dataclass
class GauntletReport:
    model_id: str
    probes: list[ProbeResult] = field(default_factory=list)
    card: ModelCard | None = None
    aborted: str | None = None

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "probes": [vars(p) for p in self.probes],
            "card": vars(self.card) if self.card else None,
            "aborted": self.aborted,
        }


def _probe_request(scenario, variables, model_id, contract):
    """Build a harness-parity request forcing the given contract."""
    prompt = harness.make_no_tools_batch_prompt(
        scenario,
        variables,
        answer_contract=contract,
        include_explanations=True,
    )
    messages = [{"role": "user", "content": prompt}]
    controls = harness._completion_controls(
        model_id,
        include_explanations=True,
        variables=variables,
    )
    timeout = max(PROBE_TIMEOUT_SECONDS, harness._request_timeout_seconds(model_id))

    if harness._uses_responses_api(model_id):
        kwargs = {
            "model": model_id,
            "input": prompt,
            "timeout": timeout,
            "max_output_tokens": controls["max_completion_tokens"],
        }
        if contract == "tool":
            kwargs.update(
                {
                    "tools": [
                        harness._responses_tool_schema(
                            variables,
                            country=scenario.country,
                            include_explanations=True,
                        )
                    ],
                    "tool_choice": {
                        "type": "function",
                        "name": harness.ANSWER_FUNCTION_NAME,
                    },
                }
            )
        return messages, kwargs, responses

    kwargs = {
        "model": model_id,
        "messages": messages,
        "timeout": timeout,
        **controls,
    }
    if contract == "tool":
        kwargs.update(
            {
                "tools": [
                    harness._build_answer_tool(
                        variables,
                        country=scenario.country,
                        include_explanations=True,
                    )
                ],
                "tool_choice": {
                    "type": "function",
                    "function": {"name": harness.ANSWER_FUNCTION_NAME},
                },
            }
        )
    else:
        kwargs["response_format"] = {"type": "json_object"}
    return messages, kwargs, completion


def _run_probe(name, scenario, variables, model_id, contract) -> ProbeResult:
    messages, kwargs, request_fn = _probe_request(
        scenario, variables, model_id, contract
    )
    budget = (
        kwargs.get("max_completion_tokens")
        or kwargs.get("max_output_tokens")
        or kwargs.get("max_tokens")
    )
    started = time.time()
    try:
        response = harness._run_request_with_wall_timeout(request_fn, kwargs)
    except Exception as error:
        return ProbeResult(
            name,
            ok=False,
            seconds=time.time() - started,
            requested=len(variables),
            error=f"{type(error).__name__}: {error}"[:300],
        )
    if harness._uses_responses_api(model_id):
        content, tool_calls = harness._responses_content_and_tool_calls(response)
        function_call = None
        finish_reason = getattr(response, "status", None)
    else:
        choice = response.choices[0]
        message = choice.message
        tool_calls = getattr(message, "tool_calls", None)
        content = getattr(message, "content", None)
        function_call = getattr(message, "function_call", None)
        finish_reason = choice.finish_reason
    predictions = harness.extract_predictions(
        content=content,
        variables=variables,
        tool_calls=tool_calls,
        function_call=function_call,
    )
    parsed = sum(1 for v in variables if predictions.get(v) is not None)
    usage = harness._extract_usage_metadata(response, model_id, messages, content or "")
    completion_tokens = usage["completion_tokens"]
    cost = usage["total_cost_usd"]
    hit_ceiling = (
        budget is not None
        and completion_tokens is not None
        and completion_tokens >= budget * CEILING_FRACTION
        and parsed == 0
    )
    return ProbeResult(
        name,
        ok=parsed == len(variables) and not hit_ceiling,
        seconds=time.time() - started,
        completion_tokens=completion_tokens,
        finish_reason=finish_reason,
        parsed=parsed,
        requested=len(variables),
        cost_usd=cost,
    )


def run_gauntlet(model_id: str, scenario, full_variables: list[str]) -> GauntletReport:
    """Probe one model and derive its suggested ModelCard.

    ``scenario`` is any benchmark scenario; ``full_variables`` its expanded
    output list (16+ entries exercises the whole-scenario request shape).
    """
    report = GauntletReport(model_id=model_id)
    small_variables = full_variables[:3]

    tool_small = _run_probe("tool-3var", scenario, small_variables, model_id, "tool")
    report.probes.append(tool_small)
    if tool_small.environment_error:
        report.aborted = f"environment error, not a serving fact: {tool_small.error}"
        return report
    contract = "tool" if tool_small.ok else "json"
    small_success = tool_small
    if not tool_small.ok:
        json_small = _run_probe(
            "json-3var", scenario, small_variables, model_id, "json"
        )
        report.probes.append(json_small)
        if json_small.environment_error:
            report.aborted = (
                f"environment error, not a serving fact: {json_small.error}"
            )
            return report
        if not json_small.ok:
            # Neither contract answers a 3-variable request; nothing further
            # to derive — the model cannot run the benchmark as-is.
            return report
        small_success = json_small

    full_vars = full_variables[:PROBE_FULL_VARIABLE_COUNT]
    full = _run_probe(f"{contract}-full", scenario, full_vars, model_id, contract)
    report.probes.append(full)
    if full.environment_error:
        report.aborted = f"environment error, not a serving fact: {full.error}"
        return report
    chunk_size = None if full.ok else 3

    slow = any(
        p.seconds > harness.THINKING_CLAUDE_REQUEST_TIMEOUT_SECONDS * SLOW_CALL_FRACTION
        for p in report.probes
        if p.ok
    )
    timeout = 600 if slow else None

    if chunk_size is None:
        expected = full.cost_usd
    elif small_success.cost_usd is not None:
        expected = small_success.cost_usd * math.ceil(len(full_variables) / chunk_size)
    else:
        expected = None
    if expected is not None:
        expected = round(expected, 3)

    report.card = ModelCard(
        litellm_id=model_id,
        answer_contract=contract,
        explanation_chunk_size=chunk_size,
        request_timeout_seconds=timeout,
        thinking_budget=True,
        expected_cost_per_scenario_usd=expected,
        notes="Derived by `policybench onboard` — verify with a 2-scenario smoke.",
    )
    return report


def format_report(report: GauntletReport) -> str:
    lines = [f"# Onboarding gauntlet: {report.model_id}", ""]
    for probe in report.probes:
        status = "PASS" if probe.ok else "FAIL"
        detail = (
            f"parsed {probe.parsed}/{probe.requested}"
            if probe.error is None
            else probe.error
        )
        lines.append(
            f"- {probe.name}: {status} ({probe.seconds:.0f}s, "
            f"tokens={probe.completion_tokens}, finish={probe.finish_reason}) "
            f"— {detail}"
        )
    lines.append("")
    if report.aborted:
        lines.append(f"ABORTED — {report.aborted}")
        lines.append("Fix the environment (credits, keys) and rerun; no card derived.")
        return "\n".join(lines)
    if report.card is None:
        lines.append(
            "No viable contract at 3 variables — the model cannot run the "
            "benchmark without harness changes."
        )
    else:
        lines.append("Suggested ModelCard (add to policybench/model_cards.py):")
        lines.append(json.dumps(vars(report.card), indent=2))
    return "\n".join(lines)
