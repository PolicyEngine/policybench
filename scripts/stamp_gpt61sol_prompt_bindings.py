"""Stamp prompt_sha256 on GPT-6.1 Sol stage verdicts judged before the runner did.

scripts/run_audit_claude.sh now records, in each verdict's sidecar, the
sha256 of the prompt it piped to the judge, and validate_verdicts requires it
of every verdict that is not carried over from the seed. The stage's first
134 Opus 5.5 re-judges ran before that. For each case GPT-6.1 Sol re-opened
(prompt-changes.json's changed and added lists) whose sidecar lacks the hash,
this script:

- finds the judge's own session transcript, by the sidecar's session_id,
  under the given Claude config directories (default ~/.claude);
- requires the transcript's first user message to be prompt.md's exact text,
  so the stamp records the prompt the judge read, not merely the file now on
  disk;
- records prompt_sha256 and how it was established in the sidecar, and copies
  the transcript beside the verdict as claude.transcript.jsonl.

verdict.json is untouched, so the sidecar's verdict_sha256 still binds it. A
sidecar that already records a prompt_sha256 must match prompt.md. Every check
runs before anything is written: one missing, ambiguous or different
transcript stops the script with nothing changed. It is idempotent.

Usage::

    python scripts/stamp_gpt61sol_prompt_bindings.py --stage-dir STAGE \\
        [--claude-config ~/.claude ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from finish_gpt61sol import rejudged_cases  # noqa: E402

SOURCE = (
    "stamped by scripts/stamp_gpt61sol_prompt_bindings.py: the judge's session "
    "transcript ({session}) shows prompt.md's exact text as its prompt"
)


def first_prompt(transcript: Path) -> str | None:
    """The text of a Claude Code transcript's first user message."""
    for line in transcript.read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") != "user":
            continue
        content = (event.get("message") or {}).get("content")
        if isinstance(content, list):
            texts = [part.get("text") for part in content if part.get("type") == "text"]
            content = texts[0] if len(texts) == 1 else None
        return content if isinstance(content, str) else None
    return None


def plan(stage: Path, configs: list[Path]) -> dict[str, tuple[dict, Path]]:
    """The sidecars to stamp and the transcript behind each, checked in full."""
    cases = stage / "audit" / "cases"
    stamps: dict[str, tuple[dict, Path]] = {}
    problems: list[str] = []
    for case in sorted(rejudged_cases(stage)):
        directory = cases / case
        meta = json.loads((directory / "verdict.meta.json").read_text())
        prompt = (directory / "prompt.md").read_bytes()
        digest = hashlib.sha256(prompt).hexdigest()
        if "prompt_sha256" in meta:
            if meta["prompt_sha256"] != digest:
                problems.append(f"{case}: its sidecar records another prompt")
            continue
        session = meta.get("session_id")
        found = [
            path
            for config in configs
            for path in sorted(config.glob(f"projects/*/{session}.jsonl"))
        ]
        if not session or len(found) != 1:
            problems.append(f"{case}: {len(found)} transcripts for session {session}")
            continue
        if first_prompt(found[0]) != prompt.decode():
            problems.append(f"{case}: transcript {session} shows another prompt")
            continue
        stamped = {
            **meta,
            "prompt_sha256": digest,
            "prompt_sha256_source": SOURCE.format(session=session),
        }
        stamps[case] = (stamped, found[0])
    if problems:
        raise SystemExit(
            f"{len(problems)} verdicts cannot be stamped; nothing written: "
            + "; ".join(problems[:8])
        )
    return stamps


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument(
        "--claude-config",
        type=Path,
        action="append",
        help="a Claude config directory holding judge transcripts (repeatable; "
        "default ~/.claude)",
    )
    args = parser.parse_args(argv)
    stage = args.stage_dir.resolve()
    configs = args.claude_config or [Path.home() / ".claude"]
    stamps = plan(stage, configs)
    cases = stage / "audit" / "cases"
    for case, (meta, transcript) in stamps.items():
        shutil.copyfile(transcript, cases / case / "claude.transcript.jsonl")
        (cases / case / "verdict.meta.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True)
        )
    print(f"Stamped prompt_sha256 on {len(stamps)} verdicts")


if __name__ == "__main__":
    main()
