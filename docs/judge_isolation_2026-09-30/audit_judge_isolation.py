#!/usr/bin/env python3
"""Audit whether each published PolicyBench judge verdict came from an isolated judge.

For every verdict in the audit trees below, bind the verdict to the transcript
that produced it and list every tool the judge called. A binding counts only
when the transcript's structured answer, serialised the way the writers
serialise verdict.json (json.dumps(indent=2, sort_keys=True)), hashes to the
verdict's own sha256. Nothing is inferred: a verdict without a bound transcript
is reported as missing.

Transcript sources, by judge runner:
  scripts/run_audit_codex.sh      the case's codex.log (the exec's full stdout)
  scripts/run_audit_claude.sh     <config>/projects/*/<session_id>.jsonl, in the
                                  desktop config, each subfleet login's config,
                                  and Logpile's copies
  Workflow tool subagents         <project>/<session>/subagents/workflows/<wf>/
                                  agent-<id>.jsonl, for every workflow whose
                                  journal names a PolicyBench case
  Claude Code main session        the orchestrating session's own transcript

Writes verdicts.csv (one row per tree and case), tool_calls.csv (one row per
judge tool call) and summary.json beside this script.
"""

from __future__ import annotations

import collections
import csv
import glob
import hashlib
import json
import os
import re
import sys
from pathlib import Path

HOME = Path.home()
OUT = Path(__file__).resolve().parent
TREES = {
    "seed": Path(
        "~/PolicyEngine/policybench-wt/adds0928-stage2/results/local/adds0928-v3/audit/cases"
    ),
    "unified": Path("~/PolicyEngine/policybench/results/local/unified_audit/audit/cases"),
}
SESSION_ROOTS = [
    HOME / ".claude/projects",
    *sorted(Path(p) for p in glob.glob(str(HOME / ".subfleet/logins/*/projects"))),
    HOME / "logpile/shared/maxghenis/claudecode",
]
CASE_RE = re.compile(r"us__scenario_\d{3}__[a-z0-9_]+")


def canon_sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, indent=2, sort_keys=True).encode("utf-8")).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wave_of(meta: dict) -> str:
    runner = meta.get("judge_runner", "")
    day = (meta.get("judged_at_utc") or "")[:10]
    if "run_audit_codex" in runner:
        # Codex sidecars were backfilled from codex.log; judged_at_utc is the
        # backfill time, so the wave is the runner, not a date.
        return "codex (sidecars backfilled)"
    if day == "2026-09-05":
        return "2026-09-05"
    if "2026-09-22" <= day <= "2026-09-24":
        return "2026-09-22"
    if "2026-09-28" <= day <= "2026-09-30":
        return "2026-09-29"
    return f"other ({day})"


def runner_kind(meta: dict) -> str:
    runner = meta.get("judge_runner", "")
    if "run_audit_codex" in runner:
        return "codex"
    if "run_audit_claude" in runner:
        return "claude_cli"
    if runner.startswith("Claude Code Workflow"):
        return "workflow_subagent"
    if runner.startswith("Claude Code main session"):
        return "main_session"
    return "unknown"


# ---------------------------------------------------------------- transcripts


def structured_outputs(path: Path):
    """Every StructuredOutput input in a Claude transcript, in order."""
    out = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "StructuredOutput" not in line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            content = (event.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if (
                    isinstance(part, dict)
                    and part.get("type") == "tool_use"
                    and part.get("name") == "StructuredOutput"
                ):
                    out.append(part.get("input"))
    return out


def index_sessions() -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = collections.defaultdict(list)
    for root in SESSION_ROOTS:
        if not root.is_dir():
            continue
        for project in os.scandir(root):
            if not project.is_dir():
                continue
            for entry in os.scandir(project.path):
                if entry.name.endswith(".jsonl") and entry.is_file():
                    found[entry.name[:-6]].append(Path(entry.path))
    return found


def judge_workflow_dirs() -> list[Path]:
    dirs = []
    pat = re.compile(rb"us__scenario_\d{3}__")
    for journal in glob.glob(str(HOME / ".claude/projects/*/*/subagents/workflows/*/journal.jsonl")):
        if pat.search(Path(journal).read_bytes()):
            dirs.append(Path(journal).parent)
    return sorted(dirs)


def index_workflow_agents(dirs: list[Path]):
    """sha of each structured answer -> [(agent transcript, workflow, agent id, label)]."""
    by_sha: dict[str, list[tuple]] = collections.defaultdict(list)
    for wf in dirs:
        labels = {}
        for line in (wf / "journal.jsonl").read_text(errors="replace").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "started" and e.get("agentId"):
                labels[e["agentId"]] = e.get("label", "")
        for agent in sorted(wf.glob("agent-*.jsonl")):
            agent_id = agent.stem[len("agent-") :]
            for answer in structured_outputs(agent):
                if isinstance(answer, dict) and "case_failure_source" in answer:
                    by_sha[canon_sha(answer)].append((agent, wf.name, agent_id, labels.get(agent_id, "")))
    return by_sha


# ---------------------------------------------------------------- classification

READ_TOOLS = {"Read", "NotebookRead"}
SEARCH_TOOLS = {"Grep", "Glob", "LS"}
SHELL_TOOLS = {"Bash", "BashOutput", "KillShell", "PowerShell"}
BROWSE_TOOLS = {"WebFetch", "WebSearch", "web_search", "web_fetch"}


def path_class(path: str, case_id: str) -> str:
    p = path or ""
    if p.endswith(f"/{case_id}/prompt.md") and "/audit/cases/" in p:
        return "own_prompt"
    low = p.lower()
    if "adjudicat" in low or "decision" in low:
        return "adjudication_records"
    # Case notes and row annotations are earlier judges' published verdicts.
    if any(k in low for k in ("case_notes", "audit_row_annotations", "audit_case_annotations")):
        return "prior_verdicts"
    if "policyengine-us" in low or "policyengine_us" in low:
        return "policyengine_us_checkout"
    if "/audit/cases/" in p or low.endswith("verdict.json"):
        return "other_audit_cases"
    if "/annotations/" in p:
        return "annotations"
    if "/policybench" in p:
        return "policybench_repo_other"
    return "other_path"


def tool_category(name: str) -> str:
    if name in READ_TOOLS:
        return "read"
    if name in SEARCH_TOOLS:
        return "search"
    if name in SHELL_TOOLS:
        return "shell"
    if name in BROWSE_TOOLS or "browser" in name.lower() or "chrome" in name.lower():
        return "browse"
    if name == "ToolSearch":
        return "tool_search"
    if name in {"Agent", "Task"}:
        return "subagent"
    if name in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        return "write"
    return "other_tool"


def result_text(part: dict) -> str:
    content = part.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            (c.get("text") or "") if isinstance(c, dict) else str(c) for c in content
        )
    return ""


SKILL_RE = re.compile(r"Base directory for this skill: \S*/skills/([A-Za-z0-9_:.-]+)|<command-name>/?([A-Za-z0-9_:.-]+)</command-name>")


def message_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            (c.get("text") or "") for c in content if isinstance(c, dict) and c.get("type") == "text"
        )
    return ""


def classify_claude(path: Path, case_id: str, stop_at_sha: str | None = None):
    """Tool calls and context of one Claude transcript, up to the bound answer.

    Besides the tool calls it returns what the judge was shown: the working
    directory and whether it was a git checkout (the environment snapshot's
    isGitRepo, or a gitBranch on any event), every instruction or nested
    memory file with the exact content injected, any skill loaded into the
    conversation, the first user message (the prompt a `claude -p` judge read
    on stdin) and the full text of each Read of its own prompt.
    """
    calls, results, attachments = [], {}, collections.Counter()
    instructions, cwds, git_repo = [], set(), set()
    instruction_contents, skills, full_results = {}, set(), {}
    first_user = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("cwd"):
                cwds.add(event["cwd"])
            # Claude Code writes gitBranch "HEAD" even outside a repository.
            if event.get("gitBranch") not in (None, "", "HEAD"):
                git_repo.add(True)
            if event.get("type") == "attachment":
                att = event.get("attachment") or {}
                kind = att.get("type")
                attachments[kind] += 1
                if kind == "environment":
                    snap = att.get("snapshot") or {}
                    git_repo.add(bool(snap.get("isGitRepo")))
                    if snap.get("workingDirectory"):
                        cwds.add(snap["workingDirectory"])
                if kind in ("instructions", "nested_memory", "memory", "claude_md"):
                    for f in att.get("files") or [att]:
                        if isinstance(f, dict):
                            fpath = f.get("path") or kind
                            instructions.append(fpath)
                            body = f.get("content")
                            if isinstance(body, dict):
                                body = body.get("content")
                            if isinstance(body, str):
                                instruction_contents[fpath] = body
                if kind in ("skill", "invoked_skills", "skill_content"):
                    skills.add(str(att.get("name") or att.get("skillName") or kind))
            msg = event.get("message") or {}
            content = msg.get("content")
            if event.get("type") == "user" and msg.get("role") == "user":
                text = message_text(content)
                if first_user is None and text and not event.get("isMeta"):
                    first_user = text
                for m in SKILL_RE.finditer(text):
                    skills.add(m.group(1) or m.group(2))
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = str(part.get("type", ""))
                if ptype == "tool_result":
                    full = result_text(part)
                    results[part.get("tool_use_id")] = (bool(part.get("is_error")), full[:300])
                    full_results[part.get("tool_use_id")] = full
                elif ptype.endswith("tool_use"):
                    name = part.get("name") or ptype
                    if name == "StructuredOutput":
                        continue
                    inp = part.get("input") or {}
                    calls.append({"id": part.get("id"), "name": name, "input": inp})
    rows, own_prompt_reads = [], []
    for c in calls:
        name, inp = c["name"], c["input"]
        cat = tool_category(name)
        if cat == "read" and path_class(inp.get("file_path", ""), case_id) == "own_prompt":
            own_prompt_reads.append(full_results.get(c["id"], ""))
        target = (
            inp.get("file_path")
            or inp.get("path")
            or inp.get("pattern")
            or inp.get("command")
            or inp.get("url")
            or inp.get("query")
            or ""
        )
        pclass = ""
        if cat == "read":
            pclass = path_class(inp.get("file_path", ""), case_id)
        elif cat == "search":
            pclass = path_class(inp.get("path", "") or "", case_id) + " | pattern=" + str(
                inp.get("pattern", "")
            )[:120]
        is_err, preview = results.get(c["id"], (None, ""))
        rows.append(
            {
                "tool": name,
                "category": cat,
                "target": str(target)[:400],
                "path_class": pclass,
                "result_is_error": is_err,
                "result_preview": preview.replace("\n", " ")[:300],
            }
        )
    return rows, {
        "cwds": sorted(cwds),
        "cwd_in_git_repo": sorted(git_repo),
        "attachments": dict(attachments),
        "instructions_files": sorted(set(instructions)),
        "instruction_contents": instruction_contents,
        "skills": sorted(skills),
        "first_user": first_user,
        "own_prompt_reads": own_prompt_reads,
    }


_GIT: dict[str, str] = {}


def is_git_checkout(path: str) -> str:
    """Whether a judge's working directory is inside a git checkout, checked now."""
    if path not in _GIT:
        if not path or not os.path.isdir(path):
            _GIT[path] = "gone"
        else:
            import subprocess

            r = subprocess.run(["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
                               capture_output=True, text=True)
            _GIT[path] = "yes" if r.stdout.strip() == "true" else "no"
    return _GIT[path]


READ_LINE = re.compile(r"^\s*(\d+)\t(.*)$")


def prompt_seen_check(ctx: dict, kind: str, prompt: str, codex_prompt: str | None = None) -> str:
    """Did the judge see exactly the published prompt.md?

    claude -p judges read it on stdin, so it is their first user message.
    Workflow judges read it with the Read tool, which returns numbered lines
    (`N<TAB>text`); every line of the published prompt must come back with
    identical text. Codex echoes the prompt after its `user` header.
    """
    want = prompt.rstrip("\n")
    if kind == "claude_cli":
        got = ctx.get("first_user")
        if got is None:
            return "no prompt in transcript"
        return "identical" if got.rstrip("\n") == want else "DIFFERS"
    if kind == "workflow_subagent":
        reads = ctx.get("own_prompt_reads") or []
        if not reads:
            return "no Read of its prompt"
        seen = {}
        for text in reads:
            for line in text.split("\n"):
                m = READ_LINE.match(line)
                if m:
                    seen[int(m.group(1))] = m.group(2)
        lines = want.split("\n")
        missing = [i for i in range(1, len(lines) + 1) if i not in seen]
        differ = [i for i in range(1, len(lines) + 1) if i in seen and seen[i] != lines[i - 1]]
        extra = [i for i in seen if i > len(lines)]
        if not missing and not differ and not extra:
            return "identical"
        return f"DIFFERS (lines missing {len(missing)}, differing {len(differ)}, extra {len(extra)}; first {(missing + differ + extra)[:5]})"
    if kind == "codex":
        if codex_prompt is None:
            return "no prompt in log"
        return "identical" if codex_prompt.strip("\n") == want.strip("\n") else "DIFFERS"
    return ""


def classify_with_delegates(path: Path, case_id: str):
    """A transcript's own calls plus those of any agents it spawned.

    A judge that launches an Agent, Task or Workflow hands work to subagents
    whose transcripts live under <project>/<session>/subagents/. Their calls
    count as the judge's.
    """
    rows, ctx = classify_claude(path, case_id)
    if any(r["tool"] in {"Agent", "Task", "Workflow"} for r in rows):
        sub = path.with_suffix("") / "subagents"
        for agent in sorted(sub.rglob("agent-*.jsonl")) if sub.is_dir() else []:
            sub_rows, _ = classify_claude(agent, case_id)
            for r in sub_rows:
                r["tool"] = f"{r['tool']} (delegate {agent.stem})"
            rows.extend(sub_rows)
    return rows, ctx


def codex_final_json(log: Path):
    """The final agent message in a codex exec log, parsed as JSON."""
    text = log.read_text(errors="replace")
    sections = re.split(r"(?m)^(user|codex|thinking|exec|tokens used)$", text)
    headers = collections.Counter(sections[1::2])
    finals = [sections[i + 1] for i in range(1, len(sections), 2) if sections[i] == "codex"]
    parsed = None
    for body in reversed(finals):
        body = body.strip()
        try:
            parsed = json.loads(body)
            break
        except ValueError:
            m = re.search(r"\{.*\}", body, re.S)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                    break
                except ValueError:
                    pass
    header = dict(re.findall(r"(?m)^(workdir|sandbox|model|session id): (.*)$", text))
    users = [sections[i + 1] for i in range(1, len(sections), 2) if sections[i] == "user"]
    header["prompt"] = users[0] if users else None
    return parsed, headers, header


def classify_codex(log: Path):
    """Codex prints each command as an `exec` block; any other tool shows as a header."""
    text = log.read_text(errors="replace")
    rows = []
    for m in re.finditer(r"(?m)^exec\n(.*)$", text):
        rows.append(
            {
                "tool": "exec",
                "category": "shell",
                "target": m.group(1)[:400],
                "path_class": "",
                "result_is_error": None,
                "result_preview": "",
            }
        )
    odd = sorted(
        set(re.findall(r"(?m)^([a-z_ ]+)$", text)) - {"user", "codex", "thinking", "tokens used"}
    )
    # Tool lines that carry a colon: `mcp: server/tool started`, `web search: ...`,
    # `apply_patch ...`, `patch: ...`.
    odd += sorted(set(re.findall(r"(?m)^(mcp:.*|web search:.*|apply_patch.*|patch:.*|tool .*)$", text)))
    for h in odd:
        rows.append(
            {
                "tool": h,
                "category": "other_tool",
                "target": "",
                "path_class": "",
                "result_is_error": None,
                "result_preview": "",
            }
        )
    return rows


# ---------------------------------------------------------------- main


def main() -> int:
    # Validation runs: --tree name=cases_dir replaces the published trees and
    # --out DIR writes the tables elsewhere.
    global OUT, TREES
    args = sys.argv[1:]
    if "--out" in args:
        OUT = Path(args[args.index("--out") + 1])
        OUT.mkdir(parents=True, exist_ok=True)
    extra = [a.split("=", 1) for a in args if "=" in a and not a.startswith("--")]
    if extra:
        TREES = {"seed": TREES["seed"], **{k: Path(v) for k, v in extra}}
    sessions = index_sessions()
    wf_dirs = judge_workflow_dirs()
    wf_index = index_workflow_agents(wf_dirs)
    print(f"indexed {len(sessions)} session transcripts, {len(wf_dirs)} judge workflows,"
          f" {sum(len(v) for v in wf_index.values())} workflow structured answers", file=sys.stderr)

    seed_shas = {}
    for case in TREES["seed"].iterdir():
        v = case / "verdict.json"
        if v.is_file():
            seed_shas[case.name] = file_sha(v)

    verdict_rows, call_rows, injected = [], [], {}
    for tree, root in TREES.items():
        for case in sorted(root.iterdir()):
            vpath, mpath = case / "verdict.json", case / "verdict.meta.json"
            if not vpath.is_file():
                continue
            vsha = file_sha(vpath)
            # Bind on the canonical serialisation: codex -o keeps the raw bytes.
            vcanon = canon_sha(json.loads(vpath.read_text()))
            meta = json.loads(mpath.read_text()) if mpath.is_file() else {}
            kind = runner_kind(meta)
            row = {
                "tree": tree,
                "case_id": case.name,
                "wave": wave_of(meta),
                "runner": kind,
                "judge_runner": meta.get("judge_runner", ""),
                "judged_at_utc": meta.get("judged_at_utc", ""),
                "verdict_sha256": vsha,
                "sidecar_binds_verdict": meta.get("verdict_sha256") == vsha,
                "prompt_sha256_now": file_sha(case / "prompt.md") if (case / "prompt.md").is_file() else "",
                "prompt_sha256_sidecar": meta.get("prompt_sha256", ""),
                "live_in_published_release": tree == "seed" or seed_shas.get(case.name) == vsha,
                "session_id": meta.get("session_id", ""),
                "workflow": meta.get("judge_workflow", ""),
                "agent_id": meta.get("judge_agent_id", ""),
            }
            transcript, status, candidates, calls, ctx = "", "missing", 0, [], {}
            if kind == "codex":
                log = case / "codex.log"
                if log.is_file():
                    parsed, headers, header = codex_final_json(log)
                    row["codex_workdir"] = header.get("workdir", "")
                    row["codex_sandbox"] = header.get("sandbox", "")
                    if parsed is not None and canon_sha(parsed) == vcanon:
                        transcript, status, candidates = str(log), "bound", 1
                        calls = classify_codex(log)
                        ctx = {"cwds": [header.get("workdir", "")]}
                        row["prompt_seen"] = prompt_seen_check(
                            {}, "codex", (case / "prompt.md").read_text(), header.get("prompt"))
                    else:
                        status = "codex.log does not hold this verdict"
                else:
                    status = "missing: no codex.log"
            elif kind == "claude_cli":
                paths = sessions.get(meta.get("session_id", ""), [])
                bound = [p for p in paths if any(
                    isinstance(a, dict) and canon_sha(a) == vcanon for a in structured_outputs(p))]
                candidates = len(paths)
                if bound:
                    # Prefer the live config copy over Logpile's.
                    bound.sort(key=lambda p: "logpile" in str(p))
                    transcript, status = str(bound[0]), "bound"
                    calls, ctx = classify_with_delegates(bound[0], case.name)
                elif paths:
                    status = "session transcript found but its answer does not hash to this verdict"
                else:
                    status = "missing: no transcript for the session id"
            elif kind == "workflow_subagent":
                hits = wf_index.get(vcanon, [])
                # Only an agent whose journal label names this case binds it.
                named = [h for h in hits if case.name in h[3]] or hits
                candidates = len(hits)
                if named:
                    agent, wf, agent_id, label = named[0]
                    transcript, status = str(agent), "bound"
                    row["workflow"] = row["workflow"] or wf
                    row["agent_id"] = row["agent_id"] or agent_id
                    row["bound_label"] = label
                    calls, ctx = classify_with_delegates(agent, case.name)
                    row["bound_agents_same_answer"] = len({h[2] for h in hits})
                else:
                    status = "missing: no workflow agent answer hashes to this verdict"
            elif kind == "main_session":
                status = "main session judged it itself (not an isolated judge)"
                paths = sessions.get(meta.get("session_id", ""), [])
                transcript = str(paths[0]) if paths else ""
            row["transcript_status"] = status
            row["transcript"] = transcript
            row["transcript_candidates"] = candidates
            row["judge_cwds"] = ";".join(ctx.get("cwds", []))
            row["judge_cwd_in_git_repo"] = ";".join(str(x) for x in ctx.get("cwd_in_git_repo", []))
            row["instructions_files"] = ";".join(ctx.get("instructions_files", []))
            row["attachment_kinds"] = json.dumps(ctx.get("attachments", {}), sort_keys=True)
            row["skills_loaded"] = ";".join(ctx.get("skills", []))
            row["judge_cwd_is_git_checkout"] = ";".join(
                f"{is_git_checkout(c)}" for c in ctx.get("cwds", []))
            if kind in ("claude_cli", "workflow_subagent") and status == "bound":
                row["prompt_seen"] = prompt_seen_check(ctx, kind, (case / "prompt.md").read_text())
            for fpath, body in (ctx.get("instruction_contents") or {}).items():
                injected.setdefault((fpath, hashlib.sha256(body.encode()).hexdigest()), [body, set()])[1].add(
                    f"{tree}|{row['wave']}")

            cats = collections.Counter()
            pclasses = collections.Counter()
            for c in calls:
                cats[c["category"]] += 1
                if c["path_class"]:
                    pclasses[c["path_class"].split(" | ")[0]] += 1
                call_rows.append({"tree": tree, "case_id": case.name, "wave": row["wave"], **c})
            read_other = sum(n for k, n in pclasses.items() if k != "own_prompt" and k)
            row["n_tool_calls"] = len(calls)
            row["read_own_prompt"] = pclasses.get("own_prompt", 0)
            row["read_other_files"] = sum(
                1 for c in calls if c["category"] == "read" and c["path_class"] != "own_prompt")
            row["read_adjudication_records"] = sum(
                1 for c in calls if c["path_class"].startswith("adjudication_records"))
            row["read_policyengine_us"] = sum(
                1 for c in calls if c["path_class"].startswith("policyengine_us_checkout"))
            row["searched"] = cats.get("search", 0)
            row["shell"] = cats.get("shell", 0)
            row["browsed"] = cats.get("browse", 0)
            row["other_tools"] = cats.get("other_tool", 0) + cats.get("subagent", 0) + cats.get("write", 0)
            row["tool_search"] = cats.get("tool_search", 0)
            row["path_classes"] = json.dumps(dict(pclasses), sort_keys=True)
            row["affected"] = (
                "yes" if (row["read_other_files"] or row["searched"] or row["shell"] or row["browsed"]
                          or row["other_tools"] or kind == "main_session")
                else ("unknown" if status != "bound" else "no")
            )
            _ = read_other
            verdict_rows.append(row)

    fields = sorted({k for r in verdict_rows for k in r}, key=lambda k: (
        list(verdict_rows[0].keys()).index(k) if k in verdict_rows[0] else 999, k))
    with open(OUT / "verdicts.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(verdict_rows)
    cfields = ["tree", "case_id", "wave", "tool", "category", "target", "path_class",
               "result_is_error", "result_preview"]
    with open(OUT / "tool_calls.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cfields)
        w.writeheader()
        w.writerows(call_rows)

    # Every distinct instruction or nested-memory text a judge was shown, as injected.
    (OUT / "injected_instructions.json").write_text(json.dumps(
        {f"{path}#{sha[:12]}": {"content": body, "seen_in": sorted(seen)}
         for (path, sha), (body, seen) in sorted(injected.items())}, indent=1))

    summary = collections.defaultdict(lambda: collections.Counter())
    for r in verdict_rows:
        key = f"{r['tree']} | {r['wave']}"
        s = summary[key]
        s["verdicts"] += 1
        s[f"transcript:{r['transcript_status'] if r['transcript_status'] == 'bound' else 'not bound'}"] += 1
        s[f"affected:{r['affected']}"] += 1
        for k in ("read_other_files", "read_adjudication_records", "read_policyengine_us",
                  "searched", "shell", "browsed", "other_tools", "tool_search"):
            if r[k]:
                s[f"judges_{k}"] += 1
        if r["live_in_published_release"]:
            s["live_in_published_release"] += 1
            if r["affected"] == "yes":
                s["affected_and_live"] += 1
    (OUT / "summary.json").write_text(json.dumps({k: dict(v) for k, v in sorted(summary.items())}, indent=2))
    print(json.dumps({k: dict(v) for k, v in sorted(summary.items())}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
