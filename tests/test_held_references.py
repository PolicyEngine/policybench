"""Held references: the rule that lists a checked cell as held, the standing
list's two records, and the evidence behind them
(reference_audit/2026-10-10-held-references)."""

from __future__ import annotations

import copy
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
    NOT_APPLIED_REASONS,
    SCHEMA_VERSION,
    apply_held_references,
    load_held_references,
    validate_held_references,
)
from policybench.prompts import get_variable_description

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


def _script(name: str):
    spec = importlib.util.spec_from_file_location(
        name, AUDIT / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- The rule ------------------------------------------------------------------


def _flag(scenario_id="scenario_001", variable=TAX, reference=100.0, answers=(50.0,)):
    return {
        "scenario_id": scenario_id,
        "variable": variable,
        "state": "PA",
        "reference": reference,
        "models_answered": 6,
        "models_exact": 0,
        "trigger": ["min_top"],
        "clusters": [
            {
                "answer": float(answer),
                "n_models": 3,
                "n_top": 3,
                "models": ["top-a", "top-b", "top-c"],
                "top_models": ["top-a", "top-b", "top-c"],
                "predictions": {"top-a": answer, "top-b": answer, "top-c": answer},
            }
            for answer in answers
        ],
    }


def _record(scenario_id="scenario_001", variable=TAX, reference=100.0, answers=(50.0,)):
    return {
        "scenario_id": scenario_id,
        "variable": variable,
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
    kept, report = apply_held_references(flags, [_record()])
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
        "models": ["top-a", "top-b", "top-c"],
        "explained_answer": 50.0,
        "explanation": "why 50.0 is wrong",
    }


@pytest.mark.parametrize(
    ("reference", "holds"),
    [(100.0, True), (100.99, True), (101.0, True), (101.01, False), (98.5, False)],
)
def test_a_record_stops_applying_once_the_reference_moves(reference, holds):
    flags = [_flag(reference=reference)]
    kept, report = apply_held_references(flags, [_record()], tolerance=1.0)
    assert bool(report["held"]) is holds
    if holds:
        assert kept == []
    else:
        assert kept == flags
        (stale,) = report["not_applied"]
        assert stale["reason"] == "reference_moved"
        assert stale["reference"] == reference and stale["held_reference"] == 100.0
        assert stale["record"] == _record()


def test_a_consensus_the_record_does_not_explain_keeps_the_cell_in_the_pass():
    # The checked answer still triggers, and models now also agree on another.
    flags = [_flag(answers=(50.0, 70.0))]
    kept, report = apply_held_references(flags, [_record(answers=(50.4,))])
    assert kept == flags and report["held"] == []
    (stale,) = report["not_applied"]
    assert stale["reason"] == "unexplained_consensus"
    assert [c["answer"] for c in stale["unexplained_clusters"]] == [70.0]
    # Explaining both answers covers the flag.
    kept, report = apply_held_references(flags, [_record(answers=(50.4, 70.0))])
    assert kept == [] and len(report["held"][0]["clusters"]) == 2


def test_a_record_whose_cell_is_not_flagged_is_listed_as_such():
    flags = [_flag("scenario_002")]
    kept, report = apply_held_references(flags, [_record()])
    assert kept == flags
    assert report["held"] == [] and report["not_applied"] == []
    assert report["not_flagged"] == [
        {"scenario_id": "scenario_001", "variable": TAX, "record": _record()}
    ]


def test_an_eligibility_output_holds_only_at_the_same_flag():
    # Within the dollar tolerance but another answer: 0 and 1 are opposites.
    flag = _flag(variable=MEDICAID, reference=1.0, answers=(0.0,))
    held = _record(variable=MEDICAID, reference=1.0, answers=(0.0,))
    assert apply_held_references([flag], [held])[1]["held"]
    moved = _record(variable=MEDICAID, reference=0.0, answers=(0.0,))
    kept, report = apply_held_references([flag], [moved])
    assert kept == [flag] and report["not_applied"][0]["reason"] == "reference_moved"
    other = _record(variable=MEDICAID, reference=1.0, answers=(1.0,))
    kept, report = apply_held_references([flag], [other])
    assert report["not_applied"][0]["reason"] == "unexplained_consensus"
    # With binary_outputs="skip" the trigger compares flags in dollars too.
    assert apply_held_references([flag], [moved], binary_outputs="skip")[1]["held"]


def test_a_cell_flagged_twice_and_a_bad_tolerance_are_refused():
    with pytest.raises(ValueError, match="flagged more than once"):
        apply_held_references([_flag(), _flag()], [_record()])
    for tolerance in (-1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="tolerance"):
            apply_held_references([_flag()], [_record()], tolerance=tolerance)


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

_CELLS = [(f"scenario_{i:03d}", v) for i in range(1, 5) for v in (TAX, MEDICAID)]
_AMOUNTS = st.sampled_from([0.0, 0.4, 1.0, 1.6, 50.0, 50.9, 52.5, 100.0, 101.5])


@st.composite
def _flags_and_records(draw):
    flagged = draw(st.lists(st.sampled_from(_CELLS), unique=True, max_size=6))
    flags = [
        _flag(
            sid,
            variable,
            reference=draw(_AMOUNTS),
            answers=draw(st.lists(_AMOUNTS, min_size=1, max_size=3, unique=True)),
        )
        for sid, variable in flagged
    ]
    listed = draw(st.lists(st.sampled_from(_CELLS), unique=True, max_size=6))
    records = [
        _record(
            sid,
            variable,
            reference=draw(_AMOUNTS),
            answers=draw(st.lists(_AMOUNTS, min_size=1, max_size=3, unique=True)),
        )
        for sid, variable in listed
    ]
    tolerance = draw(st.sampled_from([0.0, 0.5, 1.0, 2.0]))
    binary_outputs = draw(st.sampled_from(["mismatch", "skip"]))
    return flags, records, tolerance, binary_outputs


def _same(a, b, variable, tolerance, binary_outputs):
    if binary_outputs == "mismatch" and variable == MEDICAID:
        return a == b
    return abs(a - b) <= tolerance


@settings(max_examples=300, deadline=None)
@given(_flags_and_records())
def test_every_flag_is_kept_or_held_and_every_record_is_accounted_for(case):
    flags, records, tolerance, binary_outputs = case
    before = copy.deepcopy((flags, records))
    kept, report = apply_held_references(
        flags, records, tolerance=tolerance, binary_outputs=binary_outputs
    )
    assert (flags, records) == before
    assert (kept, report) == apply_held_references(
        flags, records, tolerance=tolerance, binary_outputs=binary_outputs
    )

    def cell(row):
        return (row["scenario_id"], row["variable"])

    held = {cell(row) for row in report["held"]}
    # A flag is held or kept, never both and never dropped, and order is kept.
    assert kept == [flag for flag in flags if cell(flag) not in held]
    assert len(kept) + len(report["held"]) == len(flags)
    # Each record lands in exactly one list.
    listed = [cell(row) for name in report for row in report[name]]
    assert sorted(listed) == sorted(cell(record) for record in records)
    by_cell = {cell(record): record for record in records}
    flag_by_cell = {cell(flag): flag for flag in flags}
    assert {cell(row) for row in report["not_flagged"]} == set(by_cell) - set(
        flag_by_cell
    )
    for name in report:
        for row in report[name]:
            assert row["record"] is by_cell[cell(row)]
    # A held flag meets both conditions; a stale one fails the one it names.
    for row in report["held"]:
        flag, record = flag_by_cell[cell(row)], by_cell[cell(row)]
        variable = row["variable"]
        assert _same(
            flag["reference"], record["reference"], variable, tolerance, binary_outputs
        )
        assert [c["answer"] for c in row["clusters"]] == [
            c["answer"] for c in flag["clusters"]
        ]
        explained = {entry["answer"]: entry for entry in record["consensus"]}
        for listed_cluster in row["clusters"]:
            entry = explained[listed_cluster["explained_answer"]]
            assert listed_cluster["explanation"] == entry["explanation"]
            assert _same(
                listed_cluster["answer"],
                entry["answer"],
                variable,
                tolerance,
                binary_outputs,
            )
    for row in report["not_applied"]:
        flag, record = flag_by_cell[cell(row)], by_cell[cell(row)]
        variable = row["variable"]
        assert row["reason"] in NOT_APPLIED_REASONS
        same_reference = _same(
            flag["reference"], record["reference"], variable, tolerance, binary_outputs
        )
        if row["reason"] == "reference_moved":
            assert not same_reference
        else:
            assert same_reference
            assert row["unexplained_clusters"]
            for cluster in row["unexplained_clusters"]:
                assert not any(
                    _same(
                        cluster["answer"],
                        entry["answer"],
                        variable,
                        tolerance,
                        binary_outputs,
                    )
                    for entry in record["consensus"]
                )


@settings(max_examples=200, deadline=None)
@given(_flags_and_records(), st.sampled_from([3.0, -3.0, 250.0]))
def test_moving_a_reference_or_adding_a_consensus_never_adds_a_hold(case, shift):
    flags, records, tolerance, binary_outputs = case
    options = {"tolerance": tolerance, "binary_outputs": binary_outputs}
    _, report = apply_held_references(flags, records, **options)
    held = {(row["scenario_id"], row["variable"]) for row in report["held"]}
    # Every reference moves by more than any tolerance drawn: nothing is held.
    moved = [{**flag, "reference": flag["reference"] + shift} for flag in flags]
    kept, after = apply_held_references(moved, records, **options)
    assert after["held"] == [] and kept == moved
    # A consensus at an answer no record lists: nothing is held either.
    extra = _flag(answers=(9999.0,))["clusters"]
    widened = [{**flag, "clusters": flag["clusters"] + extra} for flag in flags]
    kept, after = apply_held_references(widened, records, **options)
    assert after["held"] == [] and kept == widened
    # With no records nothing changes, and records never hold an unflagged cell.
    assert apply_held_references(flags, [], **options) == (
        flags,
        {"held": [], "not_applied": [], "not_flagged": []},
    )
    assert held <= {(flag["scenario_id"], flag["variable"]) for flag in flags}


# --- adversary-prepare --held-references -----------------------------------------

MODELS = ["top-a", "top-b", "top-c", "mid-a", "mid-b", "mid-c"]
PARAMS = ConsensusParams(min_models=3, top_k=3, min_top=2, zero_cluster_min_models=3)


def _entry(prediction, reference, explanation) -> dict:
    return {
        "prediction": prediction,
        "groundTruth": reference,
        "scored": True,
        "parsed": prediction is not None,
        "explanation": explanation,
        "referenceExplanation": "the engine's derivation",
    }


def _prompt(state: str, variables: list[str]) -> str:
    lines = ["Household:", f"- state: {state}", "- tax year: 2026", ""]
    lines += [f"- {v}: {get_variable_description(v)}" for v in variables]
    return "\n".join(lines)


def _payload(tax_reference: float = 3070.06) -> dict:
    tax = {"top-a": 4451.56, "top-b": 4451.56, "top-c": 4452.0, "mid-a": 4451.57}
    tax |= {"mid-b": 3070.06, "mid-c": None}
    medicaid = {m: 1.0 for m in MODELS[:4]} | {"mid-b": 0.0, "mid-c": 0.0}
    return {
        "country": "us",
        "scenarios": {
            "scenario_001": {"state": "PA", "prompt": {"tool": _prompt("PA", [TAX])}},
            "scenario_002": {
                "state": "MN",
                "prompt": {"tool": _prompt("MN", [MEDICAID])},
            },
        },
        "modelStats": [{"model": m} for m in MODELS],
        "scenarioPredictions": {
            "scenario_001": {
                TAX: {m: _entry(a, tax_reference, f"{m}: {a}") for m, a in tax.items()}
            },
            "scenario_002": {
                MEDICAID: {m: _entry(a, 0.0, f"{m}: {a}") for m, a in medicaid.items()}
            },
        },
    }


def _prepare_cli(*argv: str) -> None:
    from policybench import cli

    with mock.patch.object(sys, "argv", ["policybench", "adversary-prepare", *argv]):
        cli.main()


def _prepare(tmp_path: Path, payload: dict, records: list[dict] | None, capsys):
    """Write the payload, its flags and the records, then run the command."""
    payload_path = tmp_path / "data.json"
    payload_path.write_text(json.dumps(payload))
    flags_path = tmp_path / "flags.json"
    report = consensus_report(payload, PARAMS, source=str(payload_path))
    flags_path.write_text(json.dumps(report, indent=2) + "\n")
    adversary = tmp_path / "adv"
    argv = ["--payload", str(payload_path), "--flags", str(flags_path)]
    argv += ["--adversary-dir", str(adversary)]
    held_path = tmp_path / "held.json"
    if records is not None:
        held_path.write_text(json.dumps(_document(*records)))
        argv += ["--held-references", str(held_path)]
    _prepare_cli(*argv)
    cases = [
        json.loads(line)["case_id"]
        for line in (adversary / "cases.jsonl").read_text().splitlines()
    ]
    return adversary, cases, capsys.readouterr().out, flags_path, held_path


TAX_CASE = f"us__scenario_001__{TAX}"
MEDICAID_CASE = f"us__scenario_002__{MEDICAID}"


def test_prepare_gives_a_held_cell_no_case_and_lists_it(tmp_path: Path, capsys):
    record = _record(reference=3070.06, answers=(4451.56,))
    adversary, cases, out, flags_path, held_path = _prepare(
        tmp_path, _payload(), [record], capsys
    )
    assert cases == [MEDICAID_CASE]
    assert not (adversary / "cases" / TAX_CASE).exists()
    listing = json.loads((adversary / "held_references.json").read_text())
    assert listing["held_references"] == str(held_path)
    assert listing["held_references_sha256"] == file_sha256(held_path)
    assert listing["flags_sha256"] == file_sha256(flags_path)
    (held,) = listing["held"]
    assert (held["scenario_id"], held["variable"]) == ("scenario_001", TAX)
    assert held["clusters"][0]["explanation"] == "why 4451.56 is wrong"
    assert held["clusters"][0]["answer"] == 4452.0
    assert listing["not_applied"] == [] and listing["not_flagged"] == []
    assert "Prepared 1 adversary cases" in out
    assert "0 flagged cells skipped as covered elsewhere" in out
    assert "1 listed as checked and held" in out


def test_prepare_judges_a_cell_whose_reference_moved(tmp_path: Path, capsys):
    # The record held 3,070.06; an engine change has since moved the reference.
    record = _record(reference=3070.06, answers=(4451.56,))
    adversary, cases, out, _, _ = _prepare(
        tmp_path, _payload(tax_reference=3075.0), [record], capsys
    )
    assert cases == [TAX_CASE, MEDICAID_CASE]
    listing = json.loads((adversary / "held_references.json").read_text())
    assert listing["held"] == []
    (stale,) = listing["not_applied"]
    assert stale["reason"] == "reference_moved" and stale["reference"] == 3075.0
    assert "0 listed as checked and held" in out
    assert f"scenario_001 {TAX} (reference_moved)" in out


def test_prepare_without_the_option_is_unchanged_and_drops_a_stale_listing(
    tmp_path: Path, capsys
):
    record = _record(reference=3070.06, answers=(4451.56,))
    adversary, _, _, _, _ = _prepare(tmp_path, _payload(), [record], capsys)
    assert (adversary / "held_references.json").is_file()
    adversary, cases, out, _, _ = _prepare(tmp_path, _payload(), None, capsys)
    assert cases == [TAX_CASE, MEDICAID_CASE]
    assert not (adversary / "held_references.json").exists()
    assert out.startswith(
        f"Prepared 2 adversary cases under {adversary} "
        "(0 flagged cells skipped as covered elsewhere). Run "
    )


def test_prepare_counts_covered_cells_apart_from_held_ones(tmp_path: Path, capsys):
    payload_path = tmp_path / "data.json"
    payload_path.write_text(json.dumps(_payload()))
    flags_path = tmp_path / "flags.json"
    flags_path.write_text(json.dumps(consensus_report(_payload(), PARAMS)))
    held_path = tmp_path / "held.json"
    record = _record(reference=3070.06, answers=(4451.56,))
    held_path.write_text(json.dumps(_document(record)))
    skip_path = tmp_path / "covered.json"
    covered = {"scenario_id": "scenario_002", "variable": MEDICAID, "covered_by": "x"}
    skip_path.write_text(json.dumps([covered]))
    argv = ["--payload", str(payload_path), "--flags", str(flags_path)]
    argv += ["--adversary-dir", str(tmp_path / "adv"), "--skip-cells", str(skip_path)]
    _prepare_cli(*argv, "--held-references", str(held_path))
    out = capsys.readouterr().out
    assert "Prepared 0 adversary cases" in out
    assert "1 flagged cells skipped as covered elsewhere" in out
    assert "1 listed as checked and held" in out
    assert (tmp_path / "adv" / "cases.jsonl").read_text() == ""


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
    """The two records of 2026-10-10. The list is a standing one, so later
    records, checked on later payloads, are not these tests' subject."""
    listed = {
        (r["scenario_id"], r["variable"]): r for r in load_held_references(REGISTRY)
    }
    return {cell: listed[cell] for cell in (VA_039, OH_025)}


def _release_report(**overrides) -> dict:
    return consensus_report(
        _release(),
        ConsensusParams(**overrides),
        source=PAYLOAD_PATH,
        source_sha256=RELEASE_SHA256,
    )


def test_the_release_payload_is_the_pinned_one():
    assert file_sha256(_release_file(PAYLOAD_PATH)) == RELEASE_SHA256
    assert len(ranked_models(_release())) == 47


def test_the_standing_list_holds_the_two_checked_cells_with_their_write_up():
    records = _records()
    for record in records.values():
        assert (ROOT / record["evidence"]).is_file()
        assert record["checked_on"] == "2026-10-10"
        # Each record carries its reviewer's dissent and names the decision
        # that settles it; a hold is not a ruling.
        assert "Scenario ambiguous" in record["reviewer_dissent"]
        assert "d1252" in json.dumps(record)
    earlier = records[OH_025]["earlier_record"].split(" ")[0]
    assert (ROOT / earlier).is_file()
    # Every record on the list, these two or later ones, points at a write-up.
    for record in load_held_references(REGISTRY):
        assert (ROOT / record["evidence"]).is_file()


def test_each_record_states_the_release_reference_and_its_consensus():
    """The list against the payload it was checked on: the held value is the
    scored reference, and each explained answer is the answer of exactly the
    models the record names."""
    predictions = _release()["scenarioPredictions"]
    for (scenario_id, variable), record in _records().items():
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


def test_the_trigger_flags_ohio_and_not_yet_virginia_on_the_release():
    """At the default parameters the Ohio cell is flagged and held. The
    Virginia cluster has six models and two of the top five, one short of the
    trigger, so its record waits; with --min-top 2 both are held."""
    report = _release_report()
    assert (report["scored_cells"], report["flagged_cells"]) == (1926, 55)
    flags = {(f["scenario_id"], f["variable"]): f for f in report["flags"]}
    assert VA_039 not in flags
    (cluster,) = flags[OH_025]["clusters"]
    assert (cluster["answer"], cluster["n_models"], cluster["n_top"]) == (1590.0, 8, 4)
    kept, listing = apply_held_references(report["flags"], list(_records().values()))
    assert len(kept) == 54
    assert [(r["scenario_id"], r["variable"]) for r in listing["held"]] == [OH_025]
    assert [(r["scenario_id"], r["variable"]) for r in listing["not_flagged"]] == [
        VA_039
    ]
    assert listing["not_applied"] == []

    wider = _release_report(min_top=2)
    assert wider["flagged_cells"] == 71
    flags = {(f["scenario_id"], f["variable"]): f for f in wider["flags"]}
    (cluster,) = flags[VA_039]["clusters"]
    assert (cluster["answer"], cluster["n_models"], cluster["n_top"]) == (5145.0, 6, 2)
    assert cluster["top_models"] == ["claude-opus-5.5", "claude-sonnet-5.5"]
    kept, listing = apply_held_references(wider["flags"], list(_records().values()))
    assert len(kept) == 69
    assert sorted((r["scenario_id"], r["variable"]) for r in listing["held"]) == sorted(
        [VA_039, OH_025]
    )
    assert listing["not_applied"] == [] and listing["not_flagged"] == []


@pytest.mark.parametrize(
    ("suffix", "overrides"), [("", {}), ("_min_top_2", {"min_top": 2})]
)
def test_the_committed_flags_and_listings_reproduce(suffix, overrides):
    flags_name = f"consensus_flags_20261010{suffix}.json"
    flags_path = AUDIT / "verification" / flags_name
    report = _release_report(**overrides)
    assert flags_path.read_text() == json.dumps(report, indent=2) + "\n"
    listing = json.loads(
        (AUDIT / "verification" / f"held_on_20261010{suffix}.json").read_text()
    )
    assert listing["held_references"] == "reference_audit/held_references.json"
    assert listing["flags"] == (
        f"reference_audit/2026-10-10-held-references/verification/{flags_name}"
    )
    assert listing["flags_sha256"] == file_sha256(flags_path)
    _, expected = apply_held_references(report["flags"], list(_records().values()))

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
    derived = _script("hand_derivations").derivations()
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
        # The engine is within a cent of the hand derivation.
        assert abs(float(by_hand["reference_by_hand"]) - reference) < 0.011
        (consensus,) = record["consensus"]
        hand_consensus = float(by_hand[consensus_key[(scenario_id, variable)]])
        assert abs(hand_consensus - consensus["answer"]) < 0.005
        for model in consensus["models"]:
            assert abs(cell[model]["prediction"] - hand_consensus) <= 0.5
    # The other answers the write-up reconstructs, each a model's own answer.
    virginia = predictions[VA_039[0]][VA_039[1]]
    ohio = predictions[OH_025[0]][OH_025[1]]
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


def _listed_values(path: Path) -> list[str]:
    """key_variables.txt without its two version lines."""
    return path.read_text().splitlines()[2:]


def test_both_engines_reproduce_both_references():
    """The session's run on upstream main and the re-run on the release's
    engine give the same value for every listed variable and the same
    non-zero trace."""
    main = AUDIT / "traces/policyengine-us-2.38.8-75cdd8019e"
    release = AUDIT / "traces/policyengine-us-2.38.6"
    assert (
        main.joinpath("key_variables.txt")
        .read_text()
        .startswith("policyengine-us 2.38.8 at ")
    )
    assert (
        release.joinpath("key_variables.txt")
        .read_text()
        .startswith("policyengine-us 2.38.6 at ")
    )
    values = _listed_values(release / "key_variables.txt")
    assert values == _listed_values(main / "key_variables.txt")
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
    # The situations are the release's scenarios, as the script builds them.
    scenarios = _release_file(f"{RUN}/scenarios.csv")
    manifest = json.loads((AUDIT / "manifest.json").read_text())
    assert (
        manifest["release"]["inputs"][f"{RUN}/scenarios.csv"]
        == hashlib.sha256(scenarios.read_bytes()).hexdigest()
    )


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
    prompts = json.loads((AUDIT / "prompt_households.json").read_text())
    for scenario_id, household in prompts.items():
        assert household in _release()["scenarios"][scenario_id]["prompt"]["tool"]


def test_the_manifest_pins_every_evidence_file():
    """Rebuilding the manifest reproduces the committed one, so an evidence
    file that changed (a reformatted script, an edited review) fails here."""
    committed = json.loads((AUDIT / "manifest.json").read_text())
    assert _script("build_manifest").manifest() == committed
    assert committed["release"]["commit"] == RELEASE_COMMIT
    assert committed["release"]["inputs"][PAYLOAD_PATH] == RELEASE_SHA256
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
