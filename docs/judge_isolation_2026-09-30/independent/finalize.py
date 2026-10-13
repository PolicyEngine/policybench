"""Finish the independent audit: score the main-session judge, write the final CSV and summaries.

The one verdict a main session wrote itself (no StructuredOutput) is bound by audit_indep.py to
the Bash heredoc that wrote it. Its "judge" is that session; this script lists the tool calls in
the judging segment (from the first read of the case prompt for judging to the verdict write),
classifies them, and records the earlier case-specific calls still in the session's context.

usage: python finalize.py <auto_dir> <out_dir>
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from transcripts import parse_claude  # noqa: E402

MAIN = Path("~/.claude/projects/-Users-maxghenis-Library-Application-Support-Claude-scratch-workspaces-ee3763f4-e7ea-4177-bcaf-1362266768c1-4457aa9d-2dc0-4bcf-a128-e50adae6be25-scratch-2026-09-22-c3da5e/3dd3d124-a1eb-44ed-ac89-ce3df9700101.jsonl")
MAIN_CASE = ("unified", "us__scenario_020__federal_income_tax_before_refundable_credits")
PROMPT = "unified_audit/audit/cases/us__scenario_020__federal_income_tax_before_refundable_credits/prompt.md"


def main_session_row(rec: dict, det: dict):
    ans = det["main_session_answer_call"]
    parsed = parse_claude(MAIN)
    calls = parsed["calls"]
    ans_i = next(i for i, c in enumerate(calls) if c["id"] == ans["id"])
    # segment start: the first call after the answer's predecessors that reads the case prompt to judge it
    start_i = ans_i
    while start_i > 0:
        c = calls[start_i - 1]
        cmd = (c["input"] or {}).get("command", "") if isinstance(c["input"], dict) else ""
        desc = (c["input"] or {}).get("description", "") if isinstance(c["input"], dict) else ""
        start_i -= 1
        if PROMPT in cmd and "to judge it" in desc:
            break
    seg = calls[start_i:ans_i + 1]
    prior = [c for c in calls[:start_i]
             if "scenario_020" in json.dumps(c["input"]) or "pb-judge-020" in json.dumps(c["input"])]
    touched = []
    for c in seg:
        inp = c["input"] or {}
        touched.append({"row": c["row"], "ts": c["ts"], "name": c["name"],
                        "description": inp.get("description"), "command": inp.get("command", "")[:600],
                        "is_answer_write": c["id"] == ans["id"]})
    det["calls"] = touched
    det["prior_case_calls_in_context"] = [
        {"row": c["row"], "ts": c["ts"], "name": c["name"], "description": (c["input"] or {}).get("description"),
         "command": (c["input"] or {}).get("command", "")[:300]} for c in prior]
    names = Counter(c["name"] for c in seg)
    assert set(names) == {"Bash"}, names
    rec["n_tool_calls"] = len(seg)
    rec["read_other_files"] = "yes"
    rec["searched"] = "no"
    rec["shell"] = "yes"
    rec["browsed"] = "no"
    rec["other_tools"] = "no"
    rec["affected"] = "yes"
    rec["notes"] = (
        f"Judge = orchestrating main session 3dd3d124 (no StructuredOutput). Judging segment = {len(seg)} Bash calls, "
        f"rows {seg[0]['row']}-{seg[-1]['row']} ({seg[0]['ts']} to {seg[-1]['ts']}): read its prompt with sed/awk; "
        "ran PolicyEngine on the case (triage/pe_case.py scenario_020 ... --calc adjusted_gross_income taxable_income "
        "salt_deduction net_investment_income_tax ...); rewrote the case's reference explanation in "
        "adds202609/reference_v12/us_case_reference_explanations.csv and the opus55 worktree's annotations CSV; read the "
        "previous verdict for this case from adds202609/verdicts-board42-b.json ('Read the previous 020 verdict to adapt'); "
        "then wrote verdict.json by heredoc and ran scripts/validate_verdict.py on it. "
        f"Earlier in the same context: {len(prior)} case-020 calls, incl. regen_references.py (grep scenario_020), "
        "restoring 020's reference explanation from _pre_conventions, and two aborted Subfleet judge lanes (pb-judge-020, 020b). "
        "Session context also held the repo work of the whole session (compaction at row 3211)."
    )
    return rec, det


def main():
    auto, out = Path(sys.argv[1]), Path(sys.argv[2])
    rows = list(csv.DictReader(open(auto / "verdicts_indep_auto.csv")))
    details = json.load(open(auto / "details_auto.json"))
    dmap = {(d["tree"], d["case_id"]): d for d in details}
    final = []
    for r in rows:
        d = dmap[(r["tree"], r["case_id"])]
        if (r["tree"], r["case_id"]) == MAIN_CASE:
            r, d = main_session_row(r, d)
            dmap[(r["tree"], r["case_id"])] = d
        if r["runner"] == "scripts/run_audit_codex.sh" and d["meta"].get("judged_at_utc", "").startswith("2026-08-18T01:27:48"):
            r["notes"] += ("; sidecar judged_at_utc is the 2026-08-18T01:27:48Z restore time: session 3c78d187 (line 19580) "
                           "copied this verdict.json back from Time Machine snapshot 2026-08-17-194721 after #151's prompt "
                           "change invalidated banked verdicts; the verdict was judged before 19:47 local 2026-08-17")
        if r["binding_method"] == "missing" and r["runner"] == "scripts/run_audit_codex.sh":
            r["notes"] += ("; WHY MISSING: at 2026-08-18T01:25:58Z session 3c78d187 (~/.claude/projects/-Users-maxghenis/"
                           "3c78d187-d2fd-48e8-bd4e-370d86004afd.jsonl line 19542) ran pkill -f run_audit_codex, killing an in-flight "
                           "re-judge of this case that had already overwritten codex.log; at 01:27:48Z (line 19580) it restored "
                           "verdict.json from Time Machine snapshot 2026-08-17-194721. The published verdict's own codex.log "
                           "existed only in that snapshot; today the only local snapshot is 2026-09-30 and /Volumes/TimeMachine "
                           "is not readable from this session. The sidecar's backfilled_from=codex.log and model point at the "
                           "killed re-run's log (its answer, which the killed run never published, shows no exec block)")
            if (Path("~/PolicyEngine/policybench/results/local/unified_audit/audit/cases") / r["case_id"] / "verdict.json.tmp").exists():
                r["notes"] += "; the killed re-run's -o output survives as unified/<case>/verdict.json.tmp (equal to codex.log's answer)"
        if (r["tree"], r["case_id"]) in (("seed", "us__scenario_086__federal_refundable_credits"),
                                         ("unified", "us__scenario_086__federal_refundable_credits")):
            r["notes"] = ("LEAK DETAIL: Grep content output (not only Read) put prior-audit text in front of the delegates: "
                          "annotations/.../us_audit_row_annotations.csv rows 5559 (scenario_086 federal_income_tax row) and 5581 "
                          "(scenario_086 federal_refundable_credits claude-opus-4.7 diagnosis), us_case_notes.csv, "
                          "us_case_reference_explanations.csv, paper/snapshot/20260501/runs/.../reference_outputs.csv and data.json; "
                          "the TaskOutput result the judge read cites us_audit_row_annotations.csv line 5559 and PolicyEngine's "
                          "trace. Runner --disallowedTools blocked Bash/Edit/Write/NotebookEdit/WebFetch/WebSearch/Agent only, so "
                          "Workflow, ToolSearch, TaskOutput, Read, Grep, Glob stayed available; delegates' ToolSearch select:Bash "
                          "found nothing. " + r["notes"])
        ctx = d.get("context_injections") or []
        if ctx:
            r["notes"] += "; CONTEXT (not a tool call): " + ", ".join(sorted(set(ctx)))
        final.append(r)

    fields = ["tree", "case_id", "wave", "runner", "transcript_path", "binding_method", "n_tool_calls",
              "read_other_files", "searched", "shell", "browsed", "other_tools", "affected",
              "live_in_published_release", "notes"]
    with open(out / "verdicts_indep.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in final:
            w.writerow({k: r[k] for k in fields})
    json.dump([dmap[(r["tree"], r["case_id"])] for r in final], open(out / "verdicts_indep_details.json", "w"),
              indent=1, default=str)

    # summaries
    tab = defaultdict(Counter)
    for r in final:
        k = (r["tree"], r["wave"])
        tab[k]["verdicts"] += 1
        tab[k]["bound"] += r["binding_method"] not in ("missing", "ambiguous")
        tab[k]["missing"] += r["binding_method"] == "missing"
        tab[k]["affected"] += r["affected"] == "yes"
        tab[k]["unknown"] += r["affected"] == "unknown"
        tab[k]["live"] += r["live_in_published_release"] == "yes"
        tab[k]["live_affected"] += r["live_in_published_release"] == "yes" and r["affected"] == "yes"
        tab[k]["live_missing"] += r["live_in_published_release"] == "yes" and r["binding_method"] == "missing"
    lines = ["| tree | wave | verdicts | bound | missing | affected | live | live & affected | live & missing |",
             "|---|---|---|---|---|---|---|---|---|"]
    order = ["codex", "2026-09-05", "2026-09-22", "2026-09-29"]
    for tree in ("seed", "unified"):
        for wv in order:
            c = tab.get((tree, wv))
            if not c:
                lines.append(f"| {tree} | {wv} | 0 | 0 | 0 | 0 | 0 | 0 | 0 |")
                continue
            lines.append(f"| {tree} | {wv} | {c['verdicts']} | {c['bound']} | {c['missing']} | {c['affected']} | "
                         f"{c['live']} | {c['live_affected']} | {c['live_missing']} |")
    (out / "summary_table.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    anomalies = Counter()
    for d in dmap.values():
        for a in d.get("anomalies", []):
            anomalies[(d["tree"], d["wave"], re.sub(r"\d+", "#", a)[:140])] += 1
    print()
    for k, v in sorted(anomalies.items()):
        print(v, k)


if __name__ == "__main__":
    main()
