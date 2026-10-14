"""Independent judge-isolation audit of the published PolicyBench verdicts.

For every verdict in the seed (published 20260929) and unified audit trees:
  1. bind it by content to the transcript that produced it
       codex runner  -> the case's codex.log final message == verdict (parsed JSON)
       Claude judges -> a StructuredOutput tool_use whose input == verdict (parsed JSON),
                        looked up in the index built by build_index.py
       fallback      -> a Bash heredoc / Write payload in a main-session transcript == verdict
  2. list every tool call the judge (and any delegate) made, except the StructuredOutput answer
  3. classify: read_other_files / searched / shell / browsed / other_tools -> affected

Also checks sidecar hashes, sidecar ids vs the bound transcript, and whether the prompt the
judge actually saw equals the published prompt.md.

usage: python audit_indep.py <so_index.json> <out_dir>
Read-only with respect to both audit trees and the repos.
"""
from __future__ import annotations

import csv
import difflib
import glob
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from transcripts import canon, parse_claude, parse_codex, reconstruct_read  # noqa: E402

TREES = {
    "seed": Path("~/PolicyEngine/policybench-wt/adds0928-stage2/results/local/adds0928-v3/audit/cases"),
    "unified": Path("~/PolicyEngine/policybench/results/local/unified_audit/audit/cases"),
}
MAIN_SESSIONS = [
    Path("~/.claude/projects/-Users-maxghenis-Library-Application-Support-Claude-scratch-workspaces-ee3763f4-e7ea-4177-bcaf-1362266768c1-4457aa9d-2dc0-4bcf-a128-e50adae6be25-scratch-2026-09-22-c3da5e/3dd3d124-a1eb-44ed-ac89-ce3df9700101.jsonl"),
    Path("~/.claude/projects/-Users-maxghenis/3c78d187-d2fd-48e8-bd4e-370d86004afd.jsonl"),
]
HOME = os.path.expanduser("~")

SEARCH_TOOLS = {"Grep", "Glob", "LS"}
SHELL_TOOLS = {"Bash", "BashOutput", "KillShell", "KillBash", "PowerShell", "Monitor"}
BROWSE_TOOLS = {"WebFetch", "WebSearch", "web_search", "web_fetch"}
READ_TOOLS = {"Read", "NotebookRead"}
DELEGATE_TOOLS = {"Agent", "Task", "Workflow"}


def short(p: str) -> str:
    return p.replace(HOME, "~")


def wave_of(meta: dict) -> str:
    runner = meta.get("judge_runner", "")
    day = (meta.get("judged_at_utc") or "")[:10]
    if runner == "scripts/run_audit_codex.sh":
        return "codex"
    if day == "2026-09-05":
        return "2026-09-05"
    if "2026-09-22" <= day <= "2026-09-24":
        return "2026-09-22"
    if "2026-09-28" <= day <= "2026-09-30":
        return "2026-09-29"
    return f"unassigned({day})"


def classify_call(call: dict, case_id: str) -> str:
    name = call["name"] or ""
    inp = call.get("input") or {}
    if name == "StructuredOutput":
        return "structured_output"
    if name in READ_TOOLS:
        fp = inp.get("file_path") or inp.get("notebook_path") or ""
        if fp.endswith(f"/cases/{case_id}/prompt.md"):
            return "own_prompt"
        return "read_other"
    if name in SEARCH_TOOLS:
        return "search"
    if name in SHELL_TOOLS:
        return "shell"
    low = name.lower()
    if name in BROWSE_TOOLS or low.startswith("mcp__claude-in-chrome") or low.startswith("mcp__chrome") \
            or "browser" in low or "playwright" in low or low.startswith("mcp__computer-use"):
        return "browse"
    return "other"


def describe_call(call: dict) -> str:
    inp = call.get("input") or {}
    name = call["name"]
    if name in READ_TOOLS:
        s = f"Read {inp.get('file_path') or inp.get('notebook_path')}"
        if inp.get("offset") or inp.get("limit"):
            s += f" (offset={inp.get('offset')}, limit={inp.get('limit')})"
        return s
    if name == "Grep":
        return f"Grep pattern={inp.get('pattern')!r} path={inp.get('path')} glob={inp.get('glob')}"
    if name == "Glob":
        return f"Glob pattern={inp.get('pattern')!r} path={inp.get('path')}"
    if name == "LS":
        return f"LS {inp.get('path')}"
    if name in SHELL_TOOLS:
        return f"{name}: {(inp.get('command') or json.dumps(inp))[:400]}"
    if name in ("WebFetch", "WebSearch"):
        return f"{name} {inp.get('url') or inp.get('query')}"
    return f"{name} {json.dumps(inp)[:300]}"


# ----------------------------------------------------------------- workflow journals

_journal_cache: dict[str, dict] = {}


def journal_info(agent_path: Path):
    """label/phase/key for the agent from its workflow journal, if any."""
    wf_dir = agent_path.parent
    j = wf_dir / "journal.jsonl"
    if not j.exists():
        return None
    key = str(j)
    if key not in _journal_cache:
        info = {}
        results = {}
        for ln in open(j, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            d = json.loads(ln)
            if d.get("type") == "started" and d.get("agentId"):
                info[d["agentId"]] = {"label": d.get("label"), "phase": d.get("phase"), "key": d.get("key")}
            if d.get("type") == "result" and d.get("agentId"):
                results[d["agentId"]] = d.get("result")
        for aid, r in results.items():
            info.setdefault(aid, {})["result_canon"] = canon(r) if r is not None else None
        _journal_cache[key] = info
    aid = agent_path.name[len("agent-"):-len(".jsonl")]
    rec = dict(_journal_cache[key].get(aid, {}))
    rec["workflow_id"] = wf_dir.name
    rec["agent_id"] = aid
    return rec


# ----------------------------------------------------------------- delegates

def find_delegates(parsed: dict, transcript: Path):
    """Transcripts of Agent/Task/Workflow delegates launched by this judge."""
    out = []
    # session dir: .../<proj>/<sid>/subagents/... for subagents, or .../<proj>/<sid>.jsonl for sessions
    p = transcript
    if "subagents" in p.parts:
        sdir = Path(*p.parts[: p.parts.index("subagents")])
    else:
        sdir = p.with_suffix("")
    for c in parsed["calls"]:
        if c["name"] not in DELEGATE_TOOLS:
            continue
        res = parsed["results"].get(c["id"], {}).get("text", "")
        ids = set(re.findall(r"agentId:\s*([a-z0-9]+)", res)) | set(re.findall(r"agent-([a-z0-9]+)", res))
        wfs = set(re.findall(r"(wf_[0-9a-f]{8}-[0-9a-f]{3})", res))
        found = []
        for aid in ids:
            found += glob.glob(str(sdir / "subagents" / "**" / f"agent-{aid}.jsonl"), recursive=True)
        for wf in wfs:
            found += glob.glob(str(sdir / "subagents" / "workflows" / wf / "agent-*.jsonl"))
        out.append({"call": c["id"], "tool": c["name"], "agent_ids": sorted(ids), "workflows": sorted(wfs),
                    "transcripts": sorted(set(found))})
    return out


# ----------------------------------------------------------------- prompt fidelity

def compare_text(seen: str, published: str) -> tuple[str, list[str]]:
    a = seen.strip().split("\n")
    b = published.strip().split("\n")
    if a == b:
        return "identical", []
    diff = [ln for ln in difflib.unified_diff(a, b, lineterm="", n=0) if not ln.startswith(("---", "+++", "@@"))]
    return f"differs({sum(1 for d in diff if d.startswith('-'))} lines only-seen, {sum(1 for d in diff if d.startswith('+'))} lines only-published)", diff[:12]


def compare_read(lines_seen: dict, published: str):
    pub = published.split("\n")
    if pub and pub[-1] == "":
        pub = pub[:-1]
    n = len(pub)
    covered = [i for i in range(1, n + 1) if i in lines_seen]
    mism, trunc = [], 0
    for i in covered:
        s, p = lines_seen[i], pub[i - 1]
        if s == p:
            continue
        # Read truncates very long lines; accept a strict prefix
        if len(s) < len(p) and p.startswith(s.rstrip(".… ")[: max(0, len(s) - 40)]):
            trunc += 1
            continue
        mism.append(i)
    extra = [i for i in lines_seen if i > n]
    if not covered:
        return "no-content-returned", []
    status = "identical"
    if len(covered) < n:
        status = f"partial-read({len(covered)}/{n} lines)"
    if trunc:
        status += f"+{trunc}-truncated-lines-prefix-match"
    if mism or extra:
        status = f"differs({len(mism)} changed, {len(extra)} extra lines)"
    detail = [f"L{i}: seen={lines_seen[i][:160]!r} published={pub[i-1][:160]!r}" for i in mism[:4]]
    return status, detail


# ----------------------------------------------------------------- main

def main():
    index = json.load(open(sys.argv[1]))["index"]
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    verdicts = []
    for tree, root in TREES.items():
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            vb = (d / "verdict.json").read_bytes()
            verdicts.append({
                "tree": tree, "case_id": d.name, "dir": d,
                "vbytes": vb, "v": json.loads(vb),
                "meta": json.loads((d / "verdict.meta.json").read_text()),
                "prompt": (d / "prompt.md").read_text(encoding="utf-8"),
                "files": sorted(os.listdir(d)),
            })
    seed_bytes = {r["case_id"]: r["vbytes"] for r in verdicts if r["tree"] == "seed"}

    main_parsed = {}
    rows, details = [], []
    for r in verdicts:
        meta, v, case_id = r["meta"], r["v"], r["case_id"]
        wave = wave_of(meta)
        runner = meta.get("judge_runner", "")
        notes, anomalies = [], []
        rec = {
            "tree": r["tree"], "case_id": case_id, "wave": wave, "runner": runner,
            "transcript_path": "", "binding_method": "", "n_tool_calls": "",
            "read_other_files": "", "searched": "", "shell": "", "browsed": "", "other_tools": "",
            "affected": "unknown",
            "live_in_published_release": "yes" if r["tree"] == "seed" else (
                "yes" if seed_bytes.get(case_id) == r["vbytes"] else "no"),
        }
        det = {"tree": r["tree"], "case_id": case_id, "wave": wave, "runner": runner, "meta": meta,
               "calls": [], "delegates": [], "anomalies": anomalies}

        # sidecar integrity
        vsha = hashlib.sha256(r["vbytes"]).hexdigest()
        if meta.get("verdict_sha256") != vsha:
            anomalies.append(f"sidecar verdict_sha256 {meta.get('verdict_sha256')} != sha256(verdict.json) {vsha}")
        canonical_bytes = json.dumps(v, indent=2, sort_keys=True).encode()
        # codex -o keeps the raw final message, so only Claude-written verdicts must be canonical
        if canonical_bytes != r["vbytes"] and runner != "scripts/run_audit_codex.sh":
            anomalies.append("verdict.json bytes are not json.dumps(v, indent=2, sort_keys=True)")
        psha = hashlib.sha256(r["prompt"].encode("utf-8")).hexdigest()
        if meta.get("prompt_sha256") and meta["prompt_sha256"] != psha:
            anomalies.append(f"sidecar prompt_sha256 != sha256(published prompt.md)")
        if "verdict.json.tmp" in r["files"]:
            anomalies.append("stray verdict.json.tmp in case dir")
            tmpb = (r["dir"] / "verdict.json.tmp").read_bytes()
            try:
                tv = json.loads(tmpb)
                det["tmp_equals_verdict"] = tv == v
                if tv != v:
                    anomalies.append("verdict.json.tmp differs from verdict.json")
            except Exception:
                anomalies.append("verdict.json.tmp unparseable")

        calls = []
        bound = False
        if runner == "scripts/run_audit_codex.sh":
            log = r["dir"] / "codex.log"
            if not log.exists():
                rec["binding_method"] = "missing"
                notes.append("no codex.log in case dir")
            else:
                cx = parse_codex(log)
                det["codex"] = {k: cx[k] for k in ("header", "blocks", "execs", "tool_markers", "stderr_noise_in_prompt")}
                if cx["final_obj"] == v:
                    bound = True
                    rec["transcript_path"] = str(log)
                    rec["binding_method"] = "codex.log final message (after 'tokens used') == verdict.json as parsed JSON"
                    if cx["last_msg_obj"] is not None and cx["last_msg_obj"] != v:
                        anomalies.append("codex.log 'codex' block message differs from final stdout message")
                    for e in cx["execs"]:
                        calls.append({"name": "exec", "input": {"command": e}, "cls": "shell"})
                    for m in cx["tool_markers"]:
                        calls.append({"name": "codex-marker", "input": {"line": m}, "cls": "other"})
                    extra_blocks = [b for b in cx["blocks"] if b not in ("user", "codex", "tokens used", "exec")]
                    if extra_blocks:
                        anomalies.append(f"codex.log has unexpected blocks {extra_blocks}")
                    if cx["blocks"] != ["user", "codex", "tokens used"]:
                        notes.append(f"codex blocks: {cx['blocks']}")
                    st, diff = compare_text(cx["prompt"] or "", r["prompt"])
                    det["prompt_fidelity"] = st
                    det["prompt_diff"] = diff
                    wd = cx["header"].get("workdir")
                    det["workdir"] = wd
                    notes.append(f"workdir={wd}; sandbox={cx['header'].get('sandbox')}; model={cx['header'].get('model')}")
                    if st != "identical":
                        anomalies.append(f"prompt in codex.log vs published prompt.md: {st}")
                else:
                    rec["binding_method"] = "missing"
                    notes.append(
                        "case codex.log holds a different run's answer (its final message != verdict.json; "
                        f"log session {cx['header'].get('session id')}); no other codex.log copy under "
                        "policybench*/results/**/audit/cases holds this verdict; codex ran --ephemeral so no rollout; "
                        "Aug 17-18 rollouts in ~/.subfleet/lanes/codex-*/sessions and Logpile codex hold no audit prompt")
        else:
            hits = [h for h in index.get(canon(v), []) if "/logpile/" not in h["path"]]
            lp = [h for h in index.get(canon(v), []) if "/logpile/" in h["path"]]
            paths = sorted({h["path"] for h in hits})
            if len(paths) == 1:
                bound = True
                tpath = Path(paths[0])
                h = hits[0]
                rec["transcript_path"] = str(tpath)
                rec["binding_method"] = ("StructuredOutput tool_use input == verdict.json as parsed JSON "
                                         "(unique match among all indexed Claude transcripts)")
                if lp:
                    notes.append(f"Logpile copy also holds it: {short(lp[0]['path'])}")
                parsed = parse_claude(tpath)
                det["transcript"] = {k: parsed[k] for k in ("session_ids", "agent_ids", "cwds", "models", "first_ts", "last_ts", "n_rows", "sidechain_rows")}
                det["injected_attachments"] = Counter(parsed["injected"])
                # context the harness put in front of the judge besides its prompt (not tool calls)
                ctx = []
                for row in __import__("transcripts").load_lines(tpath):
                    a = row.get("attachment") if row.get("type") == "attachment" else None
                    if a and a.get("type") == "nested_memory":
                        ctx.append(f"nested_memory {short(a.get('path', ''))}")
                    if a and a.get("type") == "session_context" and (a.get("context") or {}).get("gitStatus"):
                        gs = a["context"]["gitStatus"]
                        br = re.search(r"Current branch: (\S+)", gs)
                        commits = re.findall(r"^[0-9a-f]{7,} (.+)$", gs, re.M)
                        ctx.append(f"gitStatus of {parsed['cwds'][0] if parsed['cwds'] else '?'} (branch "
                                   f"{br.group(1) if br else '?'}; recent commits: {' / '.join(c_[:70] for c_ in commits[:3])})")
                if any("<command-name>workflow-authoring</command-name>" in s_ for _, s_ in parsed["user_strings"]):
                    ctx.append("workflow-authoring skill text injected as a user turn")
                relay = [s_ for _, s_ in parsed["user_strings"] if s_.startswith("[Workflow harness — user request]")]
                if relay:
                    rq = relay[0].split("this request wins:", 1)[-1].strip()
                    ctx.append(f"relayed parent user request: {rq[:120]!r}")
                if parsed["injected"].count("instructions"):
                    ctx.append("CLAUDE.md instructions attachment")
                det["context_injections"] = ctx
                # identity checks
                jinfo = journal_info(tpath) if "workflows" in tpath.parts else None
                if jinfo:
                    det["journal"] = jinfo
                    lab = jinfo.get("label") or ""
                    notes.append(f"workflow {jinfo['workflow_id']} agent {jinfo['agent_id']} label {lab}")
                    if lab.split("#")[0].removeprefix("judge:") != case_id:
                        anomalies.append(f"journal label {lab!r} is not this case")
                    if jinfo.get("result_canon") != canon(v):
                        anomalies.append("journal result for this agent != verdict")
                    if meta.get("judge_agent_id") and meta["judge_agent_id"] != jinfo["agent_id"]:
                        anomalies.append(f"sidecar judge_agent_id {meta['judge_agent_id']} != bound agent {jinfo['agent_id']}")
                    if meta.get("judge_workflow") and meta["judge_workflow"] != jinfo["workflow_id"]:
                        anomalies.append(f"sidecar judge_workflow {meta['judge_workflow']} != bound workflow {jinfo['workflow_id']}")
                    sid = meta.get("session_id")
                    tsid = parsed["session_ids"][0] if parsed["session_ids"] else None
                    if sid and sid.startswith("wf_"):
                        if sid != jinfo["workflow_id"]:
                            anomalies.append(f"sidecar session_id (a workflow id) {sid} != bound workflow {jinfo['workflow_id']}")
                        else:
                            notes.append(f"sidecar session_id is the workflow id; parent session {tsid}")
                    elif sid and sid != tsid:
                        anomalies.append(f"sidecar session_id {sid} != transcript session {tsid}")
                else:
                    sid = meta.get("session_id")
                    if sid and sid not in parsed["session_ids"]:
                        anomalies.append(f"sidecar session_id {sid} != transcript session {parsed['session_ids']}")
                    if tpath.stem != sid:
                        anomalies.append(f"transcript filename {tpath.stem} != sidecar session id {sid}")
                    notes.append(f"session {parsed['session_ids']} cwd={parsed['cwds']}")
                sos = [c for c in parsed["calls"] if c["name"] == "StructuredOutput"]
                matching = [c for c in sos if canon(c["input"]) == canon(v)]
                if len(sos) > 1:
                    notes.append(f"{len(sos)} StructuredOutput calls ({len(matching)} equal to the verdict)")
                if parsed["calls"] and parsed["calls"][-1]["name"] != "StructuredOutput":
                    anomalies.append("last tool call is not StructuredOutput")
                if sos and matching and sos[-1] is not matching[-1]:
                    anomalies.append("verdict matches a non-final StructuredOutput call")
                answer_id = matching[-1]["id"] if matching else None
                for c in parsed["calls"]:
                    if c["id"] == answer_id:
                        continue
                    cc = dict(c)
                    cc["cls"] = classify_call(c, case_id)
                    res = parsed["results"].get(c["id"])
                    cc["is_error"] = bool(res and res["is_error"])
                    cc["result_head"] = (res["text"][:200] if res else None)
                    calls.append(cc)
                # delegates
                dels = find_delegates(parsed, tpath)
                det["delegates"] = dels
                for dl in dels:
                    for dt in dl["transcripts"]:
                        dp = parse_claude(Path(dt))
                        for c in dp["calls"]:
                            cc = dict(c)
                            cc["cls"] = classify_call(c, case_id)
                            cc["delegate"] = dt
                            calls.append(cc)
                    if not dl["transcripts"]:
                        anomalies.append(f"delegate {dl['tool']} launched but its transcript was not found")
                # prompt fidelity
                own_reads = [c for c in calls if c.get("cls") == "own_prompt"]
                if own_reads:
                    texts = [parsed["results"].get(c["id"], {}).get("text", "") for c in own_reads]
                    lines_seen = reconstruct_read(texts)
                    st, dd = compare_read(lines_seen, r["prompt"])
                    det["prompt_fidelity"] = st
                    det["prompt_diff"] = dd
                    roots = sorted({str(Path(c["input"]["file_path"]).parent.parent.parent) for c in own_reads})
                    det["prompt_read_from"] = roots
                    if str(TREES[r["tree"]].parent) not in roots:
                        notes.append(f"judge read its prompt from {', '.join(short(x) for x in roots)} (not this tree)")
                    if not st.startswith("identical"):
                        anomalies.append(f"prompt the judge read vs published prompt.md: {st}")
                    # also the on-disk copy it read, today
                    for x in roots:
                        fp = Path(x) / "cases" / case_id / "prompt.md"
                        if fp.exists() and fp.read_bytes() != r["prompt"].encode("utf-8"):
                            det.setdefault("disk_prompt_differs", []).append(str(fp))
                else:
                    # prompt arrived as the first user message (claude -p < prompt.md) or in the task text
                    first = parsed["user_strings"][0][1] if parsed["user_strings"] else ""
                    if "Workflow harness" in first or any("Workflow harness" in s for _, s in parsed["user_strings"][:2]):
                        det["prompt_fidelity"] = "prompt-not-read"
                        anomalies.append("workflow judge never read its prompt.md")
                    else:
                        st, dd = compare_text(first, r["prompt"])
                        det["prompt_fidelity"] = st
                        det["prompt_diff"] = dd
                        if st != "identical":
                            anomalies.append(f"first user message vs published prompt.md: {st}")
                    extra_user = [s[:120] for _, s in parsed["user_strings"][1:]]
                    if extra_user:
                        det["extra_user_messages"] = extra_user
                if len(sos) == 0:
                    anomalies.append("no StructuredOutput in bound transcript (?)")
            elif len(paths) > 1:
                rec["binding_method"] = "ambiguous"
                notes.append(f"verdict equals StructuredOutput in {len(paths)} transcripts: " + "; ".join(short(p) for p in paths))
            else:
                # fallback: a main session wrote it with Bash/Write
                found = None
                needle = (v.get("rationale") or "")[:80]
                for ms in MAIN_SESSIONS:
                    if not needle:
                        break
                    if ms not in main_parsed:
                        main_parsed[ms] = parse_claude(ms)
                    mp = main_parsed[ms]
                    for c in mp["calls"]:
                        blob = json.dumps(c["input"], ensure_ascii=False)
                        if needle not in blob and json.dumps(needle)[1:-1] not in blob:
                            continue
                        text = (c["input"].get("command") or c["input"].get("content") or "")
                        for m in re.finditer(r"<<'?EOF'?\n(.*?)\nEOF", text, re.S):
                            try:
                                if json.loads(m.group(1)) == v:
                                    found = (ms, c)
                            except Exception:
                                pass
                        if c["name"] == "Write":
                            try:
                                if json.loads(text) == v:
                                    found = (ms, c)
                            except Exception:
                                pass
                if found:
                    ms, c = found
                    bound = True
                    rec["transcript_path"] = str(ms)
                    rec["binding_method"] = (f"{c['name']} tool_use in the main session writes a verdict.json whose content == "
                                             "verdict.json as parsed JSON (no StructuredOutput: the main session judged it itself)")
                    det["main_session_answer_call"] = {"id": c["id"], "row": c["row"], "ts": c["ts"]}
                else:
                    rec["binding_method"] = "missing"
                    notes.append("no indexed StructuredOutput and no main-session write equals this verdict")

        if bound and not det.get("main_session_answer_call"):
            det["calls"] = [{k: c.get(k) for k in ("name", "cls", "input", "is_error", "delegate", "ts")} for c in calls]
            cls = Counter(c["cls"] for c in calls)
            rec["n_tool_calls"] = len(calls)
            rec["read_other_files"] = "yes" if cls["read_other"] else "no"
            rec["searched"] = "yes" if cls["search"] else "no"
            rec["shell"] = "yes" if cls["shell"] else "no"
            rec["browsed"] = "yes" if cls["browse"] else "no"
            rec["other_tools"] = "yes" if cls["other"] else "no"
            rec["affected"] = "yes" if any(cls[k] for k in ("read_other", "search", "shell", "browse", "other")) else "no"
            touched = [describe_call(c) + (" [error]" if c.get("is_error") else "") for c in calls if c["cls"] != "own_prompt"]
            det["touched"] = touched
            own = cls["own_prompt"]
            if own:
                notes.append(f"{own} Read(s) of its own case prompt.md")
            if touched:
                notes.append("TOUCHED: " + " | ".join(touched[:12]) + (f" | (+{len(touched)-12} more)" if len(touched) > 12 else ""))
        rec["notes"] = "; ".join(notes + [f"ANOMALY: {a}" for a in anomalies])
        rows.append(rec)
        details.append(det)

    # main-session judged verdicts get their segment analysed separately (see main_session_segment.py)
    with open(out_dir / "verdicts_indep_auto.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    json.dump(details, open(out_dir / "details_auto.json", "w"), indent=1, default=str)
    c = Counter((r["tree"], r["wave"], r["binding_method"].split(" ")[0], r["affected"]) for r in rows)
    for k, n in sorted(c.items()):
        print(n, k)


if __name__ == "__main__":
    main()
