"""The consensus trigger flags cells where many models agree on a wrong answer."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import math
import subprocess
import tempfile
from dataclasses import fields, replace
from decimal import ROUND_HALF_UP, Decimal
from functools import cache
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from policybench.consensus import (
    ANSWER_ROUNDINGS,
    BINARY_OUTPUTS,
    PROTOTYPE_PARAMS,
    TRIGGERS,
    ConsensusParams,
    _answer_units,
    consensus_flags,
    consensus_report,
    file_sha256,
    load_us_payload,
    ranked_models,
)
from policybench.spec import metric_type_for_output

ROOT = Path(__file__).resolve().parents[1]
# The payload the pass ran on: release dashboard-data-20260930's, as #187
# committed it. Later releases rewrite the working tree's payload (#202 did),
# so the tests read it from git; CI checks out full history.
PASS_COMMIT = "8b4c0ca146bb6f66deba6ce24009d49d70d92df2"
PAYLOAD_PATH = (
    "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/"
    "data.json.gz"
)
FROZEN_SHA256 = "1e029aaa87d1dfbd2ceee88419599a919dd7c9d4aba78a308ec48d008d54ae18"
TOP_FIVE = [
    "gpt-6-sol",
    "claude-opus-5.5",
    "gpt-5.6-sol",
    "gpt-6-luna",
    "claude-sonnet-5.5",
]
_PROTOTYPE_TEXT = """
scenario_007 state_refundable_credits
scenario_013 snap, state_refundable_credits
scenario_014 state_income_tax_before_refundable_credits
scenario_018 state_income_tax_before_refundable_credits
scenario_023 federal_income_tax_before_refundable_credits,
    state_income_tax_before_refundable_credits, state_refundable_credits
scenario_026 federal_refundable_credits
scenario_027 snap
scenario_028 payroll_tax, state_refundable_credits
scenario_029 state_refundable_credits
scenario_030 snap
scenario_032 payroll_tax
scenario_038 state_refundable_credits
scenario_043 payroll_tax, state_refundable_credits
scenario_045 state_refundable_credits
scenario_051 state_income_tax_before_refundable_credits
scenario_053 state_refundable_credits
scenario_054 snap
scenario_056 state_refundable_credits
scenario_057 state_refundable_credits
scenario_066 state_refundable_credits
scenario_073 snap
scenario_076 state_refundable_credits
scenario_077 state_income_tax_before_refundable_credits
scenario_079 snap, state_refundable_credits
scenario_082 payroll_tax, state_refundable_credits
scenario_085 state_income_tax_before_refundable_credits
scenario_100 tanf
scenario_108 snap
scenario_112 federal_refundable_credits
scenario_115 state_income_tax_before_refundable_credits
scenario_118 state_refundable_credits
scenario_121 snap
scenario_123 payroll_tax, state_income_tax_before_refundable_credits
"""
BINARY_CELLS = {
    ("scenario_026", "child1_medicaid_eligible"),
    ("scenario_026", "child2_medicaid_eligible"),
    ("scenario_026", "child3_medicaid_eligible"),
    ("scenario_028", "child1_chip_eligible"),
    ("scenario_028", "child2_chip_eligible"),
    ("scenario_028", "child3_chip_eligible"),
    ("scenario_029", "head_medicaid_eligible"),
    ("scenario_031", "head_medicaid_eligible"),
    ("scenario_032", "free_school_meals_eligible"),
    ("scenario_032", "reduced_price_school_meals_eligible"),
    ("scenario_032", "spouse_medicaid_eligible"),
    ("scenario_039", "head_medicare_eligible"),
    ("scenario_054", "head_wic_eligible"),
    ("scenario_075", "head_medicare_eligible"),
    ("scenario_099", "free_school_meals_eligible"),
    ("scenario_119", "child1_chip_eligible"),
    ("scenario_119", "child2_chip_eligible"),
    ("scenario_121", "head_medicare_eligible"),
}
FLAG_KEYS = {
    "scenario_id",
    "variable",
    "state",
    "reference",
    "models_answered",
    "models_exact",
    "trigger",
    "clusters",
}
CLUSTER_KEYS = {"answer", "n_models", "n_top", "models", "top_models", "predictions"}
REPORT_KEYS = {
    "params",
    "top_models",
    "source",
    "source_sha256",
    "models",
    "scored_cells",
    "flagged_cells",
    "flags",
}


def _parse_cells(text: str) -> set[tuple[str, str]]:
    cells = set()
    for line in " ".join(text.split("\n")).split("scenario_")[1:]:
        number, rest = line.split(" ", 1)
        for variable in rest.split(","):
            if variable.strip():
                cells.add((f"scenario_{number}", variable.strip()))
    return cells


PROTOTYPE_CELLS = _parse_cells(_PROTOTYPE_TEXT)


def _entry(prediction, reference, scored: bool) -> dict:
    """A scenarioPredictions entry; ``("unparsed", x)`` marks parsed=False."""
    parsed = prediction is not None
    if isinstance(prediction, tuple):
        parsed, prediction = False, prediction[1]
    return {
        "prediction": prediction,
        "groundTruth": reference,
        "scored": scored,
        "parsed": parsed,
    }


def make_payload(ranking: list[str], cells: dict, states: dict | None = None) -> dict:
    """A minimal US payload from ``{(scenario, variable): (ref, scored, preds)}``."""
    predictions: dict = {}
    for (scenario_id, variable), (reference, scored, answers) in cells.items():
        predictions.setdefault(scenario_id, {})[variable] = {
            model: _entry(answer, reference, scored)
            for model, answer in answers.items()
        }
    states = states or {}
    return {
        "country": "us",
        "scenarios": {
            scenario_id: {"country": "us", "state": states.get(scenario_id, "CA")}
            for scenario_id in predictions
        },
        "modelStats": [{"model": model} for model in ranking],
        "scenarioPredictions": predictions,
    }


def _keys(flags: list[dict]) -> set[tuple[str, str]]:
    return {(flag["scenario_id"], flag["variable"]) for flag in flags}


def _cluster_keys(flags: list[dict]) -> set[tuple[str, str, float]]:
    return {
        (flag["scenario_id"], flag["variable"], cluster["answer"])
        for flag in flags
        for cluster in flag["clusters"]
    }


def _oracle_key(value: float, rounding: str) -> float:
    """The rounding rule written independently of the module."""
    if rounding == "nearest":
        return float(math.floor(value + 0.5))
    if rounding == "truncate":
        return float(math.trunc(value))
    return float(Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def _binary(variable: str, params: ConsensusParams) -> bool:
    return (
        params.binary_outputs == "mismatch"
        and metric_type_for_output(variable) == "binary"
    )


def _oracle(payload: dict, params: ConsensusParams) -> set[tuple[str, str, float]]:
    """Brute-force (scenario, variable, answer) of every triggering cluster."""
    top = [row["model"] for row in payload["modelStats"]][: params.top_k]
    found = set()
    for scenario_id, outputs in payload["scenarioPredictions"].items():
        for variable, cell in outputs.items():
            entries = list(cell.values())
            if not entries or not entries[0]["scored"]:
                continue
            reference = entries[0]["groundTruth"]
            keyed = {}
            raw = {}
            for model, entry in cell.items():
                value = entry["prediction"]
                if entry["parsed"] and value is not None and math.isfinite(value):
                    keyed[model] = _oracle_key(value, params.answer_rounding)
                    raw[model] = value
            binary = _binary(variable, params)
            for key in set(keyed.values()):
                if binary and key == reference:
                    continue
                if not binary and abs(key - reference) <= params.tolerance:
                    continue
                # An amount answer within the tolerance is exact, whatever its key.
                members = [
                    model
                    for model, other in keyed.items()
                    if other == key
                    and (binary or abs(raw[model] - reference) > params.tolerance)
                ]
                if not members:
                    continue
                n_top = sum(model in members for model in top)
                if len(members) < params.min_models and n_top < params.min_top:
                    continue
                if key == 0 and len(members) < params.zero_cluster_min_models:
                    continue
                found.add((scenario_id, variable, key))
    return found


def check_flag_invariants(
    payload: dict, params: ConsensusParams, flags: list[dict]
) -> None:
    """Properties every flag list must satisfy, for any payload and params."""
    top = ranked_models(payload)[: params.top_k]
    assert [(f["scenario_id"], f["variable"]) for f in flags] == sorted(_keys(flags))
    for flag in flags:
        assert set(flag) == FLAG_KEYS
        cell = payload["scenarioPredictions"][flag["scenario_id"]][flag["variable"]]
        entries = list(cell.values())
        # Only scored cells are flagged, against their own reference.
        assert all(entry["scored"] for entry in entries)
        assert flag["reference"] == entries[0]["groundTruth"]
        assert flag["state"] == payload["scenarios"][flag["scenario_id"]]["state"]
        assert 0 <= flag["models_exact"] <= flag["models_answered"] <= len(cell)
        assert flag["trigger"] and flag["trigger"] == sorted(set(flag["trigger"]))
        assert set(flag["trigger"]) <= set(TRIGGERS)
        clusters = flag["clusters"]
        assert clusters
        order = [(-cluster["n_models"], cluster["answer"]) for cluster in clusters]
        assert order == sorted(order)
        seen: set[str] = set()
        met_any: set[str] = set()
        for cluster in clusters:
            assert set(cluster) == CLUSTER_KEYS
            members = cluster["models"]
            # Clusters within a cell are disjoint.
            assert not seen & set(members)
            seen |= set(members)
            assert members == sorted(members)
            assert cluster["n_models"] == len(members)
            assert set(cluster["predictions"]) == set(members)
            assert cluster["top_models"] == [model for model in top if model in members]
            assert cluster["n_top"] == len(cluster["top_models"])
            # Every flagged cluster is wrong: by more than the tolerance, or, on
            # an eligibility output compared by mismatch, by its flag.
            if _binary(flag["variable"], params):
                assert cluster["answer"] != flag["reference"]
            else:
                assert abs(cluster["answer"] - flag["reference"]) > params.tolerance
            for model, prediction in cluster["predictions"].items():
                assert prediction == cell[model]["prediction"]
                # No member of a wrong cluster also counts as exact.
                if not _binary(flag["variable"], params):
                    assert abs(prediction - flag["reference"]) > params.tolerance
                assert (
                    _oracle_key(prediction, params.answer_rounding)
                    == (cluster["answer"])
                )
            met = set()
            if cluster["n_models"] >= params.min_models:
                met.add("min_models")
            if cluster["n_top"] >= params.min_top:
                met.add("min_top")
            assert met
            met_any |= met
            # The zero rule: a zero cluster needs the larger membership.
            if cluster["answer"] == 0:
                assert cluster["n_models"] >= params.zero_cluster_min_models
        assert set(flag["trigger"]) == met_any


# Synthetic payloads -----------------------------------------------------------

MODEL_POOL = [f"model_{index:02d}" for index in range(10)]
VARIABLES = [
    "snap",
    "payroll_tax",
    "state_refundable_credits",
    "tanf",
    "head_medicaid_eligible",
    "free_school_meals_eligible",
]


@st.composite
def payloads(draw) -> dict:
    """Small payloads whose predictions crowd a few answers so clusters form."""
    models = MODEL_POOL[: draw(st.integers(2, len(MODEL_POOL)))]
    ranking = list(draw(st.permutations(models)))
    cells = {}
    for index in range(draw(st.integers(1, 3))):
        scenario_id = f"scenario_{index:03d}"
        for variable in draw(st.lists(st.sampled_from(VARIABLES), min_size=1)):
            reference = draw(
                st.sampled_from([0.0, 1.0, 100.0, 1590.5, 14192.66, -40.0])
                | st.floats(-1e5, 1e5, allow_nan=False)
            )
            near = [
                reference,
                reference + 0.4,
                reference - 0.6,
                reference + 5.0,
                reference + 5.5,
                0.0,
                0.3,
                -0.7,
                13387.65,
                13388.0,
                1.005,
            ]
            answers = {}
            for model in models:
                kind = draw(st.sampled_from(["near"] * 6 + ["any", "odd"]))
                if kind == "near":
                    answers[model] = draw(st.sampled_from(near))
                elif kind == "any":
                    answers[model] = draw(st.floats(-1e5, 1e5, allow_nan=False))
                else:
                    answers[model] = draw(
                        st.sampled_from(
                            [None, math.nan, math.inf, -math.inf, ("unparsed", 0.0)]
                        )
                    )
            cells[(scenario_id, variable)] = (reference, draw(st.booleans()), answers)
    return make_payload(ranking, cells)


@st.composite
def params(draw) -> ConsensusParams:
    top_k = draw(st.integers(1, 6))
    return ConsensusParams(
        min_models=draw(st.integers(1, 8)),
        top_k=top_k,
        min_top=draw(st.integers(1, top_k)),
        tolerance=draw(
            st.sampled_from([0.0, 0.5, 1.0, 5.0]) | st.floats(0, 20, allow_nan=False)
        ),
        answer_rounding=draw(st.sampled_from(ANSWER_ROUNDINGS)),
        zero_cluster_min_models=draw(st.integers(1, 10)),
        binary_outputs=draw(st.sampled_from(BINARY_OUTPUTS)),
    )


@settings(max_examples=300, deadline=None)
@given(payload=payloads(), consensus=params())
def test_flags_satisfy_invariants_and_match_brute_force(payload, consensus):
    flags = consensus_flags(payload, consensus)
    check_flag_invariants(payload, consensus, flags)
    # Completeness as well as soundness: exactly the brute-force clusters.
    assert _cluster_keys(flags) == _oracle(payload, consensus)


@settings(max_examples=300, deadline=None)
@given(payload=payloads(), consensus=params(), data=st.data())
def test_raising_a_threshold_never_adds_a_flag(payload, consensus, data):
    field = data.draw(
        st.sampled_from(
            ["min_models", "min_top", "zero_cluster_min_models", "tolerance"]
        )
    )
    if field == "tolerance":
        raised = consensus.tolerance + data.draw(st.floats(0, 50, allow_nan=False))
    elif field == "min_top":
        raised = data.draw(st.integers(consensus.min_top, consensus.top_k))
    else:
        raised = getattr(consensus, field) + data.draw(st.integers(0, 20))
    stricter = replace(consensus, **{field: raised})
    before = consensus_flags(payload, consensus)
    after = consensus_flags(payload, stricter)
    assert _keys(after) <= _keys(before)
    assert _cluster_keys(after) <= _cluster_keys(before)


@settings(max_examples=200, deadline=None)
@given(payload=payloads(), consensus=params(), data=st.data())
def test_dict_order_of_predictions_does_not_matter(payload, consensus, data):
    models = sorted(
        next(iter(next(iter(payload["scenarioPredictions"].values())).values()))
    )
    order = data.draw(st.permutations(models))
    shuffled = copy.deepcopy(payload)
    shuffled["scenarioPredictions"] = {
        scenario_id: {
            variable: {model: cell[model] for model in order}
            for variable, cell in reversed(outputs.items())
        }
        for scenario_id, outputs in reversed(payload["scenarioPredictions"].items())
    }
    expected = consensus_report(payload, consensus)
    actual = consensus_report(shuffled, consensus)
    assert json.dumps(actual) == json.dumps(expected)


@settings(max_examples=200, deadline=None)
@given(payload=payloads(), consensus=params())
def test_report_is_deterministic_and_leaves_payload_alone(payload, consensus):
    original = copy.deepcopy(payload)
    first = consensus_report(payload, consensus, source="x", source_sha256="y")
    second = consensus_report(payload, consensus, source="x", source_sha256="y")
    assert json.dumps(first) == json.dumps(second)
    assert json.dumps(payload, sort_keys=True) == json.dumps(original, sort_keys=True)
    assert set(first) == REPORT_KEYS
    assert first["flags"] == consensus_flags(payload, consensus)
    assert first["flagged_cells"] == len(first["flags"])
    assert first["params"] == consensus.to_dict()
    assert first["top_models"] == ranked_models(payload)[: consensus.top_k]
    assert first["models"] == len(payload["modelStats"])
    assert first["scored_cells"] == sum(
        next(iter(cell.values()))["scored"]
        for outputs in payload["scenarioPredictions"].values()
        for cell in outputs.values()
    )


@settings(max_examples=200, deadline=None)
@given(
    n_zero=st.integers(1, 12),
    zero_min=st.integers(1, 12),
    rounding=st.sampled_from(ANSWER_ROUNDINGS),
)
def test_zero_cluster_needs_zero_cluster_min_models(n_zero, zero_min, rounding):
    # Every zero answerer is a top model, so min_top alone would fire.
    models = [f"model_{index:02d}" for index in range(n_zero + 1)]
    answers = {model: 0.0 for model in models[:n_zero]}
    answers[models[-1]] = 500.0
    payload = make_payload(models, {("scenario_000", "snap"): (500.0, True, answers)})
    consensus = ConsensusParams(
        min_models=1,
        top_k=1,
        min_top=1,
        answer_rounding=rounding,
        zero_cluster_min_models=zero_min,
    )
    flags = consensus_flags(payload, consensus)
    assert bool(flags) == (n_zero >= zero_min)
    if flags:
        assert flags[0]["clusters"][0]["answer"] == 0.0
        assert flags[0]["trigger"] == ["min_models", "min_top"]


# Examples ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "rounding", "units"),
    [
        (2.5, "nearest", 3),
        (2.49, "nearest", 2),
        (-2.5, "nearest", -2),
        (-2.51, "nearest", -3),
        (13387.65, "nearest", 13388),
        (13387.65, "truncate", 13387),
        (-0.9, "truncate", 0),
        (0.9, "truncate", 0),
        (-1.2, "truncate", -1),
        (13387.65, "cents", 1338765),
        (13387.654, "cents", 1338765),
        (13387.655, "cents", 1338766),
        # Half-up on the decimal form: 1.005 * 100 is 100.49999999999999 in
        # binary floating point, which would round down.
        (1.005, "cents", 101),
        (-1.005, "cents", -101),
        (0.0, "cents", 0),
    ],
)
def test_answer_rounding_modes(value, rounding, units):
    assert _answer_units(value, rounding) == units


def _merge_payload() -> dict:
    # The top model answers correctly, so only min_models can trigger.
    ranking = ["top", "a", "b"]
    answers = {"top": 14192.66, "a": 13387.65, "b": 13388.0}
    return make_payload(
        ranking, {("scenario_081", "payroll_tax"): (14192.66, True, answers)}
    )


@pytest.mark.parametrize(
    ("rounding", "flagged"),
    [("nearest", True), ("truncate", False), ("cents", False)],
)
def test_rounding_decides_whether_close_answers_merge(rounding, flagged):
    consensus = ConsensusParams(
        min_models=2, top_k=1, min_top=1, answer_rounding=rounding
    )
    flags = consensus_flags(_merge_payload(), consensus)
    assert bool(flags) == flagged
    if flagged:
        (cluster,) = flags[0]["clusters"]
        assert cluster["answer"] == 13388.0
        assert cluster["predictions"] == {"a": 13387.65, "b": 13388.0}
        assert flags[0]["trigger"] == ["min_models"]
        assert flags[0]["models_exact"] == 1


def test_an_exact_answer_never_counts_toward_a_wrong_cluster():
    # Reference 13,387.65: 13,388.6 rounds to the key 13,389, which misses by
    # 1.35, but the answer itself is within the $1 tolerance, so it is exact
    # and leaves the cluster. 13,389.2 misses by 1.55 and stays.
    answers = {"a": 13388.6, "b": 13388.6, "c": 13389.2}
    payload = make_payload(
        ["a", "b", "c"], {("scenario_081", "payroll_tax"): (13387.65, True, answers)}
    )
    assert consensus_flags(payload, ConsensusParams(min_models=2, min_top=3)) == []
    (flag,) = consensus_flags(payload, ConsensusParams(min_models=1, min_top=3))
    (cluster,) = flag["clusters"]
    assert cluster["answer"] == 13389.0
    assert cluster["models"] == ["c"]
    assert flag["models_exact"] == 2


def test_unusable_predictions_join_no_cluster():
    answers = {
        "w1": 999.0,
        "w2": 999.4,
        "w3": 998.6,
        "ok": 100.3,
        "none": None,
        "nan": math.nan,
        "inf": math.inf,
        "unparsed": ("unparsed", 999.0),
    }
    payload = make_payload(
        sorted(answers), {("scenario_001", "snap"): (100.0, True, answers)}
    )
    consensus = ConsensusParams(min_models=3, top_k=1, min_top=1)
    (flag,) = consensus_flags(payload, consensus)
    assert flag["models_answered"] == 4
    assert flag["models_exact"] == 1
    (cluster,) = flag["clusters"]
    assert cluster["models"] == ["w1", "w2", "w3"]
    assert cluster["answer"] == 999.0
    # Counting the unparsed 999 would have made a cluster of four.
    assert not consensus_flags(payload, replace(consensus, min_models=4))


def test_unscored_cells_are_neither_counted_nor_flagged():
    answers = {f"m{index}": 7.0 for index in range(5)}
    payload = make_payload(
        sorted(answers),
        {
            ("scenario_001", "snap"): (100.0, False, answers),
            ("scenario_002", "snap"): (100.0, True, answers),
        },
    )
    report = consensus_report(payload, ConsensusParams(min_models=5))
    assert report["scored_cells"] == 1
    assert _keys(report["flags"]) == {("scenario_002", "snap")}


def test_clusters_sort_by_size_then_answer():
    answers = {"a": 10.0, "b": 10.0, "c": 30.0, "d": 30.0, "e": 20.0, "f": 20.0}
    answers |= {"g": 20.0, "h": 50.0}
    payload = make_payload(
        sorted(answers), {("scenario_001", "tanf"): (50.0, True, answers)}
    )
    (flag,) = consensus_flags(
        payload, ConsensusParams(min_models=2, top_k=1, min_top=1)
    )
    assert [cluster["answer"] for cluster in flag["clusters"]] == [20.0, 10.0, 30.0]
    assert flag["models_exact"] == 1


def test_top_models_come_from_model_stats_order():
    answers = {"a": 5.0, "b": 5.0, "c": 5.0, "d": 100.0}
    cells = {("scenario_001", "snap"): (100.0, True, answers)}
    consensus = ConsensusParams(min_models=10, top_k=3, min_top=3)
    assert consensus_flags(make_payload(["c", "b", "a", "d"], cells), consensus)
    (flag,) = consensus_flags(
        make_payload(["c", "d", "b", "a"], cells), replace(consensus, min_top=2)
    )
    assert flag["clusters"][0]["top_models"] == ["c", "b"]
    assert flag["trigger"] == ["min_top"]
    assert not consensus_flags(make_payload(["d", "c", "b", "a"], cells), consensus)


def test_malformed_payloads_are_refused():
    answers = {"a": 1.0, "b": 2.0}
    payload = make_payload(["a", "b"], {("scenario_001", "snap"): (5.0, True, answers)})
    with pytest.raises(ValueError, match="more than once"):
        ranked_models({"modelStats": [{"model": "a"}, {"model": "a"}]})
    mixed = copy.deepcopy(payload)
    mixed["scenarioPredictions"]["scenario_001"]["snap"]["a"]["scored"] = False
    with pytest.raises(ValueError, match="disagree on scored"):
        consensus_flags(mixed, ConsensusParams())
    moved = copy.deepcopy(payload)
    moved["scenarioPredictions"]["scenario_001"]["snap"]["a"]["groundTruth"] = 6.0
    with pytest.raises(ValueError, match="disagree on groundTruth"):
        consensus_flags(moved, ConsensusParams())
    missing = copy.deepcopy(payload)
    for entry in missing["scenarioPredictions"]["scenario_001"]["snap"].values():
        entry["groundTruth"] = None
    with pytest.raises(ValueError, match="no finite reference"):
        consensus_flags(missing, ConsensusParams())
    stateless = copy.deepcopy(payload)
    stateless["scenarios"] = {}
    with pytest.raises(ValueError, match="missing from payload scenarios"):
        consensus_flags(stateless, ConsensusParams(min_models=1, top_k=1, min_top=1))


def test_load_us_payload_reads_plain_gzip_and_release_wrapper(tmp_path):
    payload = make_payload(
        ["a", "b"], {("scenario_001", "snap"): (5.0, True, {"a": 1.0, "b": 1.0})}
    )
    text = json.dumps(payload)
    plain = tmp_path / "data.json"
    plain.write_text(text)
    packed = tmp_path / "data.json.gz"
    packed.write_bytes(gzip.compress(text.encode()))
    wrapped = tmp_path / "release.json"
    wrapped.write_text(json.dumps({"countries": {"us": payload, "uk": {}}}))
    wrapped_gz = tmp_path / "release.json.gz"
    wrapped_gz.write_bytes(gzip.compress(wrapped.read_bytes()))
    for path in (plain, packed, wrapped, wrapped_gz):
        assert load_us_payload(path) == payload
        assert load_us_payload(str(path)) == payload
    assert file_sha256(packed) == hashlib.sha256(packed.read_bytes()).hexdigest()

    uk_only = tmp_path / "uk.json"
    uk_only.write_text(json.dumps({"countries": {"uk": payload}}))
    with pytest.raises(ValueError, match="no 'us' country"):
        load_us_payload(uk_only)
    uk = tmp_path / "uk_payload.json"
    uk.write_text(json.dumps({**payload, "country": "uk"}))
    with pytest.raises(ValueError, match="not 'us'"):
        load_us_payload(uk)
    listing = tmp_path / "list.json"
    listing.write_text("[]")
    with pytest.raises(ValueError, match="not a JSON object"):
        load_us_payload(listing)
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps({"country": "us"}))
    with pytest.raises(ValueError, match="lacks scenarioPredictions"):
        load_us_payload(bare)


@pytest.mark.parametrize(
    "overrides",
    [
        {"min_models": 0},
        {"min_models": -1},
        {"min_models": 1.5},
        {"min_models": True},
        {"top_k": 0},
        {"min_top": 0},
        {"min_top": 6},
        {"top_k": 2, "min_top": 3},
        {"tolerance": -0.01},
        {"tolerance": math.nan},
        {"tolerance": math.inf},
        {"tolerance": "1"},
        {"tolerance": True},
        {"answer_rounding": "round"},
        {"answer_rounding": "Nearest"},
        {"zero_cluster_min_models": 0},
        {"zero_cluster_min_models": "15"},
    ],
)
def test_invalid_params_are_rejected(overrides):
    with pytest.raises(ValueError):
        ConsensusParams(**overrides)


def test_params_round_trip_and_prototype():
    assert ConsensusParams().to_dict() == {
        "min_models": 15,
        "top_k": 5,
        "min_top": 3,
        "tolerance": 1.0,
        "answer_rounding": "nearest",
        "zero_cluster_min_models": 15,
        "binary_outputs": "mismatch",
    }
    assert [field.name for field in fields(ConsensusParams)] == list(
        ConsensusParams().to_dict()
    )
    assert PROTOTYPE_PARAMS == ConsensusParams(
        answer_rounding="truncate", binary_outputs="skip"
    )
    with pytest.raises(ValueError, match="binary_outputs"):
        ConsensusParams(binary_outputs="exact")
    assert ConsensusParams(tolerance=2).tolerance == 2.0
    assert isinstance(ConsensusParams(tolerance=2).to_dict()["tolerance"], float)
    for consensus in (ConsensusParams(), PROTOTYPE_PARAMS):
        restored = ConsensusParams(**json.loads(json.dumps(consensus.to_dict())))
        assert restored == consensus
    with pytest.raises(AttributeError):
        ConsensusParams().min_models = 3


# The frozen 20260612 payload --------------------------------------------------


@cache
def _frozen_payload() -> Path:
    """The pass's payload, written from PASS_COMMIT to a scratch file."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{PASS_COMMIT}:{PAYLOAD_PATH}"],
        capture_output=True,
    )
    if result.returncode:
        pytest.fail(
            f"cannot read {PAYLOAD_PATH} at {PASS_COMMIT[:12]}; fetch full history "
            f"(git fetch --unshallow): {result.stderr.decode().strip()}"
        )
    path = Path(tempfile.mkdtemp(prefix="pb-pass-payload-")) / "data.json.gz"
    path.write_bytes(result.stdout)
    return path


@cache
def _frozen() -> dict:
    return load_us_payload(_frozen_payload())


@cache
def _frozen_flags(rounding: str, binary_outputs: str = "skip") -> tuple:
    consensus = ConsensusParams(answer_rounding=rounding, binary_outputs=binary_outputs)
    return tuple(consensus_flags(_frozen(), consensus))


def _frozen_by_cell(rounding: str, binary_outputs: str = "skip") -> dict:
    return {
        (f["scenario_id"], f["variable"]): f
        for f in _frozen_flags(rounding, binary_outputs)
    }


def test_frozen_payload_is_the_pinned_one():
    assert file_sha256(_frozen_payload()) == FROZEN_SHA256
    assert ranked_models(_frozen())[:5] == TOP_FIVE
    assert len(PROTOTYPE_CELLS) == 41


def test_prototype_params_flag_the_41_cells():
    report = consensus_report(
        _frozen(),
        PROTOTYPE_PARAMS,
        source=f"{PASS_COMMIT[:8]}:{PAYLOAD_PATH}",
        source_sha256=FROZEN_SHA256,
    )
    assert set(report) == REPORT_KEYS
    assert report["models"] == 46
    assert report["scored_cells"] == 1928
    assert report["top_models"] == TOP_FIVE
    assert report["flagged_cells"] == 41
    assert _keys(report["flags"]) == PROTOTYPE_CELLS
    assert report["params"]["answer_rounding"] == "truncate"
    assert report["source_sha256"] == FROZEN_SHA256
    check_flag_invariants(_frozen(), PROTOTYPE_PARAMS, report["flags"])


def test_nearest_dollar_adds_two_cells_to_the_prototype():
    nearest = _frozen_by_cell("nearest")
    assert len(nearest) == 43
    assert set(nearest) == PROTOTYPE_CELLS | {
        ("scenario_081", "payroll_tax"),
        ("scenario_025", "state_income_tax_before_refundable_credits"),
    }
    check_flag_invariants(
        _frozen(), ConsensusParams(binary_outputs="skip"), list(nearest.values())
    )

    payroll = nearest[("scenario_081", "payroll_tax")]
    (cluster,) = payroll["clusters"]
    assert cluster["answer"] == 13388.0
    assert set(cluster["predictions"].values()) == {13387.65, 13388.0}
    assert payroll["trigger"] == ["min_top"]
    assert cluster["top_models"] == [
        "claude-opus-5.5",
        "gpt-6-luna",
        "claude-sonnet-5.5",
    ]

    ohio = nearest[("scenario_025", "state_income_tax_before_refundable_credits")]
    (cluster,) = ohio["clusters"]
    assert ohio["state"] == "OH"
    assert cluster["answer"] == 1590.0
    assert cluster["n_top"] == 4
    assert cluster["top_models"] == [
        "gpt-6-sol",
        "claude-opus-5.5",
        "gpt-6-luna",
        "claude-sonnet-5.5",
    ]


def test_cents_drops_three_cells_from_nearest():
    cents = _frozen_by_cell("cents")
    assert len(cents) == 40
    assert set(_frozen_by_cell("nearest")) - set(cents) == {
        ("scenario_081", "payroll_tax"),
        ("scenario_025", "state_income_tax_before_refundable_credits"),
        ("scenario_054", "snap"),
    }
    assert set(cents) <= set(_frozen_by_cell("nearest"))
    check_flag_invariants(
        _frozen(),
        ConsensusParams(answer_rounding="cents", binary_outputs="skip"),
        list(cents.values()),
    )


def test_frozen_zero_rule_and_binary_outputs():
    # The zero guard removes nothing on this payload at the shipped parameters.
    for consensus in (PROTOTYPE_PARAMS, ConsensusParams()):
        unguarded = replace(consensus, zero_cluster_min_models=1)
        assert consensus_flags(_frozen(), unguarded) == consensus_flags(
            _frozen(), consensus
        )
    # Under "skip" a 0/1 output cannot be wrong by more than $1: none is flagged.
    for rounding in ANSWER_ROUNDINGS:
        assert all(
            metric_type_for_output(flag["variable"]) != "binary"
            for flag in _frozen_flags(rounding)
        )


def test_default_params_add_eighteen_eligibility_cells():
    default = _frozen_by_cell("nearest", "mismatch")
    assert len(default) == 61
    amounts = set(_frozen_by_cell("nearest"))
    assert amounts <= set(default)
    assert set(default) - amounts == BINARY_CELLS
    assert all(
        metric_type_for_output(variable) == "binary" for _, variable in BINARY_CELLS
    )
    check_flag_invariants(_frozen(), ConsensusParams(), list(default.values()))
    # Three children of one North Carolina household: 44 of 46 models, all of
    # the top five, say not Medicaid-eligible where the reference says eligible.
    children = default[("scenario_026", "child1_medicaid_eligible")]
    assert children["reference"] == 1.0
    # GPT-6 Astra answers 1; Kimi K2.6's answer did not parse.
    assert (children["models_answered"], children["models_exact"]) == (45, 1)
    (cluster,) = children["clusters"]
    assert (cluster["answer"], cluster["n_models"], cluster["n_top"]) == (0.0, 44, 5)
    assert consensus_report(_frozen())["flagged_cells"] == 61


@pytest.mark.parametrize(
    "consensus",
    [ConsensusParams(), PROTOTYPE_PARAMS, ConsensusParams(answer_rounding="cents")],
    ids=["default", "prototype", "cents"],
)
def test_models_exact_agrees_with_the_board_scorer(consensus):
    # Differential: the trigger's exact count against the payload's own exact
    # field, which the board's scorer wrote (100 for a hit), on every flag.
    for flag in consensus_flags(_frozen(), consensus):
        cell = _frozen()["scenarioPredictions"][flag["scenario_id"]][flag["variable"]]
        hits = sum(entry["exact"] == 100.0 for entry in cell.values())
        assert flag["models_exact"] == hits, (flag["scenario_id"], flag["variable"])


def test_load_payload_reads_the_requested_country(tmp_path):
    from policybench.consensus import load_payload

    us = make_payload(
        ["a", "b"], {("scenario_001", "snap"): (5.0, True, {"a": 1.0, "b": 1.0})}
    )
    uk = dict(us, country="uk")
    us = dict(us, country="us")
    release = tmp_path / "release.json"
    release.write_text(json.dumps({"countries": {"us": us, "uk": uk}}))
    uk_only = tmp_path / "uk.json"
    uk_only.write_text(json.dumps(uk))

    assert load_payload(release, "uk") == uk
    assert load_payload(release, "us") == us
    assert load_payload(uk_only, "uk") == uk
    with pytest.raises(ValueError, match="not 'us'"):
        load_payload(uk_only, "us")
    with pytest.raises(ValueError, match="country must be one of"):
        load_payload(uk_only, "fr")
