"""Audit runners accept a verdict only when it satisfies schema.json in full."""

import json
import subprocess
import sys
from pathlib import Path

from policybench.audit import AUDIT_OUTPUT_SCHEMA

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_verdict import verdict_errors  # noqa: E402

VALID = {
    "reference_suspect": False,
    "reference_bug_hypothesis": "",
    "case_failure_source": "llm_error",
    "case_failure_subtype": "age_disability",
    "rationale": "The model applied the wrong age threshold.",
    "models": [
        {
            "model": "m1",
            "failure_source": "llm_error",
            "failure_subtype": "age_disability",
            "diagnosis": "Used 62 where the statute says 65.",
        }
    ],
}


def _write(tmp_path: Path, verdict: object) -> tuple[Path, Path]:
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps(AUDIT_OUTPUT_SCHEMA))
    path = tmp_path / "verdict.json"
    path.write_text(verdict if isinstance(verdict, str) else json.dumps(verdict))
    return schema, path


def test_valid_verdict_passes(tmp_path: Path):
    schema, path = _write(tmp_path, VALID)
    assert verdict_errors(schema, path) == []
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_verdict.py"), schema, path],
        capture_output=True,
    )
    assert result.returncode == 0


def test_partial_fallback_object_is_rejected(tmp_path: Path):
    # The exact shape the old two-key check let through.
    schema, path = _write(tmp_path, {"case_failure_source": "llm_error", "models": []})
    errors = verdict_errors(schema, path)
    assert any("case_failure_subtype" in e for e in errors)
    assert any("rationale" in e for e in errors)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_verdict.py"), schema, path],
        capture_output=True,
    )
    assert result.returncode == 1


def test_enum_and_extra_property_violations_are_rejected(tmp_path: Path):
    bad_enum = json.loads(json.dumps(VALID))
    bad_enum["models"][0]["failure_source"] = "not_a_class"
    schema, path = _write(tmp_path, bad_enum)
    assert any("failure_source" in e for e in verdict_errors(schema, path))
    extra = json.loads(json.dumps(VALID))
    extra["surprise"] = 1
    schema, path = _write(tmp_path, extra)
    assert any("surprise" in e for e in verdict_errors(schema, path))
    schema, path = _write(tmp_path, "{not json")
    assert verdict_errors(schema, path)[0].startswith("verdict unreadable")


def test_runner_scripts_validate_against_the_schema():
    for name in ("run_audit_claude.sh", "run_audit_codex.sh"):
        text = (ROOT / "scripts" / name).read_text()
        assert 'validate_verdict.py" "$SCHEMA"' in text, name
        assert '{"case_failure_source", "models"} <= d.keys()' not in text, name
