"""Stage the Claude Haiku 5.5 addition; never publish or change tracked data.

Adapted from finish_gpt61sol.py. It folds one supervised run onto the 46-model
board of release dashboard-data-20261006 without any reference value revision:
the reference outputs and scenarios are pinned. The release also adds the ten
exclusions Max ruled on 2026-10-06 (d994, d1022), so an incumbent's modelStats
may change only as those records explain. All outputs, including audit
verdicts and adjudications, stay in --stage-dir. See docs/haiku55/design.md for
the run and release procedure.
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
BASE_TAG = "dashboard-data-20261006"
# The one place the new release's tag is named. The lead may change it at
# freeze time; freeze_haiku55.py and the design note read it from here.
RELEASE_TAG = "dashboard-data-20261009"
BASE_SHA256 = "1780d2ec37f90b654265f8c7a191ba57f5ec5c4d28624bf9d2e2de8a48d2f871"
BASE_MODELS = 46
BASE_OUTPUTS = 1984
BASE_EXCLUSIONS = 64
BASE_SCORED = BASE_OUTPUTS - BASE_EXCLUSIONS
MODELS = {"haiku55": "claude-haiku-5.5"}
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
ADJUDICATIONS = "us_adjudications.json"
# Stage files export binds: the cases GPT-6.1 Sol re-opened, and the
# wording-only amendments a developer lists for them.
PROMPT_CHANGES = "prompt-changes.json"
AMENDMENTS = "wording-amendments.json"
# The published record of how each new verdict (a case GPT-6.1 Sol re-opened)
# was judged. Export requires it to describe the staged verdicts and binds its
# bytes in the receipt.
JUDGE_PROVENANCE_PATH = "docs/haiku55/judge_provenance.json"
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
# A commit whose tree holds release 20261006 (PR #202's head; replaced by its
# merge on main before the freeze).
BASE_COMMIT = "8b831f2cfaa071eb850ed85d4f29f874a1671e8d"
# Release 20261006's references. Prepare stages them unchanged; the release's
# ten new exclusion records are added after triage (see EXCLUSION_SPEC).
BASE_REFERENCE_SHA256 = {
    "reference_outputs.csv": (
        "e8bbba8fd3e90f78e7c0e83df06227bc1c94563e92f7405fe12be853a30b2466"
    ),
    "reference_outputs.csv.meta.json": (
        "816fef53c452d8520a321bc12bc29b28da1e7956a06818e5ec13d7fc7b371a4b"
    ),
    "reference_exclusions.json": (
        "31e9e3cdd78bfa0296d5f88d5ee52eb22f9520c0ed902d9e04630a6df2a08d9a"
    ),
    "scenarios.csv": (
        "71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a"
    ),
    "scenarios.csv.meta.json": (
        "03a66e90b86e9bd0cc77f27520784bd581777762f749675dc716e24c1b8eaebb"
    ),
}
# The grounding the 20260929 stage (adds0928-v3) rendered into its prompts, and
# the GPT-6.1 Sol and 20261006 stages after it:
# results/local/unified_audit/grounding.csv in the main clone. Every seed
# prompt re-renders byte-identically from it and the committed snapshot, so a
# different grounding would silently invalidate carried-over verdicts.
GROUNDING_SHA256 = "b1e4a9bc74d762f410524a147efcda7d705c3afcfa3dc27f720fa60c54a7b55c"
# The seed: every judged case of release 20261006's audit (release 20260930's,
# carried unchanged), with the sha256 of its prompt and of its verdict,
# committed at docs/haiku55/seed_digest.csv. This
# pins that file's bytes; prepare refuses any other seed and binds this one in
# stage.json, and a carried-over verdict must keep the seed's bytes.
SEED_DIGEST = ROOT / "docs/haiku55/seed_digest.csv"
SEED_DIGEST_SHA256 = "c780af63adf7f99a48e7852b81d880bc251255338e905f66d104b38db02e8430"
# Claude Haiku 5.5's supervised run as it finished, pinned outside the stage: the
# sha256 of the run directory's predictions.csv and run_state.json, which
# --step pin-inputs writes here. Export and the freeze read the file as
# committed at HEAD, and the stage's inputs/<slug>/ copies must be those bytes.
INPUT_PINS_PATH = "docs/haiku55/input_pins.json"
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
# Release 20260930's tree, whose committed annotations rendered the seed's
# prompts: release 20261006 carried that audit over without re-rendering it.
SEED_RELEASE_COMMIT = "8b4c0ca146bb6f66deba6ce24009d49d70d92df2"
REFERENCE_EXPLANATIONS = (
    Path("annotations") / RUN_NAME / "us_case_reference_explanations.csv"
)
# The cases whose reference explanation release 20261006 reworded (its
# annotation rewrite ledger, docs/release_20261006/annotation_rewrites.json)
# after the seed was rendered. The explanation is the one annotation a judge's
# prompt carries, so these prompts re-render differently from the seed's, and
# prepare re-judges them like a case Claude Haiku 5.5 joins. reworded_since_seed()
# derives the set from git and must find exactly these.
REWORDED_SINCE_SEED = frozenset(
    {
        "us__scenario_031__head_medicaid_eligible",
        "us__scenario_032__payroll_tax",
        "us__scenario_043__payroll_tax",
        "us__scenario_077__state_income_tax_before_refundable_credits",
        "us__scenario_081__federal_income_tax_before_refundable_credits",
        "us__scenario_081__payroll_tax",
        "us__scenario_082__payroll_tax",
        "us__scenario_114__federal_income_tax_before_refundable_credits",
        "us__scenario_114__state_income_tax_before_refundable_credits",
    }
)


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


def verify_reference_pins(directory: Path, label: str) -> None:
    """Every reference file in ``directory`` must equal its 20260929 pin."""
    for name, pin in BASE_REFERENCE_SHA256.items():
        path = directory / name
        require(
            path.is_file() and digest(path) == pin,
            f"{label} {name} does not match its pin; this release has no "
            "reference revision",
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
            "The sha256 of Claude Haiku 5.5's supervised run files as the run "
            "finished, written by scripts/finish_haiku55.py --step pin-inputs "
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
    """The committed dashboard pointer (release 20260929 until the freeze)."""
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
            "base predictions differ from committed 20260929 snapshot",
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
    """A file as committed at BASE_COMMIT, whose tree holds release 20260929.

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
    """The snapshot's predictions are release 20260929's.

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
        "committed base predictions fail release 20260929's manifest hash",
    )


def base_payload_from_commit() -> dict:
    """Release 20260929's payload, read from BASE_COMMIT and checked."""
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
    """Release 20260929's adjudication record file, read from BASE_COMMIT.

    The working-tree copy is not a baseline: the freeze overwrites it, and a
    freeze that stops partway would leave the staged record in its place.
    """
    path = Path("annotations") / RUN_NAME / ADJUDICATIONS
    return json.loads(base_commit_blob(path))


def base_adjudications() -> list[dict]:
    """Release 20260929's adjudication entries, read from BASE_COMMIT."""
    from policybench.adjudications import parse_adjudications

    path = Path("annotations") / RUN_NAME / ADJUDICATIONS
    return parse_adjudications(base_adjudication_record(), f"{BASE_COMMIT[:12]}:{path}")


def record_text(record: dict) -> str:
    """An adjudication record as the committed file spells it."""
    return json.dumps(record, indent=2, ensure_ascii=False) + "\n"


def verify_record_form(text: str, base: dict) -> None:
    """The staged record's bytes are exactly its parsed content, and its top
    level other than the entries is release 20260929's.

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
    require(
        record_text({k: v for k, v in record.items() if k != "adjudications"})
        == record_text({k: v for k, v in base.items() if k != "adjudications"}),
        "the staged adjudication record changes its note, schema or date "
        "conventions; only entries may change",
    )


def verify_restatements(
    base: list[dict], staged: list[dict], rejudged: frozenset[str], cases_dir: Path
) -> None:
    """A re-opened entry's judge fields must be the restate script's.

    Where they differ from 20260929's, the entry must name the case's current
    Opus 5.5 verdict (bound by its sidecar) as its judge, date it by that
    sidecar's UTC day, and keep 20260929's judge_previous with exactly one
    item appended: the replaced verdict, which is the one 20260929's entry
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
                problems.append("judge_previous is not 20260929's plus one item")
            elif restated[-1] != named_item(original):
                problems.append(
                    "the appended judge_previous item is not the verdict "
                    "20260929's entry names"
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
    """The cases GPT-6.1 Sol re-opened: prompt-changes.json's changed and added.

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

    Each names a case GPT-6.1 Sol re-opened, a wording field, the exact old
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


def verify_adjudication_changes(
    base: list[dict],
    staged: list[dict],
    rejudged: frozenset[str],
    amendments: list[dict],
) -> int:
    """A staged record differs from 20260929's only where it has a reason to.

    Only a case GPT-6.1 Sol re-opened (``rejudged``) may change, and only in
    its judge fields (the restate script's JUDGE_FIELDS) and in the reasoning
    wording the listed amendments change, exactly as they say. Every other
    field of every committed entry keeps its value and its place, key order
    included, and the committed entries keep their order. A new entry may only
    decide a re-opened case, and none may be dropped. Returns how many staged
    entries are new.
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
    dropped = sorted(set(before) - set(after))
    require(not dropped, f"Staged adjudications drop recorded decisions: {dropped}")
    new = sorted(set(after) - set(before))
    require(
        set(new) <= rejudged,
        "Staged adjudications add decisions on cases GPT-6.1 Sol did not "
        f"re-open: {sorted(set(new) - rejudged)[:8]}",
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
    path: Path, rejudged: frozenset[str], amendments: list[dict], cases_dir: Path
) -> list[dict]:
    """The staged record, with its listed reasoning amendments applied.

    Checked in memory against release 20260929's record (from git) and the
    stage's verdicts; written back only when an amendment was not applied yet.
    """
    from freeze_snapshot import verify_adjudications_keep_judge_verdicts

    from policybench.adjudications import parse_adjudications

    base_record = base_adjudication_record()
    base = base_adjudications()
    current = path.read_text()
    verify_record_form(current, base_record)
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
    verify_record_form(text, base_record)
    entries = parse_adjudications(json.loads(text), path)
    verify_adjudication_changes(base, entries, rejudged, amendments)
    verify_restatements(base, entries, rejudged, cases_dir)
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
    """The 20260929 payload an export compares the incumbents against.

    Before the freeze the live pointer and the committed snapshot are
    20260929's, and resolve_base checks all of them. After the freeze they are
    this release's own, so a re-export (after a fix to the staged annotations)
    reads the 20260929 run payload from BASE_COMMIT instead and checks that it
    rewraps to the 20260929 release asset (BASE_SHA256). Any other pointer is
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
        expected_provider = registry[run.model].split("/")[-1]
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
    """The seed digest as docs/gpt61sol/seed_digest.csv spells it."""
    rows = [
        f"{case},{item['prompt_sha256']},{item['verdict_sha256']}\n"
        for case, item in sorted(seed.items())
    ]
    return "case_id,prompt_sha256,verdict_sha256\n" + "".join(rows)


def verify_seed(seed: dict[str, dict[str, str]]) -> None:
    """The seed must be the 20260929 audit the committed digest records."""
    require(
        hashlib.sha256(seed_digest_text(seed).encode()).hexdigest()
        == SEED_DIGEST_SHA256,
        "the audit seed is not release 20260929's (see docs/gpt61sol/"
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
        "--audit-seed <the 20260929 audit>",
    )
    verify_seed(receipt["seed"])
    verify_prompt_changes(stage, receipt["seed"])
    return receipt["seed"]


def verify_prompt_changes(stage: Path, seed: dict[str, dict[str, str]]) -> None:
    """prompt-changes.json must be what the stage's prompts say against the seed.

    A case whose prompt is the seed's is kept, one whose prompt differs is
    changed and one the seed lacks is added; GPT-6.1 Sol must be among the
    wrong models of every changed or added case, and no seed case may vanish
    (check_prompt_changes, as prepare applies it). The staged predictions
    must agree (verify_reopened_by_predictions).
    """
    derived = check_prompt_changes(
        stage / "audit", {case: item["prompt_sha256"] for case, item in seed.items()}
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
    """The manifest's claim that GPT-6.1 Sol re-opened a case must hold.

    cases.jsonl is editable, so re-score the staged predictions against the
    staged references with wrong_prediction_rows, the rule prepare_audit
    used to list each case's wrong models. A changed or added case must list
    the new model exactly when its prediction is wrong; any other case it
    gets wrong must be parse-failure-only as the manifest records it, so a
    kept case needs the new model's prediction right.
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
            (row.scenario_id, row.variable): tuple(row) for row in frame.itertuples()
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


def check_prompt_changes(audit: Path, seeded: dict[str, str]) -> dict[str, list]:
    """Only a case Claude Haiku 5.5 joins, or one release 20261006 reworded,
    may change or appear.

    The seed's prompts re-render byte-identically from release 20260930's
    committed snapshot and the pinned grounding, so an incumbent-only case
    whose prompt differs (or that is new) means an input changed under the
    carried-over verdicts, unless its reference explanation is one release
    20261006 reworded (reworded_since_seed); that case is re-judged.
    """
    manifest = [
        json.loads(line) for line in (audit / "cases.jsonl").read_text().splitlines()
    ]
    new_models = set(MODELS.values())
    reworded = reworded_since_seed()
    changed, added, kept, offending = [], [], [], []
    for item in manifest:
        if item["parse_failure_only"]:
            continue
        case_id = item["case_id"]
        prompt = digest(audit / "cases" / case_id / "prompt.md")
        if seeded.get(case_id) == prompt:
            kept.append(case_id)
            continue
        (changed if case_id in seeded else added).append(case_id)
        if not new_models & set(item["wrong_models"]) and case_id not in reworded:
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
    import pandas as pd

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
    grounding = pd.read_csv(args.grounding)
    lookup = {
        (str(r.scenario_id), str(r.variable)): str(r.grounding)
        for r in grounding.itertuples()
    }
    prepare_audit(bundle / "us", audit, grounding_lookup=lookup)
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
    and must record the sha256 of the prompt it judged. A verdict naming
    GPT-6.1 Sol also needs bound Opus 5.5 provenance. Returns the pending
    cases; ``remove_invalid`` sets their verdicts aside. A carried-over verdict
    that fails is refused outright: a re-judge cannot restore it.
    """
    import jsonschema

    schema = json.loads((audit / "schema.json").read_text())
    manifest = {
        item["case_id"]: item
        for item in map(json.loads, (audit / "cases.jsonl").read_text().splitlines())
    }
    seed = seed or {}
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
            bound = meta.get("prompt_sha256")
            if carried:
                if hashlib.sha256(blob).hexdigest() != seed[case_id]["verdict_sha256"]:
                    raise ValueError("a carried-over verdict is not the seed's")
                if bound is not None and bound != digest(prompt):
                    raise ValueError("verdict is bound to a different prompt")
            elif bound != digest(prompt):
                raise ValueError("a new verdict is not bound to this prompt")
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

    The record (JUDGE_PROVENANCE) lists every case GPT-6.1 Sol re-opened, each
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
    decisions = stage_adjudications(
        annotations / ADJUDICATIONS, rejudged, amendments, audit / "cases"
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
    bundle: Path, live: dict, *, partial: bool = False, early: bool = False
) -> dict:
    """The payload export writes, built from ``bundle``; the one definition.

    export_full_run's US payload must hold all 46 models. For a release, its
    roster must be the base's incumbents plus the addition, Fable 5's usage is
    carried from ``live`` (CARRIED_USAGE), and no incumbent may drift; then the
    dashboard schema. The freeze rebuilds the staged payload with this.
    export_full_run writes data.json, us/data.json and us/analysis/ into
    ``bundle``.
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
        drift = incumbent_drift(stats, previous)
        require(not drift, f"incumbent modelStats drift: {drift}")
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
        verify_reference_pins(SNAPSHOT, "committed reference")
        verify_reference_pins(bundle / "us", "staged reference")
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
        # The cases GPT-6.1 Sol re-opened, the listed wording amendments and the
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
        choices=("pin-inputs", "prepare", "bind-seed", "judge", "triage", "export"),
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
        print("All copied run states qualify; resolving 20260929 base", flush=True)
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
        if args.step == "bind-seed":
            bind_seed(args)
        elif args.step == "judge":
            judge(args, bundle)
        elif args.step == "triage":
            triage(args, bundle)
        else:
            triage(args, bundle)
            export(args, bundle, resolve_live_base(args))


if __name__ == "__main__":
    main()
