"""Tests for publishing the dashboard payload as a release asset."""

import json
import subprocess
from unittest.mock import patch

import pytest

from policybench.dashboard_schema import DashboardValidationError
from policybench.publish_dashboard import (
    PublishError,
    build_pointer,
    publish_dashboard,
)
from tests.test_dashboard_schema import make_payload


@pytest.fixture
def payload_file(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps(make_payload()), encoding="utf-8")
    return path


def test_dry_run_writes_pointer_without_gh(payload_file, tmp_path):
    pointer_path = tmp_path / "data.artifact.json"
    with patch("policybench.publish_dashboard.subprocess.run") as run:
        pointer = publish_dashboard(
            payload_file,
            "dashboard-data-20260610",
            pointer_output=pointer_path,
            dry_run=True,
        )
    run.assert_not_called()
    on_disk = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert on_disk == pointer
    assert pointer["version"] == 1
    assert pointer["tag"] == "dashboard-data-20260610"
    assert pointer["bytes"] == payload_file.stat().st_size
    assert len(pointer["sha256"]) == 64
    assert pointer["url"] == (
        "https://github.com/PolicyEngine/policybench/releases/download/"
        "dashboard-data-20260610/dashboard-data.json"
    )


def test_invalid_payload_aborts_before_upload(tmp_path):
    bad = tmp_path / "data.json"
    bad.write_text(json.dumps({"country": "us", "modelStats": []}), encoding="utf-8")
    with patch("policybench.publish_dashboard.subprocess.run") as run:
        with pytest.raises(DashboardValidationError):
            publish_dashboard(bad, "tag", pointer_output=None)
    run.assert_not_called()


def test_missing_source_raises(tmp_path):
    with pytest.raises(PublishError, match="Missing dashboard payload"):
        publish_dashboard(tmp_path / "absent.json", "tag", pointer_output=None)


def test_upload_creates_release_when_absent(payload_file, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[:3] == ["gh", "release", "view"]:
            raise subprocess.CalledProcessError(1, args, stderr="release not found")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    with patch("policybench.publish_dashboard.subprocess.run", side_effect=fake_run):
        pointer = publish_dashboard(
            payload_file,
            "dashboard-data-20260610",
            pointer_output=tmp_path / "pointer.json",
        )

    commands = [tuple(args[1:3]) for args in calls]
    assert ("release", "view") in commands
    assert ("release", "create") in commands
    assert ("release", "upload") in commands
    upload_call = next(args for args in calls if args[1:3] == ["release", "upload"])
    assert upload_call[3] == "dashboard-data-20260610"
    assert upload_call[4].endswith("dashboard-data.json")
    assert "--clobber" in upload_call
    assert pointer["sha256"]


def test_gh_failure_surfaces(payload_file):
    def fake_run(args, **kwargs):
        if args[:3] == ["gh", "release", "view"]:
            return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")
        raise subprocess.CalledProcessError(1, args, stderr="upload blew up")

    with patch("policybench.publish_dashboard.subprocess.run", side_effect=fake_run):
        with pytest.raises(PublishError, match="upload blew up"):
            publish_dashboard(payload_file, "tag", pointer_output=None)


def test_build_pointer_shape():
    pointer = build_pointer(
        repo="PolicyEngine/policybench",
        tag="t",
        asset="a.json",
        sha256="x" * 64,
        size_bytes=5,
    )
    assert set(pointer) == {
        "version",
        "repo",
        "tag",
        "asset",
        "url",
        "sha256",
        "bytes",
    }
