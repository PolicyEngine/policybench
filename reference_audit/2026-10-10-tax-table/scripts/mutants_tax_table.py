"""Break the Tax Table construction, the table parser, the sweep's look-up and
the independent scorer one way at a time, and run tests/test_tax_table_audit.py
against each.

The unmodified tests must pass first. Each mutant then replaces one exact piece
of source text (it must occur once), the tests run with -x, and the source is
restored. A mutant is killed only when pytest ran and a test failed (exit
status 1); a collection error or any other status is reported as an error, not
as a kill. A mutant the tests still pass is a property the tests do not hold.

The manifest test is left out of every run: it compares each script's sha256,
so it would fail on any edit and kill every mutant without testing anything.

A break is written into the script itself, so a run that is killed part way
could leave one in place. Before each break the script's text is saved beside it
(``<name>.before-mutation``) and removed once the script is restored; a later
run restores any script it finds saved that way before doing anything else, and
a terminate or hang-up signal restores the script on the way out.
tests/test_tax_table_audit.py's manifest test fails on a script left broken or
a saved copy left behind.

Writes verification/mutants_tax_table.txt and exits 1 if any mutant survives or
errors.

  uv run python reference_audit/2026-10-10-tax-table/scripts/mutants_tax_table.py
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
SCRIPTS = "reference_audit/2026-10-10-tax-table/scripts"
TABLE = f"{SCRIPTS}/tax_table.py"
PARSER = f"{SCRIPTS}/parse_irs_tax_table.py"
SCORER = f"{SCRIPTS}/independent_scorer.py"
SWEEP = f"{SCRIPTS}/sweep_tax_table.py"
TESTS = "tests/test_tax_table_audit.py"
MANIFEST_TEST = f"{TESTS}::test_the_manifest_pins_every_evidence_file"
SAVED = ".before-mutation"

# (what breaks, file, the text as it stands, the text with the break)
MUTANTS = [
    (
        "a half dollar rounds down",
        TABLE,
        "    return (half_cents + 100) // 200",
        "    return (half_cents + 99) // 200",
    ),
    (
        "the tax is truncated to a dollar",
        TABLE,
        "    return (half_cents + 100) // 200",
        "    return half_cents // 200",
    ),
    (
        "the tax is taken at the band's lower bound",
        TABLE,
        "half_cents = _half_cents(lower + upper, SCHEDULES[year][status])",
        "half_cents = _half_cents(2 * lower, SCHEDULES[year][status])",
    ),
    (
        "the tax is taken at the band's upper bound",
        TABLE,
        "half_cents = _half_cents(lower + upper, SCHEDULES[year][status])",
        "half_cents = _half_cents(2 * upper, SCHEDULES[year][status])",
    ),
    (
        "$25 bands run to $5,000",
        TABLE,
        "    width = 25 if taxable_income < 3_000 else 50",
        "    width = 25 if taxable_income < 5_000 else 50",
    ),
    (
        "every band above $25 is $50 wide",
        TABLE,
        "    width = 25 if taxable_income < 3_000 else 50",
        "    width = 50",
    ),
    (
        "the first band runs to $10",
        TABLE,
        "    if taxable_income < 5:\n        return 0, 5",
        "    if taxable_income < 10:\n        return 0, 10",
    ),
    (
        "a 2026 single threshold is $50 off",
        TABLE,
        '        "single": (12_400, 50_400, 105_700, 201_775, 256_225, 640_600),',
        '        "single": (12_400, 50_450, 105_700, 201_775, 256_225, 640_600),',
    ),
    (
        "a 2026 joint threshold is $50 off",
        TABLE,
        '        "joint": (24_800, 100_800, 211_400, 403_550, 512_450, 768_700),',
        '        "joint": (24_850, 100_800, 211_400, 403_550, 512_450, 768_700),',
    ),
    (
        "a 2025 head of household threshold is $50 off",
        TABLE,
        '        "head_of_household": (17_000, 64_850, 103_350, 197_300, 250_500, 626_350),',
        '        "head_of_household": (17_000, 64_900, 103_350, 197_300, 250_500, 626_350),',
    ),
    (
        "the 12 percent rate is 15 percent",
        TABLE,
        "RATES = (10, 12, 22, 24, 32, 35, 37)",
        "RATES = (10, 15, 22, 24, 32, 35, 37)",
    ),
    (
        "the top rate is 39 percent",
        TABLE,
        "RATES = (10, 12, 22, 24, 32, 35, 37)",
        "RATES = (10, 12, 22, 24, 32, 35, 39)",
    ),
    (
        "the ceiling is $110,000",
        TABLE,
        "CEILING = 100_000",
        "CEILING = 110_000",
    ),
    (
        "the table is used at exactly the ceiling",
        TABLE,
        "    if taxable_income < CEILING:\n        return float(table_tax(",
        "    if taxable_income <= CEILING:\n        return float(table_tax(",
    ),
    (
        "a surviving spouse reads the single column",
        TABLE,
        '    "SURVIVING_SPOUSE": "joint",',
        '    "SURVIVING_SPOUSE": "single",',
    ),
    (
        "the schedule skips the top of a bracket",
        TABLE,
        "        if top is None or half_dollars <= 2 * top:\n            break",
        "        if top is None or half_dollars < 2 * top + 100:\n            break",
    ),
    (
        "the parser accepts a table with bands missing",
        PARSER,
        "    if bands != expected_bands():",
        "    if False:",
    ),
    (
        "the parser reads past the Tax Table",
        PARSER,
        "    for line in text[:end].splitlines():",
        "    for line in text.splitlines():",
    ),
    (
        "an amount that rounds up to the ceiling keeps the unrounded schedule tax",
        SWEEP,
        "            elif rounded:",
        "            elif False:",
    ),
    (
        "the looked-up amount is truncated, not rounded",
        SWEEP,
        "            value = float(np.floor(value + 0.5)) if rounded else float(value)",
        "            value = float(np.floor(value)) if rounded else float(value)",
    ),
    (
        "the table is looked up in every year",
        SWEEP,
        '        if variant == "schedule_copy" or period.start.year != YEAR:',
        '        if variant == "schedule_copy":',
    ),
    (
        "the exact-match bound is exclusive",
        SCORER,
        "    return abs(reference - answer) <= TOLERANCE",
        "    return abs(reference - answer) < TOLERANCE",
    ),
    (
        "the exact-match bound is two dollars",
        SCORER,
        "TOLERANCE = 1.0",
        "TOLERANCE = 2.0",
    ),
    (
        "a missing answer is scored as zero",
        SCORER,
        "    if answer is None or math.isnan(answer):\n        return False",
        "    if answer is None or math.isnan(answer):\n        answer = 0.0",
    ),
    (
        "excluded outputs are scored",
        SCORER,
        "        if key not in excluded:",
        "        if True:",
    ),
    (
        "a group's weight is not split over its outputs",
        SCORER,
        "        key: weights[group] / total / counts[(key[0], group)]",
        "        key: weights[group] / total",
    ),
    (
        "a household's weights are not scaled to one",
        SCORER,
        "        key: weight / sums[key[0]] for key, weight in raw.items() if sums[key[0]] > 0",
        "        key: weight for key, weight in raw.items() if sums[key[0]] > 0",
    ),
    (
        "flags are scored as amounts",
        SCORER,
        '    return group.endswith("_eligible")',
        "    return False",
    ),
    (
        "an answer that is not 0 or 1 counts as eligible",
        SCORER,
        "    return None\n\n\ndef exact(",
        "    return 1\n\n\ndef exact(",
    ),
    (
        "the second accepted value is ignored",
        SCORER,
        "            if not hit and also_accept and key in also_accept:",
        "            if False:",
    ),
    (
        "the second accepted value replaces the reference",
        SCORER,
        "            hit = exact(group_of[key], reference[key], answer)\n"
        "            if not hit and also_accept and key in also_accept:",
        "            hit = False\n            if also_accept and key in also_accept:",
    ),
    (
        "a person's outputs are not grouped",
        SCORER,
        '                return f"person_{suffix}"',
        "                return variable",
    ),
    (
        "the shorter person suffix is matched first",
        SCORER,
        "        key=len,\n        reverse=True,",
        "        key=len,\n        reverse=False,",
    ),
    (
        "a model's rate is a sum over households",
        SCORER,
        "        out[model] = 100 * math.fsum(scores.values()) / len(households)",
        "        out[model] = 100 * math.fsum(scores.values())",
    ),
]


def run_tests() -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="pb-tax-table-mutants-") as scratch:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                TESTS,
                "-x",
                "-q",
                "--no-header",
                "-p",
                "no:cacheprovider",
                "--deselect",
                MANIFEST_TEST,
                "--basetemp",
                f"{scratch}/tmp",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": os.environ["PATH"],
                "HOME": os.environ.get("HOME", ""),
                "HYPOTHESIS_STORAGE_DIRECTORY": f"{scratch}/hypothesis",
            },
        )
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    tail = lines[-1].strip("= ") if lines else result.stderr.strip()[-200:]
    return result.returncode, tail


def saved_copy(path: Path) -> Path:
    return path.with_name(path.name + SAVED)


def restore_interrupted_runs() -> list[str]:
    """Put back any script an earlier, killed run left broken."""
    restored = []
    for name in sorted({name for _, name, _, _ in MUTANTS}):
        path = ROOT / name
        saved = saved_copy(path)
        if saved.exists():
            path.write_text(saved.read_text())
            saved.unlink()
            restored.append(name)
    return restored


def stop(signum, frame):
    raise SystemExit(f"stopped by signal {signum}")


def main() -> int:
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, stop)
    for name in restore_interrupted_runs():
        print(f"restored {name} from a run that did not finish")
    status, tail = run_tests()
    if status != 0:
        raise SystemExit(f"the unmodified tests do not pass ({tail}); nothing to mutate")
    lines = [
        "Each line breaks scripts/tax_table.py, scripts/parse_irs_tax_table.py,",
        "scripts/sweep_tax_table.py's look-up or scripts/independent_scorer.py one way",
        f"and runs {TESTS} (-x),",
        "without the manifest test, which would fail on any edit.",
        "scripts/mutants_tax_table.py holds each break's exact text. A mutant is",
        "killed only when pytest ran and a test failed (exit status 1).",
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
        saved = saved_copy(path)
        saved.write_text(original)
        try:
            path.write_text(original.replace(old, new))
            status, tail = run_tests()
        finally:
            path.write_text(original)
            saved.unlink()
        outcome = {0: "SURVIVED", 1: "killed"}.get(status, "ERROR")
        counts[outcome] += 1
        short = name.rsplit("/", 1)[-1]
        lines.append(f"{number:2d}. {outcome:8s}  {what} [{short}]: {tail}")
    lines.append("")
    lines.append(
        f"{counts['killed']} of {len(MUTANTS)} mutants killed, "
        f"{counts['SURVIVED']} survived, {counts['ERROR']} errored"
    )
    text = "\n".join(lines) + "\n"
    (HERE / "verification" / "mutants_tax_table.txt").write_text(text)
    print(text, end="")
    return 1 if counts["SURVIVED"] or counts["ERROR"] else 0


if __name__ == "__main__":
    sys.exit(main())
