"""The GPT-6.1 Sol freeze builds nothing from an unbound or revised stage.

Adapted from the freeze tests in test_finish_adds0928.py, with synthetic
stages; the committed references and adjudications are read, never written.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import finish_gpt61sol as driver  # noqa: E402
import freeze_gpt61sol as release  # noqa: E402

RUN = driver.RUN_NAME
BUNDLE = Path("publish") / RUN
COMMITTED_ADJUDICATIONS = driver.ANNOTATIONS / "us_adjudications.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_freeze_adds_gpt61sol_alone_under_the_driver_tag():
    assert release.NEW_MODELS == {"gpt61sol": "gpt-6.1-sol"} == driver.MODELS
    assert release.BOARD_MODELS == 46
    assert not hasattr(release, "reference_revision")


@pytest.fixture
def freeze_preflight(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(release, "ROOT", workspace)
    stage = workspace / "results/local/stage"
    stage.mkdir(parents=True)
    payload = stage / "data-board46.json"
    payload.write_text(json.dumps({"countries": {"us": {"modelStats": []}}}))
    evidence = [
        BUNDLE / "us" / name for name in (*driver.REFERENCE_FILES, "predictions.csv")
    ]
    evidence += [BUNDLE / "annotations/us_adjudications.json"]
    evidence += [Path("inputs/gpt61sol/run_state.json"), Path("audit/verdict.json")]
    for name in evidence:
        (stage / name).parent.mkdir(parents=True, exist_ok=True)
        (stage / name).write_text(f"Evidence: {name.name}\n")
    receipt = {
        "release_tag": driver.RELEASE_TAG,
        "base_tag": driver.BASE_TAG,
        "base_sha256": driver.BASE_SHA256,
        "payload_sha256": sha(payload),
        "models": 46,
        "partial": False,
        "files": {str(name): sha(stage / name) for name in evidence},
    }
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    pointer = workspace / "app/src/data.artifact.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text("The live pointer must stay unchanged.\n")
    return stage, payload, receipt


def workspace_files():
    return {
        path.relative_to(release.ROOT): path.read_bytes()
        for path in release.ROOT.rglob("*")
        if path.is_file()
    }


def test_freeze_rejects_pretty_json_before_any_workspace_mutation(freeze_preflight):
    stage, payload, receipt = freeze_preflight
    payload.write_text(json.dumps(json.loads(payload.read_text()), indent=2) + "\n")
    receipt["payload_sha256"] = sha(payload)
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    before = workspace_files()
    with pytest.raises(SystemExit, match="does not recombine to the freeze format"):
        release.main(["--stage-dir", str(stage)])
    assert workspace_files() == before


def test_the_default_tag_is_the_driver_release_tag(freeze_preflight, monkeypatch):
    stage, _, receipt = freeze_preflight
    monkeypatch.setattr(driver, "RELEASE_TAG", "dashboard-data-20261001")
    with pytest.raises(SystemExit, match="release tag 'dashboard-data-20261001'"):
        release.main(["--stage-dir", str(stage), "--dry-run"])
    receipt["release_tag"] = "dashboard-data-20261001"
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    # Past the receipt, the synthetic payload fails the dashboard schema.
    with pytest.raises(SystemExit, match="Strict dashboard gate failed"):
        release.main(["--stage-dir", str(stage), "--dry-run"])


@pytest.mark.parametrize(
    "defect",
    [
        "changed",
        "outside_stage",
        "missing_hashes",
        "board45",
        "partial",
        "tag",
        "base_tag",
        "base_sha256",
    ],
)
def test_freeze_refuses_changed_or_unbound_evidence(freeze_preflight, defect):
    stage, _, receipt = freeze_preflight
    message = "Strict export receipt does not match"
    if defect == "changed":
        (stage / "audit/verdict.json").write_text("Altered judge evidence\n")
        message = "Staged evidence changed"
    elif defect == "outside_stage":
        path = release.ROOT / "app/src/data.artifact.json"
        receipt["files"]["../../../app/src/data.artifact.json"] = sha(path)
        message = "Staged evidence changed"
    elif defect == "missing_hashes":
        receipt["files"] = {}
        message = "missing staged evidence hashes"
    elif defect == "board45":
        receipt["models"] = 45
    elif defect == "partial":
        receipt["partial"] = True
    elif defect == "base_tag":
        receipt["base_tag"] = "dashboard-data-20260922c"
        message = "does not name release 20260929 as its base"
    elif defect == "base_sha256":
        receipt["base_sha256"] = "0" * 64
        message = "does not name release 20260929 as its base"
    else:
        receipt["release_tag"] = driver.BASE_TAG
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    before = workspace_files()
    with pytest.raises(SystemExit, match=message):
        release.main(["--stage-dir", str(stage), "--dry-run"])
    assert workspace_files() == before


@pytest.mark.parametrize(
    "unbound",
    [
        str(BUNDLE / "us/reference_exclusions.json"),
        str(BUNDLE / "annotations/us_adjudications.json"),
        "inputs/gpt61sol/run_state.json",
    ],
)
def test_the_receipt_must_bind_references_adjudications_and_run_state(
    freeze_preflight, unbound
):
    stage, _, receipt = freeze_preflight
    del receipt["files"][unbound]
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    with pytest.raises(SystemExit, match="does not bind"):
        release.main(["--stage-dir", str(stage), "--dry-run"])


@pytest.fixture
def staged_board(freeze_preflight, monkeypatch):
    """A 46-row payload past the receipt, with the committed snapshot copied in."""
    import policybench.dashboard_schema

    stage, payload, receipt = freeze_preflight
    snapshot = release.ROOT / "paper/snapshot/20260501"
    frozen = snapshot / "runs" / RUN
    frozen.mkdir(parents=True)
    source = driver.ROOT / "paper/snapshot/20260501"
    for name in ("manifest.json", "model_serving_config.json"):
        shutil.copyfile(source / name, snapshot / name)
    for name in driver.REFERENCE_FILES:
        shutil.copyfile(driver.SNAPSHOT / name, frozen / name)
    serving = json.loads((snapshot / "model_serving_config.json").read_text())
    models = sorted(serving["models"]) + ["gpt-6.1-sol"]
    stats = [{"model": model, "condition": "no_tools"} for model in models]
    payload.write_text(json.dumps({"countries": {"us": {"modelStats": stats}}}))
    receipt["payload_sha256"] = sha(payload)
    monkeypatch.setattr(
        policybench.dashboard_schema, "validate_dashboard_payload", lambda *a, **k: []
    )

    def rebind():
        receipt["files"] = {name: sha(stage / name) for name in receipt["files"]}
        (stage / "release-ready.json").write_text(json.dumps(receipt))

    rebind()
    return stage, rebind


def test_the_freeze_refuses_a_revised_staged_reference_before_mutation(staged_board):
    stage, _ = staged_board
    before = workspace_files()
    with pytest.raises(SystemExit, match="Staged reference_outputs.csv changed"):
        release.main(["--stage-dir", str(stage)])
    assert workspace_files() == before


def test_the_freeze_refuses_a_dropped_adjudication_before_mutation(staged_board):
    stage, rebind = staged_board
    for name in driver.REFERENCE_FILES:
        shutil.copyfile(driver.SNAPSHOT / name, stage / BUNDLE / "us" / name)
    record = json.loads(COMMITTED_ADJUDICATIONS.read_text())
    record["adjudications"].pop(0)
    (stage / BUNDLE / "annotations/us_adjudications.json").write_text(
        json.dumps(record)
    )
    rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match="drop recorded decisions"):
        release.main(["--stage-dir", str(stage)])
    assert workspace_files() == before


# --- References ----------------------------------------------------------------


@pytest.fixture
def references(tmp_path):
    staged = tmp_path / "staged"
    frozen = tmp_path / "frozen"
    for directory in (staged, frozen):
        directory.mkdir()
        for name in driver.REFERENCE_FILES:
            shutil.copyfile(driver.SNAPSHOT / name, directory / name)
    manifest = json.loads(
        (driver.ROOT / "paper/snapshot/20260501/manifest.json").read_text()
    )
    return staged, frozen, manifest


def test_unchanged_references_pass(references):
    release.verify_references(*references)


@pytest.mark.parametrize("name", driver.REFERENCE_FILES)
@pytest.mark.parametrize("where", ["Staged", "Committed", "Manifest pin"])
def test_any_reference_revision_is_refused(references, name, where):
    staged, frozen, manifest = references
    manifest = copy.deepcopy(manifest)
    if where == "Staged":
        (staged / name).write_bytes((staged / name).read_bytes() + b"\n")
    elif where == "Committed":
        (frozen / name).write_bytes((frozen / name).read_bytes() + b"\n")
    else:
        manifest["source_run_artifacts"][RUN]["files"][name] = "0" * 64
    with pytest.raises(SystemExit, match=f"{where} (for )?{name}"):
        release.verify_references(staged, frozen, manifest)


# --- Adjudications -------------------------------------------------------------


@pytest.fixture
def adjudications(tmp_path):
    staged = tmp_path / "us_adjudications.json"
    shutil.copyfile(COMMITTED_ADJUDICATIONS, staged)
    record = json.loads(staged.read_text())
    return staged, record


def _write(path, record):
    path.write_text(json.dumps(record, indent=2) + "\n")


def test_an_unchanged_adjudication_record_passes(adjudications):
    staged, _ = adjudications
    assert (
        release.verify_adjudication_record(
            staged, COMMITTED_ADJUDICATIONS, driver.SNAPSHOT
        )
        == 0
    )


def test_triage_may_add_a_decision_that_keeps_the_output_scored(adjudications):
    staged, record = adjudications
    scored = next(
        e for e in record["adjudications"] if not e.get("excluded_from_scoring")
    )
    added = {**copy.deepcopy(scored), "scenario_id": "scenario_999"}
    record["adjudications"].append(added)
    _write(staged, record)
    assert (
        release.verify_adjudication_record(
            staged, COMMITTED_ADJUDICATIONS, driver.SNAPSHOT
        )
        == 1
    )


def test_triage_may_restate_a_rejudged_class(adjudications):
    staged, record = adjudications
    record["adjudications"][0]["judge_failure_subtype"] = "thresholds_rates"
    _write(staged, record)
    assert (
        release.verify_adjudication_record(
            staged, COMMITTED_ADJUDICATIONS, driver.SNAPSHOT
        )
        == 0
    )


def test_a_dropped_decision_is_refused(adjudications):
    staged, record = adjudications
    record["adjudications"].pop()
    _write(staged, record)
    with pytest.raises(SystemExit, match="drop recorded decisions"):
        release.verify_adjudication_record(
            staged, COMMITTED_ADJUDICATIONS, driver.SNAPSHOT
        )


def test_a_new_exclusion_is_refused(adjudications):
    staged, record = adjudications
    excluded = next(
        e for e in record["adjudications"] if e.get("excluded_from_scoring")
    )
    record["adjudications"].append(
        {**copy.deepcopy(excluded), "scenario_id": "scenario_999"}
    )
    _write(staged, record)
    with pytest.raises(SystemExit, match="change the scoring exclusions"):
        release.verify_adjudication_record(
            staged, COMMITTED_ADJUDICATIONS, driver.SNAPSHOT
        )


# --- Treatment -----------------------------------------------------------------

# The fingerprint GPT-6.1 Sol's supervised run recorded when it started
# (results/local/adds202609/gpt61sol/run/run_state.json, 2026-09-29).
GPT61SOL_FINGERPRINT = {
    "fingerprint_version": 3,
    "model_id": "gpt-6.1-sol",
    "answer_contract": "tool",
    "tool_choice_mode": "forced",
    "chunk_size": None,
    "prompt_contract_version": "2026-08-09-v2-scoring-contract",
    "completion_budget_ceiling": 128000,
    "initial_completion_budget_tokens": 16384,
    "thinking": {"mode": "provider_default"},
    "request_timeout_seconds": 300,
    "max_repair_rounds": 2,
}


def test_the_registered_treatment_matches_the_run_and_a_drift_is_refused(tmp_path):
    import freeze_snapshot as freezer

    state = {"model": "gpt-6.1-sol", "treatment_fingerprint": GPT61SOL_FINGERPRINT}
    path = tmp_path / "run_state.json"
    scenarios = driver.SNAPSHOT / "scenarios.csv"
    release.validate_treatment(freezer, state, path, scenarios)
    drifted = copy.deepcopy(state)
    drifted["treatment_fingerprint"]["request_timeout_seconds"] = 600
    with pytest.raises(SystemExit, match="disagrees with registry"):
        release.validate_treatment(freezer, drifted, path, scenarios)


# --- Rehearsal copy ------------------------------------------------------------


def test_the_rehearsal_copy_reads_scenario_csvs_only(tmp_path, monkeypatch):
    import snapshot_adds0928
    import snapshot_gpt61sol

    workspace = tmp_path / "workspace"
    reference = workspace / "reference"
    reference.mkdir(parents=True)
    (reference / "reference_outputs.csv").write_text(
        "scenario_id,variable\nscenario_007,snap\nscenario_007,ssi\n"
    )
    monkeypatch.setattr(driver, "ROOT", workspace)
    monkeypatch.setattr(driver, "SNAPSHOT", reference)
    runs = workspace / "supervised"
    source = runs / "gpt61sol/run/scenarios/scenario_006.csv"
    source.parent.mkdir(parents=True)
    raw = (
        "model,scenario_id,variable,prediction\r\n"
        "gpt-6.1-sol,scenario_007,snap,1\r\n"
        "gpt-6.1-sol,scenario_007,ssi,2\r\n"
    ).encode()
    source.write_bytes(raw)
    output = workspace / "results/local/copied-runs"
    monkeypatch.setattr(
        sys,
        "argv",
        ["snapshot_gpt61sol.py", "--runs-root", str(runs), "--out-dir", str(output)],
    )
    original = snapshot_adds0928.MODELS

    snapshot_gpt61sol.main()

    assert snapshot_adds0928.MODELS is original
    target = output / "gpt61sol/run"
    assert (target / "scenarios/scenario_006.csv").read_bytes() == raw
    with (target / "predictions.csv").open(newline="") as stream:
        assert {row["model"] for row in csv.DictReader(stream)} == {"gpt-6.1-sol"}
    state = json.loads((target / "run_state.json").read_text())
    assert state["model"] == "gpt-6.1-sol" and state["synthetic_partial"] is True
    assert state["completed"] == 1 and state["total"] == 100
    assert sorted(p.name for p in output.iterdir()) == ["gpt61sol"]
    with pytest.raises(SystemExit, match="refusing incomplete additions"):
        driver.discover_new_models(output)
