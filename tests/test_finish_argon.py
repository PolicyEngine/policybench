"""The Gemini 4 Argon and Muse Spark 1.3 additions move no incumbent.

Adapted from test_finish_musewonder.py, without its engine-upgrade tests: this
release's driver installs no reference build. Synthetic data stands in for runs,
audits and payloads. Release 20261013b is read from git at BASE_COMMIT, never
from the working tree (the freeze rewrites it). Tests that read the seed
copy, the main clone's grounding or the live stage read them only, and skip
where they are absent.
"""

from __future__ import annotations

import contextlib
import copy
import csv
import functools
import gzip
import hashlib
import inspect
import io
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

import finish_argon as driver  # noqa: E402
import finish_gpt61sol as gpt61sol  # noqa: E402
import release_20261006  # noqa: E402

from policybench.audit import AUDIT_OUTPUT_SCHEMA  # noqa: E402

# The two additions. Most synthetic cases use the first; a gate that names
# every registered model gets both.
NEW = "gemini-4-argon"
SLUG = "argon"
OTHER = "muse-spark-1.3"
OTHER_SLUG = "musespark"
ADDITIONS = {SLUG: NEW, OTHER_SLUG: OTHER}
REPO = Path(__file__).resolve().parents[1]
BASE_COMMIT = driver.BASE_COMMIT
COMMITTED_SEED_DIGEST_SHA256 = driver.SEED_DIGEST_SHA256
SNAPSHOT_PATH = Path("paper/snapshot/20260501/runs") / driver.RUN_NAME
ADJUDICATIONS_PATH = Path("annotations") / driver.RUN_NAME / driver.ADJUDICATIONS
EXCLUSIONS_NAME = "reference_exclusions.json"
BOUND_EXCLUSIONS = f"publish/{driver.RUN_NAME}/us/{EXCLUSIONS_NAME}"
# Release 20261013b's audit (the seed, a read-only copy), the grounding it was
# rendered with, the supervised runs root and the live stage. All local only;
# nothing here writes to them.
SEED = REPO / "results/local/argon/seed-20261013b/audit"
STAGE = REPO / "results/local/argon/stage"
# The working stage: STAGE itself (local only). The committed judge
# provenance record describes it.
WORKING_STAGE = STAGE
GROUNDING = Path(
    "/Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit/"
    "grounding.csv"
)
RUNS = Path("/Users/maxghenis/PolicyEngine/policybench/results/local/argon-runs")
# The UTC day a test's adjudicate step says its decisions were written on.
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


@functools.cache
def base_blob(path: Path) -> bytes:
    """A repository file as committed at BASE_COMMIT (release 20261013b)."""
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
    """Write release 20261013b's five reference files into ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in driver.REFERENCE_FILES:
        (directory / name).write_bytes(base_blob(SNAPSHOT_PATH / name))
    return directory


def base_record() -> dict:
    """Release 20261013b's exclusion record, a fresh copy each call."""
    return json.loads(base_blob(SNAPSHOT_PATH / EXCLUSIONS_NAME))


def base_adjudication_record() -> dict:
    """Release 20261013b's adjudication record file, a fresh copy each call."""
    return json.loads(base_blob(ADJUDICATIONS_PATH))


def real_spec() -> dict:
    """docs/argon/spec.json as the working tree holds it."""
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


def test_the_additions_are_argon_and_muse_spark_on_a_50_model_board():
    assert driver.MODELS == ADDITIONS
    assert driver.BASE_MODELS == 48 and driver.BOARD_MODELS == 50
    assert driver.BASE_OUTPUTS == 1984
    assert driver.BASE_EXCLUSIONS == 49 and driver.BASE_SCORED == 1935
    assert driver.NEW_EXCLUSIONS == 0 and driver.RELEASE_EXCLUSIONS == 49
    assert driver.RELEASE_SCORED == 1935
    assert driver.BASE_TAG == "dashboard-data-20261013b"
    # PENDING(#218): PR #218's squash merge on main.
    assert driver.BASE_COMMIT == "6c44858feddc68890738e6f07b31ab9e6968bac1"
    assert driver.SEED_RELEASE_COMMIT == driver.BASE_COMMIT
    assert set(driver.BASE_REFERENCE_SHA256) == set(driver.REFERENCE_FILES)
    assert driver.JUDGE_MODEL == "claude-opus-5-5"
    assert driver.JUDGE_TEMPLATE_VERSION == 2
    assert driver.REWORDED_SINCE_SEED == frozenset()
    assert driver.BASE_ENGINE == "policyengine-us 2.41.0"


def test_the_spec_names_this_drivers_release_and_base():
    """The freeze compares the spec's tag and base with the driver's."""
    spec = real_spec()
    assert spec["release_tag"] == driver.RELEASE_TAG
    assert spec["base_tag"] == driver.BASE_TAG
    assert spec["base_sha256"] == driver.BASE_SHA256


def test_the_base_pointer_at_the_base_commit_is_release_20261013b():
    """BASE_TAG and BASE_SHA256 are what the base release's merge commits as
    the live dashboard pointer."""
    pointer = json.loads(base_blob(Path("app/src/data.artifact.json")))
    assert pointer["tag"] == driver.BASE_TAG
    assert pointer["sha256"] == driver.BASE_SHA256


# --- Run discovery -------------------------------------------------------------


@pytest.fixture
def runs(tmp_path):
    root = tmp_path / "runs"
    for slug, model in ADDITIONS.items():
        directory = root / slug / "run"
        directory.mkdir(parents=True)
        (directory / "run_state.json").write_text(
            json.dumps(
                {
                    "model": model,
                    "completed": 100,
                    "total": 100,
                    "stopped_reason": None,
                }
            )
        )
        (directory / "predictions.csv").write_text("model,scenario_id,variable\n")
    return root


def change_state(root, **changes):
    path = root / SLUG / "run/run_state.json"
    state = json.loads(path.read_text())
    state.update(changes)
    path.write_text(json.dumps(state))


def test_discovers_only_the_registered_models(runs):
    extra = runs / "sonnet55/run"
    extra.mkdir(parents=True)
    (extra / "run_state.json").write_text(json.dumps({"model": "claude-sonnet-5.5"}))
    found = driver.discover_new_models(runs)
    assert [(run.slug, run.model) for run in found] == list(ADDITIONS.items())
    assert all(run.predictions.parent == run.run_dir for run in found)


def test_a_missing_run_of_either_addition_is_refused(runs):
    """Both additions must have finished: one alone is not the release."""
    shutil.rmtree(runs / OTHER_SLUG)
    with pytest.raises(SystemExit, match=f"{OTHER_SLUG}: no run_state.json"):
        driver.discover_new_models(runs)


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
    assert len(driver.discover_new_models(runs)) == len(ADDITIONS)


# --- Input pins ----------------------------------------------------------------


def test_pin_inputs_writes_the_finished_runs_file_hashes(runs, tmp_path, monkeypatch):
    """--step pin-inputs needs no stage: it hashes the finished run's
    predictions.csv and run_state.json and refuses an unfinished run."""
    pins = tmp_path / "input_pins.json"
    monkeypatch.setattr(driver, "INPUT_PINS", pins)
    driver.main(["--step", "pin-inputs", "--runs-root", str(runs)])
    record = json.loads(pins.read_text())
    assert record == driver.input_pins_record(runs)
    assert record["inputs"] == {
        slug: {
            "run": f"runs/{slug}/run",
            "sha256": {
                name: hashlib.sha256(
                    (runs / slug / "run" / name).read_bytes()
                ).hexdigest()
                for name in ("predictions.csv", "run_state.json")
            },
        }
        for slug in ADDITIONS
    }
    change_state(runs, completed=99)
    with pytest.raises(SystemExit, match="refusing incomplete additions"):
        driver.main(["--step", "pin-inputs", "--runs-root", str(runs)])


# The first and last hex digits of each addition's pinned run files, as the
# design note gives them.
COMMITTED_PINS = {
    SLUG: {
        "predictions.csv": ("76724f96", "6462"),
        "run_state.json": ("b2af6808", "f80d"),
    },
    OTHER_SLUG: {
        "predictions.csv": ("1e4c81a1", "87d3"),
        "run_state.json": ("923d8c2b", "292c"),
    },
}


def test_the_committed_input_pins_name_both_run_files_of_each_addition():
    """Runs anywhere: the committed pins name each addition's two run files,
    as the design note gives them."""
    record = json.loads(driver.INPUT_PINS.read_text())
    assert set(record["inputs"]) == set(ADDITIONS)
    for slug, expected in COMMITTED_PINS.items():
        assert record["inputs"][slug]["run"] == f"argon-runs/{slug}/run"
        pins = record["inputs"][slug]["sha256"]
        assert set(pins) == {"predictions.csv", "run_state.json"}
        assert all(re.fullmatch("[0-9a-f]{64}", value) for value in pins.values())
        for name, (start, end) in expected.items():
            assert pins[name].startswith(start) and pins[name].endswith(end)
    assert driver.INPUT_PINS.read_text() == (
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )


def test_the_committed_input_pins_are_the_finished_runs():
    """Local only: recomputed from the run directory, the pins are the same."""
    if not all((RUNS / slug / "run").is_dir() for slug in ADDITIONS):
        pytest.skip("the additions' run directories are not on this machine")
    assert driver.input_pins_record(RUNS) == json.loads(driver.INPUT_PINS.read_text())


@pytest.mark.slow
def test_the_stages_inputs_are_the_pinned_run():
    """Local only, read-only: the stage's copies are the pinned bytes, its
    prepare-time hashes hold, and its bundle rows are the run file's in every
    column (this reads the stage's 700 MB bundle predictions)."""
    if not all((STAGE / "inputs" / slug).is_dir() for slug in ADDITIONS):
        pytest.skip("needs the release's stage")
    inputs = json.loads(driver.INPUT_PINS.read_text())["inputs"]
    for slug in ADDITIONS:
        for name, pin in inputs[slug]["sha256"].items():
            assert driver.digest(STAGE / "inputs" / slug / name) == pin
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
    record = {
        "inputs": {
            slug: {"sha256": {"predictions.csv": "a" * 64, "run_state.json": "b" * 64}}
            for slug in ADDITIONS
        }
    }
    pins.write_text(json.dumps(record))
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    commit(root, "pins")
    monkeypatch.setattr(driver, "ROOT", root)
    monkeypatch.setattr(driver, "INPUT_PINS", pins)
    return pins, record


def test_the_input_pins_are_read_as_committed_at_head(pinned_repo):
    pins, record = pinned_repo
    assert driver.committed_input_pins() == {
        slug: {"predictions.csv": "a" * 64, "run_state.json": "b" * 64}
        for slug in ADDITIONS
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
    monkeypatch.setattr(driver, "INPUT_PINS_PATH", "docs/argon/other_pins.json")
    monkeypatch.setattr(driver, "INPUT_PINS", elsewhere)
    with pytest.raises(SystemExit, match="is not committed at HEAD"):
        driver.committed_input_pins()


@pytest.mark.parametrize(
    "inputs",
    [
        {},
        {SLUG: {"sha256": {"predictions.csv": "a" * 64}}},
        {SLUG: {"sha256": {"predictions.csv": "a", "run_state.json": "b"}}, "x": {}},
        # One addition pinned in full, the other not at all.
        {SLUG: {"sha256": {"predictions.csv": "a" * 64, "run_state.json": "b" * 64}}},
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
    """Release 20261013b's references, read from BASE_COMMIT, are the pinned
    bytes: 49 exclusions (42 unlisted inputs, five engine defects and two
    later-published law), and 1,935 scored outputs."""
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
    assert reasons.count("reference_engine_defect") == 5
    assert reasons.count("reference_depends_on_unlisted_input") == 42
    assert reasons.count("reference_law_published_after_freeze") == 2
    reference = pd.read_csv(snapshot / "reference_outputs.csv")
    assert len(reference) == driver.BASE_OUTPUTS
    assert reference.scenario_id.nunique() == 100
    assert len(split_reference(reference, exclusions)[0]) == driver.BASE_SCORED


def test_the_committed_adjudications_exclude_exactly_the_scoring_exclusions(
    tmp_path,
):
    """Release 20261013b's record (61 decisions, 49 of them exclusions) excludes
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
    assert len(decisions) == 61
    assert excluded_case_keys(decisions) == excluded
    assert ("scenario_023", "head_medicaid_eligible") in excluded


@pytest.fixture
def pinned_copy(tmp_path):
    """A copy of release 20261013b's five reference files."""
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
    """The release rules nothing, so its exclusion pin is release 20261013b's
    own: the committed copy passes under it, and an edited record does not."""
    assert release_sha() == driver.BASE_REFERENCE_SHA256[EXCLUSIONS_NAME]
    driver.verify_reference_pins(pinned_copy, "staged reference", release_sha())
    with (pinned_copy / EXCLUSIONS_NAME).open("a") as stream:
        stream.write(" ")
    with pytest.raises(SystemExit, match="reference_exclusions.json does not match"):
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


def test_the_base_commit_holds_release_20261013b():
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
    with pytest.raises(SystemExit, match="fail release 20261013b's manifest hash"):
        driver.verify_base_predictions(snapshot)


def test_release_20261013bs_manifest_pins_its_predictions():
    manifest = json.loads(
        driver.base_commit_blob(Path("paper/snapshot/20260501/manifest.json"))
    )
    pin = manifest["source_run_artifacts"][driver.RUN_NAME]["files"]
    raw = driver.base_commit_blob(
        driver.SNAPSHOT.relative_to(driver.ROOT) / "predictions.csv.gz"
    )
    assert hashlib.sha256(raw).hexdigest() == pin["predictions.csv.gz"]


def test_base_commit_blob_names_the_missing_history():
    with pytest.raises(
        SystemExit, match=f"cannot read .* at base commit {BASE_COMMIT[:12]}"
    ):
        driver.base_commit_blob(Path("no/such/file.csv"))


def test_base_commit_blob_names_a_missing_commit(monkeypatch):
    monkeypatch.setattr(driver, "BASE_COMMIT", "0" * 40)
    with pytest.raises(SystemExit, match="at base commit 000000000000.*unshallow"):
        driver.base_commit_blob(Path("app/src/data.artifact.json"))


def test_a_re_export_after_the_freeze_reads_20261013b_from_git(monkeypatch):
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


def test_the_git_base_must_rewrap_to_the_20261013b_asset(monkeypatch):
    raw = _gz_payload(48)
    monkeypatch.setattr(driver, "base_commit_blob", lambda path: raw)
    monkeypatch.setattr(driver, "live_pointer", lambda: {"tag": driver.RELEASE_TAG})
    with pytest.raises(SystemExit, match="base payload SHA256 mismatch"):
        driver.resolve_live_base(SimpleNamespace())
    wrapped = json.dumps({"countries": {"us": json.loads(gzip.decompress(raw))}})
    monkeypatch.setattr(
        driver, "BASE_SHA256", hashlib.sha256(wrapped.encode()).hexdigest()
    )
    live = driver.resolve_live_base(SimpleNamespace())
    assert len(live["countries"]["us"]["modelStats"]) == 48
    short = _gz_payload(47)
    monkeypatch.setattr(driver, "base_commit_blob", lambda path: short)
    wrapped = json.dumps({"countries": {"us": json.loads(gzip.decompress(short))}})
    monkeypatch.setattr(
        driver, "BASE_SHA256", hashlib.sha256(wrapped.encode()).hexdigest()
    )
    with pytest.raises(SystemExit, match="base must have 48 models"):
        driver.resolve_live_base(SimpleNamespace())


@pytest.mark.parametrize("tag", ["dashboard-data-20260930", "dashboard-data-20991231"])
def test_any_other_pointer_is_refused(monkeypatch, tag):
    monkeypatch.setattr(driver, "live_pointer", lambda: {"tag": tag})
    with pytest.raises(SystemExit, match="base pointer changed"):
        driver.resolve_live_base(SimpleNamespace())


def sha(data) -> str:
    raw = data.read_bytes() if isinstance(data, Path) else data
    return hashlib.sha256(raw).hexdigest()


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


def judged_prompt(body: str, version: int = driver.JUDGE_TEMPLATE_VERSION) -> str:
    """A synthetic prompt that begins with the header of ``version``, as
    every rendered prompt does: validate_verdicts holds a prompt's header to
    the version its verdict's sidecar records."""
    from policybench.judge_template import template_header

    return template_header(version) + "\n" + body


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
        # A new verdict is on this release's template; a seed's sidecar
        # records none (v1) and passes judge_template_version=None.
        "judge_template_version": driver.JUDGE_TEMPLATE_VERSION,
        **meta,
    }
    (case / "verdict.meta.json").write_text(
        json.dumps({k: v for k, v in sidecar.items() if v is not None})
    )


def _audit(root, wrong_models):
    case = root / "cases/us__scenario_000__snap"
    case.mkdir(parents=True)
    (case / "prompt.md").write_text(judged_prompt("Classify these wrong answers.\n"))
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


def test_a_new_verdict_must_stand_on_a_v2_prompt_whatever_its_sidecar_says(audit):
    """The review's case: a new verdict whose prompt.md is rendered on v1,
    with its verdict and prompt hashes bound and a sidecar that claims v2, is
    refused: the prompt's header must be the version the sidecar records."""
    root, case, verdict = audit
    assert driver.validate_verdicts(root) == []
    (case / "prompt.md").write_text(
        judged_prompt("Classify these wrong answers.\n", version=1)
    )
    write_verdict(case, verdict)
    meta = json.loads((case / "verdict.meta.json").read_text())
    assert meta["judge_template_version"] == 2
    assert meta["prompt_sha256"] == sha(case / "prompt.md")
    assert driver.validate_verdicts(root) == [case.name]
    # Recording v1 for it agrees with its header but is not this release's.
    write_verdict(case, verdict, judge_template_version=1)
    assert driver.validate_verdicts(root) == [case.name]


def test_a_carried_verdict_whose_sidecar_disagrees_with_its_prompt_is_refused(audit):
    """A seed case keeps its seed bytes, and its sidecar must still record the
    version its prompt was rendered on."""
    root, case, _ = audit
    seed = {
        case.name: {
            "prompt_sha256": sha(case / "prompt.md"),
            "verdict_sha256": sha(case / "verdict.json"),
        }
    }
    assert driver.validate_verdicts(root, seed=seed) == []
    meta = json.loads((case / "verdict.meta.json").read_text())
    meta["judge_template_version"] = 1
    (case / "verdict.meta.json").write_text(json.dumps(meta))
    with pytest.raises(SystemExit, match="carried-over verdicts.*judge template"):
        driver.validate_verdicts(root, seed=seed)


def test_every_verdict_is_bound_to_its_own_bytes(tmp_path):
    """An incumbent verdict's sidecar must match its bytes too, not only a
    verdict that names Gemini 4 Argon."""
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
    # MOCK: a synthetic seed judged on judge template v1 before versions
    # existed, so its sidecars record none (release 20261013b's real seed mixes
    # v1 and v2 verdicts; test_every_seed_prompt_rerenders_from_the_base_on_its_
    # recorded_version covers it).
    prepare_audit(seed_board / "us", seed, grounding_lookup=lookup, template_version=1)
    for item in map(json.loads, (seed / "cases.jsonl").read_text().splitlines()):
        write_verdict(
            seed / "cases" / item["case_id"],
            _verdict(item["wrong_models"]),
            judge_model_requested="default",
            judge_model_reported=["gpt-6.1-sol"],
            prompt_sha256=None,
            judge_template_version=None,
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
            # re-renders the case's prompt, as release 20261013b's rewording did.
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


# Gemini 4 Argon misses s0 alone: s0 is re-opened, s1 carries over.
JOINS_S0 = [
    (NEW, "s0", 99.0, "Guessed."),
    (NEW, "s1", 300.0, "Right."),
    (NEW, "s2", 100.0, "Right."),
]
# Gemini 4 Argon answers every output right: no case is joined.
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
    with pytest.raises(SystemExit, match="not release 20261013b's"):
        prepare(JOINS_S0)
    assert not (stage / "audit").exists()


def test_load_seed_refuses_a_stage_without_a_binding_or_with_another(seeded_stage):
    _, stage, prepare = seeded_stage
    prepare(JOINS_S0)
    receipt = json.loads((stage / "stage.json").read_text())
    edited = copy.deepcopy(receipt)
    edited["seed"]["us__s1__snap"]["verdict_sha256"] = "0" * 64
    (stage / "stage.json").write_text(json.dumps(edited))
    with pytest.raises(SystemExit, match="not release 20261013b's"):
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
    """Gemini 4 Argon answers s1 right and s0 wrong. Listing it as wrong on
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
    """s1's reference explanation is reworded and Gemini 4 Argon answers it
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
    """The real stage's case: Gemini 4 Argon answers all nine wrong."""
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
    of release 20261013b's 677 judged cases once."""
    raw = driver.SEED_DIGEST.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == driver.SEED_DIGEST_SHA256
    seed = _committed_seed_digest()
    assert driver.seed_digest_text(seed).encode() == raw
    assert len(seed) == 677
    hexes = [value for item in seed.values() for value in item.values()]
    assert all(len(h) == 64 and set(h) <= set("0123456789abcdef") for h in hexes)


def test_the_seed_is_release_20261013bs_audit():
    """Runs anywhere: the committed digest is release 20261013b's seed digest
    (docs/release_20261013b/seed_digest.csv), which is release 20261013's
    (docs/musewonder/seed_digest.csv with the 151 cases that release judged,
    docs/musewonder/judge_provenance.json, written over it) with the five
    cases release 20261013b re-judged (docs/release_20261013b/
    judge_provenance.json) written over those, and nothing else."""

    def read(path: Path) -> dict:
        lines = path.read_text().splitlines()
        return {
            case: {"prompt_sha256": prompt, "verdict_sha256": verdict}
            for case, prompt, verdict in (line.split(",") for line in lines[1:])
        }

    expected = read(REPO / "docs/musewonder/seed_digest.csv")
    judged = json.loads((REPO / "docs/musewonder/judge_provenance.json").read_text())
    rejudged = json.loads(
        (REPO / "docs/release_20261013b/judge_provenance.json").read_text()
    )
    assert len(expected) == 677 and len(judged["verdicts"]) == 151
    assert len(rejudged["verdicts"]) == 5
    for entry in [*judged["verdicts"], *rejudged["verdicts"]]:
        expected[entry["case_id"]] = {
            "prompt_sha256": entry["prompt_sha256"],
            "verdict_sha256": entry["verdict_sha256"],
        }
    assert _committed_seed_digest() == expected
    assert (
        driver.SEED_DIGEST.read_bytes()
        == (REPO / "docs/release_20261013b/seed_digest.csv").read_bytes()
    )


def test_every_committed_adjudication_decides_a_case_the_seed_judged():
    """Runs anywhere: a recorded decision of release 20261013b rules on a judge
    verdict, so its case is one of the seed's judged cases."""
    seed = _committed_seed_digest()
    assert {driver.case_id(entry) for entry in driver.base_adjudications()} <= set(seed)


def test_the_committed_seed_digest_matches_the_real_seed():
    """Local only: the digest equals the rebuilt seed on this machine."""
    if not SEED.is_dir():
        pytest.skip("release 20261013b's audit is not on this machine")
    assert driver.seed_digest_text(driver.seed_digest(SEED)) == (
        driver.SEED_DIGEST.read_text()
    )


def test_the_committed_adjudications_keep_the_seed_judge_verdicts():
    """Local only: every decision release 20261013b recorded keeps its seed
    verdict's class."""
    if not SEED.is_dir():
        pytest.skip("release 20261013b's audit is not on this machine")
    from freeze_snapshot import verify_adjudications_keep_judge_verdicts

    verify_adjudications_keep_judge_verdicts(
        driver.base_adjudications(), SEED / "cases"
    )


def test_each_20261013b_entry_names_its_seed_verdict_as_its_sidecar_records_it():
    """Local only: the restate script requires a re-opened entry to name its
    seed verdict, which it builds from the seed's sha256-bound sidecar: judge,
    classes, flag, flag source and UTC day. It holds for all 61 entries."""
    if not SEED.is_dir():
        pytest.skip("release 20261013b's audit is not on this machine")
    from date_adds0928_judge_verdicts import WAVE_FLAGS, _bound_verdict
    from restate_gpt61sol_adjudications import named_item, replaced_item

    waved = frozenset(json.loads(WAVE_FLAGS.read_text()))
    base = driver.base_adjudications()
    assert len(base) == 61
    for entry in base:
        found = _bound_verdict(SEED / "cases" / driver.case_id(entry))
        assert found is not None, driver.case_id(entry)
        key = f"{entry['scenario_id']}:{entry['variable']}"
        assert named_item(entry) == replaced_item(found, key in waved), entry


@pytest.mark.slow
def test_every_seed_prompt_rerenders_from_the_base_on_its_recorded_version(tmp_path):
    """Local only: release 20261013b's 48-model board, as BASE_COMMIT holds it,
    renders exactly the seed's cases, and each on the judge template version
    its verdict's sidecar records (v1 where none is recorded) is the seed's
    prompt byte for byte, so prepare_audit keeps every seed verdict (this
    reads the predictions from git into scratch). So check_prompt_changes may
    attribute every changed or new prompt to a new model joining its case."""
    if not (SEED.is_dir() and GROUNDING.is_file()):
        pytest.skip("release 20261013b's audit or grounding is not on this machine")
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
    # The seed's judged cases, as prepare copies them into a stage.
    for source in sorted((SEED / "cases").glob("*")):
        if (source / "prompt.md").is_file():
            (audit / "cases" / source.name).mkdir(parents=True)
            for name in ("prompt.md", "verdict.json", "verdict.meta.json"):
                if (source / name).is_file():
                    shutil.copyfile(source / name, audit / "cases" / source.name / name)
    arrow = hasattr(pd.options, "future") and hasattr(pd.options.future, "infer_string")
    with (
        pd.option_context("future.infer_string", False)
        if arrow
        else contextlib.nullcontext()
    ):
        prepare_audit(
            bundle / "us",
            audit,
            grounding_lookup=lookup,
            template_version=driver.JUDGE_TEMPLATE_VERSION,
        )
    seed = driver.seed_digest(SEED)
    assert driver.seed_digest(audit) == seed and len(seed) == 677


def test_the_stage_reopens_only_what_a_new_model_explains():
    """Local only, read-only: the live stage's prompt-changes.json is what
    check_prompt_changes derives from its prompts and the bound seed, and
    every re-opened case names Gemini 4 Argon or Muse Spark 1.3 among its
    wrong models."""
    if not (STAGE / driver.PROMPT_CHANGES).is_file():
        pytest.skip("needs the release's stage")
    recorded = json.loads((STAGE / driver.PROMPT_CHANGES).read_text())
    seed = json.loads((STAGE / "stage.json").read_text())["seed"]
    derived = driver.check_prompt_changes(
        STAGE / "audit",
        {case: item["prompt_sha256"] for case, item in seed.items()},
        frozenset(),
    )
    assert {key: sorted(value) for key, value in derived.items()} == recorded
    reopened = {*recorded["changed"], *recorded["added"]}
    manifest = {
        item["case_id"]: item
        for item in map(
            json.loads, (STAGE / "audit/cases.jsonl").read_text().splitlines()
        )
    }
    assert all(
        set(manifest[case]["wrong_models"]) & set(ADDITIONS.values())
        for case in reopened
    )


def test_the_stage_holds_the_installed_release_exclusions():
    """Local only, read-only: install-exclusions ran on the live stage and
    bound the release's record in both copies."""
    receipt_path = STAGE / "stage.json"
    if not receipt_path.is_file():
        pytest.skip("needs the Gemini 4 Argon stage")
    receipt = json.loads(receipt_path.read_text())
    installed = receipt.get("exclusions_installed")
    if installed is None or receipt.get("references_installed"):
        pytest.skip("install-exclusions has not run, or a build's record replaced it")
    assert installed["sha256"] == release_sha() == driver.release_exclusions_sha256()
    assert installed["base_sha256"] == driver.BASE_REFERENCE_SHA256[EXCLUSIONS_NAME]
    assert installed["records"] == driver.RELEASE_EXCLUSIONS
    assert receipt["files"][BOUND_EXCLUSIONS] == release_sha()
    for target in (STAGE / "scoring", STAGE / "publish" / driver.RUN_NAME / "us"):
        assert driver.digest(target / EXCLUSIONS_NAME) == release_sha()


# --- The release's exclusion record --------------------------------------------


def test_the_spec_rules_no_exclusion():
    """Max ruled d1252 and d1263 on 2026-10-13, both to keep: the spec names
    no proposal, no ruled adjudication and no restatement, so spec_records
    finds none and the release record is release 20261013b's."""
    spec = real_spec()
    assert spec["proposals"] == [] and spec["adjudications"] == []
    assert spec["restated_adjudications"] == []
    assert driver.NEW_EXCLUSIONS == 0
    with mock.patch.object(driver, "ROOT", REPO):
        assert driver.spec_records(spec) == []


def test_the_release_exclusions_are_release_20261013bs_unchanged():
    """With nothing ruled, build_release_exclusions returns release
    20261013b's record, and its text is the committed file's bytes."""
    with mock.patch.object(driver, "ROOT", REPO):
        record = driver.build_release_exclusions(base_record(), real_spec())
    assert record == base_record()
    assert release_text().encode() == base_blob(SNAPSHOT_PATH / EXCLUSIONS_NAME)
    assert release_sha() == driver.BASE_REFERENCE_SHA256[EXCLUSIONS_NAME]
    assert len(record["exclusions"]) == driver.RELEASE_EXCLUSIONS == 49


@pytest.mark.parametrize(
    "extra",
    [
        {"record_edits": [{"scenario_id": "scenario_000", "variable": "snap"}]},
        {"derivation_insert": {"before": " On", "text": " Extra."}},
    ],
)
def test_a_spec_that_edits_records_it_does_not_rule_is_refused(extra):
    spec = {**real_spec(), **extra}
    with mock.patch.object(driver, "ROOT", REPO):
        with pytest.raises(SystemExit, match="rules no record"):
            driver.build_release_exclusions(base_record(), spec)


# --- install-exclusions --------------------------------------------------------


@pytest.fixture
def installable(tmp_path):
    """A stage as prepare leaves it: release 20261013b's record in the scoring
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
        "records": 49,
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
    with pytest.raises(SystemExit, match="is not release 20261013b's"):
        driver.install_exclusions(SimpleNamespace(stage_dir=stage))
    assert {p: p.read_bytes() for p in stage.rglob("*") if p.is_file()} == before


def test_install_exclusions_requires_a_bound_record(installable):
    stage, _, receipt = installable
    del receipt["files"][BOUND_EXCLUSIONS]
    (stage / "stage.json").write_text(json.dumps(receipt))
    with pytest.raises(SystemExit, match="does not bind the exclusions"):
        driver.install_exclusions(SimpleNamespace(stage_dir=stage))


# --- Helpers the upgrade's adjudication tests share --------------------------


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


def _write_stage_record(tmp_path: Path, record: dict) -> Path:
    path = tmp_path / "publish" / driver.RUN_NAME / "annotations" / driver.ADJUDICATIONS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(driver.record_text(record))
    return path


JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=8),
    lambda children: (
        st.lists(children, max_size=3)
        | st.dictionaries(st.text(max_size=5), children, max_size=3)
    ),
    max_leaves=6,
)


# --- The date conventions ------------------------------------------------------

UPGRADE_WAVE = driver.DecisionWave("2026-10-13", excludes=True, affirms=False)
UPGRADE_WRITTEN = "2026-10-13"


def test_without_a_new_wave_the_date_conventions_are_release_20261013bs():
    """The release rules nothing, so with no upgrade wave the record's date
    conventions are release 20261013b's, byte for byte."""
    conventions = base_adjudication_record()["date_conventions"]
    assert driver.release_date_conventions(conventions) == conventions


def test_the_upgrade_wave_is_named_once_after_the_2026_10_10_wave(monkeypatch):
    spec = {**real_spec(), "upgrade_adjudications_written_on": UPGRADE_WRITTEN}
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
    conventions = base_adjudication_record()["date_conventions"]
    out = driver.release_date_conventions(conventions, UPGRADE_WAVE)
    day = UPGRADE_WAVE.day
    named = driver.DATE_CONVENTIONS_BASE.replace(
        " or 2026-10-10)", f", 2026-10-10 or {day})"
    )
    sentence = (
        f" The {day} wave's decisions exclude the outputs the {day} engine "
        "upgrade of the references moved onto an input the prompt does not "
        f"state, and were written on {UPGRADE_WRITTEN} UTC."
    )
    assert out == conventions.replace(driver.DATE_CONVENTIONS_BASE, named).replace(
        driver.DATE_CONVENTIONS_ANCHOR, driver.DATE_CONVENTIONS_ANCHOR + sentence
    )
    assert out.count(f"The {day} wave's decisions") == 1
    with pytest.raises(SystemExit, match="are not release 20261013b's"):
        driver.release_date_conventions(out, UPGRADE_WAVE)


def test_the_upgrade_wave_needs_its_written_day():
    spec = {
        k: v for k, v in real_spec().items() if k != "upgrade_adjudications_written_on"
    }
    with mock.patch.object(driver, "load_spec", lambda: spec):
        with pytest.raises(SystemExit, match="upgrade_adjudications_written_on"):
            driver.release_date_conventions(
                base_adjudication_record()["date_conventions"], UPGRADE_WAVE
            )


FILLER = st.text(alphabet="abc ().,0123456789-", max_size=20)


@settings(max_examples=150, deadline=None)
@given(
    parts=st.lists(FILLER, min_size=5, max_size=5),
    bases=st.integers(min_value=0, max_value=2),
    anchors=st.integers(min_value=0, max_value=2),
    wave=st.one_of(
        st.none(),
        st.builds(
            driver.DecisionWave,
            st.dates().map(lambda day: day.isoformat()),
            st.booleans(),
            st.just(True),
        ),
    ),
)
def test_release_date_conventions_requires_the_base_text_exactly_once(
    parts, bases, anchors, wave
):
    """For any text: it refuses unless the base wave list and the anchor each
    occur exactly once; then it changes nothing without a wave, and with one
    names it after 2026-10-10 and adds its sentence after the anchor."""
    a, b, c, d, e = parts
    base, anchor = driver.DATE_CONVENTIONS_BASE, driver.DATE_CONVENTIONS_ANCHOR
    text = a + (base + b) * bases + c + (anchor + d) * anchors + e
    assume(text.count(base) == bases and text.count(anchor) == anchors)
    spec = {**real_spec(), "upgrade_adjudications_written_on": UPGRADE_WRITTEN}
    with mock.patch.object(driver, "load_spec", lambda: spec):
        if (bases, anchors) != (1, 1):
            with pytest.raises(SystemExit, match="are not release 20261013b's"):
                driver.release_date_conventions(text, wave)
            return
        out = driver.release_date_conventions(text, wave)
    if wave is None:
        assert out == text
        return
    named = base.replace(" or 2026-10-10)", f", 2026-10-10 or {wave.day})")
    assert out.startswith(a + named + b + c + anchor + f" The {wave.day} wave's")
    assert out.endswith(d + e)


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
    """A one-case stage Gemini 4 Argon re-opened, with a recorded decision."""
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
        # The appended item must be the verdict 20261013b's entry names.
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
        CONVENTIONS + " Edited.",
        CONVENTIONS.replace(
            driver.DATE_CONVENTIONS_LAST_WAVE, ", 2026-10-10 or 2026-10-13)"
        ),
    ],
)
def test_triage_refuses_date_conventions_other_than_the_waves(
    triage_stage, conventions
):
    """Without an upgrade wave, the staged record's date conventions are the
    base's own text: neither an edit nor a wave the release does not add
    passes."""
    stage, record, run = triage_stage
    record.write_text(
        driver.record_text(
            {"date_conventions": conventions, "adjudications": [DECISION]}
        )
    )
    with pytest.raises(SystemExit, match="beyond naming this release's waves"):
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
    """48 rows as release 20261013b published them (1,935 scored outputs),
    including Fable 5's batch usage and Ox Alpha's $0."""
    rows = [
        _stat(f"incumbent-{i:02d}", 50.0 + i / 7, n=driver.BASE_SCORED, costUsd=1.25)
        for i in range(46)
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
    1,935 outputs and (MOCK) every incumbent's score moved, which the scope
    check must not mistake for drift; Fable's usage is gone, and the two
    additions are new."""
    stats = copy.deepcopy(incumbents)
    for row in stats:
        row.update(n=driver.RELEASE_SCORED, exact=row["exact"] + 0.25)
        row["score"] = row["exact"] / 100
    fable = stats[-1]
    fable.update(costUsd=0.0, costPerHousehold=0.0)
    del fable["totalTokens"], fable["latencySeconds"]
    return stats + [
        _stat(NEW, 65.0, costUsd=0.13),
        _stat(OTHER, 61.0, costUsd=0.11),
    ]


def _scoped(incumbents):
    """What release_20261006.export_payload returns with release 20261013b's
    record put back: every incumbent's published row, Fable's usage carried
    (it does that itself), and the two additions on 1,935 outputs."""
    return copy.deepcopy(incumbents) + [
        _stat(NEW, 65.5, n=driver.BASE_SCORED, costUsd=0.13),
        _stat(OTHER, 61.5, n=driver.BASE_SCORED, costUsd=0.11),
    ]


@pytest.fixture
def scope(monkeypatch):
    """export_full_run, release_20261006.export_payload and the dashboard
    schema replaced by fakes that hand back the given model stats and record
    what they were called with."""
    import policybench.dashboard_schema
    import policybench.full_run_export

    state = SimpleNamespace(
        stats=None, scoped=None, calls=[], gates=[], references=[], scope_gates=[]
    )

    def export_full_run(run_dir, **kwargs):
        state.calls.append(("export_full_run", Path(run_dir), kwargs))
        return {"countries": {"us": {"modelStats": copy.deepcopy(state.stats)}}}

    def export_payload(
        bundle, base, exclusions=None, *, require_failure_annotations=True
    ):
        state.calls.append(
            ("export_payload", Path(bundle), base, Path(exclusions).read_bytes())
        )
        state.scope_gates.append(require_failure_annotations)
        # The reference files the scope export reads, where the bundle has them.
        state.references.append(
            {
                name: (Path(bundle) / "us" / name).read_bytes()
                for name in driver.REFERENCE_FILES
                if (Path(bundle) / "us" / name).is_file()
            }
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

    def build(
        stats,
        scoped,
        live_stats,
        *,
        partial=False,
        early=False,
        bundle=None,
    ):
        state.stats, state.scoped = stats, scoped
        live = {"countries": {"us": {"modelStats": live_stats}}}
        return driver.build_payload(
            bundle or Path("bundle"),
            live,
            partial=partial,
            early=early,
        )

    state.build = build
    return state


def test_the_scope_check_allows_every_incumbent_change_the_base_record_explains(scope):
    """Every incumbent's score moves on the release's record, and its
    modelStats on release 20261013b's record are the published ones: the
    payload carries the release's rows, Fable 5's usage carried."""
    incumbents = _incumbents()
    stats = _exported(incumbents)
    payload = scope.build(stats, _scoped(incumbents), incumbents, bundle=Path("b"))
    rows = payload["countries"]["us"]["modelStats"]
    assert {row["n"] for row in rows} == {1935}
    fable = next(row for row in rows if row["model"] == "claude-fable-5")
    assert {key: fable[key] for key in FABLE_USAGE} == FABLE_USAGE
    assert fable["exact"] == incumbents[-1]["exact"] + 0.25
    (_, run_dir, kwargs), (_, bundle, live, record) = scope.calls
    assert run_dir == bundle == Path("b")
    assert kwargs == {"countries": ["us"], "skip_app_data": True}
    assert live == {"countries": {"us": {"modelStats": incumbents}}}
    # The scope export scores on release 20261013b's exclusion record, its
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
    target=st.integers(min_value=0, max_value=47),
    mutation=st.sampled_from(sorted(SCOPE_MUTATIONS)),
)
def test_the_scope_check_refuses_any_incumbent_change_on_the_base_record(
    scope, target, mutation
):
    """For every incumbent and every kind of change to its modelStats on
    release 20261013b's record, the build refuses and names it."""
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


def test_every_model_is_scored_on_1935_outputs(scope):
    incumbents = _incumbents()
    for index in (0, 47, 48, 49):
        stats = _exported(incumbents)
        stats[index]["n"] = 1920
        with pytest.raises(SystemExit, match="must be scored on 1935 outputs"):
            scope.build(stats, _scoped(incumbents), incumbents)
    assert [call[0] for call in scope.calls] == ["export_full_run"] * 4


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    counts=st.lists(
        st.sampled_from([1935, 1935, 1935, 1920, 1934, 1984, 0]),
        min_size=50,
        max_size=50,
    )
)
def test_the_scored_count_gate_passes_exactly_when_every_model_has_1935(scope, counts):
    incumbents = _incumbents()
    stats = _exported(incumbents)
    for row, n in zip(stats, counts):
        row["n"] = n
    if set(counts) == {1935}:
        scope.build(stats, _scoped(incumbents), incumbents)
    else:
        with pytest.raises(SystemExit, match="must be scored on 1935 outputs"):
            scope.build(stats, _scoped(incumbents), incumbents)


def test_a_partial_build_skips_the_release_gates(scope):
    stats = [_stat(f"incumbent-{i:02d}", 40.0, n=7) for i in range(48)]
    additions = [_stat(NEW, 45.0, n=7), _stat(OTHER, 44.0, n=7)]
    payload = scope.build(stats + additions, None, [], partial=True)
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
    """A stage export can run on: release 20261013b's references committed,
    the release's exclusion record staged, each addition's pinned run and an
    empty judge provenance record."""
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
    # Before the freeze: the pointer names release 20261013b, whatever the
    # working tree holds when the tests run.
    monkeypatch.setattr(driver, "live_pointer", lambda: {"tag": driver.BASE_TAG})

    def run(stats, live_stats, *, scoped=None, partial=False, early=False):
        scope.stats = stats
        scope.scoped = _scoped(live_stats) if scoped is None else scoped
        args = SimpleNamespace(stage_dir=stage, partial=partial, early=early)
        live = {"countries": {"us": {"modelStats": live_stats}}}
        return driver.export(args, bundle, live)

    return stage, bundle, run, scope.gates


# Each addition's synthetic run file: the header and its one row.
RUN_HEADER = (
    "model,scenario_id,variable,prediction,estimated_cost_usd,elapsed_seconds\n"
)
RUN_ROWS = {
    NEW: f"{NEW},scenario_000,snap,1200.0,0.0001,2.75\n",
    OTHER: f"{OTHER},scenario_000,snap,1100.0,0.0002,3.25\n",
}
PINNED = ("predictions.csv", "run_state.json")


@pytest.mark.parametrize(
    "route, reported",
    [
        ("openrouter/meta/muse-spark-1.3", "meta/muse-spark-1.3"),
        ("openrouter/thinkingmachines/inkling", "thinkingmachines/inkling"),
        ("claude-haiku-5-5", "claude-haiku-5-5"),
        ("gemini/gemini-4-argon", "gemini-4-argon"),
    ],
)
def test_the_resolved_model_is_the_id_the_provider_reports(route, reported):
    """Muse Spark 1.3's run reports "meta/muse-spark-1.3" on every row,
    OpenRouter's id (the registry route's last segment alone would refuse
    it); Gemini 4 Argon's reports the bare first-party id."""
    assert driver.resolved_model_id(route) == reported


def test_each_additions_route_resolves_to_what_its_run_reported():
    from policybench.config import MODELS

    assert driver.resolved_model_id(MODELS[NEW]) == "gemini-4-argon"
    assert driver.resolved_model_id(MODELS[OTHER]) == "meta/muse-spark-1.3"


def _write_run(stage, bundle) -> dict:
    """Each addition's run files as prepare stages them, the bundle's
    predictions holding an incumbent's row and theirs, and the prepare-time
    hashes in stage.json and model-provenance.json; returns the run files'
    pins."""
    provenance, staged = {}, []
    for slug, model in ADDITIONS.items():
        inputs = stage / "inputs" / slug
        inputs.mkdir(parents=True, exist_ok=True)
        (inputs / "predictions.csv").write_text(RUN_HEADER + RUN_ROWS[model])
        fingerprint = {"model_id": model}
        state = {"model": model, "treatment_fingerprint": fingerprint}
        (inputs / "run_state.json").write_text(json.dumps(state))
        provenance[model] = {
            "predictions_sha256": driver.digest(inputs / "predictions.csv"),
            "treatment_fingerprint": fingerprint,
        }
        staged += [inputs / name for name in PINNED]
    (bundle / "us/predictions.csv").write_text(
        RUN_HEADER
        + "incumbent,scenario_000,snap,900.0,0.002,3.5\n"
        + "".join(RUN_ROWS[model] for model in ADDITIONS.values())
    )
    names = [bundle / "us" / name for name in driver.REFERENCE_FILES]
    names += [bundle / "us/predictions.csv", *staged]
    files = {str(path.relative_to(stage)): driver.digest(path) for path in names}
    (stage / "stage.json").write_text(
        json.dumps({"partial": False, "early": False, "files": files})
    )
    (stage / "model-provenance.json").write_text(json.dumps(provenance))
    return {
        slug: {name: driver.digest(stage / "inputs" / slug / name) for name in PINNED}
        for slug in ADDITIONS
    }


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
    paths += [stage / "inputs" / slug / name for slug in ADDITIONS for name in PINNED]
    return paths + [bundle / "us" / name for name in driver.REFERENCE_FILES]


def test_strict_export_carries_fable_usage_and_binds_the_evidence(exporting):
    stage, bundle, run, gate_calls = exporting
    evidence = _evidence(stage, bundle)
    incumbents = _incumbents()
    stats = _exported(incumbents)
    payload = run(stats, incumbents)

    output = stage / "data-board50.json"
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
    assert receipt["models"] == 50 and receipt["partial"] is False
    assert receipt["base_sha256"] == driver.BASE_SHA256
    assert receipt["payload_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert receipt["files"] == {
        str(path.relative_to(stage)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in evidence
    }
    assert receipt["files"][BOUND_EXCLUSIONS] == release_sha()
    assert receipt["judge_provenance"] == {
        "path": "docs/argon/judge_provenance.json",
        "sha256": hashlib.sha256(driver.JUDGE_PROVENANCE.read_bytes()).hexdigest(),
    }


def test_export_accepts_only_the_release_exclusion_record(exporting, monkeypatch):
    """The release rules nothing, so the staged and committed records are both
    release 20261013b's; an edited copy of either is refused before a payload
    or receipt is written."""
    stage, bundle, run, _ = exporting
    _evidence(stage, bundle)
    incumbents = _incumbents()
    staged = bundle / "us" / EXCLUSIONS_NAME
    staged.write_text(release_text() + " ")
    with pytest.raises(SystemExit, match="staged reference reference_exclusions.json"):
        run(_exported(incumbents), incumbents)
    staged.write_text(release_text())
    (driver.SNAPSHOT / EXCLUSIONS_NAME).write_text(release_text() + " ")
    with pytest.raises(
        SystemExit, match="committed reference reference_exclusions.json"
    ):
        run(_exported(incumbents), incumbents)
    assert not (stage / "release-ready.json").exists()
    assert not (stage / "data-board50.json").exists()


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
    """Export checks Gemini 4 Argon's staged run files against the committed
    pins before it writes the payload or a receipt."""
    stage, bundle, run, _ = exporting
    _evidence(stage, bundle)
    pins = {SLUG: {"predictions.csv": "0" * 64, "run_state.json": "0" * 64}}
    monkeypatch.setattr(driver, "committed_input_pins", lambda: pins)
    incumbents = _incumbents()
    with pytest.raises(SystemExit, match=f"staged inputs/{SLUG}/.* is not the run"):
        run(_exported(incumbents), incumbents)
    assert not (stage / "release-ready.json").exists()
    assert not (stage / "data-board50.json").exists()


def test_export_writes_nothing_when_the_scope_check_refuses(exporting):
    stage, bundle, run, _ = exporting
    _evidence(stage, bundle)
    incumbents = _incumbents()
    scoped = _scoped(incumbents)
    scoped[7]["exact"] += 0.5
    with pytest.raises(SystemExit, match=r"drift: \['incumbent-07'\]"):
        run(_exported(incumbents), incumbents, scoped=scoped)
    assert not (stage / "release-ready.json").exists()
    assert not (stage / "data-board50.json").exists()
    assert not (bundle / "data.json").exists()


def test_partial_export_never_gets_a_release_receipt(exporting):
    stage, bundle, run, _ = exporting
    stats = [_stat(f"incumbent-{i:02d}", 40.0) for i in range(48)]
    run(stats + [_stat(NEW, 45.0), _stat(OTHER, 44.0)], [], partial=True, early=True)
    payload = stage / "PARTIAL-data-board50.json"
    assert "PARTIAL" in json.loads(payload.read_text())["stage2Status"]
    assert (bundle / "data.json").read_bytes() == payload.read_bytes()
    assert not (stage / "release-ready.json").exists()


def test_the_export_roster_must_be_the_incumbents_plus_the_additions(exporting):
    _, _, run, _ = exporting
    incumbents = _incumbents()
    for position, impostor in ((-1, "muse-spark-impostor"), (-2, "argon-impostor")):
        stats = _exported(incumbents)
        stats[position] = _stat(impostor, 65.0)
        with pytest.raises(SystemExit, match="roster"):
            run(stats, incumbents)
    with pytest.raises(SystemExit, match="48 incumbents"):
        run(_exported(incumbents), incumbents[:-1] + [_stat(NEW, 1.0)])
    # One addition alone is not the release's board.
    with pytest.raises(SystemExit, match="all 50 models"):
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
        "judge_template_version": meta.get("judge_template_version"),
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
    "judge_template_version": (ISOLATED, 1),
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
        "JUDGE_PROVENANCE_KEYS",
        "WITHHELD_ADDRESS",
        "JUDGE_MODEL",
    ):
        assert getattr(driver, name) == getattr(gpt61sol, name), name
    # This release's record also states each new verdict's judge template.
    assert driver.JUDGE_SIDECAR_FIELDS == (
        *gpt61sol.JUDGE_SIDECAR_FIELDS,
        "judge_template_version",
    )
    assert driver.JUDGE_PROVENANCE_ENTRY_KEYS == (
        gpt61sol.JUDGE_PROVENANCE_ENTRY_KEYS | {"judge_template_version"}
    )
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
    (stage / "data-board50.json").unlink()
    entry["isolated"] = False
    driver.JUDGE_PROVENANCE.write_text(json.dumps(_provenance_record([entry])))
    with pytest.raises(SystemExit, match="disagree with docs/argon"):
        run(_exported(incumbents), incumbents)
    assert not (stage / "release-ready.json").exists()
    assert not (stage / "data-board50.json").exists()


def test_the_committed_provenance_record_is_public_and_tallied():
    """Once committed: the record is json.dumps(indent=1), ASCII-escaped, with
    a trailing newline; it names no e-mail address, and its counts are the
    tally of its entries' groups."""
    if not driver.JUDGE_PROVENANCE.is_file():
        pytest.skip("docs/argon/judge_provenance.json is not written yet")
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
        pytest.skip("docs/argon/judge_provenance.json is not written yet")
    if not (WORKING_STAGE / "audit/cases").is_dir():
        pytest.skip("needs the Gemini 4 Argon working stage")
    driver.verify_judge_provenance(
        WORKING_STAGE / "audit/cases",
        driver.rejudged_cases(WORKING_STAGE),
        driver.JUDGE_PROVENANCE,
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
    source = (REPO / "scripts/finish_argon.py").read_text().splitlines()
    assert sum(driver.RELEASE_TAG in line for line in source) == 1
    for relative in (
        "scripts/freeze_argon.py",
        "docs/argon/design.md",
        "tests/test_finish_argon.py",
    ):
        path = REPO / relative
        if path.is_file():
            assert driver.RELEASE_TAG not in path.read_text(), relative
    assert real_spec()["release_tag"] == driver.RELEASE_TAG


def test_the_freeze_tests_do_not_spell_the_release_tag():
    """The same rule for tests/test_freeze_argon.py, kept apart so a
    failure names that file's lines."""
    path = REPO / "tests/test_freeze_argon.py"
    if not path.is_file():
        pytest.skip("tests/test_freeze_argon.py does not exist yet")
    lines = [
        number
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if driver.RELEASE_TAG in line
    ]
    assert lines == [], f"tests/test_freeze_argon.py spells the tag on {lines}"


def _provenance_case(root: Path, case_id: str, meta: dict) -> None:
    case = root / case_id
    case.mkdir(parents=True)
    (case / "prompt.md").write_text("prompt")
    (case / "verdict.json").write_text("{}")
    (case / "verdict.meta.json").write_text(json.dumps(meta))


def test_the_provenance_record_groups_each_verdict_by_its_declared_account(tmp_path):
    """Each entry copies its sidecar's fields (an address withheld), hashes its
    verdict and prompt, and takes its group from the declared account; the
    counts are the tally of the groups."""
    lane = "claude:max@axiom.org (subfleet lane claude-18)"
    token = next(k for k in driver.PROVENANCE_GROUPS if "setup-token" in k)
    for case_id, declared in (("us__a__x", token), ("us__b__y", lane)):
        _provenance_case(
            tmp_path,
            case_id,
            {
                "judge_account_declared": declared,
                "judge_effort": "xhigh",
                "judge_model_reported": ["claude-opus-5-5"],
                "judged_at_utc": "2026-10-09T11:00:00+00:00",
                "judge_isolation": {"cwd": "empty"},
            },
        )
    record = driver.judge_provenance_record(
        tmp_path, frozenset({"us__a__x", "us__b__y"})
    )
    assert set(record) == driver.JUDGE_PROVENANCE_KEYS
    assert record["counts"] == {
        "isolated: setup-token 2": 1,
        "isolated: subfleet lane claude-18": 1,
    }
    by_case = {entry["case_id"]: entry for entry in record["verdicts"]}
    assert set(by_case["us__a__x"]) == driver.JUDGE_PROVENANCE_ENTRY_KEYS
    assert by_case["us__b__y"]["judge_account_declared"] == (
        f"claude:{driver.WITHHELD_ADDRESS} (subfleet lane claude-18)"
    )
    assert by_case["us__a__x"]["prompt_sha256"] == hashlib.sha256(b"prompt").hexdigest()
    assert not driver.account_data(record, "record", keys=False)


@pytest.mark.parametrize(
    "meta",
    [
        {"judge_account_declared": "someone else", "judge_isolation": {}},
        {"judge_account_declared": ("claude:max@axiom.org (subfleet lane claude-18)")},
    ],
)
def test_the_provenance_record_refuses_an_unknown_account_or_an_unisolated_verdict(
    tmp_path, meta
):
    _provenance_case(tmp_path, "us__a__x", meta)
    with pytest.raises(SystemExit):
        driver.judge_provenance_record(tmp_path, frozenset({"us__a__x"}))


def test_the_provenance_record_of_the_live_stage_passes_the_export_gate():
    """Local: once every re-opened case has its verdict, the record built from
    the working stage's sidecars passes verify_judge_provenance (transcripts
    included), so export accepts it."""
    stage = WORKING_STAGE
    if not (stage / "prompt-changes.json").is_file():
        pytest.skip("no live stage")
    cases = stage / "audit" / "cases"
    rejudged = driver.rejudged_cases(stage)
    if not all((cases / case / "verdict.json").is_file() for case in rejudged):
        pytest.skip("the live stage is still being judged")
    record = driver.judge_provenance_record(cases, rejudged)
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "judge_provenance.json"
        path.write_text(json.dumps(record))
        driver.verify_judge_provenance(cases, rejudged, path)
