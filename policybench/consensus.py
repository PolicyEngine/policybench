"""Flag scored cells where a cluster of models agrees on the same wrong answer.

A cell is one scenario's one output. Models answer from parametric knowledge,
so a single model missing the reference says little about the reference. Many
models landing on the same wrong number, or several of the strongest models
doing so, is a different signal: it suggests the reference itself may be wrong
(a convention the prompt did not state, an engine defect, or later law). This
module is the trigger that picks those cells out of a frozen dashboard payload
so a reviewer or a reference adversary can look at them first. It never
changes a score or a reference; it only lists cells.

The rule, over scored cells only:

1. Each model's parsed prediction is rounded to a key (``answer_rounding``):
   ``"nearest"`` is half-up to whole dollars (``math.floor(x + 0.5)``),
   ``"truncate"`` drops the fraction toward zero (``int(x)``), and ``"cents"``
   is half-up to 0.01 on the prediction's shortest decimal form. Models that
   share a key form a cluster. A prediction that did not parse, or that is
   ``None``, NaN or infinite, joins no cluster.
2. A cluster is wrong when its key differs from the reference by more than
   ``tolerance`` dollars. On an eligibility output (``metric_type`` binary in
   ``benchmark_specs.json``) a 0/1 answer can never differ from a 0/1
   reference by more than a dollar, so ``binary_outputs`` decides those:
   ``"mismatch"`` (the default) calls a cluster wrong when its key is not the
   reference, and ``"skip"`` applies the dollar tolerance and so never flags
   one, as the prototype did. The models-exact count follows the same test.
3. A wrong cluster triggers when it has at least ``min_models`` members
   (``"min_models"``) or at least ``min_top`` of the ``top_k`` best models by
   the payload's ``modelStats`` order (``"min_top"``).
4. A wrong cluster whose key is zero also needs at least
   ``zero_cluster_min_models`` members, so a few strong models agreeing that
   a household gets nothing cannot flag a cell on the ``min_top`` trigger
   alone. On the frozen 20260612 payload this guard removes no flag at the
   prototype, default or cents parameters; it bounds what the trigger can do
   on other boards.

A cell is flagged when any of its wrong clusters triggers, and the flag lists
only the clusters that triggered. ``PROTOTYPE_PARAMS`` reproduces the
prototype that first ran this rule on 2026-10-05: answers truncated to whole
dollars and eligibility outputs never flagged (41 of the frozen run's 1,928
scored cells). The default parameters round to the nearest dollar, which also
merges answers such as 13,387.65 and 13,388 that truncation splits (43 amount
cells), and compare eligibility flags by mismatch (18 more).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

ANSWER_ROUNDINGS = ("nearest", "truncate", "cents")
BINARY_OUTPUTS = ("mismatch", "skip")
TRIGGERS = ("min_models", "min_top")
# Rounded keys are kept as integers in these units so that clusters group by
# exact equality rather than by float comparison.
_UNITS_PER_DOLLAR = {"nearest": 1, "truncate": 1, "cents": 100}
_CENT = Decimal("0.01")


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class ConsensusParams:
    """Thresholds of the consensus trigger; see the module docstring."""

    min_models: int = 15
    top_k: int = 5
    min_top: int = 3
    tolerance: float = 1.0
    answer_rounding: str = "nearest"
    zero_cluster_min_models: int = 15
    binary_outputs: str = "mismatch"

    def __post_init__(self) -> None:
        for name in ("min_models", "top_k", "min_top", "zero_cluster_min_models"):
            value = getattr(self, name)
            if not _is_count(value) or value < 1:
                raise ValueError(f"{name} must be an integer of at least 1: {value!r}")
        if self.min_top > self.top_k:
            raise ValueError(
                f"min_top ({self.min_top}) cannot exceed top_k ({self.top_k}); "
                "the min_top trigger could never fire"
            )
        tolerance = self.tolerance
        if (
            isinstance(tolerance, bool)
            or not isinstance(tolerance, (int, float))
            or not math.isfinite(tolerance)
            or tolerance < 0
        ):
            raise ValueError(
                f"tolerance must be a finite number of at least 0: {tolerance!r}"
            )
        object.__setattr__(self, "tolerance", float(tolerance))
        if self.answer_rounding not in ANSWER_ROUNDINGS:
            raise ValueError(
                f"answer_rounding must be one of {ANSWER_ROUNDINGS}: "
                f"{self.answer_rounding!r}"
            )
        if self.binary_outputs not in BINARY_OUTPUTS:
            raise ValueError(
                f"binary_outputs must be one of {BINARY_OUTPUTS}: "
                f"{self.binary_outputs!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        """The parameters as a JSON-ready dict, in field order."""
        return asdict(self)


PROTOTYPE_PARAMS = ConsensusParams(answer_rounding="truncate", binary_outputs="skip")


def load_us_payload(path: Path | str) -> dict:
    """Read a US dashboard payload from ``.json`` or ``.json.gz``.

    Accepts both the per-country payload frozen under ``paper/snapshot`` and
    the combined ``{"countries": {"us": ...}}`` shape of a dashboard release
    asset, and returns the US payload either way.
    """
    path = Path(path)
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: payload is not a JSON object")
    if "countries" in payload:
        countries = payload["countries"]
        if not isinstance(countries, dict) or "us" not in countries:
            raise ValueError(f"{path}: combined payload has no 'us' country")
        payload = countries["us"]
    country = payload.get("country")
    if country is not None and country != "us":
        raise ValueError(f"{path}: payload is for country {country!r}, not 'us'")
    if "scenarioPredictions" not in payload or "modelStats" not in payload:
        raise ValueError(f"{path}: payload lacks scenarioPredictions or modelStats")
    return payload


def file_sha256(path: Path | str) -> str:
    """The sha256 of a file's bytes, as lowercase hex."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def ranked_models(payload: dict) -> list[str]:
    """Model ids in the payload's ``modelStats`` order (best first).

    The dashboard export orders ``modelStats`` by the headline metric, so this
    order is the only ranking the trigger uses; the order of models inside
    ``scenarioPredictions`` never matters.
    """
    stats = payload.get("modelStats")
    if not isinstance(stats, list):
        raise ValueError("payload modelStats must be a list")
    models = [row["model"] for row in stats]
    duplicates = sorted({model for model in models if models.count(model) > 1})
    if duplicates:
        raise ValueError(f"modelStats lists models more than once: {duplicates}")
    return models


def _answer_units(value: float, rounding: str) -> int:
    """A prediction's rounded key in integer units of the rounding mode."""
    if rounding == "nearest":
        return math.floor(value + 0.5)
    if rounding == "truncate":
        return int(value)
    cents = Decimal(repr(value)).quantize(_CENT, rounding=ROUND_HALF_UP)
    return int(cents * 100)


def _answer(entry: Any) -> float | None:
    """A model's prediction if it parsed to a finite number, else ``None``."""
    if not isinstance(entry, dict) or entry.get("parsed") is False:
        return None
    value = entry.get("prediction")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _is_binary(variable: str) -> bool:
    """Whether an output is an eligibility flag (``metric_type`` binary)."""
    from policybench.spec import metric_type_for_output

    return metric_type_for_output(variable) == "binary"


def _misses(answer: float, reference: float, binary: bool, tolerance: float) -> bool:
    """Whether an answer (or a cluster's key) misses the reference."""
    if binary:
        return answer != reference
    return abs(answer - reference) > tolerance


def _cell_reference(
    scenario_id: str, variable: str, cell: dict[str, Any]
) -> tuple[bool, float | None]:
    """Whether a cell is scored, and its reference value if it is."""
    scored = {bool(entry.get("scored")) for entry in cell.values()}
    if len(scored) != 1:
        raise ValueError(f"{scenario_id} {variable}: models disagree on scored")
    if not scored.pop():
        return False, None
    references = {json.dumps(entry.get("groundTruth")) for entry in cell.values()}
    if len(references) != 1:
        raise ValueError(f"{scenario_id} {variable}: models disagree on groundTruth")
    reference = next(iter(cell.values())).get("groundTruth")
    if (
        isinstance(reference, bool)
        or not isinstance(reference, (int, float))
        or not math.isfinite(reference)
    ):
        raise ValueError(
            f"{scenario_id} {variable}: scored cell has no finite reference: "
            f"{reference!r}"
        )
    return True, float(reference)


def _scan(payload: dict, params: ConsensusParams) -> tuple[int, list[dict]]:
    """Count the scored cells and collect the flags, in (scenario, variable)."""
    top_models = ranked_models(payload)[: params.top_k]
    top_rank = {model: rank for rank, model in enumerate(top_models)}
    scale = _UNITS_PER_DOLLAR[params.answer_rounding]
    scenarios = payload.get("scenarios") or {}
    predictions = payload["scenarioPredictions"]
    scored_cells = 0
    flags: list[dict] = []
    for scenario_id in sorted(predictions):
        outputs = predictions[scenario_id]
        for variable in sorted(outputs):
            cell = outputs[variable]
            if not cell:
                continue
            scored, reference = _cell_reference(scenario_id, variable, cell)
            if not scored:
                continue
            scored_cells += 1
            binary = params.binary_outputs == "mismatch" and _is_binary(variable)
            answers = {
                model: answer
                for model, entry in sorted(cell.items())
                if (answer := _answer(entry)) is not None
            }
            keys = {
                model: _answer_units(answer, params.answer_rounding)
                for model, answer in answers.items()
            }
            groups: dict[int, list[str]] = {}
            for model, units in keys.items():
                groups.setdefault(units, []).append(model)
            # An eligibility answer counts as exact by its rounded value; an
            # amount by its raw value within the tolerance.
            compared = (
                {model: units / scale for model, units in keys.items()}
                if binary
                else answers
            )
            clusters = []
            triggers: set[str] = set()
            for units, members in groups.items():
                answer = units / scale
                if not _misses(answer, reference, binary, params.tolerance):
                    continue
                top = sorted(
                    (model for model in members if model in top_rank),
                    key=top_rank.__getitem__,
                )
                met = []
                if len(members) >= params.min_models:
                    met.append("min_models")
                if len(top) >= params.min_top:
                    met.append("min_top")
                if not met:
                    continue
                if units == 0 and len(members) < params.zero_cluster_min_models:
                    continue
                triggers.update(met)
                clusters.append(
                    {
                        "answer": float(answer),
                        "n_models": len(members),
                        "n_top": len(top),
                        "models": sorted(members),
                        "top_models": top,
                        "predictions": {
                            model: answers[model] for model in sorted(members)
                        },
                    }
                )
            if not clusters:
                continue
            if scenario_id not in scenarios:
                raise ValueError(f"{scenario_id}: missing from payload scenarios")
            clusters.sort(key=lambda cluster: (-cluster["n_models"], cluster["answer"]))
            flags.append(
                {
                    "scenario_id": scenario_id,
                    "variable": variable,
                    "state": scenarios[scenario_id].get("state"),
                    "reference": reference,
                    "models_answered": len(answers),
                    "models_exact": sum(
                        not _misses(value, reference, binary, params.tolerance)
                        for value in compared.values()
                    ),
                    "trigger": sorted(triggers),
                    "clusters": clusters,
                }
            )
    return scored_cells, flags


def consensus_flags(
    payload: dict, params: ConsensusParams = ConsensusParams()
) -> list[dict]:
    """The scored cells where a wrong-answer cluster triggers.

    Each flag carries the cell's scenario, variable, state and reference, how
    many models answered and how many matched the reference (within the
    tolerance; an eligibility flag by its rounded value), the triggers that
    fired, and the triggering clusters (largest first, then by answer). Flags
    are sorted by scenario id, then variable.
    """
    return _scan(payload, params)[1]


def consensus_report(
    payload: dict,
    params: ConsensusParams = ConsensusParams(),
    *,
    source: str = "",
    source_sha256: str = "",
) -> dict:
    """The flags with the parameters and counts needed to reproduce them.

    ``source`` and ``source_sha256`` name the payload file the caller read, so
    a saved report stays bound to the exact bytes it was computed from.
    """
    scored_cells, flags = _scan(payload, params)
    return {
        "params": params.to_dict(),
        "top_models": ranked_models(payload)[: params.top_k],
        "source": source,
        "source_sha256": source_sha256,
        "models": len(ranked_models(payload)),
        "scored_cells": scored_cells,
        "flagged_cells": len(flags),
        "flags": flags,
    }
