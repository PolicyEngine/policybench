"""Record when the 2026-10-09 reference sweep began and check the newest
policyengine-us release before publishing, as reference_audit/2026-09-28 did
for the 2026-09-29 move (verification/sweep_timing.json there).

The standing rule (build_references_upgrade.py's ENGINE_RULE): references
come from the newest policyengine-us release when PolicyBench begins the
reference sweep, and at publication PolicyBench checks that the newest
release gives the same values.

Two steps, each writing into this audit's verification/ directory:

  sweep_timing.py sweep --engine 2.39.0 --venv <venv> --first-output <csv>
      Reads PyPI's JSON API now and records each release's wheel upload time
      from the reference engine onward, the newest release at the read, when
      the engine was installed (the dist-info directory's birth time) and
      when the sweep wrote its first output (the file's birth time). Refuses
      unless the engine was the newest release when the sweep began: no
      release newer than it was uploaded before its first output.

  sweep_timing.py check --computed <reference computed.csv>
                        --exclusions <the build's reference_exclusions.json>
                        --check-computed <computed.csv on the newest release>
                        --check-venv <venv>
      Reads PyPI again. When a newer release is out, compares every output the
      newest release computes under the same conventions with the reference
      engine's (publication_check_<version>.csv) and records the result,
      counting scored and excluded outputs apart; when the reference engine is
      still the newest, records that.

Times are UTC. Birth times are macOS st_birthtime.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import math
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AUDIT = Path(__file__).resolve().parents[1]
VERIFICATION = AUDIT / "verification"
TIMING = VERIFICATION / "sweep_timing.json"
PYPI = "https://pypi.org/pypi/policyengine-us/json"
PACKAGE = "policyengine_us"
SAME = 1e-9
NOTE = (
    "When PolicyBench began sweeping the references for the 2026-10-09 move, "
    "which policyengine-us release was the newest then and at publication, and "
    "the publication check. Times are UTC. The PyPI upload times were read from "
    "the PyPI JSON API; the install and first-output times are filesystem birth "
    "times (st_birthtime) of the engine's dist-info directory and of the first "
    "file the sweep wrote."
)


class Refusal(SystemExit):
    pass


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def utc(timestamp: float) -> str:
    return (
        datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def now_utc() -> str:
    return utc(datetime.datetime.now(datetime.timezone.utc).timestamp())


def wheel_uploads(pypi: dict) -> dict[str, str]:
    """Each plain X.Y.Z release's wheel upload time (ISO 8601, UTC)."""
    uploads = {}
    for version, files in pypi.get("releases", {}).items():
        try:
            version_key(version)
        except ValueError:
            continue  # pre-releases and other non-numeric tags
        wheels = [f for f in files if f.get("packagetype") == "bdist_wheel"]
        if wheels and not all(f.get("yanked") for f in wheels):
            uploads[version] = min(f["upload_time_iso_8601"] for f in wheels)
    return uploads


def newest(uploads: dict[str, str]) -> str:
    return max(uploads, key=version_key)


def from_engine(uploads: dict[str, str], engine: str) -> dict[str, str]:
    """The upload times of the engine and every release after it."""
    return {
        v: uploads[v]
        for v in sorted(uploads, key=version_key)
        if version_key(v) >= version_key(engine)
    }


def newer_before(uploads: dict[str, str], engine: str, moment: str) -> list[str]:
    """Releases newer than the engine uploaded before a moment."""
    return sorted(
        (
            v
            for v, at in uploads.items()
            if version_key(v) > version_key(engine) and at[:19] < moment[:19]
        ),
        key=version_key,
    )


def read_pypi(url: str = PYPI) -> dict:
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def dist_info(venv: Path, engine: str) -> Path:
    found = sorted(venv.glob(f"lib/python*/site-packages/{PACKAGE}-{engine}.dist-info"))
    if len(found) != 1:
        raise Refusal(f"{venv} has no single {PACKAGE}-{engine}.dist-info")
    return found[0]


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def read_computed(path: Path) -> dict[tuple[str, str], tuple[str, float]]:
    with path.open(newline="") as source:
        return {
            (row["scenario_id"], row["variable"]): (
                row["state"],
                float(row["recomputed"]),
            )
            for row in csv.DictReader(source)
        }


def compare(
    reference: dict[tuple[str, str], tuple[str, float]],
    check: dict[tuple[str, str], tuple[str, float]],
    reference_engine: str,
    check_engine: str,
    excluded: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[list[dict], dict]:
    """Every output on both engines, and whether the values are the same.
    ``excluded`` names the outputs the release does not score: a newer release
    that fixes a defect behind one moves its value without touching a scored
    reference, so the summary counts scored and excluded outputs apart."""
    if set(reference) != set(check):
        raise Refusal(
            "the two sweeps cover different outputs: "
            f"{sorted(set(reference) ^ set(check))[:5]}"
        )
    rows = []
    for key in sorted(reference):
        state, before = reference[key]
        after = check[key][1]
        if not (math.isfinite(before) and math.isfinite(after)):
            raise Refusal(f"{key}: a non-finite value ({before!r}, {after!r})")
        delta = after - before
        rows.append(
            {
                "scenario_id": key[0],
                "state": state,
                "variable": key[1],
                "reference_engine": reference_engine,
                "engine": check_engine,
                "reference_value": repr(before),
                "value": repr(after),
                "delta": repr(delta),
                "same": abs(delta) <= SAME,
                "scored": key not in excluded,
            }
        )
    unknown = sorted(excluded - set(reference))
    if unknown:
        raise Refusal(f"excluded outputs the sweeps do not cover: {unknown[:5]}")
    differ = [r for r in rows if not r["same"]]
    scored = [r for r in rows if r["scored"]]

    def names(found: list[dict]) -> list[str]:
        return [f"{r['scenario_id']}|{r['variable']}" for r in found]

    return rows, {
        "outputs": len(rows),
        "same": len(rows) - len(differ),
        "differ": names(differ),
        "scored_outputs": len(scored),
        "scored_same": sum(r["same"] for r in scored),
        "scored_differ": names([r for r in differ if r["scored"]]),
        "excluded_differ": names([r for r in differ if not r["scored"]]),
        "max_abs_delta": max((abs(float(r["delta"])) for r in rows), default=0.0),
    }


def write_rows(path: Path, rows: list[dict]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sweep(args) -> dict:
    engine = args.engine
    first = Path(args.first_output)
    installed = dist_info(Path(args.venv), engine)
    first_at = utc(first.stat().st_birthtime)
    pypi = read_pypi()
    read_at = now_utc()
    uploads = wheel_uploads(pypi)
    if engine not in uploads:
        raise Refusal(f"PyPI lists no wheel for policyengine-us {engine}")
    earlier = newer_before(uploads, engine, first_at)
    if earlier:
        raise Refusal(
            f"policyengine-us {earlier} was uploaded before the sweep's first "
            f"output ({first_at}), so {engine} was not the newest release when "
            "the sweep began"
        )
    return {
        "note": NOTE,
        "pypi": {
            "source": PYPI,
            "read_at_utc": read_at,
            "newest_at_read": newest(uploads),
            "wheel_uploaded_at_utc": from_engine(uploads, engine),
        },
        "reference_sweep": {
            "engine": engine,
            "engine_installed_at_utc": utc(installed.stat().st_birthtime),
            "engine_installed_evidence": relative(installed),
            "script": (
                "reference_audit/2026-10-09-engine-upgrade/scripts/"
                "build_references_upgrade.py (first pass, empty actions)"
            ),
            "first_output_at_utc": first_at,
            "first_output": relative(first),
        },
    }


def check(args) -> dict:
    timing = json.loads(TIMING.read_text())
    engine = timing["reference_sweep"]["engine"]
    pypi = read_pypi()
    read_at = now_utc()
    uploads = wheel_uploads(pypi)
    latest = newest(uploads)
    timing["pypi"] = {
        "source": PYPI,
        "read_at_utc": read_at,
        "newest_at_read": latest,
        "wheel_uploaded_at_utc": from_engine(uploads, engine),
    }
    if latest == engine:
        timing["publication_check"] = {
            "engine": engine,
            "result": (
                f"policyengine-us {engine}, the reference engine, was still the "
                "newest release when PolicyBench read PyPI"
            ),
        }
        return timing
    if not args.check_computed or not args.check_venv:
        raise Refusal(
            f"policyengine-us {latest} is newer than the reference engine {engine}: "
            "pass --check-computed and --check-venv from a sweep on it"
        )
    check_path = Path(args.check_computed)
    installed = dist_info(Path(args.check_venv), latest)
    record = json.loads(Path(args.exclusions).read_text())["exclusions"]
    excluded = frozenset((e["scenario_id"], e["variable"]) for e in record)
    rows, summary = compare(
        read_computed(Path(args.computed)),
        read_computed(check_path),
        engine,
        latest,
        excluded,
    )
    out = VERIFICATION / f"publication_check_{latest.replace('.', '_')}.csv"
    digest = write_rows(out, rows)
    timing["publication_check"] = {
        "engine": latest,
        "engine_installed_at_utc": utc(installed.stat().st_birthtime),
        "engine_installed_evidence": relative(installed),
        "output_at_utc": utc(check_path.stat().st_birthtime),
        "output": relative(out),
        "output_sha256": digest,
        **summary,
    }
    return timing


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="step", required=True)
    s = sub.add_parser("sweep")
    s.add_argument("--engine", required=True)
    s.add_argument("--venv", required=True)
    s.add_argument("--first-output", required=True)
    c = sub.add_parser("check")
    c.add_argument("--computed", required=True)
    c.add_argument("--exclusions", required=True)
    c.add_argument("--check-computed")
    c.add_argument("--check-venv")
    args = parser.parse_args(argv)
    timing = sweep(args) if args.step == "sweep" else check(args)
    VERIFICATION.mkdir(parents=True, exist_ok=True)
    TIMING.write_text(json.dumps(timing, indent=2) + "\n")
    print(
        json.dumps(timing.get("publication_check", timing["reference_sweep"]), indent=1)
    )


if __name__ == "__main__":
    sys.exit(main())
