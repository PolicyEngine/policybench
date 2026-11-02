"""Probe the reference system for one household of the frozen run.

Builds the household exactly as the reference builder did (policyengine-us
2.15.17 plus ``latest_final``, from the frozen run's scenarios.csv, with the
builder's input rename), checks that every scored output of the household
reproduces its published reference, and then reports:

- each ``--variables`` value for 2026, per entity member;
- each ``--parameters`` node's 2026 value, its dated history and its metadata
  (references, description, uprating), as the parameter tree loaded it;
- with ``--set entity.member.variable=value`` (repeatable), the same values on
  a copy of the household with those inputs changed, beside the baseline.

It is the engine-evidence probe for the reference adversary's non-holding
verdicts; it reads no verdict and changes no reference.

  OPENBLAS_NUM_THREADS=1 PYTHONPATH=. <2.15.17 venv>/bin/python \\
    reference_audit/2026-10-05-reference-adversary/scripts/engine_probe.py \\
    scenario_018 --variables az_standard_deduction az_taxable_income \\
    --parameters gov.states.az.tax.income.deductions.standard.amount \\
    --out reference_audit/2026-10-05-reference-adversary/verification/probes/x.json
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
YEAR = 2026
INSTANT = "2026-01-01"


def _conformance():
    """The definition-conformance script, for its reference-system builder."""
    spec = importlib.util.spec_from_file_location(
        "definition_conformance_script", HERE / "definition_conformance.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scalar(value):
    if isinstance(value, (np.generic,)):
        value = value.item()
    if isinstance(value, bytes):
        value = value.decode()
    if hasattr(value, "name") and not isinstance(value, (str, int, float, bool)):
        return str(value.name)
    if isinstance(value, float):
        return round(value, 6)
    return value


def _members(situation: dict, entity_plural: str) -> list[str]:
    if entity_plural == "people":
        return list(situation["people"])
    return list(situation.get(entity_plural, {}))


def _variable(sim, system, situation: dict, name: str, period) -> dict:
    variable = system.variables.get(name)
    if variable is None:
        return {"error": f"no variable {name!r} in the reference system"}
    try:
        values = sim.calculate(name, period)
    except Exception:  # noqa: BLE001 - a monthly variable read for a year
        try:
            values = sim.calculate_add(name, period)
        except Exception as error:  # noqa: BLE001 - reported, never dropped
            return {"error": f"{type(error).__name__}: {error}"}
    if hasattr(values, "decode_to_str"):
        values = values.decode_to_str()
    plural = variable.entity.plural
    members = _members(situation, plural)
    flat = [_scalar(v) for v in np.asarray(values).tolist()]
    by_member = (
        dict(zip(members, flat)) if len(members) == len(flat) else {"values": flat}
    )
    return {
        "entity": variable.entity.key,
        "label": variable.label,
        "definition_period": str(variable.definition_period),
        "values": by_member,
    }


def _parameter(system, path: str) -> dict:
    node = system.parameters
    ancestors = []
    for part in path.split("."):
        ancestors.append(node)
        try:
            node = node.children[part] if hasattr(node, "children") else node[part]
        except (KeyError, AttributeError, TypeError):
            return {"error": f"no parameter {path!r}"}
    record: dict = {"metadata": getattr(node, "metadata", {}) or {}}
    description = getattr(node, "description", None)
    if description:
        record["description"] = description
    if "reference" not in record["metadata"]:
        # A breakdown leaf carries no citations of its own; its parent's apply.
        for ancestor in reversed(ancestors):
            metadata = getattr(ancestor, "metadata", {}) or {}
            if "reference" in metadata or "uprating" in metadata:
                record["parent_metadata"] = {
                    "parameter": getattr(ancestor, "name", ""),
                    **metadata,
                }
                break
    if hasattr(node, "values_list"):
        record["value_2026"] = _scalar(node(INSTANT))
        record["history"] = [
            {"from": str(entry.instant_str), "value": _scalar(entry.value)}
            for entry in node.values_list[:8]
        ]
    elif hasattr(node, "children"):
        record["children"] = {
            name: _parameter(system, f"{path}.{name}") for name in node.children
        }
    else:
        try:
            record["value_2026"] = str(node(INSTANT))
        except Exception as error:  # noqa: BLE001 - scales and odd nodes
            record["error"] = f"{type(error).__name__}: {error}"
    return json.loads(json.dumps(record, default=str))


def _apply_set(situation: dict, assignment: str) -> None:
    target, _, raw = assignment.partition("=")
    parts = target.split(".")
    if len(parts) == 2:
        entity, member, name = "people", parts[0], parts[1]
    elif len(parts) == 3:
        entity, member, name = parts
    else:
        raise SystemExit(f"--set expects [entity.]member.variable=value: {assignment}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    group = situation.get(entity)
    if not isinstance(group, dict) or member not in group:
        raise SystemExit(f"--set: no {entity}.{member} in the household")
    group[member][name] = {str(YEAR): value}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("scenario_id")
    parser.add_argument("--variables", nargs="*", default=[])
    parser.add_argument("--parameters", nargs="*", default=[])
    parser.add_argument("--set", action="append", default=[], dest="assignments")
    parser.add_argument("--period", default=str(YEAR))
    parser.add_argument("--out")
    args = parser.parse_args()

    conformance = _conformance()
    scenarios = pd.read_csv(conformance.RUN / "scenarios.csv")
    rows = scenarios[scenarios["scenario_id"] == args.scenario_id]
    if rows.empty:
        raise SystemExit(f"no {args.scenario_id} in the frozen run")
    from policybench.scenarios import scenario_from_dict

    scenario = scenario_from_dict(json.loads(rows.iloc[0]["scenario_json"]))
    situation = conformance.build_situation(scenario)
    system = conformance._system()
    sim = conformance._simulation(situation)

    reference = pd.read_csv(conformance.RUN / "reference_outputs.csv")
    exclusions = json.loads((conformance.RUN / "reference_exclusions.json").read_text())
    excluded = {
        (record["scenario_id"], record["variable"])
        for record in (
            exclusions.get("exclusions", [])
            if isinstance(exclusions, dict)
            else exclusions
        )
    }
    published = reference[reference["scenario_id"] == args.scenario_id]
    scored = [
        variable
        for variable in published["variable"]
        if (args.scenario_id, variable) not in excluded
    ]
    recomputed = conformance._outputs(sim, scenario, scored)
    reproduction = {}
    for row in published.itertuples(index=False):
        if row.variable not in recomputed:
            continue
        reproduction[row.variable] = {
            "published": float(row.value),
            "recomputed": round(recomputed[row.variable], 6),
            "reproduces": abs(recomputed[row.variable] - float(row.value))
            <= conformance.REPRODUCE_TOLERANCE,
        }

    period = int(args.period) if args.period.isdigit() else args.period
    report = {
        "scenario_id": args.scenario_id,
        "state": str(rows.iloc[0]["state"]),
        "reference_system": "policyengine-us "
        f"{version('policyengine-us')} + latest_final "
        "(reference_audit/2026-09-28/fixes)",
        "policyengine_core": version("policyengine-core"),
        "period": args.period,
        "people": list(situation["people"]),
        "reproduction": reproduction,
        "all_scored_reproduce": all(r["reproduces"] for r in reproduction.values()),
        "variables": {
            name: _variable(sim, system, situation, name, period)
            for name in args.variables
        },
        "parameters": {path: _parameter(system, path) for path in args.parameters},
    }
    if args.assignments:
        changed = copy.deepcopy(situation)
        for assignment in args.assignments:
            _apply_set(changed, assignment)
        alt = conformance._simulation(changed)
        report["counterfactual"] = {
            "set": args.assignments,
            "outputs": {
                name: round(value, 6)
                for name, value in conformance._outputs(alt, scenario, scored).items()
            },
            "variables": {
                name: _variable(alt, system, changed, name, period)
                for name in args.variables
            },
        }
    text = json.dumps(report, indent=2, default=str) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
