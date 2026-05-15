# Audit Annotation Workflow

This folder contains audit notes for the `full_run_20260513_policyengine_4_4_4_nested_outputs` run.

The audit has two layers:

- Row annotations: one note per wrong `(model, scenario_id, variable)` prediction. These were assigned by variable family so reviewers could focus on related policy rules.
- Case annotations: one note per wrong `(scenario_id, variable)` case. These group all wrong model responses for the same household-output target and summarize whether models overpredicted, underpredicted, failed parsing, or shared a common explanation pattern.

Row annotations also include `failure_source` and `failure_subtype`. Allowed `failure_source` values are `llm_error`, `prompt_ambiguity`, `reference_model_issue_fixed`, `reference_data_issue_fixed`, `parse_contract_failure`, and `needs_review`. Current row annotations are classified as either model errors or parse/contract failures; upstream PolicyEngine/data issues found during development were fixed before this frozen scored snapshot.

For future audits, reviewers should proceed within each variable family by grouping rows first on `(scenario_id, variable)`, reviewing all wrong model responses for that group side by side, and then writing the shared case note before adding any model-specific row notes.

`policybench.annotation_validation` enforces both layers: every wrong prediction row must have a row annotation and structured category, and every scenario-output case with at least one wrong prediction must have a case annotation and grouped category summary.
