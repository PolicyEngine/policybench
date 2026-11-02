"""Build release dashboard-data-20261013b from release dashboard-data-20261013.

The 2026-09-30 judge-isolation audit (docs/judge_isolation_2026-09-30/REPORT.md)
bound every published judge verdict to the transcript that produced it. Five
verdicts, carried unchanged through every release since, cannot be presented
as independent of the decisions published beside them:

- one judge used tools: it launched a Workflow whose agents searched the repo
  and read this case's earlier published verdict;
- one judge was shown this case's exclusion history through its checkout's git
  status;
- three verdicts have no transcript that holds their published text.

This release re-judges exactly those five on judge template v2 with the
isolated runner (scripts/run_audit_claude.sh) and changes nothing else. No
model, answer, reference, exclusion or adjudication changes, and every
model's statistics are byte-identical to release 20261013's.

Five steps. Each reads release 20261013 from git at the base commit, never
from the working tree, and refuses anything outside the release:

  prepare  stage release 20261013's bundle from git and its judged audit tree
           from the archived seed, set the five verdicts aside, and render the
           five cases on template v2;
  judge    run the isolated judge on the five cases, setting aside and
           retrying a verdict this driver rejects;
  collect  collect the new verdicts, stop on any reference question, splice
           the five cases' records into release 20261013's annotation files,
           and write the judge provenance record and the next seed digest;
  export   build the payload twice (the bytes must agree), check that it
           differs from the base only in the five cases' annotation fields,
           and write the receipt;
  freeze   freeze the snapshot through scripts/freeze_snapshot.py, then check
           what it wrote.

Usage::

    python scripts/release_20261013b.py prepare --audit-seed SEED \\
        --grounding GROUNDING --stage STAGE
    CLAUDE_CONFIG_DIR=... CLAUDE_CODE_OAUTH_TOKEN=... AUDIT_ACCOUNT=... \\
        python scripts/release_20261013b.py judge --stage STAGE
    python scripts/release_20261013b.py collect --stage STAGE
    python scripts/release_20261013b.py export --stage STAGE
    python scripts/release_20261013b.py freeze --stage STAGE [--dry-run]

``SEED`` is release 20261013's judged audit tree (its 677 cases); it is only
read. ``STAGE`` must be a new directory under results/local in this checkout.
A re-judge that flags the reference, or leaves a scored row outside the
llm_error family, stops ``collect``: that is a new reference question for
Max, not something this driver decides.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import functools
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import finish_musewonder as base_driver  # noqa: E402

RUN = base_driver.RUN_NAME
SNAPSHOT_DIR = Path("paper/snapshot/20260501")
SNAPSHOT_RUN = SNAPSHOT_DIR / "runs" / RUN
MANIFEST = SNAPSHOT_DIR / "manifest.json"
SERVING = SNAPSHOT_DIR / "model_serving_config.json"
ANNOTATIONS = Path("annotations") / RUN
POINTER = Path("app/src/data.artifact.json")
VERSIONS = Path("app/src/data.versions.json")
STAGE_ROOT = Path("results/local")
DOCS = Path("docs/release_20261013b")
PROVENANCE = DOCS / "judge_provenance.json"
SEED_DIGEST = DOCS / "seed_digest.csv"
# Developer corrections of the new verdicts' published wording: a committed
# input, applied by collect and appended to the committed amendments record.
WORDING = DOCS / "wording_amendments.json"
ADJUDICATIONS = "us_adjudications.json"
ROWS = "us_audit_row_annotations.csv"
NOTES = "us_case_notes.csv"
EXPLANATIONS = "us_case_reference_explanations.csv"
AMENDMENTS = "us_wording-amendments.json"
# The annotation files the bundle carries; AMENDMENTS is committed beside them.
STAGED_ANNOTATIONS = (ADJUDICATIONS, ROWS, NOTES, EXPLANATIONS)
EXCLUSIONS = "reference_exclusions.json"
REFERENCE_FILES = (
    "reference_outputs.csv",
    "reference_outputs.csv.meta.json",
    "scenarios.csv",
    "scenarios.csv.meta.json",
)
EXPORT_INPUTS = (
    *(f"us/{name}" for name in (*REFERENCE_FILES, EXCLUSIONS, "predictions.csv")),
    *(f"annotations/{name}" for name in (ROWS, NOTES, EXPLANATIONS)),
)

BASE_TAG = "dashboard-data-20261013"
RELEASE_TAG = "dashboard-data-20261013b"
# The squash merge of PR #217 on main, whose tree holds release 20261013, and
# that release's payload.
BASE_COMMIT = "bc305793c527531e7b3573dc789a436a7bc883d5"
BASE_SHA256 = "aef5dc73a76433c97994430f8eb6dfad6bdc6518b18ee3ea8f79cee704757477"
BASE_BYTES = 130988798
BOARD_MODELS = 48
JUDGE_MODEL = base_driver.JUDGE_MODEL
JUDGE_TEMPLATE_VERSION = 2
JUDGE_ROUNDS = 3
CARRIED_USAGE = base_driver.CARRIED_USAGE
KEY = ["scenario_id", "variable"]
# Release 20261013's judged tree, as the base commit records it: release
# 20261010's seed digest with the cases release 20261013 re-judged.
BASE_SEED_DIGEST = Path("docs/musewonder/seed_digest.csv")
BASE_PROVENANCE = Path("docs/musewonder/judge_provenance.json")

# The five cases: the sha256 of the verdict the audit examined and of the
# (template v1) prompt its judge saw, and why the case is re-judged. Both
# hashes are release 20261013's, unchanged since the audit.
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
    ROWS: (
        KEY + ["model"],
        frozenset(
            {"failure_source", "failure_subtype", "reference_suspect", "annotation"}
        ),
    ),
    NOTES: (
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
# The payload fields a re-judge writes, per (scenario, variable, model) cell.
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
# Manifest paths the freeze may change; every other leaf must equal the base's.
MANIFEST_CHANGES = (
    ("audit_annotation_artifacts", "files", ROWS),
    ("audit_annotation_artifacts", "files", NOTES),
    ("audit_annotation_artifacts", "judge_provenance"),
    ("live_dashboard_artifact",),
    ("published_dashboard_artifact",),
    ("source_run_artifacts", RUN, "files", "data.json.gz"),
    ("files", 0, "sha256"),
    ("rendered_paper_artifacts",),
)
# Frozen run files that must stay release 20261013's.
FROZEN_UNCHANGED = (*REFERENCE_FILES, EXCLUSIONS, "predictions.csv.gz")
# The audit files a case carries from the seed.
AUDIT_FILES = ("verdict.json", "verdict.meta.json", "prompt.md")
# A re-judged case's files that go aside with a replaced or rejected verdict.
JUDGE_FILES = (
    "verdict.json",
    "verdict.meta.json",
    "codex.log",
    "claude.json",
    "claude.log",
    "claude.transcript.jsonl",
)
PROVENANCE_NOTE = (
    "Provenance of the five judge verdicts release dashboard-data-20261013b "
    "replaces: the carried-over verdicts the 2026-09-30 judge-isolation audit "
    "could not clear (docs/judge_isolation_2026-09-30/REPORT.md). Each was "
    "re-judged by Claude Opus 5.5 on judge template v2 through "
    "scripts/run_audit_claude.sh, from an empty directory outside the repo, "
    "with no tools, an allowlisted environment, no user settings and a token "
    "login; each transcript passes the runner's checks. Counts are by group. "
    "Scores do not depend on judge verdicts."
)

require = base_driver.require
digest = base_driver.digest


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def case_key(case_id: str) -> tuple[str, str]:
    """(scenario_id, variable) of an audit case id."""
    _, scenario, variable = case_id.split("__", 2)
    return scenario, variable


REJUDGE_KEYS = frozenset(case_key(case) for case in REJUDGE)


def git_blob(commit: str, path: Path | str) -> bytes:
    """A file as git holds it at ``commit``."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{Path(path).as_posix()}"],
        capture_output=True,
    )
    require(
        result.returncode == 0,
        f"cannot read {path} at {commit[:12]}; fetch full history: "
        f"{result.stderr.decode().strip()}",
    )
    return result.stdout


def base_blob(path: Path | str) -> bytes:
    """A file as release 20261013 committed it."""
    return git_blob(BASE_COMMIT, path)


def base_annotation_names() -> list[str]:
    """The annotation files release 20261013 commits."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-tree", "--name-only", BASE_COMMIT]
        + [f"{ANNOTATIONS.as_posix()}/"],
        capture_output=True,
        text=True,
    )
    require(result.returncode == 0, "cannot list release 20261013's annotations")
    return sorted(Path(line).name for line in result.stdout.split())


def payload_text(payload: dict) -> str:
    """The bytes export writes and freeze_snapshot reassembles."""
    return json.dumps(payload, allow_nan=False)


def base_payload() -> dict:
    """Release 20261013's payload, from the base commit's frozen run."""
    blob = base_blob(SNAPSHOT_RUN / "data.json.gz")
    payload = {"countries": {"us": json.loads(gzip.decompress(blob))}}
    data = payload_text(payload).encode()
    require(
        sha(data) == BASE_SHA256 and len(data) == BASE_BYTES,
        "the base commit's payload is not release 20261013's",
    )
    require(
        len(payload["countries"]["us"]["modelStats"]) == BOARD_MODELS,
        f"the base must have {BOARD_MODELS} models",
    )
    return payload


def base_seed() -> dict[str, dict[str, str]]:
    """Each judged case's prompt and verdict sha256 in release 20261013's tree.

    The base commit records it in two files: release 20261010's seed digest,
    and the provenance of the cases release 20261013 re-judged over it.
    """
    rows = csv.DictReader(io.StringIO(base_blob(BASE_SEED_DIGEST).decode()))
    seed = {
        row["case_id"]: {
            "prompt_sha256": row["prompt_sha256"],
            "verdict_sha256": row["verdict_sha256"],
        }
        for row in rows
    }
    for entry in json.loads(base_blob(BASE_PROVENANCE))["verdicts"]:
        seed[entry["case_id"]] = {
            "prompt_sha256": entry["prompt_sha256"],
            "verdict_sha256": entry["verdict_sha256"],
        }
    return seed


def seed_digest_text(seed: dict[str, dict[str, str]]) -> str:
    rows = [
        f"{case},{item['prompt_sha256']},{item['verdict_sha256']}\n"
        for case, item in sorted(seed.items())
    ]
    return "case_id,prompt_sha256,verdict_sha256\n" + "".join(rows)


def stage_paths(stage: Path) -> tuple[Path, Path, Path, Path]:
    bundle = stage / "publish" / RUN
    return bundle, bundle / "us", bundle / "annotations", stage / "audit" / "cases"


def validate_stage(stage: Path) -> Path:
    stage = stage.resolve()
    require(
        (ROOT / STAGE_ROOT).resolve() in stage.parents,
        f"the stage must be under {STAGE_ROOT} in this checkout",
    )
    return stage


def tree_digests(root: Path, relative_to: Path) -> dict[str, str]:
    return {
        str(p.relative_to(relative_to)): digest(p)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def load_stage(stage: Path) -> dict:
    path = stage / "stage.json"
    require(path.is_file(), f"{path} missing: run prepare")
    record = json.loads(path.read_text())
    require(
        record.get("release_tag") == RELEASE_TAG
        and record.get("base_tag") == BASE_TAG
        and record.get("base_sha256") == BASE_SHA256
        and record.get("base_commit") == BASE_COMMIT
        and sorted(record.get("rejudge", {})) == sorted(REJUDGE),
        "stage.json does not bind this release, its base and its re-judge set",
    )
    # Every verdict set aside stays where it was put.
    for rel, pin in record.get("replaced_files", {}).items():
        target = stage / rel
        require(
            target.is_file() and digest(target) == pin,
            f"a replaced record changed: {rel}",
        )
    return record


def pin_replaced(stage: Path, record: dict) -> None:
    """Pin everything set aside so far in stage.json."""
    record["replaced_files"] = tree_digests(stage / "replaced-verdicts", stage)
    write_json(stage / "stage.json", record)


# --- Prepare ---------------------------------------------------------------------


def set_aside(case_dir: Path, destination: Path, reason: str, names) -> list[str]:
    """Move a case's judge files aside, with the reason; never delete them."""
    require(not destination.exists(), f"{destination} already exists")
    destination.mkdir(parents=True)
    moved = []
    for name in names:
        path = case_dir / name
        if path.exists():
            shutil.move(str(path), destination / name)
            moved.append(name)
    (destination / "reason.txt").write_text(reason + "\n")
    return moved


def prepare(args) -> None:
    from policybench.audit import prepare_audit
    from policybench.judge_template import template_header

    stage = validate_stage(args.stage)
    seed_dir = args.audit_seed.resolve()
    require(not stage.exists(), f"{stage} exists; prepare writes a new stage")
    require(
        stage not in seed_dir.parents and seed_dir not in stage.parents,
        "the stage overlaps the audit seed",
    )
    pointer = json.loads(base_blob(POINTER))
    require(
        pointer.get("tag") == BASE_TAG
        and pointer.get("sha256") == BASE_SHA256
        and pointer.get("bytes") == BASE_BYTES,
        "the base commit's pointer is not release 20261013",
    )
    base_payload()
    require(
        digest(args.grounding) == base_driver.GROUNDING_SHA256,
        "the grounding is not the one release 20261013's prompts were rendered with",
    )

    # The seed is release 20261013's judged tree, case for case.
    expected = base_seed()
    seed = base_driver.seed_digest(seed_dir)
    differing = sorted(
        c for c in set(seed) | set(expected) if seed.get(c) != expected.get(c)
    )
    require(
        not differing,
        f"the audit seed is not release 20261013's judged tree: {differing[:5]}",
    )
    for case, (verdict_sha, prompt_sha, _) in REJUDGE.items():
        require(
            seed[case] == {"prompt_sha256": prompt_sha, "verdict_sha256": verdict_sha},
            f"{case}: the published verdict or prompt is not the audited one",
        )
    # No decision and no exclusion rests on any of the five.
    record = json.loads(base_blob(ANNOTATIONS / ADJUDICATIONS))
    decided = {(d["scenario_id"], d["variable"]) for d in record["adjudications"]}
    excluded = {
        (e["scenario_id"], e["variable"])
        for e in json.loads(base_blob(SNAPSHOT_RUN / EXCLUSIONS))["exclusions"]
    }
    amended = {
        case_key(a["case_id"])
        for a in json.loads(base_blob(ANNOTATIONS / AMENDMENTS))["amendments"]
    }
    for name, keys in (
        ("a decision", decided),
        ("an exclusion", excluded),
        ("a wording amendment", amended),
    ):
        require(
            not keys & REJUDGE_KEYS,
            f"a re-judged case has {name}: {sorted(keys & REJUDGE_KEYS)}",
        )

    stage.mkdir(parents=True)
    bundle, us, annotations, cases = stage_paths(stage)
    us.mkdir(parents=True)
    annotations.mkdir()
    for name in (*REFERENCE_FILES, EXCLUSIONS):
        (us / name).write_bytes(base_blob(SNAPSHOT_RUN / name))
    (us / "predictions.csv").write_bytes(
        gzip.decompress(base_blob(SNAPSHOT_RUN / "predictions.csv.gz"))
    )
    for name in STAGED_ANNOTATIONS:
        (annotations / name).write_bytes(base_blob(ANNOTATIONS / name))
    cases.parent.mkdir()
    subprocess.run(["cp", "-cRp", str(seed_dir / "cases"), str(cases)], check=True)
    carried = {
        f"{p.parent.name}/{p.name}": digest(p)
        for p in sorted(cases.glob("*/*"))
        if p.name in AUDIT_FILES and p.parent.name not in REJUDGE
    }

    v1, v2 = template_header(1), template_header(JUDGE_TEMPLATE_VERSION)
    bodies = {}
    for case, (_, _, reason) in REJUDGE.items():
        prompt = (cases / case / "prompt.md").read_text(encoding="utf-8")
        require(prompt.startswith(v1), f"{case}: its prompt is not on template v1")
        bodies[case] = prompt[len(v1) :]
        moved = set_aside(
            cases / case,
            stage / "replaced-verdicts" / case / "published",
            reason,
            (*JUDGE_FILES, "prompt.md"),
        )
        require(
            {"verdict.json", "verdict.meta.json", "prompt.md"} <= set(moved),
            f"{case}: the published verdict, sidecar or prompt is missing",
        )

    # Render the five on template v2 with the repo's own renderer. Every other
    # case must keep its verdict on its own bytes.
    prepare_audit(
        us,
        cases.parent,
        grounding_lookup=base_driver.grounding_lookup(args.grounding),
        template_version=JUDGE_TEMPLATE_VERSION,
    )
    for name in ("cases.jsonl", "schema.json"):
        require(
            (cases.parent / name).read_bytes() == (seed_dir / name).read_bytes(),
            f"the staged {name} is not release 20261013's",
        )
    now = {
        f"{p.parent.name}/{p.name}": digest(p)
        for p in sorted(cases.glob("*/*"))
        if p.name in AUDIT_FILES and p.parent.name not in REJUDGE
    }
    require(now == carried, "preparing the audit changed a carried-over case")
    require(
        sorted(p.name for p in cases.iterdir()) == sorted(seed),
        "preparing the audit added or dropped a case",
    )
    prompts = {}
    for case in REJUDGE:
        present = sorted(p.name for p in (cases / case).iterdir())
        require(present == ["prompt.md"], f"{case}: unexpected files {present}")
        rendered = (cases / case / "prompt.md").read_text(encoding="utf-8")
        # The case is the one its replaced verdict judged: only the header moved.
        require(
            rendered == v2 + bodies[case],
            f"{case}: its v2 prompt is not its v1 prompt with the v2 header",
        )
        prompts[case] = digest(cases / case / "prompt.md")

    record = {
        "release_tag": RELEASE_TAG,
        "base_tag": BASE_TAG,
        "base_commit": BASE_COMMIT,
        "base_sha256": BASE_SHA256,
        "audit_seed": str(seed_dir),
        "rejudge": prompts,
        "audit_files": carried,
        "bundle_files": tree_digests(bundle, stage),
    }
    pin_replaced(stage, record)
    print(
        f"Staged {RELEASE_TAG} in {stage}: {len(carried)} carried audit files, "
        f"{len(REJUDGE)} cases rendered on template v{JUDGE_TEMPLATE_VERSION}"
    )


# --- Judge -----------------------------------------------------------------------


def judge(args) -> None:
    """Run the isolated judge on the five, retrying what this driver rejects.

    The runner skips a case whose verdict already satisfies its own checks, so
    a verdict this driver rejects is set aside, with the reasons, before the
    next round. A round the runner ends without a new verdict stops the step:
    the login cannot judge now.
    """
    stage = validate_stage(args.stage)
    record = load_stage(stage)
    cases = stage / "audit" / "cases"
    env = {
        **os.environ,
        "AUDIT_ONLY": " ".join(sorted(REJUDGE)),
        "AUDIT_MODEL": JUDGE_MODEL,
        "AUDIT_PARALLEL": "1",
        "AUDIT_PYTHON": sys.executable,
    }
    for round_number in range(1, JUDGE_ROUNDS + 1):
        before = {c for c in REJUDGE if (cases / c / "verdict.json").is_file()}
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/run_audit_claude.sh"), str(stage / "audit")],
            env=env,
            cwd=ROOT,
            check=False,
        )
        after = {c for c in REJUDGE if (cases / c / "verdict.json").is_file()}
        failing = {c: p for c in sorted(REJUDGE) if (p := case_problems(stage, c))}
        if not failing:
            break
        require(
            after - before or result.returncode == 0,
            f"the runner stopped (exit {result.returncode}) without a new verdict; "
            "the login cannot judge now. Resume judge once it can.",
        )
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for case, problems in failing.items():
            set_aside(
                cases / case,
                stage / "replaced-verdicts" / case / f"round{round_number}-{stamp}",
                "Rejected by release_20261013b.py:\n" + "\n".join(problems),
                JUDGE_FILES,
            )
        pin_replaced(stage, record)
        print(f"round {round_number}: set aside {sorted(failing)}; judging again")
    problems = validate(stage, record)
    require(not problems, "the judge step left problems:\n" + "\n".join(problems))
    print(f"Judged {len(REJUDGE)} cases; every verdict validates")


# --- Validate --------------------------------------------------------------------


def session_problems(path: Path, session_id: object) -> list[str]:
    """Every transcript event must carry the sidecar's session id."""
    if not isinstance(session_id, str) or not session_id:
        return ["the sidecar records no session id"]
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    problems = []
    for number, line in enumerate(lines, 1):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("sessionId") != session_id:
            problems.append(f"transcript line {number} is not session {session_id}")
    return problems[:3]


def case_problems(stage: Path, case: str) -> list[str]:
    """Why a re-judged case's verdict is not publishable; [] if it is."""
    import jsonschema

    from policybench.audit import is_hedged
    from policybench.judge_template import recorded_template_version, template_header

    audit = stage / "audit"
    case_dir = audit / "cases" / case
    verdict_path = case_dir / "verdict.json"
    meta_path = case_dir / "verdict.meta.json"
    prompt_path = case_dir / "prompt.md"
    if not verdict_path.is_file() or not meta_path.is_file():
        return ["no verdict yet"]
    try:
        blob = verdict_path.read_bytes()
        verdict = json.loads(blob)
        meta = json.loads(meta_path.read_text())
        prompt = prompt_path.read_bytes()
    except (OSError, ValueError) as error:
        return [f"unreadable verdict, sidecar or prompt: {error}"]
    if not isinstance(verdict, dict) or not isinstance(meta, dict):
        return ["the verdict or its sidecar is not an object"]
    problems = []
    try:
        jsonschema.validate(verdict, json.loads((audit / "schema.json").read_text()))
    except jsonschema.ValidationError as error:
        problems.append(f"schema: {error.message}")
    manifest = {
        item["case_id"]: item
        for item in map(json.loads, (audit / "cases.jsonl").read_text().splitlines())
    }
    models = verdict.get("models") if isinstance(verdict.get("models"), list) else []
    names = [m.get("model") for m in models if isinstance(m, dict)]
    expected = manifest[case]["wrong_models"]
    if len(names) != len(set(names)) or set(names) != set(expected):
        problems.append(f"models {sorted(names)} are not exactly {sorted(expected)}")
    staged_prompt = json.loads((stage / "stage.json").read_text())["rejudge"][case]
    isolation = meta.get("judge_isolation")
    auth = meta.get("judge_auth")
    checks = {
        "the sidecar does not bind the verdict": meta.get("verdict_sha256")
        == sha(blob),
        "the prompt is not the one prepare rendered": sha(prompt) == staged_prompt,
        "the sidecar does not bind the prompt": meta.get("prompt_sha256")
        == staged_prompt,
        f"the prompt is not on template v{JUDGE_TEMPLATE_VERSION}": (
            # The prompt begins with this release's header; no version is
            # read off it (policybench.judge_template: only the tree check
            # does that).
            prompt.startswith(template_header(JUDGE_TEMPLATE_VERSION).encode("utf-8"))
            and recorded_template_version(meta) == JUDGE_TEMPLATE_VERSION
        ),
        "the verdict is the replaced one": sha(blob) != REJUDGE[case][0],
        f"the judge was not {JUDGE_MODEL}": (
            meta.get("judge_model_requested") == JUDGE_MODEL
            and meta.get("judge_model_reported") == [JUDGE_MODEL]
        ),
        "the sidecar records no judging time": bool(meta.get("judged_at_utc")),
        "the runner did not record an isolated judge": (
            meta.get("judge_runner") == "scripts/run_audit_claude.sh"
            and isinstance(isolation, dict)
            and isolation.get("transcript_tool_calls") == 0
        ),
        "the judge did not run on a token login": (
            isinstance(auth, dict) and auth.get("method") == "oauth_token"
        ),
        "the sidecar declares no account": bool(meta.get("judge_account_declared")),
    }
    problems += [message for message, ok in checks.items() if not ok]
    transcript = case_dir / "claude.transcript.jsonl"
    problems += base_driver.transcript_problems(
        transcript, meta.get("judge_effort"), prompt, verdict
    )
    problems += session_problems(transcript, meta.get("session_id"))
    texts = [verdict.get("rationale")] + [
        m.get("diagnosis") for m in models if isinstance(m, dict)
    ]
    if any(is_hedged(text) for text in texts):
        problems.append("hedged text")
    return problems


def validate(stage: Path, record: dict) -> list[str]:
    """Every carried-over case unchanged; every re-judge isolated and complete."""
    problems = []
    cases = stage / "audit" / "cases"
    for rel, pin in record["audit_files"].items():
        path = cases / rel
        if not path.is_file() or digest(path) != pin:
            problems.append(f"carried-over {rel} changed or is missing")
    present = {
        f"{p.parent.name}/{p.name}"
        for p in cases.glob("*/*")
        if p.name in AUDIT_FILES and p.parent.name not in REJUDGE
    }
    extra = sorted(present - set(record["audit_files"]))
    problems += [f"unexpected audit file {rel}" for rel in extra]
    known = {rel.split("/", 1)[0] for rel in record["audit_files"]} | set(REJUDGE)
    problems += [
        f"unexpected case {p.name}" for p in cases.iterdir() if p.name not in known
    ]
    for case in sorted(REJUDGE):
        problems += [f"{case}: {p}" for p in case_problems(stage, case)]
    return problems


# --- Annotations -----------------------------------------------------------------


def csv_records(text: str) -> tuple[str, list[str]]:
    """Split CSV text into its header and whole records, each with its newline.

    Lines end only at CR or LF (not at the Unicode separators str.splitlines
    also breaks on). A record ends at a line end outside quotes; quotes inside
    a field are doubled, so a record is complete when its quote count is even.
    """
    lines = io.StringIO(text, newline="").readlines()
    require(bool(lines), "empty CSV")
    records, buffer = [], ""
    for line in lines[1:]:
        buffer += line
        if buffer.count('"') % 2 == 0:
            records.append(buffer)
            buffer = ""
    require(buffer == "", "CSV ends inside a quoted field")
    return lines[0], records


def record_fields(header: str, record: str) -> dict[str, str]:
    names = next(csv.reader(io.StringIO(header, newline="")))
    values = next(csv.reader(io.StringIO(record, newline="")))
    require(
        len(names) == len(values),
        f"a record has {len(values)} fields, not {len(names)}",
    )
    return dict(zip(names, values))


def record_key(fields: dict[str, str], key: list[str]) -> tuple[str, ...]:
    return tuple(fields[k] for k in key)


def splice_annotations(base_text: str, new_rows, key: list[str]) -> str:
    """The base's CSV with only the five cases' records replaced.

    ``new_rows`` holds every record of the five cases, as collected from the
    new verdicts. Each goes where the record it replaces was, so the file
    keeps its order; every other record keeps its exact bytes.
    """
    header, records = csv_records(base_text)
    columns = next(csv.reader(io.StringIO(header, newline="")))
    require(
        sorted(new_rows.columns) == sorted(columns),
        "the collected columns differ from the base CSV's",
    )
    newline = "\r\n" if header.endswith("\r\n") else "\n"
    serialized = new_rows[columns].to_csv(
        index=False, header=False, lineterminator=newline
    )
    _, fresh = csv_records(header + serialized)
    replacement = {record_key(record_fields(header, r), key): r for r in fresh}
    require(len(replacement) == len(fresh), "the collected rows repeat a key")
    out, used = [header], set()
    for record in records:
        fields = record_fields(header, record)
        if (fields["scenario_id"], fields["variable"]) in REJUDGE_KEYS:
            k = record_key(fields, key)
            require(k in replacement, f"the collected rows drop {k}")
            out.append(replacement[k])
            used.add(k)
        else:
            out.append(record)
    unused = sorted(set(replacement) - used)
    require(not unused, f"the collected rows add {unused}")
    return "".join(out)


def annotation_changes(base_text: str, text: str, name: str) -> list[dict]:
    """Every changed record of one annotation CSV; refuses a change beyond the five.

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


def verify_annotations(
    annotations: Path, names, expected_changes: dict | None = None
) -> dict:
    """The directory holds exactly ``names``, each release 20261013's but for
    the five cases' records in the two annotation CSVs."""
    present = sorted(p.name for p in annotations.iterdir() if p.is_file())
    require(present == sorted(names), f"{annotations} holds {present}")
    changes = {}
    for name in present:
        current = (annotations / name).read_bytes()
        base = base_blob(ANNOTATIONS / name)
        if name in ANNOTATION_CSVS:
            changes[name] = annotation_changes(base.decode(), current.decode(), name)
        elif name == AMENDMENTS:
            require(
                current == committed_amendments(),
                f"{name} is not release 20261013's with this release's appended",
            )
        else:
            require(current == base, f"{name} differs from release 20261013's")
    if expected_changes is not None:
        require(
            changes == expected_changes,
            "the annotation changes differ from annotation-changes.json",
        )
    return changes


# --- Wording amendments ----------------------------------------------------------

AMENDED_FIELDS = {"annotation": ROWS, "case_annotation": NOTES}
AMENDMENT_KEYS = {
    "annotation": {"case_id", "field", "model", "old", "new", "reason"},
    "case_annotation": {"case_id", "field", "old", "new", "reason"},
}


def load_amendments() -> list[dict]:
    """The listed wording amendments, each checked for form.

    An amendment replaces text a new verdict wrote, in one of the five cases:
    a model row's ``annotation`` (it names the ``model``) or the case note
    (``case_annotation``). It cannot touch a class, a flag or another case.
    """
    path = ROOT / WORDING
    if not path.is_file():
        return []
    listed = json.loads(path.read_text())
    require(
        isinstance(listed, dict) and set(listed) == {"note", "amendments"},
        f"{WORDING} must hold a note and a list of amendments",
    )
    amendments = listed["amendments"]
    for item in amendments:
        field = item.get("field") if isinstance(item, dict) else None
        require(field in AMENDED_FIELDS, f"an amendment names field {field!r}")
        require(
            set(item) == AMENDMENT_KEYS[field],
            f"an amendment has keys {sorted(item)}",
        )
        require(
            item["case_id"] in REJUDGE,
            f"an amendment names {item['case_id']}, which was not re-judged",
        )
        require(
            all(isinstance(item[k], str) and item[k].strip() for k in item)
            and item["old"] != item["new"],
            f"an amendment of {item['case_id']} has an empty or unchanged text",
        )
    return amendments


def apply_amendments(rows, notes, amendments: list[dict]) -> None:
    """Apply each amendment in order; its old text must occur exactly once."""
    for item in amendments:
        scenario, variable = case_key(item["case_id"])
        field = item["field"]
        frame = rows if field == "annotation" else notes
        mask = (frame.scenario_id == scenario) & (frame.variable == variable)
        label = item["case_id"]
        if field == "annotation":
            mask &= frame.model == item["model"]
            label += f" {item['model']}"
        require(int(mask.sum()) == 1, f"an amendment names no single record: {label}")
        index = frame.index[mask][0]
        text = str(frame.at[index, field])
        require(
            text.count(item["old"]) == 1,
            f"{label}: the amended text occurs {text.count(item['old'])} times",
        )
        frame.at[index, field] = text.replace(item["old"], item["new"])


def committed_amendments() -> bytes:
    """The wording-amendments record this release commits.

    Release 20261013's record is never replaced: its wording is still
    published. This release's amendments are appended after it, in their own
    order, and the note says which they are.
    """
    base = base_blob(ANNOTATIONS / AMENDMENTS)
    added = load_amendments()
    if not added:
        return base
    record = json.loads(base)
    require(
        json.dumps(record, indent=1, ensure_ascii=False).encode() == base
        and list(record) == ["note", "amendments"],
        f"release 20261013's {AMENDMENTS} is not in its committed form",
    )
    listed_note = json.loads((ROOT / WORDING).read_text())["note"].strip()
    note = (
        f"{record['note']} The last {len(added)} (after the first "
        f"{len(record['amendments'])}) are for the five cases release "
        "dashboard-data-20261013b re-judged (scripts/release_20261013b.py "
        f"load_amendments). {listed_note}"
    )
    merged = {"note": note, "amendments": record["amendments"] + added}
    return json.dumps(merged, indent=1, ensure_ascii=False).encode()


# --- Collect ---------------------------------------------------------------------


def provenance_record(cases: Path) -> dict:
    """The published record of how each of the five verdicts was judged, in
    the form of release 20261013's (docs/musewonder/judge_provenance.json)."""
    entries = []
    for case in sorted(REJUDGE):
        meta = json.loads((cases / case / "verdict.meta.json").read_text())
        declared = meta.get("judge_account_declared")
        require(
            declared in base_driver.PROVENANCE_GROUPS,
            f"{case}: no provenance group for the declared account",
        )
        entries.append(
            {
                "case_id": case,
                "group": base_driver.PROVENANCE_GROUPS[declared],
                "isolated": True,
                **{
                    field: base_driver.withhold_addresses(meta.get(field))
                    for field in base_driver.JUDGE_SIDECAR_FIELDS
                },
                "verdict_sha256": digest(cases / case / "verdict.json"),
                "prompt_sha256": digest(cases / case / "prompt.md"),
            }
        )
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["group"]] = counts.get(entry["group"], 0) + 1
    return {"note": PROVENANCE_NOTE, "counts": counts, "verdicts": entries}


def verify_provenance(cases: Path) -> None:
    """The committed provenance record describes the staged five verdicts."""
    path = ROOT / PROVENANCE
    require(path.is_file(), f"{PROVENANCE} missing: run collect")
    base_driver.verify_judge_provenance(cases, frozenset(REJUDGE), path)
    require(
        json.loads(path.read_text())["note"] == PROVENANCE_NOTE,
        f"{PROVENANCE}'s note is not this release's",
    )


MODEL_ERROR_SOURCES = (
    "llm_error",
    "parse_contract_failure",
    "budget_exhausted_at_ceiling",
)


def reference_questions(rows, notes, excluded):
    """The case notes that flag the reference, and the scored rows a verdict
    leaves outside the model-error classes. Either is a reference question
    for Max, which this release does not decide."""
    flags = notes[notes.reference_suspect.astype(bool)]
    scored = ~rows[KEY].apply(tuple, axis=1).isin(excluded)
    unresolved = rows[scored & ~rows.failure_source.isin(MODEL_ERROR_SOURCES)]
    return flags, unresolved


def collect(args) -> None:
    """Collect the new verdicts and splice the five cases into the base files."""
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
    stage = validate_stage(args.stage)
    record = load_stage(stage)
    problems = validate(stage, record)
    require(not problems, "verdicts do not validate:\n" + "\n".join(problems))
    bundle, us, annotations, cases = stage_paths(stage)
    # Staged files may differ from the base only in the five cases' records, so
    # a collect that stopped before writing, or a finished one, can run again.
    verify_annotations(annotations, STAGED_ANNOTATIONS)
    decisions = load_adjudications(annotations / ADJUDICATIONS)

    out = collect_audit(us, stage / "audit")
    for name in ("missing", "hedged", "template", "prompt_hash"):
        require(out[name].empty, f"the audit has {name} cases: {out[name]}")
    rows = out["row"]
    notes = out["case"].rename(
        columns={
            "case_failure_source": "case_failure_sources",
            "case_failure_subtype": "case_failure_subtypes",
        }
    )
    rows, notes, _ = apply_adjudications(rows, notes, decisions)
    verify_adjudications_applied(rows, notes, decisions)
    excluded = exclusion_keys(load_reference_exclusions(us))
    require(
        excluded == excluded_case_keys(decisions),
        "the adjudications and the frozen scoring exclusions disagree",
    )
    flags, unresolved = reference_questions(rows, notes, excluded)
    flags.to_csv(stage / "reference-flags.csv", index=False)
    unresolved.to_csv(stage / "unresolved-rows.csv", index=False)
    require(
        flags.empty and unresolved.empty,
        "a re-judge raised a reference question: see reference-flags.csv and "
        "unresolved-rows.csv. Queue it for Max (cos add-decision); do not "
        "decide it here.",
    )

    def five(frame):
        return frame[frame[KEY].apply(tuple, axis=1).isin(REJUDGE_KEYS)].copy()

    five_rows, five_notes = five(rows), five(notes)
    amendments = load_amendments()
    apply_amendments(five_rows, five_notes, amendments)
    spliced = {}
    for name, frame in ((ROWS, five_rows), (NOTES, five_notes)):
        key, _ = ANNOTATION_CSVS[name]
        base_text = base_blob(ANNOTATIONS / name).decode()
        spliced[name] = splice_annotations(base_text, frame, key)
        annotation_changes(base_text, spliced[name], name)
    # Everything is checked before anything is written; each write is atomic.
    for name, text in spliced.items():
        temporary = annotations / f".{name}.tmp"
        temporary.write_text(text, encoding="utf-8", newline="")
        os.replace(temporary, annotations / name)
    changes = verify_annotations(annotations, STAGED_ANNOTATIONS)
    write_json(stage / "annotation-changes.json", changes)

    (ROOT / DOCS).mkdir(exist_ok=True)
    record_text = json.dumps(
        json.loads(json.dumps(provenance_record(cases), sort_keys=True)),
        indent=1,
        allow_nan=False,
    )
    (ROOT / PROVENANCE).write_text(record_text + "\n")
    verify_provenance(cases)
    seed = base_driver.seed_digest(stage / "audit")
    (ROOT / SEED_DIGEST).write_text(seed_digest_text(seed))
    counts = {name: len(v) for name, v in changes.items()}
    print(
        f"Collected {RELEASE_TAG}: changed records {counts}; "
        f"{len(amendments)} wording amendments applied"
    )
    print(f"Wrote {PROVENANCE} and {SEED_DIGEST} ({len(seed)} judged cases)")


# --- Export ----------------------------------------------------------------------


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


def export_payload(bundle: Path, base: dict) -> dict:
    """export_full_run on a scratch copy of the bundle's export inputs, with
    Fable 5's usage carried from the base."""
    from policybench.dashboard_schema import validate_dashboard_payload
    from policybench.full_run_export import export_full_run

    with tempfile.TemporaryDirectory(dir=bundle.parent) as scratch:
        copy_root = Path(scratch) / RUN
        for rel in EXPORT_INPUTS:
            (copy_root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundle / rel, copy_root / rel)
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


def verify_payload(payload: dict, base: dict) -> list[tuple]:
    """The payload is release 20261013's but for the five cases' annotations."""
    require(set(payload) == set(base), "the payload's top level changed")
    now, before = payload["countries"]["us"], base["countries"]["us"]
    require(list(now) == list(before), "the payload's sections changed")
    for section in now:
        if section != "scenarioPredictions":
            require(
                json.dumps(now[section]) == json.dumps(before[section]),
                f"{section} changed",
            )
    diff = payload_diff(base, payload)
    outside = [p for p in diff if not allowed_path(p)]
    require(
        not outside,
        f"the payload changed outside the five cases' annotations: {outside[:8]}",
    )
    return diff


def export(args) -> None:
    stage = validate_stage(args.stage)
    record = load_stage(stage)
    problems = validate(stage, record)
    require(not problems, "verdicts do not validate:\n" + "\n".join(problems))
    bundle, us, annotations, cases = stage_paths(stage)
    changes_path = stage / "annotation-changes.json"
    require(changes_path.is_file(), "run collect first")
    verify_annotations(
        annotations, STAGED_ANNOTATIONS, json.loads(changes_path.read_text())
    )
    verify_provenance(cases)
    seed = base_driver.seed_digest(stage / "audit")
    require(
        (ROOT / SEED_DIGEST).read_text() == seed_digest_text(seed),
        f"{SEED_DIGEST} is not the staged tree's digest: run collect",
    )
    # The export inputs are the base commit's, but for the two annotation CSVs.
    for name in (*REFERENCE_FILES, EXCLUSIONS):
        require(
            (us / name).read_bytes() == base_blob(SNAPSHOT_RUN / name),
            f"the staged {name} is not release 20261013's",
        )
    require(
        digest(us / "predictions.csv")
        == record["bundle_files"][str((us / "predictions.csv").relative_to(stage))],
        "the staged predictions changed since prepare",
    )

    base = base_payload()
    payload = export_payload(bundle, base)
    text = payload_text(payload)
    require(
        text == payload_text(export_payload(bundle, base)),
        "two exports of the same stage disagree",
    )
    diff = verify_payload(payload, base)
    touched = sorted({(p[3], p[4]) for p in diff})
    write_json(
        stage / "payload-diff.json",
        {"paths": [list(p) for p in diff], "cases": [list(t) for t in touched]},
    )
    path = stage / f"data-board{BOARD_MODELS}.json"
    path.write_text(text)
    shutil.copyfile(path, bundle / "data.json")
    files = [bundle / rel for rel in EXPORT_INPUTS] + [annotations / ADJUDICATIONS]
    files += [stage / "stage.json", changes_path, stage / "payload-diff.json"]
    files += [
        cases / case / name
        for case in sorted(REJUDGE)
        for name in (*AUDIT_FILES, "claude.transcript.jsonl")
    ]
    files += [
        p for p in sorted((stage / "replaced-verdicts").rglob("*")) if p.is_file()
    ]
    data = text.encode()
    write_json(
        stage / "release-ready.json",
        {
            "release_tag": RELEASE_TAG,
            "base_tag": BASE_TAG,
            "base_commit": BASE_COMMIT,
            "base_sha256": BASE_SHA256,
            "payload_sha256": sha(data),
            "payload_bytes": len(data),
            "models": BOARD_MODELS,
            "provenance_sha256": digest(ROOT / PROVENANCE),
            "seed_digest_sha256": digest(ROOT / SEED_DIGEST),
            "amendments_sha256": sha(committed_amendments()),
            "files": {str(p.relative_to(stage)): digest(p) for p in files},
        },
    )
    print(
        f"Exported {RELEASE_TAG}: {sha(data)} ({len(data)} bytes); every section "
        f"but scenarioPredictions is release 20261013's; {len(diff)} annotation "
        f"fields changed in {len(touched)} cases"
    )


# --- Freeze ----------------------------------------------------------------------


def manifest_problems(before: dict, after: dict) -> list[tuple]:
    """Manifest paths that changed outside MANIFEST_CHANGES."""
    return [
        path
        for path in payload_diff(before, after)
        if not any(path[: len(prefix)] == prefix for prefix in MANIFEST_CHANGES)
    ]


def verify_receipt(stage: Path) -> dict:
    """The receipt binds this release, its base and every input, unchanged."""
    receipt = json.loads((stage / "release-ready.json").read_text())
    require(
        (ROOT / PROVENANCE).is_file() and (ROOT / SEED_DIGEST).is_file(),
        f"{PROVENANCE} or {SEED_DIGEST} is missing: run collect",
    )
    require(
        receipt.get("release_tag") == RELEASE_TAG
        and receipt.get("base_tag") == BASE_TAG
        and receipt.get("base_sha256") == BASE_SHA256
        and receipt.get("base_commit") == BASE_COMMIT
        and receipt.get("models") == BOARD_MODELS
        and receipt.get("provenance_sha256") == digest(ROOT / PROVENANCE)
        and receipt.get("seed_digest_sha256") == digest(ROOT / SEED_DIGEST)
        and receipt.get("amendments_sha256") == sha(committed_amendments()),
        "the receipt does not bind this release, its base, the judge provenance, "
        "the seed digest and the wording amendments",
    )
    payload = stage / f"data-board{BOARD_MODELS}.json"
    require(
        digest(payload) == receipt.get("payload_sha256"),
        "the payload changed after export",
    )
    for rel, pin in receipt["files"].items():
        path = (stage / rel).resolve()
        require(path.is_relative_to(stage), f"the receipt names a path outside: {rel}")
        require(path.is_file() and digest(path) == pin, f"{rel} changed after export")
    # Every verdict set aside is bound too; stage.json, pinned just above when
    # the receipt binds it, lists them.
    replaced = (
        json.loads((stage / "stage.json").read_text()).get("replaced_files", {})
        if "stage.json" in receipt["files"]
        else {}
    )
    bundle = f"publish/{RUN}"
    needed = {
        *replaced,
        "stage.json",
        "annotation-changes.json",
        "payload-diff.json",
        f"{bundle}/annotations/{ADJUDICATIONS}",
        *(f"{bundle}/{rel}" for rel in EXPORT_INPUTS),
        *(
            f"audit/cases/{case}/{name}"
            for case in REJUDGE
            for name in (*AUDIT_FILES, "claude.transcript.jsonl")
        ),
    }
    missing = sorted(needed - set(receipt["files"]))
    require(not missing, f"the receipt does not bind {missing[:5]}")
    return receipt


def verify_base_working_tree() -> list[str]:
    """The working tree is release 20261013 in every file the freeze reads or
    writes, and its annotations directory holds exactly the committed files.
    Returns the committed annotation file names."""
    committed = base_annotation_names()
    require(
        committed == sorted((*STAGED_ANNOTATIONS, AMENDMENTS)),
        f"release 20261013 commits annotation files {committed}",
    )
    present = sorted(p.name for p in (ROOT / ANNOTATIONS).iterdir())
    require(present == committed, f"the working tree's annotations are {present}")
    for rel in (
        MANIFEST,
        SERVING,
        POINTER,
        VERSIONS,
        *(ANNOTATIONS / name for name in committed),
        *(SNAPSHOT_RUN / name for name in FROZEN_UNCHANGED),
    ):
        path = ROOT / rel
        require(
            path.is_file() and path.read_bytes() == base_blob(rel),
            f"the working tree's {rel} is not release 20261013's",
        )
    return committed


def freeze(args) -> None:
    stage = validate_stage(args.stage)
    record = load_stage(stage)
    problems = validate(stage, record)
    require(not problems, "verdicts do not validate:\n" + "\n".join(problems))
    receipt = verify_receipt(stage)
    bundle, us, annotations, cases = stage_paths(stage)
    payload_path = stage / f"data-board{BOARD_MODELS}.json"
    changes = json.loads((stage / "annotation-changes.json").read_text())
    verify_annotations(annotations, STAGED_ANNOTATIONS, changes)
    verify_provenance(cases)

    import freeze_snapshot as freezer
    import pandas as pd

    if hasattr(pd.options, "future") and hasattr(pd.options.future, "infer_string"):
        pd.options.future.infer_string = False

    from policybench.adjudications import (
        load_adjudications,
        verify_adjudications_applied,
    )

    committed = verify_base_working_tree()
    base_manifest = json.loads(base_blob(MANIFEST))
    base_serving = base_blob(SERVING)
    window = freezer.model_response_window(
        us / "predictions.csv", freezer.MODEL_RESPONSE_START, None
    )
    require(
        window == base_manifest["model_response_date"],
        f"the response window {window} is not release 20261013's",
    )
    decisions = load_adjudications(annotations / ADJUDICATIONS)
    verify_adjudications_applied(
        pd.read_csv(annotations / ROWS), pd.read_csv(annotations / NOTES), decisions
    )
    freezer.verify_adjudications_keep_judge_verdicts(decisions, cases)
    pointer = {
        "asset": "dashboard-data.json",
        "bytes": payload_path.stat().st_size,
        "repo": "PolicyEngine/policybench",
        "sha256": receipt["payload_sha256"],
        "tag": RELEASE_TAG,
        "url": (
            "https://github.com/PolicyEngine/policybench/releases/download/"
            f"{RELEASE_TAG}/dashboard-data.json"
        ),
        "version": 1,
    }
    if args.dry_run:
        print(
            f"Validated {RELEASE_TAG}: payload {receipt['payload_sha256']}, window "
            f"{window}; references, predictions, exclusions, adjudications, serving "
            "configuration and working tree are release 20261013's; nothing written"
        )
        return

    freezer.SNAPSHOT_DATE = base_manifest["snapshot_date"]
    freezer.MODEL_RESPONSE_DATE = None
    freezer.SOURCE_RUN = bundle
    freezer.SOURCE_US = us
    freezer.SOURCE_ANNOTATIONS = annotations
    freezer.REFERENCE_META_SOURCE = us / "reference_outputs.csv.meta.json"
    freezer.REFERENCE_PINS = None
    freezer.PUBLISHED_DASHBOARD_SOURCE = payload_path
    freezer.PUBLISHED_DASHBOARD_ARTIFACT = {
        key: pointer[key] for key in ("tag", "asset", "url", "sha256", "bytes")
    }
    freezer.RUN_STATE_EVIDENCE = {}
    freezer.AUDIT_CASES_DIR = cases
    freezer.audit_judge_provenance = functools.partial(
        freezer.audit_judge_provenance, cases_dir=cases
    )
    freezer.developer_adjudications_block = functools.partial(
        freezer.developer_adjudications_block, cases_dir=cases
    )

    def freeze_serving(destination: Path) -> None:
        # No model changed, so every row keeps release 20261013's evidence.
        destination.write_bytes(base_serving)

    freezer.freeze_serving_configuration = freeze_serving
    write_json(ROOT / POINTER, pointer)
    freezer.main()

    # freeze_snapshot rebuilds the annotations directory from the stage; the
    # wording-amendments record is committed beside it, release 20261013's
    # with this release's amendments appended.
    (ROOT / ANNOTATIONS / AMENDMENTS).write_bytes(committed_amendments())
    verify_annotations(ROOT / ANNOTATIONS, committed, changes)
    for name in STAGED_ANNOTATIONS:
        require(
            (ROOT / ANNOTATIONS / name).read_bytes()
            == (annotations / name).read_bytes(),
            f"the frozen {name} is not the staged one",
        )
    for rel in (SERVING, VERSIONS, *(SNAPSHOT_RUN / n for n in FROZEN_UNCHANGED)):
        require(
            (ROOT / rel).read_bytes() == base_blob(rel),
            f"the frozen {rel} is not release 20261013's",
        )
    require(
        json.loads((ROOT / POINTER).read_text()) == pointer,
        f"the frozen {POINTER} is not the pointer this release wrote",
    )
    manifest = json.loads((ROOT / MANIFEST).read_text())
    changed = manifest_problems(base_manifest, manifest)
    require(not changed, f"the manifest changed outside the release: {changed[:8]}")
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
        asset.read_bytes() == base_blob(SNAPSHOT_RUN / "predictions.csv.gz"),
        "the predictions asset is not release 20261013's",
    )
    print(f"Froze {RELEASE_TAG} locally: payload {receipt['payload_sha256']}")
    print(
        "Next: the tests that pin the tag and the judge provenance, the paper "
        "render, freeze_snapshot.py --rendered-only, then the release upload. The "
        "release adds no note: it changes no model, reference, exclusion or score."
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="step", required=True)
    step = sub.add_parser("prepare")
    step.add_argument("--audit-seed", type=Path, required=True)
    step.add_argument("--grounding", type=Path, required=True)
    step.add_argument("--stage", type=Path, required=True)
    for name in ("judge", "collect", "export"):
        sub.add_parser(name).add_argument("--stage", type=Path, required=True)
    step = sub.add_parser("freeze")
    step.add_argument("--stage", type=Path, required=True)
    step.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    steps = {
        "prepare": prepare,
        "judge": judge,
        "collect": collect,
        "export": export,
        "freeze": freeze,
    }
    steps[args.step](args)


if __name__ == "__main__":
    main()
