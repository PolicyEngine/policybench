"""The GPT-6.1 Sol freeze builds nothing from an unbound or revised stage.

Adapted from the freeze tests in test_finish_adds0928.py, with synthetic
stages; the committed references and adjudications are read, never written.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import finish_gpt61sol as driver  # noqa: E402
import freeze_gpt61sol as release  # noqa: E402

from policybench.audit import AUDIT_OUTPUT_SCHEMA  # noqa: E402

RUN = driver.RUN_NAME
SLUG = "gpt61sol"
# The run files the committed input pins name (driver.PINNED_INPUTS).
PINNED = ("predictions.csv", "run_state.json")
BUNDLE = Path("publish") / RUN
COMMITTED_ADJUDICATIONS = driver.ANNOTATIONS / "us_adjudications.json"
# The synthetic stage's one judged case, an incumbent-only case kept from the
# seed, and the audit evidence the receipt must bind for it.
KEPT = "us__scenario_000__snap"
AUDIT_EVIDENCE = [Path("audit/cases.jsonl"), Path("audit/schema.json")] + [
    Path("audit/cases") / KEPT / name
    for name in ("prompt.md", "verdict.json", "verdict.meta.json")
]
ANNOTATION_CSVS = [
    BUNDLE / "annotations" / name
    for name in ("us_audit_row_annotations.csv", "us_case_notes.csv")
]
# The case reference explanations, which must stay release 20260929's.
EXPLANATIONS_NAME = "us_case_reference_explanations.csv"
EXPLANATIONS = BUNDLE / "annotations" / EXPLANATIONS_NAME
# The bundle files export_full_run reads (driver.EXPORT_INPUTS): the
# references and predictions, and the three annotation CSVs whose loaders
# fall back to the working directory's committed annotations.
EXPORT_READS = (
    *(f"us/{name}" for name in (*driver.REFERENCE_FILES, "predictions.csv")),
    "annotations/us_audit_row_annotations.csv",
    "annotations/us_case_notes.csv",
    f"annotations/{EXPLANATIONS_NAME}",
)


# The committed receipt pin's reader, which the fixtures stub; the tests of
# the pin itself restore it.
COMMITTED_RELEASE_RECEIPT = getattr(driver, "committed_release_receipt", None)
SOL = "gpt-6.1-sol"
# GPT-6.1 Sol's run file as the synthetic stage pins it, with the usage
# columns its published cost, tokens and latency come from, and an incumbent
# row the bundle's predictions hold beside its rows.
SOL_RUN = (
    "model,scenario_id,variable,prediction,estimated_cost_usd,total_cost_usd,"
    "total_tokens,elapsed_seconds\n"
    "gpt-6.1-sol,scenario_000,snap,1200.0,0.0125,0.0125,4096.5,12.75\n"
    "gpt-6.1-sol,scenario_001,snap,0.0,0.011,0.011,3900.25,11.5\n"
)
INCUMBENT_ROW = "incumbent,scenario_000,snap,900.0,0.002,0.002,1000.0,3.5\n"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restamp(stage: Path) -> None:
    """Write the prepare-time hashes of stage.json and model-provenance.json
    for the stage as it stands, as prepare would have."""
    names = [
        BUNDLE / "us" / name for name in (*driver.REFERENCE_FILES, "predictions.csv")
    ]
    names += [Path("inputs/gpt61sol") / name for name in PINNED]
    files = {str(name): sha(stage / name) for name in names}
    (stage / "stage.json").write_text(
        json.dumps({"partial": False, "early": False, "files": files})
    )
    inputs = stage / "inputs/gpt61sol"
    state = json.loads((inputs / "run_state.json").read_text())
    provenance = {
        SOL: {
            "predictions_sha256": sha(inputs / "predictions.csv"),
            "treatment_fingerprint": state["treatment_fingerprint"],
        }
    }
    (stage / "model-provenance.json").write_text(json.dumps(provenance))


def write_inputs(stage: Path) -> dict:
    """GPT-6.1 Sol's run files, the bundle's predictions holding its rows as
    prepare folds them, and the prepare-time hashes; returns the pins."""
    inputs = stage / "inputs/gpt61sol"
    inputs.mkdir(parents=True, exist_ok=True)
    (inputs / "predictions.csv").write_text(SOL_RUN)
    state = {"model": SOL, "treatment_fingerprint": GPT61SOL_FINGERPRINT}
    (inputs / "run_state.json").write_text(json.dumps(state))
    header, *rows = SOL_RUN.splitlines(keepends=True)
    (stage / BUNDLE / "us/predictions.csv").write_text(
        header + INCUMBENT_ROW + "".join(rows)
    )
    restamp(stage)
    return {SLUG: {name: sha(inputs / name) for name in PINNED}}


def write_audit(audit: Path) -> None:
    """One judged, kept case with a bound seed verdict; one parse-only case,
    which is never judged and so needs no verdict."""
    case = audit / "cases" / KEPT
    case.mkdir(parents=True)
    (audit / "schema.json").write_text(json.dumps(AUDIT_OUTPUT_SCHEMA))
    manifest = [
        {
            "case_id": KEPT,
            "scenario_id": "scenario_000",
            "variable": "snap",
            "wrong_models": ["incumbent"],
            "parse_failure_only": False,
        },
        {
            "case_id": "us__scenario_001__snap",
            "scenario_id": "scenario_001",
            "variable": "snap",
            "wrong_models": ["incumbent"],
            "parse_failure_only": True,
        },
    ]
    (audit / "cases.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in manifest)
    )
    (case / "prompt.md").write_text("Classify these wrong answers.\n")
    verdict = {
        "reference_suspect": False,
        "reference_bug_hypothesis": "",
        "case_failure_source": "llm_error",
        "case_failure_subtype": "thresholds_rates",
        "rationale": "The model applied an outdated threshold.",
        "models": [
            {
                "model": "incumbent",
                "failure_source": "llm_error",
                "failure_subtype": "thresholds_rates",
                "diagnosis": "The model used the prior year's threshold.",
            }
        ],
    }
    (case / "verdict.json").write_text(json.dumps(verdict))
    (case / "verdict.meta.json").write_text(
        json.dumps(
            {
                "verdict_sha256": sha(case / "verdict.json"),
                "judge_model_requested": "default",
            }
        )
    )


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
    evidence += [BUNDLE / "annotations/us_adjudications.json", *ANNOTATION_CSVS]
    evidence += [Path(driver.PROMPT_CHANGES)]
    for name in evidence:
        (stage / name).parent.mkdir(parents=True, exist_ok=True)
        (stage / name).write_text(f"Evidence: {name.name}\n")
    (stage / EXPLANATIONS).write_bytes(base_explanations())
    evidence += [EXPLANATIONS]
    # GPT-6.1 Sol's run files are the committed pins' (stubbed here), and the
    # bundle's predictions hold its rows as prepare folded them.
    pins = write_inputs(stage)
    monkeypatch.setattr(driver, "committed_input_pins", lambda: pins, raising=False)
    evidence += [Path("inputs/gpt61sol") / name for name in PINNED]
    evidence += [Path("model-provenance.json"), Path("stage.json")]
    write_audit(stage / "audit")
    evidence += AUDIT_EVIDENCE
    (stage / driver.PROMPT_CHANGES).write_text(
        json.dumps({"added": [], "changed": [], "kept": []})
    )
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

    def committed_release_receipt():
        # The pin export would write for the stage as it stands, committed;
        # the tests of the pin itself fix or restore it.
        return {
            "release_tag": json.loads((stage / "release-ready.json").read_text()).get(
                "release_tag"
            ),
            "payload_sha256": sha(payload),
            "release_ready_sha256": sha(stage / "release-ready.json"),
        }

    monkeypatch.setattr(
        driver, "committed_release_receipt", committed_release_receipt, raising=False
    )
    return stage, payload, receipt


def base_explanations() -> bytes:
    """Release 20260929's case reference explanations, from git."""
    return driver.base_commit_blob(Path("annotations") / RUN / EXPLANATIONS_NAME)


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
        (stage / "audit/cases" / KEPT / "verdict.json").write_text("Altered\n")
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
        "inputs/gpt61sol/predictions.csv",
        "model-provenance.json",
        driver.PROMPT_CHANGES,
        "stage.json",
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


@pytest.mark.parametrize(
    "unbound", [str(path) for path in (*AUDIT_EVIDENCE, *ANNOTATION_CSVS)]
)
def test_the_receipt_must_bind_every_judged_case_and_both_annotation_csvs(
    freeze_preflight, unbound
):
    """Without its receipt entry, a kept verdict or sidecar could be edited
    and re-hashed after export; the freeze refuses the missing entry."""
    stage, _, receipt = freeze_preflight
    del receipt["files"][unbound]
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    before = workspace_files()
    with pytest.raises(SystemExit, match=f"does not bind.*{re.escape(unbound)}"):
        release.main(["--stage-dir", str(stage), "--dry-run"])
    assert workspace_files() == before


def test_wording_amendments_present_in_the_stage_must_be_bound(freeze_preflight):
    stage, _, _ = freeze_preflight
    (stage / driver.AMENDMENTS).write_text(json.dumps({"amendments": []}))
    with pytest.raises(SystemExit, match=f"does not bind.*{driver.AMENDMENTS}"):
        release.main(["--stage-dir", str(stage), "--dry-run"])


# One unadjudicated case of the synthetic payload, as two models answered it.
CASE = ("scenario_017", "snap")


def _case_row(prediction: float) -> dict:
    return {
        "prediction": prediction,
        "groundTruth": 1200.0,
        "scored": True,
        "annotation": "Used the prior year's allotment.",
        "failureSource": "llm_error",
        "failureSubtype": "thresholds_rates",
        "caseAnnotation": "Both models used the prior year's maximum allotment.",
        "caseFailureSources": "llm_error",
        "caseFailureSubtypes": "thresholds_rates",
    }


@pytest.fixture
def rebuilds():
    """Each bundle the freeze's rebuild exported, with its files' bytes."""
    return []


@pytest.fixture
def exports():
    """The board the stubbed export_full_run returns for the bound bundle; a
    test that edits a bundle input edits it as export would rebuild it."""
    return {}


@pytest.fixture
def staged_board(freeze_preflight, monkeypatch, rebuilds, exports):
    """A 46-row payload past the receipt, with the committed snapshot copied in.

    export_full_run is stubbed to return what it would for the bound bundle:
    the staged payload before export carries Fable 5's usage. The freeze's
    rebuild runs export's own build on it, so an unedited payload rebuilds,
    and each test that stops at a later gate still reaches it. Like the real
    exporter, the stub writes data.json into the bundle it reads.
    """
    import policybench.dashboard_schema
    import policybench.full_run_export

    stage, payload, receipt = freeze_preflight
    # A synthetic stage binds no seed; the re-derived case list is tested in
    # test_finish_gpt61sol.py.
    monkeypatch.setattr(driver, "rejudged_cases", lambda stage: frozenset())
    # The seed stage.json binds is the synthetic audit as written: its one
    # judged case is kept, so its verdict must stay the seed's.
    seed = driver.seed_digest(stage / "audit")
    monkeypatch.setattr(driver, "load_seed", lambda stage: seed)
    snapshot = release.ROOT / "paper/snapshot/20260501"
    frozen = snapshot / "runs" / RUN
    frozen.mkdir(parents=True)
    source = driver.ROOT / "paper/snapshot/20260501"
    for name in ("manifest.json", "model_serving_config.json"):
        shutil.copyfile(source / name, snapshot / name)
    for name in driver.REFERENCE_FILES:
        shutil.copyfile(driver.SNAPSHOT / name, frozen / name)
    # The incumbents' rows are release 20260929's, as export leaves them.
    stats = driver.base_payload_from_commit()["countries"]["us"]["modelStats"]
    stats += [{"model": SOL, "condition": "no_tools", "exact": 61.5, "score": 74.2}]
    scenario, variable = CASE
    cases = {
        scenario: {
            variable: {"claude-fable-5": _case_row(900.0), SOL: _case_row(950.0)}
        }
    }
    board = {"countries": {"us": {"modelStats": stats, "scenarioPredictions": cases}}}
    payload.write_text(json.dumps(board))
    monkeypatch.setattr(
        policybench.dashboard_schema, "validate_dashboard_payload", lambda *a, **k: []
    )
    exported = copy.deepcopy(board)
    fable = next(
        row
        for row in exported["countries"]["us"]["modelStats"]
        if row["model"] == "claude-fable-5"
    )
    fable.update(costUsd=0.0, costPerHousehold=0.0)
    del fable["totalTokens"], fable["latencySeconds"]
    exports["board"] = exported

    def export_full_run(run_dir, *, countries, skip_app_data):
        assert countries == ["us"] and skip_app_data
        run_dir = Path(run_dir)
        files = {
            path.relative_to(run_dir): path.read_bytes()
            for path in run_dir.rglob("*")
            if path.is_file()
        }
        rebuilds.append((run_dir, files))
        (run_dir / "data.json").write_text("Fable 5's usage is not carried here.\n")
        return copy.deepcopy(exports["board"])

    monkeypatch.setattr(policybench.full_run_export, "export_full_run", export_full_run)

    # The synthetic stage re-opens no case, so its provenance record lists none.
    record = stage.parent / "judge_provenance.json"
    record.write_text(json.dumps({"note": "None.", "counts": {}, "verdicts": []}))
    monkeypatch.setattr(driver, "JUDGE_PROVENANCE", record)

    def rebind(restamp_stage=True):
        # Every hash in the stage follows the edit: the receipt's and, unless
        # a test keeps them, stage.json's and model-provenance.json's.
        if restamp_stage:
            restamp(stage)
        receipt["payload_sha256"] = sha(payload)
        receipt["files"] = {name: sha(stage / name) for name in receipt["files"]}
        receipt["judge_provenance"] = {
            "path": driver.JUDGE_PROVENANCE_PATH,
            "sha256": sha(record),
        }
        (stage / "release-ready.json").write_text(json.dumps(receipt))

    rebind()
    return stage, rebind


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("defect", ["edited", "unbound", "other_path", "missing"])
def test_the_freeze_refuses_a_provenance_record_export_did_not_bind(
    staged_board, defect, dry_run
):
    """Export binds the judge provenance record's hash in the receipt. A
    record edited afterwards, one the receipt does not bind or binds under
    another path, or a missing one, is refused before any workspace mutation."""
    stage, rebind = staged_board
    for name in driver.REFERENCE_FILES:
        shutil.copyfile(driver.SNAPSHOT / name, stage / BUNDLE / "us" / name)
    rebind()
    receipt = json.loads((stage / "release-ready.json").read_text())
    if defect == "edited":
        driver.JUDGE_PROVENANCE.write_text(
            json.dumps({"note": "every judge ran isolated", "verdicts": []})
        )
    elif defect == "missing":
        driver.JUDGE_PROVENANCE.unlink()
    elif defect == "unbound":
        del receipt["judge_provenance"]
    else:
        receipt["judge_provenance"]["path"] = "docs/elsewhere.json"
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    before = workspace_files()
    with pytest.raises(SystemExit, match="not the judge provenance record"):
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    assert workspace_files() == before


@pytest.mark.parametrize("dry_run", [True, False])
def test_the_freeze_refuses_incumbent_stats_edited_after_export(staged_board, dry_run):
    """Export refuses incumbent drift before it writes the receipt; an
    incumbent's cost edited afterwards, with the receipt's payload hash
    updated to match, must still be refused before any workspace mutation."""
    stage, rebind = staged_board
    payload = stage / "data-board46.json"
    board = json.loads(payload.read_text())
    row = next(
        row
        for row in board["countries"]["us"]["modelStats"]
        if row["model"] != "gpt-6.1-sol"
    )
    row["costUsd"] *= 2
    row["costPerHousehold"] *= 2
    payload.write_text(json.dumps(board))
    rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match=f"modelStats drift.*{row['model']}"):
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    assert workspace_files() == before


def _edit_new_model_scores(board: dict) -> list[str]:
    row = next(r for r in board["countries"]["us"]["modelStats"] if r["model"] == SOL)
    row.update(exact=100.0, score=100.0)
    at = f"payload.countries.us.modelStats[45 {SOL}]"
    return [f"{at}.exact", f"{at}.score"]


def _edit_case_review(board: dict) -> list[str]:
    scenario, variable = CASE
    case = board["countries"]["us"]["scenarioPredictions"][scenario][variable]
    for row in case.values():
        row.update(
            caseFailureSources="needs_review",
            reference_suspect=True,
            wrong_model_count=999,
        )
    at = f"payload.countries.us.scenarioPredictions.{scenario}.{variable}"
    return [
        f"{at}.claude-fable-5.caseFailureSources",
        f"{at}.claude-fable-5.reference_suspect (only staged)",
        f"{at}.claude-fable-5.wrong_model_count (only staged)",
    ]


# The second review's edits to the staged payload, each of which passed every
# other gate once the receipt's payload hash was updated to match.
PAYLOAD_EDITS = {
    "new_model_scores": _edit_new_model_scores,
    "case_review": _edit_case_review,
}


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("edit", PAYLOAD_EDITS)
def test_the_freeze_refuses_a_payload_edited_after_export(staged_board, edit, dry_run):
    """The receipt binds the payload only by a hash beside it. GPT-6.1 Sol's
    exact and score set to 100, or a case marked needs_review with
    reference_suspect and wrong_model_count 999, with the receipt's payload
    hash updated to match, is refused before any workspace mutation: the
    payload export builds from the bound bundle is not the staged one."""
    stage, rebind = staged_board
    for name in driver.REFERENCE_FILES:
        shutil.copyfile(driver.SNAPSHOT / name, stage / BUNDLE / "us" / name)
    payload = stage / "data-board46.json"
    board = json.loads(payload.read_text())
    paths = PAYLOAD_EDITS[edit](board)
    payload.write_text(json.dumps(board))
    rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match="is not what export builds") as refused:
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    for path in paths:
        assert repr(path) in str(refused.value)
    assert workspace_files() == before


def test_the_rebuild_reads_a_scratch_copy_of_the_bound_bundle(
    staged_board, rebuilds, monkeypatch
):
    """export_full_run writes into the bundle it reads. The rebuild hands it a
    scratch copy outside the workspace holding exactly the bundle files the
    receipt binds, with their bound bytes, and removes it; an unedited
    payload rebuilds, carrying Fable 5's usage as export does, and the
    freeze goes on to its next gate."""
    stage, rebind = staged_board
    for name in driver.REFERENCE_FILES:
        shutil.copyfile(driver.SNAPSHOT / name, stage / BUNDLE / "us" / name)
    rebind()

    def next_gate(stage):
        raise SystemExit("Reached the verdict gate")

    monkeypatch.setattr(release, "verify_verdicts", next_gate)
    receipt = json.loads((stage / "release-ready.json").read_text())
    before = workspace_files()
    with pytest.raises(SystemExit, match="Reached the verdict gate"):
        release.main(["--stage-dir", str(stage), "--dry-run"])
    assert workspace_files() == before
    [(run_dir, files)] = rebuilds
    assert run_dir.name == RUN and not run_dir.exists()
    assert not run_dir.is_relative_to(release.ROOT)
    bound = [Path(name) for name in receipt["files"]]
    assert files == {
        name.relative_to(BUNDLE): (stage / name).read_bytes()
        for name in bound
        if name.is_relative_to(BUNDLE)
    }
    assert len(files) == 10


def test_the_rebuild_reads_only_the_bytes_the_receipt_binds(staged_board, rebuilds):
    """A bound bundle file that changes after the receipt was checked is
    refused rather than exported."""
    stage, rebind = staged_board
    payload = stage / "data-board46.json"
    receipt = json.loads((stage / "release-ready.json").read_text())
    base = driver.base_payload_from_commit()
    release.rebuild_payload(stage, receipt, payload, base)
    (stage / BUNDLE / "us/predictions.csv").write_text("Edited after the check.\n")
    with pytest.raises(SystemExit, match="changed since strict export.*predictions"):
        release.rebuild_payload(stage, receipt, payload, base)
    assert len(rebuilds) == 1


def _reached(gate: str):
    def stop(*args, **kwargs):
        raise SystemExit(f"Reached the {gate}")

    return stop


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("edit", ["receipt", "payload"])
def test_the_freeze_refuses_a_stage_edited_after_its_pin_was_committed(
    staged_board, monkeypatch, edit, dry_run
):
    """The receipt binds the stage only by hashes beside it. A stage file
    edited after export, the receipt re-hashed to match (or the payload
    edited, its receipt hash updated), is refused before any later gate
    and any workspace mutation: the committed pin still names the receipt
    and payload export wrote."""
    stage, rebind = staged_board
    pin = driver.committed_release_receipt()
    monkeypatch.setattr(driver, "committed_release_receipt", lambda: pin)
    monkeypatch.setattr(driver, "verify_new_model_inputs", _reached("input gate"))
    if edit == "receipt":
        meta = stage / "audit/cases" / KEPT / "verdict.meta.json"
        meta.write_text(
            json.dumps({**json.loads(meta.read_text()), "judge_runner": "by hand"})
        )
        expected = "\\['release_ready_sha256'\\]"
    else:
        payload = stage / "data-board46.json"
        board = json.loads(payload.read_text())
        board["countries"]["us"]["modelStats"][-1]["exact"] = 100.0
        payload.write_text(json.dumps(board))
        expected = "\\['payload_sha256', 'release_ready_sha256'\\]"
    rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match=f"stage's {expected} are not what"):
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    assert workspace_files() == before


def _commit(root: Path, message: str) -> None:
    """Commit everything in a scratch repository, with no user hooks or keys."""
    git = ["git", "-C", str(root), "-c", "core.hooksPath=/dev/null"]
    git += ["-c", "commit.gpgsign=false", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-qm", message], check=True)


def test_the_freeze_reads_the_receipt_pin_as_committed_at_head(
    staged_board, monkeypatch
):
    """Export writes the pin; the freeze reads it as committed at HEAD. A pin
    never committed, or rewritten and not committed, is refused before any
    later gate; once committed, a pin that names another payload is refused
    too. Only the committed pin of this stage's receipt lets it through."""
    stage, _ = staged_board
    root = release.ROOT
    monkeypatch.setattr(driver, "committed_release_receipt", COMMITTED_RELEASE_RECEIPT)
    monkeypatch.setattr(driver, "ROOT", root)
    pin = root / "docs/gpt61sol/release_receipt.json"
    monkeypatch.setattr(driver, "RELEASE_RECEIPT", pin, raising=False)
    monkeypatch.setattr(driver, "verify_new_model_inputs", _reached("input gate"))
    pin.parent.mkdir(parents=True)
    payload = stage / "data-board46.json"
    record = {
        "note": "The stage's receipt.",
        "release_tag": driver.RELEASE_TAG,
        "payload_sha256": sha(payload),
        "release_ready_sha256": sha(stage / "release-ready.json"),
    }
    pin.write_text(json.dumps(record))
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)

    def freeze(match: str) -> None:
        before = workspace_files()
        with pytest.raises(SystemExit, match=match):
            release.main(["--stage-dir", str(stage), "--dry-run"])
        assert workspace_files() == before

    freeze("release_receipt.json is not committed at HEAD")
    _commit(root, "Pin the receipt")
    freeze("Reached the input gate")
    pin.write_text(json.dumps({**record, "payload_sha256": "0" * 64}))
    freeze("release_receipt.json differs from its HEAD commit; commit it")
    _commit(root, "Pin another payload")
    freeze("stage's \\['payload_sha256'\\] are not what")


def _edit_explanation(stage: Path) -> None:
    """Rewrite one case's written reference derivation in the staged file."""
    path = stage / EXPLANATIONS
    text = path.read_text()
    first = text.splitlines()[1]
    path.write_text(text.replace(first, first + " A sentence no review wrote.", 1))


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("receipt_entry", ["removed", "updated"])
def test_the_freeze_refuses_edited_reference_explanations(
    staged_board, receipt_entry, dry_run
):
    """The staged case reference explanations must be release 20260929's,
    byte for byte. Edited with its receipt entry removed, the file is unbound;
    edited with its entry re-hashed, it is not 20260929's. Either is refused
    before any workspace mutation."""
    stage, rebind = staged_board
    for name in driver.REFERENCE_FILES:
        shutil.copyfile(driver.SNAPSHOT / name, stage / BUNDLE / "us" / name)
    _edit_explanation(stage)
    rebind()
    if receipt_entry == "removed":
        receipt = json.loads((stage / "release-ready.json").read_text())
        del receipt["files"][str(EXPLANATIONS)]
        (stage / "release-ready.json").write_text(json.dumps(receipt))
        message = f"does not bind.*{re.escape(str(EXPLANATIONS))}"
    else:
        message = f"Staged {EXPLANATIONS_NAME} is not release 20260929's"
    before = workspace_files()
    with pytest.raises(SystemExit, match=message):
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    assert workspace_files() == before


def test_the_export_inputs_are_the_files_export_full_run_reads():
    assert driver.EXPORT_INPUTS == EXPORT_READS


@pytest.mark.parametrize("name", EXPORT_READS)
def test_the_rebuild_refuses_a_bundle_file_export_reads_and_the_receipt_omits(
    staged_board, rebuilds, name
):
    """A file export reads that the receipt does not bind is missing from the
    scratch copy. The rebuild refuses it before export_full_run runs: its
    loaders would read the working directory's committed annotations in the
    copy's place and rebuild the staged payload from other bytes."""
    stage, _ = staged_board
    receipt = json.loads((stage / "release-ready.json").read_text())
    del receipt["files"][str(BUNDLE / name)]
    payload = stage / "data-board46.json"
    with pytest.raises(SystemExit, match=f"the bundle lacks.*{re.escape(name)}"):
        release.rebuild_payload(
            stage, receipt, payload, driver.base_payload_from_commit()
        )
    assert rebuilds == []


JSON_LEAVES = st.none() | st.booleans() | st.integers() | st.text(max_size=3)
JSON_LEAVES |= st.floats(allow_nan=False, allow_infinity=False)
JSON_VALUES = st.recursive(
    JSON_LEAVES,
    lambda inner: (
        st.lists(inner, max_size=3)
        | st.dictionaries(st.sampled_from("abcd"), inner, max_size=3)
    ),
    max_leaves=12,
)


@settings(max_examples=400, deadline=None)
@given(a=JSON_VALUES, b=JSON_VALUES, swap=st.booleans())
def test_payload_differences_are_empty_exactly_when_the_bytes_match(a, b, swap):
    """The freeze refuses on bytes and names paths from the parsed values; the
    two agree, key order, 1 against 1.0, True against 1 and -0.0 included."""
    if swap and isinstance(a, dict):
        b = dict(reversed(list(a.items())))
    differ = release.payload_differences(a, b)
    assert (differ == []) == (json.dumps(a) == json.dumps(b))
    assert len(differ) <= 5


def test_payload_differences_name_the_first_differing_paths():
    rebuilt = {"rows": [{"model": "m", "x": 1, "y": [1, 2]}], "z": True}
    staged = {"z": 1, "rows": [{"model": "m", "y": [1], "x": 1.0, "w": 0}]}
    assert release.payload_differences(rebuilt, staged) == [
        "payload.rows[0 m].x",
        "payload.rows[0 m].y (length 2 rebuilt, 1 staged)",
        "payload.rows[0 m].w (only staged)",
        "payload.z",
        "payload (key order)",
    ]


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize(
    "defect", ["edited_kept", "edited_kept_sidecar", "unbound_new"]
)
def test_the_freeze_refuses_a_verdict_edited_after_export(
    staged_board, monkeypatch, defect, dry_run
):
    """Export validates the verdicts before it writes the receipt. A kept
    verdict edited afterwards, its classes kept, its sidecar and its receipt
    entry re-hashed, must still be refused before any workspace mutation; so
    must a verdict the seed does not carry that is bound to no prompt."""
    stage, rebind = staged_board
    for name in driver.REFERENCE_FILES:
        shutil.copyfile(driver.SNAPSHOT / name, stage / BUNDLE / "us" / name)
    case = stage / "audit/cases" / KEPT
    if defect == "edited_kept":
        verdict = json.loads((case / "verdict.json").read_text())
        verdict["rationale"] = "A rationale the judge never wrote."
        verdict["models"][0]["diagnosis"] = "A diagnosis the judge never wrote."
        (case / "verdict.json").write_text(json.dumps(verdict))
        meta = json.loads((case / "verdict.meta.json").read_text())
        meta["verdict_sha256"] = sha(case / "verdict.json")
        (case / "verdict.meta.json").write_text(json.dumps(meta))
        message = f"carried-over verdicts differ.*{KEPT}"
    elif defect == "edited_kept_sidecar":
        # The judge the snapshot manifest tallies, rewritten; the sidecar
        # still binds the seed's verdict bytes.
        meta = json.loads((case / "verdict.meta.json").read_text())
        meta["judge_model_requested"] = "claude-opus-5-5"
        (case / "verdict.meta.json").write_text(json.dumps(meta))
        message = f"carried-over verdicts differ.*{KEPT}.*sidecar is not the seed's"
    else:
        monkeypatch.setattr(driver, "load_seed", lambda stage: {})
        message = f"fail validation.*{KEPT}"
    rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match=message):
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    assert workspace_files() == before


def _double_cost(frame, rows) -> list[str]:
    columns = ["estimated_cost_usd", "total_cost_usd"]
    for column in columns:
        frame.loc[rows, column] = (frame.loc[rows, column].astype(float) * 2).map(str)
    return columns


def _slower(frame, rows) -> list[str]:
    frame.loc[rows, "elapsed_seconds"] = "99.0"
    return ["elapsed_seconds"]


USAGE_EDITS = {"cost": _double_cost, "elapsed_seconds": _slower}


def _edit_sol_rows(path: Path, edit) -> list[str]:
    import pandas as pd

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    columns = edit(frame, frame["model"] == SOL)
    frame.to_csv(path, index=False)
    return columns


def _republish_sol_usage(stage: Path, exports: dict) -> None:
    """The payload as export would rebuild it from the edited predictions:
    GPT-6.1 Sol's costUsd changes, and the export stub agrees."""
    payload = stage / "data-board46.json"
    board = json.loads(payload.read_text())
    for target in (board, exports["board"]):
        stats = target["countries"]["us"]["modelStats"]
        next(row for row in stats if row["model"] == SOL)["costUsd"] = 2.0
    payload.write_text(json.dumps(board))


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("edit", USAGE_EDITS)
def test_the_freeze_refuses_new_model_usage_edited_in_the_bundle(
    staged_board, exports, edit, dry_run
):
    """GPT-6.1 Sol's cost columns doubled, or its elapsed_seconds changed, in
    the bundle's predictions, with the payload rebuilt to match and every
    hash in the stage updated (the receipt's, stage.json's and
    model-provenance.json's), is refused before any workspace mutation: its
    rows must be its pinned run file's in every column."""
    stage, rebind = staged_board
    columns = _edit_sol_rows(stage / BUNDLE / "us/predictions.csv", USAGE_EDITS[edit])
    _republish_sol_usage(stage, exports)
    rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match="not the pinned run's") as refused:
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    for column in columns:
        assert f"{SOL} {column} differs from the run on 2 rows" in str(refused.value)
    assert workspace_files() == before


@pytest.mark.parametrize("dry_run", [True, False])
def test_the_freeze_refuses_a_new_model_input_edited_with_the_bundle(
    staged_board, exports, dry_run
):
    """The staged run file edited together with the bundle's rows, every
    stage hash following, is not the run file the committed pins name."""
    stage, rebind = staged_board
    for path in (
        stage / "inputs/gpt61sol/predictions.csv",
        stage / BUNDLE / "us/predictions.csv",
    ):
        _edit_sol_rows(path, _double_cost)
    _republish_sol_usage(stage, exports)
    rebind()
    before = workspace_files()
    with pytest.raises(
        SystemExit, match="staged inputs/gpt61sol/predictions.csv is not the run file"
    ):
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    assert workspace_files() == before


def _edit_json(path: Path, edit) -> None:
    value = json.loads(path.read_text())
    edit(value)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize(
    "defect",
    ["stale_stage_json", "unrecorded_input", "provenance_hash", "fingerprint"],
)
def test_the_freeze_rechecks_the_prepare_time_hashes(staged_board, defect):
    """stage.json and model-provenance.json, both bound by the receipt, must
    still describe the staged inputs."""
    stage, rebind = staged_board
    if defect == "stale_stage_json":
        path = stage / BUNDLE / "us/predictions.csv"
        path.write_text(path.read_text().replace(INCUMBENT_ROW, INCUMBENT_ROW * 2))
        message = f"changed since prepare: {BUNDLE}/us/predictions.csv"
    elif defect == "unrecorded_input":
        _edit_json(
            stage / "stage.json",
            lambda record: record["files"].pop("inputs/gpt61sol/predictions.csv"),
        )
        message = "stage.json does not record.*inputs/gpt61sol/predictions.csv"
    elif defect == "provenance_hash":
        _edit_json(
            stage / "model-provenance.json",
            lambda record: record[SOL].update(predictions_sha256="0" * 64),
        )
        message = "model-provenance.json disagrees with the staged run"
    else:
        _edit_json(
            stage / "model-provenance.json",
            lambda record: record[SOL]["treatment_fingerprint"].update(
                request_timeout_seconds=600
            ),
        )
        message = "model-provenance.json disagrees with the staged run"
    rebind(restamp_stage=False)
    before = workspace_files()
    with pytest.raises(SystemExit, match=message):
        release.main(["--stage-dir", str(stage), "--dry-run"])
    assert workspace_files() == before


def _publish_annotations(stage: Path) -> None:
    """The row annotations and case notes triage publishes for the synthetic
    audit, with a staged record that decides none of its cases."""
    from policybench.audit import collect_audit

    annotations = stage / BUNDLE / "annotations"
    (annotations / "us_adjudications.json").write_text(
        json.dumps({"adjudications": []})
    )
    collected = collect_audit(stage / BUNDLE / "us", stage / "audit")
    cases = collected["case"].rename(
        columns={
            "case_failure_source": "case_failure_sources",
            "case_failure_subtype": "case_failure_subtypes",
        }
    )
    for name, frame in (
        ("us_audit_row_annotations.csv", collected["row"]),
        ("us_case_notes.csv", cases),
    ):
        frame.to_csv(annotations / name, index=False)


@pytest.fixture
def annotated_board(staged_board, monkeypatch):
    """The synthetic stage with 20260929's references and the annotations
    triage publishes, past every gate up to the annotation gate; the next
    gate, the incumbents' predictions, stops the freeze. The kept case is
    decided by no adjudication. The record gate reads the committed record's
    69 cases, which the synthetic audit lacks; it is tested on its own."""
    stage, rebind = staged_board
    for name in driver.REFERENCE_FILES:
        shutil.copyfile(driver.SNAPSHOT / name, stage / BUNDLE / "us" / name)
    monkeypatch.setattr(release, "verify_adjudication_record", lambda *a, **k: 0)
    _publish_annotations(stage)

    def next_gate():
        raise SystemExit("Reached the prediction gate")

    monkeypatch.setattr(release, "base_prediction_rows", next_gate)
    rebind()
    return stage, rebind


def test_the_annotations_triage_publishes_pass_the_annotation_gate(annotated_board):
    stage, _ = annotated_board
    with pytest.raises(SystemExit, match="Reached the prediction gate"):
        release.main(["--stage-dir", str(stage), "--dry-run"])


@pytest.mark.parametrize("dry_run", [True, False])
def test_the_freeze_refuses_a_failure_class_no_judge_gave(
    annotated_board, exports, dry_run
):
    """A row's failure_source and its case note's case_failure_sources changed
    on the kept case, which no adjudication decides, with the payload rebuilt
    to carry the new class (export's rebuild agrees) and the receipt hashes
    of both CSVs and the payload updated, are refused before any workspace
    mutation."""
    import pandas as pd

    stage, rebind = annotated_board
    annotations = stage / BUNDLE / "annotations"
    for name, column in (
        ("us_audit_row_annotations.csv", "failure_source"),
        ("us_case_notes.csv", "case_failure_sources"),
    ):
        frame = pd.read_csv(annotations / name, dtype=str, keep_default_na=False)
        kept = frame.scenario_id == "scenario_000"
        assert list(frame.loc[kept, column]) == ["llm_error"]
        frame.loc[kept, column] = "prompt_ambiguity"
        frame.to_csv(annotations / name, index=False)
    payload = stage / "data-board46.json"
    board = json.loads(payload.read_text())
    scenario, variable = CASE
    for target in (board, exports["board"]):
        for row in target["countries"]["us"]["scenarioPredictions"][scenario][
            variable
        ].values():
            row.update(
                failureSource="prompt_ambiguity", caseFailureSources="prompt_ambiguity"
            )
    payload.write_text(json.dumps(board))
    rebind()
    before = workspace_files()
    with pytest.raises(
        SystemExit,
        match=r"us_case_notes\.csv is not what triage builds.*"
        r"us__scenario_000__snap case_failure_sources",
    ):
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    assert workspace_files() == before


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
        driver.record_text(record)
    )
    rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match="drop recorded decisions"):
        release.main(["--stage-dir", str(stage)])
    assert workspace_files() == before


def test_the_freeze_baseline_is_release_20260929_in_git_not_the_working_tree(
    staged_board, monkeypatch
):
    """A freeze that stopped after copying the staged record over the committed
    one leaves them equal; the next freeze must still compare with git."""
    import freeze_snapshot as freezer

    stage, rebind = staged_board
    monkeypatch.setattr(freezer, "ANNOTATIONS_DEST", release.ROOT / "annotations" / RUN)
    for name in driver.REFERENCE_FILES:
        shutil.copyfile(driver.SNAPSHOT / name, stage / BUNDLE / "us" / name)
    record = json.loads(COMMITTED_ADJUDICATIONS.read_text())
    record["adjudications"].pop(0)
    staged = stage / BUNDLE / "annotations/us_adjudications.json"
    staged.write_text(driver.record_text(record))
    rebind()
    # What a partial freeze leaves behind: the working-tree record is the
    # staged one, byte for byte.
    freezer.ANNOTATIONS_DEST.mkdir(parents=True)
    shutil.copyfile(staged, freezer.ANNOTATIONS_DEST / "us_adjudications.json")
    with pytest.raises(SystemExit, match="drop recorded decisions"):
        release.main(["--stage-dir", str(stage), "--dry-run"])


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
    """Release 20260929's record, from git at BASE_COMMIT: the baseline every
    staged record is checked against, before and after this release's freeze."""
    staged = tmp_path / "us_adjudications.json"
    staged.write_bytes(
        driver.base_commit_blob(COMMITTED_ADJUDICATIONS.relative_to(driver.ROOT))
    )
    record = json.loads(staged.read_text())
    return staged, record


def _write(path, record):
    path.write_text(driver.record_text(record))


def _case(entry):
    return f"{entry['country']}__{entry['scenario_id']}__{entry['variable']}"


def _verify(staged, rejudged=frozenset(), amendments=()):
    return release.verify_adjudication_record(
        staged, driver.SNAPSHOT, frozenset(rejudged), list(amendments)
    )


def test_the_committed_record_is_release_20260929s_restated_where_reopened(
    tmp_path,
):
    """The record the freeze committed is release 20260929's, changed only
    where GPT-6.1 Sol re-opened a case (the cases the committed judge
    provenance record lists), only in judge fields and by the committed
    wording amendments, and with no decision added."""
    reopened = frozenset(
        entry["case_id"]
        for entry in json.loads(driver.JUDGE_PROVENANCE.read_text())["verdicts"]
    )
    stage = tmp_path / "stage"
    stage.mkdir()
    shutil.copyfile(
        driver.ANNOTATIONS / f"us_{driver.AMENDMENTS}", stage / driver.AMENDMENTS
    )
    amendments = driver.load_amendments(stage, reopened)
    assert len(amendments) == 394
    assert _verify(COMMITTED_ADJUDICATIONS, reopened, amendments) == 0
    committed = json.loads(COMMITTED_ADJUDICATIONS.read_text())["adjudications"]
    assert committed != driver.base_adjudications()


def test_an_unchanged_adjudication_record_passes(adjudications):
    staged, _ = adjudications
    assert _verify(staged) == 0


def test_triage_may_add_a_decision_that_keeps_the_output_scored(adjudications):
    staged, record = adjudications
    scored = next(
        e for e in record["adjudications"] if not e.get("excluded_from_scoring")
    )
    added = {**copy.deepcopy(scored), "scenario_id": "scenario_999"}
    record["adjudications"].append(added)
    _write(staged, record)
    assert _verify(staged, rejudged={_case(added)}) == 1
    # A decision on a case GPT-6.1 Sol did not re-open has no reason to appear.
    with pytest.raises(SystemExit, match="did not re-open"):
        _verify(staged)


def test_a_rejudged_case_may_be_restated(adjudications):
    staged, record = adjudications
    entry = record["adjudications"][0]
    entry["judge_failure_subtype"] = "thresholds_rates"
    entry["judge_rejudged_on"] = "2026-09-30"
    entry.setdefault("judge_previous", []).append(
        {"judge_model": "claude-opus-5-5", "judged_on": "2026-09-29"}
    )
    _write(staged, record)
    assert _verify(staged, rejudged={_case(entry)}) == 0


@pytest.mark.parametrize(
    "edit",
    ["judge_class", "decision_class", "reasoning", "decision_order", "entry_order"],
)
def test_a_rewrite_of_an_incumbent_only_case_is_refused(adjudications, edit):
    """No field of a case GPT-6.1 Sol did not re-open may change, key order and
    entry order included; a re-opened case may change its judge fields only."""
    staged, record = adjudications
    entries = record["adjudications"]
    entry = entries[0]
    rejudged = set()
    if edit == "judge_class":
        entry["judge_failure_subtype"] = "thresholds_rates"
    elif edit == "decision_class":
        entry["adjudicated_failure_subtype"] = "other"
        rejudged = {_case(entry)}
    elif edit == "reasoning":
        entry["reasoning"] += " Restated."
        rejudged = {_case(entry)}
    elif edit == "decision_order":
        entries[0] = dict(reversed(list(entry.items())))
        rejudged = {_case(entry)}
    else:
        entries[0], entries[1] = entries[1], entries[0]
    _write(staged, record)
    with pytest.raises(SystemExit, match="change recorded decisions|entry order"):
        _verify(staged, rejudged=rejudged)


def test_a_dropped_decision_is_refused(adjudications):
    staged, record = adjudications
    record["adjudications"].pop()
    _write(staged, record)
    with pytest.raises(SystemExit, match="drop recorded decisions"):
        _verify(staged)


def test_a_new_exclusion_is_refused(adjudications):
    staged, record = adjudications
    excluded = next(
        e for e in record["adjudications"] if e.get("excluded_from_scoring")
    )
    added = {**copy.deepcopy(excluded), "scenario_id": "scenario_999"}
    record["adjudications"].append(added)
    _write(staged, record)
    with pytest.raises(SystemExit, match="change the scoring exclusions"):
        _verify(staged, rejudged={_case(added)})


def test_the_committed_record_is_in_the_form_the_gate_requires():
    text = COMMITTED_ADJUDICATIONS.read_text()
    driver.verify_record_form(text, driver.base_adjudication_record())
    assert text == driver.record_text(json.loads(text))


@pytest.mark.parametrize("defect", ["duplicate_key", "note", "conventions", "compact"])
def test_bytes_the_entry_gate_cannot_see_are_refused(adjudications, defect):
    """A duplicate key hides text a parser drops; the note and conventions are
    outside the entries; a record in another layout could hide either."""
    staged, record = adjudications
    text = driver.record_text(record)
    if defect == "duplicate_key":
        text = text.replace(
            '"adjudicator": "developer"',
            '"adjudicator": "SMUGGLED", "adjudicator": "developer"',
            1,
        )
    elif defect == "note":
        record["note"] = "Rewritten."
        text = driver.record_text(record)
    elif defect == "conventions":
        record["date_conventions"] = {}
        text = driver.record_text(record)
    else:
        text = json.dumps(record)
    staged.write_text(text)
    assert load_entries(staged) == driver.base_adjudications() or (
        defect in ("note", "conventions")
    )
    with pytest.raises(SystemExit, match="committed form|only entries may change"):
        _verify(staged)


def load_entries(path):
    from policybench.adjudications import load_adjudications

    return load_adjudications(path)


def _restated(entry, day="2026-09-30"):
    return {
        **entry,
        "judge_failure_subtype": "thresholds_rates",
        "judge_rejudged_on": day,
        "judge_previous": [
            *entry.get("judge_previous", []),
            {
                "judge_model": entry["judge_model"],
                "judge_failure_source": entry["judge_failure_source"],
                "judge_failure_subtype": entry["judge_failure_subtype"],
                "judge_reference_suspect": bool(entry.get("judge_reference_suspect")),
                "judged_on": "2026-09-29",
            },
        ],
        **({"judged_on_utc": day} if "judged_on_utc" in entry else {}),
    }


@pytest.fixture
def restated(tmp_path):
    """A re-opened entry restated as the restate script does, with its verdict."""
    base = driver.base_adjudications()
    entry = next(
        e
        for e in base
        if e["judge_model"] == driver.JUDGE_MODEL and e.get("judge_previous")
    )
    cases = tmp_path / "cases"
    case = cases / _case(entry)
    case.mkdir(parents=True)
    verdict = case / "verdict.json"
    verdict.write_text('{"case_failure_source": "llm_error"}')
    (case / "verdict.meta.json").write_text(
        json.dumps(
            {
                "verdict_sha256": sha(verdict),
                "judge_model_requested": driver.JUDGE_MODEL,
                "judge_model_reported": [driver.JUDGE_MODEL],
                "judged_at_utc": "2026-09-30T05:10:00+00:00",
            }
        )
    )
    staged = [_restated(e) if e is entry else e for e in base]
    return (
        base,
        staged,
        frozenset({_case(entry)}),
        cases,
        staged.index(next(e for e in staged if _case(e) == _case(entry))),
    )


def test_a_restated_entry_passes_the_restatement_check(restated):
    base, staged, rejudged, cases, _ = restated
    driver.verify_restatements(base, staged, rejudged, cases)


# Each rewrites the appended item: the verdict the re-judge replaced must stay
# the one 20260929's entry names, as its seed sidecar records it.
APPENDED_ITEM_TAMPERS = {
    "appended_judged_on": {"judged_on": "2026-09-28"},
    "appended_class": {"judge_failure_source": "reference_error"},
    "appended_subtype": {"judge_failure_subtype": "thresholds_rates"},
    "appended_flag": {"judge_reference_suspect": True},
    "appended_judge": {"judge_model": "claude-opus-5"},
    "appended_flag_source": {"judge_reference_suspect_source": "a-human-typed-this"},
}


@pytest.mark.parametrize(
    "tamper",
    [
        "judge_model",
        "emptied_history",
        "two_items",
        "rewritten_history",
        "day",
        *APPENDED_ITEM_TAMPERS,
    ],
)
def test_judge_fields_written_by_hand_are_refused(restated, tamper):
    base, staged, rejudged, cases, index = restated
    entry = copy.deepcopy(staged[index])
    if tamper == "judge_model":
        entry["judge_model"] = "a-human-typed-this"
    elif tamper == "emptied_history":
        entry["judge_previous"] = []
    elif tamper == "two_items":
        entry["judge_previous"] = entry["judge_previous"] + entry["judge_previous"][-1:]
    elif tamper == "rewritten_history":
        entry["judge_previous"][0] = {**entry["judge_previous"][0], "judged_on": "1999"}
    elif tamper in APPENDED_ITEM_TAMPERS:
        appended = entry["judge_previous"][-1]
        edit = APPENDED_ITEM_TAMPERS[tamper]
        assert all(appended.get(k) != v for k, v in edit.items())
        entry["judge_previous"][-1] = {**appended, **edit}
    else:
        entry["judge_rejudged_on"] = "1999-01-01"
    staged[index] = entry
    with pytest.raises(SystemExit, match="not restated by the restate script"):
        driver.verify_restatements(base, staged, rejudged, cases)


# The September 22c record's wording for a flag an earlier judge run raised
# (FLAG_SOURCE_EARLIER_RUN in scripts/date_adds0928_judge_verdicts.py).
EARLIER_RUN = (
    "an earlier judge run in the 2026-09-22 wave (flagged_sept22_wave.json); "
    "the case's current verdict.json does not flag it"
)
# Each: the current verdict's own flag, whether the 2026-09-22 wave flagged
# the case, the entry's top-level flag and its source, and whether the gate
# passes it. The flag is raised when the verdict or the wave raised it, and
# names a source exactly when the wave alone did.
REFERENCE_FLAGS = {
    "raised_with_a_source_the_verdict_does_not_raise": (
        False,
        False,
        True,
        EARLIER_RUN,
        False,
    ),
    "raised_with_no_source_the_verdict_does_not_raise": (
        False,
        False,
        True,
        None,
        False,
    ),
    "lowered_as_the_verdict_says": (False, False, False, None, True),
    "raised_as_the_verdict_says": (True, False, True, None, True),
    "lowered_against_the_verdict": (True, False, False, None, False),
    "raised_by_the_verdict_naming_an_earlier_run": (
        True,
        False,
        True,
        EARLIER_RUN,
        False,
    ),
    "raised_by_the_wave_alone_and_sourced": (False, True, True, EARLIER_RUN, True),
    "raised_by_the_wave_alone_unsourced": (False, True, True, None, False),
    "raised_by_the_wave_alone_in_other_words": (
        False,
        True,
        True,
        "a-human-typed-this",
        False,
    ),
    "lowered_against_the_wave": (False, True, False, None, False),
    "raised_by_both": (True, True, True, None, True),
    "raised_by_both_naming_an_earlier_run": (True, True, True, EARLIER_RUN, False),
}


def _judge_verdict(cases: Path, case: str, flag: bool) -> None:
    """The case's current verdict with its own reference flag, its sidecar
    re-bound to it."""
    verdict = cases / case / "verdict.json"
    verdict.write_text(
        json.dumps({"case_failure_source": "llm_error", "reference_suspect": flag})
    )
    meta = json.loads(verdict.with_name("verdict.meta.json").read_text())
    meta["verdict_sha256"] = sha(verdict)
    verdict.with_name("verdict.meta.json").write_text(json.dumps(meta))


def _flagged(entry: dict, flag: bool, source: str | None) -> dict:
    entry = {**entry, "judge_reference_suspect": flag}
    entry.pop("judge_reference_suspect_source", None)
    if source is not None:
        entry["judge_reference_suspect_source"] = source
    return entry


@pytest.mark.parametrize("name", REFERENCE_FLAGS)
def test_a_restated_entrys_reference_flag_is_the_current_verdicts(
    restated, monkeypatch, name
):
    """The restate script writes a re-opened entry's top-level flag from the
    current verdict and the 2026-09-22 wave; a flag the verdict does not
    raise, named to an earlier run the wave does not record, is refused. The
    gate reads the wave from BASE_COMMIT (stubbed here)."""
    verdict_flag, waved, flag, source, passes = REFERENCE_FLAGS[name]
    base, staged, rejudged, cases, index = restated
    entry = _flagged(staged[index], flag, source)
    staged[index] = entry
    _judge_verdict(cases, _case(entry), verdict_flag)
    key = f"{entry['scenario_id']}:{entry['variable']}"
    wave = frozenset({key} if waved else ())
    monkeypatch.setattr(driver, "base_wave_flags", lambda: wave, raising=False)
    if passes:
        driver.verify_restatements(base, staged, rejudged, cases)
        return
    with pytest.raises(SystemExit, match=f"{_case(entry)}: its reference flag"):
        driver.verify_restatements(base, staged, rejudged, cases)


@pytest.mark.parametrize("verdict_flag", [False, True])
def test_an_unrestated_reopened_entry_must_carry_the_current_verdicts_flag(
    restated, verdict_flag
):
    """A re-opened entry left as 20260929's wrote it is checked too: its flag
    must be the one the current verdict gives it."""
    base, staged, rejudged, cases, index = restated
    at = next(i for i, e in enumerate(base) if _case(e) == _case(staged[index]))
    _judge_verdict(cases, _case(base[at]), verdict_flag)
    # 20260929's entry, unrestated, with the flag the verdict does not give.
    base[at] = staged[index] = _flagged(base[at], not verdict_flag, None)
    with pytest.raises(SystemExit, match="its reference flag"):
        driver.verify_restatements(
            base, staged, rejudged, cases, wave_flags=frozenset()
        )
    base[at] = staged[index] = _flagged(base[at], verdict_flag, None)
    driver.verify_restatements(base, staged, rejudged, cases, wave_flags=frozenset())


@pytest.mark.parametrize(
    "original, source, passes",
    [
        (None, EARLIER_RUN, True),
        (None, "claude-opus-5-5 judge run adjudicated 2026-09-22", False),
        ("claude-opus-5-5 judge run adjudicated 2026-09-22", EARLIER_RUN, True),
        (
            "claude-opus-5-5 judge run adjudicated 2026-09-22",
            "claude-opus-5-5 judge run adjudicated 2026-09-22",
            True,
        ),
        (
            "claude-opus-5-5 judge run adjudicated 2026-09-22",
            "a-human-typed-this",
            False,
        ),
    ],
)
def test_a_named_flag_source_keeps_20260929s_wording_or_the_restate_scripts(
    original, source, passes
):
    """A flag the wave alone raised names its source in the wording 20260929's
    entry gave it, or in the restate script's FLAG_SOURCE_EARLIER_RUN, which
    a restatement writes where the entry has none (a case whose first
    re-judge flagged the reference loses its source, and a later re-judge
    that does not restores the restate script's)."""
    first = {} if original is None else {"judge_reference_suspect_source": original}
    entry = {"judge_reference_suspect": True, "judge_reference_suspect_source": source}
    problem = driver.reference_flag_problem(entry, first, False, True)
    assert (problem is None) == passes


def test_the_gate_reads_the_restate_scripts_wave_flags_from_git():
    """The restate script's --wave-flags default is the file the gate reads
    at BASE_COMMIT, and the working tree's copy is unchanged."""
    import date_adds0928_judge_verdicts as dates
    import restate_gpt61sol_adjudications as restate

    assert restate.WAVE_FLAGS == dates.WAVE_FLAGS
    assert dates.WAVE_FLAGS == driver.ROOT / driver.WAVE_FLAGS_PATH
    assert driver.base_wave_flags() == frozenset(
        json.loads(dates.WAVE_FLAGS.read_text())
    )
    assert restate.FLAG_SOURCE_EARLIER_RUN == EARLIER_RUN


def test_the_stages_restated_entries_pass_the_restatement_check():
    """Local only: every re-opened entry of the staged record, each restated
    by the restate script, passes the gate against the stage's verdicts."""
    from policybench.adjudications import load_adjudications

    stage = driver.ROOT / "results/local/gpt61sol-v1"
    if not (stage / "audit/cases").is_dir():
        pytest.skip("needs the GPT-6.1 Sol stage")
    changes = json.loads((stage / driver.PROMPT_CHANGES).read_text())
    rejudged = frozenset(changes["changed"]) | frozenset(changes["added"])
    staged = load_adjudications(stage / BUNDLE / "annotations/us_adjudications.json")
    assert sum(_case(entry) in rejudged for entry in staged) == 54
    driver.verify_restatements(
        driver.base_adjudications(), staged, rejudged, stage / "audit/cases"
    )


def test_the_freeze_reads_20260929_predictions_and_serving_from_git(monkeypatch):
    import gzip

    blobs = {}

    def blob(path):
        blobs[str(path)] = True
        if path.name == "predictions.csv.gz":
            return gzip.compress(b"model,scenario_id,variable,prediction\nm,s,v,1\n")
        return json.dumps({"models": {"m": {}}}).encode()

    monkeypatch.setattr(driver, "base_commit_blob", blob)
    assert list(release.base_prediction_rows().model) == ["m"]
    assert release.base_serving_config() == {"models": {"m": {}}}
    assert blobs == {
        f"paper/snapshot/20260501/runs/{RUN}/predictions.csv.gz": True,
        "paper/snapshot/20260501/model_serving_config.json": True,
    }


BASE_ENTRIES = None


def _base_entries():
    global BASE_ENTRIES
    if BASE_ENTRIES is None:
        BASE_ENTRIES = driver.base_adjudications()
    return copy.deepcopy(BASE_ENTRIES)


@settings(max_examples=200, deadline=None)
@given(
    index=st.integers(min_value=0, max_value=68),
    pick=st.integers(min_value=0, max_value=10**6),
    mutation=st.sampled_from(
        ["value", "delete", "add_decision_key", "add_judge_key", "swap_decisions"]
    ),
    reopened=st.booleans(),
)
def test_the_gate_allows_exactly_the_judge_fields_of_reopened_cases(
    index, pick, mutation, reopened
):
    """For every entry and every kind of single change: a change to a judge
    field passes only where the case is re-opened; any other change fails."""
    from restate_gpt61sol_adjudications import JUDGE_FIELDS

    base = _base_entries()
    staged = copy.deepcopy(base)
    entry = staged[index]
    keys = list(entry)
    judge = mutation == "add_judge_key"
    if mutation in ("value", "delete"):
        key = keys[pick % len(keys)]
        judge = key in JUDGE_FIELDS
        if key in ("country", "scenario_id", "variable"):
            return  # a different case key is a dropped plus an added entry
        if mutation == "delete":
            del entry[key]
        else:
            entry[key] = [entry[key], "mutated"]
    elif mutation == "add_decision_key":
        entry["x_extra"] = "added"
    elif mutation == "add_judge_key":
        if "judged_on_utc" in entry:
            del entry["judged_on_utc"]
        else:
            entry["judged_on_utc"] = "2026-09-30"
    else:
        decisions = [k for k in keys if k not in JUDGE_FIELDS]
        first = decisions[pick % (len(decisions) - 1)]
        second = decisions[decisions.index(first) + 1]
        items = list(entry.items())
        i, j = keys.index(first), keys.index(second)
        items[i], items[j] = items[j], items[i]
        staged[index] = entry = dict(items)
    rejudged = frozenset({_case(entry)}) if reopened else frozenset()
    if reopened and judge:
        assert driver.verify_adjudication_changes(base, staged, rejudged, []) == 0
    else:
        with pytest.raises(SystemExit, match="change recorded decisions"):
            driver.verify_adjudication_changes(base, staged, rejudged, [])


# --- Wording amendments --------------------------------------------------------


def _amendment(entry, old, new, field="reasoning", **extra):
    return {
        "case_id": _case(entry),
        "field": field,
        "old": old,
        "new": new,
        "reason": "The re-judge replaced the verdict this sentence describes.",
        **extra,
    }


def test_a_listed_wording_amendment_is_allowed_and_nothing_else(adjudications):
    staged, record = adjudications
    entry = record["adjudications"][0]
    old = entry["reasoning"].split(". ")[0]
    amendment = _amendment(entry, old, old + ", as restated")
    entry["reasoning"] = entry["reasoning"].replace(old, old + ", as restated")
    _write(staged, record)
    assert _verify(staged, {_case(entry)}, [amendment]) == 0
    # Unlisted, the same change is refused.
    with pytest.raises(SystemExit, match="change recorded decisions"):
        _verify(staged, {_case(entry)})
    # Listed but not applied, it is refused too: the list is exact.
    shutil.copyfile(COMMITTED_ADJUDICATIONS, staged)
    with pytest.raises(SystemExit, match="change recorded decisions"):
        _verify(staged, {_case(entry)}, [amendment])
    # Any other change beside it is still refused.
    entry["adjudicated_on"] = "2026-09-30"
    _write(staged, record)
    with pytest.raises(SystemExit, match="change recorded decisions"):
        _verify(staged, {_case(entry)}, [amendment])


@pytest.fixture
def amendment_stage(tmp_path, adjudications):
    _, record = adjudications
    entry = record["adjudications"][0]
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / driver.PROMPT_CHANGES).write_text(
        json.dumps({"added": [], "changed": [_case(entry)], "kept": []})
    )

    def write(*items):
        (stage / driver.AMENDMENTS).write_text(json.dumps({"amendments": items}))
        return driver.load_amendments(stage, frozenset({_case(entry)}))

    return entry, write


def test_load_amendments_accepts_wording_of_rejudged_cases(amendment_stage):
    entry, write = amendment_stage
    items = [
        _amendment(entry, "a", "b"),
        _amendment(entry, "a", "b", field="case_annotation"),
        _amendment(entry, "a", "b", field="annotation", model="gpt-6.1-sol"),
    ]
    assert write(*items) == items


@pytest.mark.parametrize(
    "defect, message",
    [
        ({"field": "adjudicated_failure_source"}, "not wording"),
        ({"field": "excluded_from_scoring"}, "not wording"),
        ({"field": "judge_failure_source"}, "not wording"),
        ({"case_id": "us__scenario_999__snap"}, "not re-judged"),
        ({"reason": " "}, "reason"),
        ({"new": None}, "new"),
        ({"old": ""}, "old"),
        ({"new": "same", "old": "same"}, "changes nothing"),
        ({"model": "gpt-6.1-sol"}, "keys"),
        ({"field": "annotation"}, "keys"),
    ],
)
def test_load_amendments_refuses_anything_but_wording_of_rejudged_cases(
    amendment_stage, defect, message
):
    entry, write = amendment_stage
    with pytest.raises(SystemExit, match=message):
        write({**_amendment(entry, "a", "b"), **defect})


# One re-opened, decided case: its verdict's rationale and diagnoses are the
# sources triage folds into the published case note and row annotations.
WORDING_CASE = "us__scenario_001__snap"
RATIONALE = "The model applied an outdated threshold."
DIAGNOSES = {"m1": "It left out A. More.", "m2": "It used last year's threshold."}
DECISION = {
    "country": "us",
    "scenario_id": "scenario_001",
    "variable": "snap",
    "judge_model": "claude-opus-5-5",
    "judge_failure_source": "llm_error",
    "judge_failure_subtype": "thresholds_rates",
    "adjudicated_failure_source": "llm_error",
    "adjudicated_failure_subtype": "thresholds_rates",
    "adjudicated_on": "2026-09-30",
    "adjudicator": "developer",
    "reasoning": "The threshold is the current year's.",
}


def _row_amendment(old, new, model="m1"):
    return {
        "case_id": WORDING_CASE,
        "field": "annotation",
        "model": model,
        "old": old,
        "new": new,
        "reason": "r",
    }


def _note_amendment(old, new):
    return {
        "case_id": WORDING_CASE,
        "field": "case_annotation",
        "old": old,
        "new": new,
        "reason": "r",
    }


# A later amendment rewrites words an earlier one wrote.
CHAINED = [
    _row_amendment("It left out A.", "It left out A, as B does."),
    _row_amendment("as B does", "as the corrected B does"),
    _note_amendment("an outdated", "the prior year's"),
]
# What triage publishes with CHAINED applied, spelled out by hand.
PUBLISHED = {
    "m1": "It left out A, as the corrected B does. More.",
    "m2": DIAGNOSES["m2"],
    "note": "The model applied the prior year's threshold."
    + " Developer adjudication (2026-09-30): the judge (claude-opus-5-5) returned "
    "llm_error; adjudicated llm_error (thresholds_rates). The threshold is the "
    "current year's.",
}


# What triage publishes on the case with CHAINED applied when no adjudication
# decides it: the case note is the amended rationale alone.
UNDECIDED = {**PUBLISHED, "note": "The model applied the prior year's threshold."}


def _wording_stage(tmp_path, published, decided=True):
    """An audit with the case's verdict, the staged record deciding it (or,
    with ``decided`` false, deciding nothing), and the published case note
    and row annotations ``published`` spells, every column as triage writes
    it: the verdict's classes, which the decision affirms, beside the text."""
    import pandas as pd

    from policybench.adjudications import adjudication_sentence

    assert PUBLISHED["note"].endswith(adjudication_sentence(DECISION))
    audit = tmp_path / "audit"
    (audit / "cases" / WORDING_CASE).mkdir(parents=True)
    keys = {"country": "us", "scenario_id": "scenario_001", "variable": "snap"}
    (audit / "cases.jsonl").write_text(
        json.dumps(
            {
                "case_id": WORDING_CASE,
                "scenario_id": keys["scenario_id"],
                "variable": keys["variable"],
                "wrong_models": list(DIAGNOSES),
                "parse_failure_only": False,
            }
        )
        + "\n"
    )
    verdict = {
        "reference_suspect": False,
        "reference_bug_hypothesis": "",
        "case_failure_source": "llm_error",
        "case_failure_subtype": "thresholds_rates",
        "rationale": RATIONALE,
        "models": [
            {
                "model": model,
                "failure_source": "llm_error",
                "failure_subtype": "thresholds_rates",
                "diagnosis": diagnosis,
            }
            for model, diagnosis in DIAGNOSES.items()
        ],
    }
    (audit / "cases" / WORDING_CASE / "verdict.json").write_text(json.dumps(verdict))
    annotations = tmp_path / "publish" / RUN / "annotations"
    annotations.mkdir(parents=True)
    (annotations / "us_adjudications.json").write_text(
        json.dumps({"adjudications": [DECISION] if decided else []})
    )
    classes = {"failure_source": "llm_error", "failure_subtype": "thresholds_rates"}
    pd.DataFrame(
        [
            {
                **keys,
                "model": model,
                **classes,
                "reference_suspect": False,
                "annotation": published[model],
            }
            for model in DIAGNOSES
            if model in published
        ]
    ).to_csv(annotations / "us_audit_row_annotations.csv", index=False)
    note = {
        **keys,
        "wrong_model_count": len(DIAGNOSES),
        "case_failure_sources": "llm_error",
        "case_failure_subtypes": "thresholds_rates",
        "reference_suspect": False,
        "reference_bug_hypothesis": "",
        "case_annotation": published["note"],
    }
    pd.DataFrame([note]).to_csv(annotations / "us_case_notes.csv", index=False)
    return annotations, audit


def test_the_freeze_replays_chained_amendments_onto_the_sources(tmp_path):
    """Each text is rebuilt from its verdict source and the adjudication
    sentence, the amendments replayed in order; the full result must be the
    published text, and a text no amendment names must be its source."""
    annotations, audit = _wording_stage(tmp_path, PUBLISHED)
    release.verify_annotation_amendments(annotations, CHAINED, audit)


@pytest.mark.parametrize(
    "published, amendments",
    [
        # The listed fragment is present, beside wording nobody listed.
        ({**PUBLISHED, "m1": PUBLISHED["m1"] + " Unlisted."}, CHAINED),
        ({**PUBLISHED, "note": "Unlisted. " + PUBLISHED["note"]}, CHAINED),
        # A text no amendment names, reworded.
        ({**PUBLISHED, "m2": "It used an unlisted threshold."}, CHAINED),
        ({**PUBLISHED, "m2": DIAGNOSES["m2"] + " Unlisted."}, CHAINED),
        # With no amendments at all, every text is still checked.
        ({**PUBLISHED, "m1": DIAGNOSES["m1"] + " Unlisted."}, []),
        # A listed amendment not applied, or only half of a chain.
        ({**PUBLISHED, "m1": DIAGNOSES["m1"]}, CHAINED),
        ({**PUBLISHED, "m1": "It left out A, as B does. More."}, CHAINED),
        # A published row annotation dropped.
        ({key: text for key, text in PUBLISHED.items() if key != "m2"}, CHAINED),
    ],
)
def test_the_freeze_refuses_wording_the_amendments_do_not_produce(
    tmp_path, published, amendments
):
    annotations, audit = _wording_stage(tmp_path, published)
    with pytest.raises(SystemExit, match="is not what triage builds"):
        release.verify_annotation_amendments(annotations, amendments, audit)


def test_each_replayed_old_text_must_occur_once_when_applied(tmp_path):
    """The first amendment makes the second's old text occur twice."""
    twice = [
        _row_amendment("It left out A.", "It left out A. A."),
        _row_amendment("A.", "B."),
    ]
    annotations, audit = _wording_stage(
        tmp_path, {**PUBLISHED, "m1": "It left out B. A. More."}
    )
    with pytest.raises(SystemExit, match="occurs 2 times"):
        release.verify_annotation_amendments(annotations, twice, audit)


def test_an_undecided_case_publishes_its_verdict_sources(tmp_path):
    annotations, audit = _wording_stage(tmp_path, UNDECIDED, decided=False)
    release.verify_annotation_amendments(annotations, CHAINED, audit)


# Each column triage publishes beside the wording, changed on the case: its
# rows' classes and flag, and its note's classes, flag, count and hypothesis.
COLUMN_EDITS = [
    ("us_audit_row_annotations.csv", "failure_source", "prompt_ambiguity"),
    ("us_audit_row_annotations.csv", "failure_subtype", "missing_output"),
    ("us_audit_row_annotations.csv", "reference_suspect", "True"),
    ("us_case_notes.csv", "case_failure_sources", "prompt_ambiguity"),
    ("us_case_notes.csv", "case_failure_subtypes", "missing_output"),
    ("us_case_notes.csv", "reference_suspect", "True"),
    ("us_case_notes.csv", "wrong_model_count", "3"),
    ("us_case_notes.csv", "reference_bug_hypothesis", "The reference is wrong."),
]


@pytest.mark.parametrize("decided", [False, True])
@pytest.mark.parametrize("name, column, value", COLUMN_EDITS)
def test_the_freeze_refuses_any_column_triage_did_not_write(
    tmp_path, decided, name, column, value
):
    """The texts unchanged, any other published column that is not the
    verdict's (or, on a decided case, the adjudication's) is refused, and
    named by its case and column."""
    import pandas as pd

    annotations, audit = _wording_stage(
        tmp_path, PUBLISHED if decided else UNDECIDED, decided=decided
    )
    frame = pd.read_csv(annotations / name, dtype=str, keep_default_na=False)
    frame.loc[0, column] = value
    frame.to_csv(annotations / name, index=False)
    with pytest.raises(
        SystemExit,
        match=rf"{re.escape(name)} is not what triage builds.*{WORDING_CASE}\S* "
        rf"{column}",
    ):
        release.verify_annotation_amendments(annotations, CHAINED, audit)


@pytest.mark.parametrize("defect", ["dropped_column", "extra_column", "row_order"])
def test_the_freeze_refuses_columns_or_rows_triage_did_not_write(tmp_path, defect):
    import pandas as pd

    annotations, audit = _wording_stage(tmp_path, PUBLISHED)
    path = annotations / "us_audit_row_annotations.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if defect == "dropped_column":
        frame = frame.drop(columns=["failure_subtype"])
        problem = "its columns"
    elif defect == "extra_column":
        frame["reviewed"] = "yes"
        problem = "its columns"
    else:
        frame = frame.iloc[::-1]
        problem = "its row order or serialization"
    frame.to_csv(path, index=False)
    with pytest.raises(SystemExit, match=f"differs at.*{problem}"):
        release.verify_annotation_amendments(annotations, CHAINED, audit)


def test_an_amendment_must_find_its_old_text_exactly_once(adjudications):
    staged, record = adjudications
    entry = record["adjudications"][0]
    for old in ("no such wording", " "):
        with pytest.raises(SystemExit, match="occurs"):
            _verify(staged, {_case(entry)}, [_amendment(entry, old, "x")])


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
