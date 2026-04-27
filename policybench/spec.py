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

PERSON_OUTPUTS = {
    "person_medicaid_eligible": {
        "suffix": "medicaid_eligible",
        "pe_variable": "is_medicaid_eligible",
        "label": "Medicaid eligibility",
        "prompt": (
            "whether {person_label} is eligible for Medicaid under PolicyEngine "
            "rules, not whether they are currently enrolled (1 if yes, 0 if no)"
        ),
        "metric_type": "binary",
        "net_income_sign": "1",
        "impact_weight_variable": "medicaid",
    },
    "person_chip_eligible": {
        "suffix": "chip_eligible",
        "pe_variable": "is_chip_eligible",
        "label": "CHIP eligibility",
        "prompt": (
            "whether {person_label} is eligible for CHIP under PolicyEngine rules, "
            "not whether they are currently enrolled (1 if yes, 0 if no)"
        ),
        "metric_type": "binary",
        "net_income_sign": "1",
        "impact_weight_variable": "chip",
    },
    "person_medicare_eligible": {
        "suffix": "medicare_eligible",
        "pe_variable": "is_medicare_eligible",
        "label": "Medicare eligibility",
        "prompt": "whether {person_label} is eligible for Medicare (1 if yes, 0 if no)",
        "metric_type": "binary",
        "net_income_sign": "1",
        "impact_weight_variable": "medicare_cost",
    },
    "person_head_start_eligible": {
        "suffix": "head_start_eligible",
        "pe_variable": "is_head_start_eligible",
        "label": "Head Start eligibility",
        "prompt": (
            "whether {person_label} is eligible for Head Start "
            "for preschool-age children, not Early Head Start (1 if yes, 0 if no)"
        ),
        "metric_type": "binary",
        "net_income_sign": "1",
        "impact_weight_variable": "head_start",
        "applies_to": "children",
    },
    "person_early_head_start_eligible": {
        "suffix": "early_head_start_eligible",
        "pe_variable": "is_early_head_start_eligible",
        "label": "Early Head Start eligibility",
        "prompt": (
            "whether {person_label} is eligible for Early Head Start as a child "
            "under this benchmark output (1 if yes, 0 if no)"
        ),
        "metric_type": "binary",
        "net_income_sign": "1",
        "impact_weight_variable": "early_head_start",
        "applies_to": "children",
    },
    "person_employee_social_security_tax": {
        "suffix": "employee_social_security_tax",
        "pe_variable": "employee_social_security_tax",
        "label": "Employee Social Security tax",
        "prompt": "annual employee Social Security tax for {person_label}",
        "metric_type": "amount",
        "net_income_sign": "-1",
    },
    "person_employee_medicare_tax": {
        "suffix": "employee_medicare_tax",
        "pe_variable": "employee_medicare_tax",
        "label": "Employee Medicare tax",
        "prompt": (
            "annual employee Medicare tax for {person_label}, excluding "
            "Additional Medicare Tax"
        ),
        "metric_type": "amount",
        "net_income_sign": "-1",
    },
}

PERSON_ELIGIBILITY_OUTPUTS = {
    output_id: output
    for output_id, output in PERSON_OUTPUTS.items()
    if output["metric_type"] == "binary"
}

LEGACY_ANY_ELIGIBILITY_OUTPUTS = {
    "any_medicaid_eligible": "medicaid",
    "any_chip_eligible": "chip",
    "any_medicare_eligible": "medicare_cost",
    "household_medicaid_eligible": "medicaid",
    "household_chip_eligible": "chip",
    "household_medicare_eligible": "medicare_cost",
}


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
    impact_weight_variable: str | None = None
    impact_weight_aggregation: str | None = None

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
        impact_weight_variable=(
            None
            if data.get("impact_weight_variable") is None
            else str(data["impact_weight_variable"])
        ),
        impact_weight_aggregation=(
            None
            if data.get("impact_weight_aggregation") is None
            else str(data["impact_weight_aggregation"])
        ),
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


def is_person_eligibility_template(output_id: str) -> bool:
    """Return whether an output id is a person-level template output."""
    return output_id in PERSON_ELIGIBILITY_OUTPUTS


def is_person_output_template(output_id: str) -> bool:
    """Return whether an output id is a person-level template output."""
    return output_id in PERSON_OUTPUTS


def parse_person_output(
    output_id: str,
) -> tuple[str, str, dict[str, str]] | None:
    """Parse a concrete person-level output id.

    Returns `(person_name, template_id, template)` for ids such as
    `adult1_medicaid_eligible` or `adult1_employee_medicare_tax`.
    """
    templates = sorted(
        PERSON_OUTPUTS.items(),
        key=lambda item: len(str(item[1]["suffix"])),
        reverse=True,
    )
    for template_id, template in templates:
        suffix = str(template["suffix"])
        marker = f"_{suffix}"
        if output_id.endswith(marker):
            person_name = output_id[: -len(marker)]
            if person_name.startswith(("adult", "child")):
                return person_name, template_id, template
    return None


def parse_person_eligibility_output(
    output_id: str,
) -> tuple[str, str, dict[str, str]] | None:
    """Parse a concrete person-level eligibility output id."""
    parsed = parse_person_output(output_id)
    if parsed is None:
        return None
    if parsed[1] in PERSON_ELIGIBILITY_OUTPUTS:
        return parsed
    return None


def person_eligibility_output_ids(scenario) -> list[str]:
    """Expand person-level eligibility templates for a scenario."""
    outputs = []
    for template in PERSON_ELIGIBILITY_OUTPUTS.values():
        for person in _people_for_template(scenario, template):
            outputs.append(f"{person.name}_{template['suffix']}")
    return outputs


def _people_for_template(scenario, template: dict[str, str]):
    if template.get("applies_to") == "children":
        return scenario.children
    return scenario.all_people


def expand_programs_for_scenario(programs: list[str], scenario) -> list[str]:
    """Expand scenario-dependent placeholder outputs into concrete outputs."""
    expanded: list[str] = []
    for program in programs:
        if is_person_output_template(program):
            template = PERSON_OUTPUTS[program]
            suffix = template["suffix"]
            expanded.extend(
                f"{person.name}_{suffix}"
                for person in _people_for_template(scenario, template)
            )
        else:
            expanded.append(program)
    return expanded


def output_group_id(output_id: str) -> str:
    """Return the metric/reporting group for a possibly concrete output id."""
    parsed = parse_person_output(output_id)
    if parsed:
        return parsed[1]
    return output_id


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
    parsed = parse_person_output(output_id)
    if parsed:
        return parsed[2]["metric_type"]
    if output_id in PERSON_OUTPUTS:
        return PERSON_OUTPUTS[output_id]["metric_type"]
    if output_id in LEGACY_ANY_ELIGIBILITY_OUTPUTS:
        return "binary"
    output = find_output_spec(output_id)
    return output.metric_type if output else "amount"


def net_income_sign_for_output(output_id: str) -> int:
    """Return the output's sign in household net income."""
    parsed = parse_person_output(output_id)
    if parsed:
        return int(parsed[2]["net_income_sign"])
    if output_id in PERSON_OUTPUTS:
        return int(PERSON_OUTPUTS[output_id]["net_income_sign"])
    if output_id in LEGACY_ANY_ELIGIBILITY_OUTPUTS:
        return 1
    output = find_output_spec(output_id)
    return output.net_income_sign if output else 1


def impact_weight_variable_for_output(output_id: str) -> str | None:
    """Return the PolicyEngine variable used to weight this output, if any."""
    parsed = parse_person_output(output_id)
    if parsed:
        return parsed[2].get("impact_weight_variable")
    if output_id in PERSON_OUTPUTS:
        return PERSON_OUTPUTS[output_id].get("impact_weight_variable")
    if output_id in LEGACY_ANY_ELIGIBILITY_OUTPUTS:
        return LEGACY_ANY_ELIGIBILITY_OUTPUTS[output_id]
    output = find_output_spec(output_id)
    return output.impact_weight_variable if output else None


def binary_output_ids() -> list[str]:
    """Return all binary output ids across specs."""
    return sorted(
        {
            output.id
            for output in iter_output_specs()
            if output.metric_type == "binary"
        }
        | set(PERSON_ELIGIBILITY_OUTPUTS)
        | set(LEGACY_ANY_ELIGIBILITY_OUTPUTS)
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
