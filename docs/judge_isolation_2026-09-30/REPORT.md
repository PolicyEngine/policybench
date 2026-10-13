# Judge isolation audit of the published PolicyBench verdicts (2026-09-30)

## Question

On 2026-09-30, during the judging for GPT-6.1 Sol's release, 9 of 134 Opus 5.5 judges read the repo's adjudication decision records and 8 read the policyengine-us checkout. The old `scripts/run_audit_claude.sh` ran each judge from inside the repo with the file and search tools enabled. This audit asks whether any judge behind a verdict in the published release did the same: read files beyond its own prompt, searched, used a shell or browsed.

Trees audited:
- **seed**: the 674 judged cases of release `dashboard-data-20260929`, at the local stage `adds0928-stage2/results/local/adds0928-v3/audit`. GPT-6.1 Sol's release carries 540 of them over byte for byte.
- **unified**: the 668 judged cases of the previous release tree, at the local `results/local/unified_audit/audit`. A unified verdict is still published only if the seed holds the same bytes.

## Method

[`audit_judge_isolation.py`](audit_judge_isolation.py) binds every verdict to the transcript that produced it and classifies every tool call in that transcript. It assumes nothing about what a judge was able to do.

- **Binding.** A verdict counts as bound only when the answer in its transcript equals the verdict, compared as parsed JSON through the writers' own serialisation (`json.dumps(indent=2, sort_keys=True)`).
  - Codex judges: the final message in the case's `codex.log`.
  - `run_audit_claude.sh` judges: the `StructuredOutput` call in the session transcript named by the sidecar's session id. Sessions were searched in `~/.claude/projects`, every subfleet login's config and Logpile's copies.
  - Workflow-subagent judges: the `StructuredOutput` call of the agent whose journal label names the case, across the 21 workflow runs whose journals name a PolicyBench case. Every verdict matched exactly one agent.
- **Tool calls.** Every `tool_use` content part counts (server and MCP tools included), except the final `StructuredOutput`. When a judge launched an Agent, Task or Workflow, its delegates' transcripts are classified too, and their calls count as the judge's. For Codex, every `exec` block and every `mcp:`, `web search:` or patch line counts. Codex 0.144.0, the judges' version, prints all of these; other logs from that version on this machine show them.
- **Context.** For each judge the audit also records:
  - the working directory, and whether it is a git checkout;
  - every CLAUDE.md or memory file injected, with its text as injected (kept with the local audit);
  - any skill loaded into the conversation;
  - whether the judge saw exactly the published `prompt.md`. For `claude -p` judges that is the stdin message; for workflow judges, the numbered lines their Read returned; for Codex, the echoed prompt.

**Validation.** On the GPT-6.1 Sol job's own 139 verdict-producing transcripts, the classifier flags exactly 18 judges. That matches the 9 decision-record readers, the 1 repo searcher and the 8 policyengine-us readers named in that job's `judge_report.md`.

**Differential check.** An independent re-implementation, written from scratch on an Opus 5.5 lane without access to this audit ([`independent/`](independent/), report [`review_independent.md`](review_independent.md)), agrees on all 1,342 rows:
- the affected label (3 yes, 6 unknown, 1,333 no);
- liveness;
- the exact transcript path of every bound verdict.

A second Opus reviewer inside that job re-checked all 1,333 "no" rows and refuted none.

An adversarial review on an Opus 5.5 lane ([`review_redteam.md`](review_redteam.md)) found no second affected verdict. It did find weaknesses in how the first version counted and described things, all fixed here:
- `us_case_notes.csv` and row-annotation reads now count as prior-verdict reads;
- Codex `mcp:` and `web search:` lines are now detected;
- injected nested CLAUDE.md content is now captured;
- git status is now checked directly, since `gitBranch: "HEAD"` appears even outside a repository;
- prompt identity is now verified.

## Results

Counts by wave. The seed is the published release; unified rows count all 668 verdicts, and "live" means the same verdict is also in the seed.

| Tree | Wave | Runner | Verdicts | Live | Bound to transcript | Used tools | Transcript missing |
|---|---|---|---|---|---|---|---|
| seed | Codex (Aug; sidecars backfilled) | run_audit_codex.sh, gpt-5.6-sol | 303 | 303 | 300 | 0 | **3** |
| seed | 2026-09-05 | run_audit_claude.sh, Opus 5 | 132 | 132 | 132 | **1** | 0 |
| seed | 2026-09-22 | 16 workflow subagents, 1 run_audit_claude.sh | 17 | 17 | 17 | 0 | 0 |
| seed | 2026-09-29 | 221 workflow subagents, 1 run_audit_claude.sh | 222 | 222 | 222 | 0 | 0 |
| unified | Codex | run_audit_codex.sh | 314 | 303 | 311 | 0 | 3 (the same 3) |
| unified | 2026-09-05 | run_audit_claude.sh | 183 | 132 | 183 | 1 (the same 086) | 0 |
| unified | 2026-09-22 | 168 workflow, 2 run_audit_claude.sh, 1 main session | 171 | 17 | 170 | 1 main-session verdict (not live) | 0 |

The 2026-09-22 wave spans judgments dated September 22 to 24. The 2026-09-29 wave's run_audit_claude.sh verdict is `082 payroll_tax`, and the 2026-09-22 wave's is `045 snap`. Both ran in a git worktree with Read, Grep and Glob enabled, and both made no tool call.

### Affected: one published verdict

**`us__scenario_086__federal_refundable_credits`** (2026-09-05 wave, Claude Opus 5 through run_audit_claude.sh, live in the seed and carried into GPT-6.1 Sol's release).

The judge ran from the `policybench-wt/newmodels` git worktree. It launched a background Workflow (`verify-actc-diagnosis`, `wf_3ac730e3-7e7`), loaded TaskOutput through ToolSearch and read the workflow's output. The workflow's four agents made 28 calls between them:
- Grep over the repo (patterns `refundable`, `12824`, `eitc`, `24150`, `scenario_086,federal_refundable_credits` and others).
- Read of `annotations/.../us_case_reference_explanations.csv`, `paper/snapshot/20260501/us_scenarios.csv` and `.../reference_outputs.csv`.
- Grep hits in `us_audit_row_annotations.csv` returned the earlier published diagnoses for **this same case**, for 9 of its models.
- A grep of `us_case_notes.csv` returned this case's earlier published case note: `llm_error / credit_phaseout`, 10 wrong models.

The published verdict repeats that class. It is not independent of the earlier verdict, and it must be re-judged.

### Transcript missing: three published verdicts

The published text of these three Codex verdicts appears in no transcript on this machine:
- `us__scenario_014__federal_refundable_credits`
- `us__scenario_015__federal_refundable_credits`
- `us__scenario_015__head_medicaid_eligible`

Each case's `codex.log` holds an answer with the same classes but different wording. The runner rewrites the log and the verdict together, so it cannot leave them out of step. Something after the logged runs replaced these three verdicts, and no record says what. Their sidecars say `backfilled_from: codex.log`, a claim that log does not support. The Codex runner passed `--ephemeral`, so no Codex session store holds them.

The independent re-implementation traced why, in session `3c78d187`:
- At 2026-08-18 01:25:58Z, a `pkill -f run_audit_codex` stopped in-flight Codex re-judges that had already overwritten these three logs.
- At 01:27:48Z, the same session restored 381 `verdict.json` files from Time Machine snapshot `2026-08-17-194721`.

The published verdicts' own logs existed only in that snapshot. The only local snapshot left is from 2026-09-30, and this session is not permitted to read the Time Machine volume. The restore is also why 469 Codex sidecars (in both trees) give 01:27:48Z as their `judged_at_utc`.

Whether these judges used tools cannot be established. They are re-judged with the hardened runner so that the published text carries a bound transcript. None of the three has an adjudication record.

### Exposed through context, without a tool call: one published verdict

**`us__scenario_045__snap`** (2026-09-24, run_audit_claude.sh, Opus 5.5, live). The judge ran from the `r33-20260922c` worktree. Claude Code gave it the checkout's git status, as it does any session in a git repository:
- branch `release-20260922c-child-support-fixed`;
- `reference_audit/2026-09-22/fixes/r33_snap_child_support_treatment.py` listed as modified;
- the latest commit, "Exclude the SNAP child support defect (r33) in release 20260922b (#177)".

This household is the Michigan child-support case that r33 is about. So the judge was told, outside its prompt, that its own case had been excluded for an engine defect that was then being fixed.

The judge called no tool. Its verdict (`llm_error / categorical_eligibility`, no reference flag) rests on facts its prompt states: "child support" appears 14 times there. No adjudication record covers the case today. It is still not independent of the decision history beside it, so it is re-judged too.

Git status also reached three other judge groups; none of them mentions their cases:
- 28 judges on 2026-09-05, whose context listed serving and provenance commits;
- `082 payroll_tax`, whose context listed reference-regeneration commits;
- one verdict that is no longer published.

The full texts are in `session_contexts.json`.

### Not an isolated judge, not published

`us__scenario_020__federal_income_tax_before_refundable_credits` in the unified tree (2026-09-23) was written by the orchestrating main session itself, per its sidecar. The seed re-judged this case, so the release does not publish it.

### Clean

In every other bound transcript the judge used no tool at all, or, for workflow judges, made exactly one Read, of its own case's prompt:
- 300 Codex, 131 from 2026-09-05, 17 from 2026-09-22 and 222 from 2026-09-29 in the seed;
- the matching unified rows.

Every Claude judge, in all three waves, saw the published `prompt.md` byte for byte.

### Context each wave ran with

| Wave | Working directory | Tools available | Injected context |
|---|---|---|---|
| Codex | the policybench repo, `--sandbox read-only` | shell (read-only) | Codex's skill list. No run executed a command. |
| 2026-09-05 | `policybench-wt/newmodels` (git worktree, since removed) | all but Bash, Edit, Write, NotebookEdit, WebFetch, WebSearch, Agent, so Read, Grep, Glob, Workflow and ToolSearch were on | `CLAUDE_CODE_SAFE_MODE` suppressed CLAUDE.md. Every one of these judges had the `workflow-authoring` skill (ultracode: "author and run a workflow for every substantive task") injected as a hidden user message, which is how 086 came to launch a workflow. |
| 2026-09-22 and 2026-09-29 workflow judges | a non-git scratch workspace (12 in the `opus55` worktree) | all, with an instruction to read only the case file | Global CLAUDE.md, AGENTS.md and an auto-memory index. The 12 also had PolicyEngine's and policybench's CLAUDE.md as nested memory when they read their prompt. None of the injected text, captured as injected, holds case facts, verdicts or decisions. |

The hardened runner on `gpt61sol-driver` closes the gaps above:
- It runs each judge from an empty non-git directory with `--tools ""`.
- It denies the file, search, web and shell tools by name.
- It passes `--disable-slash-commands`; its 17 re-judges carry no skill injection.
- It rejects any verdict whose transcript shows a tool call.

### Not contamination, but worth knowing

For 230 of the 303 published Codex verdicts, the prompt the judge saw lacks one line of today's `prompt.md`: the definition of `budget_exhausted_at_ceiling`, which was added in `8b2f1956` (2026-08-11). The other 70 match byte for byte, ignoring Codex stderr lines. Whether that line should have changed any label is a separate question, filed as its own task.

## Fix

Five cases are re-judged with the isolated runner, on judge template v2:
- `086 federal_refundable_credits`: its judge used tools;
- `045 snap`: its judge saw decision history through git status;
- `014 federal_refundable_credits`, `015 federal_refundable_credits` and `015 head_medicaid_eligible`: their transcripts are missing.

Each judge runs from an empty directory outside the repo, with tools off, on a dedicated judge login that is never the desktop login. The new verdicts replace these cases' row annotations and case notes. No adjudication record covers any of the five, so no decision changes. If a re-judge flags the reference, or leaves a scored row outside the model-error classes (`llm_error`, `parse_contract_failure` and `budget_exhausted_at_ceiling`), that is a new reference question, and it goes to Max as a decision. None did: no re-judge flags the reference, every row and case keeps its failure source, and three model rows' failure subtypes change.

The five verdicts stayed published, unchanged, through releases 20260930, 20261006, 20261010 and 20261013. The fix is release `dashboard-data-20261013b`, on top of 20261013: see [`docs/release_20261013b/design.md`](../release_20261013b/design.md).

## Files

- [`audit_judge_isolation.py`](audit_judge_isolation.py): the classifier, as run on this machine on 2026-09-30. It reads local transcript stores, so it is a record, not a CI check.
- [`verdicts.csv`](verdicts.csv): one row per tree and case. It gives the bound transcript (`~` is the audit machine's home directory), the classification, whether the judge saw exactly the published prompt, and `context_exposure` for 045 snap.
- [`tool_calls.csv`](tool_calls.csv): every tool call.
- [`session_contexts.json`](session_contexts.json): every distinct session context (git status) a Claude judge was shown, with the judges it reached.
- [`codex_prompt_identity.json`](codex_prompt_identity.json): each Codex judge's echoed prompt compared with the published one.
- [`review_redteam.md`](review_redteam.md): the adversarial review.
- [`review_independent.md`](review_independent.md) and [`independent/`](independent/): the independent re-implementation, with its scripts and CSV.

The fix is release `dashboard-data-20261013b`, built by [`scripts/release_20261013b.py`](../../scripts/release_20261013b.py).
