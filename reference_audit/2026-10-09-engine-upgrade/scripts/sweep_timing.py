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

  sweep_timing.py run --venv <venv> --engine X.Y.Z --receipt <json> -- <builder args>
      Runs the builder for the reference build through the same engine check,
      in the same single process, as the check sweep (ENGINE_RUNNER); the
      receipt records the check.

  sweep_timing.py check --build <the reference build's out-dir>
                        [--check-venv <venv with the newest release>]
      Reads PyPI again. The build must be the release's: its sidecar names the
      sweep's engine, pins its CSV and names the committed builder, its
      reference CSV, sidecar and exclusion record are the committed snapshot's
      byte for byte, and its computed.csv gives every scored reference, every
      value finite. When a newer release is out, check runs the check sweep
      itself: this audit's builder, a first pass with empty actions, in the
      given venv, which the builder refuses unless it holds that release. It
      compares every output that sweep computes with the reference engine's
      (publication_check_<version>.csv) and records the result, counting
      scored and excluded outputs apart; when the reference engine is still
      the newest, it records that. Each input is pinned in the record by
      sha256. Exits non-zero, after writing the record, when the newest
      release moves a scored output: that stops the publish.

A release whose wheels are all yanked is not one PolicyBench builds on or
checks against; the record lists any such release newer than the reference
engine (yanked_newer), so one yanked after the sweep began stays visible.

Times are UTC. Birth times are macOS st_birthtime.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AUDIT = Path(__file__).resolve().parents[1]
VERIFICATION = AUDIT / "verification"
TIMING = VERIFICATION / "sweep_timing.json"
PYPI = "https://pypi.org/pypi/policyengine-us/json"
PACKAGE = "policyengine_us"
SAME = 1e-9
# The builder's own tolerance for an output it did not move (its EPS): every
# scored reference is the engine's value, so the build's computed.csv gives it.
REFERENCE_EPS = 1e-6
RUN = "us_full_run_20260612_policyengine_4_16_1_populace"
SNAPSHOT = ROOT / "paper/snapshot/20260501/runs" / RUN
BUILDER = AUDIT / "scripts" / "build_references_upgrade.py"
SPEC = ROOT / "docs/haiku55/spec.json"
# The builder's arguments that name files or directories, and its flag.
BUILDER_PATH_FLAGS = (
    "--actions",
    "--out-dir",
    "--fixes-dir",
    "--computed-csv",
    "--evidence-request",
    "--evidence-out",
)
BUILDER_VALUE_FLAGS = (*BUILDER_PATH_FLAGS, "--regenerated-at")
BUILDER_SWITCHES = ("--allow-draft",)


def builder_arguments(argv: list[str]) -> tuple[list[str], Path | None]:
    """The builder's arguments as the builder itself reads them (the same
    flags, argparse's equals form, abbreviations and last-occurrence rule),
    rewritten in one canonical form with every path resolved here (the child
    runs in the repository root), and the computed.csv the run must write:
    --computed-csv when given, else <out-dir>/computed.csv. Unknown arguments
    are refused rather than passed on."""
    parser = argparse.ArgumentParser(prog="builder", add_help=False)
    for flag in BUILDER_VALUE_FLAGS:
        parser.add_argument(flag)
    for flag in BUILDER_SWITCHES:
        parser.add_argument(flag, action="store_true")
    try:
        parsed = parser.parse_args(argv)
    except SystemExit:
        raise Refusal(f"the builder cannot take these arguments: {argv}") from None
    canonical: list[str] = []
    values = vars(parsed)
    for flag in BUILDER_VALUE_FLAGS:
        value = values[flag[2:].replace("-", "_")]
        if value is None:
            continue
        if flag in BUILDER_PATH_FLAGS:
            value = str(Path(value).resolve())
        canonical += [flag, value]
    canonical += [
        flag for flag in BUILDER_SWITCHES if values[flag[2:].replace("-", "_")]
    ]
    computed = values["computed_csv"] or (
        str(Path(values["out_dir"]) / "computed.csv") if values["out_dir"] else None
    )
    return canonical, Path(computed).resolve() if computed else None


BASE_ENGINE = "policyengine-us 2.15.17"
BUILD_FILES = (
    "computed.csv",
    "reference_outputs.csv",
    "reference_outputs.csv.meta.json",
    "reference_exclusions.json",
)
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


def yanked_newer(pypi: dict, engine: str) -> dict[str, str]:
    """Releases newer than the engine whose wheels are all yanked, with the
    reason PyPI gives (wheel_uploads leaves them out)."""
    yanked = {}
    for version, files in pypi.get("releases", {}).items():
        try:
            key = version_key(version)
        except ValueError:
            continue
        wheels = [f for f in files if f.get("packagetype") == "bdist_wheel"]
        if (
            key > version_key(engine)
            and wheels
            and all(f.get("yanked") for f in wheels)
        ):
            yanked[version] = wheels[0].get("yanked_reason") or ""
    return dict(sorted(yanked.items(), key=lambda kv: version_key(kv[0])))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    first = Path(args.first_output).resolve()
    venv = Path(args.venv).resolve()
    installed = dist_info(venv, engine)
    install = engine_install(venv, engine)
    first_at = utc(first.stat().st_birthtime)
    pypi = read_pypi()
    read_at = now_utc()
    uploads = wheel_uploads(pypi)
    if engine not in uploads:
        raise Refusal(f"PyPI lists no wheel for policyengine-us {engine}")
    installed_at = utc(installed.stat().st_birthtime)
    sweep_order_problems(uploads[engine], installed_at, first_at, engine)
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
            "yanked_newer": yanked_newer(pypi, engine),
        },
        "reference_sweep": {
            "engine": engine,
            "engine_installed_at_utc": installed_at,
            "engine_installed_evidence": relative(installed),
            "engine_install": install,
            "script": (
                "reference_audit/2026-10-09-engine-upgrade/scripts/"
                "build_references_upgrade.py (first pass, empty actions)"
            ),
            "first_output_at_utc": first_at,
            "first_output": relative(first),
            "first_output_sha256": sha256(first),
        },
    }


def sweep_order_problems(
    uploaded_at: str, installed_at: str, output_at: str, engine: str
) -> None:
    """A sweep's output follows its engine: the wheel was on PyPI before it was
    installed, and installed before the sweep wrote its output. An older file
    (an earlier rehearsal's output, say) would otherwise backdate the sweep."""
    if not uploaded_at[:19] <= installed_at[:19] <= output_at[:19]:
        raise Refusal(
            f"policyengine-us {engine}: wheel uploaded {uploaded_at}, installed "
            f"{installed_at}, output written {output_at}; an output must follow "
            "its engine's install, and the install its upload"
        )


def build_problems(
    build: Path, engine: str, snapshot: Path
) -> tuple[dict, frozenset[tuple[str, str]], dict[str, str]]:
    """The reference build's computed values, its excluded outputs and the
    sha256 of each build file, once the build is shown to be the release's."""
    files = {name: build / name for name in BUILD_FILES}
    missing = [name for name, path in files.items() if not path.is_file()]
    if missing:
        raise Refusal(f"{build} lacks {missing}")
    pins = {name: sha256(path) for name, path in files.items()}
    meta = json.loads(files["reference_outputs.csv.meta.json"].read_text())
    revision = meta["revisions"][-1]
    if (
        revision.get("kind") != "engine_upgrade"
        or revision.get("engine_version") != f"policyengine-us {engine}"
    ):
        raise Refusal(
            f"{build}'s last revision is not an engine upgrade to {engine}: "
            f"{revision.get('kind')} {revision.get('engine_version')}"
        )
    if meta.get("reference_csv_sha256") != pins["reference_outputs.csv"]:
        raise Refusal(f"{build}'s sidecar does not pin its reference_outputs.csv")
    # The check sweep runs this audit's builder, as the build did: the same
    # conventions and adapter, so the sidecar must name the committed builder.
    named = (revision.get("provenance") or {}).get("builder_sha256")
    if named != sha256(BUILDER):
        raise Refusal(
            f"{build}'s sidecar names builder {named!r}, not the committed one"
        )
    pins["builder"] = named
    for name in (
        "reference_outputs.csv",
        "reference_outputs.csv.meta.json",
        "reference_exclusions.json",
    ):
        committed = snapshot / name
        if not committed.is_file() or sha256(committed) != pins[name]:
            raise Refusal(
                f"{build}/{name} is not the committed snapshot's ({committed}); "
                "check the build the release froze"
            )
    record = json.loads(files["reference_exclusions.json"].read_text())["exclusions"]
    excluded = frozenset((e["scenario_id"], e["variable"]) for e in record)
    with files["reference_outputs.csv"].open(newline="") as source:
        references = {
            (row["scenario_id"], row["variable"]): float(row["value"])
            for row in csv.DictReader(source)
        }
    computed = read_computed(files["computed.csv"])
    nonfinite = sorted(
        key
        for key in set(references) | set(computed)
        if not math.isfinite(references.get(key, 0.0))
        or not math.isfinite(computed.get(key, ("", 0.0))[1])
    )
    if nonfinite:
        raise Refusal(f"{build} holds non-finite values: {nonfinite[:5]}")
    if set(computed) != set(references) or not excluded <= set(references):
        raise Refusal(
            f"{build}'s computed.csv, references and record cover different outputs"
        )
    off = sorted(
        key
        for key, value in references.items()
        if key not in excluded and abs(computed[key][1] - value) > REFERENCE_EPS
    )
    if off:
        raise Refusal(f"{build}'s computed.csv is not its scored references: {off[:5]}")
    return computed, excluded, pins


# The engine check and, when a builder is named, the builder itself, in ONE
# process under the venv's interpreter, so what is checked is what computes.
# Launched with -P (no script or working directory on sys.path) and a fresh,
# empty bytecode-cache prefix, so no __pycache__ beside the sources is read:
# every module compiles from the verified source. Before policyengine_us is
# imported, it requires the expected version, an import origin inside the
# installed package, no editable install, every package file at the hash the
# wheel's RECORD gives (sha256, sha384 or sha512), and no importable file in the
# package (a module, a sourceless .pyc, a native extension) that RECORD does not
# list. It writes what it found to PB_ENGINE_RECEIPT, then runs the builder with
# the remaining arguments, or stops (exit 3) on any problem.
ENGINE_RUNNER = r"""
import base64, hashlib, importlib.machinery as mach, importlib.metadata as md
import importlib.util, json, os, pathlib, runpy, sys
expected = os.environ["PB_EXPECTED_ENGINE"]
dist = md.distribution("policyengine-us")
spec = importlib.util.find_spec("policyengine_us")
origin = pathlib.Path(spec.origin).resolve()
site = pathlib.Path(dist.locate_file("")).resolve()
package = (site / "policyengine_us").resolve()
direct = dist.read_text("direct_url.json")
editable = bool(direct and json.loads(direct).get("dir_info", {}).get("editable"))
recorded, mismatched = set(), []
for entry in dist.files or []:
    name = str(entry)
    if not name.startswith("policyengine_us/") or "__pycache__" in name:
        continue
    recorded.add(name)
    if not entry.hash or entry.hash.mode not in ("sha256", "sha384", "sha512"):
        mismatched.append(name)
        continue
    path = pathlib.Path(dist.locate_file(entry))
    data = path.read_bytes() if path.is_file() else None
    digest = hashlib.new(entry.hash.mode, data).digest() if data is not None else b""
    if base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != entry.hash.value:
        mismatched.append(name)
# No symlink anywhere in the package (a linked directory hides its files from
# the scan, and a linked file leaves the package): installs must be copies.
links = sorted(
    str(pathlib.Path(root, name).relative_to(site))
    for root, dirs, files in os.walk(package)
    for name in dirs + files
    if os.path.islink(os.path.join(root, name))
)
if os.path.islink(site / "policyengine_us"):
    links.insert(0, "policyengine_us")
suffixes = tuple(mach.all_suffixes())
unrecorded = sorted(
    str(p.relative_to(site))
    for p in package.rglob("*")
    if p.is_file() and "__pycache__" not in p.parts and p.name.endswith(suffixes)
    and str(p.relative_to(site)) not in recorded
)
found = {
    "version": dist.version,
    "origin": str(origin),
    "imported_from_package": origin.is_relative_to(package),
    "editable": editable,
    "files_verified": len(recorded) - len(mismatched),
    "files_mismatched": mismatched[:5],
    "files_unrecorded": unrecorded[:5],
    "symlinks": links[:5],
    "pycache_prefix": sys.pycache_prefix,
    "sys_path": sys.path,
}
problems = []
if found["version"] != expected:
    problems.append(f"version {found['version']}, not {expected}")
if not found["imported_from_package"]:
    problems.append(f"imports policyengine_us from {found['origin']}")
if editable:
    problems.append("an editable install")
if mismatched or not found["files_verified"]:
    problems.append(f"files unlike the wheel's RECORD {mismatched[:5]}")
if unrecorded:
    problems.append(f"importable files the wheel lacks {unrecorded[:5]}")
if links:
    problems.append(f"symlinks in the package (installs must be copies) {links[:5]}")
if not sys.pycache_prefix or any(pathlib.Path(sys.pycache_prefix).iterdir()):
    problems.append("no fresh bytecode-cache prefix")
found["problems"] = problems
pathlib.Path(os.environ["PB_ENGINE_RECEIPT"]).write_text(json.dumps(found))
if problems:
    sys.exit(3)
if len(sys.argv) > 1:
    sys.argv = sys.argv[1:]
    runpy.run_path(sys.argv[0], run_name="__main__")
"""


def sweep_env() -> dict[str, str]:
    """The environment a sweep runs in: no inherited Python overrides."""
    return {
        **{k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG")},
        "PYTHONPATH": str(ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }


def run_on_engine(
    venv: Path, engine: str, receipt: Path, builder_args: list[str] | None = None
):
    """ENGINE_RUNNER under the venv's interpreter: the engine check, then (with
    ``builder_args``) the builder in the same process. Returns the completed
    process and the check's record; refuses when the check found a problem."""
    receipt = receipt.resolve()
    if receipt.exists():
        raise Refusal(f"{receipt} exists: each run writes a fresh receipt")
    cache = Path(tempfile.mkdtemp(prefix="pb-pycache-"))
    command = [str(venv / "bin" / "python"), "-P", "-c", ENGINE_RUNNER]
    if builder_args is not None:
        command += [str(BUILDER), *builder_args]
    env = {
        **sweep_env(),
        "PYTHONPYCACHEPREFIX": str(cache),
        "PB_EXPECTED_ENGINE": engine,
        "PB_ENGINE_RECEIPT": str(receipt),
    }
    try:
        ran = subprocess.run(command, env=env, cwd=ROOT, capture_output=True, text=True)
    finally:
        shutil.rmtree(cache, ignore_errors=True)
    if not receipt.is_file():
        raise Refusal(
            f"{venv}: the engine check did not run ({ran.stderr.strip()[-300:]})"
        )
    found = json.loads(receipt.read_text())
    if found["problems"]:
        raise Refusal(
            f"{venv} is not policyengine-us {engine} as released: {found['problems']}"
        )
    return ran, {
        "version": found["version"],
        "files_verified": found["files_verified"],
        "editable": False,
        "imported_from_package": True,
        "fresh_bytecode_cache": True,
    }


def engine_install(venv: Path, engine: str) -> dict:
    """The engine check alone (ENGINE_RUNNER without a builder)."""
    with tempfile.TemporaryDirectory() as scratch:
        _, install = run_on_engine(venv, engine, Path(scratch) / "receipt.json")
    return install


def run_check_sweep(venv: Path, engine: str, out_dir: Path) -> tuple[Path, dict]:
    """The check sweep, run here: this audit's builder, a first pass with
    empty actions naming ``engine``, in the same process as the engine check
    (run_on_engine), under the venv's interpreter. The builder also refuses
    before computing unless the venv holds that release, and it pins the
    conventions and harness it applies, so the computed.csv it writes is that
    engine's under the release's conventions. Returns the file and what ran."""
    out_dir.mkdir(parents=True, exist_ok=False)
    actions = out_dir / "actions.empty.json"
    actions.write_text(
        json.dumps(
            {
                "engine": f"policyengine-us {engine}",
                "previous_engine": BASE_ENGINE,
                "date": now_utc()[:10],
                "release_spec_sha256": sha256(SPEC),
                "draft": True,
            }
        )
    )
    args = ["--actions", str(actions), "--out-dir", str(out_dir), "--allow-draft"]
    ran, install = run_on_engine(venv, engine, out_dir / "engine_install.json", args)
    (out_dir / "sweep.log").write_text(ran.stdout + ran.stderr)
    computed = out_dir / "computed.csv"
    if not computed.is_file():
        raise Refusal(
            f"the check sweep on {engine} wrote no computed.csv "
            f"(exit {ran.returncode}; see {out_dir / 'sweep.log'})"
        )
    return computed, {
        "builder_sha256": sha256(BUILDER),
        "venv": relative(venv),
        "command": "build_references_upgrade.py --actions <empty> --allow-draft",
        "exit_code": ran.returncode,
        "engine_install": install,
    }


def check(args) -> dict:
    timing = json.loads(TIMING.read_text())
    engine = timing["reference_sweep"]["engine"]
    build = Path(args.build)
    computed, excluded, pins = build_problems(
        build, engine, Path(getattr(args, "snapshot", None) or SNAPSHOT)
    )
    scored = len(computed) - len(excluded)
    pypi = read_pypi()
    read_at = now_utc()
    uploads = wheel_uploads(pypi)
    latest = newest(uploads)
    timing["pypi"] = {
        "source": PYPI,
        "read_at_utc": read_at,
        "newest_at_read": latest,
        "wheel_uploaded_at_utc": from_engine(uploads, engine),
        "yanked_newer": yanked_newer(pypi, engine),
    }
    inputs = {
        "build": relative(build),
        "build_sha256": pins,
        "scored_outputs": scored,
    }
    if latest == engine:
        timing["publication_check"] = {
            "engine": engine,
            "result": (
                f"policyengine-us {engine}, the reference engine, was still the "
                "newest release when PolicyBench read PyPI"
            ),
            **inputs,
        }
        return timing
    if not args.check_venv:
        raise Refusal(
            f"policyengine-us {latest} is newer than the reference engine {engine}: "
            "pass --check-venv, a venv holding it, and check runs the sweep"
        )
    venv = Path(args.check_venv).resolve()
    installed = dist_info(venv, latest)
    engine_install(venv, latest)  # fail fast; the sweep's own process checks again
    installed_at = utc(installed.stat().st_birthtime)
    scratch = ROOT / "results/local"
    scratch.mkdir(parents=True, exist_ok=True)
    work = (
        Path(
            getattr(args, "work_dir", None)
            or tempfile.mkdtemp(prefix=f"check-sweep-{latest}-", dir=scratch)
        ).resolve()
        / "sweep"
    )
    check_path, receipt = run_check_sweep(venv, latest, work)
    output_at = utc(check_path.stat().st_birthtime)
    sweep_order_problems(uploads[latest], installed_at, output_at, latest)
    rows, summary = compare(
        computed, read_computed(check_path), engine, latest, excluded
    )
    if summary["scored_outputs"] != scored:
        raise Refusal(
            f"the check scored {summary['scored_outputs']} outputs, not {scored}"
        )
    out = VERIFICATION / f"publication_check_{latest.replace('.', '_')}.csv"
    digest = write_rows(out, rows)
    timing["publication_check"] = {
        "engine": latest,
        "engine_installed_at_utc": installed_at,
        "engine_installed_evidence": relative(installed),
        "check_computed": relative(check_path),
        "check_computed_sha256": sha256(check_path),
        "check_sweep": receipt,
        "output_at_utc": output_at,
        "output": relative(out),
        "output_sha256": digest,
        **inputs,
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
    c.add_argument("--build", required=True)
    c.add_argument("--check-venv")
    r = sub.add_parser("run")
    r.add_argument("--venv", required=True)
    r.add_argument("--engine", required=True)
    r.add_argument("--receipt", required=True)
    r.add_argument("builder_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.step == "run":
        # The reference build itself, through the same engine check and the
        # same single process as the check sweep (run_on_engine).
        raw = list(args.builder_args)
        if raw[:1] == ["--"]:
            raw = raw[1:]
        builder_args, computed = builder_arguments(raw)
        if computed is not None and computed.exists():
            raise Refusal(f"{computed} exists: each run writes into a fresh out-dir")
        started = time.time()
        ran, install = run_on_engine(
            Path(args.venv).resolve(), args.engine, Path(args.receipt), builder_args
        )
        if computed is not None and (
            not computed.is_file() or computed.stat().st_birthtime < started - 1
        ):
            raise Refusal(
                f"the build on {args.engine} wrote no new {computed} "
                f"(exit {ran.returncode})"
            )
        sys.stdout.write(ran.stdout)
        sys.stderr.write(ran.stderr)
        print(json.dumps({"engine_install": install}), file=sys.stderr)
        raise SystemExit(ran.returncode)
    timing = sweep(args) if args.step == "sweep" else check(args)
    VERIFICATION.mkdir(parents=True, exist_ok=True)
    TIMING.write_text(json.dumps(timing, indent=2) + "\n")
    print(
        json.dumps(timing.get("publication_check", timing["reference_sweep"]), indent=1)
    )
    moved = timing.get("publication_check", {}).get("scored_differ")
    if moved:
        raise Refusal(
            f"policyengine-us {timing['publication_check']['engine']} moves scored "
            f"outputs {moved[:5]}: do not publish (the record is in "
            f"{relative(TIMING)})"
        )


if __name__ == "__main__":
    sys.exit(main())
