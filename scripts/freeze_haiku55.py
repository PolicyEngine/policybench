"""Build the Claude Haiku 5.5 release locally from a strictly gated stage.

Adapted from freeze_gpt61sol.py. It configures the existing freezer in process
and never calls a release upload. Run only after finish_haiku55.py --step
export has written release-ready.json. The optional --dry-run validates inputs
without changing repository files. Both rebuild the payload from the bound
bundle, as export builds it, and refuse a staged payload that differs.

The release folds one model onto release 20261006 and installs the ten
exclusions Max ruled on 2026-10-06 (docs/haiku55/spec.json). The reference
outputs, the scenarios and their sidecars must equal release 20261006's pinned
bytes. The exclusion record must be release 20261006's plus the ten ruled
records, as finish_haiku55.build_release_exclusions spells it. The
adjudications may change only through a staged record that triage applied and
export bound: the ruled outputs' entries, a re-opened case's judge fields, and
date conventions that name the 2026-10-06 wave. The committed wording
amendments record stays release 20261006's, with any stage list appended.
"""

from __future__ import annotations

import argparse
import copy
import datetime
import functools
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
os.environ["OPENBLAS_NUM_THREADS"] = "1"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import finish_haiku55 as driver  # noqa: E402

# The treatment check is release-independent; reuse it unchanged.
from freeze_adds0928 import validate_treatment  # noqa: E402

# The manifest comparison and the version description's exclusion counts are
# release 20261006's, which also added exclusions; reuse them unchanged.
from release_20261006 import leaf_paths  # noqa: E402
from release_20261006 import versions_description as count_exclusions  # noqa: E402

RUN = driver.RUN_NAME
NEW_MODELS = dict(driver.MODELS)
BOARD_MODELS = driver.BOARD_MODELS
ADJUDICATIONS = "us_adjudications.json"
# The published annotations the adjudications and amendments are applied to.
ANNOTATION_CSVS = ("us_audit_row_annotations.csv", "us_case_notes.csv")
# The reference narratives a judge's prompt carries. This release rewords
# none, so the staged file must be release 20261006's.
EXPLANATIONS = "us_case_reference_explanations.csv"
# The wording amendments record, as it is committed beside the adjudications.
COMMITTED_AMENDMENTS = f"us_{driver.AMENDMENTS}"
EXCLUSIONS = "reference_exclusions.json"
# The reference files this release may not change at all.
PINNED_REFERENCES = tuple(
    name for name in driver.BASE_REFERENCE_SHA256 if name != EXCLUSIONS
)
SNAPSHOT = Path("paper/snapshot/20260501")
ANNOTATIONS = Path("annotations") / RUN
POINTER = Path("app/src/data.artifact.json")
VERSIONS = Path("app/src/data.versions.json")
# The engines the exclusion records were decided on, which the live version's
# description counts by name.
EXCLUSION_ENGINES = frozenset({"policyengine-us 1.755.4", "policyengine-us 2.15.17"})
# Manifest paths the freeze may change from release 20261006's; every other
# leaf must equal that release's manifest, read from git at BASE_COMMIT.
MANIFEST_CHANGES = (
    ("audit_annotation_artifacts", "files"),
    ("audit_annotation_artifacts", "developer_adjudications"),
    ("audit_annotation_artifacts", "judge_provenance"),
    # The note counts the audited prediction rows, which the addition extends.
    ("audit_annotation_artifacts", "note"),
    ("committed_snapshot_artifacts", "model_serving_config.json"),
    ("committed_snapshot_artifacts", "us_impact_summary_by_model.csv"),
    ("description",),
    ("files",),
    ("live_dashboard_artifact",),
    ("model_response_date",),
    ("published_dashboard_artifact",),
    ("reference_exclusions",),
    ("reference_output_refresh", "snapshot_date"),
    ("rendered_paper_artifacts",),
    ("reproducibility_notes",),
    ("scope", "models"),
    ("snapshot_date",),
    ("source_run_artifacts", RUN, "files"),
)
# Pins under those paths that must stay release 20261006's all the same.
MANIFEST_PINNED = frozenset(
    {
        *(("source_run_artifacts", RUN, "files", name) for name in PINNED_REFERENCES),
        ("audit_annotation_artifacts", "files", EXPLANATIONS),
    }
)


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


def judged_cases(audit: Path) -> list[str]:
    """The cases validate_verdicts requires a verdict for, from the manifest.

    A stage without a manifest has none; the receipt then fails to bind
    audit/cases.jsonl.
    """
    manifest = audit / "cases.jsonl"
    if not manifest.is_file():
        return []
    items = map(json.loads, manifest.read_text().splitlines())
    return [item["case_id"] for item in items if not item["parse_failure_only"]]


def verify_freezer_destinations(freezer) -> None:
    """freeze_snapshot must write into this checkout, and only there.

    Both modules find the checkout from their own file, so they agree unless
    another checkout's freeze_snapshot.py comes first on the import path; that
    freezer would overwrite the other checkout's tracked snapshot.
    """
    expected = {
        "ROOT": ROOT,
        "SNAPSHOT_DIR": ROOT / SNAPSHOT,
        "RUN_DEST": ROOT / SNAPSHOT / "runs" / RUN,
        "ANNOTATIONS_DEST": ROOT / ANNOTATIONS,
    }
    elsewhere = {
        name: str(getattr(freezer, name))
        for name, path in expected.items()
        if Path(getattr(freezer, name)).resolve() != path.resolve()
    }
    if elsewhere or freezer.RUN_LABEL != RUN:
        raise SystemExit(
            f"freeze_snapshot would write outside this checkout ({ROOT}): "
            f"{elsewhere or freezer.RUN_LABEL}"
        )


def release_spec(tag: str) -> dict:
    """docs/haiku55/spec.json, with what the freeze reads from it checked.

    The snapshot date and the day the 2026-10-06 wave's decisions were written
    come from the spec alone, so a spec that lacks either stops the freeze
    here, before any gate reads it. The spec must also name the release this
    freeze builds and the base the driver pins.
    """
    spec = driver.load_spec()
    try:
        datetime.date.fromisoformat(spec.get("snapshot_date"))
    except (TypeError, ValueError):
        raise SystemExit(
            f"{driver.SPEC_PATH} names no snapshot_date (YYYY-MM-DD): "
            f"{spec.get('snapshot_date')!r}"
        ) from None
    written = spec.get("adjudications_written_on")
    if not isinstance(written, str) or not written.strip():
        raise SystemExit(
            f"{driver.SPEC_PATH} names no adjudications_written_on, the UTC day "
            "the 2026-10-06 wave's decisions were written; the record's date "
            "conventions state it"
        )
    named = {
        "release_tag": tag,
        "base_tag": driver.BASE_TAG,
        "base_sha256": driver.BASE_SHA256,
    }
    differ = {
        field: spec.get(field)
        for field, value in named.items()
        if spec.get(field) != value
    }
    if differ:
        raise SystemExit(
            f"{driver.SPEC_PATH} names another release or base than this freeze "
            f"builds ({named}): {differ}"
        )
    return spec


def engine_upgrade_installed(stage: Path) -> bool:
    """Whether the stage's stage.json records an installed engine upgrade of
    the references; an unreadable stage.json is left to the later gates."""
    try:
        receipt = read_json(stage / "stage.json")
    except (OSError, ValueError):
        return False
    return isinstance(receipt, dict) and bool(receipt.get("references_installed"))


def verify_verdicts(stage: Path) -> None:
    """Every judged verdict passes the driver's own gate against the bound seed.

    Export validates verdicts before it writes the receipt, but the receipt
    only binds hashes: a kept verdict edited afterwards, its sidecar and
    receipt entry re-hashed, must still be the seed's byte for byte, and every
    new one bound to its prompt and its Opus 5.5 judge. Without
    ``remove_invalid`` validate_verdicts changes nothing.
    """
    pending = driver.validate_verdicts(stage / "audit", seed=driver.load_seed(stage))
    if pending:
        raise SystemExit(
            f"{len(pending)} staged verdicts fail validation: {pending[:8]}; "
            "run judge and export again"
        )


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
            "Strict export receipt does not name release 20261006 as its base "
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
    required += [bundle / "annotations" / name for name in ANNOTATION_CSVS]
    required += [bundle / "annotations" / EXPLANATIONS]
    # Each new model's pinned run files, and the prepare-time hashes.
    required += [
        Path("inputs") / slug / name
        for slug in NEW_MODELS
        for name in driver.PINNED_INPUTS
    ]
    required += [Path("model-provenance.json")]
    # What the adjudication and verdict gates allow rests on these; stage.json
    # also records the exclusions install-exclusions wrote.
    required += [Path(driver.PROMPT_CHANGES), Path("stage.json")]
    if (stage / driver.AMENDMENTS).exists():
        required.append(Path(driver.AMENDMENTS))
    # Every judged case's audit evidence, as validate_verdicts reads it: an
    # unbound verdict or sidecar could be edited and re-hashed after export.
    # So could the transcript the provenance gate reads for an isolated judge.
    required += [Path("audit/cases.jsonl"), Path("audit/schema.json")]
    for case in judged_cases(stage / "audit"):
        directory = Path("audit/cases") / case
        required += [
            directory / name for name in ("verdict.json", "verdict.meta.json")
        ] + [directory / "prompt.md"]
        if (stage / directory / "claude.transcript.jsonl").is_file():
            required.append(directory / "claude.transcript.jsonl")
    unbound = [str(p) for p in required if str(p) not in receipt["files"]]
    if unbound:
        raise SystemExit(f"Strict export receipt does not bind: {unbound}")
    return receipt


def verify_installed_exclusions(stage: Path, receipt: dict, text: str) -> str:
    """The stage scores on the release's exclusion record, as installed.

    ``text`` is release 20261006's record plus the ten ruled records
    (finish_haiku55.build_release_exclusions, spelled by exclusions_text),
    rebuilt now from git and the spec. The staged record must be those bytes,
    the receipt must bind them, and stage.json, which the receipt binds, must
    record them as --step install-exclusions wrote them: the installed and
    base hashes, the record count, and the prepared file's hash. Returns the
    record's sha256.
    """
    bound = str(Path("publish") / RUN / "us" / EXCLUSIONS)
    expected = hashlib.sha256(text.encode()).hexdigest()
    staged = stage / bound
    if not staged.is_file() or staged.read_bytes() != text.encode():
        raise SystemExit(
            f"Staged {EXCLUSIONS} is not release 20261006's record plus the "
            f"{driver.NEW_EXCLUSIONS} ruled records ({driver.SPEC_PATH}); run "
            "--step install-exclusions, then triage and export again"
        )
    if receipt["files"].get(bound) != expected:
        raise SystemExit(
            f"Strict export receipt does not bind the installed {EXCLUSIONS}"
        )
    prepared = read_json(stage / "stage.json")
    installed = prepared.get("exclusions_installed")
    recorded = prepared.get("files")
    if (
        not isinstance(installed, dict)
        or not isinstance(recorded, dict)
        or installed.get("sha256") != expected
        or installed.get("base_sha256") != driver.BASE_REFERENCE_SHA256[EXCLUSIONS]
        or installed.get("records") != driver.RELEASE_EXCLUSIONS
        or recorded.get(bound) != expected
    ):
        raise SystemExit(
            f"stage.json does not record the release's {driver.RELEASE_EXCLUSIONS} "
            "exclusions as --step install-exclusions writes them "
            f"(exclusions_installed {installed!r}); run it, then triage and "
            "export again"
        )
    return expected


def verify_scored_outputs(country: dict, exclusions: list[dict]) -> None:
    """The payload publishes the release's exclusions and scores what remains.

    Its referenceExclusions name the record's outputs, in the record's order,
    and every model is scored on the outputs left. The rebuild checks the
    whole payload; this names the two counts the release states.
    """
    published = [
        (item.get("scenarioId"), item.get("variable"))
        for item in country.get("referenceExclusions", [])
    ]
    expected = [driver.spec_key(record) for record in exclusions]
    if published != expected:
        differ = sorted(set(published) ^ set(expected)) or ["their order"]
        raise SystemExit(
            f"The payload's {len(published)} excluded outputs are not the "
            f"release's {len(expected)}: {differ[:8]}"
        )
    scored = {row["model"]: row.get("n") for row in country["modelStats"]}
    off = {model: n for model, n in scored.items() if n != driver.RELEASE_SCORED}
    if off:
        raise SystemExit(
            f"Every model must be scored on {driver.RELEASE_SCORED} outputs: {off}"
        )


def verify_judge_provenance(
    stage: Path, receipt: dict, rejudged: frozenset[str]
) -> None:
    """The judge provenance record is the one export bound, and still true.

    The record is a repository file (driver.JUDGE_PROVENANCE), so the receipt
    binds it apart from the stage's files. Its bytes must be the ones export
    hashed, and it must still describe the staged new verdicts and their
    transcripts, as export checked.
    """
    bound = receipt.get("judge_provenance")
    if (
        not isinstance(bound, dict)
        or bound.get("path") != driver.JUDGE_PROVENANCE_PATH
        or not driver.JUDGE_PROVENANCE.is_file()
        or bound.get("sha256") != digest(driver.JUDGE_PROVENANCE)
    ):
        raise SystemExit(
            f"{driver.JUDGE_PROVENANCE_PATH} is not the judge provenance record "
            "the strict export bound; export again"
        )
    driver.verify_judge_provenance(
        stage / "audit" / "cases", rejudged, driver.JUDGE_PROVENANCE
    )


def verify_references(
    source_us: Path, frozen_run: Path, manifest: dict, exclusions_sha256: str
) -> None:
    """The references are release 20261006's; only the exclusion record moves.

    The reference outputs, the scenarios and their sidecars must equal release
    20261006's pins in the stage, in the committed snapshot and in the
    manifest. The staged exclusion record must be the release's
    (``exclusions_sha256``). Its committed copy and its manifest pin are
    release 20261006's before this freeze and the release's after it, so a
    second freeze finds either.
    """
    pins = manifest["source_run_artifacts"][RUN]["files"]

    def matches(path: Path, allowed: set[str]) -> bool:
        return path.is_file() and digest(path) in allowed

    for name, pin in driver.BASE_REFERENCE_SHA256.items():
        staged, committed = {pin}, {pin}
        reason = "this release revises no reference value"
        whose = "not release 20261006's"
        if name == EXCLUSIONS:
            staged, committed = {exclusions_sha256}, {pin, exclusions_sha256}
            reason = "it is not the release's record"
            whose = "neither release 20261006's nor this release's"
        if not matches(source_us / name, staged):
            raise SystemExit(f"Staged {name} changed: {reason}")
        if not matches(frozen_run / name, committed):
            raise SystemExit(f"Committed {name} changed: it is {whose}")
        if pins.get(name) not in committed:
            raise SystemExit(f"Manifest pin for {name} is {whose}")


def verify_explanations(staged_annotations: Path) -> None:
    """The staged reference explanations are release 20261006's, from git.

    A judge's prompt carries them, and this release rewords none: prepare
    copies the committed file, and no step writes it. The payload publishes
    them, so an explanation edited after export, with the payload rebuilt to
    match and every hash updated, would otherwise pass.
    """
    base = driver.base_commit_blob(ANNOTATIONS / EXPLANATIONS)
    staged = staged_annotations / EXPLANATIONS
    if not staged.is_file() or staged.read_bytes() != base:
        raise SystemExit(
            f"Staged {EXPLANATIONS} changed: this release rewords no reference "
            "explanation"
        )


def verify_adjudication_record(
    staged: Path,
    source_us: Path,
    rejudged: frozenset[str],
    amendments: list[dict],
    cases_dir: Path,
) -> int:
    """The staged record changes release 20261006's only as the release says.

    The baseline is release 20261006's record in git (BASE_COMMIT), never the
    working-tree copy this freeze overwrites. The ten ruled outputs must carry
    exactly the entries the driver builds for them from the spec and each
    case's bound verdict. A case Claude Haiku 5.5 re-opened may rewrite its
    judge fields, restated as the restate script does, and its reasoning
    exactly as the listed wording amendments say. Nothing else in any
    committed entry may change. The record excludes exactly the outputs the
    staged exclusion record lists. The staged file's bytes must be exactly its
    parsed content, with release 20261006's note, and its date conventions
    with the 2026-10-06 wave named (driver.release_date_conventions). Returns
    how many staged decisions, beyond the ruled ones, the committed record
    lacks. The staged record, prompt-changes.json and the amendments are bound
    by the receipt, which export writes only after triage applied them.
    """
    from policybench.adjudications import excluded_case_keys, load_adjudications
    from policybench.reference_exclusions import (
        exclusion_keys,
        load_reference_exclusions,
    )

    driver.verify_record_form(staged.read_text(), driver.base_adjudication_record())
    after = load_adjudications(staged)
    base = driver.base_adjudications()
    added = driver.verify_adjudication_changes(
        base, after, rejudged, amendments, cases_dir
    )
    driver.verify_restatements(base, after, rejudged, cases_dir)
    decided = excluded_case_keys(after)
    excluded = exclusion_keys(load_reference_exclusions(source_us))
    if decided != excluded:
        raise SystemExit(
            "Staged adjudications and the staged exclusion record disagree on "
            f"the excluded outputs: {sorted(decided ^ excluded)[:8]}; the release "
            f"excludes the {driver.RELEASE_EXCLUSIONS} the spec lists"
        )
    return added


def payload_differences(
    rebuilt, staged, path: str = "payload", limit: int = 5
) -> list[str]:
    """The first ``limit`` paths at which two parsed JSON values differ.

    Key order counts, as it does in the bytes: the paths are empty exactly
    when the two values serialize to the same JSON. A list item that names a
    model is labelled with it.
    """
    found: list[str] = []

    def walk(a, b, at: str) -> None:
        if len(found) >= limit:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in a:
                if key in b:
                    walk(a[key], b[key], f"{at}.{key}")
                else:
                    found.append(f"{at}.{key} (only rebuilt)")
            found.extend(f"{at}.{key} (only staged)" for key in b if key not in a)
            if a.keys() == b.keys() and list(a) != list(b):
                found.append(f"{at} (key order)")
        elif isinstance(a, list) and isinstance(b, list):
            for index, (x, y) in enumerate(zip(a, b)):
                name = x.get("model") if isinstance(x, dict) else None
                label = f"{index} {name}" if isinstance(name, str) else index
                walk(x, y, f"{at}[{label}]")
            if len(a) != len(b):
                found.append(f"{at} (length {len(a)} rebuilt, {len(b)} staged)")
        elif json.dumps(a) != json.dumps(b):
            found.append(at)

    walk(rebuilt, staged, path)
    return found[:limit]


def rebuild_payload(stage: Path, receipt: dict, payload_path: Path, live: dict) -> None:
    """The staged payload must be what export builds from the bound bundle.

    The receipt binds the payload only by a hash that sits beside it, so a
    payload edited after export (the addition's scores, an incumbent's cost, a
    case's classes) with its receipt rehashed passes every other gate.
    Export's own build (driver.build_payload, against release 20261006 as
    ``live``) runs again on a scratch copy of the bundle files the receipt
    binds, each checked against its receipt hash, and its bytes must equal the
    staged payload's. That build scores every model on the release's outputs
    and repeats export's scope check: with release 20261006's exclusion
    record put back, every incumbent's modelStats is that release's, byte for
    byte. The copy is the bundle's: export_full_run writes data.json,
    us/data.json and us/analysis/ into the bundle it reads, and its data.json
    lacks the carried usage, so a rebuild in place would rewrite the stage.
    """
    bundle = Path("publish") / RUN
    with tempfile.TemporaryDirectory(prefix="freeze-haiku55-") as scratch:
        copy_root = Path(scratch) / RUN
        for name, expected in receipt["files"].items():
            if not Path(name).is_relative_to(bundle):
                continue
            target = copy_root / Path(name).relative_to(bundle)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / name, target)
            if digest(target) != expected:
                raise SystemExit(f"Staged evidence changed since strict export: {name}")
        rebuilt = driver.payload_text(driver.build_payload(copy_root, live))
    staged = payload_path.read_bytes()
    if rebuilt.encode() != staged:
        differ = payload_differences(json.loads(rebuilt), json.loads(staged))
        raise SystemExit(
            f"Staged {payload_path.name} is not what export builds from the "
            f"bound bundle; it differs at {differ or ['its serialization']}; "
            "export again"
        )


def base_prediction_rows():
    """Release 20261006's predictions, read from git at BASE_COMMIT.

    Never the working-tree copy, which the freezer rewrites from the stage: a
    freeze that stopped partway would compare the staged rows with themselves.
    """
    import io

    import pandas as pd

    path = SNAPSHOT / "runs" / RUN / "predictions.csv.gz"
    return pd.read_csv(
        io.BytesIO(driver.base_commit_blob(path)), compression="gzip", low_memory=False
    )


def base_serving_config() -> dict:
    """Release 20261006's serving configuration, read from git at BASE_COMMIT."""
    return json.loads(driver.base_commit_blob(SNAPSHOT / "model_serving_config.json"))


def annotation_differences(
    rebuilt_text: str, staged: Path, key: list[str], limit: int = 4
) -> list[str]:
    """The first ``limit`` places where a staged annotation CSV is not the
    rebuilt one: a column set or order, a row only one side has, or a cell
    (named by its case, model and column). Empty when the two parse to the
    same cells, so only the row order or the serialization differs."""
    import io

    import pandas as pd

    def read(source) -> pd.DataFrame:
        return pd.read_csv(source, dtype=str, keep_default_na=False)

    try:
        rebuilt, published = read(io.StringIO(rebuilt_text)), read(staged)
    except ValueError:
        return ["its serialization"]
    if list(rebuilt.columns) != list(published.columns):
        return [f"its columns {list(published.columns)}, not {list(rebuilt.columns)}"]

    def by_key(frame: pd.DataFrame) -> dict[tuple, dict]:
        return {tuple(row[k] for k in key): row for row in frame.to_dict("records")}

    found = []
    if published.duplicated(key).any():
        found.append(f"duplicate {key} rows")
    built, staged_rows = by_key(rebuilt), by_key(published)
    for item in sorted(set(built) | set(staged_rows)):
        name = "__".join(item)
        if item not in staged_rows or item not in built:
            side = "rebuilt" if item in built else "staged"
            found.append(f"{name} (only {side})")
            continue
        found += [
            f"{name} {column}"
            for column in rebuilt.columns
            if built[item][column] != staged_rows[item][column]
        ]
    return found[:limit]


def verify_annotation_amendments(
    annotations: Path, amendments: list[dict], audit: Path
) -> None:
    """The staged row annotations and case notes are what triage builds from
    the verdicts, the staged adjudications and the listed amendments, in every
    column.

    Both frames are rebuilt as triage builds them: collect_audit folds each
    verdict into its rows (the model's failure class and diagnosis) and its
    case note (the case's classes, flag, hypothesis and rationale); the staged
    adjudication record, whose reasoning verify_adjudication_record has
    already replayed, sets each decided case's classes and appends its
    sentence to the case note; then the listed amendments are replayed in
    order, each old wording found exactly once when it is applied. Each staged
    file must be the rebuilt frame's bytes as triage writes them
    (driver.annotation_csv_text), so a failure class, flag or count edited on
    a case no adjudication decides is refused as surely as unlisted wording,
    even beside a listed fragment.
    """
    from policybench.adjudications import apply_adjudications, load_adjudications
    from policybench.audit import collect_audit

    collected = collect_audit(annotations.parent / "us", audit)
    rows, cases, _ = apply_adjudications(
        collected["row"],
        collected["case"].rename(
            columns={
                "case_failure_source": "case_failure_sources",
                "case_failure_subtype": "case_failure_subtypes",
            }
        ),
        load_adjudications(annotations / ADJUDICATIONS),
    )
    driver.amend_annotations(rows, cases, amendments)
    for name, rebuilt, key in (
        ("us_case_notes.csv", cases, driver.KEY),
        ("us_audit_row_annotations.csv", rows, [*driver.KEY, "model"]),
    ):
        text = driver.annotation_csv_text(rebuilt)
        if text.encode() != (annotations / name).read_bytes():
            differ = annotation_differences(text, annotations / name, ["country", *key])
            raise SystemExit(
                f"Staged {name} is not what triage builds from the verdicts, the "
                "staged adjudications and the listed wording amendments; it "
                f"differs at {differ or ['its row order or serialization']}; run "
                "triage and export again"
            )


def amendments_text(record: dict) -> str:
    """The wording amendments record as the committed file spells it."""
    return json.dumps(record, indent=1, ensure_ascii=False)


def committed_amendments(stage: Path) -> bytes:
    """The wording amendments record this freeze commits.

    Release 20261006's committed record (from git at BASE_COMMIT) lists the
    amendments GPT-6.1 Sol's re-opened cases needed, and that wording is still
    published, so the record is never replaced. With no stage list, or an
    empty one, it is committed unchanged. A stage list (driver.load_amendments
    checks each item names a case Claude Haiku 5.5 re-opened) is appended
    after the earlier amendments, in its own order, and the note says which
    items are this release's; a note the stage list carries follows it.
    """
    base = driver.base_commit_blob(ANNOTATIONS / COMMITTED_AMENDMENTS)
    source = stage / driver.AMENDMENTS
    listed = json.loads(source.read_text()) if source.exists() else {}
    added = listed.get("amendments") or []
    if not added:
        return base
    record = json.loads(base)
    if amendments_text(record).encode() != base or list(record) != [
        "note",
        "amendments",
    ]:
        raise SystemExit(
            f"Release 20261006's {COMMITTED_AMENDMENTS} is not in its committed "
            "form; cannot append this release's wording amendments"
        )
    earlier = len(record["amendments"])
    note = (
        f"{record['note']} The last {len(added)} (after the first {earlier}) "
        "are for cases Claude Haiku 5.5 re-opened (finish_haiku55.py "
        "load_amendments)."
    )
    if isinstance(listed.get("note"), str) and listed["note"].strip():
        note += " " + listed["note"].strip()
    merged = {"note": note, "amendments": record["amendments"] + added}
    return amendments_text(merged).encode()


def freeze_amendments(stage: Path, destination: Path) -> None:
    """Commit the wording amendments record beside the adjudication record.

    freeze_snapshot rebuilds the annotations directory from the stage and so
    removes the committed record; this writes it back (committed_amendments).
    """
    (destination / COMMITTED_AMENDMENTS).write_bytes(committed_amendments(stage))


def evidence_runs() -> dict[str, str]:
    """The supervised run each new model's frozen serving evidence names.

    Its runs root and slug, read from the input pins as committed at HEAD
    (``run`` there is ``<runs root>/<slug>/run``): the same record the staged
    run files are checked against.
    """
    record = json.loads(driver.head_blob(driver.INPUT_PINS_PATH))
    runs = {}
    for slug in NEW_MODELS:
        named = (record.get("inputs") or {}).get(slug, {}).get("run")
        run = PurePosixPath(named or "")
        if len(run.parts) != 3 or run.parts[1:] != (slug, "run"):
            raise SystemExit(
                f"{driver.INPUT_PINS_PATH} does not name the supervised run of "
                f"{slug} as <runs root>/{slug}/run: {named!r}"
            )
        runs[slug] = run.parent.as_posix()
    return runs


def serving_problems(
    serving: dict, previous: dict, incumbents: set[str], runs: dict[str, str]
) -> list[str]:
    """Where a serving configuration is not the release's.

    Its models are the incumbents and the addition. Every incumbent's row is
    release 20261006's (``previous``), every field. Each new model's evidence
    is its run state and names its supervised run. The evidence summary is the
    tally of the rows' evidence kinds.
    """
    models = serving.get("models")
    if not isinstance(models, dict):
        return ["no models"]
    problems = []
    expected = set(incumbents) | set(NEW_MODELS.values())
    if set(models) != expected:
        problems.append(f"roster differs on {sorted(set(models) ^ expected)[:8]}")
    problems += [
        f"{model} is not release 20261006's row"
        for model in sorted(set(incumbents) & set(models))
        if json.dumps(models[model], sort_keys=True)
        != json.dumps(previous["models"][model], sort_keys=True)
    ]
    for slug, model in NEW_MODELS.items():
        evidence = (models.get(model) or {}).get("evidence") or {}
        if evidence.get("kind") != "run_state":
            problems.append(f"{model} has no run-state evidence")
        elif evidence.get("run") != runs[slug]:
            problems.append(
                f"{model}'s evidence names run {evidence.get('run')!r}, not "
                f"{runs[slug]!r}"
            )
    counts = {"run_state": 0, "registry": 0}
    for treatment in models.values():
        kind = (treatment.get("evidence") or {}).get("kind")
        counts[kind] = counts.get(kind, 0) + 1
    if serving.get("evidence_summary") != counts:
        problems.append(
            f"evidence_summary {serving.get('evidence_summary')!r} is not the "
            f"rows' tally {counts!r}"
        )
    return problems


def merge_serving(
    serving: dict, previous: dict, incumbents: set[str], runs: dict[str, str]
) -> dict:
    """The release's serving configuration, from the freezer's (``serving``).

    The old rows already have frozen evidence. They are release 20261006's,
    kept field for field after the incumbents' predictions were checked
    identical, instead of being silently downgraded when this checkout lacks
    the historical run directories. Each new model keeps the freezer's row,
    whose evidence must be its run state and is made to name its supervised
    run. The evidence summary is recounted.
    """
    merged = copy.deepcopy(serving)
    models = merged["models"]
    for model in incumbents:
        models[model] = copy.deepcopy(previous["models"][model])
    for slug, model in NEW_MODELS.items():
        evidence = models[model]["evidence"]
        if evidence["kind"] != "run_state":
            raise SystemExit(f"Missing frozen run-state evidence for {model}")
        evidence["run"] = runs[slug]
    counts = {"run_state": 0, "registry": 0}
    for treatment in models.values():
        counts[treatment["evidence"]["kind"]] += 1
    merged["evidence_summary"] = counts
    problems = serving_problems(merged, previous, incumbents, runs)
    if problems:
        raise SystemExit(f"Frozen serving configuration: {problems[:8]}")
    return merged


def release_pointer(tag: str, payload_path: Path, payload_hash: str) -> dict:
    """The dashboard pointer the freeze commits: the staged payload as the
    release asset dashboard-data.json under ``tag``."""
    return {
        "version": 1,
        "repo": "PolicyEngine/policybench",
        "tag": tag,
        "asset": "dashboard-data.json",
        "url": (
            "https://github.com/PolicyEngine/policybench/releases/download/"
            f"{tag}/dashboard-data.json"
        ),
        "sha256": payload_hash,
        "bytes": payload_path.stat().st_size,
    }


def release_versions(
    versions: dict, exclusions: list[dict], snapshot_date: str
) -> dict:
    """The version list with the live version describing this release.

    The live version is the default one, and its artifact is the live
    pointer. Its description counts the excluded outputs by the engine each
    record was decided on and ends with the board's model count; its snapshot
    label carries the spec's snapshot date. Nothing else changes, and applying
    this to its own result changes nothing.
    """
    out = copy.deepcopy(versions)
    live = [item for item in out["versions"] if item["id"] == out["default"]]
    if len(live) != 1 or live[0].get("artifact") != {"pointer": "live"}:
        raise SystemExit("The default version is not the one live-pointer version")
    engines = {record["engine_version"] for record in exclusions}
    if engines != EXCLUSION_ENGINES:
        raise SystemExit(
            "The live version description counts exclusions decided on "
            f"{sorted(EXCLUSION_ENGINES)}; the record's are {sorted(engines)}"
        )
    description, changed = re.subn(
        r" - \d+ models$",
        f" - {BOARD_MODELS} models",
        count_exclusions(live[0]["description"], exclusions),
    )
    if changed != 1:
        raise SystemExit("Live version description has an unexpected model-count shape")
    live[0].update(description=description, snapshotLabel=f"Snapshot {snapshot_date}")
    return out


def manifest_problems(before: dict, after: dict) -> list[tuple]:
    """The manifest leaves that differ outside what the release may change.

    A leaf may differ only under a MANIFEST_CHANGES path, and never at a
    MANIFEST_PINNED one: the pinned references and the reference explanations
    keep release 20261006's hashes.
    """
    return [
        path
        for path in leaf_paths(before, after)
        if path in MANIFEST_PINNED
        or not any(path[: len(prefix)] == prefix for prefix in MANIFEST_CHANGES)
    ]


def verify_frozen(
    *,
    stage: Path,
    snapshot: Path,
    annotations: Path,
    exclusions_sha256: str,
    pointer: dict,
    window: str,
    snapshot_date: str,
    previous_serving: dict,
    incumbents: set[str],
    runs: dict[str, str],
) -> None:
    """What the freezer wrote is the release, checked file by file.

    The frozen references are release 20261006's and the frozen exclusion
    record is the release's. The annotations directory holds the staged
    adjudications and annotation CSVs, byte for byte, and the wording
    amendments record; the frozen adjudication record is in the committed
    form with the 2026-10-06 wave named. The serving configuration keeps
    release 20261006's rows and adds the new model's. The manifest differs
    from release 20261006's only where the release may change it, and states
    the release's snapshot date, model count, response window, exclusion
    counts, artifact and exclusion pin.
    """
    staged_annotations = stage / "publish" / RUN / "annotations"
    frozen_run = snapshot / "runs" / RUN
    driver.verify_reference_pins(frozen_run, "frozen reference", exclusions_sha256)
    copied = (ADJUDICATIONS, *ANNOTATION_CSVS, EXPLANATIONS)
    frozen = sorted(path.name for path in annotations.iterdir() if path.is_file())
    if frozen != sorted((*copied, COMMITTED_AMENDMENTS)):
        raise SystemExit(f"Frozen annotation files are not the release's: {frozen}")
    for name in copied:
        if (annotations / name).read_bytes() != (
            staged_annotations / name
        ).read_bytes():
            raise SystemExit(f"The frozen {name} is not the staged one")
    driver.verify_record_form(
        (annotations / ADJUDICATIONS).read_text(), driver.base_adjudication_record()
    )
    if (annotations / COMMITTED_AMENDMENTS).read_bytes() != committed_amendments(stage):
        raise SystemExit(
            f"The frozen {COMMITTED_AMENDMENTS} is not release 20261006's "
            "record with the stage's list appended"
        )
    serving = serving_problems(
        read_json(snapshot / "model_serving_config.json"),
        previous_serving,
        incumbents,
        runs,
    )
    if serving:
        raise SystemExit(f"Frozen serving configuration: {serving[:8]}")
    manifest = read_json(snapshot / "manifest.json")
    base = json.loads(driver.base_commit_blob(SNAPSHOT / "manifest.json"))
    outside = manifest_problems(base, manifest)
    if outside:
        named = [".".join(map(str, path)) for path in outside[:8]]
        raise SystemExit(f"The frozen manifest changes outside the release: {named}")
    artifact = {key: pointer[key] for key in ("tag", "asset", "url", "sha256", "bytes")}
    live = manifest["live_dashboard_artifact"]
    excluded = manifest["reference_exclusions"]
    stated = {
        "snapshot_date": (manifest["snapshot_date"], snapshot_date),
        "scope.models": (manifest["scope"]["models"], BOARD_MODELS),
        "model_response_date": (manifest["model_response_date"], window),
        "reference_exclusions.outputs": (
            excluded["outputs"],
            driver.RELEASE_EXCLUSIONS,
        ),
        "reference_exclusions.scored_outputs_per_model": (
            excluded["scored_outputs_per_model"],
            driver.RELEASE_SCORED,
        ),
        "published_dashboard_artifact": (
            manifest["published_dashboard_artifact"],
            artifact,
        ),
        "live_dashboard_artifact": ({key: live.get(key) for key in artifact}, artifact),
        f"source_run_artifacts {EXCLUSIONS}": (
            manifest["source_run_artifacts"][RUN]["files"].get(EXCLUSIONS),
            exclusions_sha256,
        ),
    }
    wrong = {name: got for name, (got, want) in stated.items() if got != want}
    if wrong:
        raise SystemExit(f"The frozen manifest does not state the release: {wrong}")


def configure_freezer(
    freezer,
    *,
    snapshot_date: str,
    source_run: Path,
    payload_path: Path,
    pointer: dict,
    evidence_paths: dict[str, str],
    cases_dir: Path,
    previous_serving: dict,
    incumbents: set[str],
    runs: dict[str, str],
) -> None:
    """Point freeze_snapshot at the stage and this release.

    Read-only input paths are all in this checkout. They override defaults
    that captured the old audit directory when freeze_snapshot was imported.
    """
    freezer.SNAPSHOT_DATE = snapshot_date
    freezer.SOURCE_RUN = source_run
    freezer.SOURCE_US = source_run / "us"
    freezer.SOURCE_ANNOTATIONS = source_run / "annotations"
    freezer.REFERENCE_META_SOURCE = source_run / "us/reference_outputs.csv.meta.json"
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
        original_freeze_serving(destination)
        serving = merge_serving(
            read_json(destination), previous_serving, incumbents, runs
        )
        serving["registry_commit"] = freezer._serving_registry_commit(serving)
        write_json(destination, serving)

    freezer.freeze_serving_configuration = freeze_serving


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--tag", default=driver.RELEASE_TAG)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"dashboard-data-\d{8}[a-z]?", args.tag):
        parser.error("--tag must be dashboard-data-YYYYMMDD[a-z]")
    stage = args.stage_dir.resolve()
    if not stage.is_relative_to(ROOT):
        parser.error("--stage-dir must be inside this checkout")
    if engine_upgrade_installed(stage):
        raise SystemExit(
            "The stage carries an engine upgrade of the references (stage.json "
            "references_installed, from finish_haiku55.py --step "
            "install-references). This freeze builds a release only on release "
            "20261006's references; extend it for the upgrade before freezing."
        )

    import freeze_snapshot as freezer
    import pandas as pd

    if hasattr(pd.options, "future") and hasattr(pd.options.future, "infer_string"):
        pd.options.future.infer_string = False

    from policybench.dashboard_schema import validate_dashboard_payload

    verify_freezer_destinations(freezer)
    payload_path = stage / f"data-board{BOARD_MODELS}.json"
    receipt = verify_receipt(stage, payload_path, args.tag)
    spec = release_spec(args.tag)
    snapshot_date = spec["snapshot_date"]
    # The release's exclusion record, rebuilt from git and the spec: what the
    # stage must score on and the freeze must commit.
    exclusions = driver.build_release_exclusions(driver.base_exclusion_record(), spec)
    exclusions_sha256 = verify_installed_exclusions(
        stage, receipt, driver.exclusions_text(exclusions)
    )
    # Claude Haiku 5.5's run files are the committed pins' and its bundle rows
    # are its run file's, every column: its cost, tokens and latency included.
    driver.verify_new_model_inputs(stage)
    runs = evidence_runs()
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

    snapshot = ROOT / SNAPSHOT
    frozen_run = snapshot / "runs" / RUN
    # The incumbents' frozen serving evidence is release 20261006's, from git.
    previous_serving = base_serving_config()
    incumbents = set(previous_serving["models"]) - set(NEW_MODELS.values())
    if len(incumbents) != driver.BASE_MODELS or model_names != incumbents | set(
        NEW_MODELS.values()
    ):
        raise SystemExit(
            f"Frozen incumbent roster and staged {BOARD_MODELS}-model roster disagree"
        )
    verify_scored_outputs(payload["countries"]["us"], exclusions["exclusions"])
    source_run = stage / "publish" / RUN
    source_us = source_run / "us"
    staged_annotations = source_run / "annotations"
    verify_references(
        source_us, frozen_run, read_json(snapshot / "manifest.json"), exclusions_sha256
    )
    verify_explanations(staged_annotations)
    del payload, stats
    # Export's own build, the incumbents' scope check included.
    base = driver.base_payload_from_commit()
    rebuild_payload(stage, receipt, payload_path, base)
    del base
    verify_verdicts(stage)
    rejudged = driver.rejudged_cases(stage)
    verify_judge_provenance(stage, receipt, rejudged)
    amendments = driver.load_amendments(stage, rejudged)
    cases_dir = stage / "audit" / "cases"
    added = verify_adjudication_record(
        staged_annotations / ADJUDICATIONS, source_us, rejudged, amendments, cases_dir
    )
    verify_annotation_amendments(staged_annotations, amendments, stage / "audit")
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
    # The freezer dates the response window from these rows: from the run
    # label's start to the last answer, not to the release date. Refuse here,
    # before the pointer is written, rather than partway through the freeze.
    window = freezer.model_response_window(
        source_us / "predictions.csv",
        freezer.MODEL_RESPONSE_START,
        freezer.MODEL_RESPONSE_DATE,
    )

    adjudications = freezer.load_adjudications(staged_annotations / ADJUDICATIONS)
    from policybench.adjudications import verify_adjudications_applied

    verify_adjudications_applied(
        pd.read_csv(staged_annotations / "us_audit_row_annotations.csv"),
        pd.read_csv(staged_annotations / "us_case_notes.csv"),
        adjudications,
    )
    freezer.verify_adjudications_keep_judge_verdicts(adjudications, cases_dir)
    pointer = release_pointer(args.tag, payload_path, payload_hash)
    versions_path = ROOT / VERSIONS
    versions = release_versions(
        read_json(versions_path), exclusions["exclusions"], snapshot_date
    )
    if args.dry_run:
        print(
            f"Validated local release inputs: {args.tag}, {BOARD_MODELS} models, "
            f"{payload_hash}; references unchanged; {driver.RELEASE_EXCLUSIONS} "
            f"exclusions ({driver.NEW_EXCLUSIONS} new); {added} adjudications "
            f"added beyond the ruled outputs; {len(amendments)} wording "
            f"amendments; model responses {window}; snapshot {snapshot_date}; "
            "nothing written"
        )
        return

    configure_freezer(
        freezer,
        snapshot_date=snapshot_date,
        source_run=source_run,
        payload_path=payload_path,
        pointer=pointer,
        evidence_paths=evidence_paths,
        cases_dir=cases_dir,
        previous_serving=previous_serving,
        incumbents=incumbents,
        runs=runs,
    )
    write_json(ROOT / POINTER, pointer)
    write_json(versions_path, versions)
    freezer.ANNOTATIONS_DEST.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        staged_annotations / ADJUDICATIONS,
        freezer.ANNOTATIONS_DEST / ADJUDICATIONS,
    )
    freezer.main()
    freeze_amendments(stage, freezer.ANNOTATIONS_DEST)
    # The freezer copies the staged references, exclusions and annotations
    # byte for byte and builds the manifest and the serving rows; confirm it.
    verify_frozen(
        stage=stage,
        snapshot=snapshot,
        annotations=freezer.ANNOTATIONS_DEST,
        exclusions_sha256=exclusions_sha256,
        pointer=pointer,
        window=window,
        snapshot_date=snapshot_date,
        previous_serving=previous_serving,
        incumbents=incumbents,
        runs=runs,
    )
    cache = ROOT / "app/.cache" / f"dashboard-data-{payload_hash[:16]}.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(payload_path, cache)
    asset = stage / "predictions.csv.gz"
    freezer.gzip_deterministic(
        source_us / "predictions.csv", asset, stored_name="predictions.csv"
    )
    if asset.read_bytes() != (frozen_run / "predictions.csv.gz").read_bytes():
        raise SystemExit("The predictions asset is not the frozen predictions")
    print(f"Built {args.tag} locally; payload and predictions remain in {stage}")
    print("Next: update note and paper prose, render the paper, re-pin, run tests.")


if __name__ == "__main__":
    main()
