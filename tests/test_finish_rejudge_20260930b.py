"""Gates of the release 20260930b re-judge driver and its freeze."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import finish_rejudge_20260930b as driver  # noqa: E402
import freeze_rejudge_20260930b as freeze  # noqa: E402

CASE = "us__scenario_086__federal_refundable_credits"
OTHER = "us__scenario_000__payroll_tax"
ROWS = "us_audit_row_annotations.csv"
NOTES = "us_case_notes.csv"


def sha(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- the pins


def test_the_rejudge_pins_are_the_audited_seed_verdicts():
    """Each pin is the seed's verdict and prompt, as the committed digest records."""
    with open(ROOT / "docs/gpt61sol/seed_digest.csv") as stream:
        seed = {row["case_id"]: row for row in csv.DictReader(stream)}
    assert len(driver.REJUDGE) == 5
    for case, (verdict_sha, prompt_sha, reason) in driver.REJUDGE.items():
        assert seed[case]["verdict_sha256"] == verdict_sha
        assert seed[case]["prompt_sha256"] == prompt_sha
        assert reason


def test_the_rejudged_cases_are_the_audit_records_findings():
    """The five are exactly the published verdicts the audit could not clear."""
    path = ROOT / "docs/judge_isolation_2026-09-30/verdicts.csv"
    with open(path) as stream:
        rows = [r for r in csv.DictReader(stream) if r["tree"] == "seed"]
    flagged = {
        r["case_id"]
        for r in rows
        if r["affected"] in ("yes", "unknown") or r["context_exposure"]
    }
    assert flagged == set(driver.REJUDGE)


def test_the_release_is_a_suffix_of_its_base():
    assert driver.RELEASE_TAG == driver.BASE_TAG + "b"


def test_nothing_reads_the_base_before_it_is_pinned(monkeypatch):
    monkeypatch.setattr(driver, "BASE_COMMIT", None)
    monkeypatch.setattr(driver, "BASE_SHA256", None)
    for call in (
        lambda: driver.base_blob("app/src/data.artifact.json"),
        driver.base_annotation_names,
        lambda: freeze.main(["--stage-dir", str(ROOT / "results/local/x")]),
    ):
        with pytest.raises(SystemExit, match="not pinned"):
            call()


# ---------------------------------------------------------------- payload scope

ROW = (
    "countries",
    "us",
    "scenarioPredictions",
    "scenario_086",
    "federal_refundable_credits",
    "gpt-5.5",
)


@pytest.mark.parametrize("field", sorted(driver.ANNOTATION_FIELDS))
def test_a_rejudged_cases_annotation_fields_may_change(field):
    assert driver.allowed_path(ROW + (field,))


@pytest.mark.parametrize(
    "path",
    [
        ROW,  # a whole model row added or dropped
        ROW + ("prediction",),
        ROW + ("score",),
        ROW + ("referenceExplanation",),
        ROW + ("annotation", "extra"),
        (
            "countries",
            "us",
            "scenarioPredictions",
            "scenario_086",
            "snap",
            "m",
            "annotation",
        ),
        (
            "countries",
            "us",
            "scenarioPredictions",
            "scenario_000",
            "payroll_tax",
            "m",
            "annotation",
        ),
        ("countries", "us", "modelStats", 0, "exact"),
        ("countries", "us", "heatmap"),
        ("countries", "us", "failureModes", "programs", 0, "overallCorrectPct"),
    ],
)
def test_nothing_else_may_change(path):
    assert not driver.allowed_path(path)


json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=5),
    lambda children: (
        st.lists(children, max_size=4)
        | st.dictionaries(st.text(min_size=1, max_size=4), children, max_size=4)
    ),
    max_leaves=20,
)


@given(json_values)
def test_a_value_does_not_differ_from_itself(value):
    assert driver.payload_diff(value, json.loads(json.dumps(value))) == []


@given(
    st.dictionaries(st.text(min_size=1, max_size=4), json_values, min_size=1),
    st.data(),
)
def test_a_changed_leaf_is_reported_at_its_path(value, data):
    key = data.draw(st.sampled_from(sorted(value)))
    changed = dict(value)
    changed[key] = {"__changed__": True}
    diff = driver.payload_diff(value, changed)
    assert diff and all(path[0] == key for path in diff)


def test_added_keys_and_resized_lists_are_differences():
    assert driver.payload_diff({"a": 1}, {"a": 1, "b": 2}) == [("b",)]
    assert driver.payload_diff({"a": [1, 2]}, {"a": [1]}) == [("a",)]


# ---------------------------------------------------------------- annotations

ROW_HEADER = (
    "country,scenario_id,variable,model,failure_source,failure_subtype,"
    "reference_suspect,annotation\n"
)
NOTE_HEADER = (
    "country,scenario_id,variable,wrong_model_count,case_failure_sources,"
    "case_failure_subtypes,reference_suspect,reference_bug_hypothesis,case_annotation\n"
)
FRC = "us,scenario_086,federal_refundable_credits"
OLD_ONE = f"{FRC},m1,llm_error,credit_phaseout,False,Old one.\n"
BASE_ROWS = (
    ROW_HEADER
    + "us,scenario_000,payroll_tax,m1,llm_error,thresholds_rates,False,"
    + '"Amended, with a comma."\n'
    + OLD_ONE
    + f"{FRC},m2,llm_error,credit_phaseout,False,Old two.\n"
    + 'us,scenario_099,snap,m1,llm_error,other,False,"He said ""no""."\n'
)
BASE_NOTES = (
    NOTE_HEADER
    + "us,scenario_000,payroll_tax,1,llm_error,thresholds_rates,False,,Blank.\n"
    + f"{FRC},2,llm_error,credit_phaseout,False,,Old note.\n"
)


def new_rows():
    import pandas as pd

    return pd.DataFrame(
        {
            "country": ["us", "us"],
            "scenario_id": ["scenario_086", "scenario_086"],
            "variable": ["federal_refundable_credits"] * 2,
            # Collected in the other order: the splice keeps the base order.
            "model": ["m2", "m1"],
            "failure_source": ["llm_error", "llm_error"],
            "failure_subtype": ["credit_phaseout", "taxable_income_or_deductions"],
            "reference_suspect": [False, False],
            "annotation": ["New two,\nover two lines.", "New one."],
        }
    )


def test_the_splice_replaces_only_the_rejudged_records():
    key, _ = driver.ANNOTATION_CSVS[ROWS]
    text = driver.splice_annotations(BASE_ROWS, new_rows(), key)
    header, records = driver.csv_records(text)
    _, base_records = driver.csv_records(BASE_ROWS)
    assert header == ROW_HEADER
    assert records[0] == base_records[0] and records[3] == base_records[3]
    parsed = list(csv.DictReader(io.StringIO(text)))
    assert [r["model"] for r in parsed] == ["m1", "m1", "m2", "m1"]
    assert parsed[1]["annotation"] == "New one."
    assert parsed[2]["annotation"] == "New two,\nover two lines."
    changes = driver.annotation_changes(BASE_ROWS, text, ROWS)
    assert [(c["model"], sorted(c["changes"])) for c in changes] == [
        ("m1", ["annotation", "failure_subtype"]),
        ("m2", ["annotation"]),
    ]


def test_the_splice_refuses_to_add_or_drop_a_record():
    key, _ = driver.ANNOTATION_CSVS[ROWS]
    with pytest.raises(SystemExit, match="drop"):
        driver.splice_annotations(BASE_ROWS, new_rows().iloc[:1], key)
    extra = new_rows()
    extra.loc[1, "model"] = "m3"
    with pytest.raises(SystemExit):
        driver.splice_annotations(BASE_ROWS, extra, key)


def test_the_splice_refuses_a_record_the_base_does_not_have():
    import pandas as pd

    key, _ = driver.ANNOTATION_CSVS[ROWS]
    extra = new_rows().iloc[:1].assign(model="m3")
    with pytest.raises(SystemExit, match="add"):
        driver.splice_annotations(BASE_ROWS, pd.concat([new_rows(), extra]), key)


def test_a_blank_field_is_not_a_change():
    """Text comparison: a blank hypothesis stays blank, not NaN against ''."""
    assert driver.annotation_changes(BASE_NOTES, BASE_NOTES, NOTES) == []


@pytest.mark.parametrize(
    "name, base, old, new, message",
    [
        (ROWS, BASE_ROWS, "Amended, with a comma.", "Edited.", "outside the five"),
        (NOTES, BASE_NOTES, "Blank.", "Edited.", "outside the five"),
        (
            ROWS,
            BASE_ROWS,
            "reference_suspect,annotation",
            "suspect,annotation",
            "header",
        ),
        (ROWS, BASE_ROWS, OLD_ONE, "", "added or dropped"),
    ],
)
def test_changes_outside_the_five_are_refused(name, base, old, new, message):
    assert old in base
    with pytest.raises(SystemExit, match=message):
        driver.annotation_changes(base, base.replace(old, new), name)


def test_a_rejudged_note_may_not_change_its_wrong_model_count():
    edited = BASE_NOTES.replace(
        "federal_refundable_credits,2,", "federal_refundable_credits,3,"
    )
    with pytest.raises(SystemExit, match="wrong_model_count"):
        driver.annotation_changes(BASE_NOTES, edited, NOTES)


def test_verify_annotations_holds_every_other_file_to_the_base(monkeypatch, tmp_path):
    base = {ROWS: BASE_ROWS, NOTES: BASE_NOTES, "us_adjudications.json": "{}\n"}
    monkeypatch.setattr(driver, "base_annotation_names", lambda: sorted(base))
    monkeypatch.setattr(
        driver, "base_blob", lambda path: base[Path(path).name].encode()
    )
    for name, text in base.items():
        (tmp_path / name).write_text(text)
    assert driver.verify_annotations(tmp_path) == {NOTES: [], ROWS: []}
    (tmp_path / "us_adjudications.json").write_text('{"x": 1}\n')
    with pytest.raises(SystemExit, match="us_adjudications.json differs"):
        driver.verify_annotations(tmp_path)
    (tmp_path / "us_adjudications.json").write_text("{}\n")
    (tmp_path / "stray.csv").write_text("")
    with pytest.raises(SystemExit, match="not in the release"):
        driver.verify_annotations(tmp_path)
    (tmp_path / "stray.csv").unlink()
    with pytest.raises(SystemExit, match="annotation-changes.json"):
        driver.verify_annotations(tmp_path, {NOTES: [], ROWS: [{"x": 1}]})


# ---------------------------------------------------------------- the judge

SESSION = "s-1"
PROMPT = "facts\nusing these exact model ids: m1, m2\n"
VERDICT = {
    "reference_suspect": False,
    "reference_bug_hypothesis": "",
    "case_failure_source": "llm_error",
    "case_failure_subtype": "credit_phaseout",
    "rationale": "The credit is absorbed by liability.",
    "models": [
        {
            "model": m,
            "failure_source": "llm_error",
            "failure_subtype": "credit_phaseout",
            "diagnosis": "It paid the cap.",
        }
        for m in ("m1", "m2")
    ],
}


def events(
    prompt=PROMPT, verdict=VERDICT, session=SESSION, model=driver.JUDGE_MODEL, extra=()
):
    return [
        {
            "type": "user",
            "sessionId": session,
            "message": {"role": "user", "content": prompt},
        },
        {
            "type": "attachment",
            "sessionId": session,
            "attachment": {"type": "environment", "snapshot": {"isGitRepo": False}},
        },
        *extra,
        {
            "type": "assistant",
            "sessionId": session,
            "message": {
                "model": model,
                "content": [
                    {"type": "tool_use", "name": "StructuredOutput", "input": verdict}
                ],
            },
        },
        {
            "type": "attachment",
            "sessionId": session,
            "attachment": {"type": "structured_output", "data": verdict},
        },
    ]


def write_transcript(path: Path, rows) -> Path:
    path.write_text("\n".join(json.dumps(e) for e in rows) + "\n")
    return path


def test_an_isolated_transcript_passes(tmp_path):
    path = write_transcript(tmp_path / "t.jsonl", events())
    assert driver.transcript_problems(path, SESSION, PROMPT, VERDICT) == []


def event(kind, **fields):
    return {"type": kind, "sessionId": SESSION, **fields}


@pytest.mark.parametrize(
    "extra, problem",
    [
        (
            event(
                "assistant", message={"content": [{"type": "tool_use", "name": "Read"}]}
            ),
            "tool call Read",
        ),
        (
            event(
                "assistant",
                message={"content": [{"type": "tool_use", "name": "Workflow"}]},
            ),
            "tool call Workflow",
        ),
        (
            event(
                "assistant",
                message={
                    "content": [{"type": "server_tool_use", "name": "web_search"}]
                },
            ),
            "tool call web_search",
        ),
        (
            event(
                "attachment",
                attachment={"type": "environment", "snapshot": {"isGitRepo": True}},
            ),
            "git repository",
        ),
        (
            event(
                "attachment",
                attachment={"type": "session_context", "context": {"gitStatus": "r33"}},
            ),
            "git status",
        ),
        (
            event(
                "attachment",
                attachment={
                    "type": "prompt_snapshot",
                    "systemPrompt": ["Current branch: x"],
                },
            ),
            "system prompt",
        ),
        (
            event(
                "attachment",
                attachment={
                    "type": "prompt_snapshot",
                    "systemPrompt": ["Contents of /a/CLAUDE.md"],
                },
            ),
            "system prompt",
        ),
        (
            event(
                "attachment", attachment={"type": "nested_memory", "path": "CLAUDE.md"}
            ),
            "nested_memory",
        ),
        (
            event(
                "user",
                message={"content": "Base directory for this skill: /x/skills/w"},
            ),
            "skill",
        ),
        (
            event("assistant", message={"model": "claude-opus-5", "content": []}),
            "answered by claude-opus-5",
        ),
        (
            {"type": "user", "sessionId": "s-2", "message": {"content": []}},
            "belongs to session s-2",
        ),
    ],
)
def test_a_transcript_that_saw_or_did_more_is_refused(tmp_path, extra, problem):
    path = write_transcript(tmp_path / "t.jsonl", events(extra=[extra]))
    assert any(
        problem in p for p in driver.transcript_problems(path, SESSION, PROMPT, VERDICT)
    )


def test_a_transcript_must_hold_this_prompt_and_this_verdict(tmp_path):
    path = write_transcript(tmp_path / "t.jsonl", events())
    other = dict(VERDICT, rationale="Another answer.")
    assert any(
        "open with" in p
        for p in driver.transcript_problems(path, SESSION, "x", VERDICT)
    )
    assert any(
        "structured answer" in p
        for p in driver.transcript_problems(path, SESSION, PROMPT, other)
    )
    assert driver.transcript_problems(tmp_path / "absent.jsonl")


def test_prompt_model_ids_come_from_the_final_line():
    prompt = "facts\n\nReturn it using these exact model ids: a, b-1, c.2\n"
    assert driver.prompt_model_ids(prompt) == ["a", "b-1", "c.2"]


# ---------------------------------------------------------------- validate


def write_case(cases: Path, case: str, verdict=VERDICT, **meta_changes) -> None:
    case_dir = cases / case
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "prompt.md").write_text(PROMPT)
    text = json.dumps(verdict, indent=2, sort_keys=True)
    (case_dir / "verdict.json").write_text(text)
    meta = {
        "verdict_sha256": sha(text),
        "prompt_sha256": sha(PROMPT),
        "judge_model_requested": driver.JUDGE_MODEL,
        "judge_model_reported": [driver.JUDGE_MODEL],
        "judge_runner": "scripts/run_audit_claude.sh",
        "judge_isolation": {"transcript_tool_calls": 0},
        "judge_auth": {"method": "oauth_token"},
        "judged_at_utc": "2026-10-01T00:00:00+00:00",
        "session_id": SESSION,
    }
    meta.update(meta_changes)
    meta = {k: v for k, v in meta.items() if v is not None}
    (case_dir / "verdict.meta.json").write_text(json.dumps(meta))
    write_transcript(case_dir / "claude.transcript.jsonl", events(verdict=verdict))


def make_stage(tmp_path: Path, monkeypatch) -> tuple[Path, dict]:
    """A stage with one carried-over case and one re-judged case."""
    from policybench.audit import AUDIT_OUTPUT_SCHEMA

    monkeypatch.setattr(driver, "REJUDGE", {CASE: ("0" * 64, sha(PROMPT), "reason")})
    stage = tmp_path / "stage"
    cases = stage / "audit" / "cases"
    cases.mkdir(parents=True)
    (stage / "audit" / "schema.json").write_text(json.dumps(AUDIT_OUTPUT_SCHEMA))
    write_case(cases, CASE)
    write_case(cases, OTHER)
    audit_files = {
        f"{case}/{name}": sha((cases / case / name).read_bytes())
        for case in (CASE, OTHER)
        for name in driver.AUDIT_FILES
    }
    return stage, {"audit_files": audit_files}


def test_a_clean_rejudge_validates(tmp_path, monkeypatch):
    stage, record = make_stage(tmp_path, monkeypatch)
    assert driver.validate(stage, record) == []


def test_a_changed_missing_or_added_carried_over_file_is_refused(tmp_path, monkeypatch):
    stage, record = make_stage(tmp_path, monkeypatch)
    cases = stage / "audit/cases"
    path = cases / OTHER / "verdict.json"
    path.write_text(path.read_text().replace("liability", "tax"))
    assert any("carried-over" in p for p in driver.validate(stage, record))
    path.unlink()
    assert any("carried-over" in p for p in driver.validate(stage, record))
    (cases / "us__scenario_001__snap").mkdir()
    (cases / "us__scenario_001__snap" / "verdict.json").write_text("{}")
    assert any("unexpected audit file" in p for p in driver.validate(stage, record))


@pytest.mark.parametrize(
    "changes, problem",
    [
        ({"verdict_sha256": "0" * 64}, "does not bind the verdict"),
        ({"prompt_sha256": "0" * 64}, "does not bind the prompt"),
        (
            {"judge_model_reported": ["claude-haiku-4-5", driver.JUDGE_MODEL]},
            "judge was not",
        ),
        ({"judge_model_requested": "opus"}, "judge was not"),
        ({"judged_at_utc": None}, "no judging time"),
        ({"judge_isolation": None}, "isolated judge"),
        ({"judge_runner": "Claude Code Workflow tool"}, "isolated judge"),
        ({"judge_auth": {"method": "api_key"}}, "subscription login"),
        ({"session_id": "s-other"}, "belongs to session"),
    ],
)
def test_a_rejudge_with_a_bad_sidecar_is_refused(
    tmp_path, monkeypatch, changes, problem
):
    stage, _ = make_stage(tmp_path, monkeypatch)
    write_case(stage / "audit/cases", CASE, **changes)
    assert any(problem in p for p in driver.case_problems(stage, CASE))


@pytest.mark.parametrize(
    "verdict, problem",
    [
        (dict(VERDICT, models=VERDICT["models"][:1]), "are not exactly"),
        (dict(VERDICT, models=VERDICT["models"] * 2), "are not exactly"),
        (dict(VERDICT, rationale="The credit may be absorbed."), "hedged"),
        (dict(VERDICT, case_failure_source="made_up"), "made_up"),
    ],
)
def test_a_rejudge_with_a_bad_verdict_is_refused(
    tmp_path, monkeypatch, verdict, problem
):
    stage, _ = make_stage(tmp_path, monkeypatch)
    write_case(stage / "audit/cases", CASE, verdict=verdict)
    assert any(problem in p for p in driver.case_problems(stage, CASE))


def test_the_replaced_verdict_and_a_changed_prompt_are_refused(tmp_path, monkeypatch):
    stage, _ = make_stage(tmp_path, monkeypatch)
    verdict_sha = sha((stage / "audit/cases" / CASE / "verdict.json").read_bytes())
    monkeypatch.setattr(driver, "REJUDGE", {CASE: (verdict_sha, sha(PROMPT), "reason")})
    assert any("replaced one" in p for p in driver.case_problems(stage, CASE))
    monkeypatch.setattr(driver, "REJUDGE", {CASE: ("0" * 64, "1" * 64, "reason")})
    assert any("not the audited one" in p for p in driver.case_problems(stage, CASE))


def test_an_unreadable_verdict_is_reported_not_raised(tmp_path, monkeypatch):
    stage, _ = make_stage(tmp_path, monkeypatch)
    (stage / "audit/cases" / CASE / "verdict.json").write_text("{not json")
    assert any("unreadable" in p for p in driver.case_problems(stage, CASE))


def test_set_aside_keeps_the_prompt_and_records_why(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    for name in ("prompt.md", "verdict.json", "verdict.meta.json", "codex.log"):
        (case_dir / name).write_text(name)
    destination = tmp_path / "aside"
    driver.set_aside(case_dir, destination, "why")
    assert sorted(p.name for p in case_dir.iterdir()) == ["prompt.md"]
    assert sorted(p.name for p in destination.iterdir()) == [
        "codex.log",
        "reason.txt",
        "verdict.json",
        "verdict.meta.json",
    ]
    assert (destination / "reason.txt").read_text() == "why\n"
    with pytest.raises(SystemExit, match="already exists"):
        driver.set_aside(case_dir, destination, "again")


def test_judge_sets_aside_a_rejected_verdict_and_judges_again(tmp_path, monkeypatch):
    """A verdict the runner accepts but the driver rejects is retried, not deleted."""
    stage, record = make_stage(tmp_path, monkeypatch)
    record.update(
        base_tag=driver.BASE_TAG,
        base_sha256="b",
        base_commit="c",
        rejudge=[CASE],
    )
    monkeypatch.setattr(driver, "BASE_SHA256", "b")
    monkeypatch.setattr(driver, "BASE_COMMIT", "c")
    (stage / driver.STAGE).write_text(json.dumps(record))
    hedged = dict(VERDICT, rationale="The credit may be absorbed.")
    write_case(stage / "audit/cases", CASE, verdict=hedged)
    calls = []

    def runner(*args, **kwargs):
        calls.append(kwargs["env"]["AUDIT_ONLY"])
        if not (stage / "audit/cases" / CASE / "verdict.json").exists():
            write_case(stage / "audit/cases", CASE)

    monkeypatch.setattr(driver.subprocess, "run", runner)

    class Args:
        stage_dir = stage

    driver.judge(Args)
    assert calls == [CASE, CASE]
    aside = list((stage / "replaced-verdicts" / CASE).iterdir())
    assert len(aside) == 1 and "hedged" in (aside[0] / "reason.txt").read_text()
    assert json.loads((stage / driver.STAGE).read_text())["replaced_files"]
    assert driver.case_problems(stage, CASE) == []


def test_judge_gives_up_after_its_rounds(tmp_path, monkeypatch):
    stage, record = make_stage(tmp_path, monkeypatch)
    record.update(
        base_tag=driver.BASE_TAG, base_sha256="b", base_commit="c", rejudge=[CASE]
    )
    monkeypatch.setattr(driver, "BASE_SHA256", "b")
    monkeypatch.setattr(driver, "BASE_COMMIT", "c")
    (stage / driver.STAGE).write_text(json.dumps(record))
    hedged = dict(VERDICT, rationale="The credit may be absorbed.")

    def runner(*args, **kwargs):
        if not (stage / "audit/cases" / CASE / "verdict.json").exists():
            write_case(stage / "audit/cases", CASE, verdict=hedged)

    monkeypatch.setattr(driver.subprocess, "run", runner)

    class Args:
        stage_dir = stage

    write_case(stage / "audit/cases", CASE, verdict=hedged)
    with pytest.raises(SystemExit, match="left problems"):
        driver.judge(Args)
    assert (
        len(list((stage / "replaced-verdicts" / CASE).iterdir())) == driver.JUDGE_ROUNDS
    )


# ---------------------------------------------------------------- the freeze


def test_the_manifest_may_change_only_in_this_releases_scope():
    base = {
        "snapshot_date": "2026-09-30",
        "live_dashboard_artifact": {"tag": "a", "sha256": "1"},
        "audit_annotation_artifacts": {
            "files": {"us_case_notes.csv": "1", "us_adjudications.json": "1"},
            "judge_provenance": {"by_judge": {"x": 1}},
            "developer_adjudications": {"cases": 68},
        },
    }
    allowed = json.loads(json.dumps(base))
    allowed["live_dashboard_artifact"] = {"tag": "b", "sha256": "2"}
    allowed["audit_annotation_artifacts"]["files"]["us_case_notes.csv"] = "2"
    allowed["audit_annotation_artifacts"]["judge_provenance"]["by_judge"] = {
        "x": 0,
        "y": 1,
    }
    assert freeze.manifest_problems(base, allowed) == []
    for path, value in (
        (("snapshot_date",), "2026-10-01"),
        (("audit_annotation_artifacts", "files", "us_adjudications.json"), "2"),
        (("audit_annotation_artifacts", "developer_adjudications", "cases"), 69),
    ):
        changed = json.loads(json.dumps(base))
        target = changed
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        assert freeze.manifest_problems(base, changed) == [path]


def test_the_freeze_refuses_a_receipt_that_does_not_bind_its_inputs(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(driver, "BASE_SHA256", "b")
    monkeypatch.setattr(driver, "BASE_COMMIT", "c")
    payload = tmp_path / "data-board46.json"
    payload.write_text("{}")
    receipt = {
        "release_tag": driver.RELEASE_TAG,
        "base_tag": driver.BASE_TAG,
        "base_sha256": "b",
        "base_commit": "c",
        "models": driver.BOARD_MODELS,
        "partial": False,
        "payload_sha256": sha("{}"),
        "files": {},
    }
    (tmp_path / "release-ready.json").write_text(json.dumps(receipt))
    with pytest.raises(SystemExit, match="does not bind"):
        freeze.verify_receipt(tmp_path, payload)
    receipt["payload_sha256"] = "0" * 64
    (tmp_path / "release-ready.json").write_text(json.dumps(receipt))
    with pytest.raises(SystemExit, match="changed after export"):
        freeze.verify_receipt(tmp_path, payload)
