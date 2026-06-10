# Run store (SQLite)

`policybench/runstore.py` is an **additive** SQLite store for benchmark run
artifacts. It does not yet replace anything: today a run still persists as
`predictions.csv` (plus `.meta.json` sidecars) with hand-rolled chunked resume
(`eval_no_tools.py`), whole-response retries (`retry_eval.py`), and row repairs
(`row_repair.py`). The store is a parallel, lossless home for the same data that
can import an existing `predictions.csv`, export it back **byte-for-byte
identically**, answer the resume question directly from SQL, and record/replace
responses with the existing accepted-retry semantics.

One SQLite file lives per run directory (default name `run.db`). Stdlib
`sqlite3` only — no new dependencies. WAL mode is enabled; upserts use
`INSERT ... ON CONFLICT DO UPDATE` via `executemany`.

## Why a store

The CSV format is faithful but awkward to operate on incrementally:

- **Resume** today re-reads the whole CSV, regroups by `(model, scenario_id)`,
  and recomputes which responses are complete. A store answers "what is still
  missing?" with one indexed query.
- **Retries and repairs** today shell out to copies, merge CSVs, and write
  several audit files (`merged_predictions.csv.gz`,
  `replaced_original_responses.csv.gz`, …). A store records a superseding
  attempt and marks the prior rows `replaced` in place, keeping the audit trail
  in one queryable table.
- **Concurrency**: many workers appending to one CSV requires a checkpoint lock;
  SQLite gives transactional upserts.

## Schema

```sql
CREATE TABLE runs (
    run_id                   TEXT PRIMARY KEY,
    country                  TEXT,
    condition                TEXT,
    created_at               TEXT,
    scenario_manifest_sha256 TEXT,
    model_set_json           TEXT,   -- models targeted (list or {name: id})
    output_set_json          TEXT,   -- {"schema": <csv schema>, "outputs": [...]}
    meta_json                TEXT     -- csv_schema, row_order, source sha, sidecars
);

CREATE TABLE responses (
    run_id          TEXT NOT NULL,
    model           TEXT NOT NULL,
    scenario_id     TEXT NOT NULL,
    attempt         INTEGER NOT NULL,   -- chunk/call index within the response;
                                        -- retries take higher attempt numbers
    status          TEXT CHECK(status IN ('ok','parse_error','llm_error','replaced')),
    call_id         TEXT,               -- "{model}:{scenario_id}" in the CSV
    raw_response    TEXT,
    error           TEXT,
    usage_json      TEXT,               -- token usage (+ reserved "_csv" blob, see below)
    cost_usd        REAL,
    latency_s       REAL,
    provider_response_id        TEXT,
    provider_system_fingerprint TEXT,
    provider_resolved_model     TEXT,
    created_at      TEXT,
    PRIMARY KEY (run_id, model, scenario_id, attempt)
);

CREATE TABLE predictions (
    run_id          TEXT NOT NULL,
    model           TEXT NOT NULL,
    scenario_id     TEXT NOT NULL,
    output_id       TEXT NOT NULL,      -- the CSV "variable" column
    condition       TEXT,
    prediction      REAL,               -- NULL when the row was a parse miss
    explanation     TEXT,
    parse_status    TEXT,               -- ok | missing | error | replaced
    source_attempt  INTEGER,            -- which response attempt produced the row
    extra_json      TEXT,               -- any long-tail CSV columns, verbatim
    PRIMARY KEY (run_id, model, scenario_id, output_id)
);
```

### Mapping to the real `predictions.csv`

The schema was built against the real snapshot artifact
`paper/snapshot/20260501/runs/{us,uk}_full_run_*_nested_outputs/predictions.csv.gz`.
The CSV has **22 columns** (one row per `(model, scenario_id, variable)`):

| CSV column | store location |
| --- | --- |
| `call_id` (`"{model}:{scenario_id}"`) | `responses.call_id` |
| `model`, `scenario_id` | key columns on both tables |
| `variable` | `predictions.output_id` |
| `prediction`, `explanation` | `predictions.prediction` / `.explanation` |
| `raw_response`, `error` | `responses.raw_response` / `.error` |
| `elapsed_seconds` | `responses.latency_s` |
| `prompt_tokens`, `completion_tokens`, `total_tokens`, `reasoning_tokens`, `cached_prompt_tokens` | `responses.usage_json` |
| `provider_reported_cost_usd`, `reconstructed_cost_usd`, `total_cost_usd`, `cost_is_estimated`, `estimated_cost_usd` | `responses.cost_usd` (+ the exact per-row values for byte-identical export) |
| `provider_response_id`, `provider_system_fingerprint`, `provider_resolved_model` | dedicated `responses` columns |
| any future/unknown column | `predictions.extra_json` |

The `run_id` column is optional in the CSV (the eval loop only writes it for
repeated runs); when present it is the run id, when absent the run id defaults to
the directory name.

### Responses are per-chunk, not per-scenario

A subtlety discovered in the real data: although `call_id` is constant within a
`(model, scenario_id)` group, the response-level columns
(`raw_response`, tokens, cost, latency, `provider_response_id`) **vary within the
group**. This is because chunked eval splits a scenario's outputs across several
provider calls, and each call's apportioned usage attaches to the variables in
that chunk. In the US snapshot there are 2,034 distinct chunk-responses across
1,300 `(model, scenario_id)` groups (mean 1.56 chunks/scenario, max 57).

The store therefore treats a **chunk** as the unit of a `responses` row: on
import, rows are grouped by their response-level column values within each
`(model, scenario_id)`, and `attempt` is assigned as the first-seen chunk index.
Each prediction's `source_attempt` points to its chunk. This is what lets export
reproduce the file exactly: the right `raw_response`/tokens/cost reattach to the
right variables.

The exact per-row CSV values for the cost/usage columns are stashed under a
reserved `"_csv"` key inside `responses.usage_json` so export can reproduce them
without widening the schema. `usage_json` remains valid JSON.

## Byte-identical export

`pandas.DataFrame.to_csv(index=False)` and `pandas.read_csv` (both with default
options, exactly as `eval_no_tools.py` and `analysis.py` use them) round-trip
**byte-for-byte** even on the full 240 MB US snapshot. Empirically:

- floats round-trip via Python's repr (`1956.142857142857` survives exactly),
- booleans emit as `True`/`False`,
- `NaN`/empty cells emit as empty strings,
- the line terminator is `\n`.

The only thing the store must reproduce is **dtype** and **row order**:

- An all-empty column reads back as `float64` (all `NaN`) and must emit as empty
  strings, not the literal `nan`/`None`. The store records each column's pandas
  emit-dtype (`runs.meta_json["csv_schema"]`) and rebuilds it on export.
- The original row order is not a simple sort, so import records the exact
  ordered list of `(model, scenario_id, variable)` keys
  (`runs.meta_json["row_order"]`) and export restores it.

Proof: `tests/test_runstore.py::test_snapshot_slice_roundtrip_is_byte_identical`
imports the first ~200 rows of the real US snapshot (written to a tmp CSV on the
fly — no new fixture committed), exports, and asserts the bytes are identical.
The full-file round-trip (US 240 MB, UK 34 MB) was verified manually and is
byte-identical; the in-test check uses a slice to stay fast and offline.

"Byte-identical for a clean run" means: a run imported from a CSV with no
in-store retries/repairs exports the original bytes. Once you apply retries that
change values, the export reflects the merged (superseded) result — which is the
intended new source of truth.

## API

```python
from policybench.runstore import RunStore, open_store

store = open_store("run.db")                  # creates schema, WAL mode

store.create_run(run_id, country=..., condition=..., model_set=..., output_set=...)

store.upsert_predictions(df)                  # CSV-shaped or store-shaped frame
store.record_response(run_id, model, scenario_id, status="ok", raw_response=...)
store.replace_response(run_id, model, scenario_id, status="ok", predictions=df)

store.missing_cases(run_id, models, scenario_ids, output_ids)   # the resume set
store.missing_responses(run_id, models, scenario_ids, output_ids=...)  # response-level
store.status_counts(run_id)                   # counts by model x status

run_id = store.import_run_csv("predictions.csv.gz", meta={...})
store.export_predictions_csv(run_id, "out.csv")   # byte-identical for a clean run
```

Module-level convenience wrappers (`create_run`, `import_run_csv`,
`export_predictions_csv`, `import_run_dir`) take a `db_path` and open/close the
store for you.

### Retry / replacement semantics

`replace_response` mirrors
`policybench.retry_eval.merge_retry_predictions`: a retry is a **whole-response
unit** keyed by `(model, scenario_id)`. When the new attempt's status is `ok`:

1. every prior `responses` row for that `(model, scenario_id)` is marked
   `replaced`,
2. the prior `predictions` rows are marked `parse_status = 'replaced'` (kept for
   audit), and
3. the new attempt's predictions are upserted and supersede the old ones via the
   predictions primary key.

If the retry itself fails (`status != 'ok'`), the prior rows are left intact and
only the new failed attempt is recorded — matching the existing pipeline, which
only applies *accepted* retries (those whose variable set exactly matches the
source, with no missing predictions/explanations and no errors).

Row-level repairs (`row_repair.py`) map onto a plain `upsert_predictions` with a
higher `source_attempt`: the predictions primary key replaces individual rows in
place, while superseded `responses` rows remain queryable.

### Resume semantics

`missing_cases(run_id, models, scenario_ids, output_ids)` returns the cartesian
product of the requested sets minus the cases that already have a **live parsed
prediction** (non-NULL `prediction`, `parse_status` not in
`{replaced, error}`). The caller supplies the expected sets because the output
set is scenario-dependent (person-level outputs expand per person); the
`status` CLI uses `missing_cases_observed`, which derives the per-scenario
expected outputs from those observed across all models, so a complete run
reports zero missing.

`missing_responses` mirrors the response-level completeness check in
`eval_no_tools._load_existing_rows`: a `(model, scenario_id)` is incomplete
unless it has a live prediction for every expected output id.

## CLI

```bash
# Import a run directory's predictions.csv[.gz] into <run-dir>/run.db
policybench runstore import --run-dir <dir> [--db <path>] [--run-id <id>]

# Export a run back to CSV (byte-identical for a clean run; .gz to compress)
policybench runstore export --db <path> --run-id <id> -o <csv>

# Counts by model/status and the missing-case count given the run's manifest
policybench runstore status --db <path> [--run-id <id>]
```

`import` reads `scenarios.csv.meta.json` next to the predictions for the country
and hashes `scenarios.csv` into `runs.scenario_manifest_sha256` when present.

## Cutover plan

The store is wired in additively (new module, new CLI subcommands, new tests;
no changes to `eval_no_tools.py`, `analysis.py`, or existing CLI commands). The
eval loop and retry/repair tooling are being refreshed in parallel PRs. Once
those land, cut over in stages so the CSV never stops being reproducible:

1. **Shadow write (now).** Keep writing `predictions.csv`; additionally import
   each finished run into `run.db`. Compare `export_predictions_csv` against the
   CSV in CI to guarantee parity (the byte-identity test is the gate).
2. **Store-first writes.** Have the eval loop call `record_response` /
   `upsert_predictions` as each chunk completes, and drive resume from
   `missing_responses` instead of re-reading the CSV. `predictions.csv` becomes
   an `export_predictions_csv` artifact emitted at the end of a run.
3. **Retries/repairs in-store.** Replace the copy-and-merge flow in
   `retry_eval.py` / `row_repair.py` with `replace_response` /
   `upsert_predictions`. The `replaced_original_responses` / `merged_predictions`
   audit files become queries over `responses` / `predictions`.
4. **Analyze reads the store.** Point `analysis.py` at
   `build_predictions_frame(run_id)` (or a thin view) instead of
   `pd.read_csv(predictions.csv)`. Keep CSV export available for the manuscript
   snapshot and external consumers.

Each step is independently revertible: as long as `export_predictions_csv`
reproduces the CSV, downstream tooling that still reads the CSV keeps working.
