"""Offline v2 fact-coverage report using PR #196's real sweep comparisons.

The evidence records actual 2.15.17 simulations, not newly computed results.
Replay feeds their baselines and perturbations through ``unlisted_input_sweep``'s
comparison/report logic. It is intentionally a report on the legacy fixtures,
not a proof that every possible engine input has been discovered. A release must
also rerun the full sweep on the proposed v2 reference builder and conventions.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Set
from typing import TYPE_CHECKING, Any

from policybench import unlisted_input_sweep as sweep

if TYPE_CHECKING:
    from policybench.prompt_contract_v2 import RenderedHouseholdContract
    from policybench.scenarios import Scenario

PAYROLL_ESTIMATE = "state_paid_leave_employee_share"


def replay_recorded_sweep(
    fixture: Mapping[str, Any],
    scenarios: Mapping[str, Scenario],
    references: Mapping[tuple[str, str], float],
    exclusions: Mapping[tuple[str, str], dict],
) -> sweep.SweepReport:
    """Run upstream comparison logic over every recorded household and output.

    Only moving perturbations were vendored; omitted readings are not fabricated
    as no-ops. All 1,984 recorded baselines are present, including excluded outputs
    that do not match their published references. The recorded payroll scope
    perturbation uses upstream movement/exclusion functions because #196 has not
    yet registered that employer choice as an estimate.
    """
    import pandas as pd

    baselines = fixture["baselines"]
    if set(baselines) != set(scenarios):
        raise ValueError("recorded baselines do not cover every frozen scenario")
    if {
        (sid, variable) for sid, values in baselines.items() for variable in values
    } != set(references):
        raise ValueError("recorded baselines do not cover every frozen output")
    readings: dict[str, dict[tuple, dict]] = defaultdict(dict)
    payroll_rows = []
    for move in fixture["moves"]:
        sid, variable = move["scenario_id"], move["variable"]
        if sid not in scenarios:
            raise ValueError(f"unknown scenario {sid}")
        key = (sid, variable)
        if key not in references:
            raise ValueError(f"unknown output {key}")
        if abs(move["reference"] - references[key]) > sweep.BASELINE_TOLERANCE:
            raise ValueError(f"published reference does not match evidence: {key}")
        baseline = move["baseline"]
        if abs(baseline - baselines[sid][variable]) > sweep.BASELINE_TOLERANCE:
            raise ValueError(f"recorded baseline does not match evidence: {key}")
        if not sweep.output_moved(
            baseline, move["value"], binary=sweep.is_binary_output(variable)
        ):
            raise ValueError(f"recorded perturbation does not move: {key}")
        if move["estimate"] == PAYROLL_ESTIMATE:
            record = exclusions.get(key)
            names_input = sweep.exclusion_names_inputs(record, (PAYROLL_ESTIMATE,))
            payroll_rows.append(
                {
                    **{column: "" for column in sweep.MOVE_COLUMNS},
                    **move,
                    "delta": move["value"] - baseline,
                    "status": (
                        "excluded_same_input"
                        if names_input
                        else "excluded_other_reason"
                    )
                    if record
                    else "scored",
                    "scored": record is None,
                    "excluded_reason": record["reason_code"] if record else "",
                    "exclusion_names_input": names_input,
                }
            )
            continue
        reading_key = (move["estimate"], move["reading"], move["kind"], move["variant"])
        reading = readings[sid].setdefault(
            reading_key,
            {
                "estimate": move["estimate"],
                "reading": move["reading"],
                "kind": move["kind"],
                "variant": move["variant"],
                "detail": {"parts": move.get("parts", [])},
                "outputs": {},
                "locality_outputs": [],
                "localities": [],
                "override_text": move.get("override", ""),
                "noop": False,
                "converged": True,
                "iterations": 0,
            },
        )
        reading["outputs"][variable] = move["value"]
        if move["status"] == "prompt_rules_out":
            reading["locality_outputs"].append(variable)
    results = [
        {
            "scenario_id": sid,
            "state": scenario.state,
            "baseline": dict(baselines[sid]),
            "local_taxes": {},
            "readings": list(readings[sid].values()),
            "simulations": 0,
        }
        for sid, scenario in sorted(scenarios.items())
    ]
    report = sweep.evaluate(results, pd.Series(dict(references)), dict(exclusions))
    if payroll_rows:
        report.moves = pd.concat(
            [report.moves, pd.DataFrame(payroll_rows, columns=sweep.MOVE_COLUMNS)],
            ignore_index=True,
        )
        report.summary = sweep.summarize(
            results, report.baseline, report.moves, report.readings
        )
    report.summary["evidence_mode"] = "recorded_simulation_replay"
    report.summary["recorded_simulations"] = fixture["sources"]["unlisted_input_sweep"][
        "simulations"
    ]
    return report


def _person_fact_text(text: str, person_name: str) -> str:
    """Select one person's bullet facts, stopping at the next entity header."""
    lines = text.splitlines()
    try:
        start = lines.index(f"Person {person_name}:") + 1
    except ValueError:
        return ""
    facts = []
    for line in lines[start:]:
        if line and not line.startswith("- "):
            break
        facts.append(line)
    return "\n".join(facts)


def _has_fact_marker(text: str, name: str) -> bool:
    # A marker in another fact's value or a disclaimer is not a statement of
    # this input. Match the actual bullet label, before its value begins.
    return re.search(rf"(?m)^- [^\[\]\n]*\[{re.escape(name)}\]: ", text) is not None


def _input_is_stated(
    name: str,
    entity: str,
    scenario: Scenario,
    rendered: RenderedHouseholdContract,
    conventions: Set[str],
    override: str,
) -> bool:
    blocked = set(rendered.unknown_facts) | set(rendered.unsupported_inputs)
    # The payroll estimate is a scope choice rather than an engine variable.
    source_names = (
        (name, "state_paid_leave_employee_share_withheld")
        if name == PAYROLL_ESTIMATE
        else (name,)
    )
    if entity == "person":
        all_people = scenario.adults + scenario.children
        affected = {
            person
            for person, variable in re.findall(
                r"([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)=", override
            )
            if variable in source_names
        }
        affected &= {person.name for person in all_people}
        people = [
            person for person in all_people if not affected or person.name in affected
        ]
        # Supplied null/unknown/unsupported overrides defeat an absent-input
        # convention. Merely placing the input name in the convention registry
        # cannot turn a supplied unknown into a stated fact.
        if any(
            f"person.{person.name}.{source}" in blocked
            or (source in person.inputs and person.inputs[source] is None)
            for person in people
            for source in source_names
        ):
            return False
        return bool(people) and all(
            (
                name in conventions
                and _has_fact_marker(
                    _person_fact_text(rendered.text, person.name), name
                )
            )
            or any(
                source in person.inputs
                and _has_fact_marker(
                    _person_fact_text(rendered.text, person.name), source
                )
                for source in source_names
            )
            for person in people
        )
    values = getattr(scenario, f"{entity}_inputs")
    if f"{entity}.{name}" in blocked or (name in values and values[name] is None):
        return False
    if name in conventions and _has_fact_marker(rendered.text, name):
        return True
    return (
        name in values
        and values[name] is not None
        and f"{entity}.{name}" not in blocked
        and _has_fact_marker(rendered.text, name)
    )


def report_required_facts(
    replay: sweep.SweepReport,
    fixture: Mapping[str, Any],
    scenarios: Mapping[str, Scenario],
    rendered: Mapping[str, RenderedHouseholdContract],
    stated_convention_inputs: Set[str],
) -> dict[str, Any]:
    """List remaining individually moving inputs; keep compound readings distinct.

    Unsupported raw labels and unknown values/provenance never establish a fact.
    A named convention counts only when supplied in ``stated_convention_inputs``
    and its exact ``[name]`` fact marker appears in this household's text. Person
    inputs require that marker within every affected person's own section; another
    person's convention never covers them. The generic unlisted-zero rule cannot
    certify an engine estimate. Compound
    literal readings can override newly stated conventions too, so their residual
    inputs are reported separately, without assigning their full move to each.
    """
    if set(rendered) != set(scenarios):
        raise ValueError("rendered contracts do not cover every scenario")
    estimates = {estimate["id"]: estimate for estimate in fixture["estimates"]}
    individual: dict[str, dict[str, Any]] = {}
    compound = []
    for move in replay.moves.to_dict("records"):
        if move["status"] == "prompt_rules_out":
            continue
        sid = move["scenario_id"]
        estimate_id = move["estimate"]
        if estimate_id == sweep.COMBINED_ESTIMATE:
            original = next(
                entry
                for entry in fixture["moves"]
                if all(
                    entry[field] == move[field]
                    for field in (
                        "scenario_id",
                        "variable",
                        "estimate",
                        "reading",
                        "variant",
                    )
                )
            )
            missing = sorted(
                {
                    name
                    for part in original["parts"]
                    for name in estimates[part]["engine_inputs"]
                    if not _input_is_stated(
                        name,
                        estimates[part]["entity"],
                        scenarios[sid],
                        rendered[sid],
                        stated_convention_inputs,
                        move["override"],
                    )
                }
            )
            compound.append(
                {"output": [sid, move["variable"]], "unstated_inputs": missing}
            )
            continue
        estimate = estimates[estimate_id]
        names = estimate["engine_inputs"] or [estimate_id]
        missing = [
            name
            for name in names
            if not _input_is_stated(
                name,
                estimate["entity"],
                scenarios[sid],
                rendered[sid],
                stated_convention_inputs,
                move["override"],
            )
        ]
        if not missing:
            continue
        entry = individual.setdefault(
            estimate_id,
            {
                "estimate": estimate_id,
                "unstated_inputs": set(),
                "outputs": set(),
                "scored_outputs": set(),
            },
        )
        entry["unstated_inputs"].update(missing)
        entry["outputs"].add((sid, move["variable"]))
        if move["status"] in ("scored", "acknowledged"):
            entry["scored_outputs"].add((sid, move["variable"]))
    remaining = []
    for estimate_id, entry in sorted(individual.items()):
        outputs = sorted(entry["outputs"])
        scored = sorted(entry["scored_outputs"])
        remaining.append(
            {
                "estimate": estimate_id,
                "unstated_inputs": sorted(entry["unstated_inputs"]),
                "outputs": [list(output) for output in outputs],
                "output_count": len(outputs),
                "scored_output_count": len(scored),
            }
        )
    return {
        "households": replay.summary["households"],
        "outputs": replay.summary["outputs"],
        "evidence_mode": replay.summary["evidence_mode"],
        "remaining": remaining,
        "compound_readings_requiring_rerun": compound,
        "note": (
            "Report only: legacy exclusions remain. Compound readings change "
            "multiple inputs and can override v2 conventions; rerun the complete "
            "sweep under the proposed reference builder before activation."
        ),
    }
