# US household prompt contract v2

`policybench.prompt_contract_v2` adds an **opt-in, unactivated household-fact
contract** for the prompt slice of [issue 165](https://github.com/PolicyEngine/policybench/issues/165).
It renders existing `Scenario` objects without importing an engine, discovering
inputs, calculating outcomes, or calling a model. No existing evaluator imports
this module. The published v1 prompt, schemas, references, board, and cost path
remain unchanged.

This slice does not complete issue 165 or create a v2 benchmark board. In
particular, it supplies no requested-output list, answer schema, marital-unit
mapping, data provenance certification, or reference validation. Its text and
diagnostics are for contract review. Do not feed this partial contract into the
v1 evaluator or treat its output as a certified evaluation request.

## Identity and example

The version is `2.0.0`. `contract_identity()` returns:

```text
policybench-us-household-prompt/2.0.0:sha256:a1a25d39795acbe6c4ee25adec297bdad8167479154ca70fb50755b8eee08a3a
```

The SHA-256 covers the **exact UTF-8 source bytes of the new module**, including
its validation, vocabulary, and preamble. It requires a source installation;
bytecode-only distributions are unsupported. This identity does not cover a
model runtime, dataset, requested outputs, or the caller's per-person facts.
There are no mutable v1 helper or runtime-registry dependencies. Record the
rendered text separately for each household. The pinned
[`scenario_074.txt`](../tests/fixtures/prompt_contract_v2/scenario_074.txt) checks
both the source identity and the full rendering. Changes require an explicit
review of the identity and golden text; do not automatically bless a new golden.

For an existing US `scenario`:

```python
from policybench.prompt_contract_v2 import render_household_contract

contract = render_household_contract(
    scenario,
    policyengine_us_version="1.755.4",  # Explicit review context, not a runtime call.
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
  `social_security_retirement`, `social_security_dependents`,
  `social_security_survivors`, `veterans_benefits`, `ssi_reported`,
  `disability_benefits`, `self_employment_income`, `bank_account_assets`,
  `stock_assets`, `pre_subsidy_rent`, `real_estate_taxes`,
  `home_mortgage_interest`, and `tip_income`. Signed monetary inputs retain their
  sign; premiums must be nonnegative. Premiums are explicitly **employer-paid
  and excluded from stated wages**. Tips remain included in stated wages.
- Boolean `is_tax_unit_head`, `is_tax_unit_spouse`,
  `is_unmarried_partner_of_household_head`, and `has_esi`. These are supplied
  facts; no couple or engine unit mapping is inferred.
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
  specified entities only when exactly `True`. False, null, numeric, and string
  overrides conflict with the preamble and raise an error. Additional take-up
  names are unsupported and remain explicitly marked.
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
  booleans to false, with the explicit unknown and filing/take-up exceptions.
  SSI means federal SSI only; a supplement needs a separately requested output.

## Evidence and remaining gates

Tests read all 100 existing public households from
[`scenarios.csv`](../paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/scenarios.csv).
The fixture's SHA-256 is
`71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a`.
Scenario 074 supplies SSDI income but no duration; scenario 008 supplies a
general disability flag. They demonstrate rendering/missingness, not new
eligibility findings. Tests retain the original fixture and assert no mutation.
Additional cases deliberately vary fixture inputs to test integer types,
program-specific labels, explicit unknowns, conflicting inputs, and provenance.

```bash
uv run pytest tests/test_prompt_contract_v2.py -q
uv run ruff check policybench/prompt_contract_v2.py tests/test_prompt_contract_v2.py
uv run ruff format --check policybench/prompt_contract_v2.py tests/test_prompt_contract_v2.py
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
