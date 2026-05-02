"""PolicyEngine runtime wiring through the policyengine.py release bundle."""

from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any

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
    """Return the bundled policyengine.py manifest and validate installed pins."""
    try:
        from policyengine.provenance.manifest import get_release_manifest
    except ModuleNotFoundError:
        from policyengine.core.release_manifest import get_release_manifest

    manifest = get_release_manifest(country)
    installed_model_version = metadata.version(manifest.model_package.name)
    if installed_model_version != manifest.model_package.version:
        raise ValueError(
            f"Installed {manifest.model_package.name} version does not match the "
            "bundled policyengine.py manifest. Expected "
            f"{manifest.model_package.version}, got {installed_model_version}."
        )

    certification = manifest.certification
    certified_data_artifact = manifest.certified_data_artifact
    return {
        "bundle_id": manifest.bundle_id,
        "country_id": manifest.country_id,
        "policyengine_version": manifest.policyengine_version,
        "model_package": manifest.model_package.name,
        "model_version": manifest.model_package.version,
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
        "compatibility_basis": (
            certification.compatibility_basis if certification is not None else None
        ),
        "certified_by": (
            certification.certified_by if certification is not None else None
        ),
    }


def get_us_situation_simulation_class():
    """Return the PE-US situation Simulation class after bundle validation."""
    policyengine_release_bundle("us")
    from policyengine_us import Simulation

    return Simulation


def make_us_microsimulation(**kwargs):
    """Create a PE-US Microsimulation after policyengine.py bundle validation."""
    from policyengine_us import Microsimulation

    sim = Microsimulation(**kwargs)
    sim.policyengine_bundle = {
        **policyengine_release_bundle("us"),
        "runtime_dataset": getattr(sim, "default_dataset", None),
        "managed_by": "policybench via policyengine.py",
    }
    return sim


def policyengine_bundles_for_countries(countries: set[str] | list[str]) -> dict:
    """Return policyengine.py bundle metadata keyed by country."""
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
    """Return the PE-UK single-year dataset class after bundle validation."""
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
        "managed_by": "policybench via policyengine.py",
    }
    return sim
