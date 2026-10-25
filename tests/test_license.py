"""Every license declaration in the repository names the license in LICENSE.

GitHub reads LICENSE, packaging reads pyproject.toml, the MyST docs site reads
docs/myst.yml and readers read the README. From the first code commit (February
2025) until October 2026, LICENSE held the Unlicense while pyproject.toml
declared MIT (docs/myst.yml followed it in February 2026), so the code's license
depended on where one looked.
"""

from __future__ import annotations

import configparser
import json
import re
import subprocess
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPDX_ID = "Unlicense"
LICENSE_URL = "https://github.com/PolicyEngine/policybench/blob/main/LICENSE"
# File names whose formats carry a license field.
MANIFESTS = {
    ".zenodo.json",
    "CITATION.cff",
    "Cargo.toml",
    "_quarto.yml",
    "codemeta.json",
    "myst.yml",
    "package.json",
    "pyproject.toml",
    "setup.cfg",
}
# Vendored third-party code keeps its own license.
THIRD_PARTY = ("app/public/paper/web/site_libs/",)


def _tracked_manifests() -> list[str]:
    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
    )
    assert listed.returncode == 0, "the license check needs a git checkout. " + (
        listed.stderr
    )
    return sorted(
        path
        for path in listed.stdout.split("\0")
        if Path(path).name in MANIFESTS and not path.startswith(THIRD_PARTY)
    )


def _parse(path: Path):
    text = path.read_text()
    if path.suffix == ".toml":
        return tomllib.loads(text)
    if path.suffix == ".json":
        return json.loads(text)
    if path.suffix == ".cfg":
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(text)
        return {section: dict(parser[section]) for section in parser.sections()}
    return yaml.safe_load(text)


def _license_values(node) -> list[str]:
    """Every value under a `license` key, at any depth. A mapping (MyST's
    {content, code}, pyproject's legacy {text}) contributes each of its values."""
    if isinstance(node, list):
        return [value for item in node for value in _license_values(item)]
    if not isinstance(node, dict):
        return []
    found = []
    for key, value in node.items():
        if str(key).lower() == "license":
            values = value.values() if isinstance(value, dict) else [value]
            found.extend(str(v) for v in values)
        else:
            found.extend(_license_values(value))
    return found


def test_license_file_is_the_unlicense():
    text = (ROOT / "LICENSE").read_text()
    assert text.startswith(
        "This is free and unencumbered software released into the public domain."
    )
    assert text.rstrip().endswith(
        "For more information, please refer to <https://unlicense.org>"
    )


def test_every_license_declaration_is_the_unlicense():
    manifests = _tracked_manifests()
    # The two files that disagreed must be found, or the check below is vacuous.
    assert {"pyproject.toml", "docs/myst.yml"} <= set(manifests)
    declared = {path: set(_license_values(_parse(ROOT / path))) for path in manifests}
    assert declared["pyproject.toml"] == {SPDX_ID}
    assert declared["docs/myst.yml"] == {SPDX_ID}
    assert {path: ids for path, ids in declared.items() if ids - {SPDX_ID}} == {}
    # MIT first appeared as a trove classifier as well as the license field.
    project = _parse(ROOT / "pyproject.toml")["project"]
    assert not [c for c in project.get("classifiers", []) if c.startswith("License")]


def test_readme_names_only_the_unlicense():
    readme = (ROOT / "README.md").read_text()
    assert "\n## License\n" in readme
    section = readme.split("\n## License\n", 1)[1].split("\n## ", 1)[0]
    section = " ".join(section.split())
    assert f"[Unlicense]({LICENSE_URL})" in section
    assert not re.search(r"\b(MIT|Apache|BSD|L?GPL|MPL|CC[- ]?BY|CC0)\b", section)
    badges = re.findall(r"shields\.io/badge/licen[cs]e-([^-/)\s]+)", readme, re.I)
    assert [badge.lower() for badge in badges if badge.lower() != "unlicense"] == []
