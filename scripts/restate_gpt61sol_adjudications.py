"""Restate the adjudication records of the cases GPT-6.1 Sol's answers re-judged.

``prepare`` re-renders the prompt of every case GPT-6.1 Sol answers wrong, so
the seed verdict no longer covers the case and ``judge`` asks Opus 5.5 again.
Some of those cases carry a developer adjudication. The record keeps the
judge's verdict verbatim beside each decision (triage checks it with
``verify_adjudications_keep_judge_verdicts``) and dates it from the verdict's
sidecar (the record's ``date_conventions``). So each re-judged entry is
restated the way release 20260929's wave restated its own re-judges
(scripts/date_adds0928_judge_verdicts.py):

- the verdict the re-judge replaced is appended to ``judge_previous``, dated
  by its sha256-bound sidecar in the seed audit. The entry's judge fields and
  date must name that verdict, or the script stops. The seed must be the
  stage's own: every carried-over case's verdict and sidecar in the stage
  must equal the seed's byte for byte;
- the stage's new verdict (judge, classes, flag) goes in at the top level, and
  ``judge_rejudged_on``, with ``judged_on_utc`` where the entry has one,
  becomes the UTC day in its sidecar;
- a flag an earlier 2026-09-22 run raised (flagged_sept22_wave.json) stays
  recorded, with its source, at each level whose own verdict does not raise
  it. The committed record follows exactly this rule. A top-level source the
  entry already carries keeps its wording (the record words it two ways); a
  new one takes the wording scripts/date_adds0928_judge_verdicts.py uses.

A top-level field the entry lacks goes after the decision fields, before the
first trailing judge field that follows ``reasoning`` (judged_on_utc,
judge_rejudged_on, judge_previous, adjudicated_verdict), where the record
keeps every flag source.

An entry is restated whenever its case was re-judged, whether or not the class
moved, as the 20260929 record did. No decision changes: every field outside
the judge fields (the adjudicated class, exclusion, reference verdict and
basis, reasoning, adjudicated_on, adjudicated_verdict) keeps its value and
place, and ``judge_previous`` becomes exactly its earlier items plus the seed
verdict; the script checks both. A new flag that no reference verdict answers
stops the script, because it needs a developer decision, not a restatement.

It is idempotent. If the stage is re-judged after a restatement, a rerun
replaces only the top-level verdict; a source that an intermediate verdict's
own flag removed then comes back in the canonical wording. The script never
writes an entry whose top level names the seed verdict, so an entry that does
is restated for the first time, even when its last judge_previous item reads
the same as the seed verdict. A re-judge that repeats the seed verdict on the
seed's own UTC day therefore stops the script: its restated entry would still
name the seed verdict, and a rerun could not tell it from one never restated.
Re-judge such a case on a later day. It checks the
restated record in memory, before it writes anything: the exact text it will
write must load, keep every judge verdict verbatim against the stage and keep
the scoring exclusions. It writes the verdicts it read, replaced and current,
to --evidence-out (default ``<stage>/restated-adjudications.json``).

Usage::

    python scripts/restate_gpt61sol_adjudications.py --stage-dir STAGE \\
        --audit-seed PATH/TO/adds0928-v3/audit
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from date_adds0928_judge_verdicts import (  # noqa: E402
    FLAG_SOURCE_EARLIER_RUN,
    ITEM_FLAG_SOURCE,
    WAVE_FLAGS,
    _bound_verdict,
    _evidence,
    _judge,
)
from finish_gpt61sol import JUDGE_MODEL, RUN_NAME  # noqa: E402

# The fields a restatement may write; everything else is a decision.
JUDGE_FIELDS = frozenset(
    {
        "judge_model",
        "judge_failure_source",
        "judge_failure_subtype",
        "judge_reference_suspect",
        "judge_reference_suspect_source",
        "judged_on_utc",
        "judge_rejudged_on",
        "judge_previous",
    }
)
# The judge fields that trail an entry's decision fields, in record order.
TRAIL = ("judged_on_utc", "judge_rejudged_on", "judge_previous", "adjudicated_verdict")
# The top-level fields that name a verdict, beside its flag source and date.
TOP = (
    "judge_model",
    "judge_failure_source",
    "judge_failure_subtype",
    "judge_reference_suspect",
)


def _put(entry: dict, key: str, value, before: tuple[str, ...] = ()) -> dict:
    """``entry`` with ``key`` set; a new key goes before the first of ``before``
    the entry has, else last."""
    if key in entry:
        return {**entry, key: value}
    names = list(entry)
    at = next((names.index(n) for n in before if n in entry), len(names))
    items = list(entry.items())
    return dict(items[:at] + [(key, value)] + items[at:])


def _trailing(entry: dict) -> tuple[str, ...]:
    """The first trailing judge field after reasoning, where a new top-level
    field goes; every flag source the committed record keeps sits there."""
    names = list(entry)
    following = names[names.index("reasoning") + 1 :] if "reasoning" in entry else []
    return tuple(name for name in following if name in TRAIL)[:1]


def _utc_day(timestamp: str) -> str:
    """The UTC calendar day of a sidecar's ``judged_at_utc`` timestamp."""
    moment = datetime.fromisoformat(timestamp)
    if moment.tzinfo is None:
        raise SystemExit(f"judged_at_utc carries no time zone: {timestamp}")
    return moment.astimezone(timezone.utc).date().isoformat()


def _case(entry: dict) -> str:
    return f"{entry['country']}__{entry['scenario_id']}__{entry['variable']}"


def _named(entry: dict) -> tuple[dict, str | None]:
    """The verdict an entry's top level names, and its date: date_conventions
    dates it by judge_rejudged_on, else judged_on_utc. Where the entry has
    both, they must name the same day, or the date is None."""
    named = {name: entry.get(name) for name in TOP}
    named["judge_reference_suspect"] = bool(named["judge_reference_suspect"])
    dated = entry.get("judge_rejudged_on") or entry.get("judged_on_utc")
    if entry.get("judged_on_utc", dated) != dated:
        dated = None
    return named, dated


def named_item(entry: dict) -> dict:
    """The judge_previous item for the verdict an entry's top level names:
    its judge, classes, flag and day, with the item wording of a flag source
    where the entry records one. A restatement that replaces that verdict
    appends exactly this item."""
    named, dated = _named(entry)
    item = {**named, "judged_on": dated}
    if "judge_reference_suspect_source" in entry:
        item["judge_reference_suspect_source"] = ITEM_FLAG_SOURCE
    return item


def replaced_item(found: tuple[dict, dict], waved: bool) -> dict:
    """The judge_previous item for a replaced verdict, as its sha256-bound
    sidecar records it (``found`` is ``_bound_verdict``'s pair); ``waved``
    says whether a 2026-09-22 run flagged its case."""
    old, old_meta = found
    old_flag = bool(old.get("reference_suspect"))
    item = {
        "judge_model": _judge(old_meta),
        "judge_failure_source": old["case_failure_source"],
        "judge_failure_subtype": old["case_failure_subtype"],
        "judge_reference_suspect": old_flag or waved,
        "judged_on": _utc_day(old_meta["judged_at_utc"]),
    }
    if waved and not old_flag:
        item["judge_reference_suspect_source"] = ITEM_FLAG_SOURCE
    return item


def _names(entry: dict, item: dict) -> bool:
    """Whether the entry's top level names ``item``: its judge, classes, flag,
    flag source and day."""
    return named_item(entry) == item


def _restated(
    entry: dict,
    top: dict,
    item: dict,
    day: str,
    previous: list[dict],
    waved: bool,
    flag: bool,
) -> dict:
    """``entry`` naming the stage verdict ``top``, dated ``day``, with ``item``
    (the replaced verdict) appended to ``previous``."""
    restated = dict(entry)
    for name, value in top.items():
        restated = _put(restated, name, value, before=_trailing(restated))
    if not (waved and not flag):
        restated.pop("judge_reference_suspect_source", None)
    elif "judge_reference_suspect_source" not in restated:
        restated = _put(
            restated,
            "judge_reference_suspect_source",
            FLAG_SOURCE_EARLIER_RUN,
            before=_trailing(restated),
        )
    if "judged_on_utc" in restated:
        restated["judged_on_utc"] = day
    restated = _put(
        restated,
        "judge_rejudged_on",
        day,
        before=("judge_previous", "adjudicated_verdict"),
    )
    return _put(
        restated, "judge_previous", [*previous, item], before=("adjudicated_verdict",)
    )


def check_seed(stage_cases: Path, seed_cases: Path, kept: list[str]) -> None:
    """Stop unless ``seed_cases`` is the audit the stage was seeded from.

    prepare copies each seed verdict and sidecar into the stage and keeps them
    for every case whose prompt did not change, so those files must match the
    seed's byte for byte. Any other seed would name the wrong replaced verdict.
    """
    differ = [
        case
        for case in kept
        for name in ("verdict.json", "verdict.meta.json")
        if not (seed_cases / case / name).is_file()
        or (stage_cases / case / name).read_bytes()
        != (seed_cases / case / name).read_bytes()
    ]
    if differ or not kept:
        raise SystemExit(
            "the audit seed is not the stage's: carried-over verdicts differ "
            f"({len(differ)} files, e.g. {sorted(set(differ))[:3]})"
        )


def restate_entries(
    entries: list[dict],
    stage_cases: Path,
    seed_cases: Path,
    rejudged: set[str] | frozenset[str],
    wave_flags: set[str] | frozenset[str] = frozenset(),
    evidence: dict | None = None,
) -> tuple[list[dict], list[str]]:
    """Return the restated entries and one line per changed entry.

    ``rejudged`` holds the case ids whose prompt changed in the stage
    (prompt-changes.json); ``wave_flags`` holds "scenario_id:variable" keys a
    2026-09-22 judge run flagged. ``evidence``, when given, collects the two
    bound verdicts behind each restated entry, keyed by case. The caller
    checks that ``seed_cases`` is the stage's seed (``check_seed``).
    """
    out: list[dict] = []
    changes: list[str] = []
    for entry in entries:
        case = _case(entry)
        if case not in rejudged:
            out.append(entry)
            continue
        waved = f"{entry['scenario_id']}:{entry['variable']}" in wave_flags
        found = _bound_verdict(stage_cases / case)
        if found is None:
            raise SystemExit(f"{case}: no bound verdict in the stage; run judge")
        verdict, meta = found
        if _judge(meta) != JUDGE_MODEL or meta.get("judge_model_reported") != [
            JUDGE_MODEL
        ]:
            raise SystemExit(f"{case}: the stage verdict is not {JUDGE_MODEL}'s")
        replaced = _bound_verdict(seed_cases / case)
        if replaced is None:
            raise SystemExit(f"{case}: no bound verdict in the seed audit")
        old, old_meta = replaced
        if old_meta["verdict_sha256"] == meta["verdict_sha256"]:
            raise SystemExit(f"{case}: the stage still holds the seed verdict")
        old_flag = bool(old.get("reference_suspect"))
        item = replaced_item(replaced, waved)
        flag = bool(verdict.get("reference_suspect"))
        top = {
            "judge_model": _judge(meta),
            "judge_failure_source": verdict["case_failure_source"],
            "judge_failure_subtype": verdict["case_failure_subtype"],
            "judge_reference_suspect": flag or waved,
        }
        day = _utc_day(meta["judged_at_utc"])
        if day < item["judged_on"]:
            raise SystemExit(
                f"{case}: the stage verdict ({day}) predates the seed verdict it "
                f"replaces ({item['judged_on']})"
            )
        if flag and not entry.get("reference_verdict"):
            raise SystemExit(
                f"{case}: the re-judge flags the reference and no reference "
                "verdict answers it; that needs a developer decision"
            )
        previous = entry.get("judge_previous", [])
        if _names(entry, item):
            # The entry names the verdict the re-judge replaced. This script
            # never writes such an entry (it refuses below), so it is restated
            # for the first time: the seed verdict is appended even when an
            # earlier judge_previous item reads the same.
            base = previous
        elif previous and previous[-1] == item:
            # Restated already: the seed verdict is the last judge_previous
            # item, so it is never appended again. The top must name an Opus
            # 5.5 re-judge dated on or after it; a later re-judge replaces
            # only the top.
            base = previous[:-1]
            if not (
                entry["judge_model"] == JUDGE_MODEL
                and (entry.get("judge_rejudged_on") or "") >= item["judged_on"]
                and entry.get("judged_on_utc", entry["judge_rejudged_on"])
                == entry["judge_rejudged_on"]
            ):
                raise SystemExit(
                    f"{case}: the record names neither the seed verdict nor "
                    "an Opus 5.5 re-judge dated on or after it"
                )
        else:
            named, dated = _named(entry)
            raise SystemExit(
                f"{case}: the record does not name the seed verdict it "
                f"replaces ({named}, dated {dated}, vs {item})"
            )
        restated = _restated(entry, top, item, day, base, waved, flag)
        if _names(restated, item):
            raise SystemExit(
                f"{case}: the re-judge repeats the seed verdict on the seed's own "
                f"UTC day ({day}), so a rerun could not tell the restated entry "
                "from one never restated; re-judge the case on a later day"
            )
        if restated == entry and list(restated) == list(entry):
            restated = entry
        kept = {k: v for k, v in entry.items() if k not in JUDGE_FIELDS}
        if kept != {k: v for k, v in restated.items() if k not in JUDGE_FIELDS}:
            raise SystemExit(f"{case}: a restatement may not touch a decision")
        if list(kept) != [k for k in restated if k not in JUDGE_FIELDS]:
            raise SystemExit(f"{case}: a restatement may not reorder a decision")
        # Guaranteed by construction; kept as a guard against a future edit.
        if restated["judge_previous"] != [*base, item] or base != previous[: len(base)]:
            raise SystemExit(f"{case}: a restatement may not rewrite judge_previous")
        out.append(restated)
        old_class = (item["judge_failure_source"], item["judge_failure_subtype"])
        new_class = (top["judge_failure_source"], top["judge_failure_subtype"])
        if evidence is not None:
            evidence[case] = {
                "replaced": _evidence("seed", replaced),
                "current": _evidence("stage", found),
                "class_changed": old_class != new_class,
                "flag_changed": old_flag != flag,
            }
        if restated is not entry:
            changes.append(
                f"{case}: {'/'.join(old_class)} flag={old_flag} "
                f"({item['judged_on']}) -> {'/'.join(new_class)} flag={flag} ({day})"
            )
    return out, changes


def main(argv: list[str] | None = None) -> None:
    from freeze_snapshot import verify_adjudications_keep_judge_verdicts

    from policybench.adjudications import (
        excluded_case_keys,
        load_adjudications,
        parse_adjudications,
    )

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--audit-seed", type=Path, required=True)
    parser.add_argument("--wave-flags", type=Path, default=WAVE_FLAGS)
    parser.add_argument("--evidence-out", type=Path)
    args = parser.parse_args(argv)
    stage = args.stage_dir.resolve()
    path = stage / "publish" / RUN_NAME / "annotations" / "us_adjudications.json"
    changed = json.loads((stage / "prompt-changes.json").read_text())
    rejudged = frozenset(changed["changed"]) | frozenset(changed["added"])
    check_seed(stage / "audit" / "cases", args.audit_seed / "cases", changed["kept"])
    record = json.loads(path.read_text())
    before = load_adjudications(path)
    evidence: dict[str, dict] = {}
    record["adjudications"], changes = restate_entries(
        record["adjudications"],
        stage / "audit" / "cases",
        args.audit_seed / "cases",
        rejudged,
        frozenset(json.loads(args.wave_flags.read_text())),
        evidence,
    )
    # Check the exact text that will replace the staged record, in memory,
    # before anything is written.
    text = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    after = parse_adjudications(json.loads(text), path)
    verify_adjudications_keep_judge_verdicts(after, stage / "audit" / "cases")
    if excluded_case_keys(after) != excluded_case_keys(before):
        raise SystemExit("a restatement moved a scoring exclusion")
    pending = path.with_name(path.name + ".restating")
    pending.write_text(text)
    os.replace(pending, path)
    out = args.evidence_out or stage / "restated-adjudications.json"
    out.write_text(
        json.dumps(
            {
                "note": (
                    "The verdicts behind each adjudication restated by "
                    "scripts/restate_gpt61sol_adjudications.py: 'replaced' is the "
                    "seed audit's verdict (release 20260929), now the last "
                    "judge_previous item; 'current' is the stage's Opus 5.5 "
                    "re-judge, now the entry's judge fields. Each is read from "
                    "verdict.json and its sha256-bound verdict.meta.json."
                ),
                "cases": dict(sorted(evidence.items())),
            },
            indent=2,
        )
        + "\n"
    )
    for line in changes:
        print(line)
    print(f"{len(changes)} entries restated in {path}")


if __name__ == "__main__":
    main()
