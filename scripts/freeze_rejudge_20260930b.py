"""Freeze release dashboard-data-20260930b from a staged re-judge.

The stage comes from ``scripts/finish_rejudge_20260930b.py``. This is a local
build: it writes the pointer, the snapshot, the annotations and
``<stage>/predictions.csv.gz``, and uploads nothing.

Release 20260930b changes only the five re-judged cases' annotations, so the
freeze refuses anything else:

- the export receipt must bind this stage's payload, the base and the tag, and
  every file it must bind, all unchanged since export;
- the working tree must be release 20260930 as merged, in every file the
  freeze reads or writes;
- the references, every model's predictions, the adjudication record, every
  other annotation file, the serving configuration and the version registry
  must equal release 20260930's;
- the board keeps release 20260930's snapshot date, model-response window,
  version description and snapshot label, because no model and no answer changed;
- afterwards the manifest may differ from release 20260930's only in the
  annotation hashes, the judge provenance, the dashboard artifact, the run
  payload's hash and the rendered paper.
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
SNAPSHOT_DIR = "paper/snapshot/20260501"
MANIFEST = f"{SNAPSHOT_DIR}/manifest.json"
SERVING = f"{SNAPSHOT_DIR}/model_serving_config.json"
POINTER = "app/src/data.artifact.json"
VERSIONS = "app/src/data.versions.json"
# Manifest paths this release may change; every other leaf must equal the base.
MANIFEST_CHANGES = (
    ("audit_annotation_artifacts", "files", "us_audit_row_annotations.csv"),
    ("audit_annotation_artifacts", "files", "us_case_notes.csv"),
    ("audit_annotation_artifacts", "judge_provenance"),
    ("live_dashboard_artifact",),
    ("published_dashboard_artifact",),
    ("source_run_artifacts", RUN, "files", "data.json.gz"),
    ("rendered_paper_artifacts",),
)
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
    bundle = f"publish/{RUN}"
    required = {
        driver.STAGE,
        "annotation-changes.json",
        "payload-diff.json",
        f"{bundle}/annotations/{ADJUDICATIONS}",
        f"{bundle}/us/predictions.csv",
        *(f"{bundle}/annotations/{name}" for name in driver.ANNOTATION_CSVS),
        *(f"{bundle}/us/{name}" for name in driver.base_driver.REFERENCE_FILES),
        *(f"audit/cases/{case}/claude.transcript.jsonl" for case in driver.REJUDGE),
    }
    missing = sorted(required - set(receipt["files"]))
    require(not missing, f"the receipt does not bind {missing}")
    for rel, pin in receipt["files"].items():
        path = (stage / rel).resolve()
        require(
            path.is_relative_to(stage),
            f"the receipt names a path outside the stage: {rel}",
        )
        require(digest(path) == pin, f"{rel} changed after export")
    return receipt


def leaf_diff(before, after, path=()) -> list[tuple]:
    return driver.payload_diff(before, after, path)


def manifest_problems(before: dict, after: dict) -> list[tuple]:
    """Manifest paths that changed outside MANIFEST_CHANGES."""
    return [
        path
        for path in leaf_diff(before, after)
        if not any(path[: len(prefix)] == prefix for prefix in MANIFEST_CHANGES)
    ]


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

    record = driver.load_stage(stage)
    problems = driver.validate(stage, record)
    require(not problems, "verdicts do not validate:\n" + "\n".join(problems))
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

    # The working tree is release 20260930 as merged, in everything the freeze
    # reads or writes.
    annotations_dest = f"annotations/{RUN}"
    committed_annotations = driver.base_annotation_names()
    for rel in (MANIFEST, SERVING, POINTER, VERSIONS) + tuple(
        f"{annotations_dest}/{name}" for name in committed_annotations
    ):
        require(
            (ROOT / rel).read_bytes() == driver.base_blob(rel),
            f"the working tree's {rel} is not release 20260930's",
        )

    snapshot = ROOT / SNAPSHOT_DIR
    frozen_run = snapshot / "runs" / RUN
    source_run = driver.bundle_dir(stage)
    source_us = source_run / "us"
    staged_annotations = source_run / "annotations"
    base_manifest = json.loads(driver.base_blob(MANIFEST))
    changes = read_json(stage / "annotation-changes.json")
    driver.verify_annotations(staged_annotations, changes)

    # References and every model's predictions are release 20260930's.
    driver.base_driver.verify_reference_pins(source_us, "staged reference")
    driver.base_driver.verify_reference_pins(frozen_run, "committed reference")
    base_predictions = gzip.decompress(
        driver.base_blob(f"{SNAPSHOT_DIR}/runs/{RUN}/predictions.csv.gz")
    )
    require(
        base_predictions == (source_us / "predictions.csv").read_bytes(),
        "staged predictions differ from release 20260930's",
    )
    adjudications = load_adjudications(staged_annotations / ADJUDICATIONS)
    verify_adjudications_applied(
        pd.read_csv(staged_annotations / "us_audit_row_annotations.csv"),
        pd.read_csv(staged_annotations / "us_case_notes.csv"),
        adjudications,
    )
    cases_dir = stage / "audit" / "cases"
    freezer.verify_adjudications_keep_judge_verdicts(adjudications, cases_dir)

    base_serving = driver.base_blob(SERVING)
    require(
        len(json.loads(base_serving)["models"]) == BOARD_MODELS,
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
    if args.dry_run:
        print(
            f"Validated local release inputs: {driver.RELEASE_TAG}, {BOARD_MODELS} "
            f"models, {payload_hash}; references, predictions, adjudications, "
            "serving configuration and working tree are release 20260930's"
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
        destination.write_bytes(base_serving)

    freezer.freeze_serving_configuration = freeze_serving
    write_json(ROOT / POINTER, pointer)
    freezer.ANNOTATIONS_DEST.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        staged_annotations / ADJUDICATIONS, freezer.ANNOTATIONS_DEST / ADJUDICATIONS
    )
    freezer.main()

    # freeze_snapshot rewrites the annotations directory from the stage; put
    # back every committed file the stage does not carry (the wording
    # amendments record), then require the directory to be release 20260930's
    # but for the two re-judged CSVs.
    for name in committed_annotations:
        path = ROOT / annotations_dest / name
        if not path.exists():
            path.write_bytes(driver.base_blob(f"{annotations_dest}/{name}"))
    frozen = sorted(p.name for p in (ROOT / annotations_dest).iterdir() if p.is_file())
    require(frozen == committed_annotations, f"frozen annotation files: {frozen}")
    driver.verify_annotations(ROOT / annotations_dest, changes)
    driver.base_driver.verify_reference_pins(frozen_run, "frozen reference")
    require(
        (ROOT / SERVING).read_bytes() == base_serving,
        "the frozen serving configuration changed",
    )
    require(
        (ROOT / VERSIONS).read_bytes() == driver.base_blob(VERSIONS),
        "the version registry changed",
    )
    changed = manifest_problems(base_manifest, read_json(ROOT / MANIFEST))
    require(
        not changed, f"the manifest changed outside this release's scope: {changed[:8]}"
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
    print(
        "Next: update the notes and tests that pin the release tag and judge "
        "provenance, render the paper, re-pin (freeze_snapshot.py --rendered-only), "
        "run the tests."
    )


if __name__ == "__main__":
    main()
