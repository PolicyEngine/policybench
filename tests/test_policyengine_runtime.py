"""Tests for PolicyEngine runtime provenance metadata."""

import copy
import json
from importlib import metadata

import pytest

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


# -- provenance computed once per supervised run ------------------------------

FAKE_BUNDLES = {
    "us": {
        "bundle_id": "us-4.16.1",
        "country_id": "us",
        "model_direct_url": {"url": "file:///x", "dir_info": {"editable": True}},
        "model_matches_policyengine_bundle": True,
        "data_build_fingerprint": None,
        "certified_by": "policyengine.py bundled manifest — “certified”",
    },
    "uk": {
        "bundle_id": None,
        "country_id": "uk",
        "model_direct_url": None,
        "model_matches_policyengine_bundle": False,
        "default_dataset": "enhanced_frs_2023_24",
        "default_dataset_uri": "hf://policyengine-uk-data-private/example.h5",
    },
}
COUNTRY_SUBSETS = [{"us"}, {"uk"}, {"us", "uk"}, {"US"}, ["uk", "us", "UK"]]


@pytest.fixture
def fake_release_bundles(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "policyengine_release_bundle",
        lambda country: copy.deepcopy(FAKE_BUNDLES[country]),
    )


def _sidecar_bytes(bundles: dict) -> str:
    # The eval-no-tools sidecar serializes metadata exactly like this.
    return json.dumps({"policyengine_bundles": bundles}, indent=2, sort_keys=True)


@pytest.mark.parametrize("countries", COUNTRY_SUBSETS, ids=str)
def test_provenance_file_reproduces_direct_computation(
    fake_release_bundles, tmp_path, monkeypatch, countries
):
    path = tmp_path / runtime.POLICYENGINE_PROVENANCE_FILENAME
    assert runtime.write_policyengine_provenance(path, {"us", "uk"}) is True
    direct = runtime.policyengine_bundles_for_countries(countries)

    monkeypatch.setattr(
        runtime,
        "policyengine_bundles_for_countries",
        lambda requested: pytest.fail("fast path computed bundles directly"),
    )
    from_file = runtime.resolve_policyengine_bundles(
        countries, env={runtime.POLICYENGINE_PROVENANCE_ENV: str(path)}
    )

    assert from_file == direct
    assert list(from_file) == list(direct)
    assert _sidecar_bytes(from_file) == _sidecar_bytes(direct)


def test_real_provenance_file_reproduces_direct_computation(tmp_path):
    """The installed PolicyEngine bundles survive the file byte-for-byte."""
    path = tmp_path / runtime.POLICYENGINE_PROVENANCE_FILENAME
    assert runtime.write_policyengine_provenance(path, {"us", "uk"}) is True
    env = {runtime.POLICYENGINE_PROVENANCE_ENV: str(path)}
    for countries in COUNTRY_SUBSETS:
        direct = runtime.policyengine_bundles_for_countries(countries)
        from_file = runtime.resolve_policyengine_bundles(countries, env=env)
        assert from_file == direct
        assert _sidecar_bytes(from_file) == _sidecar_bytes(direct)


def test_provenance_reads_process_environment_by_default(
    fake_release_bundles, tmp_path, monkeypatch
):
    path = tmp_path / runtime.POLICYENGINE_PROVENANCE_FILENAME
    runtime.write_policyengine_provenance(path, {"us"})
    expected = runtime.policyengine_bundles_for_countries({"us"})
    monkeypatch.setenv(runtime.POLICYENGINE_PROVENANCE_ENV, str(path))
    monkeypatch.setattr(
        runtime,
        "policyengine_bundles_for_countries",
        lambda requested: pytest.fail("fast path computed bundles directly"),
    )

    assert runtime.resolve_policyengine_bundles({"us"}) == expected


def _tamper(path, edit):
    payload = json.loads(path.read_text())
    edit(payload)
    path.write_text(json.dumps(payload))


@pytest.mark.parametrize(
    "corrupt,reason",
    [
        (lambda path: path.unlink(), "could not read it"),
        (lambda path: path.write_text("{not json"), "could not read it"),
        (lambda path: path.write_text("[]"), "not a JSON object"),
        (
            lambda path: _tamper(path, lambda p: p.update(format_version=0)),
            "format_version 0 differs",
        ),
        (
            lambda path: _tamper(
                path,
                lambda p: p["inputs"]["distributions"]["policyengine-us"].update(
                    version="0.0.1"
                ),
            ),
            "different PolicyEngine packages or code",
        ),
        (
            lambda path: _tamper(path, lambda p: p.pop("policyengine_bundles")),
            "no policyengine_bundles object",
        ),
        (
            lambda path: _tamper(path, lambda p: p["policyengine_bundles"].pop("uk")),
            "no bundle for uk",
        ),
    ],
    ids=[
        "missing",
        "malformed",
        "not-object",
        "format-version",
        "package-changed",
        "no-bundles",
        "missing-country",
    ],
)
def test_unusable_provenance_file_falls_back_to_direct_computation(
    fake_release_bundles, tmp_path, capsys, corrupt, reason
):
    path = tmp_path / runtime.POLICYENGINE_PROVENANCE_FILENAME
    runtime.write_policyengine_provenance(path, {"us", "uk"})
    corrupt(path)

    bundles = runtime.resolve_policyengine_bundles(
        {"us", "uk"}, env={runtime.POLICYENGINE_PROVENANCE_ENV: str(path)}
    )

    assert bundles == runtime.policyengine_bundles_for_countries({"us", "uk"})
    assert reason in capsys.readouterr().err


def test_provenance_inputs_track_package_versions(monkeypatch):
    baseline = runtime.policyengine_provenance_inputs()
    real_version = runtime._package_version_or_none
    monkeypatch.setattr(
        runtime,
        "_package_version_or_none",
        lambda name: "0.0.1" if name == "policyengine-uk" else real_version(name),
    )

    changed = runtime.policyengine_provenance_inputs()

    assert changed != baseline
    assert changed["distributions"]["policyengine-uk"]["version"] == "0.0.1"


def test_provenance_without_env_computes_directly(fake_release_bundles, monkeypatch):
    monkeypatch.delenv(runtime.POLICYENGINE_PROVENANCE_ENV, raising=False)
    calls = []
    real = runtime.policyengine_bundles_for_countries
    monkeypatch.setattr(
        runtime,
        "policyengine_bundles_for_countries",
        lambda countries: calls.append(countries) or real(countries),
    )

    assert runtime.resolve_policyengine_bundles({"us"}) == real({"us"})
    assert runtime.resolve_policyengine_bundles({"us"}, env={}) == real({"us"})
    assert len(calls) == 2


def test_provenance_file_that_does_not_round_trip_is_removed(
    tmp_path, monkeypatch, capsys
):
    # A tuple serializes like a list but no longer compares equal after
    # reading it back, so the writer must not hand the file to workers.
    monkeypatch.setattr(
        runtime,
        "policyengine_release_bundle",
        lambda country: {"country_id": country, "versions": ("1", "2")},
    )
    path = tmp_path / runtime.POLICYENGINE_PROVENANCE_FILENAME

    assert runtime.write_policyengine_provenance(path, {"us"}) is False
    assert not path.exists()
    assert "workers will compute it themselves" in capsys.readouterr().err


@pytest.mark.parametrize(
    "variable,value",
    [("POLICYENGINE_SKIP_COUNTRY_IMPORTS", "1"), ("HUGGING_FACE_TOKEN", "hf_x")],
)
def test_provenance_inputs_track_policyengine_import_flags(
    fake_release_bundles, tmp_path, monkeypatch, capsys, variable, value
):
    # Either flag can change whether ``import policyengine`` succeeds, and so
    # which branch records the US bundle.
    monkeypatch.delenv("POLICYENGINE_SKIP_COUNTRY_IMPORTS", raising=False)
    monkeypatch.delenv("HUGGING_FACE_TOKEN", raising=False)
    path = tmp_path / runtime.POLICYENGINE_PROVENANCE_FILENAME
    runtime.write_policyengine_provenance(path, {"us"})

    monkeypatch.setenv(variable, value)

    runtime.resolve_policyengine_bundles(
        {"us"}, env={runtime.POLICYENGINE_PROVENANCE_ENV: str(path)}
    )
    assert "different PolicyEngine packages or code" in capsys.readouterr().err


def test_provenance_inputs_identify_the_python_environment(
    fake_release_bundles, tmp_path, monkeypatch, capsys
):
    path = tmp_path / runtime.POLICYENGINE_PROVENANCE_FILENAME
    runtime.write_policyengine_provenance(path, {"us"})

    monkeypatch.setattr(runtime.sys, "prefix", "/some/other/venv")

    runtime.resolve_policyengine_bundles(
        {"us"}, env={runtime.POLICYENGINE_PROVENANCE_ENV: str(path)}
    )
    assert "different PolicyEngine packages or code" in capsys.readouterr().err


def test_provenance_file_never_records_the_token(
    fake_release_bundles, tmp_path, monkeypatch
):
    monkeypatch.setenv("HUGGING_FACE_TOKEN", "hf_secret_value")
    path = tmp_path / runtime.POLICYENGINE_PROVENANCE_FILENAME

    assert runtime.write_policyengine_provenance(path, {"us"}) is True

    text = path.read_text()
    assert "hf_secret_value" not in text
    assert json.loads(text)["inputs"]["environment"]["HUGGING_FACE_TOKEN_set"] is True


def test_editable_policyengine_install_is_never_reused(
    fake_release_bundles, tmp_path, monkeypatch, capsys
):
    path = tmp_path / runtime.POLICYENGINE_PROVENANCE_FILENAME
    path.write_text("stale")
    real_direct_url = runtime._package_direct_url_or_none
    monkeypatch.setattr(
        runtime,
        "_package_direct_url_or_none",
        lambda name: (
            {"url": "file:///src/policyengine-us", "dir_info": {"editable": True}}
            if name == "policyengine-us"
            else real_direct_url(name)
        ),
    )

    assert runtime.write_policyengine_provenance(path, {"us"}) is False
    assert not path.exists()
    assert "editable install of policyengine-us" in capsys.readouterr().err


def test_provenance_write_failure_leaves_no_file(
    fake_release_bundles, tmp_path, monkeypatch, capsys
):
    def deny(source, destination):
        raise PermissionError("denied")

    monkeypatch.setattr(runtime.os, "replace", deny)
    path = tmp_path / runtime.POLICYENGINE_PROVENANCE_FILENAME

    assert runtime.write_policyengine_provenance(path, {"us"}) is False
    assert list(tmp_path.iterdir()) == []
    assert "not written (PermissionError)" in capsys.readouterr().err


def test_fallback_message_is_marked_and_carries_no_error_text(
    fake_release_bundles, tmp_path, capsys
):
    path = tmp_path / "missing.json"

    runtime.resolve_policyengine_bundles(
        {"us"}, env={runtime.POLICYENGINE_PROVENANCE_ENV: str(path)}
    )

    message = capsys.readouterr().err
    assert message.startswith(runtime.POLICYENGINE_PROVENANCE_NOT_REUSED)
    assert "(FileNotFoundError)" in message
    assert "No such file" not in message
