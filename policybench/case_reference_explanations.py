"""Reference-computation narratives for each (scenario, variable) case.

For each case in the benchmark, we run the PolicyEngine simulation with the
tracer on, prune the dependency tree to non-zero subtrees, and ask an LLM
to write a 3-5 sentence narrative of how PolicyEngine derived the value.
Results are cached per case in a CSV so re-runs only do new work.

The narrative is keyed by ``(country, scenario_id, variable)`` and is the
*same* for every model — it describes the truth, not a prediction.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import litellm
import pandas as pd

from policybench.ground_truth import (
    _pe_variable_for_output,
    get_us_situation_simulation_class,
)
from policybench.scenarios import scenario_from_dict

REFERENCE_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 500
TEMPERATURE = 0.0
DEFAULT_CONCURRENCY = 8
DEFAULT_YEAR = 2026


@dataclass(frozen=True)
class CaseKey:
    country: str
    scenario_id: str
    variable: str


def _value_repr(value) -> str:
    if hasattr(value, "__len__") and len(value):
        item = value[0]
    else:
        item = value
    if hasattr(item, "item"):
        item = item.item()
    if isinstance(item, bool):
        return "True" if item else "False"
    if isinstance(item, float):
        return f"{item:.2f}".rstrip("0").rstrip(".") or "0"
    return str(item)


def _is_zero(value) -> bool:
    if hasattr(value, "__len__") and len(value):
        item = value[0]
    else:
        item = value
    if hasattr(item, "item"):
        item = item.item()
    if isinstance(item, bool):
        return item is False
    if isinstance(item, (int, float)):
        return item == 0
    return False


def _render_trace(
    node, depth: int = 0, lines: list[str] | None = None, max_depth: int = 8
) -> list[str]:
    if lines is None:
        lines = []
    if depth > max_depth:
        return lines
    if depth > 1 and _is_zero(node.value):
        return lines
    lines.append("  " * depth + node.name + " = " + _value_repr(node.value))
    for child in node.children:
        _render_trace(child, depth + 1, lines, max_depth)
    return lines


def _find_target_tree(roots, target: str):
    for root in roots:
        if root.name == target:
            return root
        match = _find_target_tree(root.children, target)
        if match is not None:
            return match
    return None


def _build_us_trace(scenario_json: str, pe_variable: str, year: int) -> str:
    Simulation = get_us_situation_simulation_class()
    scenario = scenario_from_dict(json.loads(scenario_json))
    sim = Simulation(situation=scenario.to_pe_household())
    sim.trace = True
    sim.calculate(pe_variable, year)
    tree = _find_target_tree(sim.tracer.trees, pe_variable)
    if tree is None:
        raise RuntimeError(f"trace did not produce tree for {pe_variable}")
    return "\n".join(_render_trace(tree))


def _build_us_traces_for_scenario(
    scenario_json: str,
    pe_variables: list[str],
    year: int,
) -> dict[str, str]:
    """Compute traces for many variables on a single simulation.

    Building a fresh ``Simulation`` per ``(scenario, variable)`` is slow
    because the tax/benefit system setup dominates per-call cost. Reusing one
    sim per scenario drops trace generation from hours to a few minutes for
    the full benchmark.
    """
    Simulation = get_us_situation_simulation_class()
    scenario = scenario_from_dict(json.loads(scenario_json))
    sim = Simulation(situation=scenario.to_pe_household())
    sim.trace = True
    traces: dict[str, str] = {}
    for pe_variable in pe_variables:
        sim.tracer.trees.clear()
        sim.calculate(pe_variable, year)
        tree = _find_target_tree(sim.tracer.trees, pe_variable)
        if tree is None:
            traces[pe_variable] = (
                f"[trace unavailable: no tree captured for {pe_variable}]"
            )
            continue
        traces[pe_variable] = "\n".join(_render_trace(tree))
    return traces


def _prompt(
    country: str,
    scenario_summary: str,
    variable: str,
    pe_variable: str,
    reference_value: float,
    year: int,
    trace_text: str,
) -> str:
    intro = (
        "You are summarizing how PolicyEngine derived a tax/benefit value "
        "for a benchmark household."
    )
    instructions = (
        "Write a 3-5 sentence narrative explaining how PolicyEngine arrived "
        "at this value. Reference the most important intermediate quantities "
        "by name and amount. Be concrete and quantitative. Do not editorialize "
        "about model performance; just describe the derivation. Plain prose, "
        "no headers, no bullet lists."
    )
    return f"""{intro}

VARIABLE: {variable} (PolicyEngine variable: {pe_variable})
COUNTRY: {country.upper()}
TAX YEAR: {year}
HOUSEHOLD: {scenario_summary}
REFERENCE VALUE: {reference_value}

PolicyEngine computation trace (indented dependency tree, non-zero nodes only):
```
{trace_text}
```

{instructions}
"""


def _scenario_summary(row: pd.Series) -> str:
    return (
        f"{row['state']}, {row['filing_status']}, "
        f"{int(row['num_adults'])} adults, "
        f"{int(row['num_children'])} children, "
        f"household income ~${float(row['total_income']):,.0f}"
    )


def _existing_keys(cache_path: Path) -> set[CaseKey]:
    if not cache_path.exists():
        return set()
    df = pd.read_csv(cache_path)
    return {
        CaseKey(
            country=row["country"],
            scenario_id=row["scenario_id"],
            variable=row["variable"],
        )
        for _, row in df.iterrows()
    }


async def _generate_one(
    semaphore: asyncio.Semaphore,
    country: str,
    scenario_id: str,
    variable: str,
    scenario_summary: str,
    pe_variable: str,
    reference_value: float,
    year: int,
    trace_text: str,
) -> dict | None:
    async with semaphore:
        prompt = _prompt(
            country,
            scenario_summary,
            variable,
            pe_variable,
            reference_value,
            year,
            trace_text,
        )
        try:
            response = await litellm.acompletion(
                model=REFERENCE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
        except Exception as exc:
            return {
                "country": country,
                "scenario_id": scenario_id,
                "variable": variable,
                "reference_value": reference_value,
                "trace_lines": len(trace_text.splitlines()),
                "explanation": "",
                "error": f"{type(exc).__name__}: {exc}",
            }
        explanation = response.choices[0].message.content.strip()
        return {
            "country": country,
            "scenario_id": scenario_id,
            "variable": variable,
            "reference_value": reference_value,
            "trace_lines": len(trace_text.splitlines()),
            "explanation": explanation,
            "error": "",
        }


def _build_trace(country: str, scenario_json: str, variable: str, year: int) -> str:
    if country == "us":
        pe_variable = _pe_variable_for_output(variable, "us")
        return _build_us_trace(scenario_json, pe_variable, year)
    raise NotImplementedError(
        f"Tracer is only wired for US scenarios at the moment; got {country!r}"
    )


def _resolve_pe_variable(country: str, variable: str) -> str:
    if country == "us":
        return _pe_variable_for_output(variable, "us")
    return variable


async def _run_batch(
    cases: Sequence[tuple[CaseKey, dict]],
    concurrency: int,
    year: int,
) -> list[dict]:
    semaphore = asyncio.Semaphore(concurrency)
    tasks = []
    for key, payload in cases:
        tasks.append(
            _generate_one(
                semaphore=semaphore,
                country=key.country,
                scenario_id=key.scenario_id,
                variable=key.variable,
                scenario_summary=payload["scenario_summary"],
                pe_variable=payload["pe_variable"],
                reference_value=payload["reference_value"],
                year=year,
                trace_text=payload["trace_text"],
            )
        )
    results = []
    for fut in asyncio.as_completed(tasks):
        result = await fut
        if result is not None:
            results.append(result)
    return results


def generate_country_explanations(
    country: str,
    run_dir: Path,
    output_path: Path,
    year: int = DEFAULT_YEAR,
    only_wrong: bool = False,
    annotations_dir: Path | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    limit: int | None = None,
) -> Path:
    """Generate reference explanations for a country's cases.

    Writes incrementally so an interruption doesn't lose work. Re-runs skip
    cases that already have an explanation in ``output_path``.
    """
    country_dir = run_dir / country
    scenarios_df = pd.read_csv(country_dir / "scenarios.csv")
    ground_truth = pd.read_csv(country_dir / "reference_outputs.csv")

    wrong_cases: set[tuple[str, str]] | None = None
    if only_wrong:
        if annotations_dir is None:
            raise ValueError("only_wrong=True requires annotations_dir")
        ann_files = list(annotations_dir.glob(f"{country}_*_annotations.csv"))
        if not ann_files:
            raise FileNotFoundError(
                f"No annotation files for {country!r} under {annotations_dir}"
            )
        ann = pd.concat([pd.read_csv(f) for f in ann_files], ignore_index=True)
        wrong_cases = set(zip(ann["scenario_id"], ann["variable"]))

    existing = _existing_keys(output_path)
    scenarios_by_id = {row["scenario_id"]: row for _, row in scenarios_df.iterrows()}

    # Group cases by scenario so we only build one ``Simulation`` per
    # scenario rather than per case. Building a fresh sim is the dominant
    # per-call cost, so this is a >10x speedup.
    cases_by_scenario: dict[str, list[tuple[CaseKey, dict]]] = {}
    skipped_missing_scenario = 0
    for _, row in ground_truth.iterrows():
        scenario_id = row["scenario_id"]
        variable = row["variable"]
        key = CaseKey(country=country, scenario_id=scenario_id, variable=variable)
        if key in existing:
            continue
        if wrong_cases is not None and (scenario_id, variable) not in wrong_cases:
            continue
        scenario_row = scenarios_by_id.get(scenario_id)
        if scenario_row is None:
            skipped_missing_scenario += 1
            continue
        cases_by_scenario.setdefault(scenario_id, []).append(
            (
                key,
                {
                    "scenario_row": scenario_row,
                    "variable": variable,
                    "reference_value": float(row["value"]),
                },
            )
        )

    todo: list[tuple[CaseKey, dict]] = []
    for scenario_id, scenario_cases in cases_by_scenario.items():
        scenario_row = scenario_cases[0][1]["scenario_row"]
        pe_variable_map = {
            payload["variable"]: _resolve_pe_variable(country, payload["variable"])
            for _, payload in scenario_cases
        }
        try:
            if country == "us":
                traces = _build_us_traces_for_scenario(
                    scenario_row["scenario_json"],
                    list(pe_variable_map.values()),
                    year,
                )
            else:
                raise NotImplementedError(
                    f"Tracer is only wired for US at the moment; got {country!r}"
                )
        except Exception as exc:
            traces = {}
            error_text = f"[trace unavailable: {type(exc).__name__}: {exc}]"
            for pe_variable in pe_variable_map.values():
                traces[pe_variable] = error_text
        for key, payload in scenario_cases:
            pe_variable = pe_variable_map[payload["variable"]]
            todo.append(
                (
                    key,
                    {
                        "scenario_summary": _scenario_summary(scenario_row),
                        "pe_variable": pe_variable,
                        "reference_value": payload["reference_value"],
                        "trace_text": traces.get(pe_variable, "[trace unavailable]"),
                    },
                )
            )
            if limit is not None and len(todo) >= limit:
                break
        if limit is not None and len(todo) >= limit:
            break

    print(
        f"{country}: {len(todo)} cases to generate "
        f"({len(existing)} already cached, "
        f"{skipped_missing_scenario} missing scenarios)"
    )
    if not todo:
        return output_path

    results = asyncio.run(_run_batch(todo, concurrency=concurrency, year=year))
    new_df = pd.DataFrame(results)
    if output_path.exists():
        existing_df = pd.read_csv(output_path)
        out = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        out = new_df
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)
    errors = sum(1 for r in results if r.get("error"))
    print(
        f"{country}: wrote {len(results)} new explanations "
        f"({errors} errors) to {output_path}"
    )
    return output_path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Full-run directory containing country subdirectories.",
    )
    parser.add_argument(
        "--country", action="append", default=None, help="Country code (repeat to add)."
    )
    parser.add_argument(
        "--output-dir",
        default="annotations/full_run_20260513_policyengine_4_4_4_nested_outputs",
        help="Destination directory for the explanations CSVs.",
    )
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument(
        "--only-wrong",
        action="store_true",
        help="Only generate for cases with at least one wrong prediction.",
    )
    parser.add_argument(
        "--annotations-dir",
        default=None,
        help="Annotations directory (required with --only-wrong).",
    )
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of new cases generated per country (smoke test).",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    output_dir = Path(args.output_dir)
    countries = args.country or ["us"]
    annotations_dir = Path(args.annotations_dir) if args.annotations_dir else None
    for country in countries:
        output_path = output_dir / f"{country}_case_reference_explanations.csv"
        generate_country_explanations(
            country=country,
            run_dir=run_dir,
            output_path=output_path,
            year=args.year,
            only_wrong=args.only_wrong,
            annotations_dir=annotations_dir,
            concurrency=args.concurrency,
            limit=args.limit,
        )


if __name__ == "__main__":
    main()
