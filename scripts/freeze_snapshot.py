"""Refreeze the manuscript snapshot from a completed full run.

This rebuilds ``paper/snapshot/<SNAPSHOT_DIR_NAME>/`` and its ``manifest.json``
from a finished run under ``results/``. It is deterministic and idempotent:
re-running it on the same source run produces byte-identical frozen artifacts
and the same manifest hashes.

The June 2026 refresh is US-only (populace dataset, policyengine.py 4.16.1).
There is no UK leg in this refresh, so all UK artifacts are removed.

What it freezes (all paths relative to the repo root):

* ``paper/snapshot/<dir>/runs/<label>/`` — compact copies of the run:
  ``data.json`` (copied byte-for-byte so the published-dashboard hash is
  preserved), ``predictions.csv.gz`` (deterministic gzip of the run's
  ``predictions.csv``), ``scenarios.csv`` (+ ``.meta.json``),
  ``reference_outputs.csv`` (+ ``.meta.json``), and ``analysis/`` CSVs
  (``metrics``, ``summary_by_model``, ``summary_by_variable``,
  ``usage_summary``, ``report.md``, and the legacy
  ``impact_summary_by_model.csv``).
* ``paper/snapshot/<dir>/us_*.csv`` — committed snapshot artifacts.
* ``annotations/<run>/`` — frozen developer audit annotations the snapshot
  tests read: ``us_audit_row_annotations.csv`` (row-level) and
  ``us_case_notes.csv`` (case-level, renamed to the column contract the
  validator expects).
* ``paper/snapshot/<dir>/manifest.json`` — the full manifest.

Run from the repo root::

    .venv/bin/python scripts/freeze_snapshot.py
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from policybench.analysis import score_single_prediction
from policybench.spec import net_income_sign_for_output

# ---------------------------------------------------------------------------
# Configuration for the July 2026 US-only populace refresh (26-model board,
# corrected v1.1 references).
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]

SNAPSHOT_DIR_NAME = "20260501"  # Stable id; reused across refreshes.
SNAPSHOT_DATE = "2026-07-21"
MODEL_RESPONSE_DATE = "2026-06-12 to 2026-07-21"

RUN_LABEL = "us_full_run_20260612_policyengine_4_16_1_populace"
SOURCE_RUN = ROOT / "results" / RUN_LABEL / "us"

SNAPSHOT_DIR = ROOT / "paper" / "snapshot" / SNAPSHOT_DIR_NAME
RUN_DEST = SNAPSHOT_DIR / "runs" / RUN_LABEL
ANNOTATIONS_DEST = ROOT / "annotations" / RUN_LABEL

# Legacy household-equal impact metric (removed from the package in #58 but
# still frozen for parity with prior snapshots).
HOUSEHOLD_IMPACT_SCORE_FLOOR = 0.3

ANALYSIS_CSVS = (
    "metrics.csv",
    "summary_by_model.csv",
    "summary_by_variable.csv",
    "usage_summary.csv",
    "impact_summary_by_model.csv",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def copy_exact(src: Path, dst: Path) -> None:
    """Copy a file byte-for-byte without re-serializing."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def gzip_deterministic(src: Path, dst: Path, *, stored_name: str) -> None:
    """Gzip ``src`` to ``dst`` reproducibly (mtime=0, max compression).

    Mirrors the format of the prior frozen ``predictions.csv.gz`` (the original
    filename is embedded and the mtime is zeroed) so repeated freezes hash the
    same.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    raw = src.read_bytes()
    with open(dst, "wb") as fileobj:
        gz = gzip.GzipFile(
            filename=stored_name,
            mode="wb",
            fileobj=fileobj,
            mtime=0,
            compresslevel=9,
        )
        try:
            gz.write(raw)
        finally:
            gz.close()


def household_impact_summary_by_model(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
    floor_share: float = HOUSEHOLD_IMPACT_SCORE_FLOOR,
) -> pd.DataFrame:
    """Reconstruct the legacy ``impact_summary_by_model.csv`` metric.

    This is the exact computation removed from ``policybench.analysis`` in #58,
    re-expressed against the still-present public helpers
    ``score_single_prediction`` and ``net_income_sign_for_output``. Each
    household contributes equally; within a household every requested output row
    gets a blended ``floor_share / K`` equal floor plus ``(1 - floor_share)``
    times its absolute reference-value share.
    """
    if floor_share < 0 or floor_share > 1:
        raise ValueError("floor_share must be between 0 and 1.")

    models = pd.DataFrame({"model": sorted(predictions["model"].dropna().unique())})
    expected = ground_truth.assign(_join_key=1).merge(
        models.assign(_join_key=1),
        on="_join_key",
    )
    expected = expected.drop(columns="_join_key")
    merged = expected.merge(
        predictions[["model", "scenario_id", "variable", "prediction"]],
        on=["model", "scenario_id", "variable"],
        how="left",
    )

    base_weights = ground_truth.copy()
    base_weights["net_income_sign"] = base_weights["variable"].map(
        net_income_sign_for_output
    )
    default_abs_value = (base_weights["value"] * base_weights["net_income_sign"]).abs()
    if "impact_weight" in base_weights.columns:
        explicit_weight = pd.to_numeric(
            base_weights["impact_weight"],
            errors="coerce",
        ).abs()
        base_weights["abs_value"] = explicit_weight.fillna(default_abs_value)
    else:
        base_weights["abs_value"] = default_abs_value
    base_weights["total_variables"] = base_weights.groupby("scenario_id")[
        "variable"
    ].transform("size")
    base_weights["abs_total"] = base_weights.groupby("scenario_id")[
        "abs_value"
    ].transform("sum")
    base_weights["weight"] = np.where(
        base_weights["abs_total"] > 0,
        floor_share / base_weights["total_variables"]
        + (1 - floor_share) * base_weights["abs_value"] / base_weights["abs_total"],
        1 / base_weights["total_variables"],
    )

    merged = merged.merge(
        base_weights[["scenario_id", "variable", "weight", "total_variables"]],
        on=["scenario_id", "variable"],
        how="left",
    )
    merged["row_score"] = [
        score_single_prediction(variable, y_true, y_pred)
        for variable, y_true, y_pred in zip(
            merged["variable"],
            merged["value"],
            merged["prediction"],
        )
    ]
    merged["weighted_row_score"] = merged["row_score"] * merged["weight"]

    household_scores = (
        merged.groupby(["model", "scenario_id"])
        .agg(
            impact_score=("weighted_row_score", "sum"),
            equal_weight_score=("row_score", "mean"),
            parsed_variables=("prediction", lambda s: int(s.notna().sum())),
            total_variables=("total_variables", "first"),
        )
        .reset_index()
    )
    household_scores["coverage"] = (
        household_scores["parsed_variables"] / household_scores["total_variables"]
    )
    household_scores["floor_share"] = floor_share

    return (
        household_scores.groupby("model")
        .agg(
            mean_impact_score=("impact_score", "mean"),
            mean_household_score=("equal_weight_score", "mean"),
            mean_household_coverage=("coverage", "mean"),
            households=("scenario_id", "nunique"),
            total_variables=("total_variables", "sum"),
            parsed_variables=("parsed_variables", "sum"),
            floor_share=("floor_share", "first"),
        )
        .reset_index()
        .sort_values("mean_impact_score", ascending=False)
    )


def regenerate_analysis(dest_dir: Path) -> None:
    """Run the analyze CLI into ``dest_dir`` and add the impact summary.

    The analyze CLI is deterministic and reproduces the run's standard analysis
    CSVs exactly. ``impact_summary_by_model.csv`` is no longer produced by the
    package, so it is computed here. ``data.json`` is written separately
    (byte-exact copy) to preserve the published-dashboard hash, so the CLI's
    dashboard export is routed to a throwaway path.
    """
    import subprocess
    import sys

    dest_dir.mkdir(parents=True, exist_ok=True)
    throwaway = dest_dir / "_analyze_dashboard.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "policybench.cli",
            "analyze",
            "-g",
            str(SOURCE_RUN / "reference_outputs.csv"),
            "-p",
            str(SOURCE_RUN / "predictions.csv"),
            "-s",
            str(SOURCE_RUN / "scenarios.csv"),
            "-o",
            str(dest_dir),
            "--app-data-output",
            str(throwaway),
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    throwaway.unlink(missing_ok=True)

    ground_truth = pd.read_csv(SOURCE_RUN / "reference_outputs.csv")
    predictions = pd.read_csv(SOURCE_RUN / "predictions.csv")
    impact = household_impact_summary_by_model(ground_truth, predictions)
    impact.to_csv(dest_dir / "impact_summary_by_model.csv", index=False)


def freeze_run() -> dict[str, str]:
    """Freeze the compact run artifacts and return their file->sha256 map."""
    if RUN_DEST.exists():
        shutil.rmtree(RUN_DEST)
    RUN_DEST.mkdir(parents=True, exist_ok=True)

    # data.json: copy byte-for-byte (do not re-serialize).
    copy_exact(SOURCE_RUN / "data.json", RUN_DEST / "data.json")

    # predictions.csv -> deterministic gzip.
    gzip_deterministic(
        SOURCE_RUN / "predictions.csv",
        RUN_DEST / "predictions.csv.gz",
        stored_name="predictions.csv",
    )

    # scenarios + reference outputs (+ meta).
    for name in (
        "scenarios.csv",
        "scenarios.csv.meta.json",
        "reference_outputs.csv",
        "reference_outputs.csv.meta.json",
    ):
        copy_exact(SOURCE_RUN / name, RUN_DEST / name)

    # analysis/ CSVs + report.md.
    analysis_dest = RUN_DEST / "analysis"
    regenerate_analysis(analysis_dest)

    files: dict[str, str] = {}
    for name in ANALYSIS_CSVS:
        files[f"analysis/{name}"] = sha256_file(analysis_dest / name)
    files["analysis/report.md"] = sha256_file(analysis_dest / "report.md")
    for name in (
        "data.json",
        "predictions.csv.gz",
        "reference_outputs.csv",
        "reference_outputs.csv.meta.json",
        "scenarios.csv",
        "scenarios.csv.meta.json",
    ):
        files[name] = sha256_file(RUN_DEST / name)

    return dict(sorted(files.items()))


def freeze_committed_artifacts() -> dict[str, str]:
    """Copy the US committed snapshot artifacts and return their hashes."""
    mapping = {
        "us_scenarios.csv": RUN_DEST / "scenarios.csv",
        "us_reference_outputs.csv": RUN_DEST / "reference_outputs.csv",
        "us_impact_summary_by_model.csv": RUN_DEST
        / "analysis"
        / "impact_summary_by_model.csv",
    }
    committed: dict[str, str] = {}
    for committed_name, src in mapping.items():
        copy_exact(src, SNAPSHOT_DIR / committed_name)
        committed[committed_name] = sha256_file(SNAPSHOT_DIR / committed_name)
    return committed


def freeze_annotations() -> dict[str, str]:
    """Freeze audit annotations under the path the snapshot tests read.

    Row annotations keep their ``us_audit_row_annotations.csv`` name (matches
    the ``us_*_annotations.csv`` glob the validator uses). Case annotations are
    written as ``us_case_notes.csv`` with the ``case_failure_sources`` /
    ``case_failure_subtypes`` column names the validator's case contract
    expects.
    """
    if ANNOTATIONS_DEST.exists():
        shutil.rmtree(ANNOTATIONS_DEST)
    ANNOTATIONS_DEST.mkdir(parents=True, exist_ok=True)

    audit = SOURCE_RUN / "audit"
    copy_exact(
        audit / "us_audit_row_annotations.csv",
        ANNOTATIONS_DEST / "us_audit_row_annotations.csv",
    )

    case = pd.read_csv(audit / "us_audit_case_annotations.csv")
    case = case.rename(
        columns={
            "case_failure_source": "case_failure_sources",
            "case_failure_subtype": "case_failure_subtypes",
        }
    )
    case.to_csv(ANNOTATIONS_DEST / "us_case_notes.csv", index=False)

    # Trace-grounded reference narratives (added after the June freeze) are
    # part of the frozen audit story: the judge reads them and the dashboard
    # displays them, so they freeze alongside the annotations.
    copy_exact(
        SOURCE_RUN / "audit" / "us_case_reference_explanations.csv",
        ANNOTATIONS_DEST / "us_case_reference_explanations.csv",
    )

    return {
        "us_audit_row_annotations.csv": sha256_file(
            ANNOTATIONS_DEST / "us_audit_row_annotations.csv"
        ),
        "us_case_notes.csv": sha256_file(ANNOTATIONS_DEST / "us_case_notes.csv"),
        "us_case_reference_explanations.csv": sha256_file(
            ANNOTATIONS_DEST / "us_case_reference_explanations.csv"
        ),
    }


def remove_stale_artifacts() -> None:
    """Remove the prior May (US+UK) run dirs and UK committed artifacts."""
    runs_dir = SNAPSHOT_DIR / "runs"
    if runs_dir.exists():
        for child in runs_dir.iterdir():
            if child.is_dir() and child.name != RUN_LABEL:
                shutil.rmtree(child)
    for stale in (
        "uk_scenarios.csv",
        "uk_reference_outputs.csv",
        "uk_impact_summary_by_model.csv",
        "us_scenarios.csv",
        "us_reference_outputs.csv",
        "us_impact_summary_by_model.csv",
    ):
        (SNAPSHOT_DIR / stale).unlink(missing_ok=True)


def read_reference_refresh() -> dict[str, str]:
    """Read the real PE bundle versions from the run's reference meta."""
    meta = json.loads((SOURCE_RUN / "reference_outputs.csv.meta.json").read_text())
    bundle = meta["policyengine_bundles"]["us"]
    return {
        "date": SNAPSHOT_DATE,
        "policyengine_version": bundle["policyengine_version"],
        "policyengine_us_version": bundle["model_version"],
        "policyengine_us_data_build_id": bundle["certified_data_build_id"],
        "policyengine_us_dataset": bundle["default_dataset"],
        "policyengine_us_dataset_uri": bundle["default_dataset_uri"],
        "policyengine_us_data_artifact_sha256": bundle[
            "certified_data_artifact_sha256"
        ],
    }


def prompt_payload_sha256() -> str:
    """Hash the snapshot prompts exactly as the snapshot test recomputes them."""
    data = json.loads((RUN_DEST / "data.json").read_text())
    prompts = {
        scenario_id: scenario.get("prompt")
        for scenario_id, scenario in sorted(data["scenarios"].items())
    }
    payload = json.dumps(prompts, separators=(",", ":"), sort_keys=True).encode()
    return sha256_bytes(payload)


def build_manifest(
    run_files: dict[str, str],
    committed: dict[str, str],
    annotation_files: dict[str, str],
) -> dict:
    reference_refresh = read_reference_refresh()
    data_json_sha = run_files["data.json"]

    population_weight_path = ROOT / "policybench" / "population_weights.json"
    pointer = json.loads((ROOT / "app" / "src" / "data.artifact.json").read_text())

    return {
        "snapshot_date": SNAPSHOT_DATE,
        "policy_period": {"us": "tax year 2026"},
        "live_dashboard_note": (
            "The live dashboard payload is a published release asset; the "
            "committed pointer app/src/data.artifact.json must reference the "
            "artifact pinned under published_dashboard_artifact, which equals "
            "the combined export of the source run data.json files listed under "
            "source_run_artifacts. Future refreshes publish a new artifact "
            "(policybench publish-dashboard) and either update this manifest or "
            "use a new snapshot directory."
        ),
        "source_run_labels": {"us": RUN_LABEL},
        "source_run_artifacts": {
            "note": (
                "Compact copies of run outputs used to verify this snapshot. "
                "The run data.json retains parsed scenario predictions, "
                "explanations, summaries, heatmaps, and PolicyEngine runtime "
                "metadata used by the dashboard. predictions.csv.gz is a "
                "deterministic gzip of the run's raw provider responses."
            ),
            RUN_LABEL: {
                "path": f"paper/snapshot/{SNAPSHOT_DIR_NAME}/runs/{RUN_LABEL}",
                "prompt_payload_sha256": prompt_payload_sha256(),
                "files": run_files,
            },
        },
        "committed_snapshot_artifacts": committed,
        "rendered_paper_artifacts": _existing_rendered_paper_artifacts(),
        "reproducibility_notes": [
            "The top-level scenario, reference-output, and impact-summary CSVs "
            "are byte-identical to the corresponding compact source-run "
            "artifacts copied under "
            f"paper/snapshot/{SNAPSHOT_DIR_NAME}/runs/.",
            "Model responses were collected in waves between June 12 and "
            "July 10, 2026, as models were added to the board; each model's "
            "full 100-household run is a single consistent wave. Reference "
            "outputs were generated with policyengine.py "
            f"{reference_refresh['policyengine_version']} and policyengine-us "
            f"{reference_refresh['policyengine_us_version']} against the "
            "certified PolicyEngine US populace dataset "
            f"({reference_refresh['policyengine_us_data_build_id']}, "
            f"{reference_refresh['policyengine_us_dataset']}).",
            "Canonical prediction files include parser recovery. Later "
            "waves ran under the resumable supervised runner, which retries "
            "failed or timed-out scenarios in bounded rounds; every model's "
            "canonical file covers all 100 households.",
            "Raw provider responses are retained in the compressed source-run "
            "predictions.csv.gz file. The separate LiteLLM cache remains "
            "local-only because it is a generated request cache, not the "
            "canonical snapshot artifact.",
            "The frozen scenarios.csv source_dataset column carries a stale "
            "enhanced_cps_2024 label from the pre-#77 scenario generator; the "
            "run metadata (scenarios.csv.meta.json) records the "
            "populace_us_2024 build actually loaded.",
            "Model APIs and upstream model aliases may change after the "
            "recorded 2026-06-12 to 2026-07-21 response window, so exact "
            "reruns can diverge even with the committed household inputs, "
            "reference outputs, parsed dashboard export, and analysis "
            "summaries.",
        ],
        "scope": {
            "households": {"us": 100},
            "output_groups": {"us": 18},
            "models": 26,
            "condition": (
                "No tools, no web access, one structured response per household "
                "with numeric answers and non-empty explanations."
            ),
        },
        "model_response_date": MODEL_RESPONSE_DATE,
        "reference_output_refresh": reference_refresh,
        "files": [
            {
                "path": f"runs/{RUN_LABEL}/data.json",
                "sha256": data_json_sha,
            }
        ],
        "response_retry_artifacts": {
            "path": f"paper/snapshot/{SNAPSHOT_DIR_NAME}/response_retries",
            "note": (
                "No separate whole-response retry artifacts exist for this "
                "snapshot; the supervised runner's bounded per-scenario retry "
                "rounds are folded into each model's canonical predictions."
            ),
            "files": {},
        },
        "row_repair_artifacts": {
            "path": f"paper/snapshot/{SNAPSHOT_DIR_NAME}/row_repairs",
            "note": (
                "No bulk row-repair artifacts exist for this snapshot; "
                "row-level repairs are folded into each model's canonical "
                "predictions."
            ),
            "files": {},
        },
        "audit_annotation_artifacts": {
            "path": f"annotations/{RUN_LABEL}",
            "note": (
                "Model-assisted, developer-adjudicated row and case audit "
                "annotations for every wrong prediction row in the frozen "
                "snapshot, produced under the decisive-diagnosis contract "
                "(per-model diagnoses grounded in engine facts; hedged "
                "verdicts mechanically rejected and re-judged). Row-level "
                "failure_source values are llm_error for substantive misses "
                "and parse_contract_failure for missing or unparseable "
                "answers; zero rows are reference-suspect. Case notes are "
                "stored as us_case_notes.csv with case_failure_sources / "
                "case_failure_subtypes columns. Reference narratives the "
                "judge and dashboard display are frozen as "
                "us_case_reference_explanations.csv."
            ),
            "files": annotation_files,
        },
        "population_weight_artifact": {
            "path": "policybench/population_weights.json",
            "sha256": sha256_file(population_weight_path),
            "note": (
                "Output weights for the household and aggregate scoring views. "
                "US weights use the certified PolicyEngine US populace dataset "
                "with formula-owned benchmark output inputs cleared before "
                "calculation. These weights are fixed for scoring the "
                "100-household snapshot."
            ),
        },
        "published_dashboard_artifact": {
            "tag": pointer["tag"],
            "asset": pointer["asset"],
            "url": pointer["url"],
            "sha256": pointer["sha256"],
            "bytes": pointer["bytes"],
        },
        "live_dashboard_artifact": {
            "tag": pointer["tag"],
            "asset": pointer["asset"],
            "url": pointer["url"],
            "sha256": pointer["sha256"],
            "bytes": pointer["bytes"],
            "derivation": (
                "At freeze time the live artifact equals the frozen "
                "published_dashboard_artifact: the combined export of the "
                "source-run data.json listed under source_run_artifacts. "
                "Annotation-class republishes may advance this entry ahead "
                "of the frozen pin without changing any score."
            ),
        },
    }


# Served paper artifacts the manifest pins under ``rendered_paper_artifacts``.
PUBLIC_PAPER_DIR = ROOT / "app" / "public" / "paper"
PUBLIC_PAPER_PDF = PUBLIC_PAPER_DIR / "policybench.pdf"
PUBLIC_PAPER_WEB_DIR = PUBLIC_PAPER_DIR / "web"


def rendered_paper_artifacts() -> dict:
    """Compute the ``rendered_paper_artifacts`` block from the served files.

    Reads the published manuscript under ``app/public/paper/`` (the PDF and every
    file in the ``web/`` bundle) and returns the block with fresh sha256 hashes.
    Deterministic and idempotent: re-running on the same rendered output yields
    the same block. The web ``files`` map is keyed by each file's path relative
    to ``web/`` with POSIX separators, matching the committed manifest contract
    that ``tests/test_snapshot_artifacts.py`` verifies.
    """
    if not PUBLIC_PAPER_PDF.exists():
        raise SystemExit(
            f"Rendered PDF not found: {PUBLIC_PAPER_PDF.relative_to(ROOT)}. "
            "Render the paper before re-pinning rendered hashes."
        )
    if not PUBLIC_PAPER_WEB_DIR.exists():
        raise SystemExit(
            f"Rendered web bundle not found: {PUBLIC_PAPER_WEB_DIR.relative_to(ROOT)}."
        )

    web_files = {
        path.relative_to(PUBLIC_PAPER_WEB_DIR).as_posix(): sha256_file(path)
        for path in PUBLIC_PAPER_WEB_DIR.rglob("*")
        if path.is_file()
    }
    return {
        "pdf": {
            "path": str(PUBLIC_PAPER_PDF.relative_to(ROOT).as_posix()),
            "sha256": sha256_file(PUBLIC_PAPER_PDF),
        },
        "web": {
            "path": str(PUBLIC_PAPER_WEB_DIR.relative_to(ROOT).as_posix()),
            "files": dict(sorted(web_files.items())),
        },
    }


def _existing_rendered_paper_artifacts() -> dict:
    """Return the rendered-paper block currently recorded in the manifest."""
    current = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    return current["rendered_paper_artifacts"]


def repin_rendered_paper_artifacts() -> dict:
    """Rewrite ONLY the ``rendered_paper_artifacts`` block from served files.

    Loads the committed manifest, replaces that single block with freshly
    computed hashes from ``app/public/paper/``, and writes it back using the same
    serialization the full freeze uses (``indent=2``, ``sort_keys=True``,
    trailing newline). Every other manifest block is preserved byte-for-byte, so
    the finalized snapshot blocks and their passing tests are untouched.
    """
    manifest_path = SNAPSHOT_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    block = rendered_paper_artifacts()
    manifest["rendered_paper_artifacts"] = block
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return block


def main() -> None:
    if not SOURCE_RUN.exists():
        raise SystemExit(f"Source run not found: {SOURCE_RUN}")

    remove_stale_artifacts()
    run_files = freeze_run()
    committed = freeze_committed_artifacts()
    annotation_files = freeze_annotations()

    manifest = build_manifest(run_files, committed, annotation_files)
    # Pin the rendered-paper block to the served files. Falls back to the block
    # already recorded in the manifest when the paper has not been rendered yet.
    try:
        manifest["rendered_paper_artifacts"] = rendered_paper_artifacts()
    except SystemExit:
        manifest["rendered_paper_artifacts"] = _existing_rendered_paper_artifacts()

    (SNAPSHOT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )

    print(f"Froze snapshot run: {RUN_LABEL}")
    print(f"  run dir:      {RUN_DEST.relative_to(ROOT)}")
    print(f"  annotations:  {ANNOTATIONS_DEST.relative_to(ROOT)}")
    print(f"  committed:    {', '.join(sorted(committed))}")
    print(f"  manifest:     {(SNAPSHOT_DIR / 'manifest.json').relative_to(ROOT)}")


if __name__ == "__main__":
    import sys

    # ``--rendered-only`` re-pins just the rendered-paper hashes from
    # app/public/paper/ without re-freezing the run data (which needs results/
    # and would rewrite the finalized snapshot blocks). The full freeze remains
    # the default.
    if "--rendered-only" in sys.argv[1:]:
        block = repin_rendered_paper_artifacts()
        n_web = len(block["web"]["files"])
        print("Re-pinned rendered_paper_artifacts from app/public/paper")
        print(f"  pdf sha256:   {block['pdf']['sha256']}")
        print(f"  web files:    {n_web}")
        print(f"  manifest:     {(SNAPSHOT_DIR / 'manifest.json').relative_to(ROOT)}")
    else:
        main()
