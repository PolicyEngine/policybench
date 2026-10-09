"""The Claude Haiku 5.5 addition moves an incumbent only as the ten records say.

Adapted from test_finish_gpt61sol.py. Synthetic data stands in for runs,
audits and payloads. Release 20261006 is read from git at BASE_COMMIT, never
from the working tree (the freeze rewrites it). Tests that read the seed
copy, the main clone's grounding or the live stage read them only, and skip
where they are absent.
"""

from __future__ import annotations

import contextlib
import copy
import functools
import gzip
import hashlib
import inspect
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import finish_gpt61sol as gpt61sol  # noqa: E402
import finish_haiku55 as driver  # noqa: E402
import release_20261006  # noqa: E402

from policybench.audit import AUDIT_OUTPUT_SCHEMA  # noqa: E402

NEW = "claude-haiku-5.5"
SLUG = "haiku55"
REPO = Path(__file__).resolve().parents[1]
BASE_COMMIT = driver.BASE_COMMIT
COMMITTED_SEED_DIGEST_SHA256 = driver.SEED_DIGEST_SHA256
SNAPSHOT_PATH = Path("paper/snapshot/20260501/runs") / driver.RUN_NAME
ADJUDICATIONS_PATH = Path("annotations") / driver.RUN_NAME / driver.ADJUDICATIONS
EXCLUSIONS_NAME = "reference_exclusions.json"
BOUND_EXCLUSIONS = f"publish/{driver.RUN_NAME}/us/{EXCLUSIONS_NAME}"
# Release 20261006's audit (the seed, a read-only copy), the grounding it was
# rendered with, the supervised runs root and the live stage. All local only;
# nothing here writes to them.
SEED = REPO / "results/local/release-haiku55/seed-20261006"
STAGE = REPO / "results/local/release-haiku55/stage"
GROUNDING = Path(
    "/Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit/"
    "grounding.csv"
)
RUNS = Path("/Users/maxghenis/PolicyEngine/policybench/results/local/haiku55-runs")
# The UTC day a test's adjudicate step says its decisions were written on;
# docs/haiku55/spec.json does not name one yet (see the xfail below).
WRITTEN_ON = "2026-10-09"
# The seven fields the ruling decides on an entry.
DECISION_FIELDS = (
    "adjudicated_failure_source",
    "adjudicated_failure_subtype",
    "adjudicated_on",
    "adjudicator",
    "excluded_from_scoring",
    "reference_verdict",
    "reference_basis",
)
SCENARIO_051 = ("scenario_051", "state_income_tax_before_refundable_credits")
CASE_051 = "us__scenario_051__state_income_tax_before_refundable_credits"


@functools.cache
def base_blob(path: Path) -> bytes:
    """A repository file as committed at BASE_COMMIT (release 20261006)."""
    result = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{BASE_COMMIT}:{path.as_posix()}"],
        capture_output=True,
    )
    if result.returncode:
        pytest.fail(
            f"cannot read {path} at base commit {BASE_COMMIT[:12]}; fetch full "
            f"history (git fetch --unshallow): {result.stderr.decode().strip()}"
        )
    return result.stdout


def base_references(directory: Path) -> Path:
    """Write release 20261006's five reference files into ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in driver.REFERENCE_FILES:
        (directory / name).write_bytes(base_blob(SNAPSHOT_PATH / name))
    return directory


def base_record() -> dict:
    """Release 20261006's exclusion record, a fresh copy each call."""
    return json.loads(base_blob(SNAPSHOT_PATH / EXCLUSIONS_NAME))


def base_adjudication_record() -> dict:
    """Release 20261006's adjudication record file, a fresh copy each call."""
    return json.loads(base_blob(ADJUDICATIONS_PATH))


def real_spec() -> dict:
    """docs/haiku55/spec.json as the working tree holds it."""
    return json.loads((REPO / driver.SPEC_PATH).read_text())


@functools.cache
def _release_text() -> str:
    with mock.patch.object(driver, "ROOT", REPO):
        record = driver.build_release_exclusions(base_record(), real_spec())
    return driver.exclusions_text(record)


def release_text() -> str:
    """The release's exclusion record as install-exclusions writes it,
    computed against the real repository whatever a test patched."""
    return _release_text()


def release_sha() -> str:
    return hashlib.sha256(release_text().encode()).hexdigest()


def ruled_case(item: dict) -> str:
    return f"us__{item['scenario_id']}__{item['variable']}"


RULED_CASES = frozenset(ruled_case(item) for item in real_spec()["adjudications"])
NEW_RULED_CASES = RULED_CASES - {CASE_051}


@pytest.fixture
def written_spec(monkeypatch):
    """The spec with the day its decisions were written, which the date
    conventions need."""
    spec = {**real_spec(), "adjudications_written_on": WRITTEN_ON}
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
    return spec


@pytest.fixture
def unruled_spec(monkeypatch):
    """A spec whose rulings decide no adjudication, so the gates ported from
    the GPT-6.1 Sol release see their own synthetic records only."""
    spec = {
        **real_spec(),
        "adjudications_written_on": WRITTEN_ON,
        "adjudications": [],
        "restated_adjudications": [],
    }
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
    return spec


def test_the_addition_is_haiku55_alone_on_a_47_model_board():
    assert driver.MODELS == {SLUG: NEW}
    assert driver.BASE_MODELS == 46 and driver.BOARD_MODELS == 47
    assert driver.BASE_OUTPUTS == 1984
    assert driver.BASE_EXCLUSIONS == 64 and driver.BASE_SCORED == 1920
    assert driver.NEW_EXCLUSIONS == 10 and driver.RELEASE_EXCLUSIONS == 74
    assert driver.RELEASE_SCORED == 1910
    assert driver.BASE_TAG == "dashboard-data-20261006"
    assert driver.BASE_COMMIT == "8b831f2cfaa071eb850ed85d4f29f874a1671e8d"
    assert driver.SEED_RELEASE_COMMIT == "8b4c0ca146bb6f66deba6ce24009d49d70d92df2"
    assert set(driver.BASE_REFERENCE_SHA256) == set(driver.REFERENCE_FILES)
    assert driver.JUDGE_MODEL == "claude-opus-5-5"
    assert len(driver.REWORDED_SINCE_SEED) == 9


def test_the_spec_names_this_drivers_release_and_base():
    """The freeze compares the spec's tag and base with the driver's."""
    spec = real_spec()
    assert spec["release_tag"] == driver.RELEASE_TAG
    assert spec["base_tag"] == driver.BASE_TAG
    assert spec["base_sha256"] == driver.BASE_SHA256
    assert spec["decided_on"] == "2026-10-06"


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="open item: docs/haiku55/spec.json does not name "
    "adjudications_written_on, which release_date_conventions, triage and the "
    "freeze read; remove this marker once it does",
)
def test_the_spec_names_the_day_the_decisions_were_written():
    written = real_spec().get("adjudications_written_on")
    assert isinstance(written, str) and re.fullmatch(r"2026-\d\d-\d\d", written)
    assert written >= real_spec()["decided_on"]


# --- Run discovery -------------------------------------------------------------


@pytest.fixture
def runs(tmp_path):
    root = tmp_path / "runs"
    directory = root / SLUG / "run"
    directory.mkdir(parents=True)
    (directory / "run_state.json").write_text(
        json.dumps(
            {"model": NEW, "completed": 100, "total": 100, "stopped_reason": None}
        )
    )
    (directory / "predictions.csv").write_text("model,scenario_id,variable\n")
    return root


def change_state(root, **changes):
    path = root / SLUG / "run/run_state.json"
    state = json.loads(path.read_text())
    state.update(changes)
    path.write_text(json.dumps(state))


def test_discovers_only_the_registered_model(runs):
    extra = runs / "sonnet55/run"
    extra.mkdir(parents=True)
    (extra / "run_state.json").write_text(json.dumps({"model": "claude-sonnet-5.5"}))
    found = driver.discover_new_models(runs)
    assert [(run.slug, run.model) for run in found] == [(SLUG, NEW)]
    assert found[0].predictions.parent == found[0].run_dir


@pytest.mark.parametrize(
    "changes",
    [
        {"completed": 99},
        {"completed": 38},
        {"stopped_reason": "budget exhausted"},
        {"stopped_reason": ""},
        {"stopped_reason": False},
        {"completed": 0, "total": 0},
        {"completed": -1, "total": -1},
        {"completed": True, "total": True},
        {"completed": 100.0, "total": 100.0},
        {"completed": "100", "total": "100"},
    ],
)
def test_an_incomplete_or_stopped_run_is_refused(runs, changes):
    change_state(runs, **changes)
    with pytest.raises(SystemExit, match="refusing incomplete additions"):
        driver.discover_new_models(runs)


@pytest.mark.parametrize(
    "model", ["claude-haiku-5", "claude-haiku-5-5", "claude-sonnet-5.5", "", None]
)
def test_the_wrong_model_in_a_run_state_is_refused(runs, model):
    change_state(runs, model=model)
    with pytest.raises(SystemExit, match="unexpected model"):
        driver.discover_new_models(runs)


@pytest.mark.parametrize("name", ["run_state.json", "predictions.csv"])
def test_a_missing_run_artifact_is_refused(runs, name):
    (runs / SLUG / "run" / name).unlink()
    with pytest.raises(SystemExit, match=SLUG):
        driver.discover_new_models(runs)


def test_scratch_completion_still_requires_completed_equal_total(runs):
    change_state(runs, completed=4, total=5, synthetic_partial=True)
    with pytest.raises(SystemExit, match="4/5"):
        driver.discover_new_models(runs)
    change_state(runs, completed=5)
    assert len(driver.discover_new_models(runs)) == 1


# --- Input pins ----------------------------------------------------------------


def test_pin_inputs_writes_the_finished_runs_file_hashes(runs, tmp_path, monkeypatch):
    """--step pin-inputs needs no stage: it hashes the finished run's
    predictions.csv and run_state.json and refuses an unfinished run."""
    pins = tmp_path / "input_pins.json"
    monkeypatch.setattr(driver, "INPUT_PINS", pins)
    driver.main(["--step", "pin-inputs", "--runs-root", str(runs)])
    record = json.loads(pins.read_text())
    assert record == driver.input_pins_record(runs)
    run = runs / SLUG / "run"
    assert record["inputs"] == {
        SLUG: {
            "run": f"runs/{SLUG}/run",
            "sha256": {
                name: hashlib.sha256((run / name).read_bytes()).hexdigest()
                for name in ("predictions.csv", "run_state.json")
            },
        }
    }
    change_state(runs, completed=99)
    with pytest.raises(SystemExit, match="refusing incomplete additions"):
        driver.main(["--step", "pin-inputs", "--runs-root", str(runs)])


def test_the_committed_input_pins_name_both_run_files():
    """Runs anywhere: the committed pins name Claude Haiku 5.5's two run
    files, as the design note gives them."""
    record = json.loads(driver.INPUT_PINS.read_text())
    assert set(record["inputs"]) == {SLUG}
    assert record["inputs"][SLUG]["run"] == f"haiku55-runs/{SLUG}/run"
    pins = record["inputs"][SLUG]["sha256"]
    assert set(pins) == {"predictions.csv", "run_state.json"}
    assert all(re.fullmatch("[0-9a-f]{64}", value) for value in pins.values())
    assert pins["predictions.csv"].startswith("27a5e48f")
    assert pins["predictions.csv"].endswith("8344")
    assert pins["run_state.json"].startswith("42f82f50")
    assert pins["run_state.json"].endswith("bd4e")
    assert driver.INPUT_PINS.read_text() == (
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )


def test_the_committed_input_pins_are_the_finished_runs():
    """Local only: recomputed from the run directory, the pins are the same."""
    if not (RUNS / SLUG / "run").is_dir():
        pytest.skip("Claude Haiku 5.5's run directory is not on this machine")
    assert driver.input_pins_record(RUNS) == json.loads(driver.INPUT_PINS.read_text())


@pytest.mark.slow
def test_the_stages_inputs_are_the_pinned_run():
    """Local only, read-only: the stage's copies are the pinned bytes, its
    prepare-time hashes hold, and its bundle rows are the run file's in every
    column (this reads the stage's 700 MB bundle predictions)."""
    if not (STAGE / "inputs" / SLUG).is_dir():
        pytest.skip("needs the Claude Haiku 5.5 stage")
    pins = json.loads(driver.INPUT_PINS.read_text())["inputs"][SLUG]["sha256"]
    for name, pin in pins.items():
        assert driver.digest(STAGE / "inputs" / SLUG / name) == pin
    driver.verify_prepared_inputs(STAGE)
    assert driver.new_model_row_differences(STAGE) == []


def commit(root: Path, message: str) -> str:
    """Commit everything in a scratch repository, with no user hooks or keys;
    return the new commit's sha."""
    git = ["git", "-C", str(root), "-c", "core.hooksPath=/dev/null"]
    git += ["-c", "commit.gpgsign=false", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "--allow-empty", "-qm", message], check=True)
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def pinned_repo(tmp_path, monkeypatch):
    """A git repository whose HEAD commits an input-pins file."""
    root = tmp_path / "repo"
    pins = root / driver.INPUT_PINS_PATH
    pins.parent.mkdir(parents=True)
    record = {"inputs": {SLUG: {"sha256": {"predictions.csv": "a" * 64}}}}
    record["inputs"][SLUG]["sha256"]["run_state.json"] = "b" * 64
    pins.write_text(json.dumps(record))
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    commit(root, "pins")
    monkeypatch.setattr(driver, "ROOT", root)
    monkeypatch.setattr(driver, "INPUT_PINS", pins)
    return pins, record


def test_the_input_pins_are_read_as_committed_at_head(pinned_repo):
    pins, record = pinned_repo
    assert driver.committed_input_pins() == {
        SLUG: {"predictions.csv": "a" * 64, "run_state.json": "b" * 64}
    }
    # Pins rewritten and not committed are refused, not silently ignored.
    record["inputs"][SLUG]["sha256"]["predictions.csv"] = "c" * 64
    pins.write_text(json.dumps(record))
    with pytest.raises(SystemExit, match="differs from its HEAD commit; commit it"):
        driver.committed_input_pins()


def test_input_pins_never_committed_are_refused(pinned_repo, monkeypatch):
    pins, _ = pinned_repo
    elsewhere = pins.with_name("other_pins.json")
    elsewhere.write_text(pins.read_text())
    monkeypatch.setattr(driver, "INPUT_PINS_PATH", "docs/haiku55/other_pins.json")
    monkeypatch.setattr(driver, "INPUT_PINS", elsewhere)
    with pytest.raises(SystemExit, match="is not committed at HEAD"):
        driver.committed_input_pins()


@pytest.mark.parametrize(
    "inputs",
    [
        {},
        {SLUG: {"sha256": {"predictions.csv": "a" * 64}}},
        {SLUG: {"sha256": {"predictions.csv": "a", "run_state.json": "b"}}, "x": {}},
    ],
)
def test_input_pins_that_miss_a_run_file_are_refused(pinned_repo, inputs):
    pins, _ = pinned_repo
    pins.write_text(json.dumps({"inputs": inputs}))
    commit(driver.ROOT, "other pins")
    with pytest.raises(SystemExit, match="does not pin"):
        driver.committed_input_pins()


# --- Stage isolation -----------------------------------------------------------


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setattr(driver, "ROOT", root)
    return root


@pytest.mark.parametrize("relation", ["same", "parent", "child"])
def test_stage_must_not_overlap_any_input(workspace, relation):
    stage = workspace / "results/local/stage"
    source = {"same": stage, "parent": stage.parent, "child": stage / "source"}[
        relation
    ]
    with pytest.raises(SystemExit, match="overlaps input"):
        driver.validate_stage_path(stage, [source])


@pytest.mark.parametrize("relative", ["app/src", "paper/snapshot", "results/local"])
def test_stage_must_be_a_scratch_subdirectory(workspace, relative):
    with pytest.raises(SystemExit, match="stage-dir must be below"):
        driver.validate_stage_path(workspace / relative, [])


def test_stage_cannot_contain_symlink_to_a_live_file(workspace):
    stage = workspace / "results/local/stage"
    stage.mkdir(parents=True)
    (stage / "predictions.csv").symlink_to(workspace / "live.csv")
    with pytest.raises(SystemExit, match="symlink in stage-dir"):
        driver.validate_stage_path(stage, [])


def test_disjoint_scratch_stage_is_allowed(workspace):
    driver.validate_stage_path(
        workspace / "results/local/stage", [workspace / "results/local/inputs"]
    )


# --- Prediction keys -----------------------------------------------------------


@pytest.fixture
def predictions():
    return pd.DataFrame(
        {
            "model": [NEW, NEW],
            "scenario_id": ["scenario_000", "scenario_000"],
            "variable": ["snap", "ssi"],
            "prediction": [0, 1],
        }
    )


def test_equal_row_counts_do_not_hide_substituted_output_keys(predictions):
    wrong = predictions.copy()
    wrong.loc[1, "variable"] = "medicaid"
    with pytest.raises(SystemExit, match="keys differ"):
        driver.validate_keys(wrong, predictions, NEW)


def test_duplicate_output_keys_are_rejected(predictions):
    repeated = pd.concat([predictions, predictions.iloc[:1]], ignore_index=True)
    with pytest.raises(SystemExit, match="duplicate prediction keys"):
        driver.validate_keys(repeated, predictions, NEW)


def test_predictions_cannot_be_labeled_as_another_model(predictions):
    with pytest.raises(SystemExit, match="unexpected model"):
        driver.validate_keys(predictions, predictions, "claude-sonnet-5.5")


# --- CLI -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "options, message",
    [
        (["--partial"], "--partial requires --early"),
        (["--early", "--step", "judge"], "--early only applies to prepare"),
        (["--early", "--step", "triage"], "--early only applies to prepare"),
        (["--early", "--step", "export"], "--early only applies to prepare"),
        (
            ["--early", "--step", "install-exclusions"],
            "--early only applies to prepare",
        ),
        (
            ["--early", "--step", "adjudicate-exclusions"],
            "--early only applies to prepare",
        ),
        ([], "prepare requires --runs-root"),
    ],
)
def test_cli_rejects_unsafe_mode_combinations(tmp_path, options, message, capsys):
    with pytest.raises(SystemExit):
        driver.parse_args(["--stage-dir", str(tmp_path), *options])
    assert message in capsys.readouterr().err


def test_partial_mode_is_explicitly_early(tmp_path):
    args = driver.parse_args(
        [
            "--stage-dir",
            str(tmp_path / "stage"),
            "--runs-root",
            str(tmp_path / "runs"),
            "--early",
            "--partial",
        ]
    )
    assert args.partial and args.early and args.step == "prepare"


@pytest.mark.parametrize("step", ["install-exclusions", "adjudicate-exclusions"])
def test_the_new_steps_need_a_stage(step, capsys):
    with pytest.raises(SystemExit):
        driver.parse_args(["--step", step])
    assert f"{step} requires --stage-dir" in capsys.readouterr().err


@pytest.mark.parametrize(
    "step", ["export", "triage", "install-exclusions", "adjudicate-exclusions"]
)
@pytest.mark.parametrize("field", ["partial", "early"])
def test_an_early_or_partial_stage_cannot_resume_into_release(workspace, field, step):
    stage = workspace / "results/local/stage"
    stage.mkdir(parents=True)
    receipt = {"partial": False, "early": False, "files": {}}
    receipt[field] = True
    (stage / "stage.json").write_text(json.dumps(receipt))
    with pytest.raises(SystemExit, match="cannot become a release"):
        driver.main(["--stage-dir", str(stage), "--step", step])


def test_resume_refuses_changed_staged_inputs(workspace):
    stage = workspace / "results/local/stage"
    stage.mkdir(parents=True)
    (stage / "predictions.csv").write_text("changed data")
    (stage / "stage.json").write_text(
        json.dumps(
            {
                "partial": False,
                "early": False,
                "files": {
                    "predictions.csv": hashlib.sha256(b"original data").hexdigest()
                },
            }
        )
    )
    with pytest.raises(SystemExit, match="staged input changed"):
        driver.main(["--stage-dir", str(stage), "--step", "export"])


def _resumable(stage: Path, installed: dict | None) -> None:
    stage.mkdir(parents=True)
    receipt = {"partial": False, "early": False, "files": {}}
    if installed is not None:
        receipt["exclusions_installed"] = installed
    (stage / "stage.json").write_text(json.dumps(receipt))


@pytest.mark.parametrize("step", ["triage", "export", "adjudicate-exclusions"])
@pytest.mark.parametrize("installed", [None, {}, {"sha256": "0" * 64}])
def test_later_steps_refuse_a_stage_without_the_installed_exclusions(
    workspace, monkeypatch, step, installed
):
    sha = release_sha()
    monkeypatch.setattr(driver, "release_exclusions_sha256", lambda: sha)
    for name in ("triage", "export", "adjudicate_exclusions", "resolve_live_base"):
        monkeypatch.setattr(
            driver, name, lambda *a, n=name: pytest.fail(f"{n} ran"), raising=True
        )
    stage = workspace / "results/local/stage"
    _resumable(stage, installed)
    with pytest.raises(SystemExit, match="run --step install-exclusions"):
        driver.main(["--stage-dir", str(stage), "--step", step])


@pytest.mark.parametrize(
    "step, called",
    [
        ("triage", "triage"),
        ("adjudicate-exclusions", "adjudicate_exclusions"),
        ("judge", "judge"),
        ("install-exclusions", "install_exclusions"),
    ],
)
def test_a_stage_with_the_release_exclusions_reaches_its_step(
    workspace, monkeypatch, step, called
):
    """The installed record lets triage and adjudicate-exclusions run; judge
    and install-exclusions do not need it (no prompt renders an exclusion)."""
    sha = release_sha()
    monkeypatch.setattr(driver, "release_exclusions_sha256", lambda: sha)
    calls = []
    monkeypatch.setattr(driver, called, lambda *a: calls.append(called))
    stage = workspace / "results/local/stage"
    installed = {"sha256": sha} if step in ("triage", "adjudicate-exclusions") else None
    _resumable(stage, installed)
    driver.main(["--stage-dir", str(stage), "--step", step])
    assert calls == [called]


# --- Reference pins ------------------------------------------------------------


def test_the_committed_references_match_their_pins(tmp_path):
    """Release 20261006's references, read from BASE_COMMIT, are the pinned
    bytes: 64 exclusions, 36 unlisted inputs and 28 engine defects, and 1,920
    scored outputs."""
    snapshot = base_references(tmp_path / "snapshot")
    driver.verify_reference_pins(snapshot, "committed reference")
    for name, pin in driver.BASE_REFERENCE_SHA256.items():
        raw = (snapshot / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == pin
    from policybench.reference_exclusions import (
        load_reference_exclusions,
        split_reference,
    )

    exclusions = load_reference_exclusions(snapshot)
    assert len(exclusions) == driver.BASE_EXCLUSIONS
    reasons = [e["reason_code"] for e in exclusions]
    assert reasons.count("reference_engine_defect") == 28
    assert reasons.count("reference_depends_on_unlisted_input") == 36
    reference = pd.read_csv(snapshot / "reference_outputs.csv")
    assert len(reference) == driver.BASE_OUTPUTS
    assert reference.scenario_id.nunique() == 100
    assert len(split_reference(reference, exclusions)[0]) == driver.BASE_SCORED


def test_the_committed_adjudications_exclude_exactly_the_scoring_exclusions(
    tmp_path,
):
    """Release 20261006's record (77 decisions, 64 of them exclusions) excludes
    exactly its exclusion record's outputs, scenario_023 Medicaid included."""
    from policybench.adjudications import excluded_case_keys
    from policybench.reference_exclusions import (
        exclusion_keys,
        load_reference_exclusions,
    )

    excluded = exclusion_keys(
        load_reference_exclusions(base_references(tmp_path / "snapshot"))
    )
    decisions = driver.base_adjudications()
    assert len(decisions) == 77
    assert excluded_case_keys(decisions) == excluded
    assert ("scenario_023", "head_medicaid_eligible") in excluded


@pytest.fixture
def pinned_copy(tmp_path):
    """A copy of release 20261006's five reference files."""
    return base_references(tmp_path / "references")


@pytest.mark.parametrize("name", driver.REFERENCE_FILES)
@pytest.mark.parametrize("defect", ["appended", "missing"])
def test_a_reference_file_that_misses_its_pin_is_refused(pinned_copy, name, defect):
    driver.verify_reference_pins(pinned_copy, "staged reference")
    if defect == "missing":
        (pinned_copy / name).unlink()
    else:
        with (pinned_copy / name).open("a") as stream:
            stream.write("\n")
    with pytest.raises(SystemExit, match=f"staged reference {name} does not match"):
        driver.verify_reference_pins(pinned_copy, "staged reference")


def test_the_release_exclusion_pin_replaces_only_the_exclusion_records(pinned_copy):
    """With the release's exclusion sha256, the exclusion record must be the
    release's and every other file keeps its 20261006 pin."""
    with pytest.raises(SystemExit, match="reference_exclusions.json does not match"):
        driver.verify_reference_pins(pinned_copy, "staged reference", release_sha())
    (pinned_copy / EXCLUSIONS_NAME).write_text(release_text())
    driver.verify_reference_pins(pinned_copy, "staged reference", release_sha())
    with pytest.raises(SystemExit, match="reference_exclusions.json does not match"):
        driver.verify_reference_pins(pinned_copy, "staged reference")
    (pinned_copy / "scenarios.csv").write_text("scenario_id\n")
    with pytest.raises(SystemExit, match="staged reference scenarios.csv"):
        driver.verify_reference_pins(pinned_copy, "staged reference", release_sha())


def test_resolve_base_checks_the_committed_pins_before_anything_else(
    pinned_copy, monkeypatch
):
    (pinned_copy / EXCLUSIONS_NAME).write_text('{"exclusions": []}\n')
    monkeypatch.setattr(driver, "SNAPSHOT", pinned_copy)
    monkeypatch.setattr(
        driver,
        "live_pointer",
        lambda: pytest.fail("resolve_base read the pointer before the pins"),
    )
    with pytest.raises(
        SystemExit, match="committed reference reference_exclusions.json"
    ):
        driver.resolve_base(SimpleNamespace(partial=False))


# --- Base payload in git -------------------------------------------------------


def test_the_base_commit_holds_release_20261006():
    pointer = json.loads(driver.base_commit_blob(Path("app/src/data.artifact.json")))
    assert pointer["tag"] == driver.BASE_TAG
    assert pointer["sha256"] == driver.BASE_SHA256
    for name, pin in driver.BASE_REFERENCE_SHA256.items():
        raw = driver.base_commit_blob(driver.SNAPSHOT.relative_to(driver.ROOT) / name)
        assert hashlib.sha256(raw).hexdigest() == pin


def test_the_base_exclusion_record_is_read_from_git_and_pinned(monkeypatch):
    assert driver.base_exclusion_record() == base_record()
    # The scope check writes the record back with exclusions_text, so that
    # spelling must reproduce the pinned bytes exactly.
    assert (
        hashlib.sha256(driver.exclusions_text(base_record()).encode()).hexdigest()
        == driver.BASE_REFERENCE_SHA256[EXCLUSIONS_NAME]
    )
    monkeypatch.setattr(
        driver, "base_commit_blob", lambda path: base_blob(path) + b"\n"
    )
    with pytest.raises(SystemExit, match="does not match its pin"):
        driver.base_exclusion_record()


def test_the_base_predictions_pin_is_the_release_commits_not_the_working_trees(
    tmp_path, monkeypatch
):
    """A working tree whose predictions and manifest pin are both replaced.

    The pin comes from the manifest at BASE_COMMIT, so editing the working
    tree's manifest to match substituted predictions does not pass.
    """
    committed = Path("paper/snapshot/20260501/manifest.json")
    snapshot = tmp_path / "paper/snapshot/20260501/runs" / driver.RUN_NAME
    snapshot.mkdir(parents=True)
    substitute = snapshot / "predictions.csv.gz"
    with gzip.open(substitute, "wt") as stream:
        stream.write("model,scenario_id,variable,prediction\n")
    manifest = json.loads(base_blob(committed))
    files = manifest["source_run_artifacts"][driver.RUN_NAME]["files"]
    files["predictions.csv.gz"] = driver.digest(substitute)
    (tmp_path / committed).write_text(json.dumps(manifest))
    monkeypatch.setattr(driver, "ROOT", tmp_path)
    monkeypatch.setattr(driver, "base_commit_blob", base_blob)
    with pytest.raises(SystemExit, match="fail release 20261006's manifest hash"):
        driver.verify_base_predictions(snapshot)


def test_release_20261006s_manifest_pins_its_predictions():
    manifest = json.loads(
        driver.base_commit_blob(Path("paper/snapshot/20260501/manifest.json"))
    )
    pin = manifest["source_run_artifacts"][driver.RUN_NAME]["files"]
    raw = driver.base_commit_blob(
        driver.SNAPSHOT.relative_to(driver.ROOT) / "predictions.csv.gz"
    )
    assert hashlib.sha256(raw).hexdigest() == pin["predictions.csv.gz"]


def test_base_commit_blob_names_the_missing_history():
    with pytest.raises(SystemExit, match="cannot read .* at base commit 8b831f2cfaa0"):
        driver.base_commit_blob(Path("no/such/file.csv"))


def test_base_commit_blob_names_a_missing_commit(monkeypatch):
    monkeypatch.setattr(driver, "BASE_COMMIT", "0" * 40)
    with pytest.raises(SystemExit, match="at base commit 000000000000.*unshallow"):
        driver.base_commit_blob(Path("app/src/data.artifact.json"))


def test_a_re_export_after_the_freeze_reads_20261006_from_git(monkeypatch):
    """After the freeze the pointer names RELEASE_TAG; the base comes from git."""
    monkeypatch.setattr(driver, "live_pointer", lambda: {"tag": driver.RELEASE_TAG})
    monkeypatch.setattr(
        driver, "resolve_base", lambda args: pytest.fail("read the working tree")
    )
    live = driver.resolve_live_base(SimpleNamespace())
    names = {row["model"] for row in live["countries"]["us"]["modelStats"]}
    assert len(names) == driver.BASE_MODELS and NEW not in names


def _gz_payload(models: int) -> bytes:
    stats = [{"model": f"m{i}"} for i in range(models)]
    return gzip.compress(json.dumps({"modelStats": stats}).encode())


def test_the_git_base_must_rewrap_to_the_20261006_asset(monkeypatch):
    raw = _gz_payload(46)
    monkeypatch.setattr(driver, "base_commit_blob", lambda path: raw)
    monkeypatch.setattr(driver, "live_pointer", lambda: {"tag": driver.RELEASE_TAG})
    with pytest.raises(SystemExit, match="base payload SHA256 mismatch"):
        driver.resolve_live_base(SimpleNamespace())
    wrapped = json.dumps({"countries": {"us": json.loads(gzip.decompress(raw))}})
    monkeypatch.setattr(
        driver, "BASE_SHA256", hashlib.sha256(wrapped.encode()).hexdigest()
    )
    live = driver.resolve_live_base(SimpleNamespace())
    assert len(live["countries"]["us"]["modelStats"]) == 46
    short = _gz_payload(45)
    monkeypatch.setattr(driver, "base_commit_blob", lambda path: short)
    wrapped = json.dumps({"countries": {"us": json.loads(gzip.decompress(short))}})
    monkeypatch.setattr(
        driver, "BASE_SHA256", hashlib.sha256(wrapped.encode()).hexdigest()
    )
    with pytest.raises(SystemExit, match="base must have 46 models"):
        driver.resolve_live_base(SimpleNamespace())


@pytest.mark.parametrize("tag", ["dashboard-data-20260930", "dashboard-data-20991231"])
def test_any_other_pointer_is_refused(monkeypatch, tag):
    monkeypatch.setattr(driver, "live_pointer", lambda: {"tag": tag})
    with pytest.raises(SystemExit, match="base pointer changed"):
        driver.resolve_live_base(SimpleNamespace())


# --- Audit ---------------------------------------------------------------------


def _verdict(models, source="llm_error"):
    return {
        "reference_suspect": False,
        "reference_bug_hypothesis": "",
        "case_failure_source": source,
        "case_failure_subtype": "thresholds_rates",
        "rationale": "The models applied an outdated threshold.",
        "models": [
            {
                "model": model,
                "failure_source": source,
                "failure_subtype": "thresholds_rates",
                "diagnosis": "The model used the prior year's threshold.",
            }
            for model in models
        ],
    }


def write_verdict(case, verdict, **meta):
    """A verdict and its sidecar, bound to the verdict and the case's prompt;
    a meta value of None leaves that key out."""
    path = case / "verdict.json"
    path.write_text(json.dumps(verdict))
    prompt = case / "prompt.md"
    sidecar = {
        "verdict_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "prompt_sha256": (
            hashlib.sha256(prompt.read_bytes()).hexdigest()
            if prompt.is_file()
            else None
        ),
        "judge_runner": "scripts/run_audit_claude.sh",
        "judge_model_requested": driver.JUDGE_MODEL,
        "judge_model_reported": [driver.JUDGE_MODEL],
        "judged_at_utc": "2026-10-09T01:00:00+00:00",
        **meta,
    }
    (case / "verdict.meta.json").write_text(
        json.dumps({k: v for k, v in sidecar.items() if v is not None})
    )


def _audit(root, wrong_models):
    case = root / "cases/us__scenario_000__snap"
    case.mkdir(parents=True)
    (case / "prompt.md").write_text("Classify these wrong answers.\n")
    (root / "schema.json").write_text(json.dumps(AUDIT_OUTPUT_SCHEMA))
    (root / "cases.jsonl").write_text(
        json.dumps(
            {
                "case_id": case.name,
                "wrong_models": wrong_models,
                "parse_failure_only": False,
            }
        )
        + "\n"
    )
    return case


@pytest.fixture
def audit(tmp_path):
    root = tmp_path / "audit"
    case = _audit(root, [NEW])
    verdict = _verdict([NEW])
    write_verdict(case, verdict)
    return root, case, verdict


def test_verdict_requires_full_schema_and_exact_wrong_model_coverage(audit):
    root, _, _ = audit
    assert driver.validate_verdicts(root) == []


@pytest.mark.parametrize("defect", ["missing", "extra", "duplicate", "schema", "json"])
def test_invalid_verdict_is_pending_and_removal_clears_provenance(audit, defect):
    root, case, original = audit
    verdict = copy.deepcopy(original)
    if defect == "missing":
        verdict["models"] = []
    elif defect == "extra":
        verdict["models"].append({**verdict["models"][0], "model": "other"})
    elif defect == "duplicate":
        verdict["models"].append(verdict["models"][0])
    elif defect == "schema":
        del verdict["reference_suspect"]
    write_verdict(case, verdict)
    if defect == "json":
        (case / "verdict.json").write_text("not JSON")
    assert driver.validate_verdicts(root) == [case.name]
    assert (case / "verdict.json").exists()
    assert driver.validate_verdicts(root, remove_invalid=True) == [case.name]
    assert not (case / "verdict.json").exists()
    assert not (case / "verdict.meta.json").exists()


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "stale",
        "wrong_judge",
        "not_an_object",
        "no_timestamp",
        "no_prompt_sha256",
        "other_prompt",
        "no_runner",
        "requested_other",
    ],
)
def test_new_model_verdict_requires_bound_opus55_provenance(audit, defect):
    root, case, _ = audit
    path = case / "verdict.meta.json"
    meta = json.loads(path.read_text())
    if defect == "missing":
        path.unlink()
    else:
        if defect == "stale":
            meta["verdict_sha256"] = "0" * 64
        elif defect == "wrong_judge":
            meta["judge_model_reported"] = ["claude-opus-5"]
        elif defect == "no_timestamp":
            del meta["judged_at_utc"]
        elif defect == "no_prompt_sha256":
            del meta["prompt_sha256"]
        elif defect == "other_prompt":
            meta["prompt_sha256"] = hashlib.sha256(b"another prompt").hexdigest()
        elif defect == "no_runner":
            del meta["judge_runner"]
        elif defect == "requested_other":
            meta["judge_model_requested"] = "claude-sonnet-5-5"
        else:
            meta = [meta]
        path.write_text(json.dumps(meta))
    assert driver.validate_verdicts(root) == [case.name]


def test_every_verdict_is_bound_to_its_own_bytes(tmp_path):
    """An incumbent verdict's sidecar must match its bytes too, not only a
    verdict that names Claude Haiku 5.5."""
    root = tmp_path / "audit"
    case = _audit(root, ["incumbent"])
    write_verdict(
        case,
        _verdict(["incumbent"]),
        judge_model_requested="default",
        judge_model_reported=["gpt-6.1-sol"],
    )
    assert driver.validate_verdicts(root) == []
    edited = _verdict(["incumbent"])
    edited["case_failure_subtype"] = "other"
    (case / "verdict.json").write_text(json.dumps(edited))
    assert driver.validate_verdicts(root) == [case.name]


def test_a_verdict_stays_bound_to_its_prompt_sha256(tmp_path):
    root = tmp_path / "audit"
    case = _audit(root, ["incumbent"])
    prompt = hashlib.sha256((case / "prompt.md").read_bytes()).hexdigest()
    write_verdict(
        case,
        _verdict(["incumbent"]),
        prompt_sha256=prompt,
        judge_model_requested="default",
        judge_model_reported=["gpt-6.1-sol"],
    )
    assert driver.validate_verdicts(root) == []
    (case / "prompt.md").write_text("Classify these wrong answers, and one more.\n")
    assert driver.validate_verdicts(root, remove_invalid=True) == [case.name]
    assert not (case / "verdict.json").exists()
    # Set aside, not destroyed.
    (kept,) = (tmp_path / "rejected-verdicts" / case.name).iterdir()
    assert sorted(p.name for p in kept.iterdir()) == [
        "reason.txt",
        "verdict.json",
        "verdict.meta.json",
    ]


def test_the_judge_must_cover_all_47_models_in_a_case(tmp_path):
    incumbents = [f"incumbent-{i:02d}" for i in range(46)]
    root = tmp_path / "audit"
    case = _audit(root, [*incumbents, NEW])
    write_verdict(case, _verdict(incumbents))
    assert driver.validate_verdicts(root) == [case.name]
    write_verdict(case, _verdict([*incumbents, NEW]))
    assert driver.validate_verdicts(root) == []
    # A carried-over incumbent verdict cannot name the new model, and a
    # re-judge from another judge does not qualify.
    write_verdict(
        case,
        _verdict([*incumbents, NEW]),
        judge_model_requested="default",
        judge_model_reported=["gpt-6.1-sol"],
    )
    assert driver.validate_verdicts(root) == [case.name]


def test_parse_only_cases_do_not_require_paid_judging(audit):
    root, case, _ = audit
    manifest = json.loads((root / "cases.jsonl").read_text())
    manifest["parse_failure_only"] = True
    (root / "cases.jsonl").write_text(json.dumps(manifest) + "\n")
    (case / "verdict.json").unlink()
    (case / "verdict.meta.json").unlink()
    assert driver.validate_verdicts(root) == []


def test_unchanged_incumbent_case_keeps_its_existing_judge(tmp_path):
    """A seed verdict whose sidecar never recorded its prompt carries over
    through the seed binding."""
    root = tmp_path / "audit"
    case = _audit(root, ["incumbent"])
    write_verdict(
        case,
        _verdict(["incumbent"]),
        judge_model_requested="default",
        judge_model_reported=["gpt-5.6-sol"],
        judge_runner="scripts/run_audit_codex.sh",
        prompt_sha256=None,
    )
    seed = driver.seed_digest(root)
    assert driver.validate_verdicts(root, seed=seed) == []
    # Without the binding nothing ties the verdict to its prompt.
    assert driver.validate_verdicts(root) == [case.name]


@pytest.mark.parametrize("mutation", ["edited", "rebound", "missing"])
def test_a_carried_over_verdict_must_keep_the_seeds_bytes(tmp_path, mutation):
    """Editing a carried-over verdict, even with its sidecar re-hashed to
    match, or removing it, is refused: a re-judge cannot restore it."""
    root = tmp_path / "audit"
    case = _audit(root, ["incumbent"])
    write_verdict(
        case,
        _verdict(["incumbent"]),
        judge_model_requested="default",
        judge_model_reported=["gpt-5.6-sol"],
        prompt_sha256=None,
    )
    seed = driver.seed_digest(root)
    edited = _verdict(["incumbent"])
    edited["case_failure_subtype"] = "other"
    if mutation == "edited":
        (case / "verdict.json").write_text(json.dumps(edited))
    elif mutation == "rebound":
        write_verdict(
            case,
            edited,
            judge_model_requested="default",
            judge_model_reported=["gpt-5.6-sol"],
        )
    else:
        (case / "verdict.json").unlink()
    before = sorted(p.name for p in case.iterdir())
    with pytest.raises(SystemExit, match="carried-over verdicts differ"):
        driver.validate_verdicts(root, remove_invalid=True, seed=seed)
    assert sorted(p.name for p in case.iterdir()) == before


# A two-household board whose audit prompts render for real (policybench.audit).
REFERENCE_ROWS = [
    {"scenario_id": "s0", "variable": "snap", "value": 0.0},
    {"scenario_id": "s1", "variable": "snap", "value": 300.0},
    {"scenario_id": "s2", "variable": "snap", "value": 100.0},
]
INCUMBENT_ROWS = [
    ("m1", "s0", 250.0, "Estimated benefit from income."),
    ("m2", "s0", 400.0, "Used gross income test."),
    ("m1", "s1", 300.0, "Matched the allotment."),
    ("m2", "s1", 0.0, "Assumed ineligible."),
    ("m1", "s2", 100.0, "Matched the allotment."),
    ("m2", "s2", 100.0, "Matched the allotment."),
]


def _board(directory: Path, rows) -> Path:
    us = directory / "us"
    us.mkdir(parents=True)
    pd.DataFrame(REFERENCE_ROWS).to_csv(us / "reference_outputs.csv", index=False)
    pd.DataFrame(
        [
            {
                "model": model,
                "scenario_id": scenario,
                "variable": "snap",
                "prediction": value,
                "explanation": text,
                "error": None,
            }
            for model, scenario, value, text in rows
        ]
    ).to_csv(us / "predictions.csv", index=False)
    return directory


@pytest.fixture
def seeded_stage(tmp_path, monkeypatch):
    """A judged 2-model seed audit and a stage whose board adds the new model.

    No reference explanation is reworded unless a test says so: the real
    reworded_since_seed() names cases of the real board, which this one lacks.
    """
    from policybench.audit import prepare_audit

    monkeypatch.setattr(driver, "reworded_since_seed", lambda: frozenset())
    grounding = tmp_path / "grounding.csv"
    pd.DataFrame(
        [{"scenario_id": "s1", "variable": "snap", "grounding": "Gross test: pass."}]
    ).to_csv(grounding, index=False)
    monkeypatch.setattr(
        driver, "GROUNDING_SHA256", hashlib.sha256(grounding.read_bytes()).hexdigest()
    )
    lookup = {("s1", "snap"): "Gross test: pass."}
    seed = tmp_path / "seed"
    seed_board = _board(tmp_path / "seed-board", INCUMBENT_ROWS)
    prepare_audit(seed_board / "us", seed, grounding_lookup=lookup)
    for item in map(json.loads, (seed / "cases.jsonl").read_text().splitlines()):
        write_verdict(
            seed / "cases" / item["case_id"],
            _verdict(item["wrong_models"]),
            judge_model_requested="default",
            judge_model_reported=["gpt-6.1-sol"],
            prompt_sha256=None,
        )
    digest_text = driver.seed_digest_text(driver.seed_digest(seed))
    monkeypatch.setattr(
        driver, "SEED_DIGEST_SHA256", hashlib.sha256(digest_text.encode()).hexdigest()
    )
    stage = tmp_path / "stage"

    def prepare(new_rows, *, grounding_path=grounding, explanations=None):
        bundle = _board(stage / "publish" / driver.RUN_NAME, INCUMBENT_ROWS + new_rows)
        if explanations:
            # The one annotation a judge's prompt carries: rewording it
            # re-renders the case's prompt, as release 20261006's rewording did.
            (bundle / "annotations").mkdir()
            pd.DataFrame(
                [
                    {"scenario_id": scenario, "variable": "snap", "explanation": text}
                    for scenario, text in explanations.items()
                ]
            ).to_csv(
                bundle / "annotations/us_case_reference_explanations.csv", index=False
            )
        args = SimpleNamespace(
            stage_dir=stage, audit_seed=seed, grounding=grounding_path
        )
        binding = driver.prepare_cases(args, bundle)
        # main binds the seed in stage.json beside the input hashes.
        (stage / "stage.json").write_text(
            json.dumps({"partial": False, "early": False, "files": {}, "seed": binding})
        )
        return stage / "audit"

    return seed, stage, prepare


def test_a_case_the_new_model_joins_is_rejudged_and_the_rest_carry_over(
    seeded_stage,
):
    seed, stage, prepare = seeded_stage
    audit = prepare(
        [
            (NEW, "s0", 99.0, "Guessed."),
            (NEW, "s1", 300.0, "Right."),
            (NEW, "s2", 100.0, "Right."),
        ]
    )
    joined, untouched = "us__s0__snap", "us__s1__snap"
    assert json.loads((stage / "pending.json").read_text()) == [joined]
    assert not (audit / "cases" / joined / "verdict.json").exists()
    assert not (audit / "cases" / joined / "verdict.meta.json").exists()
    for name in ("prompt.md", "verdict.json", "verdict.meta.json"):
        assert (audit / "cases" / untouched / name).read_bytes() == (
            seed / "cases" / untouched / name
        ).read_bytes()
    assert json.loads((stage / "prompt-changes.json").read_text()) == {
        "added": [],
        "changed": [joined],
        "kept": [untouched],
    }
    wrong = ["m1", "m2", NEW]
    write_verdict(audit / "cases" / joined, _verdict(wrong))
    seed_binding = driver.load_seed(stage)
    assert seed_binding == driver.seed_digest(seed)
    assert driver.validate_verdicts(audit, seed=seed_binding) == []


# Claude Haiku 5.5 misses s0 alone: s0 is re-opened, s1 carries over.
JOINS_S0 = [
    (NEW, "s0", 99.0, "Guessed."),
    (NEW, "s1", 300.0, "Right."),
    (NEW, "s2", 100.0, "Right."),
]
# Claude Haiku 5.5 answers every output right: no case is joined.
JOINS_NONE = [
    (NEW, "s0", 0.0, "Ineligible."),
    (NEW, "s1", 300.0, "Right."),
    (NEW, "s2", 100.0, "Right."),
]


def test_an_edited_carried_over_verdict_is_refused_after_prepare(seeded_stage):
    """Edit a kept incumbent verdict in a prepared stage (sidecar re-hashed to
    match) and validation refuses it."""
    _, stage, prepare = seeded_stage
    audit = prepare(JOINS_S0)
    write_verdict(audit / "cases/us__s0__snap", _verdict(["m1", "m2", NEW]))
    seed = driver.load_seed(stage)
    assert driver.validate_verdicts(audit, seed=seed) == []
    kept = audit / "cases/us__s1__snap"
    verdict = json.loads((kept / "verdict.json").read_text())
    verdict["case_failure_source"] = "prompt_ambiguity"
    write_verdict(
        kept,
        verdict,
        judge_model_requested="default",
        judge_model_reported=["gpt-6.1-sol"],
    )
    with pytest.raises(SystemExit, match="carried-over verdicts differ.*us__s1__snap"):
        driver.validate_verdicts(audit, seed=seed)


def test_prepare_refuses_a_seed_the_committed_digest_does_not_record(
    seeded_stage, monkeypatch
):
    _, stage, prepare = seeded_stage
    monkeypatch.setattr(driver, "SEED_DIGEST_SHA256", COMMITTED_SEED_DIGEST_SHA256)
    with pytest.raises(SystemExit, match="not release 20261006's"):
        prepare(JOINS_S0)
    assert not (stage / "audit").exists()


def test_load_seed_refuses_a_stage_without_a_binding_or_with_another(seeded_stage):
    _, stage, prepare = seeded_stage
    prepare(JOINS_S0)
    receipt = json.loads((stage / "stage.json").read_text())
    edited = copy.deepcopy(receipt)
    edited["seed"]["us__s1__snap"]["verdict_sha256"] = "0" * 64
    (stage / "stage.json").write_text(json.dumps(edited))
    with pytest.raises(SystemExit, match="not release 20261006's"):
        driver.load_seed(stage)
    del receipt["seed"]
    (stage / "stage.json").write_text(json.dumps(receipt))
    with pytest.raises(SystemExit, match="bind-seed"):
        driver.load_seed(stage)


def test_bind_seed_binds_a_stage_prepared_before_prepare_did(seeded_stage):
    seed, stage, prepare = seeded_stage
    prepare(JOINS_S0)
    assert json.loads((stage / driver.PROMPT_CHANGES).read_text())["kept"] == [
        "us__s1__snap"
    ]
    receipt = json.loads((stage / "stage.json").read_text())
    binding = receipt.pop("seed")
    (stage / "stage.json").write_text(json.dumps(receipt))
    args = SimpleNamespace(stage_dir=stage, audit_seed=seed)
    driver.bind_seed(args)
    assert driver.load_seed(stage) == binding
    with pytest.raises(SystemExit, match="already binds"):
        driver.bind_seed(args)


@pytest.mark.parametrize("move", ["kept_to_changed", "changed_to_kept", "dropped"])
def test_prompt_changes_that_disagree_with_the_stage_stop_every_step(
    seeded_stage, move
):
    """prompt-changes.json is re-derived from the stage's prompts and the
    bound seed on every read: moving a case between the lists, or dropping
    one, is refused."""
    _, stage, prepare = seeded_stage
    prepare(JOINS_S0)
    path = stage / driver.PROMPT_CHANGES
    changes = json.loads(path.read_text())
    if move == "kept_to_changed":
        changes["kept"].remove("us__s1__snap")
        changes["changed"].append("us__s1__snap")
    elif move == "changed_to_kept":
        changes["changed"].remove("us__s0__snap")
        changes["kept"].append("us__s0__snap")
    else:
        changes["changed"].remove("us__s0__snap")
    path.write_text(json.dumps(changes))
    for step in (driver.load_seed, driver.rejudged_cases):
        with pytest.raises(SystemExit, match="disagrees with the stage's prompts"):
            step(stage)


@pytest.mark.parametrize("edit", ["prompt_only", "verdict_sidecar_and_prompt"])
def test_a_kept_case_cannot_pass_as_a_new_verdict(seeded_stage, edit):
    """A kept case whose prompt is edited (with or without a re-bound
    verdict) is refused, not re-judged."""
    _, stage, prepare = seeded_stage
    audit = prepare(JOINS_S0)
    write_verdict(audit / "cases/us__s0__snap", _verdict(["m1", "m2", NEW]))
    kept = audit / "cases/us__s1__snap"
    (kept / "prompt.md").write_text((kept / "prompt.md").read_text() + "\n")
    if edit == "verdict_sidecar_and_prompt":
        verdict = json.loads((kept / "verdict.json").read_text())
        verdict["case_failure_subtype"] = "other"
        write_verdict(kept, verdict)
    before = sorted(p.name for p in kept.iterdir())
    with pytest.raises(SystemExit, match="incumbent-only case prompts changed"):
        driver.load_seed(stage)
    assert sorted(p.name for p in kept.iterdir()) == before


@pytest.mark.parametrize("claim", ["reopens_a_right_answer", "keeps_a_wrong_answer"])
def test_the_manifest_cannot_reopen_a_case_the_predictions_do_not(seeded_stage, claim):
    """Claude Haiku 5.5 answers s1 right and s0 wrong. Listing it as wrong on
    s1 (prompt edited, case moved to changed), or dropping it from s0 (seed
    prompt restored, case moved to kept), leaves the re-derived lists
    agreeing, so only the predictions can refuse it."""
    seed, stage, prepare = seeded_stage
    audit = prepare(JOINS_S0)
    driver.load_seed(stage)
    manifest = [
        json.loads(line) for line in (audit / "cases.jsonl").read_text().splitlines()
    ]
    changes = json.loads((stage / driver.PROMPT_CHANGES).read_text())
    case = "us__s1__snap" if claim == "reopens_a_right_answer" else "us__s0__snap"
    row = next(item for item in manifest if item["case_id"] == case)
    if claim == "reopens_a_right_answer":
        row["wrong_models"].append(NEW)
        prompt = audit / "cases" / case / "prompt.md"
        prompt.write_text(prompt.read_text() + f"{NEW}: Wrong.\n")
        changes["kept"].remove(case)
        changes["changed"].append(case)
    else:
        row["wrong_models"].remove(NEW)
        shutil.copyfile(
            seed / "cases" / case / "prompt.md", audit / "cases" / case / "prompt.md"
        )
        changes["changed"].remove(case)
        changes["kept"].append(case)
    (audit / "cases.jsonl").write_text("".join(json.dumps(r) + "\n" for r in manifest))
    (stage / driver.PROMPT_CHANGES).write_text(json.dumps(changes))
    for step in (driver.load_seed, driver.rejudged_cases):
        with pytest.raises(
            SystemExit, match=f"disagree with the staged predictions.*{case}"
        ):
            step(stage)


def test_set_aside_keeps_the_judge_evidence_with_the_verdict(tmp_path):
    root = tmp_path / "audit"
    case = _audit(root, [NEW])
    write_verdict(case, _verdict(["someone-else"]))
    for name in ("claude.json", "claude.log", "claude.transcript.jsonl"):
        (case / name).write_text(name)
    assert driver.validate_verdicts(root, remove_invalid=True) == [case.name]
    (kept,) = (tmp_path / "rejected-verdicts" / case.name).iterdir()
    assert sorted(p.name for p in kept.iterdir()) == [
        "claude.json",
        "claude.log",
        "claude.transcript.jsonl",
        "reason.txt",
        "verdict.json",
        "verdict.meta.json",
    ]
    assert sorted(p.name for p in case.iterdir()) == ["prompt.md"]


@pytest.mark.parametrize("payload", [[], "text", {"amendments": {}}])
def test_a_malformed_amendment_file_is_refused(tmp_path, payload):
    (tmp_path / driver.AMENDMENTS).write_text(json.dumps(payload))
    with pytest.raises(SystemExit, match="'amendments' is not a list"):
        driver.load_amendments(tmp_path, frozenset())


@pytest.mark.parametrize("defect", ["kept_verdict", "kept_prompt", "changed_prompt"])
def test_bind_seed_refuses_a_stage_that_disagrees_with_the_seed(seeded_stage, defect):
    seed, stage, prepare = seeded_stage
    audit = prepare(JOINS_S0)
    receipt = json.loads((stage / "stage.json").read_text())
    del receipt["seed"]
    (stage / "stage.json").write_text(json.dumps(receipt))
    if defect == "kept_verdict":
        (audit / "cases/us__s1__snap/verdict.json").write_text("{}")
    elif defect == "kept_prompt":
        (audit / "cases/us__s1__snap/prompt.md").write_text("Another prompt.\n")
    else:
        shutil.copyfile(
            seed / "cases/us__s0__snap/prompt.md",
            audit / "cases/us__s0__snap/prompt.md",
        )
    with pytest.raises(SystemExit, match="disagrees with the seed"):
        driver.bind_seed(SimpleNamespace(stage_dir=stage, audit_seed=seed))
    assert "seed" not in json.loads((stage / "stage.json").read_text())


def test_a_household_only_the_new_model_misses_becomes_a_new_case(seeded_stage):
    _, stage, prepare = seeded_stage
    audit = prepare(
        [
            (NEW, "s0", 0.0, "Ineligible."),
            (NEW, "s1", 300.0, "Right."),
            (NEW, "s2", 55.0, "Halved."),
        ]
    )
    assert json.loads((stage / "prompt-changes.json").read_text()) == {
        "added": ["us__s2__snap"],
        "changed": [],
        "kept": ["us__s0__snap", "us__s1__snap"],
    }
    assert json.loads((stage / "pending.json").read_text()) == ["us__s2__snap"]
    assert not (audit / "cases/us__s2__snap/verdict.json").exists()


def test_an_incumbent_prompt_that_changes_is_refused(
    seeded_stage, tmp_path, monkeypatch
):
    _, _, prepare = seeded_stage
    other = tmp_path / "other-grounding.csv"
    pd.DataFrame(
        [{"scenario_id": "s1", "variable": "snap", "grounding": "Gross test: fail."}]
    ).to_csv(other, index=False)
    monkeypatch.setattr(
        driver, "GROUNDING_SHA256", hashlib.sha256(other.read_bytes()).hexdigest()
    )
    with pytest.raises(SystemExit, match=r"incumbent-only case prompts changed.*s1"):
        prepare(JOINS_S0, grounding_path=other)


def test_prepare_refuses_a_grounding_other_than_the_pinned_one(seeded_stage, tmp_path):
    _, stage, prepare = seeded_stage
    other = tmp_path / "other-grounding.csv"
    other.write_text("scenario_id,variable,grounding\n")
    with pytest.raises(SystemExit, match="grounding differs"):
        prepare([], grounding_path=other)
    assert not (stage / "audit").exists()


def test_the_pinned_grounding_is_the_one_the_seed_was_rendered_with():
    if not GROUNDING.is_file():
        pytest.skip("the main clone's audit grounding is not on this machine")
    assert driver.digest(GROUNDING) == driver.GROUNDING_SHA256


# --- The nine reworded cases ---------------------------------------------------

REWORDED_S1 = {"s1": "The allotment is the maximum less 30% of net income."}


def test_a_reworded_case_may_change_without_the_new_model(seeded_stage, monkeypatch):
    """s1's reference explanation is reworded and Claude Haiku 5.5 answers it
    right: its prompt changes, it is re-opened and re-judged, and every gate
    that re-derives the lists agrees."""
    _, stage, prepare = seeded_stage
    monkeypatch.setattr(
        driver, "reworded_since_seed", lambda: frozenset({"us__s1__snap"})
    )
    audit = prepare(JOINS_S0, explanations=REWORDED_S1)
    assert json.loads((stage / driver.PROMPT_CHANGES).read_text()) == {
        "added": [],
        "changed": ["us__s0__snap", "us__s1__snap"],
        "kept": [],
    }
    assert json.loads((stage / "pending.json").read_text()) == [
        "us__s0__snap",
        "us__s1__snap",
    ]
    assert (
        "HOW POLICYENGINE DERIVED"
        in (audit / "cases/us__s1__snap/prompt.md").read_text()
    )
    manifest = {
        item["case_id"]: item
        for item in map(json.loads, (audit / "cases.jsonl").read_text().splitlines())
    }
    assert NEW not in manifest["us__s1__snap"]["wrong_models"]
    assert driver.rejudged_cases(stage) == {"us__s0__snap", "us__s1__snap"}
    write_verdict(audit / "cases/us__s0__snap", _verdict(["m1", "m2", NEW]))
    write_verdict(audit / "cases/us__s1__snap", _verdict(["m2"]))
    assert driver.validate_verdicts(audit, seed=driver.load_seed(stage)) == []


def test_a_reworded_case_the_new_model_joins_is_rejudged(seeded_stage, monkeypatch):
    """The real stage's case: Claude Haiku 5.5 answers all nine wrong."""
    _, stage, prepare = seeded_stage
    monkeypatch.setattr(
        driver, "reworded_since_seed", lambda: frozenset({"us__s0__snap"})
    )
    prepare(JOINS_S0, explanations={"s0": "The household fails the net test."})
    assert json.loads((stage / driver.PROMPT_CHANGES).read_text()) == {
        "added": [],
        "changed": ["us__s0__snap"],
        "kept": ["us__s1__snap"],
    }


def test_a_reworded_explanation_outside_the_pinned_set_is_refused(seeded_stage):
    _, stage, prepare = seeded_stage
    with pytest.raises(
        SystemExit, match=r"incumbent-only case prompts changed.*\['us__s1__snap'\]"
    ):
        prepare(JOINS_S0, explanations=REWORDED_S1)


def test_the_reworded_allowance_admits_no_other_incumbent_only_change(
    seeded_stage, monkeypatch
):
    """s0 and s1 both change without the new model; only s1 is reworded, so
    the refusal names s0 alone."""
    _, _, prepare = seeded_stage
    monkeypatch.setattr(
        driver, "reworded_since_seed", lambda: frozenset({"us__s1__snap"})
    )
    explanations = {**REWORDED_S1, "s0": "The household fails the net test."}
    with pytest.raises(
        SystemExit, match=r"incumbent-only case prompts changed.*: \['us__s0__snap'\]$"
    ):
        prepare(JOINS_NONE, explanations=explanations)


@pytest.mark.parametrize("reworded", ["us__s1__snap", "us__s9__snap"])
def test_a_reworded_case_whose_prompt_did_not_change_is_refused(
    seeded_stage, monkeypatch, reworded
):
    """A reworded case kept byte for byte (or absent from the audit) means
    the rewording did not reach its prompt: prepare stops."""
    _, _, prepare = seeded_stage
    monkeypatch.setattr(driver, "reworded_since_seed", lambda: frozenset({reworded}))
    with pytest.raises(
        SystemExit,
        match=re.escape(f"reworded cases whose prompts did not change: {[reworded]}"),
    ):
        prepare(JOINS_S0)


def test_check_prompt_changes_names_new_incumbent_only_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "reworded_since_seed", lambda: frozenset())
    root = tmp_path / "audit"
    case = _audit(root, ["incumbent"])
    with pytest.raises(SystemExit, match=case.name):
        driver.check_prompt_changes(root, {})
    manifest = json.loads((root / "cases.jsonl").read_text())
    manifest["wrong_models"] = ["incumbent", NEW]
    (root / "cases.jsonl").write_text(json.dumps(manifest) + "\n")
    assert driver.check_prompt_changes(root, {})["added"] == [case.name]
    with pytest.raises(SystemExit, match="seed cases vanished.*us__s9__snap"):
        driver.check_prompt_changes(root, {"us__s9__snap": "0" * 64})


CASE_FLAGS = st.fixed_dictionaries(
    {
        "seeded": st.booleans(),
        "same_prompt": st.booleans(),
        "new_wrong": st.booleans(),
        "reworded": st.booleans(),
        "parse_only": st.booleans(),
    }
)


@settings(max_examples=150, deadline=None)
@given(
    flags=st.lists(CASE_FLAGS, max_size=7),
    vanished=st.integers(min_value=0, max_value=2),
    stray_reworded=st.booleans(),
)
def test_check_prompt_changes_follows_its_rule_for_any_audit(
    flags, vanished, stray_reworded
):
    """For any manifest, seed and reworded set: a judged case is kept when its
    prompt is the seed's, changed when the seed has another, added when the
    seed lacks it. It refuses, in this order, a changed or added case neither
    the new model joins nor a rewording explains, a seed case that is not
    kept or changed, and a reworded case that is not changed."""
    with tempfile.TemporaryDirectory() as scratch:
        audit = Path(scratch) / "audit"
        manifest, seeded, reworded = [], {}, set()
        for index, case_flags in enumerate(flags):
            case = f"us__s{index}__snap"
            (audit / "cases" / case).mkdir(parents=True)
            prompt = audit / "cases" / case / "prompt.md"
            prompt.write_text(f"Prompt {index}.\n")
            wrong = ["m1", *([NEW] if case_flags["new_wrong"] else [])]
            manifest.append(
                {
                    "case_id": case,
                    "wrong_models": wrong,
                    "parse_failure_only": case_flags["parse_only"],
                }
            )
            if case_flags["seeded"]:
                seeded[case] = (
                    driver.digest(prompt)
                    if case_flags["same_prompt"]
                    else hashlib.sha256(f"Seed prompt {index}.\n".encode()).hexdigest()
                )
            if case_flags["reworded"]:
                reworded.add(case)
        for index in range(vanished):
            seeded[f"us__gone{index}__snap"] = "0" * 64
        if stray_reworded:
            reworded.add("us__elsewhere__snap")
        audit.mkdir(parents=True, exist_ok=True)
        (audit / "cases.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in manifest)
        )
        judged = [
            (item, flags[i])
            for i, item in enumerate(manifest)
            if not item["parse_failure_only"]
        ]
        kept = [
            item["case_id"] for item, f in judged if f["seeded"] and f["same_prompt"]
        ]
        changed = [
            item["case_id"]
            for item, f in judged
            if f["seeded"] and not f["same_prompt"]
        ]
        added = [item["case_id"] for item, f in judged if not f["seeded"]]
        offending = [
            item["case_id"]
            for item, f in judged
            if item["case_id"] not in kept
            and not f["new_wrong"]
            and item["case_id"] not in reworded
        ]
        gone = sorted(set(seeded) - {*kept, *changed})
        unrendered = sorted(reworded - set(changed))
        with mock.patch.object(
            driver, "reworded_since_seed", lambda: frozenset(reworded)
        ):
            if offending or gone or unrendered:
                with pytest.raises(SystemExit) as refusal:
                    driver.check_prompt_changes(audit, seeded)
                message = str(refusal.value)
                if offending:
                    assert "incumbent-only case prompts changed" in message
                    assert message.endswith(repr(offending[:8]))
                elif gone:
                    assert message == f"seed cases vanished from the audit: {gone[:8]}"
                else:
                    assert message == (
                        f"reworded cases whose prompts did not change: {unrendered[:8]}"
                    )
            else:
                assert driver.check_prompt_changes(audit, seeded) == {
                    "kept": kept,
                    "changed": changed,
                    "added": added,
                }


def test_the_reworded_cases_are_exactly_those_git_shows():
    """Runs anywhere with full history: the explanations committed at
    SEED_RELEASE_COMMIT and BASE_COMMIT differ on exactly the nine pinned
    cases. Read again here with the csv module, the files say the same."""
    import csv
    import io

    assert driver.reworded_since_seed() == driver.REWORDED_SINCE_SEED

    def rows(commit: str) -> dict:
        blob = subprocess.run(
            [
                "git",
                "-C",
                str(REPO),
                "show",
                f"{commit}:{driver.REFERENCE_EXPLANATIONS.as_posix()}",
            ],
            capture_output=True,
            check=True,
        ).stdout
        reader = csv.DictReader(io.StringIO(blob.decode("utf-8")))
        return {(row["scenario_id"], row["variable"]): row for row in reader}

    before, after = rows(driver.SEED_RELEASE_COMMIT), rows(BASE_COMMIT)
    assert set(before) == set(after)
    reworded = {
        f"us__{scenario}__{variable}"
        for (scenario, variable), row in after.items()
        if before[(scenario, variable)] != row
    }
    assert reworded == driver.REWORDED_SINCE_SEED
    # The rewording touches the explanation, the column a prompt renders.
    for case in reworded:
        _, scenario, variable = case.split("__", 2)
        old, new = before[(scenario, variable)], after[(scenario, variable)]
        assert old["explanation"] != new["explanation"]


def _explanations_csv(rows: list[dict]) -> bytes:
    return (
        pd.DataFrame(rows, columns=["scenario_id", "variable", "explanation"])
        .to_csv(index=False)
        .encode()
    )


EXPLANATION_ROWS = [
    {"scenario_id": f"scenario_00{i}", "variable": "snap", "explanation": text}
    for i, text in enumerate(
        ["Gross test passes.", 'Net income is $1,200, "after deductions".', "Zero."]
    )
]


@pytest.fixture
def explanation_repo(tmp_path, monkeypatch):
    """A git repository that commits the explanations file twice, the seed's
    and the base's, with the driver pointed at both commits."""
    root = tmp_path / "repo"
    path = root / driver.REFERENCE_EXPLANATIONS
    path.parent.mkdir(parents=True)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    monkeypatch.setattr(driver, "ROOT", root)

    def commits(before: list[dict], after: list[dict], pinned: set[str]):
        path.write_bytes(_explanations_csv(before))
        monkeypatch.setattr(driver, "SEED_RELEASE_COMMIT", commit(root, "seed"))
        path.write_bytes(_explanations_csv(after))
        monkeypatch.setattr(driver, "BASE_COMMIT", commit(root, "base"))
        monkeypatch.setattr(driver, "REWORDED_SINCE_SEED", frozenset(pinned))

    return commits


def _reword(rows: list[dict], *indices: int) -> list[dict]:
    return [
        {**row, "explanation": row["explanation"] + " Reworded."}
        if index in indices
        else dict(row)
        for index, row in enumerate(rows)
    ]


def test_reworded_since_seed_reads_both_commits_from_git(explanation_repo):
    explanation_repo(
        EXPLANATION_ROWS, _reword(EXPLANATION_ROWS, 1), {"us__scenario_001__snap"}
    )
    assert driver.reworded_since_seed() == {"us__scenario_001__snap"}


def test_reworded_since_seed_refuses_another_reworded_explanation(explanation_repo):
    explanation_repo(
        EXPLANATION_ROWS, _reword(EXPLANATION_ROWS, 1, 2), {"us__scenario_001__snap"}
    )
    with pytest.raises(
        SystemExit, match=re.escape("pinned set: ['us__scenario_002__snap']")
    ):
        driver.reworded_since_seed()


def test_reworded_since_seed_refuses_a_pinned_case_left_as_it_was(explanation_repo):
    explanation_repo(
        EXPLANATION_ROWS,
        _reword(EXPLANATION_ROWS, 1),
        {"us__scenario_000__snap", "us__scenario_001__snap"},
    )
    with pytest.raises(
        SystemExit, match=re.escape("pinned set: ['us__scenario_000__snap']")
    ):
        driver.reworded_since_seed()


@pytest.mark.parametrize("change", ["added", "removed"])
def test_reworded_since_seed_refuses_a_changed_set_of_cases(explanation_repo, change):
    extra = {"scenario_id": "scenario_009", "variable": "snap", "explanation": "New."}
    after = EXPLANATION_ROWS + [extra] if change == "added" else EXPLANATION_ROWS[:-1]
    explanation_repo(EXPLANATION_ROWS, after, set())
    with pytest.raises(SystemExit, match="explanation keys changed since the seed"):
        driver.reworded_since_seed()


def test_reworded_since_seed_names_a_commit_it_cannot_read(
    explanation_repo, monkeypatch
):
    explanation_repo(EXPLANATION_ROWS, EXPLANATION_ROWS, set())
    monkeypatch.setattr(driver, "SEED_RELEASE_COMMIT", "0" * 40)
    with pytest.raises(SystemExit, match="cannot read .* at 000000000000"):
        driver.reworded_since_seed()


def test_a_reordered_explanation_file_rewords_nothing(explanation_repo):
    explanation_repo(EXPLANATION_ROWS, EXPLANATION_ROWS[::-1], set())
    assert driver.reworded_since_seed() == frozenset()


EXPLANATION_TEXT = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs", "Cc"), whitelist_characters="\n,\"' "
    ),
    max_size=30,
)


@settings(max_examples=100, deadline=None)
@given(texts=st.lists(EXPLANATION_TEXT, min_size=1, max_size=8), data=st.data())
def test_reworded_since_seed_is_exactly_the_rows_that_differ(texts, data):
    """With git stubbed: for any explanations and any reworded rows, the
    derived set is those rows; it is returned when it is the pinned set and
    refused, naming the difference, when it is not."""
    count = len(texts)
    changed = data.draw(st.sets(st.integers(min_value=0, max_value=count - 1)))
    pinned_rows = data.draw(
        st.one_of(
            st.just(changed), st.sets(st.integers(min_value=0, max_value=count - 1))
        )
    )
    before = [
        {"scenario_id": f"scenario_{i:03d}", "variable": "snap", "explanation": text}
        for i, text in enumerate(texts)
    ]
    blobs = {
        "seed-commit": _explanations_csv(before),
        "base-commit": _explanations_csv(_reword(before, *changed)),
    }
    asked = []

    def run(command, capture_output):
        commit_id, path = command[-1].split(":", 1)
        asked.append(path)
        return SimpleNamespace(returncode=0, stdout=blobs[commit_id], stderr=b"")

    def cases(rows):
        return frozenset(f"us__scenario_{i:03d}__snap" for i in rows)

    with contextlib.ExitStack() as stack:
        stack.enter_context(
            mock.patch.object(driver, "subprocess", SimpleNamespace(run=run))
        )
        stack.enter_context(
            mock.patch.object(driver, "SEED_RELEASE_COMMIT", "seed-commit")
        )
        stack.enter_context(mock.patch.object(driver, "BASE_COMMIT", "base-commit"))
        stack.enter_context(
            mock.patch.object(driver, "REWORDED_SINCE_SEED", cases(pinned_rows))
        )
        if changed == pinned_rows:
            assert driver.reworded_since_seed() == cases(changed)
        else:
            difference = sorted(cases(changed) ^ cases(pinned_rows))
            with pytest.raises(SystemExit, match=re.escape(str(difference))):
                driver.reworded_since_seed()
    assert asked == [str(driver.REFERENCE_EXPLANATIONS)] * 2


# --- The committed seed --------------------------------------------------------


def _committed_seed_digest() -> dict[str, dict[str, str]]:
    lines = driver.SEED_DIGEST.read_text().splitlines()
    assert lines[0] == "case_id,prompt_sha256,verdict_sha256"
    rows = [line.split(",") for line in lines[1:]]
    return {
        case: {"prompt_sha256": prompt, "verdict_sha256": verdict}
        for case, prompt, verdict in rows
    }


def test_the_committed_seed_digest_is_the_pinned_one():
    """Runs anywhere: the committed digest hashes to the pin and spells each
    of release 20261006's 674 judged cases once."""
    raw = driver.SEED_DIGEST.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == driver.SEED_DIGEST_SHA256
    seed = _committed_seed_digest()
    assert driver.seed_digest_text(seed).encode() == raw
    assert len(seed) == 674
    hexes = [value for item in seed.values() for value in item.values()]
    assert all(len(h) == 64 and set(h) <= set("0123456789abcdef") for h in hexes)
    medicaid = seed["us__scenario_023__head_medicaid_eligible"]
    assert medicaid["prompt_sha256"].startswith("339d113a")


def test_every_ruled_output_and_reworded_case_is_a_judged_seed_case():
    """Runs anywhere: each of the ten ruled outputs and the nine reworded
    cases is a case the seed judged, so a stage holds a verdict for it."""
    seed = _committed_seed_digest()
    assert RULED_CASES <= set(seed)
    assert driver.REWORDED_SINCE_SEED <= set(seed)


def test_every_committed_adjudication_decides_a_case_the_seed_judged():
    """Runs anywhere: a recorded decision of release 20261006 rules on a judge
    verdict, so its case is one of the seed's judged cases."""
    seed = _committed_seed_digest()
    assert {driver.case_id(entry) for entry in driver.base_adjudications()} <= set(seed)


def test_the_committed_seed_digest_matches_the_real_seed():
    """Local only: the digest equals the seed copy on this machine."""
    if not SEED.is_dir():
        pytest.skip("release 20261006's audit is not on this machine")
    assert driver.seed_digest_text(driver.seed_digest(SEED)) == (
        driver.SEED_DIGEST.read_text()
    )


def test_the_committed_adjudications_keep_the_seed_judge_verdicts():
    """Local only: every decision release 20261006 recorded keeps its seed
    verdict's class, 023 Medicaid included."""
    if not SEED.is_dir():
        pytest.skip("release 20261006's audit is not on this machine")
    from freeze_snapshot import verify_adjudications_keep_judge_verdicts

    verify_adjudications_keep_judge_verdicts(
        driver.base_adjudications(), SEED / "cases"
    )
    case = SEED / "cases/us__scenario_023__head_medicaid_eligible"
    meta = json.loads((case / "verdict.meta.json").read_text())
    assert meta["prompt_sha256"] == driver.digest(case / "prompt.md")


def test_each_20261006_entry_names_its_seed_verdict_as_its_sidecar_records_it():
    """Local only: the restate script requires a re-opened entry to name its
    seed verdict, which it builds from the seed's sha256-bound sidecar: judge,
    classes, flag, flag source and UTC day. It holds for all 77 entries."""
    if not SEED.is_dir():
        pytest.skip("release 20261006's audit is not on this machine")
    from date_adds0928_judge_verdicts import WAVE_FLAGS, _bound_verdict
    from restate_gpt61sol_adjudications import named_item, replaced_item

    waved = frozenset(json.loads(WAVE_FLAGS.read_text()))
    base = driver.base_adjudications()
    assert len(base) == 77
    for entry in base:
        found = _bound_verdict(SEED / "cases" / driver.case_id(entry))
        assert found is not None, driver.case_id(entry)
        key = f"{entry['scenario_id']}:{entry['variable']}"
        assert named_item(entry) == replaced_item(found, key in waved), entry


@pytest.mark.slow
def test_every_seed_prompt_rerenders_except_the_nine_reworded(tmp_path):
    """Local only: release 20261006's 46-model board, as BASE_COMMIT holds it,
    renders exactly the seed's cases, and every seed prompt except the nine
    REWORDED_SINCE_SEED, whose reference explanations it reworded (this reads
    the 43 MB predictions from git into scratch). So
    check_prompt_changes may attribute every other changed or new prompt to
    Claude Haiku 5.5 joining its case."""
    if not (SEED.is_dir() and GROUNDING.is_file()):
        pytest.skip("release 20261006's audit or grounding is not on this machine")
    from policybench.audit import prepare_audit

    bundle = tmp_path / "publish" / driver.RUN_NAME
    (bundle / "us").mkdir(parents=True)
    for name in (*driver.REFERENCE_FILES, "predictions.csv.gz"):
        (bundle / "us" / name).write_bytes(base_blob(SNAPSHOT_PATH / name))
    (bundle / "annotations").mkdir()
    for name in driver.ANNOTATION_FILES:
        (bundle / "annotations" / name).write_bytes(
            base_blob(Path("annotations") / driver.RUN_NAME / name)
        )
    grounding = pd.read_csv(GROUNDING)
    lookup = {
        (str(r.scenario_id), str(r.variable)): str(r.grounding)
        for r in grounding.itertuples()
    }
    audit = tmp_path / "audit"
    # prepare renders with object strings, as resolve_base sets them.
    arrow = hasattr(pd.options, "future") and hasattr(pd.options.future, "infer_string")
    with (
        pd.option_context("future.infer_string", False)
        if arrow
        else contextlib.nullcontext()
    ):
        prepare_audit(bundle / "us", audit, grounding_lookup=lookup)
    # The manifest records each case's reference derivation, so it differs
    # from the seed's in that field of the nine cases and nowhere else.
    ours, seeds = (
        [json.loads(line) for line in (root / "cases.jsonl").read_text().splitlines()]
        for root in (audit, SEED)
    )
    assert [item["case_id"] for item in ours] == [item["case_id"] for item in seeds]
    moved = {}
    for item, seed_item in zip(ours, seeds):
        fields = {
            k for k in item.keys() | seed_item.keys() if item.get(k) != seed_item.get(k)
        }
        if fields:
            moved[item["case_id"]] = fields
    assert set(moved) == driver.REWORDED_SINCE_SEED
    assert set().union(*moved.values()) == {"reference_derivation"}
    rendered = driver.seed_prompt_digests(audit)
    seed = driver.seed_prompt_digests(SEED)
    assert set(rendered) == set(seed) and len(rendered) == 674
    differ = {case for case in rendered if rendered[case] != seed[case]}
    assert differ == driver.REWORDED_SINCE_SEED


def test_the_stage_reopens_every_ruled_output_and_reworded_case():
    """Local only, read-only: the live stage's prompt-changes.json is what
    check_prompt_changes derives from its prompts and the bound seed (445
    kept, 229 changed, 2 added); every re-opened case names Claude Haiku 5.5,
    and all ten ruled outputs and nine reworded cases are re-opened."""
    if not (STAGE / driver.PROMPT_CHANGES).is_file():
        pytest.skip("needs the Claude Haiku 5.5 stage")
    recorded = json.loads((STAGE / driver.PROMPT_CHANGES).read_text())
    seed = json.loads((STAGE / "stage.json").read_text())["seed"]
    derived = driver.check_prompt_changes(
        STAGE / "audit", {case: item["prompt_sha256"] for case, item in seed.items()}
    )
    assert {key: sorted(value) for key, value in derived.items()} == recorded
    assert {key: len(value) for key, value in recorded.items()} == {
        "kept": 445,
        "changed": 229,
        "added": 2,
    }
    reopened = {*recorded["changed"], *recorded["added"]}
    assert RULED_CASES <= reopened
    assert driver.REWORDED_SINCE_SEED <= set(recorded["changed"])
    manifest = {
        item["case_id"]: item
        for item in map(
            json.loads, (STAGE / "audit/cases.jsonl").read_text().splitlines()
        )
    }
    assert all(NEW in manifest[case]["wrong_models"] for case in reopened)


def test_the_stage_holds_the_installed_release_exclusions():
    """Local only, read-only: install-exclusions ran on the live stage and
    bound the release's record in both copies."""
    receipt_path = STAGE / "stage.json"
    if not receipt_path.is_file():
        pytest.skip("needs the Claude Haiku 5.5 stage")
    receipt = json.loads(receipt_path.read_text())
    installed = receipt.get("exclusions_installed")
    if installed is None:
        pytest.skip("install-exclusions has not run on this stage")
    assert installed["sha256"] == release_sha() == driver.release_exclusions_sha256()
    assert installed["base_sha256"] == driver.BASE_REFERENCE_SHA256[EXCLUSIONS_NAME]
    assert installed["records"] == driver.RELEASE_EXCLUSIONS
    assert receipt["files"][BOUND_EXCLUSIONS] == release_sha()
    for target in (STAGE / "scoring", STAGE / "publish" / driver.RUN_NAME / "us"):
        assert driver.digest(target / EXCLUSIONS_NAME) == release_sha()


# --- The ruled records ---------------------------------------------------------


def test_the_spec_names_each_ruling_and_its_outputs():
    """The spec's two proposals name eight (d1022) and two (d994) outputs,
    its ten adjudications decide exactly those, and scenario_051's is the one
    restatement. spec_records gives the ten in (scenario, variable) order:
    four engine defects, four unlisted inputs and two later-published laws."""
    spec = real_spec()
    assert {"d1022", "d994"} <= set(spec["rulings"])
    outputs = [
        [tuple(output) for output in proposal["outputs"]]
        for proposal in spec["proposals"]
    ]
    assert [len(names) for names in outputs] == [8, 2]
    named = {output for names in outputs for output in names}
    assert {driver.spec_key(item) for item in spec["adjudications"]} == named
    assert len(spec["adjudications"]) == 10
    assert [driver.spec_key(item) for item in spec["restated_adjudications"]] == [
        SCENARIO_051
    ]
    records = driver.spec_records(spec)
    keys = [driver.spec_key(record) for record in records]
    assert keys == sorted(named)
    reasons = [record["reason_code"] for record in records]
    assert reasons.count("reference_engine_defect") == 4
    assert reasons.count("reference_depends_on_unlisted_input") == 4
    assert reasons.count("reference_law_published_after_freeze") == 2
    by_key = {driver.spec_key(record): record for record in records}
    for item in spec["adjudications"]:
        source, verdict = driver.EXCLUSION_REASON_CODES[
            by_key[driver.spec_key(item)]["reason_code"]
        ]
        assert item["adjudicated_failure_source"] == source
        assert item["reference_verdict"] == verdict
    for proposal in spec["proposals"]:
        assert driver.digest(REPO / proposal["path"]) == proposal["sha256"]


@pytest.fixture
def proposals(tmp_path, monkeypatch):
    """The two proposal files copied into a scratch root, and a spec that pins
    them; ``edit`` rewrites one file (and, unless told not to, its pin)."""
    root = tmp_path / "root"
    spec = real_spec()
    for proposal in spec["proposals"]:
        target = root / proposal["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO / proposal["path"]).read_bytes())
    monkeypatch.setattr(driver, "ROOT", root)

    def edit(index: int, change, *, repin: bool = True) -> dict:
        proposal = spec["proposals"][index]
        path = root / proposal["path"]
        doc = json.loads(path.read_text())
        change(doc)
        path.write_text(json.dumps(doc, indent=2) + "\n")
        if repin:
            proposal["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        return spec

    return root, spec, edit


def _louisiana(doc: dict) -> list[dict]:
    return doc["exclusions"]


def _adversary(doc: dict) -> list[dict]:
    return [r for cause in doc["root_causes"].values() for r in cause["exclusions"]]


def test_the_scratch_proposals_give_the_real_records(proposals):
    root, spec, _ = proposals
    with mock.patch.object(driver, "ROOT", REPO):
        expected = driver.spec_records(real_spec())
    assert driver.spec_records(spec) == expected


def test_a_proposal_file_off_its_pin_is_refused(proposals):
    root, spec, edit = proposals
    edit(1, lambda doc: doc.update(note=doc["note"] + " Edited."), repin=False)
    with pytest.raises(SystemExit, match="proposed_exclusions.json is not the file"):
        driver.spec_records(spec)


def _drop_051(doc: dict) -> None:
    doc["exclusions"] = [
        r for r in doc["exclusions"] if driver.spec_key(r) != SCENARIO_051
    ]


def _duplicate_077(doc: dict) -> None:
    doc["exclusions"].append(copy.deepcopy(doc["exclusions"][-1]))


def _edit_051(**fields):
    def change(doc: dict) -> None:
        for record in doc["exclusions"]:
            if driver.spec_key(record) == SCENARIO_051:
                record.update(fields)

    return change


RECORD_DEFECTS = {
    "missing": (_drop_051, "does not hold exactly the ruled outputs"),
    "duplicated": (_duplicate_077, "does not hold exactly the ruled outputs"),
    "unknown_reason_code": (
        _edit_051(reason_code="reference_typo"),
        "is not a 2026-10-06 developer record",
    ),
    "decided_on": (
        _edit_051(decided_on="2026-10-05"),
        "is not a 2026-10-06 developer record",
    ),
    "decided_by": (_edit_051(decided_by="max"), "is not a 2026-10-06 developer"),
    "engine_version": (
        _edit_051(engine_version="policyengine-us 2.15.16"),
        "on policyengine-us 2.15.17",
    ),
}


@pytest.mark.parametrize("defect", sorted(RECORD_DEFECTS))
def test_a_record_outside_the_ruling_is_refused(proposals, defect):
    _, spec, edit = proposals
    change, problem = RECORD_DEFECTS[defect]
    edit(1, change)
    with pytest.raises(SystemExit, match=problem):
        driver.spec_records(spec)


@pytest.mark.parametrize(
    "code", ["reference_engine_defect", "reference_depends_on_unlisted_input"]
)
def test_a_record_under_another_known_reason_code_is_refused_downstream(
    proposals, tmp_path, monkeypatch, code
):
    """spec_records refuses only an unknown reason code. A pinned file that
    gives scenario_051's record another known code is refused when the
    record is built (it lacks that code's fields) and when it is adjudicated
    (the spec's classes no longer match its reason)."""
    from policybench.reference_exclusions import ReferenceExclusionError

    _, spec, edit = proposals
    edit(1, _edit_051(reason_code=code))
    records = {driver.spec_key(r): r for r in driver.spec_records(spec)}
    assert records[SCENARIO_051]["reason_code"] == code
    with pytest.raises(ReferenceExclusionError, match="entry missing"):
        driver.build_release_exclusions(base_record(), spec)
    monkeypatch.setattr(driver, "load_spec", real_spec)
    with pytest.raises(SystemExit, match="the spec's classes do not match"):
        driver.exclusion_entry(
            _base_051(), _item(SCENARIO_051), records[SCENARIO_051], tmp_path
        )


def test_an_output_the_spec_names_and_the_file_lacks_is_refused(proposals):
    _, spec, _ = proposals
    spec["proposals"][1]["outputs"].append(["scenario_076", "state_income_tax"])
    with pytest.raises(SystemExit, match="does not hold exactly the ruled outputs"):
        driver.spec_records(spec)


def test_an_output_the_spec_drops_leaves_nine_records_and_is_refused(proposals):
    _, spec, _ = proposals
    spec["proposals"][1]["outputs"].pop()
    with pytest.raises(SystemExit, match="expected 10 records"):
        driver.spec_records(spec)


def test_two_proposals_cannot_rule_on_one_output(proposals):
    """scenario_051's record added to the adversary's file and outputs: two
    ruled records share an output."""
    _, spec, edit = proposals
    record = next(
        r
        for r in _louisiana(
            json.loads((REPO / spec["proposals"][1]["path"]).read_text())
        )
        if driver.spec_key(r) == SCENARIO_051
    )
    edit(
        0,
        lambda doc: next(iter(doc["root_causes"].values()))["exclusions"].append(
            copy.deepcopy(record)
        ),
    )
    spec["proposals"][0]["outputs"].append(list(SCENARIO_051))
    with pytest.raises(SystemExit, match="two ruled records share an output"):
        driver.spec_records(spec)


def test_an_unknown_record_pointer_is_refused(proposals):
    _, spec, _ = proposals
    spec["proposals"][1]["records"] = "rows"
    with pytest.raises(SystemExit, match="unknown record pointer"):
        driver.spec_records(spec)


# --- The release's exclusion record --------------------------------------------


def test_the_release_exclusions_are_the_base_plus_the_ten_ruled_records():
    """Every base record keeps its bytes and place, the ten (sorted) sit before
    the trailing scenario_023 record, the loader accepts 74, and the
    derivation gains exactly the spec's sentence before the 2026-09-29
    marker; the spec's record edits apply to the ruled records only."""
    from policybench.reference_exclusions import load_reference_exclusions

    base, spec = base_record(), real_spec()
    pristine = copy.deepcopy(base)
    out = driver.build_release_exclusions(base, spec)
    assert base == pristine
    records = out["exclusions"]
    assert len(records) == driver.RELEASE_EXCLUSIONS == 74
    dumps = functools.partial(json.dumps, indent=2)
    assert [dumps(r) for r in records[:63]] == [
        dumps(r) for r in base["exclusions"][:-1]
    ]
    assert dumps(records[-1]) == dumps(base["exclusions"][-1])
    assert driver.spec_key(records[-1]) == ("scenario_023", "head_medicaid_eligible")
    expected = copy.deepcopy(driver.spec_records(spec))
    edits = spec.get("record_edits", [])
    by_key = {driver.spec_key(r): r for r in expected}
    for edit in edits:
        record = by_key[driver.spec_key(edit)]
        assert record[edit["field"]] == edit["replace"]
        record[edit["field"]] = edit["with"]
    assert records[63:73] == expected
    # Each edit lands on its record's named field and nowhere else.
    for edit in edits:
        built = next(r for r in records if driver.spec_key(r) == driver.spec_key(edit))
        assert built[edit["field"]] == edit["with"]
    assert list(out) == list(base)
    assert {k: v for k, v in out.items() if k not in ("exclusions", "derivation")} == {
        k: v for k, v in base.items() if k not in ("exclusions", "derivation")
    }
    insert = spec["derivation_insert"]
    assert out["derivation"] == base["derivation"].replace(
        insert["before"], insert["text"] + insert["before"]
    )
    assert out["derivation"].count(insert["text"]) == 1
    assert out["derivation"].replace(insert["text"], "", 1) == base["derivation"]
    reasons = [record["reason_code"] for record in records]
    assert reasons.count("reference_depends_on_unlisted_input") == 40
    assert reasons.count("reference_engine_defect") == 32
    assert reasons.count("reference_law_published_after_freeze") == 2
    text = driver.exclusions_text(out)
    with tempfile.TemporaryDirectory() as scratch:
        (Path(scratch) / EXCLUSIONS_NAME).write_text(text)
        assert len(load_reference_exclusions(Path(scratch))) == 74
    sha = hashlib.sha256(text.encode()).hexdigest()
    assert sha == driver.release_exclusions_sha256() == release_sha()


@settings(max_examples=30, deadline=None)
@given(ruled=st.integers(min_value=0, max_value=9), data=st.data())
def test_a_ruled_output_already_excluded_is_refused(ruled, data):
    """Wherever one of the ten already sits in the base record, the build
    refuses rather than list it twice."""
    with mock.patch.object(driver, "ROOT", REPO):
        records = driver.spec_records(real_spec())
    base = base_record()
    at = data.draw(st.integers(min_value=0, max_value=len(base["exclusions"]) - 1))
    base["exclusions"].insert(at, records[ruled])
    with mock.patch.object(driver, "ROOT", REPO):
        with pytest.raises(SystemExit, match="a ruled output is already excluded"):
            driver.build_release_exclusions(base, real_spec())


def test_a_base_that_does_not_end_with_scenario_023_is_refused():
    base = base_record()
    base["exclusions"].insert(0, base["exclusions"].pop())
    with pytest.raises(SystemExit, match="does not end with the audit's scenario_023"):
        driver.build_release_exclusions(base, real_spec())


@pytest.mark.parametrize("times", [0, 2])
def test_the_derivation_must_hold_its_marker_exactly_once(times):
    base, spec = base_record(), real_spec()
    before = spec["derivation_insert"]["before"]
    base["derivation"] = base["derivation"].replace(before, " Elsewhere")
    base["derivation"] += before * times
    with pytest.raises(SystemExit, match="2026-09-29 marker exactly once"):
        driver.build_release_exclusions(base, spec)


@settings(max_examples=25, deadline=None)
@given(data=st.data())
def test_the_ruled_records_come_out_in_one_order_whatever_the_files_order(data):
    """Any order of the proposals, of each one's outputs, of the adversary's
    root causes and of the records inside each file builds the same bytes."""
    spec = real_spec()
    expected = release_text()
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        for proposal in spec["proposals"]:
            doc = json.loads((REPO / proposal["path"]).read_text())
            if "root_causes" in doc:
                causes = list(doc["root_causes"].items())
                causes = data.draw(st.permutations(causes))
                doc["root_causes"] = {
                    name: {
                        **cause,
                        "exclusions": data.draw(st.permutations(cause["exclusions"])),
                    }
                    for name, cause in causes
                }
            else:
                doc["exclusions"] = data.draw(st.permutations(doc["exclusions"]))
            path = root / proposal["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(doc, indent=2) + "\n")
            proposal["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            proposal["outputs"] = data.draw(st.permutations(proposal["outputs"]))
        spec["proposals"] = data.draw(st.permutations(spec["proposals"]))
        with mock.patch.object(driver, "ROOT", root):
            built = driver.build_release_exclusions(base_record(), spec)
    assert driver.exclusions_text(built) == expected


# --- install-exclusions --------------------------------------------------------


@pytest.fixture
def installable(tmp_path):
    """A stage as prepare leaves it: release 20261006's record in the scoring
    source and the bundle, bound in stage.json beside another input."""
    stage = tmp_path / "stage"
    copies = [stage / "scoring", stage / "publish" / driver.RUN_NAME / "us"]
    for target in copies:
        target.mkdir(parents=True)
        (target / EXCLUSIONS_NAME).write_bytes(
            base_blob(SNAPSHOT_PATH / EXCLUSIONS_NAME)
        )
    other = stage / "inputs" / SLUG / "predictions.csv"
    other.parent.mkdir(parents=True)
    other.write_text("model,scenario_id,variable\n")
    receipt = {
        "partial": False,
        "early": False,
        "files": {
            BOUND_EXCLUSIONS: driver.BASE_REFERENCE_SHA256[EXCLUSIONS_NAME],
            f"inputs/{SLUG}/predictions.csv": driver.digest(other),
        },
        "seed": {"us__s0__snap": {"prompt_sha256": "a" * 64}},
    }
    (stage / "stage.json").write_text(json.dumps(receipt))
    return stage, copies, receipt


def test_install_exclusions_rebinds_the_stage_and_is_idempotent(installable):
    stage, copies, receipt = installable
    driver.install_exclusions(SimpleNamespace(stage_dir=stage))
    for target in copies:
        assert (target / EXCLUSIONS_NAME).read_text() == release_text()
    after = json.loads((stage / "stage.json").read_text())
    assert after["files"] == {**receipt["files"], BOUND_EXCLUSIONS: release_sha()}
    assert after["exclusions_installed"] == {
        "base_sha256": driver.BASE_REFERENCE_SHA256[EXCLUSIONS_NAME],
        "sha256": release_sha(),
        "spec_sha256": driver.digest(REPO / driver.SPEC_PATH),
        "records": 74,
    }
    assert {
        k: v for k, v in after.items() if k not in ("files", "exclusions_installed")
    } == {k: v for k, v in receipt.items() if k != "files"}
    # Every binding the resume check reads holds after the rebind.
    for name, pin in after["files"].items():
        assert driver.digest(stage / name) == pin
    written = {p: p.read_bytes() for p in stage.rglob("*") if p.is_file()}
    driver.install_exclusions(SimpleNamespace(stage_dir=stage))
    assert {p: p.read_bytes() for p in stage.rglob("*") if p.is_file()} == written


def test_install_exclusions_requires_the_bound_base_record_the_first_time(
    installable,
):
    stage, copies, receipt = installable
    receipt["files"][BOUND_EXCLUSIONS] = "0" * 64
    (stage / "stage.json").write_text(json.dumps(receipt))
    before = {p: p.read_bytes() for p in stage.rglob("*") if p.is_file()}
    with pytest.raises(SystemExit, match="is not release 20261006's"):
        driver.install_exclusions(SimpleNamespace(stage_dir=stage))
    assert {p: p.read_bytes() for p in stage.rglob("*") if p.is_file()} == before


def test_install_exclusions_requires_a_bound_record(installable):
    stage, _, receipt = installable
    del receipt["files"][BOUND_EXCLUSIONS]
    (stage / "stage.json").write_text(json.dumps(receipt))
    with pytest.raises(SystemExit, match="does not bind the exclusions"):
        driver.install_exclusions(SimpleNamespace(stage_dir=stage))


# --- Adjudicating the ten ------------------------------------------------------


def _ruled_verdicts(cases: Path, *, flagged: bool = False) -> Path:
    """A bound Opus 5.5 verdict for each ruled output, judged on WRITTEN_ON."""
    for item in real_spec()["adjudications"]:
        case = cases / ruled_case(item)
        case.mkdir(parents=True, exist_ok=True)
        (case / "prompt.md").write_text(f"Classify {case.name}.\n")
        write_verdict(
            case,
            {**_verdict([NEW]), "reference_suspect": flagged},
            judged_at_utc=f"{WRITTEN_ON}T02:00:00+00:00",
        )
    return cases


def _all_verdicts(cases: Path, entries: list[dict]) -> Path:
    """Verdicts that agree with each recorded decision's judge fields, as the
    seed's do, for every case the base record decides."""
    for entry in entries:
        case = cases / driver.case_id(entry)
        if (case / "verdict.json").is_file():
            continue
        case.mkdir(parents=True, exist_ok=True)
        (case / "prompt.md").write_text(f"Classify {case.name}.\n")
        verdict = {
            **_verdict(["m1"], entry["judge_failure_source"]),
            "case_failure_subtype": entry["judge_failure_subtype"],
            "reference_suspect": bool(entry.get("judge_reference_suspect")),
        }
        write_verdict(case, verdict, judged_at_utc="2026-09-30T02:00:00+00:00")
    return cases


def _records_by_key() -> dict:
    with mock.patch.object(driver, "ROOT", REPO):
        return {driver.spec_key(r): r for r in driver.spec_records(real_spec())}


def _item(key) -> dict:
    return next(i for i in real_spec()["adjudications"] if driver.spec_key(i) == key)


NEW_ITEMS = [
    item for item in real_spec()["adjudications"] if ruled_case(item) != CASE_051
]


@pytest.mark.parametrize("item", NEW_ITEMS, ids=ruled_case)
@pytest.mark.parametrize("flagged", [False, True])
def test_a_new_ruled_entry_carries_its_bound_verdict_in_entry_field_order(
    tmp_path, item, flagged
):
    from release_20261006 import ENTRY_FIELDS

    cases = _ruled_verdicts(tmp_path / "cases", flagged=flagged)
    record = _records_by_key()[driver.spec_key(item)]
    entry = driver.exclusion_entry(None, item, record, cases / ruled_case(item))
    assert list(entry) == list(ENTRY_FIELDS)
    source, verdict = driver.EXCLUSION_REASON_CODES[record["reason_code"]]
    basis = {
        "engine_defect": record.get("law"),
        "unlisted_input": record.get("unlisted_input"),
        "later_law": record.get("published"),
    }[verdict]
    assert basis
    assert entry == {
        "country": "us",
        "scenario_id": item["scenario_id"],
        "variable": item["variable"],
        "judge_model": "claude-opus-5-5",
        "judge_failure_source": "llm_error",
        "judge_failure_subtype": "thresholds_rates",
        "adjudicated_failure_source": source,
        "adjudicated_failure_subtype": item["adjudicated_failure_subtype"],
        "adjudicated_on": "2026-10-06",
        "adjudicator": "developer",
        "excluded_from_scoring": True,
        "judge_reference_suspect": flagged,
        "reference_verdict": verdict,
        "reference_basis": basis,
        "reasoning": item["reasoning"],
        "judged_on_utc": WRITTEN_ON,
    }


@pytest.mark.parametrize("defect", ["missing", "unbound"])
def test_a_new_ruled_entry_needs_a_bound_verdict(tmp_path, defect):
    item = NEW_ITEMS[0]
    cases = _ruled_verdicts(tmp_path / "cases")
    case = cases / ruled_case(item)
    if defect == "missing":
        (case / "verdict.json").unlink()
    else:
        (case / "verdict.json").write_text(json.dumps(_verdict(["other"])))
    with pytest.raises(SystemExit, match="no bound verdict|does not bind its verdict"):
        driver.exclusion_entry(
            None, item, _records_by_key()[driver.spec_key(item)], case
        )


@pytest.mark.parametrize(
    "field, value",
    [
        ("adjudicated_failure_source", "prompt_ambiguity"),
        ("reference_verdict", "unlisted_input"),
    ],
)
def test_the_spec_classes_must_match_the_records_reason(tmp_path, field, value):
    item = {**_item(("scenario_018", "state_income_tax_before_refundable_credits"))}
    item[field] = value
    cases = _ruled_verdicts(tmp_path / "cases")
    with pytest.raises(SystemExit, match="the spec's classes do not match"):
        driver.exclusion_entry(
            None,
            item,
            _records_by_key()[driver.spec_key(item)],
            cases / ruled_case(item),
        )


def _base_051() -> dict:
    return next(
        e
        for e in base_adjudication_record()["adjudications"]
        if driver.spec_key(e) == SCENARIO_051
    )


def test_scenario_051s_ruling_moves_only_its_decision_fields(tmp_path):
    """The 2026-09-22 regeneration becomes a later-law exclusion in place: the
    seven decision fields take the ruling's values, excluded_from_scoring
    goes right after adjudicator, the reasoning keeps the earlier text ahead
    of the ruling's, and every other field keeps its value and place."""
    base = _base_051()
    item = _item(SCENARIO_051)
    record = _records_by_key()[SCENARIO_051]
    entry = driver.exclusion_entry(base, item, record, tmp_path / "unused")
    assert "excluded_from_scoring" not in base
    names = list(base)
    at = names.index("adjudicator") + 1
    assert list(entry) == names[:at] + ["excluded_from_scoring"] + names[at:]
    assert {name: entry[name] for name in DECISION_FIELDS} == {
        "adjudicated_failure_source": "reference_later_law",
        "adjudicated_failure_subtype": "taxable_income_or_deductions",
        "adjudicated_on": "2026-10-06",
        "adjudicator": "developer",
        "excluded_from_scoring": True,
        "reference_verdict": "later_law",
        "reference_basis": record["published"],
    }
    assert entry["reasoning"] == base["reasoning"] + " " + item["reasoning"]
    for name in names:
        if name not in DECISION_FIELDS and name != "reasoning":
            assert entry[name] == base[name], name


JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=8),
    lambda children: (
        st.lists(children, max_size=3)
        | st.dictionaries(st.text(max_size=5), children, max_size=3)
    ),
    max_leaves=6,
)
EXTRA_NAMES = st.sampled_from(
    sorted(
        {
            "judge_rejudged_on",
            "judge_previous",
            "judge_reference_suspect_source",
            "judged_on_utc",
            "adjudicated_verdict",
            "note",
        }
    )
) | st.from_regex(r"x_[a-z]{1,6}", fullmatch=True)


@settings(max_examples=150, deadline=None)
@given(
    extras=st.lists(
        st.tuples(EXTRA_NAMES, JSON_VALUES, st.integers(min_value=0, max_value=30)),
        max_size=5,
    ),
    flag_at=st.none() | st.integers(min_value=0, max_value=30),
    missing=st.none() | st.sampled_from(DECISION_FIELDS),
)
def test_a_restated_decision_keeps_every_other_field_in_place(extras, flag_at, missing):
    """For any existing entry (scenario_051's with arbitrary extra fields at
    arbitrary places, with or without an excluded_from_scoring flag), the
    ruling sets the seven decision fields and appends its reasoning, and no
    other field moves or changes. An entry missing a decision field other
    than the flag is refused."""
    item = _item(SCENARIO_051)
    record = _records_by_key()[SCENARIO_051]
    items = list(_base_051().items())
    for name, value, at in extras:
        if name in dict(items):
            continue
        items.insert(min(at, len(items)), (name, value))
    if flag_at is not None:
        items.insert(min(flag_at, len(items)), ("excluded_from_scoring", False))
    if missing is not None:
        items = [(n, v) for n, v in items if n != missing]
    base = dict(items)
    if missing not in (None, "excluded_from_scoring"):
        with pytest.raises(SystemExit, match="a decision field is missing"):
            driver.exclusion_entry(base, item, record, Path("unused"))
        return
    entry = driver.exclusion_entry(base, item, record, Path("unused"))
    others = [n for n in base if n not in DECISION_FIELDS]
    assert [n for n in entry if n not in DECISION_FIELDS] == others
    for name in others:
        if name != "reasoning":
            assert json.dumps(entry[name]) == json.dumps(base[name]), name
    assert entry["reasoning"] == base["reasoning"] + " " + item["reasoning"]
    assert entry["excluded_from_scoring"] is True
    assert set(DECISION_FIELDS) <= set(entry)
    if "excluded_from_scoring" in base:
        assert list(entry) == list(base)
    else:
        names = list(entry)
        assert names.index("excluded_from_scoring") == names.index("adjudicator") + 1
        assert [n for n in names if n != "excluded_from_scoring"] == list(base)


@pytest.fixture
def ruled(tmp_path, written_spec):
    """Release 20261006's record with the ten ruled outputs decided, the cases
    directory whose bound verdicts the new entries carry, and both records
    keyed by case."""
    from policybench.adjudications import parse_adjudications

    cases = _all_verdicts(
        _ruled_verdicts(tmp_path / "cases"), base_adjudication_record()["adjudications"]
    )
    record = base_adjudication_record()
    staged = driver.exclusion_adjudications(record, cases)
    entries = parse_adjudications(staged, "staged")
    before = {driver.case_id(e): e for e in record["adjudications"]}
    after = {driver.case_id(e): e for e in entries}
    return SimpleNamespace(
        record=record, staged=staged, cases=cases, before=before, after=after
    )


def test_the_ruled_record_appends_nine_and_restates_scenario_051_in_place(ruled):
    """86 decisions, 74 of them exclusions: every 20261006 entry other than
    scenario_051's keeps its bytes and place, scenario_051's stays at its
    index, the nine new ones follow in the spec's order, and the top level
    changes only in its date conventions."""
    base, staged = ruled.record, ruled.staged
    entries = staged["adjudications"]
    assert len(entries) == 86
    assert sum(bool(e.get("excluded_from_scoring")) for e in entries) == 74
    old = base["adjudications"]
    for index, entry in enumerate(old):
        if driver.spec_key(entry) == SCENARIO_051:
            assert driver.spec_key(entries[index]) == SCENARIO_051
            assert entries[index]["reference_verdict"] == "later_law"
        else:
            assert json.dumps(entries[index]) == json.dumps(entry)
    assert [driver.spec_key(e) for e in entries[len(old) :]] == [
        driver.spec_key(item) for item in NEW_ITEMS
    ]
    assert list(staged) == list(base)
    assert {
        k: v
        for k, v in staged.items()
        if k not in ("adjudications", "date_conventions")
    } == {
        k: v for k, v in base.items() if k not in ("adjudications", "date_conventions")
    }
    assert staged["date_conventions"] == driver.release_date_conventions(
        base["date_conventions"]
    )


def test_the_adjudications_exclude_exactly_the_installed_exclusions(ruled):
    """Triage's requirement: the decided record excludes exactly the 74
    outputs the release's exclusion record lists."""
    from policybench.adjudications import excluded_case_keys
    from policybench.reference_exclusions import exclusion_keys

    installed = json.loads(release_text())["exclusions"]
    assert excluded_case_keys(list(ruled.after.values())) == exclusion_keys(installed)
    assert len(exclusion_keys(installed)) == 74


def test_the_ruled_gate_passes_the_exact_built_entries(ruled):
    assert (
        driver.ruled_adjudication_problems(ruled.before, ruled.after, ruled.cases) == []
    )


def _swap_non_judge(entry: dict, index: int) -> dict:
    from restate_gpt61sol_adjudications import JUDGE_FIELDS

    names = list(entry)
    slots = [i for i, name in enumerate(names) if name not in JUDGE_FIELDS]
    a, b = slots[index % (len(slots) - 1)], slots[index % (len(slots) - 1) + 1]
    names[a], names[b] = names[b], names[a]
    return {name: entry[name] for name in names}


@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    case=st.sampled_from(sorted(RULED_CASES)),
    kind=st.sampled_from(["value", "order", "extra", "drop"]),
    data=st.data(),
)
def test_a_ruled_entry_edited_by_hand_is_refused(ruled, case, kind, data):
    """Any edit to a ruled entry is refused: a value, the key order, an added
    or a dropped field. On scenario_051 the edit is to a field outside the
    judge fields, which the restatement gate (verify_restatements) governs."""
    from restate_gpt61sol_adjudications import JUDGE_FIELDS

    after = copy.deepcopy(ruled.after)
    entry = after[case]
    editable = [n for n in entry if case != CASE_051 or n not in JUDGE_FIELDS]
    if kind == "value":
        name = data.draw(st.sampled_from(editable))
        value = data.draw(JSON_VALUES)
        assume(json.dumps(value) != json.dumps(entry[name]))
        entry[name] = value
    elif kind == "order":
        after[case] = _swap_non_judge(entry, data.draw(st.integers(0, 40)))
    elif kind == "extra":
        name = data.draw(st.from_regex(r"x_[a-z]{1,6}", fullmatch=True))
        entry[name] = data.draw(JSON_VALUES)
    else:
        del entry[data.draw(st.sampled_from(editable))]
    problems = driver.ruled_adjudication_problems(ruled.before, after, ruled.cases)
    assert problems and all(problem.startswith(case) for problem in problems)


@pytest.mark.parametrize("case", sorted(RULED_CASES))
def test_a_ruled_entry_that_is_missing_is_refused(ruled, case):
    after = {k: v for k, v in ruled.after.items() if k != case}
    assert driver.ruled_adjudication_problems(ruled.before, after, ruled.cases) == [
        f"{case}: no staged decision"
    ]


def test_scenario_051_cannot_drop_a_field_it_held(ruled):
    after = copy.deepcopy(ruled.after)
    del after[CASE_051]["reference_basis"]
    assert driver.ruled_adjudication_problems(ruled.before, after, ruled.cases) == [
        f"{CASE_051}: fields moved outside the ruling"
    ]


def _write_stage_record(tmp_path: Path, record: dict) -> Path:
    path = tmp_path / "publish" / driver.RUN_NAME / "annotations" / driver.ADJUDICATIONS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(driver.record_text(record))
    return path


def test_triage_accepts_the_ruled_record_on_release_20261006s_base(
    ruled, tmp_path, monkeypatch
):
    """stage_adjudications, triage's gate, takes the decided record against
    release 20261006's record from git, with the ten ruled cases re-opened."""
    monkeypatch.setattr(driver, "base_adjudication_record", base_adjudication_record)
    path = _write_stage_record(tmp_path / "stage", ruled.staged)
    text = path.read_text()
    entries = driver.stage_adjudications(path, RULED_CASES, [], ruled.cases)
    assert len(entries) == 86 and path.read_text() == text


@pytest.mark.parametrize(
    "tamper",
    ["drop_judge_previous", "edit_reasoning", "edit_new_entry_class"],
)
def test_triage_refuses_a_ruled_record_edited_by_hand(
    ruled, tmp_path, monkeypatch, tamper
):
    monkeypatch.setattr(driver, "base_adjudication_record", base_adjudication_record)
    staged = copy.deepcopy(ruled.staged)
    entries = {driver.case_id(e): e for e in staged["adjudications"]}
    if tamper == "drop_judge_previous":
        del entries[CASE_051]["judge_previous"]
        problem = "not restated by the restate script"
    elif tamper == "edit_reasoning":
        entries[CASE_051]["reasoning"] += " And more."
        problem = "ruled outputs"
    else:
        case = ruled_case(NEW_ITEMS[0])
        entries[case]["adjudicated_failure_subtype"] = "other"
        problem = "ruled outputs"
    path = _write_stage_record(tmp_path / "stage", staged)
    with pytest.raises(SystemExit, match=problem):
        driver.stage_adjudications(path, RULED_CASES, [], ruled.cases)


def _restate_051(tmp_path: Path, cases: Path) -> dict:
    """Release 20261006's record with scenario_051 restated by the restate
    script, as the stage's judge and restate steps leave it: Haiku 5.5
    re-opened the case and an Opus 5.5 judge gave a new verdict."""
    from restate_gpt61sol_adjudications import restate_entries

    seed = tmp_path / "seed-cases" / CASE_051
    seed.mkdir(parents=True)
    # The verdict release 20261006's entry names: judged 2026-09-30, not
    # flagging, with the flag an earlier 2026-09-22 run raised.
    write_verdict(
        seed,
        _verdict(["m1"]),
        judged_at_utc="2026-09-30T10:00:00+00:00",
    )
    stage = cases / CASE_051
    verdict = {
        **_verdict(["m1", NEW]),
        "case_failure_subtype": "taxable_income_or_deductions",
    }
    write_verdict(stage, verdict, judged_at_utc=f"{WRITTEN_ON}T03:00:00+00:00")
    record = base_adjudication_record()
    record["adjudications"], changes = restate_entries(
        record["adjudications"],
        cases,
        tmp_path / "seed-cases",
        {CASE_051},
        wave_flags={":".join(SCENARIO_051)},
    )
    assert len(changes) == 1
    return record


def test_adjudicate_exclusions_appends_nine_entries_and_restates_scenario_051_in_place(
    tmp_path, written_spec
):
    """The step on a stage whose scenario_051 entry the restate script
    restated: the restated judge fields stay, the ruling's decision fields
    replace the old ones in place, and the nine new entries are appended."""
    from policybench.adjudications import parse_adjudications

    stage = tmp_path / "stage"
    cases = _ruled_verdicts(stage / "audit" / "cases")
    restated = _restate_051(tmp_path, cases)
    path = _write_stage_record(stage, restated)
    driver.adjudicate_exclusions(SimpleNamespace(stage_dir=stage))
    written = json.loads(path.read_text())
    assert path.read_text() == driver.record_text(written)
    entries = parse_adjudications(written, path)
    before = {driver.case_id(e): e for e in restated["adjudications"]}
    after = {driver.case_id(e): e for e in entries}
    entry = after[CASE_051]
    assert entry["judge_failure_subtype"] == "taxable_income_or_deductions"
    assert entry["judge_rejudged_on"] == WRITTEN_ON
    assert len(entry["judge_previous"]) == 3
    assert entry["reference_verdict"] == "later_law"
    assert entry == driver.exclusion_entry(
        before[CASE_051],
        _item(SCENARIO_051),
        _records_by_key()[SCENARIO_051],
        cases / CASE_051,
    )
    index = [driver.case_id(e) for e in restated["adjudications"]].index(CASE_051)
    assert driver.case_id(written["adjudications"][index]) == CASE_051
    assert [driver.case_id(e) for e in written["adjudications"][77:]] == [
        ruled_case(item) for item in NEW_ITEMS
    ]


def test_adjudicate_exclusions_refuses_a_second_run(tmp_path, written_spec):
    stage = tmp_path / "stage"
    cases = _ruled_verdicts(stage / "audit" / "cases")
    path = _write_stage_record(stage, base_adjudication_record())
    driver.adjudicate_exclusions(SimpleNamespace(stage_dir=stage))
    once = path.read_text()
    with pytest.raises(SystemExit, match="already decided in the staged record"):
        driver.adjudicate_exclusions(SimpleNamespace(stage_dir=stage))
    assert path.read_text() == once
    assert cases.is_dir()


def test_adjudicate_exclusions_writes_nothing_without_every_bound_verdict(
    tmp_path, written_spec
):
    stage = tmp_path / "stage"
    cases = _ruled_verdicts(stage / "audit" / "cases")
    (cases / ruled_case(NEW_ITEMS[-1]) / "verdict.meta.json").unlink()
    path = _write_stage_record(stage, base_adjudication_record())
    text = path.read_text()
    with pytest.raises(SystemExit, match="no bound verdict"):
        driver.adjudicate_exclusions(SimpleNamespace(stage_dir=stage))
    assert path.read_text() == text


@pytest.mark.parametrize("change", ["drop_051", "decide_018"])
def test_exclusion_adjudications_needs_exactly_the_listed_restatement(
    tmp_path, written_spec, change
):
    cases = _ruled_verdicts(tmp_path / "cases")
    record = base_adjudication_record()
    if change == "drop_051":
        record["adjudications"] = [
            e for e in record["adjudications"] if driver.spec_key(e) != SCENARIO_051
        ]
    else:
        record["adjudications"].append({**_base_051(), "scenario_id": "scenario_018"})
    with pytest.raises(SystemExit, match="differ from the spec's restated list"):
        driver.exclusion_adjudications(record, cases)


def test_triage_accepts_scenario_051_restated_then_ruled(
    tmp_path, written_spec, monkeypatch
):
    monkeypatch.setattr(driver, "base_adjudication_record", base_adjudication_record)
    stage = tmp_path / "stage"
    cases = _ruled_verdicts(stage / "audit" / "cases")
    restated = _restate_051(tmp_path, cases)
    _all_verdicts(cases, restated["adjudications"])
    staged = driver.exclusion_adjudications(restated, cases)
    path = _write_stage_record(stage, staged)
    entries = driver.stage_adjudications(path, RULED_CASES, [], cases)
    assert len(entries) == 86


# --- The date conventions ------------------------------------------------------

WAVE_SENTENCE = (
    " The 2026-10-06 wave's decisions follow Max's rulings of 2026-10-06 "
    f"(17:11 UTC) and were written on {WRITTEN_ON} UTC."
)


def test_the_date_conventions_name_the_2026_10_06_wave(written_spec):
    conventions = base_adjudication_record()["date_conventions"]
    out = driver.release_date_conventions(conventions)
    assert out == conventions.replace(
        driver.DATE_CONVENTIONS_BASE, driver.DATE_CONVENTIONS_WAVES
    ).replace(
        driver.DATE_CONVENTIONS_ANCHOR, driver.DATE_CONVENTIONS_ANCHOR + WAVE_SENTENCE
    )
    assert out.count("2026-10-06 wave's decisions") == 1
    assert out.count(driver.DATE_CONVENTIONS_WAVES) == 1
    assert driver.DATE_CONVENTIONS_BASE not in out


def test_the_wave_cannot_be_named_twice(written_spec):
    once = driver.release_date_conventions(
        base_adjudication_record()["date_conventions"]
    )
    with pytest.raises(SystemExit, match="are not release 20261006's"):
        driver.release_date_conventions(once)


def test_the_date_conventions_need_the_day_the_decisions_were_written():
    """As committed, the spec names no such day, so the step stops."""
    if "adjudications_written_on" in real_spec():
        pytest.skip("the spec names adjudications_written_on")
    with pytest.raises(KeyError, match="adjudications_written_on"):
        driver.release_date_conventions(base_adjudication_record()["date_conventions"])


FILLER = st.text(alphabet="abc ().,0123456789-", max_size=20)


@settings(max_examples=150, deadline=None)
@given(
    parts=st.lists(FILLER, min_size=5, max_size=5),
    bases=st.integers(min_value=0, max_value=2),
    anchors=st.integers(min_value=0, max_value=2),
    written=st.dates().map(lambda day: day.isoformat()),
)
def test_release_date_conventions_requires_the_base_text_exactly_once(
    parts, bases, anchors, written
):
    """For any text: it names the wave in place of the base sentence and adds
    the wave's sentence after the anchor exactly when each occurs once;
    otherwise it refuses."""
    a, b, c, d, e = parts
    base, anchor = driver.DATE_CONVENTIONS_BASE, driver.DATE_CONVENTIONS_ANCHOR
    text = a + (base + b) * bases + c + (anchor + d) * anchors + e
    assume(text.count(base) == bases and text.count(anchor) == anchors)
    spec = {**real_spec(), "adjudications_written_on": written}
    with mock.patch.object(driver, "load_spec", lambda: spec):
        if (bases, anchors) != (1, 1):
            with pytest.raises(SystemExit, match="are not release 20261006's"):
                driver.release_date_conventions(text)
            return
        out = driver.release_date_conventions(text)
    sentence = WAVE_SENTENCE.replace(WRITTEN_ON, written)
    assert out == (
        a + driver.DATE_CONVENTIONS_WAVES + b + c + anchor + sentence + d + e
    )


# --- Triage --------------------------------------------------------------------

CONVENTIONS = (
    "Dates are UTC days. "
    + driver.DATE_CONVENTIONS_BASE
    + " The 2026-10-05 wave's decisions follow Max's rulings "
    + driver.DATE_CONVENTIONS_ANCHOR
    + " The rest is as before."
)


def _base_record(*entries) -> dict:
    return {"date_conventions": CONVENTIONS, "adjudications": list(entries)}


def _record(*entries) -> str:
    """A staged record: the date conventions name the wave, as the adjudicate
    step writes them (load_spec must be patched with a written day)."""
    return driver.record_text(
        {
            "date_conventions": driver.release_date_conventions(CONVENTIONS),
            "adjudications": list(entries),
        }
    )


@pytest.mark.parametrize(
    "suspect, failure_source, report",
    [
        (True, "llm_error", "reference-flags.csv"),
        (False, "reference_engine_defect", "unresolved-rows.csv"),
        (False, "prompt_ambiguity", "unresolved-rows.csv"),
    ],
)
def test_triage_stops_and_records_flags_for_evidence_review(
    tmp_path, monkeypatch, unruled_spec, suspect, failure_source, report
):
    import policybench.audit

    stage = tmp_path / "stage"
    bundle = stage / "publish" / driver.RUN_NAME
    (bundle / "annotations").mkdir(parents=True)
    rows = pd.DataFrame(
        [
            {
                "country": "us",
                "scenario_id": "scenario_000",
                "variable": "snap",
                "model": NEW,
                "failure_source": failure_source,
                "failure_subtype": "thresholds_rates",
                "annotation": "Evidence needed.",
                "reference_suspect": suspect,
            }
        ]
    )
    cases = pd.DataFrame(
        [
            {
                "country": "us",
                "scenario_id": "scenario_000",
                "variable": "snap",
                "wrong_model_count": 1,
                "reference_suspect": suspect,
                "case_failure_source": failure_source,
                "case_failure_subtype": "thresholds_rates",
                "case_annotation": "Evidence needed.",
                "reference_bug_hypothesis": "Check the threshold.",
            }
        ]
    )
    monkeypatch.setattr(driver, "validate_verdicts", lambda *a, **kw: [])
    monkeypatch.setattr(driver, "load_seed", lambda stage: {})
    monkeypatch.setattr(driver, "base_adjudication_record", lambda: _base_record())
    (stage / driver.PROMPT_CHANGES).write_text(
        json.dumps({"added": [], "changed": [], "kept": []})
    )
    (bundle / "annotations" / driver.ADJUDICATIONS).write_text(_record())
    monkeypatch.setattr(
        policybench.audit,
        "collect_audit",
        lambda *a, **kw: {
            "missing": pd.DataFrame(),
            "hedged": pd.DataFrame(),
            "row": rows,
            "case": cases,
        },
    )
    with pytest.raises(SystemExit, match="triage required"):
        driver.triage(SimpleNamespace(stage_dir=stage), bundle)
    assert len(pd.read_csv(stage / report)) == 1
    assert not (stage / "release-ready.json").exists()


CASE = "us__scenario_000__snap"
DECISION = {
    "country": "us",
    "scenario_id": "scenario_000",
    "variable": "snap",
    "judge_model": "claude-opus-5-5",
    "judged_on_utc": "2026-09-30",
    "judge_failure_source": "llm_error",
    "judge_failure_subtype": "thresholds_rates",
    "adjudicated_failure_source": "llm_error",
    "adjudicated_failure_subtype": "thresholds_rates",
    "adjudicated_on": "2026-09-22",
    "adjudicator": "developer",
    "judge_reference_suspect": True,
    "reference_verdict": "affirmed",
    "reference_basis": "7 CFR 273.10",
    "reasoning": "The judge counted one model's row. The allotment follows the rule.",
}


@pytest.fixture
def triage_stage(tmp_path, monkeypatch, unruled_spec):
    """A one-case stage Claude Haiku 5.5 re-opened, with a recorded decision."""
    import policybench.audit

    stage = tmp_path / "stage"
    bundle = stage / "publish" / driver.RUN_NAME
    (bundle / "annotations").mkdir(parents=True)
    (stage / driver.PROMPT_CHANGES).write_text(
        json.dumps({"added": [], "changed": [CASE], "kept": []})
    )
    case = stage / "audit/cases" / CASE
    case.mkdir(parents=True)
    write_verdict(case, {**_verdict([NEW]), "reference_suspect": True})
    record = bundle / "annotations" / driver.ADJUDICATIONS
    record.write_text(_record(DECISION))
    monkeypatch.setattr(driver, "validate_verdicts", lambda *a, **kw: [])
    monkeypatch.setattr(driver, "load_seed", lambda stage: {})
    monkeypatch.setattr(
        driver, "base_adjudication_record", lambda: _base_record(DECISION)
    )
    row = {
        "country": "us",
        "scenario_id": "scenario_000",
        "variable": "snap",
        "failure_source": "llm_error",
        "failure_subtype": "thresholds_rates",
        "reference_suspect": True,
    }
    rows = pd.DataFrame(
        [
            {**row, "model": NEW, "annotation": "It used the 2025 threshold."},
            {**row, "model": "m1", "annotation": "It used the 2025 threshold."},
        ]
    )
    cases = pd.DataFrame(
        [
            {
                **{k: v for k, v in row.items() if not k.startswith("failure")},
                "wrong_model_count": 2,
                "case_failure_source": "llm_error",
                "case_failure_subtype": "thresholds_rates",
                "reference_bug_hypothesis": "",
                "case_annotation": "Both models used the 2025 threshold.",
            }
        ]
    )
    monkeypatch.setattr(
        policybench.audit,
        "collect_audit",
        lambda *a, **kw: {
            "missing": pd.DataFrame(),
            "hedged": pd.DataFrame(),
            "row": rows.copy(),
            "case": cases.copy(),
        },
    )

    def run():
        driver.triage(SimpleNamespace(stage_dir=stage), bundle)
        annotations = bundle / "annotations"
        return (
            json.loads(record.read_text())["adjudications"][0],
            pd.read_csv(annotations / "us_case_notes.csv").iloc[0],
            pd.read_csv(annotations / "us_audit_row_annotations.csv"),
        )

    return stage, record, run


SEED_ITEM = {
    "judge_model": "claude-opus-5-5",
    "judge_failure_source": "llm_error",
    "judge_failure_subtype": "thresholds_rates",
    "judge_reference_suspect": True,
    "judged_on": "2026-09-30",
}
RESTATED = {
    **DECISION,
    "judged_on_utc": "2026-10-09",
    "judge_rejudged_on": "2026-10-09",
    "judge_previous": [SEED_ITEM],
}


def test_triage_accepts_its_own_record_unchanged(triage_stage):
    stage, record, run = triage_stage
    text = record.read_text()
    entry, _, _ = run()
    assert entry == DECISION and record.read_text() == text


def test_triage_lets_a_rejudged_case_restate_its_judge_fields(triage_stage):
    stage, record, run = triage_stage
    record.write_text(_record(RESTATED))
    entry, _, _ = run()
    assert entry == RESTATED


@pytest.mark.parametrize(
    "tamper",
    [
        {"judge_model": "a-human-typed-this"},
        {"judge_previous": []},
        {"judge_rejudged_on": "1999-01-01"},
        # The appended item must be the verdict 20261006's entry names.
        {"judge_previous": [{**SEED_ITEM, "judged_on": "2026-09-28"}]},
        {"judge_previous": [{**SEED_ITEM, "judge_failure_source": "reference_error"}]},
        {"judge_previous": [{**SEED_ITEM, "judge_failure_subtype": "other"}]},
        {"judge_previous": [{**SEED_ITEM, "judge_reference_suspect": False}]},
    ],
)
def test_triage_refuses_judge_fields_written_by_hand(triage_stage, tamper):
    stage, record, run = triage_stage
    record.write_text(_record({**RESTATED, **tamper}))
    with pytest.raises(SystemExit, match="not restated by the restate script"):
        run()


def test_triage_refuses_a_record_whose_bytes_hide_text(triage_stage):
    stage, record, run = triage_stage
    text = _record(DECISION).replace(
        '"adjudicator": "developer"',
        '"adjudicator": "SMUGGLED", "adjudicator": "developer"',
    )
    record.write_text(text)
    with pytest.raises(SystemExit, match="committed form"):
        run()


@pytest.mark.parametrize(
    "conventions",
    [
        CONVENTIONS,
        CONVENTIONS + " Edited.",
        CONVENTIONS.replace(
            driver.DATE_CONVENTIONS_BASE, driver.DATE_CONVENTIONS_WAVES
        ),
    ],
)
def test_triage_refuses_date_conventions_other_than_the_waves(
    triage_stage, conventions
):
    """The staged record's date conventions are the base's with the
    2026-10-06 wave named once and its sentence added: neither the base's
    own text, nor an edit, nor half the change passes."""
    stage, record, run = triage_stage
    record.write_text(
        driver.record_text(
            {"date_conventions": conventions, "adjudications": [DECISION]}
        )
    )
    with pytest.raises(SystemExit, match="beyond naming the 2026-10-06 wave"):
        run()


@pytest.mark.parametrize(
    "field, value",
    [("adjudicated_failure_subtype", "other"), ("reasoning", "Rewritten.")],
)
def test_triage_refuses_any_other_change_to_a_recorded_decision(
    triage_stage, field, value
):
    stage, record, run = triage_stage
    record.write_text(_record({**DECISION, field: value}))
    with pytest.raises(SystemExit, match="change recorded decisions"):
        run()


def test_triage_refuses_a_judge_rewrite_of_an_incumbent_only_case(triage_stage):
    stage, record, run = triage_stage
    (stage / driver.PROMPT_CHANGES).write_text(
        json.dumps({"added": [], "changed": [], "kept": [CASE]})
    )
    record.write_text(_record(RESTATED))
    with pytest.raises(SystemExit, match="change recorded decisions"):
        run()


def _amendments(stage, *items):
    (stage / driver.AMENDMENTS).write_text(json.dumps({"amendments": list(items)}))


def _amend(field, old, new, **extra):
    return {
        "case_id": CASE,
        "field": field,
        "old": old,
        "new": new,
        "reason": "The re-judge's verdict no longer says this.",
        **extra,
    }


def test_triage_applies_exactly_the_listed_wording_amendments(triage_stage):
    stage, record, run = triage_stage
    _amendments(
        stage,
        _amend("reasoning", "one model's row", "two models' rows"),
        _amend("case_annotation", "the 2025 threshold", "the 2025 threshold, held"),
        _amend("annotation", "2025 threshold", "held 2025 threshold", model=NEW),
    )
    entry, note, rows = run()
    assert entry["reasoning"] == DECISION["reasoning"].replace(
        "one model's row", "two models' rows"
    )
    assert list(entry) == list(DECISION)
    assert note.case_annotation.startswith("Both models used the 2025 threshold, held.")
    assert "two models' rows" in note.case_annotation
    annotations = dict(zip(rows.model, rows.annotation))
    assert annotations == {
        NEW: "It used the held 2025 threshold.",
        "m1": "It used the 2025 threshold.",
    }
    # Idempotent: a second triage applies nothing twice.
    text = record.read_text()
    assert run()[0] == entry and record.read_text() == text


@pytest.mark.parametrize(
    "item",
    [
        _amend("case_annotation", "no such text", "x"),
        _amend("annotation", "2025 threshold", "x", model="not-a-model"),
        # The adjudication sentence comes from the record; only a reasoning
        # amendment may change it.
        _amend("case_annotation", "The allotment follows the rule.", "It does."),
    ],
)
def test_triage_refuses_an_amendment_it_cannot_apply_exactly(triage_stage, item):
    from policybench.adjudications import AdjudicationError

    stage, _, run = triage_stage
    _amendments(stage, item)
    with pytest.raises(
        (SystemExit, AdjudicationError), match="occurs|matches|adjudication sentence"
    ):
        run()


# --- Export, the scored count and the scope check ------------------------------

FABLE_USAGE = {
    "costUsd": 54.109099999999955,
    "costPerHousehold": 0.5410909999999995,
    "totalTokens": 3850174,
    "latencySeconds": 97.6780539804895,
}


def _stat(model, exact, n=driver.RELEASE_SCORED, **usage):
    return {
        "model": model,
        "condition": "no_tools",
        "score": exact / 100,
        "exact": exact,
        "n": n,
        **usage,
    }


def _incumbents():
    """46 rows as release 20261006 published them (1,920 scored outputs),
    including Fable 5's batch usage and Ox Alpha's $0."""
    rows = [
        _stat(f"incumbent-{i:02d}", 50.0 + i / 7, n=driver.BASE_SCORED, costUsd=1.25)
        for i in range(44)
    ]
    rows.append(
        _stat("ox-alpha", 70.0, n=driver.BASE_SCORED, costUsd=0.0, costPerHousehold=0.0)
    )
    rows.append(
        _stat(
            "claude-fable-5",
            60.0,
            n=driver.BASE_SCORED,
            costUsd=0.0,
            costPerHousehold=0.0,
        )
    )
    rows[-1].update(FABLE_USAGE)
    return rows


def _exported(incumbents):
    """What export_full_run returns on the release's record: every model on
    1,910 outputs and every incumbent's score moved by the ten exclusions;
    Fable's usage is gone, and the addition is new."""
    stats = copy.deepcopy(incumbents)
    for row in stats:
        row.update(n=driver.RELEASE_SCORED, exact=row["exact"] + 0.25)
        row["score"] = row["exact"] / 100
    fable = stats[-1]
    fable.update(costUsd=0.0, costPerHousehold=0.0)
    del fable["totalTokens"], fable["latencySeconds"]
    return stats + [_stat(NEW, 65.0, costUsd=0.13)]


def _scoped(incumbents):
    """What release_20261006.export_payload returns with release 20261006's
    record put back: every incumbent's published row, Fable's usage carried
    (it does that itself), and the addition on 1,920 outputs."""
    return copy.deepcopy(incumbents) + [
        _stat(NEW, 65.5, n=driver.BASE_SCORED, costUsd=0.13)
    ]


@pytest.fixture
def scope(monkeypatch):
    """export_full_run, release_20261006.export_payload and the dashboard
    schema replaced by fakes that hand back the given model stats and record
    what they were called with."""
    import policybench.dashboard_schema
    import policybench.full_run_export

    state = SimpleNamespace(stats=None, scoped=None, calls=[], gates=[])

    def export_full_run(run_dir, **kwargs):
        state.calls.append(("export_full_run", Path(run_dir), kwargs))
        return {"countries": {"us": {"modelStats": copy.deepcopy(state.stats)}}}

    def export_payload(bundle, base, exclusions=None):
        state.calls.append(
            ("export_payload", Path(bundle), base, Path(exclusions).read_bytes())
        )
        return {"countries": {"us": {"modelStats": copy.deepcopy(state.scoped)}}}

    def validate(payload, *, require_failure_annotations):
        state.gates.append(require_failure_annotations)
        return []

    monkeypatch.setattr(policybench.full_run_export, "export_full_run", export_full_run)
    monkeypatch.setattr(release_20261006, "export_payload", export_payload)
    monkeypatch.setattr(
        policybench.dashboard_schema, "validate_dashboard_payload", validate
    )
    monkeypatch.setattr(driver, "base_exclusion_record", base_record)

    def build(stats, scoped, live_stats, *, partial=False, early=False, bundle=None):
        state.stats, state.scoped = stats, scoped
        live = {"countries": {"us": {"modelStats": live_stats}}}
        return driver.build_payload(
            bundle or Path("bundle"), live, partial=partial, early=early
        )

    state.build = build
    return state


def test_the_scope_check_allows_every_incumbent_change_the_ten_records_explain(scope):
    """Every incumbent's score moves on the release's record, and its
    modelStats on release 20261006's record are the published ones: the
    payload carries the release's rows, Fable 5's usage carried."""
    incumbents = _incumbents()
    stats = _exported(incumbents)
    payload = scope.build(stats, _scoped(incumbents), incumbents, bundle=Path("b"))
    rows = payload["countries"]["us"]["modelStats"]
    assert {row["n"] for row in rows} == {1910}
    fable = next(row for row in rows if row["model"] == "claude-fable-5")
    assert {key: fable[key] for key in FABLE_USAGE} == FABLE_USAGE
    assert fable["exact"] == incumbents[-1]["exact"] + 0.25
    (_, run_dir, kwargs), (_, bundle, live, record) = scope.calls
    assert run_dir == bundle == Path("b")
    assert kwargs == {"countries": ["us"], "skip_app_data": True}
    assert live == {"countries": {"us": {"modelStats": incumbents}}}
    # The scope export scores on release 20261006's exclusion record, its
    # pinned bytes.
    assert (
        hashlib.sha256(record).hexdigest()
        == driver.BASE_REFERENCE_SHA256[EXCLUSIONS_NAME]
    )
    assert scope.gates == [True]


SCOPE_MUTATIONS = {
    "value": lambda row: row.update(exact=row["exact"] + 1e-12),
    "added_key": lambda row: row.update(extra=None),
    "removed_key": lambda row: row.pop("score"),
    "key_order": lambda row: row.update(model=row.pop("model")),
    "int_to_float": lambda row: row.update(n=float(row["n"])),
    "zero_cost_to_missing": lambda row: row.pop("costUsd"),
    "cost_sign": lambda row: row.update(costUsd=-row["costUsd"]),
    "renamed": lambda row: row.update(model=row["model"] + "-x"),
}


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    target=st.integers(min_value=0, max_value=45),
    mutation=st.sampled_from(sorted(SCOPE_MUTATIONS)),
)
def test_the_scope_check_refuses_an_incumbent_change_the_ten_records_do_not_explain(
    scope, target, mutation
):
    """For every incumbent and every kind of change to its modelStats on
    release 20261006's record, the build refuses and names it."""
    incumbents = _incumbents()
    scoped = _scoped(incumbents)
    SCOPE_MUTATIONS[mutation](scoped[target])
    with pytest.raises(SystemExit, match="incumbent modelStats drift") as refusal:
        scope.build(_exported(incumbents), scoped, incumbents)
    assert str(refusal.value).endswith(f"drift: {[incumbents[target]['model']]}")


def test_the_scope_check_refuses_a_scope_export_that_loses_a_model(scope):
    incumbents = _incumbents()
    with pytest.raises(SystemExit, match="scope export lost a model"):
        scope.build(_exported(incumbents), _scoped(incumbents)[:-1], incumbents)
    with pytest.raises(SystemExit, match=r"drift: \['incumbent-03'\]"):
        scope.build(
            _exported(incumbents),
            [r for r in _scoped(incumbents) if r["model"] != "incumbent-03"]
            + [_stat("stray", 1.0)],
            incumbents,
        )


def test_every_model_is_scored_on_1910_outputs(scope):
    incumbents = _incumbents()
    for index in (0, 45, 46):
        stats = _exported(incumbents)
        stats[index]["n"] = driver.BASE_SCORED
        with pytest.raises(SystemExit, match="must be scored on 1910 outputs"):
            scope.build(stats, _scoped(incumbents), incumbents)
    assert [call[0] for call in scope.calls] == ["export_full_run"] * 3


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    counts=st.lists(
        st.sampled_from([1910, 1910, 1910, 1920, 1909, 1984, 0]),
        min_size=47,
        max_size=47,
    )
)
def test_the_scored_count_gate_passes_exactly_when_every_model_has_1910(scope, counts):
    incumbents = _incumbents()
    stats = _exported(incumbents)
    for row, n in zip(stats, counts):
        row["n"] = n
    if set(counts) == {1910}:
        scope.build(stats, _scoped(incumbents), incumbents)
    else:
        with pytest.raises(SystemExit, match="must be scored on 1910 outputs"):
            scope.build(stats, _scoped(incumbents), incumbents)


def test_a_partial_build_skips_the_release_gates(scope):
    stats = [_stat(f"incumbent-{i:02d}", 40.0, n=7) for i in range(46)]
    payload = scope.build(stats + [_stat(NEW, 45.0, n=7)], None, [], partial=True)
    assert "PARTIAL" in payload["stage2Status"]
    assert [call[0] for call in scope.calls] == ["export_full_run"]


@settings(max_examples=60, deadline=None)
@given(
    rows=st.lists(
        st.fixed_dictionaries(
            {
                "exact": st.floats(allow_nan=False, allow_infinity=False),
                "n": st.integers(min_value=0, max_value=1984),
            }
        ),
        min_size=46,
        max_size=46,
    ),
    target=st.integers(min_value=0, max_value=45),
)
def test_incumbent_drift_is_exactly_the_changed_rows(rows, target):
    """Identical rows pass; a changed, dropped or reordered row is named."""
    previous = {
        f"m{i:02d}": {"model": f"m{i:02d}", **row} for i, row in enumerate(rows)
    }
    stats = [copy.deepcopy(row) for row in previous.values()]
    assert driver.incumbent_drift(stats, previous) == []
    name = f"m{target:02d}"
    reordered = copy.deepcopy(stats)
    reordered[target] = dict(reversed(list(reordered[target].items())))
    assert driver.incumbent_drift(reordered, previous) == [name]
    dropped = [row for row in stats if row["model"] != name]
    assert driver.incumbent_drift(dropped, previous) == [name]


@pytest.fixture
def exporting(tmp_path, monkeypatch, scope):
    """A stage export can run on: release 20261006's references committed,
    the release's exclusion record staged, Claude Haiku 5.5's pinned run and
    an empty judge provenance record."""
    stage = tmp_path / "stage"
    bundle = stage / "publish" / driver.RUN_NAME
    monkeypatch.setattr(
        driver, "SNAPSHOT", base_references(tmp_path / "committed-snapshot")
    )
    base_references(bundle / "us")
    (bundle / "us" / EXCLUSIONS_NAME).write_text(release_text())
    # No case is re-opened here, so the judge provenance record lists none.
    record = tmp_path / "judge_provenance.json"
    record.write_text(json.dumps(_provenance_record([])))
    monkeypatch.setattr(driver, "JUDGE_PROVENANCE", record)
    monkeypatch.setattr(driver, "rejudged_cases", lambda stage: frozenset())
    pins = _write_run(stage, bundle)
    monkeypatch.setattr(driver, "committed_input_pins", lambda: pins)
    # Before the freeze: the pointer names release 20261006, whatever the
    # working tree holds when the tests run.
    monkeypatch.setattr(driver, "live_pointer", lambda: {"tag": driver.BASE_TAG})

    def run(stats, live_stats, *, scoped=None, partial=False, early=False):
        scope.stats = stats
        scope.scoped = _scoped(live_stats) if scoped is None else scoped
        args = SimpleNamespace(stage_dir=stage, partial=partial, early=early)
        live = {"countries": {"us": {"modelStats": live_stats}}}
        return driver.export(args, bundle, live)

    return stage, bundle, run, scope.gates


# Claude Haiku 5.5's synthetic run file, and an incumbent row beside its row.
HAIKU_RUN = (
    "model,scenario_id,variable,prediction,estimated_cost_usd,elapsed_seconds\n"
    f"{NEW},scenario_000,snap,1200.0,0.0001,2.75\n"
)
PINNED = ("predictions.csv", "run_state.json")


def _write_run(stage, bundle) -> dict:
    """Claude Haiku 5.5's run files as prepare stages them, the bundle's
    predictions holding its row, and the prepare-time hashes in stage.json
    and model-provenance.json; returns the run files' pins."""
    inputs = stage / "inputs" / SLUG
    inputs.mkdir(parents=True, exist_ok=True)
    (inputs / "predictions.csv").write_text(HAIKU_RUN)
    fingerprint = {"model_id": NEW}
    state = {"model": NEW, "treatment_fingerprint": fingerprint}
    (inputs / "run_state.json").write_text(json.dumps(state))
    header, row = HAIKU_RUN.splitlines(keepends=True)
    (bundle / "us/predictions.csv").write_text(
        header + "incumbent,scenario_000,snap,900.0,0.002,3.5\n" + row
    )
    names = [bundle / "us" / name for name in driver.REFERENCE_FILES]
    names += [bundle / "us/predictions.csv", *(inputs / name for name in PINNED)]
    files = {str(path.relative_to(stage)): driver.digest(path) for path in names}
    (stage / "stage.json").write_text(
        json.dumps({"partial": False, "early": False, "files": files})
    )
    provenance = {
        "predictions_sha256": driver.digest(inputs / "predictions.csv"),
        "treatment_fingerprint": fingerprint,
    }
    (stage / "model-provenance.json").write_text(json.dumps({NEW: provenance}))
    return {SLUG: {name: driver.digest(inputs / name) for name in PINNED}}


def _evidence(stage, bundle):
    paths = [bundle / "annotations/us_adjudications.json"]
    paths += [stage / "audit/cases.jsonl", stage / "audit/schema.json"]
    paths += [stage / driver.PROMPT_CHANGES, stage / driver.AMENDMENTS]
    paths += [
        stage / "audit/cases/example" / name
        for name in (
            "verdict.json",
            "verdict.meta.json",
            "prompt.md",
            "claude.transcript.jsonl",
        )
    ]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"Evidence: {path.name}\n")
    # The run files and prepare-time hashes the exporting fixture wrote.
    paths += [bundle / "us/predictions.csv", stage / "stage.json"]
    paths += [stage / "model-provenance.json"]
    paths += [stage / "inputs" / SLUG / name for name in PINNED]
    return paths + [bundle / "us" / name for name in driver.REFERENCE_FILES]


def test_strict_export_carries_fable_usage_and_binds_the_evidence(exporting):
    stage, bundle, run, gate_calls = exporting
    evidence = _evidence(stage, bundle)
    incumbents = _incumbents()
    stats = _exported(incumbents)
    payload = run(stats, incumbents)

    output = stage / "data-board47.json"
    assert (
        output.read_bytes()
        == json.dumps({"countries": {"us": payload["countries"]["us"]}}).encode()
    )
    assert (bundle / "data.json").read_bytes() == output.read_bytes()
    fable = next(
        s
        for s in payload["countries"]["us"]["modelStats"]
        if s["model"] == "claude-fable-5"
    )
    assert {key: fable[key] for key in FABLE_USAGE} == FABLE_USAGE
    assert gate_calls == [True]
    receipt = json.loads((stage / "release-ready.json").read_text())
    assert receipt["release_tag"] == driver.RELEASE_TAG
    assert receipt["base_tag"] == driver.BASE_TAG
    assert receipt["models"] == 47 and receipt["partial"] is False
    assert receipt["base_sha256"] == driver.BASE_SHA256
    assert receipt["payload_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert receipt["files"] == {
        str(path.relative_to(stage)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in evidence
    }
    assert receipt["files"][BOUND_EXCLUSIONS] == release_sha()
    assert receipt["judge_provenance"] == {
        "path": "docs/haiku55/judge_provenance.json",
        "sha256": hashlib.sha256(driver.JUDGE_PROVENANCE.read_bytes()).hexdigest(),
    }


def test_export_accepts_only_the_release_exclusion_record(exporting, monkeypatch):
    """Before the freeze, the committed record is release 20261006's and the
    staged one the release's; any other pairing is refused before a payload
    or receipt is written."""
    stage, bundle, run, _ = exporting
    _evidence(stage, bundle)
    incumbents = _incumbents()
    staged = bundle / "us" / EXCLUSIONS_NAME
    staged.write_bytes(base_blob(SNAPSHOT_PATH / EXCLUSIONS_NAME))
    with pytest.raises(SystemExit, match="staged reference reference_exclusions.json"):
        run(_exported(incumbents), incumbents)
    staged.write_text(release_text())
    (driver.SNAPSHOT / EXCLUSIONS_NAME).write_text(release_text())
    with pytest.raises(
        SystemExit, match="committed reference reference_exclusions.json"
    ):
        run(_exported(incumbents), incumbents)
    assert not (stage / "release-ready.json").exists()
    assert not (stage / "data-board47.json").exists()


def test_a_re_export_after_the_freeze_accepts_the_frozen_exclusion_record(
    exporting, monkeypatch
):
    stage, bundle, run, _ = exporting
    _evidence(stage, bundle)
    monkeypatch.setattr(driver, "live_pointer", lambda: {"tag": driver.RELEASE_TAG})
    (driver.SNAPSHOT / EXCLUSIONS_NAME).write_text(release_text())
    incumbents = _incumbents()
    run(_exported(incumbents), incumbents)
    assert (stage / "release-ready.json").is_file()


def test_export_writes_no_receipt_when_the_inputs_are_not_the_pinned_run(
    exporting, monkeypatch
):
    """Export checks Claude Haiku 5.5's staged run files against the committed
    pins before it writes the payload or a receipt."""
    stage, bundle, run, _ = exporting
    _evidence(stage, bundle)
    pins = {SLUG: {"predictions.csv": "0" * 64, "run_state.json": "0" * 64}}
    monkeypatch.setattr(driver, "committed_input_pins", lambda: pins)
    incumbents = _incumbents()
    with pytest.raises(SystemExit, match=f"staged inputs/{SLUG}/.* is not the run"):
        run(_exported(incumbents), incumbents)
    assert not (stage / "release-ready.json").exists()
    assert not (stage / "data-board47.json").exists()


def test_export_writes_nothing_when_the_scope_check_refuses(exporting):
    stage, bundle, run, _ = exporting
    _evidence(stage, bundle)
    incumbents = _incumbents()
    scoped = _scoped(incumbents)
    scoped[7]["exact"] += 0.5
    with pytest.raises(SystemExit, match=r"drift: \['incumbent-07'\]"):
        run(_exported(incumbents), incumbents, scoped=scoped)
    assert not (stage / "release-ready.json").exists()
    assert not (stage / "data-board47.json").exists()
    assert not (bundle / "data.json").exists()


def test_partial_export_never_gets_a_release_receipt(exporting):
    stage, bundle, run, _ = exporting
    stats = [_stat(f"incumbent-{i:02d}", 40.0) for i in range(46)]
    run(stats + [_stat(NEW, 45.0)], [], partial=True, early=True)
    payload = stage / "PARTIAL-data-board47.json"
    assert "PARTIAL" in json.loads(payload.read_text())["stage2Status"]
    assert (bundle / "data.json").read_bytes() == payload.read_bytes()
    assert not (stage / "release-ready.json").exists()


def test_the_export_roster_must_be_the_incumbents_plus_the_addition(exporting):
    _, _, run, _ = exporting
    incumbents = _incumbents()
    stats = _exported(incumbents)
    stats[-1] = _stat("claude-haiku-5.5-impostor", 65.0)
    with pytest.raises(SystemExit, match="roster"):
        run(stats, incumbents)
    with pytest.raises(SystemExit, match="46 incumbents"):
        run(_exported(incumbents), incumbents[:-1] + [_stat(NEW, 1.0)])
    with pytest.raises(SystemExit, match="all 47 models"):
        run(_exported(incumbents)[:-1], incumbents)


def test_export_refuses_a_staged_reference_off_its_pin(exporting):
    _, bundle, run, _ = exporting
    path = bundle / "us/reference_outputs.csv.meta.json"
    path.write_bytes(path.read_bytes() + b"\n")
    incumbents = _incumbents()
    with pytest.raises(SystemExit, match="staged reference reference_outputs.csv.meta"):
        run(_exported(incumbents), incumbents)


def test_export_refuses_a_committed_reference_off_its_pin(
    exporting, pinned_copy, monkeypatch
):
    _, _, run, _ = exporting
    (pinned_copy / "scenarios.csv").write_text("scenario_id\n")
    monkeypatch.setattr(driver, "SNAPSHOT", pinned_copy)
    incumbents = _incumbents()
    with pytest.raises(SystemExit, match="committed reference scenarios.csv"):
        run(_exported(incumbents), incumbents)


# --- Judge provenance ----------------------------------------------------------

ISOLATED = "us__scenario_001__snap"
UNHARDENED = "us__scenario_002__snap"
# The prompt an isolated judge's transcript shows, and its case's prompt.md.
JUDGED = "Classify these wrong answers.\n"


def _event(kind, **fields):
    return {"type": kind, **fields}


def _attachment(kind, **fields):
    return _event("attachment", attachment={"type": kind, **fields})


def _call(name, call_id, answer=None):
    content = [{"type": "tool_use", "id": call_id, "name": name, "input": answer or {}}]
    return _event("assistant", effort="xhigh", message={"content": content})


def _result(call_id, error=False):
    part = {"type": "tool_result", "tool_use_id": call_id, "content": "done"}
    if error:
        part["is_error"] = True
    return _event("user", message={"content": [part]})


def _clean_transcript():
    """An isolated judge's transcript, shaped like the GPT-6.1 Sol stage's real
    ones: its one accepted StructuredOutput call answers the verdict the
    provenance fixture writes."""
    return [
        _event("user", message={"content": JUDGED}),
        _attachment("environment", snapshot={"isGitRepo": False}),
        _attachment("model"),
        _attachment("session_context", context={}),
        _attachment("date"),
        _attachment("prompt_snapshot"),
        _event("assistant", effort="xhigh", message={"content": [{"type": "text"}]}),
        _call("StructuredOutput", "call-1", _verdict([NEW])),
        _attachment("structured_output"),
        _result("call-1"),
    ]


def _write_transcript(case, events):
    (case / "claude.transcript.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )


# An isolated judge's sidecar fields: a token login on a lane whose account
# it declares, which the public record withholds.
ISOLATED_SIDECAR = {
    "judge_effort": "xhigh",
    "judge_isolation": {"tools": "none (--tools '')"},
    "judge_auth": {"method": "oauth_token", "account": None, "org": None},
    "judge_account_declared": "claude:lane@example.org (pb-judge)",
}
WITHHELD = "<account withheld>"


def _record_entry(case: Path, group: str) -> dict:
    """The entry a true record gives a staged verdict: its hashes, its group
    and isolation, and its sidecar's fields with addresses withheld."""
    meta = json.loads((case / "verdict.meta.json").read_text())
    return {
        "case_id": case.name,
        "group": group,
        "isolated": "judge_isolation" in meta,
        "judge_account_declared": (
            meta["judge_account_declared"].replace("lane@example.org", WITHHELD)
            if "judge_account_declared" in meta
            else None
        ),
        "judge_effort": meta.get("judge_effort"),
        "judge_model_reported": meta["judge_model_reported"],
        "judged_at_utc": meta["judged_at_utc"],
        "verdict_sha256": driver.digest(case / "verdict.json"),
        "prompt_sha256": driver.digest(case / "prompt.md"),
    }


def _provenance_record(entries: list[dict], note: str = "How each was judged."):
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["group"]] = counts.get(entry["group"], 0) + 1
    return {"note": note, "counts": counts, "verdicts": entries}


GROUPS = {ISOLATED: "isolated: pb-judge", UNHARDENED: "unhardened: in-repo runner"}


@pytest.fixture
def provenance(tmp_path):
    """Two new verdicts, one isolated and one not, and a true record of both."""
    cases = tmp_path / "audit/cases"
    entries = []
    for name, isolated in ((ISOLATED, True), (UNHARDENED, False)):
        case = cases / name
        case.mkdir(parents=True)
        (case / "prompt.md").write_text(JUDGED)
        write_verdict(case, _verdict([NEW]), **(ISOLATED_SIDECAR if isolated else {}))
        _write_transcript(case, _clean_transcript())
        entries.append(_record_entry(case, GROUPS[name]))
    record = tmp_path / "judge_provenance.json"

    def verify(edit=lambda entries: None, edit_record=lambda record: None):
        edited = copy.deepcopy(entries)
        edit(edited)
        written = _provenance_record(edited)
        edit_record(written)
        record.write_text(json.dumps(written))
        driver.verify_judge_provenance(cases, frozenset({ISOLATED, UNHARDENED}), record)

    return cases, verify


def test_the_judge_provenance_record_describes_the_staged_verdicts(provenance):
    _, verify = provenance
    verify()


def test_the_runners_attachment_allowlist_is_the_gates():
    script = (driver.ROOT / "scripts/run_audit_claude.sh").read_text()
    line = next(line for line in script.splitlines() if line.startswith("ATTACHMENTS="))
    assert set(line.split('"')[1].split(",")) == driver.JUDGE_ATTACHMENTS


@pytest.mark.parametrize("case", [ISOLATED, UNHARDENED])
def test_a_verdict_whose_isolation_disagrees_with_the_record_is_refused(
    provenance, case
):
    _, verify = provenance

    def flip(entries):
        entry = next(e for e in entries if e["case_id"] == case)
        entry["isolated"] = not entry["isolated"]

    with pytest.raises(SystemExit, match=f"{case}: the record says isolated"):
        verify(flip)


def test_a_sidecar_that_drops_its_isolation_disagrees_with_the_record(provenance):
    cases, verify = provenance
    case = cases / ISOLATED
    meta = json.loads((case / "verdict.meta.json").read_text())
    del meta["judge_isolation"]
    (case / "verdict.meta.json").write_text(json.dumps(meta))
    with pytest.raises(SystemExit, match="sidecar lacks judge_isolation"):
        verify()


@pytest.mark.parametrize(
    "edit, problem",
    [
        (lambda e: e.pop(), "does not list each re-opened case once"),
        (lambda e: e.append(dict(e[0])), "does not list each re-opened case once"),
        (lambda e: e[0].update(verdict_sha256="0" * 64), "names another verdict"),
        (lambda e: e[1].update(prompt_sha256="0" * 64), "names another prompt"),
    ],
)
def test_the_record_must_list_each_staged_new_verdict_once(provenance, edit, problem):
    _, verify = provenance
    with pytest.raises(SystemExit, match=problem):
        verify(edit)


def _entry(case):
    return lambda entries: next(e for e in entries if e["case_id"] == case)


# Each sidecar field the record copies, rewritten in one entry.
SIDECAR_FIELD_EDITS = {
    "judge_effort": (ISOLATED, "max"),
    "judge_model_reported": (UNHARDENED, ["claude-opus-5"]),
    "judged_at_utc": (ISOLATED, "2026-10-09T08:00:00+00:00"),
    "judge_account_declared": (ISOLATED, f"claude:{WITHHELD} (another lane)"),
    "judge_account_declared_unhardened": (UNHARDENED, "a lane it never ran on"),
}


@pytest.mark.parametrize("edit", sorted(SIDECAR_FIELD_EDITS))
def test_each_entrys_fields_must_be_its_sidecars(provenance, edit):
    _, verify = provenance
    case, value = SIDECAR_FIELD_EDITS[edit]
    field = edit.removesuffix("_unhardened")

    def rewrite(entries):
        _entry(case)(entries)[field] = value

    problem = f"{case}: its {field} .* is not the sidecar's"
    with pytest.raises(SystemExit, match=problem):
        verify(rewrite)


def test_the_record_withholds_the_sidecars_address_and_names_none(provenance):
    """The entry carries the sidecar's declaration with its address withheld;
    the address itself, there or anywhere else in the record, is refused."""
    _, verify = provenance

    def declared(entries):
        _entry(ISOLATED)(entries)["judge_account_declared"] = (
            "claude:lane@example.org (pb-judge)"
        )

    with pytest.raises(SystemExit, match=r"is public and names .*e-mail address"):
        verify(declared)

    def in_note(record):
        record["note"] += " The lane is lane@example.org."

    with pytest.raises(SystemExit, match=r"is public and names .*record\.note"):
        verify(edit_record=in_note)

    def in_group(entries):
        for entry in entries:
            entry["group"] = entry["group"].replace("pb-judge", "judge@example.org")

    with pytest.raises(SystemExit, match="is public and names"):
        verify(in_group)


# The fixture record's true counts: one entry in each group.
GROUP_COUNTS = {group: 1 for group in GROUPS.values()}


@pytest.mark.parametrize(
    "counts", [{}, {"isolated: pb-judge": 2}, {**GROUP_COUNTS, "extra": 0}]
)
def test_the_counts_must_be_the_tally_of_the_entries_groups(provenance, counts):
    _, verify = provenance
    with pytest.raises(SystemExit, match="counts .* are not the tally"):
        verify(edit_record=lambda record: record.update(counts=counts))


@pytest.mark.parametrize(
    "auth", [None, {"method": "claude.ai", "account": "8f0c"}, {"method": None}]
)
def test_an_isolated_verdict_needs_a_token_login(provenance, auth):
    cases, verify = provenance
    meta_path = cases / ISOLATED / "verdict.meta.json"
    meta = json.loads(meta_path.read_text())
    meta.pop("judge_auth")
    if auth is not None:
        meta["judge_auth"] = auth
    meta_path.write_text(json.dumps(meta))
    problem = f"{ISOLATED}: the sidecar does not record a token login"
    with pytest.raises(SystemExit, match=problem):
        verify()


def test_the_record_and_its_entries_carry_only_checked_keys(provenance):
    _, verify = provenance

    def claim(entries):
        _entry(ISOLATED)(entries)["environment"] = "allowlisted"

    with pytest.raises(SystemExit, match=f"{ISOLATED}: the entry has keys"):
        verify(claim)
    with pytest.raises(SystemExit, match="has keys .*, not"):
        verify(edit_record=lambda record: record.update(isolation="all allowlisted"))


def test_only_an_isolated_entrys_group_says_isolated(provenance):
    _, verify = provenance

    def regroup(entries):
        _entry(UNHARDENED)(entries)["group"] = "isolated: in-repo runner"

    with pytest.raises(SystemExit, match=f"{UNHARDENED}: its group .* disagrees"):
        verify(regroup)


def _read_call(events):
    events[-3:-3] = [_call("Read", "call-0"), _result("call-0")]


def _second_answer(events):
    events += [_call("StructuredOutput", "call-2"), _result("call-2")]


def _no_answer(events):
    del events[7:10]


def _user(content, **fields):
    return _event("user", message={"content": content}, **fields)


def _forged_answer(events):
    """A StructuredOutput call no assistant turn made, and its "result"."""
    content = [{"type": "tool_use", "id": "call-9", "name": "StructuredOutput"}]
    events += [
        _event("system", message={"content": content}),
        _user([{"type": "tool_result", "tool_use_id": "call-9", "content": "A hint."}]),
    ]


TRANSCRIPT_DEFECTS = {
    "read_tool_call": (_read_call, r"tool calls \['Read'\]"),
    "no_answer": (_no_answer, "0 accepted StructuredOutput"),
    "two_answers": (_second_answer, "2 accepted StructuredOutput"),
    "account_email": (
        lambda e: e[3].update(_attachment("session_context", context={"userEmail": 1})),
        r"session context carrying \['userEmail'\]",
    ),
    "credential_org": (
        lambda e: e.append(_attachment("credential_org")),
        "'credential_org' attachment",
    ),
    "skill_listing": (
        lambda e: e.append(_attachment("skill_listing")),
        "'skill_listing' attachment",
    ),
    "git_repository": (
        lambda e: e[1].update(_attachment("environment", snapshot={"isGitRepo": True})),
        "inside a git repository",
    ),
    "other_effort": (lambda e: e[6].update(effort="max"), "effort 'max'"),
    "advisor": (lambda e: e[6].update(advisorModel="m"), "advisor model"),
    "not_an_event": (lambda e: e.append("{"), "not an event"),
    # The prompt binding: one user text message, prompt.md's, and otherwise
    # only the results of the judge's own StructuredOutput calls.
    "other_prompt": (
        lambda e: e[0].update(_user("Classify another case.\n")),
        "its user message is not prompt.md",
    ),
    "no_prompt": (lambda e: e.pop(0), "0 user text messages"),
    "second_text": (
        lambda e: e.insert(7, _user("Also weigh this hint.")),
        "2 user text messages",
    ),
    "nudge_not_meta": (
        lambda e: e.insert(7, _user(driver.JUDGE_PROMPT_NUDGE)),
        "2 user text messages",
    ),
    "meta_text_part": (
        lambda e: e.insert(
            7, _user([{"type": "text", "text": "A hint."}], isMeta=True)
        ),
        "not a StructuredOutput call's result",
    ),
    "stray_result": (
        lambda e: e.append(_user([{"type": "tool_result", "tool_use_id": "call-8"}])),
        "not a StructuredOutput call's result",
    ),
    "forged_answer": (_forged_answer, "not a StructuredOutput call's result"),
    # The verdict: the one accepted answer must be verdict.json.
    "other_answer": (
        lambda e: e[7]["message"]["content"][0]["input"].update(rationale="Other."),
        "its accepted StructuredOutput answer is not verdict.json",
    ),
    # Only the event types the isolated transcripts carry.
    "unlisted_event": (
        lambda e: e.append(_event("progress", data={"phase": "thinking"})),
        "an event of type 'progress'",
    ),
    # No account data outside the prompt's own text and the judge's words.
    "email_in_system_prompt": (
        lambda e: e[5].update(
            _attachment("prompt_snapshot", systemPrompt=["Mail max@example.org."])
        ),
        r"an e-mail address at line 6\.attachment\.systemPrompt\[0\]",
    ),
    "account_key_in_environment": (
        lambda e: e[1].update(
            _attachment(
                "environment",
                snapshot={"isGitRepo": False, "identity": {"accountUuid": "8f0c"}},
            )
        ),
        r"key line 2\.attachment\.snapshot\.identity\.accountUuid",
    ),
    "email_beside_the_prompt": (
        lambda e: e[0].update(userEmail="max@example.org"),
        r"key line 1\.userEmail",
    ),
    "account_key_beside_the_judges_words": (
        lambda e: e[6].update(organizationUuid="org-1"),
        r"key line 7\.organizationUuid",
    ),
    "email_in_queue_operation": (
        lambda e: e.insert(
            0, _event("queue-operation", operation="enqueue", content="max@x.org")
        ),
        r"an e-mail address at line 1\.content",
    ),
    "git_status_key": (
        lambda e: e[4].update(_attachment("date", gitStatus="M a.py")),
        r"key line 5\.attachment\.gitStatus",
    ),
}


@pytest.mark.parametrize("defect", sorted(TRANSCRIPT_DEFECTS))
def test_an_isolated_verdict_whose_transcript_fails_the_runners_checks_is_refused(
    provenance, defect
):
    cases, verify = provenance
    edit, problem = TRANSCRIPT_DEFECTS[defect]
    events = _clean_transcript()
    edit(events)
    _write_transcript(cases / ISOLATED, events)
    with pytest.raises(SystemExit, match=f"{ISOLATED}: .*{problem}"):
        verify()


def test_an_isolated_verdict_needs_its_transcript(provenance):
    cases, verify = provenance
    (cases / ISOLATED / "claude.transcript.jsonl").unlink()
    with pytest.raises(SystemExit, match="no transcript"):
        verify()


def test_an_answer_the_schema_refused_and_the_judge_gave_again_passes(provenance):
    cases, verify = provenance
    events = _clean_transcript()
    events[7:7] = [_call("StructuredOutput", "call-0"), _result("call-0", error=True)]
    _write_transcript(cases / ISOLATED, events)
    verify()


def test_claude_codes_own_structured_output_nudge_passes(provenance):
    """The judge answered in text, Claude Code nudged it (an isMeta user
    message) and it called StructuredOutput."""
    cases, verify = provenance
    events = _clean_transcript()
    events.insert(7, _user(driver.JUDGE_PROMPT_NUDGE, isMeta=True))
    _write_transcript(cases / ISOLATED, events)
    verify()


def test_an_address_in_the_prompt_or_the_judges_own_words_passes(provenance):
    """The account-data rule reads neither the judged prompt's own text nor
    the judge's turns."""
    cases, verify = provenance
    case = cases / ISOLATED
    prompt = "Classify these wrong answers; the filer wrote to irs@example.gov.\n"
    (case / "prompt.md").write_text(prompt)
    events = _clean_transcript()
    events[0] = _user(prompt)
    events[6]["message"]["content"] = [{"type": "text", "text": "irs@example.gov"}]
    _write_transcript(case, events)

    def follow(entries):
        entry = next(e for e in entries if e["case_id"] == ISOLATED)
        entry["prompt_sha256"] = driver.digest(case / "prompt.md")

    verify(follow)


def test_the_runners_event_types_are_the_gates():
    script = (driver.ROOT / "scripts/run_audit_claude.sh").read_text()
    line = next(line for line in script.splitlines() if line.startswith("EVENT_TYPES="))
    assert set(line.split('"')[1].split(",")) == driver.JUDGE_EVENT_TYPES


def test_the_runners_account_patterns_are_the_gates():
    script = (driver.ROOT / "scripts/run_audit_claude.sh").read_text()
    assert driver.ACCOUNT_KEY.flags & re.IGNORECASE
    assert f'account_key = re.compile(r"{driver.ACCOUNT_KEY.pattern}", re.I)' in script
    assert f'email_address = re.compile(r"{driver.EMAIL_ADDRESS.pattern}")' in script


def test_the_runners_nudge_is_the_gates():
    script = (driver.ROOT / "scripts/run_audit_claude.sh").read_text()
    line = next(
        line for line in script.splitlines() if line.startswith("PROMPT_NUDGE=")
    )
    assert line == f'PROMPT_NUDGE="{driver.JUDGE_PROMPT_NUDGE}"'


TRANSCRIPT_GATE = (
    "account_data",
    "outside_the_judge",
    "transcript_problems",
    "withhold_addresses",
)


def _both_gates(path: Path, effort, prompt: bytes, verdict) -> tuple:
    results = []
    for module in (driver, gpt61sol):
        try:
            results.append(module.transcript_problems(path, effort, prompt, verdict))
        except Exception as error:  # noqa: BLE001 - compared, not swallowed
            results.append((type(error).__name__, str(error)))
    return tuple(results)


def test_this_drivers_transcript_gate_is_the_gpt61sol_drivers():
    """tests/test_run_audit_claude.py compares the runner with the GPT-6.1 Sol
    driver's Python port of its transcript checks, so this driver's port must
    be that one: the same source, the same constants and, on every defect the
    tests name, the same problems."""
    for name in TRANSCRIPT_GATE:
        assert inspect.getsource(getattr(driver, name)) == inspect.getsource(
            getattr(gpt61sol, name)
        ), name
    for name in (
        "JUDGE_ATTACHMENTS",
        "JUDGE_EVENT_TYPES",
        "JUDGE_PROMPT_NUDGE",
        "JUDGE_SIDECAR_FIELDS",
        "JUDGE_PROVENANCE_KEYS",
        "JUDGE_PROVENANCE_ENTRY_KEYS",
        "WITHHELD_ADDRESS",
        "JUDGE_MODEL",
    ):
        assert getattr(driver, name) == getattr(gpt61sol, name), name
    for name in ("ACCOUNT_KEY", "EMAIL_ADDRESS"):
        ours, theirs = getattr(driver, name), getattr(gpt61sol, name)
        assert (ours.pattern, ours.flags) == (theirs.pattern, theirs.flags), name
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "claude.transcript.jsonl"
        for defect in [None, *sorted(TRANSCRIPT_DEFECTS)]:
            events = _clean_transcript()
            if defect is not None:
                TRANSCRIPT_DEFECTS[defect][0](events)
            _write_transcript(path.parent, events)
            ours, theirs = _both_gates(path, "xhigh", JUDGED.encode(), _verdict([NEW]))
            assert ours == theirs, defect
            # The comparison is not vacuous: each named defect is a problem.
            assert (ours == []) == (defect is None), defect


JSON_EVENT = st.fixed_dictionaries(
    {"type": st.sampled_from(sorted(driver.JUDGE_EVENT_TYPES | {"system", "other"}))},
    optional={
        "message": st.fixed_dictionaries(
            {},
            optional={
                "content": st.text(max_size=12)
                | st.lists(
                    st.fixed_dictionaries(
                        {
                            "type": st.sampled_from(
                                ["text", "tool_use", "tool_result", "server_tool_use"]
                            )
                        },
                        optional={
                            "id": st.sampled_from(["c1", "c2"]),
                            "tool_use_id": st.sampled_from(["c1", "c2"]),
                            "name": st.sampled_from(["StructuredOutput", "Read"]),
                            "input": JSON_VALUES,
                            "is_error": st.booleans(),
                        },
                    ),
                    max_size=3,
                )
            },
        ),
        "attachment": st.fixed_dictionaries(
            {"type": st.sampled_from(sorted(driver.JUDGE_ATTACHMENTS | {"skill"}))},
            optional={"context": JSON_VALUES, "snapshot": JSON_VALUES},
        ),
        "effort": st.sampled_from(["xhigh", "max"]),
        "isMeta": st.booleans(),
        "userEmail": st.just("a@b.org"),
    },
)


@settings(max_examples=200, deadline=None)
@given(
    events=st.lists(JSON_EVENT | JSON_VALUES, max_size=6),
    defects=st.lists(st.sampled_from(sorted(TRANSCRIPT_DEFECTS)), max_size=3),
    effort=st.none() | st.just("xhigh"),
)
def test_the_transcript_gates_agree_on_any_transcript(events, defects, effort):
    """Differential: on arbitrary event lists, and on any combination of the
    named defects, both drivers' transcript checks give the same answer."""
    clean = _clean_transcript()
    for defect in defects:
        try:
            TRANSCRIPT_DEFECTS[defect][0](clean)
        except (IndexError, KeyError, TypeError, AttributeError):
            pass
    with tempfile.TemporaryDirectory() as scratch:
        for lines in (events, clean, clean + events):
            path = Path(scratch) / "claude.transcript.jsonl"
            path.write_text("".join(json.dumps(line) + "\n" for line in lines))
            ours, theirs = _both_gates(path, effort, JUDGED.encode(), _verdict([NEW]))
            assert ours == theirs


def test_a_prompt_changed_after_its_judge_ran_is_refused(provenance):
    """A prompt.md replaced after judging, with the record following it, still
    disagrees with the prompt the judge's transcript shows."""
    cases, verify = provenance
    (cases / ISOLATED / "prompt.md").write_text("Classify these, and one more.\n")

    def follow(entries):
        entry = next(e for e in entries if e["case_id"] == ISOLATED)
        entry["prompt_sha256"] = driver.digest(cases / ISOLATED / "prompt.md")

    with pytest.raises(SystemExit, match=f"{ISOLATED}: its user message is not"):
        verify(follow)


def test_an_unhardened_verdicts_transcript_is_not_held_to_isolation(provenance):
    cases, verify = provenance
    events = _clean_transcript()
    _read_call(events)
    _write_transcript(cases / UNHARDENED, events)
    verify()


def test_export_writes_no_receipt_when_the_record_disagrees(exporting, monkeypatch):
    stage, bundle, run, _ = exporting
    _evidence(stage, bundle)
    case = stage / "audit/cases" / ISOLATED
    case.mkdir(parents=True)
    (case / "prompt.md").write_text(JUDGED)
    write_verdict(case, _verdict([NEW]), **ISOLATED_SIDECAR)
    _write_transcript(case, _clean_transcript())
    entry = _record_entry(case, GROUPS[ISOLATED])
    driver.JUDGE_PROVENANCE.write_text(json.dumps(_provenance_record([entry])))
    monkeypatch.setattr(driver, "rejudged_cases", lambda stage: frozenset({ISOLATED}))
    incumbents = _incumbents()
    run(_exported(incumbents), incumbents)
    receipt = json.loads((stage / "release-ready.json").read_text())
    assert f"audit/cases/{ISOLATED}/claude.transcript.jsonl" in receipt["files"]

    (stage / "release-ready.json").unlink()
    (stage / "data-board47.json").unlink()
    entry["isolated"] = False
    driver.JUDGE_PROVENANCE.write_text(json.dumps(_provenance_record([entry])))
    with pytest.raises(SystemExit, match="disagree with docs/haiku55"):
        run(_exported(incumbents), incumbents)
    assert not (stage / "release-ready.json").exists()
    assert not (stage / "data-board47.json").exists()


def test_the_committed_provenance_record_is_public_and_tallied():
    """Once committed: the record is json.dumps(indent=1), ASCII-escaped, with
    a trailing newline; it names no e-mail address, and its counts are the
    tally of its entries' groups."""
    if not driver.JUDGE_PROVENANCE.is_file():
        pytest.skip("docs/haiku55/judge_provenance.json is not written yet")
    text = driver.JUDGE_PROVENANCE.read_text()
    record = json.loads(text)
    assert text == json.dumps(record, indent=1) + "\n" and text.isascii()
    assert not driver.EMAIL_ADDRESS.search(text)
    groups = [entry["group"] for entry in record["verdicts"]]
    assert record["counts"] == {group: groups.count(group) for group in groups}


def test_the_committed_provenance_record_describes_the_stage():
    """Local only, read-only, once written: the record passes the gate
    against the live stage, every isolated transcript included."""
    if not driver.JUDGE_PROVENANCE.is_file():
        pytest.skip("docs/haiku55/judge_provenance.json is not written yet")
    if not (STAGE / "audit/cases").is_dir():
        pytest.skip("needs the Claude Haiku 5.5 stage")
    driver.verify_judge_provenance(
        STAGE / "audit/cases", driver.rejudged_cases(STAGE), driver.JUDGE_PROVENANCE
    )


# --- The fold ------------------------------------------------------------------

REFERENCE = pd.read_csv(driver.SNAPSHOT / "reference_outputs.csv")[driver.KEY]
TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    max_size=12,
)
NUMBERS = st.one_of(
    st.none(),
    st.floats(min_value=-1e7, max_value=1e7, allow_nan=False).map(
        lambda x: round(x, 2)
    ),
    st.integers(min_value=0, max_value=10**6).map(float),
)


def _frame(model: str, rng, pools: dict) -> pd.DataFrame:
    count = len(REFERENCE)
    frame = REFERENCE.copy()
    frame.insert(0, "model", model)
    for column, pool in pools.items():
        frame[column] = [pool[i] for i in rng.integers(0, len(pool), count)]
    frame["provider_resolved_model"] = model
    return frame


@settings(max_examples=12, deadline=None)
@given(
    incumbents=st.integers(min_value=1, max_value=3),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
    numbers=st.lists(NUMBERS, min_size=1, max_size=6),
    words=st.lists(TEXT, min_size=1, max_size=6),
    extra_column=st.booleans(),
)
def test_the_fold_keeps_incumbent_rows_and_adds_1984_rows_for_the_addition(
    tmp_path_factory, incumbents, seed, numbers, words, extra_column
):
    """Any board: incumbent rows survive byte for byte; the addition is exact.

    Prediction columns keep their production types: numeric columns are
    floats, and text columns carry prose (a letter before any digits).
    """
    import freeze_snapshot as freezer
    import numpy as np

    from policybench.fold_board import fold_board

    rng = np.random.default_rng(seed)
    prose = [f"x{word}" for word in words] + [None]
    pools = {
        "prediction": numbers,
        "explanation": prose,
        "raw_response": prose,
        "error": [None, "Timeout, retried", 'said "no"'],
        "prompt_tokens": numbers,
        "completion_tokens": numbers,
    }
    root = tmp_path_factory.mktemp("fold")
    base = pd.concat(
        [_frame(f"incumbent-{i}", rng, pools) for i in range(incumbents)],
        ignore_index=True,
    )
    base_path = root / "base-predictions.csv"
    base.to_csv(base_path, index=False)
    addition = _frame(NEW, rng, pools)
    if extra_column:
        addition["provider_system_fingerprint"] = "fp_1"
        addition = addition.drop(columns=["raw_response"])
    addition_path = root / "fold.csv"
    addition.to_csv(addition_path, index=False)
    scoring = root / "scoring"
    scoring.mkdir()
    for name in driver.REFERENCE_FILES:
        shutil.copyfile(driver.SNAPSHOT / name, scoring / name)

    result = fold_board(
        base_path, [addition_path], scoring, root / "fold", export=False
    )

    assert result["excluded"] == {} and result["models"] == incumbents + 1
    folded_path = root / "fold/us/predictions.csv"
    folded = pd.read_csv(folded_path, low_memory=False)
    new_rows = folded[folded.model == NEW]
    assert len(new_rows) == len(REFERENCE) == 1984
    assert set(new_rows[driver.KEY].itertuples(index=False, name=None)) == set(
        REFERENCE.itertuples(index=False, name=None)
    )
    reread = pd.read_csv(base_path, low_memory=False)
    text = {"dtype": str, "keep_default_na": False}
    base_text = pd.read_csv(base_path, **text)
    folded_text = pd.read_csv(folded_path, **text)[base_text.columns]
    for i in range(incumbents):
        model = f"incumbent-{i}"
        assert freezer._model_prediction_rows_sha256(
            folded, model
        ) == freezer._model_prediction_rows_sha256(reread, model)
        before = base_text[base_text.model == model].reset_index(drop=True)
        after = folded_text[folded_text.model == model].reset_index(drop=True)
        pd.testing.assert_frame_equal(before, after)
    for name in driver.REFERENCE_FILES:
        assert (root / "fold/us" / name).read_bytes() == (
            driver.SNAPSHOT / name
        ).read_bytes()


# --- One tag constant ----------------------------------------------------------


def test_the_release_tag_is_named_in_one_place():
    """RELEASE_TAG is the only spelling of the new tag in the driver's scripts,
    tests and design note; the spec, which the freeze checks against it, is
    the one input that names it too."""
    source = (REPO / "scripts/finish_haiku55.py").read_text().splitlines()
    assert sum(driver.RELEASE_TAG in line for line in source) == 1
    for relative in (
        "scripts/freeze_haiku55.py",
        "docs/haiku55/design.md",
        "tests/test_finish_haiku55.py",
    ):
        path = REPO / relative
        if path.is_file():
            assert driver.RELEASE_TAG not in path.read_text(), relative
    assert real_spec()["release_tag"] == driver.RELEASE_TAG


def test_the_freeze_tests_do_not_spell_the_release_tag():
    """The same rule for tests/test_freeze_haiku55.py, kept apart so a
    failure names that file's lines."""
    path = REPO / "tests/test_freeze_haiku55.py"
    if not path.is_file():
        pytest.skip("tests/test_freeze_haiku55.py does not exist yet")
    lines = [
        number
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if driver.RELEASE_TAG in line
    ]
    assert lines == [], f"tests/test_freeze_haiku55.py spells the tag on {lines}"
