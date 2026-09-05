"""Reference CSV identity and staged refreeze inputs."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from policybench.full_run_export import (
    ReferenceProvenanceError,
    reference_policyengine_bundles,
)


@pytest.fixture
def reference_pair(tmp_path):
    reference = tmp_path / "reference_outputs.csv"
    reference.write_text("scenario_id,variable,value\nscenario_000,snap,100\n")
    bundle = {
        "model_package": "policyengine-us",
        "model_version": "1.755.4",
        "data_package": "populace-data",
        "data_version": "0.1.0",
        "default_dataset": "populace_us_2024",
        "default_dataset_uri": "hf://example/dataset@revision",
    }
    metadata = {
        "country": "us",
        "task": "reference_outputs",
        "reference_csv_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
        "row_count": 1,
        "policyengine_bundles": {"us": bundle},
    }
    sidecar = reference.with_name(reference.name + ".meta.json")
    sidecar.write_text(json.dumps(metadata))
    return reference, sidecar, metadata


@pytest.mark.parametrize(
    ("field", "stale_value", "message"),
    [
        ("reference_csv_sha256", "0" * 64, "hash does not match reference_csv_sha256"),
        ("row_count", 2, "row_count is 1, expected 2"),
        ("country", "uk", "country 'uk', expected 'us'"),
    ],
)
def test_reference_sidecar_rejects_stale_csv_identity(
    reference_pair, field, stale_value, message
):
    reference, sidecar, metadata = reference_pair
    metadata[field] = stale_value
    sidecar.write_text(json.dumps(metadata))
    with pytest.raises(ReferenceProvenanceError, match=message):
        reference_policyengine_bundles(reference, "us")


def test_reference_sidecar_digest_accepts_its_csv(reference_pair):
    reference, _, metadata = reference_pair
    assert (
        reference_policyengine_bundles(reference, "us", require_digest=True)
        == metadata["policyengine_bundles"]
    )


@pytest.mark.parametrize("invalid_digest", [None, "", " ", 123, False, [], {}])
@pytest.mark.parametrize("manifest_pinned", [False, True])
def test_present_invalid_digest_is_not_treated_as_legacy(
    reference_pair, invalid_digest, manifest_pinned
):
    reference, sidecar, metadata = reference_pair
    manifest_digest = metadata["reference_csv_sha256"]
    metadata["reference_csv_sha256"] = invalid_digest
    sidecar.write_text(json.dumps(metadata))

    with pytest.raises(ReferenceProvenanceError, match="invalid reference_csv_sha256"):
        reference_policyengine_bundles(
            reference,
            "us",
            require_digest=manifest_pinned,
            manifest_reference_sha256=manifest_digest if manifest_pinned else None,
        )


def test_strict_legacy_reference_requires_matching_manifest_pin(reference_pair):
    reference, sidecar, metadata = reference_pair
    manifest_digest = metadata.pop("reference_csv_sha256")
    metadata.pop("row_count")
    sidecar.write_text(json.dumps(metadata))

    with pytest.raises(ReferenceProvenanceError, match="hash pinned in the snapshot"):
        reference_policyengine_bundles(reference, "us", require_digest=True)

    with pytest.raises(ReferenceProvenanceError, match="hash does not match snapshot"):
        reference_policyengine_bundles(
            reference,
            "us",
            require_digest=True,
            manifest_reference_sha256="0" * 64,
        )

    assert (
        reference_policyengine_bundles(
            reference,
            "us",
            require_digest=True,
            manifest_reference_sha256=manifest_digest,
        )
        == metadata["policyengine_bundles"]
    )


def test_freeze_analysis_reads_only_staged_run_paths(tmp_path, monkeypatch):
    from scripts import freeze_snapshot

    staged_run = tmp_path / "snapshot" / "runs" / "us"
    source_us = tmp_path / "source" / "us"
    staged_run.mkdir(parents=True)
    # The analyze CLI receives the staged reference CSV's digest as its pin.
    (staged_run / "reference_outputs.csv").write_text("scenario_id,variable,value\n")
    (staged_run / "data.json").write_text(
        json.dumps(
            {
                "modelStats": [
                    {"model": "model-a", "condition": "no_tools", "costUsd": 1.5}
                ]
            }
        )
    )
    monkeypatch.setattr(freeze_snapshot, "RUN_DEST", staged_run)
    monkeypatch.setattr(freeze_snapshot, "SOURCE_US", source_us)
    analyzed_inputs = []

    def run_analysis(command, **kwargs):
        for option in ("-g", "-p", "-s"):
            path = Path(command[command.index(option) + 1])
            assert path.is_relative_to(staged_run)
            analyzed_inputs.append(path.name)
        assert analyzed_inputs == [
            "reference_outputs.csv",
            "predictions.csv.gz",
            "scenarios.csv",
        ]

    def read_csv(path, *args, **kwargs):
        assert Path(path).is_relative_to(staged_run)
        if Path(path).name == "summary_by_model.csv":
            return pd.DataFrame(
                {
                    "model": ["model-b", "model-a"],
                    "bounded_score": [0.9, 0.8],
                    "amount_accuracy": [0.8, 0.7],
                    "participation_accuracy": [0.95, 0.9],
                }
            )
        return pd.DataFrame()

    monkeypatch.setattr(freeze_snapshot.subprocess, "run", run_analysis)
    monkeypatch.setattr(freeze_snapshot.pd, "read_csv", read_csv)
    reports = []

    def render_report(tables, *, published_model_costs):
        assert published_model_costs == {"model-a": 1.5}
        assert tables["bounded_summary"]["model"].tolist() == ["model-a", "model-b"]
        assert tables["bounded_summary"]["bounded_score"].tolist() == [0.8, 0.9]
        reports.append(tables)
        return "Frozen report"

    monkeypatch.setattr(freeze_snapshot, "render_markdown_report", render_report)
    monkeypatch.setattr(
        freeze_snapshot,
        "household_impact_summary_by_model",
        lambda references, predictions: pd.DataFrame({"model": ["model-a"]}),
    )
    freeze_snapshot.regenerate_analysis(staged_run / "analysis")
    assert analyzed_inputs
    assert len(reports) == 1
    assert (staged_run / "analysis" / "report.md").read_text() == "Frozen report"


def test_frozen_reference_refresh_pins_committed_csv_identity():
    root = Path(__file__).resolve().parents[1]
    snapshot = root / "paper" / "snapshot" / "20260501"
    manifest = json.loads((snapshot / "manifest.json").read_text())
    run_label = manifest["source_run_labels"]["us"]
    run_dir = root / manifest["source_run_artifacts"][run_label]["path"]
    reference = run_dir / "reference_outputs.csv"
    refresh = manifest["reference_output_refresh"]

    assert (
        refresh["reference_csv_sha256"]
        == hashlib.sha256(reference.read_bytes()).hexdigest()
    )
    assert refresh["row_count"] == len(pd.read_csv(reference))
    assert reference_policyengine_bundles(
        reference,
        "us",
        require_digest=True,
        manifest_reference_sha256=refresh["reference_csv_sha256"],
    )


@pytest.mark.parametrize("changed", [False, True])
def test_serving_registry_pin_changes_only_with_serving_evidence(monkeypatch, changed):
    from scripts import freeze_snapshot

    previous = {
        "models": {"model-a": {"answer_contract": "tool"}},
        "registry_commit": "a" * 40,
    }
    generated = {
        "models": {"model-a": {"answer_contract": "json" if changed else "tool"}}
    }
    commands = []

    def git(command, **kwargs):
        commands.append(command)
        if command[1] == "show":
            assert (
                command[2] == "HEAD:paper/snapshot/20260501/model_serving_config.json"
            )
            return SimpleNamespace(returncode=0, stdout=json.dumps(previous))
        assert command == ["git", "rev-parse", "HEAD"]
        return SimpleNamespace(returncode=0, stdout="b" * 40 + "\n")

    monkeypatch.setattr(freeze_snapshot.subprocess, "run", git)
    assert freeze_snapshot._serving_registry_commit(generated) == (
        "b" * 40 if changed else "a" * 40
    )
    assert len(commands) == (2 if changed else 1)


def test_regenerate_analysis_passes_the_staged_reference_digest(tmp_path, monkeypatch):
    """The analyze CLI verifies the legacy staged sidecar against the same pin
    the freeze validated, so a refreeze cannot fail on its own committed
    references."""
    import hashlib
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "freeze_snapshot_for_digest",
        Path(__file__).resolve().parents[1] / "scripts" / "freeze_snapshot.py",
    )
    freeze_snapshot = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = freeze_snapshot
    spec.loader.exec_module(freeze_snapshot)

    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "reference_outputs.csv").write_text("scenario_id,variable,value\n")
    (staged / "predictions.csv.gz").write_bytes(b"")
    (staged / "scenarios.csv").write_text("scenario_id\n")
    monkeypatch.setattr(freeze_snapshot, "RUN_DEST", staged)
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        dest = Path(args[args.index("-o") + 1])
        for name in ("metrics.csv", "summary_by_model.csv", "summary_by_variable.csv"):
            (dest / name).write_text("model\n")

        class Done:
            returncode = 0

        return Done()

    monkeypatch.setattr(freeze_snapshot.subprocess, "run", fake_run)
    try:
        freeze_snapshot.regenerate_analysis(tmp_path / "analysis")
    except Exception:
        pass  # downstream report assembly is not under test here
    assert calls, "analyze CLI was not invoked"
    argv = calls[0]
    assert "--reference-digest" in argv
    pinned = argv[argv.index("--reference-digest") + 1]
    assert (
        pinned
        == hashlib.sha256((staged / "reference_outputs.csv").read_bytes()).hexdigest()
    )
