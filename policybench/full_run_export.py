"""Export full-run analysis and frontend payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from policybench.analysis import (
    analyze_no_tools,
    build_dashboard_payload,
    build_scenario_prompt_map,
    export_analysis,
)
from policybench.annotation_taxonomy import (
    validate_failure_source,
    validate_failure_subtype,
)
from policybench.dashboard_schema import (
    dump_country_payload,
    dump_dashboard_payload,
)
from policybench.spec import get_output_ids, output_group_id


class ReferenceProvenanceError(ValueError):
    """Reference-output provenance is unavailable for a dashboard export."""


_REQUIRED_REFERENCE_BUNDLE_FIELDS = (
    "model_package",
    "model_version",
    "data_package",
    "data_version",
    "default_dataset",
    "default_dataset_uri",
)


def _canonical_output_ids(country: str) -> set[str]:
    return set(get_output_ids(country, "headline"))


def _filter_to_canonical_outputs(frame: pd.DataFrame, country: str) -> pd.DataFrame:
    """Drop source-run rows outside the canonical headline output scope."""
    if frame.empty or "variable" not in frame.columns:
        return frame
    canonical = _canonical_output_ids(country)
    return frame[frame["variable"].map(output_group_id).isin(canonical)].reset_index(
        drop=True
    )


def load_predictions(country_dir: Path) -> pd.DataFrame:
    """Load a country run's predictions, preferring per-model CSVs when present."""
    by_model_dir = country_dir / "by_model"
    files = sorted(by_model_dir.glob("*.csv")) if by_model_dir.exists() else []
    predictions_path = country_dir / "predictions.csv"
    compressed_predictions_path = country_dir / "predictions.csv.gz"
    if files:
        predictions = pd.concat(
            (pd.read_csv(path, low_memory=False) for path in files),
            ignore_index=True,
        )
        predictions.to_csv(predictions_path, index=False)
        return predictions
    if predictions_path.exists():
        return pd.read_csv(predictions_path, low_memory=False)
    if compressed_predictions_path.exists():
        return pd.read_csv(compressed_predictions_path, low_memory=False)
    raise FileNotFoundError(
        f"Expected at least one CSV in {by_model_dir}, {predictions_path}, "
        f"or {compressed_predictions_path}."
    )


def load_annotations(country_dir: Path) -> pd.DataFrame:
    """Load optional prediction annotations for a country run."""
    country = country_dir.name
    annotations_dir = country_dir.parent / "annotations"
    committed_annotations_dir = Path("annotations") / country_dir.parent.name
    files = sorted(annotations_dir.glob(f"{country}_*_annotations.csv"))
    if not files:
        files = sorted(committed_annotations_dir.glob(f"{country}_*_annotations.csv"))
    annotation_columns = [
        "model",
        "scenario_id",
        "variable",
        "annotation",
        "failure_source",
        "failure_subtype",
    ]
    if not files:
        return pd.DataFrame(columns=annotation_columns)

    annotations = pd.concat((pd.read_csv(path) for path in files), ignore_index=True)
    required = set(annotation_columns)
    missing = required - set(annotations.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Annotation files missing columns: {missing_text}")

    annotations = annotations[annotation_columns].copy()
    annotations = annotations[
        annotations["annotation"].astype("string").fillna("").str.strip() != ""
    ]
    annotations["failure_source"] = annotations["failure_source"].map(
        validate_failure_source
    )
    annotations["failure_subtype"] = annotations["failure_subtype"].map(
        validate_failure_subtype
    )
    duplicate_keys = annotations.duplicated(
        ["model", "scenario_id", "variable"],
        keep=False,
    )
    if duplicate_keys.any():
        duplicates = annotations.loc[
            duplicate_keys, ["model", "scenario_id", "variable"]
        ].drop_duplicates()
        raise ValueError(
            "Duplicate annotations for prediction rows: "
            f"{duplicates.to_dict(orient='records')[:5]}"
        )
    return annotations


def load_case_annotations(country_dir: Path) -> pd.DataFrame:
    """Load optional grouped annotations for country scenario-output cases."""
    country = country_dir.name
    annotations_dir = country_dir.parent / "annotations"
    committed_annotations_dir = Path("annotations") / country_dir.parent.name
    files = sorted(annotations_dir.glob(f"{country}_case_notes.csv"))
    if not files:
        files = sorted(committed_annotations_dir.glob(f"{country}_case_notes.csv"))
    case_annotation_columns = [
        "scenario_id",
        "variable",
        "case_annotation",
        "case_failure_sources",
        "case_failure_subtypes",
    ]
    if not files:
        return pd.DataFrame(columns=case_annotation_columns)

    case_annotations = pd.concat(
        (pd.read_csv(path) for path in files),
        ignore_index=True,
    )
    required = set(case_annotation_columns)
    missing = required - set(case_annotations.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Case annotation files missing columns: {missing_text}")

    case_annotations = case_annotations[case_annotation_columns].copy()
    case_annotations = case_annotations[
        case_annotations["case_annotation"].astype("string").fillna("").str.strip()
        != ""
    ]
    duplicate_keys = case_annotations.duplicated(
        ["scenario_id", "variable"],
        keep=False,
    )
    if duplicate_keys.any():
        duplicates = case_annotations.loc[
            duplicate_keys, ["scenario_id", "variable"]
        ].drop_duplicates()
        raise ValueError(
            "Duplicate case annotations for scenario-output rows: "
            f"{duplicates.to_dict(orient='records')[:5]}"
        )
    return case_annotations


def load_case_reference_explanations(country_dir: Path) -> pd.DataFrame:
    """Load optional written 'reference computation' narratives for each case.

    These are agent-generated narratives describing how PolicyEngine derived
    the truth value for each ``(scenario_id, variable)`` case. The same text
    applies to every model on that case — it's about the reference, not the
    prediction.
    """
    country = country_dir.name
    annotations_dir = country_dir.parent / "annotations"
    committed_annotations_dir = Path("annotations") / country_dir.parent.name
    filename = f"{country}_case_reference_explanations.csv"
    files = sorted(annotations_dir.glob(filename))
    if not files:
        files = sorted(committed_annotations_dir.glob(filename))
    columns = ["scenario_id", "variable", "reference_explanation"]
    if not files:
        return pd.DataFrame(columns=columns)

    raw = pd.concat([pd.read_csv(path) for path in files], ignore_index=True)
    if "explanation" not in raw.columns:
        return pd.DataFrame(columns=columns)
    explanations = raw[["scenario_id", "variable", "explanation"]].rename(
        columns={"explanation": "reference_explanation"}
    )
    explanations = explanations[
        explanations["reference_explanation"].astype("string").fillna("").str.strip()
        != ""
    ]
    return explanations.drop_duplicates(["scenario_id", "variable"], keep="first")


def merge_case_reference_explanations(
    predictions: pd.DataFrame,
    explanations: pd.DataFrame,
) -> pd.DataFrame:
    """Attach the per-case reference-computation narrative to prediction rows."""
    if explanations.empty:
        return predictions
    if "reference_explanation" in predictions.columns:
        predictions = predictions.drop(columns=["reference_explanation"])
    return predictions.merge(explanations, on=["scenario_id", "variable"], how="left")


def merge_annotations(
    predictions: pd.DataFrame,
    annotations: pd.DataFrame,
) -> pd.DataFrame:
    """Attach optional audit annotations to prediction rows."""
    if annotations.empty:
        return predictions
    existing_columns = [
        column
        for column in ["annotation", "failure_source", "failure_subtype"]
        if column in predictions.columns
    ]
    recorded_columns = {column: f"_recorded_{column}" for column in existing_columns}
    if recorded_columns:
        predictions = predictions.rename(columns=recorded_columns)
    merged = predictions.merge(
        annotations,
        on=["model", "scenario_id", "variable"],
        how="left",
    )
    recorded_ceiling_exhaustion = pd.Series(False, index=merged.index)
    for column, recorded_column in recorded_columns.items():
        if column not in merged.columns:
            merged[column] = merged[recorded_column]
        else:
            merged[column] = merged[column].combine_first(merged[recorded_column])
        if column == "failure_source":
            recorded_ceiling_exhaustion = (
                merged[recorded_column].astype("string")
                == "budget_exhausted_at_ceiling"
            ).fillna(False)
            merged.loc[recorded_ceiling_exhaustion, column] = (
                "budget_exhausted_at_ceiling"
            )
        merged = merged.drop(columns=recorded_column)
    invented_ceiling_exhaustion = (
        merged["failure_source"].astype("string") == "budget_exhausted_at_ceiling"
    ).fillna(False) & ~recorded_ceiling_exhaustion
    if invented_ceiling_exhaustion.any():
        prediction_missing = (
            merged["prediction"].isna()
            if "prediction" in merged.columns
            else pd.Series(True, index=merged.index)
        )
        merged.loc[
            invented_ceiling_exhaustion & prediction_missing,
            "failure_source",
        ] = "parse_contract_failure"
        merged.loc[
            invented_ceiling_exhaustion & ~prediction_missing,
            "failure_source",
        ] = "llm_error"
    return merged


def merge_case_annotations(
    predictions: pd.DataFrame,
    case_annotations: pd.DataFrame,
) -> pd.DataFrame:
    """Attach optional grouped audit annotations to prediction rows."""
    if case_annotations.empty:
        return predictions
    existing_columns = [
        column
        for column in [
            "case_annotation",
            "case_failure_sources",
            "case_failure_subtypes",
        ]
        if column in predictions.columns
    ]
    if existing_columns:
        predictions = predictions.drop(columns=existing_columns)
    return predictions.merge(
        case_annotations,
        on=["scenario_id", "variable"],
        how="left",
    )


SNAPSHOT_MANIFEST = Path(__file__).resolve().parents[1] / (
    "paper/snapshot/20260501/manifest.json"
)


def committed_reference_digest(country: str = "us") -> str | None:
    """The reference CSV digest pinned in the committed snapshot manifest.

    Legacy reference sidecars predate ``reference_csv_sha256``; production
    exports of those references must verify the CSV against this pin instead.
    """
    if country != "us" or not SNAPSHOT_MANIFEST.exists():
        return None
    refresh = json.loads(SNAPSHOT_MANIFEST.read_text()).get(
        "reference_output_refresh", {}
    )
    digest = refresh.get("reference_csv_sha256")
    return digest if isinstance(digest, str) and digest else None


def resolve_reference_digest(value: str | None, country: str = "us") -> str | None:
    """Turn a CLI ``--reference-digest`` value into a hex digest or None.

    ``"manifest"`` selects the committed snapshot's pin; any other string is
    taken as the sha256 of ``reference_outputs.csv``.
    """
    if value is None:
        return None
    if value == "manifest":
        digest = committed_reference_digest(country)
        if digest is None:
            raise ReferenceProvenanceError(
                "No committed reference digest is available for country "
                f"{country!r}; pass the sha256 explicitly."
            )
        return digest
    return value


def export_country(country_dir: Path, *, reference_digest: str | None = None) -> dict:
    """Write analysis artifacts and dashboard payload for one country run.

    Reference provenance is verified strictly: the sidecar must carry the
    reference CSV digest, or ``reference_digest`` must supply the pin for a
    legacy sidecar (``committed_reference_digest`` for the frozen references).
    """
    ground_truth_path = country_dir / "reference_outputs.csv"
    legacy_ground_truth_path = country_dir / "ground_truth.csv"
    scenarios_path = country_dir / "scenarios.csv"
    if not ground_truth_path.exists():
        if legacy_ground_truth_path.exists():
            ground_truth_path = legacy_ground_truth_path
        else:
            raise FileNotFoundError(f"Missing {ground_truth_path}.")
    if not scenarios_path.exists():
        raise FileNotFoundError(f"Missing {scenarios_path}.")

    ground_truth = pd.read_csv(ground_truth_path)
    scenarios = pd.read_csv(scenarios_path)
    country = (
        str(scenarios["country"].dropna().iloc[0]).lower()
        if "country" in scenarios.columns and not scenarios["country"].dropna().empty
        else country_dir.name.lower().split("_", 1)[0]
    )
    policyengine_bundles = reference_policyengine_bundles(
        ground_truth_path,
        country,
        require_digest=True,
        manifest_reference_sha256=reference_digest,
    )
    predictions = load_predictions(country_dir)
    predictions = merge_annotations(predictions, load_annotations(country_dir))
    predictions = merge_case_annotations(
        predictions,
        load_case_annotations(country_dir),
    )
    predictions = merge_case_reference_explanations(
        predictions,
        load_case_reference_explanations(country_dir),
    )
    ground_truth = _filter_to_canonical_outputs(ground_truth, country)
    predictions = _filter_to_canonical_outputs(predictions, country)

    analysis = analyze_no_tools(ground_truth, predictions, scenarios=scenarios)
    export_analysis(analysis, country_dir / "analysis")

    scenario_prompts = build_scenario_prompt_map(
        scenarios,
        ground_truth["variable"].drop_duplicates().tolist(),
    )
    payload = build_dashboard_payload(
        ground_truth,
        predictions,
        analysis,
        scenarios,
        scenario_prompts=scenario_prompts,
        policyengine_bundles=policyengine_bundles,
    )
    (country_dir / "data.json").write_text(
        dump_country_payload(payload, country=country, source=str(country_dir)),
        encoding="utf-8",
    )
    return payload


def reference_policyengine_bundles(
    ground_truth_path: Path,
    country: str,
    *,
    require_digest: bool = False,
    manifest_reference_sha256: str | None = None,
) -> dict:
    """PolicyEngine provenance of the reference outputs, from their sidecar.

    ``reference_outputs.csv.meta.json`` is written by the reference generator
    and records the model package version that produced the values. The export
    must carry that provenance, not the exporting machine's installed runtime:
    the v1.1 references were regenerated with a newer policyengine-us than the
    export environment runs. Missing or incomplete provenance is an export
    error rather than permission to substitute an installed runtime.

    New sidecars bind their provenance to the reference CSV's digest and row
    count. For legacy sidecars, strict callers must supply the digest already
    pinned in the committed snapshot manifest.
    """
    sidecar = ground_truth_path.with_name(ground_truth_path.name + ".meta.json")
    if not sidecar.exists():
        raise ReferenceProvenanceError(
            f"Reference provenance sidecar is missing: {sidecar}. "
            f"Cannot export country {country!r}."
        )
    metadata = json.loads(sidecar.read_text())
    if metadata.get("country") != country:
        raise ReferenceProvenanceError(
            f"Reference provenance sidecar {sidecar} has country "
            f"{metadata.get('country')!r}, expected {country!r}."
        )
    recorded_digest = metadata.get("reference_csv_sha256")
    if "reference_csv_sha256" in metadata and (
        not isinstance(recorded_digest, str) or not recorded_digest.strip()
    ):
        raise ReferenceProvenanceError(
            f"Reference provenance sidecar {sidecar} has an invalid "
            "reference_csv_sha256; expected a nonempty string."
        )
    if require_digest and recorded_digest is None and not manifest_reference_sha256:
        raise ReferenceProvenanceError(
            f"Reference provenance sidecar {sidecar} has no reference_csv_sha256; "
            "legacy references require a hash pinned in the snapshot manifest."
        )
    expected_digests = {
        "reference_csv_sha256": recorded_digest,
        "snapshot manifest": manifest_reference_sha256,
    }
    if any(digest is not None for digest in expected_digests.values()):
        actual_digest = hashlib.sha256(ground_truth_path.read_bytes()).hexdigest()
        for label, expected_digest in expected_digests.items():
            if expected_digest is not None and actual_digest != expected_digest:
                raise ReferenceProvenanceError(
                    f"Reference CSV {ground_truth_path} hash does not match "
                    f"{label} in its provenance."
                )
    if "row_count" in metadata:
        actual_row_count = len(pd.read_csv(ground_truth_path))
        if metadata["row_count"] != actual_row_count:
            raise ReferenceProvenanceError(
                f"Reference CSV {ground_truth_path} row_count is "
                f"{actual_row_count}, expected {metadata['row_count']!r}."
            )

    bundles = metadata.get("policyengine_bundles") or {}
    bundle = bundles.get(country)
    if bundle is None:
        raise ReferenceProvenanceError(
            f"Reference provenance sidecar {sidecar} has no "
            f"policyengine_bundles entry for country {country!r}."
        )
    missing = [
        field
        for field in _REQUIRED_REFERENCE_BUNDLE_FIELDS
        if not isinstance(bundle, dict)
        or not isinstance(bundle.get(field), str)
        or not bundle[field].strip()
    ]
    if missing:
        raise ReferenceProvenanceError(
            f"Reference provenance sidecar {sidecar} has an incomplete "
            f"policyengine_bundles entry for country {country!r}; missing or "
            f"empty required keys: {', '.join(missing)}."
        )
    return {country: dict(bundle)}


def _available_countries(run_path: Path) -> list[str]:
    """Country subdirectories under a run dir that contain run artifacts."""
    found = []
    for country in ("us", "uk"):
        country_dir = run_path / country
        if country_dir.is_dir() and (
            (country_dir / "reference_outputs.csv").exists()
            or (country_dir / "by_model").is_dir()
            or (country_dir / "predictions.csv").exists()
            or (country_dir / "predictions.csv.gz").exists()
        ):
            found.append(country)
    return found


def export_full_run(
    run_dir: str | Path,
    countries: Sequence[str] | None = None,
    app_data_output: str | Path = "app/src/data.json",
    skip_app_data: bool = False,
    reference_digest: str | None = None,
) -> dict:
    """Export per-country and combined frontend artifacts from a full run.

    ``reference_digest`` pins the reference CSV for legacy sidecars that carry
    no digest of their own (see ``export_country``).
    """
    run_path = Path(run_dir)
    if countries:
        selected_countries = list(countries)
    else:
        selected_countries = _available_countries(run_path)
        if not selected_countries:
            raise FileNotFoundError(
                f"No country subdirectory with run artifacts found under "
                f"{run_path}. Expected one of us/, uk/ containing "
                "reference_outputs.csv, by_model/, or predictions.csv[.gz]."
            )

    country_payloads = {
        country: export_country(run_path / country, reference_digest=reference_digest)
        for country in selected_countries
    }
    combined_payload = {"countries": country_payloads}
    combined_json = dump_dashboard_payload(combined_payload, source=str(run_path))

    run_payload_path = run_path / "data.json"
    run_payload_path.write_text(combined_json, encoding="utf-8")
    print(f"Wrote {run_payload_path}")

    if not skip_app_data:
        app_data_path = Path(app_data_output)
        app_data_path.parent.mkdir(parents=True, exist_ok=True)
        app_data_path.write_text(combined_json, encoding="utf-8")
        print(f"Wrote {app_data_path}")

    return combined_payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Full-run directory containing country subdirectories.",
    )
    parser.add_argument(
        "--country",
        action="append",
        dest="countries",
        default=None,
        help="Country code to export. Repeat to export multiple countries.",
    )
    parser.add_argument(
        "--app-data-output",
        default="app/src/data.json",
        help="Path for the combined frontend payload.",
    )
    parser.add_argument(
        "--skip-app-data",
        action="store_true",
        help="Only write the combined payload under the run directory.",
    )
    args = parser.parse_args()

    export_full_run(
        run_dir=args.run_dir,
        countries=args.countries,
        app_data_output=args.app_data_output,
        skip_app_data=args.skip_app_data,
    )


if __name__ == "__main__":
    main()
