"""Build the September 28 release locally from a strictly gated stage.

This adapts the existing freezer in process; it never calls a release upload.
Run only after finish_adds0928.py --step export has written release-ready.json.
The optional --dry-run validates inputs without changing repository files.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["OPENBLAS_NUM_THREADS"] = "1"
sys.path.insert(0, str(ROOT))

RUN = "us_full_run_20260612_policyengine_4_16_1_populace"
NEW_MODELS = {
    "sonnet55": "claude-sonnet-5.5",
    "grok47": "grok-4.7",
    "dsflash41": "deepseek-v4.1-flash",
}


def read_json(path: Path) -> dict:
    """Read an object, with the filename retained in parse failures."""
    return json.loads(path.read_text())


def write_json(path: Path, value: dict) -> None:
    """Write reviewable deterministic JSON."""
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def digest(path: Path) -> str:
    """Hash a file without holding its bytes in memory."""
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def validate_treatment(freezer, state: dict, state_path: Path, scenarios: Path) -> None:
    """Check actual treatment against the registry before changing tracked files."""
    from policybench.config import MODELS, PROGRAMS
    from policybench.eval_no_tools import (
        _first_request_variables,
        _initial_completion_budget_tokens,
        _max_repair_rounds,
        _request_timeout_seconds,
        _thinking_configuration,
    )
    from policybench.model_cards import (
        PROMPT_CONTRACT_VERSION,
        answer_contract_for,
        completion_budget_ceiling_for,
        explanation_chunk_size_for,
    )
    from policybench.scenarios import load_scenarios_from_manifest
    from policybench.spec import expand_programs_for_scenario

    model = state["model"]
    provider_id = MODELS[model]
    contract = answer_contract_for(provider_id)
    first = load_scenarios_from_manifest(scenarios)[0]
    variables = _first_request_variables(
        provider_id,
        expand_programs_for_scenario(PROGRAMS, first),
        include_explanations=True,
    )
    expected = {
        "model_id": provider_id,
        "answer_contract": contract,
        "chunk_size": explanation_chunk_size_for(provider_id),
        "tool_choice_mode": "forced" if contract == "tool" else None,
        "prompt_contract_version": PROMPT_CONTRACT_VERSION,
        "completion_budget_ceiling": completion_budget_ceiling_for(provider_id),
        "initial_completion_budget_tokens": _initial_completion_budget_tokens(
            provider_id, variables
        ),
        "thinking": _thinking_configuration(provider_id),
        "request_timeout_seconds": _request_timeout_seconds(provider_id, env={}),
        "max_repair_rounds": _max_repair_rounds(env={}),
    }
    freezer._validate_treatment_fingerprint(
        state["treatment_fingerprint"], expected, model=model, run_state_path=state_path
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--tag", default="dashboard-data-20260928")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    match = re.fullmatch(r"dashboard-data-(\d{4})(\d{2})(\d{2})[a-z]?", args.tag)
    if not match:
        parser.error("--tag must be dashboard-data-YYYYMMDD[a-z]")
    date = "-".join(match.groups())
    stage = args.stage_dir.resolve()
    if not stage.is_relative_to(ROOT):
        parser.error("--stage-dir must be inside this checkout")

    import freeze_snapshot as freezer
    import pandas as pd

    if hasattr(pd.options, "future") and hasattr(pd.options.future, "infer_string"):
        pd.options.future.infer_string = False

    from policybench.dashboard_schema import validate_dashboard_payload

    payload_path = stage / "data-board45.json"
    receipt = read_json(stage / "release-ready.json")
    payload_hash = digest(payload_path)
    if (
        receipt.get("payload_sha256") != payload_hash
        or receipt.get("models") != 45
        or receipt.get("partial") is not False
        or receipt.get("release_tag") != args.tag
    ):
        raise SystemExit("Strict export receipt does not match data-board45.json")
    if not receipt.get("files"):
        raise SystemExit("Strict export receipt is missing staged evidence hashes")
    for name, expected in receipt["files"].items():
        source = (stage / name).resolve()
        if not source.is_relative_to(stage) or digest(source) != expected:
            raise SystemExit(f"Staged evidence changed since strict export: {name}")
    payload = read_json(payload_path)
    recombined = json.dumps({"countries": {"us": payload["countries"]["us"]}})
    if recombined.encode() != payload_path.read_bytes():
        raise SystemExit("Payload does not recombine to the freeze format")
    errors = validate_dashboard_payload(payload, require_failure_annotations=True)
    if errors:
        raise SystemExit(f"Strict dashboard gate failed: {errors[:5]}")
    stats = payload["countries"]["us"]["modelStats"]
    model_names = {row["model"] for row in stats}
    if len(stats) != 45 or any(row["condition"] != "no_tools" for row in stats):
        raise SystemExit("Release must contain exactly 45 no-tools model rows")

    snapshot = ROOT / "paper/snapshot/20260501"
    frozen_run = snapshot / "runs" / RUN
    serving_path = snapshot / "model_serving_config.json"
    previous_serving = read_json(serving_path)
    incumbents = set(previous_serving["models"]) - set(NEW_MODELS.values())
    if len(incumbents) != 42 or model_names != incumbents | set(NEW_MODELS.values()):
        raise SystemExit("Frozen incumbent roster and staged 45-model roster disagree")
    source_run = stage / "publish" / RUN
    source_us = source_run / "us"
    for name in (
        "reference_outputs.csv",
        "reference_outputs.csv.meta.json",
        "reference_exclusions.json",
        "scenarios.csv",
        "scenarios.csv.meta.json",
    ):
        if digest(source_us / name) != digest(frozen_run / name):
            raise SystemExit(
                f"{name} changed: this additive freezer needs reference review"
            )
    previous_rows = pd.read_csv(frozen_run / "predictions.csv.gz", low_memory=False)
    staged_rows = pd.read_csv(source_us / "predictions.csv", low_memory=False)
    for model in sorted(incumbents):
        if freezer._model_prediction_rows_sha256(previous_rows, model) != (
            freezer._model_prediction_rows_sha256(staged_rows, model)
        ):
            raise SystemExit(f"Incumbent prediction evidence changed: {model}")
    del previous_rows

    evidence_paths = {}
    for slug, model in NEW_MODELS.items():
        state_path = stage / "inputs" / slug / "run_state.json"
        state = read_json(state_path)
        if (
            state.get("model") != model
            or state.get("completed") != 100
            or state.get("total") != 100
            or state.get("stopped_reason") is not None
            or not isinstance(state.get("treatment_fingerprint"), dict)
        ):
            raise SystemExit(
                f"Missing completed run or treatment evidence: {state_path}"
            )
        validate_treatment(freezer, state, state_path, source_us / "scenarios.csv")
        evidence = freezer._run_state_prediction_evidence(
            state_path, staged_rows, model
        )
        if evidence["kind"] != "run_state":
            raise SystemExit(
                f"Run-state prediction evidence failed for {model}: {evidence}"
            )
        evidence_paths[model] = str(state_path)
    del staged_rows

    staged_annotations = source_run / "annotations"
    adjudications = freezer.load_adjudications(
        staged_annotations / "us_adjudications.json"
    )
    from policybench.adjudications import verify_adjudications_applied

    verify_adjudications_applied(
        pd.read_csv(staged_annotations / "us_audit_row_annotations.csv"),
        pd.read_csv(staged_annotations / "us_case_notes.csv"),
        adjudications,
    )
    cases_dir = stage / "audit" / "cases"
    freezer.verify_adjudications_keep_judge_verdicts(adjudications, cases_dir)
    pointer = {
        "version": 1,
        "repo": "PolicyEngine/policybench",
        "tag": args.tag,
        "asset": "dashboard-data.json",
        "url": (
            "https://github.com/PolicyEngine/policybench/releases/download/"
            f"{args.tag}/dashboard-data.json"
        ),
        "sha256": payload_hash,
        "bytes": payload_path.stat().st_size,
    }
    versions_path = ROOT / "app/src/data.versions.json"
    versions = read_json(versions_path)
    live = next(
        item for item in versions["versions"] if item["id"] == versions["default"]
    )
    description, changed = re.subn(
        r" - \d+ models$", " - 45 models", live["description"]
    )
    if changed != 1:
        raise SystemExit("Live version description has an unexpected model-count shape")
    live.update(description=description, snapshotLabel=f"Snapshot {date}")
    if args.dry_run:
        print(f"Validated local release inputs: {args.tag}, 45 models, {payload_hash}")
        return

    # Read-only input paths are all in this checkout. Override defaults that
    # captured the old audit directory when freeze_snapshot was imported.
    freezer.SNAPSHOT_DATE = date
    freezer.MODEL_RESPONSE_DATE = f"2026-06-12 to {date}"
    freezer.SOURCE_RUN = source_run
    freezer.SOURCE_US = source_us
    freezer.SOURCE_ANNOTATIONS = staged_annotations
    freezer.REFERENCE_META_SOURCE = source_us / "reference_outputs.csv.meta.json"
    freezer.PUBLISHED_DASHBOARD_SOURCE = payload_path
    freezer.PUBLISHED_DASHBOARD_ARTIFACT = {
        key: pointer[key] for key in ("tag", "asset", "url", "sha256", "bytes")
    }
    freezer.RUN_STATE_EVIDENCE = evidence_paths
    freezer.AUDIT_CASES_DIR = cases_dir
    freezer.audit_judge_provenance = functools.partial(
        freezer.audit_judge_provenance, cases_dir=cases_dir
    )
    freezer.developer_adjudications_block = functools.partial(
        freezer.developer_adjudications_block, cases_dir=cases_dir
    )
    original_freeze_serving = freezer.freeze_serving_configuration

    def freeze_serving(destination: Path) -> None:
        # The old rows already have frozen evidence. Preserve it byte-for-byte
        # after checking prediction identity, instead of silently downgrading
        # it when this isolated checkout lacks historical run directories.
        original_freeze_serving(destination)
        serving = read_json(destination)
        for model in incumbents:
            serving["models"][model] = previous_serving["models"][model]
        for slug, model in NEW_MODELS.items():
            evidence = serving["models"][model]["evidence"]
            if evidence["kind"] != "run_state":
                raise SystemExit(f"Missing frozen run-state evidence for {model}")
            evidence["run"] = f"adds0928/{slug}"
        counts = {"run_state": 0, "registry": 0}
        for treatment in serving["models"].values():
            counts[treatment["evidence"]["kind"]] += 1
        serving["evidence_summary"] = counts
        serving["registry_commit"] = freezer._serving_registry_commit(serving)
        write_json(destination, serving)

    freezer.freeze_serving_configuration = freeze_serving
    write_json(ROOT / "app/src/data.artifact.json", pointer)
    write_json(versions_path, versions)
    freezer.ANNOTATIONS_DEST.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        staged_annotations / "us_adjudications.json",
        freezer.ANNOTATIONS_DEST / "us_adjudications.json",
    )
    freezer.main()
    cache = ROOT / "app/.cache" / f"dashboard-data-{payload_hash[:16]}.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(payload_path, cache)
    freezer.gzip_deterministic(
        source_us / "predictions.csv",
        stage / "predictions.csv.gz",
        stored_name="predictions.csv",
    )
    print(f"Built {args.tag} locally; payload and predictions remain in {stage}")
    print("Next: update note and paper prose, render the paper, re-pin, run tests.")


if __name__ == "__main__":
    main()
