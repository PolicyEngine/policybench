"""Re-judge the carried-over verdicts the 2026-09-30 judge-isolation audit found.

The audit (``docs/judge_isolation_2026-09-30/REPORT.md``) bound every published
judge verdict to the transcript that produced it. Five verdicts carried over
into release ``dashboard-data-20260930`` cannot be presented as independent:

- one judge used tools: it launched a Workflow whose agents searched the repo
  and read this case's earlier published verdict;
- one judge was shown this case's exclusion history through the checkout's git
  status;
- three verdicts have no transcript that holds their published text.

This driver re-judges exactly those five with the isolated runner
(``scripts/run_audit_claude.sh``) and stages release ``dashboard-data-20260930b``.
Nothing else may change: every other verdict carries over byte for byte, the
adjudication record and the scoring exclusions are release 20260930's, every
model's ``modelStats`` entry and the heatmap are byte-identical, and the payload
may differ from the base only in the five cases' annotation fields.

  finish_rejudge_20260930b.py --stage-dir S --step prepare --base-stage B
  CLAUDE_CONFIG_DIR=... CLAUDE_CODE_OAUTH_TOKEN=... AUDIT_ACCOUNT=... \\
    finish_rejudge_20260930b.py --stage-dir S --step judge
  finish_rejudge_20260930b.py --stage-dir S --step triage
  finish_rejudge_20260930b.py --stage-dir S --step export
  freeze_rejudge_20260930b.py --stage-dir S [--dry-run]

Each step refuses with SystemExit before it writes anything outside the stage.
A re-judge that flags the reference, or leaves ``llm_error`` for a scored row,
stops triage: that is a new reference question for Max, not something this
driver decides.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import finish_gpt61sol as base_driver  # noqa: E402

RUN_NAME = base_driver.RUN_NAME
SNAPSHOT = base_driver.SNAPSHOT
ANNOTATIONS = base_driver.ANNOTATIONS
ADJUDICATIONS = base_driver.ADJUDICATIONS
BOARD_MODELS = base_driver.BOARD_MODELS
CARRIED_USAGE = base_driver.CARRIED_USAGE
KEY = base_driver.KEY
JUDGE_MODEL = "claude-opus-5-5"

BASE_TAG = base_driver.RELEASE_TAG
RELEASE_TAG = "dashboard-data-20260930b"
# Release 20260930 as merged to main, and its payload's sha256. Pinned from the
# merge; every step checks the checkout and the base stage against them.
BASE_COMMIT: str | None = None
BASE_SHA256: str | None = None

# The five cases: the sha256 of the verdict the audit examined, of the prompt
# its judge saw, and why it is re-judged. prepare refuses a base stage whose
# verdict or prompt for any of them differs, so the re-judge replaces exactly
# what was audited.
NO_TRANSCRIPT = "No transcript holds the published verdict's text."
REJUDGE: dict[str, tuple[str, str, str]] = {
    "us__scenario_086__federal_refundable_credits": (
        "101ad0a457764903753416f9aefa0295e8fb6de8a583407675a3e7e20f504de3",
        "278696e8621e02462272b88b837c08e4a6dd4ec2518ad57360573d0fd9435d1e",
        "Its 2026-09-05 judge launched a Workflow whose agents searched the repo "
        "and read this case's earlier published case note and row annotations.",
    ),
    "us__scenario_045__snap": (
        "aaa14a511fa37c104fb0a09aa23d8168b5d3bb817264c468eda53fb17d6ef348",
        "b2cbc9c82294274eaf513f55413f8551012d51b914779b579611bd5c8677cfcc",
        "Its 2026-09-24 judge ran in a git checkout whose status, injected into "
        "its context, named this case's r33 exclusion and fix.",
    ),
    "us__scenario_014__federal_refundable_credits": (
        "ad32821e5adc7fcf36c1d1587bf10514d6dbd6195cf48a5945605a22db528f64",
        "77d73d79de6d24641da717e264acaa4bdefe11ad22f59daf6d9b1ac6015162f3",
        NO_TRANSCRIPT,
    ),
    "us__scenario_015__federal_refundable_credits": (
        "20abcd0302b072f8fb64b41f73a46de45b9ae1c0e56f131e142f11a7a78037b2",
        "9762bfd026cc4e732c792f3b5f0715c2b19cc73284c034b388d311fc3d2b24cd",
        NO_TRANSCRIPT,
    ),
    "us__scenario_015__head_medicaid_eligible": (
        "5a389e3f4e8f93e1caabc888cded222f52155a41df43eebdcf41f7b087a04d34",
        "16802b03cfffc8cd49b6414abad9bb1000f2797a76ffe6e6bb67b8c0473cd134",
        NO_TRANSCRIPT,
    ),
}

# The payload fields a re-judge writes, per (scenario, variable, model) row.
ANNOTATION_FIELDS = frozenset(
    {
        "annotation",
        "failureSource",
        "failureSubtype",
        "caseAnnotation",
        "caseFailureSources",
        "caseFailureSubtypes",
    }
)
# What the judge's transcript may carry besides its prompt and its answer.
TRANSCRIPT_ATTACHMENTS = frozenset(
    {
        "environment",
        "model",
        "date",
        "session_context",
        "total_tokens_reminder",
        "prompt_snapshot",
        "structured_output",
        "ultra_effort_enter",
        "silent_turn_reminder",
    }
)
STAGE = "stage.json"
AUDIT_FILES = ("verdict.json", "verdict.meta.json", "prompt.md")

require = base_driver.require
digest = base_driver.digest
write_json = base_driver.write_json


def case_key(case_id: str) -> tuple[str, str]:
    """(scenario_id, variable) of an audit case id."""
    _, scenario, variable = case_id.split("__", 2)
    return scenario, variable


REJUDGE_KEYS = frozenset(case_key(case) for case in REJUDGE)


def require_pins() -> None:
    require(
        BASE_COMMIT is not None and BASE_SHA256 is not None,
        "BASE_COMMIT and BASE_SHA256 are not pinned: pin release 20260930 as merged",
    )


def base_blob(path: str) -> bytes:
    """A file as committed at BASE_COMMIT (release 20260930 on main)."""
    require_pins()
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{BASE_COMMIT}:{path}"],
        capture_output=True,
    )
    require(
        result.returncode == 0,
        f"cannot read {path} at {BASE_COMMIT[:12]}; fetch full history: "
        f"{result.stderr.decode().strip()}",
    )
    return result.stdout


def base_payload() -> dict:
    """Release 20260930's payload, from BASE_COMMIT, checked against its pin."""
    snapshot = (SNAPSHOT / "data.json.gz").relative_to(ROOT).as_posix()
    live = {"countries": {"us": json.loads(gzip.decompress(base_blob(snapshot)))}}
    require(
        hashlib.sha256(json.dumps(live).encode()).hexdigest() == BASE_SHA256,
        "base payload sha256 mismatch",
    )
    require(
        len(live["countries"]["us"]["modelStats"]) == BOARD_MODELS,
        f"base must have {BOARD_MODELS} models",
    )
    return live


def bundle_dir(stage: Path) -> Path:
    return stage / "publish" / RUN_NAME


def load_stage(stage: Path) -> dict:
    path = stage / STAGE
    require(path.is_file(), f"{path} missing: run prepare")
    record = json.loads(path.read_text())
    require(
        record.get("base_tag") == BASE_TAG
        and record.get("base_sha256") == BASE_SHA256
        and record.get("base_commit") == BASE_COMMIT
        and sorted(record.get("rejudge", [])) == sorted(REJUDGE),
        "stage.json does not bind this driver's base and re-judge set",
    )
    return record


# ---------------------------------------------------------------- prepare


def prepare(args) -> None:
    """Copy release 20260930's stage, then set aside the five verdicts."""
    require_pins()
    stage, source = args.stage_dir, args.base_stage
    require(source is not None, "--base-stage is required for prepare")
    require(not stage.exists(), f"{stage} exists; prepare writes a fresh stage")
    pointer = json.loads(base_blob("app/src/data.artifact.json"))
    require(
        pointer.get("tag") == BASE_TAG and pointer.get("sha256") == BASE_SHA256,
        "BASE_COMMIT's pointer is not release 20260930",
    )
    base_payload()

    # The base stage must be exactly the one release 20260930's receipt binds.
    receipt = json.loads((source / "release-ready.json").read_text())
    require(
        receipt.get("release_tag") == BASE_TAG
        and receipt.get("payload_sha256") == BASE_SHA256
        and receipt.get("partial") is False,
        "the base stage's receipt is not release 20260930's",
    )
    for rel, pin in receipt["files"].items():
        require(
            digest(source / rel) == pin, f"base stage file changed since export: {rel}"
        )
    # Its annotations are the committed ones.
    source_bundle = bundle_dir(source)
    for path in sorted((source_bundle / "annotations").iterdir()):
        committed = f"annotations/{RUN_NAME}/{path.name}"
        require(
            path.read_bytes() == base_blob(committed),
            f"base stage {path.name} differs from the committed {committed}",
        )
    cases = source / "audit" / "cases"
    for case, pins in REJUDGE.items():
        require(
            digest(cases / case / "verdict.json") == pins[0],
            f"{case}: the base verdict is not the audited one",
        )
        require(
            digest(cases / case / "prompt.md") == pins[1],
            f"{case}: the base prompt is not the audited one",
        )

    stage.mkdir(parents=True)
    shutil.copytree(source / "publish", stage / "publish")
    shutil.copytree(source / "audit", stage / "audit")
    audit = stage / "audit" / "cases"
    carried = {}
    for case_dir in sorted(audit.iterdir()):
        for name in AUDIT_FILES:
            path = case_dir / name
            if path.is_file():
                carried[f"{case_dir.name}/{name}"] = digest(path)
    for case, pins in REJUDGE.items():
        set_aside(audit / case, stage / "replaced-verdicts" / case, pins[2])
    bundle = bundle_dir(stage)
    write_json(
        stage / STAGE,
        {
            "base_tag": BASE_TAG,
            "base_sha256": BASE_SHA256,
            "base_commit": BASE_COMMIT,
            "base_stage": str(source),
            "release_tag": RELEASE_TAG,
            "rejudge": sorted(REJUDGE),
            "audit_files": carried,
            "bundle_files": {
                str(p.relative_to(stage)): digest(p)
                for p in sorted(bundle.rglob("*"))
                if p.is_file()
            },
        },
    )
    print(f"Prepared {stage}: {len(REJUDGE)} verdicts set aside for re-judging")


def set_aside(case_dir: Path, destination: Path, reason: str) -> None:
    """Move a case's verdict and its judge's records aside; never delete them."""
    destination.mkdir(parents=True, exist_ok=True)
    moved = []
    for path in sorted(case_dir.iterdir()):
        if path.name == "prompt.md":
            continue
        shutil.move(str(path), destination / path.name)
        moved.append(path.name)
    require("verdict.json" in moved, f"{case_dir.name}: no verdict to set aside")
    (destination / "reason.txt").write_text(reason + "\n")


# ---------------------------------------------------------------- judge


def judge(args) -> None:
    """Run the isolated runner on the five cases only, then validate."""
    record = load_stage(args.stage_dir)
    env = dict(os.environ)
    env["AUDIT_ONLY"] = " ".join(record["rejudge"])
    env["AUDIT_MODEL"] = JUDGE_MODEL
    env.setdefault("AUDIT_PARALLEL", str(len(REJUDGE)))
    env.setdefault("AUDIT_PYTHON", sys.executable)
    subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/run_audit_claude.sh"),
            str(args.stage_dir / "audit"),
        ],
        env=env,
        cwd=ROOT,
        check=False,
    )
    problems = validate(args.stage_dir, record)
    require(not problems, "judge step left problems:\n" + "\n".join(problems))
    print(f"Judged {len(REJUDGE)} cases; every verdict validates")


# ---------------------------------------------------------------- validate


def prompt_model_ids(prompt: str) -> list[str]:
    """The model ids a verdict must cover, from the prompt's final line."""
    marker = "using these exact model ids:"
    last = prompt.rstrip().splitlines()[-1]
    require(marker in last, "prompt's final line does not list the model ids")
    return [m.strip() for m in last.split(marker, 1)[1].split(",") if m.strip()]


def transcript_problems(path: Path) -> list[str]:
    """Anything in a judge transcript beyond its prompt and its answer.

    Checked here independently of the runner: a tool call other than the
    structured answer, a delegate, an attachment of an unlisted kind, a
    working directory inside a git repository, or a skill loaded into the
    conversation.
    """
    problems = []
    if not path.is_file():
        return [f"no transcript at {path}"]
    for number, line in enumerate(path.read_text().splitlines(), 1):
        try:
            event = json.loads(line)
        except ValueError:
            problems.append(f"line {number} is not JSON")
            continue
        if event.get("type") == "attachment":
            attachment = event.get("attachment") or {}
            kind = attachment.get("type")
            if kind not in TRANSCRIPT_ATTACHMENTS:
                problems.append(f"attachment {kind!r} on line {number}")
            if kind == "environment" and (attachment.get("snapshot") or {}).get(
                "isGitRepo"
            ):
                problems.append("the judge ran inside a git repository")
            if kind == "session_context" and (attachment.get("context") or {}).get(
                "gitStatus"
            ):
                problems.append("the judge was shown a git status")
        message = event.get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and "Base directory for this skill:" in content:
            problems.append(f"a skill was loaded on line {number}")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            kind = str(part.get("type", ""))
            if kind.endswith("tool_use") and not (
                kind == "tool_use" and part.get("name") == "StructuredOutput"
            ):
                problems.append(
                    f"tool call {part.get('name') or kind} on line {number}"
                )
            if kind == "text" and "Base directory for this skill:" in str(
                part.get("text")
            ):
                problems.append(f"a skill was loaded on line {number}")
    return problems


def validate(stage: Path, record: dict) -> list[str]:
    """Every carried-over verdict unchanged; every re-judge isolated and complete."""
    from validate_verdict import verdict_errors

    from policybench.audit import is_hedged

    problems = []
    audit = stage / "audit"
    schema = audit / "schema.json"
    for rel, pin in record["audit_files"].items():
        case = rel.split("/", 1)[0]
        path = audit / "cases" / rel
        if case in REJUDGE and not rel.endswith("prompt.md"):
            continue
        if not path.is_file() or digest(path) != pin:
            problems.append(f"carried-over {rel} changed or is missing")
    present = {
        f"{p.parent.name}/{p.name}"
        for p in (audit / "cases").glob("*/*")
        if p.name in AUDIT_FILES
    }
    extra = sorted(
        rel
        for rel in present - set(record["audit_files"])
        if rel.split("/", 1)[0] not in REJUDGE
    )
    problems += [f"unexpected audit file {rel}" for rel in extra]

    for case, pins in REJUDGE.items():
        case_dir = audit / "cases" / case
        verdict_path = case_dir / "verdict.json"
        meta_path = case_dir / "verdict.meta.json"
        if not verdict_path.is_file() or not meta_path.is_file():
            problems.append(f"{case}: no verdict yet")
            continue
        problems += [f"{case}: {e}" for e in verdict_errors(schema, verdict_path)]
        verdict = json.loads(verdict_path.read_text())
        meta = json.loads(meta_path.read_text())
        prompt = (case_dir / "prompt.md").read_text()
        checks = {
            "the sidecar does not bind the verdict": meta.get("verdict_sha256")
            == digest(verdict_path),
            "the prompt is not the audited one": digest(case_dir / "prompt.md")
            == pins[1],
            "the sidecar does not bind the prompt": meta.get("prompt_sha256")
            == pins[1],
            "the verdict is the replaced one": digest(verdict_path) != pins[0],
            f"the judge was not {JUDGE_MODEL}": meta.get("judge_model_reported")
            == [JUDGE_MODEL],
            "the runner did not record an isolated judge": (
                meta.get("judge_runner") == "scripts/run_audit_claude.sh"
                and (meta.get("judge_isolation") or {}).get("transcript_tool_calls")
                == 0
            ),
            "the judge did not bill a subscription login": (
                (meta.get("judge_auth") or {}).get("method")
                in ("oauth_token", "claude.ai")
            ),
        }
        problems += [f"{case}: {message}" for message, ok in checks.items() if not ok]
        problems += [
            f"{case}: {p}"
            for p in transcript_problems(case_dir / "claude.transcript.jsonl")
        ]
        judged = [m.get("model") for m in verdict.get("models", [])]
        expected = prompt_model_ids(prompt)
        if sorted(judged) != sorted(expected) or len(set(judged)) != len(judged):
            problems.append(f"{case}: models {judged} are not exactly {expected}")
        texts = [verdict.get("rationale")] + [
            m.get("diagnosis") for m in verdict.get("models", [])
        ]
        if any(is_hedged(text) for text in texts):
            problems.append(f"{case}: hedged text")
    return problems


# ---------------------------------------------------------------- triage


def triage(args) -> None:
    """Collect every verdict and write annotations that differ only for the five."""
    import pandas as pd

    from policybench.adjudications import (
        apply_adjudications,
        excluded_case_keys,
        load_adjudications,
        verify_adjudications_applied,
    )
    from policybench.audit import collect_audit
    from policybench.reference_exclusions import (
        exclusion_keys,
        load_reference_exclusions,
    )

    if hasattr(pd.options, "future") and hasattr(pd.options.future, "infer_string"):
        pd.options.future.infer_string = False
    stage = args.stage_dir
    record = load_stage(stage)
    problems = validate(stage, record)
    require(not problems, "verdicts do not validate:\n" + "\n".join(problems))
    bundle = bundle_dir(stage)
    annotations = bundle / "annotations"
    for name in ("us_audit_row_annotations.csv", "us_case_notes.csv", ADJUDICATIONS):
        rel = f"publish/{RUN_NAME}/annotations/{name}"
        require(
            digest(annotations / name) == record["bundle_files"][rel],
            f"staged {name} changed before triage; re-run prepare",
        )
    record_path = annotations / ADJUDICATIONS
    require(
        record_path.read_bytes()
        == base_blob(f"annotations/{RUN_NAME}/{ADJUDICATIONS}"),
        "the adjudication record is not release 20260930's",
    )
    decisions = load_adjudications(record_path)
    decided = {(d["scenario_id"], d["variable"]) for d in decisions}
    require(
        not decided & REJUDGE_KEYS,
        f"a re-judged case has a recorded decision: {sorted(decided & REJUDGE_KEYS)}",
    )

    out = collect_audit(bundle / "us", stage / "audit")
    require(out["missing"].empty and out["hedged"].empty, "missing or hedged verdicts")
    rows = out["row"]
    cases = out["case"].rename(
        columns={
            "case_failure_source": "case_failure_sources",
            "case_failure_subtype": "case_failure_subtypes",
        }
    )
    rows, cases, _ = apply_adjudications(rows, cases, decisions)
    verify_adjudications_applied(rows, cases, decisions)
    excluded = exclusion_keys(load_reference_exclusions(bundle / "us"))
    require(
        excluded == excluded_case_keys(decisions),
        "adjudication exclusions differ from the frozen scoring exclusions",
    )
    flags = cases[cases.reference_suspect.astype(bool)]
    scored = ~rows[KEY].apply(tuple, axis=1).isin(excluded)
    unresolved = rows[
        scored
        & ~rows.failure_source.isin(
            ["llm_error", "parse_contract_failure", "budget_exhausted_at_ceiling"]
        )
    ]
    flags.to_csv(stage / "reference-flags.csv", index=False)
    unresolved.to_csv(stage / "unresolved-rows.csv", index=False)
    require(
        flags.empty and unresolved.empty,
        "a re-judge raised a reference question: see reference-flags.csv and "
        "unresolved-rows.csv. Queue it for Max (cos add-decision); do not "
        "decide it here.",
    )

    base_rows = pd.read_csv(annotations / "us_audit_row_annotations.csv")
    base_cases = pd.read_csv(annotations / "us_case_notes.csv")
    changes = {
        "rows": annotation_changes(base_rows, rows, KEY + ["model"]),
        "cases": annotation_changes(base_cases, cases, KEY),
    }
    write_json(stage / "annotation-changes.json", changes)
    rows.to_csv(annotations / "us_audit_row_annotations.csv", index=False)
    cases.to_csv(annotations / "us_case_notes.csv", index=False)
    # Written back through pandas, every row outside the five must keep its bytes.
    for name in ("us_audit_row_annotations.csv", "us_case_notes.csv"):
        require_lines_outside_rejudge_unchanged(
            base_blob(f"annotations/{RUN_NAME}/{name}").decode(),
            (annotations / name).read_text(),
            name,
        )
    print(
        f"Triage complete: {len(rows)} rows / {len(cases)} cases; "
        f"{len(changes['rows'])} row and {len(changes['cases'])} case "
        "annotations changed"
    )


def annotation_changes(before, after, key: list[str]) -> list[dict]:
    """Every row whose values differ; only the five cases may appear.

    The key sets must match exactly: a re-judge changes text and labels, never
    which rows exist.
    """
    import pandas as pd

    require(list(before.columns) == list(after.columns), "annotation columns changed")
    left = before.set_index(key).sort_index()
    right = after.set_index(key).sort_index()
    require(left.index.equals(right.index), "annotation rows added or dropped")
    changed = []
    for index in left.index:
        a, b = left.loc[index], right.loc[index]
        diffs = {
            column: {"before": _plain(a[column]), "after": _plain(b[column])}
            for column in left.columns
            if not (pd.isna(a[column]) and pd.isna(b[column]))
            and a[column] != b[column]
        }
        if diffs:
            names = dict(zip(key, index if isinstance(index, tuple) else (index,)))
            require(
                (names["scenario_id"], names["variable"]) in REJUDGE_KEYS,
                f"an annotation outside the re-judged cases changed: {names}",
            )
            changed.append({**names, "changes": diffs})
    return changed


def _plain(value):
    return (
        None if value != value else (value.item() if hasattr(value, "item") else value)
    )


def require_lines_outside_rejudge_unchanged(before: str, after: str, name: str) -> None:
    """Byte-level check: only lines of the five cases may differ."""
    old, new = before.splitlines(), after.splitlines()
    require(old[0] == new[0], f"{name}: header changed")

    prefixes = tuple(f"us,{s},{v}," for s, v in REJUDGE_KEYS)

    def outside(lines):
        return [line for line in lines[1:] if not line.startswith(prefixes)]

    require(
        outside(old) == outside(new),
        f"{name}: a row outside the re-judged cases changed",
    )


# ---------------------------------------------------------------- export


def payload_diff(before, after, path=()) -> list[tuple]:
    """Paths of every differing leaf between two JSON values."""
    if isinstance(before, dict) and isinstance(after, dict):
        out = []
        for key in sorted(set(before) | set(after)):
            if key not in before or key not in after:
                out.append(path + (key,))
            else:
                out += payload_diff(before[key], after[key], path + (key,))
        return out
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return [path]
        out = []
        for index, (a, b) in enumerate(zip(before, after)):
            out += payload_diff(a, b, path + (index,))
        return out
    return [] if json.dumps(before) == json.dumps(after) else [path]


def allowed_path(path: tuple) -> bool:
    """A payload path a re-judge of the five cases may change."""
    # countries / us / scenarioPredictions / scenario / variable / model / field
    return (
        len(path) == 7
        and path[:3] == ("countries", "us", "scenarioPredictions")
        and (path[3], path[4]) in REJUDGE_KEYS
        and path[6] in ANNOTATION_FIELDS
    )


def export(args) -> None:
    """Export, then prove the payload moved only in the five cases' annotations."""
    from policybench.dashboard_schema import validate_dashboard_payload
    from policybench.full_run_export import export_full_run

    stage = args.stage_dir
    record = load_stage(stage)
    problems = validate(stage, record)
    require(not problems, "verdicts do not validate:\n" + "\n".join(problems))
    require((stage / "annotation-changes.json").is_file(), "run triage first")
    bundle = bundle_dir(stage)
    base_driver.verify_reference_pins(bundle / "us", "staged reference")
    live = base_payload()
    payload = export_full_run(bundle, countries=["us"], skip_app_data=True)
    stats = payload["countries"]["us"]["modelStats"]
    previous = {m["model"]: m for m in live["countries"]["us"]["modelStats"]}
    for model, keys in CARRIED_USAGE.items():
        row = next(s for s in stats if s["model"] == model)
        for key in keys:
            row[key] = previous[model][key]
    drift = base_driver.incumbent_drift(stats, previous)
    require(len(stats) == BOARD_MODELS and not drift, f"modelStats drift: {drift}")
    errors = validate_dashboard_payload(payload, require_failure_annotations=True)
    require(not errors, f"payload validation failed: {errors[:8]}")
    diff = payload_diff(live, payload)
    outside = [p for p in diff if not allowed_path(p)]
    require(
        not outside,
        f"payload changed outside the five cases' annotations: {outside[:8]}",
    )
    touched = sorted({(p[3], p[4]) for p in diff})
    write_json(
        stage / "payload-diff.json",
        {"paths": [list(p) for p in diff], "cases": [list(t) for t in touched]},
    )
    path = stage / f"data-board{BOARD_MODELS}.json"
    path.write_text(json.dumps(payload, allow_nan=False))
    shutil.copyfile(path, bundle / "data.json")
    pinned = [p for p in (bundle / "annotations").iterdir() if p.is_file()]
    pinned += [
        bundle / "us" / name
        for name in (*base_driver.REFERENCE_FILES, "predictions.csv")
    ]
    pinned += [
        stage / STAGE,
        stage / "annotation-changes.json",
        stage / "payload-diff.json",
    ]
    pinned += [
        p
        for p in (stage / "audit").rglob("*")
        if p.is_file()
        and p.name
        in {
            "verdict.json",
            "verdict.meta.json",
            "prompt.md",
            "cases.jsonl",
            "schema.json",
        }
    ]
    pinned += [
        stage / "audit/cases" / case / "claude.transcript.jsonl" for case in REJUDGE
    ]
    write_json(
        stage / "release-ready.json",
        {
            "release_tag": RELEASE_TAG,
            "base_tag": BASE_TAG,
            "base_sha256": BASE_SHA256,
            "base_commit": BASE_COMMIT,
            "payload_sha256": digest(path),
            "models": BOARD_MODELS,
            "partial": False,
            "files": {str(p.relative_to(stage)): digest(p) for p in pinned},
        },
    )
    print(
        f"STAGED {RELEASE_TAG}: payload {digest(path)[:12]}, no modelStats drift, "
        f"{len(diff)} annotation fields changed in {len(touched)} cases"
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument(
        "--step", choices=["prepare", "judge", "triage", "export"], required=True
    )
    parser.add_argument("--base-stage", type=Path)
    args = parser.parse_args(argv)
    args.stage_dir = args.stage_dir.resolve()
    if args.base_stage is not None:
        args.base_stage = args.base_stage.resolve()
    return args


def main(argv=None) -> None:
    args = parse_args(argv)
    {"prepare": prepare, "judge": judge, "triage": triage, "export": export}[args.step](
        args
    )


if __name__ == "__main__":
    main()
