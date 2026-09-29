"""Stage the September 29 additions; never publish or change tracked data.

Adapted from the September 22 finish_opus55.py and judge_stages.py. All
outputs, including audit verdicts and adjudications, stay in --stage-dir.
See docs/adds0928/stage2_design.md for the run and release procedure.
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
from dataclasses import dataclass
from pathlib import Path

os.environ["OPENBLAS_NUM_THREADS"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RUN_NAME = "us_full_run_20260612_policyengine_4_16_1_populace"
SNAPSHOT = ROOT / "paper/snapshot/20260501/runs" / RUN_NAME
ANNOTATIONS = ROOT / "annotations" / RUN_NAME
BASE_TAG = "dashboard-data-20260922c"
RELEASE_TAG = "dashboard-data-20260929"
BASE_SHA256 = "01e7e72b3a6bdd2d3178ba32625ff769d5b81dc07541af6ea8da2c852774ddcc"
MODELS = {
    "sonnet55": "claude-sonnet-5.5",
    "grok47": "grok-4.7",
    "dsflash41": "deepseek-v4.1-flash",
}
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
# main at release dashboard-data-20260922c, whose committed references are the base.
BASE_COMMIT = "3220a7a62b6be83032e9313c9df539c619ad8932"
BASE_REFERENCE_SHA256 = {
    "reference_outputs.csv": (
        "800a19bc1c225656b93c4507933d98907e8d1a939248c8b021a9f26d33e9e0c5"
    ),
    "reference_outputs.csv.meta.json": (
        "df94cc52e2146de8b9b167772e1d6b747ce21e90b1f64e96f94bb2ac4f237d93"
    ),
    "reference_exclusions.json": (
        "25c4a9fd5fee59d07666254bdc1eae409b4a7c9f4ea0381dc8878a6ac0213035"
    ),
}
KEY = ["scenario_id", "variable"]


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


@dataclass(frozen=True)
class NewRun:
    slug: str
    model: str
    run_dir: Path
    predictions: Path
    state: dict


def discover_new_models(runs_root: Path) -> list[NewRun]:
    """Require all three completed, unstopped supervisor runs, as Opus did."""
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


def resolve_base(args):
    """Pin the live payload and its committed predictions/reference bundle."""
    import pandas as pd

    # Pandas 3 infers Arrow strings and expands repeated full raw responses
    # into large buffers. Object strings retain the CSV parser's deduplication,
    # as in the Pandas 2 environment used for the previous release.
    if hasattr(pd.options, "future") and hasattr(pd.options.future, "infer_string"):
        pd.options.future.infer_string = False

    pointer = json.loads((ROOT / "app/src/data.artifact.json").read_text())
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
        len(live["countries"]["us"]["modelStats"]) == 42, "base must have 42 models"
    )

    # An explicit alternative is allowed only if it has identical CSV bytes.
    def csv_digest(path):
        opener = gzip.open if path.suffix == ".gz" else open
        h = hashlib.sha256()
        with opener(path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()

    manifest = json.loads((ROOT / "paper/snapshot/20260501/manifest.json").read_text())
    pin = manifest["source_run_artifacts"][RUN_NAME]["files"]["predictions.csv.gz"]
    require(
        digest(SNAPSHOT / "predictions.csv.gz") == pin,
        "committed base predictions fail their manifest hash",
    )
    if args.base_predictions.resolve() != (SNAPSHOT / "predictions.csv.gz").resolve():
        require(
            csv_digest(args.base_predictions)
            == csv_digest(SNAPSHOT / "predictions.csv.gz"),
            "base predictions differ from committed September 22c snapshot",
        )
    print("Reading pinned base predictions", flush=True)
    # Rehearsals do not need repeated raw provider transcripts for incumbents.
    # Their full original CSV remains hash-pinned and untouched in the snapshot.
    usecols = (lambda column: column != "raw_response") if args.partial else None
    base = pd.read_csv(args.base_predictions, low_memory=True, usecols=usecols)
    reference = pd.read_csv(SNAPSHOT / "reference_outputs.csv")
    require(
        len(reference) == 1984 and reference.scenario_id.nunique() == 100,
        "unexpected reference universe",
    )
    require(base.model.nunique() == 42, "base predictions must have 42 models")
    for model, frame in base.groupby("model"):
        validate_keys(frame, reference, model)
    from policybench.reference_exclusions import load_reference_exclusions

    # 52 on the 22c references, plus the exclusions a reviewed reference
    # revision adds (each is listed in its changed outputs).
    revision = reference_revision()
    added = (
        0
        if revision is None
        else sum(
            c.get("cause") == "excluded_reference_depends_on_unlisted_input"
            for c in revision["changed"]
        )
    )
    require(
        len(load_reference_exclusions(SNAPSHOT)) == 52 + added,
        f"expected {52 + added} exclusions",
    )
    return base, reference, live


def base_commit_blob(path: Path) -> bytes:
    """A file as committed at BASE_COMMIT, the September 22c release commit.

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


def resolve_live_base(args) -> dict:
    """The September 22c payload an export compares the incumbents against.

    Before the freeze the live pointer and the committed snapshot are 22c's,
    and resolve_base checks all of them. After the freeze they are this
    release's own, so a re-export (after a fix to the staged annotations)
    reads the 22c run payload from BASE_COMMIT instead and checks that it
    rewraps to the 22c release asset (BASE_SHA256). Any other pointer is
    refused, as before.
    """
    pointer = json.loads((ROOT / "app/src/data.artifact.json").read_text())
    if pointer["tag"] == BASE_TAG:
        return resolve_base(args)[2]
    require(
        pointer["tag"] == RELEASE_TAG,
        "base pointer changed; review the base before staging",
    )
    blob = base_commit_blob((SNAPSHOT / "data.json.gz").relative_to(ROOT))
    live = {"countries": {"us": json.loads(gzip.decompress(blob))}}
    require(
        hashlib.sha256(json.dumps(live).encode()).hexdigest() == BASE_SHA256,
        "base payload SHA256 mismatch",
    )
    require(
        len(live["countries"]["us"]["modelStats"]) == 42, "base must have 42 models"
    )
    return live


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
            from freeze_adds0928 import validate_treatment

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
        if run.model == "deepseek-v4.1-flash":
            require(
                "provider_system_fingerprint" in frame
                and frame.provider_system_fingerprint.fillna("").ne("").all(),
                "DeepSeek moving alias lacks response fingerprint",
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
        not result["excluded"] and result["models"] == 45,
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


def prepare_cases(args, bundle) -> None:
    """Seed a private audit; changed prompts invalidate copied verdicts."""
    import pandas as pd

    from policybench.audit import prepare_audit

    require(
        args.audit_seed is not None and args.grounding is not None,
        "prepare needs --audit-seed and --grounding (read-only sources)",
    )
    audit = args.stage_dir / "audit"
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
    pending = validate_verdicts(audit, remove_invalid=True)
    write_json(args.stage_dir / "pending.json", pending)
    print(f"Prepared audit: {len(pending)} cases need Opus 5.5")


def validate_verdicts(audit: Path, remove_invalid: bool = False) -> list[str]:
    """Validate full schema and exact model coverage, not just two JSON keys."""
    import jsonschema

    schema = json.loads((audit / "schema.json").read_text())
    manifest = {
        item["case_id"]: item
        for item in map(json.loads, (audit / "cases.jsonl").read_text().splitlines())
    }
    pending = []
    for case_id, item in manifest.items():
        if item["parse_failure_only"]:
            continue
        path = audit / "cases" / case_id / "verdict.json"
        try:
            verdict = json.loads(path.read_text())
            jsonschema.validate(verdict, schema)
            names = [m["model"] for m in verdict["models"]]
            if len(names) != len(set(names)) or set(names) != set(item["wrong_models"]):
                raise ValueError("wrong model coverage")
            if set(names) & set(MODELS.values()):
                meta = json.loads(path.with_name("verdict.meta.json").read_text())
                if (
                    meta.get("verdict_sha256") != digest(path)
                    or meta.get("judge_model_requested") != JUDGE_MODEL
                    or meta.get("judge_model_reported") != [JUDGE_MODEL]
                    or not meta.get("judge_runner")
                    or not meta.get("judged_at_utc")
                ):
                    raise ValueError("missing or mismatched Opus 5.5 provenance")
        except (OSError, ValueError, jsonschema.ValidationError):
            pending.append(case_id)
            if remove_invalid:
                path.unlink(missing_ok=True)
                path.with_name("verdict.meta.json").unlink(missing_ok=True)
    return sorted(pending)


def judge(args, bundle) -> None:
    """Run one Claude CLI judge at a time and retry missing/hedged cases."""
    from policybench.audit import collect_audit

    audit = args.stage_dir / "audit"
    for _ in range(3):
        validate_verdicts(audit, remove_invalid=True)
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
        pending = validate_verdicts(audit, remove_invalid=True)
        out = collect_audit(bundle / "us", audit)
        for case_id in out["hedged"].case_id:
            for name in ("verdict.json", "verdict.meta.json"):
                (audit / "cases" / case_id / name).unlink(missing_ok=True)
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
        load_adjudications,
        verify_adjudications_applied,
    )
    from policybench.audit import collect_audit
    from policybench.reference_exclusions import (
        exclusion_keys,
        load_reference_exclusions,
    )

    audit = args.stage_dir / "audit"
    require(not validate_verdicts(audit), "missing or invalid verdicts; run judge")
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
    decisions = load_adjudications(annotations / "us_adjudications.json")
    from freeze_snapshot import verify_adjudications_keep_judge_verdicts

    verify_adjudications_keep_judge_verdicts(decisions, audit / "cases")
    rows, cases, _ = apply_adjudications(rows, cases, decisions)
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
    rows.to_csv(annotations / "us_audit_row_annotations.csv", index=False)
    cases.to_csv(annotations / "us_case_notes.csv", index=False)
    require(
        flags.empty and unresolved.empty,
        "triage required: inspect reference-flags.csv/unresolved-rows.csv; "
        "record evidence in staged us_adjudications.json and rerun triage",
    )
    print(f"Triage complete: {len(rows)} rows / {len(cases)} cases")


def base_reference_bytes(name: str) -> bytes:
    """A September 22c reference file, read from git and checked against its pin."""
    raw = base_commit_blob(SNAPSHOT.relative_to(ROOT) / name)
    require(
        hashlib.sha256(raw).hexdigest() == BASE_REFERENCE_SHA256[name],
        f"base reference {name} does not match its pin",
    )
    return raw


def reference_revision() -> dict | None:
    """The reviewed reference revision the snapshot carries, or None if unchanged.

    The snapshot may differ from the September 22c references only by one
    committed engine_upgrade revision whose `changed` list is exactly the set of
    outputs whose value differs, with those values. Anything else is refused.
    """
    import io

    import pandas as pd

    if all(
        digest(SNAPSHOT / name) == sha for name, sha in BASE_REFERENCE_SHA256.items()
    ):
        return None
    meta = json.loads((SNAPSHOT / "reference_outputs.csv.meta.json").read_text())
    require(
        meta.get("reference_csv_sha256") == digest(SNAPSHOT / "reference_outputs.csv"),
        "reference sidecar does not pin the committed reference CSV",
    )
    revision = meta["revisions"][-1]
    require(
        revision.get("kind") == "engine_upgrade",
        "changed references need a committed engine_upgrade revision",
    )
    base = pd.read_csv(
        io.BytesIO(base_reference_bytes("reference_outputs.csv"))
    ).set_index(KEY)["value"]
    new = pd.read_csv(SNAPSHOT / "reference_outputs.csv").set_index(KEY)["value"]
    require(base.index.equals(new.index), "reference output keys changed")
    diff = {key: float(new[key]) for key in base.index if abs(new[key] - base[key]) > 0}
    listed = {
        (c["scenario_id"], c["variable"]): float(c["regenerated"])
        for c in revision["changed"]
    }
    require(
        set(diff) == set(listed)
        and all(abs(diff[key] - listed[key]) < 1e-9 for key in diff),
        "reference changes differ from the engine_upgrade revision's list",
    )
    return revision


def replay_base_references(args, bundle, previous) -> None:
    """Export again on the September 22c references; incumbents must not move.

    With the references as the only input put back, every incumbent's
    modelStats must reproduce the live payload exactly, so any drift in the
    real export comes from the reviewed reference revision alone.
    """
    from policybench.full_run_export import export_full_run

    replay = args.stage_dir / "replay-20260922c" / bundle.name
    if replay.parent.exists():
        shutil.rmtree(replay.parent)
    shutil.copytree(bundle, replay)
    for name in BASE_REFERENCE_SHA256:
        (replay / "us" / name).write_bytes(base_reference_bytes(name))
    stats = export_full_run(replay, countries=["us"], skip_app_data=True)["countries"][
        "us"
    ]["modelStats"]
    fable = next(s for s in stats if s["model"] == "claude-fable-5")
    for key in ("costUsd", "costPerHousehold", "totalTokens", "latencySeconds"):
        fable[key] = previous["claude-fable-5"][key]
    drift = [
        s["model"]
        for s in stats
        if s["model"] in previous and s != previous[s["model"]]
    ]
    require(not drift, f"incumbents drift even on the 22c references: {drift}")


def export(args, bundle, live) -> dict:
    """Export into scratch, preserve incumbent statistics, and gate release."""
    from policybench.dashboard_schema import validate_dashboard_payload
    from policybench.full_run_export import export_full_run

    payload = export_full_run(bundle, countries=["us"], skip_app_data=True)
    stats = payload["countries"]["us"]["modelStats"]
    require(len(stats) == 45, "export did not contain all 45 models")
    previous = {m["model"]: m for m in live["countries"]["us"]["modelStats"]}
    if not args.partial:
        fable = next(s for s in stats if s["model"] == "claude-fable-5")
        for key in ("costUsd", "costPerHousehold", "totalTokens", "latencySeconds"):
            fable[key] = previous["claude-fable-5"][key]
        changed = [
            s["model"]
            for s in stats
            if s["model"] in previous and s != previous[s["model"]]
        ]
        revision = reference_revision()
        if revision is None:
            require(not changed, f"incumbent modelStats drift: {changed}")
        else:
            replay_base_references(args, bundle, previous)
            report = [
                {
                    "model": s["model"],
                    "exact_20260922c": previous[s["model"]]["exact"],
                    "exact": s["exact"],
                    "score_20260922c": previous[s["model"]]["score"],
                    "score": s["score"],
                }
                for s in stats
                if s["model"] in previous
            ]
            write_json(
                args.stage_dir / "incumbent-drift.json",
                {
                    "reference_revision": revision["root_cause"],
                    "reference_changes": len(revision["changed"]),
                    "models": report,
                },
            )
    errors = validate_dashboard_payload(
        payload, require_failure_annotations=not args.early
    )
    require(not errors, f"payload validation failed: {errors[:8]}")
    if args.partial:
        payload["stage2Status"] = (
            "PARTIAL — incomplete household cohorts, not a release"
        )
    path = args.stage_dir / (
        "PARTIAL-data-board45.json" if args.partial else "data-board45.json"
    )
    # freeze_snapshot reassembles these exact default-json bytes from the
    # compact country payload. Pretty-printing here breaks its release hash.
    path.write_text(json.dumps(payload, allow_nan=False))
    # Keep the freeze input identical to the gated payload, including Fable usage.
    shutil.copyfile(path, bundle / "data.json")
    ranked = sorted(stats, key=lambda s: (-s["exact"], -s["score"], s["model"]))
    for index, row in enumerate(ranked, 1):
        if row["model"] in MODELS.values():
            print(
                f"{'PARTIAL common cohort' if args.partial else 'STAGED'} "
                f"{row['model']}: exact={row['exact']:.6f}% "
                f"rank={index}/45 n={row['n']}"
            )
    if not args.early:
        pinned = [p for p in (bundle / "annotations").iterdir() if p.is_file()]
        pinned += [
            bundle / "us" / name for name in (*REFERENCE_FILES, "predictions.csv")
        ]
        pinned += [p for p in (args.stage_dir / "inputs").rglob("*") if p.is_file()]
        pinned += [
            p
            for p in (args.stage_dir / "audit").rglob("*")
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
        write_json(
            args.stage_dir / "release-ready.json",
            {
                "release_tag": RELEASE_TAG,
                "payload_sha256": digest(path),
                "models": 45,
                "partial": False,
                "files": {
                    str(p.relative_to(args.stage_dir)): digest(p) for p in pinned
                },
            },
        )
    return payload


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument("--stage-dir", type=Path, required=True)
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
        "--step", choices=("prepare", "judge", "triage", "export"), default="prepare"
    )
    args = parser.parse_args(argv)
    if args.partial and not args.early:
        parser.error("--partial requires --early")
    if args.early and args.step != "prepare":
        parser.error("--early only applies to prepare")
    if args.step == "prepare" and not args.runs_root:
        parser.error("prepare requires --runs-root")
    args.stage_dir = args.stage_dir.resolve()
    return args


def main(argv=None) -> None:
    args = parse_args(argv)
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
        print("All copied run states qualify; resolving September 22c base", flush=True)
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
        if args.early:
            export(args, bundle, live)
        else:
            prepare_cases(args, bundle)
        inputs = [p for p in (stage / "inputs").rglob("*") if p.is_file()]
        inputs += [
            bundle / "us" / name for name in (*REFERENCE_FILES, "predictions.csv")
        ]
        write_json(
            receipt_path,
            {
                "partial": args.partial,
                "early": args.early,
                "base_tag": BASE_TAG,
                "files": {str(p.relative_to(stage)): digest(p) for p in inputs},
            },
        )
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
        if args.step == "judge":
            judge(args, bundle)
        elif args.step == "triage":
            triage(args, bundle)
        else:
            triage(args, bundle)
            export(args, bundle, resolve_live_base(args))


if __name__ == "__main__":
    main()
