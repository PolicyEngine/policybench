"""The diagnosis judge's template versions, and how a tree of verdicts keeps
the version each was judged on.

Invariants:
- every committed prompt re-renders on its recorded version: each prompt
  sha256 that docs/gpt61sol/ and docs/haiku55/ commit re-renders, on the
  version its verdict records, from the committed board of the release that
  judged it (local only, for it needs the audit grounding); and prepare_audit
  keeps a judged case's files only on the exact bytes its judge read: the
  case rendered on its recorded version (absent: v1), equal to prompt.md and
  to the sidecar's prompt_sha256 when it records one;
- v2 differs from v1 only by the dropped clause: the header diff is one
  deletion, V1_REVIEW_CLAIM, and the rest of a prompt does not depend on the
  version;
- version selection is explicit, never inferred: render_case_prompt,
  prepare_audit and audit-prepare require a version, every call names one,
  and prepare_audit keeps a verdict on its recorded version alone, never on
  the version a prompt begins with;
- a version's header never changes (pinned by sha256), and no header is a
  prefix of another, so a prompt's version is read off its bytes;
- after prepare_audit, a tree validates (template_version_problems is empty),
  and a second prepare_audit changes nothing.
"""

from __future__ import annotations

import ast
import contextlib
import difflib
import functools
import hashlib
import inspect
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from policybench.audit import (
    AuditCase,
    WrongModel,
    build_audit_cases,
    collect_audit,
    prepare_audit,
    prompt_hash_problems,
    render_case_prompt,
    template_version_problems,
)
from policybench.judge_template import (
    CURRENT_TEMPLATE_VERSION,
    JUDGE_TEMPLATE_HEADERS,
    TEMPLATE_VERSION_FIELD,
    UNRECORDED_TEMPLATE_VERSION,
    V1_REVIEW_CLAIM,
    recorded_template_version,
    template_header,
    template_version_of,
)

ROOT = Path(__file__).resolve().parents[1]
# Properties run on a loaded machine too: no deadline, no slow-input check.
PROPERTY = settings(
    deadline=None, suppress_health_check=[HealthCheck.too_slow], max_examples=50
)
# Each version's header, by sha256 of its UTF-8 bytes. A carried verdict was
# judged on exactly these bytes: never edit a pin, add a version.
PINNED_HEADER_SHA256 = {
    1: "25b91bdcea41c37d4aa7d105d55d4b68cf39f34b153cc0fc877a2848317572e2",
    2: "7d8ff9b27d4b0341310267c11ea895f84d403a3219b6eddb8d0bf7dc4b1354ed",
}
# origin/main before template versions: policybench/audit.py's _PROMPT_HEADER
# there is the template every verdict until then was judged on.
UNVERSIONED_COMMIT = "9ce4ade8382962a9134860c23f56d92509b5e57f"


# --- The versions --------------------------------------------------------------


def test_every_version_is_pinned():
    assert set(JUDGE_TEMPLATE_HEADERS) == set(PINNED_HEADER_SHA256)
    for version, header in JUDGE_TEMPLATE_HEADERS.items():
        digest = hashlib.sha256(header.encode("utf-8")).hexdigest()
        assert digest == PINNED_HEADER_SHA256[version], version


def test_v1_is_the_template_before_versions():
    """Differential: v1 is the header origin/main rendered before versions."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{UNVERSIONED_COMMIT}:policybench/audit.py"],
        capture_output=True,
    )
    if result.returncode:
        pytest.fail(
            f"cannot read policybench/audit.py at {UNVERSIONED_COMMIT[:12]}; fetch "
            f"full history (git fetch --unshallow): {result.stderr.decode().strip()}"
        )
    tree = ast.parse(result.stdout.decode("utf-8"))
    (header,) = [
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and [getattr(t, "id", None) for t in node.targets] == ["_PROMPT_HEADER"]
    ]
    assert JUDGE_TEMPLATE_HEADERS[1] == header


def test_the_current_version_is_the_newest_and_an_unrecorded_one_is_v1():
    assert CURRENT_TEMPLATE_VERSION == max(JUDGE_TEMPLATE_HEADERS) == 2
    assert UNRECORDED_TEMPLATE_VERSION == 1


def test_v2_is_v1_without_the_review_claim():
    v1, v2 = JUDGE_TEMPLATE_HEADERS[1], JUDGE_TEMPLATE_HEADERS[2]
    assert v1.count(V1_REVIEW_CLAIM) == 1
    assert v2 == v1.replace(V1_REVIEW_CLAIM, "", 1)
    for phrase in (
        "has survived an adversarial review program",
        "the few real bugs found were fixed before this run",
    ):
        assert phrase in v1 and phrase not in v2
    assert (
        "generated directly from the engine's computation trace. Treat the "
        "reference and its derivation as correct." in " ".join(v2.split())
    )


def test_the_header_diff_is_one_deletion_of_the_clause():
    """v2 differs from v1 only by the dropped clause, and no diff can place
    the deletion anywhere else: the common prefix ends where the clause
    starts, the common suffix starts where it ends, and difflib's edit is that
    one deletion."""
    v1, v2 = JUDGE_TEMPLATE_HEADERS[1], JUDGE_TEMPLATE_HEADERS[2]
    prefix = len(os.path.commonprefix([v1, v2]))
    suffix = len(os.path.commonprefix([v1[::-1], v2[::-1]]))
    assert prefix + suffix == len(v2)
    assert v1[prefix : len(v1) - suffix] == V1_REVIEW_CLAIM
    opcodes = difflib.SequenceMatcher(None, v1, v2, autojunk=False).get_opcodes()
    edits = [
        (tag, v1[i1:i2], v2[j1:j2]) for tag, i1, i2, j1, j2 in opcodes if tag != "equal"
    ]
    assert edits == [("delete", V1_REVIEW_CLAIM, "")]


def test_no_header_is_a_prefix_of_another():
    for version, header in JUDGE_TEMPLATE_HEADERS.items():
        for other, other_header in JUDGE_TEMPLATE_HEADERS.items():
            if version != other:
                assert not other_header.startswith(header), (version, other)


def test_an_unknown_version_cannot_be_rendered():
    for version in (0, 3, True, "1", None, 1.0):
        with pytest.raises(ValueError, match="no judge template version"):
            template_header(version)


@PROPERTY
@given(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(-5, 10),
        st.floats(allow_nan=False),
        st.text(max_size=3),
        st.lists(st.integers(), max_size=2),
    )
)
def test_recorded_version_is_the_field_when_it_names_one(value):
    expected = value if type(value) is int and value in JUDGE_TEMPLATE_HEADERS else None
    assert recorded_template_version({TEMPLATE_VERSION_FIELD: value}) == expected
    assert recorded_template_version({"judge_runner": "x"}) == 1
    assert recorded_template_version(None) == 1


# --- Rendering -------------------------------------------------------------------

TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    max_size=60,
)


@st.composite
def audit_cases(draw) -> AuditCase:
    models = draw(
        st.lists(
            st.from_regex(r"[a-z][a-z0-9.-]{0,12}", fullmatch=True),
            min_size=1,
            max_size=4,
            unique=True,
        )
    )
    return AuditCase(
        case_id=draw(st.from_regex(r"us__s[0-9]{1,3}__[a-z_]{1,12}", fullmatch=True)),
        country=draw(st.sampled_from(["us", "uk"])),
        scenario_id=draw(st.from_regex(r"s[0-9]{1,3}", fullmatch=True)),
        variable=draw(st.from_regex(r"[a-z_]{1,20}", fullmatch=True)),
        metric_type=draw(st.sampled_from(["amount", "binary"])),
        reference_value=draw(st.sampled_from(["$0", "$1,234", "Yes", "No"])),
        reference_derivation=draw(TEXT),
        question=draw(TEXT),
        wrong_models=tuple(
            WrongModel(
                model=model,
                prediction=draw(st.sampled_from(["$250", "$0", "missing", "No"])),
                explanation=draw(TEXT),
            )
            for model in models
        ),
        grounding=draw(TEXT),
    )


@PROPERTY
@given(audit_cases())
def test_a_prompts_version_is_read_off_its_bytes(case):
    for version in JUDGE_TEMPLATE_HEADERS:
        prompt = render_case_prompt(case, template_version=version)
        assert prompt.startswith(template_header(version))
        assert template_version_of(prompt) == version
        assert template_version_of(prompt.encode("utf-8")) == version


@PROPERTY
@given(audit_cases())
def test_only_the_header_depends_on_the_version(case):
    bodies = {
        render_case_prompt(case, template_version=version)[len(header) :]
        for version, header in JUDGE_TEMPLATE_HEADERS.items()
    }
    assert len(bodies) == 1
    v1 = render_case_prompt(case, template_version=1)
    v2 = render_case_prompt(case, template_version=2)
    assert v2 == v1.replace(V1_REVIEW_CLAIM, "", 1)
    # The one deletion is the clause, where the header states it.
    start = v1.index(V1_REVIEW_CLAIM)
    assert v2 == v1[:start] + v1[start + len(V1_REVIEW_CLAIM) :]
    assert start == JUDGE_TEMPLATE_HEADERS[1].index(V1_REVIEW_CLAIM)


@PROPERTY
@given(st.binary(max_size=80))
def test_a_prompt_without_a_header_has_no_version(data):
    if not any(data.startswith(h.encode()) for h in JUDGE_TEMPLATE_HEADERS.values()):
        assert template_version_of(data) is None
    assert template_version_of(b"\xff\xfe" + data) is None


# --- prepare_audit ---------------------------------------------------------------


def _board(directory: Path, answers: dict[str, float]) -> Path:
    """A US run in which model m1 misses each scenario's $0 SNAP reference
    with the given answer."""
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"scenario_id": s, "variable": "snap", "value": 0.0} for s in answers]
    ).to_csv(directory / "reference_outputs.csv", index=False)
    pd.DataFrame(
        [
            {
                "model": "m1",
                "scenario_id": s,
                "variable": "snap",
                "prediction": answer,
                "explanation": f"Estimated {answer}.",
                "error": None,
            }
            for s, answer in answers.items()
        ]
    ).to_csv(directory / "predictions.csv", index=False)
    return directory


VERDICT = {
    "reference_suspect": False,
    "reference_bug_hypothesis": "",
    "case_failure_source": "llm_error",
    "case_failure_subtype": "thresholds_rates",
    "rationale": "Used the gross income test alone.",
    "models": [
        {
            "model": "m1",
            "failure_source": "llm_error",
            "failure_subtype": "thresholds_rates",
            "diagnosis": "Applied the 2025 threshold.",
        }
    ],
}
# How a seed case's verdict records its template: the sidecar it gets.
SEED_STATES = {
    "unjudged": None,
    "no sidecar": None,
    "v1, field absent": {},
    "v1": {TEMPLATE_VERSION_FIELD: 1},
    "v2": {TEMPLATE_VERSION_FIELD: 2},
    "unknown (null)": {TEMPLATE_VERSION_FIELD: None},
    "unknown (99)": {TEMPLATE_VERSION_FIELD: 99},
    "unknown (true)": {TEMPLATE_VERSION_FIELD: True},
}
# The version a state's prompt was rendered with: an unjudged case's is the
# current one, as prepare_audit writes it; an unknown one's is v1's bytes.
SEED_PROMPT_VERSION = {
    "unjudged": CURRENT_TEMPLATE_VERSION,
    "no sidecar": 1,
    "v1, field absent": 1,
    "v1": 1,
    "v2": 2,
    "unknown (null)": 1,
    "unknown (99)": 1,
    "unknown (true)": 1,
}


def _judge(case_dir: Path, sidecar: dict | None) -> None:
    """Write a verdict and, unless ``sidecar`` is None, its sidecar."""
    path = case_dir / "verdict.json"
    path.write_text(json.dumps(VERDICT, indent=2, sort_keys=True))
    if sidecar is not None:
        meta = {
            "judge_runner": "scripts/run_audit_claude.sh",
            "verdict_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            **sidecar,
        }
        (case_dir / "verdict.meta.json").write_text(json.dumps(meta))


def _seed(audit: Path, board: Path, states: dict[str, str]) -> dict[str, AuditCase]:
    """Prepare ``board`` into ``audit``, then give each scenario's case the
    prompt and verdict its state names. Returns the cases by scenario."""
    prepare_audit(board, audit, template_version=CURRENT_TEMPLATE_VERSION)
    cases = {case.scenario_id: case for case in build_audit_cases(board)}
    for scenario, state in states.items():
        case_dir = audit / "cases" / cases[scenario].case_id
        (case_dir / "prompt.md").write_text(
            render_case_prompt(
                cases[scenario], template_version=SEED_PROMPT_VERSION[state]
            )
        )
        if state != "unjudged":
            _judge(case_dir, SEED_STATES[state])
    return cases


def _tree(audit: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(audit)): path.read_bytes()
        for path in sorted(audit.rglob("*"))
        if path.is_file()
    }


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    st.dictionaries(
        st.sampled_from(["s0", "s1", "s2", "s3"]),
        st.tuples(st.sampled_from(sorted(SEED_STATES)), st.booleans()),
        min_size=1,
    ),
    st.sampled_from(sorted(JUDGE_TEMPLATE_HEADERS)),
)
def test_prepare_keeps_each_judged_case_on_its_own_template(plan, version):
    """Property over seed trees: a judged case whose case is unchanged keeps
    its prompt, verdict and sidecar bytes when its recorded version is known;
    every other case is (re-)opened on ``version``. The prepared tree
    validates, and preparing again changes nothing."""
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        board = _board(root / "us", {s: 250.0 for s in plan})
        audit = root / "audit"
        states = {scenario: state for scenario, (state, _) in plan.items()}
        before_cases = _seed(audit, board, states)
        before = _tree(audit)
        # Re-run m1 on the scenarios the plan changes: their prompts change.
        changed = {s for s, (_, change) in plan.items() if change}
        _board(board, {s: 999.0 if s in changed else 250.0 for s in plan})
        prepare_audit(board, audit, template_version=version)
        cases = {case.scenario_id: case for case in build_audit_cases(board)}
        after = _tree(audit)
        for scenario, state in states.items():
            case_dir = f"cases/{cases[scenario].case_id}"
            assert cases[scenario].case_id == before_cases[scenario].case_id
            recorded = (
                recorded_template_version(SEED_STATES[state])
                if state != "unjudged"
                else None
            )
            carried = recorded is not None and scenario not in changed
            if carried:
                for name in ("prompt.md", "verdict.json", "verdict.meta.json"):
                    key = f"{case_dir}/{name}"
                    assert after.get(key) == before.get(key), (state, name)
                assert template_version_of(after[f"{case_dir}/prompt.md"]) == recorded
            else:
                assert f"{case_dir}/verdict.json" not in after, state
                assert f"{case_dir}/verdict.meta.json" not in after, state
                assert after[f"{case_dir}/prompt.md"] == render_case_prompt(
                    cases[scenario], template_version=version
                ).encode("utf-8")
        assert template_version_problems(audit) == []
        assert prompt_hash_problems(audit) == []
        prepare_audit(board, audit, template_version=version)
        assert _tree(audit) == after


def test_a_new_audit_on_the_current_version_drops_the_claim(tmp_path):
    board = _board(tmp_path / "us", {"s0": 250.0, "s1": 100.0})
    audit = tmp_path / "audit"
    cases = prepare_audit(board, audit, template_version=CURRENT_TEMPLATE_VERSION)
    for case in cases:
        prompt = (audit / "cases" / case.case_id / "prompt.md").read_bytes()
        assert template_version_of(prompt) == CURRENT_TEMPLATE_VERSION == 2
        assert b"fixed before this run" not in prompt
        assert b"survived an adversarial review program" not in prompt


def test_a_requested_version_renders_new_cases_and_an_unknown_one_is_refused(
    tmp_path,
):
    board = _board(tmp_path / "us", {"s0": 250.0})
    audit = tmp_path / "audit"
    (case,) = prepare_audit(board, audit, template_version=1)
    prompt = (audit / "cases" / case.case_id / "prompt.md").read_text()
    assert prompt == render_case_prompt(case, template_version=1)
    assert "fixed before this run" in prompt
    with pytest.raises(ValueError, match="no judge template version 3"):
        prepare_audit(board, tmp_path / "other", template_version=3)
    assert not (tmp_path / "other").exists()


def test_a_v1_seed_carries_over_and_a_reopened_case_moves_to_v2(tmp_path):
    """The fold drivers' flow, for a driver that names v2: a seed judged on v1
    (its sidecar predates the field) is copied into a stage; the case a new
    model joins is re-opened on v2, and the other keeps the seed's bytes."""
    seed_board = _board(tmp_path / "seed" / "us", {"s0": 250.0, "s1": 100.0})
    seed = tmp_path / "seed" / "audit"
    prepare_audit(seed_board, seed, template_version=1)
    for case_dir in (seed / "cases").iterdir():
        _judge(case_dir, {})
    stage = tmp_path / "stage" / "audit"
    stage.mkdir(parents=True)
    for case_dir in (seed / "cases").iterdir():
        target = stage / "cases" / case_dir.name
        target.mkdir(parents=True)
        for name in ("prompt.md", "verdict.json", "verdict.meta.json"):
            (target / name).write_bytes((case_dir / name).read_bytes())
    board = _board(tmp_path / "stage" / "us", {"s0": 250.0, "s1": 100.0})
    # A new model misses s0 and answers s1's $0 reference exactly.
    predictions = pd.read_csv(board / "predictions.csv")
    new = predictions.assign(model="new")
    new.loc[new.scenario_id == "s1", "prediction"] = 0.0
    pd.concat([predictions, new]).to_csv(board / "predictions.csv", index=False)
    cases = {
        case.scenario_id: case
        for case in prepare_audit(board, stage, template_version=2)
    }
    kept, reopened = (stage / "cases" / cases[s].case_id for s in ("s1", "s0"))
    for name in ("prompt.md", "verdict.json", "verdict.meta.json"):
        assert (kept / name).read_bytes() == (
            seed / "cases" / kept.name / name
        ).read_bytes()
    assert template_version_of((kept / "prompt.md").read_bytes()) == 1
    assert not (reopened / "verdict.json").exists()
    assert (reopened / "prompt.md").read_text() == render_case_prompt(
        cases["s0"], template_version=2
    )
    assert template_version_problems(stage) == []


# --- A mixed tree ----------------------------------------------------------------


def _mixed_tree(tmp_path: Path) -> tuple[Path, Path, dict[str, AuditCase]]:
    board = _board(tmp_path / "us", {f"s{i}": 250.0 + i for i in range(5)})
    audit = tmp_path / "audit"
    cases = _seed(
        audit,
        board,
        {
            "s0": "no sidecar",
            "s1": "v1, field absent",
            "s2": "v1",
            "s3": "v2",
            "s4": "unjudged",
        },
    )
    return board, audit, cases


def test_a_mixed_tree_validates_and_collects(tmp_path):
    board, audit, cases = _mixed_tree(tmp_path)
    assert template_version_problems(audit) == []
    out = collect_audit(board, audit)
    assert out["template"].empty
    assert list(out["template"].columns) == ["case_id", "problem"]
    assert sorted(out["missing"]["case_id"]) == [cases["s4"].case_id]
    assert len(out["case"]) == 4
    # Preparing it again, on either version, keeps every verdict: each judged
    # case renders to its bytes on the version it records. Only the unjudged
    # case follows the version the caller names.
    before = _tree(audit)
    unjudged = f"cases/{cases['s4'].case_id}/prompt.md"
    for version in sorted(JUDGE_TEMPLATE_HEADERS):
        prepare_audit(board, audit, template_version=version)
        after = _tree(audit)
        assert after[unjudged] == render_case_prompt(
            cases["s4"], template_version=version
        ).encode("utf-8")
        assert {k: v for k, v in after.items() if k != unjudged} == {
            k: v for k, v in before.items() if k != unjudged
        }
    assert _tree(audit) == before
    _collect_cli(board, audit, tmp_path / "out")
    assert (tmp_path / "out" / "us_audit_case_annotations.csv").is_file()


def test_a_verdict_whose_template_disagrees_with_its_prompt_is_flagged(tmp_path):
    board, audit, cases = _mixed_tree(tmp_path)
    case_dir = {s: audit / "cases" / case.case_id for s, case in cases.items()}

    def meta(scenario: str, **fields) -> None:
        path = case_dir[scenario] / "verdict.meta.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), **fields}))

    meta("s1", judge_template_version=2)  # records v2 on a v1 prompt
    sidecar = case_dir["s3"] / "verdict.meta.json"
    stripped = json.loads(sidecar.read_text())
    del stripped[TEMPLATE_VERSION_FIELD]
    sidecar.write_text(json.dumps(stripped))  # v2 prompt, field absent (v1)
    meta("s2", judge_template_version="2")  # names no version
    (case_dir["s0"] / "prompt.md").unlink()  # a verdict without its prompt
    (case_dir["s4"] / "verdict.json").write_text(json.dumps(VERDICT))
    (case_dir["s4"] / "prompt.md").write_text("Classify this miss.\n")
    problems = dict(template_version_problems(audit))
    assert problems == {
        cases["s0"].case_id: "a verdict without prompt.md",
        cases["s1"].case_id: "prompt.md is v1, but its verdict records v2",
        cases["s2"].case_id: (
            "its sidecar's judge_template_version '2' names no template "
            "version ([1, 2])"
        ),
        cases["s3"].case_id: "prompt.md is v2, but its verdict records v1",
        cases["s4"].case_id: "prompt.md is no template version, but its verdict "
        "records v1",
    }
    out = collect_audit(board, audit)
    assert dict(out["template"].itertuples(index=False)) == problems
    with pytest.raises(SystemExit, match="5 verdicts disagree with their prompt.md"):
        _collect_cli(board, audit, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    # Preparing again re-opens every flagged case. The verdict that lost its
    # prompt has no sidecar, so nothing records the bytes its judge read.
    prepare_audit(board, audit, template_version=2)
    assert template_version_problems(audit) == []
    for scenario in ("s0", "s1", "s2", "s3", "s4"):
        assert not (case_dir[scenario] / "verdict.json").exists(), scenario
        assert (case_dir[scenario] / "prompt.md").read_bytes() == render_case_prompt(
            cases[scenario], template_version=2
        ).encode("utf-8")


def _judged_case(tmp_path: Path, answer: float = 250.0, **sidecar):
    """A one-case board whose case is judged on v1, with ``sidecar``'s fields
    in its sidecar. Returns the board, the audit, the case and its dir."""
    board = _board(tmp_path / "us", {"s0": answer})
    audit = tmp_path / "audit"
    (case,) = prepare_audit(board, audit, template_version=1)
    case_dir = audit / "cases" / case.case_id
    _judge(case_dir, {TEMPLATE_VERSION_FIELD: 1, **sidecar})
    return board, audit, case, case_dir


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_a_verdict_without_its_prompt_stands_only_on_its_recorded_hash(tmp_path):
    """Without prompt.md, the sidecar's prompt_sha256 is the only record of
    what the judge read. A verdict whose hash is the case rendered on its
    version keeps its files, and its prompt comes back byte for byte; one
    with no hash, or another hash, is re-opened."""
    for name, recorded in (
        ("matching", "v1"),
        ("no hash", None),
        ("another hash", "v2"),
    ):
        root = tmp_path / name.replace(" ", "-")
        board = _board(root / "us", {"s0": 250.0})
        audit = root / "audit"
        (case,) = prepare_audit(board, audit, template_version=1)
        case_dir = audit / "cases" / case.case_id
        renders = {
            v: render_case_prompt(case, template_version=v).encode("utf-8")
            for v in JUDGE_TEMPLATE_HEADERS
        }
        fields = {TEMPLATE_VERSION_FIELD: 1}
        if recorded is not None:
            fields["prompt_sha256"] = _sha256(renders[int(recorded[1])])
        _judge(case_dir, fields)
        verdict = (case_dir / "verdict.json").read_bytes()
        (case_dir / "prompt.md").unlink()
        assert dict(template_version_problems(audit)) == {
            case.case_id: "a verdict without prompt.md"
        }
        prepare_audit(board, audit, template_version=2)
        if recorded == "v1":
            assert (case_dir / "verdict.json").read_bytes() == verdict, name
            assert (case_dir / "prompt.md").read_bytes() == renders[1], name
        else:
            assert not (case_dir / "verdict.json").exists(), name
            assert not (case_dir / "verdict.meta.json").exists(), name
            assert (case_dir / "prompt.md").read_bytes() == renders[2], name
        assert template_version_problems(audit) == []


def test_a_changed_case_without_its_prompt_is_reopened(tmp_path):
    """The review's case: a verdict judged on m1's $250 answer loses its
    prompt.md, and m1 is re-run and answers $999. The case renders anew, so
    the verdict is dropped, even though its sidecar hashes the old prompt."""
    board, audit, case, case_dir = _judged_case(tmp_path)
    old = (case_dir / "prompt.md").read_bytes()
    meta = json.loads((case_dir / "verdict.meta.json").read_text())
    meta["prompt_sha256"] = _sha256(old)
    (case_dir / "verdict.meta.json").write_text(json.dumps(meta))
    (case_dir / "prompt.md").unlink()
    _board(board, {"s0": 999.0})
    (changed,) = prepare_audit(board, audit, template_version=1)
    assert changed.case_id == case.case_id
    assert not (case_dir / "verdict.json").exists()
    assert not (case_dir / "verdict.meta.json").exists()
    new = (case_dir / "prompt.md").read_bytes()
    assert new != old and b"999" in new


def test_a_sidecar_hash_that_is_not_the_prompt_reopens_the_case(tmp_path):
    """A prompt.md that renders right but is not the bytes the sidecar says
    its judge read is not the verdict's prompt."""
    board, audit, case, case_dir = _judged_case(tmp_path, prompt_sha256="0" * 64)
    prepare_audit(board, audit, template_version=1)
    assert not (case_dir / "verdict.json").exists()


def test_collect_refuses_a_verdict_published_on_rewritten_bytes(tmp_path):
    """The review's race: a runner's judge reads the $250 case on v1; an
    audit-prepare racing it re-runs m1 at $999 and rewrites prompt.md, on the
    same version; then the runner publishes. The verdict's sidecar truthfully
    hashes the $250 prompt, so audit-collect refuses it, and audit-prepare
    re-opens it."""
    board = _board(tmp_path / "us", {"s0": 250.0})
    audit = tmp_path / "audit"
    (case,) = prepare_audit(board, audit, template_version=1)
    case_dir = audit / "cases" / case.case_id
    judged = (case_dir / "prompt.md").read_bytes()
    _board(board, {"s0": 999.0})
    prepare_audit(board, audit, template_version=1)
    rewritten = (case_dir / "prompt.md").read_bytes()
    assert rewritten != judged
    _judge(case_dir, {TEMPLATE_VERSION_FIELD: 1, "prompt_sha256": _sha256(judged)})
    assert template_version_problems(audit) == []
    problem = "prompt.md is not the bytes its judge read (its sidecar's prompt_sha256)"
    assert prompt_hash_problems(audit) == [(case.case_id, problem)]
    out = collect_audit(board, audit)
    assert list(out["prompt_hash"].itertuples(index=False)) == [(case.case_id, problem)]
    with pytest.raises(SystemExit, match="1 verdicts disagree with their prompt.md"):
        _collect_cli(board, audit, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    prepare_audit(board, audit, template_version=1)
    assert not (case_dir / "verdict.json").exists()
    assert (case_dir / "prompt.md").read_bytes() == rewritten
    assert prompt_hash_problems(audit) == []


def test_prepare_racing_a_publish_never_strands_the_verdict(tmp_path):
    """The round-3 review's schedule, step by step. A $250 case holds a
    truncated verdict.json. A runner's judge reads the $250 v1 prompt and the
    runner publishes its sidecar. Before its verdict arrives, an
    audit-prepare re-runs m1 at $999 on v1: it drops the truncated verdict
    but leaves the sidecar, which describes another verdict. Then the
    runner's verdict arrives. It still has its sidecar, whose prompt hash is
    the $250 prompt's, so audit-collect refuses it and the next preparation
    re-opens it."""
    board = _board(tmp_path / "us", {"s0": 250.0})
    audit = tmp_path / "audit"
    (case,) = prepare_audit(board, audit, template_version=1)
    case_dir = audit / "cases" / case.case_id
    judged = (case_dir / "prompt.md").read_bytes()
    (case_dir / "verdict.json").write_text("{")
    verdict = json.dumps(VERDICT, indent=2, sort_keys=True).encode()
    sidecar = {
        "judge_runner": "scripts/run_audit_codex.sh",
        "verdict_sha256": _sha256(verdict),
        "prompt_sha256": _sha256(judged),
        TEMPLATE_VERSION_FIELD: 1,
    }
    (case_dir / "verdict.meta.json").write_text(json.dumps(sidecar))
    _board(board, {"s0": 999.0})
    prepare_audit(board, audit, template_version=1)
    assert not (case_dir / "verdict.json").exists()
    assert json.loads((case_dir / "verdict.meta.json").read_text()) == sidecar
    (case_dir / "verdict.json").write_bytes(verdict)
    assert [case_id for case_id, _ in prompt_hash_problems(audit)] == [case.case_id]
    with pytest.raises(SystemExit, match="1 verdicts disagree with their prompt.md"):
        _collect_cli(board, audit, tmp_path / "out")
    prepare_audit(board, audit, template_version=1)
    assert not (case_dir / "verdict.json").exists()
    assert not (case_dir / "verdict.meta.json").exists()


def test_a_dropped_verdict_takes_only_its_own_sidecar(tmp_path):
    """Re-opening a case removes its sidecar when the sidecar describes the
    verdict (verdict_sha256) or records no verdict_sha256, as legacy sidecars
    do; a sidecar describing another verdict stays for its runner."""
    for name, verdict_sha256, stays in (
        ("own", "verdict", False),
        ("legacy", None, False),
        ("another verdict's", "0" * 64, True),
    ):
        root = tmp_path / name.replace(" ", "-").replace("'", "")
        board, audit, case, case_dir = _judged_case(root)
        meta = json.loads((case_dir / "verdict.meta.json").read_text())
        if verdict_sha256 is None:
            del meta["verdict_sha256"]
        elif verdict_sha256 != "verdict":
            meta["verdict_sha256"] = verdict_sha256
        (case_dir / "verdict.meta.json").write_text(json.dumps(meta))
        _board(board, {"s0": 999.0})
        prepare_audit(board, audit, template_version=1)
        assert not (case_dir / "verdict.json").exists(), name
        assert (case_dir / "verdict.meta.json").exists() == stays, name


def test_a_verdict_its_sidecar_does_not_describe_is_reopened(tmp_path):
    """An unchanged case whose verdict.json is not the verdict its sidecar
    describes is re-opened; the sidecar, another verdict's, stays."""
    board, audit, case, case_dir = _judged_case(tmp_path)
    (case_dir / "verdict.json").write_text(json.dumps({**VERDICT, "rationale": "x"}))
    prepare_audit(board, audit, template_version=1)
    assert not (case_dir / "verdict.json").exists()
    assert (case_dir / "verdict.meta.json").exists()


def test_prompts_compare_and_keep_exact_bytes(tmp_path):
    """Byte equality, with no newline translation either way: a case whose
    text holds a carriage return keeps its verdict and its prompt's bytes on
    every preparation; a prompt.md with CRLF line endings is not the case's
    rendering, so its verdict is re-opened and the prompt rewritten exactly."""
    board = _board(tmp_path / "us", {"s0": 250.0})
    predictions = pd.read_csv(board / "predictions.csv")
    predictions["explanation"] = "Gross income\rtest only."
    predictions.to_csv(board / "predictions.csv", index=False)
    audit = tmp_path / "audit"
    (case,) = prepare_audit(board, audit, template_version=1)
    rendered = render_case_prompt(case, template_version=1).encode("utf-8")
    assert b"Gross income\rtest only." in rendered
    case_dir = audit / "cases" / case.case_id
    assert (case_dir / "prompt.md").read_bytes() == rendered
    _judge(case_dir, {TEMPLATE_VERSION_FIELD: 1, "prompt_sha256": _sha256(rendered)})
    before = _tree(audit)
    for version in sorted(JUDGE_TEMPLATE_HEADERS):
        prepare_audit(board, audit, template_version=version)
        assert _tree(audit) == before, version
    (case_dir / "prompt.md").write_bytes(rendered.replace(b"\n", b"\r\n"))
    prepare_audit(board, audit, template_version=1)
    assert not (case_dir / "verdict.json").exists()
    assert (case_dir / "prompt.md").read_bytes() == rendered


def _collect_cli(board: Path, audit: Path, out: Path) -> None:
    from policybench import cli

    argv = ["policybench", "audit-collect", "--country-dir", str(board)]
    argv += ["--audit-dir", str(audit), "--output-dir", str(out)]
    with mock.patch.object(sys, "argv", argv):
        cli.main()


def test_audit_prepare_requires_a_template_version(tmp_path, capsys):
    from policybench import cli

    board = _board(tmp_path / "us", {"s0": 250.0})
    for version in sorted(JUDGE_TEMPLATE_HEADERS):
        audit = tmp_path / f"audit-{version}"
        argv = ["policybench", "audit-prepare", "--country-dir", str(board)]
        argv += ["--audit-dir", str(audit), "--template-version", str(version)]
        with mock.patch.object(sys, "argv", argv):
            cli.main()
        (prompt,) = (audit / "cases").glob("*/prompt.md")
        assert template_version_of(prompt.read_bytes()) == version
        assert f"on judge template v{version}." in capsys.readouterr().out
    # No flag: argparse refuses before anything is written.
    argv = ["policybench", "audit-prepare", "--country-dir", str(board)]
    argv += ["--audit-dir", str(tmp_path / "audit-none")]
    with mock.patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as refused:
            cli.main()
    assert refused.value.code == 2
    assert "--template-version" in capsys.readouterr().err
    assert not (tmp_path / "audit-none").exists()
    argv = ["policybench", "audit-prepare", "--country-dir", str(board)]
    argv += ["--audit-dir", str(tmp_path / "audit-9"), "--template-version", "9"]
    with mock.patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit, match="no judge template version 9"):
            cli.main()
    assert not (tmp_path / "audit-9").exists()


# --- Version selection is explicit, never inferred ------------------------------


def test_the_renderers_have_no_default_version():
    """Every renderer takes the version as a required keyword: none falls back
    to CURRENT_TEMPLATE_VERSION, so adding a version moves no caller."""
    for function in (render_case_prompt, prepare_audit):
        parameter = inspect.signature(function).parameters["template_version"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, function.__name__
        assert parameter.default is inspect.Parameter.empty, function.__name__


def test_a_renderer_called_without_a_version_is_refused(tmp_path):
    board = _board(tmp_path / "us", {"s0": 250.0})
    (case,) = build_audit_cases(board)
    with pytest.raises(TypeError, match="template_version"):
        render_case_prompt(case)
    with pytest.raises(TypeError):
        render_case_prompt(case, CURRENT_TEMPLATE_VERSION)  # not by name
    with pytest.raises(TypeError, match="template_version"):
        prepare_audit(board, tmp_path / "audit")
    assert not (tmp_path / "audit").exists()


# The modules outside the tests that render judge prompts, and their calls.
RENDERER_CALLS = {
    "policybench/audit.py": {"render_case_prompt": 2},
    "policybench/cli.py": {"prepare_audit": 1},
    "scripts/finish_adds0928.py": {"prepare_audit": 1},
    "scripts/finish_gpt61sol.py": {"prepare_audit": 1},
    "scripts/finish_haiku55.py": {"prepare_audit": 2, "render_case_prompt": 1},
}
RENDERERS = ("render_case_prompt", "prepare_audit")


def _called_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def test_every_renderer_call_names_its_version():
    """Static: every call of render_case_prompt or prepare_audit in
    policybench/, scripts/ and reference_audit/ passes template_version by
    name, and no value passed is read off a prompt (template_version_of)."""
    found: dict[str, dict[str, int]] = {}
    paths = [
        path
        for part in ("policybench", "scripts", "reference_audit")
        for path in sorted((ROOT / part).rglob("*.py"))
    ]
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        for call in ast.walk(ast.parse(path.read_text(), filename=relative)):
            if not isinstance(call, ast.Call) or _called_name(call) not in RENDERERS:
                continue
            name = _called_name(call)
            counts = found.setdefault(relative, {})
            counts[name] = counts.get(name, 0) + 1
            keywords = {k.arg: k.value for k in call.keywords}
            where = f"{relative}:{call.lineno} {name}"
            assert "template_version" in keywords, f"{where} names no version"
            inferred = [
                node
                for node in ast.walk(keywords["template_version"])
                if isinstance(node, ast.Call)
                and _called_name(node) == "template_version_of"
            ]
            assert not inferred, f"{where} reads its version off a prompt"
    for relative, counts in RENDERER_CALLS.items():
        assert found.get(relative) == counts, relative


# Where Python code may read a version off a prompt: only to check a tree.
# (The runners' embedded Python also records what a judge read.)
TEMPLATE_VERSION_OF_CALLERS = {("policybench/audit.py", "template_version_problems")}


def test_only_the_tree_check_reads_a_version_off_a_prompt():
    """Static, closing the scan's gap for a version read into a variable and
    passed on: template_version_of is called nowhere in policybench/,
    scripts/ or reference_audit/ but in template_version_problems, which
    renders nothing."""
    callers = set()
    for part in ("policybench", "scripts", "reference_audit"):
        for path in sorted((ROOT / part).rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(), filename=relative)
            for function in ast.walk(tree):
                if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                for call in ast.walk(function):
                    if (
                        isinstance(call, ast.Call)
                        and _called_name(call) == "template_version_of"
                        and function.name != "template_version_of"
                    ):
                        callers.add((relative, function.name))
            module_level = [
                node
                for node in tree.body
                if not isinstance(
                    node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
                )
            ]
            for node in module_level:
                for call in ast.walk(node):
                    if (
                        isinstance(call, ast.Call)
                        and _called_name(call) == "template_version_of"
                    ):
                        callers.add((relative, "<module>"))
    assert callers == TEMPLATE_VERSION_OF_CALLERS


# The release drivers of releases judged before versions existed: each
# judged every verdict on v1.
V1_DRIVERS = (
    "scripts/finish_adds0928.py",
    "scripts/finish_gpt61sol.py",
    "scripts/finish_haiku55.py",
)


def test_each_past_release_driver_renders_on_v1_by_name():
    """Each driver states the version its release was judged on as the
    module constant JUDGE_TEMPLATE_VERSION = 1, and passes that constant, not
    a literal or another value, to every renderer it calls."""
    for relative in V1_DRIVERS:
        tree = ast.parse((ROOT / relative).read_text(), filename=relative)
        (value,) = [
            node.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and [getattr(t, "id", None) for t in node.targets]
            == ["JUDGE_TEMPLATE_VERSION"]
        ]
        assert isinstance(value, ast.Constant) and value.value == 1, relative
        calls = [
            call
            for call in ast.walk(tree)
            if isinstance(call, ast.Call) and _called_name(call) in RENDERERS
        ]
        assert calls, relative
        for call in calls:
            (named,) = [k.value for k in call.keywords if k.arg == "template_version"]
            assert isinstance(named, ast.Name), (relative, call.lineno)
            assert named.id == "JUDGE_TEMPLATE_VERSION", (relative, call.lineno)


# A judged case's prompt.md, as the property draws it.
PROMPT_KINDS = (
    "v1",
    "v2",
    "v1 + text",
    "v2 + text",
    "v1 CRLF",
    "v2 CRLF",
    "no header",
    "missing",
)
JUDGED_STATES = sorted(state for state in SEED_STATES if state != "unjudged")
# What the sidecar's prompt_sha256 hashes: nothing (no field), each version's
# rendering of the case, or bytes no prompt has.
HASHES = (None, "v1", "v2", "other")


@PROPERTY
@given(
    st.sampled_from(JUDGED_STATES),
    st.sampled_from(PROMPT_KINDS),
    st.sampled_from(HASHES),
    st.booleans(),
    st.sampled_from(sorted(JUDGE_TEMPLATE_HEADERS)),
    TEXT,
)
def test_a_verdict_is_kept_on_its_recorded_version_alone(
    state, kind, hashed, described, version, text
):
    """Never inferred, and byte for byte: prepare_audit keeps an unchanged
    judged case's verdict exactly when the case rendered on the version its
    sidecar records is the bytes its judge read. Those are prompt.md's bytes,
    which must also hash to the sidecar's prompt_sha256 when it records one;
    without prompt.md, that hash alone. A prompt.md on another version is
    re-opened, though template_version_of reads a version off it and though
    the caller may name that very version, and so is a CRLF copy. A sidecar
    must also describe the verdict (its verdict_sha256); when ``described``
    is false, verdict.json is another verdict. A kept case's files are
    untouched. A re-opened case loses its verdict, and its sidecar unless the
    sidecar describes another verdict; it renders on the caller's version."""
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        board = _board(root / "us", {"s0": 250.0})
        audit = root / "audit"
        (case,) = prepare_audit(board, audit, template_version=version)
        case_dir = audit / "cases" / case.case_id
        renders = {
            v: render_case_prompt(case, template_version=v).encode("utf-8")
            for v in JUDGE_TEMPLATE_HEADERS
        }
        if kind == "missing":
            prompt = None
        elif kind == "no header":
            prompt = f"Classify this miss.\n{text}".encode()
        else:
            prompt = renders[int(kind[1])]
            if kind.endswith("+ text"):
                prompt += f"\n{text}.".encode()
            if kind.endswith("CRLF"):
                prompt = prompt.replace(b"\n", b"\r\n")
        if prompt is None:
            (case_dir / "prompt.md").unlink()
        else:
            (case_dir / "prompt.md").write_bytes(prompt)
        sidecar = SEED_STATES[state]
        recorded_sha256 = None
        if sidecar is not None and hashed is not None:
            recorded_sha256 = (
                "0" * 64 if hashed == "other" else _sha256(renders[int(hashed[1])])
            )
            sidecar = {**sidecar, "prompt_sha256": recorded_sha256}
        _judge(case_dir, sidecar)
        if not described:
            (case_dir / "verdict.json").write_text(
                json.dumps({**VERDICT, "rationale": "Another verdict."})
            )
        other_verdict = sidecar is not None and not described
        before = _tree(audit)
        recorded = recorded_template_version(sidecar)
        judged = renders.get(recorded)
        kept = (
            not other_verdict
            and judged is not None
            and recorded_sha256 in (None, _sha256(judged))
            and (prompt == judged if prompt is not None else bool(recorded_sha256))
        )
        prepare_audit(board, audit, template_version=version)
        after = _tree(audit)
        where = (state, kind, hashed, described)
        if kept:
            restored = {f"cases/{case.case_id}/prompt.md": judged}
            assert after == {**before, **restored}, where
        else:
            assert not (case_dir / "verdict.json").exists(), where
            assert (case_dir / "verdict.meta.json").exists() == other_verdict, where
            assert (case_dir / "prompt.md").read_bytes() == renders[version]
        assert template_version_problems(audit) == []
        assert prompt_hash_problems(audit) == []


# --- Every committed prompt re-renders on its recorded version ------------------

RUN_NAME = "us_full_run_20260612_policyengine_4_16_1_populace"
BOARD_PATH = Path("paper/snapshot/20260501/runs") / RUN_NAME
ANNOTATIONS_PATH = Path("annotations") / RUN_NAME
# The board files an audit renders from, and the annotations beside them.
BOARD_FILES = (
    "reference_outputs.csv",
    "reference_outputs.csv.meta.json",
    "reference_exclusions.json",
    "scenarios.csv",
    "scenarios.csv.meta.json",
    "predictions.csv.gz",
)
ANNOTATION_FILES = (
    "us_audit_row_annotations.csv",
    "us_case_notes.csv",
    "us_case_reference_explanations.csv",
    "us_adjudications.json",
)
# Each release PR's squash on main, which commits the board the release's
# audit renders from. A dashboard-data tag marks main when its GitHub release
# was cut, before that merge, so it does not hold the release's board.
RELEASE_COMMITS = {
    "20260929": "d616e67c33b6f80dabf5cb7329f069f9a1de069d",
    "20260930": "8b4c0ca146bb6f66deba6ce24009d49d70d92df2",
    "20261010": "5a8164a001efb27fa55f47fe7ea26666a0de31f8",
}
# The audit grounding these releases rendered with, which the release drivers
# pin as GROUNDING_SHA256. It is not committed, so rendering is local only.
GROUNDING = Path(
    "/Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit/"
    "grounding.csv"
)
GROUNDING_SHA256 = "b1e4a9bc74d762f410524a147efcda7d705c3afcfa3dc27f720fa60c54a7b55c"


def _seed_records(path: str) -> dict[str, dict]:
    """A committed seed digest: each judged case's prompt and verdict sha256."""
    lines = (ROOT / path).read_text().splitlines()
    assert lines[0] == "case_id,prompt_sha256,verdict_sha256"
    return {
        case: {"prompt_sha256": prompt, "verdict_sha256": verdict}
        for case, prompt, verdict in (line.split(",") for line in lines[1:])
    }


def _provenance_records(path: str) -> dict[str, dict]:
    """A committed judge provenance record: each re-judged verdict's entry."""
    verdicts = json.loads((ROOT / path).read_text())["verdicts"]
    records = {entry["case_id"]: entry for entry in verdicts}
    assert len(records) == len(verdicts), path
    return records


def _committed_prompts() -> dict[str, dict[str, dict]]:
    """Every committed prompt record, by the release whose audit holds it.

    Release 20260929's audit is docs/gpt61sol/seed_digest.csv. Release
    20260930 re-judged the cases docs/gpt61sol/judge_provenance.json lists
    and carried the rest; release 20261006 carried that audit, as
    docs/haiku55/seed_digest.csv records. Release 20261010 re-judged the
    cases docs/haiku55/judge_provenance.json lists and carried the rest.
    """
    seed_0929 = _seed_records("docs/gpt61sol/seed_digest.csv")
    seed_1006 = _seed_records("docs/haiku55/seed_digest.csv")
    return {
        "20260929": seed_0929,
        "20260930": {
            **seed_0929,
            **_provenance_records("docs/gpt61sol/judge_provenance.json"),
        },
        "20261006": seed_1006,
        "20261010": {
            **seed_1006,
            **_provenance_records("docs/haiku55/judge_provenance.json"),
        },
    }


def test_the_committed_prompt_records_agree_and_name_a_version():
    """Runs anywhere: each committed record names a known template version
    (none records the field, so each records v1), and release 20261006's
    seed digest is release 20260930's audit: release 20260929's digest with
    the prompts and verdicts of the cases release 20260930 re-judged."""
    committed = _committed_prompts()
    assert {release: len(records) for release, records in committed.items()} == {
        "20260929": 674,
        "20260930": 674,
        "20261006": 674,
        # The seed's 674 and three cases release 20261010 added.
        "20261010": 677,
    }
    for records in committed.values():
        for case, record in records.items():
            assert recorded_template_version(record) == 1, case
    digests = {
        release: {
            case: (record["prompt_sha256"], record["verdict_sha256"])
            for case, record in records.items()
        }
        for release, records in committed.items()
    }
    assert digests["20261006"] == digests["20260930"]


@functools.cache
def _blob(commit: str, path: Path) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{path.as_posix()}"],
        capture_output=True,
    )
    if result.returncode:
        pytest.fail(
            f"cannot read {path} at {commit[:12]}; fetch full history (git fetch "
            f"--unshallow): {result.stderr.decode().strip()}"
        )
    return result.stdout


@contextlib.contextmanager
def _object_strings():
    """Render as the release drivers did: with pandas' inferred Arrow strings
    off."""
    if hasattr(pd.options, "future") and hasattr(pd.options.future, "infer_string"):
        with pd.option_context("future.infer_string", False):
            yield
    else:
        yield


@pytest.mark.slow
@pytest.mark.parametrize("release", sorted(RELEASE_COMMITS))
def test_every_committed_prompt_rerenders_on_its_recorded_version(tmp_path, release):
    """Local only: release ``release``'s board, read from the commit that
    committed it, renders every judged case of its audit, on the version its
    committed record names, to the prompt sha256 that record commits; and it
    renders no other case. Release 20261006 judged nothing: it carried
    release 20260930's audit, which test_the_committed_prompt_records_agree
    checks, while rewording nine explanations that release 20261010
    re-opened, so its own board is not one an audit was rendered from."""
    if not GROUNDING.is_file():
        pytest.skip("the audit grounding is not on this machine")
    assert hashlib.sha256(GROUNDING.read_bytes()).hexdigest() == GROUNDING_SHA256
    commit = RELEASE_COMMITS[release]
    country_dir = tmp_path / RUN_NAME / "us"
    country_dir.mkdir(parents=True)
    for name in BOARD_FILES:
        (country_dir / name).write_bytes(_blob(commit, BOARD_PATH / name))
    (tmp_path / RUN_NAME / "annotations").mkdir()
    for name in ANNOTATION_FILES:
        (tmp_path / RUN_NAME / "annotations" / name).write_bytes(
            _blob(commit, ANNOTATIONS_PATH / name)
        )
    grounding = pd.read_csv(GROUNDING)
    lookup = {
        (str(r.scenario_id), str(r.variable)): str(r.grounding)
        for r in grounding.itertuples()
    }
    committed = _committed_prompts()[release]
    rendered = {}
    with _object_strings():
        for case in build_audit_cases(country_dir, grounding_lookup=lookup):
            if case.to_manifest_row()["parse_failure_only"]:
                continue
            record = committed.get(case.case_id)
            assert record is not None, f"{case.case_id} has no committed prompt"
            prompt = render_case_prompt(
                case, template_version=recorded_template_version(record)
            )
            rendered[case.case_id] = hashlib.sha256(prompt.encode()).hexdigest()
    expected = {case: record["prompt_sha256"] for case, record in committed.items()}
    assert sorted(rendered) == sorted(expected)
    differ = sorted(case for case in rendered if rendered[case] != expected[case])
    assert not differ, differ
