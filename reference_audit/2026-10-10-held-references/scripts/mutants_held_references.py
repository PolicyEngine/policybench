"""Break the held-references rule and its command one way at a time, and run
tests/test_held_references.py against each break.

The unmodified tests must pass first. Each mutant then replaces one exact
piece of source text (it must occur once), the tests run with -x, and the
source is restored. A mutant is killed only when pytest ran and a test failed
(exit status 1); a collection error or any other status is reported as an
error, not as a kill. A mutant the tests still pass is a property the tests
do not hold. Writes verification/mutants_held_references.txt and exits 1 if
any mutant survives or errors.

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
        "a cluster may answer for models it does not name",
        RULE,
        "    if len(set(models)) != len(models) or set(models) != set(predictions):\n"
        "        return None\n",
        "",
    ),
    (
        "a cluster may count more members than it names",
        RULE,
        '    if cluster.get("n_models") != len(models):\n        return None\n',
        "",
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
        "the flags' recorded payload is never compared",
        CLI,
        "            if source_sha256 != payload_sha256:",
        "            if False:",
    ),
    (
        "flags that record no payload are accepted",
        CLI,
        "            if source_sha256 != payload_sha256:",
        "            if source_sha256 and source_sha256 != payload_sha256:",
    ),
    (
        "the flags are not recomputed from the payload",
        CLI,
        "            if consensus_flags(payload, flag_params) != flags:",
        "            if False:",
    ),
    (
        "the held cells' cases are not looked for",
        CLI,
        "                payload, [flag for flag in flags if id(flag) not in unheld_ids]",
        "                payload, []",
    ),
    (
        "a runner's files for a cell that became held are deleted",
        CLI,
        "            if runner_files:\n                raise SystemExit(",
        "            if False:\n                raise SystemExit(",
    ),
    (
        "only a published stage 1 or verdict protects a case",
        CLI,
        "                    child.name != STAGE1_PROMPT",
        '                    child.name in ("stage1.json", "verdict.json")',
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


def run_tests() -> tuple[int, str]:
    """pytest's exit status and the last line it printed, without the time."""
    run = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-q", "-x", "--tb=no"]
        + ["-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    tail = (run.stdout.strip().splitlines() or ["(no output)"])[-1]
    return run.returncode, tail.rsplit(" in ", 1)[0]


def main() -> int:
    status, tail = run_tests()
    if status != 0:
        raise SystemExit(f"the unmodified tests do not pass ({tail}); nothing to mutate")
    lines = [
        "Each line breaks policybench/held_references.py or the adversary-prepare",
        f"branch of policybench/cli.py one way and runs {TESTS} (-x).",
        "scripts/mutants_held_references.py holds each break's exact text. A mutant",
        "is killed only when pytest ran and a test failed (exit status 1).",
        "",
        f"Unmodified: {tail}",
        "",
    ]
    counts = {"killed": 0, "SURVIVED": 0, "ERROR": 0}
    for number, (what, name, old, new) in enumerate(MUTANTS, start=1):
        path = ROOT / name
        original = path.read_text()
        if original.count(old) != 1:
            raise SystemExit(
                f"mutant {number} ({what}): text occurs {original.count(old)} times"
            )
        try:
            path.write_text(original.replace(old, new))
            status, tail = run_tests()
        finally:
            path.write_text(original)
        outcome = {0: "SURVIVED", 1: "killed"}.get(status, "ERROR")
        counts[outcome] += 1
        lines.append(f"{number:2d}. {outcome:8s}  {what} [{name}]: {tail}")
    lines.append("")
    lines.append(
        f"{counts['killed']} of {len(MUTANTS)} mutants killed, "
        f"{counts['SURVIVED']} survived, {counts['ERROR']} errored"
    )
    text = "\n".join(lines) + "\n"
    (HERE / "verification" / "mutants_held_references.txt").write_text(text)
    print(text, end="")
    return 1 if counts["SURVIVED"] or counts["ERROR"] else 0


if __name__ == "__main__":
    sys.exit(main())
