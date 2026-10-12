"""Rebuild release dashboard-data-20261010's judged audit tree (677 cases).

The release's stage (results/local/final/pe2.38.6/stage in the removed
release-haiku55 worktree) was deleted on 2026-10-10, with the 232 verdicts its
Opus 5.5 judges wrote. Each judge was a Claude Code session whose transcript
is still in the judge login's CLAUDE_CONFIG_DIR (projects/*/<session>.jsonl).
The runner (scripts/run_audit_claude.sh) wrote
  prompt.md    = the bytes the judge read (its one user text message)
  verdict.json = json.dumps(accepted StructuredOutput input, indent=2, sort_keys=True)
so both are recoverable from the transcript, and each must hash to the sha256
docs/haiku55/judge_provenance.json committed for its case.

The tree is release 20261006's seed (674 judged cases, which must match
docs/haiku55/seed_digest.csv) with the 232 recovered cases written over it.
Usage: recover_20261010_audit.py <repo> <seed-20261006-audit> <out-audit>
Read-only on its inputs; refuses to write into an existing out dir.
"""
import csv, glob, hashlib, json, os, shutil, sys
from pathlib import Path

repo, seed_dir, out = (Path(a) for a in sys.argv[1:4])
CONFIGS = {
    "pb-judge": Path.home() / ".policybench-judge/pb-judge-config",
    "claude-18": Path.home() / ".policybench-judge/claude-18-config",
}
NUDGE = "[structured-output-enforce] You MUST call the StructuredOutput tool to complete this request. Call this tool now."
sha = lambda b: hashlib.sha256(b).hexdigest()

def fail(msg):
    sys.exit(f"REFUSED: {msg}")

# 1. The 20261006 seed tree must be the committed digest.
digest = {r["case_id"]: r for r in csv.DictReader(open(repo / "docs/haiku55/seed_digest.csv"))}
cases = sorted(p for p in (seed_dir / "cases").iterdir() if (p / "prompt.md").is_file())
got = {c.name: {"prompt_sha256": sha((c / "prompt.md").read_bytes()),
                "verdict_sha256": sha((c / "verdict.json").read_bytes())} for c in cases}
if set(got) != set(digest) or any(got[k]["prompt_sha256"] != digest[k]["prompt_sha256"]
        or got[k]["verdict_sha256"] != digest[k]["verdict_sha256"] for k in got):
    fail("the 20261006 seed tree is not docs/haiku55/seed_digest.csv")
print(f"20261006 seed: {len(got)} judged cases match the committed digest")

# 2. The 232 committed provenance entries.
prov = json.load(open(repo / "docs/haiku55/judge_provenance.json"))["verdicts"]
want = {e["case_id"]: e for e in prov}
by_prompt = {}
for e in prov:
    by_prompt.setdefault(e["prompt_sha256"], []).append(e["case_id"])
print(f"provenance: {len(want)} re-judged cases")

# 3. Scan every judge transcript; keep the ones whose prompt and verdict hash match.
found = {}
scanned = 0
for login, cfg in CONFIGS.items():
    for path in sorted(glob.glob(str(cfg / "projects/*/*.jsonl"))):
        scanned += 1
        texts, structured, refused, version, session = [], [], set(), set(), None
        for line in open(path, encoding="utf-8"):
            ev = json.loads(line)
            session = ev.get("sessionId", session)
            if ev.get("version"):
                version.add(ev["version"])
            content = (ev.get("message") or {}).get("content")
            if ev.get("type") == "user" and isinstance(content, str):
                if not (ev.get("isMeta") is True and content == NUDGE):
                    texts.append(content)
            if isinstance(content, list):
                structured += [p for p in content if isinstance(p, dict)
                               and p.get("type") == "tool_use" and p.get("name") == "StructuredOutput"]
                refused |= {p.get("tool_use_id") for p in content if isinstance(p, dict)
                            and p.get("type") == "tool_result" and p.get("is_error")}
        if len(texts) != 1:
            continue
        prompt = texts[0].encode("utf-8")
        candidates = by_prompt.get(sha(prompt), [])
        accepted = [p for p in structured if p.get("id") not in refused]
        if not candidates or len(accepted) != 1:
            continue
        verdict = json.dumps(accepted[0]["input"], indent=2, sort_keys=True).encode("utf-8")
        for case in candidates:
            if sha(verdict) == want[case]["verdict_sha256"]:
                if case in found and found[case]["verdict"] != verdict:
                    fail(f"two transcripts give {case} different verdict bytes")
                found.setdefault(case, {"prompt": prompt, "verdict": verdict, "transcript": path,
                                        "login": login, "session_id": session,
                                        "cli_versions": sorted(version)})
print(f"scanned {scanned} transcripts; recovered {len(found)} of {len(want)}")
missing = sorted(set(want) - set(found))
if missing:
    fail(f"{len(missing)} cases not recoverable: {missing[:10]}")

# 4. Write the tree: the 20261006 seed, then the recovered cases over it.
if out.exists():
    fail(f"{out} exists")
shutil.copytree(seed_dir, out, symlinks=False)
record = []
for case, item in sorted(found.items()):
    d = out / "cases" / case
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    (d / "prompt.md").write_bytes(item["prompt"])
    (d / "verdict.json").write_bytes(item["verdict"])
    shutil.copyfile(item["transcript"], d / "claude.transcript.jsonl")
    e = want[case]
    meta = {
        "judge_runner": "scripts/run_audit_claude.sh",
        "verdict_sha256": e["verdict_sha256"],
        "prompt_sha256": e["prompt_sha256"],
        "judge_template_version": 1,
        "judge_model_reported": e["judge_model_reported"],
        "judge_effort": e["judge_effort"],
        "judge_account_declared": e["judge_account_declared"],
        "judged_at_utc": e["judged_at_utc"],
        "session_id": item["session_id"],
        "judge_cli_version": item["cli_versions"][0] if len(item["cli_versions"]) == 1 else item["cli_versions"],
        "recovered": {
            "why": "release 20261010's stage was deleted with its worktree on 2026-10-10; "
                   "the original sidecar was lost with it",
            "from": f"the judge's Claude Code session transcript ({item['login']} login)",
            "checks": "prompt.md and verdict.json hash to docs/haiku55/judge_provenance.json",
            "on": "2026-10-12",
        },
    }
    (d / "verdict.meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    record.append({"case_id": case, "login": item["login"], "session_id": item["session_id"],
                   "prompt_sha256": e["prompt_sha256"], "verdict_sha256": e["verdict_sha256"]})

# 5. The rebuilt tree's digest is the 20261006 digest overlaid with the provenance.
final = {c.name: (sha((c / "prompt.md").read_bytes()), sha((c / "verdict.json").read_bytes()))
         for c in sorted((out / "cases").iterdir()) if (c / "prompt.md").is_file()}
expect = {k: (v["prompt_sha256"], v["verdict_sha256"]) for k, v in digest.items()}
expect.update({k: (v["prompt_sha256"], v["verdict_sha256"]) for k, v in want.items()})
if final != expect:
    fail("rebuilt tree does not match the 20261006 digest overlaid with the provenance")
text = "case_id,prompt_sha256,verdict_sha256\n" + "".join(f"{k},{p},{v}\n" for k, (p, v) in sorted(final.items()))
(out.parent / "seed_digest_20261010.csv").write_text(text)
json.dump({"recovered": record}, open(out.parent / "recovery_record.json", "w"), indent=1)
print(f"rebuilt {len(final)} judged cases; digest sha256 {sha(text.encode())}")
