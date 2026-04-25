"""Benchmark output specifications.

The spec layer is the source of truth for what PolicyBench asks models to
produce, how those outputs map to PolicyEngine variables, and how they should
be scored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_SPEC_ID = "v2"
DEFAULT_PROGRAM_SET = "v2_headline"


@dataclass(frozen=True)
class OutputSpec:
    """One benchmark output and its PolicyEngine mapping."""

    id: str
    country: str
    pe_variable: str
    label: str
    prompt: str
    metric_type: str
    role: str
    output_set: str
    aggregation: str
    net_income_sign: int

    @property
    def is_binary(self) -> bool:
        return self.metric_type == "binary"

    @property
    def is_rate(self) -> bool:
        return self.metric_type == "rate"

    @property
    def is_budget_component(self) -> bool:
        return self.metric_type == "amount" and self.net_income_sign != 0


@dataclass(frozen=True)
class BenchmarkSpec:
    """A complete benchmark scope."""

    id: str
    description: str
    outputs: tuple[OutputSpec, ...]

    def outputs_for_country(
        self,
        country: str,
        output_set: str | None = "headline",
    ) -> tuple[OutputSpec, ...]:
        return tuple(
            output
            for output in self.outputs
            if output.country == country
            and (output_set is None or output.output_set == output_set)
        )

    def output_ids(
        self,
        country: str,
        output_set: str | None = "headline",
    ) -> list[str]:
        return [output.id for output in self.outputs_for_country(country, output_set)]


def _spec_path() -> Path:
    return Path(__file__).with_name("benchmark_specs.json")


@lru_cache(maxsize=1)
def _raw_spec_data() -> dict[str, Any]:
    return json.loads(_spec_path().read_text(encoding="utf-8"))


def _parse_output(country: str, data: dict[str, Any]) -> OutputSpec:
    return OutputSpec(
        id=str(data["id"]),
        country=country,
        pe_variable=str(data["pe_variable"]),
        label=str(data["label"]),
        prompt=str(data["prompt"]),
        metric_type=str(data["metric_type"]),
        role=str(data["role"]),
        output_set=str(data["output_set"]),
        aggregation=str(data["aggregation"]),
        net_income_sign=int(data["net_income_sign"]),
    )


@lru_cache(maxsize=None)
def get_benchmark_spec(spec_id: str = DEFAULT_SPEC_ID) -> BenchmarkSpec:
    """Load a benchmark spec by id."""
    raw_specs = _raw_spec_data()["specs"]
    if spec_id not in raw_specs:
        valid = ", ".join(sorted(raw_specs))
        raise ValueError(f"Unknown benchmark spec '{spec_id}'. Valid specs: {valid}.")

    raw_spec = raw_specs[spec_id]
    outputs: list[OutputSpec] = []
    for country, country_outputs in raw_spec["countries"].items():
        outputs.extend(_parse_output(country, output) for output in country_outputs)

    return BenchmarkSpec(
        id=spec_id,
        description=str(raw_spec["description"]),
        outputs=tuple(outputs),
    )


def available_spec_ids() -> list[str]:
    """Return available benchmark spec ids."""
    return sorted(_raw_spec_data()["specs"])


def parse_program_set(program_set: str | None) -> tuple[str, str]:
    """Parse a public program-set name into (spec_id, output_set)."""
    if not program_set:
        return parse_program_set(DEFAULT_PROGRAM_SET)
    if program_set in available_spec_ids():
        return program_set, "headline"
    if "_" in program_set:
        spec_id, output_set = program_set.split("_", 1)
        if spec_id in available_spec_ids():
            return spec_id, output_set
    valid = []
    for spec_id in available_spec_ids():
        valid.append(spec_id)
        output_sets = sorted(
            {output.output_set for output in get_benchmark_spec(spec_id).outputs}
        )
        valid.extend(f"{spec_id}_{output_set}" for output_set in output_sets)
    raise ValueError(
        f"Unknown program set '{program_set}'. Valid program sets: "
        f"{', '.join(valid)}."
    )


def get_output_specs(
    country: str,
    program_set: str | None = None,
) -> tuple[OutputSpec, ...]:
    """Return output specs for a country and public program set."""
    spec_id, output_set = parse_program_set(program_set)
    spec = get_benchmark_spec(spec_id)
    outputs = spec.outputs_for_country(country, output_set)
    if not outputs:
        valid_countries = sorted({output.country for output in spec.outputs})
        raise ValueError(
            f"No outputs for country '{country}' in program set '{program_set}'. "
            f"Valid countries for spec '{spec_id}': {', '.join(valid_countries)}."
        )
    return outputs


def get_output_ids(country: str, program_set: str | None = None) -> list[str]:
    """Return benchmark output ids for a country and public program set."""
    return [output.id for output in get_output_specs(country, program_set)]


def iter_output_specs(
    spec_id: str | None = None,
) -> tuple[OutputSpec, ...]:
    """Return output specs from one spec or all specs."""
    if spec_id:
        return get_benchmark_spec(spec_id).outputs

    outputs: list[OutputSpec] = []
    for available_spec_id in available_spec_ids():
        outputs.extend(get_benchmark_spec(available_spec_id).outputs)
    return tuple(outputs)


def find_output_spec(
    output_id: str,
    country: str | None = None,
    spec_id: str | None = None,
) -> OutputSpec | None:
    """Find an output spec by benchmark id."""
    matches = [
        output
        for output in iter_output_specs(spec_id)
        if output.id == output_id and (country is None or output.country == country)
    ]
    if not matches:
        return None
    return matches[0]


def require_output_spec(
    output_id: str,
    country: str,
    spec_id: str | None = None,
) -> OutputSpec:
    """Find an output spec or raise a clear error."""
    output = find_output_spec(output_id, country=country, spec_id=spec_id)
    if output is None:
        scope = spec_id or "all specs"
        raise ValueError(
            f"Unknown benchmark output '{output_id}' for country '{country}' "
            f"in {scope}."
        )
    return output


def metric_type_for_output(output_id: str) -> str:
    """Return the scoring metric type for an output id."""
    output = find_output_spec(output_id)
    return output.metric_type if output else "amount"


def net_income_sign_for_output(output_id: str) -> int:
    """Return the output's sign in household net income."""
    output = find_output_spec(output_id)
    return output.net_income_sign if output else 1


def binary_output_ids() -> list[str]:
    """Return all binary output ids across specs."""
    return sorted(
        {
            output.id
            for output in iter_output_specs()
            if output.metric_type == "binary"
        }
    )


def rate_output_ids() -> list[str]:
    """Return all rate output ids across specs."""
    return sorted(
        {
            output.id
            for output in iter_output_specs()
            if output.metric_type == "rate"
        }
    )
