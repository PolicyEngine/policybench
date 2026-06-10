"""Publish the dashboard payload as a content-addressed GitHub release asset.

This is the write half of moving generated artifacts out of git history:
``publish_dashboard`` validates the payload, uploads it to a GitHub release,
and writes a small committed pointer file recording the download URL and
sha256. The app's prepare-data step resolves the pointer (and verifies the
hash) when ``app/src/data.json`` is not present in the working tree.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from policybench.dashboard_schema import assert_valid_dashboard_payload

DEFAULT_REPO = "PolicyEngine/policybench"
DEFAULT_ASSET_NAME = "dashboard-data.json"
DEFAULT_POINTER_PATH = "app/src/data.artifact.json"
POINTER_VERSION = 1


class PublishError(RuntimeError):
    pass


def _run_gh(args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["gh", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise PublishError(
            "GitHub CLI (gh) not found; publish-dashboard uploads release "
            "assets through gh"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip()
        raise PublishError(f"gh {' '.join(args[:3])} failed: {detail}") from exc


def _release_exists(repo: str, tag: str) -> bool:
    try:
        _run_gh(["release", "view", tag, "--repo", repo, "--json", "tagName"])
        return True
    except PublishError:
        return False


def build_pointer(
    *, repo: str, tag: str, asset: str, sha256: str, size_bytes: int
) -> dict:
    return {
        "version": POINTER_VERSION,
        "repo": repo,
        "tag": tag,
        "asset": asset,
        "url": f"https://github.com/{repo}/releases/download/{tag}/{asset}",
        "sha256": sha256,
        "bytes": size_bytes,
    }


def publish_dashboard(
    source: str | Path,
    tag: str,
    *,
    repo: str = DEFAULT_REPO,
    asset_name: str = DEFAULT_ASSET_NAME,
    pointer_output: str | Path | None = DEFAULT_POINTER_PATH,
    dry_run: bool = False,
) -> dict:
    """Validate, upload, and write the artifact pointer. Returns the pointer."""
    source_path = Path(source)
    if not source_path.exists():
        raise PublishError(f"Missing dashboard payload: {source_path}")

    raw = source_path.read_bytes()
    payload = json.loads(raw)
    assert_valid_dashboard_payload(payload, source=str(source_path))

    digest = hashlib.sha256(raw).hexdigest()
    pointer = build_pointer(
        repo=repo,
        tag=tag,
        asset=asset_name,
        sha256=digest,
        size_bytes=len(raw),
    )

    if not dry_run:
        if not _release_exists(repo, tag):
            _run_gh(
                [
                    "release",
                    "create",
                    tag,
                    "--repo",
                    repo,
                    "--title",
                    tag,
                    "--notes",
                    f"Dashboard data artifact.\n\nsha256: {digest}",
                ]
            )
        # gh names assets after the uploaded file, so stage a copy with the
        # canonical asset name.
        with tempfile.TemporaryDirectory() as staging:
            staged = Path(staging) / asset_name
            shutil.copyfile(source_path, staged)
            _run_gh(
                [
                    "release",
                    "upload",
                    tag,
                    str(staged),
                    "--repo",
                    repo,
                    "--clobber",
                ]
            )

    if pointer_output is not None:
        pointer_path = Path(pointer_output)
        pointer_path.parent.mkdir(parents=True, exist_ok=True)
        pointer_path.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")

    return pointer
