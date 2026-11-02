"""Index every StructuredOutput answer in the candidate Claude transcripts.

Output: a JSON map canonical-verdict -> list of {path, agent_ids, session_ids, row, ts}.
Candidate transcripts:
  * each sidecar session id's <sid>.jsonl in ~/.claude/projects/*, ~/.subfleet/logins/*/projects/*,
    and the Logpile copy (~/logpile/shared/maxghenis/claudecode/*)
  * every agent-*.jsonl under <session>/subagents/ (recursively) for every session that owns a
    subagents dir among those, plus the two Workflow parent sessions found by glob.
Files are prefiltered on the bytes '"StructuredOutput"' before JSON parsing.

usage: python build_index.py <sid_hits.json> <out_index.json> [extra transcript paths or dirs ...]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transcripts import canon, load_lines  # noqa: E402

TOOL_TYPES = {"tool_use", "server_tool_use", "mcp_tool_use"}


def so_entries(path: Path):
    b = open(path, "rb").read()
    if b'"StructuredOutput"' not in b:
        return []
    out = []
    seen = set()
    for i, d in enumerate(load_lines(path)):
        msg = d.get("message") if isinstance(d.get("message"), dict) else None
        if not msg or d.get("type") != "assistant" or not isinstance(msg.get("content"), list):
            continue
        for p in msg["content"]:
            if isinstance(p, dict) and p.get("type") in TOOL_TYPES and p.get("name") == "StructuredOutput":
                if p.get("id") in seen:
                    continue
                seen.add(p.get("id"))
                out.append({
                    "canon": canon(p.get("input")),
                    "row": i,
                    "ts": d.get("timestamp"),
                    "agent_id": d.get("agentId"),
                    "session_id": d.get("sessionId"),
                    "tool_use_id": p.get("id"),
                })
    return out


def main():
    hits = json.load(open(sys.argv[1]))
    out_path = Path(sys.argv[2])
    files = set()
    session_dirs = set()
    for k, v in hits.items():
        for p in v:
            if k.endswith("/dir"):
                session_dirs.add(p)
            else:
                files.add(p)
                d = p[: -len(".jsonl")]
                if os.path.isdir(d):
                    session_dirs.add(d)
    for extra in sys.argv[3:]:
        if os.path.isdir(extra):
            session_dirs.add(extra)
        else:
            files.add(extra)
    for sd in sorted(session_dirs):
        sub = Path(sd) / "subagents"
        if sub.is_dir():
            for p in sub.rglob("agent-*.jsonl"):
                files.add(str(p))
    index = {}
    n_so = 0
    for f in sorted(files):
        for e in so_entries(Path(f)):
            n_so += 1
            index.setdefault(e.pop("canon"), []).append({"path": f, **e})
    json.dump({"files_scanned": sorted(files), "index": index}, open(out_path, "w"))
    print(f"scanned {len(files)} files, {n_so} StructuredOutput calls, {len(index)} distinct answers")


if __name__ == "__main__":
    main()
