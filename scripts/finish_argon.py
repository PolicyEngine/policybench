"""Stage the Gemini 4 Argon and Muse Spark 1.3 additions; never publish.

Adapted from finish_musewonder.py. It folds two supervised runs, Google's
Gemini 4 Argon and Meta's Muse Spark 1.3 (Max, 2026-10-13, d1441), onto the
48-model board of release dashboard-data-20261013b, and changes no tracked
data. The references stay that
release's, computed on policyengine-us 2.41.0: the newest release when this
one was staged, 2.41.3, and when it was frozen, 2.42.4, give the same value
for every output
(reference_audit/2026-10-12-engine-upgrade/verification/), so the driver
installs no reference build and has no --step install-references (see "No
engine upgrade of the references" below). The release rules no new exclusion,
so docs/argon/spec.json lists
no proposals and --step install-exclusions installs release 20261013b's record
unchanged. All outputs, including audit verdicts and adjudications, stay in
--stage-dir. See docs/argon/design.md for the run and release procedure.

The seed is release 20261013b's judged audit, kept when that release's stage
was removed (docs/argon/design.md): every judged case keeps the prompt and
verdict its judge wrote, on the judge template version its sidecar records,
and new and re-opened cases render on judge template v2
(JUDGE_TEMPLATE_VERSION).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

os.environ["OPENBLAS_NUM_THREADS"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RUN_NAME = "us_full_run_20260612_policyengine_4_16_1_populace"
SNAPSHOT = ROOT / "paper/snapshot/20260501/runs" / RUN_NAME
ANNOTATIONS = ROOT / "annotations" / RUN_NAME
BASE_TAG = "dashboard-data-20261013b"
# The one place the new release's tag is named. The lead may change it at
# freeze time; freeze_argon.py and the design note read it from here.
RELEASE_TAG = "dashboard-data-20261014"
# PENDING(#218): the payload at PR #218's frozen head; confirm at its merge.
BASE_SHA256 = "0a4b754a4ce3b249e0608efac62e52646e4c6f33c6a28c1a496c4c9fda49b507"
BASE_MODELS = 48
BASE_OUTPUTS = 1984
BASE_EXCLUSIONS = 49
BASE_SCORED = BASE_OUTPUTS - BASE_EXCLUSIONS
# Ruled exclusions, installed by --step install-exclusions and adjudicated by
# --step adjudicate-exclusions, as docs/argon/spec.json lists them. This
# release rules none: Max ruled d1252 (VA 039, OH 025) and d1263 (the Tax
# Table) on 2026-10-13, both to keep, so nothing scored changes on their points.
SPEC_PATH = Path("docs/argon/spec.json")
NEW_EXCLUSIONS = 0
RELEASE_EXCLUSIONS = BASE_EXCLUSIONS + NEW_EXCLUSIONS
RELEASE_SCORED = BASE_OUTPUTS - RELEASE_EXCLUSIONS
MODELS = {"argon": "gemini-4-argon", "musespark": "muse-spark-1.3"}
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
# The judge template (policybench.judge_template) this driver renders new
# and re-opened cases on: v2, which drops v1's claim that the reference
# pipeline survived an adversarial review with its real bugs fixed (#210). A
# seed case keeps the version its sidecar records (v1 for the cases judged
# before release 20261013, v2 for the 151 that release judged and the five
# release 20261013b re-judged), so the stage's audit mixes the two.
JUDGE_TEMPLATE_VERSION = 2
ADJUDICATIONS = "us_adjudications.json"
# Stage files export binds: the cases a new model re-opened, and the
# wording-only amendments a developer lists for them.
PROMPT_CHANGES = "prompt-changes.json"
AMENDMENTS = "wording-amendments.json"
# The published record of how each new verdict (a case a new model re-opened)
# was judged. Export requires it to describe the staged verdicts and binds its
# bytes in the receipt.
JUDGE_PROVENANCE_PATH = "docs/argon/judge_provenance.json"
JUDGE_PROVENANCE = ROOT / JUDGE_PROVENANCE_PATH
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
# The commit whose tree holds release 20261013b. PENDING(#218): PR #218's
# frozen head; becomes its squash merge on main, whose tree must be the same.
BASE_COMMIT = "6c44858feddc68890738e6f07b31ab9e6968bac1"
# Release 20261013b's references (policyengine-us 2.41.0), which are release
# 20261013's byte for byte: 20261013b re-judged five verdicts and changed no
# reference. Prepare stages them unchanged, and they stay the release's.
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
# every stage after it through release 20261013b's:
# results/local/unified_audit/grounding.csv in the main clone. Every seed
# prompt re-renders byte-identically from it and the committed snapshot, so a
# different grounding would silently invalidate carried-over verdicts.
GROUNDING_SHA256 = "b1e4a9bc74d762f410524a147efcda7d705c3afcfa3dc27f720fa60c54a7b55c"
# The seed: every judged case of release 20261013b's audit, with the sha256 of
# its prompt and of its verdict, committed at docs/argon/seed_digest.csv:
# release 20261013's 677 judged cases (docs/musewonder/seed_digest.csv with the
# 151 that release judged, docs/musewonder/judge_provenance.json, written over
# them) with the five that release 20261013b re-judged written over those.
# This pins that file's bytes; prepare refuses any other seed and binds this
# one in stage.json, and a carried-over verdict must keep the seed's bytes.
SEED_DIGEST = ROOT / "docs/argon/seed_digest.csv"
# docs/release_20261013b/seed_digest.csv, copied.
SEED_DIGEST_SHA256 = "0f59925720a5c4f73f05585d7fffce4df8f70d78f506d0ed3c58587bddff911d"
# Each new model's supervised run as it finished, pinned outside the stage: the
# sha256 of the run directory's predictions.csv and run_state.json, which
# --step pin-inputs writes here. Export and the freeze read the file as
# committed at HEAD, and the stage's inputs/<slug>/ copies must be those bytes.
INPUT_PINS_PATH = "docs/argon/input_pins.json"
INPUT_PINS = ROOT / INPUT_PINS_PATH
PINNED_INPUTS = ("predictions.csv", "run_state.json")
# Incumbent usage the exporter cannot recompute from committed predictions:
# Fable 5 ran through the Anthropic batch adapter, and its rows carry no cost,
# token or latency fields, so export_full_run reports $0 and omits the rest.
# The released values are carried over; the drift gate then checks every field.
CARRIED_USAGE = {
    "claude-fable-5": ("costUsd", "costPerHousehold", "totalTokens", "latencySeconds")
}
KEY = ["scenario_id", "variable"]
# The tree whose committed annotations render every seed prompt: release
# 20261013b's own (PR #218's merge). Every judged case re-renders from it on
# the template version its sidecar records (tests/test_judge_template.py's
# committed-prompt invariant), so this is BASE_COMMIT.
SEED_RELEASE_COMMIT = BASE_COMMIT
REFERENCE_EXPLANATIONS = (
    Path("annotations") / RUN_NAME / "us_case_reference_explanations.csv"
)
# The cases whose reference explanation changed between the seed's rendering
# and the base. Both are release 20261013b, so none: reworded_since_seed()
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
    """Every reference file in ``directory`` must equal its 20261013b pin; the
    exclusion record may instead be the release's (``exclusions_sha256``).

    ``pins`` replaces the 20261013b pins outright: an installed engine upgrade
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
            "finished, written by scripts/finish_argon.py --step pin-inputs "
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


def new_model_row_differences(stage: Path, limit: int = 5) -> list[str]:
    """Where a new model's rows in the bundle's predictions are not its run's.

    Every column of the staged run file (inputs/<slug>/predictions.csv, which
    verify_input_pins pins) is compared cell by cell, as text, keyed by
    scenario and variable: the answers and also the cost, token and latency
    columns the payload's costUsd, totalTokens and latencySeconds come from.
    No column is exempt. prepare_inputs copies the run file, and fold_board
    reads it with read_csv and writes its concat with the base by to_csv.
    That round trip could rewrite a cell (an integer column the base leaves
    blank would come back as a float), and such a cell is refused, never
    skipped; on the real stage it changes no cell of the run's 26 columns
    (its token and cost columns are already floats). A bundle column the run
    lacks (a base column the concat adds) must be empty on the new model's
    rows.
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
                f"{model}: the bundle holds {len(board)} rows, not the run's "
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
    differ = new_model_row_differences(stage)
    require(
        not differ,
        f"{sorted(MODELS.values())} rows in the bundle's predictions are not the "
        f"pinned run's: {differ}; prepare a new stage",
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
    """The committed dashboard pointer (release 20261013b until the freeze)."""
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
        # The compact snapshot freezes the country payload, not its wrapper.
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
            "base predictions differ from committed 20261013b snapshot",
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
    """A file as committed at BASE_COMMIT, whose tree holds release 20261013b.

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
    """The snapshot's predictions are release 20261013b's.

    The pin is that release's own: the snapshot manifest as committed at
    BASE_COMMIT, not the working tree's, which could be edited together with
    the predictions it pins.
    """
    manifest = json.loads(
        base_commit_blob(Path("paper/snapshot/20260501/manifest.json"))
    )
    pin = manifest["source_run_artifacts"][RUN_NAME]["files"]["predictions.csv.gz"]
    require(
        digest(snapshot / "predictions.csv.gz") == pin,
        "committed base predictions fail release 20261013b's manifest hash",
    )


def base_payload_from_commit() -> dict:
    """Release 20261013b's payload, read from BASE_COMMIT and checked."""
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
    """Release 20261013b's adjudication record file, read from BASE_COMMIT.

    The working-tree copy is not a baseline: the freeze overwrites it, and a
    freeze that stops partway would leave the staged record in its place.
    """
    path = Path("annotations") / RUN_NAME / ADJUDICATIONS
    return json.loads(base_commit_blob(path))


def base_adjudications() -> list[dict]:
    """Release 20261013b's adjudication entries, read from BASE_COMMIT."""
    from policybench.adjudications import parse_adjudications

    path = Path("annotations") / RUN_NAME / ADJUDICATIONS
    return parse_adjudications(base_adjudication_record(), f"{BASE_COMMIT[:12]}:{path}")


# --- Ruled exclusions (none in this release) ---------------------------------

EXCLUSION_REASON_CODES = {
    "reference_engine_defect": ("reference_engine_defect", "engine_defect"),
    "reference_depends_on_unlisted_input": ("prompt_ambiguity", "unlisted_input"),
    "reference_law_published_after_freeze": ("reference_later_law", "later_law"),
}
# Release 20261013b's date conventions: the waves it names, and the end of the
# sentence on its last wave, after which a new wave's sentence goes.
DATE_CONVENTIONS_BASE = (
    "adjudicated_on names the audit wave that made the decision (2026-09-05, "
    "2026-09-22, 2026-09-29, 2026-10-05, 2026-10-06 or 2026-10-10)."
)
DATE_CONVENTIONS_LAST_WAVE = " or 2026-10-10)"
DATE_CONVENTIONS_ANCHOR = (
    "moved onto an input the prompt does not state, and were written on 2026-10-10 UTC."
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
    """Release 20261013b's exclusion record, read from BASE_COMMIT and pinned."""
    blob = base_commit_blob((SNAPSHOT / "reference_exclusions.json").relative_to(ROOT))
    require(
        hashlib.sha256(blob).hexdigest()
        == BASE_REFERENCE_SHA256["reference_exclusions.json"],
        "release 20261013b's exclusion record does not match its pin",
    )
    return json.loads(blob)


def build_release_exclusions(base: dict, spec: dict) -> dict:
    """Release 20261013b's record plus the spec's ruled records (none here).

    The new records go after the earlier waves' and before the audit's
    trailing scenario_023 record (tests/test_reference_upgrade.py requires that
    tail); the derivation's new sentence goes before the 2026-09-29 marker, as
    release 20261013b's did. Every earlier record keeps its bytes.
    """
    import copy
    import tempfile

    from policybench.reference_exclusions import load_reference_exclusions

    doc = copy.deepcopy(base)
    new = spec_records(spec)
    if not new:
        # Nothing ruled: the release's record is release 20261013b's, and the
        # spec may carry no edit or derivation sentence for records it lacks.
        require(
            not spec.get("record_edits") and not spec.get("derivation_insert"),
            "the spec edits records or the derivation but rules no record",
        )
        return doc
    tail = doc["exclusions"][-1]
    require(
        spec_key(tail) == ("scenario_023", "head_medicaid_eligible"),
        "release 20261013b's record does not end with the audit's scenario_023 record",
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

    Prepare staged release 20261013b's record (pinned); this step replaces it
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
            "the stage's exclusion record is not release 20261013b's",
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
    audit tree) as its judge fields, in release 20261013b's entry order. An
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
            # In release 20261013b's entry order, the flag follows the adjudicator.
            entry["excluded_from_scoring"] = True
    require(
        set(decision) <= set(entry), f"{spec_key(item)}: a decision field is missing"
    )
    entry["reasoning"] = base["reasoning"] + " " + item["reasoning"]
    return entry


# A triage decision's fields, in release 20261013b's entry order (an affirmed
# reference carries no excluded_from_scoring, as release 20261013b's do not).
# A decision on a case whose verdict flags nothing carries no reference_verdict
# or reference_basis, as release 20261013b's scenario_007 and scenario_008
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
    """docs/argon/spec.json's triage_adjudications: the developer's decisions
    on re-opened cases whose verdict triage could not accept as it stands.
    Each keeps the output scored and gives the case's rows the decided final
    class. It either affirms a reference the case's verdict flagged
    (reference_verdict "affirmed", with its basis) or, where the verdict flags
    nothing, resolves rows the judge gave a class outside the final set (no
    reference verdict or basis, as release 20261013b's scenario_007 decision).
    An exclusion is ruled, never a triage decision.

    The driver installs no engine upgrade (``upgrade`` is always None), so the
    decisions are this release's own wave: each is dated by the spec's
    triage_decided_on."""
    require(upgrade is None, "this release's driver installs no engine upgrade")
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
            f for f in TRIAGE_FIELDS if f not in ("reference_verdict", "reference_basis")
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
    on an unflagged case (``resolves``). This driver installs no engine
    upgrade, so decision_wave builds only the second form."""

    day: str
    excludes: bool
    affirms: bool
    upgrade: bool = True
    resolves: bool = False


def decision_wave(added, triage) -> DecisionWave | None:
    """The DecisionWave of the release's triage decisions (``triage``, as
    triage_items lists them), or None when there are none, all dated by one
    day, their adjudicated_on. ``added`` (upgrade_decisions) is always empty:
    the driver installs no engine upgrade."""
    require(not added, "this release's driver installs no engine upgrade")
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
    """Release 20261013b's date conventions with each wave this release adds
    named; the one definition the adjudicate step writes and the record gate
    expects.

    A wave is added for the spec's ruled records, when it rules any (its
    decided_on, with its wave_sentence and adjudications_written_on), and for
    ``wave`` (decision_wave): this release's triage decisions, with the day
    the spec says they were written (triage_adjudications_written_on), or, in
    finish_musewonder.py's form, an installed engine upgrade's decisions
    (upgrade_adjudications_written_on). With neither, the conventions are
    release 20261013b's, unchanged.
    """
    require(
        conventions.count(DATE_CONVENTIONS_BASE) == 1
        and conventions.count(DATE_CONVENTIONS_ANCHOR) == 1,
        "the record's date conventions are not release 20261013b's",
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
        "the base conventions do not end their wave list on 2026-10-10",
    )
    named = ", ".join(["2026-10-10", *days[:-1]]) + f" or {days[-1]})"
    waves = DATE_CONVENTIONS_BASE.replace(DATE_CONVENTIONS_LAST_WAVE, ", " + named)
    conventions = conventions.replace(DATE_CONVENTIONS_BASE, waves)
    return conventions.replace(
        DATE_CONVENTIONS_ANCHOR, DATE_CONVENTIONS_ANCHOR + sentence
    )


def upgrade_decisions(upgrade, spec: dict | None = None) -> list[tuple[dict, dict]]:
    """The (spec item, build record) pairs that decide the outputs an installed
    engine upgrade newly excludes, in (scenario_id, variable) order.

    docs/argon/spec.json's upgrade_adjudications holds one item per such
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
        f"engine upgrade newly excludes: {sorted(added)}, not {sorted(keys)}",
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
    build keeps excluded, and drops the decisions of the release 20261013b
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
        "put the staged record back to release 20261013b's (from git at "
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
    level other than the entries is release 20261013b's.

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

    Where they differ from 20261013b's, the entry must name the case's current
    Opus 5.5 verdict (bound by its sidecar) as its judge, date it by that
    sidecar's UTC day, and keep 20261013b's judge_previous with exactly one
    item appended: the replaced verdict, which is the one 20261013b's entry
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
                problems.append("judge_previous is not 20261013b's plus one item")
            elif restated[-1] != named_item(original):
                problems.append(
                    "the appended judge_previous item is not the verdict "
                    "20261013b's entry names"
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
    """Where the staged decisions on the ten ruled outputs are not exactly what
    exclusion_entry builds: a new one from its case's bound verdict, and
    scenario_051's from its release 20261013b entry with the judge fields the
    restate script gave it.

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
            # The staged entry before the ruling: release 20261013b's decision
            # fields and reasoning, with the judge fields the restate script
            # wrote. Outside the judge fields it must be 20261013b's entry.
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
            problems.append(f"{case}: release 20261013b already decides it")
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
    """A staged record differs from 20261013b's only where it has a reason to.

    Only a case a new model re-opened (``rejudged``) may change, and only in
    its judge fields (the restate script's JUDGE_FIELDS) and in the reasoning
    wording the listed amendments change, exactly as they say. Every other
    field of every committed entry keeps its value and its place, key order
    included, and the committed entries keep their order. A new entry may only
    decide a re-opened case, and none may be dropped. Returns how many staged
    entries are new.

    With an engine upgrade installed, ``regenerated`` names the ruled outputs
    it regenerated (no longer decided as ruled) and ``dropped`` the cases of
    the release 20261013b records it regenerated: exactly those decisions must
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
        f"Staged adjudications drop decisions release 20261013b lacks: {stray[:8]}",
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

    Checked in memory against release 20261013b's record (from git) and the
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
    # A dropped decision is gone, so an entry on its case is new, not restated.
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
            f"matches {int(mask.sum())} rows, not one",
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
    """The 20261013b payload an export compares the incumbents against.

    Before the freeze the live pointer and the committed snapshot are
    20261013b's, and resolve_base checks all of them. After the freeze they are
    this release's own, so a re-export (after a fix to the staged annotations)
    reads the 20261013b run payload from BASE_COMMIT instead and checks that it
    rewraps to the 20261013b release asset (BASE_SHA256). Any other pointer is
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
            "estimated_cost_usd",
            "total_tokens",
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
    """The seed digest as docs/argon/seed_digest.csv spells it."""
    rows = [
        f"{case},{item['prompt_sha256']},{item['verdict_sha256']}\n"
        for case, item in sorted(seed.items())
    ]
    return "case_id,prompt_sha256,verdict_sha256\n" + "".join(rows)


def verify_seed(seed: dict[str, dict[str, str]]) -> None:
    """The seed must be the 20261013b audit the committed digest records."""
    require(
        hashlib.sha256(seed_digest_text(seed).encode()).hexdigest()
        == SEED_DIGEST_SHA256,
        "the audit seed is not release 20261013b's (see docs/argon/"
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
        "--audit-seed <the 20261013b audit>",
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
    from the staged files against release 20261013b's in git). The staged
    predictions must agree (verify_reopened_by_predictions).
    """
    derived = check_prompt_changes(
        stage / "audit",
        {case: item["prompt_sha256"] for case, item in seed.items()},
        upgraded=frozenset(),
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
    verify_reopened_by_predictions(stage, derived)


def verify_reopened_by_predictions(stage: Path, derived: dict[str, list]) -> None:
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
    from policybench.audit import _case_id, _load_manifest
    from policybench.case_annotations import wrong_prediction_rows

    us = stage / "publish" / RUN_NAME / "us"
    wrong = wrong_prediction_rows(us)
    manifest = _load_manifest(stage / "audit")
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
    """Only a case a new model joins, or one release 20261013b reworded,
    may change or appear.

    The seed's prompts re-render byte-identically from release 20261013b's
    committed snapshot (SEED_RELEASE_COMMIT) and the pinned grounding, so an
    incumbent-only case whose prompt differs (or that is new) means an input
    changed under the
    carried-over verdicts, unless its reference explanation is one release
    20261013b reworded (reworded_since_seed), or its reference value or
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
    audit = args.stage_dir / "audit"
    # Compare against the read-only seed, not the stage copy, so a retried
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
    cannot claim v2 for a prompt rendered on another version. A verdict naming
    a new model also needs bound Opus 5.5 provenance. Returns the pending
    cases; ``remove_invalid`` sets their verdicts aside. A carried-over verdict
    that fails is refused outright: a re-judge cannot restore it.
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
            if set(names) & set(MODELS.values()):
                if (
                    meta.get("judge_model_requested") != JUDGE_MODEL
                    or meta.get("judge_model_reported") != [JUDGE_MODEL]
                    or not meta.get("judge_runner")
                    or not meta.get("judged_at_utc")
                ):
                    raise ValueError("missing or mismatched Opus 5.5 provenance")
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
        problems.append(f"{len(accepted)} accepted StructuredOutput calls, not 1")
    elif json.dumps(accepted[0].get("input"), sort_keys=True) != json.dumps(
        verdict, sort_keys=True
    ):
        problems.append("its accepted StructuredOutput answer is not verdict.json")
    if len(texts) != 1:
        problems.append(f"{len(texts)} user text messages, not the prompt alone")
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
    fields its sidecar's. Its isolation must be its sidecar's: a sidecar
    records judge_isolation only when scripts/run_audit_claude.sh's hardened
    runner wrote it, and only an isolated entry's group says "isolated: ".
    An isolated verdict's sidecar must record a token login
    (judge_auth.method oauth_token), and its transcript,
    claude.transcript.jsonl, must pass the runner's transcript checks
    (transcript_problems), its prompt and verdict included: the one user
    text message must be the staged prompt.md, and the one accepted
    StructuredOutput answer the staged verdict.json.
    """
    record = json.loads(record_path.read_text())
    entries = record.get("verdicts") if isinstance(record, dict) else None
    require(
        isinstance(entries, list) and all(isinstance(e, dict) for e in entries),
        f"{JUDGE_PROVENANCE_PATH} lists no verdicts",
    )
    require(
        set(record) == JUDGE_PROVENANCE_KEYS,
        f"{JUDGE_PROVENANCE_PATH} has keys {sorted(record)}, not "
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
        if entry.get("isolated") is not isolated:
            problems.append(
                f"the record says isolated={entry.get('isolated')!r} but the "
                f"sidecar {'records' if isolated else 'lacks'} judge_isolation"
            )
        elif isolated:
            auth = meta.get("judge_auth")
            if not isinstance(auth, dict) or auth.get("method") != "oauth_token":
                problems.append(
                    "the sidecar does not record a token login (judge_auth "
                    f"method oauth_token): {auth!r}"
                )
            problems += transcript_problems(
                case / "claude.transcript.jsonl",
                meta.get("judge_effort"),
                prompt,
                verdict,
            )
        if problems:
            wrong.append(f"{entry['case_id']}: {'; '.join(problems)}")
    require(
        not wrong,
        f"{len(wrong)} new verdicts disagree with {JUDGE_PROVENANCE_PATH}: {wrong[:4]}",
    )


# The provenance groups of this release's new verdicts, by the account their
# sidecar declares. Every one ran on the pb-judge setup-token login of Max's
# 2026-09-30 opt-in (the GPT-6.1 Sol stage's "setup-token 2"). The two Subfleet
# lanes earlier releases borrowed stay listed so a record naming either is
# grouped, not refused; this release used neither.
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
PROVENANCE_NOTE = (
    "Provenance of the new Opus 5.5 judge verdicts in the Gemini 4 Argon and "
    "Muse Spark 1.3 stage: every case either new model re-opened. Every "
    "verdict ran through scripts/run_audit_claude.sh from an empty directory "
    "outside the repo, with no tools, an allowlisted environment, no user "
    "settings and a token login, at effort xhigh, on judge template v2; each "
    "transcript passes the runner's checks. All ran on Max's second "
    "setup-token login (2026-09-30 opt-in), two at a time and then one at a "
    "time. A call whose transcript failed the runner's checks (a dropped "
    "network connection leaves retry events in it), or whose verdict missed a "
    "model, was judged again. "
    "Counts are by group. Scores do not depend on judge verdicts."
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
    return {"note": PROVENANCE_NOTE, "counts": counts, "verdicts": entries}


def write_judge_provenance(args) -> None:
    """Write JUDGE_PROVENANCE from the stage's sidecars, then check it."""
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
    JUDGE_PROVENANCE.write_text(json.dumps(record, indent=1, allow_nan=False) + "\n")
    verify_judge_provenance(cases, rejudged, JUDGE_PROVENANCE)
    print(f"Wrote {JUDGE_PROVENANCE_PATH}: {len(rejudged)} verdicts")


def judge(args, bundle) -> None:
    """Run one Claude CLI judge at a time and retry missing/hedged cases."""
    from policybench.audit import collect_audit

    audit = args.stage_dir / "audit"
    seed = load_seed(args.stage_dir)
    for _ in range(3):
        validate_verdicts(audit, remove_invalid=True, seed=seed)
        subprocess.run(
            ["bash", str(ROOT / "scripts/run_audit_claude.sh"), str(audit)],
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
) -> dict:
    """The payload export writes, built from ``bundle``; the one definition.

    export_full_run's US payload must hold all BOARD_MODELS (50) models. For a
    release, its roster must be the base's 48 incumbents plus the two
    additions, Fable 5's usage is carried from ``live`` (CARRIED_USAGE), every
    model is scored on RELEASE_SCORED outputs, and no incumbent may drift;
    then the dashboard schema. The freeze rebuilds the staged payload with
    this. export_full_run writes data.json, us/data.json and us/analysis/ into
    ``bundle``.

    The scope check: this release changes no reference and no exclusion, so
    with release 20261013b's exclusion record put back every incumbent's
    modelStats must be release 20261013b's byte for byte.
    """
    from policybench.dashboard_schema import validate_dashboard_payload
    from policybench.full_run_export import export_full_run

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
        expected = RELEASE_SCORED
        require(
            set(scored.values()) == {expected},
            f"every model must be scored on {expected} outputs: {scored}",
        )
        # The scope check: with release 20261013b's exclusion record put back,
        # every incumbent's modelStats is release 20261013b's byte for byte.
        # The release's record is that record, so no incumbent may change.
        import tempfile

        from release_20261006 import export_payload

        with tempfile.TemporaryDirectory() as scratch:
            record = Path(scratch) / "reference_exclusions.json"
            record.write_text(exclusions_text(base_exclusion_record()))
            scoped = export_payload(bundle, live, record)
        scoped_stats = scoped["countries"]["us"]["modelStats"]
        require(len(scoped_stats) == BOARD_MODELS, "scope export lost a model")
        drift = incumbent_drift(scoped_stats, previous)
        require(
            not drift,
            "with release 20261013b's exclusion record, incumbent modelStats "
            f"drift: {drift}",
        )
    errors = validate_dashboard_payload(payload, require_failure_annotations=not early)
    require(not errors, f"payload validation failed: {errors[:8]}")
    if partial:
        payload["stage2Status"] = (
            "PARTIAL — incomplete household cohorts, not a release"
        )
    return payload


def export(args, bundle, live) -> dict:
    """Export into scratch, preserve incumbent statistics, and gate release."""
    if not args.partial:
        stage_upgrade(args.stage_dir)
        # After the freeze the pointer and committed record are this release's.
        release = release_exclusions_sha256()
        frozen = live_pointer()["tag"] == RELEASE_TAG
        verify_reference_pins(
            SNAPSHOT, "committed reference", release if frozen else None
        )
        verify_reference_pins(bundle / "us", "staged reference", release)
    if not args.early:
        verify_new_model_inputs(args.stage_dir)
        verify_judge_provenance(
            args.stage_dir / "audit" / "cases",
            rejudged_cases(args.stage_dir),
            JUDGE_PROVENANCE,
        )
    payload = build_payload(bundle, live, partial=args.partial, early=args.early)
    stats = payload["countries"]["us"]["modelStats"]
    path = args.stage_dir / (
        f"PARTIAL-data-board{BOARD_MODELS}.json"
        if args.partial
        else f"data-board{BOARD_MODELS}.json"
    )
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
        # The cases a new model re-opened, the listed wording amendments and the
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
            },
        )
    return payload


# --- No engine upgrade of the references --------------------------------------
#
# finish_musewonder.py could install an engine upgrade of the references
# (--step install-references): a build gated against the base release, with
# the decisions of the records it regenerated dropped. This release has no
# such step. Its references are release 20261013b's, computed on
# policyengine-us 2.41.0, and the publication check
# (reference_audit/2026-10-12-engine-upgrade/scripts/sweep_timing.py check)
# found that the newest release gives the same value for every output. If a
# later release moves an output before publication, that check exits non-zero
# and the release stops: moving the references then needs an engine-upgrade
# audit with its own builder, as release 20261013 had, and a driver that
# installs its build. The helpers that took an installed upgrade keep their
# parameters and are called with none, so they stay comparable, line for
# line, with finish_musewonder.py's.

# The engine release 20261013b's references were computed on: its sidecar's
# last revision, the 2026-10-13 engine_upgrade.
BASE_ENGINE = "policyengine-us 2.41.0"


def stage_upgrade(stage: Path) -> None:
    """This release installs no reference build, so a stage has none: refuse
    a stage whose receipt claims one (it was not prepared by this driver)."""
    path = stage / "stage.json"
    if path.is_file():
        require(
            not json.loads(path.read_text()).get("references_installed"),
            "stage.json records an installed reference build, which this "
            "release's driver cannot install or gate; prepare a new stage",
        )
    return None


def grounding_lookup(path: Path) -> dict[tuple[str, str], str]:
    """The audit grounding by output, as prepare_audit takes it."""
    import pandas as pd

    grounding = pd.read_csv(path)
    return {
        (str(r.scenario_id), str(r.variable)): str(r.grounding)
        for r in grounding.itertuples()
    }


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
            f"--{name}"
            for name in ("built", "explanations", "actions", "grounding")
            if getattr(args, name) is None
        ]
        if missing:
            parser.error(f"install-references requires {' '.join(missing)}")
        for name in ("built", "explanations", "actions", "grounding"):
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
    if args.step == "prepare":
        runs = discover_new_models(args.runs_root)
        print("All copied run states qualify; resolving 20261013b base", flush=True)
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
        if args.early:
            export(args, bundle, live)
        else:
            seed = prepare_cases(args, bundle)
        inputs = [p for p in (stage / "inputs").rglob("*") if p.is_file()]
        inputs += [
            bundle / "us" / name for name in (*REFERENCE_FILES, "predictions.csv")
        ]
        receipt = {
            "partial": args.partial,
            "early": args.early,
            "base_tag": BASE_TAG,
            "base_commit": BASE_COMMIT,
            "files": {str(p.relative_to(stage)): digest(p) for p in inputs},
        }
        if seed is not None:
            receipt["seed"] = seed
        write_json(receipt_path, receipt)
    else:
        receipt = json.loads(receipt_path.read_text())
        require(
            not receipt["partial"] and not receipt["early"],
            "early/partial stage cannot become a release; prepare fresh full inputs",
        )
        for name, expected in receipt["files"].items():
            require(
                digest(stage / name) == expected,
                f"staged input changed: {name}; prepare a new stage",
            )
        (stage / "release-ready.json").unlink(missing_ok=True)
        if args.step in ("triage", "export", "adjudicate-exclusions"):
            installed = receipt.get("exclusions_installed") or {}
            stage_upgrade(stage)
            require(
                installed.get("sha256") == release_exclusions_sha256(),
                "the stage's exclusions are not the release's; run "
                "--step install-exclusions",
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
