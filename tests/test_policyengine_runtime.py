"""Tests for PolicyEngine runtime provenance metadata."""

from importlib import metadata

import policybench.policyengine_runtime as runtime


def test_uk_policyengine_bundle_uses_transfer_artifact(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "policyengine_release_bundle",
        lambda country: {
            "country_id": country,
            "default_dataset": "enhanced_frs_2023_24",
            "default_dataset_uri": "hf://policyengine-uk-data-private/example.h5",
            "certified_data_artifact_sha256": None,
        },
    )

    bundle = runtime.policyengine_bundles_for_countries({"uk"})["uk"]

    assert bundle["default_dataset"] == "enhanced_cps_2025"
    assert "private" not in bundle["default_dataset_uri"]
    assert bundle["runtime_dataset"] == "enhanced_cps_2025"
    assert bundle["runtime_dataset_sha256"] == (
        "199ebc61d29231b4799ad337a95393765b5fb5aede1834b93ff2acecceded866"
    )
    assert "not native UK survey microdata" in bundle["runtime_dataset_note"]


def test_unbundled_runtime_metadata_does_not_import_policyengine(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "_bundled_model_version_from_policyengine_metadata",
        lambda country, model_package_name: "1.0.0",
    )
    monkeypatch.setattr(runtime, "_load_policyengine_manifest", lambda country: None)
    monkeypatch.setattr(
        runtime,
        "_load_raw_policyengine_manifest",
        lambda country: {
            "bundle_id": f"{country}-bundle",
            "policyengine_version": "4.0.0",
            "data_package": {
                "name": f"policyengine-{country}-data",
                "version": "1.2.3",
                "repo_id": f"policyengine/{country}-data",
            },
            "default_dataset": "sample_dataset",
            "datasets": {"sample_dataset": {"path": "sample_dataset.h5"}},
            "certification": {
                "compatibility_basis": "exact_build_model_version",
                "data_build_id": "sample-build",
                "built_with_model_version": "1.0.0",
                "certified_by": "policyengine.py bundled manifest",
            },
        },
    )
    monkeypatch.setattr(
        metadata,
        "version",
        lambda package: {
            "policyengine": "4.3.1",
            "policyengine-us": "1.1.0",
        }[package],
    )

    runtime.policyengine_release_bundle.cache_clear()
    bundle = runtime.policyengine_release_bundle("us")

    assert bundle["model_version"] == "1.1.0"
    assert bundle["bundled_model_version"] == "1.0.0"
    assert bundle["model_matches_policyengine_bundle"] is False
    assert (
        bundle["compatibility_basis"]
        == "installed_model_package_not_policyengine_py_bundle"
    )
    assert bundle["data_version"] == "1.2.3"
    assert bundle["certified_data_build_id"] == "sample-build"
    runtime.policyengine_release_bundle.cache_clear()


def test_matching_raw_manifest_marks_policyengine_bundle_match(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "_bundled_model_version_from_policyengine_metadata",
        lambda country, model_package_name: None,
    )
    monkeypatch.setattr(
        runtime,
        "_load_policyengine_manifest",
        lambda country: (_ for _ in ()).throw(AssertionError("should not import")),
    )
    monkeypatch.setattr(
        runtime,
        "_load_raw_policyengine_manifest",
        lambda country: {
            "bundle_id": f"{country}-4.14.2",
            "country_id": country,
            "policyengine_version": "4.14.2",
            "model_package": {
                "name": f"policyengine-{country}",
                "version": "1.715.2",
            },
            "data_package": {
                "name": f"policyengine-{country}-data",
                "version": "1.115.5",
                "repo_id": f"policyengine/policyengine-{country}-data",
            },
            "default_dataset": "enhanced_cps_2024",
            "certified_data_artifact": {
                "dataset": "enhanced_cps_2024",
                "uri": (
                    "hf://policyengine/policyengine-us-data/"
                    "enhanced_cps_2024.h5@example"
                ),
                "build_id": "policyengine-us-data-1.115.5",
                "sha256": "abc123",
            },
            "certification": {
                "compatibility_basis": "legacy_compatible_model_package",
                "data_build_id": "policyengine-us-data-1.115.5",
                "built_with_model_version": "1.700.0",
                "certified_by": "policyengine-us-data release manifest",
            },
        },
    )
    monkeypatch.setattr(
        metadata,
        "version",
        lambda package: {
            "policyengine": "4.14.2",
            "policyengine-us": "1.715.2",
        }[package],
    )

    runtime.policyengine_release_bundle.cache_clear()
    bundle = runtime.policyengine_release_bundle("us")

    assert bundle["model_matches_policyengine_bundle"] is True
    assert bundle["bundled_model_version"] == "1.715.2"
    assert bundle["model_version_source"] == "policyengine.py bundle"
    assert bundle["compatibility_basis"] == "legacy_compatible_model_package"
    assert bundle["default_dataset_uri"] == (
        "hf://policyengine/policyengine-us-data/enhanced_cps_2024.h5@example"
    )
    assert bundle["certified_data_artifact_sha256"] == "abc123"
    runtime.policyengine_release_bundle.cache_clear()
