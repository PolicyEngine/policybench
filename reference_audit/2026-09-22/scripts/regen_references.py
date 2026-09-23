"""Regenerate the scored references under the benchmark's publication conventions.

Rule (Max, 2026-09-22): a scored reference follows from the stated facts and from
law published before the 2026-07-03 reference freeze. Where policyengine-us 1.755.4
used a projection of an amount published after the freeze, the reference takes the
last amount published before it. The conventions are the root_causes.json entries
of class "convention"; each names the fix module that implements it:
  c_snap_hold_fy2026  SNAP October-December 2026 at the FY2026 figures, with the
                      statutory rounding (sweep/fixes/r13_hold_fy2026_v2.py)
  c_ca_hold_2025      California's 2026 indexed amounts at the published 2025
                      amounts (sweep/fixes/r19_ca_convention.py)
  ...                 and the other parameter conventions root_causes.json lists
                      (IRS sales tax tables, Wisconsin, Idaho, ...)

Every output is recomputed with all conventions applied together. A scored output
whose value changes takes the regenerated value; an excluded output keeps the frozen
value its exclusion record names. The sidecar gains one revision per convention,
listing the outputs that convention moves on its own.

Step 1 (policyengine-us 1.755.4 triage venv) writes the reference CSV, the sidecar,
and the engine traces of every changed output:
  PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/opus55 \\
    .venv-pe1755/bin/python regen_references.py references \\
      --exclusions records/reference_exclusions.json --out-dir ../reference_v12

Step 2 (policybench venv, which has litellm) rewrites the derivation narratives of
changed outputs whose explanation does not already carry the regenerated value:
  ANTHROPIC_API_KEY=... PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/opus55 \\
    /Users/maxghenis/PolicyEngine/policybench/.venv/bin/python \\
      regen_references.py narratives --out-dir ../reference_v12 \\
      --explanations <annotations>/us_case_reference_explanations.csv
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
FIXES = HERE / "sweep" / "fixes"
BUNDLE = Path(
    "/Users/maxghenis/PolicyEngine/policybench/results/local/newmodels/publish/"
    "us_full_run_20260612_policyengine_4_16_1_populace/us"
)
# The frozen v1.1 bundle (reference_outputs.csv sha256 b9136a15...), read-only. Not
# adds202609/publish/: the fold overwrites that dir with the regenerated references.
YEAR = 2026
DATE = "2026-09-22"
ENGINE = "policyengine-us 1.755.4"
RULE = (
    "A scored reference follows from the stated facts and from law published before "
    "the 2026-07-03 reference freeze."
)
def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def conventions() -> dict[str, dict]:
    causes = json.loads((HERE / "root_causes.json").read_text())
    return {k: v for k, v in causes.items() if isinstance(v, dict) and v.get("class") == "convention"}


def load_reform(fix: str):
    spec = importlib.util.spec_from_file_location(f"conv_{fix}", FIXES / f"{fix}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.reform


def compute_all(system) -> pd.DataFrame:
    """Every reference output under one tax-benefit system, as the sweep computes it."""
    sys.path.insert(0, str(HERE / "sweep"))
    from sweep import build_situation  # noqa: E402

    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output
    from policybench.scenarios import scenario_from_dict
    from policybench.spec import expand_programs_for_scenario
    from policyengine_us import Simulation

    meta = json.loads((BUNDLE / "reference_outputs.csv.meta.json").read_text())
    frozen = pd.read_csv(BUNDLE / "reference_outputs.csv").set_index(["scenario_id", "variable"])["value"]
    rows = []
    for _, srow in pd.read_csv(BUNDLE / "scenarios.csv").iterrows():
        scenario = scenario_from_dict(json.loads(srow["scenario_json"]))
        sim = Simulation(tax_benefit_system=system, situation=build_situation(scenario))
        for variable in expand_programs_for_scenario(meta["programs"], scenario):
            if (scenario.id, variable) not in frozen.index:
                continue
            value = _extract_person_value(
                sim.calculate(_pe_variable_for_output(variable, "us"), YEAR), scenario, variable
            )
            rows.append({"scenario_id": scenario.id, "variable": variable, "value": float(value)})
    return pd.DataFrame(rows).set_index(["scenario_id", "variable"])["value"]


def references(args) -> None:
    from policyengine_us import CountryTaxBenefitSystem

    convs = conventions()
    reference = pd.read_csv(BUNDLE / "reference_outputs.csv")
    excluded = {
        (e["scenario_id"], e["variable"])
        for e in json.loads(Path(args.exclusions).read_text())["exclusions"]
    }
    reforms = {name: load_reform(c["fix"]) for name, c in convs.items()}
    combined = compute_all(CountryTaxBenefitSystem(reform=tuple(reforms.values())))
    # Which convention moves each output on its own (from its verified sweep).
    alone, alone_value = {}, {}
    for name, c in convs.items():
        sweep = pd.read_csv(HERE / "sweep" / "out" / f"{c['fix']}.csv")
        moved = sweep.loc[sweep["delta"].abs() > 1e-6]
        alone[name] = set(map(tuple, moved[["scenario_id", "variable"]].values))
        alone_value[name] = moved.set_index(["scenario_id", "variable"])["recomputed"].to_dict()

    changed = {name: [] for name in convs}
    for idx, row in reference.iterrows():
        key = (row["scenario_id"], row["variable"])
        new = float(combined[key])
        if key in excluded or abs(new - float(row["value"])) <= 1e-6:
            continue
        owners = [name for name in convs if key in alone[name]]
        if not owners:
            raise SystemExit(f"{key} changes under the combined conventions but under none alone")
        # The conventions touch disjoint parameters; one that moves an output alone
        # must give the combined value (no interaction), or the attribution is wrong.
        if len(owners) == 1 and abs(alone_value[owners[0]][key] - new) > 1e-3:
            raise SystemExit(f"{key}: combined {new} differs from {owners[0]} alone {alone_value[owners[0]][key]}")
        for name in owners:
            changed[name].append(
                {"scenario_id": key[0], "variable": key[1], "frozen": float(row["value"]), "regenerated": new}
            )
        reference.loc[idx, "value"] = new

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    reference.to_csv(out / "reference_outputs.csv", index=False)
    meta = json.loads((BUNDLE / "reference_outputs.csv.meta.json").read_text())
    meta["reference_csv_sha256"] = sha256(out / "reference_outputs.csv")
    meta["revisions"] = [
        {
            "date": DATE,
            "convention": name,
            "outputs": c["outputs"],
            "rule": f"{RULE} {c['rule']}",
            "basis": c["basis"],
            "engine_version": ENGINE,
            "fix_module": f"{c['fix']}.py",
            "fix_module_sha256": sha256(FIXES / f"{c['fix']}.py"),
            "applied_together_with": sorted(set(convs) - {name}),
            "excluded_outputs_untouched": True,
            "changed": changed[name],
        }
        for name, c in convs.items()
    ]
    (out / "reference_outputs.csv.meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    # Engine traces of the changed outputs, for the narratives in step 2.
    sys.modules.setdefault("litellm", types.ModuleType("litellm"))
    sys.path.insert(0, str(HERE / "sweep"))
    from sweep import build_situation  # noqa: E402

    from policybench.case_reference_explanations import _find_target_tree, _render_trace
    from policybench.ground_truth import _pe_variable_for_output
    from policybench.scenarios import scenario_from_dict
    from policyengine_us import Simulation

    system = CountryTaxBenefitSystem(reform=tuple(reforms.values()))
    scenarios = pd.read_csv(BUNDLE / "scenarios.csv").set_index("scenario_id")
    traces = {}
    for name, items in changed.items():
        for item in items:
            scenario = scenario_from_dict(json.loads(scenarios.loc[item["scenario_id"], "scenario_json"]))
            sim = Simulation(tax_benefit_system=system, situation=build_situation(scenario))
            sim.trace = True
            pe_variable = _pe_variable_for_output(item["variable"], "us")
            sim.calculate(pe_variable, YEAR)
            tree = _find_target_tree(sim.tracer.trees, pe_variable)
            traces[f"{item['scenario_id']}|{item['variable']}"] = {
                "pe_variable": pe_variable,
                "trace": "\n".join(_render_trace(tree)) if tree else "",
            }
    (out / "reference_traces.json").write_text(json.dumps(traces, indent=1))
    print(f"sha256 {meta['reference_csv_sha256']}")
    for name, items in changed.items():
        print(f"{name}: {len(items)} regenerated")
        for item in items:
            print(f"  {item['scenario_id']} {item['variable']:46s} {item['frozen']:>11.2f} -> {item['regenerated']:>11.2f}")


def narratives(args) -> None:
    import litellm

    from policybench.case_reference_explanations import (
        MAX_TOKENS,
        REFERENCE_MODEL,
        TEMPERATURE,
        _prompt,
        _scenario_summary,
    )

    out = Path(args.out_dir)
    meta = json.loads((out / "reference_outputs.csv.meta.json").read_text())
    traces = json.loads((out / "reference_traces.json").read_text())
    scenarios = pd.read_csv(BUNDLE / "scenarios.csv").set_index("scenario_id", drop=False)
    explanations = pd.read_csv(args.explanations)
    todo = []
    for revision in meta["revisions"]:
        for item in revision["changed"]:
            mask = (explanations["scenario_id"] == item["scenario_id"]) & (
                explanations["variable"] == item["variable"]
            )
            current = explanations.loc[mask, "reference_value"]
            if len(current) and abs(float(current.iloc[0]) - item["regenerated"]) <= 1e-6:
                continue
            todo.append((revision["convention"], item))

    async def one(convention, item):
        row = scenarios.loc[item["scenario_id"]]
        traced = traces[f"{item['scenario_id']}|{item['variable']}"]
        trace = traced["trace"]
        prompt = _prompt(
            "us",
            _scenario_summary(row),
            item["variable"],
            traced["pe_variable"],
            item["regenerated"],
            YEAR,
            trace,
            grounding=conventions()[convention]["grounding"],
        )
        response = await litellm.acompletion(
            model=REFERENCE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        text = response.choices[0].message.content.strip()
        lines = text.split("\n")
        if lines and lines[0].lstrip().startswith("#"):
            text = "\n".join(lines[1:]).strip()
        return item, text, len(trace.splitlines())

    async def run_all():
        return await asyncio.gather(*(one(c, item) for c, item in todo))

    for item, text, n_lines in asyncio.run(run_all()):
        mask = (explanations["scenario_id"] == item["scenario_id"]) & (
            explanations["variable"] == item["variable"]
        )
        explanations.loc[mask, "reference_value"] = item["regenerated"]
        explanations.loc[mask, "trace_lines"] = n_lines
        explanations.loc[mask, "explanation"] = text
        explanations.loc[mask, "error"] = pd.NA
        print(f"--- {item['scenario_id']} {item['variable']} ({item['regenerated']:.2f})\n{text}\n")
    explanations.to_csv(out / "us_case_reference_explanations.csv", index=False)
    print(f"rewrote {len(todo)} narratives")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["references", "narratives"])
    parser.add_argument("--exclusions")
    parser.add_argument("--explanations")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    {"references": references, "narratives": narratives}[args.step](args)


if __name__ == "__main__":
    main()
