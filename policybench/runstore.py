"""Additive SQLite run store for PolicyBench benchmark artifacts.

Today a benchmark run persists as ``predictions.csv`` (plus ``.meta.json``
sidecars) with hand-rolled chunked resume, whole-response retries, and row
repairs scattered across :mod:`policybench.eval_no_tools`,
:mod:`policybench.retry_eval`, and :mod:`policybench.row_repair`. This module is
a *purely additive* alternative store: it does not replace any of that yet. It
gives a single ``run.db`` SQLite database per run directory that can:

* import an existing ``predictions.csv`` / ``predictions.csv.gz`` losslessly,
* export it back **byte-for-byte identically** for a clean run,
* answer the resume question (which model x scenario x output cases are still
  missing) directly from SQL, and
* record/replace LLM responses with the same accepted-retry semantics the
  existing retry pipeline uses (a later ``ok`` attempt marks the prior attempt's
  rows ``replaced`` and supersedes the parsed predictions).

Design notes
------------
The on-disk ``predictions.csv`` is the contract. It is emitted by pandas via
``DataFrame.to_csv(index=False)`` and consumed by ``pandas.read_csv`` (see
``eval_no_tools.py`` and ``analysis.py``). Empirically, reading that CSV and
re-emitting it with the same call is byte-identical even on the full 240 MB
snapshot, because pandas round-trips floats by repr, writes ``True``/``False``
for booleans, and writes empty strings for ``NaN``. The only subtlety is dtype:
an all-empty column reads back as ``float64`` (all-``NaN``), a mixed column as
``object``. We therefore persist, per run, the exact ordered column list and the
pandas emit-dtype of each column (``output_set_json``), and on export rebuild
each column with that dtype so the re-emitted bytes match.

To stay faithful while still offering a useful semantic schema, every known
prediction column is mapped onto typed store columns and anything left over for
a given run is stashed verbatim in ``predictions.extra_json``. Export reassembles
the original column order from the stored CSV schema, so unknown/long-tail
columns survive a round-trip.

Stdlib ``sqlite3`` only; no new dependencies.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "RunStore",
    "STATUS_VALUES",
    "DEFAULT_DB_NAME",
    "create_run",
    "open_store",
    "import_run_csv",
    "export_predictions_csv",
]

DEFAULT_DB_NAME = "run.db"

#: Valid values for ``responses.status``. ``ok`` means the response parsed and
#: satisfied the output contract; ``parse_error`` means the provider returned a
#: response we could not parse into predictions; ``llm_error`` means the
#: provider/transport failed; ``replaced`` is set by :meth:`RunStore.replace_response`
#: on a superseded earlier attempt.
STATUS_VALUES = ("ok", "parse_error", "llm_error", "replaced")

#: Parse statuses recorded per prediction row. ``ok`` is a parsed value;
#: ``missing`` is a row that exists (the response was attempted) but produced no
#: numeric prediction; ``replaced`` is a superseded row.
PREDICTION_PARSE_STATUSES = ("ok", "missing", "replaced", "error")

# ---------------------------------------------------------------------------
# Column model for predictions.csv
#
# Discovered from the real snapshot predictions.csv.gz under
# paper/snapshot/20260501/runs/{us,uk}_full_run_*_nested_outputs/ (22 columns).
# ``variable`` is the output id. ``call_id`` == "{model}:{scenario_id}"
# (optionally "{run_id}:{model}:{scenario_id}") and is the scenario-level key.
# Token/cost/latency/raw_response/error/provider_* columns are response-level:
# the eval loop apportions per-call usage across the response's variables, so the
# same value repeats on every prediction row of a response. We persist them once
# on ``responses`` and fan them back out on export.
# ---------------------------------------------------------------------------

# Columns that uniquely identify a prediction row.
_KEY_COLUMNS = ("model", "scenario_id", "variable")

# Response-level columns (one value per model x scenario response). These live on
# the ``responses`` table and are broadcast back to every prediction row of the
# response on export.
_RESPONSE_COLUMNS = (
    "call_id",
    "raw_response",
    "error",
    "elapsed_seconds",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "reasoning_tokens",
    "cached_prompt_tokens",
    "provider_reported_cost_usd",
    "reconstructed_cost_usd",
    "total_cost_usd",
    "cost_is_estimated",
    "estimated_cost_usd",
    "provider_response_id",
    "provider_system_fingerprint",
    "provider_resolved_model",
)

# Prediction-level columns (one value per output id).
_PREDICTION_COLUMNS = ("prediction", "explanation")

# An optional run_id column appears only when the eval loop is given a run_id.
_RUN_ID_COLUMN = "run_id"

# Every column we know how to route to a typed store column. Anything outside
# this set for a given run is preserved in predictions.extra_json.
_KNOWN_COLUMNS = frozenset(
    (_RUN_ID_COLUMN,) + _KEY_COLUMNS + _PREDICTION_COLUMNS + _RESPONSE_COLUMNS
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# DataFrame <-> CSV faithfulness helpers
# ---------------------------------------------------------------------------


def _read_predictions_dataframe(path: str | Path) -> pd.DataFrame:
    """Read a predictions CSV (optionally .gz) exactly as the repo does.

    ``eval_no_tools`` and ``analysis`` both call ``pd.read_csv`` with default
    options, so we do the same to inherit identical type inference.
    """
    path = Path(path)
    if path.suffix == ".gz" or path.name.endswith(".csv.gz"):
        with gzip.open(path, "rb") as handle:
            data = handle.read()
        return pd.read_csv(io.BytesIO(data))
    return pd.read_csv(path)


def _emit_dtype(series: pd.Series) -> str:
    """Return a stable token describing how to rebuild this column on export.

    The token captures the distinctions that matter for byte-identical
    ``to_csv`` output: float vs int vs bool vs object/string. All-empty columns
    arrive as ``float64`` and must be rebuilt as ``float64`` (so they emit as
    empty strings, not the literal ``nan``/``None``).
    """
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "bool"
    if pd.api.types.is_integer_dtype(dtype):
        return "int64"
    if pd.api.types.is_float_dtype(dtype):
        return "float64"
    return "object"


def _csv_schema(frame: pd.DataFrame) -> dict[str, Any]:
    """Capture the ordered columns and emit-dtypes needed to rebuild ``frame``."""
    return {
        "columns": list(frame.columns),
        "dtypes": {col: _emit_dtype(frame[col]) for col in frame.columns},
    }


def _coerce_column(values: pd.Series, emit_dtype: str) -> pd.Series:
    """Rebuild a column to its recorded emit-dtype for byte-identical export."""
    if emit_dtype == "bool":
        return values.astype(bool)
    if emit_dtype == "int64":
        return values.astype("int64")
    if emit_dtype == "float64":
        return pd.to_numeric(values, errors="coerce").astype("float64")
    # object/string: SQLite returns None for NULL; pandas read_csv used NaN.
    # Normalize None -> NaN so to_csv writes an empty field (not "None").
    return values.where(values.notna(), np.nan)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def _store_scalar(value: Any) -> Any:
    """Convert a pandas/numpy scalar into a value sqlite3 can bind.

    NaN/NA -> ``None`` (SQL NULL); numpy scalars -> Python scalars; everything
    else passes through.
    """
    if _is_missing(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, np.str_):
        return str(value)
    return value


def _signature_value(value: Any) -> Any:
    """Normalize a value for use in a chunk-response signature.

    NaN/None collapse to a single sentinel so rows from the same provider call
    (which share identical response-level columns) group together regardless of
    how missing values are spelled.
    """
    if _is_missing(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def _store_bool(value: Any) -> int | None:
    """Store a possibly-NaN boolean-ish CSV value as 0/1/NULL."""
    if _is_missing(value):
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return 1
        if normalized in {"false", "0", ""}:
            return 0
    return 1 if bool(value) else 0


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id                  TEXT PRIMARY KEY,
    country                 TEXT,
    condition               TEXT,
    created_at              TEXT,
    scenario_manifest_sha256 TEXT,
    model_set_json          TEXT,
    output_set_json         TEXT,
    meta_json               TEXT
);

CREATE TABLE IF NOT EXISTS responses (
    run_id          TEXT NOT NULL,
    model           TEXT NOT NULL,
    scenario_id     TEXT NOT NULL,
    attempt         INTEGER NOT NULL,
    status          TEXT CHECK(status IN ('ok','parse_error','llm_error','replaced')),
    call_id         TEXT,
    raw_response    TEXT,
    error           TEXT,
    usage_json      TEXT,
    cost_usd        REAL,
    latency_s       REAL,
    provider_response_id        TEXT,
    provider_system_fingerprint TEXT,
    provider_resolved_model     TEXT,
    created_at      TEXT,
    PRIMARY KEY (run_id, model, scenario_id, attempt)
);

CREATE TABLE IF NOT EXISTS predictions (
    run_id          TEXT NOT NULL,
    model           TEXT NOT NULL,
    scenario_id     TEXT NOT NULL,
    output_id       TEXT NOT NULL,
    condition       TEXT,
    prediction      REAL,
    explanation     TEXT,
    parse_status    TEXT,
    source_attempt  INTEGER,
    extra_json      TEXT,
    PRIMARY KEY (run_id, model, scenario_id, output_id)
);

CREATE INDEX IF NOT EXISTS idx_predictions_lookup
    ON predictions (run_id, model, scenario_id);
CREATE INDEX IF NOT EXISTS idx_responses_status
    ON responses (run_id, status);
"""


# ---------------------------------------------------------------------------
# RunStore
# ---------------------------------------------------------------------------


class RunStore:
    """A SQLite-backed store for one or more benchmark runs in a single file.

    Open with :func:`open_store` (or construct directly with a path). The store
    keeps a single connection in WAL mode. It is not thread-safe; use one store
    per worker, or serialize access.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "RunStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    # -- runs --------------------------------------------------------------

    def create_run(
        self,
        run_id: str,
        *,
        country: str | None = None,
        condition: str | None = None,
        scenario_manifest_sha256: str | None = None,
        model_set: Sequence[str] | dict[str, str] | None = None,
        output_set: Sequence[str] | dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> str:
        """Create (or update) a run row. Returns ``run_id``.

        ``model_set`` and ``output_set`` may be the literal sets used to drive
        the resume query, or richer structures (e.g. the CSV schema for
        ``output_set``). They are stored as JSON verbatim.
        """
        self._conn.execute(
            """
            INSERT INTO runs (
                run_id, country, condition, created_at,
                scenario_manifest_sha256, model_set_json, output_set_json, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                country=excluded.country,
                condition=excluded.condition,
                created_at=excluded.created_at,
                scenario_manifest_sha256=excluded.scenario_manifest_sha256,
                model_set_json=excluded.model_set_json,
                output_set_json=excluded.output_set_json,
                meta_json=excluded.meta_json
            """,
            (
                run_id,
                country,
                condition,
                created_at or _utcnow(),
                scenario_manifest_sha256,
                _json_dumps(model_set) if model_set is not None else None,
                _json_dumps(output_set) if output_set is not None else None,
                _json_dumps(meta) if meta is not None else None,
            ),
        )
        self._conn.commit()
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def list_runs(self) -> list[str]:
        return [
            r["run_id"]
            for r in self._conn.execute(
                "SELECT run_id FROM runs ORDER BY run_id"
            ).fetchall()
        ]

    # -- responses ---------------------------------------------------------

    def record_response(
        self,
        run_id: str,
        model: str,
        scenario_id: str,
        *,
        attempt: int = 0,
        status: str,
        raw_response: str | None = None,
        error: str | None = None,
        usage: dict[str, Any] | None = None,
        cost_usd: float | None = None,
        latency_s: float | None = None,
        call_id: str | None = None,
        provider_response_id: str | None = None,
        provider_system_fingerprint: str | None = None,
        provider_resolved_model: str | None = None,
        created_at: str | None = None,
    ) -> None:
        """Upsert a single response attempt.

        ``status`` must be one of :data:`STATUS_VALUES`. Re-recording the same
        ``(run_id, model, scenario_id, attempt)`` overwrites it.
        """
        if status not in STATUS_VALUES:
            raise ValueError(f"status must be one of {STATUS_VALUES!r}, got {status!r}")
        if call_id is None:
            call_id = f"{model}:{scenario_id}"
        self._conn.execute(
            """
            INSERT INTO responses (
                run_id, model, scenario_id, attempt, status, call_id,
                raw_response, error, usage_json, cost_usd, latency_s,
                provider_response_id, provider_system_fingerprint,
                provider_resolved_model, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, model, scenario_id, attempt) DO UPDATE SET
                status=excluded.status,
                call_id=excluded.call_id,
                raw_response=excluded.raw_response,
                error=excluded.error,
                usage_json=excluded.usage_json,
                cost_usd=excluded.cost_usd,
                latency_s=excluded.latency_s,
                provider_response_id=excluded.provider_response_id,
                provider_system_fingerprint=excluded.provider_system_fingerprint,
                provider_resolved_model=excluded.provider_resolved_model,
                created_at=excluded.created_at
            """,
            (
                run_id,
                model,
                scenario_id,
                int(attempt),
                status,
                call_id,
                raw_response,
                error,
                _json_dumps(usage) if usage is not None else None,
                cost_usd,
                latency_s,
                provider_response_id,
                provider_system_fingerprint,
                provider_resolved_model,
                created_at or _utcnow(),
            ),
        )
        self._conn.commit()

    def replace_response(
        self,
        run_id: str,
        model: str,
        scenario_id: str,
        *,
        status: str,
        attempt: int | None = None,
        predictions: pd.DataFrame | Iterable[dict[str, Any]] | None = None,
        raw_response: str | None = None,
        error: str | None = None,
        usage: dict[str, Any] | None = None,
        cost_usd: float | None = None,
        latency_s: float | None = None,
        provider_response_id: str | None = None,
        provider_system_fingerprint: str | None = None,
        provider_resolved_model: str | None = None,
    ) -> int:
        """Record a retry attempt that supersedes the prior response.

        Mirrors the accepted-retry semantics in
        :func:`policybench.retry_eval.merge_retry_predictions`: a retry is a
        whole-response unit keyed by ``(model, scenario_id)``. When the new
        attempt's ``status`` is ``ok`` we:

        * mark every prior attempt row for this response ``replaced``,
        * mark the prior parsed prediction rows ``replaced`` (kept for audit),
          and
        * upsert the new attempt's predictions, which supersede the old ones via
          the predictions primary key.

        If ``status`` is not ``ok`` (the retry itself failed), the prior rows are
        left intact and only the new failed attempt is recorded, matching the
        existing pipeline's behaviour of only applying *accepted* retries.

        Returns the integer attempt number assigned to the new response.
        """
        if status not in STATUS_VALUES or status == "replaced":
            raise ValueError(
                "replace_response status must be one of "
                f"{('ok', 'parse_error', 'llm_error')!r}, got {status!r}"
            )

        next_attempt = (
            attempt
            if attempt is not None
            else self._next_attempt(run_id, model, scenario_id)
        )

        if status == "ok":
            # Supersede prior attempts and their parsed rows.
            self._conn.execute(
                """
                UPDATE responses SET status = 'replaced'
                WHERE run_id = ? AND model = ? AND scenario_id = ?
                  AND attempt < ? AND status != 'replaced'
                """,
                (run_id, model, scenario_id, next_attempt),
            )
            self._conn.execute(
                """
                UPDATE predictions SET parse_status = 'replaced'
                WHERE run_id = ? AND model = ? AND scenario_id = ?
                  AND source_attempt < ?
                """,
                (run_id, model, scenario_id, next_attempt),
            )

        self.record_response(
            run_id,
            model,
            scenario_id,
            attempt=next_attempt,
            status=status,
            raw_response=raw_response,
            error=error,
            usage=usage,
            cost_usd=cost_usd,
            latency_s=latency_s,
            provider_response_id=provider_response_id,
            provider_system_fingerprint=provider_system_fingerprint,
            provider_resolved_model=provider_resolved_model,
        )

        if status == "ok" and predictions is not None:
            frame = self._predictions_to_frame(
                predictions, run_id, model, scenario_id, next_attempt
            )
            self.upsert_predictions(frame)

        self._conn.commit()
        return next_attempt

    def _next_attempt(self, run_id: str, model: str, scenario_id: str) -> int:
        row = self._conn.execute(
            """
            SELECT MAX(attempt) AS m FROM responses
            WHERE run_id = ? AND model = ? AND scenario_id = ?
            """,
            (run_id, model, scenario_id),
        ).fetchone()
        current = row["m"] if row is not None else None
        return 0 if current is None else int(current) + 1

    @staticmethod
    def _predictions_to_frame(
        predictions: pd.DataFrame | Iterable[dict[str, Any]],
        run_id: str,
        model: str,
        scenario_id: str,
        attempt: int,
    ) -> pd.DataFrame:
        if isinstance(predictions, pd.DataFrame):
            frame = predictions.copy()
        else:
            frame = pd.DataFrame(list(predictions))
        frame["run_id"] = run_id
        frame["model"] = model
        frame["scenario_id"] = scenario_id
        if "source_attempt" not in frame.columns:
            frame["source_attempt"] = attempt
        return frame

    # -- predictions -------------------------------------------------------

    def upsert_predictions(self, df: pd.DataFrame, *, run_id: str | None = None) -> int:
        """Upsert prediction rows from a DataFrame.

        Accepts either the *store* shape (``output_id``/``parse_status``/...) or
        the raw *CSV* shape (``variable``/``prediction``/``explanation`` plus the
        response-level columns). CSV-shaped frames are decomposed: response-level
        columns populate ``responses`` (attempt 0 unless ``source_attempt`` is
        present), prediction-level columns populate ``predictions``, and any
        unknown columns are preserved in ``extra_json``.

        Returns the number of prediction rows written.
        """
        if df is None or df.empty:
            return 0

        frame = df.copy()
        if run_id is not None:
            frame[_RUN_ID_COLUMN] = run_id

        is_store_shape = "output_id" in frame.columns
        if is_store_shape:
            return self._upsert_store_predictions(frame)
        return self._upsert_csv_predictions(frame)

    def _resolve_run_id(self, frame: pd.DataFrame) -> str:
        if _RUN_ID_COLUMN in frame.columns:
            run_ids = sorted(
                {_store_scalar(v) for v in frame[_RUN_ID_COLUMN] if not _is_missing(v)}
            )
            if len(run_ids) == 1:
                return str(run_ids[0])
            if len(run_ids) > 1:
                raise ValueError(
                    "Predictions frame mixes multiple run_ids; pass one frame "
                    f"per run_id (saw {run_ids!r})."
                )
        existing = self.list_runs()
        if len(existing) == 1:
            return existing[0]
        raise ValueError(
            "Could not determine run_id: frame has no run_id column and the "
            f"store holds {len(existing)} runs. Pass run_id explicitly or "
            "create the run first."
        )

    def _upsert_store_predictions(self, frame: pd.DataFrame) -> int:
        run_id = self._resolve_run_id(frame)
        run_condition = self._condition_for(run_id)
        rows = []
        for record in frame.to_dict("records"):
            extra = record.get("extra_json")
            if isinstance(extra, dict):
                extra = _json_dumps(extra)
            condition = _store_scalar(record.get("condition"))
            if condition is None:
                condition = run_condition
            rows.append(
                (
                    run_id,
                    str(record["model"]),
                    str(record["scenario_id"]),
                    str(record["output_id"]),
                    condition,
                    _store_scalar(record.get("prediction")),
                    _store_scalar(record.get("explanation")),
                    _store_scalar(record.get("parse_status")),
                    _store_scalar(record.get("source_attempt")),
                    _store_scalar(extra),
                )
            )
        self._executemany_predictions(rows)
        return len(rows)

    def _upsert_csv_predictions(self, frame: pd.DataFrame) -> int:
        run_id = self._resolve_run_id(frame)
        condition = self._condition_for(run_id)

        present_columns = list(frame.columns)
        extra_columns = [col for col in present_columns if col not in _KNOWN_COLUMNS]
        has_attempt = "source_attempt" in present_columns

        # A logical "response" is one provider call. In chunked runs a scenario's
        # outputs are split across several calls, each with its own raw_response,
        # latency, tokens and cost (all constant within the chunk). We therefore
        # group rows by their response-level column values *within* each
        # (model, scenario_id) and assign attempt = first-seen chunk index. The
        # response columns repeat verbatim on every prediction row in the CSV, so
        # this reconstructs the file exactly on export. A whole-response retry
        # (see replace_response) occupies higher attempt numbers.
        response_signature_cols = [
            col for col in _RESPONSE_COLUMNS if col in present_columns
        ]

        response_rows: dict[tuple[str, str, int], dict[str, Any]] = {}
        # Per (model, scenario_id): map a chunk signature -> assigned attempt.
        chunk_attempts: dict[tuple[str, str], dict[tuple, int]] = {}
        prediction_rows = []

        for record in frame.to_dict("records"):
            model = str(record["model"])
            scenario_id = str(record["scenario_id"])
            if has_attempt:
                attempt = int(_store_scalar(record["source_attempt"]) or 0)
            else:
                signature = tuple(
                    _signature_value(record.get(col)) for col in response_signature_cols
                )
                group = (model, scenario_id)
                seen = chunk_attempts.setdefault(group, {})
                if signature not in seen:
                    seen[signature] = len(seen)
                attempt = seen[signature]

            key = (model, scenario_id, attempt)
            if key not in response_rows:
                response_rows[key] = self._response_record_from_csv(
                    record, model, scenario_id, attempt
                )

            extra = {col: _store_scalar(record.get(col)) for col in extra_columns}
            prediction_rows.append(
                (
                    run_id,
                    model,
                    scenario_id,
                    str(record["variable"]),
                    condition,
                    _store_scalar(record.get("prediction")),
                    _store_scalar(record.get("explanation")),
                    self._prediction_parse_status(record),
                    attempt,
                    _json_dumps(extra) if extra else None,
                )
            )

        self._executemany_responses(run_id, response_rows.values())
        self._executemany_predictions(prediction_rows)
        return len(prediction_rows)

    def _response_record_from_csv(
        self, record: dict[str, Any], model: str, scenario_id: str, attempt: int
    ) -> dict[str, Any]:
        usage = {
            field: _store_scalar(record.get(field))
            for field in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "reasoning_tokens",
                "cached_prompt_tokens",
            )
            if field in record
        }
        usage = {k: v for k, v in usage.items() if v is not None}
        return {
            "model": model,
            "scenario_id": scenario_id,
            "attempt": attempt,
            "status": self._response_status_from_csv(record),
            "call_id": _store_scalar(record.get("call_id") or f"{model}:{scenario_id}"),
            "raw_response": _store_scalar(record.get("raw_response")),
            "error": _store_scalar(record.get("error")),
            "usage_json": _json_dumps(usage) if usage else None,
            "cost_usd": _store_scalar(record.get("total_cost_usd")),
            "latency_s": _store_scalar(record.get("elapsed_seconds")),
            "provider_response_id": _store_scalar(record.get("provider_response_id")),
            "provider_system_fingerprint": _store_scalar(
                record.get("provider_system_fingerprint")
            ),
            "provider_resolved_model": _store_scalar(
                record.get("provider_resolved_model")
            ),
            # Keep the apportioned per-variable cost columns for byte-identical
            # export. They are duplicated on every prediction row in the CSV.
            "_csv": {
                col: _store_scalar(record.get(col))
                for col in _RESPONSE_COLUMNS
                if col in record
            },
        }

    @staticmethod
    def _response_status_from_csv(record: dict[str, Any]) -> str:
        from policybench.eval_no_tools import is_infrastructure_error_text

        error = record.get("error")
        if not _is_missing(error) and is_infrastructure_error_text(str(error)):
            return "llm_error"
        # A response with no parsed prediction at all is a parse failure.
        if _is_missing(record.get("prediction")) and _is_missing(
            record.get("raw_response")
        ):
            return "llm_error"
        return "ok"

    @staticmethod
    def _prediction_parse_status(record: dict[str, Any]) -> str:
        if not _is_missing(record.get("prediction")):
            return "ok"
        from policybench.eval_no_tools import is_infrastructure_error_text

        error = record.get("error")
        if not _is_missing(error) and is_infrastructure_error_text(str(error)):
            return "error"
        return "missing"

    def _executemany_responses(
        self, run_id: str, records: Iterable[dict[str, Any]]
    ) -> None:
        rows = []
        for r in records:
            usage_json = r.get("usage_json")
            csv_blob = r.get("_csv")
            # Stash the apportioned CSV response columns inside usage_json under a
            # reserved key so export can reproduce them exactly without widening
            # the schema. usage_json stays valid JSON.
            usage_obj: dict[str, Any] = {}
            if usage_json:
                usage_obj = json.loads(usage_json)
            if csv_blob:
                usage_obj["_csv"] = csv_blob
            rows.append(
                (
                    run_id,
                    r["model"],
                    r["scenario_id"],
                    int(r["attempt"]),
                    r["status"],
                    r.get("call_id"),
                    r.get("raw_response"),
                    r.get("error"),
                    _json_dumps(usage_obj) if usage_obj else None,
                    r.get("cost_usd"),
                    r.get("latency_s"),
                    r.get("provider_response_id"),
                    r.get("provider_system_fingerprint"),
                    r.get("provider_resolved_model"),
                    _utcnow(),
                )
            )
        self._conn.executemany(
            """
            INSERT INTO responses (
                run_id, model, scenario_id, attempt, status, call_id,
                raw_response, error, usage_json, cost_usd, latency_s,
                provider_response_id, provider_system_fingerprint,
                provider_resolved_model, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, model, scenario_id, attempt) DO UPDATE SET
                status=excluded.status,
                call_id=excluded.call_id,
                raw_response=excluded.raw_response,
                error=excluded.error,
                usage_json=excluded.usage_json,
                cost_usd=excluded.cost_usd,
                latency_s=excluded.latency_s,
                provider_response_id=excluded.provider_response_id,
                provider_system_fingerprint=excluded.provider_system_fingerprint,
                provider_resolved_model=excluded.provider_resolved_model,
                created_at=excluded.created_at
            """,
            rows,
        )
        self._conn.commit()

    def _executemany_predictions(self, rows: Sequence[tuple]) -> None:
        if not rows:
            return
        self._conn.executemany(
            """
            INSERT INTO predictions (
                run_id, model, scenario_id, output_id, condition,
                prediction, explanation, parse_status, source_attempt, extra_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, model, scenario_id, output_id) DO UPDATE SET
                condition=excluded.condition,
                prediction=excluded.prediction,
                explanation=excluded.explanation,
                parse_status=excluded.parse_status,
                source_attempt=excluded.source_attempt,
                extra_json=excluded.extra_json
            """,
            rows,
        )
        self._conn.commit()

    def _condition_for(self, run_id: str) -> str | None:
        run = self.get_run(run_id)
        return run["condition"] if run else None

    # -- resume ------------------------------------------------------------

    def missing_cases(
        self,
        run_id: str,
        models: Iterable[str],
        scenario_ids: Iterable[str],
        output_ids: Iterable[str],
    ) -> list[tuple[str, str, str]]:
        """Return the resume set: expected cases with no usable prediction.

        A case ``(model, scenario_id, output_id)`` is *satisfied* when a
        prediction row exists with a non-NULL ``prediction`` and a
        ``parse_status`` that is not ``replaced``/``error`` (i.e. a live, parsed
        value). Everything else in the expected cartesian product is returned, so
        the caller can re-run exactly those cases. Result is sorted for
        determinism.

        The expected sets are passed explicitly (per the resume contract). To
        build them from the run's stored manifest, see
        :meth:`expected_cases_from_manifest`.
        """
        models = list(dict.fromkeys(str(m) for m in models))
        scenario_ids = list(dict.fromkeys(str(s) for s in scenario_ids))
        output_ids = list(dict.fromkeys(str(o) for o in output_ids))

        satisfied = self._satisfied_cases(run_id)

        missing = []
        for model in models:
            for scenario_id in scenario_ids:
                for output_id in output_ids:
                    if (model, scenario_id, output_id) not in satisfied:
                        missing.append((model, scenario_id, output_id))
        missing.sort()
        return missing

    def _satisfied_cases(self, run_id: str) -> set[tuple[str, str, str]]:
        rows = self._conn.execute(
            """
            SELECT model, scenario_id, output_id
            FROM predictions
            WHERE run_id = ?
              AND prediction IS NOT NULL
              AND (parse_status IS NULL OR parse_status NOT IN ('replaced', 'error'))
            """,
            (run_id,),
        ).fetchall()
        return {(r["model"], r["scenario_id"], r["output_id"]) for r in rows}

    def missing_responses(
        self,
        run_id: str,
        models: Iterable[str],
        scenario_ids: Iterable[str],
        output_ids_by_scenario: dict[str, Iterable[str]] | None = None,
        output_ids: Iterable[str] | None = None,
    ) -> list[tuple[str, str]]:
        """Return incomplete ``(model, scenario_id)`` responses.

        Mirrors the response-level resume in
        :func:`policybench.eval_no_tools._load_existing_rows`: a response is
        complete when it has a live parsed prediction for every expected output
        id for that scenario. Supply ``output_ids_by_scenario`` for the precise,
        scenario-dependent expansion (some outputs expand per person), or a flat
        ``output_ids`` set applied to every scenario.
        """
        models = list(dict.fromkeys(str(m) for m in models))
        scenario_ids = list(dict.fromkeys(str(s) for s in scenario_ids))
        satisfied = self._satisfied_cases(run_id)

        incomplete = []
        for model in models:
            for scenario_id in scenario_ids:
                if output_ids_by_scenario is not None:
                    expected = output_ids_by_scenario.get(scenario_id, [])
                elif output_ids is not None:
                    expected = output_ids
                else:
                    raise ValueError("Provide output_ids_by_scenario or output_ids.")
                expected_set = {str(o) for o in expected}
                have = {o for (m, s, o) in satisfied if m == model and s == scenario_id}
                if not expected_set.issubset(have):
                    incomplete.append((model, scenario_id))
        incomplete.sort()
        return incomplete

    def expected_cases_from_manifest(
        self, run_id: str
    ) -> tuple[list[str], list[str], list[str]]:
        """Best-effort (models, scenario_ids, output_ids) from stored metadata.

        Reads ``runs.model_set_json`` and ``runs.output_set_json`` plus the
        distinct scenario ids already seen in predictions. Returns flat lists;
        callers needing per-scenario output expansion should pass their own.
        """
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        model_set = json.loads(run["model_set_json"]) if run["model_set_json"] else []
        if isinstance(model_set, dict):
            models = list(model_set.keys())
        else:
            models = list(model_set)
        output_set = (
            json.loads(run["output_set_json"]) if run["output_set_json"] else []
        )
        if isinstance(output_set, dict):
            # output_set may be the CSV schema; fall back to distinct output ids.
            outputs = output_set.get("outputs", [])
        else:
            outputs = list(output_set)
        scenarios = [
            r["scenario_id"]
            for r in self._conn.execute(
                "SELECT DISTINCT scenario_id FROM predictions WHERE run_id = ? "
                "ORDER BY scenario_id",
                (run_id,),
            ).fetchall()
        ]
        return models, scenarios, list(outputs)

    def observed_outputs_by_scenario(self, run_id: str) -> dict[str, set[str]]:
        """Map each scenario to the output ids any model produced for it.

        This is the de-facto expected output set per scenario, accounting for
        person-level outputs that expand differently across scenarios (e.g. a
        two-child scenario has ``child2_*`` outputs that a childless one does
        not). Used by :meth:`missing_cases_observed` and the status report so the
        missing count is not inflated by structurally-impossible combinations.
        """
        mapping: dict[str, set[str]] = {}
        for r in self._conn.execute(
            "SELECT DISTINCT scenario_id, output_id FROM predictions WHERE run_id = ?",
            (run_id,),
        ).fetchall():
            mapping.setdefault(r["scenario_id"], set()).add(r["output_id"])
        return mapping

    def missing_cases_observed(self, run_id: str) -> list[tuple[str, str, str]]:
        """Resume set using the per-scenario observed output set.

        Equivalent to :meth:`missing_cases` but the expected outputs for each
        scenario are those observed across all models for that scenario, and the
        models are those seen in the run. Use this when you do not have the
        original manifest's scenario-dependent output expansion on hand.
        """
        models = [
            r["model"]
            for r in self._conn.execute(
                "SELECT DISTINCT model FROM predictions WHERE run_id = ? "
                "ORDER BY model",
                (run_id,),
            ).fetchall()
        ]
        outputs_by_scenario = self.observed_outputs_by_scenario(run_id)
        satisfied = self._satisfied_cases(run_id)
        missing = []
        for model in models:
            for scenario_id in sorted(outputs_by_scenario):
                for output_id in sorted(outputs_by_scenario[scenario_id]):
                    if (model, scenario_id, output_id) not in satisfied:
                        missing.append((model, scenario_id, output_id))
        missing.sort()
        return missing

    # -- status ------------------------------------------------------------

    def status_counts(self, run_id: str) -> dict[str, Any]:
        """Return counts by model x response-status and by prediction parse-status."""
        response_counts = [
            dict(r)
            for r in self._conn.execute(
                """
                SELECT model, status, COUNT(*) AS n
                FROM responses WHERE run_id = ?
                GROUP BY model, status ORDER BY model, status
                """,
                (run_id,),
            ).fetchall()
        ]
        prediction_counts = [
            dict(r)
            for r in self._conn.execute(
                """
                SELECT model, parse_status, COUNT(*) AS n
                FROM predictions WHERE run_id = ?
                GROUP BY model, parse_status ORDER BY model, parse_status
                """,
                (run_id,),
            ).fetchall()
        ]
        totals = dict(
            self._conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM responses WHERE run_id = :r) AS responses,
                    (SELECT COUNT(*) FROM predictions WHERE run_id = :r) AS predictions,
                    (SELECT COUNT(*) FROM predictions
                        WHERE run_id = :r AND prediction IS NOT NULL
                        AND (parse_status IS NULL
                             OR parse_status NOT IN ('replaced','error')))
                        AS live_predictions
                """,
                {"r": run_id},
            ).fetchone()
        )
        return {
            "run_id": run_id,
            "totals": totals,
            "responses_by_model_status": response_counts,
            "predictions_by_model_parse_status": prediction_counts,
        }

    # -- import / export ---------------------------------------------------

    def import_run_csv(
        self,
        path: str | Path,
        *,
        meta: dict[str, Any] | None = None,
        run_id: str | None = None,
        country: str | None = None,
        condition: str | None = None,
        scenario_manifest_sha256: str | None = None,
    ) -> str:
        """Import a ``predictions.csv`` / ``.csv.gz`` into the store.

        The CSV schema (ordered columns + emit-dtypes) and the distinct output
        ids are recorded on the run so :meth:`export_predictions_csv` can
        reproduce the original bytes for a clean run. ``meta`` is merged into
        ``runs.meta_json``. Returns the resolved ``run_id``.
        """
        path = Path(path)
        frame = _read_predictions_dataframe(path)

        resolved_run_id = run_id
        if resolved_run_id is None and _RUN_ID_COLUMN in frame.columns:
            unique = sorted(
                {
                    str(_store_scalar(v))
                    for v in frame[_RUN_ID_COLUMN]
                    if not _is_missing(v)
                }
            )
            if len(unique) == 1:
                resolved_run_id = unique[0]
        if resolved_run_id is None:
            resolved_run_id = path.parent.name or path.stem

        schema = _csv_schema(frame)
        outputs = sorted(frame["variable"].astype(str).unique().tolist())
        models = sorted(frame["model"].astype(str).unique().tolist())

        run_meta = dict(meta or {})
        run_meta["csv_schema"] = schema
        run_meta["source_csv"] = str(path)
        run_meta["source_csv_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        # Capture the exact original row order so export reproduces the file
        # byte-for-byte. The (model, scenario_id, variable) tuple is the
        # predictions primary key and is unique across the file.
        run_meta["row_order"] = [
            [str(m), str(s), str(v)]
            for m, s, v in zip(frame["model"], frame["scenario_id"], frame["variable"])
        ]

        output_set = {"schema": schema, "outputs": outputs}

        self.create_run(
            resolved_run_id,
            country=country,
            condition=condition,
            scenario_manifest_sha256=scenario_manifest_sha256,
            model_set=models,
            output_set=output_set,
            meta=run_meta,
        )
        self.upsert_predictions(frame, run_id=resolved_run_id)
        return resolved_run_id

    def export_predictions_csv(
        self, run_id: str, path: str | Path, *, compress: bool | None = None
    ) -> Path:
        """Export a run's predictions as a CSV that re-imports byte-identically.

        For a clean run (imported via :meth:`import_run_csv`, no partial retries)
        the bytes equal the original ``to_csv(index=False)`` output. We rebuild
        the DataFrame by joining live predictions back to their response columns,
        restore the recorded column order and emit-dtypes, and emit with the same
        pandas call the repo uses.
        """
        path = Path(path)
        frame = self.build_predictions_frame(run_id)

        if compress is None:
            compress = path.name.endswith(".gz")
        path.parent.mkdir(parents=True, exist_ok=True)
        csv_text = frame.to_csv(index=False)
        if compress:
            with gzip.open(path, "wt", newline="") as handle:
                handle.write(csv_text)
        else:
            path.write_text(csv_text)
        return path

    def build_predictions_frame(self, run_id: str) -> pd.DataFrame:
        """Reconstruct the CSV-shaped DataFrame for a run (live rows only)."""
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        schema = self._schema_for(run)
        columns = schema["columns"]
        dtypes = schema["dtypes"]

        # Pull live predictions (drop superseded rows).
        pred_rows = self._conn.execute(
            """
            SELECT model, scenario_id, output_id AS variable,
                   prediction, explanation, source_attempt, extra_json
            FROM predictions
            WHERE run_id = ? AND (parse_status IS NULL OR parse_status != 'replaced')
            """,
            (run_id,),
        ).fetchall()

        # Pull live responses keyed by (model, scenario_id, attempt).
        resp_index: dict[tuple[str, str, int], dict[str, Any]] = {}
        for r in self._conn.execute(
            """
            SELECT model, scenario_id, attempt, call_id, raw_response, error,
                   usage_json, cost_usd, latency_s, provider_response_id,
                   provider_system_fingerprint, provider_resolved_model
            FROM responses
            WHERE run_id = ? AND status != 'replaced'
            """,
            (run_id,),
        ).fetchall():
            resp_index[(r["model"], r["scenario_id"], int(r["attempt"]))] = dict(r)

        records = []
        for pr in pred_rows:
            attempt = int(pr["source_attempt"] or 0)
            key = (pr["model"], pr["scenario_id"], attempt)
            response = resp_index.get(key) or self._fallback_response(
                run_id, pr["model"], pr["scenario_id"]
            )
            record = self._csv_record(pr, response, run_id, columns)
            records.append(record)

        frame = pd.DataFrame.from_records(records, columns=columns)
        frame = self._restore_dtypes(frame, dtypes)
        frame = self._sort_like_source(frame, run)
        return frame

    def _fallback_response(
        self, run_id: str, model: str, scenario_id: str
    ) -> dict[str, Any]:
        row = self._conn.execute(
            """
            SELECT model, scenario_id, attempt, call_id, raw_response, error,
                   usage_json, cost_usd, latency_s, provider_response_id,
                   provider_system_fingerprint, provider_resolved_model
            FROM responses
            WHERE run_id = ? AND model = ? AND scenario_id = ? AND status != 'replaced'
            ORDER BY attempt DESC LIMIT 1
            """,
            (run_id, model, scenario_id),
        ).fetchone()
        return dict(row) if row is not None else {}

    def _csv_record(
        self,
        pred: sqlite3.Row,
        response: dict[str, Any],
        run_id: str,
        columns: Sequence[str],
    ) -> dict[str, Any]:
        usage_obj: dict[str, Any] = {}
        if response.get("usage_json"):
            usage_obj = json.loads(response["usage_json"])
        csv_blob = usage_obj.get("_csv", {}) if isinstance(usage_obj, dict) else {}

        extra = {}
        if pred["extra_json"]:
            extra = json.loads(pred["extra_json"])

        record: dict[str, Any] = {}
        for col in columns:
            if col == _RUN_ID_COLUMN:
                record[col] = run_id
            elif col == "model":
                record[col] = pred["model"]
            elif col == "scenario_id":
                record[col] = pred["scenario_id"]
            elif col == "variable":
                record[col] = pred["variable"]
            elif col == "prediction":
                record[col] = pred["prediction"]
            elif col == "explanation":
                record[col] = pred["explanation"]
            elif col in _RESPONSE_COLUMNS:
                # Prefer the exact per-variable apportioned CSV value if stored.
                if col in csv_blob:
                    record[col] = csv_blob[col]
                else:
                    record[col] = self._response_column_value(col, response)
            elif col in extra:
                record[col] = extra[col]
            else:
                record[col] = None
        return record

    @staticmethod
    def _response_column_value(col: str, response: dict[str, Any]) -> Any:
        mapping = {
            "call_id": "call_id",
            "raw_response": "raw_response",
            "error": "error",
            "elapsed_seconds": "latency_s",
            "total_cost_usd": "cost_usd",
            "provider_response_id": "provider_response_id",
            "provider_system_fingerprint": "provider_system_fingerprint",
            "provider_resolved_model": "provider_resolved_model",
        }
        if col in mapping:
            return response.get(mapping[col])
        usage = {}
        if response.get("usage_json"):
            usage = json.loads(response["usage_json"])
        return usage.get(col)

    @staticmethod
    def _restore_dtypes(frame: pd.DataFrame, dtypes: dict[str, str]) -> pd.DataFrame:
        for col in frame.columns:
            emit = dtypes.get(col, "object")
            frame[col] = _coerce_column(frame[col], emit)
        return frame

    def _sort_like_source(
        self, frame: pd.DataFrame, run: dict[str, Any]
    ) -> pd.DataFrame:
        """Restore the original row order recorded at import time, if available."""
        meta = json.loads(run["meta_json"]) if run["meta_json"] else {}
        order = meta.get("row_order")
        if order:
            order_index = {tuple(k): i for i, k in enumerate(order)}
            keys = list(zip(frame["model"], frame["scenario_id"], frame["variable"]))
            frame = frame.assign(_ord=[order_index.get(k, len(order)) for k in keys])
            frame = frame.sort_values("_ord", kind="stable").drop(columns="_ord")
        return frame.reset_index(drop=True)

    @staticmethod
    def _schema_for(run: dict[str, Any]) -> dict[str, Any]:
        meta = json.loads(run["meta_json"]) if run["meta_json"] else {}
        schema = meta.get("csv_schema")
        if schema:
            return schema
        output_set = (
            json.loads(run["output_set_json"]) if run["output_set_json"] else {}
        )
        if isinstance(output_set, dict) and "schema" in output_set:
            return output_set["schema"]
        raise ValueError(
            f"Run {run['run_id']!r} has no recorded CSV schema; it was not "
            "imported from a predictions CSV."
        )


# ---------------------------------------------------------------------------
# Module-level convenience API (matches the requested function surface)
# ---------------------------------------------------------------------------


def open_store(path: str | Path) -> RunStore:
    """Open (creating if needed) a :class:`RunStore` at ``path``."""
    return RunStore(path)


def create_run(db_path: str | Path, run_id: str, **kwargs: Any) -> str:
    """Create a run in the database at ``db_path``. See :meth:`RunStore.create_run`."""
    with RunStore(db_path) as store:
        return store.create_run(run_id, **kwargs)


def import_run_csv(db_path: str | Path, csv_path: str | Path, **kwargs: Any) -> str:
    """Import a predictions CSV into the database at ``db_path``."""
    with RunStore(db_path) as store:
        return store.import_run_csv(csv_path, **kwargs)


def export_predictions_csv(
    db_path: str | Path, run_id: str, out_path: str | Path, **kwargs: Any
) -> Path:
    """Export a run's predictions from the database at ``db_path``."""
    with RunStore(db_path) as store:
        return store.export_predictions_csv(run_id, out_path, **kwargs)


def import_run_dir(
    run_dir: str | Path,
    db_path: str | Path | None = None,
    **kwargs: Any,
) -> tuple[str, Path]:
    """Import a run *directory* (``predictions.csv[.gz]`` + sidecar meta).

    Looks for ``predictions.csv.gz`` then ``predictions.csv`` in ``run_dir``,
    reads the scenario manifest sidecar for ``country``/manifest hash if present,
    and writes to ``<run_dir>/run.db`` unless ``db_path`` is given. Returns
    ``(run_id, db_path)``.
    """
    run_dir = Path(run_dir)
    csv_path = None
    for candidate in ("predictions.csv.gz", "predictions.csv"):
        if (run_dir / candidate).exists():
            csv_path = run_dir / candidate
            break
    if csv_path is None:
        raise FileNotFoundError(f"No predictions.csv[.gz] found in {run_dir}")

    db_path = Path(db_path) if db_path is not None else run_dir / DEFAULT_DB_NAME

    country = kwargs.pop("country", None)
    manifest_sha = kwargs.pop("scenario_manifest_sha256", None)
    meta = dict(kwargs.pop("meta", {}) or {})

    scenario_meta_path = run_dir / "scenarios.csv.meta.json"
    if scenario_meta_path.exists():
        sidecar = json.loads(scenario_meta_path.read_text())
        country = country or sidecar.get("country")
        meta.setdefault("scenario_manifest_meta", sidecar)
    scenario_manifest = run_dir / "scenarios.csv"
    if manifest_sha is None and scenario_manifest.exists():
        manifest_sha = hashlib.sha256(scenario_manifest.read_bytes()).hexdigest()

    with RunStore(db_path) as store:
        run_id = store.import_run_csv(
            csv_path,
            country=country,
            scenario_manifest_sha256=manifest_sha,
            meta=meta,
            **kwargs,
        )
    return run_id, db_path


# ---------------------------------------------------------------------------
# CLI wiring
#
# Kept here so cli.py needs only a one-line import plus a subparser registration
# and a single dispatch branch, leaving the rest of cli.py untouched for the
# parallel PRs editing it.
# ---------------------------------------------------------------------------


def add_runstore_subparser(subparsers: Any) -> None:
    """Register the ``runstore`` subcommand on an argparse subparsers object."""
    runstore_parser = subparsers.add_parser(
        "runstore",
        help="Additive SQLite run store (import/export/status).",
    )
    runstore_sub = runstore_parser.add_subparsers(dest="runstore_command")

    import_parser = runstore_sub.add_parser(
        "import", help="Import a run directory's predictions.csv into a SQLite db."
    )
    import_parser.add_argument(
        "--run-dir",
        required=True,
        help="Run directory containing predictions.csv[.gz] (and sidecars).",
    )
    import_parser.add_argument(
        "--db",
        default=None,
        help=f"Output SQLite path (default: <run-dir>/{DEFAULT_DB_NAME}).",
    )
    import_parser.add_argument(
        "--run-id",
        default=None,
        help="Run id to assign (default: inferred from CSV or run-dir name).",
    )

    export_parser = runstore_sub.add_parser(
        "export", help="Export a run's predictions back to CSV (byte-identical)."
    )
    export_parser.add_argument("--db", required=True, help="SQLite db path.")
    export_parser.add_argument("--run-id", required=True, help="Run id to export.")
    export_parser.add_argument(
        "-o", "--output", required=True, help="Destination CSV (.gz to compress)."
    )

    status_parser = runstore_sub.add_parser(
        "status", help="Show counts by model/status and the missing-case count."
    )
    status_parser.add_argument("--db", required=True, help="SQLite db path.")
    status_parser.add_argument(
        "--run-id",
        default=None,
        help="Run id (default: the only run, if the db holds exactly one).",
    )


def run_runstore_command(args: Any) -> None:
    """Dispatch a parsed ``runstore`` subcommand."""
    command = getattr(args, "runstore_command", None)
    if command == "import":
        run_id, db_path = import_run_dir(
            args.run_dir, db_path=args.db, run_id=args.run_id
        )
        with RunStore(db_path) as store:
            counts = store.status_counts(run_id)
        totals = counts["totals"]
        print(f"Imported run {run_id!r} into {db_path}")
        print(
            f"  responses={totals['responses']} "
            f"predictions={totals['predictions']} "
            f"live={totals['live_predictions']}"
        )
        return

    if command == "export":
        out = export_predictions_csv(args.db, args.run_id, args.output)
        print(f"Exported run {args.run_id!r} to {out}")
        return

    if command == "status":
        with RunStore(args.db) as store:
            run_id = args.run_id
            if run_id is None:
                runs = store.list_runs()
                if len(runs) != 1:
                    raise SystemExit(
                        f"Specify --run-id (db holds {len(runs)} runs: {runs})."
                    )
                run_id = runs[0]
            counts = store.status_counts(run_id)
            run = store.get_run(run_id) or {}
            models, scenarios, _ = store.expected_cases_from_manifest(run_id)
            missing = store.missing_cases_observed(run_id)

        totals = counts["totals"]
        print(f"Run: {run_id}")
        if run.get("country"):
            print(f"Country: {run['country']}")
        print(
            f"Totals: responses={totals['responses']} "
            f"predictions={totals['predictions']} "
            f"live={totals['live_predictions']}"
        )
        print("\nResponses by model x status:")
        for row in counts["responses_by_model_status"]:
            print(f"  {row['model']:32} {row['status']:12} {row['n']}")
        print("\nPredictions by model x parse_status:")
        for row in counts["predictions_by_model_parse_status"]:
            status = row["parse_status"] or "(none)"
            print(f"  {row['model']:32} {status:12} {row['n']}")
        print(
            f"\nMissing cases ({len(models)} models x {len(scenarios)} scenarios, "
            f"per-scenario observed outputs): {len(missing)}"
        )
        return

    raise SystemExit(
        "Usage: policybench runstore {import|export|status} ... (see --help)."
    )
