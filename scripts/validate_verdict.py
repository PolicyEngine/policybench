"""Validate one audit verdict file against the audit tree's schema.json.

    python scripts/validate_verdict.py <audit_dir>/schema.json <verdict.json>

Exit 0 when the verdict is well-formed JSON that satisfies the schema, 1
otherwise. Both audit runners call this before treating a case as judged, so a
fallback parse that yields a partial object can neither be published nor mark
the case complete on a later resumable run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema


def verdict_errors(schema_path: Path, verdict_path: Path) -> list[str]:
    """Return the schema violations of ``verdict_path`` (empty when valid)."""
    try:
        schema = json.loads(Path(schema_path).read_text())
    except (OSError, ValueError) as exc:
        return [f"schema unreadable: {exc}"]
    try:
        verdict = json.loads(Path(verdict_path).read_text())
    except (OSError, ValueError) as exc:
        return [f"verdict unreadable: {exc}"]
    validator = jsonschema.Draft202012Validator(schema)
    return sorted(
        f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(verdict)
    )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    errors = verdict_errors(Path(args[0]), Path(args[1]))
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
