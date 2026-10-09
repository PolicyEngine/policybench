"""Rebuild PolicyBench's US references on a newer policyengine-us (the second
engine upgrade, after release dashboard-data-20261006).

Generalized from reference_audit/2026-09-28/scripts/build_references_latest.py,
which moved the references from policyengine-us 1.755.4 to 2.15.17 (PR #182).

Rulings:
- Max, 2026-09-28: "we should be using the latest pe for this always!"
- Max, 2026-10-09, on the release that adds Claude Haiku 5.5: "yes i want to wait
  for hte fixed engine". The references move from 2.15.17 to the newer release
  that fixes engine defects behind PolicyBench's exclusions; a cell the new
  engine fixes is regenerated and its exclusion record removed (the #178
  precedent, cb312fd7).
- d1022 and d994 (docs/haiku55/spec.json): the release's ten ruled exclusions.
  The household-scope cells (scenario_123, scenario_093, federal and state) and
  the Louisiana cells (scenario_051, scenario_077) stay excluded; the four
  engine-defect cells (AZ 018, OH 025, CO 043, NY 082) are regenerated once the
  engine lands on their audited corrected values.
- Rule 5: an excluded output keeps the value it was decided on; an excluded
  output that moves gets an excluded_rechecked entry.

Base (read from git, never from the checkout, whose snapshot holds whatever was
last installed): release 20261006 at BASE_COMMIT, i.e. 2.15.17 references and the
64-record exclusion record, each file pinned by sha256. The release's ten ruled
records come from scripts/finish_haiku55.py's build_release_exclusions, so the
74-record release record this script edits is byte-for-byte the one the Haiku
driver installs. The original v1.1 frozen values (each change's "frozen") come
from FROZEN_COMMIT.

Method: every output is computed on the installed policyengine-us with
reference_audit/2026-09-28/fixes/latest_final.py (the pre-freeze conventions and
the Maryland local-scope adapter), imported in place from --fixes-dir, with the
households built by reference_audit/2026-09-28/scripts/sweep.py's
build_situation. Every fix module's sha256 must equal the one the 2026-09-29
engine_upgrade revision records; latest_final.py, sweep.py and the sales tax
tables (r19_irs_sales_tax_2025.json, which latest_c_irs_sales_tax_2025.py reads
from its own directory) must each equal the bytes committed at BASE_COMMIT (the
tables as reference_audit/2026-09-22/fixes holds them).

A move is a change beyond the exact-match tolerance
(policybench.paper_results.moves_beyond_tolerance: more than $1 for an amount,
any change for a 0/1 flag). A scored output takes the computed value; one that
changes by $1 or less (more than EPS) is recorded as engine_upgrade_within_1.

ACTIONS FILE (JSON; every list optional except where a move needs it):

  engine            "policyengine-us X.Y.Z"; must equal the installed release.
  previous_engine   "policyengine-us 2.15.17"; must equal the base sidecar's
                    last engine_upgrade engine_version.
  date              UTC day of the build (YYYY-MM-DD): the revision's date, the
                    derivation's, and each new record's decided_on. The sidecar's
                    regenerated_at_utc must fall on it.
  release_spec_sha256  sha256 of docs/haiku55/spec.json the actions were drafted
                    against.
  draft             true for actions_from_cells.py's output; the builder
                    refuses a draft unless --allow-draft (rehearsals only).
  review, note      free text for reviewers; ignored.
  approved          [{scenario_id, variable, value, cause, basis}]: scored
                    outputs allowed to move; the engine must give value within
                    APPROVED_TOL (half a cent).
  regenerated_exclusions  [{scenario_id, variable, alternative_value,
                    tolerance, upstream, basis}]: excluded outputs (in
                    20261006's record or the release's ruled records) whose
                    reference_engine_defect the new engine fixes. alternative_value
                    must be the record's audited corrected value; tolerance is at
                    most $1; the engine must land within it (a flag must equal
                    it); upstream must name the fix ("to be filed" does not).
                    The record is removed and the output scored at the engine
                    value.
  new_exclusions    [complete exclusion record]: scored outputs the new engine
                    moves onto an input the prompt does not state (for example
                    Indiana county). frozen_value must be the engine value
                    (within 1e-3), engine_version the new engine, decided_on the
                    date, and the alternative must differ beyond the tolerance.
  excluded_rechecked  [{scenario_id, variable, reason}]: excluded outputs that
                    move but stay excluded, keeping the decided value.
  kept_exclusions_from_release  [{scenario_id, variable}]: the release's ruled
                    outputs that stay excluded. Together with the ruled outputs
                    listed in regenerated_exclusions they must be exactly the
                    spec's ruled outputs. A kept output that moves is also
                    listed in excluded_rechecked, the one pair of lists that
                    may share an output.

The builder refuses, listing every problem with exact engine values: an
unexplained move (scored or excluded), an approved output that does not move or
lands elsewhere, a regenerated output off its target or not an engine defect, a
new exclusion on an output that does not move, a rechecked output that does not
move, an entry on an unknown output, and an output named by two actions.

It writes to --out-dir:
  reference_outputs.csv   20261006's rows byte for byte, except each changed row,
                          whose value field is rewritten.
  reference_exclusions.json  the release record (20261006's 64 + the ruled ten)
                          less the regenerated records, with the new exclusions
                          before the trailing 2026-09-29 audit record and one
                          sentence appended to the derivation naming the upgrade.
  reference_outputs.csv.meta.json  the base sidecar with the US bundle, csv
                          sha256 and regenerated_at_utc updated and a second
                          engine_upgrade revision appended; every earlier revision
                          is kept byte for byte.
  reference_traces.json   engine traces of every changed output.
  computed.csv            (also with --computed-csv, written before any refusal)
                          every output on the new engine, in sweep.py's columns.

Run (PYTHONPATH is the checkout; the fixes directory needs the sales tax tables):

  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=<checkout> \\
    <venv with policyengine-us X.Y.Z>/bin/python \\
    reference_audit/2026-10-09-engine-upgrade/scripts/build_references_upgrade.py \\
      --actions <actions.json> --out-dir <dir> [--fixes-dir <dir>] [--allow-draft]
"""

from __future__ import annotations

import argparse
import copy
import csv
import datetime
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUN = "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
# The merge of PR #202 on main, whose tree holds release 20261006.
BASE_COMMIT = "9ce4ade8382962a9134860c23f56d92509b5e57f"
BASE_SHA256 = {
    "reference_outputs.csv": (
        "e8bbba8fd3e90f78e7c0e83df06227bc1c94563e92f7405fe12be853a30b2466"
    ),
    "reference_outputs.csv.meta.json": (
        "816fef53c452d8520a321bc12bc29b28da1e7956a06818e5ec13d7fc7b371a4b"
    ),
    "reference_exclusions.json": (
        "92741dfd047298eacb79a0dadeb7e4965e3c6f986beab0341b12ff8f5b023815"
    ),
    "scenarios.csv": (
        "71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a"
    ),
}
# Re-freeze on the 24-model board (#121): the snapshot's last commit holding the
# v1.1 frozen references (policyengine-us 1.755.4), the bundle the 2026-09-29
# builder read as "frozen".
FROZEN_COMMIT = "f108a959d91567c050a99d4d1d583904b3d5a809"
FROZEN_SHA256 = "b9136a15e285f9c02ba78bee854b8a3af180e280485512642c829e8ffd7d2368"
PREVIOUS_ENGINE = "policyengine-us 2.15.17"
FIXES_REL = "reference_audit/2026-09-28/fixes"
FIXES = ROOT / FIXES_REL
HARNESS_REL = "reference_audit/2026-09-28/scripts/sweep.py"
HARNESS = ROOT / HARNESS_REL
FIX_ENTRY = "latest_final"
SALES_TAX_TABLES = "r19_irs_sales_tax_2025.json"
SALES_TAX_REL = f"reference_audit/2026-09-22/fixes/{SALES_TAX_TABLES}"
SALES_TAX_SOURCE = ROOT / SALES_TAX_REL
YEAR = 2026
EPS = 1e-6
FROZEN_TOL = 1e-3
APPROVED_TOL = 0.005
MAX_REGENERATION_TOL = 1.0
# The trailing record of 20261006's exclusion record: the 2026-09-29 audit's
# exclusion, which tests/test_reference_upgrade.py requires last.
AUDIT_TAIL = ("scenario_023", "head_medicaid_eligible")
ENGINE_DEFECT = "reference_engine_defect"
# A regeneration claims a released upstream fix and must name it.
UNNAMED_UPSTREAM = frozenset({"", "to be filed", "none", "unknown"})
ACTION_KEYS = frozenset(
    {
        "engine",
        "previous_engine",
        "date",
        "release_spec_sha256",
        "draft",
        "review",
        "note",
        "approved",
        "regenerated_exclusions",
        "new_exclusions",
        "excluded_rechecked",
        "kept_exclusions_from_release",
    }
)
RULE = (
    "A scored reference follows from the stated facts and from law published before "
    "the 2026-07-03 reference freeze."
)
ENGINE_RULE = (
    "References come from the newest policyengine-us release when PolicyBench begins "
    "the reference sweep; at publication PolicyBench checks that the newest release "
    "gives the same values."
)
UPGRADE_RULE = (
    "Max, 2026-10-09, on waiting for the release that fixes the engine defects "
    "behind PolicyBench's exclusions: 'yes i want to wait for hte fixed engine'. An "
    "excluded output whose engine defect the new release fixes, landing on its "
    "audited corrected value, is regenerated and its exclusion record removed; every "
    "other excluded output keeps the value it was decided on."
)
NUMBER_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}

Key = tuple[str, str]


class Refusal(SystemExit):
    """The builder refuses to write references."""


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def dump_record(value: dict) -> str:
    """The serialization of the sidecar and the exclusion record."""
    return json.dumps(value, indent=2) + "\n"


def words(n: int) -> str:
    return NUMBER_WORDS.get(n, str(n))


def key_of(item: dict) -> Key:
    return (str(item["scenario_id"]), str(item["variable"]))


def engine_number(engine: str) -> str:
    prefix = "policyengine-us "
    if not engine.startswith(prefix):
        raise Refusal(f"engine must read 'policyengine-us X.Y.Z', not {engine!r}")
    return engine.removeprefix(prefix)


def beyond(variable: str, before: float, after: float) -> bool:
    """A move beyond the exact-match tolerance, as the paper counts it."""
    from policybench.paper_results import moves_beyond_tolerance

    return moves_beyond_tolerance(variable, before, after)


# --- Base ------------------------------------------------------------------


def git_blob(commit: str, path: str, root: Path = ROOT) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{commit}:{path}"], capture_output=True
    )
    if result.returncode:
        raise Refusal(
            f"cannot read {path} at {commit[:12]} (fetch full history): "
            f"{result.stderr.decode().strip()}"
        )
    return result.stdout


@dataclass
class Row:
    key: Key
    fields: list[str]
    raw: str

    @property
    def value(self) -> float:
        return float(self.fields[2])


@dataclass
class ReferenceCsv:
    header_raw: str
    header: list[str]
    rows: list[Row]

    def values(self) -> dict[Key, float]:
        return {row.key: row.value for row in self.rows}


def physical_lines(text: str) -> list[str]:
    """Split on '\\n' only, each piece keeping its terminator."""
    lines = text.split("\n")
    out = [line + "\n" for line in lines[:-1]]
    if lines[-1]:
        out.append(lines[-1])
    return out


def parse_reference_csv(text: str) -> ReferenceCsv:
    """Rows with their raw text, so an unchanged row is written byte for byte."""
    lines = physical_lines(text)
    reader = csv.reader(iter(lines))
    records, used = [], 0
    for fields in reader:
        records.append((fields, "".join(lines[used : reader.line_num])))
        used = reader.line_num
    (header, header_raw), body = records[0], records[1:]
    if header[:3] != ["scenario_id", "variable", "value"]:
        raise Refusal(f"unexpected reference header {header}")
    rows = [Row((f[0], f[1]), f, raw) for f, raw in body]
    if len({row.key for row in rows}) != len(rows):
        raise Refusal("the reference CSV lists an output twice")
    return ReferenceCsv(header_raw, header, rows)


def format_row(fields: list[str]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerow(fields)
    return buffer.getvalue()


def render_reference_csv(reference: ReferenceCsv, new_values: dict[Key, float]) -> str:
    """The base CSV with each output in new_values rewritten at that value."""
    parts = [reference.header_raw]
    for row in reference.rows:
        if row.key in new_values:
            fields = list(row.fields)
            fields[2] = repr(float(new_values[row.key]))
            raw = format_row(fields)
            if not row.raw.endswith("\n"):
                raw = raw.removesuffix("\n")
            parts.append(raw)
        else:
            parts.append(row.raw)
    return "".join(parts)


@dataclass
class Base:
    reference: ReferenceCsv
    meta: dict
    exclusions: dict
    scenarios_csv: str
    frozen: dict[Key, float]


def load_base(root: Path = ROOT) -> Base:
    """Release 20261006's references at BASE_COMMIT, each file pinned."""
    blobs = {}
    for name, pin in BASE_SHA256.items():
        raw = git_blob(BASE_COMMIT, f"{RUN}/{name}", root)
        if sha256_bytes(raw) != pin:
            raise Refusal(f"{name} at {BASE_COMMIT[:12]} does not match its pin")
        blobs[name] = raw.decode()
    frozen_raw = git_blob(FROZEN_COMMIT, f"{RUN}/reference_outputs.csv", root)
    if sha256_bytes(frozen_raw) != FROZEN_SHA256:
        raise Refusal("the v1.1 frozen references do not match their pin")
    return Base(
        reference=parse_reference_csv(blobs["reference_outputs.csv"]),
        meta=json.loads(blobs["reference_outputs.csv.meta.json"]),
        exclusions=json.loads(blobs["reference_exclusions.json"]),
        scenarios_csv=blobs["scenarios.csv"],
        frozen=parse_reference_csv(frozen_raw.decode()).values(),
    )


def release_record(base_exclusions: dict) -> tuple[dict, set[Key], str]:
    """The release's 74-record exclusion record, as scripts/finish_haiku55.py
    builds it from the spec; the ruled outputs; and the spec's sha256."""
    path = ROOT / "scripts" / "finish_haiku55.py"
    spec = importlib.util.spec_from_file_location("finish_haiku55_for_upgrade", path)
    driver = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = driver
    spec.loader.exec_module(driver)
    release_spec = driver.load_spec()
    doc = driver.build_release_exclusions(copy.deepcopy(base_exclusions), release_spec)
    ruled = {driver.spec_key(r) for r in driver.spec_records(release_spec)}
    return doc, ruled, sha256(ROOT / driver.SPEC_PATH)


# --- The plan ----------------------------------------------------------------


@dataclass
class Plan:
    problems: list[str] = field(default_factory=list)
    new_values: dict[Key, float] = field(default_factory=dict)
    changed: list[dict] = field(default_factory=list)
    within: list[dict] = field(default_factory=list)
    rechecked: list[dict] = field(default_factory=list)
    regenerated: list[dict] = field(default_factory=list)
    new_records: list[dict] = field(default_factory=list)
    kept: list[Key] = field(default_factory=list)


def _entries(actions: dict, name: str) -> dict[Key, dict]:
    entries: dict[Key, dict] = {}
    for item in actions.get(name, []):
        k = key_of(item)
        if k in entries:
            raise Refusal(f"{name} lists {k} twice")
        entries[k] = item
    return entries


def validate_actions(actions: dict, *, allow_draft: bool = False) -> None:
    unknown = set(actions) - ACTION_KEYS
    if unknown:
        raise Refusal(f"unknown actions keys {sorted(unknown)}")
    for name in ("engine", "previous_engine", "date"):
        if not isinstance(actions.get(name), str) or not actions[name]:
            raise Refusal(f"actions must name {name}")
    datetime.date.fromisoformat(actions["date"])
    engine_number(actions["engine"])
    if actions.get("draft") and not allow_draft:
        raise Refusal(
            "the actions file is a draft (actions_from_cells.py output): review "
            "every judgment call and set draft to false, or pass --allow-draft "
            "for a rehearsal"
        )
    lists = (
        "approved",
        "regenerated_exclusions",
        "new_exclusions",
        "excluded_rechecked",
        "kept_exclusions_from_release",
    )
    # A kept ruled output that moves is also rechecked (rule 5): kept declares
    # it stays excluded, rechecked records its move. No other pair may share an
    # output.
    allowed = {frozenset({"excluded_rechecked", "kept_exclusions_from_release"})}
    seen: dict[Key, str] = {}
    for name in lists:
        for k in _entries(actions, name):
            if k in seen and frozenset({seen[k], name}) not in allowed:
                raise Refusal(f"{k} is in both {seen[k]} and {name}")
            seen.setdefault(k, name)


def plan_upgrade(
    base: Base,
    release: dict,
    ruled: set[Key],
    actions: dict,
    computed: dict[Key, float],
) -> Plan:
    """Decide every output's value and record; never raise on a move, collect
    every problem instead. Pure: no engine, no files."""
    plan = Plan()
    engine = actions["engine"]
    date = actions["date"]
    board = base.reference.values()
    records = {key_of(r): r for r in release["exclusions"]}
    excluded = set(records)
    base_excluded = {key_of(r) for r in base.exclusions["exclusions"]}
    if not ruled <= excluded or excluded - ruled != base_excluded:
        plan.problems.append("the release record is not 20261006's plus the ruled")
    approved = _entries(actions, "approved")
    regenerated = _entries(actions, "regenerated_exclusions")
    added = _entries(actions, "new_exclusions")
    rechecked = _entries(actions, "excluded_rechecked")
    kept = _entries(actions, "kept_exclusions_from_release")
    if set(computed) != set(board):
        missing = sorted(set(board) - set(computed))[:5]
        extra = sorted(set(computed) - set(board))[:5]
        plan.problems.append(
            f"computed outputs differ: missing {missing} extra {extra}"
        )
    for name, entries in (
        ("approved", approved),
        ("regenerated_exclusions", regenerated),
        ("new_exclusions", added),
        ("excluded_rechecked", rechecked),
        ("kept_exclusions_from_release", kept),
    ):
        for k in entries:
            if k not in board:
                plan.problems.append(f"{name} names {k}, which is not a reference")
    if actions["previous_engine"] != PREVIOUS_ENGINE:
        plan.problems.append(
            f"previous_engine is {actions['previous_engine']}, not {PREVIOUS_ENGINE}"
        )
    regenerated_ruled = {k for k in regenerated if k in ruled}
    if set(kept) | regenerated_ruled != ruled:
        missing = sorted(ruled - set(kept) - regenerated_ruled)
        plan.problems.append(
            "kept_exclusions_from_release and the regenerated ruled outputs must be "
            f"the spec's ruled outputs: missing {missing}, extra "
            f"{sorted(set(kept) - ruled)}"
        )
    plan.kept = sorted(k for k in kept if k in ruled)

    def change(k: Key, value: float, cause: str, basis: str) -> dict:
        return {
            "scenario_id": k[0],
            "variable": k[1],
            "frozen": float(base.frozen[k]),
            "previous": board[k],
            "regenerated": value,
            "cause": cause,
            "basis": basis,
        }

    within_basis = (
        f"Moves by $1 or less on {engine}; no score changes at the exact-match "
        "tolerance."
    )
    for row in base.reference.rows:
        k = row.key
        if k not in computed:
            continue
        value, old = float(computed[k]), board[k]
        moves = beyond(k[1], old, value)
        if k in excluded:
            for name, entries in (("approved", approved), ("new_exclusions", added)):
                if k in entries:
                    plan.problems.append(f"{name} names {k}, which is excluded")
            record = records[k]
            if k in regenerated:
                entry = regenerated[k]
                alternative = float(record["alternative_value"])
                tolerance = float(entry.get("tolerance", -1))
                if record["reason_code"] != ENGINE_DEFECT:
                    plan.problems.append(
                        f"regenerated {k} is {record['reason_code']}, not an engine "
                        "defect"
                    )
                    continue
                if abs(float(entry["alternative_value"]) - alternative) > EPS:
                    plan.problems.append(
                        f"regenerated {k}: alternative_value "
                        f"{entry['alternative_value']} is not the record's "
                        f"{alternative}"
                    )
                    continue
                if not 0 <= tolerance <= MAX_REGENERATION_TOL:
                    plan.problems.append(
                        f"regenerated {k}: tolerance {tolerance} outside [0, "
                        f"{MAX_REGENERATION_TOL}]"
                    )
                    continue
                # A flag must equal its target; an amount must land within the
                # tolerance, which is at most the exact-match $1.
                if abs(value - alternative) > tolerance or beyond(
                    k[1], alternative, value
                ):
                    plan.problems.append(
                        f"regenerated {k} misses its audited target: engine "
                        f"{value!r}, target {alternative!r} +/- {tolerance}"
                    )
                    continue
                if not str(entry.get("basis", "")).strip():
                    plan.problems.append(f"regenerated {k} has no basis")
                    continue
                upstream = str(entry.get("upstream", "")).strip()
                if upstream.lower() in UNNAMED_UPSTREAM:
                    plan.problems.append(
                        f"regenerated {k} names no upstream fix ({upstream!r})"
                    )
                    continue
                if abs(value - old) > EPS:
                    plan.new_values[k] = value
                    plan.changed.append(
                        change(k, value, "regenerated_upstream_fix", entry["basis"])
                    )
                plan.regenerated.append(
                    {
                        "scenario_id": k[0],
                        "variable": k[1],
                        "root_cause": record["root_cause"],
                        "decided_on": record["decided_on"],
                        "kept_value": old,
                        f"value_on_{engine_number(engine).replace('.', '_')}": value,
                        "audited_alternative_value": alternative,
                        "regenerated": value,
                        "tolerance": tolerance,
                        "upstream": entry["upstream"],
                        "basis": entry["basis"],
                        "record": copy.deepcopy(record),
                    }
                )
                continue
            # Stays excluded: keeps the value it was decided on (rule 5).
            if moves:
                if k not in rechecked:
                    plan.problems.append(
                        f"excluded output moved without a recheck: {k}: "
                        f"{old!r} -> {value!r}"
                    )
                elif not str(rechecked[k].get("reason", "")).strip():
                    plan.problems.append(f"rechecked {k} has no reason")
                else:
                    plan.rechecked.append(
                        {
                            "scenario_id": k[0],
                            "variable": k[1],
                            "kept_value": old,
                            f"value_on_{engine_number(engine).replace('.', '_')}": (
                                value
                            ),
                            "reason": rechecked[k]["reason"],
                        }
                    )
            elif k in rechecked:
                plan.problems.append(
                    f"rechecked {k} does not move: {old!r} -> {value!r}"
                )
            continue
        # Scored in the base and in the release.
        for name, entries in (
            ("regenerated_exclusions", regenerated),
            ("excluded_rechecked", rechecked),
            ("kept_exclusions_from_release", kept),
        ):
            if k in entries:
                plan.problems.append(f"{name} names {k}, which is scored")
        if k in added:
            record = added[k]
            problems = new_exclusion_problems(record, value, old, engine, date)
            if problems:
                plan.problems.extend(f"new exclusion {k}: {p}" for p in problems)
                continue
            plan.new_values[k] = value
            plan.new_records.append(copy.deepcopy(record))
            plan.changed.append(
                change(
                    k,
                    value,
                    f"excluded_{record['reason_code']}",
                    f"Newly excluded from scoring on {record['decided_on']} "
                    "(reference_exclusions.json): "
                    + str(
                        record.get("unlisted_input")
                        or record.get("root_cause")
                        or record["alternative_reading"]
                    ),
                )
            )
            continue
        if k in approved:
            entry = approved[k]
            if not moves:
                plan.problems.append(
                    f"approved {k} does not move: {old!r} -> {value!r}"
                )
                continue
            if abs(value - float(entry["value"])) > APPROVED_TOL:
                plan.problems.append(
                    f"approved {k}: engine {value!r} != approved {entry['value']!r}"
                )
                continue
            if (
                not str(entry.get("cause", "")).strip()
                or not str(entry.get("basis", "")).strip()
            ):
                plan.problems.append(f"approved {k} needs a cause and a basis")
                continue
            plan.new_values[k] = value
            plan.changed.append(change(k, value, entry["cause"], entry["basis"]))
            continue
        if moves:
            plan.problems.append(f"unreviewed move {k}: {old!r} -> {value!r}")
            continue
        if abs(value - old) > EPS:
            plan.new_values[k] = value
            plan.within.append(
                change(k, value, "engine_upgrade_within_1", within_basis)
            )
    plan.new_records.sort(key=key_of)
    return plan


def new_exclusion_problems(
    record: dict, value: float, old: float, engine: str, date: str
) -> list[str]:
    from policybench.reference_exclusions import (
        REASON_CODES,
        REQUIRED_FIELDS_BY_REASON,
    )

    variable = record["variable"]
    if record.get("reason_code") not in REASON_CODES:
        return [f"unknown reason_code {record.get('reason_code')!r}"]
    missing = [
        name
        for name in REQUIRED_FIELDS_BY_REASON[record["reason_code"]]
        if record.get(name) in (None, "")
    ]
    if missing:
        return [f"record missing {missing}"]
    problems = []
    if not beyond(variable, old, value):
        problems.append(f"the output does not move: {old!r} -> {value!r}")
    if abs(float(record["frozen_value"]) - value) > FROZEN_TOL:
        problems.append(f"frozen_value {record['frozen_value']!r} != engine {value!r}")
    if not beyond(
        variable, float(record["frozen_value"]), float(record["alternative_value"])
    ):
        problems.append("the alternative is within the exact-match tolerance")
    if record["engine_version"] != engine:
        problems.append(f"engine_version {record['engine_version']!r} != {engine!r}")
    if record["decided_on"] != date:
        problems.append(f"decided_on {record['decided_on']!r} != {date!r}")
    return problems


# --- Records -------------------------------------------------------------------


def upgrade_sentence(plan: Plan, actions: dict) -> str:
    """The derivation's sentence naming the upgrade."""
    engine, date = actions["engine"], actions["date"]
    number = engine_number(engine)
    parts = [
        f" On {date} the references moved from {actions['previous_engine']} to"
        f" {engine} with the same pre-freeze conventions"
        " (reference_audit/2026-10-09-engine-upgrade), and every output was"
        " recomputed there."
    ]
    n = len(plan.regenerated)
    if n == 1:
        parts.append(
            " The new engine fixes the defect behind one excluded output, which"
            " lands within $1 of its record's corrected value, so its record was"
            " removed and the output is scored again (the reference sidecar's second"
            " engine_upgrade revision lists it under regenerated_exclusions)."
        )
    elif n:
        parts.append(
            f" The new engine fixes the defects behind {words(n)} excluded outputs,"
            " each landing within $1 of its record's corrected value, so their"
            " records were removed and the outputs are scored again (the reference"
            " sidecar's second engine_upgrade revision lists them under"
            " regenerated_exclusions)."
        )
    n = len(plan.new_records)
    if n == 1:
        parts.append(
            " One scored output the new engine moved was excluded that day; its"
            f" record is computed on {number}."
        )
    elif n:
        parts.append(
            f" {words(n).capitalize()} scored outputs the new engine moved were"
            f" excluded that day; their records are computed on {number}."
        )
    n = len(plan.rechecked)
    if n == 1:
        parts.append(
            " Of the excluded outputs that stay excluded, one moved; it was"
            " re-reviewed and keeps the value it was decided on"
            " (excluded_outputs_rechecked)."
        )
    elif n:
        parts.append(
            f" Of the excluded outputs that stay excluded, {words(n)} moved; each"
            " was re-reviewed and keeps the value it was decided on"
            " (excluded_outputs_rechecked)."
        )
    else:
        parts.append(
            " No excluded output that stays excluded moved; each keeps the value it"
            " was decided on."
        )
    return "".join(parts)


def upgrade_exclusions(release: dict, plan: Plan, actions: dict) -> dict:
    """The release record less the regenerated, the new records before the
    trailing audit record, and the derivation naming the upgrade."""
    doc = copy.deepcopy(release)
    gone = {key_of(r) for r in plan.regenerated}
    records = [r for r in doc["exclusions"] if key_of(r) not in gone]
    tail = records[-1:] if records and key_of(records[-1]) == AUDIT_TAIL else []
    body = records[: len(records) - len(tail)]
    doc["exclusions"] = body + copy.deepcopy(plan.new_records) + tail
    doc["derivation"] = doc["derivation"] + upgrade_sentence(plan, actions)
    return doc


def upgrade_revision(
    plan: Plan,
    actions: dict,
    *,
    bundle: dict,
    fix_modules: list[dict],
    provenance: dict,
) -> dict:
    engine = actions["engine"]
    return {
        "date": actions["date"],
        "kind": "engine_upgrade",
        "root_cause": "engine_upgrade_policyengine_us_"
        + engine_number(engine).replace(".", "_"),
        "outputs": "every scored output",
        "rule": f"{RULE} {ENGINE_RULE} {UPGRADE_RULE}",
        "engine_version": engine,
        "previous_engine_version": actions["previous_engine"],
        "policyengine_py": (
            f"policyengine {bundle.get('policyengine_version')}, provenance only: its "
            "certified US bundle is policyengine-us "
            f"{bundle.get('bundled_model_version')}"
        ),
        "fix_modules": fix_modules,
        "builder": (
            "reference_audit/2026-10-09-engine-upgrade/scripts/"
            "build_references_upgrade.py; households from "
            "policybench.scenarios.Scenario.to_pe_household through "
            "reference_audit/2026-09-28/scripts/sweep.py build_situation, as in the "
            "2026-09-29 upgrade"
        ),
        "provenance": provenance,
        "excluded_outputs_untouched": True,
        "kept_exclusions_from_release": [
            {"scenario_id": k[0], "variable": k[1]} for k in plan.kept
        ],
        "excluded_outputs_rechecked": plan.rechecked,
        "regenerated_exclusions": plan.regenerated,
        "new_exclusions": [
            {
                "scenario_id": r["scenario_id"],
                "variable": r["variable"],
                "reason_code": r["reason_code"],
                "frozen_value": r["frozen_value"],
                "alternative_value": r["alternative_value"],
                "decided_on": r["decided_on"],
            }
            for r in plan.new_records
        ],
        "changed": plan.changed + plan.within,
    }


def upgrade_meta(
    base_meta: dict, revision: dict, *, csv_sha256: str, bundle: dict, now: str
) -> dict:
    meta = copy.deepcopy(base_meta)
    meta["policyengine_bundles"]["us"] = bundle
    meta["reference_csv_sha256"] = csv_sha256
    meta["regenerated_at_utc"] = now
    meta["revisions"].append(revision)
    return meta


def verify_outputs(
    base: Base,
    plan: Plan,
    csv_text: str,
    exclusions: dict,
    meta: dict,
) -> None:
    """The written records agree: the loader accepts the exclusion record, every
    excluded output carries its frozen value, every unchanged row keeps its
    bytes, and every earlier revision is kept as it was."""
    import tempfile

    import pandas as pd

    from policybench.reference_exclusions import (
        load_reference_exclusions,
        verify_exclusions_against_reference,
    )

    def check(condition: bool, message: str) -> None:
        if not condition:
            raise Refusal(f"written records disagree: {message}")

    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "reference_exclusions.json"
        path.write_text(dump_record(exclusions))
        loaded = load_reference_exclusions(path)
    verify_exclusions_against_reference(pd.read_csv(io.StringIO(csv_text)), loaded)
    written = parse_reference_csv(csv_text)
    check(
        [r.key for r in written.rows] == [r.key for r in base.reference.rows],
        "row order",
    )
    for old, new in zip(base.reference.rows, written.rows):
        if old.key in plan.new_values:
            check(new.value == plan.new_values[old.key], f"{old.key} value")
        else:
            check(new.raw == old.raw, f"{old.key} bytes")
    check(meta["revisions"][:-1] == base.meta["revisions"], "earlier revisions")
    check(
        dump_record({"r": meta["revisions"][:-1]})
        == dump_record({"r": base.meta["revisions"]}),
        "earlier revision bytes",
    )


@dataclass
class Written:
    csv_text: str
    exclusions: dict
    meta: dict
    traces: dict


def write_outputs(
    out_dir: Path,
    base: Base,
    release: dict,
    plan: Plan,
    actions: dict,
    *,
    bundle: dict,
    fix_modules: list[dict],
    provenance: dict,
    traces: dict,
    now: str,
) -> Written:
    if now[:10] != actions["date"]:
        raise Refusal(
            f"regenerated_at_utc {now} does not fall on the actions date "
            f"{actions['date']}; pass --regenerated-at or redate the actions"
        )
    csv_text = render_reference_csv(base.reference, plan.new_values)
    exclusions = upgrade_exclusions(release, plan, actions)
    revision = upgrade_revision(
        plan, actions, bundle=bundle, fix_modules=fix_modules, provenance=provenance
    )
    meta = upgrade_meta(
        base.meta,
        revision,
        csv_sha256=sha256_bytes(csv_text.encode()),
        bundle=bundle,
        now=now,
    )
    verify_outputs(base, plan, csv_text, exclusions, meta)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "reference_outputs.csv").write_text(csv_text)
    (out / "reference_exclusions.json").write_text(dump_record(exclusions))
    (out / "reference_outputs.csv.meta.json").write_text(dump_record(meta))
    (out / "reference_traces.json").write_text(json.dumps(traces, indent=1))
    return Written(csv_text, exclusions, meta, traces)


def write_computed(path: Path, base: Base, computed: dict[Key, float], states) -> None:
    """Every output on the new engine, in sweep.py's columns."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as sink:
        writer = csv.writer(sink, lineterminator="\n")
        writer.writerow(
            [
                "fix",
                "scenario_id",
                "state",
                "variable",
                "frozen",
                "recomputed",
                "delta",
                "moved",
            ]
        )
        for row in base.reference.rows:
            if row.key not in computed:
                continue
            value = float(computed[row.key])
            writer.writerow(
                [
                    FIX_ENTRY,
                    row.key[0],
                    states.get(row.key[0], ""),
                    row.key[1],
                    repr(row.value),
                    repr(value),
                    repr(value - row.value),
                    beyond(row.key[1], row.value, value),
                ]
            )


# --- Engine ------------------------------------------------------------------


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fix_module_pins(base_meta: dict, fixes_dir: Path) -> list[dict]:
    """The modules latest_final.py composes, each the bytes the 2026-09-29
    revision pins, plus latest_final.py and the sales tax tables."""
    first = [r for r in base_meta["revisions"] if r["kind"] == "engine_upgrade"][-1]
    entries = []
    for entry in first["fix_modules"]:
        path = fixes_dir / entry["module"]
        if not path.is_file() or sha256(path) != entry["sha256"]:
            raise Refusal(f"{path} is not the module the 2026-09-29 upgrade pins")
        entries.append(
            {
                "module": entry["module"],
                "path": f"reference_audit/2026-09-28/fixes/{entry['module']}",
                "sha256": entry["sha256"],
            }
        )
    # Pinned to the bytes committed at the base commit, not to FIXES: imported
    # in place, fixes_dir is FIXES and that comparison would be with itself.
    entry_path = fixes_dir / f"{FIX_ENTRY}.py"
    committed = git_blob(BASE_COMMIT, f"{FIXES_REL}/{FIX_ENTRY}.py")
    if not entry_path.is_file() or sha256(entry_path) != sha256_bytes(committed):
        raise Refusal(
            f"{entry_path} is not {FIX_ENTRY}.py as committed at {BASE_COMMIT[:12]}"
        )
    entries.append(
        {
            "module": f"{FIX_ENTRY}.py",
            "path": f"reference_audit/2026-09-28/fixes/{FIX_ENTRY}.py",
            "sha256": sha256(entry_path),
        }
    )
    tables = fixes_dir / SALES_TAX_TABLES
    if not tables.is_file():
        raise Refusal(
            f"{tables} is missing: latest_c_irs_sales_tax_2025.py reads it from its "
            f"own directory; copy {SALES_TAX_SOURCE.relative_to(ROOT)} beside the "
            "fixes"
        )
    committed_tables = git_blob(BASE_COMMIT, SALES_TAX_REL)
    if sha256(tables) != sha256_bytes(committed_tables) or sha256(
        SALES_TAX_SOURCE
    ) != sha256_bytes(committed_tables):
        raise Refusal(f"{tables} is not {SALES_TAX_REL} as committed")
    entries.append(
        {
            "module": SALES_TAX_TABLES,
            "path": f"reference_audit/2026-09-22/fixes/{SALES_TAX_TABLES}",
            "sha256": sha256(tables),
        }
    )
    return entries


def harness_pin(path: Path = HARNESS) -> dict:
    """sweep.py, whose build_situation builds every household, must be the
    bytes committed at the base commit."""
    committed = git_blob(BASE_COMMIT, HARNESS_REL)
    if not Path(path).is_file() or sha256(path) != sha256_bytes(committed):
        raise Refusal(f"{path} is not {HARNESS_REL} as committed at {BASE_COMMIT[:12]}")
    return {"path": HARNESS_REL, "sha256": sha256_bytes(committed)}


def compute_outputs(system, scenarios, programs, build_situation) -> dict[Key, float]:
    from policyengine_us import Simulation

    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output
    from policybench.scenarios import scenario_from_dict
    from policybench.spec import expand_programs_for_scenario

    computed = {}
    for _, srow in scenarios.iterrows():
        scenario = scenario_from_dict(json.loads(srow["scenario_json"]))
        situation = build_situation(scenario)
        if scenario.id == "scenario_066":
            head = next(iter(situation["people"].values()))
            assert "weekly_hours_worked_before_lsr" in head, "builder hours mapping"
        sim = Simulation(tax_benefit_system=system, situation=situation)
        for variable in expand_programs_for_scenario(programs, scenario):
            pe_variable = _pe_variable_for_output(variable, "us")
            computed[(scenario.id, variable)] = float(
                _extract_person_value(
                    sim.calculate(pe_variable, YEAR), scenario, variable
                )
            )
    return computed


def trace_outputs(system, scenarios, items, build_situation) -> dict:
    import types

    sys.modules.setdefault("litellm", types.ModuleType("litellm"))
    from policyengine_us import Simulation

    from policybench.case_reference_explanations import _find_target_tree, _render_trace
    from policybench.ground_truth import _pe_variable_for_output
    from policybench.scenarios import scenario_from_dict

    by_id = scenarios.set_index("scenario_id")
    traces = {}
    for item in items:
        scenario = scenario_from_dict(
            json.loads(by_id.loc[item["scenario_id"], "scenario_json"])
        )
        sim = Simulation(tax_benefit_system=system, situation=build_situation(scenario))
        sim.trace = True
        pe_variable = _pe_variable_for_output(item["variable"], "us")
        sim.calculate(pe_variable, YEAR)
        tree = _find_target_tree(sim.tracer.trees, pe_variable)
        traces[f"{item['scenario_id']}|{item['variable']}"] = {
            "pe_variable": pe_variable,
            "trace": "\n".join(_render_trace(tree)) if tree else "",
        }
    return traces


def main(argv: list[str] | None = None) -> None:
    from importlib.metadata import version

    import pandas as pd

    parser = argparse.ArgumentParser()
    parser.add_argument("--actions", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--fixes-dir", default=str(FIXES))
    parser.add_argument("--computed-csv")
    parser.add_argument("--regenerated-at")
    parser.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args(argv)

    actions_path = Path(args.actions)
    actions = json.loads(actions_path.read_text())
    validate_actions(actions, allow_draft=args.allow_draft)
    engine = engine_number(actions["engine"])
    installed = version("policyengine-us")
    if installed != engine:
        raise Refusal(f"need policyengine-us {engine}, have {installed}")

    base = load_base()
    release, ruled, spec_sha = release_record(base.exclusions)
    if actions.get("release_spec_sha256") != spec_sha:
        drafted = actions.get("release_spec_sha256")
        raise Refusal(
            f"the actions were drafted against spec {drafted}, not "
            f"docs/haiku55/spec.json {spec_sha}"
        )
    fixes_dir = Path(args.fixes_dir).resolve()
    fix_modules = fix_module_pins(base.meta, fixes_dir)
    harness_pinned = harness_pin()
    harness = load_module("upgrade_sweep_harness", HARNESS)
    final = load_module(f"upgrade_{FIX_ENTRY}", fixes_dir / f"{FIX_ENTRY}.py")

    from policyengine_us import CountryTaxBenefitSystem

    from policybench.policyengine_runtime import policyengine_release_bundle

    system = CountryTaxBenefitSystem(reform=final.reform)
    scenarios = pd.read_csv(io.StringIO(base.scenarios_csv))
    computed = compute_outputs(
        system, scenarios, base.meta["programs"], harness.build_situation
    )
    states = dict(zip(scenarios["scenario_id"], scenarios["state"]))
    out = Path(args.out_dir)
    write_computed(
        Path(args.computed_csv or out / "computed.csv"), base, computed, states
    )
    plan = plan_upgrade(base, release, ruled, actions, computed)
    if plan.problems:
        raise Refusal("refusing to write references:\n  " + "\n  ".join(plan.problems))

    traces = trace_outputs(
        system, scenarios, plan.changed + plan.within, harness.build_situation
    )
    now = (
        args.regenerated_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    provenance = {
        "builder_sha256": sha256(Path(__file__)),
        "harness": harness_pinned["path"],
        "harness_sha256": harness_pinned["sha256"],
        "actions_sha256": sha256(actions_path),
        "release_spec_sha256": spec_sha,
        "base_commit": BASE_COMMIT,
        "policyengine_core": version("policyengine-core"),
    }
    written = write_outputs(
        out,
        base,
        release,
        plan,
        actions,
        bundle=policyengine_release_bundle("us"),
        fix_modules=fix_modules,
        provenance=provenance,
        traces=traces,
        now=now,
    )
    print(f"sha256 {written.meta['reference_csv_sha256']}")
    print(
        f"{len(plan.changed)} reviewed changes, {len(plan.within)} within $1, "
        f"{len(plan.regenerated)} regenerated exclusions, {len(plan.new_records)} new "
        f"exclusions, {len(plan.rechecked)} excluded outputs rechecked, "
        f"{len(written.exclusions['exclusions'])} exclusion records"
    )
    for c in plan.changed + plan.within:
        print(
            f"  {c['scenario_id']} {c['variable']:46s} {c['previous']:>11.2f} -> "
            f"{c['regenerated']:>11.2f}  {c['cause']}"
        )


if __name__ == "__main__":
    main()
