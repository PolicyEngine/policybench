"""Freeze release dashboard-data-20260930b from a staged re-judge.

The stage comes from ``scripts/finish_rejudge_20260930b.py``. This is a local
build: it writes the pointer, the snapshot, the annotations and
``<stage>/predictions.csv.gz``, and uploads nothing.

Release 20260930b changes only the five re-judged cases' annotations, so the
freeze refuses anything else:

- the export receipt must bind this stage's payload, the base and the tag, and
  every file it pins must be unchanged;
- the references, the predictions of every model and the adjudication record
  must equal release 20260930's;
- the serving configuration is release 20260930's, byte for byte;
- the board keeps release 20260930's snapshot date, model-response window,
  version description and snapshot label, because no model and no answer changed.
"""

from __future__ import annotations

import argparse
import functools
import gzip
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import finish_rejudge_20260930b as driver  # noqa: E402

RUN = driver.RUN_NAME
ADJUDICATIONS = driver.ADJUDICATIONS
BOARD_MODELS = driver.BOARD_MODELS
require = driver.require
digest = driver.digest


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def verify_receipt(stage: Path, payload_path: Path) -> dict:
    """The export receipt must bind this payload, base and tag, unchanged since."""
    receipt = read_json(stage / "release-ready.json")
    require(
        receipt.get("release_tag") == driver.RELEASE_TAG
        and receipt.get("base_tag") == driver.BASE_TAG
        and receipt.get("base_sha256") == driver.BASE_SHA256
        and receipt.get("base_commit") == driver.BASE_COMMIT
        and receipt.get("models") == BOARD_MODELS
        and receipt.get("partial") is False,
        "the export receipt does not bind this release and its base",
    )
    require(
        receipt.get("payload_sha256") == digest(payload_path),
        "the payload changed after export",
    )
    for rel, pin in receipt["files"].items():
        require(digest(stage / rel) == pin, f"{rel} changed after export")
    return receipt


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    stage = args.stage_dir.resolve()
    require(stage.is_relative_to(ROOT), "--stage-dir must be inside this checkout")
    driver.require_pins()

    import freeze_snapshot as freezer
    import pandas as pd

    if hasattr(pd.options, "future") and hasattr(pd.options.future, "infer_string"):
        pd.options.future.infer_string = False

    from policybench.adjudications import (
        load_adjudications,
        verify_adjudications_applied,
    )
    from policybench.dashboard_schema import validate_dashboard_payload

    driver.load_stage(stage)
    payload_path = stage / f"data-board{BOARD_MODELS}.json"
    verify_receipt(stage, payload_path)
    payload_hash = digest(payload_path)
    payload = read_json(payload_path)
    recombined = json.dumps({"countries": {"us": payload["countries"]["us"]}})
    require(
        recombined.encode() == payload_path.read_bytes(),
        "payload does not recombine to the freeze format",
    )
    errors = validate_dashboard_payload(payload, require_failure_annotations=True)
    require(not errors, f"strict dashboard gate failed: {errors[:5]}")

    snapshot = ROOT / "paper/snapshot/20260501"
    frozen_run = snapshot / "runs" / RUN
    source_run = driver.bundle_dir(stage)
    source_us = source_run / "us"
    staged_annotations = source_run / "annotations"
    base_manifest = json.loads(
        driver.base_blob("paper/snapshot/20260501/manifest.json")
    )

    # References and every model's predictions are release 20260930's.
    driver.base_driver.verify_reference_pins(source_us, "staged reference")
    driver.base_driver.verify_reference_pins(frozen_run, "committed reference")
    base_predictions = gzip.decompress(
        driver.base_blob(f"paper/snapshot/20260501/runs/{RUN}/predictions.csv.gz")
    )
    require(
        base_predictions == (source_us / "predictions.csv").read_bytes(),
        "staged predictions differ from release 20260930's",
    )
    # The adjudication record is release 20260930's, byte for byte.
    require(
        (staged_annotations / ADJUDICATIONS).read_bytes()
        == driver.base_blob(f"annotations/{RUN}/{ADJUDICATIONS}"),
        "the adjudication record changed",
    )
    adjudications = load_adjudications(staged_annotations / ADJUDICATIONS)
    verify_adjudications_applied(
        pd.read_csv(staged_annotations / "us_audit_row_annotations.csv"),
        pd.read_csv(staged_annotations / "us_case_notes.csv"),
        adjudications,
    )
    cases_dir = stage / "audit" / "cases"
    freezer.verify_adjudications_keep_judge_verdicts(adjudications, cases_dir)

    serving_path = "paper/snapshot/20260501/model_serving_config.json"
    base_serving_bytes = driver.base_blob(serving_path)
    require(
        len(json.loads(base_serving_bytes)["models"]) == BOARD_MODELS,
        f"release 20260930's serving configuration must list {BOARD_MODELS} models",
    )
    pointer = {
        "version": 1,
        "repo": "PolicyEngine/policybench",
        "tag": driver.RELEASE_TAG,
        "asset": "dashboard-data.json",
        "url": (
            "https://github.com/PolicyEngine/policybench/releases/download/"
            f"{driver.RELEASE_TAG}/dashboard-data.json"
        ),
        "sha256": payload_hash,
        "bytes": payload_path.stat().st_size,
    }
    versions_path = ROOT / "app/src/data.versions.json"
    require(
        versions_path.read_bytes() == driver.base_blob("app/src/data.versions.json"),
        "data.versions.json differs from release 20260930's",
    )
    if args.dry_run:
        print(
            f"Validated local release inputs: {driver.RELEASE_TAG}, {BOARD_MODELS} "
            f"models, {payload_hash}; references, predictions, adjudications and "
            "serving configuration unchanged"
        )
        return

    freezer.SNAPSHOT_DATE = base_manifest["snapshot_date"]
    freezer.MODEL_RESPONSE_DATE = base_manifest["model_response_date"]
    freezer.SOURCE_RUN = source_run
    freezer.SOURCE_US = source_us
    freezer.SOURCE_ANNOTATIONS = staged_annotations
    freezer.REFERENCE_META_SOURCE = source_us / "reference_outputs.csv.meta.json"
    freezer.PUBLISHED_DASHBOARD_SOURCE = payload_path
    freezer.PUBLISHED_DASHBOARD_ARTIFACT = {
        key: pointer[key] for key in ("tag", "asset", "url", "sha256", "bytes")
    }
    freezer.RUN_STATE_EVIDENCE = {}
    freezer.AUDIT_CASES_DIR = cases_dir
    freezer.audit_judge_provenance = functools.partial(
        freezer.audit_judge_provenance, cases_dir=cases_dir
    )
    freezer.developer_adjudications_block = functools.partial(
        freezer.developer_adjudications_block, cases_dir=cases_dir
    )

    def freeze_serving(destination: Path) -> None:
        # No model changed, so every row keeps release 20260930's evidence.
        destination.write_bytes(base_serving_bytes)

    freezer.freeze_serving_configuration = freeze_serving
    write_json(ROOT / "app/src/data.artifact.json", pointer)
    freezer.ANNOTATIONS_DEST.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        staged_annotations / ADJUDICATIONS, freezer.ANNOTATIONS_DEST / ADJUDICATIONS
    )
    freezer.main()
    driver.base_driver.verify_reference_pins(frozen_run, "frozen reference")
    require(
        (ROOT / serving_path).read_bytes() == base_serving_bytes,
        "the frozen serving configuration changed",
    )
    cache = ROOT / "app/.cache" / f"dashboard-data-{payload_hash[:16]}.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(payload_path, cache)
    freezer.gzip_deterministic(
        source_us / "predictions.csv",
        stage / "predictions.csv.gz",
        stored_name="predictions.csv",
    )
    print(f"Built {driver.RELEASE_TAG} locally; payload and predictions are in {stage}")


if __name__ == "__main__":
    main()
