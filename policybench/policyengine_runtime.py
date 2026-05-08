"""PolicyEngine runtime provenance and model wiring."""

import json
import re
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any

MODEL_PACKAGES = {
    "us": "policyengine-us",
    "uk": "policyengine-uk",
}

DATA_PACKAGES = {
    "us": "policyengine-us-data",
    "uk": "policyengine-uk-data",
}

SOURCE_DATA_PROVENANCE = {
    "us": {
        "data_package": "policyengine-us-data",
        "data_version": "1.73.0",
        "default_dataset": "enhanced_cps_2024",
        "default_dataset_uri": (
            "hf://policyengine/policyengine-us-data/enhanced_cps_2024.h5@1.73.0"
        ),
        "certified_data_build_id": "policyengine-us-data-1.73.0",
        "certified_data_artifact_sha256": (
            "18cdc668d05311c32ae37364abcea89b0221c27154559667e951c7b19f5b5cbd"
        ),
        "data_build_model_version": "1.647.0",
    },
    "uk": {
        "data_package": "policyengine-uk-data",
        "data_version": "1.40.4",
        "default_dataset": "enhanced_frs_2023_24",
        "default_dataset_uri": (
            "hf://policyengine/policyengine-uk-data-private/"
            "enhanced_frs_2023_24.h5@1.40.4"
        ),
        "certified_data_build_id": "policyengine-uk-data-1.40.4",
        "data_build_model_version": "2.88.0",
    },
}

UK_TRANSFER_DATASET = {
    "runtime_dataset": "enhanced_cps_2025",
    "runtime_dataset_filename": "enhanced_cps_2025.h5",
    "runtime_dataset_repo": "PolicyEngine/policyengine-uk-data",
    "runtime_dataset_pinned_commit": ("9514dfb7ec607897c9f7122a2e073b922c9fd8b6"),
    "runtime_dataset_pinned_url": (
        "https://raw.githubusercontent.com/PolicyEngine/"
        "policyengine-uk-data/9514dfb7ec607897c9f7122a2e073b922c9fd8b6/"
        "policyengine_uk_data/storage/enhanced_cps_2025.h5"
    ),
    "runtime_dataset_uri": (
        "policyengine_uk_data/storage/enhanced_cps_2025.h5 from the public "
        "PolicyEngine/policyengine-uk-data repository, pinned to commit "
        "9514dfb7ec607897c9f7122a2e073b922c9fd8b6"
    ),
    "runtime_dataset_sha256": (
        "199ebc61d29231b4799ad337a95393765b5fb5aede1834b93ff2acecceded866"
    ),
    "runtime_dataset_note": (
        "UK calibrated transfer dataset derived from benchmark-compatible "
        "PolicyEngine US Enhanced CPS households. The artifact is checked "
        "into the public PolicyEngine/policyengine-uk-data GitHub "
        "repository at the pinned commit; subsequent commits in that "
        "repository may rebuild the file. It is not native UK survey "
        "microdata, enhanced FRS, or population-representative."
    ),
}


@lru_cache(maxsize=None)
def policyengine_release_bundle(country: str) -> dict[str, Any]:
    """Return PolicyEngine runtime metadata for the installed model package.

    policyengine.py bundles identify certified model/data combinations. PolicyBench
    can also run against newer installed model-package releases before a matching
    policyengine.py bundle exists, so the metadata keeps both the bundle version
    and the installed version explicit instead of rejecting the run.
    """
    country = country.lower()
    installed_policyengine_version = _package_version_or_none("policyengine")
    model_package_name = MODEL_PACKAGES[country]
    installed_model_version = metadata.version(model_package_name)
    bundled_model_version = _bundled_model_version_from_policyengine_metadata(
        country,
        model_package_name,
    )
    manifest = None
    if bundled_model_version == installed_model_version:
        manifest = _load_policyengine_manifest(country)

    if manifest is None:
        return _unbundled_policyengine_metadata(
            country=country,
            installed_policyengine_version=installed_policyengine_version,
            model_package_name=model_package_name,
            installed_model_version=installed_model_version,
            bundled_model_version=bundled_model_version,
            raw_manifest=_load_raw_policyengine_manifest(country),
        )

    model_matches_bundle = installed_model_version == bundled_model_version

    certification = manifest.certification
    certified_data_artifact = manifest.certified_data_artifact
    bundled_compatibility_basis = (
        certification.compatibility_basis if certification is not None else None
    )
    bundled_certifier = (
        certification.certified_by if certification is not None else None
    )
    return {
        "bundle_id": manifest.bundle_id,
        "country_id": manifest.country_id,
        "policyengine_version": installed_policyengine_version,
        "bundled_policyengine_version": manifest.policyengine_version,
        "model_package": manifest.model_package.name,
        "model_version": installed_model_version,
        "bundled_model_version": bundled_model_version,
        "model_version_source": "policyengine.py bundle"
        if model_matches_bundle
        else "installed package",
        "model_matches_policyengine_bundle": model_matches_bundle,
        "data_package": manifest.data_package.name,
        "data_version": manifest.data_package.version,
        "default_dataset": manifest.default_dataset,
        "default_dataset_uri": manifest.default_dataset_uri,
        "certified_data_build_id": (
            certification.data_build_id
            if certification is not None
            else (
                certified_data_artifact.build_id
                if certified_data_artifact is not None
                else None
            )
        ),
        "certified_data_artifact_sha256": (
            certified_data_artifact.sha256
            if certified_data_artifact is not None
            else None
        ),
        "data_build_model_version": (
            certification.built_with_model_version
            if certification is not None
            else None
        ),
        "data_build_model_git_sha": (
            certification.built_with_model_git_sha
            if certification is not None
            else None
        ),
        "data_build_fingerprint": (
            certification.data_build_fingerprint if certification is not None else None
        ),
        "compatibility_basis": bundled_compatibility_basis
        if model_matches_bundle
        else "installed_model_package_not_policyengine_py_bundle",
        "bundled_compatibility_basis": bundled_compatibility_basis,
        "certified_by": bundled_certifier
        if model_matches_bundle
        else (
            "installed model package; policyengine.py bundle metadata retained "
            "for provenance"
        ),
        "bundled_certified_by": bundled_certifier,
    }


def _bundled_model_version_from_policyengine_metadata(
    country: str,
    model_package_name: str,
) -> str | None:
    """Read the model version pinned by policyengine.py without importing it."""
    try:
        requires_dist = metadata.metadata("policyengine").get_all("Requires-Dist") or []
    except metadata.PackageNotFoundError:
        return None

    pattern = re.compile(
        rf"^{re.escape(model_package_name)}==([^;]+); extra == [\"']{country}[\"']"
    )
    for requirement in requires_dist:
        match = pattern.match(requirement)
        if match:
            return match.group(1)
    return None


def _package_version_or_none(package_name: str) -> str | None:
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return None


def _load_policyengine_manifest(country: str) -> Any | None:
    """Load a policyengine.py manifest when it is importable for this environment."""
    try:
        from policyengine.provenance.manifest import get_release_manifest
    except Exception:
        try:
            from policyengine.core.release_manifest import get_release_manifest
        except Exception:
            return None

    try:
        return get_release_manifest(country)
    except Exception:
        return None


def _load_raw_policyengine_manifest(country: str) -> dict[str, Any] | None:
    """Read the bundled release-manifest JSON without importing policyengine."""
    try:
        distribution = metadata.distribution("policyengine")
    except metadata.PackageNotFoundError:
        return None
    manifest_path = Path(
        distribution.locate_file(f"policyengine/data/release_manifests/{country}.json")
    )
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _default_dataset_uri_from_raw_manifest(raw_manifest: dict[str, Any]) -> str | None:
    default_dataset = raw_manifest.get("default_dataset")
    certified_artifact = raw_manifest.get("certified_data_artifact") or {}
    if certified_artifact.get("dataset") == default_dataset:
        return certified_artifact.get("uri")

    data_package = raw_manifest.get("data_package") or {}
    repo_id = data_package.get("repo_id")
    data_version = data_package.get("version")
    dataset_entry = (raw_manifest.get("datasets") or {}).get(default_dataset) or {}
    path = dataset_entry.get("path")
    if repo_id and data_version and path:
        return f"hf://{repo_id}/{path}@{data_version}"
    return None


def _unbundled_policyengine_metadata(
    *,
    country: str,
    installed_policyengine_version: str | None,
    model_package_name: str,
    installed_model_version: str,
    bundled_model_version: str | None,
    raw_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build runtime metadata when installed models are newer than policyengine.py."""
    data_package = (raw_manifest or {}).get("data_package") or {}
    certification = (raw_manifest or {}).get("certification") or {}
    certified_artifact = (raw_manifest or {}).get("certified_data_artifact") or {}
    source_data = SOURCE_DATA_PROVENANCE[country]
    return {
        "bundle_id": (raw_manifest or {}).get("bundle_id"),
        "country_id": country,
        "policyengine_version": installed_policyengine_version,
        "bundled_policyengine_version": (raw_manifest or {}).get(
            "policyengine_version"
        ),
        "model_package": model_package_name,
        "model_version": installed_model_version,
        "bundled_model_version": bundled_model_version,
        "model_version_source": "installed package",
        "model_matches_policyengine_bundle": False,
        "data_package": data_package.get(
            "name", source_data.get("data_package", DATA_PACKAGES[country])
        ),
        "data_version": data_package.get("version", source_data.get("data_version")),
        "default_dataset": (raw_manifest or {}).get(
            "default_dataset", source_data.get("default_dataset")
        ),
        "default_dataset_uri": _default_dataset_uri_from_raw_manifest(raw_manifest)
        if raw_manifest
        else source_data.get("default_dataset_uri"),
        "certified_data_build_id": certification.get("data_build_id")
        or certified_artifact.get("build_id")
        or source_data.get("certified_data_build_id"),
        "certified_data_artifact_sha256": certified_artifact.get("sha256")
        or source_data.get("certified_data_artifact_sha256"),
        "data_build_model_version": certification.get("built_with_model_version")
        or source_data.get("data_build_model_version"),
        "data_build_model_git_sha": certification.get("built_with_model_git_sha"),
        "data_build_fingerprint": certification.get("data_build_fingerprint"),
        "compatibility_basis": "installed_model_package_not_policyengine_py_bundle",
        "bundled_compatibility_basis": certification.get("compatibility_basis"),
        "certified_by": (
            "installed model package; no matching policyengine.py bundle manifest"
        ),
        "bundled_certified_by": certification.get("certified_by"),
    }


def get_us_situation_simulation_class():
    """Return the PE-US situation Simulation class and record runtime metadata."""
    policyengine_release_bundle("us")
    from policyengine_us import Simulation

    return Simulation


def make_us_microsimulation(**kwargs):
    """Create a PE-US Microsimulation with runtime provenance attached."""
    from policyengine_us import Microsimulation

    sim = Microsimulation(**kwargs)
    sim.policyengine_bundle = {
        **policyengine_release_bundle("us"),
        "runtime_dataset": getattr(sim, "default_dataset", None),
        "managed_by": "policybench via installed PolicyEngine packages",
    }
    return sim


def policyengine_bundles_for_countries(countries: set[str] | list[str]) -> dict:
    """Return PolicyEngine runtime metadata keyed by country."""
    bundles = {}
    for country in sorted({country.lower() for country in countries}):
        bundle = policyengine_release_bundle(country).copy()
        if country == "uk":
            bundle.update(UK_TRANSFER_DATASET)
            bundle["default_dataset"] = UK_TRANSFER_DATASET["runtime_dataset"]
            bundle["default_dataset_uri"] = UK_TRANSFER_DATASET["runtime_dataset_uri"]
        bundles[country] = bundle
    return bundles


def runtime_metadata_for_country(
    country: str,
    *,
    source_dataset_path: str | Path | None = None,
) -> dict:
    """Build serializable runtime provenance for benchmark artifacts."""
    country = country.lower()
    metadata = {
        "policyengine_bundles": policyengine_bundles_for_countries({country}),
    }
    if source_dataset_path is not None:
        metadata["source_dataset_path"] = str(Path(source_dataset_path))
    return metadata


def get_uk_single_year_dataset_class():
    """Return the PE-UK single-year dataset class and record runtime metadata."""
    policyengine_release_bundle("uk")
    from policyengine_uk.data import UKSingleYearDataset

    return UKSingleYearDataset


def make_uk_transfer_microsimulation(dataset_path: str | Path):
    """Create a PE-UK Microsimulation for PolicyBench's public transfer data.

    policyengine.py managed datasets do not yet identify the public UK transfer
    dataset that PolicyBench uses at runtime.
    PolicyBench's public UK path deliberately uses a local calibrated transfer
    artifact, so we validate the model bundle and attach provenance explicitly.
    """
    from policyengine_uk import Microsimulation

    dataset_path = Path(dataset_path)
    UKSingleYearDataset = get_uk_single_year_dataset_class()
    dataset = UKSingleYearDataset(file_path=str(dataset_path))
    sim = Microsimulation(dataset=dataset)
    sim.policyengine_bundle = {
        **policyengine_bundles_for_countries({"uk"})["uk"],
        "runtime_dataset": dataset_path.stem,
        "runtime_dataset_source": str(dataset_path),
        "managed_by": "policybench via installed PolicyEngine packages",
    }
    return sim
