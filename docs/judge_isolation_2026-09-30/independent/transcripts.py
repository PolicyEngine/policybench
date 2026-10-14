"""Transcript parsing helpers for the independent judge-isolation audit.

Reads Claude Code session/subagent JSONL transcripts and Codex text logs.
Read-only: never writes outside the caller's chosen output paths.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TOOL_PART_TYPES = {"tool_use", "server_tool_use", "mcp_tool_use"}
CASE_RE = re.compile(r"us__scenario_\d{3}__[a-z0-9_]+")


def canon(obj) -> str:
    """Canonical form used for content binding (parsed-JSON equality)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def load_lines(path: Path):
    out = []
    with open(path, "rb") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except Exception:
                out.append({"_unparseable": raw[:200].decode("utf-8", "replace")})
    return out


def _text_of(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict):
                if p.get("type") == "text":
                    parts.append(p.get("text", ""))
                elif p.get("type") == "tool_reference":
                    parts.append(f"[tool_reference {p.get('tool_name')}]")
                else:
                    parts.append(json.dumps(p)[:2000])
            else:
                parts.append(str(p))
        return "\n".join(parts)
    return json.dumps(content)


def parse_claude(path: Path) -> dict:
    """Summarise one Claude transcript: tool calls, results, prompts, ids."""
    rows = load_lines(path)
    calls, seen = [], set()
    results = {}
    user_strings = []  # (index, text) of plain user prompts, in order
    session_ids, agent_ids, cwds = set(), set(), set()
    models = set()
    first_ts = last_ts = None
    sidechain_rows = 0
    injected = []
    final_texts = []
    for i, d in enumerate(rows):
        if "sessionId" in d:
            session_ids.add(d["sessionId"])
        if d.get("agentId"):
            agent_ids.add(d["agentId"])
        if d.get("cwd"):
            cwds.add(d["cwd"])
        ts = d.get("timestamp")
        if ts:
            first_ts = first_ts or ts
            last_ts = ts
        if d.get("isSidechain"):
            sidechain_rows += 1
        msg = d.get("message") if isinstance(d.get("message"), dict) else None
        typ = d.get("type")
        if typ == "attachment":
            att = d.get("attachment") or {}
            injected.append(att.get("type"))
        if not msg:
            continue
        content = msg.get("content")
        if typ == "assistant":
            if msg.get("model"):
                models.add(msg["model"])
            if isinstance(content, list):
                for p in content:
                    if not isinstance(p, dict):
                        continue
                    if p.get("type") in TOOL_PART_TYPES:
                        tid = p.get("id") or f"{i}:{p.get('name')}"
                        if tid in seen:
                            continue
                        seen.add(tid)
                        calls.append({
                            "id": tid,
                            "name": p.get("name"),
                            "input": p.get("input"),
                            "row": i,
                            "ts": ts,
                            "part_type": p.get("type"),
                            "sidechain": bool(d.get("isSidechain")),
                        })
                    elif p.get("type") == "text":
                        final_texts.append((i, p.get("text", "")))
        elif typ == "user":
            if isinstance(content, str):
                user_strings.append((i, content))
            elif isinstance(content, list):
                for p in content:
                    if not isinstance(p, dict):
                        continue
                    if p.get("type") == "tool_result":
                        results[p.get("tool_use_id")] = {
                            "is_error": bool(p.get("is_error")),
                            "text": _text_of(p.get("content")),
                            "row": i,
                        }
                    elif p.get("type") == "text":
                        user_strings.append((i, p.get("text", "")))
    return {
        "path": str(path),
        "calls": calls,
        "results": results,
        "user_strings": user_strings,
        "session_ids": sorted(session_ids),
        "agent_ids": sorted(agent_ids),
        "cwds": sorted(cwds),
        "models": sorted(models),
        "first_ts": first_ts,
        "last_ts": last_ts,
        "sidechain_rows": sidechain_rows,
        "n_rows": len(rows),
        "injected": injected,
        "final_texts": final_texts,
    }


def structured_outputs(parsed: dict):
    return [c for c in parsed["calls"] if c["name"] == "StructuredOutput"]


# ---------------------------------------------------------------- codex logs

STDERR_NOISE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s+(ERROR|WARN|INFO|DEBUG|TRACE)\b.*"
    r"|warning: .*"
    r"|codex-shim: .*"
    r"|Reading prompt from stdin\.\.\.)$"
)


def parse_codex(path: Path) -> dict:
    txt = path.read_text(encoding="utf-8", errors="replace")
    lines = txt.split("\n")
    header = {}
    for ln in lines[:20]:
        m = re.match(r"^(workdir|model|provider|approval|sandbox|reasoning effort|reasoning summaries|session id): (.*)$", ln)
        if m:
            header[m.group(1)] = m.group(2)
    blocks = []  # (index, header word)
    block_words = {"user", "codex", "exec", "thinking", "tokens used", "mcp", "tool", "apply_patch",
                   "file update", "web search", "web_search", "plan update", "turn diff"}
    for i, ln in enumerate(lines):
        if ln in block_words:
            blocks.append((i, ln))
    execs = []
    for bi, (i, w) in enumerate(blocks):
        if w == "exec":
            end = blocks[bi + 1][0] if bi + 1 < len(blocks) else len(lines)
            execs.append("\n".join(lines[i + 1:end]).strip())
    # other tool-ish markers codex prints inline
    tool_markers = [ln for ln in lines if re.match(r"^(🌐|🔎|✓|✗|mcp: |tool |web search|Searched|apply_patch)", ln)]
    user_idx = [i for i, w in blocks if w == "user"]
    codex_idx = [i for i, w in blocks if w == "codex"]
    tok_idx = [i for i, w in blocks if w == "tokens used"]
    prompt = None
    noise = []
    if user_idx:
        end = min([i for i, _ in blocks if i > user_idx[0]] or [len(lines)])
        raw = lines[user_idx[0] + 1:end]
        kept = []
        for ln in raw:
            if STDERR_NOISE.match(ln):
                noise.append(ln)
            else:
                kept.append(ln)
        prompt = "\n".join(kept)
    final = None
    final_obj = None
    if tok_idx:
        final = "\n".join(lines[tok_idx[-1] + 2:]).strip()
        try:
            final_obj = json.loads(final)
        except Exception:
            final_obj = None
    last_msg_obj = None
    if codex_idx:
        s = codex_idx[-1] + 1
        e = tok_idx[-1] if tok_idx and tok_idx[-1] > s else len(lines)
        body = "\n".join(lines[s:e]).strip()
        try:
            last_msg_obj = json.loads(body)
        except Exception:
            last_msg_obj = None
    return {
        "path": str(path),
        "header": header,
        "blocks": [w for _, w in blocks],
        "execs": execs,
        "tool_markers": tool_markers,
        "prompt": prompt,
        "stderr_noise_in_prompt": noise,
        "final_obj": final_obj,
        "last_msg_obj": last_msg_obj,
    }


# ------------------------------------------------------------- read content

_LINE_PREFIX = re.compile(r"^\s*(\d+)(?:\t|→)(.*)$")


def reconstruct_read(texts):
    """Rebuild file lines from one or more Read tool results (cat -n format)."""
    got = {}
    for t in texts:
        t = re.sub(r"<system-reminder>.*?</system-reminder>", "", t, flags=re.S)
        for ln in t.split("\n"):
            m = _LINE_PREFIX.match(ln)
            if m:
                got[int(m.group(1))] = m.group(2)
    return got
