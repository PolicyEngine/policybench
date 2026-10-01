"""Validate one audit verdict file against the audit tree's schema.json.

    python scripts/validate_verdict.py <schema> <verdict> [<cases.jsonl> <case_id>]

Exit 0 when the verdict is well-formed JSON that satisfies the schema, 1
otherwise. Both audit runners call this before treating a case as judged, so a
fallback parse that yields a partial object can neither be published nor mark
the case complete on a later resumable run. Given audit-prepare's manifest and
the case's id, the verdict must also name exactly the models the case lists,
by the finish driver's rule (scripts/finish_gpt61sol.py, validate_verdicts).
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


def manifest_wrong_models(manifest_path: Path) -> dict[str, list[str]]:
    """Each case's listed models, from audit-prepare's cases.jsonl."""
    rows = map(json.loads, Path(manifest_path).read_text().splitlines())
    return {row["case_id"]: list(row["wrong_models"]) for row in rows}


def coverage_errors(verdict: dict, wrong_models: list[str] | None) -> list[str]:
    """Why a schema-valid verdict does not name exactly its case's models.

    The finish driver's rule (scripts/finish_gpt61sol.py, validate_verdicts):
    each model the case lists, once, and no other. ``wrong_models`` is None
    when the manifest does not list the case.
    """
    if wrong_models is None:
        return ["cases.jsonl lists no such case"]
    names = [m["model"] for m in verdict["models"]]
    if len(names) != len(set(names)) or set(names) != set(wrong_models):
        return [
            f"wrong model coverage: the verdict names {sorted(names)}, "
            f"the case lists {sorted(wrong_models)}"
        ]
    return []


def case_verdict_errors(
    schema_path: Path, verdict_path: Path, wrong_models: list[str] | None
) -> list[str]:
    """Schema violations, else model coverage errors (empty when it counts)."""
    errors = verdict_errors(schema_path, verdict_path)
    if errors:
        return errors
    verdict = json.loads(Path(verdict_path).read_text())
    return coverage_errors(verdict, wrong_models)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (2, 4):
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    if len(args) == 2:
        errors = verdict_errors(Path(args[0]), Path(args[1]))
    else:
        try:
            wrong_models = manifest_wrong_models(Path(args[2])).get(args[3])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors = [f"manifest unreadable: {exc!r}"]
        else:
            errors = case_verdict_errors(Path(args[0]), Path(args[1]), wrong_models)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
