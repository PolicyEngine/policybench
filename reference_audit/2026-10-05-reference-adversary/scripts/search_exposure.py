"""Audit every Claude transcript of this pass for search results from a blocked
source, and compare the re-judged cases with their originals.

The code review of PR #200 found that WebSearch results listing PolicyEngine and
GitHub pages reached the judges. The Claude runner denies the blocked domains to
WebFetch only, and its transcript audit read each search's query but not its
results. `claude_transcript_audit` now reads the results too. This script runs
it over every transcript in runs/claude (the 52 cases) and runs/claude-rejudge
(the cases the audit flags, re-judged with the source rule that asks for
blocked_domains on every search), and writes:

- verification/search_exposure.json: for each run, the transcripts audited, the
  searches made and how many passed blocked_domains, and every problem the
  audit finds, with the query and what its result exposed; for each re-judged
  case, its original and re-judged stage 1 and verdict side by side;
- verification/search_exposure.md: the same as tables;
- runs/rejudge_flags.json: consensus_flags.json restricted to the cells whose
  original stage 1 or verdict the audit flags. `policybench adversary-prepare`
  read it to build runs/claude-rejudge.

It reads transcripts and outputs and never writes one.

  uv run python reference_audit/2026-10-05-reference-adversary/scripts/search_exposure.py
"""

from __future__ import annotations

import difflib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from policybench.reference_adversary import BLOCKED_DOMAINS, claude_transcript_audit

HERE = Path(__file__).resolve().parents[1]
RUNS = HERE / "runs"
OUT = HERE / "verification"
ORIGINAL = RUNS / "claude"
REJUDGE = RUNS / "claude-rejudge"
FLAGS = HERE / "consensus_flags.json"
REJUDGE_FLAGS = RUNS / "rejudge_flags.json"
# (transcript stage, its prompt, its output)
STAGES = (
    ("stage1", "stage1_prompt.md", "stage1.json"),
    ("stage2", "stage2_prompt.md", "verdict.json"),
)
SEARCH_PROBLEM = "a search returned a blocked source: "
STAGE1_FIELDS = ("law_supports", "independent_answer", "confidence")
VERDICT_FIELDS = ("verdict", "confidence", "suggested_adjudication")


def _source(exposed: str) -> str:
    """The kind of blocked source one exposure is: a host, a GitHub owner, or
    the name a result's text gave."""
    if exposed.startswith("text names "):
        return exposed
    parts = urlsplit(exposed)
    host = (parts.hostname or "").lower()
    if host in ("github.com", "raw.githubusercontent.com"):
        owner = parts.path.strip("/").split("/")[0]
        return f"github.com/{owner}" if owner else "github.com"
    return host


def _web_searches(transcript: str) -> list[dict]:
    """The input of every WebSearch call in a transcript."""
    inputs = []
    for line in transcript.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = (event.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if (
                isinstance(part, dict)
                and part.get("type") == "tool_use"
                and part.get("name") == "WebSearch"
            ):
                inputs.append(part.get("input") or {})
    return inputs


def audit_run(adversary: Path) -> dict:
    """Every transcript of one adversary directory, through the current audit."""
    transcripts = 0
    searches = 0
    with_blocked_domains = 0
    with_every_domain = 0
    flagged = []
    for case_dir in sorted((adversary / "cases").iterdir()):
        for stage, prompt, _ in STAGES:
            path = case_dir / f"{stage}.claude.transcript.jsonl"
            if not path.is_file():
                continue
            transcripts += 1
            text = path.read_text()
            for search in _web_searches(text):
                searches += 1
                blocked = set(search.get("blocked_domains") or ())
                with_blocked_domains += bool(blocked)
                with_every_domain += set(BLOCKED_DOMAINS) <= blocked
            problems, _, _ = claude_transcript_audit(
                text, (case_dir / prompt).read_text()
            )
            if not problems:
                continue
            exposures, other = [], []
            for problem in problems:
                if problem.startswith(SEARCH_PROBLEM):
                    query, _, exposed = problem[len(SEARCH_PROBLEM) :].rpartition(
                        " -> "
                    )
                    items = exposed.split(", ")
                    exposures.append(
                        {
                            "query": query,
                            "exposed": items,
                            "sources": sorted({_source(item) for item in items}),
                        }
                    )
                else:
                    other.append(problem)
            flagged.append(
                {
                    "case_id": case_dir.name,
                    "stage": stage,
                    "exposed_searches": exposures,
                    "other_problems": other,
                }
            )
    sources = Counter(
        source
        for row in flagged
        for exposure in row["exposed_searches"]
        for source in exposure["sources"]
    )
    return {
        "adversary_dir": adversary.relative_to(HERE).as_posix(),
        "transcripts": transcripts,
        "searches": searches,
        "searches_with_blocked_domains": with_blocked_domains,
        "searches_with_every_blocked_domain": with_every_domain,
        "flagged_transcripts": len(flagged),
        "flagged_cases": sorted({row["case_id"] for row in flagged}),
        "exposed_searches": sum(len(row["exposed_searches"]) for row in flagged),
        "exposed_searches_by_source": dict(sorted(sources.items())),
        "flagged": flagged,
    }


def _pick(path: Path, fields: tuple[str, ...]) -> dict:
    document = json.loads(path.read_text())
    return {field: document.get(field) for field in fields}


def _changed_lines(before: Path, after: Path) -> list[str]:
    """The lines a re-judged prompt replaced, removed or added."""
    return [
        line
        for line in difflib.unified_diff(
            before.read_text().splitlines(),
            after.read_text().splitlines(),
            lineterm="",
            n=0,
        )
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]


def compare(original_audit: dict) -> list[dict]:
    """Each re-judged case's original and re-judged stage 1 and verdict."""
    exposed_stages: dict[str, list[str]] = {}
    for row in original_audit["flagged"]:
        exposed_stages.setdefault(row["case_id"], []).append(row["stage"])
    rows = []
    for case_dir in sorted((REJUDGE / "cases").iterdir()):
        before = ORIGINAL / "cases" / case_dir.name
        stage1_prompt = _changed_lines(
            before / "stage1_prompt.md", case_dir / "stage1_prompt.md"
        )
        stage1 = {
            "original": _pick(before / "stage1.json", STAGE1_FIELDS),
            "rejudge": _pick(case_dir / "stage1.json", STAGE1_FIELDS),
        }
        verdict = {
            "original": _pick(before / "verdict.json", VERDICT_FIELDS),
            "rejudge": _pick(case_dir / "verdict.json", VERDICT_FIELDS),
        }
        rows.append(
            {
                "case_id": case_dir.name,
                "original_exposed_stages": exposed_stages.get(case_dir.name, []),
                # One line replaced: the source rule, which now asks for
                # blocked_domains on every search. Nothing else differs.
                "stage1_prompt_changed_lines": stage1_prompt,
                "stage1": stage1,
                "verdict": verdict,
                "verdict_unchanged": verdict["original"]["verdict"]
                == verdict["rejudge"]["verdict"],
                "stage1_law_supports_unchanged": stage1["original"]["law_supports"]
                == stage1["rejudge"]["law_supports"],
            }
        )
    return rows


def rejudge_flags(original_audit: dict) -> dict:
    """consensus_flags.json restricted to the cells the audit flags."""
    manifest = {}
    for line in (ORIGINAL / "cases.jsonl").read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            manifest[row["case_id"]] = (row["scenario_id"], row["variable"])
    cells = {manifest[case_id] for case_id in original_audit["flagged_cases"]}
    flags = json.loads(FLAGS.read_text())
    flags["flags"] = [
        flag for flag in flags["flags"] if (flag["scenario_id"], flag["variable"]) in cells
    ]
    flags["flagged_cells"] = len(flags["flags"])
    flags["rejudge_note"] = (
        f"The {len(flags['flags'])} cells whose committed stage 1 or verdict a "
        "search result exposed to a blocked source "
        "(verification/search_exposure.json); a subset of consensus_flags.json."
    )
    return flags


def _cell(text: object) -> str:
    return " ".join(str(text if text is not None else "").split()).replace("|", "\\|")


def _stage1(row: dict) -> str:
    return f"{row['law_supports']}, {row['independent_answer']:g} ({row['confidence']})"


def render(report: dict) -> str:
    original, rejudge = report["runs"]["claude"], report["runs"]["claude-rejudge"]
    lines = [
        "# Search results from blocked sources",
        "",
        "Written by `scripts/search_exposure.py`, which runs the current "
        "`claude_transcript_audit` over every transcript. WebSearch has no deny "
        "rule, so its results reach the judge; the audit now rejects an output "
        "whose search results list a URL on a blocked domain "
        f"({', '.join(BLOCKED_DOMAINS)}) or name PolicyEngine or PolicyBench.",
        "",
        "| Run | Transcripts | Searches | With blocked_domains | Flagged transcripts | Flagged cases | Exposed searches |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, run in report["runs"].items():
        lines.append(
            f"| `runs/{name}` | {run['transcripts']} | {run['searches']} | "
            f"{run['searches_with_blocked_domains']} | {run['flagged_transcripts']} | "
            f"{len(run['flagged_cases'])} | {run['exposed_searches']} |"
        )
    lines += [
        "",
        "Exposed searches in `runs/claude` by blocked source (a search can expose "
        "more than one):",
        "",
        "| Source | Exposed searches |",
        "|---|---:|",
    ]
    for source, count in original["exposed_searches_by_source"].items():
        lines.append(f"| {_cell(source)} | {count} |")
    lines += [
        "",
        "## Flagged transcripts in `runs/claude`",
        "",
        "| Case | Stage | Query | Exposed |",
        "|---|---|---|---|",
    ]
    for row in original["flagged"]:
        for exposure in row["exposed_searches"]:
            lines.append(
                f"| {row['case_id']} | {row['stage']} | {_cell(exposure['query'])} | "
                f"{_cell(', '.join(exposure['exposed']))} |"
            )
        for problem in row["other_problems"]:
            lines.append(f"| {row['case_id']} | {row['stage']} | | {_cell(problem)} |")
    lines += [
        "",
        f"`runs/claude-rejudge`: {rejudge['flagged_transcripts']} flagged transcripts.",
        "",
        "## Re-judged cases",
        "",
        "Each re-judged stage-1 prompt differs from the original in one line, the "
        "source rule, which now asks for blocked_domains on every search.",
        "",
        "| Case | Exposed (original) | Stage 1: original | Stage 1: re-judged | Verdict: original | Verdict: re-judged |",
        "|---|---|---|---|---|---|",
    ]
    for row in report["rejudged"]:
        verdict = row["verdict"]
        lines.append(
            f"| {row['case_id']} | {', '.join(row['original_exposed_stages'])} | "
            f"{_stage1(row['stage1']['original'])} | {_stage1(row['stage1']['rejudge'])} | "
            f"{verdict['original']['verdict']} ({verdict['original']['confidence']}) | "
            f"{verdict['rejudge']['verdict']} ({verdict['rejudge']['confidence']}) |"
        )
    unchanged = sum(row["verdict_unchanged"] for row in report["rejudged"])
    lines += [
        "",
        f"Verdict unchanged in {unchanged} of {len(report['rejudged'])} re-judged cases.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    original = audit_run(ORIGINAL)
    rejudge = audit_run(REJUDGE)
    rejudged = compare(original)
    if {row["case_id"] for row in rejudged} != set(original["flagged_cases"]):
        raise SystemExit(
            "runs/claude-rejudge does not hold exactly the cases the audit flags"
        )
    for row in rejudged:
        changed = row["stage1_prompt_changed_lines"]
        if len(changed) != 2 or "blocked_domains" not in changed[1]:
            raise SystemExit(f"{row['case_id']}: stage 1 prompt changed beyond the source rule")
    report = {
        "runs": {"claude": original, "claude-rejudge": rejudge},
        "rejudged": rejudged,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "search_exposure.json").write_text(json.dumps(report, indent=2) + "\n")
    (OUT / "search_exposure.md").write_text(render(report))
    REJUDGE_FLAGS.write_text(json.dumps(rejudge_flags(original), indent=2))
    print(
        f"runs/claude: {original['flagged_transcripts']} of {original['transcripts']} "
        f"transcripts flagged in {len(original['flagged_cases'])} cases; "
        f"runs/claude-rejudge: {rejudge['flagged_transcripts']} of "
        f"{rejudge['transcripts']}; verdict unchanged in "
        f"{sum(row['verdict_unchanged'] for row in rejudged)} of {len(rejudged)}"
    )


if __name__ == "__main__":
    main()
