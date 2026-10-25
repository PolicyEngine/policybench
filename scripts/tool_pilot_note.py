"""The tool pilot behind the 2026-10-20 note: three board models given a tool that
runs PolicyEngine, on the board's 100 US households, and the note's facts.

scripts/tool_pilot_argon.py ran the pilot: Gemini 4 Argon on 2026-10-14, GPT-6 Sol
and Claude Opus 5.5 on 2026-10-15. Each model saw the board's prompt and request
settings plus ``calculate_household``, which runs policyengine-us 2.41.0 with the
reference builder's convention reform (reference_audit/2026-09-28/fixes/
latest_final.py) on a household the model writes as JSON. The no-tool arm is each
model's frozen board row in release dashboard-data-20261014.

Committed rows (notes/data/):
- tool_pilot_20261015.csv: each model's tool-arm answer for every scored output.
- tool_pilot_20261015_households.csv: per household, the tool arm's model turns,
  calculations, failed calculations, whether it hit the 8-turn cap, and its cost.
- tool_pilot_20261015_misses.csv: every tool-arm miss, with how the model's
  household or read-back differed from the reference's, as tool_pilot_argon.py's
  ``diagnose`` classified it.

Scoring is the board's: policybench.analysis.row_hit_scores (exact), the release's
globalWeights.household by output group, renormalised within each household, and an
equal-household mean over the scored outputs.

usage: python scripts/tool_pilot_note.py build <pilot results dir>  (CSVs and meta)
       python scripts/tool_pilot_note.py facts  (prints the note's facts)
"""

from __future__ import annotations

import csv
import datetime
import gzip
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from policybench.analysis import row_hit_scores  # noqa: E402
from policybench.spec import PERSON_OUTPUTS, output_group_id  # noqa: E402

RUN_DIR = (
    ROOT / "paper/snapshot/20260501/runs/"
    "us_full_run_20260612_policyengine_4_16_1_populace"
)
DATA = ROOT / "notes/data"
ROWS_PATH = DATA / "tool_pilot_20261015.csv"
HOUSEHOLDS_PATH = DATA / "tool_pilot_20261015_households.csv"
MISSES_PATH = DATA / "tool_pilot_20261015_misses.csv"
META_PATH = DATA / "tool_pilot_20261015.meta.json"
RELEASE = "dashboard-data-20261014"
# The pilot's run directories, by model, under the results dir build() reads.
RUNS = {
    "gemini-4-argon": "run",
    "gpt-6-sol": "gpt-6-sol/run",
    "claude-opus-5.5": "claude-opus-5.5/run",
}
RUN_DATES = {
    "gemini-4-argon": "2026-10-14",
    "gpt-6-sol": "2026-10-15",
    "claude-opus-5.5": "2026-10-15",
}
TURN_CAP = 8  # tool_pilot_argon.TOOL_TURN_CAP: calculation turns per household
# Misses that rest partly on a prompt label hiding a distinction the engine draws,
# as the pilot's diagnosis recorded them.
LABEL_NOTES = {
    ("gemini-4-argon", "scenario_076", "state_income_tax_before_refundable_credits"): (
        'The label "employer sponsored insurance premiums" never says the employer '
        "paid them; the engine's variable holds employer-paid premiums, and the "
        "model entered them as premiums the household paid."
    ),
    ("gpt-6-sol", "scenario_121", "snap"): (
        'The label "disability benefits" never says they are not Social Security; '
        "the engine's variable holds disability benefits from employment, and the "
        "model entered them as Social Security disability."
    ),
}
# How a tool-arm answer missed, from diagnose's category and mapping kind.
MISS_KINDS = {
    ("wrong_input_mapping", "entered_differently"): "fact_under_another_variable",
    ("wrong_input_mapping", "left_out"): "fact_left_out",
    ("wrong_variable_or_period", ""): "read_back_wrong_output",
}


# ---------------------------------------- build (one-time, from the pilot results)


def build(results: Path) -> None:
    rows, households, misses = [], [], []
    for model, sub in RUNS.items():
        run = results / sub
        with (run / "scored_rows.csv").open(encoding="utf-8", newline="") as source:
            for r in csv.DictReader(source):
                rows.append(
                    {
                        "model": model,
                        "scenario_id": r["scenario_id"],
                        "variable": r["variable"],
                        "tool_prediction": r["arm2"],
                    }
                )
        with (run / "usage_by_household.csv").open(encoding="utf-8") as source:
            for r in csv.DictReader(source):
                households.append(
                    {
                        "model": model,
                        "scenario_id": r["scenario_id"],
                        "model_turns": r["arm2_model_turns"],
                        "calculations": r["arm2_tool_calls"],
                        "failed_calculations": r["arm2_tool_errors"],
                        "turn_cap_hit": r["arm2_cap_hit"],
                        "tool_cost_usd": r["arm2_cost_usd"],
                    }
                )
        with (run / "misses.csv").open(encoding="utf-8", newline="") as source:
            for r in csv.DictReader(source):
                misses.append(
                    {
                        "model": model,
                        "scenario_id": r["scenario_id"],
                        "variable": r["variable"],
                        "reference": r["reference"],
                        "tool_prediction": r["arm2"],
                        "no_tool_hit": r["arm1_hit"],
                        "kind": MISS_KINDS[(r["category"], r["mapping_kind"])],
                        "entered_as": r["entered_as"],
                        "single_causes": r["single_causes"],
                        "necessary_inputs": r["necessary_inputs"],
                        "detail": r["detail"],
                        "prompt_label_note": LABEL_NOTES.get(
                            (model, r["scenario_id"], r["variable"]), ""
                        ),
                    }
                )
    DATA.mkdir(parents=True, exist_ok=True)
    for path, data in (
        (ROWS_PATH, rows),
        (HOUSEHOLDS_PATH, households),
        (MISSES_PATH, misses),
    ):
        with path.open("w", encoding="utf-8", newline="") as sink:
            writer = csv.DictWriter(sink, fieldnames=list(data[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(data)
    meta = {
        "release": RELEASE,
        "source_run": RUN_DIR.name,
        "runner": "scripts/tool_pilot_argon.py",
        "run_dates": RUN_DATES,
        "tool": (
            "calculate_household: policyengine-us 2.41.0 with "
            "reference_audit/2026-09-28/fixes/latest_final.py, the reference "
            "builder's convention reform, on a household the model writes as JSON"
        ),
        "turn_cap": TURN_CAP,
        "oracle": json.loads((results / "oracle_summary.json").read_text())["summary"],
        "no_tool_arm": "each model's frozen board row in the release",
        "files": {
            p.name: {"rows": n, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p, n in (
                (ROWS_PATH, len(rows)),
                (HOUSEHOLDS_PATH, len(households)),
                (MISSES_PATH, len(misses)),
            )
        },
        "generated_at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "script": "scripts/tool_pilot_note.py",
    }
    META_PATH.write_text(json.dumps(meta, indent=2) + "\n")


# ---------------------------------------- scoring and facts


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def references() -> dict:
    excluded = {
        (e["scenario_id"], e["variable"])
        for e in json.loads((RUN_DIR / "reference_exclusions.json").read_text())[
            "exclusions"
        ]
    }
    with (RUN_DIR / "reference_outputs.csv").open(
        encoding="utf-8", newline=""
    ) as source:
        return {
            (r["scenario_id"], r["variable"]): float(r["value"])
            for r in csv.DictReader(source)
            if (r["scenario_id"], r["variable"]) not in excluded
        }


def weights(keys, global_weights: dict) -> dict:
    by = defaultdict(list)
    for sid, var in keys:
        by[(sid, output_group_id(var))].append(var)
    w = {}
    for (sid, group), variables in by.items():
        for var in variables:
            w[(sid, var)] = global_weights.get(group, 0.0) / len(variables)
    total = defaultdict(float)
    for (sid, _), x in w.items():
        total[sid] += x
    return {k: (x / total[k[0]] if total[k[0]] > 0 else 0.0) for k, x in w.items()}


def hit(ref: dict, key, prediction) -> float:
    return row_hit_scores(key[1], ref[key], prediction)["exact"]


def weighted_exact(preds: dict, ref: dict, w: dict) -> float:
    scores = []
    for sid in sorted({k[0] for k in ref}):
        keys = [k for k in ref if k[0] == sid]
        if sum(w[k] for k in keys) > 0:
            scores.append(sum(w[k] * hit(ref, k, preds.get(k)) for k in keys))
    return 100 * sum(scores) / len(scores)


def board_predictions(payload: dict, model: str) -> dict:
    preds = {}
    for sid, variables in payload["scenarioPredictions"].items():
        for var, models in variables.items():
            if model in models:
                row = models[model]
                preds[(sid, var)] = row.get("prediction") if row.get("parsed") else None
    return preds


def tool_predictions(rows: list[dict], model: str) -> dict:
    return {
        (r["scenario_id"], r["variable"]): float(r["tool_prediction"])
        for r in rows
        if r["model"] == model and r["tool_prediction"] not in ("", "nan", "None")
    }


def is_amount(variable: str) -> bool:
    """A dollar amount, not a 1/0 eligibility decision."""
    binary = {k for k, v in PERSON_OUTPUTS.items() if v["metric_type"] == "binary"}
    return output_group_id(variable) not in binary and not variable.endswith(
        "_eligible"
    )


def label_share() -> tuple[int, int]:
    """Stated input facts (not ages or wages) whose prompt label turns back into the
    engine variable it sets, by lowercasing it and replacing spaces with
    underscores, and all stated input facts."""
    from policybench.prompts import _humanize_input_label
    from policybench.scenarios import (
        is_excluded_prompt_input_name,
        scenario_from_dict,
    )

    csv.field_size_limit(sys.maxsize)
    matches = total = 0
    with (RUN_DIR / "scenarios.csv").open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            s = scenario_from_dict(json.loads(row["scenario_json"]))
            fields = [f for p in s.adults + s.children for f in p.inputs]
            fields += [*s.tax_unit_inputs, *s.spm_unit_inputs, *s.household_inputs]
            for field in fields:
                if is_excluded_prompt_input_name(field):
                    continue
                total += 1
                matches += (
                    _humanize_input_label(field).lower().replace(" ", "_") == field
                )
    return matches, total


def right_to_wrong(model: str) -> int:
    """Tool-arm misses the model answered right without the tool."""
    return sum(
        r["model"] == model and r["no_tool_hit"] == "True" for r in _read(MISSES_PATH)
    )


def fixes(payload: dict, model: str) -> tuple[int, int]:
    """Outputs the tool turned from wrong to right, all and nonzero amounts only."""
    ref = references()
    board = board_predictions(payload, model)
    tool = tool_predictions(_read(ROWS_PATH), model)
    fixed = [
        k for k in ref if not hit(ref, k, board.get(k)) and hit(ref, k, tool.get(k))
    ]
    return len(fixed), sum(is_amount(k[1]) and ref[k] != 0 for k in fixed)


def facts(payload: dict) -> dict:
    ref = references()
    w = weights(ref.keys(), payload["globalWeights"]["household"])
    rows, households, misses = (
        _read(ROWS_PATH),
        _read(HOUSEHOLDS_PATH),
        _read(MISSES_PATH),
    )
    stats = {
        r["model"]: r for r in payload["modelStats"] if r["condition"] == "no_tools"
    }
    nonzero = [k for k in ref if is_amount(k[1]) and ref[k] != 0]
    short = {"gpt-6-sol": "sol", "claude-opus-5.5": "opus", "gemini-4-argon": "argon"}

    def one(x: float) -> float:
        return float(f"{x:.1f}")

    out = {"households": len({k[0] for k in ref}), "nonzeroAmounts": len(nonzero)}
    for model, s in short.items():
        board, tool = board_predictions(payload, model), tool_predictions(rows, model)
        out[f"{s}BoardExact"] = one(weighted_exact(board, ref, w))
        out[f"{s}ToolExact"] = one(weighted_exact(tool, ref, w))
        out[f"{s}NonzeroRate"] = one(
            100 * sum(hit(ref, k, board.get(k)) for k in nonzero) / len(nonzero)
        )
        out[f"{s}NonzeroToolRate"] = one(
            100 * sum(hit(ref, k, tool.get(k)) for k in nonzero) / len(nonzero)
        )
        out[f"{s}Misses"] = sum(r["model"] == model for r in misses)
        out[f"{s}BoardCost"] = f"{stats[model]['costUsd']:.2f}"
        tool_cost = sum(
            float(h["tool_cost_usd"]) for h in households if h["model"] == model
        )
        out[f"{s}ToolCost"] = f"{tool_cost:.2f}"
    out["toolMisses"] = len(misses)
    out["enteredElsewhere"] = sum(
        r["kind"] == "fact_under_another_variable" for r in misses
    )
    out["leftOut"] = sum(r["kind"] == "fact_left_out" for r in misses)
    out["wrongOutput"] = sum(r["kind"] == "read_back_wrong_output" for r in misses)
    out["solFlips"] = sum(
        r["model"] == "gpt-6-sol" and r["no_tool_hit"] == "True" for r in misses
    )
    out["labelMisses"] = sum(bool(r["prompt_label_note"]) for r in misses)
    capped = {
        (h["model"], h["scenario_id"])
        for h in households
        if h["turn_cap_hit"] == "True"
    }
    out["solCapMisses"] = sum(
        r["model"] == "gpt-6-sol" and (r["model"], r["scenario_id"]) in capped
        for r in misses
    )
    out["turnCap"] = TURN_CAP
    out["labelMatches"], out["statedFacts"] = label_share()
    return out


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        build(Path(sys.argv[2]).expanduser())
    elif sys.argv[1:2] == ["facts"]:
        payload = json.load(gzip.open(RUN_DIR / "data.json.gz"))
        print(json.dumps(facts(payload), indent=1))
    else:
        sys.exit(__doc__)
