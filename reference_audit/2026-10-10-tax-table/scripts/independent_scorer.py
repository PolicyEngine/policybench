"""PolicyBench's headline exact rate, computed without the repo's scorer.

A second implementation of the published headline (the household-equal,
population-weighted exact-match rate), written from the benchmark's stated rule
and reading the run's files directly. It imports nothing from ``policybench``, so
agreement with ``policybench.analysis.weighted_hit_rate_scores_by_model`` is a
differential check on both.

The rule:
- An output is scored unless ``reference_exclusions.json`` lists it.
- An amount answer is exact when it is within $1 of the reference. A 0/1 output
  (its group ends in ``_eligible``) is exact when the answer is 0 or 1 and equals
  the reference. A missing answer is a miss.
- Each output belongs to a group: its own name, or ``person_<suffix>`` for a
  person's output such as ``head_medicaid_eligible``. Group weights come from the
  source population (``policybench/population_weights.json``, household kind),
  normalized over the groups present among the scored outputs.
- Inside a household a group's weight is split equally over its scored outputs
  and the household's weights are scaled to sum to one. The household's score is
  the weighted share of exact outputs. A household with no weight is left out.
- A model's rate is the mean of its household scores, times 100.

``also_accept`` gives a second accepted value for some outputs: an answer is then
exact when it is exact against either value.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WEIGHTS = ROOT / "policybench/population_weights.json"
PERSON_PREFIXES = ("adult", "child", "dependent")
TOLERANCE = 1.0


def group_weights() -> dict[str, float]:
    payload = json.loads(WEIGHTS.read_text(encoding="utf-8"))
    raw = payload["countries"]["us"]["weights"]["household"]
    return {group: max(0.0, float(weight)) for group, weight in raw.items()}


def output_group(variable: str, groups) -> str:
    """``person_<suffix>`` for a person's output, the output's own name otherwise."""
    suffixes = sorted(
        (g[len("person_") :] for g in groups if g.startswith("person_")),
        key=len,
        reverse=True,
    )
    for suffix in suffixes:
        marker = f"_{suffix}"
        if variable.endswith(marker):
            person = variable[: -len(marker)]
            if person in ("head", "spouse") or person.startswith(PERSON_PREFIXES):
                return f"person_{suffix}"
    return variable


def is_flag(group: str) -> bool:
    return group.endswith("_eligible")


def flag(value) -> int | None:
    if value == 0.0:
        return 0
    if value == 1.0:
        return 1
    return None


def exact(group: str, reference: float, answer: float | None) -> bool:
    if answer is None or math.isnan(answer):
        return False
    if is_flag(group):
        return flag(answer) is not None and flag(answer) == flag(reference)
    return abs(reference - answer) <= TOLERANCE


def read_reference(run_dir: Path) -> dict[tuple[str, str], float]:
    with (run_dir / "reference_outputs.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    record = run_dir / "reference_exclusions.json"
    excluded = set()
    if record.exists():
        excluded = {
            (str(e["scenario_id"]), str(e["variable"]))
            for e in json.loads(record.read_text())["exclusions"]
        }
    reference = {}
    for row in rows:
        key = (row["scenario_id"], row["variable"])
        if key in reference:
            raise ValueError(f"duplicate reference {key}")
        if key not in excluded:
            reference[key] = float(row["value"])
    return reference


def read_answers(run_dir: Path) -> dict[str, dict[tuple[str, str], float | None]]:
    raw = gzip.decompress((run_dir / "predictions.csv.gz").read_bytes())
    answers: dict[str, dict] = defaultdict(dict)
    csv.field_size_limit(1 << 30)
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")):
        key = (row["scenario_id"], row["variable"])
        if key in answers[row["model"]]:
            raise ValueError(f"duplicate answer {row['model']} {key}")
        text = row["prediction"].strip()
        answers[row["model"]][key] = float(text) if text else None
    return answers


def row_weights(reference: dict) -> dict[tuple[str, str], float]:
    """Each scored output's weight inside its household (weights sum to one)."""
    weights = group_weights()
    groups = {key: output_group(key[1], weights) for key in reference}
    present = set(groups.values())
    missing = present - set(weights)
    if missing:
        raise ValueError(f"no population weight for {sorted(missing)}")
    total = sum(weights[g] for g in present)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for (scenario, _), group in groups.items():
        counts[(scenario, group)] += 1
    raw = {
        key: weights[group] / total / counts[(key[0], group)]
        for key, group in groups.items()
    }
    sums: dict[str, float] = defaultdict(float)
    for (scenario, _), weight in raw.items():
        sums[scenario] += weight
    return {
        key: weight / sums[key[0]] for key, weight in raw.items() if sums[key[0]] > 0
    }


def rates(
    reference: dict, answers: dict, also_accept: dict | None = None
) -> dict[str, float]:
    """Each model's headline exact rate, in percent, from loaded data."""
    weights = row_weights(reference)
    known = group_weights()
    group_of = {key: output_group(key[1], known) for key in reference}
    households = sorted({scenario for scenario, _ in weights})
    out = {}
    for model, given in answers.items():
        scores = dict.fromkeys(households, 0.0)
        for key, weight in weights.items():
            answer = given.get(key)
            hit = exact(group_of[key], reference[key], answer)
            if not hit and also_accept and key in also_accept:
                hit = exact(group_of[key], float(also_accept[key]), answer)
            if hit:
                scores[key[0]] += weight
        out[model] = 100 * math.fsum(scores.values()) / len(households)
    return out


def exact_rates(run_dir: Path, also_accept: dict | None = None) -> dict[str, float]:
    """Each model's headline exact rate, in percent, from a run directory."""
    run_dir = Path(run_dir)
    return rates(read_reference(run_dir), read_answers(run_dir), also_accept)
