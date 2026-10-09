"""The diagnosis judge's template versions, and how a tree of verdicts keeps
the version each was judged on.

Invariants:
- a version's header never changes (pinned by sha256), and no header is a
  prefix of another, so a prompt's version is read off its bytes;
- the rest of a prompt does not depend on the version, and v2 is v1 without
  the review claim;
- prepare_audit keeps a judged case's prompt, verdict and sidecar bytes when
  the case re-renders to them with its recorded version (absent: v1), and
  renders every other case with the requested version (default: current);
- after prepare_audit, a tree validates (template_version_problems is empty),
  and a second prepare_audit changes nothing.
"""

from __future__ import annotations

import ast
import hashlib
import json
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
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\r"),
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
        prompt = render_case_prompt(case, version)
        assert prompt.startswith(template_header(version))
        assert template_version_of(prompt) == version
        assert template_version_of(prompt.encode("utf-8")) == version


@PROPERTY
@given(audit_cases())
def test_only_the_header_depends_on_the_version(case):
    bodies = {
        render_case_prompt(case, version)[len(header) :]
        for version, header in JUDGE_TEMPLATE_HEADERS.items()
    }
    assert len(bodies) == 1
    v1, v2 = render_case_prompt(case, 1), render_case_prompt(case, 2)
    assert v2 == v1.replace(V1_REVIEW_CLAIM, "", 1)
    assert render_case_prompt(case) == render_case_prompt(
        case, CURRENT_TEMPLATE_VERSION
    )


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
    prepare_audit(board, audit)
    cases = {case.scenario_id: case for case in build_audit_cases(board)}
    for scenario, state in states.items():
        case_dir = audit / "cases" / cases[scenario].case_id
        (case_dir / "prompt.md").write_text(
            render_case_prompt(cases[scenario], SEED_PROMPT_VERSION[state])
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
                    cases[scenario], version
                ).encode("utf-8")
        assert template_version_problems(audit) == []
        prepare_audit(board, audit, template_version=version)
        assert _tree(audit) == after


def test_new_cases_get_the_current_version(tmp_path):
    board = _board(tmp_path / "us", {"s0": 250.0, "s1": 100.0})
    audit = tmp_path / "audit"
    cases = prepare_audit(board, audit)
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
    assert prompt == render_case_prompt(case, 1)
    assert "fixed before this run" in prompt
    with pytest.raises(ValueError, match="no judge template version 3"):
        prepare_audit(board, tmp_path / "other", template_version=3)
    assert not (tmp_path / "other").exists()


def test_a_v1_seed_carries_over_and_a_reopened_case_moves_to_v2(tmp_path):
    """The fold drivers' flow: a seed judged on v1 (its sidecar predates the
    field) is copied into a stage; the case a new model joins is re-opened on
    v2, and the other keeps the seed's bytes."""
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
    cases = {case.scenario_id: case for case in prepare_audit(board, stage)}
    kept, reopened = (stage / "cases" / cases[s].case_id for s in ("s1", "s0"))
    for name in ("prompt.md", "verdict.json", "verdict.meta.json"):
        assert (kept / name).read_bytes() == (
            seed / "cases" / kept.name / name
        ).read_bytes()
    assert template_version_of((kept / "prompt.md").read_bytes()) == 1
    assert not (reopened / "verdict.json").exists()
    assert (reopened / "prompt.md").read_text() == render_case_prompt(cases["s0"], 2)
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
    # Preparing it again keeps every verdict: each case renders to its bytes.
    before = _tree(audit)
    prepare_audit(board, audit)
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
    # Preparing again re-opens every flagged case except the verdict that
    # lost its prompt, which keeps its verdict and gets its v1 prompt back.
    prepare_audit(board, audit)
    assert template_version_problems(audit) == []
    assert (case_dir["s0"] / "verdict.json").is_file()
    assert (case_dir["s0"] / "prompt.md").read_text() == render_case_prompt(
        cases["s0"], 1
    )
    for scenario in ("s1", "s2", "s3", "s4"):
        assert not (case_dir[scenario] / "verdict.json").exists(), scenario
        assert (case_dir[scenario] / "prompt.md").read_text() == render_case_prompt(
            cases[scenario], 2
        )


def _collect_cli(board: Path, audit: Path, out: Path) -> None:
    from policybench import cli

    argv = ["policybench", "audit-collect", "--country-dir", str(board)]
    argv += ["--audit-dir", str(audit), "--output-dir", str(out)]
    with mock.patch.object(sys, "argv", argv):
        cli.main()


def test_audit_prepare_takes_a_template_version(tmp_path, capsys):
    from policybench import cli

    board = _board(tmp_path / "us", {"s0": 250.0})
    for flag, version in ((["--template-version", "1"], 1), ([], 2)):
        audit = tmp_path / f"audit-{version}"
        argv = ["policybench", "audit-prepare", "--country-dir", str(board)]
        argv += ["--audit-dir", str(audit), *flag]
        with mock.patch.object(sys, "argv", argv):
            cli.main()
        (prompt,) = (audit / "cases").glob("*/prompt.md")
        assert template_version_of(prompt.read_bytes()) == version
    argv = ["policybench", "audit-prepare", "--country-dir", str(board)]
    argv += ["--audit-dir", str(tmp_path / "audit-9"), "--template-version", "9"]
    with mock.patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit, match="no judge template version 9"):
            cli.main()
