"""Build release dashboard-data-20261006 from release dashboard-data-20260930.

The release applies Max's rulings of 2026-10-05 (docs/release_20261006/spec.json)
to release 20260930. No model and no answer changes, and no reference value
changes:

- eight outputs leave scoring for every model, as
  ``reference_depends_on_unlisted_input`` records from the three 2026-10-05
  audits (state income tax withheld in SALT, the Medicare Part B premium, and
  the optional employer pass-through of state paid-leave premiums), with eight
  developer adjudications;
- four existing records gain the text the audits wrote for them;
- the audit text of the excluded and Louisiana outputs is reworded
  (docs/release_20261006/annotation_rewrites.json), and scenario_031's
  Medicaid text carries PolicyEngine/policybench#197's rewrites, which are
  already committed;
- the model response window ends on the last answer's UTC date
  (scripts/freeze_snapshot.py, model_response_window).

Three steps. Each reads the release-20260930 baseline from git at the base
commit, never from the working tree, and refuses anything outside the release:

  prepare  stage release 20260930's bundle and audit tree, install the records,
           adjudications and rewrites, and record the judge evidence;
  export   build the payload twice (the bytes must agree), check every change
           against the base, and write the receipt;
  freeze   freeze the snapshot through scripts/freeze_snapshot.py, then check
           what it wrote.

Usage::

    python scripts/release_20261006.py prepare --base-stage BASE --stage STAGE
    python scripts/release_20261006.py export --stage STAGE
    python scripts/release_20261006.py freeze --stage STAGE [--dry-run]

``BASE`` is release 20260930's archived stage (results/local/gpt61sol-stage/
gpt61sol-v1, or an APFS clone of it); it is only read. ``STAGE`` must be a new
directory under results/local in this checkout.
"""

from __future__ import annotations

import argparse
import copy
import csv
import functools
import gzip
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

RUN = "us_full_run_20260612_policyengine_4_16_1_populace"
SPEC_PATH = Path("docs/release_20261006/spec.json")
REWRITES_PATH = Path("docs/release_20261006/annotation_rewrites.json")
SNAPSHOT_DIR = Path("paper/snapshot/20260501")
SNAPSHOT_RUN = SNAPSHOT_DIR / "runs" / RUN
MANIFEST = SNAPSHOT_DIR / "manifest.json"
SERVING = SNAPSHOT_DIR / "model_serving_config.json"
ANNOTATIONS = Path("annotations") / RUN
ADJUDICATIONS = "us_adjudications.json"
ROWS = "us_audit_row_annotations.csv"
CASES = "us_case_notes.csv"
EXPLANATIONS = "us_case_reference_explanations.csv"
AMENDMENTS = "us_wording-amendments.json"
ANNOTATION_CSVS = (ROWS, CASES, EXPLANATIONS)
EXCLUSIONS = "reference_exclusions.json"
REFERENCE_FILES = (
    "reference_outputs.csv",
    "reference_outputs.csv.meta.json",
    "scenarios.csv",
    "scenarios.csv.meta.json",
)
EVIDENCE = Path("reference_audit/2026-09-28/verification/judge_verdicts.json")
RULE_031 = Path("reference_audit/2026-10-05-medicaid-031-annotations/rewrites.json")
POINTER = Path("app/src/data.artifact.json")
VERSIONS = Path("app/src/data.versions.json")
STAGE_ROOT = Path("results/local")
BOARD_MODELS = 46
TOTAL_OUTPUTS = 1984
# Fable 5 ran through the Anthropic batch adapter, whose rows carry no cost,
# token or latency fields; release 20260930 carried its released values, and
# so does this release (scripts/finish_gpt61sol.py, CARRIED_USAGE).
CARRIED_USAGE = {
    "claude-fable-5": ("costUsd", "costPerHousehold", "totalTokens", "latencySeconds")
}
# modelStats fields no exclusion can move.
STABLE_STATS = (
    "condition",
    "costUsd",
    "costPerHousehold",
    "totalTokens",
    "latencySeconds",
    "accuracy",
)
# Payload sections an exclusion or a rewording can move; the others must be
# release 20260930's.
CHANGED_SECTIONS = frozenset(
    {
        "modelStats",
        "programStats",
        "heatmap",
        "failureModes",
        "referenceExclusions",
        "scenarioPredictions",
    }
)
# Fields of a scenarioPredictions cell that a new exclusion can move.
EXCLUSION_CELL_FIELDS = frozenset(
    {"scored", "excludedReason", "excludedInput", "failureSource", "failureSubtype"}
)
# Fields a rewording can move.
TEXT_CELL_FIELDS = frozenset({"annotation", "caseAnnotation", "referenceExplanation"})
# Classes the adjudications set on a newly excluded case.
CLASS_CELL_FIELDS = frozenset(
    {"caseFailureSources", "caseFailureSubtypes", "failureSource", "failureSubtype"}
)
# Field order of the 2026-09-29 wave's unlisted-input adjudications.
ENTRY_FIELDS = (
    "country",
    "scenario_id",
    "variable",
    "judge_model",
    "judge_failure_source",
    "judge_failure_subtype",
    "adjudicated_failure_source",
    "adjudicated_failure_subtype",
    "adjudicated_on",
    "adjudicator",
    "excluded_from_scoring",
    "judge_reference_suspect",
    "reference_verdict",
    "reference_basis",
    "reasoning",
    "judged_on_utc",
)
DATE_CONVENTIONS_OLD = (
    "adjudicated_on names the audit wave that made the decision (2026-09-05, "
    "2026-09-22 or 2026-09-29). It carries no time of day or time zone. The "
    "2026-09-05 and 2026-09-22 waves' decisions were written up to the day each "
    "wave's release was committed (2026-09-05 and 2026-09-23), and the "
    "2026-09-29 wave's decisions were written on 2026-09-29 UTC, after its "
    "reference sweep began."
)
DATE_CONVENTIONS_NEW = (
    "adjudicated_on names the audit wave that made the decision (2026-09-05, "
    "2026-09-22, 2026-09-29 or 2026-10-05). It carries no time of day or time "
    "zone. The 2026-09-05, 2026-09-22 and 2026-09-29 waves' decisions were "
    "written up to the day each wave's release was committed (2026-09-05, "
    "2026-09-23 and 2026-09-30); the 2026-09-29 wave's reference sweep began "
    "on 2026-09-29 UTC, before its decisions were written. The 2026-10-05 "
    "wave's decisions follow Max's rulings of 2026-10-05 US Eastern time "
    "(2026-10-06 UTC) and were written on 2026-10-06 UTC."
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"release_20261006: {message}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_spec(root: Path = ROOT) -> dict:
    return json.loads((root / SPEC_PATH).read_text())


def git_blob(commit: str, path: Path, root: Path = ROOT) -> bytes:
    """A file as committed at ``commit``. CI checks out full history."""
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{commit}:{path.as_posix()}"],
        capture_output=True,
    )
    require(
        result.returncode == 0,
        f"cannot read {path} at {commit[:12]} (fetch full history): "
        f"{result.stderr.decode().strip()}",
    )
    return result.stdout


def key(entry: dict) -> tuple[str, str]:
    return entry["scenario_id"], entry["variable"]


# --- Exclusion records ---------------------------------------------------------


def exclusions_text(doc: dict) -> str:
    """The exclusion record as the reference builder spells it
    (reference_audit/2026-09-28/scripts/build_references_latest.py)."""
    return json.dumps(doc, indent=2) + "\n"


def proposal_records(spec: dict, root: Path = ROOT) -> list[dict]:
    """The ruled records, exactly the outputs each ruling names, in
    (scenario_id, variable) order."""
    records = []
    for proposal in spec["proposals"]:
        found = json.loads((root / proposal["path"]).read_text())["exclusions"]
        named = [tuple(output) for output in proposal["outputs"]]
        chosen = [record for record in found if key(record) in set(named)]
        require(
            sorted(key(record) for record in chosen) == sorted(named),
            f"{proposal['path']} does not hold exactly the ruled outputs {named}",
        )
        records.extend(copy.deepcopy(chosen))
    keys = [key(record) for record in records]
    require(len(set(keys)) == len(keys), f"two ruled records share an output: {keys}")
    for record in records:
        require(
            record["reason_code"] == "reference_depends_on_unlisted_input"
            and record["decided_on"] == spec["decided_on"]
            and record["decided_by"] == "developer"
            and record["engine_version"] == "policyengine-us 2.15.17",
            f"{key(record)} is not a 2026-10-05 developer unlisted-input record "
            "on policyengine-us 2.15.17",
        )
    return sorted(records, key=key)


def _pointer(value, path: list):
    for part in path:
        value = value[part]
    return value


def apply_record_edit(record: dict, edit: dict, root: Path = ROOT) -> dict:
    """One spec edit, applied to a copy; refuses an edit that does not fit."""
    record = copy.deepcopy(record)
    field = edit["field"]
    text = record[field]
    if "replace" in edit:
        require(
            text.count(edit["replace"]) == 1,
            f"{key(record)} {field} does not hold the replaced text exactly once",
        )
        record[field] = text.replace(edit["replace"], edit["with"])
        return record
    if "append_from" in edit:
        source, *path = edit["append_from"]
        appended = _pointer(json.loads((root / source).read_text()), path)
        target = _pointer(json.loads((root / source).read_text()), path[:-1])
        require(
            (target["scenario_id"], target["variable"]) == key(record),
            f"{source} {path} is written for another output than {key(record)}",
        )
        appended = " " + appended
    else:
        appended = edit["append"]
    require(not text.endswith(appended), f"{key(record)} {field} already carries it")
    record[field] = text + appended
    return record


def build_exclusions(base: dict, spec: dict, root: Path = ROOT) -> dict:
    """Release 20260930's record plus the eight ruled records.

    The new records go after the earlier waves' and before the audit's trailing
    scenario_023 record (tests/test_reference_upgrade.py requires that tail); the
    derivation's new sentence goes before the 2026-09-29 marker, which the same
    test splits on. Every other record keeps its bytes except the four edits.
    """
    doc = copy.deepcopy(base)
    tail = doc["exclusions"][-1]
    require(
        key(tail) == ("scenario_023", "head_medicaid_eligible"),
        "release 20260930's record does not end with the audit's scenario_023 record",
    )
    new = proposal_records(spec, root)
    existing = {key(record) for record in doc["exclusions"]}
    require(
        not existing & {key(record) for record in new},
        "a ruled output is already excluded",
    )
    records = doc["exclusions"][:-1] + new + [tail]
    by_key = {key(record): index for index, record in enumerate(records)}
    for edit in spec["record_edits"]:
        index = by_key.get((edit["scenario_id"], edit["variable"]))
        require(index is not None, f"no record for edit {edit['scenario_id']}")
        records[index] = apply_record_edit(records[index], edit, root)
    doc["exclusions"] = records
    rule = spec["rule"]
    require(
        doc["rule"].count(rule["old"]) == 1,
        "the record's rule is not release 20260930's",
    )
    doc["rule"] = doc["rule"].replace(rule["old"], rule["new"])
    insert = spec["derivation_insert"]
    require(
        doc["derivation"].count(insert["before"]) == 1,
        "the derivation does not hold its 2026-09-29 marker exactly once",
    )
    doc["derivation"] = doc["derivation"].replace(
        insert["before"], insert["text"] + insert["before"]
    )
    return doc


# --- Adjudications and judge evidence ------------------------------------------


def bound_verdict(case_dir: Path) -> tuple[dict, dict]:
    """(verdict, sidecar), where the sidecar binds the verdict by sha256."""
    verdict_path, meta_path = case_dir / "verdict.json", case_dir / "verdict.meta.json"
    require(
        verdict_path.is_file() and meta_path.is_file(),
        f"{case_dir.name} has no bound verdict in the stage's audit tree",
    )
    meta = json.loads(meta_path.read_text())
    require(
        meta.get("verdict_sha256") == digest(verdict_path),
        f"{case_dir.name}'s sidecar does not bind its verdict",
    )
    return json.loads(verdict_path.read_text()), meta


def case_dir_name(scenario_id: str, variable: str) -> str:
    return f"us__{scenario_id}__{variable}"


def new_adjudications(spec: dict, exclusions: dict, cases_dir: Path) -> list[dict]:
    """One developer adjudication per ruled record, keeping the judge's verdict
    in the release's audit tree verbatim (freeze_snapshot.py checks it)."""
    from date_adds0928_judge_verdicts import _judge

    records = {key(record): record for record in exclusions["exclusions"]}
    entries = []
    for item in spec["adjudications"]:
        record = records[key(item)]
        verdict, meta = bound_verdict(
            cases_dir / case_dir_name(item["scenario_id"], item["variable"])
        )
        entry = {
            "country": "us",
            "scenario_id": item["scenario_id"],
            "variable": item["variable"],
            "judge_model": _judge(meta),
            "judge_failure_source": verdict["case_failure_source"],
            "judge_failure_subtype": verdict["case_failure_subtype"],
            "adjudicated_failure_source": "prompt_ambiguity",
            "adjudicated_failure_subtype": item["adjudicated_failure_subtype"],
            "adjudicated_on": spec["decided_on"],
            "adjudicator": "developer",
            "excluded_from_scoring": True,
            "judge_reference_suspect": bool(verdict.get("reference_suspect")),
            "reference_verdict": "unlisted_input",
            "reference_basis": record["unlisted_input"],
            "reasoning": item["reasoning"],
            "judged_on_utc": meta["judged_at_utc"][:10],
        }
        require(list(entry) == list(ENTRY_FIELDS), "entry fields out of order")
        entries.append(entry)
    return entries


def build_adjudication_record(base: dict, entries: list[dict]) -> dict:
    record = copy.deepcopy(base)
    existing = {key(entry) for entry in record["adjudications"]}
    require(
        not existing & {key(entry) for entry in entries},
        "a ruled output already has an adjudication",
    )
    require(
        record["date_conventions"].count(DATE_CONVENTIONS_OLD) == 1,
        "the record's date conventions are not release 20260930's",
    )
    record["date_conventions"] = record["date_conventions"].replace(
        DATE_CONVENTIONS_OLD, DATE_CONVENTIONS_NEW
    )
    record["adjudications"] = record["adjudications"] + entries
    return record


def record_text(record: dict) -> str:
    """The adjudication record as the committed file spells it."""
    return json.dumps(record, indent=2, ensure_ascii=False) + "\n"


def build_evidence(
    evidence: dict, spec: dict, entries: list[dict], cases_dir: Path, root: Path = ROOT
) -> dict:
    """Fill the 2026-09-29 wave's release, add the 2026-10-05 wave, and add the
    judge verdict each new decision reviewed."""
    from date_adds0928_judge_verdicts import _evidence

    evidence = copy.deepcopy(evidence)
    fill, new = spec["judge_evidence"]["fill_wave"], spec["judge_evidence"]["new_wave"]
    waves = evidence["wave_releases"]
    require(
        waves.get(fill["wave"], {}).get("commit") is None
        and list(waves) == ["2026-09-05", "2026-09-22", "2026-09-29"],
        "the evidence's waves are not release 20260930's",
    )
    waves[fill["wave"]] = {
        "commit": fill["commit"],
        "release": waves[fill["wave"]]["release"],
        "pull_request": fill["pull_request"],
        "committed_on": fill["committed_on"],
    }
    waves[new["wave"]] = {
        "commit": None,
        "release": new["release"],
        "pull_request": None,
        "adjudications_written_on": new["adjudications_written_on"],
    }
    published = json.loads(git_blob(fill["commit"], ANNOTATIONS / ADJUDICATIONS, root))[
        "adjudications"
    ]
    filled = 0
    for entry in published:
        if entry["adjudicated_on"] != fill["wave"]:
            continue
        case = case_dir_name(*key(entry))
        require(
            "published" not in evidence["cases"][case],
            f"{case} already has published evidence",
        )
        evidence["cases"][case]["published"] = {
            "release": waves[fill["wave"]]["release"],
            "commit": fill["commit"],
            "judge_model": entry["judge_model"],
            "case_failure_source": entry["judge_failure_source"],
            "case_failure_subtype": entry["judge_failure_subtype"],
            "judged_on_utc": entry.get("judged_on_utc"),
        }
        filled += 1
    require(filled > 0, f"the {fill['wave']} release published no decisions")
    for entry in entries:
        case = case_dir_name(*key(entry))
        require(case not in evidence["cases"], f"{case} already has evidence")
        evidence["cases"][case] = {
            "current": _evidence("stage", bound_verdict(cases_dir / case))
        }
    return evidence


def evidence_text(evidence: dict) -> str:
    return json.dumps(evidence, indent=2) + "\n"


# --- Annotation text -------------------------------------------------------------

REWRITE_KEYS = {
    ROWS: ("scenario_id", "variable", "model"),
    CASES: ("scenario_id", "variable"),
    EXPLANATIONS: ("scenario_id", "variable"),
}
REWRITE_FIELDS = {
    ROWS: "annotation",
    CASES: "case_annotation",
    EXPLANATIONS: "explanation",
}


def _read_csv(data: bytes) -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"), newline="")))
    return rows[0], rows[1:]


def _write_csv(header: list[str], rows: list[list[str]]) -> bytes:
    out = io.StringIO(newline="")
    csv.writer(out, lineterminator="\n").writerows([header, *rows])
    return out.getvalue().encode("utf-8")


def apply_text_rewrites(
    files: dict[str, bytes], rewrites: list[dict]
) -> dict[str, bytes]:
    """Whole-field rewrites, as #197's apply_rewrites.py applies them: each names
    one row and holds the field's whole old and new text; nothing else moves.
    Refuses a missing or ambiguous row, a repeated rewrite, or a field holding
    neither text; a field already holding the new text is left as it is."""
    out = dict(files)
    by_file: dict[str, list[dict]] = {}
    for item in rewrites:
        require(item["file"] in REWRITE_KEYS, f"{item['file']} is not rewritable")
        require(
            item["field"] == REWRITE_FIELDS[item["file"]],
            f"{item['file']}: {item['field']} is not its text field",
        )
        by_file.setdefault(item["file"], []).append(item)
    for name, items in by_file.items():
        header, rows = _read_csv(out[name])
        require(_write_csv(header, rows) == out[name], f"{name} does not round-trip")
        columns = {column: index for index, column in enumerate(header)}
        key_columns = [columns[c] for c in REWRITE_KEYS[name]]
        field = columns[REWRITE_FIELDS[name]]
        index: dict[tuple, list[int]] = {}
        for position, row in enumerate(rows):
            index.setdefault(tuple(row[c] for c in key_columns), []).append(position)
        seen = set()
        for item in items:
            row_key = tuple(item[c] for c in REWRITE_KEYS[name])
            require(row_key not in seen, f"{name}: two rewrites of {row_key}")
            seen.add(row_key)
            hits = index.get(row_key, [])
            require(len(hits) == 1, f"{name}: {row_key} matches {len(hits)} rows")
            current = rows[hits[0]][field]
            if current == item["new"]:
                continue
            require(
                current == item["old"],
                f"{name}: {row_key} holds neither the old nor the new text",
            )
            rows[hits[0]][field] = item["new"]
        out[name] = _write_csv(header, rows)
    return out


def adjudicated_csvs(
    files: dict[str, bytes], adjudications: list[dict]
) -> dict[str, bytes]:
    """The row annotations and case notes with every adjudication applied, as
    scripts/apply_adjudications.py writes them."""
    import pandas as pd

    from policybench.adjudications import (
        apply_adjudications,
        unresolved_suspect_cases,
        verify_adjudications_applied,
    )

    rows = pd.read_csv(io.BytesIO(files[ROWS]))
    cases = pd.read_csv(io.BytesIO(files[CASES]))
    rows, cases, _ = apply_adjudications(rows, cases, adjudications)
    verify_adjudications_applied(rows, cases, adjudications)
    require(
        not unresolved_suspect_cases(cases, adjudications),
        "a reference-suspect case has no reference verdict",
    )
    out = dict(files)
    out[ROWS] = rows.to_csv(index=False).encode("utf-8")
    out[CASES] = cases.to_csv(index=False).encode("utf-8")
    return out


def changed_cells(before: bytes, after: bytes, keys: tuple[str, ...]) -> dict:
    """{row key: [changed columns]} between two versions of an annotation CSV
    whose rows and columns must otherwise agree."""
    header_a, rows_a = _read_csv(before)
    header_b, rows_b = _read_csv(after)
    require(header_a == header_b, "an annotation file's columns changed")
    index = [header_a.index(c) for c in keys]
    require(
        [tuple(r[i] for i in index) for r in rows_a]
        == [tuple(r[i] for i in index) for r in rows_b],
        "an annotation file's rows changed order or membership",
    )
    changes = {}
    for row_a, row_b in zip(rows_a, rows_b):
        columns = [header_a[i] for i, (a, b) in enumerate(zip(row_a, row_b)) if a != b]
        if columns:
            changes[tuple(row_a[i] for i in index)] = columns
    return changes


def verify_annotation_scope(
    base: dict[str, bytes],
    staged: dict[str, bytes],
    new_keys: set[tuple[str, str]],
    reworded: set[tuple[str, str]],
) -> dict[str, int]:
    """Only the newly excluded outputs' classes and only reworded outputs' text
    may differ from release 20260930's annotations."""
    counts = {}
    allowed = {
        ROWS: ({"failure_source", "failure_subtype"}, {"annotation"}),
        CASES: (
            {"case_failure_sources", "case_failure_subtypes", "case_annotation"},
            {"case_annotation"},
        ),
        EXPLANATIONS: (set(), {"explanation"}),
    }
    for name in ANNOTATION_CSVS:
        keys = REWRITE_KEYS[name]
        changes = changed_cells(base[name], staged[name], keys)
        for row_key, columns in changes.items():
            output = row_key[:2]
            classes, text = allowed[name]
            permitted = (classes if output in new_keys else set()) | (
                text if output in reworded else set()
            )
            require(
                set(columns) <= permitted,
                f"{name}: {row_key} changes {columns}, outside the release",
            )
        counts[name] = len(changes)
    return counts


# --- Prepare ---------------------------------------------------------------------


def stage_paths(stage: Path) -> tuple[Path, Path, Path, Path]:
    bundle = stage / "publish" / RUN
    return bundle, bundle / "us", bundle / "annotations", stage / "audit" / "cases"


def validate_stage(stage: Path) -> Path:
    stage = stage.resolve()
    require(
        stage.is_relative_to((ROOT / STAGE_ROOT).resolve()),
        f"the stage must be under {STAGE_ROOT} in this checkout",
    )
    return stage


def verify_base_stage(base_stage: Path, spec: dict) -> None:
    """The base stage holds release 20260930's payload and the bundle files the
    base commit froze."""
    payload = base_stage / "data-board46.json"
    require(
        payload.is_file() and digest(payload) == spec["base_sha256"],
        "the base stage's payload is not release 20260930's",
    )
    bundle, us, annotations, cases = stage_paths(base_stage)
    commit = spec["base_commit"]
    for name in (*REFERENCE_FILES, EXCLUSIONS):
        require(
            (us / name).read_bytes() == git_blob(commit, SNAPSHOT_RUN / name),
            f"the base stage's {name} is not the base commit's",
        )
    require(
        (us / "predictions.csv").read_bytes()
        == gzip.decompress(git_blob(commit, SNAPSHOT_RUN / "predictions.csv.gz")),
        "the base stage's predictions are not the base commit's",
    )
    for name in (ADJUDICATIONS, *ANNOTATION_CSVS):
        require(
            (annotations / name).read_bytes() == git_blob(commit, ANNOTATIONS / name),
            f"the base stage's {name} is not the base commit's",
        )
    require(cases.is_dir(), "the base stage has no audit tree")


def committed_annotation_inputs(spec: dict) -> dict[str, bytes]:
    """The committed annotation CSVs, which must be release 20260930's with
    #197's scenario_031 rewrites (its ledger) and nothing else."""
    commit = spec["base_commit"]
    base = {name: git_blob(commit, ANNOTATIONS / name) for name in ANNOTATION_CSVS}
    ledger = json.loads((ROOT / RULE_031).read_text())["rewrites"]
    expected = apply_text_rewrites(base, ledger)
    head = {name: git_blob("HEAD", ANNOTATIONS / name) for name in ANNOTATION_CSVS}
    for name in ANNOTATION_CSVS:
        require(
            head[name] == expected[name],
            f"the committed {name} is not release 20260930's plus #197's rewrites",
        )
        require(
            (ROOT / ANNOTATIONS / name).read_bytes() == head[name],
            f"the working tree's {name} is not HEAD's",
        )
    return head


def prepare(args) -> None:
    spec = load_spec()
    base_stage = args.base_stage.resolve()
    stage = validate_stage(args.stage)
    require(not stage.exists(), f"{stage} exists; prepare writes a new stage")
    verify_base_stage(base_stage, spec)
    commit = spec["base_commit"]

    stage.mkdir(parents=True)
    for part in ("publish", "audit"):
        subprocess.run(
            ["cp", "-cRp", str(base_stage / part), str(stage / part)], check=True
        )
    bundle, us, annotations, cases_dir = stage_paths(stage)
    # Export writes these; a stale copy must not survive into the new stage.
    for stale in (bundle / "data.json", us / "data.json"):
        stale.unlink(missing_ok=True)
    shutil.rmtree(us / "analysis", ignore_errors=True)

    base_exclusions = json.loads(git_blob(commit, SNAPSHOT_RUN / EXCLUSIONS))
    exclusions = build_exclusions(base_exclusions, spec)
    (us / EXCLUSIONS).write_text(exclusions_text(exclusions))

    base_record = json.loads(git_blob(commit, ANNOTATIONS / ADJUDICATIONS))
    entries = new_adjudications(spec, exclusions, cases_dir)
    record = build_adjudication_record(base_record, entries)
    from policybench.adjudications import excluded_case_keys, parse_adjudications

    adjudications = parse_adjudications(record, "staged record")
    require(
        excluded_case_keys(adjudications) == {key(e) for e in exclusions["exclusions"]},
        "the adjudications and the exclusions disagree on the excluded outputs",
    )
    (annotations / ADJUDICATIONS).write_text(record_text(record))

    files = committed_annotation_inputs(spec)
    rewrites = json.loads((ROOT / REWRITES_PATH).read_text())["rewrites"]
    files = apply_text_rewrites(files, rewrites)
    files = adjudicated_csvs(files, adjudications)
    new_keys = {key(e) for e in entries}
    reworded = {(r["scenario_id"], r["variable"]) for r in rewrites} | {
        (r["scenario_id"], r["variable"])
        for r in json.loads((ROOT / RULE_031).read_text())["rewrites"]
    }
    base_files = {
        name: git_blob(commit, ANNOTATIONS / name) for name in ANNOTATION_CSVS
    }
    counts = verify_annotation_scope(base_files, files, new_keys, reworded)
    for name, data in files.items():
        (annotations / name).write_bytes(data)

    evidence = build_evidence(
        json.loads(git_blob(commit, EVIDENCE)), spec, entries, cases_dir
    )
    (ROOT / EVIDENCE).write_text(evidence_text(evidence))

    write_json(
        stage / "stage.json",
        {
            "release_tag": spec["release_tag"],
            "base_tag": spec["base_tag"],
            "base_commit": commit,
            "base_sha256": spec["base_sha256"],
            "exclusions": len(exclusions["exclusions"]),
            "new_exclusions": sorted(map(list, new_keys)),
            "adjudications": len(record["adjudications"]),
            "changed_annotation_rows": counts,
            "spec_sha256": digest(ROOT / SPEC_PATH),
            "rewrites_sha256": digest(ROOT / REWRITES_PATH),
        },
    )
    print(
        f"Staged {spec['release_tag']} in {stage}: {len(exclusions['exclusions'])} "
        f"exclusions ({len(new_keys)} new), {len(record['adjudications'])} "
        f"adjudications, changed annotation rows {counts}"
    )


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


# --- Export ----------------------------------------------------------------------


def base_payload(spec: dict) -> dict:
    """Release 20260930's payload, from the base commit's frozen run."""
    blob = git_blob(spec["base_commit"], SNAPSHOT_RUN / "data.json.gz")
    payload = {"countries": {"us": json.loads(gzip.decompress(blob))}}
    text = payload_text(payload)
    require(
        sha(text.encode()) == spec["base_sha256"]
        and len(text.encode()) == spec["base_bytes"],
        "the base commit's payload is not release 20260930's",
    )
    return payload


def payload_text(payload: dict) -> str:
    """The bytes export writes and freeze_snapshot reassembles."""
    return json.dumps(payload, allow_nan=False)


EXPORT_INPUTS = (
    *(f"us/{name}" for name in (*REFERENCE_FILES, EXCLUSIONS, "predictions.csv")),
    *(f"annotations/{name}" for name in ANNOTATION_CSVS),
)


def export_payload(bundle: Path, base: dict, exclusions: Path | None = None) -> dict:
    """export_full_run on a scratch copy of the bundle's export inputs, with
    Fable 5's usage carried from the base. ``exclusions`` substitutes another
    exclusion record (the scope check rebuilds with the base's)."""
    from policybench.dashboard_schema import validate_dashboard_payload
    from policybench.full_run_export import export_full_run

    with tempfile.TemporaryDirectory(dir=bundle.parent) as scratch:
        copy_root = Path(scratch) / RUN
        for rel in EXPORT_INPUTS:
            (copy_root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundle / rel, copy_root / rel)
        if exclusions is not None:
            shutil.copyfile(exclusions, copy_root / "us" / EXCLUSIONS)
        payload = export_full_run(copy_root, countries=["us"], skip_app_data=True)
    previous = {row["model"]: row for row in base["countries"]["us"]["modelStats"]}
    for model, fields in CARRIED_USAGE.items():
        row = next(
            r for r in payload["countries"]["us"]["modelStats"] if r["model"] == model
        )
        for field in fields:
            row[field] = previous[model][field]
    errors = validate_dashboard_payload(payload, require_failure_annotations=True)
    require(not errors, f"dashboard schema: {errors[:5]}")
    return payload


def by_model(payload: dict) -> dict[str, dict]:
    return {row["model"]: row for row in payload["countries"]["us"]["modelStats"]}


def verify_payload(
    payload: dict, base: dict, spec: dict, reworded: set, new_keys: set
) -> None:
    """Every change from release 20260930's payload is one the release makes."""
    now, before = payload["countries"]["us"], base["countries"]["us"]
    require(set(now) == set(before), "the payload's sections changed")
    for section in set(now) - CHANGED_SECTIONS:
        require(now[section] == before[section], f"{section} changed")
    stats, base_stats = by_model(payload), by_model(base)
    require(
        set(stats) == set(base_stats) and len(stats) == BOARD_MODELS,
        "the roster is not release 20260930's 46 models",
    )
    scored = TOTAL_OUTPUTS - len(now["referenceExclusions"])
    for model, row in stats.items():
        require(row["n"] == scored, f"{model} is scored on {row['n']}, not {scored}")
        require(list(row) == list(base_stats[model]), f"{model}'s fields changed order")
        for field in STABLE_STATS:
            require(
                json.dumps(row.get(field)) == json.dumps(base_stats[model].get(field)),
                f"{model}'s {field} changed",
            )
    base_excluded = {
        (e["scenarioId"], e["variable"]) for e in before["referenceExclusions"]
    }
    now_excluded = {
        (e["scenarioId"], e["variable"]) for e in now["referenceExclusions"]
    }
    require(
        now_excluded - base_excluded == new_keys and base_excluded <= now_excluded,
        "the payload's exclusions are not the base's plus the ruled outputs",
    )
    require(
        set(now["scenarioPredictions"]) == set(before["scenarioPredictions"]),
        "the payload's households changed",
    )
    for scenario, cells in now["scenarioPredictions"].items():
        require(
            set(cells) == set(before["scenarioPredictions"][scenario]),
            f"{scenario}'s outputs changed",
        )
        for variable, cell in cells.items():
            old = before["scenarioPredictions"][scenario][variable]
            output = (scenario, variable)
            permitted = set()
            if output in new_keys:
                permitted |= EXCLUSION_CELL_FIELDS | CLASS_CELL_FIELDS
            if output in reworded or output in new_keys:
                permitted |= TEXT_CELL_FIELDS
            for model, entry in cell.items() if isinstance(cell, dict) else []:
                previous = old.get(model) if isinstance(old, dict) else None
                if entry == previous:
                    continue
                require(
                    isinstance(entry, dict) and isinstance(previous, dict),
                    f"{output} {model} changed shape",
                )
                fields = {
                    f
                    for f in set(entry) | set(previous)
                    if entry.get(f) != previous.get(f)
                }
                require(
                    fields <= permitted,
                    f"{output} {model} changes {sorted(fields)}, outside the release",
                )
            require(set(cell) == set(old), f"{output}'s models changed")


def export(args) -> None:
    spec = load_spec()
    stage = validate_stage(args.stage)
    stage_meta = json.loads((stage / "stage.json").read_text())
    require(
        stage_meta["spec_sha256"] == digest(ROOT / SPEC_PATH)
        and stage_meta["rewrites_sha256"] == digest(ROOT / REWRITES_PATH),
        "the spec or the rewrites changed since prepare; prepare a new stage",
    )
    bundle, us, annotations, cases_dir = stage_paths(stage)
    base = base_payload(spec)
    payload = export_payload(bundle, base)
    again = export_payload(bundle, base)
    text = payload_text(payload)
    require(text == payload_text(again), "two exports of the same stage disagree")
    new_keys = {tuple(k) for k in stage_meta["new_exclusions"]}
    rewrites = json.loads((ROOT / REWRITES_PATH).read_text())["rewrites"]
    reworded = {(r["scenario_id"], r["variable"]) for r in rewrites} | {
        (r["scenario_id"], r["variable"])
        for r in json.loads((ROOT / RULE_031).read_text())["rewrites"]
    }
    verify_payload(payload, base, spec, reworded, new_keys)

    # Scope: with release 20260930's exclusion record, the staged bundle
    # rebuilds release 20260930's statistics exactly. So every score change
    # comes from the eight records, and none from the annotation text.
    with tempfile.NamedTemporaryFile(dir=stage, suffix=".json") as handle:
        handle.write(git_blob(spec["base_commit"], SNAPSHOT_RUN / EXCLUSIONS))
        handle.flush()
        with_base_exclusions = export_payload(bundle, base, Path(handle.name))
    for section in ("modelStats", "programStats", "heatmap", "globalWeights"):
        require(
            with_base_exclusions["countries"]["us"][section]
            == base["countries"]["us"][section],
            f"with the base exclusions, {section} is not release 20260930's",
        )

    path = stage / f"data-board{BOARD_MODELS}.json"
    path.write_text(text)
    shutil.copyfile(path, bundle / "data.json")
    files = [bundle / rel for rel in EXPORT_INPUTS] + [annotations / ADJUDICATIONS]
    files += [
        cases_dir / case_dir_name(*k) / name
        for k in sorted(new_keys)
        for name in ("verdict.json", "verdict.meta.json")
    ]
    write_json(
        stage / "release-ready.json",
        {
            "release_tag": spec["release_tag"],
            "base_tag": spec["base_tag"],
            "base_commit": spec["base_commit"],
            "base_sha256": spec["base_sha256"],
            "payload_sha256": sha(text.encode()),
            "payload_bytes": len(text.encode()),
            "models": BOARD_MODELS,
            "spec_sha256": digest(ROOT / SPEC_PATH),
            "rewrites_sha256": digest(ROOT / REWRITES_PATH),
            "evidence_sha256": digest(ROOT / EVIDENCE),
            "files": {str(p.relative_to(stage)): digest(p) for p in files},
        },
    )
    ranked = sorted(
        by_model(payload).values(), key=lambda r: (-r["exact"], -r["score"], r["model"])
    )
    before = by_model(base)
    for rank, row in enumerate(ranked, 1):
        print(
            f"{rank:>2} {row['model']:32s} {before[row['model']]['exact']:.3f} -> "
            f"{row['exact']:.3f} n={row['n']}"
        )
    data = text.encode()
    print(f"Exported {spec['release_tag']}: {sha(data)} ({len(data)} bytes)")


# --- Freeze ----------------------------------------------------------------------

# Manifest paths the freeze may change; every other leaf must equal HEAD's.
MANIFEST_CHANGES = (
    ("audit_annotation_artifacts", "files"),
    ("audit_annotation_artifacts", "developer_adjudications"),
    ("committed_snapshot_artifacts", "us_impact_summary_by_model.csv"),
    ("developer_adjudications",),
    ("reference_exclusions",),
    ("live_dashboard_artifact",),
    ("published_dashboard_artifact",),
    ("source_run_artifacts", RUN, "files"),
    ("files",),
    ("model_response_date",),
    ("reproducibility_notes",),
    ("rendered_paper_artifacts",),
)
# Frozen run files that must stay release 20260930's.
FROZEN_UNCHANGED = (*REFERENCE_FILES, "predictions.csv.gz")


def leaf_paths(before, after, path=()) -> list[tuple]:
    if isinstance(before, dict) and isinstance(after, dict):
        out = []
        for name in sorted(set(before) | set(after)):
            if name not in before or name not in after:
                out.append((*path, name))
            else:
                out.extend(leaf_paths(before[name], after[name], (*path, name)))
        return out
    if (
        isinstance(before, list)
        and isinstance(after, list)
        and len(before) == len(after)
    ):
        out = []
        for index, (a, b) in enumerate(zip(before, after)):
            out.extend(leaf_paths(a, b, (*path, index)))
        return out
    return [] if before == after else [path]


def manifest_problems(before: dict, after: dict) -> list[tuple]:
    return [
        path
        for path in leaf_paths(before, after)
        if not any(path[: len(prefix)] == prefix for prefix in MANIFEST_CHANGES)
    ]


def versions_description(text: str, exclusions: list[dict]) -> str:
    """The live version's description with the exclusion counts recomputed."""
    by_engine: dict[str, int] = {}
    for record in exclusions:
        by_engine[record["engine_version"]] = (
            by_engine.get(record["engine_version"], 0) + 1
        )
    old, new = (
        by_engine["policyengine-us 1.755.4"],
        by_engine["policyengine-us 2.15.17"],
    )
    pattern = re.compile(
        r"the \d+ excluded outputs keep the values they were decided on: \d+ from "
        r"policyengine-us 1\.755\.4, \d+ from 2\.15\.17"
    )
    require(len(pattern.findall(text)) == 1, "the version description changed form")
    return pattern.sub(
        f"the {old + new} excluded outputs keep the values they were decided on: "
        f"{old} from policyengine-us 1.755.4, {new} from 2.15.17",
        text,
    )


def verify_receipt(stage: Path, spec: dict) -> dict:
    receipt = json.loads((stage / "release-ready.json").read_text())
    require(
        receipt["release_tag"] == spec["release_tag"]
        and receipt["base_sha256"] == spec["base_sha256"]
        and receipt["base_commit"] == spec["base_commit"]
        and receipt["spec_sha256"] == digest(ROOT / SPEC_PATH)
        and receipt["rewrites_sha256"] == digest(ROOT / REWRITES_PATH)
        and receipt["evidence_sha256"] == digest(ROOT / EVIDENCE),
        "the receipt does not bind this release, its base, spec, rewrites and evidence",
    )
    payload = stage / f"data-board{BOARD_MODELS}.json"
    require(
        digest(payload) == receipt["payload_sha256"], "the payload changed after export"
    )
    for rel, pin in receipt["files"].items():
        require(digest(stage / rel) == pin, f"{rel} changed after export")
    return receipt


def freeze(args) -> None:
    spec = load_spec()
    stage = validate_stage(args.stage)
    receipt = verify_receipt(stage, spec)
    bundle, us, annotations, cases_dir = stage_paths(stage)
    payload_path = stage / f"data-board{BOARD_MODELS}.json"

    import freeze_snapshot as freezer
    import pandas as pd

    if hasattr(pd.options, "future") and hasattr(pd.options.future, "infer_string"):
        pd.options.future.infer_string = False

    window = freezer.model_response_window(
        us / "predictions.csv", spec["model_response_start"]
    )
    head_manifest = json.loads(git_blob("HEAD", MANIFEST))
    # The working tree is HEAD in every file the freeze reads or writes.
    for rel in (
        MANIFEST,
        SERVING,
        POINTER,
        VERSIONS,
        *(ANNOTATIONS / n for n in (ADJUDICATIONS, AMENDMENTS, *ANNOTATION_CSVS)),
    ):
        require(
            (ROOT / rel).read_bytes() == git_blob("HEAD", rel),
            f"the working tree's {rel} is not HEAD's",
        )
    base_serving = git_blob(spec["base_commit"], SERVING)
    require(
        git_blob("HEAD", SERVING) == base_serving,
        "HEAD's serving configuration is not the base's",
    )
    tag = spec["release_tag"]
    pointer = {
        "asset": "dashboard-data.json",
        "bytes": payload_path.stat().st_size,
        "repo": "PolicyEngine/policybench",
        "sha256": receipt["payload_sha256"],
        "tag": tag,
        "url": f"https://github.com/PolicyEngine/policybench/releases/download/{tag}/dashboard-data.json",
        "version": 1,
    }
    exclusions = json.loads((us / EXCLUSIONS).read_text())["exclusions"]
    versions = json.loads(git_blob("HEAD", VERSIONS))
    live = next(v for v in versions["versions"] if v["artifact"] == {"pointer": "live"})
    live["description"] = versions_description(live["description"], exclusions)
    if args.dry_run:
        print(
            f"Validated {tag}: payload {receipt['payload_sha256']}, window {window}, "
            f"{len(exclusions)} exclusions; nothing written"
        )
        return

    freezer.SNAPSHOT_DATE = spec["snapshot_date"]
    freezer.MODEL_RESPONSE_START = spec["model_response_start"]
    freezer.MODEL_RESPONSE_DATE = None
    freezer.SOURCE_RUN = bundle
    freezer.SOURCE_US = us
    freezer.SOURCE_ANNOTATIONS = annotations
    freezer.REFERENCE_META_SOURCE = us / "reference_outputs.csv.meta.json"
    freezer.PUBLISHED_DASHBOARD_SOURCE = payload_path
    freezer.PUBLISHED_DASHBOARD_ARTIFACT = {
        k: pointer[k] for k in ("tag", "asset", "url", "sha256", "bytes")
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
    (ROOT / VERSIONS).write_text(json.dumps(versions, indent=2, sort_keys=True) + "\n")
    shutil.copyfile(annotations / ADJUDICATIONS, ROOT / ANNOTATIONS / ADJUDICATIONS)
    freezer.main()

    # freeze_snapshot rebuilds the annotations directory from the stage; the
    # wording-amendments record is committed beside it and does not change.
    (ROOT / ANNOTATIONS / AMENDMENTS).write_bytes(
        git_blob("HEAD", ANNOTATIONS / AMENDMENTS)
    )
    frozen = sorted(p.name for p in (ROOT / ANNOTATIONS).iterdir() if p.is_file())
    require(
        frozen == sorted((ADJUDICATIONS, AMENDMENTS, *ANNOTATION_CSVS)),
        f"frozen annotation files: {frozen}",
    )
    for name in (ADJUDICATIONS, *ANNOTATION_CSVS):
        require(
            (ROOT / ANNOTATIONS / name).read_bytes()
            == (annotations / name).read_bytes(),
            f"the frozen {name} is not the staged one",
        )
    for name in FROZEN_UNCHANGED:
        require(
            (ROOT / SNAPSHOT_RUN / name).read_bytes()
            == git_blob(spec["base_commit"], SNAPSHOT_RUN / name),
            f"the frozen {name} is not release 20260930's",
        )
    require(
        (ROOT / SNAPSHOT_RUN / EXCLUSIONS).read_bytes()
        == (us / EXCLUSIONS).read_bytes(),
        "the frozen exclusion record is not the staged one",
    )
    require(
        (ROOT / SERVING).read_bytes() == base_serving,
        "the serving configuration changed",
    )
    manifest = json.loads((ROOT / MANIFEST).read_text())
    problems = manifest_problems(head_manifest, manifest)
    require(not problems, f"the manifest changed outside the release: {problems[:8]}")
    require(
        manifest["model_response_date"] == window,
        "the manifest's window is not the derived one",
    )
    cache = (
        ROOT / "app/.cache" / f"dashboard-data-{receipt['payload_sha256'][:16]}.json"
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(payload_path, cache)
    asset = stage / "predictions.csv.gz"
    freezer.gzip_deterministic(
        us / "predictions.csv", asset, stored_name="predictions.csv"
    )
    require(
        asset.read_bytes() == (ROOT / SNAPSHOT_RUN / "predictions.csv.gz").read_bytes(),
        "the predictions asset is not the frozen predictions",
    )
    print(f"Froze {tag} locally: payload {receipt['payload_sha256']}, window {window}")
    print(
        "Next: sensitivity rescoring, prose, notes and tests, paper render, "
        "freeze_snapshot.py --rendered-only, then the release upload."
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="step", required=True)
    step = sub.add_parser("prepare")
    step.add_argument("--base-stage", type=Path, required=True)
    step.add_argument("--stage", type=Path, required=True)
    step = sub.add_parser("export")
    step.add_argument("--stage", type=Path, required=True)
    step = sub.add_parser("freeze")
    step.add_argument("--stage", type=Path, required=True)
    step.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    {"prepare": prepare, "export": export, "freeze": freeze}[args.step](args)


if __name__ == "__main__":
    main()
