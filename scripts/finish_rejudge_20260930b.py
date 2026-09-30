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
Nothing else may change:

- every other verdict carries over byte for byte;
- the adjudication record, the scoring exclusions, the references and the
  predictions are release 20260930's;
- the annotation files are release 20260930's committed bytes with only the
  five cases' records replaced, so every wording amendment stays as published;
- every model's ``modelStats`` entry is byte-identical;
- the payload differs from the base only in the five cases' annotation fields.

  finish_rejudge_20260930b.py --stage-dir S --step prepare --base-stage B
  CLAUDE_CONFIG_DIR=... CLAUDE_CODE_OAUTH_TOKEN=... AUDIT_ACCOUNT=... \\
    finish_rejudge_20260930b.py --stage-dir S --step judge
  finish_rejudge_20260930b.py --stage-dir S --step triage
  finish_rejudge_20260930b.py --stage-dir S --step export
  freeze_rejudge_20260930b.py --stage-dir S [--dry-run]

Each step refuses with SystemExit before it writes anything outside the stage.
A re-judge that flags the reference, or leaves a scored row outside the
llm_error family, stops triage: that is a new reference question for Max, not
something this driver decides.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import gzip
import hashlib
import io
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
ADJUDICATIONS = base_driver.ADJUDICATIONS
BOARD_MODELS = base_driver.BOARD_MODELS
CARRIED_USAGE = base_driver.CARRIED_USAGE
KEY = base_driver.KEY
JUDGE_MODEL = "claude-opus-5-5"
JUDGE_ROUNDS = 3

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

# The two annotation files a re-judge rewrites: their key columns, and the
# columns the judge's verdict decides. Every other column keeps its bytes.
ANNOTATION_CSVS: dict[str, tuple[list[str], frozenset[str]]] = {
    "us_audit_row_annotations.csv": (
        KEY + ["model"],
        frozenset(
            {"failure_source", "failure_subtype", "reference_suspect", "annotation"}
        ),
    ),
    "us_case_notes.csv": (
        KEY,
        frozenset(
            {
                "case_failure_sources",
                "case_failure_subtypes",
                "reference_suspect",
                "reference_bug_hypothesis",
                "case_annotation",
            }
        ),
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
# Text that would mean a system prompt carried a checkout's git status or an
# instruction file.
SYSTEM_PROMPT_LEAKS = (
    "gitStatus",
    "Current branch:",
    "Recent commits:",
    "Contents of /",
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


def base_annotation_names() -> list[str]:
    """The annotation files release 20260930 commits."""
    require_pins()
    result = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "ls-tree",
            "--name-only",
            BASE_COMMIT,
            f"annotations/{RUN_NAME}/",
        ],
        capture_output=True,
        text=True,
    )
    require(result.returncode == 0, "cannot list release 20260930's annotations")
    return sorted(Path(line).name for line in result.stdout.split())


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


def tree_digests(root: Path, relative_to: Path) -> dict[str, str]:
    return {
        str(p.relative_to(relative_to)): digest(p)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


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
    # Every verdict set aside stays where it was put.
    for rel, pin in record.get("replaced_files", {}).items():
        path = stage / rel
        require(
            path.is_file() and digest(path) == pin, f"replaced record changed: {rel}"
        )
    return record


def add_replaced(stage: Path, record: dict) -> None:
    """Pin everything set aside so far in stage.json."""
    record["replaced_files"] = tree_digests(stage / "replaced-verdicts", stage)
    write_json(stage / STAGE, record)


# ---------------------------------------------------------------- prepare


def prepare(args) -> None:
    """Copy release 20260930's stage, then set aside the five verdicts."""
    require_pins()
    stage, source = args.stage_dir, args.base_stage
    require(source is not None, "--base-stage is required for prepare")
    base_driver.validate_stage_path(stage, [source])
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
    # Every verdict, sidecar and prompt it carries is one the receipt binds.
    carried_names = {
        str(p.relative_to(source))
        for p in (source / "audit" / "cases").glob("*/*")
        if p.name in AUDIT_FILES
    }
    unbound = sorted(carried_names - set(receipt["files"]))
    require(
        not unbound, f"base stage audit files the receipt does not bind: {unbound[:5]}"
    )
    # Its annotations are the committed ones.
    committed = base_annotation_names()
    for path in sorted((bundle_dir(source) / "annotations").iterdir()):
        require(path.name in committed, f"base stage has an uncommitted {path.name}")
        require(
            path.read_bytes() == base_blob(f"annotations/{RUN_NAME}/{path.name}"),
            f"base stage {path.name} differs from the committed one",
        )
    cases = source / "audit" / "cases"
    for case, (verdict_sha, prompt_sha, _) in REJUDGE.items():
        require(
            digest(cases / case / "verdict.json") == verdict_sha,
            f"{case}: the base verdict is not the audited one",
        )
        require(
            digest(cases / case / "prompt.md") == prompt_sha,
            f"{case}: the base prompt is not the audited one",
        )

    stage.mkdir(parents=True)
    shutil.copytree(source / "publish", stage / "publish")
    shutil.copytree(source / "audit", stage / "audit")
    audit = stage / "audit" / "cases"
    carried = {
        f"{p.parent.name}/{p.name}": digest(p)
        for p in sorted(audit.glob("*/*"))
        if p.name in AUDIT_FILES
    }
    for case, (_, _, reason) in REJUDGE.items():
        set_aside(
            audit / case, stage / "replaced-verdicts" / case / "published", reason
        )
    record = {
        "base_tag": BASE_TAG,
        "base_sha256": BASE_SHA256,
        "base_commit": BASE_COMMIT,
        "base_stage": str(source),
        "release_tag": RELEASE_TAG,
        "rejudge": sorted(REJUDGE),
        "audit_files": carried,
        "bundle_files": tree_digests(bundle_dir(stage), stage),
    }
    add_replaced(stage, record)
    print(f"Prepared {stage}: {len(REJUDGE)} verdicts set aside for re-judging")


def set_aside(case_dir: Path, destination: Path, reason: str) -> None:
    """Move a case's verdict and its judge's records aside; never delete them."""
    require(not destination.exists(), f"{destination} already exists")
    destination.mkdir(parents=True)
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
    """Run the isolated runner on the five cases, retrying a rejected verdict.

    The runner skips a case whose verdict already satisfies the schema, so a
    verdict that fails this driver's checks is set aside, with the reasons,
    and the case is judged again, up to JUDGE_ROUNDS times.
    """
    stage = args.stage_dir
    record = load_stage(stage)
    env = dict(os.environ)
    env["AUDIT_ONLY"] = " ".join(record["rejudge"])
    env["AUDIT_MODEL"] = JUDGE_MODEL
    env.setdefault("AUDIT_PARALLEL", str(len(REJUDGE)))
    env.setdefault("AUDIT_PYTHON", sys.executable)
    for round_number in range(1, JUDGE_ROUNDS + 1):
        subprocess.run(
            ["bash", str(ROOT / "scripts/run_audit_claude.sh"), str(stage / "audit")],
            env=env,
            cwd=ROOT,
            check=False,
        )
        failing = {}
        for case in REJUDGE:
            problems = case_problems(stage, case)
            if problems and (stage / "audit/cases" / case / "verdict.json").is_file():
                failing[case] = problems
        if not failing:
            break
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for case, problems in failing.items():
            set_aside(
                stage / "audit/cases" / case,
                stage / "replaced-verdicts" / case / f"round{round_number}-{stamp}",
                "Rejected by finish_rejudge_20260930b.py:\n" + "\n".join(problems),
            )
        add_replaced(stage, record)
        print(f"round {round_number}: set aside {sorted(failing)}; judging again")
    problems = validate(stage, record)
    require(not problems, "judge step left problems:\n" + "\n".join(problems))
    print(f"Judged {len(REJUDGE)} cases; every verdict validates")


# ---------------------------------------------------------------- validate


def prompt_model_ids(prompt: str) -> list[str]:
    """The model ids a verdict must cover, from the prompt's final line."""
    marker = "using these exact model ids:"
    last = prompt.rstrip().splitlines()[-1]
    require(marker in last, "prompt's final line does not list the model ids")
    return [m.strip() for m in last.split(marker, 1)[1].split(",") if m.strip()]


def transcript_problems(
    path: Path,
    session_id: str | None = None,
    prompt: str | None = None,
    verdict: dict | None = None,
) -> list[str]:
    """Anything in a judge transcript beyond its prompt and its answer.

    Checked here independently of the runner. The transcript must belong to
    the sidecar's session, open with exactly the case's prompt, end with
    exactly the verdict as its structured answer, and come from JUDGE_MODEL.
    It fails on any tool call but the structured answer, an attachment of an
    unlisted kind, a working directory inside a git repository, a git status,
    a system prompt carrying a git status or an instruction file, or a skill
    loaded into the conversation.
    """
    if not path.is_file():
        return [f"no transcript at {path}"]
    problems, first_user, answers = [], None, []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        try:
            event = json.loads(line)
        except ValueError:
            problems.append(f"line {number} is not JSON")
            continue
        if session_id is not None and event.get("sessionId") not in (None, session_id):
            problems.append(
                f"line {number} belongs to session {event.get('sessionId')}"
            )
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
            if kind == "prompt_snapshot":
                text = json.dumps(attachment.get("systemPrompt"))
                if any(leak in text for leak in SYSTEM_PROMPT_LEAKS):
                    problems.append(
                        f"the system prompt on line {number} carries context"
                    )
            if kind == "structured_output":
                answers.append(attachment.get("data"))
        message = event.get("message") or {}
        content = message.get("content")
        if event.get("type") == "assistant" and message.get("model") not in (
            None,
            JUDGE_MODEL,
        ):
            problems.append(f"line {number} was answered by {message.get('model')}")
        if (
            event.get("type") == "user"
            and isinstance(content, str)
            and first_user is None
        ):
            first_user = content
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
    if prompt is not None and first_user != prompt:
        problems.append("the transcript does not open with the case's prompt")
    if verdict is not None and (not answers or answers[-1] != verdict):
        problems.append("the transcript's structured answer is not the verdict")
    return problems


def case_problems(stage: Path, case: str) -> list[str]:
    """Why a re-judged case's verdict is not yet publishable, if it is not."""
    from validate_verdict import verdict_errors

    from policybench.audit import is_hedged

    _, prompt_sha, _ = REJUDGE[case]
    case_dir = stage / "audit" / "cases" / case
    verdict_path = case_dir / "verdict.json"
    meta_path = case_dir / "verdict.meta.json"
    if not verdict_path.is_file() or not meta_path.is_file():
        return ["no verdict yet"]
    try:
        verdict = json.loads(verdict_path.read_text())
        meta = json.loads(meta_path.read_text())
    except ValueError as error:
        return [f"unreadable verdict or sidecar: {error}"]
    problems = list(verdict_errors(stage / "audit" / "schema.json", verdict_path))
    prompt_path = case_dir / "prompt.md"
    prompt = prompt_path.read_text()
    checks = {
        "the sidecar does not bind the verdict": meta.get("verdict_sha256")
        == digest(verdict_path),
        "the prompt is not the audited one": digest(prompt_path) == prompt_sha,
        "the sidecar does not bind the prompt": meta.get("prompt_sha256") == prompt_sha,
        "the verdict is the replaced one": digest(verdict_path) != REJUDGE[case][0],
        f"the judge was not {JUDGE_MODEL}": meta.get("judge_model_reported")
        == [JUDGE_MODEL]
        and meta.get("judge_model_requested") == JUDGE_MODEL,
        "the sidecar records no judging time": bool(meta.get("judged_at_utc")),
        "the runner did not record an isolated judge": (
            meta.get("judge_runner") == "scripts/run_audit_claude.sh"
            and (meta.get("judge_isolation") or {}).get("transcript_tool_calls") == 0
        ),
        "the judge did not bill a subscription login": (
            (meta.get("judge_auth") or {}).get("method") in ("oauth_token", "claude.ai")
        ),
    }
    problems += [message for message, ok in checks.items() if not ok]
    problems += transcript_problems(
        case_dir / "claude.transcript.jsonl", meta.get("session_id"), prompt, verdict
    )
    models = verdict.get("models") if isinstance(verdict.get("models"), list) else []
    judged = [m.get("model") for m in models if isinstance(m, dict)]
    expected = prompt_model_ids(prompt)
    if sorted(judged) != sorted(expected) or len(set(judged)) != len(judged):
        problems.append(f"models {judged} are not exactly {expected}")
    texts = [verdict.get("rationale")] + [
        m.get("diagnosis") for m in models if isinstance(m, dict)
    ]
    if any(is_hedged(text) for text in texts):
        problems.append("hedged text")
    return problems


def validate(stage: Path, record: dict) -> list[str]:
    """Every carried-over verdict unchanged; every re-judge isolated and complete."""
    problems = []
    cases = stage / "audit" / "cases"
    for rel, pin in record["audit_files"].items():
        case = rel.split("/", 1)[0]
        if case in REJUDGE and not rel.endswith("prompt.md"):
            continue
        path = cases / rel
        if not path.is_file() or digest(path) != pin:
            problems.append(f"carried-over {rel} changed or is missing")
    present = {
        f"{p.parent.name}/{p.name}" for p in cases.glob("*/*") if p.name in AUDIT_FILES
    }
    extra = sorted(
        rel
        for rel in present - set(record["audit_files"])
        if rel.split("/", 1)[0] not in REJUDGE
    )
    problems += [f"unexpected audit file {rel}" for rel in extra]
    for case in REJUDGE:
        problems += [f"{case}: {p}" for p in case_problems(stage, case)]
    return problems


# ---------------------------------------------------------------- annotations


def csv_records(text: str) -> tuple[str, list[str]]:
    """Split CSV text into its header and whole records, each with its newline.

    A record ends at a newline outside quotes. Quotes inside a field are
    doubled, so a record is complete when its quote count is even.
    """
    lines = text.splitlines(keepends=True)
    require(lines, "empty CSV")
    records, buffer = [], ""
    for line in lines[1:]:
        buffer += line
        if buffer.count('"') % 2 == 0:
            records.append(buffer)
            buffer = ""
    require(buffer == "", "CSV ends inside a quoted field")
    return lines[0], records


def record_fields(header: str, record: str) -> dict[str, str]:
    names = next(csv.reader(io.StringIO(header)))
    values = next(csv.reader(io.StringIO(record)))
    require(
        len(names) == len(values), f"record has {len(values)} fields, not {len(names)}"
    )
    return dict(zip(names, values))


def record_key(fields: dict[str, str], key: list[str]) -> tuple[str, ...]:
    return tuple(fields[k] for k in key)


def splice_annotations(base_text: str, new_rows, key: list[str]) -> str:
    """Release 20260930's CSV with only the five cases' records replaced.

    ``new_rows`` holds every record of the five cases, as collected from the
    new verdicts. Each case's records go where its old ones were, in the old
    order; every other record keeps its exact bytes.
    """
    header, records = csv_records(base_text)
    columns = next(csv.reader(io.StringIO(header)))
    require(
        sorted(new_rows.columns) == sorted(columns),
        "collected columns differ from the base CSV",
    )
    newline = "\r\n" if header.endswith("\r\n") else "\n"
    serialized = new_rows[columns].to_csv(
        index=False, header=False, lineterminator=newline
    )
    _, fresh = csv_records(header + serialized)
    replacement = {record_key(record_fields(header, r), key): r for r in fresh}
    require(len(replacement) == len(fresh), "collected rows repeat a key")
    out, used = [header], set()
    for record in records:
        fields = record_fields(header, record)
        if (fields["scenario_id"], fields["variable"]) in REJUDGE_KEYS:
            k = record_key(fields, key)
            require(k in replacement, f"collected rows drop {k}")
            out.append(replacement[k])
            used.add(k)
        else:
            out.append(record)
    require(
        used == set(replacement),
        f"collected rows add {sorted(set(replacement) - used)}",
    )
    return "".join(out)


def annotation_changes(base_text: str, text: str, name: str) -> list[dict]:
    """Every changed record of one annotation CSV; refuses any change beyond the five.

    Records compare as text, field by field, so a blank field is blank on both
    sides. Records outside the five must keep their bytes and their order, the
    five cases' key sets must not change, and within them only the columns the
    verdict decides may change.
    """
    key, decided = ANNOTATION_CSVS[name]
    header, old = csv_records(base_text)
    new_header, new = csv_records(text)
    require(header == new_header, f"{name}: header changed")
    require(len(old) == len(new), f"{name}: records added or dropped")
    changes = []
    for before, after in zip(old, new):
        a, b = record_fields(header, before), record_fields(header, after)
        require(
            record_key(a, key) == record_key(b, key),
            f"{name}: records reordered or rekeyed",
        )
        if before == after:
            continue
        require(
            (a["scenario_id"], a["variable"]) in REJUDGE_KEYS,
            f"{name}: a record outside the five changed: {record_key(a, key)}",
        )
        diffs = {c: {"before": a[c], "after": b[c]} for c in a if a[c] != b[c]}
        undecided = sorted(set(diffs) - decided)
        require(not undecided, f"{name}: {record_key(a, key)} changed {undecided}")
        changes.append({**dict(zip(key, record_key(a, key))), "changes": diffs})
    return changes


def verify_annotations(annotations: Path, expected_changes: dict | None = None) -> dict:
    """Every annotation file is release 20260930's, but for the five cases' records."""
    committed = base_annotation_names()
    staged = sorted(p.name for p in annotations.iterdir() if p.is_file())
    require(
        set(staged) <= set(committed), f"annotation files not in the release: {staged}"
    )
    changes = {}
    for name in staged:
        current = (annotations / name).read_bytes()
        base = base_blob(f"annotations/{RUN_NAME}/{name}")
        if name in ANNOTATION_CSVS:
            changes[name] = annotation_changes(base.decode(), current.decode(), name)
        else:
            require(current == base, f"{name} differs from release 20260930's")
    if expected_changes is not None:
        require(
            changes == expected_changes,
            "annotation changes differ from annotation-changes.json",
        )
    return changes


# ---------------------------------------------------------------- triage


def triage(args) -> None:
    """Collect the five cases' new annotations and splice them into the base files."""
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
    # Staged files may differ from the base only in the five cases' records, so
    # a triage that stopped before writing, or a finished one, can run again.
    verify_annotations(annotations)
    record_path = annotations / ADJUDICATIONS
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

    def five(frame):
        return frame[frame[KEY].apply(tuple, axis=1).isin(REJUDGE_KEYS)]

    spliced = {}
    for name, frame in (
        ("us_audit_row_annotations.csv", rows),
        ("us_case_notes.csv", cases),
    ):
        key, _ = ANNOTATION_CSVS[name]
        base_text = base_blob(f"annotations/{RUN_NAME}/{name}").decode()
        spliced[name] = splice_annotations(base_text, five(frame), key)
        annotation_changes(base_text, spliced[name], name)
    # Check everything before writing anything; then replace atomically.
    for name, text in spliced.items():
        temporary = annotations / f".{name}.tmp"
        temporary.write_text(text)
        os.replace(temporary, annotations / name)
    changes = verify_annotations(annotations)
    write_json(stage / "annotation-changes.json", changes)
    counts = {name: len(v) for name, v in changes.items()}
    print(f"Triage complete: changed records {counts}")


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
    changes_path = stage / "annotation-changes.json"
    require(changes_path.is_file(), "run triage first")
    bundle = bundle_dir(stage)
    verify_annotations(bundle / "annotations", json.loads(changes_path.read_text()))
    base_driver.verify_reference_pins(bundle / "us", "staged reference")
    # The export inputs are the ones prepare copied; export itself rewrites
    # data.json and the analysis outputs, so those are not compared.
    for name in (*base_driver.REFERENCE_FILES, "predictions.csv"):
        rel = str((bundle / "us" / name).relative_to(stage))
        require(
            digest(stage / rel) == record["bundle_files"][rel], f"staged {rel} changed"
        )
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
    pinned += [stage / STAGE, changes_path, stage / "payload-diff.json"]
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
    pinned += [p for p in (stage / "replaced-verdicts").rglob("*") if p.is_file()]
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
