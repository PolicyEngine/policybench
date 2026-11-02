# The audit seed: release 20261010's judged audit, rebuilt

Release dashboard-data-20261010 (PR #208) judged 232 cases with Opus 5.5 on judge template v1 and carried 445 cases from release 20261006, 677 judged cases in all. Its stage, which held those verdicts, was in the release worktree, and that worktree was removed on 2026-10-10 after the release shipped. The repository kept only hashes: `docs/haiku55/judge_provenance.json` gives each re-judged case's prompt and verdict sha256.

Each judge was a Claude Code session run by `scripts/run_audit_claude.sh`. Its session transcript was still in the judge login's configuration directory (`~/.policybench-judge/pb-judge-config` or `claude-18-config`, under `projects/`). The runner writes:

- `prompt.md`: the bytes the judge read, which are the transcript's one user text message;
- `verdict.json`: `json.dumps(structured_output, indent=2, sort_keys=True)`, where the transcript holds the one accepted StructuredOutput call with the same input.

`scripts/recover_20261010_audit.py` therefore rebuilds both files from the transcripts.

How the rebuild ran (2026-10-12):

1. Release 20261006's local seed tree (674 judged cases) must match `docs/haiku55/seed_digest.csv`. It did.
2. It scanned the 288 judge transcripts. For each, it took the one user text message and the one accepted StructuredOutput input. A transcript stands for a case only when both hash to that case's entry in `docs/haiku55/judge_provenance.json`.
3. All 232 cases were found: 193 on the pb-judge login's transcripts and 39 on claude-18's, the provenance record's two groups. No two transcripts gave one case different bytes.
4. It wrote the 232 cases over release 20261006's tree. Each got its prompt, its verdict, its transcript and a sidecar. The sidecar is rebuilt from the provenance entry and the transcript, and is marked `recovered` because the original sidecar was lost.
5. The rebuilt tree's digest must equal release 20261006's digest overlaid with the provenance entries. It did, and that digest is `docs/musewonder/seed_digest.csv` (sha256 `bc7c057e…`).

`docs/musewonder/seed_recovery.json` lists each recovered case's login and session id. The tests derive the committed digest from the two Haiku 5.5 records alone (`tests/test_finish_musewonder.py`).

No verdict text is new. Every carried verdict is the one release 20261010 published, and its committed annotations already reflect it.
