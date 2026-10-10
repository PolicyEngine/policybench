# Reference adversary, October 5–6, 2026

This directory records a pass whose only job was to attack PolicyBench's US references. It flagged the scored cells where many models, or several of the strongest, agree on the same wrong answer. A blind judge then worked each flagged cell from primary law before seeing how the engine computed the reference. Two engine-side checks tested every reference against its output's definition and against where its 2026 parameter values come from.

The frozen run is `paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace`, with 46 models and 1,928 scored cells, and references from policyengine-us 2.15.17 plus `latest_final`.

- 61 cells were flagged. 9 belong to other audits, so 52 were run.
- The adversary's verdicts: 45 `reference_holds`, 6 `reference_wrong` and 1 `definition_mismatch`.
- In 10 cases, web search results listing PolicyEngine and GitHub pages reached the judge, which the run's audit did not check. Those 10 were re-judged. The prompt asked the search tool to exclude those domains, and an audit read every result. No result from a blocked source reached the judge, and every verdict stayed the same.
- An independent agent checked each of the 7 that did not hold:
  - CONFIRMED: four engine defects behind four references (Arizona 018, Ohio 025, Colorado 043, New York 082).
  - AMBIGUOUS: a definition-scope question (Pennsylvania 123), which reaches four cells across two scenarios.
  - REFUTED: North Carolina 026, covering two cells; both references stand.
- Max ruled on 2026-10-06 (d1022). The next release after dashboard-data-20261006 excludes the eight cells. Each defect cell is regenerated later, once a fixed policyengine-us version lands.

This PR adds evidence and tooling only. It changes no reference, exclusion record or score. `proposed_changes.json` holds the records a release installs.

## Design

PolicyBench's diagnosis judge (`docs/audit.md`) explains why models miss. Its prompt treats the reference and its derivation as correct, so it is not built to find a wrong reference. The reference adversary is a separate pass, and it never changes a score.

1. **Consensus trigger** (`policybench consensus-flags`, `policybench/consensus.py`). Each model's prediction is rounded to a key, and models sharing a key form a cluster. A cluster is wrong when its key differs from the reference by more than the tolerance, or, on an eligibility output, when its key is not the reference. A wrong cluster flags its cell when it has at least `min_models` members, or at least `min_top` of the `top_k` best models. A wrong cluster at zero needs `zero_cluster_min_models` members either way.
2. **Cases** (`policybench adversary-prepare`). There is one two-stage case per flagged cell, minus the cells listed in `covered_elsewhere.json`. Each case freezes the engine's derivation of the reference, and each of the 52 derivations states the payload's reference value: 35 as an amount, and 17 eligibility outputs in words.
3. **Stage 1, law first.** The judge sees the household prompt, the output's definition, the reference value and each consensus member's model, answer and explanation, but not the engine derivation. It works the answer from statutes, regulations, forms and agency publications. It dates each rule against the 2026-07-03 freeze and says which answer the law supports.
4. **Stage 2, reconcile.** A fresh call gets the frozen stage 1 output (bound by its sha256) and, only now, the derivation. It returns `reference_holds`, `reference_wrong`, `definition_mismatch` or `prompt_ambiguous`, with citations and a suggested adjudication.
5. **Blinding** (`scripts/run_reference_adversary_claude.sh`). Each call runs from an empty directory outside any repository, in safe mode, with exactly two tools, WebSearch and WebFetch.
   - WebFetch is denied on policybench.org, policyengine.org, github.com and raw.githubusercontent.com.
   - WebSearch has no deny rule, so its results reach the judge. The prompt now asks the judge to pass those domains as `blocked_domains` on every search.
   - After each call the runner audits the transcript. It rejects an output if the judge used another tool, got content from a blocked URL or one naming PolicyEngine or PolicyBench, searched for either, saw any user message but its prompt, cited a blocked source, or failed the stage's schema.
   - It also rejects an output when a search result lists a blocked URL or names PolicyEngine or PolicyBench. The run below predates this check; see [Search results from blocked sources](#search-results-from-blocked-sources).
6. **Collection** (`policybench adversary-collect`). This writes the verdict tables and the adjudication queue. The queue lists every case other than `reference_holds`, and every case with an inconsistent verdict. The command fails when a case has no usable verdict, unless `--allow-missing` is given.
7. **Independent verification.** A separate agent rechecked every non-holding verdict against primary law and the engine source (`verification/independent/`). The machine was overloaded, so no verifier ran a simulation. Engine values come from the frozen probes (`verification/probes/`, written by `scripts/engine_probe.py`) and from reading the source.
8. **Engine-side checks** (`policybench/definition_conformance.py`, `policybench/publication_sources.py`). These run on the reference system and are summarized below.

## Flag parameters

| Parameter | Default (this pass) | Prototype |
|---|---|---|
| `min_models` | 15 | 15 |
| `top_k` / `min_top` | 5 / 3 | 5 / 3 |
| `tolerance` | $1 | $1 |
| `answer_rounding` | `nearest` (half-up to whole dollars) | `truncate` |
| `zero_cluster_min_models` | 15 | 15 |
| `binary_outputs` | `mismatch` | `skip` (eligibility outputs never flagged) |
| Cells flagged | **61** of 1,928 | 41 |

Inputs:

- The pass read the frozen run and its annotations as release dashboard-data-20260930 committed them at `8b4c0ca1` (#187). Later commits rewrote several of the working tree's copies: release dashboard-data-20261006 (#202) the run's payload, exclusion record and annotations, and #204 one of the reference system's convention modules. So every script in `scripts/` reads the inputs below only through `scripts/pass_inputs.py`. It writes `git show <commit>:<path>` to scratch and stops (SystemExit) unless the bytes match the pinned sha256. Each script stages everything it reads before it computes or writes anything, and before it imports the engine. No script reads the working tree's copy. `<run>` is `paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace`.

  | Input | Commit | sha256 | Read by |
  |---|---|---|---|
  | `<run>/data.json.gz`, the payload | `8b4c0ca1` | `1e029aaa87d1dfbd2ceee88419599a919dd7c9d4aba78a308ec48d008d54ae18` | `consensus-flags`, `adversary-prepare`, `definition_conformance.py`, `publication_sources.py`, `leaderboard_impact.py` |
  | `<run>/predictions.csv.gz` | `8b4c0ca1` | `ca2c4c48c7fd3e680c9c61a7380ecfcb60ce95f913c5c363762e023949d8ad12` | `leaderboard_impact.py` |
  | `<run>/reference_outputs.csv` | `8b4c0ca1` | `e8bbba8fd3e90f78e7c0e83df06227bc1c94563e92f7405fe12be853a30b2466` | `definition_conformance.py`, `publication_sources.py`, `engine_probe.py`, `build_proposals.py`, `leaderboard_impact.py` |
  | `<run>/reference_outputs.csv.meta.json` | `8b4c0ca1` | `816fef53c452d8520a321bc12bc29b28da1e7956a06818e5ec13d7fc7b371a4b` | `definition_conformance.py`, `publication_sources.py`, `leaderboard_impact.py` |
  | `<run>/reference_exclusions.json` | `8b4c0ca1` | `bf4e6a249aeee01d0b71f5834ef7a35c4bab2266d2c59d0e81b12a0da44281c2` | `publication_sources.py`, `engine_probe.py`, `build_proposals.py`, `leaderboard_impact.py` |
  | `<run>/scenarios.csv` | `8b4c0ca1` | `71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a` | `definition_conformance.py`, `publication_sources.py`, `engine_probe.py`, `leaderboard_impact.py` |
  | `<run>/scenarios.csv.meta.json` | `8b4c0ca1` | `03a66e90b86e9bd0cc77f27520784bd581777762f749675dc716e24c1b8eaebb` | `leaderboard_impact.py` |
  | `annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_case_reference_explanations.csv` | `8b4c0ca1` | `6cccc5586815f2ecc4f1b527e79e141f858d0e75cc30b3a867d107909cbb38c4` | `adversary-prepare` |
  | `policybench/benchmark_specs.json`, the output definitions | `8b4c0ca1` | `ce233f8cbb0549b33469b5929fc6df3cd5d064c727529afafe26ff2da7970cc5` | `definition_conformance.py`, `publication_sources.py`, `engine_probe.py` |
  | `reference_audit/2026-10-05-payroll/program_classification.json`, #194's classification of state paid-leave programs | `049f4f09` | `282cbf25ce9110a3c5c51873b7ca0e89f1f5ed38592b0c5b51d393f08000089a` | `definition_conformance.py` |
  | `reference_audit/2026-10-05-reference-adversary/proposed_changes.json` | `4db91b5f` | `3a6e5920a2d02e94e1df52c95c1def2739f3eb21b1fb67fc74a7d68219a749bf` | `leaderboard_impact.py` |
  | `reference_audit/2026-10-05-reference-adversary/verification/definition_conformance.json` | `4db91b5f` | `05e503f1b291c505b90182395c4afb88844dcb45fb2952c004ca09d4273894a0` | `build_proposals.py` |

- `policybench` loads `benchmark_specs.json` itself, once per process: first as `policybench.scenarios` is imported, and every later lookup of an output's engine variable or aggregation uses that loaded copy. The three engine-side scripts therefore point the package at their staged copy (`pass_inputs.use_staged_specs`) before they import anything else from it, in the main process and in every worker. A checkout whose definitions have changed since the pass does not change what they compute. `leaderboard_impact.py` is the exception. It scores with `policybench analyze` in a child process and treats the definitions as part of the checkout's scoring code, which its published-reproduction check covers.
- The reference system is policyengine-us 2.15.17 plus `latest_final`, built from the convention modules below as `8b4c0ca1` held them. They are read by `definition_conformance.py`, `publication_sources.py` and `engine_probe.py`. The main process and every worker stage their own copy; workers are started with the spawn method, so none inherits the main process's system. `latest_final` loads `latest_conventions` (the nine `latest_c_*` modules) and `latest_md_local_output_scope`. #204 later rewrote `latest_alt_snap_mortgage_residence.py`, which `latest_final` does not load, but `verification/definition_conformance.json` records every module's sha256.

  | Module | Commit | sha256 |
  |---|---|---|
  | `reference_audit/2026-09-22/fixes/r19_irs_sales_tax_2025.json` | `8b4c0ca1` | `7cf93799aad6a8c3a6fc70e7df4acc6043202a1ecc083f2c3101f76b87a85eae` |
  | `reference_audit/2026-09-28/fixes/alt_conventions_r25.py` | `8b4c0ca1` | `0f77fdd44e758581f7e563b0f7b70c4d4359a833b08a4ac45a614c380938775e` |
  | `reference_audit/2026-09-28/fixes/latest_alt_r02_ira_219g.py` | `8b4c0ca1` | `3e71bab1db867988544e6f87f6dda4dc7c719d51320fbbb7558cd574a0374f6e` |
  | `reference_audit/2026-09-28/fixes/latest_alt_salt_refund_no_prior_benefit.py` | `8b4c0ca1` | `d8a314093466caf5fe0a226f1060acba2e4364c4b87befbd80639ebf41cc4a2c` |
  | `reference_audit/2026-09-28/fixes/latest_alt_snap_mortgage_residence.py` | `8b4c0ca1` | `00cd13886a8c3d03c4e84944d35f7e8a1448af26838e8bc0761b914b887c70cd` |
  | `reference_audit/2026-09-28/fixes/latest_alt_unlisted_hours_40.py` | `8b4c0ca1` | `5e6538a903112243ad85051ccba26b6133bdfbd5b9e5ba3dfa81ba690c061b32` |
  | `reference_audit/2026-09-28/fixes/latest_c_ca_hold_2025.py` | `8b4c0ca1` | `f19a47b9583032a0602a31e52f995eee824a427a76e87a9d4257d6682a016fa2` |
  | `reference_audit/2026-09-28/fixes/latest_c_id_hold_2025.py` | `8b4c0ca1` | `39fb99292691600cd273a1c6ef3c90847453e21e4d7b872603bcaac71727f8a5` |
  | `reference_audit/2026-09-28/fixes/latest_c_irs_sales_tax_2025.py` | `8b4c0ca1` | `7f7fd235b29c45d1d5cceded0c3391aceb38740518dfda770e3aebcc3003228e` |
  | `reference_audit/2026-09-28/fixes/latest_c_md_2026.py` | `8b4c0ca1` | `8111c77ffd2e43d434d083994a7e8506ba42461a0845b33ac47ce0df988c2c76` |
  | `reference_audit/2026-09-28/fixes/latest_c_mi_published_2026.py` | `8b4c0ca1` | `787cf837422e0bdf331a8e01a6fa8e8f2e3b78c35c248a4da83f3b2dbfa9ef9e` |
  | `reference_audit/2026-09-28/fixes/latest_c_mn_published_2026.py` | `8b4c0ca1` | `02a8ccc1fce71485fc9411d4a55f33226de4c8de09cf6375f99866b79da70522` |
  | `reference_audit/2026-09-28/fixes/latest_c_mo_published_2026.py` | `8b4c0ca1` | `0474524c83a7eb0c8440abf06bbeee38d4394e08260464d0dacb195ed3a8d916` |
  | `reference_audit/2026-09-28/fixes/latest_c_snap_hold_fy2026.py` | `8b4c0ca1` | `3a8709ef36582af2248e460136db618fd319d490b7aeed94adbd6143ad9c07dd` |
  | `reference_audit/2026-09-28/fixes/latest_c_wi_published_2026.py` | `8b4c0ca1` | `4edf4c714c05d300e6fa32c4b56879aad8aa0de1d9ddd9a77987eefe3b06acce` |
  | `reference_audit/2026-09-28/fixes/latest_conventions.py` | `8b4c0ca1` | `4155ed4a0be72c907815b33e2b3603cf0b5ea3eca351ad7509f8bd9ea5bb8ddb` |
  | `reference_audit/2026-09-28/fixes/latest_final.py` | `8b4c0ca1` | `dbbdd228b99933c6f336af97970821c25c863a18606285e8d6d9ffb3bc9af78e` |
  | `reference_audit/2026-09-28/fixes/latest_map_stated_hours.py` | `8b4c0ca1` | `b210e780a31cfa0a3a0da2c49a8068ee14f00029b3ed39c00be67a1e917eda21` |
  | `reference_audit/2026-09-28/fixes/latest_md_local_output_scope.py` | `8b4c0ca1` | `53a6de3cd9b149467e5d86a5bb1fcc258e859478a7c16b7d3df951c713e423dd` |
  | `reference_audit/2026-09-28/fixes/latest_state_conventions.py` | `8b4c0ca1` | `56e62e399d20ba8c8d9c5dc9bc7ea6681e74d2b529fa38561dbc8e8b2a90b442` |

- Who checks the pins:
  - `definition_conformance.py`, `publication_sources.py`, `engine_probe.py`, `build_proposals.py` and `leaderboard_impact.py` stage every input above that they read, and stop on any sha256 mismatch before they compute or write anything. The engine-side scripts also stop before they import the engine or start a worker. `pass_inputs.py` is the only file that holds a pin, and each script checks that the `pass_inputs` it imported is the one beside it. `publication_sources.py` has no mode that builds a report from a saved file.
  - `tests/test_reference_adversary_inputs.py` checks that each commit holds its pinned bytes, that the committed evidence records the same hashes, and that this table lists each pin with the scripts that stage it. It also checks that any changed byte is refused, that each script refuses #202's run before it computes or writes, and that a wrong convention or definitions pin stops each script before the engine is imported.
  - An audit hook (`tests/working_tree_fence.py`) fails any open of the working tree's copy of a pinned input, `benchmark_specs.json` included. It is armed while the scripts stage and read their inputs, and in every process, workers included, of the slow regenerations below. A copy of the package with changed definitions, put first on the path, does not change the engine variable the scripts' helpers look up.
  - `tests/test_reference_adversary_impact.py` checks the impact script from a checkout whose working-tree run and proposals are junk. Its slow regeneration runs under the same hook in the script and in its scoring children, except that `policybench` may read its own `benchmark_specs.json` there.
  - `consensus-flags` and `adversary-prepare` read the payload and annotations at the paths they are given, and record the payload's path and sha256 in their output. `tests/test_consensus.py` and `tests/test_reference_adversary.py` read the payload and the explanations from `8b4c0ca1`.
- Top 5 by the payload's `modelStats` order: gpt-6-sol, claude-opus-5.5, gpt-5.6-sol, gpt-6-luna and claude-sonnet-5.5.
- `consensus_flags.json` holds the default run, and `consensus_flags_prototype.json` reproduces the 2026-10-05 prototype.
- `verification/flags_table.md` lists all 61 cells, each with its cluster, its exact-model count and whether the prototype flagged it.

## Flagged, skipped and run

61 cells were flagged, and 9 were skipped because another audit owns them (`covered_elsewhere.json`). The other 52 were run.

| Skipped cell | Owner | Reason |
|---|---|---|
| scenario_051 state income tax (LA) | #192 | The Louisiana 2026 standard deduction audit: the reference uses policyengine-us's own CPI computation of the 2026 deduction rather than a published amount |
| scenario_077 state income tax (LA) | #192 | Same |
| scenario_028, 032, 043, 081, 082, 123 `payroll_tax` (PA, MN, CO, MA, NY, PA) | #194 (cos d972) | The state payroll components audit: the reference counts paid-leave and disability employee shares that the employer may, but need not, pass on, while the output asks for "mandatory" employee payroll taxes |
| scenario_031 head Medicaid eligibility (CA) | #197 | Rewrites the scenario_031 annotations to the engine's California disregard, following a finding from the Medicare Part B audit (#193) |

Before choosing the skips, the pass checked #191, #193 and #196. None of the cells those PRs move was flagged; #196's New York City moves are on `local_income_tax`, which no flagged cell is.

## Verdicts

| Class | Cases |
|---|---:|
| `reference_holds` | 45 |
| `reference_wrong` | 6 |
| `definition_mismatch` | 1 |
| `prompt_ambiguous` | 0 |
| contaminated or invalid | 0 under the audit at run time; 13 outputs in 10 cases under the current audit, all re-judged (next section) |

The counts are the same with the 10 re-judged cases' outputs in place of the originals.

The adversary rated 40 verdicts high confidence and 12 medium (39 and 13 with the re-judged outputs).

Stage 1 sided with the reference in 42 cases, with the consensus in 6, with neither in 2, and found both readings defensible in 2. With the re-judged outputs, those are 41, 6, 3 and 2. Stage 2 overruled a stage-1 finding twice, both times keeping the reference:

- scenario_023 state income tax: stage 1 had used California amounts published after the freeze.
- scenario_026 child3: stage 1 had missed North Carolina's 42 CFR 435.218 election.

The re-judge adds a third, scenario_013 SNAP, described in the next section.

`verification/verdict_table.md` has every verdict of the original run with its citations. `runs/collected/` has the machine-readable tables, and `runs/claude/cases/<case>/` has each case's prompts, outputs, sidecars and transcripts.

## Search results from blocked sources

`verification/search_exposure.md` and `.json`, from `scripts/search_exposure.py`.

**What the review found.**

- The runner denies the blocked domains to WebFetch only. WebSearch has no deny rule, so the search tool's results, a list of links and its written summary of them, reach the judge.
- The run's transcript audit read each search's query, but not its results.
- The code review of this PR found results listing policyengine.org and github.com/PolicyEngine pages in the run's transcripts.
- The audit now reads every search result. Run over the original transcripts, it flags 13 of 104, in 10 cases. They contain 28 searches whose results exposed a blocked source (a search can expose more than one):

  | Blocked source | Searches |
  |---|---:|
  | github.com/TheAxiomFoundation (rulespec-us issues) | 15 |
  | github.com/PolicyEngine (policyengine-us and policyengine-taxsim issues, one pull request) | 12 |
  | result text naming PolicyEngine | 12 |
  | www.policyengine.org | 1 |
  | another GitHub account | 1 |

**The re-judge** (`runs/claude-rejudge/`).

- On 2026-10-06, from 21:12 to 22:58 UTC, a separate lane re-judged the 10 flagged cases. Their flags are `runs/rejudge_flags.json`.
- The cases, derivations and schemas are those of `runs/claude`. Each stage-1 prompt differs in one line, the source rule, which now asks for `blocked_domains` on every search.
- 160 of the 175 searches passed it, and the current audit flags none of the 20 transcripts.
- `adversary-collect` (`runs/collected-rejudge/`) finds 10 verdicts, none missing or inconsistent, and queues Colorado 043.

**Outcome.** Every verdict is unchanged, including Colorado 043's `reference_wrong` (high). Confidence moved in three cases: scenario_030 and scenario_079 SNAP from high to medium, and scenario_115 from medium to high. One stage 1 moved, scenario_013 SNAP (Arizona):

- The reference is $240: the $24 minimum benefit for March to December. It rests on the derivation's statement that from March 2026 Arizona's expanded categorical eligibility reaches gross income up to 200% of the poverty guideline. The household's gross income is above the earlier 185% limit and below 200%.
- All 46 models answered $0.
- The original stage 1 dated the change to March 1, 2026 "from search-index text attributed to the DES change log". It noted that it could not open the DES manual. Its searches had returned github.com/TheAxiomFoundation/rulespec-us/issues/1460.
- Re-judged blind, stage 1 could not date the change, because the DES manual returned 403 errors. It applied 200% to all twelve months and found $288, which supports neither the reference nor the consensus.
- Stage 2 held the $240 reference (medium). It took the March start from the engine's derivation. A secondary source it cites, DB101, lists the 185% limit for October 2025 through September 2026.
- No run confirmed the effective date from a primary source; see open items.

## The seven non-holding verdicts

| Cell | Adversary | Independent check | Reference | Law | Models exact: reference / law |
|---|---|---|---:|---:|---|
| scenario_018 AZ state income tax | reference_wrong (medium) | **CONFIRMED** engine defect | 1,146.05 | 1,137.30 | 0 / 12 |
| scenario_025 OH state income tax | reference_wrong (medium) | **CONFIRMED** engine defect | 1,921.57 | 1,916.60 | 0 / 0 |
| scenario_043 CO state refundable credits | reference_wrong (high) | **CONFIRMED** engine defect | 19 | 0 | 0 / 39 |
| scenario_082 NY state refundable credits | reference_wrong (high) | **CONFIRMED** engine defect | 667 | 1,187.61 | 0 / 0 |
| scenario_123 PA state income tax | definition_mismatch (medium) | **AMBIGUOUS** (definition scope) | 3,070.06 | 4,451.56 on the other reading | 0 / 33 |
| scenario_026 NC child1 Medicaid eligible | reference_wrong (medium) | **REFUTED**: the reference holds | 1 | 1 | 1 / 1 |
| scenario_026 NC child2 Medicaid eligible | reference_wrong (medium) | **REFUTED**: the reference holds | 1 | 1 | 1 / 1 |

"Exact" means within $1 of the value, out of 46 models. The verifier's files hold the complete law, engine paths, model answers and fix specifications. Each was checked against upstream policyengine-us main at 2.29.11 (commit 4c900b6d), and all four engine defects are still on main.

### Arizona standard deduction indexing (scenario_018), CONFIRMED

`verification/independent/az_018.md`

**Law.**

- Laws 2026, Ch. 140 (HB 4168) was approved on 2026-06-13, before the freeze. It set the single standard deduction at $15,750 "subject to subsection H of this section".
- A.R.S. 43-1041(H) requires the department to adjust that amount "in the same manner in which the federal basic standard deduction is adjusted for inflation pursuant to section 63".
- The federal amount starts from the same $15,750 base (26 U.S.C. 63(c)(7)(B)), and Rev. Proc. 2025-32 s. 4.14 gives $16,100 for 2026. Arizona's 2026 single deduction is therefore $16,100.
- The tax is 2.5% × ($61,592 − $16,100) = $1,137.30.
- The verifier found no reading that yields $15,750 for 2026.

**Engine.**

- `parameters/gov/states/az/tax/income/deductions/standard/amount.yaml` puts `uprating: gov.irs.uprating` on the parent node, with no `propagate_metadata_to_children`.
- policyengine-core 3.32.8 uprates only leaf parameters whose own metadata carries `uprating` (`uprate_parameters.py:198-208`). The filing-status leaves therefore end at their 2025 values ($15,750 single), and the probe reads `value_2026 = 15750`.
- The YAML itself says the parent uprating "remains inactive pending selective propagation in PolicyEngine/policyengine-core#537".
- The engine's own HB 4168 integration test asserts the unindexed 2026 amount, so the fix must update it.
- The counterfactual probe with $16,100 gives $1,137.302246 (`verification/probes/az_standard_deduction_scenario_018.json`).

**Scope.** This is the only scored cell that moves. Scope probes of scenarios 013, 040 and 079, the other Arizona households, leave every scored output unchanged.

### Ohio medical deduction premiums (scenario_025), CONFIRMED

`verification/independent/oh_025.md`

**Law.**

- R.C. 5747.01(A)(10)(b) deducts unreimbursed medical care above 7.5% of federal AGI. The page shows "Effective: March 5, 2026", before the freeze.
- (A)(10)(c) defines medical care by IRC 213(d), and 213(d)(1)(D) includes insurance premiums. The bar on subsidized employer plans is written into (A)(10)(a) alone.
- Ohio's worksheet line 3 reads "Medicare or an employer-paid health care plan".
- The head's $6,500 of after-tax premiums plus $800 of other medical expenses exceed 7.5% of federal AGI ($7,119.40) by $180.60.
- Ohio tax is then $332 + 2.75% × ($90,944.69 − $26,050) − $200 = $1,916.60.

**Engine.**

- `oh_insured_unreimbursed_medical_care_expense_amount.py:25-28` counts premiums only when the person is Medicare-eligible AND the employer paid none.
- The line-1 branch reads `health_insurance_premiums`, which has been a bare input with no formula since policyengine-us #8178. A non-Medicare filer's premiums therefore reach neither line.
- The verifier also found a latent double count for couples. A person variable `adds` a tax-unit variable, which core broadcasts to every member. The fix must cover it too.

**Models.** The consensus ($1,589.56, 8 models) omits the statutory $332 base and is wrong under every reading. No model is within $1 of either value, so the correction changes only error-based scores.

**Scope.** Ohio scenarios 048, 107 and 110 are unaffected.

### Colorado sales tax refund surplus condition (scenario_043), CONFIRMED

`verification/independent/co_043.md`

**Law.**

- C.R.S. 39-22-2003(2) allows the six-tier refund for a tax year only "if there were excess state revenues for the fiscal year ending in that tax year", here FY 2025-26.
- Under 39-22-2002(2)(a) and 39-3-209, the homestead-exemption reimbursement absorbs a surplus first.
- Every pre-freeze forecast that names a tax year 2026 sales tax refund gives $0 in every tier: Legislative Council Staff in December 2025, March 2026 and June 2026. The June forecast put FY 2025-26 $424.9M below the Referendum C cap.
- OSPB's forecast of 2026-06-18 put it $15.3M below and "continues to anticipate no refunds". Even its upside case leaves no six-tier refund.
- On 2026-09-08, after the freeze, the State Controller certified a $175.9M shortfall.
- The household has no other Colorado refundable credit, so the law gives $0.

**Engine.**

- `co_sales_tax_refund.py` has no test of excess state revenues.
- `scale.yaml` ends at the tax year 2025 table ($19 in the lowest single tier), which carries into 2026 unchanged.

**Corrections to the adversary.** Its conclusion holds, but two of its supporting claims were wrong or overstated:

- The condition is in subsection (2), not (1).
- Not every pre-freeze projection was $424.9M below the cap; OSPB's was $15.3M.

**Scope.** This is the only Colorado scenario, and only this cell moves.

### New York child and dependent care credit, Tax Law 606(c-2) (scenario_082), CONFIRMED

`verification/independent/ny_082.md`

**Law.**

- L.2026, ch. 59, Part A (S.9009-C/A.10009-C) was signed on 2026-05-28, before the freeze.
- It confined the old 606(c)(1) credit (a percentage of the federal credit) to tax years beginning before 2026.
- It added a refundable 606(c-2) credit: qualifying expenses up to $3,000 for one child, times 55% less 0.00025 percentage points per dollar of New York AGI above $15,000, with a 4% floor.
- At New York AGI of $117,585.15 that is 29.3537% × $3,000 = $880.61. With the $307 Empire State child credit, the total is $1,187.61.

**Engine.**

- `ny_cdcc.py:16-24` has no year branch, so it computes the pre-2026 credit in 2026: 0.6 × the federal 20% rate × $3,000 = $360, giving a total of $667.
- Open policyengine-us #9835 reworks only the pre-2026 IT-216 arithmetic.

**Models.** No model is within $1 of either value, and 18 answered $0.

**Scope.** Of the New York scenarios (004, 071, 082, 104, 118), only this cell moves.

**Not counted.** The 2026 POWER credit (606(uuu)) is left out. Its eligibility turns on 2024 facts the prompt does not state.

### Pennsylvania dependent's own return (scenario_123), AMBIGUOUS

`verification/independent/pa_123.md`, `verification/definition_conformance.md` (household scope)

**Two quantities.**

- The reference, $3,070.06, is the parents' joint PA-40.
- The 16-year-old has $45,000 of wages and must file a PA-40 too. PA-40 instructions require a return above $33 of income, "even if claimed as a dependent". The child owes $1,381.50.
- The total over every return the household must file is therefore $4,451.56, the 33-model consensus.

**Why the text doesn't decide.** The output definitions name no return, tax unit or household. The prompt points both ways:

- It shows one "Tax unit" block and puts everyone "in one household group for tax and benefit calculations".
- It also asks for quantities "for this household" and says "Assume tax filing … when required".

Careful readers split. In the sibling federal cell, 8 models used the parents' return only, 15 added the child's return, and 20 pooled the child's wages onto the joint return, which 26 U.S.C. 73(a) does not allow.

**Engine.** policyengine-us computes the parents' return correctly:

- `irs_gross_income` zeroes dependents' income.
- Pennsylvania taxable income starts from `irs_gross_income`.
- Nothing computes a dependent's own return inside the parents' unit.

The root cause is a gap in scenario generation and definition scope, not an engine defect.

**Other cells with the same question.** The definition-conformance scan built the dependent's own return as a separate tax unit. It found the same issue in scenario_093 (Missouri, a 27-year-old dependent with $45,000 of wages). Four cells are affected:

| Cell | Reference | With the dependent's return | Models exact: reference / other reading |
|---|---:|---:|---|
| scenario_123 state income tax | 3,070.06 | 4,451.56 | 0 / 33 |
| scenario_123 federal income tax | 5,200.24 | 8,420.24 | 1 / 2 |
| scenario_093 state income tax | 3,388.25 | 4,528.08 | 0 / 0 |
| scenario_093 federal income tax | 8,628.99 | 11,848.99 | 1 / 0 |

**Disposition.** The verifier recommended excluding all four together, not regenerating them; regenerating would only move the penalty to the other reasonable reader.

- The exclusion records use `reference_depends_on_unlisted_input`, the one of the exclusion schema's three reason codes that fits, and name the unlisted input as the scope question.
- The verifier suggested a dedicated `definition_scope_ambiguous` code. That would be a schema change, so this PR does not make it.

### North Carolina children's Medicaid (scenario_026 child1, child2), REFUTED

`verification/independent/nc_026.md`

**The adversary's claim.** North Carolina covers children aged 6–18 between 133% and 211% FPL only through the optional targeted low-income child group (42 CFR 435.229). That group excludes children with group health coverage, so these insured children would be ineligible.

**Why it fails.**

- The approved SPA NC-23-0009 (2023-07-28) also elects the "Individuals above 133% FPL under Age 65" group (42 CFR 435.218) at 211% for all children under 19.
- The SPA's own text says that group covers "children who have separate group health plan or health insurance coverage". CMS's approval letter says insured children are enrolled and claimed at regular FMAP.
- So insurance decides the funding source, not eligibility.
- The adversary's stage 1 had flagged its 435.229 premise as an inference.
- Its child3 verdict, `reference_holds`, was the correct one. The three children are in the same legal position.

**Engine.** The engine's single older-child test (211% plus the 5-point disregard, with no coverage condition) matches the law. The references stay at 1, and nothing is excluded.

**Caveat.** North Carolina switches to the new poverty guideline on April 1. Each child is ineligible January–March 2026 and eligible from April. That is a benchmark-wide question about annual flags near a threshold, not the defect alleged. It applies equally to child3.

## Leaderboard impact

`scripts/leaderboard_impact.py` copies the frozen run to scratch, applies each alternative in `proposed_changes.json`, and scores every copy with `policybench analyze`, the command the freeze runs. It takes the run and the proposals from git at their pinned commits (Inputs above), not from the working tree. The unchanged copy reproduces the published scoring: every `modelStats` field (except the cost and latency fields the freeze overlays), plus `programStats`, `heatmap`, `globalWeights` and `failureModes` exactly. Full tables are in `verification/leaderboard_impact.json` and `verification/leaderboard_impact_*_{models,programs}.csv`.

| Variant | Scored cells | Exact-rate change across models | Leader (gpt-6-sol) exact | Exact-rank changes |
|---|---:|---|---|---|
| **`exclude_all`**: d1022, next release | 1,920 | +0.40 to +0.65 pp (mean +0.55) | 95.00 → 95.64 | claude-sonnet-5.5 5 → 4, gpt-6-luna 4 → 5; gemini-3-flash-preview 30 → 29, claude-opus-4.7 29 → 30 |
| `recommended`: four defects regenerated with this file's values, scope cells excluded | 1,924 | +0.30 to +0.58 pp (mean +0.45) | 95.00 → 95.59 | the same four |
| `exclude:household_scope_dependent_returns` alone | 1,924 | +0.26 to +0.51 pp (mean +0.43) | 95.00 → 95.52 | the same four |
| `regenerate:az_standard_deduction_indexing` | 1,928 | 0 to +0.06 pp | 95.00 → 95.07 | none |
| `regenerate:co_sales_tax_refund_surplus` | 1,928 | 0 to +0.006 pp | 95.00 → 95.01 | none |
| `regenerate:oh_medical_deduction_premiums` | 1,928 | 0 | unchanged | none |
| `regenerate:ny_cdcc_606_c2` | 1,928 | 0 | unchanged | none |

Three things stand out:

- **The household-scope exclusion drives the rank changes.** It removes four cells that almost every model missed. gpt-6-luna matched one of them, the scenario_093 federal reference, so it gains least (+0.40 pp) and drops below claude-sonnet-5.5.
- **Score ranks shift more than exact ranks, and within-1% ranks less.**
  - Under `exclude_all`, 18 models move one or two score ranks; gpt-5.6-sol goes from 6 to 4 and claude-sonnet-5.5 from 4 to 6.
  - Within 1%, only claude-opus-4.8 and minimax-m3 move, swapping places 39 and 40.
- **The always-zero baseline rises** from 69.98% to 70.47% exact under `exclude_all`.

The next release adds d994's two Louisiana exclusions, whose impact is #192's to compute. The release computes the combined impact when it freezes.

## Definition conformance

`verification/definition_conformance.md` and `.json`, from `scripts/definition_conformance.py` with `policybench.definition_conformance`.

**Baseline.** Before reporting, the scan recomputes all 1,928 scored references and requires each to match within 1e-3. It then walks every output's sum to its leaves: 8,128 node-sum checks, with 0 failures.

**Results.** 18 outputs, 17 component mismatches, 9 of them material, touching 8 scored cells.

- **`payroll_tax`, "mandatory".** Five employee contributions rest on an optional employer pass-through, either by policyengine-us's own wording ("assuming the employer withholds the maximum permitted employee share") or by the cited law. These are #194's subject (d972), and this pass skipped those cells.

  | Contribution | Cell | Amount |
  |---|---|---:|
  | Colorado FAMLI | 043 | $17.99 |
  | Massachusetts PFML | 081 | $805.01 |
  | Minnesota paid leave | 032 | $127.60 |
  | New York DBL | 082 | $31.20 |
  | New York PFL | 082 | $411.91 |

- **Household scope.** The four income tax cells above.
- **Not material in any scored cell.**
  - Delaware, Maine and Vermont employee contributions, flagged by the same wording.
  - Mississippi's state income tax component, which comes before its nonrefundable credits.
  - NYC income tax and refundable credits, and Montgomery County's EITC, which sit in the state lists.

## Publication sources

`verification/publication_sources.md` and `.json`, from `scripts/publication_sources.py` with `policybench.publication_sources`.

**What it checks.** For every 2026 parameter value a scored reference reads, it records:

- where the value comes from: a 2026 YAML entry, an older entry carried forward, a value computed at load, or a convention;
- whether its citations include a government publication for 2026 not dated after the freeze.

The scan first recomputed all 1,984 outputs, and no scored reference differed by more than 1e-3.

**Counts.**

- Scored cells read 8,611 (parameter, 2026 value) pairs across 8,284 parameters.
- 1,194 values (1,188 of them law parameters) carry a flag saying the 2026 amount may not have been published before the freeze, and 1,542 scored cells read at least one.
- The largest of those groups are 788 indexed or computed values and 365 explicit 2026 entries without a 2026 publication.

**Louisiana's 2026 standard deduction.**

- The single amount, 12,835, is computed in a YAML comment: 12,500 × CPI-U ratio. That reproduces the value.
- None of its four citations is a candidate 2026 publication.
- This is the finding behind #192 and d994.

**Post-freeze citations.** 7 values of 4 parameters cite a publication dated after the freeze: South Dakota's child care age limits and a Colorado contributed-reform switch. 12 scored cells read them.

**Limits.**

- The check reads citation metadata, not the cited documents.
- It does not flag a value carried forward from an older entry. Colorado's $19 (scenario_043) was classified `carried_forward` and not flagged, though its statute conditions each year's amount on that year's surplus. The defect surfaced only through the consensus trigger and the adversary. The diagnosis judge's annotation had marked the cell `reference_suspect: False`.

## Judge runs and cost

`runs/run_record.json` and `verification/verdict_counts.json`.

**Configuration.**

- Model: Claude Code CLI 2.1.284 with `--model opus` at `xhigh` effort, four cases at a time.
- Login: Subfleet lane claude-9, account max@thesisinstitute.org, by OAuth token. The desktop login and API keys were not used.
- The CLI's sidecars report both `claude-opus-5-5` and `claude-haiku-4-5-20251001` for every call.

**Runs.**

- Run 1 used the committed batch runner and judged four cases. It was stopped at 02:23 UTC to switch to the rolling pool (commit f25e5a01); no call was interrupted.
- Run 2 judged the rest and finished at 04:08 UTC on 2026-10-06.
- Results: no call was refused with 401, 403 or 429, and the audit as it then stood rejected no output as contaminated or invalid.
- The re-judge (`runs/claude-rejudge.run1.log`) ran on Subfleet lane claude-10, account max@farness.ai, by OAuth token, three cases at a time, with the same CLI, model and effort. It made 20 calls, and all were accepted.

**Cost.**

| Measure | Value |
|---|---:|
| Judge calls | **104** (52 stage 1 and 52 stage 2; run 1: 8, run 2: 96) |
| Accepted outputs | 104 |
| Cost reported by the CLI | **$91.22**. This is the CLI's API-price estimate; the calls billed a subscription login. |
| Judge-hours | **5.25** (the sum of the CLI's per-call durations) |

The re-judge's 20 calls add $24.82 and 4.70 judge-hours (`runs/run_record.json` `rejudge`). The independent verifications and probes ran outside the judge runs, so they are not in these counts.

## Rulings

Both are recorded in `proposed_changes.json` `status`.

- **d1022 (Max, 2026-10-06, "approve").**
  - The next release after dashboard-data-20261006 excludes the eight cells: the four confirmed defect cells (AZ 018, OH 025, CO 043, NY 082) and the four household-scope cells (PA 123 and MO 093, state and federal).
  - Once fixed policyengine-us versions land, the four defect cells are regenerated.
  - NC 026 is refuted and stays as published.
- **d994 (Max, 2026-10-06, "approve").**
  - Exclude Louisiana scenario_051 and scenario_077 state income tax.
  - Keep the published-amounts convention: no change to Idaho 076, SNAP 008/038/109 or Maryland 068.
  - The ruling adds that v2 states indexed amounts in the prompt, and applies from the next release after 20261006.
  - This pass skipped both cells, which belong to #192, so `proposed_changes.json` carries the ruling but no records for them.

The pass's own expectations are not part of either ruling (`status.not_ruled`). A reference regenerated on a fixed policyengine-us should reproduce its regeneration record's `regenerated_value` within the $1 exact-match tolerance. The upstream engine fixes are opened separately, so each record's `upstream` still reads "to be filed".

## Open items

- **Engine fixes.** As of 2026-10-08 these are open, unmerged policyengine-us pull requests:
  - Arizona: #9928.
  - Colorado: #9946.
  - New York: #9948.
  - Ohio: #9925 fixes the double count the verifier found, but no pull request yet carries the premiums fix behind scenario_025.

  Each of the four confirmed verification files gives a fix specification and YAML tests with hand-computed expectations.
- **scenario_013 SNAP's effective date.** The $240 reference holds only if Arizona's 200% limit took effect in March 2026, and no run confirmed that date from a primary source (see [Search results from blocked sources](#search-results-from-blocked-sources)). An independent check of the DES manual's revision history would settle it.
- **Codex runner blinding.** No run here used the Codex runner. Codex's event log records a search's query but not its results, so the Codex runner cannot make the Claude runner's search-result check. The prompt's `blocked_domains` request is its only guard. Codex also adds instructions to a session without an event. The runner skips the lane's `config.toml`, turns the memories, hooks, plugins and apps features off, gives each call an empty `HOME`, and refuses a Codex home with `AGENTS.md`, `AGENTS.override.md` or its own skills. It does not control what Codex bundles, an administrator's `/etc/codex`, or a feature those flags leave on.
- **Household scope for future runs.** The methodology choice for future runs is queued for Max as d1029, because the definitions admit both readings:
  - either state the scope in both income tax definitions and filter out households whose dependents must file;
  - or build the dependent's own return as a second tax unit.
- **scenario_093's dependency status.** A 27-year-old with $45,000 of wages is a qualifying child only if permanently and totally disabled (26 U.S.C. 152(c)(3)(B)), and the prompt's general disability flag does not settle that. Its two income tax cells are excluded under d1022, but the verifier did not examine the scenario's other outputs.
- **Annual eligibility flags in April-switch states.** See the North Carolina caveat above.

## Files

| Path | What it is |
|---|---|
| `consensus_flags.json`, `consensus_flags_prototype.json` | Flag reports at the default and prototype parameters |
| `covered_elsewhere.json` | The 9 cells skipped and the audit that owns each |
| `runs/claude/` | The 52 cases: prompts, frozen derivations, stage 1 and verdict JSON, sidecars, transcripts |
| `runs/claude-rejudge/`, `runs/rejudge_flags.json` | The 10 re-judged cases, in the same layout, and the flags they were prepared from |
| `runs/claude.run1.log`, `runs/claude.run2.log`, `runs/claude-rejudge.run1.log`, `runs/run_record.json` | Runner logs and the run record |
| `runs/collected/`, `runs/collected-rejudge/` | `adversary-collect` output for each: verdicts, adjudication queue, missing and inconsistent lists (all empty) |
| `verification/flags_table.md`, `verdict_table.md`, `verdict_counts.json` | Rendered flags and verdicts |
| `verification/search_exposure.*` | Search results from blocked sources in every transcript, and the re-judge against the original |
| `verification/independent/` | Independent verification of the 7 non-holding verdicts |
| `verification/probes/` | Engine probes on policyengine-us 2.15.17 plus `latest_final` |
| `verification/definition_conformance.*`, `publication_sources.*` | The two engine-side checks |
| `verification/leaderboard_impact*` | Leaderboard impact of each alternative |
| `verification/pytest_*.txt` | Test runs: after the rebase, the rolling-pool change, and the final run (391 passed) |
| `proposed_changes.json` | Exclusion and regeneration records per root cause, and the rulings |
| `scripts/` | The scripts that wrote the files above, and `pass_inputs.py`, which pins and stages their inputs |

The code is in `policybench/consensus.py`, `reference_adversary.py`, `definition_conformance.py` and `publication_sources.py`, with CLI commands in `policybench/cli.py`. The runners are `scripts/run_reference_adversary_{claude,codex}.sh`, and `docs/audit.md` has the pipeline. The diagnosis judge's prompt still claims that earlier audits' bugs "were fixed before this run", which the frozen run's 28 unfixed engine-defect exclusions contradict. Removing it changes every judge prompt and breaks byte-identical carry-over of existing verdicts, so it waits for a versioned judge template, which a separate PR adds. Tests are in `tests/test_consensus.py`, `test_reference_adversary.py`, `test_reference_adversary_inputs.py`, `test_reference_adversary_impact.py`, `test_reference_adversary_runner.py`, `test_definition_conformance.py`, `test_publication_sources.py` and `test_audit.py`.

## Reproduce

The scripts in `scripts/` stage the pass's inputs from git (the tables under [Flag parameters](#flag-parameters)), so they run from any checkout that has `8b4c0ca1`, `049f4f09` and `4db91b5f` in its history, whatever its working tree's run, convention modules and records hold. The code they run is the checkout's. A shallow clone needs `git fetch --unshallow`. Each script's docstring gives its command.

The CLI steps read the payload and annotations at the paths they are given and record the payload's path in their output (`consensus_flags.json` `source`). So they need the working tree's run and annotations as `8b4c0ca1` committed them, not today's, which release dashboard-data-20261006 (#202) rewrote. Restore both from `8b4c0ca1` first, and put today's back when done:

```bash
run=paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace
git restore --source 8b4c0ca1 -- "$run" "annotations/${run##*/}"
# ... the CLI steps below ...
git restore -- "$run" "annotations/${run##*/}"
```

```bash
uv run policybench consensus-flags --payload <run>/data.json.gz \
  --output reference_audit/2026-10-05-reference-adversary/consensus_flags.json
uv run policybench adversary-prepare --payload <run>/data.json.gz \
  --flags reference_audit/2026-10-05-reference-adversary/consensus_flags.json \
  --annotations-dir annotations/<run> \
  --skip-cells reference_audit/2026-10-05-reference-adversary/covered_elsewhere.json \
  --adversary-dir reference_audit/2026-10-05-reference-adversary/runs/claude
# inside a Subfleet lane, with the lane's CLAUDE_CONFIG_DIR (resumable):
AUDIT_PYTHON=<2.15.17 venv>/bin/python \
  scripts/run_reference_adversary_claude.sh reference_audit/2026-10-05-reference-adversary/runs/claude
uv run policybench adversary-collect \
  --adversary-dir claude=reference_audit/2026-10-05-reference-adversary/runs/claude \
  --output-dir reference_audit/2026-10-05-reference-adversary/runs/collected
# the re-judge: flags for the cases whose search results reached a blocked
# source, then the same steps into runs/claude-rejudge
uv run python reference_audit/2026-10-05-reference-adversary/scripts/search_exposure.py
uv run policybench adversary-prepare --payload <run>/data.json.gz \
  --flags reference_audit/2026-10-05-reference-adversary/runs/rejudge_flags.json \
  --annotations-dir annotations/<run> \
  --adversary-dir reference_audit/2026-10-05-reference-adversary/runs/claude-rejudge
AUDIT_PYTHON=<2.15.17 venv>/bin/python \
  scripts/run_reference_adversary_claude.sh reference_audit/2026-10-05-reference-adversary/runs/claude-rejudge
uv run policybench adversary-collect \
  --adversary-dir claude=reference_audit/2026-10-05-reference-adversary/runs/claude-rejudge \
  --output-dir reference_audit/2026-10-05-reference-adversary/runs/collected-rejudge
uv run python reference_audit/2026-10-05-reference-adversary/scripts/search_exposure.py
```

Preparing `runs/claude` today reproduces its `cases.jsonl` and derivations byte for byte. Each stage-1 prompt then differs from the committed one in one line, because the source rule now asks for `blocked_domains`. The re-judge's preparation reproduces `runs/claude-rejudge`'s inputs byte for byte.

`definition_conformance.py`, `publication_sources.py`, `engine_probe.py` and `leaderboard_impact.py` need the policyengine-us 2.15.17 environment, which `uv sync --locked --extra dev --python 3.12` provides. Write their output to scratch and compare it with the committed files:

```bash
a=reference_audit/2026-10-05-reference-adversary
export OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
uv run python $a/scripts/definition_conformance.py --out-dir <scratch>
uv run python $a/scripts/publication_sources.py --out-dir <scratch>
uv run python $a/scripts/engine_probe.py scenario_043 \
  --variables co_sales_tax_refund co_refundable_credits co_eitc co_tabor_cash_back state_refundable_credits \
  --parameters gov.states.co.tax.income.credits.sales_tax_refund.amount.flat_amount_enabled \
    gov.states.co.tax.income.credits.sales_tax_refund.amount.amount \
  --out <scratch>/co_sales_tax_refund_scenario_043.json
uv run python $a/scripts/leaderboard_impact.py --scratch <scratch> --out-dir <scratch>/impact
uv run python $a/scripts/build_proposals.py --out <scratch>/proposed_changes.json
```

Each committed probe records its own arguments: `scenario_id`, `period`, the keys of `variables` and `parameters`, and `counterfactual.set`. `build_proposals.py` never writes the committed `proposed_changes.json`, which `leaderboard_impact.py` and the Haiku 5.5 release pin at `3a6e5920…`. It refuses that path for `--out`, and it creates `--out` exclusively, so it never writes any file that already exists (a hard link to the committed file, or another checkout's copy, included).

The tests regenerate every one of these outputs into scratch and require the committed file byte for byte:

- `build_proposals.py`: `proposed_changes.json`, in the fast suite.
- `definition_conformance.py`: both files, except two lines of `definition_conformance.json`: `run.seconds`, the wall time, and `run.script_sha256`, the script's own sha256. The committed file records `33ce4c3e…`, the script as #200 merged it; the test requires a regeneration to record the current script's hash.
- `publication_sources.py`: both files, except `meta.seconds`.
- `engine_probe.py`: all 8 probes, from the arguments each records.
- `leaderboard_impact.py`: all 23 `verification/leaderboard_impact*` files.

The engine-side regenerations took 21 minutes on a loaded machine, so they are marked slow and CI deselects them:

```bash
OPENBLAS_NUM_THREADS=1 uv run pytest -m slow tests/test_reference_adversary_inputs.py tests/test_reference_adversary_impact.py
```
