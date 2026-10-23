"""AI judges on each batch of a household set, before the next batch runs.

Max, 2026-10-22: "we should go slowly since the new microdata could reveal
different pe bugs - we should do ai judges in small batches or real time".

Each batch of a household set (scripts/household_set.py) runs every model in
every arm of the tool pilot (scripts/tool_pilot_argon.py --board). This script
then hands the batch to PolicyBench's reference adversary
(policybench/reference_adversary.py), arm by arm:

    batch_judge.py payload --board DIR --runs ROOT --stage S --arm none \\
        --batch K --out payload.json
    policybench consensus-flags --payload payload.json --output flags.json \\
        --min-models 2 --top-k 3 --min-top 2 --zero-cluster-min-models 2
    batch_judge.py derivations --board DIR --payload payload.json \\
        --flags flags.json --out-dir annotations/
    policybench adversary-prepare --payload payload.json --flags flags.json \\
        --adversary-dir judge/ --annotations-dir annotations/
    scripts/run_reference_adversary_claude.sh judge/
    policybench adversary-collect --adversary-dir claude=judge/ --output-dir out/

``payload`` writes one arm's answers as a dashboard payload, each model a
"model" of the board, so the consensus trigger and the adversary run on it
unchanged. Only the no-tools and web arms are judged: a calculator arm answers
with the reference engine itself, and its explanations name it, which the
adversary's blinding refuses. The payload carries what the models saw: the
v2-pilot household prompt (the tool contract's, checked against each record's
sent prompt hash), the v2-pilot output definitions, and the condition they
answered under (from memory, or with web search).

The trigger's thresholds are the board's, scaled to three models: a cell is
flagged when two of the three models agree on one answer other than the
reference (``min_models`` 2, a zero cluster too), or when two of the three
(all are "top") do.

``derivations`` writes the engine derivation of each flagged reference: the
pruned computation trace on the household set's own reference system (its
engine and fix modules), in the frozen annotations' CSV format. A trace is the
engine's own record; no model narrates it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import tool_pilot_argon as pilot  # noqa: E402

MODELS = ("gpt-6-sol", "claude-opus-5.5", "gemini-4-argon")
JUDGED_ARMS = {
    "none": "answering from memory, without tools",
    "web": "answering with web search",
}
# The tool contract's household prompt is the dashboard payload's
# ``prompt.tool``; this model is on the tool contract.
PROMPT_MODEL = "gpt-6-sol"
TRACE_MAX_LINES = 400
YEAR = 2026


def arm_folder(arm: str) -> str:
    return arm.replace("+", "-")


def load_batch(board: Path, batch: int) -> list[str]:
    batches = json.loads((board / "batches.json").read_text())["batches"]
    if not 0 <= batch < len(batches):
        raise SystemExit(f"{board} has batches 0 to {len(batches) - 1}")
    return list(batches[batch])


def prompt_model_for(models) -> str:
    """The model whose household prompt a payload shows: the first on the tool
    contract (the dashboard's ``prompt.tool``), else the first model."""
    for model in models:
        if pilot.model_profile(model, "none").contract == "tool":
            return model
    return models[0]


def household_prompt(
    scenario, variables: list[str], prompt_version: str, model: str = PROMPT_MODEL
) -> str:
    """The household prompt ``model`` saw, without the arm's notice: the
    board's prompt in the run's prompt version."""
    profile = pilot.model_profile(model, "none", prompt_version, False)
    prompt, kwargs = pilot.build_initial_request(scenario, variables, profile)
    return prompt[: len(prompt) - len(profile.notice)] if profile.notice else prompt


def output_definitions(variables, prompt_version: str) -> dict[str, str]:
    from policybench.prompts import get_variable_description

    definitions = {}
    for variable in sorted(set(variables)):
        text = get_variable_description(variable, country="us")
        if prompt_version == "v2-pilot":
            text = pilot.v2_pilot_text(text)
        definitions[variable] = text
    return definitions


def build_payload(
    board_dir: Path,
    runs: Path,
    stage: str,
    arm: str,
    batch: int | None = None,
    scenarios: list[str] | None = None,
    models: tuple[str, ...] = MODELS,
) -> dict:
    """One arm's answers on one batch (or on named households), as a
    dashboard payload, from ``models`` (the frontier three by default; cheap
    models for development, Max 2026-10-23)."""
    models = tuple(models)
    if len(models) < 2:
        raise SystemExit("a payload needs at least two models")
    prompt_model = prompt_model_for(models)
    if arm not in JUDGED_ARMS:
        raise SystemExit(f"only {sorted(JUDGED_ARMS)} are judged, not {arm}")
    if (batch is None) == (not scenarios):
        raise SystemExit("name a batch or households, not both")
    board = pilot.load_board(board_dir)
    ids = list(scenarios) if scenarios else load_batch(board_dir, batch)
    unknown = sorted(set(ids) - set(board["scenarios"]))
    if unknown:
        raise SystemExit(f"{board_dir} has no households {unknown}")
    scored = set(zip(board["scored"].scenario_id, board["scored"].variable))
    reference = board["reference"].set_index(["scenario_id", "variable"])["value"]
    records = {}
    for model in models:
        folder = runs / model / arm_folder(arm) / stage / "households"
        found = {}
        for sid in ids:
            path = folder / f"{sid}.json"
            if not path.exists():
                raise SystemExit(f"{path} is missing: the batch has not finished")
            found[sid] = json.loads(path.read_text())
        if pilot.records_model(found) != model or pilot.records_arm(found) != arm:
            raise SystemExit(f"{folder} does not hold {model} {arm} records")
        records[model] = found
    versions = {pilot.records_prompt(r)[0] for r in records.values()}
    if len(versions) != 1:
        raise SystemExit(f"the models ran different prompt versions: {versions}")
    prompt_version = versions.pop()

    labels = {model: f"{model}+{arm}" for model in models}
    scenarios, predictions, variables_seen = {}, {}, set()
    for sid in ids:
        scenario = board["scenarios"][sid]
        variables = board["variables"][sid]
        prompt = household_prompt(scenario, variables, prompt_version, prompt_model)
        sent = records[prompt_model][sid].get("sent_board_prompt_sha256")
        if sent != hashlib.sha256(prompt.encode()).hexdigest():
            raise SystemExit(
                f"{sid}: the rebuilt prompt is not the one {prompt_model} saw"
            )
        scenarios[sid] = {"prompt": {"tool": prompt}, "state": scenario.state}
        cells = {}
        for variable in variables:
            variables_seen.add(variable)
            cell = {}
            for model, label in labels.items():
                record = records[model][sid]
                cell[label] = {
                    "prediction": record["predictions"].get(variable),
                    "explanation": record["explanations"].get(variable),
                    "groundTruth": float(reference[(sid, variable)]),
                    "scored": (sid, variable) in scored,
                }
            cells[variable] = cell
        predictions[sid] = cells
    return {
        "country": "us",
        "source": {
            "board": str(board_dir),
            "board_reference_sha256": board["meta"].get("reference_csv_sha256"),
            "runs": str(runs),
            "stage": stage,
            "arm": arm,
            "batch": batch,
            "households": ids,
            "prompt_version": prompt_version,
        },
        "answerCondition": JUDGED_ARMS[arm],
        "models": list(models),
        "outputDefinitions": output_definitions(variables_seen, prompt_version),
        "modelStats": [{"model": labels[model]} for model in models],
        "scenarios": scenarios,
        "scenarioPredictions": predictions,
    }


def render_trace(system, scenario, variable: str) -> str:
    """The pruned computation trace of one output on ``system``."""
    import household_set
    from policyengine_us import Simulation

    from policybench.case_reference_explanations import (
        _find_target_tree,
        _render_trace,
    )
    from policybench.ground_truth import (
        _extract_person_value,
        _pe_variable_for_output,
        _person_index_for_output,
    )

    pe_variable = _pe_variable_for_output(variable, "us")
    simulation = Simulation(
        tax_benefit_system=system, situation=household_set.situation_for(scenario)
    )
    simulation.trace = True
    result = simulation.calculate(pe_variable, YEAR)
    tree = _find_target_tree(simulation.tracer.trees, pe_variable)
    if tree is None:
        raise RuntimeError(f"no trace for {pe_variable}")
    value = float(_extract_person_value(result, scenario, variable))
    lines = _render_trace(tree)
    cut = len(lines) > TRACE_MAX_LINES
    person = _person_index_for_output(scenario, variable)
    header = [
        f"Output {variable} = {value:g}, computed as the engine variable "
        f"{pe_variable} for {YEAR}"
        + (f", read for person index {person}." if person is not None else "."),
        "Each line is a variable and its value; a variable's inputs are indented "
        "beneath it. Zero-valued branches below the first level are omitted.",
        "",
    ]
    footer = [f"... ({len(lines) - TRACE_MAX_LINES} more lines cut)"] if cut else []
    return "\n".join(header + lines[:TRACE_MAX_LINES] + footer)


def command_payload(args) -> None:
    payload = build_payload(
        Path(args.board),
        Path(args.runs),
        args.stage,
        args.arm,
        batch=args.batch,
        scenarios=args.scenarios,
        models=tuple(args.models),
    )
    Path(args.out).write_text(json.dumps(payload, indent=1) + "\n")
    cells = sum(len(v) for v in payload["scenarioPredictions"].values())
    print(f"{len(payload['scenarios'])} households, {cells} cells, arm {args.arm}")


def command_derivations(args) -> None:
    board_dir = Path(args.board)
    pilot._require_engine(board_dir)
    payload = json.loads(Path(args.payload).read_text())
    if payload["source"]["board"] != str(board_dir):
        raise SystemExit("the payload is from another board")
    flags = json.loads(Path(args.flags).read_text())["flags"]
    board = pilot.load_board(board_dir)
    system = pilot.build_tool_system(reform=True, snapshot=board_dir)
    rows = []
    for flag in flags:
        sid, variable = flag["scenario_id"], flag["variable"]
        rows.append(
            {
                "country": "us",
                "scenario_id": sid,
                "variable": variable,
                "reference_value": flag["reference"],
                "trace_lines": None,
                "explanation": render_trace(system, board["scenarios"][sid], variable),
                "error": None,
            }
        )
    for row in rows:
        row["trace_lines"] = row["explanation"].count("\n") + 1
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        rows,
        columns=[
            "country",
            "scenario_id",
            "variable",
            "reference_value",
            "trace_lines",
            "explanation",
            "error",
        ],
    ).to_csv(out / "us_case_reference_explanations.csv", index=False)
    print(f"{len(rows)} derivations in {out}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    payload = sub.add_parser("payload", help="one arm's batch as a dashboard payload")
    payload.add_argument("--board", required=True)
    payload.add_argument("--runs", required=True)
    payload.add_argument("--stage", required=True)
    payload.add_argument("--arm", required=True, choices=sorted(JUDGED_ARMS))
    payload.add_argument("--batch", type=int)
    payload.add_argument(
        "--scenarios", nargs="*", help="households, for a board without batches"
    )
    payload.add_argument("--out", required=True)
    payload.add_argument(
        "--models", nargs="+", default=list(MODELS), help="the models to judge"
    )
    payload.set_defaults(func=command_payload)
    derivations = sub.add_parser("derivations", help="traces of flagged references")
    derivations.add_argument("--board", required=True)
    derivations.add_argument("--payload", required=True)
    derivations.add_argument("--flags", required=True)
    derivations.add_argument("--out-dir", required=True)
    derivations.set_defaults(func=command_derivations)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
