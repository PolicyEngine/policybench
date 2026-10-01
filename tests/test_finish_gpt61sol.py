"""The GPT-6.1 Sol addition cannot move an incumbent or a reference.

Adapted from test_finish_adds0928.py. Synthetic data stands in for runs,
audits and payloads; the committed snapshot is read only where a test pins it.
"""

from __future__ import annotations

import contextlib
import copy
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import finish_gpt61sol as driver  # noqa: E402

from policybench.audit import AUDIT_OUTPUT_SCHEMA  # noqa: E402

NEW = "gpt-6.1-sol"
SLUG = "gpt61sol"
COMMITTED_SEED_DIGEST_SHA256 = driver.SEED_DIGEST_SHA256
# Release 20260929's audit (the seed) and the grounding it was rendered with.
SEED = Path(
    "/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/results/local/"
    "adds0928-v3/audit"
)
GROUNDING = Path(
    "/Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit/"
    "grounding.csv"
)
# The supervised runs root holding GPT-6.1 Sol's finished run.
RUNS = Path("/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609")


def test_the_addition_is_gpt61sol_alone_on_a_46_model_board():
    assert driver.MODELS == {SLUG: NEW}
    assert driver.BASE_MODELS == 45 and driver.BOARD_MODELS == 46
    assert driver.BASE_OUTPUTS == 1984
    assert driver.BASE_EXCLUSIONS == 56 and driver.BASE_SCORED == 1928
    assert driver.BASE_TAG == "dashboard-data-20260929"
    assert driver.BASE_COMMIT == "d616e67c33b6f80dabf5cb7329f069f9a1de069d"
    assert set(driver.BASE_REFERENCE_SHA256) == set(driver.REFERENCE_FILES)
    assert not hasattr(driver, "reference_revision")
    assert not hasattr(driver, "replay_base_references")


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
    extra = runs / "gpt6sol/run"
    extra.mkdir(parents=True)
    (extra / "run_state.json").write_text(json.dumps({"model": "gpt-6-sol"}))
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


@pytest.mark.parametrize("model", ["gpt-6-sol", "gpt-6.1-luna", "", None])
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
    """Runs anywhere: the committed pins name GPT-6.1 Sol's two run files."""
    record = json.loads(driver.INPUT_PINS.read_text())
    assert set(record["inputs"]) == {SLUG}
    pins = record["inputs"][SLUG]["sha256"]
    assert set(pins) == {"predictions.csv", "run_state.json"}
    assert all(re.fullmatch("[0-9a-f]{64}", value) for value in pins.values())
    assert driver.INPUT_PINS.read_text() == (
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )


def test_the_committed_input_pins_are_the_finished_runs():
    """Local only: recomputed from the run directory, the pins are the same."""
    if not (RUNS / SLUG / "run").is_dir():
        pytest.skip("GPT-6.1 Sol's run directory is not on this machine")
    assert driver.input_pins_record(RUNS) == json.loads(driver.INPUT_PINS.read_text())


def test_the_stages_inputs_are_the_pinned_run():
    """Local only: the stage's copies are the pinned bytes, its prepare-time
    hashes hold, and its bundle rows are the run file's in every column."""
    stage = driver.ROOT / "results/local/gpt61sol-v1"
    if not (stage / "inputs" / SLUG).is_dir():
        pytest.skip("needs the GPT-6.1 Sol stage")
    pins = json.loads(driver.INPUT_PINS.read_text())["inputs"][SLUG]["sha256"]
    for name, pin in pins.items():
        assert driver.digest(stage / "inputs" / SLUG / name) == pin
    driver.verify_prepared_inputs(stage)
    assert driver.new_model_row_differences(stage) == []


def commit(root: Path, message: str) -> None:
    """Commit everything in a scratch repository, with no user hooks or keys."""
    git = ["git", "-C", str(root), "-c", "core.hooksPath=/dev/null"]
    git += ["-c", "commit.gpgsign=false", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-qm", message], check=True)


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
    monkeypatch.setattr(driver, "INPUT_PINS_PATH", "docs/gpt61sol/other_pins.json")
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
        driver.validate_keys(predictions, predictions, "gpt-6-sol")


# --- CLI -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "options, message",
    [
        (["--partial"], "--partial requires --early"),
        (["--early", "--step", "judge"], "--early only applies to prepare"),
        (["--early", "--step", "triage"], "--early only applies to prepare"),
        (["--early", "--step", "export"], "--early only applies to prepare"),
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


@pytest.mark.parametrize("field", ["partial", "early"])
def test_an_early_or_partial_stage_cannot_resume_into_release(workspace, field):
    stage = workspace / "results/local/stage"
    stage.mkdir(parents=True)
    receipt = {"partial": False, "early": False, "files": {}}
    receipt[field] = True
    (stage / "stage.json").write_text(json.dumps(receipt))
    with pytest.raises(SystemExit, match="cannot become a release"):
        driver.main(["--stage-dir", str(stage), "--step", "export"])


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


# --- Reference pins ------------------------------------------------------------


def test_the_committed_references_match_their_pins():
    driver.verify_reference_pins(driver.SNAPSHOT, "committed reference")
    for name, pin in driver.BASE_REFERENCE_SHA256.items():
        raw = (driver.SNAPSHOT / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == pin
    from policybench.reference_exclusions import (
        load_reference_exclusions,
        split_reference,
    )

    exclusions = load_reference_exclusions(driver.SNAPSHOT)
    assert len(exclusions) == driver.BASE_EXCLUSIONS
    reasons = [e["reason_code"] for e in exclusions]
    assert reasons.count("reference_engine_defect") == 28
    assert reasons.count("reference_depends_on_unlisted_input") == 28
    reference = pd.read_csv(driver.SNAPSHOT / "reference_outputs.csv")
    assert len(reference) == driver.BASE_OUTPUTS
    assert reference.scenario_id.nunique() == 100
    assert len(split_reference(reference, exclusions)[0]) == driver.BASE_SCORED


def test_the_committed_adjudications_exclude_exactly_the_scoring_exclusions():
    """Triage requires this of the staged copy, which prepare takes from here."""
    from policybench.adjudications import excluded_case_keys, load_adjudications
    from policybench.reference_exclusions import (
        exclusion_keys,
        load_reference_exclusions,
    )

    decisions = load_adjudications(driver.ANNOTATIONS / "us_adjudications.json")
    assert excluded_case_keys(decisions) == exclusion_keys(
        load_reference_exclusions(driver.SNAPSHOT)
    )
    # Excluded on review of release 20260929, apart from any engine change.
    assert ("scenario_023", "head_medicaid_eligible") in excluded_case_keys(decisions)


@pytest.fixture
def pinned_copy(tmp_path):
    """A copy of the five committed reference files."""
    directory = tmp_path / "references"
    directory.mkdir()
    for name in driver.REFERENCE_FILES:
        shutil.copyfile(driver.SNAPSHOT / name, directory / name)
    return directory


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


def test_resolve_base_checks_the_committed_pins_before_anything_else(
    pinned_copy, monkeypatch
):
    (pinned_copy / "reference_exclusions.json").write_text('{"exclusions": []}\n')
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


def test_the_base_commit_holds_release_20260929():
    pointer = json.loads(driver.base_commit_blob(Path("app/src/data.artifact.json")))
    assert pointer["tag"] == driver.BASE_TAG
    assert pointer["sha256"] == driver.BASE_SHA256
    for name, pin in driver.BASE_REFERENCE_SHA256.items():
        raw = driver.base_commit_blob(driver.SNAPSHOT.relative_to(driver.ROOT) / name)
        assert hashlib.sha256(raw).hexdigest() == pin


def test_the_base_predictions_pin_is_the_release_commits_not_the_working_trees(
    tmp_path, monkeypatch
):
    """A working tree whose predictions and manifest pin are both replaced.

    The pin comes from the manifest at BASE_COMMIT, so editing the working
    tree's manifest to match substituted predictions does not pass.
    """
    real_root = driver.ROOT
    committed = Path("paper/snapshot/20260501/manifest.json")
    snapshot = tmp_path / "paper/snapshot/20260501/runs" / driver.RUN_NAME
    snapshot.mkdir(parents=True)
    substitute = snapshot / "predictions.csv.gz"
    with gzip.open(substitute, "wt") as stream:
        stream.write("model,scenario_id,variable,prediction\n")
    manifest = json.loads((real_root / committed).read_text())
    files = manifest["source_run_artifacts"][driver.RUN_NAME]["files"]
    files["predictions.csv.gz"] = driver.digest(substitute)
    (tmp_path / committed).write_text(json.dumps(manifest))

    def blob(path):
        return subprocess.run(
            ["git", "-C", str(real_root), "show", f"{driver.BASE_COMMIT}:{path}"],
            capture_output=True,
            check=True,
        ).stdout

    monkeypatch.setattr(driver, "ROOT", tmp_path)
    monkeypatch.setattr(driver, "base_commit_blob", blob)
    with pytest.raises(SystemExit, match="fail release 20260929's manifest hash"):
        driver.verify_base_predictions(snapshot)


def test_release_20260929s_manifest_pins_its_predictions():
    manifest = json.loads(
        driver.base_commit_blob(Path("paper/snapshot/20260501/manifest.json"))
    )
    pin = manifest["source_run_artifacts"][driver.RUN_NAME]["files"]
    raw = driver.base_commit_blob(
        driver.SNAPSHOT.relative_to(driver.ROOT) / "predictions.csv.gz"
    )
    assert hashlib.sha256(raw).hexdigest() == pin["predictions.csv.gz"]


def test_base_commit_blob_names_the_missing_history():
    with pytest.raises(SystemExit, match="cannot read .* at base commit d616e67c33b6"):
        driver.base_commit_blob(Path("no/such/file.csv"))


def test_base_commit_blob_names_a_missing_commit(monkeypatch):
    monkeypatch.setattr(driver, "BASE_COMMIT", "0" * 40)
    with pytest.raises(SystemExit, match="at base commit 000000000000.*unshallow"):
        driver.base_commit_blob(Path("app/src/data.artifact.json"))


def test_a_re_export_after_the_freeze_reads_20260929_from_git(monkeypatch):
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


def test_the_git_base_must_rewrap_to_the_20260929_asset(monkeypatch):
    raw = _gz_payload(45)
    monkeypatch.setattr(driver, "base_commit_blob", lambda path: raw)
    monkeypatch.setattr(driver, "live_pointer", lambda: {"tag": driver.RELEASE_TAG})
    with pytest.raises(SystemExit, match="base payload SHA256 mismatch"):
        driver.resolve_live_base(SimpleNamespace())
    wrapped = json.dumps({"countries": {"us": json.loads(gzip.decompress(raw))}})
    monkeypatch.setattr(
        driver, "BASE_SHA256", hashlib.sha256(wrapped.encode()).hexdigest()
    )
    assert (
        len(
            driver.resolve_live_base(SimpleNamespace())["countries"]["us"]["modelStats"]
        )
        == 45
    )
    short = _gz_payload(44)
    monkeypatch.setattr(driver, "base_commit_blob", lambda path: short)
    wrapped = json.dumps({"countries": {"us": json.loads(gzip.decompress(short))}})
    monkeypatch.setattr(
        driver, "BASE_SHA256", hashlib.sha256(wrapped.encode()).hexdigest()
    )
    with pytest.raises(SystemExit, match="base must have 45 models"):
        driver.resolve_live_base(SimpleNamespace())


@pytest.mark.parametrize("tag", ["dashboard-data-20260922c", "dashboard-data-20991231"])
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
        "judged_at_utc": "2026-09-30T01:00:00+00:00",
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
            meta["judge_model_reported"] = ["claude-opus-4-6"]
        elif defect == "no_timestamp":
            del meta["judged_at_utc"]
        elif defect == "no_prompt_sha256":
            del meta["prompt_sha256"]
        elif defect == "other_prompt":
            meta["prompt_sha256"] = hashlib.sha256(b"another prompt").hexdigest()
        else:
            meta = [meta]
        path.write_text(json.dumps(meta))
    assert driver.validate_verdicts(root) == [case.name]


def test_every_verdict_is_bound_to_its_own_bytes(tmp_path):
    """An incumbent verdict's sidecar must match its bytes too, not only a
    verdict that names GPT-6.1 Sol."""
    root = tmp_path / "audit"
    case = _audit(root, ["incumbent"])
    write_verdict(
        case,
        _verdict(["incumbent"]),
        judge_model_requested="default",
        judge_model_reported=["gpt-5.6-sol"],
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
        judge_model_reported=["gpt-5.6-sol"],
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


def test_the_judge_must_cover_all_46_models_in_a_case(tmp_path):
    incumbents = [f"incumbent-{i:02d}" for i in range(45)]
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
        judge_model_reported=["gpt-5.6-sol"],
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


def _seed_of(root):
    return driver.seed_digest(root)


def test_unchanged_incumbent_case_keeps_its_existing_judge(tmp_path):
    """A seed verdict whose sidecar never recorded its prompt (453 of the
    20260929 audit's 674) carries over through the seed binding."""
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
    seed = _seed_of(root)
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
    seed = _seed_of(root)
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
    """A judged 2-model seed audit and a stage whose board adds the new model."""
    from policybench.audit import prepare_audit

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
            judge_model_reported=["gpt-5.6-sol"],
            prompt_sha256=None,
        )
    digest_text = driver.seed_digest_text(driver.seed_digest(seed))
    monkeypatch.setattr(
        driver, "SEED_DIGEST_SHA256", hashlib.sha256(digest_text.encode()).hexdigest()
    )
    stage = tmp_path / "stage"

    def prepare(new_rows, *, grounding_path=grounding):
        bundle = _board(stage / "publish" / driver.RUN_NAME, INCUMBENT_ROWS + new_rows)
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


# GPT-6.1 Sol misses s0 alone: s0 is re-opened, s1 carries over.
JOINS_S0 = [
    (NEW, "s0", 99.0, "Guessed."),
    (NEW, "s1", 300.0, "Right."),
    (NEW, "s2", 100.0, "Right."),
]


def test_an_edited_carried_over_verdict_is_refused_after_prepare(seeded_stage):
    """The mutation the review asked for: edit a kept incumbent verdict in a
    prepared stage (sidecar re-hashed to match) and validation refuses it."""
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
        judge_model_reported=["gpt-5.6-sol"],
    )
    with pytest.raises(SystemExit, match="carried-over verdicts differ.*us__s1__snap"):
        driver.validate_verdicts(audit, seed=seed)


def test_prepare_refuses_a_seed_the_committed_digest_does_not_record(
    seeded_stage, monkeypatch
):
    _, stage, prepare = seeded_stage
    monkeypatch.setattr(driver, "SEED_DIGEST_SHA256", COMMITTED_SEED_DIGEST_SHA256)
    with pytest.raises(SystemExit, match="not release 20260929's"):
        prepare(JOINS_S0)
    assert not (stage / "audit").exists()


def test_load_seed_refuses_a_stage_without_a_binding_or_with_another(seeded_stage):
    _, stage, prepare = seeded_stage
    prepare(JOINS_S0)
    receipt = json.loads((stage / "stage.json").read_text())
    edited = copy.deepcopy(receipt)
    edited["seed"]["us__s1__snap"]["verdict_sha256"] = "0" * 64
    (stage / "stage.json").write_text(json.dumps(edited))
    with pytest.raises(SystemExit, match="not release 20260929's"):
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
    one, is refused (the review's bypass of the adjudication gate)."""
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
    """The review's bypass of finding 2: a kept case whose prompt is edited
    (with or without a re-bound verdict) is refused, not re-judged."""
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
    """The review's finding 4: GPT-6.1 Sol answers s1 right and s0 wrong.
    Listing it as wrong on s1 (prompt edited, case moved to changed), or
    dropping it from s0 (seed prompt restored, case moved to kept), leaves
    the re-derived lists agreeing, so only the predictions can refuse it."""
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
    rows = [
        (NEW, "s0", 99.0, "Guessed."),
        (NEW, "s1", 300.0, "Right."),
        (NEW, "s2", 100.0, "Right."),
    ]
    with pytest.raises(SystemExit, match=r"incumbent-only case prompts changed.*s1"):
        prepare(rows, grounding_path=other)


def test_prepare_refuses_a_grounding_other_than_the_pinned_one(seeded_stage, tmp_path):
    _, stage, prepare = seeded_stage
    other = tmp_path / "other-grounding.csv"
    other.write_text("scenario_id,variable,grounding\n")
    with pytest.raises(SystemExit, match="grounding differs"):
        prepare([], grounding_path=other)
    assert not (stage / "audit").exists()


def test_the_pinned_grounding_is_the_one_the_20260929_stage_used():
    if not GROUNDING.is_file():
        pytest.skip("the main clone's audit grounding is not on this machine")
    assert driver.digest(GROUNDING) == driver.GROUNDING_SHA256


def _committed_seed_digest() -> dict[str, dict[str, str]]:
    lines = driver.SEED_DIGEST.read_text().splitlines()
    assert lines[0] == "case_id,prompt_sha256,verdict_sha256"
    rows = [line.split(",") for line in lines[1:]]
    return {
        case: {"prompt_sha256": prompt, "verdict_sha256": verdict}
        for case, prompt, verdict in rows
    }


def test_the_committed_seed_digest_is_the_pinned_one():
    """Runs anywhere: the committed digest hashes to the pin, spells each of
    the 20260929 audit's 674 judged cases once, and records the prompt the
    design note gives for scenario_023 Medicaid."""
    raw = driver.SEED_DIGEST.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == driver.SEED_DIGEST_SHA256
    seed = _committed_seed_digest()
    assert driver.seed_digest_text(seed).encode() == raw
    assert len(seed) == 674
    hexes = [value for item in seed.values() for value in item.values()]
    assert all(len(h) == 64 and set(h) <= set("0123456789abcdef") for h in hexes)
    medicaid = seed["us__scenario_023__head_medicaid_eligible"]
    assert medicaid["prompt_sha256"].startswith("339d113a")


def test_every_committed_adjudication_decides_a_case_the_seed_judged():
    """Runs anywhere: a recorded decision rules on a judge verdict, so its case
    is one of the seed's judged cases."""
    from policybench.adjudications import load_adjudications

    seed = _committed_seed_digest()
    decisions = load_adjudications(driver.ANNOTATIONS / "us_adjudications.json")
    assert {driver.case_id(entry) for entry in decisions} <= set(seed)


def test_the_committed_seed_digest_matches_the_real_seed():
    """Local only: the digest equals the 20260929 audit on this machine."""
    if not SEED.is_dir():
        pytest.skip("release 20260929's audit is not on this machine")
    assert driver.seed_digest_text(driver.seed_digest(SEED)) == (
        driver.SEED_DIGEST.read_text()
    )


def test_the_committed_adjudications_keep_the_seed_judge_verdicts():
    """Every recorded decision keeps its seed verdict's class, 023 Medicaid too.

    Triage and the freeze re-check this against the staged audit, where a
    carried-over verdict is the seed's.
    """
    if not SEED.is_dir():
        pytest.skip("release 20260929's audit is not on this machine")
    from freeze_snapshot import verify_adjudications_keep_judge_verdicts

    from policybench.adjudications import load_adjudications

    decisions = load_adjudications(driver.ANNOTATIONS / "us_adjudications.json")
    verify_adjudications_keep_judge_verdicts(decisions, SEED / "cases")
    case = SEED / "cases/us__scenario_023__head_medicaid_eligible"
    meta = json.loads((case / "verdict.meta.json").read_text())
    assert meta["prompt_sha256"] == driver.digest(case / "prompt.md")


def test_each_20260929_entry_names_its_seed_verdict_as_its_sidecar_records_it():
    """verify_restatements requires a restatement's appended item to be the
    verdict release 20260929's entry names. That is the item the restate
    script builds from the seed verdict and its sha256-bound sidecar, for
    every entry: judge, classes, flag, flag source and UTC day."""
    if not SEED.is_dir():
        pytest.skip("release 20260929's audit is not on this machine")
    from date_adds0928_judge_verdicts import WAVE_FLAGS, _bound_verdict
    from restate_gpt61sol_adjudications import named_item, replaced_item

    waved = frozenset(json.loads(WAVE_FLAGS.read_text()))
    base = driver.base_adjudications()
    assert len(base) == 69
    for entry in base:
        found = _bound_verdict(SEED / "cases" / driver.case_id(entry))
        assert found is not None, driver.case_id(entry)
        key = f"{entry['scenario_id']}:{entry['variable']}"
        assert named_item(entry) == replaced_item(found, key in waved), entry


@pytest.mark.slow
def test_every_seed_prompt_rerenders_from_the_committed_snapshot(tmp_path):
    """The committed 45-model board renders exactly the seed's cases and prompts.

    So check_prompt_changes may attribute every changed or new prompt in a
    stage to GPT-6.1 Sol joining its case. #182's review excluded
    scenario_023 head_medicaid_eligible and rewrote its adjudication and case
    note; neither enters a prompt, and its prompt is unchanged.
    """
    if not (SEED.is_dir() and GROUNDING.is_file()):
        pytest.skip("release 20260929's audit or grounding is not on this machine")
    from policybench.audit import prepare_audit

    bundle = tmp_path / "publish" / driver.RUN_NAME
    (bundle / "us").mkdir(parents=True)
    for name in (*driver.REFERENCE_FILES, "predictions.csv.gz"):
        shutil.copyfile(driver.SNAPSHOT / name, bundle / "us" / name)
    (bundle / "annotations").mkdir()
    for name in driver.ANNOTATION_FILES:
        shutil.copyfile(driver.ANNOTATIONS / name, bundle / "annotations" / name)
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
    assert (audit / "cases.jsonl").read_bytes() == (SEED / "cases.jsonl").read_bytes()
    rendered = driver.seed_prompt_digests(audit)
    assert rendered == driver.seed_prompt_digests(SEED) and len(rendered) == 674
    case = "us__scenario_023__head_medicaid_eligible"
    meta = json.loads((SEED / "cases" / case / "verdict.meta.json").read_text())
    assert rendered[case] == meta["prompt_sha256"]


def test_check_prompt_changes_names_new_incumbent_only_cases(tmp_path):
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


# --- Triage --------------------------------------------------------------------


@pytest.mark.parametrize(
    "suspect, failure_source, report",
    [
        (True, "llm_error", "reference-flags.csv"),
        (False, "reference_engine_defect", "unresolved-rows.csv"),
        (False, "prompt_ambiguity", "unresolved-rows.csv"),
    ],
)
def test_triage_stops_and_records_flags_for_evidence_review(
    tmp_path, monkeypatch, suspect, failure_source, report
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
    monkeypatch.setattr(
        driver, "base_adjudication_record", lambda: {"adjudications": []}
    )
    (stage / driver.PROMPT_CHANGES).write_text(
        json.dumps({"added": [], "changed": [], "kept": []})
    )
    (bundle / "annotations" / driver.ADJUDICATIONS).write_text(
        driver.record_text({"adjudications": []})
    )
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
    "judged_on_utc": "2026-09-29",
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
def triage_stage(tmp_path, monkeypatch):
    """A one-case stage GPT-6.1 Sol re-opened, with a recorded decision."""
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
    record.write_text(
        json.dumps({"adjudications": [DECISION]}, indent=2, ensure_ascii=False) + "\n"
    )
    monkeypatch.setattr(driver, "validate_verdicts", lambda *a, **kw: [])
    monkeypatch.setattr(driver, "load_seed", lambda stage: {})
    monkeypatch.setattr(
        driver, "base_adjudication_record", lambda: {"adjudications": [DECISION]}
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
    "judged_on": "2026-09-29",
}
RESTATED = {
    **DECISION,
    "judged_on_utc": "2026-09-30",
    "judge_rejudged_on": "2026-09-30",
    "judge_previous": [SEED_ITEM],
}


def _record(*entries):
    return driver.record_text({"adjudications": list(entries)})


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
        # The appended item must be the verdict 20260929's entry names.
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


def _item(field, old, new, **extra):
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
        _item("reasoning", "one model's row", "two models' rows"),
        _item("case_annotation", "the 2025 threshold", "the 2025 threshold, held"),
        _item("annotation", "2025 threshold", "held 2025 threshold", model=NEW),
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
        _item("case_annotation", "no such text", "x"),
        _item("annotation", "2025 threshold", "x", model="not-a-model"),
        # The adjudication sentence comes from the record; only a reasoning
        # amendment may change it.
        _item("case_annotation", "The allotment follows the rule.", "It does."),
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


# --- Export and the no-drift gate ---------------------------------------------

FABLE_USAGE = {
    "costUsd": 54.109099999999955,
    "costPerHousehold": 0.5410909999999995,
    "totalTokens": 3850174,
    "latencySeconds": 97.6780539804895,
}


def _stat(model, exact, **usage):
    return {
        "model": model,
        "condition": "no_tools",
        "score": exact / 100,
        "exact": exact,
        "n": 1928,
        **usage,
    }


def _incumbents():
    """45 released rows, including Fable 5's batch usage and Ox Alpha's $0."""
    rows = [_stat(f"incumbent-{i:02d}", 50.0 + i / 7, costUsd=1.25) for i in range(43)]
    rows.append(_stat("ox-alpha", 70.0, costUsd=0.0, costPerHousehold=0.0))
    rows.append(_stat("claude-fable-5", 60.0, costUsd=0.0, costPerHousehold=0.0))
    rows[-1].update(FABLE_USAGE)
    return rows


def _exported(incumbents):
    """What export_full_run returns: Fable's usage is gone, the addition is new."""
    stats = copy.deepcopy(incumbents)
    fable = stats[-1]
    fable.update(costUsd=0.0, costPerHousehold=0.0)
    del fable["totalTokens"], fable["latencySeconds"]
    return stats + [_stat(NEW, 65.0, costUsd=2.0)]


@pytest.fixture
def exporting(tmp_path, monkeypatch):
    import policybench.dashboard_schema
    import policybench.full_run_export

    stage = tmp_path / "stage"
    bundle = stage / "publish" / driver.RUN_NAME
    for name in driver.REFERENCE_FILES:
        (bundle / "us").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(driver.SNAPSHOT / name, bundle / "us" / name)
    exported = {}
    gate_calls = []

    def validate(payload, *, require_failure_annotations):
        gate_calls.append(require_failure_annotations)
        return []

    monkeypatch.setattr(
        policybench.full_run_export,
        "export_full_run",
        lambda *a, **kw: {"countries": {"us": {"modelStats": exported["stats"]}}},
    )
    monkeypatch.setattr(
        policybench.dashboard_schema, "validate_dashboard_payload", validate
    )
    # No case is re-opened here, so the judge provenance record lists none.
    record = tmp_path / "judge_provenance.json"
    record.write_text(json.dumps(_provenance_record([])))
    monkeypatch.setattr(driver, "JUDGE_PROVENANCE", record)
    monkeypatch.setattr(driver, "rejudged_cases", lambda stage: frozenset())
    # GPT-6.1 Sol's staged run, its pins standing in for the committed ones.
    pins = _write_run(stage, bundle)
    monkeypatch.setattr(driver, "committed_input_pins", lambda: pins, raising=False)

    def run(stats, live_stats, *, partial=False, early=False):
        exported["stats"] = stats
        args = SimpleNamespace(stage_dir=stage, partial=partial, early=early)
        live = {"countries": {"us": {"modelStats": live_stats}}}
        return driver.export(args, bundle, live)

    return stage, bundle, run, gate_calls


# GPT-6.1 Sol's synthetic run file, and an incumbent row beside its row.
SOL_RUN = (
    "model,scenario_id,variable,prediction,estimated_cost_usd,elapsed_seconds\n"
    f"{NEW},scenario_000,snap,1200.0,0.0125,12.75\n"
)
PINNED = ("predictions.csv", "run_state.json")


def _write_run(stage, bundle) -> dict:
    """GPT-6.1 Sol's run files as prepare stages them, the bundle's
    predictions holding its row, and the prepare-time hashes in stage.json
    and model-provenance.json; returns the run files' pins."""
    inputs = stage / "inputs" / SLUG
    inputs.mkdir(parents=True, exist_ok=True)
    (inputs / "predictions.csv").write_text(SOL_RUN)
    fingerprint = {"model_id": NEW}
    state = {"model": NEW, "treatment_fingerprint": fingerprint}
    (inputs / "run_state.json").write_text(json.dumps(state))
    header, row = SOL_RUN.splitlines(keepends=True)
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

    output = stage / "data-board46.json"
    assert (
        output.read_bytes()
        == json.dumps({"countries": {"us": payload["countries"]["us"]}}).encode()
    )
    assert (bundle / "data.json").read_bytes() == output.read_bytes()
    fable = next(s for s in stats if s["model"] == "claude-fable-5")
    assert json.dumps(fable) == json.dumps(incumbents[-1])
    assert gate_calls == [True]
    receipt = json.loads((stage / "release-ready.json").read_text())
    assert receipt["release_tag"] == driver.RELEASE_TAG
    assert receipt["models"] == 46 and receipt["partial"] is False
    assert receipt["base_sha256"] == driver.BASE_SHA256
    assert receipt["payload_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert receipt["files"] == {
        str(path.relative_to(stage)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in evidence
    }
    assert receipt["judge_provenance"] == {
        "path": "docs/gpt61sol/judge_provenance.json",
        "sha256": hashlib.sha256(driver.JUDGE_PROVENANCE.read_bytes()).hexdigest(),
    }


def test_the_freeze_rebuilds_exactly_what_export_wrote(exporting, monkeypatch):
    """Export and the freeze's rebuild share build_payload. Rebuilt from a
    scratch copy of the bundle files the receipt binds, an exported stage's
    payload comes back byte for byte, Fable 5's usage carried again, and the
    stage is left as export left it; a score edited after export is refused."""
    import freeze_gpt61sol as release

    import policybench.full_run_export

    stage, bundle, run, _ = exporting
    _evidence(stage, bundle)
    incumbents = _incumbents()
    stats = _exported(incumbents)

    def export_full_run(run_dir, **kwargs):
        (Path(run_dir) / "data.json").write_text("Fable 5's usage is not carried.\n")
        return {"countries": {"us": {"modelStats": copy.deepcopy(stats)}}}

    monkeypatch.setattr(policybench.full_run_export, "export_full_run", export_full_run)
    run(stats, incumbents)
    receipt = json.loads((stage / "release-ready.json").read_text())
    payload = stage / "data-board46.json"
    live = {"countries": {"us": {"modelStats": incumbents}}}
    exported = {path: path.read_bytes() for path in stage.rglob("*") if path.is_file()}
    release.rebuild_payload(stage, receipt, payload, live)
    assert {
        path: path.read_bytes() for path in stage.rglob("*") if path.is_file()
    } == exported
    board = json.loads(payload.read_text())
    board["countries"]["us"]["modelStats"][-1]["exact"] = 100.0
    payload.write_text(json.dumps(board))
    with pytest.raises(SystemExit, match=r"export builds.*\[45 gpt-6\.1-sol\]\.exact"):
        release.rebuild_payload(stage, receipt, payload, live)


def test_export_writes_no_receipt_when_the_inputs_are_not_the_pinned_run(
    exporting, monkeypatch
):
    """Export checks GPT-6.1 Sol's staged run files against the committed pins
    before it writes the payload or a receipt."""
    stage, bundle, run, _ = exporting
    _evidence(stage, bundle)
    pins = {SLUG: {"predictions.csv": "0" * 64, "run_state.json": "0" * 64}}
    monkeypatch.setattr(driver, "committed_input_pins", lambda: pins, raising=False)
    incumbents = _incumbents()
    with pytest.raises(SystemExit, match=f"staged inputs/{SLUG}/.* is not the run"):
        run(_exported(incumbents), incumbents)
    assert not (stage / "release-ready.json").exists()
    assert not (stage / "data-board46.json").exists()


def test_partial_export_never_gets_a_release_receipt(exporting):
    stage, bundle, run, _ = exporting
    stats = [_stat(f"incumbent-{i:02d}", 40.0) for i in range(45)]
    run(stats + [_stat(NEW, 45.0)], [], partial=True, early=True)
    payload = stage / "PARTIAL-data-board46.json"
    assert "PARTIAL" in json.loads(payload.read_text())["stage2Status"]
    assert (bundle / "data.json").read_bytes() == payload.read_bytes()
    assert not (stage / "release-ready.json").exists()


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
    """An isolated judge's transcript, shaped like the stage's real ones: its
    one accepted StructuredOutput call answers the verdict the provenance
    fixture writes."""
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
    "judge_account_declared": "claude:lane@example.org (lane 7)",
}


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


WITHHELD = "<account withheld>"
GROUPS = {ISOLATED: "isolated: lane 7", UNHARDENED: "unhardened: in-repo runner"}


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
    "judged_at_utc": (ISOLATED, "2026-09-30T08:00:00+00:00"),
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
            "claude:lane@example.org (lane 7)"
        )

    with pytest.raises(SystemExit, match=r"is public and names .*e-mail address"):
        verify(declared)

    def in_note(record):
        record["note"] += " Lane 7 is lane@example.org."

    with pytest.raises(SystemExit, match=r"is public and names .*record\.note"):
        verify(edit_record=in_note)

    def in_group(entries):
        for entry in entries:
            entry["group"] = entry["group"].replace("lane 7", "lane7@example.org")

    with pytest.raises(SystemExit, match="is public and names"):
        verify(in_group)


# The fixture record's true counts: one entry in each group.
GROUP_COUNTS = {group: 1 for group in GROUPS.values()}


@pytest.mark.parametrize(
    "counts", [{}, {"isolated: lane 7": 2}, {**GROUP_COUNTS, "extra": 0}]
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
    # Only the event types the stage's isolated transcripts carry.
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
    """As in the stage's us__scenario_031__head_medicaid_eligible transcript."""
    cases, verify = provenance
    events = _clean_transcript()
    events[7:7] = [_call("StructuredOutput", "call-0"), _result("call-0", error=True)]
    _write_transcript(cases / ISOLATED, events)
    verify()


def test_claude_codes_own_structured_output_nudge_passes(provenance):
    """As in the stage's us__scenario_014__state_income_tax_before_refundable_
    credits transcript: the judge answered in text, Claude Code nudged it (an
    isMeta user message) and it called StructuredOutput."""
    cases, verify = provenance
    events = _clean_transcript()
    events.insert(7, _user(driver.JUDGE_PROMPT_NUDGE, isMeta=True))
    _write_transcript(cases / ISOLATED, events)
    verify()


def test_an_address_in_the_prompt_or_the_judges_own_words_passes(provenance):
    """The account-data rule reads neither the judged prompt's own text nor
    the judge's turns: a prompt that quotes an e-mail address, and a judge
    that repeats it, carry no account context."""
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


STAGE = driver.ROOT / "results/local/gpt61sol-v1"


@pytest.mark.skipif(
    not (STAGE / "audit/cases").is_dir(), reason="needs the GPT-6.1 Sol stage"
)
def test_every_isolated_transcript_in_the_stage_passes_the_gate():
    """(local) All 60 isolated verdicts the record names pass the transcript
    checks, the answer, event-type and account-data rules included."""
    record = json.loads(driver.JUDGE_PROVENANCE.read_text())["verdicts"]
    isolated = [entry["case_id"] for entry in record if entry["isolated"]]
    failing = {}
    for name in isolated:
        case = STAGE / "audit/cases" / name
        meta = json.loads((case / "verdict.meta.json").read_text())
        problems = driver.transcript_problems(
            case / "claude.transcript.jsonl",
            meta.get("judge_effort"),
            (case / "prompt.md").read_bytes(),
            json.loads((case / "verdict.json").read_text()),
        )
        if problems:
            failing[name] = problems
    assert len(isolated) == 60 and failing == {}


def test_the_committed_provenance_record_is_public_and_tallied():
    """Runs anywhere: the record is json.dumps(indent=1), ASCII-escaped, with a
    trailing newline; it names no e-mail address, and its counts are the
    tally of its entries' groups."""
    text = driver.JUDGE_PROVENANCE.read_text()
    record = json.loads(text)
    assert text == json.dumps(record, indent=1) + "\n" and text.isascii()
    assert not driver.EMAIL_ADDRESS.search(text)
    groups = [entry["group"] for entry in record["verdicts"]]
    assert record["counts"] == {group: groups.count(group) for group in groups}


@pytest.mark.skipif(
    not (STAGE / "audit/cases").is_dir(), reason="needs the GPT-6.1 Sol stage"
)
def test_the_record_and_its_isolation_note_are_the_sidecars():
    """(local) The committed record passes the gate against the stage. Of its
    60 isolated verdicts, the 43 whose sidecars record an allowlisted
    environment and no user settings are exactly those outside the 17
    "subfleet lane claude-10" verdicts, which record neither and were judged
    on the first hardened runner: after 33493f80 (09:02:46Z) and before
    51b3e722 (11:13:07Z) added both."""
    driver.verify_judge_provenance(
        STAGE / "audit/cases", driver.rejudged_cases(STAGE), driver.JUDGE_PROVENANCE
    )
    record = json.loads(driver.JUDGE_PROVENANCE.read_text())
    isolated = [entry for entry in record["verdicts"] if entry["isolated"]]
    hardened, first = [], []
    for entry in isolated:
        case = STAGE / "audit/cases" / entry["case_id"]
        meta = json.loads((case / "verdict.meta.json").read_text())
        isolation = meta["judge_isolation"]
        if isolation.get("environment") == "allowlisted" and "settings" in isolation:
            hardened.append(entry)
        else:
            assert "environment" not in isolation and "settings" not in isolation
            first.append(entry)
    assert len(isolated) == 60 and len(hardened) == 43 and len(first) == 17
    assert {entry["group"] for entry in first} == {"isolated: subfleet lane claude-10"}
    assert all(
        "2026-09-30T09:02:46" <= entry["judged_at_utc"] < "2026-09-30T11:13:07"
        for entry in first
    )
    assert "43 of them also ran with an allowlisted environment" in record["note"]


def test_the_runners_nudge_is_the_gates():
    script = (driver.ROOT / "scripts/run_audit_claude.sh").read_text()
    line = next(
        line for line in script.splitlines() if line.startswith("PROMPT_NUDGE=")
    )
    assert line == f'PROMPT_NUDGE="{driver.JUDGE_PROMPT_NUDGE}"'


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
    (stage / "data-board46.json").unlink()
    entry["isolated"] = False
    driver.JUDGE_PROVENANCE.write_text(json.dumps(_provenance_record([entry])))
    with pytest.raises(SystemExit, match="disagree with docs/gpt61sol"):
        run(_exported(incumbents), incumbents)
    assert not (stage / "release-ready.json").exists()
    assert not (stage / "data-board46.json").exists()


MUTATIONS = {
    "value": lambda row: row.update(exact=row["exact"] + 1e-12),
    "added_key": lambda row: row.update(extra=None),
    "removed_key": lambda row: row.pop("score"),
    "key_order": lambda row: row.update(model=row.pop("model")),
    "int_to_float": lambda row: row.update(n=float(row["n"])),
    "zero_cost_to_missing": lambda row: row.pop("costUsd"),
    "zero_to_negative_zero": lambda row: row.update(costUsd=-row["costUsd"]),
}


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    target=st.integers(min_value=0, max_value=44),
    mutation=st.sampled_from(sorted(MUTATIONS)),
)
def test_the_no_drift_gate_refuses_any_change_to_any_incumbent(
    exporting, target, mutation
):
    """For every incumbent and every kind of change, export refuses."""
    stage, _, run, _ = exporting
    incumbents = _incumbents()
    stats = _exported(incumbents)
    MUTATIONS[mutation](stats[target])
    (stage / "data-board46.json").unlink(missing_ok=True)
    # Fable's usage values are carried over from the base (the exporter cannot
    # recompute them), so a changed value there is replaced by the released
    # one; a missing key comes back out of order and is still refused.
    if target == 44 and mutation == "zero_to_negative_zero":
        run(stats, incumbents, early=True)
        assert json.dumps(stats[target]) == json.dumps(incumbents[target])
        return
    with pytest.raises(SystemExit, match="incumbent modelStats drift"):
        run(stats, incumbents, early=True)
    assert not (stage / "data-board46.json").exists()


@settings(max_examples=60, deadline=None)
@given(
    rows=st.lists(
        st.fixed_dictionaries(
            {
                "exact": st.floats(allow_nan=False, allow_infinity=False),
                "n": st.integers(min_value=0, max_value=1984),
            }
        ),
        min_size=45,
        max_size=45,
    ),
    target=st.integers(min_value=0, max_value=44),
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


def test_the_export_roster_must_be_the_incumbents_plus_the_addition(exporting):
    _, _, run, _ = exporting
    incumbents = _incumbents()
    stats = _exported(incumbents)
    stats[-1] = _stat("gpt-6-sol-impostor", 65.0)
    with pytest.raises(SystemExit, match="roster"):
        run(stats, incumbents)
    with pytest.raises(SystemExit, match="45 incumbents"):
        run(_exported(incumbents), incumbents[:-1] + [_stat(NEW, 1.0)])


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
    """RELEASE_TAG is the only spelling of the new tag in the driver's files."""
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/finish_gpt61sol.py").read_text().splitlines()
    assert sum(driver.RELEASE_TAG in line for line in source) == 1
    for relative in (
        "scripts/freeze_gpt61sol.py",
        "scripts/snapshot_gpt61sol.py",
        "docs/gpt61sol/design.md",
        "tests/test_freeze_gpt61sol.py",
        "tests/test_finish_gpt61sol.py",
    ):
        assert driver.RELEASE_TAG not in (root / relative).read_text(), relative
