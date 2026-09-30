"""Tests for PolicyEngine runtime provenance metadata."""

import copy
import hashlib
import json
import tempfile
from importlib import metadata
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

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


class _Distribution:
    def __init__(self, root):
        self.root = root

    def locate_file(self, path):
        return self.root / path


def test_raw_manifest_reads_the_policyengine_6_bundle_layout(monkeypatch, tmp_path):
    """policyengine.py 6.x moved per-country manifests into one bundle manifest."""
    import json

    bundle = tmp_path / "policyengine" / "data" / "bundle"
    bundle.mkdir(parents=True)
    release = {
        "bundle_id": "us-6.1.2",
        "data_package": {"name": "microcosm-data", "version": "0.1.0"},
        "default_dataset": "populace_us_2024",
    }
    (bundle / "manifest.json").write_text(
        json.dumps({"bundle_version": "6.1.2", "data_releases": {"us": release}})
    )
    monkeypatch.setattr(metadata, "distribution", lambda name: _Distribution(tmp_path))
    assert runtime._load_raw_policyengine_manifest("us") == release
    assert runtime._load_raw_policyengine_manifest("uk") is None


def test_installed_policyengine_yields_a_complete_reference_bundle():
    """The pinned policyengine.py gives every field the reference sidecar needs."""
    from policybench.full_run_export import _REQUIRED_REFERENCE_BUNDLE_FIELDS

    runtime.policyengine_release_bundle.cache_clear()
    bundle = runtime.policyengine_release_bundle("us")
    runtime.policyengine_release_bundle.cache_clear()
    missing = [
        field
        for field in _REQUIRED_REFERENCE_BUNDLE_FIELDS
        if not isinstance(bundle.get(field), str) or not bundle[field].strip()
    ]
    assert not missing, missing


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


# Where each policyengine.py layout keeps its release manifests: 4.16.1 ships
# one per country, 6.1.2 one bundle manifest with each under data_releases.
RELEASE_MANIFEST = "policyengine/data/release_manifests/{country}.json"
BUNDLE_MANIFEST = "policyengine/data/bundle/manifest.json"
LAYOUTS = ["per-country", "bundle"]


class _RelocatedDistribution:
    """An installed distribution whose package files live under ``root``."""

    def __init__(self, distribution, root):
        self._distribution = distribution
        self._root = Path(root)

    def locate_file(self, path):
        return self._root / path

    def __getattr__(self, name):
        return getattr(self._distribution, name)


def _relocate_policyengine(monkeypatch, root):
    real = metadata.distribution
    monkeypatch.setattr(
        metadata,
        "distribution",
        lambda name: (
            _RelocatedDistribution(real(name), root)
            if name == "policyengine"
            else real(name)
        ),
    )


def _file_texts(files):
    """``{relative path: JSON payload}`` as written; a None payload is absent.

    Key order survives serialization, so payloads that compare equal as
    dicts can still differ as files.
    """
    return {
        relative_path: json.dumps(payload)
        for relative_path, payload in files.items()
        if payload is not None
    }


def _write_files(root, files):
    for relative_path, text in _file_texts(files).items():
        path = Path(root) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _release(country, bundle_id):
    return {
        "bundle_id": bundle_id,
        "policyengine_version": "6.1.2",
        "data_package": {"name": f"{country}-fixture-data", "version": "0.1.0"},
        "default_dataset": f"{country}_fixture_dataset",
    }


def _layout_files(layout, us_bundle_id):
    releases = {"us": _release("us", us_bundle_id), "uk": _release("uk", "uk-fixture")}
    if layout == "per-country":
        return {
            RELEASE_MANIFEST.format(country=country): release
            for country, release in releases.items()
        }
    return {BUNDLE_MANIFEST: {"bundle_version": "6.1.2", "data_releases": releases}}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def relocated_policyengine(monkeypatch, tmp_path):
    """policyengine's package files under a temporary root, read unimported.

    ``_load_policyengine_manifest`` returns None, as it does when no installed
    model package is the version policyengine.py pins, so every bundle comes
    from ``_load_raw_policyengine_manifest``.
    """
    root = tmp_path / "site-packages"
    _relocate_policyengine(monkeypatch, root)
    monkeypatch.setattr(runtime, "_load_policyengine_manifest", lambda country: None)
    runtime.policyengine_release_bundle.cache_clear()
    yield root
    runtime.policyengine_release_bundle.cache_clear()


@pytest.mark.parametrize("layout", LAYOUTS)
def test_provenance_inputs_hash_each_layouts_manifests(relocated_policyengine, layout):
    """The per-country layout fingerprints as before; the bundle manifest too."""
    root = relocated_policyengine
    _write_files(root, _layout_files(layout, "us-fixture-1"))

    inputs = runtime.policyengine_provenance_inputs()

    if layout == "per-country":
        assert inputs["release_manifest_sha256"] == {
            country: _sha256(root / RELEASE_MANIFEST.format(country=country))
            for country in ("uk", "us")
        }
        assert inputs["bundle_manifest_sha256"] is None
    else:
        assert inputs["release_manifest_sha256"] == {"uk": None, "us": None}
        assert inputs["bundle_manifest_sha256"] == _sha256(root / BUNDLE_MANIFEST)


@pytest.mark.parametrize("layout", LAYOUTS)
def test_manifest_edited_in_place_makes_the_provenance_file_stale(
    relocated_policyengine, tmp_path, capsys, layout
):
    """An in-place edit of the release a bundle came from is never reused.

    For the bundle layout this is the review of PR #182: editing
    data_releases.us.bundle_id left the fingerprint unchanged.
    """
    root = relocated_policyengine
    _write_files(root, _layout_files(layout, "us-fixture-1"))
    path = tmp_path / runtime.POLICYENGINE_PROVENANCE_FILENAME
    env = {runtime.POLICYENGINE_PROVENANCE_ENV: str(path)}
    assert runtime.write_policyengine_provenance(path, {"us"}) is True
    before = runtime.policyengine_provenance_inputs()
    reused = runtime.resolve_policyengine_bundles({"us"}, env=env)
    assert reused["us"]["bundle_id"] == "us-fixture-1"

    _write_files(root, _layout_files(layout, "us-fixture-2"))
    # As in a worker started after the edit.
    runtime.policyengine_release_bundle.cache_clear()

    assert runtime.policyengine_provenance_inputs() != before
    bundles, reason = runtime._read_policyengine_provenance(path, ["us"])
    assert bundles is None
    assert reason == "it was written for different PolicyEngine packages or code"
    fresh = runtime.resolve_policyengine_bundles({"us"}, env=env)
    assert fresh["us"]["bundle_id"] == "us-fixture-2"
    assert runtime.POLICYENGINE_PROVENANCE_NOT_REUSED in capsys.readouterr().err


def test_installed_policyengine_manifest_is_fingerprinted():
    """Whichever layout the pinned policyengine.py ships, its manifest is hashed."""
    assert runtime._load_raw_policyengine_manifest("us") is not None
    inputs = runtime.policyengine_provenance_inputs()
    hashes = [
        *inputs["release_manifest_sha256"].values(),
        inputs["bundle_manifest_sha256"],
    ]
    assert any(sha256 is not None for sha256 in hashes)


_RELEASES = st.sampled_from([{"bundle_id": "one"}, {"bundle_id": "two"}])
# Any mix of the two layouts' files, each present with some content or absent.
_MANIFEST_FILES = st.fixed_dictionaries(
    {
        RELEASE_MANIFEST.format(country="us"): st.none() | _RELEASES,
        RELEASE_MANIFEST.format(country="uk"): st.none() | _RELEASES,
        BUNDLE_MANIFEST: st.none()
        | st.fixed_dictionaries(
            {"data_releases": st.fixed_dictionaries({"us": _RELEASES, "uk": _RELEASES})}
        ),
    }
)


def _fingerprint_and_raw_manifests(files):
    with (
        pytest.MonkeyPatch.context() as monkeypatch,
        tempfile.TemporaryDirectory() as root,
    ):
        _write_files(root, files)
        _relocate_policyengine(monkeypatch, root)
        return runtime.policyengine_provenance_inputs(), {
            country: runtime._load_raw_policyengine_manifest(country)
            for country in runtime.MODEL_PACKAGES
        }


@settings(max_examples=60, deadline=None)
@given(first=_MANIFEST_FILES, second=_MANIFEST_FILES)
def test_equal_fingerprints_mean_equal_raw_manifests(first, second):
    """Every file the raw manifest reader reads is in the fingerprint.

    For two environments that differ only in these files, the fingerprints
    are equal exactly when the files are byte for byte the same, wherever
    they are installed; so equal fingerprints hand every country the same
    release.
    """
    first_inputs, first_manifests = _fingerprint_and_raw_manifests(first)
    second_inputs, second_manifests = _fingerprint_and_raw_manifests(second)

    assert (first_inputs == second_inputs) == (
        _file_texts(first) == _file_texts(second)
    )
    if first_inputs == second_inputs:
        assert first_manifests == second_manifests


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
