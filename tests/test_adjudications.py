"""Developer adjudications resolve non-final judge verdicts auditably."""

import json
import subprocess
from collections import Counter
from functools import cache
from pathlib import Path

import pandas as pd
import pytest

from policybench.adjudications import (
    AdjudicationError,
    apply_adjudications,
    load_adjudications,
    unresolved_suspect_cases,
    verify_adjudications_applied,
)

ROOT = Path(__file__).resolve().parents[1]
RUN_LABEL = "us_full_run_20260612_policyengine_4_16_1_populace"
ANNOTATIONS = ROOT / "annotations" / RUN_LABEL
# The merge of #182, which froze release dashboard-data-20260929. Release
# 20260930 (GPT-6.1 Sol) restated the judge fields of the decisions on the
# cases GPT-6.1 Sol re-opened; everything else in the record is 20260929's.
RELEASE_20260929_COMMIT = "d616e67c33b6f80dabf5cb7329f069f9a1de069d"
EVIDENCE_20260930 = ROOT / "docs/gpt61sol/judge_verdicts_20260930.json"
# The squash merge of #187, which froze release dashboard-data-20260930. Release
# 20261006 (Max's rulings of 2026-10-05) builds on it and adds the 2026-10-05
# wave's decisions; every earlier entry is 20260930's.
RELEASE_20260930_COMMIT = "8b4c0ca146bb6f66deba6ce24009d49d70d92df2"
# The squash merge of #202, which froze release dashboard-data-20261006.
# Release 20261010 (Claude Haiku 5.5) builds on it: it restates the decisions
# on the cases Claude Haiku 5.5 re-opened (docs/haiku55/judge_verdicts_20261010.json),
# drops the decisions on records its engine upgrade regenerated, and adds the
# 2026-10-06 and 2026-10-09 waves' decisions.
RELEASE_20261006_COMMIT = "9ce4ade8382962a9134860c23f56d92509b5e57f"
(EVIDENCE_20261010,) = sorted((ROOT / "docs/haiku55").glob("judge_verdicts_*.json"))
# The UTC day of the frozen references' last engine upgrade: the wave of the
# decisions on the outputs it newly excludes (2026-10-09 in the rehearsal).
UPGRADE_WAVE = [
    revision["date"]
    for revision in json.loads(
        (
            ROOT
            / "paper/snapshot/20260501/runs"
            / "us_full_run_20260612_policyengine_4_16_1_populace"
            / "reference_outputs.csv.meta.json"
        ).read_text()
    )["revisions"]
    if revision["kind"] == "engine_upgrade"
][-1]


@cache
def _record_text(commit: str) -> str:
    """The adjudication record as a release commit holds it."""
    shown = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "show",
            f"{commit}:annotations/{RUN_LABEL}/us_adjudications.json",
        ],
        capture_output=True,
        text=True,
    )
    assert shown.returncode == 0, (
        f"the record at {commit[:12]} needs git history; fetch full history. "
        + shown.stderr
    )
    return shown.stdout


def _entries_at(commit: str, tmp_path: Path) -> list[dict]:
    """A release's adjudication entries, as its commit holds them."""
    path = tmp_path / f"us_adjudications_{commit[:12]}.json"
    path.write_text(_record_text(commit))
    return load_adjudications(path)


def _entries_20260929(tmp_path: Path) -> list[dict]:
    """Release 20260929's adjudication entries, as its commit holds them."""
    return _entries_at(RELEASE_20260929_COMMIT, tmp_path)


def _entries_20260930(tmp_path: Path) -> list[dict]:
    """Release 20260930's adjudication entries, as its commit holds them."""
    return _entries_at(RELEASE_20260930_COMMIT, tmp_path)


def _entries_20261006(tmp_path: Path) -> list[dict]:
    """Release 20261006's adjudication entries, as its commit holds them."""
    return _entries_at(RELEASE_20261006_COMMIT, tmp_path)


def _entry(**overrides: object) -> dict:
    entry = {
        "country": "us",
        "scenario_id": "scenario_001",
        "variable": "ssi",
        "judge_model": "claude-opus-5",
        "judge_failure_source": "prompt_ambiguity",
        "judge_failure_subtype": "age_disability",
        "adjudicated_failure_source": "llm_error",
        "adjudicated_failure_subtype": "age_disability",
        "adjudicated_on": "2026-09-05",
        "adjudicator": "developer",
        "reasoning": "The prompt fixes unlisted facts to false.",
    }
    entry.update(overrides)
    return entry


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = pd.DataFrame(
        [
            ("us", "scenario_001", "ssi", "m1", "prompt_ambiguity", "age_disability"),
            ("us", "scenario_001", "ssi", "m2", "prompt_ambiguity", "age_disability"),
            (
                "us",
                "scenario_001",
                "ssi",
                "m3",
                "parse_contract_failure",
                "missing_output",
            ),
            ("us", "scenario_002", "snap", "m1", "llm_error", "thresholds_rates"),
        ],
        columns=[
            "country",
            "scenario_id",
            "variable",
            "model",
            "failure_source",
            "failure_subtype",
        ],
    )
    rows["reference_suspect"] = False
    rows["annotation"] = "diagnosis"
    cases = pd.DataFrame(
        [
            (
                "us",
                "scenario_001",
                "ssi",
                3,
                "prompt_ambiguity",
                "age_disability",
                "note one.",
            ),
            (
                "us",
                "scenario_002",
                "snap",
                1,
                "llm_error",
                "thresholds_rates",
                "note two.",
            ),
        ],
        columns=[
            "country",
            "scenario_id",
            "variable",
            "wrong_model_count",
            "case_failure_sources",
            "case_failure_subtypes",
            "case_annotation",
        ],
    )
    return rows, cases


def test_apply_rewrites_only_the_judged_class_and_records_the_adjudication():
    rows, cases = _frames()
    out_rows, out_cases, report = apply_adjudications(rows, cases, [_entry()])

    case_rows = out_rows[out_rows["scenario_id"] == "scenario_001"]
    assert case_rows["failure_source"].tolist() == [
        "llm_error",
        "llm_error",
        "parse_contract_failure",
    ]
    assert out_rows.loc[3, "failure_source"] == "llm_error"
    note = out_cases.loc[0]
    assert note["case_failure_sources"] == "llm_error"
    assert "Developer adjudication (2026-09-05)" in note["case_annotation"]
    assert "returned prompt_ambiguity" in note["case_annotation"]
    assert out_cases.loc[1, "case_annotation"] == "note two."
    assert report == [
        {
            "case": ["us", "scenario_001", "ssi"],
            "rows_rewritten": 2,
            "from": "prompt_ambiguity",
            "to": "llm_error",
        }
    ]
    # The originals are untouched and a second application changes nothing.
    assert rows.loc[0, "failure_source"] == "prompt_ambiguity"
    again_rows, again_cases, _ = apply_adjudications(out_rows, out_cases, [_entry()])
    pd.testing.assert_frame_equal(again_rows, out_rows)
    pd.testing.assert_frame_equal(again_cases, out_cases)


def test_verify_rejects_unapplied_or_missing_cases():
    rows, cases = _frames()
    with pytest.raises(AdjudicationError, match="still carry"):
        verify_adjudications_applied(rows, cases, [_entry()])
    out_rows, out_cases, _ = apply_adjudications(rows, cases, [_entry()])
    verify_adjudications_applied(out_rows, out_cases, [_entry()])
    with pytest.raises(AdjudicationError, match="unknown case"):
        apply_adjudications(rows, cases, [_entry(scenario_id="scenario_999")])


def test_load_validates_the_record(tmp_path: Path):
    path = tmp_path / "us_adjudications.json"
    assert load_adjudications(path) == []
    path.write_text(json.dumps({"adjudications": [_entry()]}))
    assert len(load_adjudications(path)) == 1
    path.write_text(
        json.dumps(
            {"adjudications": [_entry(adjudicated_failure_source="needs_review")]}
        )
    )
    with pytest.raises(AdjudicationError, match="must be final"):
        load_adjudications(path)
    path.write_text(
        json.dumps(
            {"adjudications": [_entry(adjudicated_failure_source="prompt_ambiguity")]}
        )
    )
    with pytest.raises(AdjudicationError, match="excluded_from_scoring"):
        load_adjudications(path)
    path.write_text(
        json.dumps(
            {
                "adjudications": [
                    _entry(
                        adjudicated_failure_source="prompt_ambiguity",
                        excluded_from_scoring=True,
                    )
                ]
            }
        )
    )
    assert load_adjudications(path)[0]["excluded_from_scoring"] is True
    path.write_text(json.dumps({"adjudications": [_entry(excluded_from_scoring=True)]}))
    with pytest.raises(AdjudicationError, match="only valid with"):
        load_adjudications(path)
    path.write_text(json.dumps({"adjudications": [_entry(), _entry()]}))
    with pytest.raises(AdjudicationError, match="duplicate"):
        load_adjudications(path)
    path.write_text(json.dumps({"adjudications": [_entry(reasoning="")]}))
    with pytest.raises(AdjudicationError, match="missing"):
        load_adjudications(path)


def test_committed_record_is_applied_to_the_frozen_annotations():
    entries = load_adjudications(ANNOTATIONS / "us_adjudications.json")
    # 69 through release 20260930; the 2026-10-05 wave added one
    # prompt_ambiguity decision for each of the eight outputs the 2026-10-05
    # audits excluded (77 in release 20261006). Release 20261010 dropped the
    # decisions on the three records its engine upgrade regenerated (039 state,
    # 064 federal and state income tax), decided the six ruled records the
    # upgrade kept (2026-10-06: four unlisted-input scope cells, and
    # Louisiana's two outputs as later law, scenario_051's restated in place
    # from a regenerated-reference decision) and the two Indiana county
    # outputs the upgrade newly excludes (2026-10-09).
    assert len(entries) == 81
    assert Counter(e["adjudicated_failure_source"] for e in entries) == Counter(
        {
            "reference_engine_defect": 25,
            "prompt_ambiguity": 42,
            "llm_error": 12,
            "reference_later_law": 2,
        }
    )
    assert Counter(
        (e["adjudicated_on"], e["adjudicated_failure_source"], e["reference_verdict"])
        for e in entries
        if e["adjudicated_on"] in ("2026-10-06", UPGRADE_WAVE)
    ) == Counter(
        {
            ("2026-10-06", "prompt_ambiguity", "unlisted_input"): 4,
            ("2026-10-06", "reference_later_law", "later_law"): 2,
            (UPGRADE_WAVE, "prompt_ambiguity", "unlisted_input"): 2,
        }
    )
    new_wave = [e for e in entries if e["adjudicated_on"] == "2026-10-05"]
    assert len(new_wave) == 8
    assert {
        (
            e["adjudicated_failure_source"],
            e["reference_verdict"],
            e["excluded_from_scoring"],
        )
        for e in new_wave
    } == {("prompt_ambiguity", "unlisted_input", True)}
    # Every excluded output has its adjudication. Ten llm_error entries are
    # the references a flag questioned and the adjudication affirmed (five) or
    # replaced with a regenerated reference (five; scenario_051's became a
    # later-law exclusion on 2026-10-06); the other two resolve rows the
    # September 29 judge called later law (scenario_007 federal income tax
    # and scenario_008 New Jersey refundable credits), whose law predates the
    # reference freeze.
    assert sum(bool(e.get("excluded_from_scoring")) for e in entries) == 69
    assert Counter(
        e.get("reference_verdict")
        for e in entries
        if e["adjudicated_failure_source"] == "llm_error"
    ) == Counter({"affirmed": 5, "regenerated": 5, None: 2})
    assert {
        (e["scenario_id"], e["variable"])
        for e in entries
        if e["adjudicated_failure_source"] == "llm_error"
        and e.get("reference_verdict") is None
    } == {
        ("scenario_007", "federal_income_tax_before_refundable_credits"),
        ("scenario_008", "state_refundable_credits"),
    }
    keys = {(e["scenario_id"], e["variable"]) for e in entries}
    assert ("scenario_064", "ssi") in keys and (
        "scenario_074",
        "head_medicare_eligible",
    ) in keys
    opus = next(
        e
        for e in entries
        if (e["scenario_id"], e["variable"]) == ("scenario_064", "ssi")
    )
    # GPT-6.1 Sol re-opened 064 SSI; its 2026-09-30 verdict calls it an LLM
    # error, and the verdict release 20260929 recorded (prompt ambiguity) is
    # the last judge_previous item. The decision itself is unchanged.
    assert opus["judge_failure_source"] == "llm_error"
    assert opus["judge_rejudged_on"] == "2026-09-30"
    assert opus["judge_previous"][-1]["judge_failure_source"] == "prompt_ambiguity"
    rejudged = next(
        e
        for e in entries
        if (e["scenario_id"], e["variable"]) == ("scenario_067", "ssi")
    )
    assert rejudged["judge_model"] == "claude-opus-5-5"
    assert rejudged["reference_verdict"] == "unlisted_input"
    rows = pd.read_csv(ANNOTATIONS / "us_audit_row_annotations.csv")
    cases = pd.read_csv(ANNOTATIONS / "us_case_notes.csv")
    verify_adjudications_applied(rows, cases, entries)
    ambiguous = rows[rows["failure_source"] == "prompt_ambiguity"]
    assert set(zip(ambiguous["scenario_id"], ambiguous["variable"])) <= keys
    manifest = json.loads((ROOT / "paper/snapshot/20260501/manifest.json").read_text())
    block = manifest["audit_annotation_artifacts"]["developer_adjudications"]
    assert block["cases"] == 81
    # The judge's own class for each case (its verdict.json), not the
    # adjudicated one; the freezer refuses a record that differs from it.
    # After the 2026-09-30 restatements (release 20260929 had llm_error 50,
    # prompt_ambiguity 2, reference_data_issue_fixed 1 and
    # reference_model_issue_fixed 16), release 20260930 had llm_error 59; the
    # judge called each of the 2026-10-05 wave's eight cases an LLM error.
    # Release 20261010's Opus 5.5 verdicts on the cases Claude Haiku 5.5
    # re-opened give its counts.
    assert block["by_judge_verdict"] == {
        "llm_error": 67,
        "prompt_ambiguity": 6,
        "reference_data_issue_fixed": 1,
        "reference_engine_defect": 1,
        "reference_later_law": 1,
        "reference_model_issue_fixed": 5,
    }
    assert block["by_judge_verdict"] == dict(
        Counter(e["judge_failure_source"] for e in entries)
    )
    # unlisted_input was 20 in release 20260930 and 28 in release 20261006.
    assert block["by_reference_verdict"] == {
        "affirmed": 5,
        "engine_defect": 25,
        "later_law": 2,
        "regenerated": 5,
        "unlisted_input": 34,
    }
    assert block["by_reference_verdict"] == dict(
        Counter(e["reference_verdict"] for e in entries if e.get("reference_verdict"))
    )
    # The judge flagged none of the 2026-10-05 wave's references.
    assert block["judge_flagged_by_reference_verdict"] == {
        "affirmed": 5,
        "engine_defect": 18,
        "later_law": 1,
        "regenerated": 5,
        "unlisted_input": 8,
    }
    assert not any(e["judge_reference_suspect"] for e in new_wave)
    assert manifest["audit_annotation_artifacts"]["files"]["us_adjudications.json"]
    assert manifest["reference_exclusions"]["outputs"] == 69


def test_verify_requires_agreement_with_the_complete_record():
    rows, cases = _frames()
    out_rows, out_cases, _ = apply_adjudications(rows, cases, [_entry()])
    verify_adjudications_applied(out_rows, out_cases, [_entry()])

    # A revised subtype fails until the revision is re-applied.
    revised = _entry(adjudicated_failure_subtype="thresholds_rates")
    with pytest.raises(AdjudicationError, match="subtype other than"):
        verify_adjudications_applied(out_rows, out_cases, [revised])
    re_rows, re_cases, _ = apply_adjudications(out_rows, out_cases, [revised])
    verify_adjudications_applied(re_rows, re_cases, [revised])
    assert re_cases.loc[0, "case_annotation"].count("Developer adjudication") == 1

    # Revised reasoning replaces the sentence rather than accumulating.
    reworded = _entry(reasoning="Different reasoning.")
    with pytest.raises(AdjudicationError, match="does not carry"):
        verify_adjudications_applied(out_rows, out_cases, [reworded])
    rw_rows, rw_cases, _ = apply_adjudications(out_rows, out_cases, [reworded])
    verify_adjudications_applied(rw_rows, rw_cases, [reworded])
    note = rw_cases.loc[0, "case_annotation"]
    assert "Different reasoning." in note
    assert "The prompt fixes unlisted facts to false." not in note

    # A case note edited to disagree with its rows fails closed.
    bad_cases = out_cases.copy()
    bad_cases.loc[0, "case_failure_subtypes"] = "thresholds_rates"
    with pytest.raises(AdjudicationError, match="case note"):
        verify_adjudications_applied(out_rows, bad_cases, [_entry()])
    bad_rows = out_rows.copy()
    bad_rows.loc[1, "failure_subtype"] = "thresholds_rates"
    with pytest.raises(AdjudicationError, match="subtype other than"):
        verify_adjudications_applied(bad_rows, out_cases, [_entry()])


def _suspect_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, cases = _frames()
    rows.loc[rows["scenario_id"] == "scenario_001", "reference_suspect"] = True
    rows.loc[rows["scenario_id"] == "scenario_001", "failure_source"] = (
        "reference_model_issue_fixed"
    )
    cases["reference_suspect"] = [True, False]
    cases.loc[0, "case_failure_sources"] = "reference_model_issue_fixed"
    return rows, cases


def _verdict_entry(verdict: str, **overrides: object) -> dict:
    source = {
        "affirmed": "llm_error",
        "regenerated": "llm_error",
        "engine_defect": "reference_engine_defect",
        "unlisted_input": "prompt_ambiguity",
        "later_law": "reference_later_law",
    }[verdict]
    entry = _entry(
        judge_failure_source="reference_model_issue_fixed",
        adjudicated_failure_source=source,
        reference_verdict=verdict,
        reference_basis="42 U.S.C. 1382c(a)(3)(A)",
    )
    if verdict not in ("affirmed", "regenerated"):
        entry["excluded_from_scoring"] = True
    entry.update(overrides)
    return entry


@pytest.mark.parametrize(
    "verdict",
    ["affirmed", "regenerated", "engine_defect", "unlisted_input", "later_law"],
)
def test_reference_verdict_clears_the_suspect_flag_and_is_recorded(tmp_path, verdict):
    rows, cases = _suspect_frames()
    entry = _verdict_entry(verdict)
    path = tmp_path / "adj.json"
    path.write_text(json.dumps({"adjudications": [entry]}))
    assert load_adjudications(path)[0]["reference_verdict"] == verdict
    assert unresolved_suspect_cases(cases, [entry | {"reference_verdict": None}]) == [
        ("us", "scenario_001", "ssi")
    ]
    out_rows, out_cases, _ = apply_adjudications(rows, cases, [entry])
    assert not out_rows["reference_suspect"].any()
    assert not out_cases["reference_suspect"].any()
    assert "42 U.S.C. 1382c(a)(3)(A)" in out_cases.loc[0, "case_annotation"]
    verify_adjudications_applied(out_rows, out_cases, [entry])
    assert unresolved_suspect_cases(out_cases, [entry]) == []


def test_reference_verdict_must_match_class_and_scoring(tmp_path):
    path = tmp_path / "adj.json"
    bad = [
        (_verdict_entry("affirmed", excluded_from_scoring=True), "only valid with"),
        (
            _verdict_entry(
                "engine_defect", adjudicated_failure_source="prompt_ambiguity"
            ),
            "requires adjudicated_failure_source",
        ),
        (_verdict_entry("unlisted_input", reference_basis=""), "reference_basis"),
        (_verdict_entry("engine_defect", reference_verdict="maybe"), "unknown"),
        (
            _verdict_entry("engine_defect", reference_verdict=None),
            "requires a reference_verdict",
        ),
    ]
    for entry, message in bad:
        path.write_text(json.dumps({"adjudications": [entry]}))
        with pytest.raises(AdjudicationError, match=message):
            load_adjudications(path)


def test_verification_fails_while_a_verdict_leaves_the_flag_set():
    rows, cases = _suspect_frames()
    entry = _verdict_entry("affirmed")
    out_rows, out_cases, _ = apply_adjudications(rows, cases, [entry])
    out_rows.loc[0, "reference_suspect"] = True
    with pytest.raises(AdjudicationError, match="still carry reference_suspect"):
        verify_adjudications_applied(out_rows, out_cases, [entry])


def test_judge_dates_follow_each_judge_release_and_each_other():
    """A recorded judge date falls on or after its judge model's release, and a
    re-judged entry's current verdict is dated on or after the verdict it
    replaced (its judge_previous). Every current date is a day the manifest's
    judge provenance records for that judge. A judge_previous item without a
    matching earlier verdict would carry adjudicated_on instead of a judge
    date."""
    from policybench.config import MODELS
    from policybench.paper_results import MODEL_RELEASE_DATES

    board_key = {provider: board for board, provider in MODELS.items()}

    def released(judge: str) -> str:
        return MODEL_RELEASE_DATES[board_key[judge]]

    entries = load_adjudications(ANNOTATIONS / "us_adjudications.json")
    manifest = json.loads((ROOT / "paper/snapshot/20260501/manifest.json").read_text())
    provenance = manifest["audit_annotation_artifacts"]["judge_provenance"]["by_judge"]
    rejudged = 0
    for entry in entries:
        key = (entry["scenario_id"], entry["variable"])
        if "judged_on_utc" in entry and "judge_rejudged_on" in entry:
            assert entry["judged_on_utc"] == entry["judge_rejudged_on"], key
        current = entry.get("judge_rejudged_on") or entry.get("judged_on_utc")
        if current is not None:
            assert current >= released(entry["judge_model"]), key
            assert current in provenance[entry["judge_model"]]["judged_on_utc"], key
        previous = entry.get("judge_previous", [])
        if previous:
            rejudged += 1
            assert entry.get("judge_rejudged_on"), key
        for item in previous:
            assert ("judged_on" in item) != ("adjudicated_on" in item), key
            if "judged_on" in item:
                assert item["judged_on"] >= released(item["judge_model"]), key
                assert item["judged_on"] <= entry["judge_rejudged_on"], key
    # 54 in release 20260929. The 2026-09-30 restatements gave four more
    # entries their first judge_previous item: 008 state refundable credits,
    # 078 and 117 federal income tax, and 100 federal refundable credits.
    # Release 20261010's restatements of the cases Claude Haiku 5.5 re-opened
    # gave nine more theirs (58 in release 20261006).
    assert rejudged == 67


def _write_case(root: Path, case: str, verdict: dict, meta: dict) -> None:
    import hashlib

    directory = root / case
    directory.mkdir(parents=True)
    blob = json.dumps(verdict).encode()
    (directory / "verdict.json").write_bytes(blob)
    meta = {**meta, "verdict_sha256": hashlib.sha256(blob).hexdigest()}
    (directory / "verdict.meta.json").write_text(json.dumps(meta))


def test_judge_dates_come_from_bound_verdict_sidecars(tmp_path):
    """scripts/date_adds0928_judge_verdicts.py dates the current verdict and a
    matching previous verdict from their sidecars, and renames a previous date
    it cannot bind to a verdict adjudicated_on."""
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from date_adds0928_judge_verdicts import date_entries

    current, previous = tmp_path / "current", tmp_path / "previous"
    classes = {"case_failure_source": "llm_error", "case_failure_subtype": "x"}
    opus55 = {"judge_model_requested": "claude-opus-5-5"}
    for n in ("1", "2"):
        _write_case(
            current,
            f"us__scenario_00{n}__snap",
            classes,
            {**opus55, "judged_at_utc": "2026-09-29T01:49:57+00:00"},
        )
    _write_case(
        previous,
        "us__scenario_001__snap",
        classes,
        {**opus55, "judged_at_utc": "2026-09-23T00:27:09+00:00"},
    )
    # The second case's previous verdict has another class than the record.
    _write_case(
        previous,
        "us__scenario_002__snap",
        {**classes, "case_failure_subtype": "y"},
        {**opus55, "judged_at_utc": "2026-09-23T00:27:09+00:00"},
    )

    def entry(n: str) -> dict:
        return {
            "country": "us",
            "scenario_id": f"scenario_00{n}",
            "variable": "snap",
            "judge_model": "claude-opus-5-5",
            "judge_failure_source": "llm_error",
            "judge_failure_subtype": "x",
            "judged_on_utc": "2026-09-23",
            "judge_rejudged_on": "2026-09-28",
            "judge_previous": [
                {
                    "judge_model": "claude-opus-5-5",
                    "judge_failure_source": "llm_error",
                    "judge_failure_subtype": "x",
                    "judged_on": "2026-09-05",
                }
            ],
        }

    entries = [entry("1"), entry("2")]
    changes = date_entries(entries, current, previous)
    for record in entries:
        assert record["judge_rejudged_on"] == record["judged_on_utc"] == "2026-09-29"
    assert entries[0]["judge_previous"][0]["judged_on"] == "2026-09-23"
    assert entries[1]["judge_previous"][0] == {
        "judge_model": "claude-opus-5-5",
        "judge_failure_source": "llm_error",
        "judge_failure_subtype": "x",
        "adjudicated_on": "2026-09-05",
    }
    assert len(changes) == 6
    # Idempotent: a second pass changes nothing.
    assert date_entries(entries, current, previous) == []


# --- The verdicts the record's dates and flags name ---------------------------

VERIFICATION = ROOT / "reference_audit" / "2026-09-28" / "verification"


def _judge_evidence() -> dict:
    """The verdicts scripts/date_adds0928_judge_verdicts.py bound the record's
    dates to, committed beside the upgrade (verification/judge_verdicts.json),
    as each later release brought it up to date (release 20261006's driver,
    scripts/date_haiku55_judge_verdicts.py)."""
    return json.loads((VERIFICATION / "judge_verdicts.json").read_text())


@cache
def _judge_evidence_at(commit: str) -> dict:
    """verification/judge_verdicts.json as a release commit holds it."""
    shown = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "show",
            f"{commit}:reference_audit/2026-09-28/verification/judge_verdicts.json",
        ],
        capture_output=True,
        text=True,
    )
    assert shown.returncode == 0, (
        f"the evidence at {commit[:12]} needs git history; fetch full history. "
        + shown.stderr
    )
    return json.loads(shown.stdout)


def _case(entry: dict) -> str:
    return f"{entry['country']}__{entry['scenario_id']}__{entry['variable']}"


def test_each_judge_flag_is_the_flag_of_the_verdict_its_date_names(tmp_path):
    """A recorded verdict carries its bound verdict's judge, classes, UTC day
    and reference-suspect flag. A flag the dated verdict does not raise is
    kept only with judge_reference_suspect_source, and only for a case an
    earlier run of the 2026-09-22 wave flagged (flagged_sept22_wave.json).

    The evidence describes release 20260929's record, so this reads that
    record from its commit, and the evidence as release 20261006 committed
    it (a later wave that restates a decision in place gives its case new
    evidence); test_each_restatement_names_its_20260930_verdict checks what
    release 20260930 changed."""
    evidence = _judge_evidence_at(RELEASE_20261006_COMMIT)["cases"]
    wave_flags = set(
        json.loads((VERIFICATION / "flagged_sept22_wave.json").read_text())
    )
    entries = _entries_20260929(tmp_path)
    explained = 0
    for entry in entries:
        case, key = _case(entry), f"{entry['scenario_id']}:{entry['variable']}"
        current = evidence[case]["current"]
        assert (
            current["judge_model"],
            current["case_failure_source"],
            current["case_failure_subtype"],
        ) == (
            entry["judge_model"],
            entry["judge_failure_source"],
            entry["judge_failure_subtype"],
        ), case
        day = current["judged_at_utc"][:10]
        for field in ("judged_on_utc", "judge_rejudged_on"):
            if field in entry:
                assert entry[field] == day, case
        assert "judged_on_utc" in entry or "judge_rejudged_on" in entry, case
        flag = bool(entry.get("judge_reference_suspect"))
        if flag != current["reference_suspect"]:
            assert flag and entry.get("judge_reference_suspect_source"), case
            assert key in wave_flags, case
            explained += 1
        else:
            assert "judge_reference_suspect_source" not in entry, case
        for item in entry.get("judge_previous", []):
            if "adjudicated_on" in item:
                continue
            previous = evidence[case]["previous"]
            assert (
                previous["judge_model"],
                previous["case_failure_source"],
                previous["case_failure_subtype"],
                previous["judged_at_utc"][:10],
            ) == (
                item["judge_model"],
                item["judge_failure_source"],
                item["judge_failure_subtype"],
                item["judged_on"],
            ), case
            item_flag = bool(item.get("judge_reference_suspect"))
            if item_flag != previous["reference_suspect"]:
                assert item_flag and item.get("judge_reference_suspect_source"), case
                assert key in wave_flags, case
                explained += 1
            else:
                assert "judge_reference_suspect_source" not in item, case
    # Flags kept from an earlier judge run: sixteen at the top level, and the
    # eight judge_previous items whose 2026-09-23 verdict does not flag the
    # reference (005 state, 028, 030, 042 federal, 051, 064 federal, 109, 112).
    assert explained == 24


def test_each_restatement_names_its_20260930_verdict(tmp_path):
    """Release 20260930 changed the record only on decisions about cases
    GPT-6.1 Sol re-opened, and each such entry names that case's 2026-09-30
    verdict (docs/gpt61sol/judge_verdicts_20260930.json): its judge, classes
    and UTC day. Its judge_previous is release 20260929's, with 20260929's own
    verdict appended. A flag the new verdict does not raise is kept as release
    20260929 kept flags: with judge_reference_suspect_source, for a case an
    earlier 2026-09-22 run flagged.

    This reads release 20260930's record from its commit, and then checks that
    release 20261006's record keeps every one of those entries unchanged and
    adds only the 2026-10-05 wave's decisions."""
    evidence = json.loads(EVIDENCE_20260930.read_text())
    assert evidence["base_commit"] == RELEASE_20260929_COMMIT
    restated = evidence["cases"]
    wave_flags = set(
        json.loads((VERIFICATION / "flagged_sept22_wave.json").read_text())
    )
    base = {_case(e): e for e in _entries_20260929(tmp_path)}
    entries = _entries_20260930(tmp_path)
    assert {_case(e) for e in entries} == set(base)
    kept_flags = 0
    for entry in entries:
        case = _case(entry)
        before = base[case]
        if case not in restated:
            assert entry == before, case
            continue
        current = restated[case]
        assert (
            current["judge_model"],
            current["case_failure_source"],
            current["case_failure_subtype"],
            current["judged_at_utc"][:10],
        ) == (
            entry["judge_model"],
            entry["judge_failure_source"],
            entry["judge_failure_subtype"],
            entry["judge_rejudged_on"],
        ), case
        decision = {
            k: v
            for k, v in entry.items()
            if not k.startswith("judge") and k != "reasoning"
        }
        assert decision == {
            k: v
            for k, v in before.items()
            if not k.startswith("judge") and k != "reasoning"
        }, case
        history = entry["judge_previous"]
        assert history[:-1] == before.get("judge_previous", []), case
        assert (
            history[-1]["judge_model"],
            history[-1]["judge_failure_source"],
            history[-1]["judge_failure_subtype"],
            history[-1]["judged_on"],
        ) == (
            before["judge_model"],
            before["judge_failure_source"],
            before["judge_failure_subtype"],
            before.get("judge_rejudged_on") or before.get("judged_on_utc"),
        ), case
        flag = bool(entry.get("judge_reference_suspect"))
        if flag != current["reference_suspect"]:
            assert flag and entry.get("judge_reference_suspect_source"), case
            assert f"{entry['scenario_id']}:{entry['variable']}" in wave_flags, case
            kept_flags += 1
        else:
            assert "judge_reference_suspect_source" not in entry, case
    assert len(restated) == 54
    # Flags raised by an earlier 2026-09-22 run that the 2026-09-30 verdict
    # does not raise.
    assert kept_flags == 22
    # Release 20261006 leaves each of release 20260930's entries as it was and
    # appends the 2026-10-05 wave's eight decisions.
    committed = _entries_20261006(tmp_path)
    assert committed[: len(entries)] == entries
    added = committed[len(entries) :]
    assert len(added) == 8
    assert {e["adjudicated_on"] for e in added} == {"2026-10-05"}
    assert not {_case(e) for e in added} & set(base)


def test_each_decision_records_the_verdict_it_reviewed_by_its_wave_release():
    """adjudicated_on names the audit wave (date_conventions). A committed
    wave's decisions were written up to the day its release was committed;
    this release's waves (2026-10-06 and 2026-10-09), whose release has no
    commit yet, record the day their adjudications were written. So the
    verdict each decision reviewed -- adjudicated_verdict where a later wave
    replaced it, otherwise the earliest verdict the entry keeps -- is dated on
    or before that day, and a committed wave's decision reviewed the verdict
    its release published.

    Intended exceptions to "on or before adjudicated_on": 42 decisions of the
    2026-09-22 wave reviewed verdicts its own judge runs finished on
    2026-09-23 UTC, before its release was committed that day (46 in release
    20261006, which this release drops three of with the records its engine
    upgrade regenerated, and moves scenario_051's to the 2026-10-06 wave); and
    five of the 2026-10-06 wave's six decisions reviewed verdicts this
    release's judge runs finished on 2026-10-08 and 2026-10-09 UTC, before
    they were written (scenario_051's, restated in place, reviewed an earlier
    verdict it keeps)."""
    record = json.loads((ANNOTATIONS / "us_adjudications.json").read_text())
    evidence = _judge_evidence()
    released, uncommitted = {}, []
    for wave, release in evidence["wave_releases"].items():
        if release["commit"] is None:
            # Not committed yet: the day the adjudications were written, and
            # no commit or pull request until the next release fills them.
            assert "committed_on" not in release and release["pull_request"] is None
            released[wave] = release["adjudications_written_on"]
            uncommitted.append(wave)
        else:
            assert "adjudications_written_on" not in release
            assert release["pull_request"] is not None, wave
            released[wave] = release["committed_on"]
        # A wave's decisions are written on or after the wave's own date.
        assert wave <= released[wave], wave
    waves = list(released)
    assert waves == sorted(waves)
    # Only this release's own waves, the latest two, have no commit.
    assert uncommitted == waves[-2:] == ["2026-10-06", UPGRADE_WAVE]
    committed = waves[:-2]
    assert len(committed) == 4
    # The record's decisions come from exactly these waves.
    assert {e["adjudicated_on"] for e in record["adjudications"]} == set(waves)
    # The record's date conventions name the waves and state the same days.
    assert (
        "adjudicated_on names the audit wave that made the decision "
        f"({', '.join(waves[:-1])} or {waves[-1]})."
    ) in record["date_conventions"]
    # The 2026-09-29 wave's reference sweep began on the wave's own date, on
    # or before the day its release was committed.
    timing = json.loads((VERIFICATION / "sweep_timing.json").read_text())
    sweep_day = timing["reference_sweep"]["first_output_at_utc"][:10]
    assert sweep_day == "2026-09-29" <= released["2026-09-29"]
    # Release 20260929 wrote this sentence for the first three waves.
    committed_days = (
        f"The {committed[0]}, {committed[1]} and {committed[2]} waves' decisions "
        "were written up to the day each wave's release was committed "
        f"({released[committed[0]]}, {released[committed[1]]} and "
        f"{released[committed[2]]}); the 2026-09-29 wave's reference sweep "
        f"began on {sweep_day} UTC, before its decisions were written. "
    )
    assert record["date_conventions"].count(committed_days) == 1
    # One sentence per later wave follows, in order, giving the day its
    # decisions were written: for release 20261006's wave, on or before the
    # day that release was committed; for this release's waves, the day the
    # evidence records. How each describes Max's rulings is pinned by its
    # release's driver tests, not here, so the tests cannot require
    # different texts.
    rest = record["date_conventions"].split(committed_days, 1)[1]
    for wave in waves[3:]:
        sentence, rest = rest.split(". ", 1)
        assert sentence.startswith(f"The {wave} wave's decisions"), sentence
        written = sentence.rsplit(" were written on ", 1)[1].removesuffix(" UTC")
        if wave in uncommitted:
            assert written == released[wave], sentence
        else:
            assert wave <= written <= released[wave], sentence
    later_than_wave = later_than_own_wave = 0
    for entry in record["adjudications"]:
        case, wave = _case(entry), entry["adjudicated_on"]
        kept = [
            (
                entry["judge_model"],
                entry["judge_failure_source"],
                entry["judge_failure_subtype"],
                entry.get("judge_rejudged_on") or entry["judged_on_utc"],
            )
        ] + [
            (
                item["judge_model"],
                item["judge_failure_source"],
                item["judge_failure_subtype"],
                item["judged_on"],
            )
            for item in entry.get("judge_previous", [])
            if "judged_on" in item
        ]
        reviewed = entry.get("adjudicated_verdict")
        if reviewed is None:
            day = min(verdict[3] for verdict in kept)
        else:
            day = reviewed["judged_on"]
        assert day <= released[wave], case
        if day > wave and wave in uncommitted:
            # This release's judge runs (2026-10-08 and 2026-10-09 UTC) re-judged
            # the cases its 2026-10-06 rulings decide, before those decisions
            # were written (checked above).
            assert wave == "2026-10-06" and day in ("2026-10-08", "2026-10-09", "2026-10-10"), case
            later_than_own_wave += 1
        elif day > wave:
            assert (wave, day) == ("2026-09-22", "2026-09-23"), case
            later_than_wave += 1
        published = evidence["cases"][case].get("published")
        # A committed wave's release published the verdict each of its
        # decisions reviewed; this release's own waves have published nothing.
        assert (published is None) == (wave in uncommitted), case
        if published is None:
            assert reviewed is None, case
            continue
        published_verdict = (
            published["judge_model"],
            published["case_failure_source"],
            published["case_failure_subtype"],
        )
        if published_verdict in {verdict[:3] for verdict in kept}:
            assert reviewed is None, case
        else:
            assert reviewed is not None, case
            assert (
                reviewed["judge_model"],
                reviewed["judge_failure_source"],
                reviewed["judge_failure_subtype"],
                reviewed["judged_on"],
            ) == (*published_verdict, published["judged_on_utc"]), case
            assert published["release"] in reviewed["recorded_in"], case
    assert later_than_wave == 42
    assert later_than_own_wave == 5


def test_published_verdicts_in_the_evidence_match_each_wave_release():
    """Differential check of the evidence against git: the judge verdict each
    earlier wave's release published for each decision."""
    import subprocess

    evidence = _judge_evidence()
    record_path = f"annotations/{RUN_LABEL}/us_adjudications.json"
    published = {}
    for wave, release in evidence["wave_releases"].items():
        if release["commit"] is None:
            continue
        shown = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{release['commit']}:{record_path}"],
            capture_output=True,
        )
        if shown.returncode != 0:
            pytest.skip(f"git history unavailable: {release['commit'][:10]}")
        for entry in json.loads(shown.stdout)["adjudications"]:
            if entry["adjudicated_on"] == wave:
                published[_case(entry)] = (release["release"], entry)
    # A decision a later, uncommitted wave restated in place (scenario_051's
    # Louisiana output, 2026-10-06) is now that wave's: its evidence names
    # the verdict the new decision reviewed, which no release has published.
    record = {
        _case(e): e for e in load_adjudications(ANNOTATIONS / "us_adjudications.json")
    }
    uncommitted = {
        wave for wave, r in evidence["wave_releases"].items() if r["commit"] is None
    }
    restated = {
        case
        for case in published
        if case in record and record[case]["adjudicated_on"] in uncommitted
    }
    assert restated == {"us__scenario_051__state_income_tax_before_refundable_credits"}
    compared = 0
    for case, found in evidence["cases"].items():
        if "published" not in found:
            assert case not in published or case in restated, case
            continue
        release, entry = published[case]
        assert found["published"] == {
            "release": release,
            "commit": next(
                r["commit"]
                for r in evidence["wave_releases"].values()
                if r["release"] == release
            ),
            "judge_model": entry["judge_model"],
            "case_failure_source": entry["judge_failure_source"],
            "case_failure_subtype": entry["judge_failure_subtype"],
            "judged_on_utc": entry.get("judged_on_utc"),
        }, case
        compared += 1
    assert compared == len(published) - len(restated)


def _script():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import date_adds0928_judge_verdicts

    return date_adds0928_judge_verdicts


def test_a_previous_flag_its_dated_verdict_lacks_names_the_run_that_raised_it(
    tmp_path,
):
    """date_entries binds a judge_previous item to its verdict by judge and
    classes, and then compares the flag: a flag the bound verdict does not
    raise is kept with judge_reference_suspect_source when an earlier run of
    the wave flagged the case, and stops the script otherwise."""
    script = _script()
    current, previous = tmp_path / "current", tmp_path / "previous"
    classes = {"case_failure_source": "llm_error", "case_failure_subtype": "x"}
    opus55 = {"judge_model_requested": "claude-opus-5-5"}
    case = "us__scenario_001__snap"
    _write_case(
        current, case, classes, {**opus55, "judged_at_utc": "2026-09-29T01:49:57Z"}
    )
    _write_case(
        previous,
        case,
        {**classes, "reference_suspect": False},
        {**opus55, "judged_at_utc": "2026-09-23T12:00:01Z"},
    )

    def entry() -> dict:
        return {
            "country": "us",
            "scenario_id": "scenario_001",
            "variable": "snap",
            "judge_model": "claude-opus-5-5",
            "judge_failure_source": "llm_error",
            "judge_failure_subtype": "x",
            "judge_rejudged_on": "2026-09-28",
            "judge_previous": [
                {
                    "judge_model": "claude-opus-5-5",
                    "judge_failure_source": "llm_error",
                    "judge_failure_subtype": "x",
                    "judge_reference_suspect": True,
                    "judged_on": "2026-09-22",
                }
            ],
        }

    with pytest.raises(SystemExit, match="no earlier run raised it"):
        script.date_entries([entry()], current, previous)
    entries = [entry()]
    evidence: dict = {}
    script.date_entries(
        entries, current, previous, frozenset({"scenario_001:snap"}), evidence
    )
    (item,) = entries[0]["judge_previous"]
    assert item["judged_on"] == "2026-09-23"
    assert item["judge_reference_suspect"] is True
    assert item["judge_reference_suspect_source"] == script.ITEM_FLAG_SOURCE
    assert evidence[case]["previous"]["reference_suspect"] is False
    assert (
        script.date_entries(
            entries, current, previous, frozenset({"scenario_001:snap"})
        )
        == []
    )


from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

_CLASSES = st.sampled_from(["x", "y"])
_DAYS = st.sampled_from(["2026-09-05", "2026-09-22", "2026-09-23", "2026-09-29"])


@st.composite
def _judged_cases(draw):
    """Entries with a bound current verdict, and for some a previous verdict
    that may or may not carry the recorded classes and flag."""
    cases = []
    for n in range(draw(st.integers(1, 4))):
        subtype = draw(_CLASSES)
        rejudged = draw(st.booleans())
        case = {
            "n": n,
            "subtype": subtype,
            "current_day": draw(_DAYS),
            "rejudged": rejudged,
            "previous": None,
            # The top-level flag, the current verdict's flag, and whether the
            # entry names an earlier run as the flag's source.
            "top_flag": draw(st.booleans()),
            "verdict_flag": draw(st.booleans()),
            "top_source": draw(st.booleans()),
        }
        if rejudged:
            case["previous"] = {
                "exists": draw(st.booleans()),
                "subtype": draw(_CLASSES),
                "recorded_subtype": draw(_CLASSES),
                "day": draw(_DAYS),
                "flag": draw(st.booleans()),
                "recorded_flag": draw(st.booleans()),
                "stale_day": draw(_DAYS),
            }
        cases.append(case)
    return cases


@settings(max_examples=60, deadline=None)
@given(cases=_judged_cases(), in_wave=st.booleans())
def test_date_entries_properties(tmp_path_factory, cases, in_wave):
    """For any record: every judge_previous item ends with exactly one of
    judged_on and adjudicated_on; it keeps judged_on exactly when a bound
    previous verdict carries its judge and classes, and then takes that
    verdict's UTC day; a flag mismatch, at the top level or on a dated
    judge_previous item, is either explained (the recorded flag is set, the
    entry names its source, and an earlier run of the wave flagged the case)
    or stops the script; a source survives exactly where it explains a
    mismatch; the change lines count the fields that changed; and a second
    pass changes nothing."""
    script = _script()
    root = tmp_path_factory.mktemp("cases")
    current, previous = root / "current", root / "previous"
    entries, wave = [], set()
    for case in cases:
        sid = f"scenario_{case['n']:03d}"
        name = f"us__{sid}__snap"
        if in_wave:
            wave.add(f"{sid}:snap")
        _write_case(
            current,
            name,
            {
                "case_failure_source": "llm_error",
                "case_failure_subtype": case["subtype"],
                "reference_suspect": case["verdict_flag"],
            },
            {
                "judge_model_requested": "claude-opus-5-5",
                "judged_at_utc": f"{case['current_day']}T12:00:00Z",
            },
        )
        entry = {
            "country": "us",
            "scenario_id": sid,
            "variable": "snap",
            "judge_model": "claude-opus-5-5",
            "judge_failure_source": "llm_error",
            "judge_failure_subtype": case["subtype"],
            "judge_reference_suspect": case["top_flag"],
        }
        if case["top_source"]:
            entry["judge_reference_suspect_source"] = script.FLAG_SOURCE_EARLIER_RUN
        prior = case["previous"]
        if prior is not None:
            if prior["exists"]:
                _write_case(
                    previous,
                    name,
                    {
                        "case_failure_source": "llm_error",
                        "case_failure_subtype": prior["subtype"],
                        "reference_suspect": prior["flag"],
                    },
                    {
                        "judge_model_requested": "claude-opus-5-5",
                        "judged_at_utc": f"{prior['day']}T12:00:00Z",
                    },
                )
            entry["judge_rejudged_on"] = "2026-09-28"
            entry["judge_previous"] = [
                {
                    "judge_model": "claude-opus-5-5",
                    "judge_failure_source": "llm_error",
                    "judge_failure_subtype": prior["recorded_subtype"],
                    "judge_reference_suspect": prior["recorded_flag"],
                    "judged_on": prior["stale_day"],
                }
            ]
        entries.append(entry)

    def bound(prior) -> bool:
        return prior["exists"] and prior["subtype"] == prior["recorded_subtype"]

    def top_mismatch(case) -> bool:
        return case["top_flag"] != case["verdict_flag"]

    unexplained_top = any(
        top_mismatch(case) and not (case["top_flag"] and case["top_source"] and in_wave)
        for case in cases
    )
    unexplained_previous = any(
        case["previous"] is not None
        and bound(case["previous"])
        and case["previous"]["recorded_flag"] != case["previous"]["flag"]
        and not (case["previous"]["recorded_flag"] and in_wave)
        for case in cases
    )
    unexplained = unexplained_top or unexplained_previous
    if unexplained:
        with pytest.raises(SystemExit):
            script.date_entries(entries, current, previous, frozenset(wave))
        return
    changes = script.date_entries(entries, current, previous, frozenset(wave))
    for case, entry in zip(cases, entries):
        day = case["current_day"]
        prior = case["previous"]
        # The top-level flag never changes; its source stays exactly where it
        # explains a flag the current verdict does not raise.
        assert entry["judge_reference_suspect"] is case["top_flag"]
        assert ("judge_reference_suspect_source" in entry) == top_mismatch(case)
        if prior is None:
            assert entry["judged_on_utc"] == day
            assert "judge_previous" not in entry
            continue
        assert entry["judge_rejudged_on"] == day
        (item,) = entry["judge_previous"]
        assert ("judged_on" in item) != ("adjudicated_on" in item)
        if bound(prior):
            assert item["judged_on"] == prior["day"]
            mismatch = prior["recorded_flag"] != prior["flag"]
            assert ("judge_reference_suspect_source" in item) == mismatch
        else:
            assert item["adjudicated_on"] == prior["stale_day"]
            assert "judge_reference_suspect_source" not in item
    assert len(changes) == len(set(changes))
    assert script.date_entries(entries, current, previous, frozenset(wave)) == []


def test_each_restatement_names_its_20261010_verdict(tmp_path):
    """Release 20261010 changed release 20261006's record in three ways. Each
    decision on a case Claude Haiku 5.5 re-opened names that case's new
    verdict (docs/haiku55/judge_verdicts_20261010.json): its judge, classes
    and UTC day, with release 20261006's verdict appended to judge_previous
    when the new one replaces it. The decisions on records its engine upgrade
    regenerated are dropped (the #178 precedent). The 2026-10-06 and
    2026-10-09 waves' decisions are added, or restated in place where a ruled
    output already had a decision. Everything else is release 20261006's."""
    evidence = json.loads(EVIDENCE_20261010.read_text())
    assert evidence["base_commit"] == RELEASE_20261006_COMMIT
    verdicts = evidence["cases"]
    base = {_case(e): e for e in _entries_20261006(tmp_path)}
    entries = {
        _case(e): e for e in load_adjudications(ANNOTATIONS / "us_adjudications.json")
    }
    sidecar = json.loads(
        (
            ROOT
            / "paper/snapshot/20260501/runs"
            / RUN_LABEL
            / "reference_outputs.csv.meta.json"
        ).read_text()
    )
    upgrade = [r for r in sidecar["revisions"] if r["kind"] == "engine_upgrade"][-1]
    regenerated = {
        f"us__{item['scenario_id']}__{item['variable']}"
        for item in upgrade["regenerated_exclusions"]
    }
    new_waves = {"2026-10-06", UPGRADE_WAVE}
    assert set(base) - set(entries) == regenerated & set(base)
    added = set(entries) - set(base)
    assert added and {entries[c]["adjudicated_on"] for c in added} <= new_waves
    moved = {
        c
        for c in set(base) & set(entries)
        if entries[c]["adjudicated_on"] != base[c]["adjudicated_on"]
    }
    assert {entries[c]["adjudicated_on"] for c in moved} <= new_waves
    replaced = 0
    for case in sorted(set(base) & set(entries)):
        before, entry = base[case], entries[case]
        if case not in verdicts:
            if case not in moved:
                assert entry == before, case
            continue
        current = verdicts[case]
        assert (
            entry["judge_model"],
            entry["judge_failure_source"],
            entry["judge_failure_subtype"],
            entry.get("judge_rejudged_on") or entry.get("judged_on_utc"),
        ) == (
            current["judge_model"],
            current["case_failure_source"],
            current["case_failure_subtype"],
            current["judged_at_utc"][:10],
        ), case
        assert _flag_agrees(entry, current["reference_suspect"]), case
        if case not in moved:
            decision = {
                k: v
                for k, v in entry.items()
                if not k.startswith("judge") and k != "reasoning"
            }
            assert decision == {
                k: v
                for k, v in before.items()
                if not k.startswith("judge") and k != "reasoning"
            }, case
        history = entry.get("judge_previous", [])
        assert history[:-1] == before.get("judge_previous", []), case
        assert (
            history[-1]["judge_model"],
            history[-1]["judge_failure_source"],
            history[-1]["judge_failure_subtype"],
        ) == (
            before["judge_model"],
            before["judge_failure_source"],
            before["judge_failure_subtype"],
        ), case
        replaced += 1
    # Every verdict the evidence lists belongs to a committed decision: the 60
    # restated ones, and the new waves' decisions.
    assert set(verdicts) <= set(entries)
    assert replaced == 60
    assert set(verdicts) - set(base) == added
    # The judge evidence names, for each of the new waves' decisions, the
    # verdict that decision carries (its "current" verdict).
    judged = _judge_evidence()["cases"]
    for case, entry in entries.items():
        if entry["adjudicated_on"] not in new_waves:
            continue
        current = judged[case]["current"]
        assert "published" not in judged[case], case
        assert (
            entry["judge_model"],
            entry["judge_failure_source"],
            entry["judge_failure_subtype"],
            entry.get("judge_rejudged_on") or entry.get("judged_on_utc"),
        ) == (
            current["judge_model"],
            current["case_failure_source"],
            current["case_failure_subtype"],
            current["judged_at_utc"][:10],
        ), case
        assert current["verdict_sha256"] == verdicts[case]["verdict_sha256"], case
        assert _flag_agrees(entry, current["reference_suspect"]), case


def _flag_agrees(entry: dict, flagged_now: bool) -> bool:
    """A decision's reference flag is its verdict's, or set from an earlier
    run the verdict does not repeat, which judge_reference_suspect_source
    must say."""
    flagged = bool(entry.get("judge_reference_suspect"))
    if flagged == bool(flagged_now):
        return True
    return (
        flagged
        and not flagged_now
        and bool(entry.get("judge_reference_suspect_source"))
    )


def test_the_evidence_script_refuses_a_decision_that_does_not_name_its_verdict():
    """MOCK decision and verdict: scripts/date_haiku55_judge_verdicts.py
    finds each way a decision's judge fields can depart from the verdict it
    names, and accepts a flag set from an earlier run only with its source."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "date_haiku55_judge_verdicts", ROOT / "scripts/date_haiku55_judge_verdicts.py"
    )
    dating = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dating)

    verdict = {
        "case_failure_source": "llm_error",
        "case_failure_subtype": "thresholds_rates",
        "reference_suspect": False,
    }
    meta = {
        "judge_model_requested": "claude-opus-5-5",
        "judged_at_utc": "2026-10-10T03:00:00Z",
    }
    entry = {
        "judge_model": "claude-opus-5-5",
        "judge_failure_source": "llm_error",
        "judge_failure_subtype": "thresholds_rates",
        "judge_rejudged_on": "2026-10-10",
        "judge_reference_suspect": False,
    }
    assert dating.judge_disagreements(entry, verdict, meta) == []
    for field, value, found in (
        ("judge_model", "claude-sonnet-5-5", "judge_model"),
        ("judge_failure_subtype", "other", "judge_failure_subtype"),
        ("judge_rejudged_on", "2026-10-09", "judged on"),
        ("judge_reference_suspect", True, "reference flag"),
    ):
        problems = dating.judge_disagreements({**entry, field: value}, verdict, meta)
        assert len(problems) == 1 and found in problems[0], (field, problems)
    earlier = {
        **entry,
        "judge_reference_suspect": True,
        "judge_reference_suspect_source": "MOCK earlier run",
    }
    assert dating.judge_disagreements(earlier, verdict, meta) == []
    unflagged = dating.judge_disagreements(
        entry, {**verdict, "reference_suspect": True}, meta
    )
    assert unflagged and "reference flag" in unflagged[0]
