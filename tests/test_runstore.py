"""Tests for the additive SQLite run store (policybench/runstore.py).

Fast and offline. Byte-equality is proven against a *slice* of the real,
in-repo snapshot artifact (no new fixture committed): we read the first ~200
rows of the US snapshot predictions.csv.gz, write them to a tmp CSV, import,
export, and compare bytes.
"""

import gzip
import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from policybench.runstore import (
    STATUS_VALUES,
    RunStore,
    export_predictions_csv,
    import_run_csv,
)

ROOT = Path(__file__).resolve().parents[1]
US_SNAPSHOT_PREDICTIONS = (
    ROOT
    / "paper"
    / "snapshot"
    / "20260501"
    / "runs"
    / "us_full_run_20260513_policyengine_4_4_4_nested_outputs"
    / "predictions.csv.gz"
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_predictions_frame(
    *,
    models=("model-a", "model-b"),
    scenarios=("scenario_000", "scenario_001"),
    variables=("snap", "ssi", "tanf"),
    with_response_columns=True,
):
    """Build a small CSV-shaped predictions frame, one chunk per response."""
    rows = []
    for model in models:
        for scenario in scenarios:
            call_id = f"{model}:{scenario}"
            raw = json.dumps({"outputs": {v: {"value": 1.0} for v in variables}})
            for i, variable in enumerate(variables):
                row = {
                    "call_id": call_id,
                    "model": model,
                    "scenario_id": scenario,
                    "variable": variable,
                    "prediction": float(i * 10),
                    "explanation": f"why {variable}",
                }
                if with_response_columns:
                    row.update(
                        {
                            "raw_response": raw,
                            "error": "",
                            "elapsed_seconds": 1.5,
                            "prompt_tokens": 100.0,
                            "completion_tokens": 20.0,
                            "total_tokens": 120.0,
                            "total_cost_usd": 0.001,
                            "provider_response_id": f"resp-{model}-{scenario}",
                            "provider_resolved_model": model,
                        }
                    )
                rows.append(row)
    return pd.DataFrame(rows)


def _slice_snapshot_csv(tmp_path: Path, n_rows: int = 200) -> tuple[Path, bytes]:
    """Write the first ``n_rows`` of the real US snapshot CSV to a tmp file.

    Returns ``(csv_path, expected_bytes)``. The expected bytes are exactly the
    decompressed header + ``n_rows`` data lines, so a byte-identical export must
    reproduce them.
    """
    if not US_SNAPSHOT_PREDICTIONS.exists():
        pytest.skip(f"snapshot artifact missing: {US_SNAPSHOT_PREDICTIONS}")
    with gzip.open(US_SNAPSHOT_PREDICTIONS, "rt", newline="") as handle:
        lines = []
        for i, line in enumerate(handle):
            lines.append(line)
            if i >= n_rows:  # header + n_rows data lines
                break
    text = "".join(lines)
    csv_path = tmp_path / "predictions.csv"
    csv_path.write_text(text)
    return csv_path, text.encode("utf-8")


# ---------------------------------------------------------------------------
# Schema round-trip
# ---------------------------------------------------------------------------


def test_schema_creates_expected_tables(tmp_path):
    store = RunStore(tmp_path / "run.db")
    names = {
        r["name"]
        for r in store.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"runs", "responses", "predictions"} <= names
    store.close()


def test_wal_mode_enabled(tmp_path):
    store = RunStore(tmp_path / "run.db")
    mode = store.connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    store.close()


def test_create_run_roundtrip(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run(
        "r1",
        country="us",
        condition="no_tools",
        model_set=["model-a", "model-b"],
        output_set={"outputs": ["snap", "ssi"]},
        meta={"note": "hello"},
    )
    run = store.get_run("r1")
    assert run["country"] == "us"
    assert run["condition"] == "no_tools"
    assert json.loads(run["model_set_json"]) == ["model-a", "model-b"]
    assert json.loads(run["meta_json"])["note"] == "hello"
    assert store.list_runs() == ["r1"]
    store.close()


def test_create_run_upsert_overwrites(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1", country="us")
    store.create_run("r1", country="uk", condition="x")
    run = store.get_run("r1")
    assert run["country"] == "uk"
    assert run["condition"] == "x"
    assert store.list_runs() == ["r1"]
    store.close()


def test_upsert_predictions_roundtrip_store_shape(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1", condition="no_tools")
    df = pd.DataFrame(
        [
            {
                "run_id": "r1",
                "model": "m",
                "scenario_id": "s0",
                "output_id": "snap",
                "prediction": 12.5,
                "explanation": "x",
                "parse_status": "ok",
                "source_attempt": 0,
            }
        ]
    )
    n = store.upsert_predictions(df)
    assert n == 1
    rows = store.connection.execute(
        "SELECT * FROM predictions WHERE run_id='r1'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["output_id"] == "snap"
    assert rows[0]["prediction"] == 12.5
    assert rows[0]["condition"] == "no_tools"
    store.close()


def test_upsert_predictions_idempotent(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1")
    df = _make_predictions_frame()
    df["run_id"] = "r1"
    store.upsert_predictions(df)
    first = store.connection.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    store.upsert_predictions(df)
    second = store.connection.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    assert first == second  # upsert, not append
    store.close()


def test_status_check_constraint_rejects_bad_status(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1")
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(
            "INSERT INTO responses (run_id, model, scenario_id, attempt, status) "
            "VALUES ('r1','m','s',0,'bogus')"
        )
    store.close()


def test_record_response_validates_status(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1")
    with pytest.raises(ValueError):
        store.record_response("r1", "m", "s", status="nope")
    store.close()


# ---------------------------------------------------------------------------
# Resume query correctness
# ---------------------------------------------------------------------------


def test_missing_cases_full_when_empty(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1")
    missing = store.missing_cases("r1", ["m1", "m2"], ["s0", "s1"], ["snap", "ssi"])
    # 2 models x 2 scenarios x 2 outputs = 8
    assert len(missing) == 8
    assert ("m1", "s0", "snap") in missing
    store.close()


def test_missing_cases_after_partial_seed(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1")
    # Seed only model-a's full set; model-b absent; and leave one of model-a's
    # outputs as a missing (NaN) prediction.
    df = _make_predictions_frame(
        models=("model-a",), scenarios=("s0",), variables=("snap", "ssi")
    )
    df["run_id"] = "r1"
    # Blank out the ssi prediction to simulate a parse miss.
    df.loc[df["variable"] == "ssi", "prediction"] = float("nan")
    df.loc[df["variable"] == "ssi", "explanation"] = ""
    store.upsert_predictions(df)

    missing = store.missing_cases("r1", ["model-a", "model-b"], ["s0"], ["snap", "ssi"])
    missing_set = set(missing)
    # model-a/s0/snap is satisfied -> not missing
    assert ("model-a", "s0", "snap") not in missing_set
    # model-a/s0/ssi was NaN -> still missing
    assert ("model-a", "s0", "ssi") in missing_set
    # model-b entirely missing
    assert ("model-b", "s0", "snap") in missing_set
    assert ("model-b", "s0", "ssi") in missing_set
    assert len(missing) == 3
    store.close()


def test_missing_cases_is_sorted_and_deduped(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1")
    missing = store.missing_cases(
        "r1", ["m2", "m1", "m1"], ["s1", "s0"], ["b", "a", "a"]
    )
    assert missing == sorted(missing)
    # duplicates collapsed: 2 models x 2 scenarios x 2 outputs
    assert len(missing) == 8


def test_missing_responses_response_level_resume(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1")
    df = _make_predictions_frame(
        models=("model-a",), scenarios=("s0", "s1"), variables=("snap", "ssi")
    )
    df["run_id"] = "r1"
    # s1 is missing its ssi prediction -> response incomplete.
    mask = (df["scenario_id"] == "s1") & (df["variable"] == "ssi")
    df.loc[mask, "prediction"] = float("nan")
    store.upsert_predictions(df)

    incomplete = store.missing_responses(
        "r1", ["model-a", "model-b"], ["s0", "s1"], output_ids=["snap", "ssi"]
    )
    incomplete_set = set(incomplete)
    assert ("model-a", "s0") not in incomplete_set  # complete
    assert ("model-a", "s1") in incomplete_set  # missing ssi
    assert ("model-b", "s0") in incomplete_set  # never ran
    assert ("model-b", "s1") in incomplete_set
    store.close()


def test_missing_cases_observed_zero_for_complete_run(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1")
    df = _make_predictions_frame()
    df["run_id"] = "r1"
    store.upsert_predictions(df)
    assert store.missing_cases_observed("r1") == []
    store.close()


# ---------------------------------------------------------------------------
# Retry replacement semantics
# ---------------------------------------------------------------------------


def test_replace_response_supersedes_prior_attempt(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1")
    # Attempt 0: snap parsed, ssi missing (a failed-contract response).
    df = _make_predictions_frame(
        models=("m",), scenarios=("s0",), variables=("snap", "ssi")
    )
    df["run_id"] = "r1"
    df.loc[df["variable"] == "ssi", "prediction"] = float("nan")
    df.loc[df["variable"] == "ssi", "explanation"] = ""
    store.upsert_predictions(df)

    before = set(store.missing_cases("r1", ["m"], ["s0"], ["snap", "ssi"]))
    assert ("m", "s0", "ssi") in before

    # Retry the whole response with a clean attempt (snap + ssi both parsed).
    retry = pd.DataFrame(
        [
            {
                "model": "m",
                "scenario_id": "s0",
                "variable": "snap",
                "prediction": 5.0,
                "explanation": "x",
                "parse_status": "ok",
            },
            {
                "model": "m",
                "scenario_id": "s0",
                "variable": "ssi",
                "prediction": 7.0,
                "explanation": "y",
                "parse_status": "ok",
            },
        ]
    )
    attempt = store.replace_response(
        "r1", "m", "s0", status="ok", predictions=retry, raw_response="{}"
    )
    assert attempt == 1

    # Prior response attempt is marked replaced; new one is ok.
    statuses = dict(
        store.connection.execute(
            "SELECT attempt, status FROM responses WHERE model='m' AND scenario_id='s0'"
        ).fetchall()
    )
    assert statuses[0] == "replaced"
    assert statuses[1] == "ok"

    # The superseding predictions win the primary key; nothing missing now.
    after = store.missing_cases("r1", ["m"], ["s0"], ["snap", "ssi"])
    assert after == []
    # ssi now carries the retry value.
    ssi = store.connection.execute(
        "SELECT prediction, source_attempt FROM predictions "
        "WHERE model='m' AND scenario_id='s0' AND output_id='ssi'"
    ).fetchone()
    assert ssi["prediction"] == 7.0
    assert ssi["source_attempt"] == 1
    store.close()


def test_replace_response_failed_retry_leaves_originals(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1")
    df = _make_predictions_frame(models=("m",), scenarios=("s0",), variables=("snap",))
    df["run_id"] = "r1"
    store.upsert_predictions(df)

    # A retry that itself failed (llm_error) must not supersede prior rows.
    store.replace_response("r1", "m", "s0", status="llm_error", error="boom")
    resp = dict(
        store.connection.execute(
            "SELECT attempt, status FROM responses WHERE model='m' AND scenario_id='s0'"
        ).fetchall()
    )
    assert resp[0] == "ok"  # original intact
    assert resp[1] == "llm_error"  # failed retry recorded
    # Original prediction still live.
    assert store.missing_cases("r1", ["m"], ["s0"], ["snap"]) == []
    store.close()


def test_replace_response_rejects_replaced_status(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1")
    with pytest.raises(ValueError):
        store.replace_response("r1", "m", "s0", status="replaced")
    store.close()


def test_record_response_upsert(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1")
    store.record_response("r1", "m", "s0", status="ok", raw_response="a", cost_usd=0.01)
    store.record_response("r1", "m", "s0", status="ok", raw_response="b", cost_usd=0.02)
    rows = store.connection.execute(
        "SELECT raw_response, cost_usd FROM responses WHERE model='m'"
    ).fetchall()
    assert len(rows) == 1  # same (run, model, scenario, attempt) -> upsert
    assert rows[0]["raw_response"] == "b"
    store.close()


# ---------------------------------------------------------------------------
# Status counts
# ---------------------------------------------------------------------------


def test_status_counts_shape(tmp_path):
    store = RunStore(tmp_path / "run.db")
    store.create_run("r1")
    df = _make_predictions_frame()
    df["run_id"] = "r1"
    store.upsert_predictions(df)
    counts = store.status_counts("r1")
    assert counts["totals"]["predictions"] == len(df)
    assert counts["totals"]["live_predictions"] == len(df)
    assert counts["responses_by_model_status"]
    assert all("status" in row for row in counts["responses_by_model_status"])
    store.close()


# ---------------------------------------------------------------------------
# Import / export round-trip on synthetic data
# ---------------------------------------------------------------------------


def test_import_export_roundtrip_synthetic(tmp_path):
    frame = _make_predictions_frame()
    csv_path = tmp_path / "predictions.csv"
    frame.to_csv(csv_path, index=False)
    expected = csv_path.read_bytes()

    db = tmp_path / "run.db"
    run_id = import_run_csv(db, csv_path, run_id="synthetic")
    out = tmp_path / "export.csv"
    export_predictions_csv(db, run_id, out)
    assert out.read_bytes() == expected


def test_export_gz_when_path_ends_gz(tmp_path):
    frame = _make_predictions_frame()
    csv_path = tmp_path / "predictions.csv"
    frame.to_csv(csv_path, index=False)
    db = tmp_path / "run.db"
    import_run_csv(db, csv_path, run_id="synthetic")
    out = tmp_path / "export.csv.gz"
    export_predictions_csv(db, "synthetic", out)
    # The gz decompresses to the same CSV text.
    with gzip.open(out, "rt") as handle:
        text = handle.read()
    assert text == csv_path.read_text()


def test_unknown_columns_preserved_in_extra_json(tmp_path):
    frame = _make_predictions_frame()
    frame["some_future_column"] = "long-tail-value"
    csv_path = tmp_path / "predictions.csv"
    frame.to_csv(csv_path, index=False)
    expected = csv_path.read_bytes()

    db = tmp_path / "run.db"
    import_run_csv(db, csv_path, run_id="r")
    # The unknown column should be in extra_json, not dropped.
    store = RunStore(db)
    row = store.connection.execute(
        "SELECT extra_json FROM predictions LIMIT 1"
    ).fetchone()
    assert "some_future_column" in json.loads(row["extra_json"])
    store.close()
    out = tmp_path / "export.csv"
    export_predictions_csv(db, "r", out)
    assert out.read_bytes() == expected


# ---------------------------------------------------------------------------
# THE PROOF: byte-identical round-trip on a slice of the real snapshot
# ---------------------------------------------------------------------------


def test_snapshot_slice_roundtrip_is_byte_identical(tmp_path):
    csv_path, expected = _slice_snapshot_csv(tmp_path, n_rows=200)

    db = tmp_path / "run.db"
    run_id = import_run_csv(db, csv_path, run_id="us_slice")
    out = tmp_path / "export.csv"
    export_predictions_csv(db, run_id, out)
    actual = out.read_bytes()

    assert actual == expected, (
        "Export is not byte-identical to the imported snapshot slice. "
        f"expected {len(expected)} bytes, got {len(actual)}."
    )


def test_snapshot_slice_preserves_all_columns(tmp_path):
    csv_path, _ = _slice_snapshot_csv(tmp_path, n_rows=200)
    db = tmp_path / "run.db"
    run_id = import_run_csv(db, csv_path, run_id="us_slice")

    store = RunStore(db)
    exported = store.build_predictions_frame(run_id)
    original = pd.read_csv(csv_path)
    # Same columns, same order, same shape.
    assert list(exported.columns) == list(original.columns)
    assert exported.shape == original.shape
    # Chunk decomposition recovered the per-variable raw_response exactly.
    pd.testing.assert_series_equal(exported["raw_response"], original["raw_response"])
    store.close()


def test_import_run_dir_uses_sidecar_country(tmp_path):
    """import_run_dir picks up country from the scenarios sidecar."""
    csv_path, _ = _slice_snapshot_csv(tmp_path, n_rows=50)
    # Drop a minimal scenarios.csv.meta.json next to it.
    (tmp_path / "scenarios.csv.meta.json").write_text(json.dumps({"country": "us"}))
    from policybench.runstore import import_run_dir

    run_id, db_path = import_run_dir(tmp_path, run_id="us_slice")
    store = RunStore(db_path)
    assert store.get_run(run_id)["country"] == "us"
    store.close()


def test_status_values_constant_matches_schema():
    assert STATUS_VALUES == ("ok", "parse_error", "llm_error", "replaced")


# ---------------------------------------------------------------------------
# Float-formatting platform-independence (regression for the ubuntu-only CI
# failure where total_tokens=2297.3333333333335 exported as 2297.333333333333).
#
# Root cause: the value round-tripped through a float (parse on import, store as
# REAL / JSON number, re-format on export). Two platform-dependent steps could
# corrupt it: (1) pandas' default CSV float parser (xstrtod) is fast but lossy
# and lands on different doubles on different builds; (2) sqlite renders
# REAL->TEXT with a version-dependent precision. The fix keeps the exact source
# string for every float-bearing column (response columns + prediction/
# explanation) and emits it verbatim, so no float parse/format is on the
# byte-identical export path.
# ---------------------------------------------------------------------------

# A value whose shortest round-trip repr (17 sig digits) differs from its
# %.16g rendering -- exactly the token value that broke ubuntu CI.
_TRICKY_FLOAT_TEXT = "2297.3333333333335"

# A value the default (lossy) pandas CSV parser resolves to a *different* double
# than the round-trip parser -- the import-side half of the same root cause.
_LOSSY_PARSED_FLOAT_TEXT = "1234.5678901234567"


def _predictions_frame_with_tricky_floats():
    """One response whose token/cost columns carry %.16g-sensitive values."""
    variables = ("snap", "ssi", "tanf")
    raw = '{"outputs": {}}'
    rows = []
    for i, variable in enumerate(variables):
        rows.append(
            {
                "call_id": "m:s0",
                "model": "m",
                "scenario_id": "s0",
                "variable": variable,
                "prediction": float(i),
                "explanation": f"e{i}",
                "raw_response": raw,
                "error": "",
                "elapsed_seconds": 3.292535610900294,
                "prompt_tokens": 1956.142857142857,
                "completion_tokens": 341.1904761904762,
                "total_tokens": float(_TRICKY_FLOAT_TEXT),
                "reasoning_tokens": 0.0,
                "cached_prompt_tokens": 0.0,
                "total_cost_usd": 0.0036620952380952,
                "provider_response_id": "rid",
            }
        )
    return pd.DataFrame(rows)


def test_response_column_stash_stores_exact_source_strings(tmp_path):
    """The stash holds verbatim CSV text, not parsed floats."""
    frame = _predictions_frame_with_tricky_floats()
    csv_path = tmp_path / "predictions.csv"
    frame.to_csv(csv_path, index=False)
    # Confirm the source text really contains the 17-digit form.
    assert _TRICKY_FLOAT_TEXT in csv_path.read_text()

    db = tmp_path / "run.db"
    import_run_csv(db, csv_path, run_id="r")

    store = RunStore(db)
    usage_json = store.connection.execute(
        "SELECT usage_json FROM responses LIMIT 1"
    ).fetchone()[0]
    blob = json.loads(usage_json)
    assert blob["_csv_raw"] is True
    # Stored as the exact source string -- not a JSON float number.
    assert blob["_csv"]["total_tokens"] == _TRICKY_FLOAT_TEXT
    assert isinstance(blob["_csv"]["total_tokens"], str)
    store.close()


def test_export_response_columns_emit_verbatim_strings(tmp_path):
    """Export builds response columns as verbatim strings (no float coercion)."""
    frame = _predictions_frame_with_tricky_floats()
    csv_path = tmp_path / "predictions.csv"
    frame.to_csv(csv_path, index=False)
    db = tmp_path / "run.db"
    import_run_csv(db, csv_path, run_id="r")

    store = RunStore(db)
    exported = store.build_predictions_frame("r")
    # total_tokens is now an object/string column holding the exact source text.
    assert exported["total_tokens"].map(type).eq(str).all()
    assert (exported["total_tokens"] == _TRICKY_FLOAT_TEXT).all()
    store.close()


class _MangledRow(dict):
    """A mapping that behaves like ``sqlite3.Row`` for the store's access."""


def _old_sqlite_row_factory(cursor, row):
    """Render every float read from sqlite as ``%.16g`` text.

    Pre-3.43 sqlite builds (such as the one bundled with the Linux CI Python)
    render floats with up to 16 significant digits rather than the shortest
    round-trip form. Simulating the worst case proves the export must not depend
    on sqlite's float-to-text rendering.
    """
    columns = [d[0] for d in cursor.description]
    return _MangledRow(
        (col, "%.16g" % val if isinstance(val, float) else val)
        for col, val in zip(columns, row)
    )


def test_export_is_byte_identical_under_simulated_old_sqlite(tmp_path):
    """Byte-identity must not depend on sqlite's REAL->TEXT formatting.

    This reproduces the ubuntu-only failure mode locally: every float read from
    sqlite is rendered with %.16g (as the older CI sqlite would). The export must
    still reproduce the source bytes exactly.
    """
    csv_path, expected = _slice_snapshot_csv(tmp_path, n_rows=200)

    db = tmp_path / "run.db"
    run_id = import_run_csv(db, csv_path, run_id="us_slice")

    store = RunStore(db)
    # Swap the row factory so every float read renders as %.16g, mimicking the
    # older CI sqlite. dict(row) and row["col"] both keep working.
    store.connection.row_factory = _old_sqlite_row_factory
    try:
        out = tmp_path / "export.csv"
        store.export_predictions_csv(run_id, out)
        actual = out.read_bytes()
    finally:
        store.close()

    assert actual == expected, (
        "Export is not byte-identical when sqlite renders REAL->TEXT as %.16g "
        "(the ubuntu CI failure mode). A float is leaking into the export's "
        "text formatting."
    )


def _old_sqlite_row_factory_15g(cursor, row):
    """As above but with %.15g (the documented pre-3.52 sqlite REAL->TEXT)."""
    columns = [d[0] for d in cursor.description]
    return _MangledRow(
        (col, "%.15g" % val if isinstance(val, float) else val)
        for col, val in zip(columns, row)
    )


def test_export_byte_identical_under_pre352_sqlite_15g(tmp_path):
    """Pre-3.52 sqlite rounds REAL->TEXT to 15 digits; export must not depend on it."""
    csv_path, expected = _slice_snapshot_csv(tmp_path, n_rows=200)
    db = tmp_path / "run.db"
    run_id = import_run_csv(db, csv_path, run_id="us_slice")
    store = RunStore(db)
    store.connection.row_factory = _old_sqlite_row_factory_15g
    try:
        out = tmp_path / "export.csv"
        store.export_predictions_csv(run_id, out)
        actual = out.read_bytes()
    finally:
        store.close()
    assert actual == expected


def test_high_precision_prediction_roundtrips_byte_identically(tmp_path):
    """A prediction the lossy parser mangles must still export verbatim.

    The default pandas CSV parser resolves this token to a different double than
    the source; storing the exact source string and emitting it keeps the export
    byte-identical regardless of the parser/platform.
    """
    variables = ("snap", "ssi")
    rows = [
        {
            "call_id": "m:s0",
            "model": "m",
            "scenario_id": "s0",
            "variable": var,
            "prediction": float(_LOSSY_PARSED_FLOAT_TEXT) if i == 0 else float(i),
            "explanation": f"e{i}",
            "raw_response": "{}",
            "error": "",
            "elapsed_seconds": 1.5,
            "total_tokens": float(_TRICKY_FLOAT_TEXT),
            "total_cost_usd": 0.0036620952380952,
            "provider_response_id": "rid",
        }
        for i, var in enumerate(variables)
    ]
    frame = pd.DataFrame(rows)
    csv_path = tmp_path / "predictions.csv"
    frame.to_csv(csv_path, index=False)
    assert _LOSSY_PARSED_FLOAT_TEXT in csv_path.read_text()
    expected = csv_path.read_bytes()

    db = tmp_path / "run.db"
    run_id = import_run_csv(db, csv_path, run_id="r")

    # The exact prediction source string is preserved for verbatim export.
    store = RunStore(db)
    extra_json = store.connection.execute(
        "SELECT extra_json FROM predictions WHERE output_id = 'snap'"
    ).fetchone()[0]
    assert json.loads(extra_json)["_raw_prediction"] == _LOSSY_PARSED_FLOAT_TEXT

    out = tmp_path / "export.csv"
    store.export_predictions_csv(run_id, out)
    store.close()
    assert out.read_bytes() == expected


def test_default_csv_parser_is_lossy_for_the_token_class():
    """Document the import-side root cause: the default float parser is lossy.

    The default pandas parser (xstrtod) is fast but can land on a different
    double than the round-trip parser, and exactly which double is
    build/platform-dependent -- the import-side half of the ubuntu CI failure.
    The round-trip parser always recovers the canonical shortest-repr value. This
    is why the store keeps exact source strings rather than relying on a
    re-parsed float. (The default parser is lossy for this token on the platforms
    we ship to; we don't hard-assert it here to stay build-robust.)
    """
    import io

    csv = f"x\n{_LOSSY_PARSED_FLOAT_TEXT}\n"
    round_trip = float(
        pd.read_csv(io.StringIO(csv), float_precision="round_trip")["x"].iloc[0]
    )
    # The round-trip parser always recovers the exact canonical value.
    assert repr(round_trip) == _LOSSY_PARSED_FLOAT_TEXT
