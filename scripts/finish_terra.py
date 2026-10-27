"""Stage GPT-6.1 Terra and the reviewed October 22 reference build.

Argon's release gates and seed binding remain in force. Muse Wonder's
installation gates validate the committed build and re-open changed prompts.
All release data stays in the scratch stage until the lead runs the freeze.
See docs/terra/design.md for the command sequence.
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

os.environ["OPENBLAS_NUM_THREADS"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RUN_NAME = "us_full_run_20260612_policyengine_4_16_1_populace"
SNAPSHOT = ROOT / "paper/snapshot/20260501/runs" / RUN_NAME
ANNOTATIONS = ROOT / "annotations" / RUN_NAME
BASE_TAG = "dashboard-data-20261014"
# The one place the new release's tag is named. The lead may change it at
# freeze time; freeze_terra.py and the design note read it from here.
RELEASE_TAG = "dashboard-data-20261027"
# Release 20261014's payload, published by PR #221 on 2026-10-14.
BASE_SHA256 = "22db9a9c052545371687f6afa3551896336abbd15c76f767ebb777a77f6d2268"
BASE_MODELS = 50
BASE_OUTPUTS = 1984
BASE_EXCLUSIONS = 49
BASE_SCORED = BASE_OUTPUTS - BASE_EXCLUSIONS
# Ruled exclusions, installed by --step install-exclusions and adjudicated by
# --step adjudicate-exclusions, as docs/terra/spec.json lists them. This
# release rules none: Max ruled d1252 (VA 039, OH 025) and d1263 (the Tax
# Table) on 2026-10-13, both to keep, so nothing scored changes on their points.
SPEC_PATH = Path("docs/terra/spec.json")
NEW_EXCLUSIONS = 0
RELEASE_EXCLUSIONS = BASE_EXCLUSIONS + NEW_EXCLUSIONS
RELEASE_SCORED = BASE_OUTPUTS - RELEASE_EXCLUSIONS
MODELS = {"terra": "gpt-6.1-terra"}
BOARD_MODELS = BASE_MODELS + len(MODELS)
REFERENCE_FILES = (
    "reference_outputs.csv",
    "reference_outputs.csv.meta.json",
    "reference_exclusions.json",
    "scenarios.csv",
    "scenarios.csv.meta.json",
)
ANNOTATION_FILES = (
    "us_audit_row_annotations.csv",
    "us_case_notes.csv",
    "us_case_reference_explanations.csv",
    "us_adjudications.json",
)
JUDGE_MODEL = "claude-opus-5-5"
# The runner the judge step runs, as it names itself in each verdict's sidecar
# (judge_runner). Every verdict this release judges must have been written by it.
JUDGE_RUNNER = "scripts/run_audit_claude.sh"
# The judge template (policybench.judge_template) this driver renders new
# and re-opened cases on: v2, which drops v1's claim that the reference
# pipeline survived an adversarial review with its real bugs fixed (#210). A
# seed case keeps the version its sidecar records (v1 for the cases judged
# before template v2 was introduced), so the stage's audit mixes versions.
JUDGE_TEMPLATE_VERSION = 2
ADJUDICATIONS = "us_adjudications.json"
# Stage files export binds: the cases a new model re-opened, and the
# wording-only amendments a developer lists for them.
PROMPT_CHANGES = "prompt-changes.json"
AMENDMENTS = "wording-amendments.json"
# The published record of how each new verdict (a case a new model re-opened)
# was judged. Export requires it to describe the staged verdicts and binds its
# bytes in the receipt.
JUDGE_PROVENANCE_PATH = "docs/terra/judge_provenance.json"
JUDGE_PROVENANCE = ROOT / JUDGE_PROVENANCE_PATH
# Repository data read by the freeze outside the staged bundle. Scoring's two
# immutable data files are checked against BASE_COMMIT by the consuming gate.
REPOSITORY_INPUT_FILES = (
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("reference_audit/2026-10-22-engine-upgrade/verification/sweep_timing.json"),
    Path("paper/snapshot/20260501/manifest.json"),
    Path("app/src/data.versions.json"),
)
BASE_REPOSITORY_INPUT_FILES = (
    Path("policybench/benchmark_specs.json"),
    Path("policybench/population_weights.json"),
)


def repository_input_hashes(root: Path | None = None) -> dict[str, str | None]:
    """Bind every mutable repository data input, including paper inventory.

    The optional rendered paper can be absent when the shared freezer falls
    back to the existing manifest. Bind absence too, so an added PDF or web
    file cannot change that choice after export.
    """
    root = ROOT if root is None else root
    for path in REPOSITORY_INPUT_FILES:
        require((root / path).is_file(), f"Repository input is missing: {path}")
    files = {str(path): digest(root / path) for path in REPOSITORY_INPUT_FILES}
    paper = Path("app/public/paper")
    pdf = paper / "policybench.pdf"
    files[str(pdf)] = digest(root / pdf) if (root / pdf).is_file() else None
    web = root / paper / "web"
    files[str(paper / "web") + "/"] = "directory" if web.is_dir() else None
    files.update(
        {
            str(path.relative_to(root)): digest(path)
            for path in sorted(web.rglob("*"))
            if path.is_file()
        }
    )
    return files


# The record's keys, and each entry's: every one is checked, against the
# case's verdict, prompt or sidecar, the entries' tally, or the isolated flag.
JUDGE_PROVENANCE_KEYS = frozenset({"note", "counts", "verdicts"})
JUDGE_PROVENANCE_ENTRY_KEYS = frozenset(
    {
        "case_id",
        "group",
        "isolated",
        "judge_account_declared",
        "judge_effort",
        "judge_model_reported",
        "judged_at_utc",
        "judge_template_version",
        "prompt_sha256",
        "verdict_sha256",
    }
)
# The entry fields copied from the verdict's sidecar, an e-mail address in any
# of them withheld as WITHHELD_ADDRESS: the record is public.
JUDGE_SIDECAR_FIELDS = (
    "judge_effort",
    "judge_model_reported",
    "judged_at_utc",
    "judge_account_declared",
    "judge_template_version",
)
WITHHELD_ADDRESS = "<account withheld>"
# The context attachments an isolated judge's transcript may carry: ATTACHMENTS
# in scripts/run_audit_claude.sh, which a test keeps equal to this set.
JUDGE_ATTACHMENTS = frozenset(
    {
        "environment",
        "model",
        "date",
        "session_context",
        "total_tokens_reminder",
        "prompt_snapshot",
        "structured_output",
        "silent_turn_reminder",
    }
)
# The event types an isolated judge's transcript may carry, the types the
# stage's 60 isolated transcripts carry: EVENT_TYPES in
# scripts/run_audit_claude.sh, which a test keeps equal to this set.
JUDGE_EVENT_TYPES = frozenset(
    {
        "queue-operation",
        "user",
        "attachment",
        "atis-latch",
        "last-prompt",
        "assistant",
        "cost-state",
    }
)
# Account data an isolated judge's transcript may not carry outside the judged
# prompt's own user message and the judge's own words: an e-mail address in any
# key or string, or a key that names an account, at any depth. The runner's
# extract_verdict uses the same two patterns.
ACCOUNT_KEY = re.compile(r"email|account|credential|organi[sz]ation|gitstatus", re.I)
EMAIL_ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Claude Code's own nudge to a judge that answered in text, the one user text
# message an isolated judge's transcript may carry besides its prompt:
# PROMPT_NUDGE in scripts/run_audit_claude.sh, which a test keeps equal to this.
JUDGE_PROMPT_NUDGE = (
    "[structured-output-enforce] You MUST call the StructuredOutput tool to "
    "complete this request. Call this tool now."
)
# PR #221's squash merge, whose tree holds release 20261014. Main's run
# directory, annotations and held-reference records at e0217ede are equal
# to this commit's bytes.
BASE_COMMIT = "bf845cbe4e92de495150c8660c35ea357d996a8c"
# Release 20261014's references (policyengine-us 2.41.0). Prepare first
# stages these base files and audit; installing the reviewed build then
# replaces the three reference files and re-opens changed prompts.
BASE_REFERENCE_SHA256 = {
    "reference_outputs.csv": (
        "2d00cf595adf183fcfa3d069756723b5ce09bd4123fbf3e673635474346b3a0c"
    ),
    "reference_outputs.csv.meta.json": (
        "0dc1ba15a11a20d9a3915a4537a33127e5406b5fde4797586d39ce5dbf170915"
    ),
    "reference_exclusions.json": (
        "a2ddf91634ed66124d13105a09badea39ec6b5f11863011fa51f9ca17f8f3939"
    ),
    "scenarios.csv": (
        "71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a"
    ),
    "scenarios.csv.meta.json": (
        "03a66e90b86e9bd0cc77f27520784bd581777762f749675dc716e24c1b8eaebb"
    ),
}
# The grounding the 20260929 stage (adds0928-v3) rendered into its prompts, and
# every stage after it through release 20261014's:
# results/local/unified_audit/grounding.csv in the main clone. Every seed
# prompt re-renders byte-identically from it and the committed snapshot, so a
# different grounding would silently invalidate carried-over verdicts.
GROUNDING_SHA256 = "b1e4a9bc74d762f410524a147efcda7d705c3afcfa3dc27f720fa60c54a7b55c"
# The seed: every judged case of release 20261014's audit, with the sha256 of
# its prompt and of its verdict, committed at docs/terra/seed_digest.csv:
# 678 cases in the Argon release's retained stage2/audit tree. That release
# judged 196 new or re-opened cases on template v2.
# This pins that file's bytes; prepare refuses any other seed and binds this
# one in stage.json, and a carried-over verdict must keep the seed's bytes.
SEED_DIGEST = ROOT / "docs/terra/seed_digest.csv"
# Derived from the retained release audit, as its parent README records.
SEED_DIGEST_SHA256 = "e80285307cb1030ab656fd18eac50437b6f42912a1655a55a9f2f1dad7dd07ed"
# Each new model's supervised run as it finished, pinned outside the stage: the
# sha256 of the run directory's predictions.csv and run_state.json, which
# --step pin-inputs writes here. Export and the freeze read the file as
# committed at HEAD, and the stage's inputs/<slug>/ copies must be those bytes.
INPUT_PINS_PATH = "docs/terra/input_pins.json"
INPUT_PINS = ROOT / INPUT_PINS_PATH
PINNED_INPUTS = ("predictions.csv", "run_state.json")
# Incumbent usage the exporter cannot recompute from committed predictions:
# Fable 5's board rows were rebuilt from release 20260701 without their cost,
# token and latency fields (its original per-call rows are that release's
# claude-fable-5-predictions.csv.gz), so export_full_run reports none of its
# usage.
# The released values are carried over; the drift gate then checks every field.
CARRIED_USAGE = {
    "claude-fable-5": ("costUsd", "costPerHousehold", "totalTokens", "latencySeconds")
}
KEY = ["scenario_id", "variable"]
# The tree whose committed annotations render every seed prompt: release
# 20261014's own (PR #221's merge). Every judged case re-renders from it on
# the template version its sidecar records (tests/test_judge_template.py's
# committed-prompt invariant), so this is BASE_COMMIT.
SEED_RELEASE_COMMIT = BASE_COMMIT
REFERENCE_EXPLANATIONS = (
    Path("annotations") / RUN_NAME / "us_case_reference_explanations.csv"
)
# The cases whose reference explanation changed between the seed's rendering
# and the base. Both are release 20261014, so none: reworded_since_seed()
# derives the set from git and must find it empty.
REWORDED_SINCE_SEED: frozenset[str] = frozenset()


def require(condition: bool, message: str) -> None:
    """Fail before an unsafe or incomplete stage can proceed."""
    if not condition:
        raise SystemExit(message)


def digest(path: Path) -> str:
    """Hash a file without retaining its contents in memory."""
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path: Path, value: object) -> None:
    """Write a deterministic, finite JSON artifact."""
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def verify_reference_pins(
    directory: Path,
    label: str,
    exclusions_sha256: str | None = None,
    pins: dict[str, str] | None = None,
) -> None:
    """Every reference file in ``directory`` must equal its 20261014 pin; the
    exclusion record may instead be the release's (``exclusions_sha256``).

    ``pins`` replaces the 20261014 pins outright: an installed engine upgrade
    names its build's hashes (upgraded_reference_pins)."""
    for name, pin in (BASE_REFERENCE_SHA256 if pins is None else pins).items():
        if name == "reference_exclusions.json" and exclusions_sha256 is not None:
            pin = exclusions_sha256
        path = directory / name
        require(
            path.is_file() and digest(path) == pin,
            f"{label} {name} does not match its pin; "
            + (
                "this release revises no reference value"
                if pins is None
                else "it is not the installed engine upgrade's build"
            ),
        )


@dataclass(frozen=True)
class NewRun:
    slug: str
    model: str
    run_dir: Path
    predictions: Path
    state: dict


def discover_new_models(runs_root: Path) -> list[NewRun]:
    """Require every named run to be completed and unstopped, as before."""
    found = []
    skipped = []
    for slug, expected in MODELS.items():
        directory = runs_root / slug / "run"
        state_path = directory / "run_state.json"
        if not state_path.is_file():
            skipped.append(f"{slug}: no run_state.json")
            continue
        state = json.loads(state_path.read_text())
        completed, total = state.get("completed"), state.get("total")
        reason = state.get("stopped_reason")
        predictions = directory / "predictions.csv"
        if (
            type(total) is not int
            or type(completed) is not int
            or total <= 0
            or completed != total
            or reason is not None
        ):
            skipped.append(f"{slug}: {completed}/{total}, stopped_reason={reason!r}")
        elif state.get("model") != expected:
            skipped.append(f"{slug}: unexpected model {state.get('model')!r}")
        elif not predictions.is_file():
            skipped.append(f"{slug}: no predictions.csv")
        else:
            found.append(NewRun(slug, expected, directory, predictions, state))
    require(not skipped, "refusing incomplete additions: " + "; ".join(skipped))
    return found


def input_pins_record(runs_root: Path) -> dict:
    """The record --step pin-inputs writes: the sha256 of each new model's
    finished run files, read from the run directory under ``runs_root``."""
    return {
        "note": (
            "The sha256 of each new model's supervised run files as the run "
            "finished, written by scripts/finish_terra.py --step pin-inputs "
            "from the run directory. prepare copies them into the stage's "
            "inputs/<slug>/; export and the freeze refuse a staged copy that "
            "is not these bytes, and read this file as committed at HEAD."
        ),
        "inputs": {
            run.slug: {
                "run": f"{runs_root.name}/{run.slug}/run",
                "sha256": {name: digest(run.run_dir / name) for name in PINNED_INPUTS},
            }
            for run in discover_new_models(runs_root)
        },
    }


def pin_inputs(args) -> None:
    """Write INPUT_PINS from the finished run; commit it before export."""
    write_json(INPUT_PINS, input_pins_record(args.runs_root))
    print(f"Pinned {', '.join(PINNED_INPUTS)} of {sorted(MODELS)} in {INPUT_PINS_PATH}")


def head_blob(path: str) -> bytes:
    """A repository file as committed at HEAD, never the working tree's copy,
    which could be edited together with the stage it pins."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"HEAD:{path}"], capture_output=True
    )
    require(
        result.returncode == 0,
        f"{path} is not committed at HEAD; commit it: {result.stderr.decode().strip()}",
    )
    return result.stdout


def committed_input_pins() -> dict[str, dict[str, str]]:
    """Each new model's pinned run-file sha256, as committed at HEAD.

    The working-tree file must be HEAD's too, so pins written and not yet
    committed are refused rather than silently ignored.
    """
    blob = head_blob(INPUT_PINS_PATH)
    require(
        INPUT_PINS.is_file() and INPUT_PINS.read_bytes() == blob,
        f"{INPUT_PINS_PATH} differs from its HEAD commit; commit it",
    )
    record = json.loads(blob)
    inputs = record.get("inputs") if isinstance(record, dict) else None
    require(
        isinstance(inputs, dict)
        and set(inputs) == set(MODELS)
        and all(
            isinstance(item, dict)
            and isinstance(item.get("sha256"), dict)
            and set(item["sha256"]) == set(PINNED_INPUTS)
            for item in inputs.values()
        ),
        f"{INPUT_PINS_PATH} does not pin {list(PINNED_INPUTS)} for {sorted(MODELS)}",
    )
    return {slug: item["sha256"] for slug, item in inputs.items()}


def verify_input_pins(stage: Path) -> None:
    """The stage's copies of each new model's run files are the pinned bytes."""
    for slug, pins in committed_input_pins().items():
        for name, pin in pins.items():
            path = stage / "inputs" / slug / name
            require(
                path.is_file() and digest(path) == pin,
                f"staged inputs/{slug}/{name} is not the run file "
                f"{INPUT_PINS_PATH} pins; prepare a new stage from the pinned run",
            )


def verify_prepared_inputs(stage: Path) -> None:
    """The prepare-time hashes in stage.json and model-provenance.json hold.

    stage.json records every file prepare copied or folded (each new model's
    run files, the bundle's predictions and references); model-provenance.json
    records each new model's predictions sha256 and treatment fingerprint.
    """
    receipt = json.loads((stage / "stage.json").read_text())
    files = receipt.get("files") if isinstance(receipt, dict) else None
    require(isinstance(files, dict), "stage.json records no prepared files")
    us = Path("publish") / RUN_NAME / "us"
    expected = {str(us / name) for name in (*REFERENCE_FILES, "predictions.csv")}
    expected |= {
        str(Path("inputs") / slug / name) for slug in MODELS for name in PINNED_INPUTS
    }
    require(
        expected <= set(files),
        f"stage.json does not record {sorted(expected - set(files))}",
    )
    for name, pin in files.items():
        path = (stage / name).resolve()
        require(
            path.is_relative_to(stage.resolve())
            and path.is_file()
            and digest(path) == pin,
            f"staged input changed since prepare: {name}",
        )
    provenance = json.loads((stage / "model-provenance.json").read_text())
    require(
        isinstance(provenance, dict) and set(provenance) == set(MODELS.values()),
        f"model-provenance.json does not describe exactly {sorted(MODELS.values())}",
    )
    for slug, model in MODELS.items():
        inputs = stage / "inputs" / slug
        state = json.loads((inputs / "run_state.json").read_text())
        entry = provenance[model]
        fingerprint = state.get("treatment_fingerprint")
        require(
            isinstance(entry, dict)
            and entry.get("predictions_sha256") == digest(inputs / "predictions.csv")
            and entry.get("treatment_fingerprint") == fingerprint,
            f"model-provenance.json disagrees with the staged run of {model}",
        )


def require_combined_predictions(bundle: Path, *, require_file: bool = True) -> None:
    """Every release consumer reads the bound combined CSV without alternatives."""
    candidates = set(bundle.rglob("by_model"))
    candidates.add(bundle / "us/by_model")
    shadows = sorted(
        str(path.relative_to(bundle))
        for path in candidates
        if path.exists() or path.is_symlink()
    )
    require(not shadows, f"by_model would shadow combined predictions: {shadows}")
    if require_file:
        require(
            (bundle / "us/predictions.csv").is_file(),
            "missing combined predictions.csv",
        )


def new_model_row_differences(stage: Path, limit: int = 5) -> list[str]:
    """Where a new model's rows in the bundle's predictions are not its run's.

    Every column of the staged run file (inputs/<slug>/predictions.csv, which
    verify_input_pins pins) is compared cell by cell, as text, keyed by
    scenario and variable: the answers and also the cost, token and latency
    columns the payload's costUsd, totalTokens and latencySeconds come from.
    No column is exempt. prepare_inputs copies the run file, and fold_board
    reads it with read_csv and writes its concat with the base by to_csv.
    restore_run_row_text restores every source cell after that fold, including
    integer call counts that a concat with empty incumbent cells promotes to
    floats. This gate compares all 29 columns in the Terra run. A bundle
    column the run lacks must be empty on the new model's rows.
    """
    import pandas as pd

    text = {"dtype": str, "keep_default_na": False}
    us = stage / "publish" / RUN_NAME / "us" / "predictions.csv"
    header = list(pd.read_csv(us, nrows=0, **text).columns)
    if "model" not in header:
        return [f"{us.name} has no model column"]
    parts: dict[str, list] = {}
    for chunk in pd.read_csv(us, chunksize=100_000, **text):
        for model in MODELS.values():
            rows = chunk[chunk["model"] == model]
            if len(rows):
                parts.setdefault(model, []).append(rows)
    found = []
    for slug, model in MODELS.items():
        source = pd.read_csv(stage / "inputs" / slug / "predictions.csv", **text)
        folded = (
            pd.concat(parts[model]) if model in parts else pd.DataFrame(columns=header)
        )
        missing = [column for column in source.columns if column not in header]
        if missing or not set(KEY) <= set(source.columns):
            found.append(f"{model}: run columns {missing or KEY} not in the bundle")
            continue
        run = source.sort_values(KEY, kind="stable").reset_index(drop=True)
        board = folded.sort_values(KEY, kind="stable").reset_index(drop=True)
        if (
            run.duplicated(KEY).any()
            or len(run) != len(board)
            or not run[KEY].equals(board[KEY])
        ):
            found.append(
                f"{model}: the bundle holds {len(board)} rows; the run has "
                f"{len(run)} scenario and variable keys"
            )
            continue
        for column in header:
            if column in run.columns:
                differ = run[column] != board[column]
                what = "differs from the run"
            else:
                differ = board[column] != ""
                what = "is filled, and the run has no such column"
            if differ.any():
                first = board.loc[differ.idxmax(), KEY]
                found.append(
                    f"{model} {column} {what} on {int(differ.sum())} rows "
                    f"(first {'__'.join(first)})"
                )
    return found[:limit]


def verify_new_model_inputs(stage: Path) -> None:
    """Each new model's staged inputs are its pinned run, as prepare folded it.

    Its staged run files are the bytes INPUT_PINS (committed at HEAD) records,
    the prepare-time hashes in stage.json and model-provenance.json still
    hold, and its rows in the bundle's predictions are its run file's, every
    column, so its published cost, tokens and latency are the run's.
    """
    verify_input_pins(stage)
    verify_prepared_inputs(stage)
    import pandas as pd

    for slug, model in MODELS.items():
        frame = pd.read_csv(stage / "inputs" / slug / "predictions.csv")
        verify_call_provenance(frame, model)
        verify_usage(frame, model)
    differ = new_model_row_differences(stage)
    require(
        not differ,
        f"{sorted(MODELS.values())} rows in the bundle's predictions are not the "
        f"pinned run's: {differ}; prepare a new stage",
    )


def verify_call_provenance(frame, model: str) -> None:
    """Require the live/cache disclosure written by the post-#231 runner.

    Counts describe the request group and repeat across its rows. Times are
    each row's apportioned share, including only the successful attempt.
    The published elapsed_seconds keeps cache lookup time, as #228 states.
    """
    import numpy as np
    import pandas as pd

    names = ("live_calls", "cache_hit_calls", "live_elapsed_seconds", "elapsed_seconds")
    require(set(names) <= set(frame.columns), f"missing call provenance: {model}")
    values = {name: pd.to_numeric(frame[name], errors="coerce") for name in names}
    require(
        all(
            np.isfinite(value).all() and (value >= 0).all() for value in values.values()
        ),
        f"invalid call provenance: {model}",
    )
    live, replay = values["live_calls"], values["cache_hit_calls"]
    require(
        (live == np.floor(live)).all()
        and (replay == np.floor(replay)).all()
        and ((live + replay) > 0).all()
        and (values["live_elapsed_seconds"] <= values["elapsed_seconds"] + 1e-9).all()
        and ((live > 0) | (values["live_elapsed_seconds"] == 0)).all(),
        f"inconsistent call provenance: {model}",
    )


def verify_usage(frame, model: str) -> None:
    """Keep #230's missing-usage rule while accepting actual recorded costs."""
    import numpy as np
    import pandas as pd

    for name in ("estimated_cost_usd", "total_tokens"):
        require(name in frame, f"missing {name}: {model}")
        present = frame[name].notna()
        numbers = pd.to_numeric(frame[name], errors="coerce")
        require(
            (np.isfinite(numbers[present]) & (numbers[present] >= 0)).all(),
            f"invalid {name}: {model}",
        )
    # Missing cost remains missing. full_run_export applies a price override
    # only to rows that recorded both token counts; it cannot infer one from
    # another row. The pinned source text survives the fold unchanged.


def verify_engine_pins(engine: str, root: Path | None = None) -> None:
    """Hold both dependency declarations and the lock's package to the build.

    The lead updates the pin and resolves the lock separately. This check
    performs no package installation and leaves the test interpreter alone.
    """
    import tomllib

    root = ROOT if root is None else root
    version = engine.removeprefix("policyengine-us ")
    project = tomllib.loads((root / "pyproject.toml").read_text())
    pins = [
        p for p in project["project"]["dependencies"] if p.startswith("policyengine-us")
    ]
    require(
        pins == [f"policyengine-us=={version}"],
        f"pyproject policyengine-us pin disagrees with installed engine {engine}",
    )
    lock = tomllib.loads((root / "uv.lock").read_text())
    packages = [p for p in lock["package"] if p["name"] == "policyengine-us"]
    declarations = [
        d
        for p in lock["package"]
        for d in p.get("metadata", {}).get("requires-dist", [])
        if d.get("name") == "policyengine-us"
    ]
    require(
        len(packages) == 1
        and packages[0].get("version") == version
        and declarations
        and all(d.get("specifier") == f"=={version}" for d in declarations),
        f"uv.lock policyengine-us pin disagrees with installed engine {engine}",
    )


def restore_run_row_text(path: Path, runs: list[NewRun]) -> None:
    """Write new-model cells from their pinned source after pandas folding.

    Concatenating integer call counts with legacy empty cells promotes them
    to floats. The immutable run supplies the exact CSV text for every cell;
    the fold still has to supply exactly its model and output keys.
    """
    import csv

    csv.field_size_limit(sys.maxsize)
    source = {}
    for run in runs:
        with run.predictions.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        keyed = {(row["scenario_id"], row["variable"]): row for row in rows}
        require(len(keyed) == len(rows), f"duplicate source keys: {run.model}")
        source[run.model] = keyed
    seen = {model: set() for model in source}
    pending = path.with_name(path.name + ".restoring")
    try:
        with path.open(newline="") as stream, pending.open("w", newline="") as out:
            reader = csv.DictReader(stream)
            header = reader.fieldnames
            require(header is not None, "folded predictions lack a header")
            writer = csv.DictWriter(
                out, fieldnames=header, lineterminator="\n", quoting=csv.QUOTE_ALL
            )
            writer.writeheader()
            for row in reader:
                model = row["model"]
                if model in source:
                    key = row["scenario_id"], row["variable"]
                    require(
                        key in source[model] and key not in seen[model],
                        f"fold changed output keys: {model}",
                    )
                    original = source[model][key]
                    require(
                        set(original) <= set(header), f"fold lost run columns: {model}"
                    )
                    row = {name: original.get(name, "") for name in header}
                    seen[model].add(key)
                writer.writerow(row)
        require(
            all(seen[model] == set(rows) for model, rows in source.items()),
            "fold lost new-model outputs",
        )
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def require_release_stage(receipt) -> None:
    """A stage.json that may become a release: prepare records both rehearsal
    flags, ``early`` (a fold and export without paid judging) and ``partial``
    (a scratch cohort rehearsal), and each must be the boolean False. A flag
    that is True, missing or anything else stops the step."""
    flags = (
        {name: receipt.get(name, "missing") for name in ("early", "partial")}
        if isinstance(receipt, dict)
        else {"stage.json": type(receipt).__name__}
    )
    require(
        isinstance(receipt, dict) and all(value is False for value in flags.values()),
        f"early/partial stage cannot become a release ({flags}); prepare fresh "
        "full inputs",
    )


def validate_stage_path(stage: Path, sources: list[Path]) -> None:
    """Allow only scratch outputs, disjoint from every read-only source."""
    stage = stage.resolve()
    scratch = (ROOT / "results/local").resolve()
    require(scratch in stage.parents, f"stage-dir must be below {scratch}")
    for source in sources:
        source = source.resolve()
        require(
            source != stage
            and source not in stage.parents
            and stage not in source.parents,
            f"stage-dir overlaps input: {source}",
        )
    if stage.exists():
        require(
            not any(p.is_symlink() for p in stage.rglob("*")), "symlink in stage-dir"
        )


def validate_keys(frame, reference, model: str) -> None:
    """Row count alone cannot detect substituted or missing output keys."""
    require(set(frame.model) == {model}, f"unexpected model rows for {model}")
    require(not frame.duplicated(KEY).any(), f"duplicate prediction keys: {model}")
    expected = set(reference[KEY].itertuples(index=False, name=None))
    actual = set(frame[KEY].itertuples(index=False, name=None))
    require(actual == expected, f"prediction keys differ from reference: {model}")


def live_pointer() -> dict:
    """The committed dashboard pointer (release 20261014 until the freeze)."""
    return json.loads((ROOT / "app/src/data.artifact.json").read_text())


def resolve_base(args):
    """Pin the live payload and its committed predictions/reference bundle."""
    import pandas as pd

    # Pandas 3 infers Arrow strings and expands repeated full raw responses
    # into large buffers. Object strings retain the CSV parser's deduplication,
    # as in the Pandas 2 environment used for the previous release.
    if hasattr(pd.options, "future") and hasattr(pd.options.future, "infer_string"):
        pd.options.future.infer_string = False

    verify_reference_pins(SNAPSHOT, "committed reference")
    pointer = live_pointer()
    require(
        pointer["tag"] == BASE_TAG and pointer["sha256"] == BASE_SHA256,
        "base pointer changed; review the base before staging",
    )
    opener = gzip.open if args.base_payload.suffix == ".gz" else open
    with opener(args.base_payload, "rb") as stream:
        raw = stream.read()
    live = json.loads(raw)
    if "countries" not in live:
        # The compact snapshot freezes the country payload without its wrapper.
        live = {"countries": {"us": live}}
        raw = json.dumps(live).encode()
    require(
        hashlib.sha256(raw).hexdigest() == BASE_SHA256, "base payload SHA256 mismatch"
    )
    require(
        len(live["countries"]["us"]["modelStats"]) == BASE_MODELS,
        f"base must have {BASE_MODELS} models",
    )

    # An explicit alternative is allowed only if it has identical CSV bytes.
    def csv_digest(path):
        opener = gzip.open if path.suffix == ".gz" else open
        h = hashlib.sha256()
        with opener(path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()

    verify_base_predictions(SNAPSHOT)
    if args.base_predictions.resolve() != (SNAPSHOT / "predictions.csv.gz").resolve():
        require(
            csv_digest(args.base_predictions)
            == csv_digest(SNAPSHOT / "predictions.csv.gz"),
            "base predictions differ from committed 20261014 snapshot",
        )
    print("Reading pinned base predictions", flush=True)
    # Rehearsals do not need repeated raw provider transcripts for incumbents.
    # Their full original CSV remains hash-pinned and untouched in the snapshot.
    usecols = (lambda column: column != "raw_response") if args.partial else None
    base = pd.read_csv(args.base_predictions, low_memory=True, usecols=usecols)
    reference = pd.read_csv(SNAPSHOT / "reference_outputs.csv")
    require(
        len(reference) == BASE_OUTPUTS and reference.scenario_id.nunique() == 100,
        "unexpected reference universe",
    )
    require(
        base.model.nunique() == BASE_MODELS,
        f"base predictions must have {BASE_MODELS} models",
    )
    for model, frame in base.groupby("model"):
        validate_keys(frame, reference, model)
    from policybench.reference_exclusions import (
        load_reference_exclusions,
        split_reference,
    )

    exclusions = load_reference_exclusions(SNAPSHOT)
    require(
        len(exclusions) == BASE_EXCLUSIONS, f"expected {BASE_EXCLUSIONS} exclusions"
    )
    require(
        len(split_reference(reference, exclusions)[0]) == BASE_SCORED,
        f"expected {BASE_SCORED} scored outputs",
    )
    return base, reference, live


def base_commit_blob(path: Path) -> bytes:
    """A file as committed at BASE_COMMIT, whose tree holds release 20261014.

    The checkout must hold that commit: a shallow clone (CI's default) does
    not, so the CI test job checks out full history.
    """
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{BASE_COMMIT}:{path.as_posix()}"],
        capture_output=True,
    )
    require(
        result.returncode == 0,
        f"cannot read {path} at base commit {BASE_COMMIT[:12]}; fetch full "
        f"history (git fetch --unshallow): {result.stderr.decode().strip()}",
    )
    return result.stdout


def verify_base_predictions(snapshot: Path) -> None:
    """The snapshot's predictions are release 20261014's.

    The pin is that release's own: the snapshot manifest as committed at
    BASE_COMMIT. The working tree's manifest could be edited together with
    the predictions it pins.
    """
    manifest = json.loads(
        base_commit_blob(Path("paper/snapshot/20260501/manifest.json"))
    )
    pin = manifest["source_run_artifacts"][RUN_NAME]["files"]["predictions.csv.gz"]
    require(
        digest(snapshot / "predictions.csv.gz") == pin,
        "committed base predictions fail release 20261014's manifest hash",
    )


def base_payload_from_commit() -> dict:
    """Release 20261014's payload, read from BASE_COMMIT and checked."""
    blob = base_commit_blob((SNAPSHOT / "data.json.gz").relative_to(ROOT))
    live = {"countries": {"us": json.loads(gzip.decompress(blob))}}
    require(
        hashlib.sha256(json.dumps(live).encode()).hexdigest() == BASE_SHA256,
        "base payload SHA256 mismatch",
    )
    require(
        len(live["countries"]["us"]["modelStats"]) == BASE_MODELS,
        f"base must have {BASE_MODELS} models",
    )
    return live


def base_adjudication_record() -> dict:
    """Release 20261014's adjudication record file, read from BASE_COMMIT.

    The working-tree copy is not a baseline: the freeze overwrites it, and a
    freeze that stops partway would leave the staged record in its place.
    """
    path = Path("annotations") / RUN_NAME / ADJUDICATIONS
    return json.loads(base_commit_blob(path))


def base_adjudications() -> list[dict]:
    """Release 20261014's adjudication entries, read from BASE_COMMIT."""
    from policybench.adjudications import parse_adjudications

    path = Path("annotations") / RUN_NAME / ADJUDICATIONS
    return parse_adjudications(base_adjudication_record(), f"{BASE_COMMIT[:12]}:{path}")


# --- Ruled exclusions (none in this release) ---------------------------------

EXCLUSION_REASON_CODES = {
    "reference_engine_defect": ("reference_engine_defect", "engine_defect"),
    "reference_depends_on_unlisted_input": ("prompt_ambiguity", "unlisted_input"),
    "reference_law_published_after_freeze": ("reference_later_law", "later_law"),
}
# Release 20261014's date conventions: the waves it names, and the end of the
# sentence on its last wave, after which a new wave's sentence goes.
DATE_CONVENTIONS_BASE = (
    "adjudicated_on names the audit wave that made the decision (2026-09-05, "
    "2026-09-22, 2026-09-29, 2026-10-05, 2026-10-06, 2026-10-10 or 2026-10-14)."
)
DATE_CONVENTIONS_LAST_WAVE = " or 2026-10-14)"
DATE_CONVENTIONS_ANCHOR = (
    "affirming a reference the case's verdict flagged or resolving rows the judge "
    "gave a class outside the final set, and were written on 2026-10-14 UTC."
)


def load_spec() -> dict:
    return json.loads((ROOT / SPEC_PATH).read_text())


def spec_key(item: dict) -> tuple[str, str]:
    return item["scenario_id"], item["variable"]


def spec_records(spec: dict) -> list[dict]:
    """The ruled records, exactly the outputs each proposal names, in
    (scenario_id, variable) order; each proposal file must be the bytes the
    spec pins."""
    import copy

    records = []
    for proposal in spec["proposals"]:
        path = ROOT / proposal["path"]
        require(
            digest(path) == proposal["sha256"],
            f"{proposal['path']} is not the file the spec pins",
        )
        doc = json.loads(path.read_text())
        if proposal["records"] == "root_causes.*.exclusions":
            found = [
                record
                for cause in doc["root_causes"].values()
                for record in cause["exclusions"]
            ]
        else:
            require(proposal["records"] == "exclusions", "unknown record pointer")
            found = doc["exclusions"]
        named = sorted(tuple(output) for output in proposal["outputs"])
        chosen = [record for record in found if spec_key(record) in set(named)]
        require(
            sorted(spec_key(record) for record in chosen) == named,
            f"{proposal['path']} does not hold exactly the ruled outputs {named}",
        )
        records.extend(copy.deepcopy(chosen))
    keys = [spec_key(record) for record in records]
    require(len(set(keys)) == len(keys), f"two ruled records share an output: {keys}")
    require(len(records) == NEW_EXCLUSIONS, f"expected {NEW_EXCLUSIONS} records")
    for record in records:
        require(
            record["reason_code"] in EXCLUSION_REASON_CODES
            and record["decided_on"] == spec["decided_on"]
            and record["decided_by"] == "developer"
            and record["engine_version"] == BASE_ENGINE,
            f"{spec_key(record)} is not a {spec['decided_on']} developer record on "
            f"{BASE_ENGINE}",
        )
    return sorted(records, key=spec_key)


def base_exclusion_record() -> dict:
    """Release 20261014's exclusion record, read from BASE_COMMIT and pinned."""
    blob = base_commit_blob((SNAPSHOT / "reference_exclusions.json").relative_to(ROOT))
    require(
        hashlib.sha256(blob).hexdigest()
        == BASE_REFERENCE_SHA256["reference_exclusions.json"],
        "release 20261014's exclusion record does not match its pin",
    )
    return json.loads(blob)


def build_release_exclusions(base: dict, spec: dict) -> dict:
    """Release 20261014's record plus the spec's ruled records (none here).

    The new records go after the earlier waves' and before the audit's
    trailing scenario_023 record (tests/test_reference_upgrade.py requires that
    tail); the derivation's new sentence goes before the 2026-09-29 marker, as
    release 20261014's did. Every earlier record keeps its bytes.
    """
    import copy
    import tempfile

    from policybench.reference_exclusions import load_reference_exclusions

    doc = copy.deepcopy(base)
    new = spec_records(spec)
    if not new:
        # Nothing ruled: the release's record is release 20261014's, and the
        # spec may carry no edit or derivation sentence for records it lacks.
        require(
            not spec.get("record_edits") and not spec.get("derivation_insert"),
            "the spec edits records or the derivation but rules no record",
        )
        return doc
    tail = doc["exclusions"][-1]
    require(
        spec_key(tail) == ("scenario_023", "head_medicaid_eligible"),
        "release 20261014's record does not end with the audit's scenario_023 record",
    )
    existing = {spec_key(record) for record in doc["exclusions"]}
    require(
        not existing & {spec_key(record) for record in new},
        "a ruled output is already excluded",
    )
    by_key = {spec_key(record): record for record in new}
    for edit in spec.get("record_edits", []):
        record = by_key.get(spec_key(edit))
        require(record is not None, f"no ruled record for edit {spec_key(edit)}")
        text = record[edit["field"]]
        require(
            text == edit["replace"],
            f"{spec_key(edit)} {edit['field']} is not the text the edit replaces",
        )
        record[edit["field"]] = edit["with"]
    doc["exclusions"] = doc["exclusions"][:-1] + new + [tail]
    insert = spec["derivation_insert"]
    require(
        doc["derivation"].count(insert["before"]) == 1,
        "the derivation does not hold its 2026-09-29 marker exactly once",
    )
    doc["derivation"] = doc["derivation"].replace(
        insert["before"], insert["text"] + insert["before"]
    )
    with tempfile.TemporaryDirectory() as scratch:
        # The loader is the record's one validator: reason codes, required
        # fields, numeric values that differ, and no output listed twice.
        (Path(scratch) / "reference_exclusions.json").write_text(exclusions_text(doc))
        loaded = load_reference_exclusions(Path(scratch))
    require(len(loaded) == RELEASE_EXCLUSIONS, "wrong exclusion count")
    return doc


def exclusions_text(doc: dict) -> str:
    """The exclusion record as the reference builder spells it."""
    return json.dumps(doc, indent=2) + "\n"


def release_exclusions_sha256() -> str:
    return hashlib.sha256(
        exclusions_text(
            build_release_exclusions(base_exclusion_record(), load_spec())
        ).encode()
    ).hexdigest()


def install_exclusions(args) -> None:
    """Write the release's exclusion record into the stage and rebind it.

    Prepare staged release 20261014's record (pinned); this step replaces it
    in the stage's scoring source and bundle with build_release_exclusions'
    bytes and records the change in stage.json, so every later step's input
    check binds the installed record. Judge prompts do not render exclusions.
    """
    stage = args.stage_dir
    receipt_path = stage / "stage.json"
    receipt = json.loads(receipt_path.read_text())
    bound = f"publish/{RUN_NAME}/us/reference_exclusions.json"
    require(bound in receipt["files"], "stage.json does not bind the exclusions")
    stage_upgrade(stage)
    text = exclusions_text(
        build_release_exclusions(base_exclusion_record(), load_spec())
    )
    installed = hashlib.sha256(text.encode()).hexdigest()
    previous = receipt.get("exclusions_installed")
    if previous is None:
        require(
            receipt["files"][bound]
            == BASE_REFERENCE_SHA256["reference_exclusions.json"],
            "the stage's exclusion record is not release 20261014's",
        )
    for target in (stage / "scoring", stage / "publish" / RUN_NAME / "us"):
        (target / "reference_exclusions.json").write_text(text)
    receipt["files"][bound] = installed
    receipt["exclusions_installed"] = {
        "base_sha256": BASE_REFERENCE_SHA256["reference_exclusions.json"],
        "sha256": installed,
        "spec_sha256": digest(ROOT / SPEC_PATH),
        "records": RELEASE_EXCLUSIONS,
    }
    write_json(receipt_path, receipt)
    print(
        f"Installed {RELEASE_EXCLUSIONS} exclusions ({NEW_EXCLUSIONS} new): {installed}"
    )


def exclusion_entry(
    base: dict | None,
    item: dict,
    record: dict,
    case_dir: Path,
    adjudicated_on: str | None = None,
) -> dict:
    """The adjudication of one ruled output (or, with ``adjudicated_on`` its
    record's day, one output an engine upgrade newly excludes).

    A new entry carries the case's bound Opus 5.5 verdict (in this release's
    audit tree) as its judge fields, in release 20261014's entry order. An
    output that already has a decision (scenario_051's 2026-09-22
    regeneration) keeps its judge fields, which the restate script set, and
    takes the ruling's decision fields in their places; its reasoning keeps the
    earlier decision's history ahead of the ruling's text.
    """
    from date_adds0928_judge_verdicts import _judge
    from release_20261006 import ENTRY_FIELDS, bound_verdict

    source, verdict_kind = EXCLUSION_REASON_CODES[record["reason_code"]]
    basis = {
        "engine_defect": record.get("law"),
        "unlisted_input": record.get("unlisted_input"),
        "later_law": record.get("published"),
    }[verdict_kind]
    decision = {
        "adjudicated_failure_source": source,
        "adjudicated_failure_subtype": item["adjudicated_failure_subtype"],
        "adjudicated_on": adjudicated_on or load_spec()["decided_on"],
        "adjudicator": "developer",
        "excluded_from_scoring": True,
        "reference_verdict": verdict_kind,
        "reference_basis": basis,
    }
    require(
        item["adjudicated_failure_source"] == source
        and item["reference_verdict"] == verdict_kind,
        f"{spec_key(item)}: the spec's classes do not match the record's reason",
    )
    if base is None:
        verdict, meta = bound_verdict(case_dir)
        entry = {
            "country": "us",
            "scenario_id": item["scenario_id"],
            "variable": item["variable"],
            "judge_model": _judge(meta),
            "judge_failure_source": verdict["case_failure_source"],
            "judge_failure_subtype": verdict["case_failure_subtype"],
            **decision,
            "judge_reference_suspect": bool(verdict.get("reference_suspect")),
            "reasoning": item["reasoning"],
            "judged_on_utc": meta["judged_at_utc"][:10],
        }
        entry = {name: entry[name] for name in ENTRY_FIELDS}
        require(list(entry) == list(ENTRY_FIELDS), "entry fields out of order")
        return entry
    entry = {}
    for name, value in base.items():
        entry[name] = decision.get(name, value)
        if name == "adjudicator" and "excluded_from_scoring" not in base:
            # In release 20261014's entry order, the flag follows the adjudicator.
            entry["excluded_from_scoring"] = True
    require(
        set(decision) <= set(entry), f"{spec_key(item)}: a decision field is missing"
    )
    entry["reasoning"] = base["reasoning"] + " " + item["reasoning"]
    return entry


# A triage decision's fields, in release 20261014's entry order (an affirmed
# reference carries no excluded_from_scoring, as release 20261014's do not).
# A decision on a case whose verdict flags nothing carries no reference_verdict
# or reference_basis, as release 20261014's scenario_007 and scenario_008
# decisions do not.
TRIAGE_FIELDS = (
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
    "judge_reference_suspect",
    "reference_verdict",
    "reference_basis",
    "reasoning",
    "judged_on_utc",
)
TRIAGE_ITEM_KEYS = frozenset(
    {
        "scenario_id",
        "variable",
        "adjudicated_failure_source",
        "adjudicated_failure_subtype",
        "adjudicated_on",
        "reference_verdict",
        "reference_basis",
        "reasoning",
    }
)


def triage_items(upgrade, spec: dict | None = None) -> list[dict]:
    """docs/terra/spec.json's triage_adjudications: the developer's decisions
    on re-opened cases whose verdict triage could not accept as it stands.
    Each keeps the output scored and gives the case's rows the decided final
    class. It either affirms a reference the case's verdict flagged
    (reference_verdict "affirmed", with its basis) or, where the verdict flags
    nothing, resolves rows the judge gave a class outside the final set (no
    reference verdict or basis, as release 20261014's scenario_007 decision).
    An exclusion is ruled, never a triage decision.

    The installed build adds no exclusion decisions, so these decisions are
    this release's own wave: each is dated by the spec's
    triage_decided_on."""
    require(
        upgrade is None or not upgrade.added,
        "this reference build adds no exclusion decisions",
    )
    spec = load_spec() if spec is None else spec
    items = spec.get("triage_adjudications", [])
    require(
        isinstance(items, list)
        and all(isinstance(i, dict) and set(i) == TRIAGE_ITEM_KEYS for i in items),
        "the spec's triage_adjudications must be items with "
        f"{sorted(TRIAGE_ITEM_KEYS)}",
    )
    keys = [spec_key(item) for item in items]
    require(len(set(keys)) == len(keys), f"a triage decision is listed twice: {keys}")
    require(
        all(
            (
                item["reference_verdict"] == "affirmed"
                and isinstance(item["reference_basis"], str)
                and bool(item["reference_basis"].strip())
            )
            or (item["reference_verdict"] is None and item["reference_basis"] is None)
            for item in items
        ),
        "a triage decision may only affirm a reference, with its basis, or leave "
        "an unflagged reference without a verdict or basis; an exclusion is ruled",
    )
    if not items:
        return []
    day = spec.get("triage_decided_on")
    require(
        isinstance(day, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) is not None,
        f"{SPEC_PATH} names no triage_decided_on (YYYY-MM-DD), the wave its "
        "triage decisions are dated by",
    )
    wrong = sorted(spec_key(i) for i in items if i["adjudicated_on"] != day)
    require(
        not wrong,
        f"a triage decision is dated by this release's wave ({day}): {wrong}",
    )
    return sorted(items, key=spec_key)


# The classes triage accepts on a scored row (triage's own list).
TRIAGE_FINAL_SOURCES = frozenset(
    {"llm_error", "parse_contract_failure", "budget_exhausted_at_ceiling"}
)


def triage_entry(item: dict, case_dir: Path) -> dict:
    """The adjudication of a triage decision, with the case's bound Opus 5.5
    verdict as its judge fields.

    The decision must answer what triage stops on in that verdict: an
    affirmation needs the verdict's reference flag, and a decision without a
    reference verdict needs an unflagged verdict whose case or rows carry a
    class outside the final set."""
    from date_adds0928_judge_verdicts import _judge
    from release_20261006 import bound_verdict

    verdict, meta = bound_verdict(case_dir)
    flagged = bool(verdict.get("reference_suspect"))
    affirms = item["reference_verdict"] == "affirmed"
    require(
        flagged == affirms,
        f"{case_dir.name}: a triage decision affirms the reference exactly when "
        f"the case's verdict flags it (flagged {flagged}, affirmed {affirms})",
    )
    open_classes = {verdict["case_failure_source"]} | {
        model["failure_source"] for model in verdict.get("models", [])
    }
    require(
        affirms or bool(open_classes - TRIAGE_FINAL_SOURCES),
        f"{case_dir.name}: the verdict leaves triage nothing to decide",
    )
    entry = {
        "country": "us",
        "scenario_id": item["scenario_id"],
        "variable": item["variable"],
        "judge_model": _judge(meta),
        "judge_failure_source": verdict["case_failure_source"],
        "judge_failure_subtype": verdict["case_failure_subtype"],
        "adjudicated_failure_source": item["adjudicated_failure_source"],
        "adjudicated_failure_subtype": item["adjudicated_failure_subtype"],
        "adjudicated_on": item["adjudicated_on"],
        "adjudicator": "developer",
        "judge_reference_suspect": flagged,
        "reference_verdict": item["reference_verdict"],
        "reference_basis": item["reference_basis"],
        "reasoning": item["reasoning"],
        "judged_on_utc": meta["judged_at_utc"][:10],
    }
    fields = TRIAGE_FIELDS
    if not affirms:
        fields = tuple(
            f
            for f in TRIAGE_FIELDS
            if f not in ("reference_verdict", "reference_basis")
        )
        entry = {name: entry[name] for name in fields}
    require(list(entry) == list(fields), "triage entry fields out of order")
    return entry


def exclusion_adjudications(
    record: dict,
    cases_dir: Path,
    regenerated: frozenset = frozenset(),
    added: list[tuple[dict, dict]] | tuple = (),
    triage: list[dict] | tuple = (),
) -> dict:
    """``record`` (the staged adjudication record) with the ruled outputs
    decided: an existing entry is restated in place, a new one appended in the
    spec's order, and the date conventions name the 2026-10-06 wave. Each
    ``triage`` item (triage_items) is appended last (triage_entry).

    ``regenerated`` names the ruled outputs an installed engine upgrade
    regenerated (spec_regenerated); they are scored again, so none is decided.
    ``added`` (upgrade_decisions) decides the outputs the upgrade newly
    excludes, each appended after the ruled ones and dated by its record; the
    date conventions then name that wave too.
    """
    import copy

    spec = load_spec()
    records = {
        spec_key(r): r for r in spec_records(spec) if spec_key(r) not in regenerated
    }
    items = [
        item for item in spec["adjudications"] if spec_key(item) not in regenerated
    ]
    require(
        set(records) == {spec_key(item) for item in items},
        "the spec's adjudications and records name different outputs",
    )
    restated = {
        spec_key(item) for item in spec.get("restated_adjudications", [])
    } - regenerated
    out = copy.deepcopy(record)
    by_key = {
        spec_key(entry): index for index, entry in enumerate(out["adjudications"])
    }
    require(
        set(by_key) & set(records) == restated,
        "existing decisions on ruled outputs differ from the spec's restated list: "
        f"{sorted(set(by_key) & set(records))}",
    )
    appended = []
    for item in items:
        k = spec_key(item)
        case_dir = cases_dir / f"us__{k[0]}__{k[1]}"
        if k in by_key:
            out["adjudications"][by_key[k]] = exclusion_entry(
                out["adjudications"][by_key[k]], item, records[k], case_dir
            )
        else:
            appended.append(exclusion_entry(None, item, records[k], case_dir))
    for item, upgraded in added:
        k = spec_key(item)
        require(
            k not in by_key,
            f"{k}: the engine upgrade newly excludes an output that already has a "
            "decision; restating one is not supported",
        )
        appended.append(
            exclusion_entry(
                None,
                item,
                upgraded,
                cases_dir / f"us__{k[0]}__{k[1]}",
                adjudicated_on=upgraded["decided_on"],
            )
        )
    wave = decision_wave(added, triage)
    for item in triage:
        k = spec_key(item)
        require(
            k not in by_key,
            f"{k}: a triage decision on a case that already has a decision; "
            "restating one is not supported",
        )
        appended.append(triage_entry(item, cases_dir / f"us__{k[0]}__{k[1]}"))
    out["adjudications"] = out["adjudications"] + appended
    out["date_conventions"] = release_date_conventions(out["date_conventions"], wave)
    return out


@dataclass(frozen=True)
class DecisionWave:
    """A wave of decisions this release adds, and its UTC day.

    With ``upgrade`` (the form finish_musewonder.py has), the wave of an
    installed engine upgrade's decisions: whether they exclude outputs the
    upgrade moved onto an unstated input (upgrade_decisions) or affirm
    references it changed. Without it, this release's own triage wave
    (triage_items): whether its decisions affirm a flagged reference
    (``affirms``) or resolve rows the judge gave a class outside the final set
    on an unflagged case (``resolves``). This build changes scored references
    and adds no exclusion decisions, so decision_wave builds the triage form."""

    day: str
    excludes: bool
    affirms: bool
    upgrade: bool = True
    resolves: bool = False


def decision_wave(added, triage) -> DecisionWave | None:
    """The DecisionWave of the release's triage decisions (``triage``, as
    triage_items lists them), or None when there are none, all dated by one
    day, their adjudicated_on. ``added`` (upgrade_decisions) is always empty:
    the installed build adds no exclusion decisions."""
    require(not added, "this reference build adds no exclusion decisions")
    days = {item["adjudicated_on"] for item in triage}
    require(len(days) <= 1, f"the triage decisions name several days: {days}")
    if not days:
        return None
    return DecisionWave(
        next(iter(days)),
        excludes=False,
        affirms=any(item["reference_verdict"] == "affirmed" for item in triage),
        upgrade=False,
        resolves=any(item["reference_verdict"] is None for item in triage),
    )


def release_date_conventions(conventions: str, wave: DecisionWave | None = None) -> str:
    """Release 20261014's date conventions with each wave this release adds
    named; the one definition the adjudicate step writes and the record gate
    expects.

    A wave is added for the spec's ruled records, when it rules any (its
    decided_on, with its wave_sentence and adjudications_written_on), and for
    ``wave`` (decision_wave): this release's triage decisions, with the day
    the spec says they were written (triage_adjudications_written_on), or, in
    finish_musewonder.py's form, an installed engine upgrade's decisions
    (upgrade_adjudications_written_on). With neither, the conventions are
    release 20261014's, unchanged.
    """
    require(
        conventions.count(DATE_CONVENTIONS_BASE) == 1
        and conventions.count(DATE_CONVENTIONS_ANCHOR) == 1,
        "the record's date conventions are not release 20261014's",
    )
    spec = load_spec()
    days, sentence = [], ""
    if spec_records(spec):
        day = spec["decided_on"]
        days.append(day)
        sentence += (
            f" The {day} wave's decisions {spec['wave_sentence']} and were written "
            f"on {spec['adjudications_written_on']} UTC."
        )
    if wave is not None and not wave.upgrade:
        written = spec.get("triage_adjudications_written_on")
        require(
            isinstance(written, str) and written.strip(),
            f"{SPEC_PATH} names no triage_adjudications_written_on, the UTC day "
            "this release's triage decisions were written",
        )
        require(wave.day not in days, f"the {wave.day} wave is named twice")
        require(not wave.excludes, "a triage decision never excludes an output")
        days.append(wave.day)
        how = []
        if wave.affirms:
            how.append("affirming a reference the case's verdict flagged")
        if wave.resolves:
            how.append("resolving rows the judge gave a class outside the final set")
        require(bool(how), f"the {wave.day} wave decides nothing")
        sentence += (
            f" The {wave.day} wave's decisions keep scored outputs on cases this "
            f"release's new models re-opened, {' or '.join(how)}, and were "
            f"written on {written} UTC."
        )
    elif wave is not None:
        upgrade_written = spec.get("upgrade_adjudications_written_on")
        require(
            isinstance(upgrade_written, str) and upgrade_written.strip(),
            f"{SPEC_PATH} names no upgrade_adjudications_written_on, the UTC day "
            "the engine upgrade's decisions were written",
        )
        require(wave.day not in days, f"the {wave.day} wave is named twice")
        days.append(wave.day)
        upgrade = f"the {wave.day} engine upgrade of the references"
        what = []
        if wave.excludes:
            what.append(
                f"exclude the outputs {upgrade} moved onto an input the prompt "
                "does not state"
            )
        if wave.affirms:
            what.append(
                f"affirm references {upgrade} changed, which a re-judged case's "
                "verdict flagged"
            )
        require(bool(what), f"the {wave.day} wave decides nothing")
        sentence += (
            f" The {wave.day} wave's decisions {' and '.join(what)}, and were "
            f"written on {upgrade_written} UTC."
        )
    if not days:
        return conventions
    require(
        DATE_CONVENTIONS_BASE.count(DATE_CONVENTIONS_LAST_WAVE) == 1,
        "the base conventions do not end their wave list on 2026-10-14",
    )
    named = ", ".join(["2026-10-14", *days[:-1]]) + f" or {days[-1]})"
    waves = DATE_CONVENTIONS_BASE.replace(DATE_CONVENTIONS_LAST_WAVE, ", " + named)
    conventions = conventions.replace(DATE_CONVENTIONS_BASE, waves)
    return conventions.replace(
        DATE_CONVENTIONS_ANCHOR, DATE_CONVENTIONS_ANCHOR + sentence
    )


def upgrade_decisions(upgrade, spec: dict | None = None) -> list[tuple[dict, dict]]:
    """The (spec item, build record) pairs that decide the outputs an installed
    engine upgrade newly excludes, in (scenario_id, variable) order.

    docs/terra/spec.json's upgrade_adjudications holds one item per such
    output, in the spec adjudications' shape (classes and reasoning); each
    record is the build's, computed on the build's engine and decided on its
    revision's day. Without an upgrade, or one that excludes nothing new, none;
    the spec may then name none either.
    """
    spec = load_spec() if spec is None else spec
    items = spec.get("upgrade_adjudications", [])
    require(
        isinstance(items, list) and all(isinstance(i, dict) for i in items),
        "the spec's upgrade_adjudications is not a list of items",
    )
    if upgrade is None:
        return []
    added = upgrade.added
    keys = [spec_key(item) for item in items]
    if not added:
        require(
            not keys,
            f"the spec's upgrade_adjudications names {sorted(keys)}, but the engine "
            "upgrade newly excludes nothing",
        )
        return []
    require(
        len(set(keys)) == len(keys) and set(keys) == set(added),
        "the spec's upgrade_adjudications must decide exactly the outputs the "
        f"engine upgrade newly excludes: {sorted(added)}; "
        f"the spec names {sorted(keys)}",
    )
    records = {
        spec_key(record): record
        for record in json.loads(upgrade.exclusions_text)["exclusions"]
    }
    pairs = []
    for item in sorted(items, key=spec_key):
        record = records[spec_key(item)]
        require(
            record["engine_version"] == upgrade.engine_version
            and record["decided_on"] == upgrade.revision["date"],
            f"{spec_key(item)}: the build's record is not decided on its engine and "
            "day",
        )
        pairs.append((item, record))
    return pairs


def upgrade_wave(added) -> str | None:
    """The day the upgrade's newly excluded outputs were decided, if any."""
    days = {record["decided_on"] for _, record in added}
    require(len(days) <= 1, f"the upgrade's new records name several days: {days}")
    return next(iter(days), None)


def adjudicate_exclusions(args) -> None:
    """Decide the ruled outputs in the staged record (after judge and restate).

    With an engine upgrade installed it decides only the ruled outputs the
    build keeps excluded, and drops the decisions of the release 20261014
    records the build regenerated, as release 20260922c dropped scenario_045
    SNAP's (#178). Each drop is recorded in stage.json (adjudications_dropped)
    before the record is written, so triage can hold the record to it.
    """
    from policybench.adjudications import parse_adjudications

    path = args.stage_dir / "publish" / RUN_NAME / "annotations" / ADJUDICATIONS
    record = json.loads(path.read_text())
    upgrade = stage_upgrade(args.stage_dir)
    regenerated = frozenset() if upgrade is None else upgrade.regenerated_ruled
    added = upgrade_decisions(upgrade)
    keys = {spec_key(item) for item in load_spec()["adjudications"]}
    keys |= {spec_key(item) for item, _ in added}
    require(
        not any(
            entry.get("excluded_from_scoring") and spec_key(entry) in keys - regenerated
            for entry in record["adjudications"]
        ),
        "the ruled outputs are already decided in the staged record",
    )
    require(
        not any(
            entry.get("excluded_from_scoring") and spec_key(entry) in regenerated
            for entry in record["adjudications"]
        ),
        "the staged record excludes ruled outputs the engine upgrade regenerated; "
        "put the staged record back to release 20261014's (from git at "
        "BASE_COMMIT), then restate and decide again",
    )
    staged = exclusion_adjudications(
        record,
        args.stage_dir / "audit" / "cases",
        regenerated,
        added,
        triage_items(upgrade),
    )
    parse_adjudications(staged, path)
    path.write_text(record_text(staged))
    decided = len(keys - regenerated)
    print(f"Decided {decided} ruled outputs in {path}")


def record_text(record: dict) -> str:
    """An adjudication record as the committed file spells it."""
    return json.dumps(record, indent=2, ensure_ascii=False) + "\n"


def verify_record_form(text: str, base: dict, wave: DecisionWave | None = None) -> None:
    """The staged record's bytes are exactly its parsed content, and its top
    level other than the entries is release 20261014's.

    Duplicate keys, or any other bytes a parser drops, would ship in the
    frozen file unseen by the entry gate; so would a rewritten note or date
    convention.
    """
    record = json.loads(text)
    require(
        text == record_text(record),
        "the staged adjudication record is not in the committed form (duplicate "
        "keys or other bytes the entry gate cannot see); write it with "
        "json.dumps(indent=2, ensure_ascii=False)",
    )
    expected = {k: v for k, v in base.items() if k != "adjudications"}
    expected["date_conventions"] = release_date_conventions(
        expected["date_conventions"], wave
    )
    require(
        record_text({k: v for k, v in record.items() if k != "adjudications"})
        == record_text(expected),
        "the staged adjudication record changes its note, schema or date "
        "conventions beyond naming this release's waves; only entries may change",
    )


def verify_restatements(
    base: list[dict], staged: list[dict], rejudged: frozenset[str], cases_dir: Path
) -> None:
    """A re-opened entry's judge fields must be the restate script's.

    Where they differ from 20261014's, the entry must name the case's current
    Opus 5.5 verdict (bound by its sidecar) as its judge, date it by that
    sidecar's UTC day, and keep 20261014's judge_previous with exactly one
    item appended: the replaced verdict, which is the one 20261014's entry
    names (its judge, classes, flag and day are its seed verdict's, as the
    sha256-bound sidecar records it). A new entry must name the current judge
    too.
    """
    from restate_gpt61sol_adjudications import JUDGE_FIELDS, _utc_day, named_item

    before = {case_id(entry): entry for entry in base}
    wrong = []
    for entry in staged:
        case = case_id(entry)
        if case not in rejudged:
            continue
        original = before.get(case)
        judge = {k: v for k, v in entry.items() if k in JUDGE_FIELDS}
        if original is not None and judge == {
            k: v for k, v in original.items() if k in JUDGE_FIELDS
        }:
            continue
        verdict = cases_dir / case / "verdict.json"
        meta_path = verdict.with_name("verdict.meta.json")
        meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
        bound = verdict.is_file() and meta.get("verdict_sha256") == digest(verdict)
        day = _utc_day(meta["judged_at_utc"]) if meta.get("judged_at_utc") else None
        problems = []
        if not bound or entry.get("judge_model") != JUDGE_MODEL:
            problems.append("judge is not the current Opus 5.5 verdict")
        if original is not None:
            previous = original.get("judge_previous", [])
            restated = entry.get("judge_previous", [])
            if len(restated) != len(previous) + 1 or restated[:-1] != previous:
                problems.append("judge_previous is not 20261014's plus one item")
            elif restated[-1] != named_item(original):
                problems.append(
                    "the appended judge_previous item is not the verdict "
                    "20261014's entry names"
                )
            if (
                entry.get("judge_rejudged_on") != day
                or entry.get("judged_on_utc", day) != day
            ):
                problems.append(f"not dated by the current verdict's day {day}")
        if problems:
            wrong.append(f"{case}: {'; '.join(problems)}")
    require(
        not wrong,
        f"re-opened adjudications not restated by the restate script: {wrong[:4]}",
    )


def rejudged_cases(stage: Path) -> frozenset[str]:
    """The cases a new model re-opened: prompt-changes.json's changed and added.

    load_seed re-derives prompt-changes.json from the stage's prompts and the
    seed stage.json binds, so the lists cannot drift from the stage.
    """
    load_seed(stage)
    changes = json.loads((stage / PROMPT_CHANGES).read_text())
    return frozenset(changes["changed"]) | frozenset(changes["added"])


def case_id(entry: dict) -> str:
    """An adjudication entry's audit case id."""
    return f"{entry['country']}__{entry['scenario_id']}__{entry['variable']}"


# The only published wording an amendment may change, and where it lives: the
# decision's reasoning in the adjudication record, the case note, and one
# model's row annotation. None of them carries a class, an exclusion or a score.
AMENDABLE_FIELDS = {
    "reasoning": "adjudication record",
    "case_annotation": "case note",
    "annotation": "row annotation",
}


def load_amendments(stage: Path, rejudged: frozenset[str]) -> list[dict]:
    """The stage's wording-only amendments, each checked for shape and scope.

    Each names a case a new model re-opened, a wording field, the exact old
    text, the new text and the reason; a row annotation also names its model.
    An absent file lists none.
    """
    path = stage / AMENDMENTS
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    amendments = payload.get("amendments") if isinstance(payload, dict) else None
    require(isinstance(amendments, list), f"{AMENDMENTS}: 'amendments' is not a list")
    for item in amendments:
        require(isinstance(item, dict), f"{AMENDMENTS}: {item!r} is not an object")
        field = item.get("field")
        require(
            field in AMENDABLE_FIELDS,
            f"{AMENDMENTS}: field {field!r} is not wording; only "
            f"{sorted(AMENDABLE_FIELDS)} may be amended",
        )
        keys = {"case_id", "field", "old", "new", "reason"}
        if field == "annotation":
            keys.add("model")
        require(
            set(item) == keys,
            f"{AMENDMENTS}: an amendment of {field} has keys {sorted(keys)}, "
            f"not {sorted(item)}",
        )
        require(
            item["case_id"] in rejudged,
            f"{AMENDMENTS}: {item['case_id']} was not re-judged in this stage",
        )
        for key in ("old", "new", "reason", *(("model",) if "model" in keys else ())):
            require(
                isinstance(item[key], str) and item[key].strip(),
                f"{AMENDMENTS}: {key} must be non-empty text: {item!r}",
            )
        require(
            item["old"] != item["new"],
            f"{AMENDMENTS}: an amendment changes nothing: {item!r}",
        )
    return amendments


def amend_text(text: str, amendments: list[dict], label: str) -> str:
    """``text`` with each amendment's old wording, found exactly once, replaced."""
    for item in amendments:
        count = text.count(item["old"])
        require(
            count == 1,
            f"{label}: the old text of a wording amendment occurs {count} times, "
            f"not once: {item['old'][:80]!r}",
        )
        text = text.replace(item["old"], item["new"])
    return text


def _record_amendments(amendments: list[dict]) -> dict[str, list[dict]]:
    """The amendments of the adjudication record, by case."""
    grouped: dict[str, list[dict]] = {}
    for item in amendments:
        if item["field"] == "reasoning":
            grouped.setdefault(item["case_id"], []).append(item)
    return grouped


def ruled_adjudication_problems(
    before: dict[str, dict],
    after: dict[str, dict],
    cases_dir: Path,
    regenerated: frozenset = frozenset(),
    added: list[tuple[dict, dict]] | tuple = (),
    triage: list[dict] | tuple = (),
) -> list[str]:
    """Where staged decisions differ from what exclusion_entry builds.

    A new decision uses its case's bound verdict. A restated decision keeps
    the base entry outside the judge fields the restate script supplies.
    This release initially rules no exclusion.

    A ruled output an installed engine upgrade regenerated (``regenerated``)
    is scored again: no staged decision may exclude it, and any other decision
    on it is an ordinary re-opened case's (verify_adjudication_changes). Each
    output the upgrade newly excludes (``added``, upgrade_decisions) must have
    exactly the new entry exclusion_entry builds from its item, its build
    record and its case's bound verdict, dated by the record."""
    from restate_gpt61sol_adjudications import JUDGE_FIELDS

    spec = load_spec()
    records = {spec_key(r): r for r in spec_records(spec)}
    problems = []
    for item in spec["adjudications"]:
        k = spec_key(item)
        case = f"us__{k[0]}__{k[1]}"
        if k in regenerated:
            if after.get(case, {}).get("excluded_from_scoring"):
                problems.append(
                    f"{case}: the engine upgrade regenerated this output, so no "
                    "decision may exclude it"
                )
            continue
        if case not in after:
            problems.append(f"{case}: no staged decision")
            continue
        base = before.get(case)
        if base is not None:
            # The staged entry before the ruling: release 20261014's decision
            # fields and reasoning, with the judge fields the restate script
            # wrote. Outside the judge fields it must be 20261014's entry.
            staged = after[case]
            pre = {
                name: value if name in JUDGE_FIELDS else base[name]
                for name, value in staged.items()
                if name in base or name in JUDGE_FIELDS
            }

            def outside_judge(entry: dict) -> list:
                return [[n, v] for n, v in entry.items() if n not in JUDGE_FIELDS]

            if outside_judge(pre) != outside_judge(base):
                problems.append(f"{case}: fields moved outside the ruling")
                continue
            base = pre
        expected = exclusion_entry(base, item, records[k], cases_dir / case)
        if json.dumps(after[case], ensure_ascii=False) != json.dumps(
            expected, ensure_ascii=False
        ):
            problems.append(f"{case}: differs from the ruling's entry")
    for item, record in added:
        k = spec_key(item)
        case = f"us__{k[0]}__{k[1]}"
        if case in before:
            problems.append(f"{case}: release 20261014 already decides it")
            continue
        if case not in after:
            problems.append(f"{case}: no staged decision")
            continue
        expected = exclusion_entry(
            None, item, record, cases_dir / case, adjudicated_on=record["decided_on"]
        )
        if json.dumps(after[case], ensure_ascii=False) != json.dumps(
            expected, ensure_ascii=False
        ):
            problems.append(f"{case}: differs from the upgrade's entry")
    for item in triage:
        k = spec_key(item)
        case = f"us__{k[0]}__{k[1]}"
        if case not in after:
            problems.append(f"{case}: no staged triage decision")
            continue
        expected = triage_entry(item, cases_dir / case)
        if json.dumps(after[case], ensure_ascii=False) != json.dumps(
            expected, ensure_ascii=False
        ):
            problems.append(f"{case}: differs from the triage decision's entry")
    return problems


def verify_adjudication_changes(
    base: list[dict],
    staged: list[dict],
    rejudged: frozenset[str],
    amendments: list[dict],
    cases_dir: Path,
    *,
    regenerated: frozenset = frozenset(),
    dropped: frozenset[str] = frozenset(),
    added: list[tuple[dict, dict]] | tuple = (),
    triage: list[dict] | tuple = (),
) -> int:
    """A staged record differs from 20261014's only where it has a reason to.

    Only a case a new model re-opened (``rejudged``) may change, and only in
    its judge fields (the restate script's JUDGE_FIELDS) and in the reasoning
    wording the listed amendments change, exactly as they say. Every other
    field of every committed entry keeps its value and its place, key order
    included, and the committed entries keep their order. A new entry must be
    one the spec lists (a ruled or triage decision), and none may be dropped.
    Returns how many staged entries are new beyond those: always 0, since any
    is refused.

    With an engine upgrade installed, ``regenerated`` names the ruled outputs
    it regenerated (no longer decided as ruled) and ``dropped`` the cases of
    the release 20261014 records it regenerated: exactly those decisions must
    be gone, and every other one stays. ``added`` (upgrade_decisions) decides
    the outputs it newly excludes, gated as the ruled outputs are.
    """
    from restate_gpt61sol_adjudications import JUDGE_FIELDS

    def serialized(entry: dict, rejudged_case: bool) -> str:
        # A re-opened case may rewrite its judge fields; nothing else may move.
        items = [
            [key, value]
            for key, value in entry.items()
            if not (rejudged_case and key in JUDGE_FIELDS)
        ]
        return json.dumps(items, ensure_ascii=False, allow_nan=False)

    before = {case_id(entry): entry for entry in base}
    after = {case_id(entry): entry for entry in staged}
    ruled = ruled_adjudication_problems(
        before, after, cases_dir, regenerated, added, triage
    )
    triage_cases = {f"us__{k[0]}__{k[1]}" for k in map(spec_key, triage)}
    require(
        triage_cases <= rejudged,
        "triage decisions name cases this stage did not re-open: "
        f"{sorted(triage_cases - rejudged)[:8]}",
    )
    require(
        not (triage_cases & set(before)) or triage_cases & set(before) <= dropped,
        "a triage decision replaces a recorded decision: "
        f"{sorted((triage_cases & set(before)) - dropped)[:8]}",
    )
    require(not ruled, f"Staged adjudications of the ruled outputs: {ruled[:8]}")
    ruled_cases = {
        f"us__{k[0]}__{k[1]}"
        for k in (spec_key(item) for item in load_spec()["adjudications"])
        if k not in regenerated
    } | {f"us__{k[0]}__{k[1]}" for k in (spec_key(item) for item, _ in added)}
    ruled_cases |= triage_cases
    stray = sorted(dropped - set(before))
    require(
        not stray,
        f"Staged adjudications drop decisions release 20261014 lacks: {stray[:8]}",
    )
    # A regenerated record's decision is gone; a triage decision may affirm the
    # regenerated reference in its place (it is in ruled_cases, gated above).
    kept = sorted((dropped & set(after)) - triage_cases)
    require(
        not kept,
        "Staged adjudications keep the decisions of records the engine upgrade "
        f"regenerated; run --step adjudicate-exclusions: {kept[:8]}",
    )
    before = {
        case: entry
        for case, entry in before.items()
        if case not in ruled_cases and case not in dropped
    }
    after = {case: entry for case, entry in after.items() if case not in ruled_cases}
    dropped = sorted(set(before) - set(after))
    require(not dropped, f"Staged adjudications drop recorded decisions: {dropped}")
    new = sorted(set(after) - set(before))
    require(
        set(new) <= rejudged,
        "Staged adjudications add decisions on cases no new model "
        f"re-opened: {sorted(set(new) - rejudged)[:8]}",
    )
    # The only new decisions this release makes are the spec's (ruled and
    # triage, gated above as ruled_cases); any other would bypass the triage
    # restrictions, an affirmation of an unflagged reference among them.
    require(
        not new,
        "Staged adjudications add decisions the spec does not list: "
        f"{new[:8]}; a new decision goes in docs/terra/spec.json's "
        "triage_adjudications",
    )
    require(
        [case for case in after if case in before] == list(before),
        "Staged adjudications change the committed entry order",
    )
    grouped = _record_amendments(amendments)
    require(
        set(grouped) <= set(before),
        f"Wording amendments name cases with no recorded decision: "
        f"{sorted(set(grouped) - set(before))}",
    )
    changed = []
    for case, entry in before.items():
        if case in grouped:
            entry = {
                **entry,
                "reasoning": amend_text(
                    entry["reasoning"], grouped[case], f"{case} reasoning"
                ),
            }
        reopened = case in rejudged
        if serialized(after[case], reopened) != serialized(entry, reopened):
            changed.append(case)
    require(
        not changed,
        "Staged adjudications change recorded decisions beyond the re-judged "
        f"cases' judge fields and the listed wording amendments: {changed[:8]}",
    )
    return len(new)


def stage_adjudications(
    path: Path,
    rejudged: frozenset[str],
    amendments: list[dict],
    cases_dir: Path,
    *,
    regenerated: frozenset = frozenset(),
    dropped: frozenset[str] = frozenset(),
    added: list[tuple[dict, dict]] | tuple = (),
    triage: list[dict] | tuple = (),
) -> list[dict]:
    """The staged record, with its listed reasoning amendments applied.

    Checked in memory against release 20261014's record (from git) and the
    stage's verdicts; written back only when an amendment was not applied yet.
    ``regenerated``, ``dropped`` and ``added`` describe an installed engine
    upgrade (verify_adjudication_changes).
    """
    from freeze_snapshot import verify_adjudications_keep_judge_verdicts

    from policybench.adjudications import parse_adjudications

    base_record = base_adjudication_record()
    base = base_adjudications()
    current = path.read_text()
    wave = decision_wave(added, triage)
    verify_record_form(current, base_record, wave)
    record = json.loads(current)
    grouped = _record_amendments(amendments)
    original = {case_id(entry): entry for entry in base}
    applied = False
    for entry in record["adjudications"]:
        case = case_id(entry)
        if case in grouped and case in original:
            wording = original[case]["reasoning"]
            if entry["reasoning"] == wording:
                entry["reasoning"] = amend_text(
                    wording, grouped[case], f"{case} reasoning"
                )
                applied = True
    text = record_text(record)
    verify_record_form(text, base_record, wave)
    entries = parse_adjudications(json.loads(text), path)
    verify_adjudication_changes(
        base,
        entries,
        rejudged,
        amendments,
        cases_dir,
        regenerated=regenerated,
        dropped=dropped,
        added=added,
        triage=triage,
    )
    # A dropped decision is gone, so an entry on its case is treated as new.
    verify_restatements(
        [entry for entry in base if case_id(entry) not in dropped],
        entries,
        rejudged,
        cases_dir,
    )
    verify_adjudications_keep_judge_verdicts(entries, cases_dir)
    if applied:
        pending = path.with_name(path.name + ".amending")
        pending.write_text(text)
        os.replace(pending, path)
    return entries


def amend_annotations(rows, cases, amendments: list[dict]) -> None:
    """Apply the listed case-note and row-annotation amendments in place.

    Each must find exactly one row, and its old text exactly once in it.
    """
    for item in amendments:
        if item["field"] == "reasoning":
            continue
        country, scenario, variable = item["case_id"].split("__", 2)
        frame = cases if item["field"] == "case_annotation" else rows
        mask = (
            (frame["country"].astype(str) == country)
            & (frame["scenario_id"].astype(str) == scenario)
            & (frame["variable"].astype(str) == variable)
        )
        if item["field"] == "annotation":
            mask &= frame["model"].astype(str) == item["model"]
        require(
            int(mask.sum()) == 1,
            f"a wording amendment of {item['case_id']} {item['field']} "
            f"matches {int(mask.sum())} rows; exactly one is required",
        )
        index = frame.index[mask][0]
        frame.loc[index, item["field"]] = amend_text(
            str(frame.loc[index, item["field"]]),
            [item],
            f"{item['case_id']} {item['field']}",
        )


def annotation_csv_text(frame) -> str:
    """The bytes triage writes for the row annotations or the case notes, and
    the freeze rebuilds: every column, in collect_audit's row order."""
    return frame.to_csv(index=False)


def resolve_live_base(args) -> dict:
    """The 20261014 payload an export compares the incumbents against.

    Before the freeze the live pointer and the committed snapshot are
    20261014's, and resolve_base checks all of them. After the freeze they are
    this release's own, so a re-export (after a fix to the staged annotations)
    reads the 20261014 run payload from BASE_COMMIT instead and checks that it
    rewraps to the 20261014 release asset (BASE_SHA256). Any other pointer is
    refused.
    """
    pointer = live_pointer()
    if pointer["tag"] == BASE_TAG:
        return resolve_base(args)[2]
    require(
        pointer["tag"] == RELEASE_TAG,
        "base pointer changed; review the base before staging",
    )
    return base_payload_from_commit()


def resolved_model_id(route: str) -> str:
    """The model id a provider's responses report for a registry route.

    OpenRouter reports its own id, the route after "openrouter/" (Muse
    Wonder's rows say "meta/muse-wonder"); a first-party provider reports the
    bare model id, the route's last segment (Gemini 4 Argon's rows say
    "gemini-4-argon").
    """
    if route.startswith("openrouter/"):
        return route.removeprefix("openrouter/")
    return route.split("/")[-1]


def prepare_inputs(args, runs, base, reference) -> tuple[Path, dict]:
    """Copy immutable inputs and fold full or explicitly partial cohorts."""
    import pandas as pd

    from policybench.config import MODELS as registry
    from policybench.config import PRICE_OVERRIDES_PER_1M
    from policybench.fold_board import fold_board

    stage = args.stage_dir
    frames = {}
    provenance = {}
    for run in runs:
        frame = pd.read_csv(run.predictions, low_memory=False)
        verify_call_provenance(frame, run.model)
        verify_usage(frame, run.model)
        if args.partial:
            frame = frame.drop(columns=["raw_response"], errors="ignore")
        households = set(frame.scenario_id)
        require(
            len(households) == run.state["total"],
            f"state/CSV household mismatch: {run.model}",
        )
        require(
            households <= set(reference.scenario_id), f"unknown households: {run.model}"
        )
        validate_keys(
            frame, reference[reference.scenario_id.isin(households)], run.model
        )
        require(
            run.model in registry and run.model in PRICE_OVERRIDES_PER_1M,
            f"missing model registration/pricing: {run.model}",
        )
        if not args.partial:
            require(
                run.state["total"] == 100 and households == set(reference.scenario_id),
                f"full release requires 100 households: {run.model}",
            )
            require(
                not run.state.get("synthetic_partial"),
                "synthetic run state is partial only",
            )
            fingerprint = run.state.get("treatment_fingerprint")
            require(
                isinstance(fingerprint, dict)
                and fingerprint.get("model_id") == registry[run.model],
                f"missing/mismatched treatment fingerprint: {run.model}",
            )
            import freeze_snapshot as freezer
            from freeze_gpt61sol import validate_treatment

            validate_treatment(
                freezer,
                run.state,
                run.run_dir / "run_state.json",
                SNAPSHOT / "scenarios.csv",
            )
        for field in (
            "provider_resolved_model",
            "provider_response_id",
        ):
            require(
                field in frame and frame[field].notna().all(),
                f"missing {field}: {run.model}",
            )
        expected_provider = resolved_model_id(registry[run.model])
        require(
            set(frame.provider_resolved_model) == {expected_provider},
            f"unexpected provider-resolved model: {run.model}",
        )
        target = stage / "inputs" / run.slug
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(run.predictions, target / "predictions.csv")
        shutil.copyfile(run.run_dir / "run_state.json", target / "run_state.json")
        frames[run.model] = frame
        provenance[run.model] = {
            "households": len(households),
            "rows": len(frame),
            "predictions_sha256": digest(target / "predictions.csv"),
            "treatment_fingerprint": run.state.get("treatment_fingerprint"),
            "provider_resolved_models": sorted(
                frame.provider_resolved_model.dropna().unique()
            ),
            "provider_system_fingerprints": sorted(
                frame.get("provider_system_fingerprint", pd.Series(dtype=str))
                .dropna()
                .unique()
            ),
        }
    shared = set.intersection(*(set(frame.scenario_id) for frame in frames.values()))
    require(bool(shared), "no households completed by every addition")
    selected = (
        reference[reference.scenario_id.isin(shared)] if args.partial else reference
    )
    scoring = stage / "scoring"
    scoring.mkdir(exist_ok=True)
    for name in REFERENCE_FILES:
        shutil.copyfile(SNAPSHOT / name, scoring / name)
    if args.partial:
        selected.to_csv(scoring / "reference_outputs.csv", index=False)
        meta = json.loads((scoring / "reference_outputs.csv.meta.json").read_text())
        meta.update(
            reference_csv_sha256=digest(scoring / "reference_outputs.csv"),
            row_count=len(selected),
            partial=True,
        )
        write_json(scoring / "reference_outputs.csv.meta.json", meta)
        scenarios = pd.read_csv(scoring / "scenarios.csv")
        scenarios[scenarios.scenario_id.isin(shared)].to_csv(
            scoring / "scenarios.csv", index=False
        )
        exclusions = json.loads((scoring / "reference_exclusions.json").read_text())
        exclusions["exclusions"] = [
            e for e in exclusions["exclusions"] if e["scenario_id"] in shared
        ]
        write_json(scoring / "reference_exclusions.json", exclusions)
        base = base[base.scenario_id.isin(shared)]
    else:
        verify_reference_pins(scoring, "staged reference")
    base_path = stage / "base-predictions.csv"
    base.to_csv(base_path, index=False)
    additions = []
    for run in runs:
        path = stage / "inputs" / run.slug / "fold.csv"
        frames[run.model][frames[run.model].scenario_id.isin(shared)].to_csv(
            path, index=False
        )
        additions.append(path)
    result = fold_board(base_path, additions, scoring, stage / "fold", export=False)
    require(
        not result["excluded"] and result["models"] == BOARD_MODELS,
        f"fold refused additions: {result}",
    )
    bundle = stage / "publish" / RUN_NAME
    us = bundle / "us"
    us.mkdir(parents=True, exist_ok=True)
    require(
        not (us / "by_model").exists(), "by_model would shadow combined predictions"
    )
    shutil.copyfile(stage / "fold/us/predictions.csv", us / "predictions.csv")
    if not args.partial:
        restore_run_row_text(us / "predictions.csv", runs)
    for name in REFERENCE_FILES:
        shutil.copyfile(scoring / name, us / name)
    annotations = bundle / "annotations"
    annotations.mkdir(exist_ok=True)
    for name in ANNOTATION_FILES:
        # Re-preparing must not overwrite a recorded stage adjudication.
        if not (annotations / name).exists():
            shutil.copyfile(ANNOTATIONS / name, annotations / name)
    write_json(stage / "model-provenance.json", provenance)
    return bundle, frames


def partial_scores(args, base, reference, frames) -> None:
    """Rank each addition against incumbents on its own completed households."""
    import pandas as pd

    from policybench.analysis import analyze_no_tools
    from policybench.reference_exclusions import (
        load_reference_exclusions,
        split_reference,
    )

    scored, _ = split_reference(reference, load_reference_exclusions(SNAPSHOT))
    scenarios = pd.read_csv(SNAPSHOT / "scenarios.csv")
    results = []
    for model, frame in frames.items():
        ids = set(frame.scenario_id)
        cohort = pd.concat([base[base.scenario_id.isin(ids)], frame], ignore_index=True)
        analysis = analyze_no_tools(
            scored[scored.scenario_id.isin(ids)],
            cohort,
            scenarios=scenarios[scenarios.scenario_id.isin(ids)],
        )
        stats = analysis["bounded_summary"].set_index("model")
        exact = float(stats.loc[model, "weighted_exact"])
        rank = 1 + int((stats.weighted_exact > exact).sum())
        result = {
            "label": "PARTIAL",
            "model": model,
            "households": len(ids),
            "scored_outputs": int(scored.scenario_id.isin(ids).sum()),
            "exact_percent": exact * 100,
            "rank": rank,
            "models": len(stats),
        }
        results.append(result)
        print(json.dumps(result))
    write_json(args.stage_dir / "partial-scores.json", results)


def seed_prompt_digests(audit: Path) -> dict[str, str]:
    """The sha256 of every prompt a case carries, keyed by case id."""
    return {
        case.name: digest(case / "prompt.md")
        for case in sorted((audit / "cases").glob("*"))
        if (case / "prompt.md").is_file()
    }


def seed_digest(audit: Path) -> dict[str, dict[str, str]]:
    """Each judged case's prompt and verdict sha256, keyed by case id."""
    seed = {}
    for case in sorted((audit / "cases").glob("*")):
        if not (case / "prompt.md").is_file():
            continue
        require((case / "verdict.json").is_file(), f"seed case unjudged: {case.name}")
        seed[case.name] = {
            "prompt_sha256": digest(case / "prompt.md"),
            "verdict_sha256": digest(case / "verdict.json"),
        }
    return seed


def seed_digest_text(seed: dict[str, dict[str, str]]) -> str:
    """The seed digest as docs/terra/seed_digest.csv spells it."""
    rows = [
        f"{case},{item['prompt_sha256']},{item['verdict_sha256']}\n"
        for case, item in sorted(seed.items())
    ]
    return "case_id,prompt_sha256,verdict_sha256\n" + "".join(rows)


def verify_seed(seed: dict[str, dict[str, str]]) -> None:
    """The seed must be the 20261014 audit the committed digest records."""
    require(
        hashlib.sha256(seed_digest_text(seed).encode()).hexdigest()
        == SEED_DIGEST_SHA256,
        "the audit seed is not release 20261014's (see docs/terra/"
        "seed_digest.csv): its cases, prompts or verdicts differ",
    )


def load_seed(stage: Path) -> dict[str, dict[str, str]]:
    """The seed stage.json binds, checked against the committed digest.

    It also re-derives which cases are kept, changed and added from the
    stage's prompts and that seed, and refuses unless prompt-changes.json
    says the same: a kept case's prompt that drifts, a case moved between
    the lists, or a manifest whose wrong models the staged predictions do not
    bear out, stops every step that relies on them.
    """
    receipt = json.loads((stage / "stage.json").read_text())
    require(
        "seed" in receipt,
        "stage.json does not bind the audit seed; run --step bind-seed "
        "--audit-seed <the 20261014 audit>",
    )
    verify_seed(receipt["seed"])
    verify_prompt_changes(stage, receipt["seed"])
    return receipt["seed"]


def verify_prompt_changes(stage: Path, seed: dict[str, dict[str, str]]) -> None:
    """prompt-changes.json must be what the stage's prompts say against the seed.

    A case whose prompt is the seed's is kept, one whose prompt differs is
    changed and one the seed lacks is added; a new model must be among the
    wrong models of every changed or added case, and no seed case may vanish
    (check_prompt_changes, as prepare applies it). With an engine upgrade
    installed, a case whose reference value or explanation the installed
    revision changed may change or appear without it (upgraded_cases, derived
    from the staged files against release 20261014's in git). The staged
    predictions must agree (verify_reopened_by_predictions).
    """
    evidence = verify_parse_failure_flags(stage)
    derived = check_prompt_changes(
        stage / "audit",
        {case: item["prompt_sha256"] for case, item in seed.items()},
        upgraded=upgraded_cases(stage),
    )
    recorded = json.loads((stage / PROMPT_CHANGES).read_text())
    differ = sorted(
        {
            case
            for key in ("kept", "changed", "added")
            for case in set(derived[key]) ^ set(recorded.get(key, []))
        }
    )
    require(
        not differ,
        f"{PROMPT_CHANGES} disagrees with the stage's prompts and the bound "
        f"seed on {len(differ)} cases: {differ[:8]}",
    )
    verify_reopened_by_predictions(stage, derived, evidence=evidence)


def verify_parse_failure_flags(stage: Path):
    """A parse-only case has no numeric prediction among its actual wrong rows."""
    import pandas as pd

    from policybench.audit import _case_id, _load_manifest
    from policybench.case_annotations import wrong_prediction_rows

    us = stage / "publish" / RUN_NAME / "us"
    require_combined_predictions(us.parent)
    wrong = wrong_prediction_rows(us)
    manifest = _load_manifest(stage / "audit")
    parse_only = {
        _case_id(us.name, str(scenario), str(variable)): bool(
            pd.to_numeric(rows["prediction"], errors="coerce").isna().all()
        )
        for (scenario, variable), rows in wrong.groupby(KEY, sort=False)
    }
    differ = [
        case
        for case, row in manifest.items()
        if case not in parse_only
        or row.get("parse_failure_only") is not parse_only[case]
    ]
    require(
        not differ,
        "audit parse_failure_only disagrees with staged predictions: "
        f"{sorted(differ)[:8]}",
    )
    return wrong, manifest


def verify_reopened_by_predictions(
    stage: Path, derived: dict[str, list], *, evidence: tuple | None = None
) -> None:
    """The manifest's claim that a new model re-opened a case must hold.

    cases.jsonl is editable, so re-score the staged predictions against the
    staged references with wrong_prediction_rows, the rule prepare_audit
    used to list each case's wrong models. A changed or added case must list
    the new model exactly when its prediction is wrong; any other case it
    gets wrong must be parse-failure-only as the manifest records it, so a
    kept case needs the new model's prediction right. The staged references
    are the installed engine upgrade's when one is installed, so a case the
    upgrade re-opened without the new model (its prediction right on the new
    reference) passes, and one the upgrade made it miss must list it.
    """
    from policybench.audit import _case_id

    us = stage / "publish" / RUN_NAME / "us"
    wrong, manifest = (
        verify_parse_failure_flags(stage) if evidence is None else evidence
    )
    reopened = {*derived["changed"], *derived["added"]}
    parse_only = {case for case, row in manifest.items() if row["parse_failure_only"]}
    differ = set()
    for model in MODELS.values():
        rows = wrong[wrong.model == model]
        missed = {
            _case_id(us.name, str(scenario), str(variable))
            for scenario, variable in zip(rows.scenario_id, rows.variable)
        }
        differ |= {
            case
            for case in reopened
            if (model in manifest[case]["wrong_models"]) != (case in missed)
        }
        differ |= missed - reopened - parse_only
    require(
        not differ,
        f"the audit manifest's wrong models disagree with the staged "
        f"predictions of {sorted(MODELS.values())} on {len(differ)} cases: "
        f"{sorted(differ)[:8]}",
    )


def bind_seed(args) -> None:
    """Bind the seed in the stage.json of a stage prepared before prepare did.

    The seed must match the committed digest, and the stage must agree with it
    case by case: every kept case keeps the seed's prompt and verdict bytes,
    every changed case's prompt differs, and no added case is a seed case.
    """
    receipt_path = args.stage_dir / "stage.json"
    if not receipt_path.is_file():
        receipt_path = args.stage_dir / "reference-install.json"
        require(
            receipt_path.is_file(),
            "bind-seed needs an installed build or prepared stage",
        )
        receipt = json.loads(receipt_path.read_text())
        require(
            "seed" not in receipt, "reference-install.json already binds its audit seed"
        )
        require(args.audit_seed is not None, "bind-seed needs --audit-seed")
        seed = seed_digest(args.audit_seed)
        verify_seed(seed)
        receipt["seed"] = seed
        write_json(receipt_path, receipt)
        print(f"Bound the audit seed before prepare: {len(seed)} judged cases")
        return
    receipt = json.loads(receipt_path.read_text())
    require("seed" not in receipt, "stage.json already binds its audit seed")
    require(args.audit_seed is not None, "bind-seed needs --audit-seed")
    seed = seed_digest(args.audit_seed)
    verify_seed(seed)
    changes = json.loads((args.stage_dir / PROMPT_CHANGES).read_text())
    cases = args.stage_dir / "audit" / "cases"
    differ = [
        case
        for case in changes["kept"]
        if case not in seed
        or not (cases / case / "verdict.json").is_file()
        or digest(cases / case / "prompt.md") != seed[case]["prompt_sha256"]
        or digest(cases / case / "verdict.json") != seed[case]["verdict_sha256"]
    ]
    differ += [
        case
        for case in changes["changed"]
        if case not in seed
        or digest(cases / case / "prompt.md") == seed[case]["prompt_sha256"]
    ]
    differ += [case for case in changes["added"] if case in seed]
    differ += sorted(set(seed) - {*changes["kept"], *changes["changed"]})
    require(
        not differ,
        f"the stage disagrees with the seed on {len(differ)} cases: {differ[:8]}",
    )
    receipt["seed"] = seed
    write_json(receipt_path, receipt)
    print(f"Bound the audit seed: {len(seed)} judged cases")


def reworded_since_seed() -> frozenset[str]:
    """The cases whose committed reference explanation differs between the
    seed's release (SEED_RELEASE_COMMIT) and the base (BASE_COMMIT).

    Refuses unless they are exactly REWORDED_SINCE_SEED, so a change to any
    other explanation since the seed stops prepare instead of re-opening a
    case nobody reviewed.
    """
    import io

    import pandas as pd

    def explanations(commit: str) -> dict[tuple[str, str], tuple]:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{commit}:{REFERENCE_EXPLANATIONS}"],
            capture_output=True,
        )
        require(
            result.returncode == 0,
            f"cannot read {REFERENCE_EXPLANATIONS} at {commit[:12]}: "
            f"{result.stderr.decode().strip()}",
        )
        frame = pd.read_csv(io.BytesIO(result.stdout), dtype=str, keep_default_na=False)
        return {
            (row.scenario_id, row.variable): tuple(row)
            for row in frame.itertuples(index=False)
        }

    before = explanations(SEED_RELEASE_COMMIT)
    after = explanations(BASE_COMMIT)
    require(set(before) == set(after), "explanation keys changed since the seed")
    derived = frozenset(
        f"us__{scenario}__{variable}"
        for (scenario, variable), row in after.items()
        if before[(scenario, variable)] != row
    )
    require(
        derived == REWORDED_SINCE_SEED,
        "reference explanations changed since the seed outside the pinned "
        f"set: {sorted(derived ^ REWORDED_SINCE_SEED)}",
    )
    return derived


def check_prompt_changes(
    audit: Path, seeded: dict[str, str], upgraded: frozenset[str] = frozenset()
) -> dict[str, list]:
    """Only a case a new model joins, or one release 20261014 reworded,
    may change or appear.

    The seed's prompts re-render byte-identically from release 20261014's
    committed snapshot (SEED_RELEASE_COMMIT) and the pinned grounding, so an
    incumbent-only case whose prompt differs (or that is new) means an input
    changed under the
    carried-over verdicts, unless its reference explanation is one release
    20261014 reworded (reworded_since_seed), or its reference value or
    explanation is one an installed engine upgrade changed (``upgraded``,
    upgraded_cases); that case is re-judged.
    """
    manifest = [
        json.loads(line) for line in (audit / "cases.jsonl").read_text().splitlines()
    ]
    prompts = {
        item["case_id"]: digest(audit / "cases" / item["case_id"] / "prompt.md")
        for item in manifest
        if not item["parse_failure_only"]
    }
    return classify_prompt_changes(
        manifest, prompts, seeded, reworded_since_seed(), upgraded
    )


def classify_prompt_changes(
    manifest: list[dict],
    prompts: dict[str, str],
    seeded: dict[str, str],
    reworded: frozenset[str],
    upgraded: frozenset[str] = frozenset(),
) -> dict[str, list]:
    """check_prompt_changes' rule on a manifest and its prompts' sha256.

    install-references applies it to the audit it is about to write, so it
    refuses before it writes anything.
    """
    new_models = set(MODELS.values())
    changed, added, kept, offending = [], [], [], []
    for item in manifest:
        if item["parse_failure_only"]:
            continue
        case_id = item["case_id"]
        prompt = prompts[case_id]
        if seeded.get(case_id) == prompt:
            kept.append(case_id)
            continue
        (changed if case_id in seeded else added).append(case_id)
        if (
            not new_models & set(item["wrong_models"])
            and case_id not in reworded
            and case_id not in upgraded
        ):
            offending.append(case_id)
    require(
        not offending,
        "incumbent-only case prompts changed against the seed (grounding, "
        f"references or annotations differ): {offending[:8]}",
    )
    # Adding a model cannot remove a wrong answer, so every judged seed case
    # must still be a case.
    vanished = sorted(set(seeded) - {*kept, *changed})
    require(not vanished, f"seed cases vanished from the audit: {vanished[:8]}")
    unrendered = sorted(reworded - set(changed))
    require(
        not unrendered,
        f"reworded cases whose prompts did not change: {unrendered[:8]}",
    )
    return {"kept": kept, "changed": changed, "added": added}


def prepare_cases(args, bundle) -> dict[str, dict[str, str]]:
    """Seed a private audit; changed prompts invalidate copied verdicts.

    Returns the seed digest, which main binds in stage.json.
    """
    from policybench.audit import prepare_audit

    require(
        args.audit_seed is not None and args.grounding is not None,
        "prepare needs --audit-seed and --grounding (read-only sources)",
    )
    require(
        digest(args.grounding) == GROUNDING_SHA256,
        "grounding differs from the one the 20260929 audit was rendered with",
    )
    require_combined_predictions(bundle)
    audit = args.stage_dir / "audit"
    # Compare against the read-only seed so a retried
    # prepare cannot mistake its own earlier rendering for the seed.
    seed = seed_digest(args.audit_seed)
    verify_seed(seed)
    seeded = {case: item["prompt_sha256"] for case, item in seed.items()}
    if not audit.exists():
        for source in sorted((args.audit_seed / "cases").glob("*")):
            if not (source / "prompt.md").is_file():
                continue
            target = audit / "cases" / source.name
            target.mkdir(parents=True)
            for name in ("prompt.md", "verdict.json", "verdict.meta.json", "codex.log"):
                if (source / name).is_file():
                    shutil.copyfile(source / name, target / name)
    lookup = grounding_lookup(args.grounding)
    prepare_audit(
        bundle / "us",
        audit,
        grounding_lookup=lookup,
        template_version=JUDGE_TEMPLATE_VERSION,
    )
    changes = check_prompt_changes(audit, seeded)
    write_json(
        args.stage_dir / "prompt-changes.json",
        {key: sorted(value) for key, value in changes.items()},
    )
    pending = validate_verdicts(audit, remove_invalid=True, seed=seed)
    write_json(args.stage_dir / "pending.json", pending)
    print(
        f"Prepared audit: {len(changes['kept'])} prompts unchanged, "
        f"{len(changes['changed'])} changed and {len(changes['added'])} new; "
        f"{len(pending)} cases need Opus 5.5"
    )
    return seed


def set_aside(audit: Path, case_id: str, reason: str) -> None:
    """Move a case's verdict, sidecar and judge evidence out of the audit.

    They go to <stage>/rejected-verdicts/<case>/<UTC time>/ with the judge's
    envelope, log and transcript, so a re-judge never destroys the verdict it
    replaces or the record of how it was made.
    """
    from datetime import datetime, timezone

    case = audit / "cases" / case_id
    names = (
        "verdict.json",
        "verdict.meta.json",
        "claude.json",
        "claude.log",
        "claude.transcript.jsonl",
    )
    files = [case / name for name in names]
    if not any(path.exists() for path in files[:2]):
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = audit.parent / "rejected-verdicts" / case_id / stamp
    target.mkdir(parents=True)
    (target / "reason.txt").write_text(reason + "\n")
    for path in files:
        if path.exists():
            os.replace(path, target / path.name)


def judge_identity_problems(meta: dict) -> list[str]:
    """Why a sidecar does not show this release's judge; [] if it does.

    The judge step requests JUDGE_MODEL through JUDGE_RUNNER, which records
    the request, the models the CLI reports having used (that model alone),
    itself, and the moment the verdict was written as an ISO 8601 timestamp
    in UTC (judged_at_utc).
    """
    from datetime import datetime, timedelta

    problems = []
    if meta.get("judge_model_requested") != JUDGE_MODEL:
        problems.append(
            f"judge_model_requested {meta.get('judge_model_requested')!r}; "
            f"expected {JUDGE_MODEL!r}"
        )
    if meta.get("judge_model_reported") != [JUDGE_MODEL]:
        problems.append(
            f"judge_model_reported {meta.get('judge_model_reported')!r}; "
            f"expected {[JUDGE_MODEL]!r}"
        )
    if meta.get("judge_runner") != JUDGE_RUNNER:
        problems.append(
            f"judge_runner {meta.get('judge_runner')!r}; expected {JUDGE_RUNNER!r}"
        )
    stamp = meta.get("judged_at_utc")
    try:
        moment = datetime.fromisoformat(stamp) if isinstance(stamp, str) else None
    except ValueError:
        moment = None
    if moment is None or moment.utcoffset() != timedelta(0):
        problems.append(f"judged_at_utc {stamp!r} is not an ISO 8601 timestamp in UTC")
    return problems


def verify_verdict_inventory(audit: Path) -> tuple[str, ...]:
    """Refuse verdicts outside the manifest's judged case directories.

    Parse-only cases have no judge, so their directories cannot contribute
    verdicts either. The release receipt binds this manifest and every listed
    judged case; no other directory may become published provenance.
    """
    manifest = audit / "cases.jsonl"
    judged = (
        {
            item["case_id"]
            for item in map(json.loads, manifest.read_text().splitlines())
            if not item["parse_failure_only"]
        }
        if manifest.is_file()
        else set()
    )
    cases = audit / "cases"
    verdicts = {
        str(path.parent.relative_to(cases))
        for path in cases.rglob("verdict.json")
        if path.is_file()
    }
    if cases.is_dir():
        # Include direct symlinked directories, which rglob does not recurse
        # into but the shared whole-tree tally would otherwise discover.
        verdicts.update(
            str(directory.relative_to(cases))
            for directory in cases.iterdir()
            if (directory / "verdict.json").is_file()
        )
    extra = sorted(verdicts - judged)
    require(
        not extra,
        "verdict-bearing directories are not manifest-listed judged cases: "
        f"{extra[:8]}",
    )
    return tuple(sorted(judged))


def validate_verdicts(
    audit: Path,
    remove_invalid: bool = False,
    seed: dict[str, dict[str, str]] | None = None,
) -> list[str]:
    """Validate schema, model coverage and each verdict's binding to its bytes.

    Every judged verdict's sidecar must carry the verdict's own sha256. A case
    whose prompt is the seed's (``seed``, as stage.json binds it) carries its
    seed verdict over: the verdict must be the seed's, byte for byte, and any
    prompt_sha256 its sidecar records must match. Every other verdict is new
    and must record the sha256 of the prompt it judged and template
    JUDGE_TEMPLATE_VERSION. Every judged case's prompt must begin with the
    header of the version its sidecar records
    (policybench.audit.template_version_problems), so a new verdict's sidecar
    cannot claim v2 for a prompt rendered on another version. Every new
    verdict, and any verdict naming a new model, also needs this release's
    judge identity (judge_identity_problems): a case re-opened because the
    installed build moved its reference is held to it even when only
    incumbents answered it wrong. Every non-carried verdict also needs the
    hardened runner's isolation, token authentication and a transcript bound
    to its prompt and answer (judge_isolation_problems). Returns the pending cases;
    ``remove_invalid`` sets their verdicts aside. A carried-over verdict that
    fails is refused outright: a re-judge cannot restore it.
    """
    import jsonschema

    from policybench.audit import template_version_problems
    from policybench.judge_template import recorded_template_version

    schema = json.loads((audit / "schema.json").read_text())
    manifest = {
        item["case_id"]: item
        for item in map(json.loads, (audit / "cases.jsonl").read_text().splitlines())
    }
    seed = seed or {}
    templates = dict(template_version_problems(audit))
    pending, refused = [], []
    for case_id, item in manifest.items():
        if item["parse_failure_only"]:
            continue
        path = audit / "cases" / case_id / "verdict.json"
        meta_path = path.with_name("verdict.meta.json")
        prompt = path.with_name("prompt.md")
        carried = (
            case_id in seed
            and prompt.is_file()
            and digest(prompt) == seed[case_id]["prompt_sha256"]
        )
        try:
            blob = path.read_bytes()
            verdict = json.loads(blob)
            jsonschema.validate(verdict, schema)
            names = [m["model"] for m in verdict["models"]]
            if len(names) != len(set(names)) or set(names) != set(item["wrong_models"]):
                raise ValueError("wrong model coverage")
            meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
            if not isinstance(meta, dict):
                raise ValueError("verdict provenance is not an object")
            if meta.get("verdict_sha256") != hashlib.sha256(blob).hexdigest():
                raise ValueError("the sidecar is not bound to this verdict")
            if case_id in templates:
                raise ValueError(f"judge template: {templates[case_id]}")
            bound = meta.get("prompt_sha256")
            if carried:
                if hashlib.sha256(blob).hexdigest() != seed[case_id]["verdict_sha256"]:
                    raise ValueError("a carried-over verdict is not the seed's")
                if bound is not None and bound != digest(prompt):
                    raise ValueError("verdict is bound to a different prompt")
            elif bound != digest(prompt):
                raise ValueError("a new verdict is not bound to this prompt")
            elif recorded_template_version(meta) != JUDGE_TEMPLATE_VERSION:
                # A new or re-opened case is rendered on this release's
                # template, and its judge must have read that version: the
                # sidecar records it, and the prompt's header (checked above)
                # is that version's.
                raise ValueError(
                    f"a new verdict is not on judge template v{JUDGE_TEMPLATE_VERSION}"
                )
            # Every verdict judged for this release, whichever models it names:
            # a case the installed build re-opened may list incumbents alone.
            if not carried or set(names) & set(MODELS.values()):
                identity = judge_identity_problems(meta)
                if identity:
                    raise ValueError(
                        "missing or mismatched Opus 5.5 provenance: "
                        + "; ".join(identity)
                    )
            if not carried:
                isolation = judge_isolation_problems(
                    path.parent, meta, prompt.read_bytes(), verdict
                )
                if isolation:
                    raise ValueError(
                        "missing or invalid judge isolation: " + "; ".join(isolation)
                    )
        except (OSError, ValueError, jsonschema.ValidationError) as error:
            if carried:
                refused.append(f"{case_id} ({error})")
                continue
            pending.append(case_id)
            if remove_invalid:
                set_aside(audit, case_id, f"invalid: {error}")
    require(
        not refused,
        f"{len(refused)} carried-over verdicts differ from the seed's; a stage "
        f"input changed after prepare: {refused[:4]}",
    )
    return sorted(pending)


def account_data(value, at: str, keys: bool = True) -> list[str]:
    """Where ``value`` carries an e-mail address or a key naming an account.

    Any key that matches ACCOUNT_KEY (unless ``keys`` is false), and any key
    or string that holds an e-mail address (EMAIL_ADDRESS), at any depth;
    ``at`` names ``value``.
    """
    hits = []
    if isinstance(value, dict):
        for key, item in value.items():
            where = f"{at}.{key}"
            if keys and ACCOUNT_KEY.search(str(key)):
                hits.append(f"key {where}")
            if EMAIL_ADDRESS.search(str(key)):
                hits.append(f"an e-mail address in key {where}")
            hits += account_data(item, where, keys)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits += account_data(item, f"{at}[{index}]", keys)
    elif isinstance(value, str) and EMAIL_ADDRESS.search(value):
        hits.append(f"an e-mail address at {at}")
    return hits


def outside_the_judge(event: dict, prompt: str | None) -> dict:
    """``event`` without the judged prompt's own user message or the judge's
    words: the text of a user event that is exactly ``prompt``, and the content
    of an assistant turn. The account-data rule reads everything else."""
    message = event.get("message")
    if isinstance(message, dict) and (
        event.get("type") == "assistant"
        or (
            event.get("type") == "user"
            and prompt is not None
            and message.get("content") == prompt
        )
    ):
        rest = {key: value for key, value in message.items() if key != "content"}
        return {**event, "message": rest}
    return event


def transcript_problems(
    path: Path, effort: str | None, prompt: bytes, verdict: object
) -> list[str]:
    """Why a judge's transcript does not show an isolated judge; [] if it does.

    A Python port of the transcript checks in scripts/run_audit_claude.sh
    (extract_verdict): no tool call but StructuredOutput, no event of a type
    outside its EVENT_TYPES (JUDGE_EVENT_TYPES), no context attachment outside
    its ATTACHMENTS (JUDGE_ATTACHMENTS; so no skill listing and no
    credential_org record), a session context that is empty (no account e-mail
    or git status), no account data anywhere outside the prompt's own user
    message and the judge's own turns (account_data, outside_the_judge), no
    working directory inside a git repository, every assistant turn at the
    effort the sidecar records, when it records one (the sidecars of the
    stage's first 17 isolated verdicts record none), no advisor model, and
    user events that are exactly one text message, the case's ``prompt``
    (prompt.md's bytes, decoded as UTF-8), besides Claude Code's own nudge
    (JUDGE_PROMPT_NUDGE) and the results of the judge's StructuredOutput calls.
    It also requires exactly one accepted StructuredOutput call, whose input
    is the published ``verdict`` (verdict.json, parsed): any other call must
    be one the schema refused, which the judge then answered again.
    """
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return ["no transcript"]
    try:
        text = prompt.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    problems, calls, refused = [], [], set()
    # The user events: text messages (the prompt) and everything else (which
    # may only answer the judge's own StructuredOutput calls, by id).
    texts, others, answers = [], [], set()

    def answer(part: dict) -> bool:
        return part.get("type") == "tool_use" and part.get("name") == "StructuredOutput"

    for number, line in enumerate(lines, 1):
        try:
            event = json.loads(line)
        except ValueError:
            problems.append(f"transcript line {number} is not JSON")
            continue
        if not isinstance(event, dict):
            problems.append(f"transcript line {number} is not an event")
            continue
        if event.get("type") not in JUDGE_EVENT_TYPES:
            problems.append(f"an event of type {event.get('type')!r}")
        problems += account_data(outside_the_judge(event, text), f"line {number}")
        if event.get("type") == "attachment":
            attachment = event.get("attachment") or {}
            kind = attachment.get("type")
            if kind not in JUDGE_ATTACHMENTS:
                problems.append(f"a {kind!r} attachment")
            if kind == "environment" and (attachment.get("snapshot") or {}).get(
                "isGitRepo"
            ):
                problems.append("a working directory inside a git repository")
            context = attachment.get("context")
            if kind == "session_context" and context != {}:
                carried = sorted(context) if isinstance(context, dict) else context
                problems.append(f"a session context carrying {carried!r}")
        if event.get("type") == "assistant":
            if effort is not None and event.get("effort") != effort:
                problems.append(f"a turn at effort {event.get('effort')!r}")
            if event.get("advisorModel"):
                problems.append(f"advisor model {event.get('advisorModel')!r}")
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if event.get("type") == "user":
            if not isinstance(content, str):
                others.append(content)
            elif not (event.get("isMeta") is True and content == JUDGE_PROMPT_NUDGE):
                texts.append(content)
        for part in content if isinstance(content, list) else []:
            if not isinstance(part, dict):
                continue
            if str(part.get("type", "")).endswith("tool_use"):
                calls.append(part)
                if event.get("type") == "assistant" and answer(part):
                    answers.add(part.get("id"))
            elif part.get("type") == "tool_result" and part.get("is_error"):
                refused.add(part.get("tool_use_id"))

    structured = [part for part in calls if answer(part)]
    other = [part.get("name") or part.get("type") for part in calls if not answer(part)]
    if other:
        problems.append(f"tool calls {other}")
    accepted = [part for part in structured if part.get("id") not in refused]
    if len(accepted) != 1:
        problems.append(
            f"{len(accepted)} accepted StructuredOutput calls; exactly 1 is required"
        )
    elif json.dumps(accepted[0].get("input"), sort_keys=True) != json.dumps(
        verdict, sort_keys=True
    ):
        problems.append("its accepted StructuredOutput answer is not verdict.json")
    if len(texts) != 1:
        problems.append(f"{len(texts)} user text messages; only the prompt is allowed")
    elif text is None or texts[0] != text:
        problems.append("its user message is not prompt.md")
    if not all(
        isinstance(content, list)
        and content
        and all(
            isinstance(part, dict)
            and part.get("type") == "tool_result"
            and part.get("tool_use_id") in answers
            for part in content
        )
        for content in others
    ):
        problems.append("a user event that is not a StructuredOutput call's result")
    return problems


def judge_isolation_problems(
    case: Path, meta: dict, prompt: bytes, verdict: object
) -> list[str]:
    """Every verdict judged for this release uses the hardened token runner."""
    problems = []
    if "judge_isolation" not in meta:
        problems.append("the verdict is not isolated (sidecar lacks judge_isolation)")
    auth = meta.get("judge_auth")
    if not isinstance(auth, dict) or auth.get("method") != "oauth_token":
        problems.append(
            "the sidecar does not record a token login (judge_auth "
            f"method oauth_token): {auth!r}"
        )
    problems += transcript_problems(
        case / "claude.transcript.jsonl", meta.get("judge_effort"), prompt, verdict
    )
    return problems


def withhold_addresses(value):
    """``value`` with every e-mail address in it replaced by WITHHELD_ADDRESS."""
    if not isinstance(value, str):
        return value
    return EMAIL_ADDRESS.sub(WITHHELD_ADDRESS, value)


def verify_judge_provenance(
    cases_dir: Path, rejudged: frozenset[str], record_path: Path
) -> None:
    """The published judge provenance must describe the staged new verdicts.

    The record (JUDGE_PROVENANCE) lists every case a new model re-opened, each
    once, with its verdict's and prompt's sha256, its group and whether its
    judge ran isolated, and its sidecar's judge_effort, judge_model_reported,
    judged_at_utc and judge_account_declared (JUDGE_SIDECAR_FIELDS), an
    e-mail address in any of them withheld as WITHHELD_ADDRESS. The record and
    each entry carry exactly their listed keys (JUDGE_PROVENANCE_KEYS,
    JUDGE_PROVENANCE_ENTRY_KEYS), its counts are the tally of the entries'
    groups, and it names no e-mail address anywhere, for it is public. Each
    entry's hashes must be the staged verdict's and prompt's, and its other
    fields its sidecar's. Its group must be PROVENANCE_GROUPS' group for the
    sidecar's declared account; an unlisted account is refused. Every entry
    must be isolated: its sidecar records
    judge_isolation from scripts/run_audit_claude.sh's hardened runner, and
    its group says "isolated: ". Every verdict's sidecar must record a token login
    (judge_auth.method oauth_token), and its transcript,
    claude.transcript.jsonl, must pass the runner's transcript checks
    (transcript_problems), its prompt and verdict included: the one user
    text message must be the staged prompt.md, and the one accepted
    StructuredOutput answer the staged verdict.json. The record's note must
    be the one its entries give (provenance_note), so it states nothing the
    entries do not record.
    """
    record = json.loads(record_path.read_text())
    entries = record.get("verdicts") if isinstance(record, dict) else None
    require(
        isinstance(entries, list) and all(isinstance(e, dict) for e in entries),
        f"{JUDGE_PROVENANCE_PATH} lists no verdicts",
    )
    require(
        set(record) == JUDGE_PROVENANCE_KEYS,
        f"{JUDGE_PROVENANCE_PATH} has keys {sorted(record)}; expected "
        f"{sorted(JUDGE_PROVENANCE_KEYS)}",
    )
    addresses = account_data(record, "record", keys=False)
    require(
        not addresses,
        f"{JUDGE_PROVENANCE_PATH} is public and names {addresses[:4]}; withhold "
        f"each e-mail address as {WITHHELD_ADDRESS!r}",
    )
    named = [entry.get("case_id") for entry in entries]
    require(
        len(named) == len(set(named)) and set(named) == set(rejudged),
        f"{JUDGE_PROVENANCE_PATH} does not list each re-opened case once: "
        f"{sorted(set(named) ^ set(rejudged))[:4]}",
    )
    tally: dict = {}
    for entry in entries:
        group = entry.get("group")
        tally[group] = tally.get(group, 0) + 1
    require(
        record["counts"] == tally,
        f"{JUDGE_PROVENANCE_PATH} counts {record['counts']!r} are not the tally "
        f"of its entries' groups {tally!r}",
    )
    require(
        record["note"] == provenance_note(entries),
        f"{JUDGE_PROVENANCE_PATH}'s note is not the one its entries give "
        f"(provenance_note): {record['note']!r}",
    )
    wrong = []
    for entry in entries:
        case = cases_dir / entry["case_id"]
        try:
            meta = json.loads((case / "verdict.meta.json").read_text())
            verdict = json.loads((case / "verdict.json").read_text())
            prompt = (case / "prompt.md").read_bytes()
            problems = []
            if entry.get("verdict_sha256") != digest(case / "verdict.json"):
                problems.append("the record names another verdict")
            if entry.get("prompt_sha256") != hashlib.sha256(prompt).hexdigest():
                problems.append("the record names another prompt")
        except (OSError, ValueError) as error:
            wrong.append(f"{entry['case_id']}: {error}")
            continue
        if set(entry) != JUDGE_PROVENANCE_ENTRY_KEYS:
            problems.append(f"the entry has keys {sorted(entry)}")
        meta = meta if isinstance(meta, dict) else {}
        for field in JUDGE_SIDECAR_FIELDS:
            expected = withhold_addresses(meta.get(field))
            if entry.get(field) != expected:
                problems.append(
                    f"its {field} {entry.get(field)!r} is not the sidecar's "
                    f"{expected!r}"
                )
        isolated = "judge_isolation" in meta
        group = entry.get("group")
        if not isinstance(group, str) or group.startswith("isolated: ") != isolated:
            problems.append(f"its group {group!r} disagrees with its isolation")
        declared = meta.get("judge_account_declared")
        if not isinstance(declared, str) or declared not in PROVENANCE_GROUPS:
            problems.append("no provenance group for the sidecar's declared account")
        elif group != PROVENANCE_GROUPS[declared]:
            problems.append(
                f"its group {group!r} is not the declared account's group "
                f"{PROVENANCE_GROUPS[declared]!r}"
            )
        if entry.get("isolated") is not isolated:
            problems.append(
                f"the record says isolated={entry.get('isolated')!r} but the "
                f"sidecar {'records' if isolated else 'lacks'} judge_isolation"
            )
        problems += judge_isolation_problems(case, meta, prompt, verdict)
        if problems:
            wrong.append(f"{entry['case_id']}: {'; '.join(problems)}")
    require(
        not wrong,
        f"{len(wrong)} new verdicts disagree with {JUDGE_PROVENANCE_PATH}: {wrong[:4]}",
    )


# The allowed provenance groups, by the account a sidecar declares. They
# include Max's 2026-09-30 pb-judge opt-in and the two Subfleet lanes earlier
# releases borrowed. The generated record states which groups judged this
# release's cases.
PROVENANCE_GROUPS = {
    "claude setup-token login (token sha256 6a6daf56361b), Max 2026-09-30": (
        "isolated: setup-token 2"
    ),
    "claude:max@axiom.org (subfleet lane claude-18)": (
        "isolated: subfleet lane claude-18"
    ),
    "claude:max@farness.ai (subfleet lane claude-10)": (
        "isolated: subfleet lane claude-10"
    ),
}


def _tally_phrase(entries: list[dict], field: str, label) -> str:
    """How many ``entries`` give each spelling (``label``) of ``field``, in
    the spellings' order; "none" when there are no entries."""
    counts: dict[str, int] = {}
    for entry in entries:
        spelled = label(entry.get(field))
        counts[spelled] = counts.get(spelled, 0) + 1
    if not counts:
        return "none"
    return ", ".join(
        f"{spelled} ({count})" for spelled, count in sorted(counts.items())
    )


def _reported_models(value) -> str:
    if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
        return " and ".join(value)
    return "none reported" if value in (None, []) else repr(value)


def provenance_note(entries: list[dict]) -> str:
    """The judge provenance record's note, every claim in it read from
    ``entries``.

    It says what the record lists and what verify_judge_provenance checks of
    each entry, and tallies what the entries' sidecar fields record: the
    judge model each reports, the effort and judge template each records, and
    whether each judge ran isolated. The logins are the record's counts, by
    the group of the account each sidecar declares. It states no schedule,
    concurrency or retry history, which no record carries.
    """
    return (
        f"Provenance of the {len(entries)} new judge verdicts in the GPT-6.1 "
        "Terra stage: the cases it re-opened, because GPT-6.1 Terra joined a "
        "case or the installed reference build changed a reference value or "
        "explanation it shows. Each entry gives its verdict's and prompt's "
        "sha256 and the fields its sidecar (verdict.meta.json) records. Judge "
        "model reported: "
        f"{_tally_phrase(entries, 'judge_model_reported', _reported_models)}. "
        "Effort recorded: "
        + _tally_phrase(
            entries,
            "judge_effort",
            lambda value: value if isinstance(value, str) else "none recorded",
        )
        + ". Judge template: "
        + _tally_phrase(
            entries,
            "judge_template_version",
            lambda value: f"v{value}" if isinstance(value, int) else "none recorded",
        )
        + ". Isolation: "
        + _tally_phrase(
            entries,
            "isolated",
            lambda value: "isolated" if value is True else "not isolated",
        )
        + ". An isolated entry's sidecar records the isolation "
        f"{JUDGE_RUNNER} ran its judge under (judge_isolation) and a token "
        "login (judge_auth method oauth_token), and its transcript passes the "
        "runner's checks. Counts are by the group of the account each sidecar "
        "declares."
    )


def judge_provenance_record(cases_dir: Path, rejudged: frozenset[str]) -> dict:
    """The record verify_judge_provenance checks, built from the sidecars."""
    entries = []
    for case_id in sorted(rejudged):
        case = cases_dir / case_id
        meta = json.loads((case / "verdict.meta.json").read_text())
        declared = meta.get("judge_account_declared")
        require(
            declared in PROVENANCE_GROUPS,
            f"{case_id}: no provenance group for the declared account",
        )
        require("judge_isolation" in meta, f"{case_id}: the verdict is not isolated")
        entry = {
            "case_id": case_id,
            "group": PROVENANCE_GROUPS[declared],
            "isolated": True,
            **{
                field: withhold_addresses(meta.get(field))
                for field in JUDGE_SIDECAR_FIELDS
            },
            "verdict_sha256": digest(case / "verdict.json"),
            "prompt_sha256": digest(case / "prompt.md"),
        }
        entries.append(entry)
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["group"]] = counts.get(entry["group"], 0) + 1
    return {"note": provenance_note(entries), "counts": counts, "verdicts": entries}


def write_judge_provenance(args) -> None:
    """Verify a candidate from the sidecars, then replace JUDGE_PROVENANCE."""
    import tempfile

    cases = args.stage_dir / "audit" / "cases"
    rejudged = rejudged_cases(args.stage_dir)
    require(
        not validate_verdicts(args.stage_dir / "audit", seed=load_seed(args.stage_dir)),
        "missing or invalid verdicts; run judge",
    )
    # json.dumps(indent=1), as release 20260930's docs/gpt61sol record is.
    record = json.loads(
        json.dumps(judge_provenance_record(cases, rejudged), sort_keys=True)
    )
    with tempfile.TemporaryDirectory(
        prefix=".terra-judge-provenance-", dir=JUDGE_PROVENANCE.parent
    ) as scratch:
        candidate = Path(scratch) / JUDGE_PROVENANCE.name
        candidate.write_text(json.dumps(record, indent=1, allow_nan=False) + "\n")
        verify_judge_provenance(cases, rejudged, candidate)
        os.replace(candidate, JUDGE_PROVENANCE)
    print(f"Wrote {JUDGE_PROVENANCE_PATH}: {len(rejudged)} verdicts")


def judge(args, bundle) -> None:
    """Run one Claude CLI judge at a time and retry missing/hedged cases."""
    from policybench.audit import collect_audit

    audit = args.stage_dir / "audit"
    seed = load_seed(args.stage_dir)
    for _ in range(3):
        validate_verdicts(audit, remove_invalid=True, seed=seed)
        subprocess.run(
            ["bash", str(ROOT / JUDGE_RUNNER), str(audit)],
            cwd=ROOT,
            env={
                **os.environ,
                "AUDIT_MODEL": JUDGE_MODEL,
                "AUDIT_PARALLEL": "1",
                "AUDIT_PYTHON": sys.executable,
            },
            check=True,
        )
        pending = validate_verdicts(audit, remove_invalid=True, seed=seed)
        out = collect_audit(bundle / "us", audit)
        for case_id in out["hedged"].case_id:
            set_aside(audit, case_id, "hedged")
        if not pending and out["missing"].empty and out["hedged"].empty:
            return
    raise SystemExit(
        "audit missing/hedged after three passes; resume judge after investigation"
    )


def triage(args, bundle) -> None:
    """Collect, apply recorded decisions, and stop for unresolved flags."""
    from policybench.adjudications import (
        apply_adjudications,
        excluded_case_keys,
        verify_adjudications_applied,
    )
    from policybench.audit import collect_audit
    from policybench.reference_exclusions import (
        exclusion_keys,
        load_reference_exclusions,
    )

    audit = args.stage_dir / "audit"
    require(
        not validate_verdicts(audit, seed=load_seed(args.stage_dir)),
        "missing or invalid verdicts; run judge",
    )
    out = collect_audit(bundle / "us", audit)
    require(
        out["missing"].empty and out["hedged"].empty, "missing/hedged audit; run judge"
    )
    rows = out["row"]
    cases = out["case"].rename(
        columns={
            "case_failure_source": "case_failure_sources",
            "case_failure_subtype": "case_failure_subtypes",
        }
    )
    counts = rows.groupby(KEY).size()
    require(
        all(
            int(r.wrong_model_count) == counts[(r.scenario_id, r.variable)]
            for r in cases.itertuples()
        ),
        "case wrong_model_count disagrees with collected rows",
    )
    annotations = bundle / "annotations"
    rejudged = rejudged_cases(args.stage_dir)
    amendments = load_amendments(args.stage_dir, rejudged)
    upgrade = stage_upgrade(args.stage_dir)
    decisions = stage_adjudications(
        annotations / ADJUDICATIONS,
        rejudged,
        amendments,
        audit / "cases",
        regenerated=frozenset() if upgrade is None else upgrade.regenerated_ruled,
        dropped=frozenset() if upgrade is None else upgrade.dropped_cases,
        added=upgrade_decisions(upgrade),
        triage=triage_items(upgrade),
    )
    rows, cases, _ = apply_adjudications(rows, cases, decisions)
    amend_annotations(rows, cases, amendments)
    # An amendment may not touch the adjudication sentence a case note carries.
    verify_adjudications_applied(rows, cases, decisions)
    excluded = exclusion_keys(load_reference_exclusions(bundle / "us"))
    require(
        excluded == excluded_case_keys(decisions),
        "adjudication exclusions differ from frozen scoring exclusions",
    )
    flags = cases[cases.reference_suspect.astype(bool)]
    scored = ~rows[KEY].apply(tuple, axis=1).isin(excluded)
    unresolved = rows[
        scored
        & ~rows.failure_source.isin(
            [
                "llm_error",
                "parse_contract_failure",
                "budget_exhausted_at_ceiling",
            ]
        )
    ]
    flags.to_csv(args.stage_dir / "reference-flags.csv", index=False)
    unresolved.to_csv(args.stage_dir / "unresolved-rows.csv", index=False)
    for name, frame in (
        ("us_audit_row_annotations.csv", rows),
        ("us_case_notes.csv", cases),
    ):
        (annotations / name).write_text(annotation_csv_text(frame), encoding="utf-8")
    require(
        flags.empty and unresolved.empty,
        "triage required: inspect reference-flags.csv/unresolved-rows.csv; "
        "record evidence in staged us_adjudications.json and rerun triage",
    )
    print(f"Triage complete: {len(rows)} rows / {len(cases)} cases")


def incumbent_drift(stats: list[dict], previous: dict[str, dict]) -> list[str]:
    """Incumbents whose modelStats entry is not byte-identical to the base's.

    Serialized as the payload serializes it, so key order counts as well as
    values. A missing incumbent counts as drift.
    """
    exported = {row["model"]: row for row in stats}
    return sorted(
        model
        for model, row in previous.items()
        if model not in exported
        or json.dumps(exported[model], allow_nan=False)
        != json.dumps(row, allow_nan=False)
    )


def payload_text(payload: dict) -> str:
    """The bytes export writes for a payload, and the freeze rebuilds.

    freeze_snapshot reassembles these exact default-json bytes from the
    compact country payload. Pretty-printing here breaks its release hash.
    """
    return json.dumps(payload, allow_nan=False)


def build_payload(
    bundle: Path,
    live: dict,
    *,
    partial: bool = False,
    early: bool = False,
    upgrade: Upgrade | None = None,
    outputs: dict[str, bytes] | None = None,
) -> dict:
    """Compute and validate every export in a disposable copy of its inputs."""
    import tempfile

    from release_20261006 import EXPORT_INPUTS

    require_combined_predictions(bundle)
    with tempfile.TemporaryDirectory(prefix="export-terra-") as scratch:
        working = Path(scratch) / bundle.name
        for relative in EXPORT_INPUTS:
            target = working / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundle / relative, target)
        payload = _build_payload_in_scratch(
            working, live, partial=partial, early=early, upgrade=upgrade
        )
        if outputs is not None:
            generated = [working / "us/data.json"]
            generated.extend((working / "us/analysis").rglob("*"))
            outputs.update(
                {
                    str(p.relative_to(working)): p.read_bytes()
                    for p in generated
                    if p.is_file()
                }
            )
    return payload


def _build_payload_in_scratch(
    bundle: Path,
    live: dict,
    *,
    partial: bool = False,
    early: bool = False,
    upgrade: Upgrade | None = None,
) -> dict:
    """The payload export writes, built from ``bundle``; the one definition.

    export_full_run's US payload must hold all 51 models. For a release, its
    roster must be the base's incumbents plus the addition, Fable 5's usage is
    carried from ``live`` (CARRIED_USAGE), and no incumbent may drift; then the
    dashboard schema. The freeze rebuilds the staged payload with this.
    export_full_run writes data.json, us/data.json and us/analysis/ into
    its disposable ``bundle``.

    With an engine upgrade installed (``upgrade``) the scope check is two-sided:
    (a) with release 20261014's references and exclusion record both put back,
    every incumbent's modelStats is release 20261014's byte for byte; (b)
    every model is scored on 1,984 outputs less the build's exclusion count.
    """
    from policybench.dashboard_schema import validate_dashboard_payload
    from policybench.full_run_export import export_full_run

    require_combined_predictions(bundle)
    payload = export_full_run(bundle, countries=["us"], skip_app_data=True)
    stats = payload["countries"]["us"]["modelStats"]
    require(
        len(stats) == BOARD_MODELS,
        f"export did not contain all {BOARD_MODELS} models",
    )
    previous = {m["model"]: m for m in live["countries"]["us"]["modelStats"]}
    if not partial:
        require(
            len(previous) == BASE_MODELS and not set(previous) & set(MODELS.values()),
            f"base must hold the {BASE_MODELS} incumbents only",
        )
        require(
            {s["model"] for s in stats} == set(previous) | set(MODELS.values()),
            "export roster is not the incumbents plus the addition",
        )
        for model, keys in CARRIED_USAGE.items():
            row = next(s for s in stats if s["model"] == model)
            for key in keys:
                row[key] = previous[model][key]
        scored = {row["model"]: row["n"] for row in stats}
        expected = RELEASE_SCORED if upgrade is None else upgrade.scored_outputs
        require(
            set(scored.values()) == {expected},
            f"every model must be scored on {expected} outputs: {scored}",
        )
        # The scope check puts back release 20261014's exclusion record and,
        # with an upgrade installed, its references. Every incumbent's stats
        # must then equal the base byte for byte. This confines score changes
        # to the reviewed build's references and exclusion record.
        import tempfile

        from release_20261006 import export_payload

        with tempfile.TemporaryDirectory() as scratch:
            record = Path(scratch) / "reference_exclusions.json"
            record.write_text(exclusions_text(base_exclusion_record()))
            if upgrade is None:
                scoped = export_payload(bundle, live, record)
            else:
                scoped = export_on_base_references(bundle, live, record)
        scoped_stats = scoped["countries"]["us"]["modelStats"]
        require(len(scoped_stats) == BOARD_MODELS, "scope export lost a model")
        drift = incumbent_drift(scoped_stats, previous)
        put_back = (
            "exclusion record" if upgrade is None else "references and exclusion record"
        )
        require(
            not drift,
            f"with release 20261014's {put_back}, incumbent modelStats drift: {drift}",
        )
        if upgrade is not None:
            # Recompute on the approved build too. Together with the restored
            # base and unchanged predictions this permits only its four moves.
            allowed = export_payload(bundle, live)
            allowed_stats = {
                row["model"]: row
                for row in allowed["countries"]["us"]["modelStats"]
                if row["model"] in previous
            }
            drift = incumbent_drift(stats, allowed_stats)
            require(
                set(allowed_stats) == set(previous) and not drift,
                f"incumbent drift beyond the four approved reference moves: {drift}",
            )
    errors = validate_dashboard_payload(payload, require_failure_annotations=not early)
    require(not errors, f"payload validation failed: {errors[:8]}")
    if partial:
        payload["stage2Status"] = (
            "PARTIAL — incomplete household cohorts; release gates were skipped"
        )
    return payload


def export(args, bundle, live) -> dict:
    """Export into scratch, preserve incumbent statistics, and gate release."""
    require_combined_predictions(bundle)
    if not args.early:
        verify_verdict_inventory(args.stage_dir / "audit")
    upgrade = None if args.partial else stage_upgrade(args.stage_dir)
    if not args.partial and upgrade is None:
        # After the freeze the pointer and committed record are this release's.
        release = release_exclusions_sha256()
        frozen = live_pointer()["tag"] == RELEASE_TAG
        verify_reference_pins(
            SNAPSHOT, "committed reference", release if frozen else None
        )
        verify_reference_pins(bundle / "us", "staged reference", release)
    elif upgrade is not None:
        # The staged references are the installed build's (BASE_REFERENCE_SHA256
        # stays release 20261014's); the committed ones are release 20261014's
        # until the freeze and the build's after it.
        pins = upgraded_reference_pins(upgrade)
        frozen = live_pointer()["tag"] == RELEASE_TAG
        verify_reference_pins(
            SNAPSHOT, "committed reference", pins=pins if frozen else None
        )
        verify_reference_pins(bundle / "us", "staged reference", pins=pins)
    if not args.early:
        verify_parse_failure_flags(args.stage_dir)
        verify_new_model_inputs(args.stage_dir)
        verify_judge_provenance(
            args.stage_dir / "audit" / "cases",
            rejudged_cases(args.stage_dir),
            JUDGE_PROVENANCE,
        )
    outputs = {}
    payload = build_payload(
        bundle,
        live,
        partial=args.partial,
        early=args.early,
        upgrade=upgrade,
        outputs=outputs,
    )
    repository_inputs = None if args.early else repository_input_hashes()
    stats = payload["countries"]["us"]["modelStats"]
    path = args.stage_dir / (
        f"PARTIAL-data-board{BOARD_MODELS}.json"
        if args.partial
        else f"data-board{BOARD_MODELS}.json"
    )
    outputs["us/data.json"] = json.dumps(payload["countries"]["us"]).encode()
    for relative, contents in outputs.items():
        destination = bundle / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
    path.write_text(payload_text(payload))
    # Keep the freeze input identical to the gated payload, including Fable usage.
    shutil.copyfile(path, bundle / "data.json")
    ranked = sorted(stats, key=lambda s: (-s["exact"], -s["score"], s["model"]))
    for index, row in enumerate(ranked, 1):
        if row["model"] in MODELS.values():
            print(
                f"{'PARTIAL common cohort' if args.partial else 'STAGED'} "
                f"{row['model']}: exact={row['exact']:.6f}% "
                f"rank={index}/{BOARD_MODELS} n={row['n']}"
            )
    if not args.early:
        pinned = [p for p in (bundle / "annotations").iterdir() if p.is_file()]
        pinned += [
            bundle / "us" / name for name in (*REFERENCE_FILES, "predictions.csv")
        ]
        pinned += [p for p in (args.stage_dir / "inputs").rglob("*") if p.is_file()]
        # An installed engine upgrade's build, verbatim (absent otherwise).
        pinned += [
            p for p in sorted((args.stage_dir / BUILD_COPY).glob("*")) if p.is_file()
        ]
        # The cases Terra re-opened, the listed wording amendments and the
        # seed binding decide what the adjudication and verdict gates allow;
        # stage.json and model-provenance.json hold the prepare-time hashes.
        pinned += [
            path
            for path in (
                args.stage_dir / PROMPT_CHANGES,
                args.stage_dir / AMENDMENTS,
                args.stage_dir / "stage.json",
                args.stage_dir / "model-provenance.json",
            )
            if path.is_file()
        ]
        pinned += [
            p
            for p in (args.stage_dir / "audit").rglob("*")
            if p.is_file()
            and p.name
            in {
                "verdict.json",
                "verdict.meta.json",
                "prompt.md",
                "claude.transcript.jsonl",
                "cases.jsonl",
                "schema.json",
            }
        ]
        write_json(
            args.stage_dir / "release-ready.json",
            {
                "release_tag": RELEASE_TAG,
                "base_tag": BASE_TAG,
                "base_sha256": BASE_SHA256,
                "payload_sha256": digest(path),
                "models": BOARD_MODELS,
                "partial": False,
                "files": {
                    str(p.relative_to(args.stage_dir)): digest(p) for p in pinned
                },
                # A repository file, so outside "files", which binds stage files.
                "judge_provenance": {
                    "path": JUDGE_PROVENANCE_PATH,
                    "sha256": digest(JUDGE_PROVENANCE),
                },
                "repository_inputs": repository_inputs,
            },
        )
    return payload


# --- An engine upgrade of the references (--step install-references) ---------
#
# Max, 2026-09-28: "we should be using the latest pe for this always!" The
# release installs the reviewed move from policyengine-us 2.41.0 to 2.60.0.
# The 2026-10-22 audit's builder reads release 20261014's references from
# git and recomputes all 1,984 outputs. Its committed build changes four
# scored outputs and rechecks sixteen exclusions while retaining all 49.
# The narratives script rebuilds the four changed explanations from the
# hand-corrected texts. install-references gates the build against the base
# and installs it; every later release step requires that exact build.

BUILT_FILES = (
    "reference_outputs.csv",
    "reference_outputs.csv.meta.json",
    "reference_exclusions.json",
    "reference_traces.json",
)
CSV_NAME, META_NAME, EXCLUSIONS_NAME, TRACES_NAME = BUILT_FILES
# The reference files a build replaces in the stage's scoring source and
# bundle; scenarios.csv and its sidecar keep their 20261014 pins.
UPGRADED_FILES = (CSV_NAME, META_NAME, EXCLUSIONS_NAME)
EXPLANATIONS_NAME = "us_case_reference_explanations.csv"
ACTIONS_NAME = "final_actions.json"
# The stage directory that keeps the installed build verbatim: the four built
# files, the regenerated explanations and the build's actions. Later steps
# re-gate it, and export binds it.
BUILD_COPY = "reference-build"
BUILD_COPY_FILES = (*BUILT_FILES, EXPLANATIONS_NAME, ACTIONS_NAME)
# All inputs that identify this reviewed build live in one table. Repointing
# a later audit requires reviewing this entire binding, including narratives.
REFERENCE_BUILD = {
    "directory": Path("reference_audit/2026-10-22-engine-upgrade"),
    "engine_version": "policyengine-us 2.60.0",
    "builder_sha256": (
        "d4b00204390c6ada97bdf91358dc3d60ae3307d101062b8982fa62923cc9c645"
    ),
    "narratives_script_sha256": (
        "c65edf7d7ae8d3ae222c397234842752087cbc793dddf7f6de1b4d306deaf6e0"
    ),
    "corrections_sha256": (
        "1376018aa24a324a9a4b006177961bd3de94ae98e28614cae0766f72c40021c7"
    ),
    "sha256": {
        CSV_NAME: "eab09a0c184c14b0c33679d9ac132d6f1de720c439ac30685a67ca38655184cb",
        META_NAME: "55c17fe298f9ac09ff56b2187d1d314ede7d239e94924da6abb6e0ad2542260c",
        EXCLUSIONS_NAME: (
            "91408c0f3d49e1984b436164a047f8cedc3e501feb2099ba0e7d2782ee8ac73d"
        ),
        TRACES_NAME: "fbb47dc29251389d9d3aa13c556c906df74fc0874e916889bce4fad8c93add99",
        EXPLANATIONS_NAME: (
            "47c33db094072c97ca18bb763526767c9fc23ecc50d153951be54b43182bc5e4"
        ),
        ACTIONS_NAME: (
            "93fc088f0d2617e9e6d5bf5f0b65e4e8709d46bdd64da12e5cb9d92c06c8fd21"
        ),
    },
}


def committed_build_sources(out: Path) -> tuple[Path, Path, Path]:
    """Rebuild the four narratives offline from the committed audited inputs."""
    audit = ROOT / REFERENCE_BUILD["directory"]
    built = audit / BUILD_COPY
    sources = {
        **{built / name: REFERENCE_BUILD["sha256"][name] for name in BUILT_FILES},
        audit / ACTIONS_NAME: REFERENCE_BUILD["sha256"][ACTIONS_NAME],
        audit / "scripts/build_references_upgrade.py": REFERENCE_BUILD[
            "builder_sha256"
        ],
        audit / "scripts/narratives_upgrade.py": REFERENCE_BUILD[
            "narratives_script_sha256"
        ],
        audit / "hand_corrected_narratives.json": REFERENCE_BUILD["corrections_sha256"],
    }
    for path, pin in sources.items():
        require(
            path.is_file() and digest(path) == pin,
            f"committed build input off its pin: {path}",
        )
        require(
            path.read_bytes() == head_blob(path.relative_to(ROOT).as_posix()),
            f"build input differs from HEAD: {path}",
        )
    corrections = json.loads((audit / "hand_corrected_narratives.json").read_text())
    meta = json.loads((built / META_NAME).read_text())
    changed = {
        f"{item['scenario_id']}|{item['variable']}"
        for item in meta["revisions"][-1]["changed"]
    }
    require(
        set(corrections) == changed,
        "every changed narrative must be hand-corrected; no writer call is permitted",
    )
    out.mkdir(parents=True, exist_ok=True)
    explanations = out / EXPLANATIONS_NAME
    # Use the audited script's pure hand-correction rewrite. Its CLI imports
    # the writer SDK even for supplied texts; this path loads no writer and
    # cannot make an API call or an import-time pricing request.
    previous_path = list(sys.path)
    previous_builder = sys.modules.pop("build_references_upgrade", None)
    try:
        sys.path.insert(0, str(audit / "scripts"))
        module = runpy.run_path(str(audit / "scripts/narratives_upgrade.py"))
        traces = json.loads((built / TRACES_NAME).read_text())
        rewrites = {}
        for item in meta["revisions"][-1]["changed"]:
            key = spec_key(item)
            listed = "|".join(key)
            text = corrections[listed]
            require(
                not module["missing_amounts"](item, text),
                f"hand-corrected narrative omits its new reference: {listed}",
            )
            rewrites[key] = (
                item["regenerated"],
                len(traces[listed]["trace"].splitlines()),
                text,
            )
        explanations.write_text(
            module["rewrite_explanations"](
                base_explanations_bytes().decode("utf-8"), rewrites
            )
        )
        require(
            digest(explanations) == REFERENCE_BUILD["sha256"][EXPLANATIONS_NAME],
            "rebuilt narratives are off their pin",
        )
    finally:
        sys.path[:] = previous_path
        sys.modules.pop("build_references_upgrade", None)
        if previous_builder is not None:
            sys.modules["build_references_upgrade"] = previous_builder
    return built, explanations, audit / ACTIONS_NAME


# Release 20261014's reference explanations, us_case_reference_explanations.csv
# as committed at BASE_COMMIT.
BASE_EXPLANATIONS_SHA256 = (
    "0e6797d079d41858b960117f54027bdc9681999daafa6f278fd57f2884f9e534"
)
# The engine release 20261014's references were computed on: its sidecar's last
# revision, the 2026-10-13 engine_upgrade.
BASE_ENGINE = "policyengine-us 2.41.0"
ENGINE_PREFIX = "policyengine-us "
# The sidecar fields a build rewrites; every other field must stay 20261014's.
SIDECAR_REWRITTEN = frozenset(
    {"policyengine_bundles", "reference_csv_sha256", "regenerated_at_utc", "revisions"}
)
# A regenerated record's output must come back within this of the record's
# alternative_value, the value its exclusion said the law gives.
REGENERATION_TOLERANCE = 1.0
# An excluded output keeps the value it was decided on (rule 5); the loader's
# own tolerance for a record's frozen_value (verify_exclusions_against_reference).
FROZEN_TOLERANCE = 1e-3
# How far an approved move's engine value may sit from the value its action
# approves: the builder's APPROVED_TOL, half a cent.
APPROVED_TOLERANCE = 0.005


@dataclass(frozen=True)
class Baseline:
    """What a build is gated against: release 20261014's reference files and
    explanations, read from git and pinned; the release's ruled records, as
    build_release_exclusions spells them (record_edits applied); and the ruled
    outputs the spec says an engine upgrade regenerates (spec_regenerated)."""

    files: dict
    explanations: bytes
    ruled: dict
    regenerated: frozenset


@dataclass(frozen=True)
class Upgrade:
    """An installed, gated engine upgrade of the references.

    ``changed`` maps each output whose reference the build moved to its new
    value. ``regenerated_base`` and ``regenerated_ruled`` are the release
    20261014 records and ruled records the build regenerated (scored again);
    ``added`` the records it newly excludes. ``records`` counts the build's
    exclusion record, ``exclusions_text`` is its bytes, and ``sha256`` binds
    each of BUILD_COPY_FILES.
    """

    engine_version: str
    previous_engine_version: str
    revision: dict
    changed: dict
    regenerated_base: frozenset
    regenerated_ruled: frozenset
    added: frozenset
    records: int
    exclusions_text: str
    sha256: dict

    @property
    def regenerated(self) -> frozenset:
        return self.regenerated_base | self.regenerated_ruled

    @property
    def scored_outputs(self) -> int:
        return BASE_OUTPUTS - self.records

    @property
    def upgraded_cases(self) -> frozenset[str]:
        """The audit cases whose reference value or explanation it changed."""
        return frozenset(output_case(key) for key in self.changed)

    @property
    def dropped_cases(self) -> frozenset[str]:
        """The cases whose release 20261014 decision it drops (#178)."""
        return frozenset(output_case(key) for key in self.regenerated_base)


def output_case(key: tuple[str, str]) -> str:
    """The audit case id of a US output."""
    return f"us__{key[0]}__{key[1]}"


def base_reference_bytes(name: str) -> bytes:
    """A release 20261014 reference file, read from BASE_COMMIT and pinned."""
    raw = base_commit_blob(Path("paper/snapshot/20260501/runs") / RUN_NAME / name)
    require(
        hashlib.sha256(raw).hexdigest() == BASE_REFERENCE_SHA256[name],
        f"release 20261014's {name} does not match its pin",
    )
    return raw


def base_explanations_bytes() -> bytes:
    """Release 20261014's reference explanations, read from BASE_COMMIT."""
    raw = base_commit_blob(REFERENCE_EXPLANATIONS)
    require(
        hashlib.sha256(raw).hexdigest() == BASE_EXPLANATIONS_SHA256,
        f"release 20261014's {EXPLANATIONS_NAME} does not match its pin",
    )
    return raw


def spec_regenerated(spec: dict) -> frozenset[tuple[str, str]]:
    """The ruled outputs an installed engine upgrade regenerates.

    docs/terra/spec.json's regenerated_by_upgrade.outputs names them; every
    other ruled output stays excluded (kept). Each must be a ruled record with
    reason code reference_engine_defect: an upgrade can fix the engine, never
    an unlisted input or a figure published after the freeze. The field is
    read only with an upgrade installed; an absent field names none.
    """
    from policybench.reference_exclusions import ENGINE_DEFECT

    section = spec.get("regenerated_by_upgrade")
    if section is None:
        return frozenset()
    outputs = section.get("outputs") if isinstance(section, dict) else None
    require(
        isinstance(outputs, list)
        and all(
            isinstance(o, list) and len(o) == 2 and all(isinstance(p, str) for p in o)
            for o in outputs
        ),
        "the spec's regenerated_by_upgrade.outputs is not a list of "
        "[scenario_id, variable] pairs",
    )
    keys = [tuple(output) for output in outputs]
    require(
        len(set(keys)) == len(keys),
        f"the spec's regenerated_by_upgrade names an output twice: {keys}",
    )
    ruled = {spec_key(record): record for record in spec_records(spec)}
    unknown = sorted(set(keys) - set(ruled))
    require(
        not unknown,
        f"the spec's regenerated_by_upgrade names outputs it does not rule on: "
        f"{unknown}",
    )
    other = sorted(k for k in keys if ruled[k]["reason_code"] != ENGINE_DEFECT)
    require(
        not other,
        "an engine upgrade regenerates only an engine-defect record; the spec's "
        f"regenerated_by_upgrade names {other}",
    )
    return frozenset(keys)


def upgrade_baseline(spec: dict | None = None) -> Baseline:
    """The Baseline a build is gated against, from git and the spec."""
    spec = load_spec() if spec is None else spec
    files = {name: base_reference_bytes(name) for name in UPGRADED_FILES}
    release = build_release_exclusions(json.loads(files[EXCLUSIONS_NAME]), spec)
    ruled_keys = {spec_key(record) for record in spec_records(spec)}
    ruled = {
        spec_key(record): record
        for record in release["exclusions"]
        if spec_key(record) in ruled_keys
    }
    return Baseline(files, base_explanations_bytes(), ruled, spec_regenerated(spec))


def regeneration_lands(variable: str, value: float, alternative: float) -> bool:
    """Whether a regenerated output lands on its audited corrected value:
    within REGENERATION_TOLERANCE ($1, the exact-match tolerance) for an
    amount, equal for a 0/1 flag (policybench.paper_results'
    moves_beyond_tolerance, which the builder applies too)."""
    from policybench.paper_results import moves_beyond_tolerance

    return abs(value - alternative) <= REGENERATION_TOLERANCE and not (
        moves_beyond_tolerance(variable, alternative, value)
    )


def engine_older(older: str, newer: str) -> bool:
    """Whether one 'policyengine-us X.Y.Z' release precedes another."""

    def parts(engine) -> tuple[int, ...] | None:
        if not isinstance(engine, str) or not engine.startswith(ENGINE_PREFIX):
            return None
        try:
            return tuple(int(p) for p in engine.removeprefix(ENGINE_PREFIX).split("."))
        except ValueError:
            return None

    a, b = parts(older), parts(newer)
    return a is not None and b is not None and a < b


# The audited root-cause fix modules a "fix_modules" regeneration target
# names, as committed at BASE_COMMIT; and the upgrade audit's own modules, for
# defects found later, as committed at HEAD (the builder's fix_location). A
# target names such a module's path.
AUDIT_FIXES = Path("reference_audit/2026-09-22/fixes")
LOCAL_FIXES = Path("reference_audit/2026-10-12-engine-upgrade/fixes")


def fix_module_blob(name: str) -> tuple[str, bytes]:
    """A fix module's repository path and committed bytes: under AUDIT_FIXES
    at BASE_COMMIT, or, for one the upgrade audit adds (absent there), under
    LOCAL_FIXES at HEAD."""
    path = AUDIT_FIXES / name
    result = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", f"{BASE_COMMIT}:{path.as_posix()}"],
        capture_output=True,
    )
    if result.returncode == 0:
        return path.as_posix(), base_commit_blob(path)
    return (LOCAL_FIXES / name).as_posix(), head_blob((LOCAL_FIXES / name).as_posix())


TARGET_KEYS = {
    "record": {"kind", "value", "engine"},
    "fix_modules": {
        "kind",
        "value",
        "engine",
        "engine_value",
        "modules",
        "dependencies",
        "evidence",
        "evidence_sha256",
        "value_with_modules",
    },
}


def committed_dependencies(names: list[str]) -> list[str]:
    """The siblings the named fix modules load, transitively, as committed
    (fix_module_blob), in the builder's order: the builder's module_dependencies
    (policybench.fix_module_closure), re-derived here from the committed
    bytes. Raises ClosureError for a module that loads local files any way
    but Path(__file__).with_name("<file>"), and for a sibling whose name
    resolves to another folder than the module's own: the module loads it
    from its own directory, so the pin would name a file other than the one
    that runs."""
    from policybench.fix_module_closure import ClosureError, dependency_closure

    found: list[str] = []
    for name in names:
        read = lambda file: fix_module_blob(file)[1]  # noqa: E731
        home = PurePosixPath(fix_module_blob(name)[0]).parent
        for dep in dependency_closure(name, read):
            where = PurePosixPath(fix_module_blob(dep)[0]).parent
            if where != home:
                raise ClosureError(
                    f"{name} loads {dep} from {home}, but that name is pinned "
                    f"from {where}: a fix module's siblings must be committed "
                    "beside it"
                )
            if dep not in names and dep not in found:
                found.append(dep)
    return found


def regeneration_action_problems(
    key: tuple[str, str], record: dict, entry, action
) -> list[str]:
    """Where a revision's regenerated_exclusions entry departs from the one
    reviewed action that asks for it. The builder copies the action's
    tolerance, upstream and basis, checks its alternative_value against the
    record, and expands its target: a record target to the record's value, a
    fix_modules target to the evidence's for the action's modules and
    evidence file. The gates therefore bind the build to the reviewed action
    and independently check what its revision claims."""
    if not isinstance(action, dict):
        return [f"{key}: the build's actions do not regenerate it exactly once"]
    if not isinstance(entry, dict):
        return [f"{key}: the build's revision does not list it exactly once"]
    problems = []
    tolerance = action.get("tolerance")
    if not _number(tolerance) or not 0 <= tolerance <= REGENERATION_TOLERANCE:
        return [f"{key}: the action's tolerance {tolerance!r} is not in [0, $1]"]
    if not (_number(entry.get("tolerance")) and entry["tolerance"] == tolerance):
        problems.append(
            f"{key}: the revision's tolerance {entry.get('tolerance')!r} is not the "
            f"action's {tolerance!r}"
        )
    if not _same(
        action.get("alternative_value"), record.get("alternative_value"), 1e-6
    ):
        problems.append(f"{key}: the action's alternative_value is not the record's")
    for field in ("upstream", "basis"):
        if entry.get(field) != action.get(field):
            problems.append(f"{key}: the revision's {field} is not the action's")
    asked = action.get("target", {"kind": "record"})
    built = entry.get("target")
    if (
        not isinstance(asked, dict)
        or not isinstance(built, dict)
        or (asked.get("kind") != built.get("kind"))
    ):
        problems.append(f"{key}: the revision's target is not the kind the action asks")
    elif asked.get("kind") == "fix_modules":
        ref = asked.get("evidence")
        modules = built.get("modules")
        names = (
            [m.get("module") for m in modules if isinstance(m, dict)]
            if isinstance(modules, list)
            else None
        )
        if (
            names != asked.get("modules")
            or not isinstance(ref, dict)
            or ref.get("path") != built.get("evidence")
            or ref.get("sha256") != built.get("evidence_sha256")
        ):
            problems.append(
                f"{key}: the revision's fix modules or evidence are not the action's"
            )
    return problems


def regeneration_target_problems(
    key: tuple[str, str],
    record: dict,
    target,
    value: float,
    engine: str,
    tolerance: float = REGENERATION_TOLERANCE,
) -> list[str]:
    """Why a regenerated output's audited target does not hold, re-derived
    from what the build cites (the builder's regeneration_target).

    A "record" target is the record's alternative_value on the record's
    engine. A "fix_modules" target is the corrected value in a committed
    evidence file, at its sha256, computed on an older engine than the build's
    with committed fix modules (fix_module_blob); there the modules moved the
    output beyond the exact-match tolerance (the defect was present), and on
    the build's engine they moved it by no more than REGENERATION_TOLERANCE
    (nothing is left to fix). Either way the build's value lands on it.
    """
    variable = key[1]
    if not isinstance(target, dict) or target.get("kind") not in TARGET_KEYS:
        return [f"{key}: the regeneration names no audited target"]
    kind = target["kind"]
    if set(target) != TARGET_KEYS[kind]:
        return [f"{key}: the {kind} target's fields are {sorted(target)}"]
    if not _number(target["value"]):
        return [f"{key}: the target's value is not a number"]
    problems = []
    if not _number(tolerance) or not 0 <= tolerance <= REGENERATION_TOLERANCE:
        return [f"{key}: the regeneration's tolerance {tolerance!r} is not in [0, $1]"]
    if kind == "record":
        if not _same(target["value"], float(record["alternative_value"])) or (
            target["engine"] != record["engine_version"]
        ):
            problems.append(f"{key}: the record target is not the record's")
    else:
        problems.extend(
            _fix_modules_target_problems(key, target, value, engine, tolerance)
        )
    if not regeneration_lands(variable, value, float(target["value"])) or (
        abs(value - float(target["value"])) > tolerance
    ):
        problems.append(
            f"{key}: regenerated at {value}, outside ${tolerance:g} of its "
            f"audited target {target['value']} ({kind})"
        )
    return problems


def _fix_modules_target_problems(
    key: tuple[str, str],
    target: dict,
    value: float,
    engine: str,
    tolerance: float = REGENERATION_TOLERANCE,
) -> list[str]:
    from policybench.paper_results import moves_beyond_tolerance

    variable = key[1]
    path = target["evidence"]
    if (
        not isinstance(path, str)
        or Path(path).is_absolute()
        or ".." in Path(path).parts
    ):
        return [f"{key}: the evidence path {path!r} is not in the checkout"]
    file = ROOT / path
    if not file.is_file() or digest(file) != target["evidence_sha256"]:
        return [f"{key}: {path} is missing or not the evidence its sha256 pins"]
    try:
        doc = json.loads(file.read_text())
    except ValueError:
        return [f"{key}: {path} is not JSON"]
    problems = []
    if not isinstance(doc, dict) or doc.get("kind") != "regeneration_evidence":
        return [f"{key}: {path} is not regeneration evidence"]
    if doc.get("engine") != target["engine"] or not engine_older(
        target["engine"], engine
    ):
        problems.append(
            f"{key}: the evidence's engine {doc.get('engine')!r} is not the target's, "
            f"or is not older than the build's {engine}"
        )
    modules = target["modules"]

    def pinned(item) -> bool:
        # A module the upgrade audit adds names its path; no other does.
        if not isinstance(item, dict) or not isinstance(item.get("module"), str):
            return False
        local = fix_module_blob(item["module"])[0].startswith(LOCAL_FIXES.as_posix())
        keys = {"module", "sha256", "path"} if local else {"module", "sha256"}
        return set(item) == keys and (
            not local or item["path"] == (LOCAL_FIXES / item["module"]).as_posix()
        )

    if not (isinstance(modules, list) and modules and all(map(pinned, modules))):
        return [*problems, f"{key}: the target lists no fix modules"]
    names = [m["module"] for m in modules]
    from policybench.fix_module_closure import ClosureError

    try:
        closure = committed_dependencies(names)
    except ClosureError as error:
        return [*problems, f"{key}: {error}"]
    expected = []
    for dep in closure:
        where, blob = fix_module_blob(dep)
        item = {"module": dep, "sha256": hashlib.sha256(blob).hexdigest()}
        if where.startswith(LOCAL_FIXES.as_posix()):
            item["path"] = where
        expected.append(item)
    if target["dependencies"] != expected or any(
        doc["modules"].get(item["module"]) != item["sha256"] for item in expected
    ):
        problems.append(
            f"{key}: the target and evidence do not pin the siblings its modules load "
            f"as committed: {[i['module'] for i in expected]}"
        )
    for entry in modules:
        name = entry["module"]
        where, blob = fix_module_blob(name)
        committed = hashlib.sha256(blob).hexdigest()
        if entry["sha256"] != committed or doc["modules"].get(name) != committed:
            problems.append(f"{key}: {name} is not {where} as committed")
    items = [
        item
        for item in doc.get("items", [])
        if isinstance(item, dict)
        and spec_key(item) == key
        and item.get("modules") == names
    ]
    if len(items) != 1:
        return [*problems, f"{key}: {path} has {len(items)} items for {names}"]
    item = items[0]
    if not (
        _same(item.get("engine_value"), target["engine_value"])
        and _same(item.get("corrected_value"), target["value"])
    ):
        problems.append(f"{key}: the target's values are not the evidence's")
    elif not moves_beyond_tolerance(
        variable, float(item["engine_value"]), float(item["corrected_value"])
    ):
        problems.append(
            f"{key}: on {doc['engine']} the modules do not move it, so the evidence "
            "shows no defect"
        )
    # On the build's engine the modules move it by no more than the
    # regeneration's tolerance, as the builder requires.
    after = target["value_with_modules"]
    if (
        not _number(after)
        or not regeneration_lands(variable, float(after), value)
        or abs(float(after) - value) > tolerance
    ):
        problems.append(
            f"{key}: on {engine} the audited fix still moves it: {value} -> {after}"
        )
    return problems


def _number(value) -> bool:
    import math

    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _same(a, b, tolerance: float = 1e-9) -> bool:
    return _number(a) and _number(b) and abs(float(a) - float(b)) <= tolerance


def reference_values(blob: bytes) -> dict[tuple[str, str], float]:
    """Each output's reference value in a reference CSV."""
    import io

    import pandas as pd

    frame = pd.read_csv(io.BytesIO(blob))
    return {
        (str(s), str(v)): float(x)
        for s, v, x in zip(frame.scenario_id, frame.variable, frame.value)
    }


def reference_value_changes(base: bytes, new: bytes) -> dict[tuple[str, str], float]:
    """The outputs whose reference value differs between two reference CSVs.

    The CSVs must hold the same outputs in the same order and the same columns,
    and every column but ``value`` (impact_weight among them) must be equal on
    every row, as PR #182's driver required (reference_revision). Any change
    to a value, however small, counts.
    """
    import io

    import pandas as pd

    before = pd.read_csv(io.BytesIO(base))
    after = pd.read_csv(io.BytesIO(new))
    require(
        list(after.columns) == list(before.columns),
        f"reference columns changed: {list(before.columns)} -> {list(after.columns)}",
    )
    require(
        "value" in before.columns and set(KEY) <= set(before.columns),
        f"the reference CSV lacks {KEY} or value",
    )
    keys = [tuple(map(str, row)) for row in before[KEY].itertuples(index=False)]
    require(
        len(after) == len(before)
        and [tuple(map(str, row)) for row in after[KEY].itertuples(index=False)]
        == keys,
        "the reference CSV's outputs or their order changed",
    )
    for column in before.columns:
        if column in (*KEY, "value"):
            continue
        same = (before[column] == after[column]) | (
            before[column].isna() & after[column].isna()
        )
        moved = [keys[i] for i in range(len(keys)) if not bool(same.iloc[i])]
        require(not moved, f"reference {column} changed: {moved[:5]}")
    values = after["value"].astype(float)
    require(not values.isna().any(), "a reference value is missing")
    base_values = before["value"].astype(float)
    return {
        keys[i]: float(values.iloc[i])
        for i in range(len(keys))
        if float(values.iloc[i]) != float(base_values.iloc[i])
    }


def explanation_rows(blob: bytes, label: str) -> tuple[list[str], list[tuple]]:
    """A reference explanations CSV's header and its (output, row) pairs, as
    text exactly as written."""
    import csv
    import io

    try:
        rows = list(csv.reader(io.StringIO(blob.decode("utf-8"), newline="")))
    except (UnicodeDecodeError, csv.Error) as error:
        raise SystemExit(f"{label} {EXPLANATIONS_NAME} is not a CSV: {error}")
    require(
        bool(rows) and {"scenario_id", "variable"} <= set(rows[0]),
        f"{label} {EXPLANATIONS_NAME} has no scenario_id and variable columns",
    )
    header = rows[0]
    s, v = header.index("scenario_id"), header.index("variable")
    require(
        all(len(row) == len(header) for row in rows[1:]),
        f"{label} {EXPLANATIONS_NAME} has a row of the wrong width",
    )
    return header, [((row[s], row[v]), row) for row in rows[1:]]


def explanation_changes(
    base: bytes, new: bytes
) -> tuple[frozenset[tuple[str, str]], dict[tuple[str, str], dict]]:
    """The outputs whose explanation row differs from release 20261014's, and
    every new row by output.

    The new file must have the base's columns and the base's outputs in the
    base's order; a row is compared field by field as text, so every row the
    narratives did not rewrite must be the base's, byte for byte.
    """
    header, before = explanation_rows(base, "release 20261014's")
    new_header, after = explanation_rows(new, "the build's")
    require(
        new_header == header,
        f"the reference explanations' columns changed: {header} -> {new_header}",
    )
    require(
        [key for key, _ in after] == [key for key, _ in before],
        "the reference explanations' outputs or their order changed",
    )
    differ = frozenset(
        key for (key, row), (_, old) in zip(after, before, strict=True) if row != old
    )
    return differ, {key: dict(zip(header, row)) for key, row in after}


def upgrade_revision(base_meta: dict, meta: dict, csv_sha256: str) -> dict:
    """The build's engine_upgrade revision, once its sidecar is shown to be
    release 20261014's with exactly that revision added.

    Every field but SIDECAR_REWRITTEN keeps 20261014's value, in 20261014's
    order; the sidecar pins the built CSV; release 20261014's revisions stay,
    and one engine_upgrade revision follows them, from BASE_ENGINE to a newer
    policyengine-us that the sidecar's bundle names; the revision lists its
    changes and keeps every excluded output untouched (rule 5).
    """
    require(
        isinstance(meta, dict) and list(meta) == list(base_meta),
        "the build's sidecar does not have release 20261014's fields in order",
    )
    moved = sorted(
        key
        for key in base_meta
        if key not in SIDECAR_REWRITTEN
        and json.dumps(meta[key]) != json.dumps(base_meta[key])
    )
    require(
        not moved,
        f"the build's sidecar changes {moved}; a build rewrites only "
        f"{sorted(SIDECAR_REWRITTEN)}",
    )
    require(
        meta["reference_csv_sha256"] == csv_sha256,
        "the build's sidecar does not pin the built reference CSV",
    )
    require(
        isinstance(meta["regenerated_at_utc"], str),
        "the build's sidecar does not date its regeneration",
    )
    revisions, before = meta["revisions"], base_meta["revisions"]
    require(
        isinstance(revisions, list)
        and len(revisions) == len(before) + 1
        and json.dumps(revisions[:-1]) == json.dumps(before),
        "the build's sidecar does not keep release 20261014's revisions and add one",
    )
    revision = revisions[-1]
    require(
        isinstance(revision, dict) and revision.get("kind") == "engine_upgrade",
        "the build's added revision is not an engine_upgrade",
    )
    previous = before[-1].get("engine_version")
    engine = revision.get("engine_version")
    require(
        isinstance(engine, str)
        and engine.startswith(ENGINE_PREFIX)
        and engine != previous,
        f"the build's revision names no newer engine than {previous}: {engine!r}",
    )
    require(
        revision.get("previous_engine_version") == previous,
        f"the build's revision does not upgrade from {previous}, release "
        f"20261014's engine: {revision.get('previous_engine_version')!r}",
    )
    bundles = meta["policyengine_bundles"]
    require(
        isinstance(bundles, dict)
        and set(bundles) == set(base_meta["policyengine_bundles"])
        and isinstance(bundles.get("us"), dict)
        and bundles["us"].get("model_version") == engine.removeprefix(ENGINE_PREFIX),
        f"the build's sidecar bundle does not name {engine}",
    )
    require(
        revision.get("excluded_outputs_untouched") is True,
        "the build's revision does not keep every excluded output untouched",
    )
    changed = revision.get("changed")
    require(
        isinstance(changed, list)
        and all(
            isinstance(item, dict)
            and isinstance(item.get("scenario_id"), str)
            and isinstance(item.get("variable"), str)
            and _number(item.get("previous"))
            and _number(item.get("regenerated"))
            for item in changed
        ),
        "the build's revision does not list each change's output, previous and "
        "regenerated value",
    )
    rechecked = revision.get("excluded_outputs_rechecked", [])
    require(
        isinstance(rechecked, list)
        and all(
            isinstance(item, dict)
            and isinstance(item.get("scenario_id"), str)
            and isinstance(item.get("variable"), str)
            and _number(item.get("kept_value"))
            for item in rechecked
        ),
        "the build's revision lists a malformed excluded_outputs_rechecked entry",
    )
    return revision


def declared_exclusions(plan: dict) -> dict[tuple[str, str], dict]:
    """The records a build's actions newly exclude: new_exclusions, each the
    record itself, and audit_exclusions, each carrying its record (#182)."""
    require(
        all(
            isinstance(plan.get(name, []), list)
            for name in ("approved", "new_exclusions", "audit_exclusions")
        )
        and isinstance(plan.get("excluded_rechecked", []), list),
        "the build's actions are not lists of actions",
    )
    declared: dict[tuple[str, str], dict] = {}
    items = [
        *((item, item) for item in plan.get("new_exclusions", [])),
        *((item, item.get("exclusion")) for item in plan.get("audit_exclusions", [])),
    ]
    for item, record in items:
        require(
            isinstance(item, dict) and isinstance(record, dict),
            "the build's actions list a malformed new exclusion",
        )
        key = spec_key(item)
        require(
            spec_key(record) == key and key not in declared,
            f"the build's actions list {key} twice or under another output",
        )
        declared[key] = record
    return declared


def upgrade_exclusion_records(
    baseline: Baseline,
    text: str,
    values: dict[tuple[str, str], float],
    changed: dict[tuple[str, str], float],
    plan: dict,
    engine: str,
    revision: dict | None = None,
) -> tuple[list[dict], frozenset, frozenset, frozenset]:
    """The build's exclusion record, gated: the release's record.

    It must be release 20261014's records, minus the ones the build
    regenerated, plus the spec's kept ruled records, plus the records the
    build's actions newly exclude, and nothing else. So the regenerated ruled
    records are exactly the spec's regenerated_by_upgrade; each regenerated
    record is an engine defect whose output the built CSV now scores within
    REGENERATION_TOLERANCE of its audited target, as the revision's
    regenerated_exclusions entry states it and regeneration_target_problems
    re-derives it (the record's alternative_value, or the corrected value in a
    committed fix-module evidence file); a kept record keeps its
    bytes and its output its value (rule 5: unlisted in ``changed``); a new
    record is its action's, computed on the build's engine and frozen at the
    built value. Release 20261014's records keep their order and its last
    (the audit's scenario_023 record) stays last. The record is in the
    builder's form and passes the loader. Returns the records and the
    regenerated base, regenerated ruled and added outputs.
    """
    import tempfile

    from policybench.reference_exclusions import (
        ENGINE_DEFECT,
        ReferenceExclusionError,
        load_reference_exclusions,
    )

    try:
        doc = json.loads(text)
    except ValueError as error:
        raise SystemExit(f"the build's exclusion record is not JSON: {error}")
    require(
        isinstance(doc, dict) and text == exclusions_text(doc),
        "the build's exclusion record is not in the builder's form (duplicate keys "
        "or other bytes the gates cannot see); write it with json.dumps(indent=2)",
    )
    base_doc = json.loads(baseline.files[EXCLUSIONS_NAME])
    require(
        list(doc) == list(base_doc)
        and all(
            doc[key] == base_doc[key]
            for key in base_doc
            if key not in ("exclusions", "derivation")
        )
        and isinstance(doc["derivation"], str)
        and doc["derivation"].strip(),
        "the build's exclusion record changes release 20261014's fields outside "
        "its records and derivation",
    )
    with tempfile.TemporaryDirectory() as scratch:
        (Path(scratch) / EXCLUSIONS_NAME).write_text(text)
        try:
            load_reference_exclusions(Path(scratch))
        except ReferenceExclusionError as error:
            raise SystemExit(f"the build's exclusion record fails the loader: {error}")
    built = {spec_key(record): record for record in doc["exclusions"]}
    base = {spec_key(record): record for record in base_doc["exclusions"]}
    known = set(base) | set(baseline.ruled)
    regenerated = known - set(built)
    added = set(built) - known
    regenerated_ruled = frozenset(regenerated & set(baseline.ruled))
    regenerated_base = frozenset(regenerated & set(base))
    require(
        regenerated_ruled == baseline.regenerated,
        "the build regenerates ruled records "
        f"{sorted(regenerated_ruled)}, but the spec's regenerated_by_upgrade "
        f"names {sorted(baseline.regenerated)}",
    )
    declared = declared_exclusions(plan)
    require(
        added == set(declared),
        "the build's new exclusions are not its actions': unlisted "
        f"{sorted(added - set(declared))[:8]}, listed but absent "
        f"{sorted(set(declared) - added)[:8]}",
    )
    problems = []

    def dumps(record: dict) -> str:
        return json.dumps(record, ensure_ascii=False)

    for key in sorted(set(built) & set(base)):
        if dumps(built[key]) != dumps(base[key]):
            problems.append(f"{key}: changes release 20261014's record")
    for key in sorted(set(built) & set(baseline.ruled)):
        if dumps(built[key]) != dumps(baseline.ruled[key]):
            problems.append(f"{key}: changes the release's ruled record")
    for key in sorted(set(built) & known):
        frozen = float(built[key]["frozen_value"])
        if key in changed or abs(values[key] - frozen) > FROZEN_TOLERANCE:
            problems.append(
                f"{key}: an excluded output keeps the value it was decided on "
                f"({frozen}), but the build gives {values[key]}"
            )
    for key in sorted(added):
        record = built[key]
        if dumps(record) != dumps(declared[key]):
            problems.append(f"{key}: the new record is not its action's")
        if record.get("engine_version") != engine:
            problems.append(f"{key}: the new record is not computed on {engine}")
        if abs(values[key] - float(record["frozen_value"])) > FROZEN_TOLERANCE:
            problems.append(f"{key}: the new record's frozen_value is not the build's")
    for key in sorted(regenerated):
        record = base.get(key) or baseline.ruled[key]
        if record["reason_code"] != ENGINE_DEFECT:
            problems.append(
                f"{key}: an engine upgrade regenerates only an engine defect; "
                f"this is a {record['reason_code']} record"
            )
        entries = [
            item
            for item in (revision or {}).get("regenerated_exclusions", [])
            if isinstance(item, dict) and spec_key(item) == key
        ]
        actions = [
            item
            for item in plan.get("regenerated_exclusions", [])
            if isinstance(item, dict) and spec_key(item) == key
        ]
        entry = entries[0] if len(entries) == 1 else None
        action = actions[0] if len(actions) == 1 else None
        bound = regeneration_action_problems(key, record, entry, action)
        if bound:
            problems.extend(bound)
            continue
        # The reviewed action's tolerance, which the revision restates.
        problems.extend(
            regeneration_target_problems(
                key, record, entry["target"], values[key], engine, action["tolerance"]
            )
        )
    order = [key for key in map(spec_key, doc["exclusions"]) if key in base]
    if order != [key for key in map(spec_key, base_doc["exclusions"]) if key in built]:
        problems.append("release 20261014's records changed their order")
    if base_doc["exclusions"]:
        tail = spec_key(base_doc["exclusions"][-1])
        if tail in built and spec_key(doc["exclusions"][-1]) != tail:
            problems.append(f"release 20261014's last record {tail} is not last")
    require(not problems, f"the build's exclusion record: {problems[:8]}")
    return doc["exclusions"], regenerated_base, regenerated_ruled, frozenset(added)


def load_build(
    built: Path, explanations: Path, actions: Path, baseline: Baseline | None = None
) -> Upgrade:
    """Gate a reference build against release 20261014 and describe it.

    The build's base must be the pinned release 20261014: its sidecar is
    20261014's with one engine_upgrade revision added (upgrade_revision). Its
    reference CSV differs from 20261014's exactly in that revision's changed
    list, at the listed values (reference_value_changes); its exclusion record
    is the release's (upgrade_exclusion_records); its traces cover every
    changed output; its explanations differ from 20261014's only on changed
    outputs, each row stating its new value (explanation_changes); and its
    actions name its engine, approve only listed moves at their values, and
    recheck exactly the excluded outputs the revision rechecks, reasons
    verbatim.
    """
    for path in [*(built / name for name in BUILT_FILES), explanations, actions]:
        require(path.is_file(), f"the reference build lacks {path}")
    blobs = {name: (built / name).read_bytes() for name in BUILT_FILES}
    blobs[EXPLANATIONS_NAME] = explanations.read_bytes()
    blobs[ACTIONS_NAME] = actions.read_bytes()
    for name, blob in blobs.items():
        require(
            hashlib.sha256(blob).hexdigest() == REFERENCE_BUILD["sha256"][name],
            f"the reference build's {name} is off its pin",
        )
    baseline = upgrade_baseline() if baseline is None else baseline
    try:
        meta = json.loads(blobs[META_NAME])
        traces = json.loads(blobs[TRACES_NAME])
        plan = json.loads(blobs[ACTIONS_NAME])
        text = blobs[EXCLUSIONS_NAME].decode("utf-8")
    except ValueError as error:
        raise SystemExit(f"the reference build's records do not parse: {error}")
    require(isinstance(plan, dict), "the build's actions are not an object")
    revision = upgrade_revision(
        json.loads(baseline.files[META_NAME]),
        meta,
        hashlib.sha256(blobs[CSV_NAME]).hexdigest(),
    )
    engine = revision["engine_version"]
    require(
        engine == REFERENCE_BUILD["engine_version"],
        "the build names a different installed engine",
    )
    provenance = revision.get("provenance", {})
    require(
        provenance.get("builder_sha256") == REFERENCE_BUILD["builder_sha256"]
        and provenance.get("actions_sha256") == REFERENCE_BUILD["sha256"][ACTIONS_NAME],
        "the sidecar's builder or actions differs from its pin",
    )
    audit = ROOT / REFERENCE_BUILD["directory"]
    require(
        digest(audit / "scripts/build_references_upgrade.py")
        == REFERENCE_BUILD["builder_sha256"],
        "the builder is off its pin",
    )
    timing = json.loads((audit / "verification/sweep_timing.json").read_text())[
        "publication_check"
    ]
    recorded = timing["build_sha256"]
    require(
        timing["engine"] == engine.removeprefix(ENGINE_PREFIX)
        and all(
            recorded[name] == REFERENCE_BUILD["sha256"][name] for name in UPGRADED_FILES
        )
        and recorded["builder"] == REFERENCE_BUILD["builder_sha256"],
        "audit publication record disagrees with the build pins",
    )
    base_values = reference_values(baseline.files[CSV_NAME])
    values = reference_values(blobs[CSV_NAME])
    changed = reference_value_changes(baseline.files[CSV_NAME], blobs[CSV_NAME])
    listed: dict[tuple[str, str], dict] = {}
    for item in revision["changed"]:
        key = (item["scenario_id"], item["variable"])
        require(key not in listed, f"the build's revision lists {key} twice")
        listed[key] = item
    require(
        set(changed) == set(listed),
        "the reference CSV differs from release 20261014's outside the build's "
        f"changed list: unlisted moves {sorted(set(changed) - set(listed))[:8]}, "
        f"listed changes that did not happen {sorted(set(listed) - set(changed))[:8]}",
    )
    misstated = sorted(
        key
        for key, item in listed.items()
        if not _same(item["regenerated"], changed[key])
        or not _same(item["previous"], base_values[key])
    )
    require(
        not misstated,
        f"the build's changed list misstates the previous or regenerated value of "
        f"{misstated[:8]}",
    )
    records, regenerated_base, regenerated_ruled, added = upgrade_exclusion_records(
        baseline, text, values, changed, plan, engine, revision
    )
    expected_traces = {f"{s}|{v}" for s, v in changed}
    require(
        isinstance(traces, dict)
        and set(traces) == expected_traces
        and all(
            isinstance(item, dict)
            and isinstance(item.get("pe_variable"), str)
            and isinstance(item.get("trace"), str)
            for item in traces.values()
        ),
        "the build's traces do not cover exactly its changed outputs: "
        f"{sorted(set(traces) ^ expected_traces)[:8]}",
    )
    rewritten, rows = explanation_changes(
        baseline.explanations, blobs[EXPLANATIONS_NAME]
    )
    outside = sorted(rewritten - set(changed))
    require(
        not outside,
        f"the build's explanations rewrite outputs it did not change: {outside[:8]}",
    )
    stale = sorted(
        key
        for key in changed
        if (
            "reference_value" in rows[key]
            and not _same(_float(rows[key]["reference_value"]), changed[key], 1e-6)
        )
        or not rows[key].get("explanation", "x").strip()
    )
    require(
        not stale,
        "the build's explanations do not state the new reference of "
        f"{stale[:8]}; run the narratives for every changed output",
    )
    require(
        plan.get("engine") == engine,
        f"the build's actions name {plan.get('engine')!r}; expected {engine}",
    )
    approved = {}
    for item in plan.get("approved", []):
        require(isinstance(item, dict), "the build's actions list a malformed move")
        approved[spec_key(item)] = item
    off = sorted(
        key
        for key, item in approved.items()
        if key not in changed
        or not _same(item.get("value"), changed[key], APPROVED_TOLERANCE)
    )
    require(
        not off,
        f"the build's actions approve moves the build did not make: {off[:8]}",
    )
    # Every scored reference the build moves beyond the exact-match tolerance
    # needs an approval: a regenerated or newly excluded output has its own
    # record, and a move within $1 none.
    from policybench.paper_results import moves_beyond_tolerance

    unapproved = sorted(
        key
        for key, new in changed.items()
        if key not in regenerated_base | regenerated_ruled | added
        and moves_beyond_tolerance(key[1], base_values[key], new)
        and key not in approved
    )
    require(
        not unapproved,
        "the build moves scored references beyond the tolerance without an "
        f"approval in its actions: {unapproved[:8]}",
    )
    rechecked = {
        spec_key(item): item for item in revision.get("excluded_outputs_rechecked", [])
    }
    planned = {spec_key(item): item for item in plan.get("excluded_rechecked", [])}
    excluded = {spec_key(record) for record in records}
    require(
        set(rechecked) == set(planned),
        "the build's revision and actions recheck different excluded outputs: "
        f"{sorted(set(rechecked) ^ set(planned))[:8]}",
    )
    wrong = sorted(
        key
        for key, item in rechecked.items()
        if key not in excluded
        or not _same(item["kept_value"], values[key], FROZEN_TOLERANCE)
        or ("reason" in planned[key] and planned[key]["reason"] != item.get("reason"))
    )
    require(
        not wrong,
        "the build rechecks outputs it does not keep excluded at their value, or "
        f"with another reason: {wrong[:8]}",
    )
    claims = builder_claim_problems(
        baseline,
        revision,
        plan,
        values,
        regenerated_base | regenerated_ruled,
        regenerated_ruled,
        added,
        hashlib.sha256(blobs[ACTIONS_NAME]).hexdigest(),
    )
    require(
        not claims,
        f"the build's account of the upgrade disagrees with its records: {claims[:8]}",
    )
    return Upgrade(
        engine_version=engine,
        previous_engine_version=revision["previous_engine_version"],
        revision=revision,
        changed=changed,
        regenerated_base=regenerated_base,
        regenerated_ruled=regenerated_ruled,
        added=added,
        records=len(records),
        exclusions_text=text,
        sha256={name: hashlib.sha256(blob).hexdigest() for name, blob in blobs.items()},
    )


def builder_claim_problems(
    baseline: Baseline,
    revision: dict,
    plan: dict,
    values: dict[tuple[str, str], float],
    regenerated: frozenset,
    regenerated_ruled: frozenset,
    added: frozenset,
    actions_sha256: str,
) -> list[str]:
    """Where the builder's own account of the upgrade disagrees with the
    records: reference_audit/2026-10-22-engine-upgrade/scripts/
    build_references_upgrade.py lists the regenerated records (each with the
    record it removed and its new value), the ruled records kept, and the new
    exclusions, in its revision and its actions, and its revision's
    provenance names its actions' sha256 and release 20261014's commit."""

    def outputs(items) -> set:
        return {spec_key(item) for item in items if isinstance(item, dict)}

    kept = set(baseline.ruled) - regenerated_ruled
    stated = {
        "the revision's regenerated_exclusions": (
            revision.get("regenerated_exclusions", []),
            regenerated,
        ),
        "the actions' regenerated_exclusions": (
            plan.get("regenerated_exclusions", []),
            regenerated,
        ),
        "the revision's kept_exclusions_from_release": (
            revision.get("kept_exclusions_from_release", []),
            kept,
        ),
        "the actions' kept_exclusions_from_release": (
            plan.get("kept_exclusions_from_release", []),
            kept,
        ),
        "the revision's new_exclusions": (revision.get("new_exclusions", []), added),
    }
    problems = []
    for label, (items, want) in stated.items():
        if not isinstance(items, list):
            problems.append(f"{label} is not a list")
        elif outputs(items) != set(want) or len(items) != len(want):
            problems.append(f"{label} names {sorted(outputs(items) ^ set(want))[:4]}")
    base = {
        spec_key(record): record
        for record in json.loads(baseline.files[EXCLUSIONS_NAME])["exclusions"]
    }
    for item in revision.get("regenerated_exclusions", []):
        if not isinstance(item, dict):
            continue
        key = spec_key(item)
        record = base.get(key) or baseline.ruled.get(key)
        if record is not None and json.dumps(item.get("record")) != (
            json.dumps(record)
        ):
            problems.append(f"{key}: the revision's record is not the removed record")
        # The builder writes a value that moved by no more than 1e-6 as it was.
        if key in values and not _same(item.get("regenerated"), values[key], 1e-6):
            problems.append(f"{key}: the revision's regenerated value is not the CSV's")
    provenance = revision.get("provenance")
    if (
        not isinstance(provenance, dict)
        or provenance.get("actions_sha256") != actions_sha256
        or provenance.get("base_commit") != BASE_COMMIT
    ):
        problems.append(
            "the revision's provenance does not name these actions and release "
            f"20261014's commit {BASE_COMMIT[:12]}"
        )
    if plan.get("previous_engine") != revision["previous_engine_version"]:
        problems.append(
            f"the actions upgrade from {plan.get('previous_engine')!r}; expected "
            f"{revision['previous_engine_version']}"
        )
    return problems


def _float(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def upgraded_reference_pins(upgrade: Upgrade) -> dict[str, str]:
    """Release 20261014's reference pins with the build's three files'."""
    return {
        **BASE_REFERENCE_SHA256,
        **{name: upgrade.sha256[name] for name in UPGRADED_FILES},
    }


def grounding_lookup(path: Path) -> dict[tuple[str, str], str]:
    """The audit grounding by output, as prepare_audit takes it."""
    import pandas as pd

    grounding = pd.read_csv(path)
    return {
        (str(r.scenario_id), str(r.variable)): str(r.grounding)
        for r in grounding.itertuples()
    }


@contextlib.contextmanager
def object_strings():
    """Render prompts as prepare rendered the stage's: resolve_base turns
    pandas 3's inferred Arrow strings off before prepare runs."""
    import pandas as pd

    if hasattr(pd.options, "future") and hasattr(pd.options.future, "infer_string"):
        with pd.option_context("future.infer_string", False):
            yield
    else:
        yield


def render_audit_with(
    bundle: Path,
    sources: dict[str, bytes],
    lookup: dict,
    versions: dict[str, int] | None = None,
) -> list[tuple[str, dict[int, str], dict]]:
    """Each audit case (id, prompts by template version, manifest row) the
    bundle gives once the build's references and explanations are in it,
    rendered in memory.

    A scratch run directory links every other bundle file and holds the
    build's, so nothing in the stage changes. The order is prepare_audit's.
    Every case is rendered on JUDGE_TEMPLATE_VERSION, the version new and
    re-opened cases take, and a judged case also on the version its sidecar
    records (``versions``), as prepare_audit compares it: the stage's audit
    mixes the seed's v1 verdicts with this release's v2 ones.
    """
    import tempfile

    from policybench.audit import build_audit_cases, render_case_prompt

    require_combined_predictions(bundle)
    versions = versions or {}
    with tempfile.TemporaryDirectory(prefix="install-references-") as scratch:
        run = Path(scratch) / bundle.name
        for part in ("us", "annotations"):
            (run / part).mkdir(parents=True)
            if (bundle / part).is_dir():
                for path in sorted((bundle / part).iterdir()):
                    if path.is_file():
                        os.symlink(path.resolve(), run / part / path.name)
        replaced = {
            **{run / "us" / name: sources[name] for name in UPGRADED_FILES},
            run / "annotations" / EXPLANATIONS_NAME: sources[EXPLANATIONS_NAME],
        }
        for path, blob in replaced.items():
            path.unlink(missing_ok=True)
            path.write_bytes(blob)
        with object_strings():
            cases = build_audit_cases(run / "us", grounding_lookup=lookup)
            return [
                (
                    case.case_id,
                    {
                        version: render_case_prompt(case, template_version=version)
                        for version in {
                            JUDGE_TEMPLATE_VERSION,
                            versions.get(case.case_id, JUDGE_TEMPLATE_VERSION),
                        }
                    },
                    case.to_manifest_row(),
                )
                for case in cases
            ]


def recorded_versions(audit: Path) -> dict[str, int]:
    """The template version each judged case's sidecar records (absent: v1),
    for the cases that hold a verdict; a sidecar that records an unknown
    version is left out, so its case renders on JUDGE_TEMPLATE_VERSION."""
    from policybench.judge_template import recorded_template_version

    found = {}
    for case in sorted((audit / "cases").glob("*")):
        meta_path = case / "verdict.meta.json"
        if not (case / "verdict.json").is_file() or not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except ValueError:
            continue
        version = recorded_template_version(meta if isinstance(meta, dict) else None)
        if version is not None:
            found[case.name] = version
    return found


def verify_install_target(stage: Path, receipt: dict) -> None:
    """The stage's references are release 20261014's (its exclusion record
    perhaps the release's, from install-exclusions) or an earlier install's,
    in the scoring source and the bundle; its explanations likewise."""
    previous = (receipt.get("references_installed") or {}).get("sha256", {})
    for name in UPGRADED_FILES:
        allowed = {BASE_REFERENCE_SHA256[name]}
        if name in previous:
            allowed.add(previous[name])
        if name == EXCLUSIONS_NAME:
            allowed.add(release_exclusions_sha256())
        for target in (stage / "scoring", stage / "publish" / RUN_NAME / "us"):
            path = target / name
            require(
                path.is_file() and digest(path) in allowed,
                f"the stage's {path.relative_to(stage)} is neither release "
                "20261014's nor an installed build's; prepare a new stage",
            )
    path = stage / "publish" / RUN_NAME / "annotations" / EXPLANATIONS_NAME
    allowed = {BASE_EXPLANATIONS_SHA256, previous.get(EXPLANATIONS_NAME)}
    require(
        path.is_file() and digest(path) in allowed,
        f"the stage's {EXPLANATIONS_NAME} is neither release 20261014's nor an "
        "installed build's; prepare a new stage",
    )


def references_record(upgrade: Upgrade, previous: dict | None) -> dict:
    """What stage.json records of an installed build (references_installed).

    Installing the same build again records the same thing; installing another
    keeps the one it replaces under ``superseded``.
    """

    def keys(outputs) -> list[list[str]]:
        return [list(key) for key in sorted(outputs)]

    record = {
        "engine_version": upgrade.engine_version,
        "previous_engine_version": upgrade.previous_engine_version,
        "actions_sha256": upgrade.sha256[ACTIONS_NAME],
        "sha256": dict(upgrade.sha256),
        "base_sha256": {
            **{name: BASE_REFERENCE_SHA256[name] for name in UPGRADED_FILES},
            EXPLANATIONS_NAME: BASE_EXPLANATIONS_SHA256,
        },
        "changed": keys(upgrade.changed),
        "regenerated_base": keys(upgrade.regenerated_base),
        "regenerated_ruled": keys(upgrade.regenerated_ruled),
        "added": keys(upgrade.added),
        "records": upgrade.records,
        "scored_outputs": upgrade.scored_outputs,
        "spec_sha256": digest(ROOT / SPEC_PATH),
    }
    superseded = list((previous or {}).get("superseded", []))
    if previous and {k: v for k, v in previous.items() if k != "superseded"} != record:
        superseded.append({k: v for k, v in previous.items() if k != "superseded"})
    record["superseded"] = superseded
    return record


def bind_build_exclusions(stage: Path, receipt: dict, upgrade: Upgrade) -> None:
    """Write the build's exclusion record into the stage and bind it as the
    release's (exclusions_installed); the receipt is written by the caller."""
    blob = upgrade.exclusions_text.encode("utf-8")
    for target in (stage / "scoring", stage / "publish" / RUN_NAME / "us"):
        (target / EXCLUSIONS_NAME).write_bytes(blob)
    receipt["files"][f"publish/{RUN_NAME}/us/{EXCLUSIONS_NAME}"] = upgrade.sha256[
        EXCLUSIONS_NAME
    ]
    receipt["exclusions_installed"] = {
        "base_sha256": BASE_REFERENCE_SHA256[EXCLUSIONS_NAME],
        "sha256": upgrade.sha256[EXCLUSIONS_NAME],
        "spec_sha256": digest(ROOT / SPEC_PATH),
        "records": upgrade.records,
        "source": f"{BUILD_COPY}/{EXCLUSIONS_NAME}",
        "engine_version": upgrade.engine_version,
    }


def install_references(args) -> None:
    """Install a gated engine upgrade of the references into the stage.

    load_build gates the build against release 20261014 before anything is
    written, and the audit the new references give is rendered in memory and
    held to check_prompt_changes' rule, so a build that would re-open a case
    nothing explains is refused first. Then the build goes, verbatim, into
    BUILD_COPY; its three reference files into the scoring source and the
    bundle, its explanations into the bundle's annotations; stage.json binds
    them (files, references_installed with the build's sha256s, engine and
    actions, and exclusions_installed for the build's record). Then
    policybench.audit.prepare_audit runs again in place on stage/audit with
    the pinned grounding: every verdict whose prompt changes (or whose case
    leaves the audit) is set aside first, with its judge evidence, in
    rejected-verdicts/, and every other verdict keeps its bytes. Last,
    prompt-changes.json and pending.json are written anew. Installing the same
    build again preserves its binding when the spec is unchanged. A spec
    edit requires installing the same reviewed build again to rebind it.
    """
    if any(
        getattr(args, name, None) is None
        for name in ("built", "explanations", "actions")
    ):
        require(
            all(
                getattr(args, name, None) is None
                for name in ("built", "explanations", "actions")
            ),
            "supply all three build sources or let the driver read the committed build",
        )
        import tempfile

        with tempfile.TemporaryDirectory(prefix="terra-narratives-") as scratch:
            built, explanations, actions = committed_build_sources(Path(scratch))
            install_references(
                argparse.Namespace(
                    **{
                        **vars(args),
                        "built": built,
                        "explanations": explanations,
                        "actions": actions,
                    }
                )
            )
        return
    stage = args.stage_dir
    require(
        digest(args.grounding) == GROUNDING_SHA256,
        "grounding differs from the one the 20260929 audit was rendered with",
    )
    receipt_path = stage / "stage.json"
    upgrade = load_build(args.built, args.explanations, args.actions)
    verify_engine_pins(upgrade.engine_version)
    if not receipt_path.is_file():
        # The requested command sequence installs before prepare. Cache the
        # gated build now; prepare first binds the base audit and then runs
        # the same installation and prompt invalidation gates below.
        copy = stage / BUILD_COPY
        copy.mkdir(parents=True, exist_ok=True)
        sources = {name: (args.built / name).read_bytes() for name in BUILT_FILES}
        sources[EXPLANATIONS_NAME] = args.explanations.read_bytes()
        sources[ACTIONS_NAME] = args.actions.read_bytes()
        require(
            {name: hashlib.sha256(blob).hexdigest() for name, blob in sources.items()}
            == upgrade.sha256,
            "the build changed while it was gated",
        )
        for name, blob in sources.items():
            (copy / name).write_bytes(blob)
        marker = stage / "reference-install.json"
        previous = json.loads(marker.read_text()) if marker.exists() else {}
        record = {"sha256": upgrade.sha256, "engine_version": upgrade.engine_version}
        if "seed" in previous:
            verify_seed(previous["seed"])
            record["seed"] = previous["seed"]
        write_json(marker, record)
        print(f"Bound the committed {upgrade.engine_version} build; run --step prepare")
        return
    receipt = json.loads(receipt_path.read_text())
    require(
        "seed" in receipt,
        "stage.json does not bind the audit seed; run --step bind-seed first",
    )
    seed = receipt["seed"]
    verify_seed(seed)
    verify_install_target(stage, receipt)
    sources = {name: (args.built / name).read_bytes() for name in BUILT_FILES}
    sources[EXPLANATIONS_NAME] = args.explanations.read_bytes()
    sources[ACTIONS_NAME] = args.actions.read_bytes()
    require(
        {name: hashlib.sha256(blob).hexdigest() for name, blob in sources.items()}
        == upgrade.sha256,
        "the reference build changed while it was gated",
    )
    bundle = stage / "publish" / RUN_NAME
    audit = stage / "audit"
    lookup = grounding_lookup(args.grounding)
    versions = recorded_versions(audit)
    rendered = render_audit_with(bundle, sources, lookup, versions)
    renders = {
        case: texts for case, texts, row in rendered if not row["parse_failure_only"]
    }
    reopen, kept = {}, {}
    for case in sorted((audit / "cases").iterdir()):
        if not case.is_dir() or not (
            (case / "verdict.json").exists() or (case / "verdict.meta.json").exists()
        ):
            continue
        prompt = case / "prompt.md"
        judged_on = versions.get(case.name, JUDGE_TEMPLATE_VERSION)
        if case.name not in renders:
            reopen[case.name] = (
                f"install-references: the case leaves the audit on "
                f"{upgrade.engine_version}"
            )
        elif not prompt.is_file() or prompt.read_bytes() != renders[case.name][
            judged_on
        ].encode("utf-8"):
            reopen[case.name] = (
                "install-references: its prompt re-renders on "
                f"{upgrade.engine_version}, whose reference value or explanation "
                "it shows"
            )
        elif (case / "verdict.json").is_file():
            kept[case.name] = digest(case / "verdict.json")
    # The prompt each case will hold after prepare_audit: a kept verdict's own
    # bytes, on its recorded version; every other case on JUDGE_TEMPLATE_VERSION.
    texts = {
        case: forms[versions.get(case, JUDGE_TEMPLATE_VERSION)]
        if case in kept
        else forms[JUDGE_TEMPLATE_VERSION]
        for case, forms in renders.items()
    }
    seeded = {case: item["prompt_sha256"] for case, item in seed.items()}
    upgraded = upgrade.upgraded_cases
    changes = classify_prompt_changes(
        [row for _, _, row in rendered],
        {
            case: hashlib.sha256(text.encode()).hexdigest()
            for case, text in texts.items()
        },
        seeded,
        reworded_since_seed(),
        upgraded,
    )

    # Install the build and bind it before the audit is touched: a stage left
    # partway is resumed by installing the same build again.
    copy = stage / BUILD_COPY
    copy.mkdir(exist_ok=True)
    for name, blob in sources.items():
        (copy / name).write_bytes(blob)
    for target in (stage / "scoring", bundle / "us"):
        for name in UPGRADED_FILES:
            (target / name).write_bytes(sources[name])
    (bundle / "annotations").mkdir(exist_ok=True)
    (bundle / "annotations" / EXPLANATIONS_NAME).write_bytes(sources[EXPLANATIONS_NAME])
    for name in UPGRADED_FILES:
        receipt["files"][f"publish/{RUN_NAME}/us/{name}"] = upgrade.sha256[name]
    receipt["files"][f"publish/{RUN_NAME}/annotations/{EXPLANATIONS_NAME}"] = (
        upgrade.sha256[EXPLANATIONS_NAME]
    )
    receipt["references_installed"] = references_record(
        upgrade, receipt.get("references_installed")
    )
    require(
        not upgrade.regenerated and not upgrade.added,
        "this release keeps all 49 exclusion records",
    )
    receipt["adjudications_dropped"] = []
    bind_build_exclusions(stage, receipt, upgrade)
    pending_receipt = receipt_path.with_name("stage.json.installing")
    write_json(pending_receipt, receipt)
    os.replace(pending_receipt, receipt_path)

    from policybench.audit import prepare_audit

    for case, reason in reopen.items():
        set_aside(audit, case, reason)
    with object_strings():
        prepare_audit(
            bundle / "us",
            audit,
            grounding_lookup=lookup,
            template_version=JUDGE_TEMPLATE_VERSION,
        )
    manifest = [
        json.loads(line) for line in (audit / "cases.jsonl").read_text().splitlines()
    ]
    require(
        manifest == [row for _, _, row in rendered]
        and all(
            (audit / "cases" / case / "prompt.md").read_bytes() == text.encode("utf-8")
            for case, text in texts.items()
        ),
        "prepare_audit rendered the stage's audit unlike the in-memory rendering",
    )
    moved = sorted(
        case
        for case, sha in kept.items()
        if not (audit / "cases" / case / "verdict.json").is_file()
        or digest(audit / "cases" / case / "verdict.json") != sha
    )
    require(not moved, f"verdicts whose prompts did not change moved: {moved[:8]}")
    on_disk = check_prompt_changes(audit, seeded, upgraded)
    require(
        on_disk == changes, "the written audit's prompt changes are not the rendered"
    )
    write_json(
        stage / PROMPT_CHANGES, {key: sorted(value) for key, value in changes.items()}
    )
    pending = validate_verdicts(audit, remove_invalid=True, seed=seed)
    write_json(stage / "pending.json", pending)
    verify_prompt_changes(stage, seed)
    print(
        f"Installed the {upgrade.engine_version} references: {len(upgrade.changed)} "
        f"outputs changed, {len(upgrade.regenerated)} exclusions regenerated, "
        f"{len(upgrade.added)} added, {upgrade.records} records "
        f"({upgrade.scored_outputs} scored). Audit: {len(changes['kept'])} prompts "
        f"unchanged, {len(changes['changed'])} changed and {len(changes['added'])} "
        f"new; {len(reopen)} verdicts set aside; {len(pending)} cases need Opus 5.5"
    )


def verify_installed_references(stage: Path, receipt: dict) -> Upgrade:
    """The stage's installed engine upgrade, gated again.

    The build kept in BUILD_COPY must be the bytes stage.json records, must
    pass load_build against git and the spec as they are now, must name the
    recorded engine, and the stage's scoring source, bundle and explanations
    must be its files.
    """
    installed = receipt["references_installed"]
    copy = stage / BUILD_COPY
    pins = installed.get("sha256")
    require(
        isinstance(pins, dict) and set(pins) == set(BUILD_COPY_FILES),
        "stage.json's references_installed does not bind the build's files",
    )
    for name, pin in pins.items():
        require(
            (copy / name).is_file() and digest(copy / name) == pin,
            f"the installed build's {name} changed; run --step install-references "
            "again",
        )
    upgrade = load_build(copy, copy / EXPLANATIONS_NAME, copy / ACTIONS_NAME)
    require(
        upgrade.engine_version == installed.get("engine_version")
        and upgrade.sha256 == pins,
        "the installed build is not the one stage.json records",
    )
    bundle = stage / "publish" / RUN_NAME
    targets = [stage / "scoring" / name for name in UPGRADED_FILES]
    targets += [bundle / "us" / name for name in UPGRADED_FILES]
    for path in targets:
        require(
            path.is_file() and digest(path) == pins[path.name],
            f"the stage's {path.relative_to(stage)} is not the installed build's; "
            "run --step install-references again",
        )
    path = bundle / "annotations" / EXPLANATIONS_NAME
    require(
        path.is_file() and digest(path) == pins[EXPLANATIONS_NAME],
        f"the stage's {EXPLANATIONS_NAME} is not the installed build's",
    )
    return upgrade


def stage_upgrade(stage: Path) -> Upgrade | None:
    """Require and re-gate the release's installed engine upgrade."""
    path = stage / "stage.json"
    require(path.is_file(), "stage lacks stage.json and the installed reference build")
    receipt = json.loads(path.read_text())
    require(
        receipt.get("references_installed"),
        "stage lacks the installed reference build; run --step install-references",
    )
    return verify_installed_references(stage, receipt)


def upgraded_cases(stage: Path) -> frozenset[str]:
    """The cases whose reference value or explanation the installed engine
    upgrade changed, derived like reworded_since_seed: from the staged
    references and explanations against release 20261014's in git.

    They must be exactly the installed revision's changed outputs (each
    explanation the narratives rewrote among them). Without an install, none.
    """
    receipt = json.loads((stage / "stage.json").read_text())
    if not receipt.get("references_installed"):
        return frozenset()
    bundle = stage / "publish" / RUN_NAME
    meta = json.loads((bundle / "us" / META_NAME).read_text())
    revision = (meta.get("revisions") or [{}])[-1]
    listed = {
        (item["scenario_id"], item["variable"])
        for item in revision.get("changed", [])
        if revision.get("kind") == "engine_upgrade"
    }
    values = reference_value_changes(
        base_reference_bytes(CSV_NAME), (bundle / "us" / CSV_NAME).read_bytes()
    )
    texts, _ = explanation_changes(
        base_explanations_bytes(),
        (bundle / "annotations" / EXPLANATIONS_NAME).read_bytes(),
    )
    require(
        set(values) == listed and texts <= listed,
        "the staged references or explanations differ from release 20261014's "
        "outside the installed revision's changed list: "
        f"{sorted((set(values) | texts) ^ listed)[:8]}; run --step "
        "install-references again",
    )
    return frozenset(output_case(key) for key in set(values) | texts)


def drop_regenerated_adjudications(
    record: dict, upgrade: Upgrade
) -> tuple[dict, list[dict]]:
    """``record`` without the decisions of the release 20261014 records the
    upgrade regenerated, and what was dropped, as stage.json records it.

    Each regenerated record has exactly one decision, which excludes it; it
    is dropped outright, as #178 dropped scenario_045 SNAP's.
    """
    dropped, kept = [], []
    for entry in record["adjudications"]:
        if case_id(entry) not in upgrade.dropped_cases:
            kept.append(entry)
            continue
        require(
            entry.get("excluded_from_scoring") is True,
            f"{case_id(entry)}: the decision on a regenerated record does not "
            "exclude it",
        )
        dropped.append(
            {
                "case_id": case_id(entry),
                "reason": (
                    f"Regenerated on {upgrade.engine_version}: the upgrade fixes "
                    "the engine defect behind this exclusion, so its record leaves "
                    "the exclusion record and this decision leaves the "
                    "adjudication record, as release 20260922c dropped "
                    "scenario_045 SNAP's (#178)."
                ),
                "entry": entry,
            }
        )
    named = [item["case_id"] for item in dropped]
    require(
        len(named) == len(set(named)) and set(named) == upgrade.dropped_cases,
        "the staged record does not hold one decision for each regenerated "
        f"record: {sorted(set(named) ^ upgrade.dropped_cases)[:8]}",
    )
    return {**record, "adjudications": kept}, dropped


def verify_recorded_drops(stage: Path, upgrade: Upgrade) -> None:
    """stage.json records the drop of exactly the decisions of the records the
    upgrade regenerated, each release 20261014's outside its judge fields."""
    from restate_gpt61sol_adjudications import JUDGE_FIELDS

    receipt = json.loads((stage / "stage.json").read_text())
    recorded = receipt.get("adjudications_dropped")
    require(
        isinstance(recorded, list) and all(isinstance(i, dict) for i in recorded),
        "stage.json records no dropped adjudications; run --step adjudicate-exclusions",
    )
    named = [item.get("case_id") for item in recorded]
    require(
        len(named) == len(set(named)) and set(named) == upgrade.dropped_cases,
        "stage.json's dropped adjudications are not the regenerated records': "
        f"{sorted(set(named) ^ upgrade.dropped_cases)[:8]}",
    )
    base = {
        case_id(entry): entry for entry in base_adjudication_record()["adjudications"]
    }

    def outside_judge(entry: dict) -> dict:
        # stage.json is written with sorted keys, so compare values only.
        return {k: v for k, v in entry.items() if k not in JUDGE_FIELDS}

    wrong = [
        item["case_id"]
        for item in recorded
        if not isinstance(item.get("entry"), dict)
        or item["case_id"] not in base
        or case_id(item["entry"]) != item["case_id"]
        or outside_judge(item["entry"]) != outside_judge(base[item["case_id"]])
    ]
    require(
        not wrong,
        f"stage.json records dropped decisions that are not release 20261014's: "
        f"{wrong[:8]}",
    )


def export_on_base_references(bundle: Path, live: dict, record: Path) -> dict:
    """release_20261006.export_payload on a scratch copy of the bundle's export
    inputs with release 20261014's five reference files put back (from git)
    and ``record`` as the exclusion record: the upgrade's scope export, read
    only for its modelStats.

    The dashboard schema is checked without requiring a failure annotation on
    every wrong answer: the stage's annotations follow the upgraded
    references, so an answer the new reference makes right and the old one
    wrong has none here. The release's own payload, on the upgraded
    references, is checked with that requirement (build_payload).
    """
    import tempfile

    from release_20261006 import EXPORT_INPUTS, export_payload

    with tempfile.TemporaryDirectory(dir=bundle.parent, prefix="base-refs-") as scratch:
        copy_root = Path(scratch) / bundle.name
        for rel in EXPORT_INPUTS:
            (copy_root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundle / rel, copy_root / rel)
        for name in REFERENCE_FILES:
            (copy_root / "us" / name).write_bytes(base_reference_bytes(name))
        return export_payload(
            copy_root, live, record, require_failure_annotations=False
        )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument("--stage-dir", type=Path)
    parser.add_argument(
        "--base-predictions", type=Path, default=SNAPSHOT / "predictions.csv.gz"
    )
    parser.add_argument("--base-payload", type=Path, default=SNAPSHOT / "data.json.gz")
    parser.add_argument("--audit-seed", type=Path)
    parser.add_argument("--grounding", type=Path)
    parser.add_argument("--built", type=Path)
    parser.add_argument("--explanations", type=Path)
    parser.add_argument("--actions", type=Path)
    parser.add_argument(
        "--early", action="store_true", help="fold and export without paid judging"
    )
    parser.add_argument(
        "--partial",
        action="store_true",
        help="scratch-only cohort rehearsal; requires --early",
    )
    parser.add_argument(
        "--step",
        choices=(
            "pin-inputs",
            "prepare",
            "bind-seed",
            "install-exclusions",
            "install-references",
            "judge",
            "adjudicate-exclusions",
            "provenance",
            "triage",
            "export",
        ),
        default="prepare",
        help="pin-inputs writes the finished run's file hashes to "
        f"{INPUT_PINS_PATH} (no stage); bind-seed binds the audit seed in the "
        "stage.json of a stage prepared before prepare bound it",
    )
    args = parser.parse_args(argv)
    if args.partial and not args.early:
        parser.error("--partial requires --early")
    if args.early and args.step != "prepare":
        parser.error("--early only applies to prepare")
    if args.step in ("prepare", "pin-inputs") and not args.runs_root:
        parser.error(f"{args.step} requires --runs-root")
    if args.step == "install-references":
        missing = [
            f"--{name}" for name in ("grounding",) if getattr(args, name) is None
        ]
        if missing:
            parser.error(f"install-references requires {' '.join(missing)}")
        for name in ("built", "explanations", "actions", "grounding"):
            if getattr(args, name) is not None:
                setattr(args, name, getattr(args, name).resolve())
    if args.step != "pin-inputs":
        if args.stage_dir is None:
            parser.error(f"{args.step} requires --stage-dir")
        args.stage_dir = args.stage_dir.resolve()
    return args


def main(argv=None) -> None:
    args = parse_args(argv)
    if args.step == "pin-inputs":
        pin_inputs(args)
        return
    sources = [SNAPSHOT, ANNOTATIONS, args.base_predictions, args.base_payload]
    sources += [
        p for p in (args.runs_root, args.audit_seed, args.grounding) if p is not None
    ]
    validate_stage_path(args.stage_dir, sources)
    stage = args.stage_dir
    bundle = stage / "publish" / RUN_NAME
    receipt_path = stage / "stage.json"
    if args.step == "install-references":
        install_references(args)
        return
    if args.step == "bind-seed" and not receipt_path.exists():
        bind_seed(args)
        return
    if args.step == "prepare":
        if not args.partial:
            marker = stage / "reference-install.json"
            require(
                marker.is_file(),
                "prepare needs the committed build; run --step install-references",
            )
            installed = json.loads(marker.read_text())
            copy = stage / BUILD_COPY
            upgrade = load_build(copy, copy / EXPLANATIONS_NAME, copy / ACTIONS_NAME)
            require(
                installed.get("sha256") == upgrade.sha256
                and installed.get("engine_version") == upgrade.engine_version,
                "preinstalled build differs from its binding",
            )
            verify_engine_pins(upgrade.engine_version)
        runs = discover_new_models(args.runs_root)
        print("All copied run states qualify; resolving 20261014 base", flush=True)
        base, reference, live = resolve_base(args)
        print("Base verified; folding copied additions", flush=True)
        stage.mkdir(parents=True, exist_ok=True)
        require(
            not receipt_path.exists(),
            "stage already prepared; use a fresh stage-dir "
            "or resume judge/triage/export",
        )
        bundle, frames = prepare_inputs(args, runs, base, reference)
        if args.partial:
            partial_scores(args, base, reference, frames)
        seed = None
        preview = {}
        if args.early:
            if not args.partial:
                for target in (stage / "scoring", bundle / "us"):
                    for name in UPGRADED_FILES:
                        shutil.copyfile(copy / name, target / name)
                shutil.copyfile(
                    copy / EXPLANATIONS_NAME,
                    bundle / "annotations" / EXPLANATIONS_NAME,
                )
                provisional = {
                    "early": True,
                    "partial": False,
                    "files": {},
                    "references_installed": references_record(upgrade, None),
                }
                bind_build_exclusions(stage, provisional, upgrade)
                preview = {
                    name: provisional[name]
                    for name in ("references_installed", "exclusions_installed")
                }
                write_json(receipt_path, provisional)
            export(args, bundle, live)
        else:
            seed = prepare_cases(args, bundle)
        inputs = [p for p in (stage / "inputs").rglob("*") if p.is_file()]
        inputs += [
            bundle / "us" / name for name in (*REFERENCE_FILES, "predictions.csv")
        ]
        receipt = {
            **preview,
            "partial": args.partial,
            "early": args.early,
            "base_tag": BASE_TAG,
            "base_commit": BASE_COMMIT,
            "files": {str(p.relative_to(stage)): digest(p) for p in inputs},
        }
        if seed is not None:
            receipt["seed"] = seed
        write_json(receipt_path, receipt)
        if not args.partial and not args.early:
            if "seed" in installed:
                require(
                    installed["seed"] == seed, "prepare's seed differs from bind-seed"
                )
            install_references(
                argparse.Namespace(
                    **{
                        **vars(args),
                        "built": copy,
                        "explanations": copy / EXPLANATIONS_NAME,
                        "actions": copy / ACTIONS_NAME,
                    }
                )
            )
    else:
        receipt = json.loads(receipt_path.read_text())
        require_release_stage(receipt)
        if args.step == "export":
            require_combined_predictions(bundle, require_file=False)
        for name, expected in receipt["files"].items():
            require(
                digest(stage / name) == expected,
                f"staged input changed: {name}; prepare a new stage",
            )
        if args.step != "export":
            (stage / "release-ready.json").unlink(missing_ok=True)
        if args.step not in ("bind-seed", "install-exclusions"):
            installed = receipt.get("exclusions_installed") or {}
            upgrade = stage_upgrade(stage)
            require(
                installed.get("sha256") == upgrade.sha256[EXCLUSIONS_NAME],
                "the stage's exclusions are not the release's; run "
                "--step install-references",
            )
        if args.step == "bind-seed":
            bind_seed(args)
        elif args.step == "install-exclusions":
            install_exclusions(args)
        elif args.step == "adjudicate-exclusions":
            adjudicate_exclusions(args)
        elif args.step == "provenance":
            write_judge_provenance(args)
        elif args.step == "judge":
            judge(args, bundle)
        elif args.step == "triage":
            triage(args, bundle)
        else:
            triage(args, bundle)
            export(args, bundle, resolve_live_base(args))


if __name__ == "__main__":
    main()
