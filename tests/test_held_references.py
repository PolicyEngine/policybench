"""Held references: the rule that lists a checked cell as held, the standing
list's two records, and the evidence behind them
(reference_audit/2026-10-10-held-references)."""

from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from functools import cache
from pathlib import Path
from unittest import mock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from policybench.consensus import (
    ConsensusParams,
    consensus_report,
    file_sha256,
    load_us_payload,
    ranked_models,
)
from policybench.held_references import (
    HELD_VERDICT,
    HOLD_TOLERANCE,
    NOT_APPLIED_REASONS,
    SCHEMA_VERSION,
    apply_held_references,
    load_held_references,
    prompt_sha256,
    validate_held_references,
)
from policybench.prompts import get_variable_description
from policybench.scenarios import load_scenarios_from_manifest

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "reference_audit/held_references.json"
AUDIT = ROOT / "reference_audit/2026-10-10-held-references"
RUN = "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
PAYLOAD_PATH = f"{RUN}/data.json.gz"
# The records were checked on release dashboard-data-20261010's payload, as
# #208 committed it. Later releases rewrite the working tree's, so the tests
# read it from git; CI checks out full history.
RELEASE_COMMIT = "5a8164a001efb27fa55f47fe7ea26666a0de31f8"
RELEASE_SHA256 = "535a51db14f13284b7054f2980b3663c3bc4317037eb3a0cc65e392096df5a90"
VA_039 = ("scenario_039", "federal_income_tax_before_refundable_credits")
OH_025 = ("scenario_025", "state_income_tax_before_refundable_credits")
TAX = "state_income_tax_before_refundable_credits"
MEDICAID = "head_medicaid_eligible"
MEMBERS = ["top-a", "top-b", "top-c"]


def _script(name: str):
    spec = importlib.util.spec_from_file_location(
        name, AUDIT / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# --- The rule ------------------------------------------------------------------


def _cluster(answers) -> dict:
    """A triggering cluster whose members give ``answers`` (one answer for
    all three members, or one each)."""
    if isinstance(answers, (int, float)):
        answers = [answers] * len(MEMBERS)
    return {
        "answer": float(round(answers[0])),
        "n_models": len(answers),
        "n_top": len(answers),
        "models": MEMBERS[: len(answers)],
        "top_models": MEMBERS[: len(answers)],
        "predictions": dict(zip(MEMBERS, answers)),
    }


def _flag(scenario_id="scenario_001", variable=TAX, reference=100.0, answers=(50.0,)):
    return {
        "scenario_id": scenario_id,
        "variable": variable,
        "state": "PA",
        "reference": reference,
        "models_answered": 6,
        "models_exact": 0,
        "trigger": ["min_top"],
        "clusters": [_cluster(answer) for answer in answers],
    }


def _prompt_of(scenario_id: str) -> str:
    return f"Household {scenario_id}: the facts and the requested outputs."


def _prompts(*scenario_ids: str, **changed: str) -> dict:
    """A payload carrying only what the rule reads: each scenario's prompt."""
    texts = {sid: _prompt_of(sid) for sid in scenario_ids} | changed
    return {"scenarios": {sid: {"prompt": {"tool": t}} for sid, t in texts.items()}}


PROMPTS = _prompts("scenario_001", "scenario_002")


def _record(scenario_id="scenario_001", variable=TAX, reference=100.0, answers=(50.0,)):
    return {
        "scenario_id": scenario_id,
        "variable": variable,
        "prompt_sha256": _sha(_prompt_of(scenario_id)),
        "reference": reference,
        "verdict": HELD_VERDICT,
        "checked_on": "2026-10-10",
        "evidence": "reference_audit/somewhere/README.md",
        "consensus": [
            {"answer": answer, "explanation": f"why {answer} is wrong"}
            for answer in answers
        ],
    }


def test_a_checked_cell_is_listed_as_held_with_its_explanation():
    flags = [_flag(), _flag("scenario_002")]
    kept, report = apply_held_references(flags, [_record()], PROMPTS)
    assert kept == [flags[1]]
    assert report["not_applied"] == [] and report["not_flagged"] == []
    (held,) = report["held"]
    assert (held["scenario_id"], held["variable"]) == ("scenario_001", TAX)
    assert held["reference"] == 100.0 and held["held_reference"] == 100.0
    assert held["record"] == _record()
    (cluster,) = held["clusters"]
    assert cluster == {
        "answer": 50.0,
        "n_models": 3,
        "n_top": 3,
        "models": MEMBERS,
        "predictions": {"top-a": 50.0, "top-b": 50.0, "top-c": 50.0},
        "explained_answer": 50.0,
        "explanation": "why 50.0 is wrong",
    }


@pytest.mark.parametrize(
    ("reference", "holds"),
    [(100.0, True), (100.99, True), (101.0, True), (101.01, False), (98.5, False)],
)
def test_a_record_stops_applying_once_the_reference_moves(reference, holds):
    assert HOLD_TOLERANCE == 1.0
    flags = [_flag(reference=reference)]
    kept, report = apply_held_references(flags, [_record()], PROMPTS)
    assert bool(report["held"]) is holds
    if holds:
        assert kept == []
    else:
        assert kept == flags
        (stale,) = report["not_applied"]
        assert stale["reason"] == "reference_moved"
        assert stale["reference"] == reference and stale["held_reference"] == 100.0
        assert stale["record"] == _record()


def test_a_reference_that_moves_onto_the_held_value_is_held():
    """Moving is not the test; being the held value is. A reference of 50
    against a record that held 52.5 is not covered; at 53 it is."""
    record = _record(reference=52.5, answers=(100.0,))
    before = [_flag(reference=50.0, answers=(100.0,))]
    assert apply_held_references(before, [record], PROMPTS)[1]["held"] == []
    after = [_flag(reference=53.0, answers=(100.0,))]
    assert apply_held_references(after, [record], PROMPTS)[0] == []


def test_a_consensus_the_record_does_not_explain_keeps_the_cell_in_the_pass():
    # The checked answer still triggers, and models now also agree on another.
    flags = [_flag(answers=(50.0, 70.0))]
    kept, report = apply_held_references(flags, [_record(answers=(50.4,))], PROMPTS)
    assert kept == flags and report["held"] == []
    (stale,) = report["not_applied"]
    assert stale["reason"] == "unexplained_consensus"
    assert [c["answer"] for c in stale["unexplained_clusters"]] == [70.0]
    # Explaining both answers covers the flag.
    both = _record(answers=(50.4, 70.0))
    kept, report = apply_held_references(flags, [both], PROMPTS)
    assert kept == [] and len(report["held"][0]["clusters"]) == 2


def test_every_member_of_a_cluster_must_give_the_explained_answer():
    """A cluster is a rounded key. Its members' own answers are what the
    record must explain, and one entry must explain all of them."""
    record = _record(answers=(50.0,))
    # 50.9 is the explained answer, by a dollar; 51.2 is not.
    near = [_flag(answers=([50.0, 50.9, 49.2],))]
    assert apply_held_references(near, [record], PROMPTS)[0] == []
    far = [_flag(answers=([50.0, 50.9, 51.2],))]
    kept, report = apply_held_references(far, [record], PROMPTS)
    assert kept == far
    assert report["not_applied"][0]["reason"] == "unexplained_consensus"
    # Two explained answers do not add up to one cluster's explanation.
    split = _record(answers=(50.0, 52.0))
    kept, report = apply_held_references(
        [_flag(answers=([49.5, 50.5, 52.6],))], [split], PROMPTS
    )
    assert report["not_applied"][0]["reason"] == "unexplained_consensus"


@pytest.mark.parametrize(
    "broken",
    [
        {"predictions": {}},
        {"predictions": {"top-a": 50.0, "top-b": 50.0}},
        {"predictions": {"top-a": 50.0, "top-b": 50.0, "top-c": None}},
        {"predictions": {"top-a": 50.0, "top-b": 50.0, "top-c": float("nan")}},
        {"models": []},
        # The cluster names one set of models and answers for another.
        {"models": ["top-a"], "n_models": 1},
        {"models": ["top-a", "top-b", "top-c", "mid-a"], "n_models": 4},
        {"models": ["top-a", "top-a", "top-b", "top-c"], "n_models": 4},
        # It counts more members than it names.
        {"n_models": 4},
        {"n_models": None},
    ],
)
def test_a_cluster_that_does_not_answer_for_exactly_its_members_is_not_explained(
    broken,
):
    flag = _flag()
    flag["clusters"][0] |= broken
    kept, report = apply_held_references([flag], [_record()], PROMPTS)
    assert kept == [flag]
    assert report["not_applied"][0]["reason"] == "unexplained_consensus"


def test_an_answer_outside_the_named_members_is_not_explained_away():
    """The review's case: a record that explains 50 must not hold a cluster
    that names one model at 50 and also carries another's 70."""
    flag = _flag()
    flag["clusters"][0] = {
        "answer": 50.0,
        "n_models": 2,
        "n_top": 1,
        "models": ["a"],
        "predictions": {"a": 50.0, "b": 70.0},
    }
    kept, report = apply_held_references([flag], [_record()], PROMPTS)
    assert kept == [flag] and report["held"] == []


def test_a_record_is_bound_to_the_prompt_the_models_answered():
    """The same scenario id, reference and consensus answer, under another
    prompt, is another question: a scenario id is only a position in a run."""
    flags = [_flag()]
    record = _record()
    assert apply_held_references(flags, [record], PROMPTS)[0] == []
    for other in (
        _prompts("scenario_002", scenario_001="Another household, same numbers."),
        _prompts("scenario_002", scenario_001=_prompt_of("scenario_001") + " "),
        _prompts("scenario_002"),
        {"scenarios": {"scenario_001": {"prompt": {"tool": ""}}}},
        {},
    ):
        kept, report = apply_held_references(flags, [record], other)
        assert kept == flags and report["held"] == []
        (stale,) = report["not_applied"]
        assert stale["reason"] == "prompt_changed"
        assert stale["prompt_sha256"] == prompt_sha256(other, "scenario_001")
        assert stale["prompt_sha256"] != record["prompt_sha256"]


def test_reasons_are_reported_in_the_order_they_are_tested():
    flags = [_flag(reference=500.0, answers=(70.0,))]
    record = _record()
    changed = _prompts(scenario_001="another prompt")
    assert (
        apply_held_references(flags, [record], changed)[1]["not_applied"][0]["reason"]
        == NOT_APPLIED_REASONS[0]
        == "prompt_changed"
    )
    assert (
        apply_held_references(flags, [record], PROMPTS)[1]["not_applied"][0]["reason"]
        == NOT_APPLIED_REASONS[1]
        == "reference_moved"
    )
    flags = [_flag(answers=(70.0,))]
    assert (
        apply_held_references(flags, [record], PROMPTS)[1]["not_applied"][0]["reason"]
        == NOT_APPLIED_REASONS[2]
        == "unexplained_consensus"
    )


def test_a_record_whose_cell_is_not_flagged_is_listed_as_such():
    flags = [_flag("scenario_002")]
    kept, report = apply_held_references(flags, [_record()], PROMPTS)
    assert kept == flags
    assert report["held"] == [] and report["not_applied"] == []
    assert report["not_flagged"] == [
        {"scenario_id": "scenario_001", "variable": TAX, "record": _record()}
    ]


def test_an_eligibility_output_holds_only_at_the_same_flag():
    # Within a dollar but another answer: 0 and 1 are opposites.
    flag = _flag(variable=MEDICAID, reference=1.0, answers=(0.0,))
    held = _record(variable=MEDICAID, reference=1.0, answers=(0.0,))
    assert apply_held_references([flag], [held], PROMPTS)[1]["held"]
    moved = _record(variable=MEDICAID, reference=0.0, answers=(0.0,))
    kept, report = apply_held_references([flag], [moved], PROMPTS)
    assert kept == [flag] and report["not_applied"][0]["reason"] == "reference_moved"
    other = _record(variable=MEDICAID, reference=1.0, answers=(1.0,))
    kept, report = apply_held_references([flag], [other], PROMPTS)
    assert report["not_applied"][0]["reason"] == "unexplained_consensus"


def test_malformed_flags_and_records_are_refused():
    with pytest.raises(ValueError, match="flagged more than once"):
        apply_held_references([_flag(), _flag()], [_record()], PROMPTS)
    # A flag with no cluster would be "explained" by anything.
    for clusters in ([], None):
        empty = {**_flag(), "clusters": clusters}
        with pytest.raises(ValueError, match="no triggering cluster"):
            apply_held_references([empty], [_record()], PROMPTS)
        with pytest.raises(ValueError, match="no triggering cluster"):
            apply_held_references([empty], [], PROMPTS)
    # A direct call checks its records as the file loader does.
    with pytest.raises(ValueError, match="listed more than once"):
        apply_held_references([_flag()], [_record(), _record()], PROMPTS)
    with pytest.raises(ValueError, match="verdict must be"):
        apply_held_references(
            [_flag()], [{**_record(), "verdict": "reference_wrong"}], PROMPTS
        )


def _document(*records) -> dict:
    return {"schema_version": SCHEMA_VERSION, "records": list(records)}


@pytest.mark.parametrize(
    ("document", "fragment"),
    [
        ([], "not a JSON object"),
        ({"schema_version": 2, "records": []}, "schema_version must be 1"),
        ({"schema_version": 1}, "records must be a list"),
        (_document("x"), "is not an object"),
        (_document({**_record(), "scenario_id": ""}), "scenario_id must be"),
        (_document({**_record(), "evidence": " "}), "evidence must be"),
        (_document({**_record(), "checked_on": None}), "checked_on must be"),
        (_document({**_record(), "prompt_sha256": None}), "prompt_sha256 must be"),
        (_document({**_record(), "prompt_sha256": "abc"}), "prompt_sha256 must be"),
        (_document({**_record(), "prompt_sha256": "A" * 64}), "prompt_sha256 must be"),
        (_document({**_record(), "reference": "100"}), "reference must be a finite"),
        (_document({**_record(), "reference": True}), "reference must be a finite"),
        (_document({**_record(), "reference": float("nan")}), "reference must be"),
        (_document({**_record(), "verdict": "reference_wrong"}), "verdict must be"),
        (_document({**_record(), "consensus": []}), "consensus must be a non-empty"),
        (
            _document({**_record(), "consensus": [{"answer": 50.0}]}),
            "needs a finite answer and an explanation",
        ),
        (
            _document({**_record(), "consensus": [{"explanation": "why"}]}),
            "needs a finite answer and an explanation",
        ),
        (_document(_record(), _record()), "listed more than once"),
    ],
)
def test_malformed_documents_are_refused(document, fragment):
    with pytest.raises(ValueError, match=fragment):
        validate_held_references(document)


def test_a_valid_document_loads_and_keeps_extra_keys(tmp_path: Path):
    record = {**_record(), "open_decision": "pending", "state": "PA"}
    path = tmp_path / "held.json"
    path.write_text(json.dumps(_document(record)))
    assert load_held_references(path) == [record]
    assert validate_held_references(_document()) == []


# Properties ---------------------------------------------------------------------

_SCENARIOS = [f"scenario_{i:03d}" for i in range(1, 5)]
_CELLS = [(sid, variable) for sid in _SCENARIOS for variable in (TAX, MEDICAID)]
_AMOUNTS = st.sampled_from([0.0, 0.4, 1.0, 1.6, 50.0, 50.9, 52.5, 100.0, 101.5])


# A cluster's members: answers near one another, with the odd stray.
_MEMBERS = st.builds(
    lambda base, offsets: [base + offset for offset in offsets],
    _AMOUNTS,
    st.lists(
        st.sampled_from([0.0, 0.0, 0.0, 0.0, 0.4, -0.3, 0.9, 5.0]),
        min_size=1,
        max_size=3,
    ),
)
_NUDGE = st.sampled_from([0.0, 0.0, 0.0, 0.0, 0.3, -0.7, 1.0, 1.4])


@st.composite
def _case(draw):
    """Flags, records and a payload, with every way a record can fail to
    apply left open: another prompt, another reference, another answer. Most
    records of a flagged cell are written from its flag, give or
    take a nudge, so that holds and near misses are both common."""
    flags = [
        _flag(
            sid,
            variable,
            reference=draw(_AMOUNTS),
            answers=draw(st.lists(_MEMBERS, min_size=1, max_size=3)),
        )
        for sid, variable in draw(
            st.lists(st.sampled_from(_CELLS), unique=True, max_size=6)
        )
    ]
    by_cell = {_cell(flag): flag for flag in flags}
    records = []
    for cell in draw(st.lists(st.sampled_from(_CELLS), unique=True, max_size=6)):
        flag = by_cell.get(cell)
        if flag is not None and draw(st.sampled_from([True, True, True, False])):
            reference = flag["reference"] + draw(_NUDGE)
            answers = [
                next(iter(cluster["predictions"].values())) + draw(_NUDGE)
                for cluster in flag["clusters"]
            ]
            answers = list(dict.fromkeys(answers))
        else:
            reference = draw(_AMOUNTS)
            answers = draw(st.lists(_AMOUNTS, min_size=1, max_size=3, unique=True))
        records.append(_record(*cell, reference=reference, answers=answers))
    reworded = draw(st.lists(st.sampled_from(_SCENARIOS), unique=True, max_size=1))
    payload = _prompts(*_SCENARIOS, **{sid: "a reworded prompt" for sid in reworded})
    return flags, records, payload


def _is(a: float, b: float, variable: str) -> bool:
    """The test's own statement of "the same value"."""
    return a == b if variable == MEDICAID else abs(a - b) <= 1.0


def _cell(row: dict) -> tuple[str, str]:
    return (row["scenario_id"], row["variable"])


def _covers(record: dict, flag: dict) -> bool:
    """Whether each of the flag's clusters is one answer the record explains."""
    return all(
        any(
            all(
                _is(answer, entry["answer"], flag["variable"])
                for answer in cluster["predictions"].values()
            )
            for entry in record["consensus"]
        )
        for cluster in flag["clusters"]
    )


@settings(max_examples=400, deadline=None)
@given(_case())
def test_every_flag_is_kept_or_held_and_every_record_is_accounted_for(case):
    flags, records, payload = case
    before = copy.deepcopy(case)
    kept, report = apply_held_references(flags, records, payload)
    assert case == before
    assert (kept, report) == apply_held_references(flags, records, payload)

    held = {_cell(row) for row in report["held"]}
    # A flag is held or kept, never both and never dropped, and order is kept.
    assert kept == [flag for flag in flags if _cell(flag) not in held]
    assert len(kept) + len(report["held"]) == len(flags)
    # Each record lands in exactly one list.
    listed = [_cell(row) for name in report for row in report[name]]
    assert sorted(listed) == sorted(_cell(record) for record in records)
    by_cell = {_cell(record): record for record in records}
    flag_by_cell = {_cell(flag): flag for flag in flags}
    assert {_cell(row) for row in report["not_flagged"]} == set(by_cell) - set(
        flag_by_cell
    )
    for name in report:
        for row in report[name]:
            assert row["record"] == by_cell[_cell(row)]

    # A flag is held exactly when its record meets all three conditions, and a
    # record that does not apply names the first condition that fails.
    for cell, flag in flag_by_cell.items():
        record = by_cell.get(cell)
        if record is None:
            assert cell not in held
            continue
        same_prompt = prompt_sha256(payload, cell[0]) == record["prompt_sha256"]
        same_reference = _is(flag["reference"], record["reference"], cell[1])
        explained = _covers(record, flag)
        assert (cell in held) == (same_prompt and same_reference and explained)
        if cell in held:
            continue
        (row,) = [r for r in report["not_applied"] if _cell(r) == cell]
        assert row["reason"] == (
            "prompt_changed"
            if not same_prompt
            else "reference_moved"
            if not same_reference
            else "unexplained_consensus"
        )
    for row in report["held"]:
        flag = flag_by_cell[_cell(row)]
        assert [c["predictions"] for c in row["clusters"]] == [
            c["predictions"] for c in flag["clusters"]
        ]
        explanations = {
            entry["answer"]: entry["explanation"]
            for entry in by_cell[_cell(row)]["consensus"]
        }
        for listed_cluster in row["clusters"]:
            assert (
                listed_cluster["explanation"]
                == explanations[listed_cluster["explained_answer"]]
            )


@settings(max_examples=300, deadline=None)
@given(_case(), st.sampled_from([2.5, -2.5, 250.0]))
def test_a_held_cell_stops_being_held_when_what_was_checked_changes(case, shift):
    """For a cell that is held: moving its reference by more than twice the
    bound, adding a consensus no record explains, or rewording its prompt each
    send it back to the pass, and none of them makes any other cell held."""
    flags, records, payload = case
    _, report = apply_held_references(flags, records, payload)
    held = {_cell(row) for row in report["held"]}

    def held_after(new_flags, new_payload) -> set:
        _, after = apply_held_references(new_flags, records, new_payload)
        return {_cell(row) for row in after["held"]}

    for target in sorted(held):
        others = held - {target}
        moved = [
            {**flag, "reference": flag["reference"] + shift}
            if _cell(flag) == target
            else flag
            for flag in flags
        ]
        assert held_after(moved, payload) == others
        extra = [_cluster(9999.0)]
        widened = [
            {**flag, "clusters": flag["clusters"] + extra}
            if _cell(flag) == target
            else flag
            for flag in flags
        ]
        assert held_after(widened, payload) == others
        reworded = {
            "scenarios": payload["scenarios"]
            | {target[0]: {"prompt": {"tool": "this household, asked another way"}}}
        }
        # The prompt belongs to the scenario, so every cell of it is released.
        assert held_after(flags, reworded) == {c for c in others if c[0] != target[0]}
    # With no records nothing changes, and a record never holds an unflagged cell.
    assert apply_held_references(flags, [], payload) == (
        flags,
        {"held": [], "not_applied": [], "not_flagged": []},
    )
    assert held <= {_cell(flag) for flag in flags}


# --- adversary-prepare --held-references -----------------------------------------

MODELS = ["top-a", "top-b", "top-c", "mid-a", "mid-b", "mid-c"]
PARAMS = ConsensusParams(min_models=3, top_k=3, min_top=2, zero_cluster_min_models=3)
TAX_CASE = f"us__scenario_001__{TAX}"
MEDICAID_CASE = f"us__scenario_002__{MEDICAID}"


def _entry(prediction, reference, explanation) -> dict:
    return {
        "prediction": prediction,
        "groundTruth": reference,
        "scored": True,
        "parsed": prediction is not None,
        "explanation": explanation,
        "referenceExplanation": "the engine's derivation",
    }


def _tool_prompt(state: str, variables: list[str]) -> str:
    lines = ["Household:", f"- state: {state}", "- tax year: 2026", ""]
    lines += [f"- {v}: {get_variable_description(v)}" for v in variables]
    return "\n".join(lines)


def _payload(
    tax_reference: float = 3070.06,
    state: str = "PA",
    top_a=4451.56,
    newcomers: float | None = None,
) -> dict:
    """Two flagged cells. ``newcomers`` adds three models that agree on
    another tax answer, a consensus that formed after an earlier payload."""
    tax = {"top-a": top_a, "top-b": 4451.56, "top-c": 4452.0, "mid-a": 4451.57}
    tax |= {"mid-b": 3070.06, "mid-c": None}
    medicaid = {m: 1.0 for m in MODELS[:4]} | {"mid-b": 0.0, "mid-c": 0.0}
    models = list(MODELS)
    if newcomers is not None:
        for model in ("new-a", "new-b", "new-c"):
            models.append(model)
            tax[model] = newcomers
            medicaid[model] = 0.0
    return {
        "country": "us",
        "scenarios": {
            "scenario_001": {
                "state": state,
                "prompt": {"tool": _tool_prompt(state, [TAX])},
            },
            "scenario_002": {
                "state": "MN",
                "prompt": {"tool": _tool_prompt("MN", [MEDICAID])},
            },
        },
        "modelStats": [{"model": m} for m in models],
        "scenarioPredictions": {
            "scenario_001": {
                TAX: {m: _entry(a, tax_reference, f"{m}: {a}") for m, a in tax.items()}
            },
            "scenario_002": {
                MEDICAID: {m: _entry(a, 0.0, f"{m}: {a}") for m, a in medicaid.items()}
            },
        },
    }


def _tax_record(**overrides) -> dict:
    """The record a check of ``_payload()``'s tax cell would have written."""
    record = _record(reference=3070.06, answers=(4451.56,))
    record["prompt_sha256"] = prompt_sha256(_payload(), "scenario_001")
    return record | overrides


def _prepare_cli(*argv: str) -> None:
    from policybench import cli

    with mock.patch.object(sys, "argv", ["policybench", "adversary-prepare", *argv]):
        cli.main()


PACKINGS = ("plain", "gzip", "wrapped", "wrapped-gzip")


def _write_inputs(
    tmp_path: Path,
    payload: dict,
    records: list[dict] | None,
    *,
    flags_from: dict | None = None,
    params: ConsensusParams = PARAMS,
    claims: str | None = "this payload",
    packing: str = "plain",
) -> list[str]:
    """Write the payload, the flags (computed from ``flags_from`` when it is
    another payload) and the records; return the command's arguments.

    ``claims`` is the payload hash the flags report records: this payload's
    (whatever the flags were computed from), a given string, or none.
    ``packing`` is how the payload file holds the payload: as it is, inside a
    release's ``{"countries": {"us": ...}}`` wrapper, and gzipped or not.
    """
    wrapped = {"countries": {"us": payload}} if "wrapped" in packing else payload
    data = json.dumps(wrapped).encode()
    payload_path = tmp_path / ("data.json.gz" if "gzip" in packing else "data.json")
    payload_path.write_bytes(gzip.compress(data) if "gzip" in packing else data)
    if claims == "this payload":
        claims = file_sha256(payload_path)
    report = consensus_report(
        payload if flags_from is None else flags_from,
        params,
        source=str(payload_path),
        source_sha256=claims or "",
    )
    if claims is None:
        del report["source_sha256"]
    (tmp_path / "flags.json").write_text(json.dumps(report, indent=2) + "\n")
    argv = ["--payload", str(payload_path), "--flags", str(tmp_path / "flags.json")]
    argv += ["--adversary-dir", str(tmp_path / "adv")]
    if records is not None:
        (tmp_path / "held.json").write_text(json.dumps(_document(*records)))
        argv += ["--held-references", str(tmp_path / "held.json")]
    return argv


def _prepared(tmp_path: Path) -> dict[str, bytes]:
    """A directory an earlier preparation with holds left, as its bytes: the
    manifest, the schemas, the other cell's case and the held listing."""
    _prepare_cli(*_write_inputs(tmp_path, _payload(), [_tax_record()]))
    return _snapshot(tmp_path)


def _snapshot(tmp_path: Path) -> dict[str, bytes]:
    root = tmp_path / "adv"
    files = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    assert {"cases.jsonl", "held_references.json", "schema_verdict.json"} <= set(files)
    return files


def _cases(tmp_path: Path) -> list[str]:
    manifest = (tmp_path / "adv" / "cases.jsonl").read_text().splitlines()
    return [json.loads(line)["case_id"] for line in manifest]


def _listing(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "adv" / "held_references.json").read_text())


def test_prepare_gives_a_held_cell_no_case_and_lists_it(tmp_path: Path, capsys):
    _prepare_cli(*_write_inputs(tmp_path, _payload(), [_tax_record()]))
    out = capsys.readouterr().out
    assert _cases(tmp_path) == [MEDICAID_CASE]
    assert not (tmp_path / "adv" / "cases" / TAX_CASE).exists()
    listing = _listing(tmp_path)
    assert listing["held_references"] == str(tmp_path / "held.json")
    assert listing["held_references_sha256"] == file_sha256(tmp_path / "held.json")
    assert listing["flags_sha256"] == file_sha256(tmp_path / "flags.json")
    assert listing["payload_sha256"] == file_sha256(tmp_path / "data.json")
    (held,) = listing["held"]
    assert (held["scenario_id"], held["variable"]) == ("scenario_001", TAX)
    assert held["clusters"][0]["explanation"] == "why 4451.56 is wrong"
    assert held["clusters"][0]["answer"] == 4452.0
    assert held["clusters"][0]["predictions"]["top-c"] == 4452.0
    assert listing["not_applied"] == [] and listing["not_flagged"] == []
    assert "Prepared 1 adversary cases" in out
    assert "0 flagged cells skipped as covered elsewhere" in out
    assert "1 listed as checked and held" in out


def test_prepare_judges_a_cell_whose_reference_moved(tmp_path: Path, capsys):
    # The record held 3,070.06; an engine change has since moved the reference.
    argv = _write_inputs(tmp_path, _payload(tax_reference=3075.0), [_tax_record()])
    _prepare_cli(*argv)
    out = capsys.readouterr().out
    assert _cases(tmp_path) == [TAX_CASE, MEDICAID_CASE]
    listing = _listing(tmp_path)
    assert listing["held"] == []
    (stale,) = listing["not_applied"]
    assert stale["reason"] == "reference_moved" and stale["reference"] == 3075.0
    assert stale["case"] == "prepared"
    assert "0 listed as checked and held" in out
    assert f"scenario_001 {TAX} (reference_moved; judged)" in out


def test_prepare_judges_the_same_cell_under_another_prompt(tmp_path: Path, capsys):
    """The review's case: the same scenario id, reference and consensus answer
    for a household in another state. The record does not cover it."""
    _prepare_cli(*_write_inputs(tmp_path, _payload(state="OH"), [_tax_record()]))
    assert _cases(tmp_path) == [TAX_CASE, MEDICAID_CASE]
    (stale,) = _listing(tmp_path)["not_applied"]
    assert stale["reason"] == "prompt_changed"
    assert f"scenario_001 {TAX} (prompt_changed; judged)" in capsys.readouterr().out


def test_a_loose_pass_tolerance_does_not_stretch_a_record(tmp_path: Path, capsys):
    """Flags computed at --tolerance 300: the consensus at 4,452 is 1,382 from
    the reference, so it triggers, and 292 from the answer the record explains.
    The record's bound is a dollar whatever the pass's is."""
    loose = ConsensusParams(
        min_models=3, top_k=3, min_top=2, zero_cluster_min_models=3, tolerance=300.0
    )
    record = _tax_record(
        consensus=[{"answer": 4160.0, "explanation": "another answer altogether"}]
    )
    _prepare_cli(*_write_inputs(tmp_path, _payload(), [record], params=loose))
    assert TAX_CASE in _cases(tmp_path)
    (stale,) = _listing(tmp_path)["not_applied"]
    assert stale["reason"] == "unexplained_consensus"
    assert stale["unexplained_clusters"][0]["answer"] == 4452.0
    # And a pass run at tolerance 0 still recognizes the checked answer.
    strict = ConsensusParams(
        min_models=3, top_k=3, min_top=2, zero_cluster_min_models=3, tolerance=0.0
    )
    _prepare_cli(*_write_inputs(tmp_path, _payload(), [_tax_record()], params=strict))
    assert TAX_CASE not in _cases(tmp_path)
    assert len(_listing(tmp_path)["held"]) == 1


@pytest.mark.parametrize("claims", ["", None, "0" * 64, "another payload"])
def test_prepare_needs_flags_that_record_this_payload(tmp_path: Path, claims):
    """Flags with no payload hash, or another payload's, are refused before
    any record is applied, whatever they contain, and an existing directory
    is left as it was."""
    before = _prepared(tmp_path)
    argv = _write_inputs(tmp_path, _payload(), [_tax_record()], claims=claims)
    with pytest.raises(SystemExit, match="--held-references needs flags computed"):
        _prepare_cli(*argv)
    assert _snapshot(tmp_path) == before


def test_old_flags_cannot_hide_a_consensus_that_formed_since(tmp_path: Path):
    """The review's case. Three models that were not in the old payload agree
    on 6,000. The old flags know only the answer the record explains, so
    applying them would list the cell as held and the new consensus would
    never be judged. They are refused, with or without the right hash."""
    old, new = _payload(), _payload(newcomers=6000.0)
    before = _prepared(tmp_path)
    for claims in ("", "this payload"):
        argv = _write_inputs(
            tmp_path, new, [_tax_record()], flags_from=old, claims=claims
        )
        with pytest.raises(SystemExit, match="consensus|needs flags computed"):
            _prepare_cli(*argv)
        assert _snapshot(tmp_path) == before
    # The payload's own flags carry both clusters, and the cell is judged.
    _prepare_cli(*_write_inputs(tmp_path, new, [_tax_record()]))
    assert TAX_CASE in _cases(tmp_path)
    (stale,) = _listing(tmp_path)["not_applied"]
    assert stale["reason"] == "unexplained_consensus"
    assert [c["answer"] for c in stale["unexplained_clusters"]] == [6000.0]


@pytest.mark.parametrize(
    "stale",
    [
        {"tax_reference": 2000.0},
        {"top_a": 4451.0},
        {"state": "OH"},
        {"newcomers": 6000.0},
    ],
)
def test_prepare_recomputes_the_flags_it_is_given(tmp_path: Path, stale):
    """A recorded hash is a claim. Flags that carry this payload's hash but
    are not what the trigger computes from it are refused: a moved reference,
    a changed answer, another household, a new consensus. An existing
    directory is left as it was."""
    before = _prepared(tmp_path)
    argv = _write_inputs(
        tmp_path, _payload(**stale), [_tax_record()], flags_from=_payload()
    )
    if stale == {"state": "OH"}:
        # The flag's state is another payload's; nothing else differs.
        assert (
            _payload(**stale)["scenarioPredictions"]
            == (_payload()["scenarioPredictions"])
        )
    with pytest.raises(SystemExit, match="is not what the consensus trigger computes"):
        _prepare_cli(*argv)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("packing", PACKINGS)
def test_prepare_reads_every_form_of_payload_a_release_ships(tmp_path: Path, packing):
    """Plain or gzipped, bare or inside a release's wrapper: the hash is the
    file's, the flags are recomputed from the US payload inside, and the cell
    is held all the same."""
    argv = _write_inputs(tmp_path, _payload(), [_tax_record()], packing=packing)
    _prepare_cli(*argv)
    assert _cases(tmp_path) == [MEDICAID_CASE]
    listing = _listing(tmp_path)
    assert [_cell(row) for row in listing["held"]] == [("scenario_001", TAX)]
    (payload_path,) = tmp_path.glob("data.json*")
    assert listing["payload_sha256"] == file_sha256(payload_path)
    # The hash is the file's bytes, not the payload's: the same flags under
    # the hash of the bare JSON are refused once the file is packed.
    report = json.loads((tmp_path / "flags.json").read_text())
    before = _snapshot(tmp_path)
    (tmp_path / "flags.json").write_text(
        json.dumps(report | {"source_sha256": _sha(json.dumps(_payload()))})
    )
    if packing != "plain":
        with pytest.raises(SystemExit, match="--held-references needs flags computed"):
            _prepare_cli(*argv)
        assert _snapshot(tmp_path) == before


def _integral(value):
    """A JSON document with whole floats written as integers."""
    if isinstance(value, dict):
        return {key: _integral(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_integral(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def test_prepare_accepts_the_same_flags_written_another_way(tmp_path: Path):
    """The flags are compared by value: key order, and 4452 for 4452.0, do
    not make them another payload's."""
    argv = _write_inputs(tmp_path, _payload(), [_tax_record()])
    report = json.loads((tmp_path / "flags.json").read_text())
    rewritten = json.dumps(_integral(report), sort_keys=True)
    assert rewritten != json.dumps(report) and json.loads(rewritten) == report
    assert '"answer": 4452,' in rewritten and '"reference": 0,' in rewritten
    (tmp_path / "flags.json").write_text(rewritten)
    _prepare_cli(*argv)
    assert _cases(tmp_path) == [MEDICAID_CASE]
    (held,) = _listing(tmp_path)["held"]
    assert held["clusters"][0]["predictions"]["top-c"] == 4452


def test_prepare_refuses_edited_flags_and_flags_without_parameters(tmp_path: Path):
    argv = _write_inputs(tmp_path, _payload(), [_tax_record()])
    flags_path = tmp_path / "flags.json"
    report = json.loads(flags_path.read_text())
    # A cluster edited to drop a member whose answer the record does not explain.
    edited = json.loads(flags_path.read_text())
    (tax_flag,) = [f for f in edited["flags"] if f["variable"] == TAX]
    tax_flag["clusters"][0]["models"].remove("top-c")
    flags_path.write_text(json.dumps(edited))
    with pytest.raises(SystemExit, match="is not what the consensus trigger computes"):
        _prepare_cli(*argv)
    # Other parameters than the flags were computed at: the defaults flag less.
    flags_path.write_text(json.dumps(report | {"params": {}}))
    with pytest.raises(SystemExit, match="is not what the consensus trigger computes"):
        _prepare_cli(*argv)
    # No parameters to recompute with.
    for broken in ({"min_models": 0}, {"no_such_parameter": 1}, None, []):
        flags_path.write_text(json.dumps(report | {"params": broken}))
        with pytest.raises(SystemExit, match="no usable consensus parameters"):
            _prepare_cli(*argv)
    del report["params"]
    flags_path.write_text(json.dumps(report))
    with pytest.raises(SystemExit, match="no usable consensus parameters"):
        _prepare_cli(*argv)
    assert not (tmp_path / "adv").exists()


@pytest.mark.parametrize(
    "left_behind",
    [
        "stage1.json",
        "verdict.json",
        "stage1.meta.json",
        "stage2_prompt.md",
        # What an interrupted runner leaves before it publishes a result.
        "stage1.claude.json",
        "stage1.claude.transcript.jsonl",
        "stage1.codex.out",
        "verdict.codex.events.jsonl",
    ],
)
def test_prepare_will_not_delete_a_runners_files_for_a_cell_that_became_held(
    tmp_path: Path, left_behind
):
    """Preparing removes the directory of a case no longer listed. A cell
    with any runner file in this directory, since recorded as held, is
    refused, so judge output is not lost: a verdict, or one file from a run
    that was interrupted."""
    _prepare_cli(*_write_inputs(tmp_path, _payload(), None))
    case_dir = tmp_path / "adv" / "cases" / TAX_CASE
    derivation = tmp_path / "adv" / "derivations" / f"{TAX_CASE}.md"
    assert [p.name for p in case_dir.iterdir()] == ["stage1_prompt.md"]
    (case_dir / left_behind).write_text("a runner wrote this")
    argv = _write_inputs(tmp_path, _payload(), [_tax_record()])
    with pytest.raises(SystemExit, match="holds a runner's files for cells now listed"):
        _prepare_cli(*argv)
    assert (case_dir / left_behind).read_text() == "a runner wrote this"
    assert (case_dir / "stage1_prompt.md").is_file() and derivation.is_file()
    assert not (tmp_path / "adv" / "held_references.json").exists()
    # A prepared case no runner has touched is simply dropped.
    (case_dir / left_behind).unlink()
    _prepare_cli(*argv)
    assert _cases(tmp_path) == [MEDICAID_CASE]
    assert not case_dir.exists() and not derivation.exists()


def test_prepare_without_the_option_is_unchanged_and_drops_a_stale_listing(
    tmp_path: Path, capsys
):
    _prepare_cli(*_write_inputs(tmp_path, _payload(), [_tax_record()]))
    assert (tmp_path / "adv" / "held_references.json").is_file()
    capsys.readouterr()
    # Without the option the flags need record no payload, as before.
    _prepare_cli(*_write_inputs(tmp_path, _payload(), None, claims=None))
    assert _cases(tmp_path) == [TAX_CASE, MEDICAID_CASE]
    assert not (tmp_path / "adv" / "held_references.json").exists()
    assert capsys.readouterr().out.startswith(
        f"Prepared 2 adversary cases under {tmp_path / 'adv'} "
        "(0 flagged cells skipped as covered elsewhere). Run "
    )


def _covered(tmp_path: Path, scenario_id: str, variable: str) -> list[str]:
    path = tmp_path / "covered.json"
    cell = {"scenario_id": scenario_id, "variable": variable, "covered_by": "x"}
    path.write_text(json.dumps([cell]))
    return ["--skip-cells", str(path)]


def test_prepare_counts_covered_cells_apart_from_held_ones(tmp_path: Path, capsys):
    argv = _write_inputs(tmp_path, _payload(), [_tax_record()])
    _prepare_cli(*argv, *_covered(tmp_path, "scenario_002", MEDICAID))
    out = capsys.readouterr().out
    assert "Prepared 0 adversary cases" in out
    assert "1 flagged cells skipped as covered elsewhere" in out
    assert "1 listed as checked and held" in out
    assert _cases(tmp_path) == []


def test_a_stale_record_for_a_covered_cell_is_not_said_to_be_judged(
    tmp_path: Path, capsys
):
    """The record no longer applies and another audit covers the cell: no
    case is prepared, and neither the message nor the listing says one is."""
    argv = _write_inputs(tmp_path, _payload(tax_reference=3075.0), [_tax_record()])
    _prepare_cli(*argv, *_covered(tmp_path, "scenario_001", TAX))
    out = capsys.readouterr().out
    assert _cases(tmp_path) == [MEDICAID_CASE]
    (stale,) = _listing(tmp_path)["not_applied"]
    assert stale["reason"] == "reference_moved"
    assert stale["case"] == "covered_elsewhere"
    assert f"scenario_001 {TAX} (reference_moved; covered elsewhere)" in out
    assert "judged" not in out
    # A held cell that is also covered is listed as held, and counted once.
    argv = _write_inputs(tmp_path, _payload(), [_tax_record()])
    _prepare_cli(*argv, *_covered(tmp_path, "scenario_001", TAX))
    out = capsys.readouterr().out
    assert "0 flagged cells skipped as covered elsewhere" in out
    assert "1 listed as checked and held" in out


# --- The standing list and the 2026-10-10 evidence -------------------------------


@cache
def _release_file(path: str) -> Path:
    """``path`` as RELEASE_COMMIT holds it, written to a scratch file."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{RELEASE_COMMIT}:{path}"],
        capture_output=True,
    )
    if result.returncode:
        pytest.fail(
            f"cannot read {path} at {RELEASE_COMMIT[:12]}; fetch full history "
            f"(git fetch --unshallow): {result.stderr.decode().strip()}"
        )
    target = Path(tempfile.mkdtemp(prefix="pb-held-")) / Path(path).name
    target.write_bytes(result.stdout)
    return target


@cache
def _release() -> dict:
    return load_us_payload(_release_file(PAYLOAD_PATH))


@cache
def _records() -> dict:
    """The two records as this check wrote them on 2026-10-10
    (``records.json``). The standing list is free to change: a record's notes
    may be brought up to date, or a later check may replace it."""
    archived = load_held_references(AUDIT / "records.json")
    assert [_cell(record) for record in archived] == [VA_039, OH_025]
    return {_cell(record): record for record in archived}


# The parameters of the 2026-10-10 runs, as their committed reports record
# them. The trigger's defaults may change; what was run that day does not.
PARAMS_20261010 = {
    "": {
        "min_models": 15,
        "top_k": 5,
        "min_top": 3,
        "tolerance": 1.0,
        "answer_rounding": "nearest",
        "zero_cluster_min_models": 15,
        "binary_outputs": "mismatch",
    },
}
PARAMS_20261010["_min_top_2"] = PARAMS_20261010[""] | {"min_top": 2}


def _release_report(suffix: str = "") -> dict:
    """The trigger on the release's payload, at one run's own parameters."""
    return consensus_report(
        _release(),
        ConsensusParams(**PARAMS_20261010[suffix]),
        source=PAYLOAD_PATH,
        source_sha256=RELEASE_SHA256,
    )


def _apply(flags: list[dict], payload: dict | None = None):
    return apply_held_references(
        flags, list(_records().values()), _release() if payload is None else payload
    )


def test_the_release_payload_is_the_pinned_one():
    assert file_sha256(_release_file(PAYLOAD_PATH)) == RELEASE_SHA256
    assert len(ranked_models(_release())) == 47


def test_the_records_carry_their_write_up_dissent_and_open_decision():
    records = _records()
    for record in records.values():
        assert (ROOT / record["evidence"]).is_file()
        assert record["checked_on"] == "2026-10-10"
        # Each record carries its reviewer's dissent and names the decision
        # that settles it; a hold is not a ruling.
        assert "Scenario ambiguous" in record["reviewer_dissent"]
        assert "d1252" in record["open_decision"]
        assert "not ruled" in record["open_decision"]
    earlier = records[OH_025]["earlier_record"].split(" ")[0]
    assert (ROOT / earlier).is_file()


def test_the_standing_list_is_valid_and_agrees_with_the_write_ups_it_cites():
    """The standing list as it is today, whatever it has come to hold: every
    record points at a write-up, and a record that still cites this check
    holds what this check held, against the same prompt and answers."""
    archived = _records()
    for record in load_held_references(REGISTRY):
        assert (ROOT / record["evidence"]).is_file()
        mine = archived.get(_cell(record))
        if mine is None or record["evidence"] != mine["evidence"]:
            continue
        for key in ("prompt_sha256", "reference", "verdict", "checked_on"):
            assert record[key] == mine[key]
        assert [entry["answer"] for entry in record["consensus"]] == [
            entry["answer"] for entry in mine["consensus"]
        ]


def test_each_record_states_the_release_prompt_reference_and_consensus():
    """The records against the payload they were checked on: the prompt is
    the one the payload exports, the held value is the scored reference, and
    each explained answer is the answer of exactly the models the record
    names."""
    predictions = _release()["scenarioPredictions"]
    for (scenario_id, variable), record in _records().items():
        assert record["prompt_sha256"] == prompt_sha256(_release(), scenario_id)
        assert record["state"] == _release()["scenarios"][scenario_id]["state"]
        cell = predictions[scenario_id][variable]
        assert {entry["scored"] for entry in cell.values()} == {True}
        (reference,) = {entry["groundTruth"] for entry in cell.values()}
        assert abs(reference - record["reference"]) < 0.01
        for consensus in record["consensus"]:
            near = sorted(
                model
                for model, entry in cell.items()
                if entry.get("prediction") is not None
                and abs(entry["prediction"] - consensus["answer"]) <= 1.0
            )
            assert near == sorted(consensus["models"])
    # The household blocks the write-up quotes are in those prompts, under
    # either answer contract a model may have been served.
    prompts = json.loads((AUDIT / "prompt_households.json").read_text())
    for scenario_id, household in prompts.items():
        exported = _release()["scenarios"][scenario_id]["prompt"]
        assert household in exported["tool"] and household in exported["json"]


def test_the_trigger_flags_ohio_and_not_yet_virginia_on_the_release():
    """At the default parameters the Ohio cell is flagged and held. The
    Virginia cluster has six models and two of the top five, one short of the
    trigger, so its record waits; with --min-top 2 both are held."""
    report = _release_report()
    assert (report["scored_cells"], report["flagged_cells"]) == (1926, 55)
    flags = {_cell(f): f for f in report["flags"]}
    assert VA_039 not in flags
    (cluster,) = flags[OH_025]["clusters"]
    assert (cluster["answer"], cluster["n_models"], cluster["n_top"]) == (1590.0, 8, 4)
    kept, listing = _apply(report["flags"])
    assert len(kept) == 54
    assert [_cell(r) for r in listing["held"]] == [OH_025]
    assert [_cell(r) for r in listing["not_flagged"]] == [VA_039]
    assert listing["not_applied"] == []

    wider = _release_report("_min_top_2")
    assert wider["flagged_cells"] == 71
    flags = {_cell(f): f for f in wider["flags"]}
    (cluster,) = flags[VA_039]["clusters"]
    assert (cluster["answer"], cluster["n_models"], cluster["n_top"]) == (5145.0, 6, 2)
    assert cluster["top_models"] == ["claude-opus-5.5", "claude-sonnet-5.5"]
    kept, listing = _apply(wider["flags"])
    assert len(kept) == 69
    assert sorted(_cell(r) for r in listing["held"]) == sorted([VA_039, OH_025])
    assert listing["not_applied"] == [] and listing["not_flagged"] == []


def _release_flag(cell: tuple[str, str]) -> dict:
    (flag,) = [f for f in _release_report("_min_top_2")["flags"] if _cell(f) == cell]
    return copy.deepcopy(flag)


@pytest.mark.parametrize(
    ("cell", "key"),
    [
        (VA_039, "reviewer_estate_income_preferential"),
        (OH_025, "reviewer_employer_premiums_paid_by_head_subsidized_plan"),
        (OH_025, "reviewer_employer_premiums_paid_by_head_unsubsidized_plan"),
    ],
)
def test_a_consensus_on_a_reviewer_alternative_would_be_judged(cell, key):
    """Each record explains only the answer that was checked. If models came
    to agree on the answer a reviewer's other reading gives, the cell goes
    back to the pass: that answer is the question decision d1252 leaves open."""
    other = float(_script("hand_derivations").derivations()[cell[0]][key])
    flag = _release_flag(cell)
    assert [_cell(r) for r in _apply([flag])[1]["held"]] == [cell]
    flag["clusters"].append(_cluster(other))
    kept, listing = _apply([flag])
    assert kept == [flag] and listing["held"] == []
    (stale,) = listing["not_applied"]
    assert stale["reason"] == "unexplained_consensus"
    assert stale["unexplained_clusters"][0]["predictions"]["top-a"] == other


@pytest.mark.parametrize("cell", [VA_039, OH_025])
def test_the_records_do_not_follow_their_scenario_ids_to_another_household(cell):
    """The review's case: scenario_025 with the same reference and consensus
    answer, but a household in another state under another prompt."""
    flag = _release_flag(cell)
    scenarios = dict(_release()["scenarios"])
    prompt = scenarios[cell[0]]["prompt"]["tool"]
    here = f"- state: {flag['state']}"
    assert here in prompt
    scenarios[cell[0]] = {"prompt": {"tool": prompt.replace(here, "- state: PA")}}
    kept, listing = _apply([flag], {"scenarios": scenarios})
    assert kept == [flag]
    assert listing["not_applied"][0]["reason"] == "prompt_changed"
    # And a reference an engine change has moved by more than a dollar.
    flag["reference"] += 1.5
    assert _apply([flag])[1]["not_applied"][0]["reason"] == "reference_moved"


@pytest.mark.parametrize("suffix", sorted(PARAMS_20261010))
def test_the_committed_flags_and_listings_reproduce(suffix):
    flags_name = f"consensus_flags_20261010{suffix}.json"
    flags_path = AUDIT / "verification" / flags_name
    assert json.loads(flags_path.read_text())["params"] == PARAMS_20261010[suffix]
    report = _release_report(suffix)
    assert flags_path.read_text() == json.dumps(report, indent=2) + "\n"
    listing = json.loads(
        (AUDIT / "verification" / f"held_on_20261010{suffix}.json").read_text()
    )
    assert listing["held_references"] == "reference_audit/held_references.json"
    assert listing["flags"] == (
        f"reference_audit/2026-10-10-held-references/verification/{flags_name}"
    )
    assert listing["flags_sha256"] == file_sha256(flags_path)
    assert listing["payload_sha256"] == RELEASE_SHA256
    _, expected = _apply(report["flags"])

    def outline(rows: dict) -> dict:
        """A listing without its copies of the records, whose notes may be
        brought up to date later (a ruling on the open decision, say)."""
        return {
            name: [
                {k: v for k, v in row.items() if k != "record"} for row in rows[name]
            ]
            for name in ("held", "not_applied", "not_flagged")
        }

    assert outline(listing) == outline(expected)


def test_the_hand_derivations_agree_with_the_engine_and_the_models():
    """Three routes to the same numbers: the law worked by hand in exact
    decimals, the engine's reference in the payload, and the models' answers."""
    script = _script("hand_derivations")
    derived = script.derivations()
    committed = json.loads((AUDIT / "verification/hand_derivations.json").read_text())
    assert derived == committed
    predictions = _release()["scenarioPredictions"]
    consensus_key = {
        VA_039: "consensus_qualifying_surviving_spouse_from_prompt_dollars",
        OH_025: "consensus_no_base_amount_no_deduction",
    }
    for (scenario_id, variable), record in _records().items():
        by_hand = derived[scenario_id]
        cell = predictions[scenario_id][variable]
        reference = next(iter(cell.values()))["groundTruth"]
        # The statute's figure is within a cent of the engine's reference.
        assert abs(float(by_hand["reference_by_hand"]) - reference) < 0.011
        (consensus,) = record["consensus"]
        hand_consensus = float(by_hand[consensus_key[(scenario_id, variable)]])
        assert abs(hand_consensus - consensus["answer"]) < 0.005
        for model in consensus["models"]:
            assert abs(cell[model]["prediction"] - hand_consensus) <= 0.5
    virginia = predictions[VA_039[0]][VA_039[1]]
    ohio = predictions[OH_025[0]][OH_025[1]]
    # Ohio's cent: the statute's $332.00 gives 1,916.60, and the engine's
    # 332.00204 gives the reference, 1,916.61.
    ohio_reference = next(iter(ohio.values()))["groundTruth"]
    assert derived["scenario_025"]["reference_by_hand"] == "1916.60"
    with_engine_base = derived["scenario_025"]["reference_with_engine_base_amount"]
    assert with_engine_base == f"{ohio_reference:.2f}" == "1916.61"
    assert (
        f"{next(iter(virginia.values()))['groundTruth']:.2f}"
        == (derived["scenario_039"]["reference_by_hand"])
    )
    # The other answers the write-up reconstructs, each a model's own answer.
    for cell, model, key, scenario in [
        (virginia, "gpt-5.6-luna", "joint_return_social_security_thresholds_too", 39),
        (ohio, "gpt-6.1-sol", "premiums_in_full_on_line_1_from_prompt_dollars", 25),
        (ohio, "gpt-5.6-sol", "base_amount_of_2024_from_prompt_dollars", 25),
        (
            ohio,
            "gpt-6-astra",
            "reviewer_employer_premiums_paid_by_head_from_prompt_dollars",
            25,
        ),
    ]:
        by_hand = float(derived[f"scenario_{scenario:03d}"][key])
        assert abs(cell[model]["prediction"] - by_hand) < 0.02

    # Who answers each reviewer's other reading: nobody the Virginia one, and
    # one model the Ohio one (its subsidized-plan branch).
    def near(cell: dict, scenario_id: str, key: str) -> list[str]:
        other = float(derived[scenario_id][key])
        return sorted(
            model
            for model, entry in cell.items()
            if entry.get("prediction") is not None
            and abs(entry["prediction"] - other) <= 1.0
        )

    assert near(virginia, "scenario_039", "reviewer_estate_income_preferential") == []
    assert near(
        ohio, "scenario_025", "reviewer_employer_premiums_paid_by_head_subsidized_plan"
    ) == ["gpt-6-astra"]
    assert (
        near(
            ohio,
            "scenario_025",
            "reviewer_employer_premiums_paid_by_head_unsubsidized_plan",
        )
        == []
    )
    # Ohio's exemption tiers, with the 2026 ceiling of R.C. 5747.025(A).
    exemption = script.oh_exemption
    assert [exemption(script.D(m)) for m in (40000, 40001, 80000, 80001)] == [
        2400,
        2150,
        2150,
        1900,
    ]
    assert exemption(script.D("499999.99")) == 1900 and exemption(script.D(500000)) == 0


def _listed_values(path: Path) -> list[str]:
    """key_variables.txt without its two version lines."""
    return path.read_text().splitlines()[2:]


def test_both_engines_reproduce_both_references():
    """The session's run on upstream main, the re-run on that commit and the
    run on the release's engine give the same value for every listed variable;
    the two engines give the same short trace."""
    main = AUDIT / "traces/policyengine-us-2.38.8-75cdd8019e"
    release = AUDIT / "traces/policyengine-us-2.38.6"
    for folder, version in ((main, "2.38.8"), (main / "rerun", "2.38.8")):
        text = folder.joinpath("key_variables.txt").read_text()
        assert text.startswith(f"policyengine-us {version} at ")
        assert text.splitlines()[1] == "policyengine-core 3.33.0"
    text = release.joinpath("key_variables.txt").read_text()
    assert text.startswith("policyengine-us 2.38.6 at ")
    assert text.splitlines()[1] == "policyengine-core 3.32.29"
    values = _listed_values(release / "key_variables.txt")
    assert len([line for line in values if line.startswith("  ")]) == 77
    assert values == _listed_values(main / "key_variables.txt")
    assert values == _listed_values(main / "rerun" / "key_variables.txt")
    assert (
        "===== scenario_039 income_tax_before_refundable_credits = 8,596.03" in values
    )
    assert (
        "===== scenario_025 state_income_tax_before_refundable_credits = 1,916.61"
        in values
    )
    for name in (
        "scenario_039_situation.json",
        "scenario_025_situation.json",
        "scenario_039_trace.txt",
        "scenario_025_trace.txt",
    ):
        assert (release / name).read_bytes() == (main / name).read_bytes()
    # The re-run was installed from the report's commit and wrote the same files.
    rerun = json.loads((main / "rerun" / "install.json").read_text())
    assert rerun["policyengine-us"] == "2.38.8"
    assert rerun["direct_url"]["vcs_info"]["commit_id"] == (
        "75cdd8019e07b54c78f0c8d077935c5dc9b14670"
    )
    assert set(rerun["identical_to_the_session_files"].values()) == {True}
    for name, digest in rerun["outputs_sha256"].items():
        assert hashlib.sha256((main / name).read_bytes()).hexdigest() == digest


def test_the_traced_situations_are_what_policybench_gives_the_engine():
    """The trace script builds each situation itself. PolicyBench's own
    builder, on the release's scenarios, builds the same one."""
    scenarios = {
        scenario.id: scenario
        for scenario in load_scenarios_from_manifest(
            _release_file(f"{RUN}/scenarios.csv")
        )
    }
    assert len(scenarios) == 100
    for scenario_id in ("scenario_039", "scenario_025"):
        built = scenarios[scenario_id].to_pe_household()
        for engine in ("policyengine-us-2.38.8-75cdd8019e", "policyengine-us-2.38.6"):
            traced = AUDIT / "traces" / engine / f"{scenario_id}_situation.json"
            assert json.loads(traced.read_text()) == built


def test_the_model_answers_are_the_release_payload_answers():
    rows = json.loads((AUDIT / "model_answers.json").read_text())
    predictions = _release()["scenarioPredictions"]
    assert len(rows) == 94
    assert {(r["scenario_id"], r["variable"]) for r in rows} == {VA_039, OH_025}
    for row in rows:
        entry = predictions[row["scenario_id"]][row["variable"]][row["model"]]
        if entry.get("prediction") is None:
            assert row["prediction"] in ("", None)
        else:
            assert float(row["prediction"]) == entry["prediction"]
        assert (row.get("explanation") or "").strip() == (
            entry.get("explanation") or ""
        ).strip()


def test_the_manifest_pins_every_evidence_file():
    """Rebuilding the manifest reproduces the committed one, so an evidence
    file that changed (a reformatted script, an edited review) fails here."""
    committed = json.loads((AUDIT / "manifest.json").read_text())
    assert _script("build_manifest").manifest() == committed
    assert committed["release"]["commit"] == RELEASE_COMMIT
    assert committed["release"]["inputs"][PAYLOAD_PATH] == RELEASE_SHA256
    assert committed["release"]["inputs"][f"{RUN}/scenarios.csv"] == file_sha256(
        _release_file(f"{RUN}/scenarios.csv")
    )
    assert [engine["version"] for engine in committed["engines"]] == [
        "2.38.8",
        "2.38.6",
    ]
    assert committed["engines"][0]["commit"].startswith("75cdd8019e")
    for path in ("report/REPORT.md", "reviews/review_va039.md", "law/excerpts.md"):
        assert path in committed["files"]
    # Whole law documents stay out of the repository.
    assert sorted(p for p in committed["files"] if p.startswith("law/")) == [
        "law/excerpts.md",
        "law/sources.json",
    ]
