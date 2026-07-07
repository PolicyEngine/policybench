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
import time
from dataclasses import dataclass, field

from litellm import completion

from policybench import eval_no_tools as harness
from policybench.model_cards import ModelCard

PROBE_SMALL_VARIABLES = ["payroll_tax", "snap", "ssi"]
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
    "402",
    "authentication",
    "invalid api key",
    "api key not found",
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
        return any(marker in lowered for marker in ENVIRONMENT_ERROR_MARKERS)


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
    messages, kwargs = harness._chat_completion_request_kwargs(
        scenario, variables, model_id
    )
    kwargs.pop("caching", None)
    kwargs["timeout"] = PROBE_TIMEOUT_SECONDS
    if contract == "json":
        for key in ("tools", "tool_choice"):
            kwargs.pop(key, None)
        prompt = harness.make_no_tools_batch_prompt(
            scenario,
            variables,
            answer_contract="json",
            include_explanations=True,
        )
        messages = [{"role": "user", "content": prompt}]
    return messages, kwargs


def _run_probe(name, scenario, variables, model_id, contract) -> ProbeResult:
    messages, kwargs = _probe_request(scenario, variables, model_id, contract)
    budget = kwargs.get("max_completion_tokens") or kwargs.get("max_tokens")
    started = time.time()
    try:
        response = completion(
            messages=messages, **{k: v for k, v in kwargs.items() if k != "messages"}
        )
    except Exception as error:
        return ProbeResult(
            name,
            ok=False,
            seconds=time.time() - started,
            requested=len(variables),
            error=f"{type(error).__name__}: {error}"[:300],
        )
    choice = response.choices[0]
    message = choice.message
    tool_calls = getattr(message, "tool_calls", None)
    content = getattr(message, "content", None)
    predictions = harness.extract_predictions(
        content=content,
        variables=variables,
        tool_calls=tool_calls,
        function_call=getattr(message, "function_call", None),
    )
    parsed = sum(1 for v in variables if predictions.get(v) is not None)
    usage = getattr(response, "usage", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    cost = None
    if usage is not None:
        cost = getattr(usage, "cost", None)
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
        finish_reason=choice.finish_reason,
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

    tool_small = _run_probe(
        "tool-3var", scenario, PROBE_SMALL_VARIABLES, model_id, "tool"
    )
    report.probes.append(tool_small)
    if tool_small.environment_error:
        report.aborted = f"environment error, not a serving fact: {tool_small.error}"
        return report
    contract = "tool" if tool_small.ok else "json"
    if not tool_small.ok:
        json_small = _run_probe(
            "json-3var", scenario, PROBE_SMALL_VARIABLES, model_id, "json"
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

    costs = [p.cost_usd for p in report.probes if p.cost_usd]
    calls_per_scenario = 1 if chunk_size is None else 6
    expected = round(sum(costs) / len(costs) * calls_per_scenario, 3) if costs else None

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
