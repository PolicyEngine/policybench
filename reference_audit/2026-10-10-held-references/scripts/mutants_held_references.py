"""Break the held-references rule and its command one way at a time, and run
tests/test_held_references.py against each break.

Each mutant replaces one exact piece of source text (it must occur once), the
tests run with -x, and the source is restored. A mutant the tests still pass
is a property the tests do not hold. Writes
verification/mutants_held_references.txt and exits 1 if any mutant survives.

  uv run python reference_audit/2026-10-10-held-references/scripts/mutants_held_references.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RULE = "policybench/held_references.py"
CLI = "policybench/cli.py"
TESTS = "tests/test_held_references.py"

# (what breaks, file, the text as it stands, the text with the break)
MUTANTS = [
    (
        "the prompt is never compared",
        RULE,
        'if prompt != record["prompt_sha256"]:',
        "if False:",
    ),
    (
        "a missing prompt counts as the checked one",
        RULE,
        'if prompt != record["prompt_sha256"]:',
        'if prompt is not None and prompt != record["prompt_sha256"]:',
    ),
    (
        "the held reference is never compared",
        RULE,
        'if not _same(reference, float(record["reference"]), exact):',
        "if False:",
    ),
    (
        "an unexplained consensus no longer keeps the cell",
        RULE,
        "        if unexplained:",
        "        if False:",
    ),
    (
        "the bound is exclusive",
        RULE,
        "abs(a - b) <= HOLD_TOLERANCE",
        "abs(a - b) < HOLD_TOLERANCE",
    ),
    (
        "the bound is two dollars",
        RULE,
        "HOLD_TOLERANCE = 1.0",
        "HOLD_TOLERANCE = 2.0",
    ),
    (
        "eligibility outputs compare in dollars",
        RULE,
        "return a == b if exact else",
        "return",
    ),
    (
        "one member near the explained answer is enough",
        RULE,
        "                        if all(\n                            _same(answer, float(entry",
        "                        if any(\n                            _same(answer, float(entry",
    ),
    (
        "the cluster's rounded key is compared, not its members",
        RULE,
        "            answers = _member_answers(cluster)",
        '            answers = [float(cluster["answer"])]',
    ),
    (
        "a cluster with no member answers is explained by anything",
        RULE,
        "    if not all(_finite(answer) for answer in answers):\n        return None",
        "    if not all(_finite(answer) for answer in answers):\n        return []",
    ),
    (
        "a flag with no cluster is accepted",
        RULE,
        '        if not flag.get("clusters"):',
        "        if False:",
    ),
    (
        "not_flagged lists the flagged records",
        RULE,
        "        if cell not in flagged",
        "        if cell in flagged",
    ),
    (
        "a flag with no record is dropped",
        RULE,
        "        if record is None:\n            kept.append(flag)\n            continue",
        "        if record is None:\n            continue",
    ),
    (
        "a flag whose reference moved is dropped instead of kept",
        RULE,
        '            kept.append(flag)\n            not_applied.append(\n                {**summary, "reason": "reference_moved"',
        '            not_applied.append(\n                {**summary, "reason": "reference_moved"',
    ),
    (
        "a held cell is also kept",
        RULE,
        '        held.append({**summary, "clusters": clusters, "record": record})',
        '        held.append({**summary, "clusters": clusters, "record": record})\n'
        "        kept.append(flag)",
    ),
    (
        "a cell flagged twice is accepted",
        RULE,
        "        if cell in flagged:\n            raise",
        "        if False:\n            raise",
    ),
    (
        "a cell may be listed twice",
        RULE,
        "        if cell in seen:",
        "        if False:",
    ),
    (
        "any verdict is accepted",
        RULE,
        '        if record.get("verdict") != HELD_VERDICT:',
        "        if False:",
    ),
    (
        "a record needs no prompt hash",
        RULE,
        "        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):",
        "        if False:",
    ),
    (
        "a direct call does not check its records",
        RULE,
        "for r in validate_records(records)}",
        "for r in records}",
    ),
    (
        "the explanation is not carried into the listing",
        RULE,
        '"explanation": covering["explanation"],',
        '"explanation": "",',
    ),
    (
        "flags from another payload are accepted",
        CLI,
        "            if source_sha256 and source_sha256 != payload_sha256:",
        "            if False:",
    ),
    (
        "held flags are not checked against the payload",
        CLI,
        "                payload, [flag for flag in flags if id(flag) not in judged_ids]",
        "                payload, []",
    ),
    (
        "a judged case that became held is deleted",
        CLI,
        "            if judged:\n                raise SystemExit(",
        "            if False:\n                raise SystemExit(",
    ),
    (
        "a stale record of a covered cell is said to be judged",
        CLI,
        'row["case"] = "covered_elsewhere" if cell in skipped else "prepared"',
        'row["case"] = "prepared"',
    ),
    (
        "the listing outlives a preparation without the option",
        CLI,
        "            held_path.unlink(missing_ok=True)",
        "            pass",
    ),
    (
        "covered cells are counted with held ones",
        CLI,
        '            f"({len(unheld) - len(kept)} flagged cells skipped as covered "',
        '            f"({len(flags) - len(kept)} flagged cells skipped as covered "',
    ),
]


def main() -> int:
    lines = [
        "Each line breaks policybench/held_references.py or the adversary-prepare",
        f"branch of policybench/cli.py one way and runs {TESTS} (-x).",
        "scripts/mutants_held_references.py holds each break's exact text.",
        "",
    ]
    survivors = 0
    for number, (what, name, old, new) in enumerate(MUTANTS, start=1):
        path = ROOT / name
        original = path.read_text()
        if original.count(old) != 1:
            raise SystemExit(f"mutant {number} ({what}): text occurs {original.count(old)} times")
        try:
            path.write_text(original.replace(old, new))
            run = subprocess.run(
                [sys.executable, "-m", "pytest", TESTS, "-q", "-x", "--tb=no", "-p", "no:cacheprovider"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
        finally:
            path.write_text(original)
        killed = run.returncode != 0
        survivors += not killed
        tail = run.stdout.strip().splitlines()[-1]
        # Drop the run time, which differs from run to run.
        tail = tail.rsplit(" in ", 1)[0]
        lines.append(f"{number:2d}. {'killed  ' if killed else 'SURVIVED'}  {what} [{name}]: {tail}")
    lines.append("")
    lines.append(f"{len(MUTANTS) - survivors} of {len(MUTANTS)} mutants killed")
    text = "\n".join(lines) + "\n"
    (HERE / "verification" / "mutants_held_references.txt").write_text(text)
    print(text, end="")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
