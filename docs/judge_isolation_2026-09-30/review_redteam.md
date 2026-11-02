# Red-team of the PolicyBench judge-isolation audit

I found no second live verdict that used tools. But the audit claims more than its evidence supports in several places. Two of the six conclusions are misstated, and one hides a real provenance gap. I modified no files; everything below comes from reads and greps.

## Confirmed problems

**1. The counts in conclusion 1 don't match the audit's own `verdicts.csv`.** *Changes 1.*
- The file binds 611 Codex, 319 run_audit_claude.sh and 405 Workflow verdicts, not 611 / 315 / 390.
- That totals 1,335 bound rows, plus 7 unbound, for 1,342 rows (matching `summary.json`).
- The 4 extra run_audit_claude.sh verdicts are:
  - `us__scenario_045__snap` (seed and unified, judged 2026-09-24; `verdicts.csv:272`, `:944`)
  - `us__scenario_015__federal_income_tax_before_refundable_credits` (unified; `:770`)
  - `us__scenario_082__payroll_tax` (seed, judged 2026-09-29; `:456`)

**2. Conclusion 6 assigns waves to runners by date alone.** *Changes 6.*
- `wave_of()` (`audit_judge_isolation.py:66-71`) puts those run_audit_claude.sh judges into the "2026-09-22" and "2026-09-29" waves, which conclusion 6 calls Workflow-subagent waves.
- Two of them are in the release: 045 snap and 082 payroll.
- They had tools available. `run_audit_claude.sh:130` blocks only Bash, Edit, Write, NotebookEdit, WebFetch, WebSearch and Agent, which leaves Read, Grep, Glob, Workflow, ToolSearch and TaskOutput.
- They ran from git worktrees. 082 ran in the release worktree itself (transcript `9b0255fa…jsonl` shows `"gitBranch":"adds-0928-stage2"`).
- Both made zero tool calls, so their verdicts stay clean.

**3. The 2026-09-05 judges were pushed toward tool use, and the classifier can't see how.** *Doesn't change 2, but the context was not benign.*
- Every judge transcript contains a hidden user message that loads the `workflow-authoring` skill. It says: "When a system-reminder confirms ultracode is on … author and run a workflow for every substantive task by default" (`-Users-maxghenis-PolicyEngine-policybench-wt-newmodels/795387a7…jsonl` lines 8-9). An `ultra_effort_enter` attachment comes with it. The same injection is in 082's transcript (`9b0255fa…jsonl` lines 7-11, 23).
- `classify_claude` (lines 225-237) records only attachment events, so this never appears in `instructions_files` or `attachment_kinds`.
- `judge_cwd_in_git_repo` is blank for all 315 of these verdicts. The events show `cwd` `policybench-wt/newmodels` and `"gitBranch":"add-new-models-2026-09"`, so they ran in a git worktree with Read, Grep, Glob and Workflow on. That is the mechanism behind 086.
- I checked independently. Among all transcripts in that project, the only judge that called anything besides StructuredOutput is `aed1cb53` (086) and its 4 workflow agents. The other four sessions with tool calls (`5df551ff`, `bd624e7b`, `4ad7006d`, `461fa671`) are orchestrator sessions using Bash, and none of them appears in `verdicts.csv`.

**4. Conclusion 3's "earlier answer" framing is unsupported.** *Changes 3; these three live verdicts have unknown provenance.*
- The runner rewrites `codex.log` on every exec (`run_audit_codex.sh:86`). It only runs a case that has no valid verdict (line 70), and it writes the verdict and the log together (lines 87-91). So the runner cannot leave a verdict that differs from its own log.
- `codex_run.log` (636 `[ok]` lines, "636/636 verdicts present") and `codex_run2.log` never list 014 or 015 `federal_refundable_credits`. Those verdicts existed before any logged run.
- `015__head_medicaid_eligible` is `[ok]` in both runs (`codex_run.log:96`, `codex_run2.log:85`). Its `codex.log` is most likely run 2's, the latest, not an earlier answer. Something after run 2 replaced the verdict.
- The verdict writes "Indiana’s" with a curly apostrophe; the log writes "Indiana's".
- All three sidecars say `"backfilled_from": "codex.log"`. Their runner and model (`gpt-5.6-sol`) were assigned after the fact, from a log that does not hold the verdict.
- No codex session store exists for those accounts (`~/.codex-3/sessions` and `~/.codex-4/sessions` are absent; the runner used `--ephemeral`).

**5. All 303 Codex sidecars in the release are backfilled.** *Weakens 1 and 5.*
- Each has `"backfilled_from": "codex.log"`. `judged_at_utc` is the backfill time, not the judging time: dozens share `2026-08-18T01:27:48.1…`. So the "2026-08-18 to 2026-09-02" date range is not evidence.
- None records `prompt_sha256`, so the audit never checked that Codex verdicts were judged on the published prompt. The log echoes the prompt. I compared one by eye (`us__scenario_000__payroll_tax`), and it matched.

**6. The Codex classifier can't detect MCP or web-search calls.** *Latent bug; 5 still holds on direct evidence.*
- The catch-all regex `^([a-z_ ]+)$` (line 353) can't match lines with a colon, such as `mcp: codex_apps/github.create_pull_request started` or `web search: …`.
- Codex 0.144.0 does print those lines (`~/m6-sol-lanes/sol-ce-purpose-prod-r1-a.out.err.log:21116-21129`, version on line 2; `remarr-r2.log:39886`).
- I grepped every `codex.log` in both trees for `mcp:`, `web search:`, `apply patch`, `patch:`, `tool ` and a bare `exec`: zero hits. Every log has exactly three lone-word lines (`user`, `codex`, `tokens used`): 1,275 in 425 files (seed) and 1,464 in 488 files (unified).

**7. 086's adjudication reads aren't counted as adjudication.** *Conclusion 2 names the files, but `summary.json` understates it.*
- `path_class` flags only paths containing "adjudicat" or "decision" (lines 171-172). So the 086 row (`:475`) has `read_adjudication_records=0`.
- Yet its delegates read `us_case_reference_explanations.csv`, and conclusion 2 says they also consumed `us_case_notes.csv`. That file holds earlier judges' case verdicts: its columns include `case_failure_sources`, `reference_suspect` and `case_annotation`.

**8. The context claim in conclusion 6 isn't backed by captured content.** *Weakens 6.*
- Twelve Workflow verdicts had `PolicyEngine/CLAUDE.md` and `policybench/CLAUDE.md` injected as nested memory (`verdicts.csv` rows 259, 542, 827, 830, 931, 1026, 1031, 1047, 1124, 1210, 1221, 1322).
- `injected_instructions.json` holds neither file. Its 7 entries are 4 versions of the global CLAUDE.md, the global AGENTS.md and two MEMORY.md files.
- I read the current versions of both: no case facts. The versions in effect at judging time were never captured.

**9. Workflow judges read prompts from other trees.** *Residual risk; doesn't change any conclusion.*
- Their Read targets are under `adds0928-provisional`, `adds0928-v2` or `unified_audit`, never the published `adds0928-v3`. `path_class` (line 168) counts any `/audit/cases/<case>/prompt.md` as the judge's own prompt.
- For the 2026-09-29 wave, `write_verdicts.py:68` compared the prompt bytes only at write time. For the 2026-09-22 wave, `judge_stages.py` `stage_write` does no prompt check at all.
- The audit could have compared the Read result stored in each transcript, but didn't. One spot check (`us__scenario_014__payroll_tax`) shows the same prompt hash in both trees today.

**10. The git-repo flag is wrong for Workflow agents.** *Minor.*
- They show `judge_cwd_in_git_repo=False` while running in git worktrees: row 259 (`opus55`, False) against row 770 (same directory, True). The agent transcripts record `"gitBranch":"HEAD"`.

## Checked and found sound
- **Sidecar hashes:** every sidecar hashes to its verdict. Where a prompt hash was recorded, none differs from the current `prompt.md` (tested on the first hex character, which catches 15 of 16 mismatches).
- **Workflow binding:**
  - Every `bound_agents_same_answer` is 1.
  - Every agent id matches its transcript path, and the Workflow column matches the path.
  - The one re-judge (`067__dependent1_medicare_eligible#r1`) is bound to the re-judge agent. Its extra instruction only names the hedge ("rationale: 'may be'").
- **Live copy against the Logpile copy for 086:** both hold the same 4 tool calls (Workflow, ToolSearch, TaskOutput, StructuredOutput). Its 4 workflow agents are present.
- **Tool-call shapes:** the classifier catches any content type ending in `tool_use` (server and MCP tools included). Any unknown tool name, including TaskOutput, Monitor and ToolSearch, marks the verdict affected.
- **Workflow agent task text:** in the judge workflows, none contains adjudication, decisions, `reference_suspect`, `us_case_`, `annotations/`, `policyengine-us` or `verdict.json`. Other workflows in that session do contain such terms (e.g. `wf_7fdf90ed`, `wf_0d2f95b5`), but none is bound to a published verdict.
- **Published `prompt.md` files (674):** "adjudicated" appears only in the shared boilerplate on line 3. Nothing else carries decisions, notes or rulings. The "AUTHORITATIVE ENGINE FACTS" sections are engine facts, not decisions. 182 prompts and 182 verdicts include `ox-alpha`.
- **Injected global CLAUDE.md, AGENTS.md and MEMORY.md:** none mentions PolicyBench case content.
- **Conclusion 4:** the main-session verdict is not in the release (row 784, `live_in_published_release=False`).
- **Codex context:** there is no `AGENTS.md` in the repo, in `~/PolicyEngine`, or in `~/.codex-3`. Codex did load a skills list (a "Skill descriptions were shortened" warning appears in the logs), which I did not inspect.

## Not established
- Whether the Workflow judges saw the published prompt bytes (item 9).
- What produced the three unbound verdicts (item 4).
- The exact CLAUDE.md contents at judging time (item 8).

I couldn't write the plan file or exit plan mode because those tools weren't available in this session.