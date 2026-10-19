"""America.gov on PolicyBench: the replies behind the 2026-10-19 note, and the note's
facts.

America.gov, the General Services Administration's public assistant, was sent each of
the 100 US households of release dashboard-data-20261014 in a fresh chat, with the
board's JSON-format prompt, between 2026-10-15 and 2026-10-19. Six prompts exceed the
8,000 characters America.gov asks a message to stay within, so each went in as two chats
(halves a and b), each keeping the prompt's instructions, household facts and answer
format and asking for a contiguous half of the requested outputs. A refused unit (a
household, or one half) was asked again with the identical prompt in a fresh chat, for
up to two rounds; round 2 asked only the units round 1 left refused.
notes/data/america_gov_20261019.csv holds every reply.

Two views of the replies:
- first: each unit's first reply.
- retried: a unit whose first reply breaks the answer contract (a refusal, or a reply
  missing a requested output, a finite number or an explanation) is replaced whole by
  its first retry that meets it: exactly the requested outputs, each with a finite
  number and a nonempty explanation (the board's full-response retry rule,
  docs/runbook.md section 5).

Every attempt in the file is a finished reply. A reply with no parseable answer is
recorded as refused, with its text; scenario_018's first refusal reached the capture cut
off at 1,000 of its 1,167 characters (meta: truncated_refusals).

Scoring is the board's: policybench.analysis.row_hit_scores (exact), the release's
globalWeights.household by output group, renormalised within each household, and an
equal-household mean; excluded outputs are unscored and an unanswered output is a miss.

usage: python scripts/america_gov_note.py build <capture workspace>  (CSV and meta)
       python scripts/america_gov_note.py facts  (prints the note's facts)
"""

from __future__ import annotations

import csv
import datetime
import gzip
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from policybench.analysis import row_hit_scores  # noqa: E402
from policybench.spec import output_group_id  # noqa: E402

RUN_DIR = (
    ROOT / "paper/snapshot/20260501/runs/"
    "us_full_run_20260612_policyengine_4_16_1_populace"
)
ROWS_PATH = ROOT / "notes/data/america_gov_20261019.csv"
META_PATH = ROWS_PATH.with_suffix(ROWS_PATH.suffix + ".meta.json")
RELEASE = "dashboard-data-20261014"
COLUMNS = [
    "unit",
    "scenario_id",
    "half",
    "attempt",
    "captured_at_utc",
    "outcome",
    "variable",
    "value",
    "explanation",
    "refusal_text",
]
PROMPT_HEAD = "Provide the following policy quantities for this household:\n"
PROMPT_TAIL = "\n\nReturn a single JSON object"
# Output groups whose v1 definitions name PolicyEngine.
POLICYENGINE_GROUPS = (
    "person_medicaid_eligible",
    "person_chip_eligible",
    "free_school_meals_eligible",
    "reduced_price_school_meals_eligible",
)
ROUNDS = (1, 2)
# America.gov's own words, as its pages read on 2026-10-19.
SITE_QUOTES = {
    "fetched_utc": "2026-10-19",
    "how_it_works": {
        "url": "https://america.gov/how-it-works",
        "quote": (
            "Super Intelligence (SI) to find and explain information from official "
            "government sources"
        ),
    },
    "terms": {
        "url": "https://america.gov/terms",
        "quote": (
            "Some answers on America.gov are generated with SI. They can be "
            "incomplete or wrong"
        ),
    },
    "message_limit": {
        "url": "https://america.gov/",
        "quote": "Please keep your message to 8,000 characters or fewer.",
    },
}


def requested(prompt: str) -> list[str]:
    block = prompt.split(PROMPT_HEAD)[1].split(PROMPT_TAIL)[0]
    return [line[2:].split(": ")[0] for line in block.split("\n")]


# ---------------------------------------- build (one-time, from captures)


def build(workspace: Path) -> None:
    """Write the CSV and its meta from the capture workspace (replies/, replies_split/,
    replies_retry/, prompts/, prompts_split/)."""
    rows, split_units = [], {}

    def add(unit: str, sid: str, half: str, attempt: int, record: dict) -> None:
        if record.get("outputs"):
            for variable, out in record["outputs"].items():
                rows.append(
                    {
                        "unit": unit,
                        "scenario_id": sid,
                        "half": half,
                        "attempt": attempt,
                        "captured_at_utc": record["captured_at"],
                        "outcome": "answered",
                        "variable": variable,
                        "value": repr(float(out["value"])),
                        "explanation": out["explanation"],
                        "refusal_text": "",
                    }
                )
        else:
            rows.append(
                {
                    "unit": unit,
                    "scenario_id": sid,
                    "half": half,
                    "attempt": attempt,
                    "captured_at_utc": record["captured_at"],
                    "outcome": "refused",
                    "variable": "",
                    "value": "",
                    "explanation": "",
                    "refusal_text": record.get("raw_if_unparsed") or "",
                }
            )

    for path in sorted((workspace / "replies").glob("scenario_*.json")):
        record = json.loads(path.read_text())
        sid = record["sid"]
        if record.get("split"):
            split_units[sid] = {}
            for half in "ab":
                unit = f"{sid}_{half}"
                split_units[sid][half] = requested(
                    (workspace / "prompts_split" / f"{unit}.txt").read_text()
                )
                add(
                    unit,
                    sid,
                    half,
                    1,
                    json.loads(
                        (workspace / "replies_split" / f"{unit}.json").read_text()
                    ),
                )
        else:
            add(sid, sid, "", 1, record)
    for path in sorted((workspace / "replies_retry").glob("scenario_*_r*.json")):
        unit, round_ = path.stem.rsplit("_r", 1)
        sid = unit[:12]
        add(
            unit,
            sid,
            unit[13:] if len(unit) > 12 else "",
            int(round_) + 1,
            json.loads(path.read_text()),
        )
    rows.sort(key=lambda r: (r["scenario_id"], r["half"], r["attempt"], r["variable"]))

    ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ROWS_PATH.open("w", encoding="utf-8", newline="") as sink:
        writer = csv.DictWriter(sink, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    meta = {
        "release": RELEASE,
        "source_run": RUN_DIR.name,
        "subject": (
            "America.gov (https://america.gov), the General Services "
            "Administration's assistant"
        ),
        "captured": (
            "2026-10-15T00:28Z to 2026-10-19T01:06Z, one chat at a time, "
            "each in a fresh chat"
        ),
        "prompt": (
            "the board's JSON-format prompt for each household "
            "(scenarios[sid].prompt.json in the release payload)"
        ),
        "message_limit_characters": 8000,
        "split_units": split_units,
        "attempts": (
            "1 = first reply; 2 and 3 = retry rounds 1 and 2 of a refused unit, "
            "same prompt, fresh chat"
        ),
        "every_attempt_finished": True,
        "refused_means": "no parseable answer JSON; refusal_text is the reply's text",
        "truncated_refusals": {
            "scenario_018": {
                "attempt": 1,
                "kept_characters": 1000,
                "reply_characters": 1167,
                "note": "cut off by the capture tool's output limit",
            }
        },
        "site_quotes": SITE_QUOTES,
        "rows": len(rows),
        "sha256": hashlib.sha256(ROWS_PATH.read_bytes()).hexdigest(),
        "generated_at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "script": "scripts/america_gov_note.py",
    }
    META_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------- views and scoring


def load_rows(path: Path = ROWS_PATH) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def units(rows: list[dict]) -> dict[str, dict[int, list[dict]]]:
    """unit -> attempt -> its rows."""
    by: dict[str, dict[int, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by[row["unit"]][int(row["attempt"])].append(row)
    return by


def unit_requested(unit: str, payload: dict, meta: dict) -> list[str]:
    sid, half = unit[:12], unit[13:]
    if half:
        return meta["split_units"][sid][half]
    return requested(payload["scenarios"][sid]["prompt"]["json"])


def answered(reply: list[dict]) -> bool:
    return all(row["outcome"] == "answered" for row in reply)


def meets_contract(reply: list[dict], wanted: list[str]) -> bool:
    if not answered(reply):
        return False
    values = {row["variable"]: row for row in reply}
    return set(values) == set(wanted) and all(
        math.isfinite(float(row["value"])) and row["explanation"].strip()
        for row in values.values()
    )


def view(rows: list[dict], payload: dict, meta: dict, *, retried: bool) -> dict:
    """{(scenario_id, variable): value} for the first or retried view; unanswered
    outputs are absent."""
    preds = {}
    for unit, attempts in units(rows).items():
        reply = attempts[1]
        if retried and not meets_contract(reply, unit_requested(unit, payload, meta)):
            wanted = unit_requested(unit, payload, meta)
            for n in ROUNDS:
                if n + 1 in attempts and meets_contract(attempts[n + 1], wanted):
                    reply = attempts[n + 1]
                    break
        if answered(reply):
            wanted = set(unit_requested(unit, payload, meta))
            for row in reply:
                if row["variable"] in wanted:
                    preds[(row["scenario_id"], row["variable"])] = float(row["value"])
    return preds


def references() -> tuple[dict, dict]:
    excluded = {
        (e["scenario_id"], e["variable"])
        for e in json.loads((RUN_DIR / "reference_exclusions.json").read_text())[
            "exclusions"
        ]
    }
    with (RUN_DIR / "reference_outputs.csv").open(
        encoding="utf-8", newline=""
    ) as source:
        ref = {
            (r["scenario_id"], r["variable"]): float(r["value"])
            for r in csv.DictReader(source)
            if (r["scenario_id"], r["variable"]) not in excluded
        }
    return ref, excluded


def weights(keys, global_weights: dict) -> dict:
    by = defaultdict(list)
    for sid, var in keys:
        by[(sid, output_group_id(var))].append(var)
    w = {}
    for (sid, group), variables in by.items():
        for var in variables:
            w[(sid, var)] = global_weights.get(group, 0.0) / len(variables)
    total = defaultdict(float)
    for (sid, _), x in w.items():
        total[sid] += x
    return {k: (x / total[k[0]] if total[k[0]] > 0 else 0.0) for k, x in w.items()}


def weighted_exact(preds: dict, ref: dict, w: dict) -> float:
    households = sorted({k[0] for k in ref})
    scores = []
    for sid in households:
        keys = [k for k in ref if k[0] == sid]
        if sum(w[k] for k in keys) <= 0:
            continue
        scores.append(
            sum(
                w[k] * row_hit_scores(k[1], ref[k], preds.get(k))["exact"] for k in keys
            )
        )
    return 100 * sum(scores) / len(scores)


def board_predictions(payload: dict) -> dict:
    board = defaultdict(dict)
    for sid, variables in payload["scenarioPredictions"].items():
        for var, models in variables.items():
            for model, v in models.items():
                board[model][(sid, var)] = (
                    v.get("prediction") if v.get("parsed") else None
                )
    return board


def rank(value: float, others: list[float]) -> int:
    return 1 + sum(other > value for other in others)


def group_rate(
    preds: dict, ref: dict, group: str, *, answered_only: bool = False
) -> float:
    keys = [k for k in ref if output_group_id(k[1]) == group]
    if answered_only:
        keys = [k for k in keys if preds.get(k) is not None]
    return (
        100
        * sum(row_hit_scores(k[1], ref[k], preds.get(k))["exact"] for k in keys)
        / len(keys)
    )


def facts(payload: dict, rows: list[dict], meta: dict) -> dict:
    ref, _ = references()
    gw = payload["globalWeights"]["household"]
    w = weights(ref.keys(), gw)
    board = board_predictions(payload)
    first = view(rows, payload, meta, retried=False)
    retried = view(rows, payload, meta, retried=True)
    board_exact = {m: weighted_exact(p, ref, w) for m, p in board.items()}
    others = list(board_exact.values())
    by_model = {
        r["model"]: r for r in payload["modelStats"] if r["condition"] == "no_tools"
    }

    def median_group(group: str) -> float:
        return statistics.median(group_rate(p, ref, group) for p in board.values())

    def models_right(key) -> int:
        return sum(
            row_hit_scores(key[1], ref[key], p.get(key))["exact"]
            for p in board.values()
        )

    by_unit = units(rows)
    first_refused = [u for u, a in by_unit.items() if not answered(a[1])]
    retry_answered = [
        u
        for u in first_refused
        if any(
            n + 1 in by_unit[u]
            and meets_contract(by_unit[u][n + 1], unit_requested(u, payload, meta))
            for n in ROUNDS
        )
    ]
    still_refused = [u for u in first_refused if u not in retry_answered]
    unanswered = [k for k in ref if retried.get(k) is None]

    no_pe = {
        k: v for k, v in ref.items() if output_group_id(k[1]) not in POLICYENGINE_GROUPS
    }
    w_no_pe = weights(no_pe.keys(), gw)
    no_pe_others = [weighted_exact(p, no_pe, w_no_pe) for p in board.values()]
    # Answered cells on both sides: America.gov's, and each board model's own.
    pe_gap = max(
        statistics.median(
            group_rate(p, ref, g, answered_only=True) for p in board.values()
        )
        - group_rate(retried, ref, g, answered_only=True)
        for g in POLICYENGINE_GROUPS
    )
    best = {**retried, **{k: ref[k] for k in unanswered}}

    def one(x: float) -> float:
        return float(f"{x:.1f}")

    return {
        "agovExact": one(weighted_exact(retried, ref, w)),
        "agovRank": rank(weighted_exact(retried, ref, w), others),
        "nRanked": len(board) + 1,
        "gpt55Exact": one(by_model["gpt-5.5"]["exact"]),
        "solExact": one(by_model["gpt-6-sol"]["exact"]),
        "households": len({k[0] for k in ref}),
        "charLimit": meta["message_limit_characters"],
        "agovFirstExact": one(weighted_exact(first, ref, w)),
        "agovFirstRank": rank(weighted_exact(first, ref, w), others),
        "firstRefusals": len(first_refused),
        "answeredOnRetry": len(retry_answered),
        "refusedThrice": sum(
            all(not answered(by_unit[u][a]) for a in (1, 2, 3) if a in by_unit[u])
            and len(by_unit[u]) == 3
            for u in still_refused
        ),
        "unansweredRate": one(100 * len(unanswered) / len(ref)),
        "fullModels": sum(r["nParsed"] == r["n"] for r in by_model.values()),
        "nModels": len(by_model),
        "fedTaxRate": one(
            group_rate(retried, ref, "federal_income_tax_before_refundable_credits")
        ),
        "fedTaxMedianRate": one(
            median_group("federal_income_tax_before_refundable_credits")
        ),
        "stateTaxRate": one(
            group_rate(retried, ref, "state_income_tax_before_refundable_credits")
        ),
        "stateTaxMedianRate": one(
            median_group("state_income_tax_before_refundable_credits")
        ),
        "snapRate": one(group_rate(retried, ref, "snap")),
        "snapMedianRate": one(median_group("snap")),
        "snap072": int(retried[("scenario_072", "snap")]),
        "snap072Models": models_right(("scenario_072", "snap")),
        "medicaidRate": one(group_rate(retried, ref, "person_medicaid_eligible")),
        "medicaidMedianRate": one(median_group("person_medicaid_eligible")),
        # Models right on both adults.
        "medicaid004Models": sum(
            all(
                row_hit_scores(v, ref[("scenario_004", v)], p.get(("scenario_004", v)))[
                    "exact"
                ]
                for v in ("head_medicaid_eligible", "spouse_medicaid_eligible")
            )
            for p in board.values()
        ),
        "peOutputs": len(POLICYENGINE_GROUPS),
        "peRefusals": sum(
            "PolicyEngine" in by_unit[u][1][0]["refusal_text"] for u in first_refused
        ),
        # A bound ("never more than X points below"), so it rounds up.
        "peMaxGap": f"{math.ceil(max(pe_gap, 0) * 10) / 10:.1f}",
        "noPeRank": rank(weighted_exact(retried, no_pe, w_no_pe), no_pe_others),
        "rowRepairChats": sum(
            len(unit_requested(u, payload, meta)) for u in still_refused
        ),
        "rowRepairMaxRate": one(weighted_exact(best, ref, w)),
    }


def _board_rows(predictions_path: Path):
    csv.field_size_limit(sys.maxsize)
    with gzip.open(predictions_path, "rt", encoding="utf-8", newline="") as source:
        yield from csv.DictReader(source)


def _unanswered(row: dict) -> bool:
    return row["prediction"] in ("", "nan", "None")


def board_refusals_citing_policyengine(predictions_path: Path) -> list[tuple]:
    """(model, household) pairs where a board model answered none of the household's
    outputs and its response refuses in a sentence that names PolicyEngine."""
    import re

    refusal = re.compile(
        r"\bI (?:can(?:no|')t|am unable|won't|will not)|"
        r"\bunable to (?:provide|compute|calculate|estimate)|"
        r"cannot (?:provide|run|compute|calculate|estimate|produce)",
        re.IGNORECASE,
    )
    policyengine = re.compile(r"policy\s*engine", re.IGNORECASE)
    outputs, unanswered, cites = defaultdict(int), defaultdict(int), set()
    for row in _board_rows(predictions_path):
        key = (row["model"], row["scenario_id"])
        outputs[key] += 1
        if not _unanswered(row):
            continue
        unanswered[key] += 1
        raw = row["raw_response"] or ""
        for match in refusal.finditer(raw):
            window = raw[max(0, match.start() - 120) : match.end() + 160]
            if policyengine.search(window):
                cites.add(key)
    return sorted(k for k in cites if unanswered[k] == outputs[k])


def board_cannot_run_policyengine(predictions_path: Path) -> list[tuple]:
    """(model, household) pairs whose response or explanations say the model
    cannot run, access, invoke or use PolicyEngine."""
    import re

    cannot = re.compile(
        r"(?:can(?:no|')t|cannot|unable to)\s+(?:\w+\s+){0,3}?"
        r"(?:run|access|invoke|use|call|execute)\s+(?:the\s+)?(?:\w+\s+){0,2}?"
        r"policy\s*engine",
        re.IGNORECASE,
    )
    found = set()
    for row in _board_rows(predictions_path):
        text = (row["raw_response"] or "") + " " + (row["explanation"] or "")
        if cannot.search(text):
            found.add((row["model"], row["scenario_id"]))
    return sorted(found)


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        build(Path(sys.argv[2]).expanduser())
    elif sys.argv[1:2] == ["facts"]:
        payload = json.load(gzip.open(RUN_DIR / "data.json.gz"))
        print(
            json.dumps(
                facts(payload, load_rows(), json.loads(META_PATH.read_text())), indent=1
            )
        )
    else:
        sys.exit(__doc__)
