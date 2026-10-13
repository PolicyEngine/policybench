"""Cross-check: recursively walk every row of each bound Claude transcript for tool_use parts
anywhere in the JSON (not only assistant message content) and compare with the audit's call lists.
usage: python crosscheck_walk.py verdicts_indep.csv verdicts_indep_details.json"""
import csv, json, sys, collections

def walk(o, out):
    if isinstance(o, dict):
        if o.get("type") in ("tool_use", "server_tool_use", "mcp_tool_use") and "name" in o:
            out.append((o.get("id"), o["name"]))
        for v in o.values():
            walk(v, out)
    elif isinstance(o, list):
        for v in o:
            walk(v, out)

rows = list(csv.DictReader(open(sys.argv[1])))
det = {(d["tree"], d["case_id"]): d for d in json.load(open(sys.argv[2]))}
cache = {}
res = collections.Counter(); bad = []
for r in rows:
    p = r["transcript_path"]
    if not p.endswith(".jsonl") or "3dd3d124-a1eb-44ed-ac89-ce3df9700101.jsonl" in p:
        continue
    if p not in cache:
        found = []
        for ln in open(p, "rb"):
            ln = ln.strip()
            if ln:
                walk(json.loads(ln), found)
        ids = {}
        for i, n in found:
            ids.setdefault(i, n)
        cache[p] = ids
    ids = cache[p]
    d = det[(r["tree"], r["case_id"])]
    judge_calls = [c for c in d["calls"] if not c.get("delegate")]
    names_walk = collections.Counter(n for n in ids.values())
    # audit excludes exactly one answer StructuredOutput from the judge's own file
    names_audit = collections.Counter(c["name"] for c in judge_calls)
    names_audit["StructuredOutput"] += 1
    ok = names_walk == names_audit
    res[(r["wave"], ok)] += 1
    if not ok:
        bad.append((r["tree"], r["case_id"], dict(names_walk), dict(names_audit)))
print(res)
for b in bad[:10]:
    print(b)
