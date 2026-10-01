"""Tests for PolicyEngine runtime provenance metadata.

``policyengine_release_bundle`` must record the same bundle on every call, in
every process, whatever the policyengine import flags say, and the bundle must
not contradict itself. Until 2026-09-29 the US bundle depended on whether
``import policyengine`` had already been attempted in the process: the first
attempt fails without HUGGING_FACE_TOKEN (the UK model's data certification
gets a 401), so sidecars recorded "installed package, no matching
policyengine.py bundle manifest" for a model that matched the bundle.

The synthetic tests enumerate every combination of the inputs that decide the
bundle. The installed-environment tests pin the real result in fresh processes
and check the manifest reading against policyengine's own code.
"""

import copy
import hashlib
import importlib.util
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from importlib import metadata
from pathlib import Path

import pydantic
import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

import policybench.policyengine_runtime as runtime

# The only fields allowed to differ between a matching and a non-matching
# installed model for the same bundled manifest.
MATCH_DEPENDENT_FIELDS = {
    "model_version",
    "model_version_source",
    "model_matches_policyengine_bundle",
    "compatibility_basis",
    "certified_by",
}

PINNED_US_MODEL = "1.0.0"


def _installed_policyengine_root() -> Path:
    root = Path(metadata.distribution("policyengine").locate_file("policyengine"))
    assert root.is_dir(), root
    return root


def _raw_installed_manifest(country: str) -> dict:
    """The installed manifest's own JSON, read without the runtime's reader."""
    root = _installed_policyengine_root()
    per_country = root / "data" / "release_manifests" / f"{country}.json"
    if per_country.is_file():
        return json.loads(per_country.read_text(encoding="utf-8"))
    bundle = json.loads(
        (root / "data" / "bundle" / "manifest.json").read_text(encoding="utf-8")
    )
    return bundle["data_releases"][country]


def _installed_model_matches_bundle(country: str) -> bool:
    """policyengine's own rule: the installed model is the manifest's model."""
    installed = metadata.version(runtime.MODEL_PACKAGES[country])
    return installed == _raw_installed_manifest(country)["model_package"]["version"]


@pytest.fixture(autouse=True)
def _fresh_caches():
    runtime.policyengine_release_bundle.cache_clear()
    runtime._load_policyengine_manifest_schema.cache_clear()
    sys.modules.pop(runtime.MANIFEST_SCHEMA_MODULE, None)
    yield
    runtime.policyengine_release_bundle.cache_clear()
    runtime._load_policyengine_manifest_schema.cache_clear()
    sys.modules.pop(runtime.MANIFEST_SCHEMA_MODULE, None)


def _policyengine_modules() -> set[str]:
    return {
        name
        for name in sys.modules
        if name == "policyengine" or name.startswith("policyengine.")
    }


# -- synthetic policyengine distributions ------------------------------------


def _synthetic_manifest(
    *,
    certification: str = "full",
    certified_artifact: str = "default",
    default_in_datasets: bool = True,
    dataset_pins: bool = False,
) -> dict:
    """A bundled US manifest built from one point of the input space."""
    manifest = {
        "schema_version": 1,
        "bundle_id": "us-9.9.9",
        "country_id": "us",
        "policyengine_version": "9.9.9",
        "model_package": {"name": "policyengine-us", "version": PINNED_US_MODEL},
        "data_package": {
            "name": "sample-data",
            "version": "0.1.0",
            "repo_id": "policyengine/sample-data",
            "release_manifest_revision": "sample-build-rev",
        },
        "default_dataset": "sample_2024",
        "datasets": {},
    }
    if default_in_datasets:
        reference = {"path": "sample_2024.h5"}
        if dataset_pins:
            reference |= {"repo_id": "policyengine/pinned", "revision": "pin-rev"}
        manifest["datasets"]["sample_2024"] = reference
    if certification == "full":
        manifest["certification"] = {
            "compatibility_basis": "exact_build_model_version",
            "certified_for_model_version": PINNED_US_MODEL,
            "data_build_id": "sample-build",
            "built_with_model_version": PINNED_US_MODEL,
            "built_with_model_git_sha": "abc123",
            "data_build_fingerprint": "sha256:feed",
            "certified_by": "policyengine.py bundled manifest",
        }
    elif certification == "partial":
        manifest["certification"] = {
            "compatibility_basis": "bundle_candidate",
            "certified_for_model_version": PINNED_US_MODEL,
        }
    if certified_artifact != "absent":
        manifest["certified_data_artifact"] = {
            "dataset": "sample_2024" if certified_artifact == "default" else "other",
            "uri": "hf://policyengine/sample-data/certified.h5@certified-rev",
            "sha256": "0" * 64,
            "build_id": "certified-build",
        }
    return manifest


OVERLAY = {"sample_overlay": {"path": "overlay.h5", "revision": "overlay-rev"}}


@pytest.fixture
def fake_policyengine(tmp_path, monkeypatch):
    """Point the runtime at a synthetic policyengine distribution.

    The schema module is the installed policyengine's real manifest.py, copied
    next to the synthetic manifest, so validation runs policyengine's own model.
    ``layout`` is policyengine.py 4.x's per-country manifest file or 6.x's
    single bundle manifest (with a dataset overlay).
    """
    site = tmp_path / "site-packages"
    root = site / "policyengine"
    (root / "provenance").mkdir(parents=True)
    (root / "data" / "release_manifests").mkdir(parents=True)
    (root / "data" / "bundle").mkdir(parents=True)
    shutil.copy(
        _installed_policyengine_root() / "provenance" / "manifest.py",
        root / "provenance" / "manifest.py",
    )
    per_country_path = root / "data" / "release_manifests" / "us.json"
    bundle_path = root / "data" / "bundle" / "manifest.json"
    state = {"installed": PINNED_US_MODEL, "pinned": PINNED_US_MODEL}

    def install(
        manifest: dict | None,
        *,
        installed: str,
        pinned=PINNED_US_MODEL,
        layout: str = "per_country",
        overlays: dict | None = None,
    ):
        per_country_path.unlink(missing_ok=True)
        bundle_path.unlink(missing_ok=True)
        if manifest is not None and layout == "per_country":
            per_country_path.write_text(json.dumps(manifest), encoding="utf-8")
        elif manifest is not None:
            bundle_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "data_releases": {"us": manifest},
                        "dataset_overlays": {
                            "us": OVERLAY if overlays is None else overlays
                        },
                    }
                ),
                encoding="utf-8",
            )
        state["installed"] = installed
        state["pinned"] = pinned
        runtime.policyengine_release_bundle.cache_clear()

    _relocate_policyengine(monkeypatch, site)
    monkeypatch.setattr(
        runtime,
        "_bundled_model_version_from_policyengine_metadata",
        lambda country, model_package_name: state["pinned"],
    )
    monkeypatch.setattr(
        runtime,
        "_package_version_or_none",
        lambda package: {"policyengine": "9.9.9"}.get(package),
    )
    monkeypatch.setattr(runtime, "_package_direct_url_or_none", lambda package: None)
    real_version = metadata.version
    monkeypatch.setattr(
        runtime.metadata,
        "version",
        lambda package: (
            state["installed"]
            if package == "policyengine-us"
            else real_version(package)
        ),
    )
    install.root = root
    install.per_country_path = per_country_path
    install.bundle_path = bundle_path
    return install


# Every shape of bundled manifest the runtime distinguishes, in both layouts,
# plus no manifest at all.
INPUT_SPACE = [
    (True, *shape)
    for shape in itertools.product(
        ("per_country", "bundle"),  # policyengine.py 4.x or 6.x layout
        ("full", "partial", "absent"),  # certification
        ("default", "other", "absent"),  # certified data artifact
        (True, False),  # default dataset listed in the manifest
        (True, False),  # that listing pins its own repo and revision
    )
] + [(False, "per_country", "absent", "absent", False, False)]


@pytest.mark.parametrize(
    "manifest_present,layout,certification,certified_artifact,"
    "default_in_datasets,dataset_pins",
    INPUT_SPACE,
)
def test_bundle_invariants_hold_for_every_manifest_shape(
    fake_policyengine,
    manifest_present,
    layout,
    certification,
    certified_artifact,
    default_in_datasets,
    dataset_pins,
):
    manifest = (
        _synthetic_manifest(
            certification=certification,
            certified_artifact=certified_artifact,
            default_in_datasets=default_in_datasets,
            dataset_pins=dataset_pins,
        )
        if manifest_present
        else None
    )
    loaded_before = _policyengine_modules()

    results = {}
    for installed in (PINNED_US_MODEL, "1.0.1"):
        fake_policyengine(manifest, installed=installed, layout=layout)
        attempts = []
        for _ in range(3):
            runtime.policyengine_release_bundle.cache_clear()
            attempts.append(runtime.policyengine_release_bundle("us"))
        # Determinism: the attempt count never changes the bundle.
        assert all(attempt == attempts[0] for attempt in attempts)
        results[installed] = attempts[0]

    # Isolation: computing the bundle never imports policyengine.
    assert _policyengine_modules() == loaded_before

    for installed, bundle in results.items():
        matches = manifest_present and installed == PINNED_US_MODEL
        certification_block = (manifest or {}).get("certification") or {}
        # Consistency: every match-dependent field agrees with the match.
        assert bundle["model_matches_policyengine_bundle"] is matches
        assert bundle["model_version"] == installed
        assert bundle["bundled_model_version"] == PINNED_US_MODEL
        assert bundle["model_version_source"] == (
            "policyengine.py bundle" if matches else "installed package"
        )
        if matches:
            assert (
                bundle["compatibility_basis"]
                == bundle["bundled_compatibility_basis"]
                == certification_block.get("compatibility_basis")
            )
            assert (
                bundle["certified_by"]
                == bundle["bundled_certified_by"]
                == certification_block.get("certified_by")
            )
        else:
            assert bundle["compatibility_basis"] == (
                runtime.UNBUNDLED_COMPATIBILITY_BASIS
            )
            assert bundle["certified_by"] == runtime.UNBUNDLED_CERTIFIED_BY

    # Branch agreement: a matching and a newer installed model record the same
    # bundle except for the match-dependent fields.
    matching, newer = results[PINNED_US_MODEL], results["1.0.1"]
    assert list(matching) == list(newer)
    differing = {key for key in matching if matching[key] != newer[key]}
    assert differing <= MATCH_DEPENDENT_FIELDS

    # Field provenance: the data fields come from the manifest when there is one.
    if manifest is not None:
        for bundle in results.values():
            assert bundle["bundle_id"] == manifest["bundle_id"]
            assert bundle["bundled_policyengine_version"] == "9.9.9"
            assert bundle["data_package"] == "sample-data"
            assert bundle["data_version"] == "0.1.0"
            assert bundle["default_dataset"] == "sample_2024"
            assert bundle["default_dataset_uri"] == _expected_default_uri(
                certified_artifact, default_in_datasets, dataset_pins
            )


def _expected_default_uri(certified_artifact, default_in_datasets, dataset_pins):
    """policyengine's default_dataset_uri, written out for the synthetic shapes."""
    if certified_artifact == "default":
        return "hf://policyengine/sample-data/certified.h5@certified-rev"
    if not default_in_datasets:
        return None  # policyengine would look further, on disk or online
    if dataset_pins:
        return "hf://policyengine/pinned/sample_2024.h5@pin-rev"
    return "hf://policyengine/sample-data/sample_2024.h5@sample-build-rev"


def test_bundle_layout_merges_dataset_overlays(fake_policyengine):
    fake_policyengine(_synthetic_manifest(), installed=PINNED_US_MODEL, layout="bundle")

    raw = runtime._load_raw_policyengine_manifest("us")

    assert raw["datasets"] == {"sample_2024": {"path": "sample_2024.h5"}} | OVERLAY
    assert runtime._load_raw_policyengine_manifest("uk") is None
    assert runtime.policyengine_release_bundle("us")[
        "model_matches_policyengine_bundle"
    ]


@pytest.mark.parametrize("name", ["sample_2024", "other_2024"])
def test_overlay_that_replaces_a_certified_dataset_raises(fake_policyengine, name):
    manifest = _synthetic_manifest()
    manifest["datasets"]["other_2024"] = {"path": "other_2024.h5"}
    fake_policyengine(
        manifest,
        installed=PINNED_US_MODEL,
        layout="bundle",
        overlays={name: {"path": "replacement.h5"}},
    )

    with pytest.raises(ValueError, match="overlays may only add datasets"):
        runtime.policyengine_release_bundle("us")


def test_invalid_matching_manifest_raises_instead_of_recording_no_manifest(
    fake_policyengine,
):
    manifest = _synthetic_manifest()
    del manifest["model_package"]
    fake_policyengine(manifest, installed=PINNED_US_MODEL)

    with pytest.raises(pydantic.ValidationError, match="model_package"):
        runtime.policyengine_release_bundle("us")


@pytest.mark.parametrize(
    "field,value",
    [
        (("model_package", "version"), "1.0.2"),
        (("model_package", "name"), "policyengine-uk"),
        (("country_id",), "uk"),
        (("certification", "certified_for_model_version"), "0.9.0"),
    ],
)
def test_manifest_that_contradicts_the_pin_raises(fake_policyengine, field, value):
    manifest = _synthetic_manifest()
    target = manifest
    for key in field[:-1]:
        target = target[key]
    target[field[-1]] = value
    fake_policyengine(manifest, installed=PINNED_US_MODEL)

    with pytest.raises(ValueError, match="contradictory PolicyEngine provenance"):
        runtime.policyengine_release_bundle("us")


def test_newer_installed_model_does_not_validate_the_manifest(fake_policyengine):
    """A model newer than the bundle keeps the tolerant raw-JSON read."""
    manifest = _synthetic_manifest()
    manifest["model_package"]["version"] = "not validated"
    fake_policyengine(manifest, installed="1.0.1")

    bundle = runtime.policyengine_release_bundle("us")

    assert bundle["model_matches_policyengine_bundle"] is False
    assert bundle["data_version"] == "0.1.0"
    assert runtime.MANIFEST_SCHEMA_MODULE not in sys.modules


def test_no_policyengine_distribution_records_the_source_data_fallback(
    fake_policyengine, monkeypatch
):
    fake_policyengine(None, installed="1.0.1", pinned=None)
    monkeypatch.setattr(runtime, "_policyengine_package_file", lambda relative: None)

    bundle = runtime.policyengine_release_bundle("us")

    assert bundle["model_matches_policyengine_bundle"] is False
    assert bundle["bundled_model_version"] is None
    assert bundle["bundle_id"] is None
    assert (
        bundle["default_dataset_uri"]
        == runtime.SOURCE_DATA_PROVENANCE["us"]["default_dataset_uri"]
    )


def test_schema_module_that_imports_policyengine_is_refused(
    fake_policyengine, monkeypatch
):
    fake_policyengine(_synthetic_manifest(), installed=PINNED_US_MODEL)
    leaked = "policyengine._policybench_test_leak"
    monkeypatch.delitem(sys.modules, leaked, raising=False)
    schema_path = fake_policyengine.root / "provenance" / "manifest.py"
    schema_path.write_text(
        "import sys, types\n"
        f"sys.modules[{leaked!r}] = types.ModuleType({leaked!r})\n"
        + schema_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    try:
        with pytest.raises(RuntimeError, match="without running"):
            runtime.policyengine_release_bundle("us")
        assert runtime.MANIFEST_SCHEMA_MODULE not in sys.modules
    finally:
        sys.modules.pop(leaked, None)


def test_missing_schema_module_raises_for_a_matching_manifest(fake_policyengine):
    fake_policyengine(_synthetic_manifest(), installed=PINNED_US_MODEL)
    (fake_policyengine.root / "provenance" / "manifest.py").unlink()

    with pytest.raises(RuntimeError, match="provenance/manifest.py"):
        runtime.policyengine_release_bundle("us")


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


# -- the installed PolicyEngine packages -------------------------------------


@pytest.mark.parametrize("country", sorted(runtime.MODEL_PACKAGES))
def test_installed_bundle_follows_policyengines_match_rule_on_every_attempt(country):
    raw = _raw_installed_manifest(country)
    certification = raw.get("certification") or {}
    matches = _installed_model_matches_bundle(country)
    loaded_before = _policyengine_modules()

    attempts = []
    for _ in range(2):
        runtime.policyengine_release_bundle.cache_clear()
        attempts.append(runtime.policyengine_release_bundle(country))

    assert attempts[0] == attempts[1]
    bundle = attempts[0]
    assert bundle["model_matches_policyengine_bundle"] is matches
    assert bundle["model_version_source"] == (
        "policyengine.py bundle" if matches else "installed package"
    )
    assert bundle["compatibility_basis"] == (
        certification.get("compatibility_basis")
        if matches
        else runtime.UNBUNDLED_COMPATIBILITY_BASIS
    )
    assert bundle["certified_by"] == (
        certification.get("certified_by") if matches else runtime.UNBUNDLED_CERTIFIED_BY
    )
    assert bundle["bundle_id"] == raw["bundle_id"]
    assert _policyengine_modules() == loaded_before


# Runs in a fresh interpreter with sockets disabled, so a bundle that needed the
# network (the old import path) would fail or change instead of passing.
BUNDLE_PROBE = textwrap.dedent(
    """
    import json, os, socket, sys

    def _no_network(*args, **kwargs):
        raise OSError("network disabled by test_policyengine_runtime")

    socket.socket.connect = _no_network
    socket.create_connection = _no_network

    mode = os.environ["PROBE_MODE"]
    if mode in ("after_policyengine_import", "after_failed_policyengine_import"):
        # Leaves whatever policyengine modules the attempt loaded, as production
        # processes had, whether or not the import succeeds here.
        try:
            import policyengine.provenance.manifest  # noqa: F401
        except Exception:
            pass

    from policybench import policyengine_runtime as runtime

    loaded_before = {m for m in sys.modules if m.split(".")[0] == "policyengine"}
    attempts = 2 if mode == "second_attempt" else 1
    for _ in range(attempts):
        runtime.policyengine_release_bundle.cache_clear()
        bundles = runtime.policyengine_bundles_for_countries({"us", "uk"})
    loaded_after = {m for m in sys.modules if m.split(".")[0] == "policyengine"}
    assert loaded_after == loaded_before, sorted(loaded_after - loaded_before)
    print(json.dumps(bundles, sort_keys=True))
    """
)

PROBE_VARIANTS = {
    "first_attempt": {},
    "second_attempt": {},
    "skip_country_imports": {"POLICYENGINE_SKIP_COUNTRY_IMPORTS": "1"},
    "invalid_hf_token": {"HUGGING_FACE_TOKEN": "hf_invalid_policybench_test"},
    "after_policyengine_import": {"POLICYENGINE_SKIP_COUNTRY_IMPORTS": "1"},
}


def _probe(mode: str, extra_env: dict) -> dict:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"HUGGING_FACE_TOKEN", "POLICYENGINE_SKIP_COUNTRY_IMPORTS"}
    }
    env |= extra_env | {"PROBE_MODE": mode}
    completed = subprocess.run(
        [sys.executable, "-c", BUNDLE_PROBE],
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_bundles_are_identical_across_processes_attempts_and_env_flags():
    bundles = {mode: _probe(mode, env) for mode, env in PROBE_VARIANTS.items()}

    reference = bundles["first_attempt"]
    for mode, bundle in bundles.items():
        assert bundle == reference, mode
    for country, bundle in reference.items():
        assert bundle["model_matches_policyengine_bundle"] is (
            _installed_model_matches_bundle(country)
        ), country


@pytest.mark.slow
def test_bundle_is_unchanged_after_the_failed_package_import():
    """The production failure: policyengine's import raised before provenance.

    Without POLICYENGINE_SKIP_COUNTRY_IMPORTS the import builds the US model
    before the UK data certification fails, so this is slow.
    """
    reference = _probe("first_attempt", {})
    assert _probe("after_failed_policyengine_import", {}) == reference


def _policyengine_manifest_module(monkeypatch):
    """policyengine's own manifest module, executed from its file.

    Its ``get_release_manifest`` finds the package through
    ``importlib.resources.files("policyengine")``, which imports policyengine.
    That one lookup is pointed at the installed package directory; everything
    else is policyengine's code as shipped.
    """
    root = _installed_policyengine_root()
    name = "_policybench_test_policyengine_manifest"
    spec = importlib.util.spec_from_file_location(
        name, root / "provenance" / "manifest.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "files", lambda package: root)
    return module


@pytest.mark.parametrize("country", sorted(runtime.MODEL_PACKAGES))
def test_manifest_reading_agrees_with_policyengines_own_code(monkeypatch, country):
    policyengine_manifest = _policyengine_manifest_module(monkeypatch)
    loaded_before = _policyengine_modules()

    expected = policyengine_manifest.get_release_manifest(country)
    raw = runtime._load_raw_policyengine_manifest(country)
    schema = runtime._policyengine_manifest_schema()
    ours = schema.CountryReleaseManifest.model_validate(copy.deepcopy(raw))

    assert ours.model_dump(mode="json") == expected.model_dump(mode="json")
    assert (
        runtime._default_dataset_uri_from_raw_manifest(raw)
        == expected.default_dataset_uri
    )
    assert expected.datasets
    for name in expected.datasets:
        assert runtime._dataset_uri_from_raw_manifest(
            raw, name
        ) == policyengine_manifest.resolve_dataset_reference(country, name), name
    assert _policyengine_modules() == loaded_before


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


# Sorted, so the ids do not depend on set iteration order (PYTHONHASHSEED).
@pytest.mark.parametrize(
    "countries", COUNTRY_SUBSETS, ids=lambda countries: ",".join(sorted(countries))
)
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
# Spelled out rather than taken from the module, so a wrong path there fails.
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

    No installed model package is made the version policyengine.py pins, so
    the fixture releases, which name no model package, are never validated.
    """
    root = tmp_path / "site-packages"
    _relocate_policyengine(monkeypatch, root)
    monkeypatch.setattr(
        runtime,
        "_bundled_model_version_from_policyengine_metadata",
        lambda country, model_package_name: None,
    )
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

    For the bundle layout this is the edit the pre-merge delta review of #182
    showed went undetected: data_releases.us.bundle_id.
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
# A bundle manifest may also carry dataset_overlays beside data_releases, which
# policyengine.py 6.1.2's own loader applies.
_MANIFEST_FILES = st.fixed_dictionaries(
    {
        RELEASE_MANIFEST.format(country="us"): st.none() | _RELEASES,
        RELEASE_MANIFEST.format(country="uk"): st.none() | _RELEASES,
        BUNDLE_MANIFEST: st.none()
        | st.fixed_dictionaries(
            {
                "data_releases": st.fixed_dictionaries(
                    {"us": _RELEASES, "uk": _RELEASES}
                )
            },
            optional={"dataset_overlays": st.sampled_from([{}, {"us": {}}])},
        ),
    }
)
_PER_COUNTRY_FILES = {
    RELEASE_MANIFEST.format(country=country): {"bundle_id": "one"}
    for country in ("us", "uk")
}


def _bundle(us_bundle_id, **extra):
    return {
        "data_releases": {
            "us": {"bundle_id": us_bundle_id},
            "uk": {"bundle_id": "one"},
        },
        **extra,
    }


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
# Both layouts at once: policyengine.py 6.1.2's loader reads the bundle
# manifest even where a per-country file exists, so it is hashed regardless.
@example(
    first={**_PER_COUNTRY_FILES, BUNDLE_MANIFEST: _bundle("one")},
    second={**_PER_COUNTRY_FILES, BUNDLE_MANIFEST: _bundle("two")},
)
# The whole bundle manifest counts, not only data_releases.
@example(
    first={BUNDLE_MANIFEST: _bundle("one")},
    second={BUNDLE_MANIFEST: _bundle("one", dataset_overlays={"us": {}})},
)
def test_equal_fingerprints_mean_equal_raw_manifests(first, second):
    """Both layouts' manifest files, all the raw reader opens, are fingerprinted.

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
def test_provenance_file_is_reused_whatever_the_policyengine_import_flags(
    fake_release_bundles, tmp_path, monkeypatch, capsys, variable, value
):
    # The bundles never import policyengine, so neither flag can change them.
    monkeypatch.delenv("POLICYENGINE_SKIP_COUNTRY_IMPORTS", raising=False)
    monkeypatch.delenv("HUGGING_FACE_TOKEN", raising=False)
    path = tmp_path / runtime.POLICYENGINE_PROVENANCE_FILENAME
    runtime.write_policyengine_provenance(path, {"us"})
    assert "environment" not in runtime.policyengine_provenance_inputs()

    monkeypatch.setenv(variable, value)
    monkeypatch.setattr(
        runtime,
        "policyengine_bundles_for_countries",
        lambda requested: pytest.fail("fast path computed bundles directly"),
    )

    assert runtime.resolve_policyengine_bundles(
        {"us"}, env={runtime.POLICYENGINE_PROVENANCE_ENV: str(path)}
    ) == {"us": FAKE_BUNDLES["us"]}
    assert runtime.POLICYENGINE_PROVENANCE_NOT_REUSED not in capsys.readouterr().err


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
    assert "HUGGING_FACE_TOKEN" not in text


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
