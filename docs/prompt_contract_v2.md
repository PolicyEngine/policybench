# US household prompt contract v2

`policybench.prompt_contract_v2` adds an **opt-in, unactivated household-fact
contract** for the prompt slice of [issue 165](https://github.com/PolicyEngine/policybench/issues/165),
including the October 5 audit decisions **d963, d972, and d974**.
It renders existing `Scenario` objects without importing an engine, discovering
inputs, calculating outcomes, or calling a model. No existing evaluator imports
this module. Proposed v2 output wording has separate, version-gated keys in
`benchmark_specs.json`; the published v1 wording, schemas, references, board,
and cost path remain unchanged.

This slice does not complete issue 165 or create a v2 benchmark board. In
particular, proposed definitions are not a requested-output list. It supplies
no answer schema, marital-unit
mapping, data provenance certification, or reference validation. Its text and
diagnostics are for contract review. Do not feed this partial contract into the
v1 evaluator or treat its output as a certified evaluation request.

## Identity and example

The version is `2.1.0`. `contract_identity()` returns:

```text
policybench-us-household-prompt/2.1.0:sha256:0d1cf7d3fc7e6125d2c921424b66f85b160711bde67cba046a3c8d409f732a45
```

The SHA-256 covers the **exact UTF-8 source bytes of the module**, a newline,
and the canonical JSON of the proposed output definitions selected by
`v2_prompt_contract == "2.1.0"` in `benchmark_specs.json`. Changes to the v1
`prompt` keys do not change this identity. A source installation including
that spec file is required; bytecode-only distributions are unsupported.
This identity does not cover a model runtime, dataset, requested outputs,
or the caller's per-person facts. There are no mutable v1 helper or
runtime-registry dependencies. Record the rendered text separately for each
household. The pinned
[`scenario_074.txt`](../tests/fixtures/prompt_contract_v2/scenario_074.txt) checks
both the source identity and the full rendering. Changes require an explicit
review of the identity and golden text; do not automatically bless a new golden.

For an existing US `scenario`:

```python
from policybench.prompt_contract_v2 import render_household_contract

contract = render_household_contract(
    scenario,
    policyengine_us_version="2.15.17",  # Explicit review context, not a runtime call.
)
print(contract.text)
print(contract.unknown_facts)
print(contract.unsupported_inputs)
```

The caller must supply an exact `x.y.z` model version. The renderer labels this
version as unverified; it never reads an installed package version or asserts
that the declared conventions match that version. `source_dataset` is likewise
a label, not evidence of observation or imputation. `metadata` is not interpreted
as provenance, dates, or engine unit mappings.

## Supported values and unknown provenance

All input lines retain the exact input name in brackets. Facts sort by name
within each person/entity; people retain the scenario's order. Values do not
round to dollars or whole hours. Built-in Python types corresponding to JSON
scalars are supported; NumPy scalars, enums, arrays, period dictionaries, NaN,
and infinities are not silently converted.

| Inputs | Contract interpretation |
| --- | --- |
| `is_disabled` | General survey characteristic; establishes no program-specific disability gate. |
| `is_blind` | Blindness indicator; establishes no separate program-specific disability finding. |
| `meets_ssi_disability_criteria` | SSI disability criterion before the substantial-gainful-activity test. The earnings test remains separate. |
| `is_usda_disabled` | Supplied SNAP receipt-based disability status; this renderer does not calculate it from receipts. |
| `is_permanently_and_totally_disabled` | Supplied IRC 152/22 disability fact. |
| `is_incapable_of_self_care` | Supplied IRC 21 self-care fact. |
| `social_security_disability` | Supplied SSDI income, separate from entitlement history. |
| `months_receiving_social_security_disability` | Nonnegative integer months, measured as of January 1 of the scenario year under the declared convention. `24` prints as `24 months`; `24.0`, `"24"`, and `True` raise `ContractInputError`. |

The six disability booleans accept only `True`, `False`, or `None`. All eight
fields above print for every person, including when absent. Omitted or null
values are **unknown**, overriding the generic unlisted-input default. The
renderer never uses general disability or SSDI income to fill another field.

Optional provenance uses exact person and field names:

```python
from policybench.prompt_contract_v2 import FactProvenance

# Only use this structure when the named source actually supports the value.
provenance = {
    "head": {
        "meets_ssi_disability_criteria": FactProvenance(
            "imputed", "the actual build and field-level imputation record"
        ),
    },
}
```

`observed` and `imputed` require a non-empty, single-line source and a non-null
supplied value. The single-line boundary also rejects Unicode line separators,
including NEXT LINE (`U+0085`), in sources, scenario IDs, and dataset labels.
`unknown` may name a source documenting missingness. Missing
annotations default to `unknown`, never `observed`. A supplied `False` without
provenance prints `no (supplied value; provenance: unknown; not an observed
fact)`; absent values print `unknown (not supplied; provenance: unknown)`.
Unknown persons, misspelled fields, unsupported provenance kinds, and annotations
for unsupported fields raise an error. The renderer displays sources without
fetching or validating them. Synthetic annotations in tests demonstrate syntax
only; they are not claims about the frozen dataset.

`unknown_facts` lists sorted paths with an unknown value **or** unknown
provenance, for example `person.head.meets_ssi_disability_criteria`.
`unsupported_inputs` lists sorted paths whose meaning/units are unsupported.
Neither tuple is a readiness certificate, even if empty.

Other supported person facts are:

- Required `age` (nonnegative integer years) and `employment_income` (finite
  annual wages). Repeating either in `Person.inputs` raises an error.
- Finite monetary inputs: `employer_sponsored_insurance_premiums`,
  `pre_tax_health_insurance_premiums`,
  `health_insurance_premiums_without_medicare_part_b`,
  `health_insurance_premiums`, `other_health_insurance_premiums`,
  `medicare_part_b_premium`,
  `medical_expense_health_insurance_premiums`, `financial_assistance`,
  `social_security_retirement`, `social_security_dependents`,
  `social_security_survivors`, `veterans_benefits`, `ssi_reported`,
  `disability_benefits`, `self_employment_income`, `bank_account_assets`,
  `stock_assets`, `pre_subsidy_rent`, `real_estate_taxes`,
  `home_mortgage_interest`, and `tip_income`. Signed monetary inputs retain their
  sign; premiums must be nonnegative. Every premium label identifies the
  payer and tax treatment, as described below. Tips remain included in stated
  wages.
- Boolean `is_tax_unit_head`, `is_tax_unit_spouse`,
  `is_unmarried_partner_of_household_head`, `has_esi`,
  `takes_up_medicare_if_eligible`, `is_surviving_spouse`,
  `dependent_child_lives_in_home`, and
  `state_paid_leave_employee_share_withheld`. These are supplied facts;
  no couple or engine unit mapping is inferred.
- Single-line text `financial_assistance_source` and integer
  `spouse_death_year`. They make the deciding facts explicit rather than
  treating a loaded label as a legal conclusion.
- Tax-unit annual dollars `state_withheld_income_tax`. The name of the engine
  input is retained; the renderer does not substitute state tax liability.
- Nonnegative finite `hourly_wage` in dollars/hour, and the weekly-hours fields
  below. Optional supported inputs may be null, which means unknown.

Known fields on the wrong entity raise an error. Other scalar inputs print as
exact JSON with `unsupported input; meaning and units not interpreted`, including
strings and zeros. Nothing is filtered using v1's excluded-field list. For
example, an unrecognized integer status prints its integer value without a
guessed currency, enum label, or boolean interpretation. Non-scalar or non-finite
unsupported values raise an error. Reviewers must resolve these marked inputs
before any future evaluation.

Only US state/DC codes, integer calendar years, and the existing lowercase
`single`, `joint`, and `head_of_household` filing statuses are accepted. Person
names must be unique lowercase identifiers. UK scenarios, unknown filing status,
and malformed structural inputs are rejected.

## Frozen assumptions

The preamble follows the proposed language in issue 165 as a **declared v2
convention**, not a verified description of the published reference engine.

- Filing and full take-up apply to eligible requested benefits and eligible
  TANF/MOE noncash benefits used for SNAP categorical eligibility. Computed
  receipt may feed downstream calculations; the exception does not establish
  eligibility or historical entitlement. Social Security, SSDI, and veterans
  payments/histories remain supplied inputs only.
- The existing `scenarios.DEFAULT_TAKEUP_INPUTS` vocabulary is accepted on its
  specified entities only when exactly `True`, apart from the explicit Medicare
  exception below. False, null, numeric, and string overrides of the remaining
  take-up inputs conflict with the preamble and raise an error. Additional
  take-up names are unsupported and remain explicitly marked.
- `hours_worked_last_week` and `weekly_hours_worked` accept finite numbers from
  0 to 168 hours/week. Both names are printed without aliasing. If both are
  supplied, their values must agree; null and a numeric value conflict. When
  neither is supplied, each person's text states the **0 hours/week contract
  assumption**. Null is unknown, not zero. Hours never come from wages divided
  by an hourly rate. A future adapter must check which input the selected engine
  reads; this renderer does not create or modify any engine input.
- Facts remain constant throughout the year, with no income volatility or
  status changes. Medicare eligibility and SSDI duration use January 1. This
  slice accepts no separate duration date/start-date schema; any such extra input
  remains marked unsupported. The caller must resolve the reference date before
  a future evaluation.
- Generic unlisted numerics, including integers, default to zero, and unlisted
  booleans to false, with the explicit unknown, filing/take-up, and named
  calculation-convention exceptions.
  SSI means federal SSI only; a supplement needs a separately requested output.

## October 5 calculation conventions

These additions state reference conventions where the frozen households lack
observed facts. They do not certify that a household actually paid, enrolled,
withheld, or received the named amount. The renderer accepts supplied values
where supported and never runs a simulation to fill them.

**State income tax paid for SALT (d963; [PR 191](https://github.com/PolicyEngine/policybench/pull/191)).**
For each supplied tax unit, state the annual input
`state_withheld_income_tax`, or follow the declared model's per-state AGI-based
withholding estimate and treat that estimate as paid during the year. This is
distinct from final state income tax liability. A supplied tax-unit amount
overrides the estimate. The audited policyengine-us 2.15.17 federal SALT reader
chooses the larger of `state_withheld_income_tax + local_income_tax` and
`state_sales_tax + local_sales_tax`, then adds real estate taxes and applies
the deduction cap. Montana's separate person-level `mt_withheld_income_tax`
reader requires its own stated input or convention before that reference can
be scored; the tax-unit convention does not cover it.

**Medicare enrollment and premiums (d974; [PR 193](https://github.com/PolicyEngine/policybench/pull/193)).**
Every person's text states `takes_up_medicare_if_eligible`: enrollment includes
Part B and is assumed if eligible unless a supplied boolean overrides it.
A supplied null is unknown. Eligibility still depends on the separate age,
SSDI, and entitlement-duration facts; this convention does not supply an
unknown duration. The annual enrollee payment `medicare_part_b_premium` is
employee after-tax spending. When absent, it follows the declared model's
standard premium plus IRMAA, net of Medicare Savings Program support, and is
paid only while enrolled. For year 2026 with declared version 2.15.17, the
rendering additionally states the $202.90 monthly / $2,434.80 annual standard
premium before IRMAA and support. Unlisted two-year-prior IRMAA MAGI is $0.

The medical-expense reader `medical_expense_health_insurance_premiums` uses
a nonzero direct `health_insurance_premiums` total instead of the component
sum. Otherwise it uses `health_insurance_premiums_without_medicare_part_b`
(zero when absent) plus the enrolled person's net Part B premium. Supplying
zero in `health_insurance_premiums` still invokes that component sum; it does
not suppress Medicare spending. A direct medical-expense input overrides the
aggregate. These rules avoid counting an all-in premium and its components
twice.

**Who pays a premium.** `employer_sponsored_insurance_premiums` means
employer-paid premiums excluded from the stated wages, rather than a deduction
from those wages. `pre_tax_health_insurance_premiums` means employee pre-tax
payroll withholding and reduces income-tax and FICA wages under the declared
model. Direct out-of-pocket, non-Medicare, Medicare, and medical-expense
premium labels mean employee after-tax spending under this convention and
do not reduce FICA wages.

**Employer withholding choice (d972; [PR 194](https://github.com/PolicyEngine/policybench/pull/194)).**
For each person in MN Paid Leave, CO FAMLI, MA PFML, NY PFL/DBL, DE Paid Leave,
ME PFML, VT child-care contribution, or WA PFML, the prompt states whether
the employer withholds the employee share. The declared convention is full
employee-share withholding unless
`state_paid_leave_employee_share_withheld` supplies another choice. `False`
means the employer pays that share and the payroll output excludes it; null
means the choice is unknown. Amounts follow the declared model's
employee-share parameters, including its 52-weeks-per-year annualization of
NY DBL. This states a reference convention rather than claiming every model
parameter is the legal maximum; PR 194 records a Massachusetts cap ambiguity
and classifies WA PFML as mixed/unclear. Other programs classified as mandatory
in that audit retain the employee-side payroll scope.

**Loaded household labels.** When `is_surviving_spouse` is true, state the
spouse's death year and whether a dependent child lives in the home. Missing
death year uses the synthetic convention of the previous calendar year;
listed children are assumed dependent children living in the home. These are
declared assumptions, not observations of the frozen data. Apply the dated
filing rules; the label alone establishes no qualifying-surviving-spouse
status. Scenario 000 has no listed child, so its convention explicitly says
no dependent child lives in the home.

`financial_assistance` names cash gifts from friends or relatives outside the
household when no explicit `financial_assistance_source` is supplied, and
states that this is SNAP unearned cash income. This makes scenario 030's
source and countability explicit; it does not invent an observed donor.

## Proposed v2 output scope

`v2_output_definitions()` reads only definitions carrying the matching
`v2_prompt_contract` version. The renderer displays those definitions as
proposals, not an output request. Existing spec loading continues to read
the original `prompt` keys, so v1 payloads retain their published wording.

The v2 payroll definition covers all listed people's employee-side payroll
tax, including dependent wages, mandatory state contributions, and optional
employee shares that the employer chooses to withhold under the stated
convention. Employer-paid shares and employer taxes remain outside that
output. Thus the optional pass-through convention has an explicit counterpart
in the output definition.

The federal income tax, federal refundable credits, state income tax, state
refundable credits, and local income tax definitions all state the same
household tax scope: do not add a dependent's separate income tax return;
retain dependent-related provisions on the specified tax-unit return. The
local definition separately retains explicitly applicable local wage or
earnings taxes on listed people. Each output retains its own jurisdiction and
credit boundary. In particular,
scenario 123's 16-year-old's $45,000 of wages count in payroll, without adding
a separate dependent federal/state return. The convention does not ignore
dependent inputs that affect the parent's return, or discard wage taxes that
the separate local-income-tax output reads directly from a dependent.

## Required-facts report and release hook

Every input a scored reference reads whose change by a plausible amount moves
that reference by **more than $1** must be stated or covered by a named,
explicit convention. A generic unlisted-zero rule does not cover an engine's
computed estimate. Unknown values, unknown required provenance, and raw
unsupported labels remain gaps even when their names appear in the text.

The report reuses the comparison and exclusion logic from
[PR 196](https://github.com/PolicyEngine/policybench/pull/196), vendored as
`policybench.unlisted_input_sweep`. The helper
`policybench.prompt_contract_v2_required_facts` replays actual recorded
policyengine-us 2.15.17 baselines and perturbations across all **100 frozen
households and 1,984 outputs**. The evidence fixture names its source hashes,
model version, and run provenance. It is an offline replay, not a fresh engine
run or a discovery proof; absent readings are not fabricated as no-ops. The
recorded sweep predates PR 196's later Part B `not_enrolled` reading, which a
fresh release sweep must include.

`tests/test_prompt_contract_v2_required_facts.py` runs that logic and prints
remaining unstated, individually moving inputs in
`test_legacy_required_fact_report_lists_gaps_without_gating`. It reports
legacy gaps without requiring zero gaps. Compound readings can change
multiple inputs and override new v2 conventions, so their residual inputs are
reported separately and need a fresh run under the proposed reference builder.

The current replay has 70 moving rows. Its remaining individually moving inputs
are `county` (2 outputs), `meets_ssi_disability_criteria` (4),
`months_receiving_social_security_disability` (5),
`first_home_mortgage_origination_year` and
`second_home_mortgage_origination_year` (one shared output), and
`weekly_hours_worked_before_lsr` (2). All 13 distinct affected outputs are already
excluded from legacy scoring; none is a scored residual. These counts describe
outputs, not newly discovered people or proven legal effects. `local_sales_tax`
also remains in three compound-reading rows, which simultaneously change
now-stated conventions; the replay does not assign their whole movement to
that one input. A fresh sweep under v2 conventions must resolve those rows.

Before activation, adapt the reference builder to the stated conventions and
run the complete sweep through `unlisted_input_sweep.add_arguments(parser)`
and `unlisted_input_sweep.run(args)`, including its registered engine-estimate
inputs and plausible readings. Extend that registry for other reference-read
inputs rather than treating it as an exhaustive discovery mechanism. Its CLI
is deliberately not registered in the published
v1 path. Resolve or exclude every scored move, validate baseline agreement,
and record the new evidence. Merely rendering all households or replaying
legacy evidence is insufficient to activate a board.

## Evidence and remaining gates

Tests read all 100 existing public households from
[`scenarios.csv`](../paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/scenarios.csv).
The fixture's SHA-256 is
`71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a`.
Scenario 074 supplies SSDI income but no duration; scenario 008 supplies a
general disability flag. They demonstrate rendering/missingness, not new
eligibility findings. Tests retain the original fixture and assert no mutation.
Additional cases deliberately vary fixture inputs to test integer types,
program-specific labels, explicit unknowns, conflicting inputs, provenance,
SALT payment overrides, Medicare enrollment/premium aggregation, premium
payers, optional payroll withholding, dependent-return scope, and the deciding
facts behind loaded labels. V1 prompt tests check that its frozen text and
payload remain unchanged.

```bash
uv run pytest tests/test_prompt_contract_v2.py tests/test_prompt_contract_v2_required_facts.py tests/test_eval_no_tools.py tests/test_spec.py -q
uv run pytest tests/test_prompt_contract_v2_required_facts.py::test_legacy_required_fact_report_lists_gaps_without_gating -s -q
uv run ruff check .
uv run ruff format --check .
```

Issue 165 still requires suitable Microcosm data, real per-fact provenance,
duration/date evidence, marital-unit identifiers, resolution of the engine's
working-student disability gate, and an explicit decision on IRC 152/22 data
coverage. Before activating any later board, retain the standing requirement
to recompute references under every unlisted-input reading and exclude outputs
that move, using `reference_exclusions.json`. Those computations, model runs,
reference regeneration, data migration, board publication, and changes to cost
ledgers/schemas/reporting are outside this slice. Coordinator review and all
existing approval conditions remain required; this document grants none.

## Change record

2026-09-07: added the unactivated v2 household-contract module, dedicated tests,
and pinned fixture rendering. Host finding PB-CONTRACT-001 was fixed by rejecting
all recognized Unicode line separators and updating the source identity; fixture
fact text did not change. No published v1 file or board artifact changed.

2026-10-06: extended the draft contract to 2.1.0 for October 5 decisions d963,
d972, and d974. Added named SALT, Medicare, and employer-withholding conventions;
premium payer/tax labels; dependent-return scope; spouse-death/child and cash
assistance source facts; and the required-facts rule with PR 196's report-only
legacy sweep replay. Proposed definitions are version-gated, and their canonical
JSON now contributes to the contract identity. Updated the golden rendering and
rendered all 100 frozen fixtures. PR 173 remains a draft; benchmark activation is
Max's decision. No published v1 prompt, reference, exclusion, board, or payload
was changed.
