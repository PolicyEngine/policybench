"""Release dashboard-data-20261006: the frozen records are what the driver builds.

scripts/release_20261006.py builds the release from release 20260930 (read
from git at the base commit) and docs/release_20261006/. These tests rebuild
each committed record from the same inputs without the stage, and check the
driver's gates with properties.

Invariants:
- the exclusion record is release 20260930's plus exactly the eight ruled
  records, with the four spec edits and nothing else;
- the adjudication record is release 20260930's plus one developer
  adjudication per ruled record, each keeping the judge verdict the evidence
  file binds;
- the annotation files are release 20260930's with #197's ledger, the release's
  rewrites and the adjudications applied, byte for byte;
- the references and predictions are release 20260930's;
- every score change comes from the eight records: rescoring the payload's own
  rows with the eight outputs scored again gives release 20260930's scores.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_20261006 as release  # noqa: E402

SPEC = release.load_spec()
BASE = SPEC["base_commit"]
FROZEN = ROOT / release.SNAPSHOT_RUN
ANNOTATIONS = ROOT / release.ANNOTATIONS


def _base_json(path: Path) -> dict:
    return json.loads(release.git_blob(BASE, path))


def _committed_json(path: Path) -> dict:
    return json.loads((ROOT / path).read_text())


def _frozen_release() -> str:
    manifest = _committed_json(release.MANIFEST)
    return manifest["published_dashboard_artifact"]["tag"]


def _require_frozen() -> None:
    if _frozen_release() != SPEC["release_tag"]:
        pytest.skip(f"the frozen release is not {SPEC['release_tag']}")


# --- Spec ------------------------------------------------------------------------


def test_the_spec_names_each_ruling_and_its_outputs():
    keys = [tuple(o) for p in SPEC["proposals"] for o in p["outputs"]]
    assert len(keys) == len(set(keys)) == 8
    assert {k[1] for k in keys} == {
        "federal_income_tax_before_refundable_credits",
        "state_income_tax_before_refundable_credits",
        "payroll_tax",
    }
    assert sorted(keys) == sorted(
        (item["scenario_id"], item["variable"]) for item in SPEC["adjudications"]
    )
    assert set(SPEC["rulings"]) == {"d963", "d974", "d972", "d831", "louisiana"}


def test_the_part_b_text_is_the_audits_own():
    """The words the 114 federal record gains are quoted from #193's record
    verbatim, not retyped."""
    edit = next(e for e in SPEC["record_edits"] if "append" in e)
    source = _committed_json(
        Path("reference_audit/2026-10-05-medicare-part-b/proposed_exclusions.json")
    )
    assert (
        edit["append"]
        in source["conditional_on_salt_decision"][0]["if_salt_record_adopted"]
    )


# --- Exclusions ------------------------------------------------------------------


def test_the_frozen_exclusions_are_the_base_plus_the_ruled_records():
    _require_frozen()
    base = _base_json(release.SNAPSHOT_RUN / release.EXCLUSIONS)
    built = release.build_exclusions(base, SPEC)
    frozen = (FROZEN / release.EXCLUSIONS).read_text()
    assert frozen == release.exclusions_text(built)
    records = json.loads(frozen)["exclusions"]
    assert len(records) == len(base["exclusions"]) + 8 == 64
    edited = {(e["scenario_id"], e["variable"]) for e in SPEC["record_edits"]}
    new = {tuple(o) for p in SPEC["proposals"] for o in p["outputs"]}
    old = {release.key(r): r for r in base["exclusions"]}
    for record in records:
        k = release.key(record)
        if k in new:
            assert record["decided_on"] == SPEC["decided_on"]
        elif k not in edited:
            assert record == old[k], k
    assert release.key(records[-1]) == ("scenario_023", "head_medicaid_eligible")


def test_the_references_and_predictions_are_release_20260930s():
    _require_frozen()
    for name in (*release.REFERENCE_FILES, "predictions.csv.gz"):
        assert (FROZEN / name).read_bytes() == release.git_blob(
            BASE, release.SNAPSHOT_RUN / name
        ), name


def test_every_model_is_scored_on_the_remaining_outputs():
    _require_frozen()
    from policybench.snapshot_payload import read_run_payload

    payload = read_run_payload(FROZEN)
    excluded = len(
        _committed_json(release.SNAPSHOT_RUN / release.EXCLUSIONS)["exclusions"]
    )
    assert {row["n"] for row in payload["modelStats"]} == {1984 - excluded} == {1920}
    assert len(payload["modelStats"]) == 46


# --- Adjudications and evidence --------------------------------------------------


def test_the_new_adjudications_keep_the_bound_judge_verdicts():
    _require_frozen()
    record = _committed_json(release.ANNOTATIONS / release.ADJUDICATIONS)
    base = _base_json(release.ANNOTATIONS / release.ADJUDICATIONS)
    assert (
        record["adjudications"][: len(base["adjudications"])] == base["adjudications"]
    )
    new = record["adjudications"][len(base["adjudications"]) :]
    assert len(new) == 8
    exclusions = {
        release.key(r): r
        for r in _committed_json(release.SNAPSHOT_RUN / release.EXCLUSIONS)[
            "exclusions"
        ]
    }
    evidence = _committed_json(release.EVIDENCE)["cases"]
    spec = {(i["scenario_id"], i["variable"]): i for i in SPEC["adjudications"]}
    for entry in new:
        k = release.key(entry)
        assert list(entry) == list(release.ENTRY_FIELDS)
        assert entry["reference_basis"] == exclusions[k]["unlisted_input"]
        assert entry["reasoning"] == spec[k]["reasoning"]
        assert entry["adjudicated_on"] == SPEC["decided_on"]
        assert entry["adjudicated_failure_source"] == "prompt_ambiguity"
        current = evidence[release.case_dir_name(*k)]["current"]
        assert (
            entry["judge_model"],
            entry["judge_failure_source"],
            entry["judge_failure_subtype"],
            entry["judge_reference_suspect"],
            entry["judged_on_utc"],
        ) == (
            current["judge_model"],
            current["case_failure_source"],
            current["case_failure_subtype"],
            current["reference_suspect"],
            current["judged_at_utc"][:10],
        )
    assert release.DATE_CONVENTIONS_NEW in record["date_conventions"]


def test_the_evidence_fills_the_2026_09_29_wave_and_adds_the_new_one():
    _require_frozen()
    evidence = _committed_json(release.EVIDENCE)
    base = _base_json(release.EVIDENCE)
    fill = SPEC["judge_evidence"]["fill_wave"]
    waves = evidence["wave_releases"]
    assert list(waves) == ["2026-09-05", "2026-09-22", "2026-09-29", "2026-10-05"]
    assert waves["2026-09-29"]["commit"] == fill["commit"]
    assert waves["2026-10-05"]["commit"] is None
    # Every earlier case keeps its evidence; the 2026-09-29 wave's gain
    # their published verdict.
    for case, found in base["cases"].items():
        current = evidence["cases"][case]
        extra = set(current) - set(found)
        assert {k: current[k] for k in found} == found, case
        assert extra <= {"published"}, case


# --- Annotations -----------------------------------------------------------------


def test_the_committed_annotations_rebuild_from_the_base_and_the_ledgers():
    """Byte for byte: release 20260930's files, #197's scenario_031 ledger, the
    release's rewrites, then every adjudication."""
    _require_frozen()
    from policybench.adjudications import parse_adjudications

    files = {
        name: release.git_blob(BASE, release.ANNOTATIONS / name)
        for name in release.ANNOTATION_CSVS
    }
    files = release.apply_text_rewrites(
        files, _committed_json(release.RULE_031)["rewrites"]
    )
    files = release.apply_text_rewrites(
        files, _committed_json(release.REWRITES_PATH)["rewrites"]
    )
    record = _committed_json(release.ANNOTATIONS / release.ADJUDICATIONS)
    files = release.adjudicated_csvs(
        files, parse_adjudications(record, "committed record")
    )
    for name in release.ANNOTATION_CSVS:
        assert (ANNOTATIONS / name).read_bytes() == files[name], name


def test_every_release_rewrite_is_in_force():
    _require_frozen()
    rewrites = _committed_json(release.REWRITES_PATH)["rewrites"]
    record = _committed_json(release.ANNOTATIONS / release.ADJUDICATIONS)
    excluded = {
        release.key(e): e
        for e in record["adjudications"]
        if e.get("excluded_from_scoring")
    }
    from policybench.adjudications import adjudication_sentence

    for item in rewrites:
        name = item["file"]
        rows = list(csv.DictReader(io.StringIO((ANNOTATIONS / name).read_text())))
        keys = release.REWRITE_KEYS[name]
        hits = [r for r in rows if all(r[k] == item[k] for k in keys)]
        assert len(hits) == 1, item
        expected = item["new"]
        k = (item["scenario_id"], item["variable"])
        if name == release.CASES and k in excluded:
            expected = expected.rstrip() + adjudication_sentence(excluded[k])
        assert hits[0][item["field"]] == expected, item


# --- Scores ----------------------------------------------------------------------


def _household_exact(country: dict, rescore: set) -> dict[str, float]:
    """Each model's household-impact-weighted exact rate from the payload's
    own rows, with the outputs in ``rescore`` scored again: the aggregation
    test_snapshot_artifacts mirrors, written out again here."""
    from policybench.spec import output_group_id

    weights: dict[str, float] = {}
    for variable, weight in country["globalWeights"]["household"].items():
        group = output_group_id(variable)
        weights[group] = weights.get(group, 0.0) + weight
    totals: dict[str, list[float]] = {}
    for scenario, variables in country["scenarioPredictions"].items():
        kept = [
            (variable, rows)
            for variable, rows in variables.items()
            if output_group_id(variable) in weights
            and (
                (scenario, variable) in rescore
                or not any(row.get("scored") is False for row in rows.values())
            )
        ]
        counts: dict[str, int] = {}
        for variable, _ in kept:
            counts[output_group_id(variable)] = (
                counts.get(output_group_id(variable), 0) + 1
            )
        raw = {
            v: weights[output_group_id(v)] / counts[output_group_id(v)] for v, _ in kept
        }
        total = sum(raw.values())
        if total <= 0:
            continue
        models = {model for _, rows in kept for model in rows}
        for model in models:
            score = sum(raw[v] / total * rows[model]["exact"] for v, rows in kept)
            entry = totals.setdefault(model, [0.0, 0])
            entry[0] += score
            entry[1] += 1
    return {model: s / n for model, (s, n) in totals.items()}


def test_the_score_changes_are_the_eight_exclusions_alone():
    """Scoring the eight outputs again in this release's payload gives release
    20260930's published exact rates, and this release's are its modelStats:
    no annotation, window or other change moves a score."""
    _require_frozen()
    from policybench.snapshot_payload import read_run_payload

    payload = read_run_payload(FROZEN)
    base = json.loads(
        gzip.decompress(release.git_blob(BASE, release.SNAPSHOT_RUN / "data.json.gz"))
    )
    new = {tuple(o) for p in SPEC["proposals"] for o in p["outputs"]}
    now = {row["model"]: row["exact"] for row in payload["modelStats"]}
    before = {row["model"]: row["exact"] for row in base["modelStats"]}
    rebuilt_now = _household_exact(payload, set())
    rebuilt_before = _household_exact(payload, new)
    for model in now:
        assert rebuilt_now[model] == pytest.approx(now[model], abs=1e-9), model
        assert rebuilt_before[model] == pytest.approx(before[model], abs=1e-9), model


# --- Properties of the driver's gates --------------------------------------------

TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    max_size=30,
)


def _csv(rows: list[list[str]]) -> bytes:
    return release._write_csv(["scenario_id", "variable", "model", "annotation"], rows)


ROWS = st.lists(
    st.tuples(
        st.sampled_from(["s1", "s2", "s3"]),
        st.sampled_from(["a", "b"]),
        st.sampled_from(["m1", "m2"]),
        TEXT,
    ),
    max_size=8,
    unique_by=lambda r: r[:3],
)


@settings(max_examples=150, deadline=None)
@given(ROWS, st.data())
def test_rewrites_move_only_their_fields_and_are_idempotent(rows, data):
    rows = [list(r) for r in rows]
    files = {release.ROWS: _csv(rows)}
    targets = (
        data.draw(
            st.lists(
                st.integers(0, max(len(rows) - 1, 0)), unique=True, max_size=len(rows)
            )
        )
        if rows
        else []
    )
    news = [data.draw(TEXT) for _ in targets]
    ledger = [
        {
            "file": release.ROWS,
            "scenario_id": rows[i][0],
            "variable": rows[i][1],
            "model": rows[i][2],
            "field": "annotation",
            "old": rows[i][3],
            "new": new,
        }
        for i, new in zip(targets, news)
    ]
    once = release.apply_text_rewrites(files, ledger)
    assert release.apply_text_rewrites(once, ledger) == once
    _, after = release._read_csv(once[release.ROWS])
    for index, (before, row) in enumerate(zip(rows, after)):
        assert row[:3] == before[:3]
        if index in targets:
            assert row[3] == news[targets.index(index)]
        else:
            assert row[3] == before[3]


@settings(max_examples=100, deadline=None)
@given(ROWS, TEXT, TEXT)
def test_a_rewrite_of_text_the_field_does_not_hold_is_refused(rows, old, new):
    rows = [list(r) for r in rows]
    if not rows or old in (rows[0][3], new):
        return
    files = {release.ROWS: _csv(rows)}
    item = {
        "file": release.ROWS,
        "scenario_id": rows[0][0],
        "variable": rows[0][1],
        "model": rows[0][2],
        "field": "annotation",
        "old": old,
        "new": new,
    }
    if rows[0][3] == new:
        return
    with pytest.raises(SystemExit):
        release.apply_text_rewrites(files, [item])


JSONISH = st.recursive(
    st.one_of(st.integers(-3, 3), st.booleans(), st.none(), TEXT),
    lambda children: (
        st.dictionaries(st.sampled_from(list("abcd")), children, max_size=3)
        | st.lists(children, max_size=3)
    ),
    max_leaves=12,
)


@settings(max_examples=200, deadline=None)
@given(JSONISH, JSONISH)
def test_leaf_paths_are_empty_exactly_when_equal_and_symmetric(a, b):
    paths = release.leaf_paths(a, b)
    assert (paths == []) == (a == b)
    assert sorted(map(repr, paths)) == sorted(map(repr, release.leaf_paths(b, a)))


@settings(max_examples=100, deadline=None)
@given(st.dictionaries(st.sampled_from(list("abcd")), JSONISH, max_size=4), JSONISH)
def test_a_change_under_an_allowed_prefix_is_never_a_problem(before, value):
    after = {**before, "model_response_date": value}
    before = {**before, "model_response_date": "x"}
    assert release.manifest_problems(before, after) == []


def test_a_change_outside_the_release_is_a_problem():
    before = {"snapshot_date": "2026-09-30", "model_response_date": "a"}
    after = {"snapshot_date": "2026-10-06", "model_response_date": "b"}
    assert release.manifest_problems(before, after) == [("snapshot_date",)]


@settings(max_examples=50, deadline=None)
@given(st.integers(0, 60), st.integers(0, 60))
def test_the_version_description_counts_the_records_it_is_given(old, new):
    text = (
        "Scored reference outputs (the 56 excluded outputs keep the values they "
        "were decided on: 52 from policyengine-us 1.755.4, 4 from 2.15.17, and more)"
    )
    records = [{"engine_version": "policyengine-us 1.755.4"}] * old + [
        {"engine_version": "policyengine-us 2.15.17"}
    ] * new
    if not old or not new:
        with pytest.raises(KeyError):
            release.versions_description(text, records)
        return
    result = release.versions_description(text, records)
    assert (
        f"the {old + new} excluded outputs keep the values they were decided on: "
        f"{old} from policyengine-us 1.755.4, {new} from 2.15.17"
    ) in result


def test_an_edit_that_does_not_fit_is_refused():
    record = {"scenario_id": "s", "variable": "v", "note": "abc abc"}
    with pytest.raises(SystemExit):
        release.apply_record_edit(
            record, {"field": "note", "replace": "abc", "with": "x"}
        )
    with pytest.raises(SystemExit):
        release.apply_record_edit(record, {"field": "note", "append": " abc"})
    assert (
        release.apply_record_edit(record, {"field": "note", "append": " d"})["note"]
        == "abc abc d"
    )


def test_annotation_scope_refuses_a_change_to_another_output():
    header = [
        "country",
        "scenario_id",
        "variable",
        "model",
        "failure_source",
        "failure_subtype",
        "reference_suspect",
        "annotation",
    ]
    base = release._write_csv(
        header, [["us", "s1", "v", "m", "llm_error", "x", "False", "t"]]
    )
    moved = release._write_csv(
        header, [["us", "s1", "v", "m", "prompt_ambiguity", "x", "False", "t"]]
    )
    files = {
        name: base if name == release.ROWS else b"" for name in release.ANNOTATION_CSVS
    }
    staged = dict(files, **{release.ROWS: moved})
    cases = release._write_csv(["scenario_id", "variable"], [])
    files[release.CASES] = staged[release.CASES] = cases
    files[release.EXPLANATIONS] = staged[release.EXPLANATIONS] = cases
    assert (
        release.verify_annotation_scope(files, staged, {("s1", "v")}, set())[
            release.ROWS
        ]
        == 1
    )
    with pytest.raises(SystemExit):
        release.verify_annotation_scope(files, staged, set(), {("s1", "v")})
