"""Render the reference adversary's verdicts as the Markdown tables the README quotes.

Reads one judge's adversary directory (runs/claude), the tables
`policybench adversary-collect` wrote from it (runs/collected), the runner's
logs (runs/claude.run*.log) and any archived rejected attempts
(runs/rejected/run*/), and writes:

- verification/verdict_table.md: counts by class, every judge call, the
  table of every verdict other than reference_holds with its citations and
  the engine evidence, and the full verdict list;
- verification/verdict_counts.json: the same counts, machine-readable.

It reads verdicts and never writes one.

  uv run python reference_audit/2026-10-05-reference-adversary/scripts/verdict_table.py
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
RUNS = HERE / "runs"
ADV = RUNS / "claude"
COLLECTED = RUNS / "collected"
LABEL = "claude"
VERDICT_ORDER = (
    "reference_holds",
    "reference_wrong",
    "definition_mismatch",
    "prompt_ambiguous",
)
# A runner line that reports a finished judge call. "[FAIL] <case> stage <n>"
# with one of PRE_CALL_FAILURES happened before any call was made.
CALL_LINE = re.compile(
    r"^\[(ok|contaminated|invalid|FAIL)\] (\S+) stage ([12])(?: \((.*)\))?$"
)
PRE_CALL_FAILURES = (
    "no scratch directory",
    "scratch directory is inside a git repository",
    "no scratch file for the prompt",
    "could not copy and hash the prompt",
)


def _read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _fmt(value: object) -> str:
    if value in (None, ""):
        return "null"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number):
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _cell(text: object) -> str:
    """Text safe inside a Markdown table cell."""
    return " ".join(str(text or "").split()).replace("|", "\\|")


def _manifest() -> dict[str, dict]:
    rows = {}
    for line in (ADV / "cases.jsonl").read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["case_id"]] = row
    return rows


def judge_calls() -> dict:
    """Every judge call the runner logs report, by run, stage and outcome."""
    calls = []
    for log in sorted(RUNS.glob("claude.run*.log")):
        run = log.name.split(".")[1]
        for line in log.read_text().splitlines():
            match = CALL_LINE.match(line.strip())
            if not match:
                continue
            outcome, case_id, stage, detail = match.groups()
            if outcome == "FAIL" and any(
                reason in (detail or "") for reason in PRE_CALL_FAILURES
            ):
                continue
            calls.append(
                {
                    "run": run,
                    "case_id": case_id,
                    "stage": int(stage),
                    "outcome": outcome,
                    "detail": detail or "",
                }
            )
    by_outcome = Counter(call["outcome"] for call in calls)
    by_stage = Counter(f"stage{call['stage']}" for call in calls)
    by_run = Counter(call["run"] for call in calls)
    return {
        "total": len(calls),
        "by_outcome": dict(sorted(by_outcome.items())),
        "by_stage": dict(sorted(by_stage.items())),
        "by_run": dict(sorted(by_run.items())),
        "rejected": [c for c in calls if c["outcome"] != "ok"],
    }


def accepted_sidecars() -> dict:
    """Cost, time and models of the accepted calls, from their sidecars."""
    cost = 0.0
    duration_ms = 0
    models: Counter = Counter()
    accounts: Counter = Counter()
    n = 0
    for meta_path in sorted(ADV.glob("cases/*/*.meta.json")):
        meta = json.loads(meta_path.read_text())
        n += 1
        cost += float(meta.get("cost_usd") or 0.0)
        duration_ms += int(meta.get("duration_ms") or 0)
        for model in meta.get("judge_model_reported") or []:
            models[model] += 1
        auth = meta.get("judge_auth") or {}
        accounts[
            f"{auth.get('method')} (declared {meta.get('judge_account_declared')})"
        ] += 1
    return {
        "accepted_outputs": n,
        "reported_cost_usd": round(cost, 2),
        "judge_hours": round(duration_ms / 3_600_000, 2),
        "models_reported": dict(models),
        "logins": dict(accounts),
    }


def _citations(raw: str, limit: int = 3) -> str:
    try:
        citations = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    parts = []
    for citation in citations[:limit]:
        when = citation.get("published") or "undated"
        freeze = {True: "pre-freeze", False: "post-freeze", None: "freeze unknown"}[
            citation.get("pre_freeze")
        ]
        parts.append(
            f"[{_cell(citation.get('source'))}, {_cell(citation.get('pinpoint'))}]"
            f"({citation.get('url')}) ({_cell(when)}, {freeze})"
        )
    if len(citations) > limit:
        parts.append(f"and {len(citations) - limit} more")
    return "; ".join(parts)


def main() -> None:
    manifest = _manifest()
    verdicts = _read_csv(COLLECTED / f"adversary_{LABEL}_verdicts.csv")
    missing = _read_csv(COLLECTED / f"adversary_{LABEL}_missing.csv")
    inconsistent = _read_csv(COLLECTED / f"adversary_{LABEL}_inconsistent.csv")
    queue = _read_csv(COLLECTED / "adversary_adjudication_queue.csv")
    calls = judge_calls()
    sidecars = accepted_sidecars()

    counts = Counter(row["verdict"] for row in verdicts)
    class_counts = {name: counts.get(name, 0) for name in VERDICT_ORDER}
    class_counts["contaminated_or_invalid"] = len(missing)
    report = {
        "cases": len(manifest),
        "verdicts": len(verdicts),
        "class_counts": class_counts,
        "suggested_adjudication": dict(
            Counter(
                f"{row['verdict']}/{row['suggested_adjudication']}" for row in verdicts
            )
        ),
        "missing": missing,
        "inconsistent": inconsistent,
        "queued_for_adjudication": len(queue),
        "judge_calls": {k: v for k, v in calls.items() if k != "rejected"},
        "rejected_calls": calls["rejected"],
        "accepted_sidecars": sidecars,
    }
    (HERE / "verification" / "verdict_counts.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )

    lines = [
        "# Reference adversary verdicts",
        "",
        f"{len(manifest)} cases; {len(verdicts)} valid verdicts; "
        f"{len(queue)} queued for developer adjudication. "
        "Generated by `scripts/verdict_table.py` from `runs/collected/` "
        "(`policybench adversary-collect`) and the runner logs. "
        "A verdict changes no score.",
        "",
        "## Counts by class",
        "",
        "| Class | Cases |",
        "| --- | ---: |",
    ]
    for name, value in class_counts.items():
        lines.append(f"| {name} | {value} |")
    lines += [
        "",
        "## Judge calls",
        "",
        f"{calls['total']} judge calls in the runner logs: "
        + ", ".join(f"{k} {v}" for k, v in calls["by_outcome"].items())
        + "; by stage "
        + ", ".join(f"{k} {v}" for k, v in calls["by_stage"].items())
        + "; by run "
        + ", ".join(f"{k} {v}" for k, v in calls["by_run"].items())
        + ".",
        "",
        f"Accepted outputs with sidecars: {sidecars['accepted_outputs']}; "
        f"reported cost ${sidecars['reported_cost_usd']:,.2f} (the CLI's "
        f"API-price estimate; the calls bill a subscription login); "
        f"{sidecars['judge_hours']} judge-hours; models reported "
        + ", ".join(f"{k} ({v})" for k, v in sidecars["models_reported"].items())
        + "; logins "
        + ", ".join(f"{k} ({v})" for k, v in sidecars["logins"].items())
        + ".",
        "",
    ]
    if calls["rejected"]:
        lines += [
            "Rejected calls (the runner published nothing from them):",
            "",
            "| Run | Case | Stage | Outcome | Detail |",
            "| --- | --- | ---: | --- | --- |",
        ]
        for call in calls["rejected"]:
            lines.append(
                f"| {call['run']} | {call['case_id']} | {call['stage']} "
                f"| {call['outcome']} | {_cell(call['detail'])} |"
            )
        lines.append("")
    if missing:
        lines += [
            "Cases without a valid verdict:",
            "",
            "| Case | Reason |",
            "| --- | --- |",
        ]
        for row in missing:
            lines.append(f"| {row['case_id']} | {_cell(row['reason'])} |")
        lines.append("")
    if inconsistent:
        lines += [
            "Verdicts `adversary-collect` reports as inconsistent (kept in the "
            "table, flagged here):",
            "",
            "| Case | Problem |",
            "| --- | --- |",
        ]
        for row in inconsistent:
            lines.append(f"| {row['case_id']} | {_cell(row['problem'])} |")
        lines.append("")

    flagged = [row for row in verdicts if row["verdict"] != "reference_holds"]
    lines += [
        "## Every verdict other than reference_holds",
        "",
        "Engine evidence is the judge's `engine_step_at_issue`, read against "
        "the frozen derivation at `runs/claude/derivations/<case>.md`. "
        "Citations are the verdict's first three.",
        "",
        "| # | Cell | State | Reference | Consensus | Adversary | Verdict "
        "(suggestion, confidence) | Engine step at issue | Citations | Summary |",
        "| ---: | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |",
    ]
    for number, row in enumerate(flagged, start=1):
        case = manifest[row["case_id"]]
        lines.append(
            f"| {number} | {row['scenario_id']} {row['variable']} "
            f"| {case.get('state', '')} | {_fmt(row['reference_value'])} "
            f"| {_fmt(row['consensus_value'])} | {_fmt(row['independent_answer'])} "
            f"| {row['verdict']} ({row['suggested_adjudication']}, "
            f"{row['confidence']}) | {_cell(row['engine_step_at_issue'])} "
            f"| {_citations(row['citations'])} | {_cell(row['summary'])} |"
        )
    if not flagged:
        lines.append("| | none | | | | | | | | |")
    lines += [
        "",
        "## All verdicts",
        "",
        "| Cell | State | Reference | Consensus | Adversary | Stage 1 law supports "
        "| Verdict | Suggestion | Confidence | Stage-1 error named |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- |",
    ]
    for row in verdicts:
        case = manifest[row["case_id"]]
        lines.append(
            f"| {row['scenario_id']} {row['variable']} | {case.get('state', '')} "
            f"| {_fmt(row['reference_value'])} | {_fmt(row['consensus_value'])} "
            f"| {_fmt(row['independent_answer'])} | {row['stage1_law_supports']} "
            f"| {row['verdict']} | {row['suggested_adjudication']} "
            f"| {row['confidence']} | {'yes' if row['stage1_error'].strip() else ''} |"
        )
    out = HERE / "verification" / "verdict_table.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out} and verdict_counts.json: {json.dumps(class_counts)}")


if __name__ == "__main__":
    main()
