"""Tests for PolicyEngine runtime provenance metadata."""

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
