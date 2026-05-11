"""Tests for benchmark runtime provenance helpers."""

from policybench.provenance import (
    dependency_lockfile_hashes,
    installed_package_versions,
    runtime_provenance,
)


def test_installed_package_versions_skips_missing_packages():
    versions = installed_package_versions(("definitely-not-installed-policybench",))

    assert versions == {}


def test_runtime_provenance_includes_python_and_packages():
    provenance = runtime_provenance()

    assert provenance["python"]["version"]
    assert provenance["python"]["implementation"]
    assert provenance["python"]["executable"]
    assert "litellm" in provenance["packages"]
    assert "uv.lock" in provenance["lockfiles"]


def test_dependency_lockfile_hashes_hashes_existing_lockfiles(tmp_path):
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text("lock contents", encoding="utf-8")

    hashes = dependency_lockfile_hashes(tmp_path)

    assert hashes == {
        "uv.lock": "af45314a8a7cff86a2eb1073b95f9bc85fad1640809e031318555ce2f4bcf760"
    }
