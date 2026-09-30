"""Gates of the release 20260930b re-judge driver and its freeze."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import finish_rejudge_20260930b as driver  # noqa: E402

CASE = "us__scenario_086__federal_refundable_credits"
OTHER = "us__scenario_000__payroll_tax"


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


def test_the_release_is_a_suffix_of_its_base():
    assert driver.RELEASE_TAG == driver.BASE_TAG + "b"


def test_every_step_refuses_before_the_base_is_pinned(monkeypatch, tmp_path):
    monkeypatch.setattr(driver, "BASE_COMMIT", None)
    monkeypatch.setattr(driver, "BASE_SHA256", None)
    with pytest.raises(SystemExit, match="not pinned"):
        driver.base_blob("app/src/data.artifact.json")


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
        ROW + ("prediction",),
        ROW + ("score",),
        ROW + ("referenceExplanation",),
        (
            "countries",
            "us",
            "scenarioPredictions",
            "scenario_086",
            "snap",
            "gpt-5.5",
            "annotation",
        ),
        (
            "countries",
            "us",
            "scenarioPredictions",
            "scenario_000",
            "payroll_tax",
            "gpt-5.5",
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
    st.dictionaries(st.text(min_size=1, max_size=4), json_values, min_size=1), st.data()
)
def test_a_changed_leaf_is_reported_at_its_path(value, data):
    key = data.draw(st.sampled_from(sorted(value)))
    changed = dict(value)
    changed[key] = {"__changed__": True}
    diff = driver.payload_diff(value, changed)
    assert diff and all(path[0] == key for path in diff)


# ---------------------------------------------------------------- annotations


def test_only_the_rejudged_cases_lines_may_change():
    header = "country,scenario_id,variable,model,annotation"
    before = "\n".join(
        [
            header,
            "us,scenario_086,federal_refundable_credits,m,old",
            "us,scenario_000,payroll_tax,m,same",
        ]
    )
    rejudged = before.replace(",old", ",new")
    driver.require_lines_outside_rejudge_unchanged(before, rejudged, "rows")
    with pytest.raises(SystemExit, match="outside the re-judged cases"):
        driver.require_lines_outside_rejudge_unchanged(
            before, before.replace(",same", ",different"), "rows"
        )


def test_annotation_changes_refuse_a_change_outside_the_five():
    import pandas as pd

    key = ["scenario_id", "variable", "model"]
    before = pd.DataFrame(
        {
            "scenario_id": ["scenario_086", "scenario_000"],
            "variable": ["federal_refundable_credits", "payroll_tax"],
            "model": ["m", "m"],
            "annotation": ["old", "same"],
        }
    )
    inside = before.copy()
    inside.loc[0, "annotation"] = "new"
    changes = driver.annotation_changes(before, inside, key)
    assert [c["scenario_id"] for c in changes] == ["scenario_086"]
    outside = before.copy()
    outside.loc[1, "annotation"] = "different"
    with pytest.raises(SystemExit, match="outside the re-judged cases"):
        driver.annotation_changes(before, outside, key)
    with pytest.raises(SystemExit, match="added or dropped"):
        driver.annotation_changes(before, before.iloc[:1], key)


# ---------------------------------------------------------------- the judge


def transcript(*events: dict) -> str:
    return "\n".join(json.dumps(e) for e in events) + "\n"


ANSWER = {
    "type": "assistant",
    "message": {
        "content": [{"type": "tool_use", "name": "StructuredOutput", "input": {}}]
    },
}
CLEAN_ENV = {
    "type": "attachment",
    "attachment": {"type": "environment", "snapshot": {"isGitRepo": False}},
}


def test_an_isolated_transcript_passes(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(transcript(CLEAN_ENV, ANSWER))
    assert driver.transcript_problems(path) == []


@pytest.mark.parametrize(
    "event, problem",
    [
        (
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "name": "Read", "input": {}}]
                },
            },
            "tool call Read",
        ),
        (
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "name": "Workflow", "input": {}}]
                },
            },
            "tool call Workflow",
        ),
        (
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "server_tool_use", "name": "web_search"}]
                },
            },
            "tool call web_search",
        ),
        (
            {
                "type": "attachment",
                "attachment": {"type": "environment", "snapshot": {"isGitRepo": True}},
            },
            "git repository",
        ),
        (
            {
                "type": "attachment",
                "attachment": {
                    "type": "session_context",
                    "context": {"gitStatus": "Recent commits: r33"},
                },
            },
            "git status",
        ),
        (
            {
                "type": "attachment",
                "attachment": {"type": "nested_memory", "path": "CLAUDE.md"},
            },
            "nested_memory",
        ),
        (
            {
                "type": "user",
                "message": {"content": "Base directory for this skill: /x/skills/w-a"},
            },
            "skill",
        ),
    ],
)
def test_a_transcript_that_saw_or_did_more_is_refused(tmp_path, event, problem):
    path = tmp_path / "t.jsonl"
    path.write_text(transcript(CLEAN_ENV, event, ANSWER))
    assert any(problem in p for p in driver.transcript_problems(path))


def test_a_missing_transcript_is_refused(tmp_path):
    assert driver.transcript_problems(tmp_path / "absent.jsonl")


def test_prompt_model_ids_come_from_the_final_line():
    prompt = "facts\n\nReturn it using these exact model ids: a, b-1, c.2\n"
    assert driver.prompt_model_ids(prompt) == ["a", "b-1", "c.2"]


# ---------------------------------------------------------------- validate


def make_stage(tmp_path: Path, monkeypatch) -> tuple[Path, dict]:
    """A stage with one carried-over case and one re-judged case."""
    from policybench.audit import AUDIT_OUTPUT_SCHEMA

    monkeypatch.setattr(driver, "REJUDGE", {CASE: ("0" * 64, "", "reason")})
    stage = tmp_path / "stage"
    cases = stage / "audit" / "cases"
    (stage / "audit").mkdir(parents=True)
    (stage / "audit" / "schema.json").write_text(json.dumps(AUDIT_OUTPUT_SCHEMA))
    prompt = "facts\nusing these exact model ids: m1, m2\n"
    for case in (CASE, OTHER):
        (cases / case).mkdir(parents=True)
        (cases / case / "prompt.md").write_text(prompt)
    verdict = {
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
    for case in (CASE, OTHER):
        text = json.dumps(verdict, indent=2, sort_keys=True)
        (cases / case / "verdict.json").write_text(text)
        meta = {
            "verdict_sha256": sha(text),
            "prompt_sha256": sha(prompt),
            "judge_model_reported": [driver.JUDGE_MODEL],
            "judge_runner": "scripts/run_audit_claude.sh",
            "judge_isolation": {"transcript_tool_calls": 0},
            "judge_auth": {"method": "oauth_token"},
        }
        (cases / case / "verdict.meta.json").write_text(json.dumps(meta))
    (cases / CASE / "claude.transcript.jsonl").write_text(transcript(CLEAN_ENV, ANSWER))
    monkeypatch.setattr(driver, "REJUDGE", {CASE: ("0" * 64, sha(prompt), "reason")})
    audit_files = {
        f"{case}/{name}": sha((cases / case / name).read_bytes())
        for case in (CASE, OTHER)
        for name in driver.AUDIT_FILES
    }
    return stage, {"audit_files": audit_files}


def test_a_clean_rejudge_validates(tmp_path, monkeypatch):
    stage, record = make_stage(tmp_path, monkeypatch)
    assert driver.validate(stage, record) == []


def test_a_changed_carried_over_verdict_is_refused(tmp_path, monkeypatch):
    stage, record = make_stage(tmp_path, monkeypatch)
    path = stage / "audit/cases" / OTHER / "verdict.json"
    path.write_text(path.read_text().replace("liability", "tax"))
    assert any("carried-over" in p for p in driver.validate(stage, record))


def test_a_rejudge_whose_judge_called_a_tool_is_refused(tmp_path, monkeypatch):
    stage, record = make_stage(tmp_path, monkeypatch)
    read = {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "Read", "input": {}}]},
    }
    (stage / "audit/cases" / CASE / "claude.transcript.jsonl").write_text(
        transcript(read, ANSWER)
    )
    assert any("tool call Read" in p for p in driver.validate(stage, record))


def test_a_rejudge_that_drops_a_model_is_refused(tmp_path, monkeypatch):
    stage, record = make_stage(tmp_path, monkeypatch)
    path = stage / "audit/cases" / CASE / "verdict.json"
    verdict = json.loads(path.read_text())
    verdict["models"] = verdict["models"][:1]
    text = json.dumps(verdict, indent=2, sort_keys=True)
    path.write_text(text)
    meta_path = stage / "audit/cases" / CASE / "verdict.meta.json"
    meta = json.loads(meta_path.read_text())
    meta["verdict_sha256"] = sha(text)
    meta_path.write_text(json.dumps(meta))
    assert any("are not exactly" in p for p in driver.validate(stage, record))


def test_a_rejudge_the_runner_did_not_isolate_is_refused(tmp_path, monkeypatch):
    stage, record = make_stage(tmp_path, monkeypatch)
    meta_path = stage / "audit/cases" / CASE / "verdict.meta.json"
    meta = json.loads(meta_path.read_text())
    del meta["judge_isolation"]
    meta_path.write_text(json.dumps(meta))
    assert any("isolated judge" in p for p in driver.validate(stage, record))


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
