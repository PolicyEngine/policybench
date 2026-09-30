"""scripts/restate_gpt61sol_adjudications.py restates re-judged adjudications."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import restate_gpt61sol_adjudications as restate  # noqa: E402
from freeze_snapshot import verify_adjudications_keep_judge_verdicts  # noqa: E402

from policybench.adjudications import (  # noqa: E402
    excluded_case_keys,
    load_adjudications,
)

OPUS55 = "claude-opus-5-5"
CASE = "us__scenario_001__snap"
KEY = "scenario_001:snap"


def _write_case(root: Path, case: str, verdict: dict, day: str, **meta) -> None:
    """A verdict and its sha256-bound sidecar, as run_audit_claude.sh writes."""
    directory = root / case
    directory.mkdir(parents=True, exist_ok=True)
    # Each judge run writes its own verdict: a re-judge never repeats the
    # seed's bytes (it also covers GPT-6.1 Sol's answer).
    verdict = {**verdict, "rationale": f"{verdict['rationale']} Judged {day}."}
    blob = json.dumps(verdict, indent=2, sort_keys=True).encode()
    (directory / "verdict.json").write_bytes(blob)
    sidecar = {
        "judge_runner": "scripts/run_audit_claude.sh",
        "judge_model_requested": OPUS55,
        "judge_model_reported": [OPUS55],
        "judged_at_utc": f"{day}T03:05:58+00:00",
        "verdict_sha256": hashlib.sha256(blob).hexdigest(),
        **meta,
    }
    (directory / "verdict.meta.json").write_text(json.dumps(sidecar))


def _verdict(source: str, subtype: str = "state_local_rule", flag: bool = False):
    return {
        "case_failure_source": source,
        "case_failure_subtype": subtype,
        "reference_suspect": flag,
        "rationale": "The reference applies the enacted schedule.",
        "reference_bug_hypothesis": "",
        "models": [],
    }


def _entry(**overrides) -> dict:
    """A 2026-09-29 decision on a case the 09-29 wave re-judged once."""
    entry = {
        "country": "us",
        "scenario_id": "scenario_001",
        "variable": "snap",
        "judge_model": OPUS55,
        "judge_failure_source": "reference_model_issue_fixed",
        "judge_failure_subtype": "state_local_rule",
        "adjudicated_failure_source": "reference_engine_defect",
        "adjudicated_failure_subtype": "state_local_rule",
        "adjudicated_on": "2026-09-22",
        "adjudicator": "developer",
        "excluded_from_scoring": True,
        "judge_reference_suspect": True,
        "reference_verdict": "engine_defect",
        "reference_basis": "7 CFR 273.9(d)(6)",
        "reasoning": "The engine drops the utility allowance.",
        "judge_rejudged_on": "2026-09-29",
        "judge_previous": [
            {
                "judge_model": OPUS55,
                "judge_failure_source": "reference_model_issue_fixed",
                "judge_failure_subtype": "state_local_rule",
                "judge_reference_suspect": True,
                "judged_on": "2026-09-23",
            }
        ],
    }
    entry.update(overrides)
    return entry


@pytest.fixture
def trees(tmp_path):
    return tmp_path / "stage", tmp_path / "seed"


def _run(entries, trees, wave=frozenset(), rejudged=frozenset({CASE})):
    stage, seed = trees
    return restate.restate_entries(copy.deepcopy(entries), stage, seed, rejudged, wave)


def _decisions(entry: dict) -> list:
    return [(k, v) for k, v in entry.items() if k not in restate.JUDGE_FIELDS]


def test_a_changed_class_moves_the_replaced_verdict_under_judge_previous(trees):
    stage, seed = trees
    _write_case(
        seed, CASE, _verdict("reference_model_issue_fixed", flag=True), "2026-09-29"
    )
    _write_case(stage, CASE, _verdict("llm_error", flag=True), "2026-09-30")
    entry = _entry()
    (out,), changes = _run([entry], trees)
    assert out["judge_failure_source"] == "llm_error"
    assert out["judge_reference_suspect"] is True
    assert out["judge_rejudged_on"] == "2026-09-30"
    assert out["judge_previous"] == [
        *entry["judge_previous"],
        {
            "judge_model": OPUS55,
            "judge_failure_source": "reference_model_issue_fixed",
            "judge_failure_subtype": "state_local_rule",
            "judge_reference_suspect": True,
            "judged_on": "2026-09-29",
        },
    ]
    assert _decisions(out) == _decisions(entry)
    assert list(out) == list(entry)
    assert changes == [
        f"{CASE}: reference_model_issue_fixed/state_local_rule flag=True "
        "(2026-09-29) -> llm_error/state_local_rule flag=True (2026-09-30)"
    ]
    verify_adjudications_keep_judge_verdicts([out], stage)


def test_a_first_rejudge_dates_both_fields_and_keeps_adjudicated_verdict_last(trees):
    stage, seed = trees
    _write_case(seed, CASE, _verdict("llm_error"), "2026-09-29")
    _write_case(stage, CASE, _verdict("reference_later_law"), "2026-09-30")
    entry = {
        "country": "us",
        "scenario_id": "scenario_001",
        "variable": "snap",
        "judge_model": OPUS55,
        "judged_on_utc": "2026-09-29",
        "judge_failure_source": "llm_error",
        "judge_failure_subtype": "state_local_rule",
        "adjudicated_failure_source": "llm_error",
        "adjudicated_failure_subtype": "state_local_rule",
        "adjudicated_on": "2026-09-29",
        "adjudicator": "developer",
        "judge_reference_suspect": False,
        "reasoning": "The schedule was enacted before the freeze.",
        "adjudicated_verdict": {"judge_model": "claude-opus-5"},
    }
    (out,), _ = _run([entry], trees)
    assert out["judged_on_utc"] == out["judge_rejudged_on"] == "2026-09-30"
    assert out["judge_failure_source"] == "reference_later_law"
    assert list(out)[-3:] == [
        "judge_rejudged_on",
        "judge_previous",
        "adjudicated_verdict",
    ]
    assert out["judge_previous"][-1]["judge_failure_source"] == "llm_error"
    assert _decisions(out) == _decisions(entry)


def test_a_same_class_rejudge_is_restated_with_its_dates(trees):
    stage, seed = trees
    _write_case(
        seed, CASE, _verdict("reference_model_issue_fixed", flag=True), "2026-09-29"
    )
    _write_case(
        stage, CASE, _verdict("reference_model_issue_fixed", flag=True), "2026-09-30"
    )
    (out,), changes = _run([_entry()], trees)
    assert out["judge_rejudged_on"] == "2026-09-30"
    assert [item["judged_on"] for item in out["judge_previous"]] == [
        "2026-09-23",
        "2026-09-29",
    ]
    assert len(changes) == 1


@pytest.mark.parametrize("new_flag", [False, True])
def test_a_wave_flag_stays_recorded_where_the_verdict_does_not_raise_it(
    trees, new_flag
):
    stage, seed = trees
    _write_case(seed, CASE, _verdict("llm_error", flag=False), "2026-09-29")
    _write_case(stage, CASE, _verdict("llm_error", flag=new_flag), "2026-09-30")
    entry = _entry(
        judge_failure_source="llm_error",
        judge_reference_suspect_source=restate.FLAG_SOURCE_EARLIER_RUN,
    )
    (out,), _ = _run([entry], trees, wave=frozenset({KEY}))
    assert out["judge_reference_suspect"] is True
    assert ("judge_reference_suspect_source" in out) is not new_flag
    item = out["judge_previous"][-1]
    assert item["judge_reference_suspect"] is True
    assert item["judge_reference_suspect_source"] == restate.ITEM_FLAG_SOURCE
    verify_adjudications_keep_judge_verdicts([out], stage)


def test_a_flag_outside_the_wave_follows_each_verdict(trees):
    stage, seed = trees
    _write_case(
        seed, CASE, _verdict("reference_model_issue_fixed", flag=True), "2026-09-29"
    )
    _write_case(stage, CASE, _verdict("llm_error", flag=False), "2026-09-30")
    (out,), _ = _run([_entry()], trees)
    assert out["judge_reference_suspect"] is False
    assert "judge_reference_suspect_source" not in out
    assert out["judge_previous"][-1]["judge_reference_suspect"] is True
    assert "judge_reference_suspect_source" not in out["judge_previous"][-1]


def test_a_new_flag_without_a_reference_verdict_stops(trees):
    stage, seed = trees
    _write_case(seed, CASE, _verdict("llm_error"), "2026-09-29")
    _write_case(stage, CASE, _verdict("llm_error", flag=True), "2026-09-30")
    entry = _entry(
        judge_failure_source="llm_error",
        judge_reference_suspect=False,
        adjudicated_failure_source="llm_error",
        excluded_from_scoring=False,
    )
    del entry["reference_verdict"], entry["reference_basis"]
    with pytest.raises(SystemExit, match="needs a developer decision"):
        _run([entry], trees)


@pytest.mark.parametrize(
    "field, value",
    [
        ("judge_failure_subtype", "thresholds_rates"),
        ("judge_model", "claude-opus-5"),
        ("judge_reference_suspect", False),
        ("judge_reference_suspect_source", "an earlier run"),
        # Dated by another verdict than the seed's (date_conventions).
        ("judge_rejudged_on", "2026-09-28"),
    ],
)
def test_a_record_that_does_not_name_the_seed_verdict_stops(trees, field, value):
    stage, seed = trees
    _write_case(
        seed, CASE, _verdict("reference_model_issue_fixed", flag=True), "2026-09-29"
    )
    _write_case(stage, CASE, _verdict("llm_error", flag=True), "2026-09-30")
    with pytest.raises(SystemExit, match="does not name the seed verdict"):
        _run([_entry(**{field: value})], trees)


@pytest.mark.parametrize("defect", ["unbound", "other model", "missing", "seed"])
def test_a_stage_verdict_that_is_not_a_bound_opus55_rejudge_stops(trees, defect):
    stage, seed = trees
    _write_case(
        seed, CASE, _verdict("reference_model_issue_fixed", flag=True), "2026-09-29"
    )
    if defect == "seed":
        _write_case(
            stage,
            CASE,
            _verdict("reference_model_issue_fixed", flag=True),
            "2026-09-29",
        )
    elif defect != "missing":
        extra = (
            {"judge_model_reported": ["claude-opus-5"]}
            if defect == "other model"
            else {}
        )
        _write_case(
            stage, CASE, _verdict("llm_error", flag=True), "2026-09-30", **extra
        )
        if defect == "unbound":
            (stage / CASE / "verdict.json").write_text("{}")
    with pytest.raises(SystemExit):
        _run([_entry()], trees)


def test_a_stage_verdict_older_than_the_seed_verdict_stops(trees):
    stage, seed = trees
    _write_case(
        seed, CASE, _verdict("reference_model_issue_fixed", flag=True), "2026-09-29"
    )
    _write_case(stage, CASE, _verdict("llm_error", flag=True), "2026-09-28")
    with pytest.raises(SystemExit, match="predates the seed verdict"):
        _run([_entry()], trees)


def test_an_entry_whose_two_dates_disagree_stops(trees):
    """judged_on_utc and judge_rejudged_on both date the top-level verdict."""
    stage, seed = trees
    _write_case(
        seed, CASE, _verdict("reference_model_issue_fixed", flag=True), "2026-09-29"
    )
    _write_case(stage, CASE, _verdict("llm_error", flag=True), "2026-09-30")
    with pytest.raises(SystemExit, match="does not name the seed verdict"):
        _run([_entry(judged_on_utc="2026-09-05")], trees)
    (out,), _ = _run([_entry(judged_on_utc="2026-09-29")], trees)
    assert out["judged_on_utc"] == out["judge_rejudged_on"] == "2026-09-30"


def test_a_sidecar_timestamp_is_read_as_its_utc_day():
    assert restate._utc_day("2026-09-29T22:30:00-05:00") == "2026-09-30"
    assert restate._utc_day("2026-09-30T03:05:58.219252+00:00") == "2026-09-30"
    with pytest.raises(SystemExit, match="no time zone"):
        restate._utc_day("2026-09-30T03:05:58")


def test_entries_outside_the_rejudged_cases_are_untouched(trees):
    entry = _entry()
    out, changes = _run([entry], trees, rejudged=frozenset())
    assert out == [entry] and changes == []


def _staged(tmp_path, kept_verdict):
    """A stage whose record holds one re-judged entry and one carried over."""
    stage, seed = tmp_path / "stage", tmp_path / "seed"
    _write_case(
        seed / "cases",
        CASE,
        _verdict("reference_model_issue_fixed", flag=True),
        "2026-09-29",
    )
    _write_case(
        stage / "audit" / "cases", CASE, _verdict("llm_error", flag=True), "2026-09-30"
    )
    record_path = stage / "publish" / restate.RUN_NAME / "annotations"
    record_path.mkdir(parents=True)
    record_path /= "us_adjudications.json"
    kept = _entry(scenario_id="scenario_002")
    # A carried-over verdict: triage's verbatim check reads it from the stage.
    _write_case(
        stage / "audit" / "cases", "us__scenario_002__snap", kept_verdict, "2026-09-29"
    )
    # prepare copied the seed's verdict and sidecar for a case it kept.
    carried = "us__scenario_003__snap"
    for tree in (seed / "cases", stage / "audit" / "cases"):
        _write_case(tree, carried, _verdict("llm_error"), "2026-09-29")
    record = {"schema_version": 2, "note": "n", "adjudications": [_entry(), kept]}
    record_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    (stage / "prompt-changes.json").write_text(
        json.dumps({"kept": [carried], "changed": [CASE], "added": []})
    )
    wave = tmp_path / "wave.json"
    wave.write_text("[]")
    args = ["--stage-dir", str(stage), "--audit-seed", str(seed)]
    return stage, record_path, kept, [*args, "--wave-flags", str(wave)]


def test_main_restates_the_staged_record_and_writes_its_evidence(tmp_path):
    stage, record_path, kept, args = _staged(
        tmp_path, _verdict("reference_model_issue_fixed", flag=True)
    )
    restate.main(args)
    text = record_path.read_text()
    written = json.loads(text)
    assert text == json.dumps(written, indent=2, ensure_ascii=False) + "\n"
    assert written["adjudications"][0]["judge_failure_source"] == "llm_error"
    assert written["adjudications"][1] == kept
    evidence = json.loads((stage / "restated-adjudications.json").read_text())
    assert evidence["cases"][CASE]["class_changed"] is True
    assert evidence["cases"][CASE]["flag_changed"] is False
    assert evidence["cases"][CASE]["replaced"]["judged_at_utc"].startswith("2026-09-29")
    # A second pass leaves the record byte-identical.
    restate.main(args)
    assert record_path.read_text() == text


def test_main_leaves_the_record_alone_when_the_restated_record_fails_triage(
    tmp_path,
):
    """The carried-over entry names a class its stage verdict does not have, so
    triage's verbatim check fails: nothing is written."""
    stage, record_path, _, args = _staged(tmp_path, _verdict("llm_error", flag=True))
    text = record_path.read_text()
    with pytest.raises(SystemExit, match="verbatim"):
        restate.main(args)
    assert record_path.read_text() == text
    assert sorted(p.name for p in record_path.parent.iterdir()) == [
        "us_adjudications.json"
    ]
    assert not (stage / "restated-adjudications.json").exists()


def test_main_refuses_a_seed_that_is_not_the_stages(tmp_path):
    """A seed whose carried-over verdicts differ from the stage's (an older
    audit, say) would name the wrong replaced verdict: stop before writing."""
    stage, record_path, _, args = _staged(
        tmp_path, _verdict("reference_model_issue_fixed", flag=True)
    )
    text = record_path.read_text()
    seed = Path(args[args.index("--audit-seed") + 1])
    _write_case(
        seed / "cases", "us__scenario_003__snap", _verdict("llm_error"), "2026-09-22"
    )
    with pytest.raises(SystemExit, match="not the stage's"):
        restate.main(args)
    assert record_path.read_text() == text
    assert not (stage / "restated-adjudications.json").exists()


def test_an_entry_without_a_recorded_flag_gains_it_before_the_trailing_fields(
    trees,
):
    stage, seed = trees
    _write_case(seed, CASE, _verdict("llm_error"), "2026-09-29")
    _write_case(stage, CASE, _verdict("llm_error"), "2026-09-30")
    entry = _entry(
        judge_failure_source="llm_error",
        adjudicated_failure_source="llm_error",
        excluded_from_scoring=False,
    )
    for name in ("judge_reference_suspect", "reference_verdict", "reference_basis"):
        del entry[name]
    entry["adjudicated_verdict"] = {"judge_model": "claude-opus-5"}
    (out,), _ = _run([entry], trees)
    assert list(out)[list(out).index("reasoning") :] == [
        "reasoning",
        "judge_reference_suspect",
        "judge_rejudged_on",
        "judge_previous",
        "adjudicated_verdict",
    ]
    assert out["judge_reference_suspect"] is False


def test_a_new_source_sits_after_the_decisions_and_an_old_one_keeps_its_wording(
    trees,
):
    """The record keeps a top-level source after the decision fields, before
    the first trailing judge field after reasoning (judged_on_utc where it
    comes last), and words it two ways."""
    stage, seed = trees
    other = "us__scenario_002__snap"
    _write_case(seed, CASE, _verdict("llm_error", flag=True), "2026-09-29")
    _write_case(stage, CASE, _verdict("llm_error", flag=False), "2026-09-30")
    _write_case(seed, other, _verdict("llm_error", flag=False), "2026-09-29")
    _write_case(stage, other, _verdict("llm_error", flag=False), "2026-09-30")
    late = _entry(judge_failure_source="llm_error", judged_on_utc="2026-09-29")
    del late["judge_rejudged_on"], late["judge_previous"]
    worded = "claude-opus-5-5 judge run adjudicated 2026-09-22"
    sourced = _entry(
        scenario_id="scenario_002",
        judge_failure_source="llm_error",
        judge_reference_suspect_source=worded,
    )
    wave = frozenset({KEY, "scenario_002:snap"})
    (first, second), _ = _run(
        [late, sourced], trees, wave=wave, rejudged=frozenset({CASE, other})
    )
    assert list(first)[list(first).index("reasoning") :] == [
        "reasoning",
        "judge_reference_suspect_source",
        "judged_on_utc",
        "judge_rejudged_on",
        "judge_previous",
    ]
    assert first["judge_reference_suspect_source"] == restate.FLAG_SOURCE_EARLIER_RUN
    assert "judge_reference_suspect_source" not in first["judge_previous"][-1]
    assert second["judge_reference_suspect_source"] == worded
    assert (
        second["judge_previous"][-1]["judge_reference_suspect_source"]
        == restate.ITEM_FLAG_SOURCE
    )


def test_a_new_source_follows_reference_fields_that_come_after_reasoning(trees):
    stage, seed = trees
    _write_case(seed, CASE, _verdict("llm_error", flag=True), "2026-09-29")
    _write_case(stage, CASE, _verdict("llm_error", flag=False), "2026-09-30")
    entry = _entry(judge_failure_source="llm_error")
    reasoning = entry.pop("reasoning")
    names = list(entry)
    at = names.index("judge_reference_suspect")
    items = list(entry.items())
    entry = dict(items[:at] + [("reasoning", reasoning)] + items[at:])
    entry["adjudicated_verdict"] = {"judge_model": "claude-opus-5"}
    (out,), _ = _run([entry], trees, wave=frozenset({KEY}))
    assert list(out)[list(out).index("reasoning") :] == [
        "reasoning",
        "judge_reference_suspect",
        "reference_verdict",
        "reference_basis",
        "judge_reference_suspect_source",
        "judge_rejudged_on",
        "judge_previous",
        "adjudicated_verdict",
    ]


@pytest.mark.parametrize(
    "field, value",
    [
        ("judge_model", "gpt-5.6-sol"),
        ("judge_rejudged_on", "2020-01-01"),
        ("judged_on_utc", "2026-09-28"),
    ],
)
def test_a_restated_record_whose_top_is_not_a_later_opus55_verdict_stops(
    trees, field, value
):
    """The seed verdict already sits last in judge_previous, but the top names
    no Opus 5.5 re-judge dated after it: stop rather than overwrite it."""
    stage, seed = trees
    _write_case(
        seed, CASE, _verdict("reference_model_issue_fixed", flag=True), "2026-09-29"
    )
    _write_case(stage, CASE, _verdict("llm_error", flag=True), "2026-09-30")
    (restated,), _ = _run([_entry()], trees)
    tampered = {**restated, "judge_failure_source": "prompt_ambiguity", field: value}
    with pytest.raises(SystemExit, match="names neither the seed verdict"):
        _run([tampered], trees)
    # An honest later re-judge replaces only the top.
    later = {**restated, "judge_failure_source": "prompt_ambiguity"}
    (again,), _ = _run([later], trees)
    assert again == restated


def test_an_earlier_item_that_reads_like_the_seed_verdict_still_gains_it(trees):
    """The 09-29 wave re-judged the case on the day it first judged it and got
    the same class, so the last judge_previous item reads exactly like the seed
    verdict. The top still names the seed verdict, so it is appended once."""
    stage, seed = trees
    _write_case(
        seed, CASE, _verdict("reference_model_issue_fixed", flag=True), "2026-09-29"
    )
    _write_case(stage, CASE, _verdict("llm_error", flag=True), "2026-09-30")
    earlier = {
        "judge_model": OPUS55,
        "judge_failure_source": "reference_model_issue_fixed",
        "judge_failure_subtype": "state_local_rule",
        "judge_reference_suspect": True,
        "judged_on": "2026-09-29",
    }
    entry = _entry(judge_previous=[earlier])
    (out,), changes = _run([entry], trees)
    assert out["judge_previous"] == [earlier, earlier]
    assert out["judge_failure_source"] == "llm_error"
    assert out["judge_rejudged_on"] == "2026-09-30"
    assert len(changes) == 1
    (again,), none = _run([out], trees)
    assert again == out and none == []


def test_a_same_day_rejudge_that_repeats_the_seed_verdict_stops(trees):
    """A restated entry would still name the seed verdict, so a rerun could not
    tell it from an entry never restated."""
    stage, seed = trees
    _write_case(
        seed, CASE, _verdict("reference_model_issue_fixed", flag=True), "2026-09-29"
    )
    repeat = {
        **_verdict("reference_model_issue_fixed", flag=True),
        "rationale": "A second run.",
    }
    _write_case(stage, CASE, repeat, "2026-09-29")
    with pytest.raises(SystemExit, match="repeats the seed verdict"):
        _run([_entry()], trees)
    # The same class a day later is an ordinary same-class re-judge.
    _write_case(stage, CASE, repeat, "2026-09-30")
    (out,), _ = _run([_entry()], trees)
    assert out["judge_rejudged_on"] == "2026-09-30"


WORDED = "claude-opus-5-5 judge run adjudicated 2026-09-22"
SOURCES = [
    "llm_error",
    "reference_model_issue_fixed",
    "reference_later_law",
    "prompt_ambiguity",
]
SUBTYPES = ["state_local_rule", "thresholds_rates", "age_disability"]


@st.composite
def _histories(draw):
    decided = draw(st.booleans())  # a reference verdict answers a flag
    waved = decided and draw(st.booleans())
    return {
        "decided": decided,
        "waved": waved,
        "seed": (
            draw(st.sampled_from(SOURCES)),
            draw(st.sampled_from(SUBTYPES)),
            decided and draw(st.booleans()),
        ),
        "rejudges": draw(
            st.lists(
                st.tuples(
                    st.sampled_from(SOURCES), st.sampled_from(SUBTYPES), st.booleans()
                ),
                min_size=1,
                max_size=2,
            )
        ),
        "rejudged_before": draw(st.booleans()),
        "judged_on_utc": draw(st.booleans()),
        "adjudicated_verdict": draw(st.booleans()),
        # The record words a top-level source two ways.
        "wording": draw(st.sampled_from([restate.FLAG_SOURCE_EARLIER_RUN, WORDED])),
        # A re-judge may fall on the seed verdict's own UTC day.
        "same_day": draw(st.booleans()),
        # The earlier wave's re-judge reads exactly like the seed verdict.
        "echo": draw(st.booleans()),
    }


@settings(max_examples=80, deadline=None)
@given(history=_histories())
def test_restatement_properties(tmp_path_factory, history):
    """For any adjudicated case and any sequence of stage re-judges: a flag no
    reference verdict answers stops the script, and so does a re-judge that
    repeats the seed verdict on the seed's own day; otherwise the decisions and
    their order survive byte for byte, the top level names the latest stage
    verdict under the wave-flag rule, judge_previous gains exactly the seed
    verdict, dated from its sidecar, the dates follow the latest sidecar,
    triage's verbatim-verdict check passes, a second pass changes nothing,
    and restating after each re-judge equals restating once after the last."""
    root = tmp_path_factory.mktemp("restate")
    seed = root / "seed"
    source, subtype, seed_flag = history["seed"]
    _write_case(seed, CASE, _verdict(source, subtype, seed_flag), "2026-09-29")
    waved = history["waved"]
    wave = frozenset({KEY}) if waved else frozenset()
    # Keys in the committed record's order: judged_on_utc after the judge
    # model, a top-level flag source right after reasoning, the re-judge
    # fields next and adjudicated_verdict last.
    entry = {"country": "us", "scenario_id": "scenario_001", "variable": "snap"}
    entry["judge_model"] = OPUS55
    # Every entry carries a date: judged_on_utc until a later wave re-judges
    # it, and sometimes beside judge_rejudged_on after that.
    if history["judged_on_utc"] or not history["rejudged_before"]:
        entry["judged_on_utc"] = "2026-09-29"
    entry.update(
        judge_failure_source=source,
        judge_failure_subtype=subtype,
        adjudicated_failure_source="llm_error",
        adjudicated_failure_subtype=subtype,
        adjudicated_on="2026-09-22",
        adjudicator="developer",
    )
    if history["decided"]:
        entry.update(
            adjudicated_failure_source="reference_engine_defect",
            excluded_from_scoring=True,
        )
    entry["judge_reference_suspect"] = seed_flag or waved
    if history["decided"]:
        entry.update(reference_verdict="engine_defect", reference_basis="b")
    entry["reasoning"] = "r"
    if waved and not seed_flag:
        entry["judge_reference_suspect_source"] = history["wording"]
    if history["rejudged_before"]:
        entry["judge_rejudged_on"] = "2026-09-29"
        earlier = {
            "judge_model": OPUS55,
            "judge_failure_source": "llm_error",
            "judge_failure_subtype": subtype,
            "judge_reference_suspect": waved,
            "judged_on": "2026-09-23",
        }
        if history["echo"]:
            earlier = {
                "judge_model": OPUS55,
                "judge_failure_source": source,
                "judge_failure_subtype": subtype,
                "judge_reference_suspect": seed_flag or waved,
                "judged_on": "2026-09-29",
            }
            if waved and not seed_flag:
                earlier["judge_reference_suspect_source"] = restate.ITEM_FLAG_SOURCE
        entry["judge_previous"] = [earlier]
    if history["adjudicated_verdict"]:
        entry["adjudicated_verdict"] = {"judge_model": "claude-opus-5"}
    original = copy.deepcopy(entry)
    restated = entry
    days = ("2026-09-29" if history["same_day"] else "2026-09-30", "2026-10-01")
    dropped = False  # an earlier re-judge flagged, so its own flag cleared the source
    for index, (new_source, new_subtype, new_flag) in enumerate(history["rejudges"]):
        stage = root / f"stage{index}"
        day = days[index]
        rejudge = {**_verdict(new_source, new_subtype, new_flag)}
        rejudge["rationale"] = f"Re-judge {index}."
        _write_case(stage, CASE, rejudge, day)
        if new_flag and not history["decided"]:
            with pytest.raises(SystemExit, match="needs a developer decision"):
                _run([restated], (stage, seed), wave)
            return
        if day == "2026-09-29" and (new_source, new_subtype, new_flag) == (
            source,
            subtype,
            seed_flag,
        ):
            with pytest.raises(SystemExit, match="repeats the seed verdict"):
                _run([restated], (stage, seed), wave)
            return
        (restated,), changes = _run([restated], (stage, seed), wave)
        assert _decisions(restated) == _decisions(original)
        assert restated["judge_failure_source"] == new_source
        assert restated["judge_failure_subtype"] == new_subtype
        assert restated["judge_reference_suspect"] is (new_flag or waved)
        assert ("judge_reference_suspect_source" in restated) is (
            waved and not new_flag
        )
        if "judge_reference_suspect_source" in restated:
            # An existing source keeps its wording; one an intermediate
            # verdict's flag cleared returns in the canonical wording.
            assert restated["judge_reference_suspect_source"] == (
                restate.FLAG_SOURCE_EARLIER_RUN
                if dropped or "judge_reference_suspect_source" not in original
                else original["judge_reference_suspect_source"]
            )
        item = restated["judge_previous"][-1]
        assert restated["judge_previous"][:-1] == original.get("judge_previous", [])
        assert (
            item["judge_failure_source"],
            item["judge_failure_subtype"],
            item["judge_reference_suspect"],
            item["judged_on"],
        ) == (source, subtype, seed_flag or waved, "2026-09-29")
        assert ("judge_reference_suspect_source" in item) is (waved and not seed_flag)
        assert restated["judge_rejudged_on"] == day
        if "judged_on_utc" in restated:
            assert restated["judged_on_utc"] == day
        if "adjudicated_verdict" in restated:
            assert list(restated)[-1] == "adjudicated_verdict"
        verify_adjudications_keep_judge_verdicts([restated], stage)
        # Idempotent.
        (again,), none = _run([restated], (stage, seed), wave)
        assert again == restated and none == []
        # Order-free: restating the original once against this verdict agrees,
        # up to the wording of a source an intermediate verdict cleared.
        (once,), _ = _run([original], (stage, seed), wave)
        if dropped and "judge_reference_suspect_source" in once:
            once["judge_reference_suspect_source"] = restate.FLAG_SOURCE_EARLIER_RUN
        assert once == restated and list(once) == list(restated)
        dropped = dropped or new_flag
    record = root / "record.json"
    record.write_text(json.dumps({"adjudications": [original, restated]}))
    with pytest.raises(Exception, match="duplicate"):
        load_adjudications(record)
    record.write_text(json.dumps({"adjudications": [restated]}))
    (loaded,) = load_adjudications(record)
    assert excluded_case_keys([loaded]) == excluded_case_keys([original])
