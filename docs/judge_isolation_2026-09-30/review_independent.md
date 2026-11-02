I found three affected rows, which come from two distinct judges, and six verdicts I can't bind. Only one of the affected judges is behind a verdict in the published release. Every other verdict in both trees binds by content to a transcript in which the judge used no tool except reading its own `prompt.md`.

**Where the output is.** The CSV is `verdicts_indep.csv` in the job workspace (`~/.subfleet/worktrees/20260930-071142-pb-judge-indep/`). The job rules forbid writing under `~/.subfleet-scratch/pb-judge-isolation-indep`, so it sits at the same relative path in the workspace, committed at `4993247`. Subfleet keeps it under `refs/subfleet-salvage/` in that repo. The helper scripts are beside it: `transcripts.py`, `build_index.py`, `audit_indep.py`, `finalize.py` and `crosscheck_walk.py`. So are `verdicts_indep_details.json` (every tool call, sidecar and prompt check per row) and `summary_table.md`. I did not read the other agent's audit directory, and nothing in either audit tree or the repo was modified.

## How verdicts were bound
- **Codex (611):** the case's `codex.log` final message after `tokens used` equals `verdict.json` as parsed JSON.
- **Claude (724):** a `StructuredOutput` tool_use input equals `verdict.json` as parsed JSON. It was looked up in an index of 1,534 such calls across 1,807 transcripts. Each verdict matched exactly one transcript, not counting the Logpile copies, which agree in all 186 run_audit_claude.sh sessions they cover.
- **Main session (1):** a Bash heredoc in the main session whose JSON equals the verdict.
- **Cross-checks:**
  - A second method walked every JSON row of each Claude transcript; it agreed with the tool-call lists for all 724.
  - The 184 unified `claude.json` envelopes agree on both session id and answer.
  - Sidecar timestamps fall 0.1–2.1 s after each CLI transcript ends.
  - A grep of every codex log for any command, tool or search trace found nothing.
- **Independent review:** a separate Opus reviewer re-checked all 1,333 `affected=no` rows. It refuted no classification. I verified its two corrections to my notes and applied them.

## Counts by tree and wave

| tree | wave | verdicts | bound | missing | affected | live | live and affected | live and missing |
|---|---|---|---|---|---|---|---|---|
| seed | codex | 303 | 300 | 3 | 0 | 303 | 0 | 3 |
| seed | 2026-09-05 | 132 | 132 | 0 | 1 | 132 | 1 | 0 |
| seed | 2026-09-22 | 17 | 17 | 0 | 0 | 17 | 0 | 0 |
| seed | 2026-09-29 | 222 | 222 | 0 | 0 | 222 | 0 | 0 |
| unified | codex | 314 | 311 | 3 | 0 | 303 | 0 | 3 |
| unified | 2026-09-05 | 183 | 183 | 0 | 1 | 132 | 1 | 0 |
| unified | 2026-09-22 | 171 | 171 | 0 | 1 | 17 | 0 | 0 |

What the judges did, by wave:
- **Codex:** no `exec` block and no other tool trace in any of the 611 bound logs.
- **2026-09-05 CLI judges:** 314 of 315 made no call besides the answer. Some of these (51 verdict rows) include one earlier `StructuredOutput` that the schema rejected, followed by a valid retry. I list those retries but don't count them as other tools.
- **2026-09-22 and 2026-09-29 Workflow judges:** all 405 made exactly one call, a Read of their own case `prompt.md`.
- **Later CLI judges (2026-09-22/24/29):** the three sessions made no tool calls.

## Affected verdicts
1. **`us__scenario_086__federal_refundable_credits`, seed and unified: byte-identical and live.**
   - **Judge:** `claude -p` session `aed1cb53` (2026-09-05, `~/.claude/projects/-Users-maxghenis-PolicyEngine-policybench-wt-newmodels/aed1cb53-….jsonl`).
   - **Judge's own calls:** it ran the Workflow tool (`wf_3ac730e3-7e7`, "verify-actc-diagnosis", 4 agents), then `ToolSearch select:TaskOutput`, then `TaskOutput`. It made 35 calls besides its answer.
   - **Delegates' calls, all rooted in `~/PolicyEngine/policybench-wt/newmodels`:**
     - About 25 Grep calls, for patterns such as `scenario_086`, `^scenario_086`, `12824|12,824`, `eitc`, `refundable_ctc|ctc_refundable|additional child tax`.
     - 4 Reads: `us_case_reference_explanations.csv` line 50, `paper/snapshot/20260501/us_scenarios.csv` lines 1 and 72, and `runs/…/reference_outputs.csv`.
     - 2 Globs.
     - `ToolSearch select:Bash`, which found nothing.
   - **What leaked:** Grep output put prior-audit text for this case in front of the delegates: `us_audit_row_annotations.csv` rows 5559 and 5581, plus `us_case_notes.csv`. The `TaskOutput` text the judge read back cites row 5559 and PolicyEngine's trace.
   - **Why it could:** the runner's `--disallowedTools` blocked Bash, Edit, Write, NotebookEdit, WebFetch, WebSearch and Agent. It never blocked Read, Grep, Glob, Workflow, ToolSearch or TaskOutput.
2. **`us__scenario_020__federal_income_tax_before_refundable_credits`, unified: not live.** The seed holds a different verdict for this case, from a 2026-09-29 Workflow judge that read only its prompt.
   - **Judge:** the orchestrating main session `3dd3d124` wrote the verdict itself with a Bash heredoc (2026-09-23 01:36:36Z).
   - **What it did in the 8-call judging window:**
     - read its prompt with `sed` and `awk`;
     - ran PolicyEngine on the case with `triage/pe_case.py scenario_020 … --calc …`;
     - rewrote the case's reference explanation in two CSVs;
     - read the previous verdict from `adds202609/verdicts-board42-b.json`, a call it labelled "Read the previous 020 verdict to adapt";
     - wrote the verdict and validated it.
   - **Earlier in the same context:** 29 more calls about this case, including regenerating references and two aborted judge lanes.

## Missing transcripts
The same three cases are missing in both trees, and all six verdicts are live: `us__scenario_014__federal_refundable_credits`, `us__scenario_015__federal_refundable_credits` and `us__scenario_015__head_medicaid_eligible`.
- **What happened:** at 2026-08-18 01:25:58Z, session `3c78d187` (line 19542) ran `pkill -f run_audit_codex`, killing in-flight re-judges that had already overwritten these three `codex.log` files. At 01:27:48Z (line 19580) it restored 381 `verdict.json` files from Time Machine snapshot `2026-08-17-194721`.
- **Why they can't be bound:** the published verdicts' own logs existed only in that snapshot. The codex runs were `--ephemeral`, so no rollouts were kept.
- **Where I looked, with no match:** every `codex.log` copy under the PolicyBench results trees, the Aug 17–18 lane rollouts, and Logpile's codex copies. The only local snapshot left is from 2026-09-30, and `/Volumes/TimeMachine` returns "Operation not permitted" to this session.
- **Possible recovery:** an external Time Machine backup may still hold the original logs. Checking it would need access this session didn't have.

## Anomalies
- **Stale codex sidecars:** 469 codex sidecars (233 seed, 236 unified) give the 01:27:48Z restore time as `judged_at_utc`, not the judging time. For the three missing cases, `backfilled_from: codex.log` and the reported model point at the killed re-run.
- **Stray temp files:** three `verdict.json.tmp` files in unified hold the killed re-runs' answers.
- **Codex prompt drift:** 463 codex verdicts were judged on an older prompt. It lacks one line the published `prompt.md` now has: "- budget_exhausted_at_ceiling: …". Before comparing, I stripped the codex error and warning lines that `2>&1` interleaves into the log; otherwise the prompts are identical.
- **Claude prompts match:** all 724 Claude judges saw text identical to the published prompt. 237 seed Workflow judges read it from another tree (adds0928-provisional 201, v2 13, final 7, unified 16), with identical content.
- **Sidecar integrity:** all 1,342 `verdict_sha256` values match. All 221 `prompt_sha256` values and all agent and workflow ids match.
- **Weak sidecar ids:** 184 Workflow sidecars from 2026-09-22/23 carry no workflow or agent id; 12 of them instead carry a workflow id as `session_id`, and their parent session `3c78d187` isn't named anywhere. I found all 184 agents by content.
- **Context that reached judges without a tool call:** none of these mentions the case except one, and I did not mark any of them as affected.
  - The workflow-authoring skill text was injected as a user turn into all 318 CLI sessions (319 rows). The one judge that delegated used the Workflow tool that text describes.
  - The git status went into 32 CLI rows. For `scenario_045 snap` (live) it lists SNAP commits: "Exclude the SNAP child support defect (r33)" and "Add a note on the five SNAP BBCE households…".
  - `~/PolicyEngine/CLAUDE.md` and the repo's `CLAUDE.md` were auto-loaded into 12 Workflow judges, 4 of them live. Neither file mentions the case, the audit or verdicts.
  - The parent session's user request was relayed to Workflow judges. For 9 unified income-tax judges (not live), that request was about SNAP and BBCE.
- **Isolation was by instruction only for Workflow judges:** the sampled `wf_d0fdd77d` judge had Bash, Edit, Write and Skill defined and didn't use them.

DONE