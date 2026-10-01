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


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_audit(audit: Path) -> None:
    """One judged, kept case with a bound seed verdict; one parse-only case,
    which is never judged and so needs no verdict."""
    case = audit / "cases" / KEPT
    case.mkdir(parents=True)
    (audit / "schema.json").write_text(json.dumps(AUDIT_OUTPUT_SCHEMA))
    manifest = [
        {"case_id": KEPT, "wrong_models": ["incumbent"], "parse_failure_only": False},
        {
            "case_id": "us__scenario_001__snap",
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
    evidence += [Path("inputs/gpt61sol/run_state.json")]
    evidence += [Path(driver.PROMPT_CHANGES), Path("stage.json")]
    for name in evidence:
        (stage / name).parent.mkdir(parents=True, exist_ok=True)
        (stage / name).write_text(f"Evidence: {name.name}\n")
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


@pytest.fixture
def staged_board(freeze_preflight, monkeypatch):
    """A 46-row payload past the receipt, with the committed snapshot copied in."""
    import policybench.dashboard_schema

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
    stats += [{"model": "gpt-6.1-sol", "condition": "no_tools"}]
    payload.write_text(json.dumps({"countries": {"us": {"modelStats": stats}}}))
    monkeypatch.setattr(
        policybench.dashboard_schema, "validate_dashboard_payload", lambda *a, **k: []
    )

    # The synthetic stage re-opens no case, so its provenance record lists none.
    record = stage.parent / "judge_provenance.json"
    record.write_text(json.dumps({"verdicts": []}))
    monkeypatch.setattr(driver, "JUDGE_PROVENANCE", record)

    def rebind():
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


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("defect", ["edited_kept", "unbound_new"])
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
    else:
        monkeypatch.setattr(driver, "load_seed", lambda stage: {})
        message = f"fail validation.*{KEPT}"
    rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match=message):
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
    staged = tmp_path / "us_adjudications.json"
    shutil.copyfile(COMMITTED_ADJUDICATIONS, staged)
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


def test_the_committed_record_is_release_20260929s():
    """The working-tree record the tests edit is the one at BASE_COMMIT."""
    assert (
        json.loads(COMMITTED_ADJUDICATIONS.read_text())["adjudications"]
        == driver.base_adjudications()
    )


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
    assert load_entries(staged) == load_entries(COMMITTED_ADJUDICATIONS) or (
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


def _wording_stage(tmp_path, published):
    """An audit with the case's verdict, the staged record deciding it, and
    the published case note and row annotations ``published`` spells."""
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
        json.dumps({"adjudications": [DECISION]})
    )
    pd.DataFrame(
        [
            {**keys, "model": model, "annotation": published[model]}
            for model in DIAGNOSES
            if model in published
        ]
    ).to_csv(annotations / "us_audit_row_annotations.csv", index=False)
    pd.DataFrame([{**keys, "case_annotation": published["note"]}]).to_csv(
        annotations / "us_case_notes.csv", index=False
    )
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
    with pytest.raises(SystemExit, match="not their verdict sources"):
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
