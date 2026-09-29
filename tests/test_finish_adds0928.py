"""The September additions cannot turn partial or unaudited data into a release."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import finish_adds0928 as driver  # noqa: E402

from policybench.audit import AUDIT_OUTPUT_SCHEMA  # noqa: E402


@pytest.fixture
def runs(tmp_path):
    root = tmp_path / "runs"
    for slug, model in driver.MODELS.items():
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
    path = root / "sonnet55/run/run_state.json"
    state = json.loads(path.read_text())
    state.update(changes)
    path.write_text(json.dumps(state))


def test_discovers_only_the_three_registered_models(runs):
    extra = runs / "unrelated/run"
    extra.mkdir(parents=True)
    (extra / "run_state.json").write_text("{}")
    found = driver.discover_new_models(runs)
    assert {run.model for run in found} == set(driver.MODELS.values())
    assert all(run.predictions.parent == run.run_dir for run in found)


@pytest.mark.parametrize(
    "changes",
    [
        {"completed": 99},
        {"stopped_reason": "budget exhausted"},
        {"stopped_reason": ""},
        {"stopped_reason": False},
        {"completed": 0, "total": 0},
        {"completed": -1, "total": -1},
        {"completed": True, "total": True},
        {"completed": 100.0, "total": 100.0},
        {"completed": "100", "total": "100"},
        {"model": "claude-sonnet-4.6"},
    ],
)
def test_one_incomplete_or_invalid_run_refuses_the_entire_addition(runs, changes):
    change_state(runs, **changes)
    with pytest.raises(SystemExit, match="refusing incomplete additions"):
        driver.discover_new_models(runs)


@pytest.mark.parametrize("name", ["run_state.json", "predictions.csv"])
def test_missing_run_artifact_refuses_all_three(runs, name):
    (runs / "grok47/run" / name).unlink()
    with pytest.raises(SystemExit, match="grok47"):
        driver.discover_new_models(runs)


def test_scratch_completion_still_requires_completed_equal_total(runs):
    change_state(runs, completed=4, total=5, synthetic_partial=True)
    with pytest.raises(SystemExit, match="4/5"):
        driver.discover_new_models(runs)
    change_state(runs, completed=5)
    assert len(driver.discover_new_models(runs)) == 3


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


def test_symlink_cannot_disguise_overlapping_source(workspace):
    stage = workspace / "results/local/stage"
    stage.mkdir(parents=True)
    alias = workspace / "source-link"
    alias.symlink_to(stage, target_is_directory=True)
    with pytest.raises(SystemExit, match="overlaps input"):
        driver.validate_stage_path(stage, [alias])


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


@pytest.fixture
def predictions():
    return pd.DataFrame(
        {
            "model": ["grok-4.7", "grok-4.7"],
            "scenario_id": ["scenario_000", "scenario_000"],
            "variable": ["snap", "ssi"],
            "prediction": [0, 1],
        }
    )


def test_equal_row_counts_do_not_hide_substituted_output_keys(predictions):
    wrong = predictions.copy()
    wrong.loc[1, "variable"] = "medicaid"
    with pytest.raises(SystemExit, match="keys differ"):
        driver.validate_keys(wrong, predictions, "grok-4.7")


def test_duplicate_output_keys_are_rejected(predictions):
    repeated = pd.concat([predictions, predictions.iloc[:1]], ignore_index=True)
    with pytest.raises(SystemExit, match="duplicate prediction keys"):
        driver.validate_keys(repeated, predictions, "grok-4.7")


def test_predictions_cannot_be_labeled_as_another_model(predictions):
    with pytest.raises(SystemExit, match="unexpected model"):
        driver.validate_keys(predictions, predictions, "claude-sonnet-5.5")


def test_key_comparison_is_independent_of_row_order(predictions):
    driver.validate_keys(predictions.iloc[::-1], predictions, "grok-4.7")


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


@pytest.fixture
def audit(tmp_path):
    root = tmp_path / "audit"
    case = root / "cases/us__scenario_000__snap"
    case.mkdir(parents=True)
    model = "claude-sonnet-5.5"
    (root / "schema.json").write_text(json.dumps(AUDIT_OUTPUT_SCHEMA))
    (root / "cases.jsonl").write_text(
        json.dumps(
            {"case_id": case.name, "wrong_models": [model], "parse_failure_only": False}
        )
        + "\n"
    )
    verdict = {
        "reference_suspect": False,
        "reference_bug_hypothesis": "",
        "case_failure_source": "llm_error",
        "case_failure_subtype": "thresholds_rates",
        "rationale": "The model applied an outdated threshold.",
        "models": [
            {
                "model": model,
                "failure_source": "llm_error",
                "failure_subtype": "thresholds_rates",
                "diagnosis": "The model used the prior year's threshold.",
            }
        ],
    }
    write_verdict(case, verdict)
    return root, case, verdict


def write_verdict(case, verdict):
    path = case / "verdict.json"
    path.write_text(json.dumps(verdict))
    (case / "verdict.meta.json").write_text(
        json.dumps(
            {
                "verdict_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "judge_runner": "scripts/run_audit_claude.sh",
                "judge_model_requested": driver.JUDGE_MODEL,
                "judge_model_reported": [driver.JUDGE_MODEL],
                "judged_at_utc": "2026-09-28T23:30:00+00:00",
            }
        )
    )


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


@pytest.mark.parametrize("defect", ["missing", "stale", "wrong_judge"])
def test_new_model_verdict_requires_bound_opus55_provenance(audit, defect):
    root, case, _ = audit
    path = case / "verdict.meta.json"
    if defect == "missing":
        path.unlink()
    else:
        meta = json.loads(path.read_text())
        if defect == "stale":
            meta["verdict_sha256"] = "0" * 64
        else:
            meta["judge_model_reported"] = ["claude-opus-4-6"]
        path.write_text(json.dumps(meta))
    assert driver.validate_verdicts(root) == [case.name]


def test_parse_only_cases_do_not_require_paid_judging(audit):
    root, case, _ = audit
    manifest = json.loads((root / "cases.jsonl").read_text())
    manifest["parse_failure_only"] = True
    (root / "cases.jsonl").write_text(json.dumps(manifest) + "\n")
    (case / "verdict.json").unlink()
    (case / "verdict.meta.json").unlink()
    assert driver.validate_verdicts(root) == []


def test_unchanged_incumbent_case_keeps_its_existing_judge(audit):
    root, case, verdict = audit
    manifest = json.loads((root / "cases.jsonl").read_text())
    manifest["wrong_models"] = ["incumbent"]
    (root / "cases.jsonl").write_text(json.dumps(manifest) + "\n")
    verdict["models"][0]["model"] = "incumbent"
    write_verdict(case, verdict)
    meta = json.loads((case / "verdict.meta.json").read_text())
    meta["judge_model_requested"] = "gpt-5.6-sol"
    meta["judge_model_reported"] = ["gpt-5.6-sol"]
    meta["judge_runner"] = "scripts/run_audit_codex.sh"
    (case / "verdict.meta.json").write_text(json.dumps(meta))
    assert driver.validate_verdicts(root) == []


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
                "model": "claude-sonnet-5.5",
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


def test_export_uses_scratch_only_and_partial_never_gets_release_receipt(
    tmp_path, monkeypatch
):
    import policybench.dashboard_schema
    import policybench.full_run_export

    stage = tmp_path / "stage"
    bundle = stage / "publish" / driver.RUN_NAME
    bundle.mkdir(parents=True)
    stats = [
        {"model": f"incumbent-{i}", "exact": 50.0, "score": 0.5, "n": 20}
        for i in range(42)
    ] + [
        {"model": model, "exact": 60.0, "score": 0.6, "n": 20}
        for model in driver.MODELS.values()
    ]
    calls = []

    def export_full_run(path, *, countries, skip_app_data):
        calls.append((path, countries, skip_app_data))
        return {"countries": {"us": {"modelStats": stats}}}

    monkeypatch.setattr(policybench.full_run_export, "export_full_run", export_full_run)
    monkeypatch.setattr(
        policybench.dashboard_schema, "validate_dashboard_payload", lambda *a, **kw: []
    )
    args = SimpleNamespace(stage_dir=stage, partial=True, early=True)
    driver.export(args, bundle, {"countries": {"us": {"modelStats": []}}})
    assert calls == [(bundle, ["us"], True)]
    payload = stage / "PARTIAL-data-board45.json"
    assert "PARTIAL" in json.loads(payload.read_text())["stage2Status"]
    assert (bundle / "data.json").read_bytes() == payload.read_bytes()
    assert not (stage / "release-ready.json").exists()


def test_strict_export_recombines_to_freeze_bytes_and_binds_evidence(
    tmp_path, monkeypatch
):
    import policybench.dashboard_schema
    import policybench.full_run_export

    stage = tmp_path / "stage"
    bundle = stage / "publish" / driver.RUN_NAME
    evidence = [
        bundle / "us" / name for name in (*driver.REFERENCE_FILES, "predictions.csv")
    ] + [
        bundle / "annotations/us_adjudications.json",
        stage / "inputs/sonnet55/run_state.json",
        stage / "audit/cases/example/verdict.json",
        stage / "audit/cases/example/verdict.meta.json",
        stage / "audit/cases/example/prompt.md",
        stage / "audit/cases.jsonl",
        stage / "audit/schema.json",
    ]
    for path in evidence:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"Evidence: {path.name}\n")
    incumbents = [
        {"model": f"incumbent-{i}", "exact": 50.0, "score": 0.5, "n": 1932}
        for i in range(41)
    ] + [
        {
            "model": "claude-fable-5",
            "exact": 60.0,
            "score": 0.6,
            "n": 1932,
            "costUsd": 54.1091,
            "costPerHousehold": 0.541091,
            "totalTokens": 3850174,
            "latencySeconds": 97.678,
        }
    ]
    stats = copy.deepcopy(incumbents) + [
        {"model": model, "exact": 65.0, "score": 0.65, "n": 1932}
        for model in driver.MODELS.values()
    ]
    for field in ("costUsd", "costPerHousehold", "totalTokens", "latencySeconds"):
        stats[41][field] = None
    payload = {"countries": {"us": {"modelStats": stats}}}
    live = {"countries": {"us": {"modelStats": incumbents}}}
    gate_calls = []

    def validate(payload, *, require_failure_annotations):
        gate_calls.append(require_failure_annotations)
        return []

    monkeypatch.setattr(
        policybench.full_run_export, "export_full_run", lambda *a, **kw: payload
    )
    monkeypatch.setattr(
        policybench.dashboard_schema, "validate_dashboard_payload", validate
    )
    args = SimpleNamespace(stage_dir=stage, partial=False, early=False)
    driver.export(args, bundle, live)

    output = stage / "data-board45.json"
    assert (
        output.read_bytes()
        == json.dumps({"countries": {"us": payload["countries"]["us"]}}).encode()
    )
    assert (bundle / "data.json").read_bytes() == output.read_bytes()
    assert stats[41] == incumbents[41]
    assert gate_calls == [True]
    receipt = json.loads((stage / "release-ready.json").read_text())
    assert receipt["payload_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert receipt["files"] == {
        str(path.relative_to(stage)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in evidence
    }


@pytest.fixture
def freeze_preflight(workspace, monkeypatch):
    import freeze_adds0928 as release

    monkeypatch.setattr(release, "ROOT", workspace)
    stage = workspace / "results/local/stage"
    stage.mkdir(parents=True)
    payload = stage / "data-board45.json"
    payload.write_text(json.dumps({"countries": {"us": {"modelStats": []}}}))
    evidence = stage / "audit/verdict.json"
    evidence.parent.mkdir()
    evidence.write_text("Original judge evidence\n")
    receipt = {
        "release_tag": driver.RELEASE_TAG,
        "payload_sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
        "models": 45,
        "partial": False,
        "files": {
            "audit/verdict.json": hashlib.sha256(evidence.read_bytes()).hexdigest()
        },
    }
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    pointer = workspace / "app/src/data.artifact.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text("The live pointer must stay unchanged.\n")
    return release, stage, payload, receipt


def test_freeze_rejects_pretty_json_before_any_workspace_mutation(freeze_preflight):
    release, stage, payload, receipt = freeze_preflight
    payload.write_text(json.dumps(json.loads(payload.read_text()), indent=2) + "\n")
    receipt["payload_sha256"] = hashlib.sha256(payload.read_bytes()).hexdigest()
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    before = {
        path.relative_to(release.ROOT): path.read_bytes()
        for path in release.ROOT.rglob("*")
        if path.is_file()
    }
    with pytest.raises(SystemExit, match="does not recombine to the freeze format"):
        release.main(["--stage-dir", str(stage)])
    assert {
        path.relative_to(release.ROOT): path.read_bytes()
        for path in release.ROOT.rglob("*")
        if path.is_file()
    } == before


@pytest.mark.parametrize("defect", ["changed", "outside_stage", "missing_hashes"])
def test_freeze_refuses_changed_or_unbound_evidence(freeze_preflight, defect):
    release, stage, _, receipt = freeze_preflight
    if defect == "changed":
        (stage / "audit/verdict.json").write_text("Altered judge evidence\n")
        message = "Staged evidence changed"
    elif defect == "outside_stage":
        path = release.ROOT / "app/src/data.artifact.json"
        receipt["files"] = {
            "../../../app/src/data.artifact.json": hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        }
        message = "Staged evidence changed"
    else:
        receipt["files"] = {}
        message = "missing staged evidence hashes"
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    pointer = release.ROOT / "app/src/data.artifact.json"
    original = pointer.read_bytes()
    with pytest.raises(SystemExit, match=message):
        release.main(["--stage-dir", str(stage), "--dry-run"])
    assert pointer.read_bytes() == original


def test_snapshot_uses_embedded_household_ids_without_reading_live_states(
    workspace, monkeypatch
):
    import snapshot_adds0928 as snapshot

    reference = workspace / "reference"
    reference.mkdir()
    (reference / "reference_outputs.csv").write_text(
        "scenario_id,variable\nscenario_007,snap\nscenario_007,ssi\n"
    )
    monkeypatch.setattr(snapshot, "ROOT", workspace)
    monkeypatch.setattr(snapshot, "SNAPSHOT", reference)
    runs = workspace / "supervised"
    output = workspace / "results/local/copied-runs"
    originals = {}
    for slug, model in driver.MODELS.items():
        # The filename is queue position 006; the household is scenario_007.
        path = runs / slug / "run/scenarios/scenario_006.csv"
        path.parent.mkdir(parents=True)
        raw = (
            "model,scenario_id,variable,prediction,raw_response\r\n"
            f'{model},scenario_007,snap,1,"First line\nSecond line"\r\n'
            f'{model},scenario_007,ssi,2,"First line\nSecond line"\r\n'
        ).encode()
        path.write_bytes(raw)
        originals[slug] = raw
        assert not (path.parent.parent / "run_state.json").exists()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "snapshot_adds0928.py",
            "--runs-root",
            str(runs),
            "--out-dir",
            str(output),
        ],
    )

    snapshot.main()

    for slug, model in driver.MODELS.items():
        target = output / slug / "run"
        copied = target / "scenarios/scenario_006.csv"
        assert copied.read_bytes() == originals[slug]
        with (target / "predictions.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert {
            (row["model"], row["scenario_id"], row["variable"]) for row in rows
        } == {(model, "scenario_007", "snap"), (model, "scenario_007", "ssi")}
        assert len(rows) == 2
        assert all(row["raw_response"] == "First line\nSecond line" for row in rows)
        state = json.loads((target / "run_state.json").read_text())
        assert state["completed"] == 1 and state["total"] == 100
        assert state["synthetic_partial"] is True and state["stopped_reason"] is None
        assert json.loads((target / "scenario-sha256.json").read_text()) == {
            "scenario_006.csv": hashlib.sha256(originals[slug]).hexdigest()
        }
        source = runs / slug / "run"
        assert not (source / "run_state.json").exists()
        assert (source / "scenarios/scenario_006.csv").read_bytes() == originals[slug]


# --- Reference revision gate --------------------------------------------------

from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

REVISION_KEYS = [(f"scenario_{i:03d}", v) for i in range(6) for v in ("snap", "eitc")]


def _reference_csv(values: dict) -> bytes:
    rows = ["scenario_id,variable,value,impact_weight"]
    rows += [f"{s},{v},{values[(s, v)]!r},1.0" for s, v in REVISION_KEYS]
    return ("\n".join(rows) + "\n").encode()


@pytest.fixture
def reference_snapshot(tmp_path, monkeypatch):
    """A synthetic snapshot whose base (22c) references are pinned in memory."""
    base_values = {key: float(i * 100) for i, key in enumerate(REVISION_KEYS)}
    base = {
        "reference_outputs.csv": _reference_csv(base_values),
        "reference_outputs.csv.meta.json": b'{"revisions": []}',
        "reference_exclusions.json": b'{"exclusions": []}',
    }
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    for name, raw in base.items():
        (snapshot / name).write_bytes(raw)
    monkeypatch.setattr(driver, "SNAPSHOT", snapshot)
    monkeypatch.setattr(
        driver,
        "BASE_REFERENCE_SHA256",
        {name: hashlib.sha256(raw).hexdigest() for name, raw in base.items()},
    )
    monkeypatch.setattr(driver, "base_reference_bytes", lambda name: base[name])

    def revise(new_values: dict, listed: dict, kind: str = "engine_upgrade"):
        (snapshot / "reference_outputs.csv").write_bytes(_reference_csv(new_values))
        meta = {
            "reference_csv_sha256": driver.digest(snapshot / "reference_outputs.csv"),
            "revisions": [
                {
                    "kind": kind,
                    "root_cause": "engine_upgrade_test",
                    "changed": [
                        {"scenario_id": s, "variable": v, "regenerated": value}
                        for (s, v), value in listed.items()
                    ],
                }
            ],
        }
        (snapshot / "reference_outputs.csv.meta.json").write_text(json.dumps(meta))

    return base_values, revise


def test_unchanged_snapshot_has_no_revision(reference_snapshot):
    assert driver.reference_revision() is None


def test_the_committed_snapshot_is_still_the_22c_base():
    # Until the reference revision is committed, the pins describe this checkout.
    assert driver.reference_revision() is None or (
        driver.reference_revision()["kind"] == "engine_upgrade"
    )


@settings(max_examples=60, deadline=None)
@given(
    changes=st.dictionaries(
        st.sampled_from(REVISION_KEYS),
        st.floats(min_value=-5e5, max_value=5e5, allow_nan=False).map(
            lambda x: round(x, 2)
        ),
        min_size=1,
        max_size=6,
    )
)
def test_revision_is_accepted_iff_it_lists_exactly_the_changed_values(
    tmp_path_factory, changes
):
    """The exact list passes; an omission, an extra entry or a wrong value fails."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        root = tmp_path_factory.mktemp("rev")
        base_values = {key: float(i * 100) for i, key in enumerate(REVISION_KEYS)}
        base = {
            "reference_outputs.csv": _reference_csv(base_values),
            "reference_outputs.csv.meta.json": b'{"revisions": []}',
            "reference_exclusions.json": b'{"exclusions": []}',
        }
        for name, raw in base.items():
            (root / name).write_bytes(raw)
        monkeypatch.setattr(driver, "SNAPSHOT", root)
        monkeypatch.setattr(
            driver,
            "BASE_REFERENCE_SHA256",
            {name: hashlib.sha256(raw).hexdigest() for name, raw in base.items()},
        )
        monkeypatch.setattr(driver, "base_reference_bytes", lambda name: base[name])
        real = {k: v for k, v in changes.items() if v != base_values[k]}
        new_values = {**base_values, **real}

        def write(listed, kind="engine_upgrade"):
            (root / "reference_outputs.csv").write_bytes(_reference_csv(new_values))
            meta = {
                "reference_csv_sha256": driver.digest(root / "reference_outputs.csv"),
                "revisions": [
                    {
                        "kind": kind,
                        "root_cause": "t",
                        "changed": [
                            {"scenario_id": s, "variable": v, "regenerated": x}
                            for (s, v), x in listed.items()
                        ],
                    }
                ],
            }
            (root / "reference_outputs.csv.meta.json").write_text(json.dumps(meta))

        if not real:
            return
        write(real)
        assert driver.reference_revision()["root_cause"] == "t"
        first = next(iter(real))
        write({k: v for k, v in real.items() if k != first})  # omission
        with pytest.raises(SystemExit):
            driver.reference_revision()
        spare = next(k for k in REVISION_KEYS if k not in real)
        write({**real, spare: base_values[spare] + 1})  # extra
        with pytest.raises(SystemExit):
            driver.reference_revision()
        write({**real, first: real[first] + 0.5})  # wrong value
        with pytest.raises(SystemExit):
            driver.reference_revision()
        write(real, kind="convention")  # not an engine upgrade
        with pytest.raises(SystemExit):
            driver.reference_revision()


def test_sidecar_must_pin_the_committed_csv(reference_snapshot):
    base_values, revise = reference_snapshot
    key = REVISION_KEYS[0]
    revise({**base_values, key: 7.0}, {key: 7.0})
    meta_path = driver.SNAPSHOT / "reference_outputs.csv.meta.json"
    meta = json.loads(meta_path.read_text())
    meta["reference_csv_sha256"] = "0" * 64
    meta_path.write_text(json.dumps(meta))
    with pytest.raises(SystemExit):
        driver.reference_revision()


def test_base_reference_bytes_are_checked_against_their_pins(monkeypatch):
    for name in driver.BASE_REFERENCE_SHA256:
        raw = driver.base_reference_bytes(name)
        assert hashlib.sha256(raw).hexdigest() == driver.BASE_REFERENCE_SHA256[name]
    monkeypatch.setitem(driver.BASE_REFERENCE_SHA256, "reference_outputs.csv", "0" * 64)
    with pytest.raises(SystemExit):
        driver.base_reference_bytes("reference_outputs.csv")


def test_a_re_export_after_the_freeze_gates_on_the_22c_asset(monkeypatch):
    """After the freeze the live pointer names this release, so a re-export
    reads the 22c payload from git and checks it against the 22c asset's
    sha256; any other pointer is refused."""
    pointer = json.loads((driver.ROOT / "app/src/data.artifact.json").read_text())
    if pointer["tag"] == driver.BASE_TAG:
        pytest.skip("this checkout is still at the 22c base")
    live = driver.resolve_live_base(SimpleNamespace())
    stats = live["countries"]["us"]["modelStats"]
    assert len(stats) == 42
    assert "claude-sonnet-5.5" not in {row["model"] for row in stats}
    monkeypatch.setattr(driver, "BASE_SHA256", "0" * 64)
    with pytest.raises(SystemExit, match="base payload SHA256 mismatch"):
        driver.resolve_live_base(SimpleNamespace())
    monkeypatch.setattr(driver, "RELEASE_TAG", "dashboard-data-20991231")
    with pytest.raises(SystemExit, match="base pointer changed"):
        driver.resolve_live_base(SimpleNamespace())
