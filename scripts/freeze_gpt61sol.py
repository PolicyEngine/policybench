"""Build the GPT-6.1 Sol release locally from a strictly gated stage.

Adapted from freeze_adds0928.py. It configures the existing freezer in process
and never calls a release upload. Run only after finish_gpt61sol.py --step
export has written release-ready.json. The optional --dry-run validates inputs
without changing repository files. This release has no reference revision:
the references, exclusions and scenarios must equal release 20260929's pinned
bytes, and the adjudications may change only through a staged record that
triage applied and export bound.
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
sys.path.insert(0, str(ROOT / "scripts"))

import finish_gpt61sol as driver  # noqa: E402

# The treatment check is release-independent; reuse it unchanged.
from freeze_adds0928 import validate_treatment  # noqa: E402

RUN = driver.RUN_NAME
NEW_MODELS = dict(driver.MODELS)
BOARD_MODELS = driver.BOARD_MODELS
# Frozen serving evidence names the supervised run by its runs root and slug.
EVIDENCE_RUN_ROOT = "adds202609"
ADJUDICATIONS = "us_adjudications.json"


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


def verify_receipt(stage: Path, payload_path: Path, tag: str) -> dict:
    """The strict export receipt must bind this payload and all staged evidence."""
    receipt = read_json(stage / "release-ready.json")
    if (
        receipt.get("payload_sha256") != digest(payload_path)
        or receipt.get("models") != BOARD_MODELS
        or receipt.get("partial") is not False
        or receipt.get("release_tag") != tag
    ):
        raise SystemExit(
            f"Strict export receipt does not match {payload_path.name} "
            f"(release tag {tag!r}; re-export after changing RELEASE_TAG)"
        )
    if (
        receipt.get("base_tag") != driver.BASE_TAG
        or receipt.get("base_sha256") != driver.BASE_SHA256
    ):
        raise SystemExit(
            "Strict export receipt does not name release 20260929 as its base "
            f"({receipt.get('base_tag')!r}, {receipt.get('base_sha256')!r})"
        )
    if not receipt.get("files"):
        raise SystemExit("Strict export receipt is missing staged evidence hashes")
    for name, expected in receipt["files"].items():
        source = (stage / name).resolve()
        if (
            not source.is_relative_to(stage)
            or not source.is_file()
            or digest(source) != expected
        ):
            raise SystemExit(f"Staged evidence changed since strict export: {name}")
    bundle = Path("publish") / RUN
    required = [bundle / "us" / name for name in driver.REFERENCE_FILES]
    required += [bundle / "us/predictions.csv", bundle / "annotations" / ADJUDICATIONS]
    required += [Path("inputs") / slug / "run_state.json" for slug in NEW_MODELS]
    # What the adjudication and verdict gates allow rests on these.
    required += [Path(driver.PROMPT_CHANGES), Path("stage.json")]
    if (stage / driver.AMENDMENTS).exists():
        required.append(Path(driver.AMENDMENTS))
    unbound = [str(p) for p in required if str(p) not in receipt["files"]]
    if unbound:
        raise SystemExit(f"Strict export receipt does not bind: {unbound}")
    return receipt


def verify_references(source_us: Path, frozen_run: Path, manifest: dict) -> None:
    """Staged, committed and manifest-pinned references all equal 20260929's."""
    pins = manifest["source_run_artifacts"][RUN]["files"]
    for name, pin in driver.BASE_REFERENCE_SHA256.items():
        if digest(source_us / name) != pin:
            raise SystemExit(f"Staged {name} changed: this release has no revision")
        if digest(frozen_run / name) != pin:
            raise SystemExit(f"Committed {name} changed: this release has no revision")
        if pins.get(name) != pin:
            raise SystemExit(f"Manifest pin for {name} is not release 20260929's")


def verify_adjudication_record(
    staged: Path,
    source_us: Path,
    rejudged: frozenset[str],
    amendments: list[dict],
    cases_dir: Path | None = None,
) -> int:
    """The staged record may change only where GPT-6.1 Sol re-opened a case.

    The baseline is release 20260929's record in git (BASE_COMMIT), never the
    working-tree copy this freeze overwrites. A re-opened case may rewrite its
    judge fields, and its reasoning exactly as the listed wording amendments
    say; nothing else in any committed entry may change, and the scoring
    exclusions stay release 20260929's. Returns how many staged decisions the
    committed record lacks. The staged file's bytes must be exactly its
    parsed content, with 20260929's note and conventions; with ``cases_dir``,
    each re-opened entry must be restated as the restate script does. The
    staged record, prompt-changes.json and the amendments are bound by the
    receipt, which export writes only after triage applied them.
    """
    from policybench.adjudications import excluded_case_keys, load_adjudications
    from policybench.reference_exclusions import (
        exclusion_keys,
        load_reference_exclusions,
    )

    driver.verify_record_form(staged.read_text(), driver.base_adjudication_record())
    after = load_adjudications(staged)
    base = driver.base_adjudications()
    added = driver.verify_adjudication_changes(base, after, rejudged, amendments)
    if cases_dir is not None:
        driver.verify_restatements(base, after, rejudged, cases_dir)
    if excluded_case_keys(after) != exclusion_keys(
        load_reference_exclusions(source_us)
    ):
        raise SystemExit(
            "Staged adjudications change the scoring exclusions; this release "
            "has no reference revision"
        )
    return added


def base_prediction_rows():
    """Release 20260929's predictions, read from git at BASE_COMMIT.

    Never the working-tree copy, which the freezer rewrites from the stage: a
    freeze that stopped partway would compare the staged rows with themselves.
    """
    import io

    import pandas as pd

    path = Path("paper/snapshot/20260501/runs") / RUN / "predictions.csv.gz"
    return pd.read_csv(
        io.BytesIO(driver.base_commit_blob(path)), compression="gzip", low_memory=False
    )


def base_serving_config() -> dict:
    """Release 20260929's serving configuration, read from git at BASE_COMMIT."""
    path = Path("paper/snapshot/20260501/model_serving_config.json")
    return json.loads(driver.base_commit_blob(path))


def verify_annotation_amendments(annotations: Path, amendments: list[dict]) -> None:
    """Every listed case-note and row-annotation amendment is in the staged CSVs.

    Amendments of one text apply in order, and a later one may rewrite words
    an earlier one wrote, so the expected fragments are chained the same way
    before each is looked for in the staged text.
    """
    import pandas as pd

    frames = {
        "case_annotation": pd.read_csv(annotations / "us_case_notes.csv"),
        "annotation": pd.read_csv(annotations / "us_audit_row_annotations.csv"),
    }
    expected: dict[tuple, list[str]] = {}
    for item in amendments:
        if item["field"] not in frames:
            continue
        target = (item["case_id"], item["field"], item.get("model"))
        fragments = expected.setdefault(target, [])
        for index, fragment in enumerate(fragments):
            if item["old"] in fragment:
                fragments[index] = fragment.replace(item["old"], item["new"], 1)
                break
        else:
            fragments.append(item["new"])
    for (case, field, model), fragments in expected.items():
        frame = frames[field]
        country, scenario, variable = case.split("__", 2)
        mask = (
            (frame["country"].astype(str) == country)
            & (frame["scenario_id"].astype(str) == scenario)
            & (frame["variable"].astype(str) == variable)
        )
        if model is not None:
            mask &= frame["model"].astype(str) == model
        texts = frame.loc[mask, field].astype(str).tolist()
        if len(texts) != 1 or any(fragment not in texts[0] for fragment in fragments):
            raise SystemExit(
                f"Staged {field} of {case} does not carry its listed wording "
                "amendment; run triage and export again"
            )


def freeze_amendments(stage: Path, destination: Path) -> None:
    """Commit the stage's wording amendments beside the adjudication record.

    The amended case notes, row annotations and reasoning are published; the
    list says what changed, from what, and why.
    """
    source = stage / driver.AMENDMENTS
    if source.exists() and json.loads(source.read_text())["amendments"]:
        shutil.copyfile(source, destination / f"us_{driver.AMENDMENTS}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--tag", default=driver.RELEASE_TAG)
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

    payload_path = stage / f"data-board{BOARD_MODELS}.json"
    verify_receipt(stage, payload_path, args.tag)
    payload_hash = digest(payload_path)
    payload = read_json(payload_path)
    recombined = json.dumps({"countries": {"us": payload["countries"]["us"]}})
    if recombined.encode() != payload_path.read_bytes():
        raise SystemExit("Payload does not recombine to the freeze format")
    errors = validate_dashboard_payload(payload, require_failure_annotations=True)
    if errors:
        raise SystemExit(f"Strict dashboard gate failed: {errors[:5]}")
    stats = payload["countries"]["us"]["modelStats"]
    model_names = {row["model"] for row in stats}
    if len(stats) != BOARD_MODELS or any(
        row["condition"] != "no_tools" for row in stats
    ):
        raise SystemExit(
            f"Release must contain exactly {BOARD_MODELS} no-tools model rows"
        )

    snapshot = ROOT / "paper/snapshot/20260501"
    frozen_run = snapshot / "runs" / RUN
    # The incumbents' frozen serving evidence is release 20260929's, from git.
    previous_serving = base_serving_config()
    incumbents = set(previous_serving["models"]) - set(NEW_MODELS.values())
    if len(incumbents) != driver.BASE_MODELS or model_names != incumbents | set(
        NEW_MODELS.values()
    ):
        raise SystemExit(
            f"Frozen incumbent roster and staged {BOARD_MODELS}-model roster disagree"
        )
    source_run = stage / "publish" / RUN
    source_us = source_run / "us"
    verify_references(source_us, frozen_run, read_json(snapshot / "manifest.json"))
    staged_annotations = source_run / "annotations"
    rejudged = driver.rejudged_cases(stage)
    amendments = driver.load_amendments(stage, rejudged)
    added = verify_adjudication_record(
        staged_annotations / ADJUDICATIONS,
        source_us,
        rejudged,
        amendments,
        stage / "audit" / "cases",
    )
    verify_annotation_amendments(staged_annotations, amendments)
    previous_rows = base_prediction_rows()
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

    adjudications = freezer.load_adjudications(staged_annotations / ADJUDICATIONS)
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
        r" - \d+ models$", f" - {BOARD_MODELS} models", live["description"]
    )
    if changed != 1:
        raise SystemExit("Live version description has an unexpected model-count shape")
    live.update(description=description, snapshotLabel=f"Snapshot {date}")
    if args.dry_run:
        print(
            f"Validated local release inputs: {args.tag}, {BOARD_MODELS} models, "
            f"{payload_hash}; references unchanged; {added} adjudications added; "
            f"{len(amendments)} wording amendments"
        )
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
            evidence["run"] = f"{EVIDENCE_RUN_ROOT}/{slug}"
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
        staged_annotations / ADJUDICATIONS,
        freezer.ANNOTATIONS_DEST / ADJUDICATIONS,
    )
    freezer.main()
    freeze_amendments(stage, freezer.ANNOTATIONS_DEST)
    # The freezer copies the staged references byte for byte; confirm it.
    driver.verify_reference_pins(frozen_run, "frozen reference")
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
