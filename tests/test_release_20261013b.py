"""Gates of the release 20261013b re-judge driver (scripts/release_20261013b.py)."""

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

import release_20261013b as driver  # noqa: E402

from policybench.judge_template import template_header  # noqa: E402

CASE = "us__scenario_086__federal_refundable_credits"
OTHER = "us__scenario_000__payroll_tax"
ROWS, NOTES = driver.ROWS, driver.NOTES


def sha(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- the pins


def test_the_rejudge_pins_are_release_20261013s_verdicts():
    """Each pin is the case's verdict and prompt in release 20261013's judged
    tree, as the base commit's seed digest and provenance record them."""
    seed = driver.base_seed()
    assert len(seed) == 677 and len(driver.REJUDGE) == 5
    for case, (verdict_sha, prompt_sha, reason) in driver.REJUDGE.items():
        assert seed[case] == {
            "prompt_sha256": prompt_sha,
            "verdict_sha256": verdict_sha,
        }
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


def test_the_base_is_release_20261013_and_the_release_its_suffix():
    assert driver.RELEASE_TAG == driver.BASE_TAG + "b"
    pointer = json.loads(driver.base_blob(driver.POINTER))
    assert pointer["tag"] == driver.BASE_TAG
    assert pointer["sha256"] == driver.BASE_SHA256
    assert pointer["bytes"] == driver.BASE_BYTES


def test_no_decision_exclusion_or_amendment_rests_on_the_five():
    record = json.loads(driver.base_blob(driver.ANNOTATIONS / driver.ADJUDICATIONS))
    decided = {(d["scenario_id"], d["variable"]) for d in record["adjudications"]}
    exclusions = json.loads(driver.base_blob(driver.SNAPSHOT_RUN / driver.EXCLUSIONS))
    excluded = {(e["scenario_id"], e["variable"]) for e in exclusions["exclusions"]}
    amendments = json.loads(driver.base_blob(driver.ANNOTATIONS / driver.AMENDMENTS))
    amended = {driver.case_key(a["case_id"]) for a in amendments["amendments"]}
    assert not (decided | excluded | amended) & driver.REJUDGE_KEYS


# ---------------------------------------------------------------- payload scope

CELL = (
    "countries",
    "us",
    "scenarioPredictions",
    "scenario_086",
    "federal_refundable_credits",
    "gpt-5.5",
)
SP = ("countries", "us", "scenarioPredictions")


@pytest.mark.parametrize("field", sorted(driver.ANNOTATION_FIELDS))
def test_a_rejudged_cases_annotation_fields_may_change(field):
    assert driver.allowed_path(CELL + (field,))


@pytest.mark.parametrize(
    "path",
    [
        CELL,  # a whole model cell added or dropped
        CELL + ("prediction",),
        CELL + ("score",),
        CELL + ("referenceExplanation",),
        CELL + ("annotation", "extra"),
        SP + ("scenario_086", "snap", "m", "annotation"),
        SP + ("scenario_000", "payroll_tax", "m", "annotation"),
        ("countries", "us", "modelStats", 0, "exact"),
        ("countries", "us", "heatmap"),
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


def payload(annotation="old", exact=90.0, other="same"):
    cell = {"prediction": 1.0, "annotation": annotation, "failureSource": "llm_error"}
    return {
        "countries": {
            "us": {
                "modelStats": [{"model": "m", "exact": exact}],
                "heatmap": [1],
                "scenarioPredictions": {
                    "scenario_086": {"federal_refundable_credits": {"m": cell}},
                    "scenario_000": {"payroll_tax": {"m": {"annotation": other}}},
                },
            }
        }
    }


def test_verify_payload_allows_only_the_fives_annotations():
    base = payload()
    assert driver.verify_payload(payload(annotation="new"), base) == [
        (*SP, "scenario_086", "federal_refundable_credits", "m", "annotation")
    ]
    with pytest.raises(SystemExit, match="modelStats changed"):
        driver.verify_payload(payload(exact=90.1), base)
    with pytest.raises(SystemExit, match="outside the five"):
        driver.verify_payload(payload(other="edited"), base)


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


def new_rows(second="New two,\nover two lines."):
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
            "annotation": [second, "New one."],
        }
    )


def test_the_splice_replaces_only_the_rejudged_records():
    key, _ = driver.ANNOTATION_CSVS[ROWS]
    text = driver.splice_annotations(BASE_ROWS, new_rows(), key)
    header, records = driver.csv_records(text)
    _, base_records = driver.csv_records(BASE_ROWS)
    assert header == ROW_HEADER
    assert records[0] == base_records[0] and records[3] == base_records[3]
    parsed = list(csv.DictReader(io.StringIO(text, newline="")))
    assert [r["model"] for r in parsed] == ["m1", "m1", "m2", "m1"]
    assert parsed[1]["annotation"] == "New one."
    assert parsed[2]["annotation"] == "New two,\nover two lines."
    changes = driver.annotation_changes(BASE_ROWS, text, ROWS)
    assert [(c["model"], sorted(c["changes"])) for c in changes] == [
        ("m1", ["annotation", "failure_subtype"]),
        ("m2", ["annotation"]),
    ]


@pytest.mark.parametrize("separator", [" ", " ", "\u0085", "\x0b", "\x0c"])
def test_a_unicode_separator_in_a_field_does_not_split_a_record(separator):
    """str.splitlines breaks on these; a CSV record ends only at CR or LF."""
    key, _ = driver.ANNOTATION_CSVS[ROWS]
    text = driver.splice_annotations(BASE_ROWS, new_rows(f"one{separator}two"), key)
    parsed = list(csv.DictReader(io.StringIO(text, newline="")))
    assert parsed[2]["annotation"] == f"one{separator}two"
    assert len(driver.annotation_changes(BASE_ROWS, text, ROWS)) == 2


def test_the_splice_refuses_to_add_or_drop_a_record():
    import pandas as pd

    key, _ = driver.ANNOTATION_CSVS[ROWS]
    with pytest.raises(SystemExit, match="drop"):
        driver.splice_annotations(BASE_ROWS, new_rows().iloc[:1], key)
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
        (ROWS, BASE_ROWS, "reference_suspect,annotation", "suspect,annotation", "head"),
        (ROWS, BASE_ROWS, OLD_ONE, "", "added or dropped"),
    ],
)
def test_changes_outside_the_five_are_refused(name, base, old, new, message):
    assert old in base
    with pytest.raises(SystemExit, match=message):
        driver.annotation_changes(base, base.replace(old, new), name)


def test_a_rejudged_note_may_not_change_its_wrong_model_count():
    edited = BASE_NOTES.replace(f"{FRC},2,", f"{FRC},3,")
    with pytest.raises(SystemExit, match="wrong_model_count"):
        driver.annotation_changes(BASE_NOTES, edited, NOTES)


def test_verify_annotations_needs_exactly_the_named_files(monkeypatch, tmp_path):
    base = {ROWS: BASE_ROWS, NOTES: BASE_NOTES, "us_adjudications.json": "{}\n"}
    monkeypatch.setattr(
        driver, "base_blob", lambda path: base[Path(path).name].encode()
    )
    for name, text in base.items():
        (tmp_path / name).write_text(text)
    assert driver.verify_annotations(tmp_path, sorted(base)) == {NOTES: [], ROWS: []}
    (tmp_path / "us_adjudications.json").write_text('{"x": 1}\n')
    with pytest.raises(SystemExit, match="us_adjudications.json differs"):
        driver.verify_annotations(tmp_path, sorted(base))
    (tmp_path / "us_adjudications.json").write_text("{}\n")
    (tmp_path / "stray.csv").write_text("")
    with pytest.raises(SystemExit, match="holds"):
        driver.verify_annotations(tmp_path, sorted(base))
    (tmp_path / "stray.csv").unlink()
    # A missing file is refused before any destructive step.
    (tmp_path / "us_adjudications.json").unlink()
    with pytest.raises(SystemExit, match="holds"):
        driver.verify_annotations(tmp_path, sorted(base))
    (tmp_path / "us_adjudications.json").write_text("{}\n")
    with pytest.raises(SystemExit, match="annotation-changes.json"):
        driver.verify_annotations(tmp_path, sorted(base), {NOTES: [], ROWS: [{}]})


# ---------------------------------------------------------------- the judge

SESSION = "11111111-2222-3333-4444-555555555555"
PROMPT = template_header(2) + "\nCOUNTRY: US\nfacts\n"
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


def transcript(verdict=VERDICT, prompt=PROMPT, session=SESSION, extra=()):
    def event(kind, **fields):
        return {"type": kind, "sessionId": session, **fields}

    snapshot = {"isGitRepo": False}
    return [
        event("user", message={"role": "user", "content": prompt}),
        event("attachment", attachment={"type": "environment", "snapshot": snapshot}),
        event("attachment", attachment={"type": "session_context", "context": {}}),
        *extra,
        event(
            "assistant",
            effort="xhigh",
            message={
                "model": driver.JUDGE_MODEL,
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": "StructuredOutput",
                        "input": verdict,
                    }
                ],
            },
        ),
        event(
            "user",
            message={
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "call-1"}],
            },
        ),
    ]


def write_case(stage: Path, case: str, verdict=VERDICT, events=None, **meta_changes):
    case_dir = stage / "audit" / "cases" / case
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "prompt.md").write_text(PROMPT)
    text = json.dumps(verdict, indent=2, sort_keys=True)
    (case_dir / "verdict.json").write_text(text)
    meta = {
        "verdict_sha256": sha(text),
        "prompt_sha256": sha(PROMPT),
        "judge_template_version": 2,
        "judge_model_requested": driver.JUDGE_MODEL,
        "judge_model_reported": [driver.JUDGE_MODEL],
        "judge_runner": "scripts/run_audit_claude.sh",
        "judge_isolation": {"transcript_tool_calls": 0},
        "judge_auth": {"method": "oauth_token", "account": None, "org": None},
        "judge_account_declared": "a declared login",
        "judge_effort": "xhigh",
        "judged_at_utc": "2026-10-13T18:00:00+00:00",
        "session_id": SESSION,
    }
    meta.update(meta_changes)
    meta = {k: v for k, v in meta.items() if v is not None}
    (case_dir / "verdict.meta.json").write_text(json.dumps(meta))
    rows = transcript(verdict) if events is None else events
    (case_dir / "claude.transcript.jsonl").write_text(
        "\n".join(json.dumps(e) for e in rows) + "\n"
    )


def make_stage(tmp_path: Path, monkeypatch) -> tuple[Path, dict]:
    """A stage with one carried-over case and one re-judged case."""
    from policybench.audit import AUDIT_OUTPUT_SCHEMA

    monkeypatch.setattr(driver, "REJUDGE", {CASE: ("0" * 64, "1" * 64, "reason")})
    monkeypatch.setattr(driver, "BASE_SHA256", "b")
    monkeypatch.setattr(driver, "BASE_COMMIT", "c")
    stage = tmp_path / "stage"
    audit = stage / "audit"
    (audit / "cases").mkdir(parents=True)
    (audit / "schema.json").write_text(json.dumps(AUDIT_OUTPUT_SCHEMA))
    manifest = [
        {"case_id": case, "wrong_models": ["m1", "m2"], "parse_failure_only": False}
        for case in (CASE, OTHER)
    ]
    (audit / "cases.jsonl").write_text("".join(json.dumps(m) + "\n" for m in manifest))
    write_case(stage, CASE)
    write_case(stage, OTHER)
    record = {
        "release_tag": driver.RELEASE_TAG,
        "base_tag": driver.BASE_TAG,
        "base_sha256": "b",
        "base_commit": "c",
        "rejudge": {CASE: sha(PROMPT)},
        "audit_files": {
            f"{OTHER}/{name}": sha((audit / "cases" / OTHER / name).read_bytes())
            for name in driver.AUDIT_FILES
        },
    }
    (stage / "stage.json").write_text(json.dumps(record))
    return stage, record


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
    problems = driver.validate(stage, record)
    assert any("unexpected audit file" in p for p in problems)
    assert any("unexpected case" in p for p in problems)


@pytest.mark.parametrize(
    "changes, problem",
    [
        ({"verdict_sha256": "0" * 64}, "does not bind the verdict"),
        ({"prompt_sha256": "0" * 64}, "does not bind the prompt"),
        ({"judge_template_version": 1}, "template v2"),
        ({"judge_template_version": None}, "template v2"),
        ({"judge_model_reported": ["claude-haiku-4-5", "x"]}, "judge was not"),
        ({"judge_model_requested": "opus"}, "judge was not"),
        ({"judged_at_utc": None}, "no judging time"),
        ({"judge_isolation": None}, "isolated judge"),
        ({"judge_runner": "Claude Code Workflow tool"}, "isolated judge"),
        ({"judge_auth": {"method": "claude.ai"}}, "token login"),
        ({"judge_account_declared": None}, "declares no account"),
        ({"session_id": None}, "no session id"),
        ({"session_id": "another-session"}, "is not session"),
        ({"judge_effort": "high"}, "effort"),
    ],
)
def test_a_rejudge_with_a_bad_sidecar_is_refused(
    tmp_path, monkeypatch, changes, problem
):
    stage, _ = make_stage(tmp_path, monkeypatch)
    write_case(stage, CASE, **changes)
    assert any(problem in p for p in driver.case_problems(stage, CASE))


@pytest.mark.parametrize(
    "verdict, problem",
    [
        (dict(VERDICT, models=VERDICT["models"][:1]), "are not exactly"),
        (dict(VERDICT, models=VERDICT["models"] * 2), "are not exactly"),
        (dict(VERDICT, rationale="The credit may be absorbed."), "hedged"),
        (dict(VERDICT, case_failure_source="made_up"), "schema"),
    ],
)
def test_a_rejudge_with_a_bad_verdict_is_refused(
    tmp_path, monkeypatch, verdict, problem
):
    stage, _ = make_stage(tmp_path, monkeypatch)
    write_case(stage, CASE, verdict=verdict)
    assert any(problem in p for p in driver.case_problems(stage, CASE))


def tool(name):
    return {
        "type": "assistant",
        "sessionId": SESSION,
        "effort": "xhigh",
        "message": {"content": [{"type": "tool_use", "id": "x", "name": name}]},
    }


@pytest.mark.parametrize(
    "extra, problem",
    [
        (tool("Read"), "tool calls"),
        (tool("Workflow"), "tool calls"),
        (
            {
                "type": "attachment",
                "sessionId": SESSION,
                "attachment": {
                    "type": "session_context",
                    "context": {"gitStatus": "Recent commits: r33"},
                },
            },
            "session context",
        ),
        (
            {
                "type": "attachment",
                "sessionId": SESSION,
                "attachment": {"type": "skill_listing", "content": "x"},
            },
            "skill_listing",
        ),
        (
            {
                "type": "user",
                "sessionId": SESSION,
                "message": {"role": "user", "content": "An earlier published note."},
            },
            "user text messages",
        ),
        ({"type": "user", "message": {"content": []}}, "is not session"),
    ],
)
def test_a_transcript_that_saw_or_did_more_is_refused(
    tmp_path, monkeypatch, extra, problem
):
    stage, _ = make_stage(tmp_path, monkeypatch)
    write_case(stage, CASE, events=transcript(extra=[extra]))
    assert any(problem in p for p in driver.case_problems(stage, CASE))


def test_a_transcript_of_another_prompt_or_answer_is_refused(tmp_path, monkeypatch):
    stage, _ = make_stage(tmp_path, monkeypatch)
    write_case(stage, CASE, events=transcript(prompt=PROMPT + "more"))
    assert any("prompt.md" in p for p in driver.case_problems(stage, CASE))
    other = dict(VERDICT, rationale="Another answer.")
    write_case(stage, CASE, events=transcript(verdict=other))
    assert any("verdict.json" in p for p in driver.case_problems(stage, CASE))
    (stage / "audit/cases" / CASE / "claude.transcript.jsonl").unlink()
    assert any("no transcript" in p for p in driver.case_problems(stage, CASE))


def test_the_replaced_verdict_and_a_changed_prompt_are_refused(tmp_path, monkeypatch):
    stage, _ = make_stage(tmp_path, monkeypatch)
    verdict_sha = sha((stage / "audit/cases" / CASE / "verdict.json").read_bytes())
    monkeypatch.setattr(driver, "REJUDGE", {CASE: (verdict_sha, "1" * 64, "reason")})
    assert any("replaced one" in p for p in driver.case_problems(stage, CASE))
    record = json.loads((stage / "stage.json").read_text())
    record["rejudge"][CASE] = "2" * 64
    (stage / "stage.json").write_text(json.dumps(record))
    assert any("prepare rendered" in p for p in driver.case_problems(stage, CASE))


def test_an_unreadable_verdict_is_reported_not_raised(tmp_path, monkeypatch):
    stage, _ = make_stage(tmp_path, monkeypatch)
    (stage / "audit/cases" / CASE / "verdict.json").write_text("{not json")
    assert any("unreadable" in p for p in driver.case_problems(stage, CASE))


def test_set_aside_moves_the_named_files_and_records_why(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    for name in ("prompt.md", "verdict.json", "verdict.meta.json", "codex.log"):
        (case_dir / name).write_text(name)
    destination = tmp_path / "aside"
    moved = driver.set_aside(case_dir, destination, "why", driver.JUDGE_FILES)
    assert sorted(moved) == ["codex.log", "verdict.json", "verdict.meta.json"]
    assert sorted(p.name for p in case_dir.iterdir()) == ["prompt.md"]
    assert (destination / "reason.txt").read_text() == "why\n"
    with pytest.raises(SystemExit, match="already exists"):
        driver.set_aside(case_dir, destination, "again", driver.JUDGE_FILES)


class Runner:
    """A stand-in for scripts/run_audit_claude.sh: one scripted action a call."""

    def __init__(self, stage: Path, script: list):
        self.stage, self.script, self.calls = stage, list(script), []

    def __call__(self, *args, **kwargs):
        self.calls.append(kwargs["env"]["AUDIT_ONLY"])
        action, code = self.script.pop(0)
        present = (self.stage / "audit/cases" / CASE / "verdict.json").exists()
        if action is not None and not present:
            write_case(self.stage, CASE, verdict=action)

        class Result:
            returncode = code

        return Result()


def run_judge(tmp_path, monkeypatch, script, first=None):
    stage, _ = make_stage(tmp_path, monkeypatch)
    monkeypatch.setattr(driver, "validate_stage", lambda path: path)
    for name in driver.JUDGE_FILES:
        (stage / "audit/cases" / CASE / name).unlink(missing_ok=True)
    if first is not None:
        write_case(stage, CASE, verdict=first)
    runner = Runner(stage, script)
    monkeypatch.setattr(driver.subprocess, "run", runner)

    class Args:
        pass

    Args.stage = stage
    return stage, runner, Args


HEDGED = dict(VERDICT, rationale="The credit may be absorbed.")


def test_judge_sets_aside_a_rejected_verdict_and_judges_again(tmp_path, monkeypatch):
    stage, runner, args = run_judge(
        tmp_path, monkeypatch, [(None, 0), (VERDICT, 0)], first=HEDGED
    )
    driver.judge(args)
    assert runner.calls == [CASE, CASE]
    aside = list((stage / "replaced-verdicts" / CASE).iterdir())
    assert len(aside) == 1 and "hedged" in (aside[0] / "reason.txt").read_text()
    assert json.loads((stage / "stage.json").read_text())["replaced_files"]
    assert driver.case_problems(stage, CASE) == []


def test_judge_retries_a_call_that_left_no_verdict(tmp_path, monkeypatch):
    stage, runner, args = run_judge(tmp_path, monkeypatch, [(None, 0), (VERDICT, 0)])
    driver.judge(args)
    assert runner.calls == [CASE, CASE]
    assert driver.case_problems(stage, CASE) == []


def test_judge_stops_when_the_login_cannot_judge(tmp_path, monkeypatch):
    _, runner, args = run_judge(tmp_path, monkeypatch, [(None, 1), (VERDICT, 0)])
    with pytest.raises(SystemExit, match="cannot judge now"):
        driver.judge(args)
    assert runner.calls == [CASE]


def test_judge_gives_up_after_its_rounds(tmp_path, monkeypatch):
    script = [(HEDGED, 0)] * driver.JUDGE_ROUNDS
    stage, runner, args = run_judge(tmp_path, monkeypatch, script)
    with pytest.raises(SystemExit, match="left problems"):
        driver.judge(args)
    assert len(runner.calls) == driver.JUDGE_ROUNDS
    aside = list((stage / "replaced-verdicts" / CASE).iterdir())
    assert len(aside) == driver.JUDGE_ROUNDS


# ---------------------------------------------------------------- the freeze


def test_the_manifest_may_change_only_in_this_releases_scope():
    """Checked on release 20261013's own manifest: the payload's hash is
    recorded twice, and both copies move together."""
    base = json.loads(driver.base_blob(driver.MANIFEST))
    after = json.loads(json.dumps(base))
    after["files"][0]["sha256"] = "f" * 64
    after["source_run_artifacts"][driver.RUN]["files"]["data.json.gz"] = "f" * 64
    after["published_dashboard_artifact"]["tag"] = driver.RELEASE_TAG
    after["live_dashboard_artifact"]["tag"] = driver.RELEASE_TAG
    after["audit_annotation_artifacts"]["files"][ROWS] = "f" * 64
    after["audit_annotation_artifacts"]["files"][NOTES] = "f" * 64
    after["audit_annotation_artifacts"]["judge_provenance"]["by_judge"] = {}
    assert driver.manifest_problems(base, after) == []
    for path, value in (
        (("snapshot_date",), "2026-10-14"),
        (("model_response_date",), "2026-06-12 to 2026-10-14"),
        (("audit_annotation_artifacts", "files", driver.ADJUDICATIONS), "f" * 64),
        (("audit_annotation_artifacts", "files", driver.EXPLANATIONS), "f" * 64),
        (("source_run_artifacts", driver.RUN, "files", "predictions.csv.gz"), "f"),
        (("reference_exclusions", "outputs"), 0),
    ):
        changed = json.loads(json.dumps(base))
        target = changed
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        assert driver.manifest_problems(base, changed) == [path]


def test_the_freeze_refuses_a_receipt_that_does_not_bind_its_inputs(
    tmp_path, monkeypatch
):
    payload_path = tmp_path / f"data-board{driver.BOARD_MODELS}.json"
    payload_path.write_text("{}")
    for name in ("PROVENANCE", "SEED_DIGEST"):
        (tmp_path / name).write_text(name)
        monkeypatch.setattr(driver, name, tmp_path / name)
    receipt = {
        "release_tag": driver.RELEASE_TAG,
        "base_tag": driver.BASE_TAG,
        "base_sha256": driver.BASE_SHA256,
        "base_commit": driver.BASE_COMMIT,
        "models": driver.BOARD_MODELS,
        "provenance_sha256": "p",
        "seed_digest_sha256": "s",
        "payload_sha256": sha("{}"),
        "files": {},
    }
    (tmp_path / "release-ready.json").write_text(json.dumps(receipt))
    with pytest.raises(SystemExit, match="does not bind this release"):
        driver.verify_receipt(tmp_path)
    receipt["provenance_sha256"] = sha("PROVENANCE")
    receipt["seed_digest_sha256"] = sha("SEED_DIGEST")
    (tmp_path / "release-ready.json").write_text(json.dumps(receipt))
    with pytest.raises(SystemExit, match="the receipt does not bind"):
        driver.verify_receipt(tmp_path)
    receipt["payload_sha256"] = "0" * 64
    (tmp_path / "release-ready.json").write_text(json.dumps(receipt))
    with pytest.raises(SystemExit, match="changed after export"):
        driver.verify_receipt(tmp_path)
