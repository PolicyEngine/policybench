"""scripts/stamp_gpt61sol_prompt_bindings.py stamps only what a transcript shows."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import stamp_gpt61sol_prompt_bindings as stamp  # noqa: E402

REOPENED = "us__scenario_001__snap"
KEPT = "us__scenario_002__snap"


def _case(stage: Path, case: str, session: str) -> Path:
    directory = stage / "audit" / "cases" / case
    directory.mkdir(parents=True)
    (directory / "prompt.md").write_text(f"Classify {case}.\n")
    verdict = directory / "verdict.json"
    verdict.write_text('{"case_failure_source": "llm_error"}')
    (directory / "verdict.meta.json").write_text(
        json.dumps(
            {
                "judge_runner": "scripts/run_audit_claude.sh",
                "session_id": session,
                "verdict_sha256": hashlib.sha256(verdict.read_bytes()).hexdigest(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return directory


def _transcript(config: Path, session: str, prompt: str) -> Path:
    path = config / "projects" / "-private-tmp-x" / f"{session}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    events = [
        {"type": "queue-operation"},
        {"type": "user", "message": {"role": "user", "content": prompt}},
        {"type": "assistant", "message": {"content": [{"type": "text"}]}},
    ]
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    return path


@pytest.fixture
def stage(tmp_path, monkeypatch):
    # The driver re-derives the re-opened cases from a bound seed; these
    # synthetic stages have none, so read prompt-changes.json as written.
    monkeypatch.setattr(
        stamp,
        "rejudged_cases",
        lambda stage: frozenset(
            json.loads((stage / "prompt-changes.json").read_text())["changed"]
        ),
    )
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "prompt-changes.json").write_text(
        json.dumps({"added": [], "changed": [REOPENED], "kept": [KEPT]})
    )
    reopened = _case(stage, REOPENED, "s-1")
    kept = _case(stage, KEPT, "s-2")
    config = tmp_path / "claude"
    _transcript(config, "s-1", (reopened / "prompt.md").read_text())
    return stage, reopened, kept, config


def _files(stage: Path) -> dict:
    return {p: p.read_bytes() for p in stage.rglob("*") if p.is_file()}


def test_a_verdict_is_stamped_with_the_prompt_its_transcript_shows(stage):
    stage, reopened, kept, config = stage
    verdict = (reopened / "verdict.json").read_bytes()
    kept_before = _files(kept)
    stamp.main(["--stage-dir", str(stage), "--claude-config", str(config)])
    meta = json.loads((reopened / "verdict.meta.json").read_text())
    assert (
        meta["prompt_sha256"]
        == hashlib.sha256((reopened / "prompt.md").read_bytes()).hexdigest()
    )
    assert "s-1" in meta["prompt_sha256_source"]
    assert (reopened / "verdict.json").read_bytes() == verdict
    assert meta["verdict_sha256"] == hashlib.sha256(verdict).hexdigest()
    assert (reopened / "claude.transcript.jsonl").is_file()
    # A carried-over case is never touched.
    assert _files(kept) == kept_before
    # Idempotent.
    before = _files(stage)
    stamp.main(["--stage-dir", str(stage), "--claude-config", str(config)])
    assert _files(stage) == before


@pytest.mark.parametrize(
    "defect", ["other_prompt", "missing", "duplicate", "stale", "no_sidecar"]
)
def test_nothing_is_stamped_unless_every_transcript_agrees(stage, tmp_path, defect):
    stage, reopened, _, config = stage
    transcript = config / "projects/-private-tmp-x/s-1.jsonl"
    if defect == "other_prompt":
        _transcript(config, "s-1", "Classify something else.\n")
    elif defect == "missing":
        transcript.unlink()
    elif defect == "duplicate":
        _transcript(tmp_path / "other-claude", "s-1", "Classify anything.\n")
    elif defect == "no_sidecar":
        (reopened / "verdict.meta.json").unlink()
    else:
        meta = json.loads((reopened / "verdict.meta.json").read_text())
        meta["prompt_sha256"] = "0" * 64
        (reopened / "verdict.meta.json").write_text(json.dumps(meta))
    before = _files(stage)
    configs = ["--claude-config", str(config)]
    if defect == "duplicate":
        configs += ["--claude-config", str(tmp_path / "other-claude")]
    with pytest.raises(SystemExit, match="cannot be stamped; nothing written"):
        stamp.main(["--stage-dir", str(stage), *configs])
    assert _files(stage) == before


def test_first_prompt_reads_string_and_single_text_part_messages(tmp_path):
    path = tmp_path / "t.jsonl"
    for content, expected in (
        ("Plain.\n", "Plain.\n"),
        ([{"type": "text", "text": "Part.\n"}], "Part.\n"),
        ([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}], None),
    ):
        path.write_text(json.dumps({"type": "user", "message": {"content": content}}))
        assert stamp.first_prompt(path) == expected
