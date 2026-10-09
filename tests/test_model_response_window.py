"""The snapshot's model response window ends on the last answer it records.

Release dashboard-data-20260930 dated the window's end by its tag: the drivers
set ``2026-06-12 to <release date>``. GPT-6.1 Sol, the last model on that
board, finished answering at 2026-09-29 22:36 UTC and no model answered on
September 30. ``freeze_snapshot.model_response_window`` now dates the end from
the predictions' latest ``request_completed_at``, and the freeze refuses a
configured window that disagrees.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import freeze_snapshot as freezer  # noqa: E402

START = "2026-06-12"


def utc(*parts: int) -> float:
    return datetime(*parts, tzinfo=timezone.utc).timestamp()


# Release 20260930's last answer (GPT-6.1 Sol) and release 20260929's (Grok
# 4.7), as the frozen predictions record them.
LAST_ANSWER_20260930 = utc(2026, 9, 29, 22, 36, 32, 205154)
LAST_ANSWER_20260929 = utc(2026, 9, 29, 1, 26, 43, 931609)


def write_predictions(path: Path, rows: list[tuple]) -> Path:
    """A predictions file whose rows are (request_started_at,
    request_completed_at) pairs; None is a row without timestamps, as the
    first waves' and the batch adapter's rows are."""
    frame = pd.DataFrame(
        rows, columns=["request_started_at", "request_completed_at"], dtype="float64"
    )
    frame.insert(0, "model", "model")
    frame.to_csv(path, index=False)
    return path


def test_the_window_ends_on_the_last_answer_not_the_release_date(tmp_path):
    """The mismatch release 20260930 published: its freeze configured
    "2026-06-12 to 2026-09-30" from the tag, while the last answer is
    September 29's. The derived window ends on the 29th, and the configured
    one is refused."""
    predictions = write_predictions(
        tmp_path / "predictions.csv",
        [(None, None), (LAST_ANSWER_20260930 - 3_600, LAST_ANSWER_20260930)],
    )
    window = freezer.model_response_window(predictions, START)
    assert window == "2026-06-12 to 2026-09-29"
    released = "2026-06-12 to 2026-09-30"
    with pytest.raises(
        SystemExit,
        match=r"\(2026-06-12 to 2026-09-30\) is not the predictions' "
        r"\(2026-06-12 to 2026-09-29\)",
    ):
        freezer.model_response_window(predictions, START, released)
    # A configured window that names the last answer passes.
    assert freezer.model_response_window(predictions, START, window) == window


def test_rows_without_timestamps_cannot_move_the_end(tmp_path):
    """The first waves predate the timestamp columns; their blank rows leave
    the end on the last timed answer."""
    rows = [(None, None)] * 5 + [(utc(2026, 7, 2, 7, 50), utc(2026, 7, 2, 8, 40))]
    predictions = write_predictions(tmp_path / "predictions.csv", rows)
    assert freezer.model_response_window(predictions, START) == (
        "2026-06-12 to 2026-07-02"
    )


def test_predictions_that_time_no_answer_are_refused(tmp_path):
    predictions = write_predictions(tmp_path / "predictions.csv", [(None, None)])
    with pytest.raises(SystemExit, match="times no answer"):
        freezer.model_response_window(predictions, START)
    untimed = tmp_path / "untimed.csv"
    pd.DataFrame({"model": ["model"], "prediction": [1.0]}).to_csv(untimed)
    with pytest.raises(SystemExit, match="no request_completed_at, request_started"):
        freezer.model_response_window(untimed, START)


def test_a_start_after_the_first_timed_request_is_refused(tmp_path):
    """The start is configured, but the recorded requests bound it: a request
    on July 2 cannot sit in a window that opens on July 3."""
    predictions = write_predictions(
        tmp_path / "predictions.csv",
        [(utc(2026, 7, 2, 23, 59, 59), utc(2026, 7, 3, 0, 0, 1))],
    )
    assert freezer.model_response_window(predictions, "2026-07-02") == (
        "2026-07-02 to 2026-07-03"
    )
    with pytest.raises(SystemExit, match="request on 2026-07-02, before"):
        freezer.model_response_window(predictions, "2026-07-03")


def test_a_request_started_after_the_last_answer_is_refused(tmp_path):
    """A request that started after every completion (a row with a start and
    no completion) would sit outside a window that ends on the last answer."""
    predictions = write_predictions(
        tmp_path / "predictions.csv",
        [(utc(2026, 9, 28, 20), utc(2026, 9, 28, 21)), (utc(2026, 9, 30, 1), None)],
    )
    with pytest.raises(SystemExit, match="request on 2026-09-30, after its last"):
        freezer.model_response_window(predictions, START)


def test_the_frozen_gzip_dates_like_the_staged_csv(tmp_path):
    """The freeze dates the staged predictions.csv; the snapshot keeps its
    deterministic gzip, which dates the same."""
    rows = [(None, None), (LAST_ANSWER_20260930 - 60, LAST_ANSWER_20260930)]
    staged = write_predictions(tmp_path / "predictions.csv", rows)
    frozen = tmp_path / "frozen" / "predictions.csv.gz"
    frozen.parent.mkdir()
    freezer.gzip_deterministic(staged, frozen, stored_name="predictions.csv")
    assert freezer.model_response_window(frozen, START) == (
        freezer.model_response_window(staged, START)
    )


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="needs time.tzset")
@pytest.mark.parametrize(
    "zone", ["UTC", "America/New_York", "America/Los_Angeles", "Pacific/Kiritimati"]
)
@pytest.mark.parametrize(
    "last_answer, end",
    [
        # Release 20260929's last answer: September 28 in US time.
        (LAST_ANSWER_20260929, "2026-09-29"),
        # Release 20260901's (Claude Fable 5.1): September 1 in US time.
        (utc(2026, 9, 2, 0, 29, 19), "2026-09-02"),
        (LAST_ANSWER_20260930, "2026-09-29"),
    ],
)
def test_the_end_is_the_utc_date_on_any_machine_clock(tmp_path, zone, last_answer, end):
    predictions = write_predictions(
        tmp_path / "predictions.csv", [(last_answer - 60, last_answer)]
    )
    saved = os.environ.get("TZ")
    os.environ["TZ"] = zone
    time.tzset()
    try:
        window = freezer.model_response_window(predictions, START)
    finally:
        if saved is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = saved
        time.tzset()
    assert window == f"2026-06-12 to {end}"


def test_a_time_just_before_utc_midnight_stays_on_its_day():
    """``datetime.fromtimestamp`` rounds to the microsecond and would carry
    the largest float before midnight into the next day."""
    midnight = utc(2026, 9, 30)
    before = float.__sub__(midnight, 2.5e-7)
    assert before < midnight
    assert freezer._utc_date(before) == date(2026, 9, 29)
    assert freezer._utc_date(midnight) == date(2026, 9, 30)


# --- The freeze --------------------------------------------------------------


@pytest.fixture
def freeze_inputs(tmp_path, monkeypatch):
    """A source run whose predictions end on release 20260930's last answer,
    with every step of freeze_snapshot.main that writes stubbed to record
    that it ran."""
    source = tmp_path / "run"
    (source / "us").mkdir(parents=True)
    write_predictions(
        source / "us" / "predictions.csv",
        [(None, None), (LAST_ANSWER_20260930 - 60, LAST_ANSWER_20260930)],
    )
    for name in ("dashboard.json", "reference_outputs.csv.meta.json"):
        (tmp_path / name).write_text("{}\n")
    monkeypatch.setattr(freezer, "SOURCE_RUN", source)
    monkeypatch.setattr(freezer, "SOURCE_US", source / "us")
    monkeypatch.setattr(
        freezer, "PUBLISHED_DASHBOARD_SOURCE", tmp_path / "dashboard.json"
    )
    monkeypatch.setattr(
        freezer, "REFERENCE_META_SOURCE", tmp_path / "reference_outputs.csv.meta.json"
    )
    monkeypatch.setattr(freezer, "MODEL_RESPONSE_DATE", None)
    ran = []
    for step in (
        "remove_stale_artifacts",
        "freeze_run",
        "freeze_committed_artifacts",
        "freeze_annotations",
    ):
        monkeypatch.setattr(freezer, step, lambda step=step: ran.append(step))

    def build_manifest(run_files, committed, annotation_files, response_window):
        raise RuntimeError(f"manifest window: {response_window}")

    monkeypatch.setattr(freezer, "build_manifest", build_manifest)
    return ran


def test_the_freeze_dates_the_manifest_from_the_predictions(freeze_inputs):
    with pytest.raises(
        RuntimeError, match=r"^manifest window: 2026-06-12 to 2026-09-29$"
    ):
        freezer.main()
    assert freeze_inputs == [
        "remove_stale_artifacts",
        "freeze_run",
        "freeze_committed_artifacts",
        "freeze_annotations",
    ]


def test_the_freeze_refuses_a_release_date_window_before_any_write(
    freeze_inputs, monkeypatch
):
    """What freeze_gpt61sol configured for dashboard-data-20260930."""
    monkeypatch.setattr(freezer, "MODEL_RESPONSE_DATE", "2026-06-12 to 2026-09-30")
    with pytest.raises(SystemExit, match="not the release date"):
        freezer.main()
    assert freeze_inputs == []


def test_a_csv_time_just_before_utc_midnight_stays_on_its_day(tmp_path):
    """End to end through the CSV parser, not only ``_utc_date``: the last
    double before 2027-02-01 00:00 UTC is a January 31 answer. pandas'
    default float parser rounds it up to midnight."""
    import math

    completed = math.nextafter(utc(2027, 2, 1), -math.inf)
    predictions = write_predictions(
        tmp_path / "predictions.csv", [(completed - 60, completed)]
    )
    assert freezer.model_response_window(predictions, START) == (
        "2026-06-12 to 2027-01-31"
    )


def test_the_real_manifest_builder_publishes_the_window_it_is_given(monkeypatch):
    """The stubbed ``build_manifest`` above checks only the argument. Build
    the manifest from the committed snapshot with a window no release has
    used, and require it in ``model_response_date`` and in both notes that
    state the window. The two blocks that read the local audit tree are
    stubbed; nothing is written."""
    monkeypatch.setattr(freezer, "developer_adjudications_block", lambda: {})
    monkeypatch.setattr(freezer, "audit_judge_provenance", lambda: {})
    manifest_path = freezer.SNAPSHOT_DIR / "manifest.json"
    committed = json.loads(manifest_path.read_text())
    run_files = committed["source_run_artifacts"][freezer.RUN_LABEL]["files"]
    window = "2026-06-12 to 2026-07-03"
    manifest = freezer.build_manifest(
        run_files,
        committed["committed_snapshot_artifacts"],
        committed["audit_annotation_artifacts"]["files"],
        window,
    )
    assert manifest["model_response_date"] == window
    notes = " ".join(manifest["reproducibility_notes"])
    assert "June 12 and July 3, 2026" in notes
    assert f"recorded {window} response window" in notes
    for stale in ("September 29", "September 30", "2026-09-29", "2026-09-30"):
        assert stale not in notes, stale


# --- Properties --------------------------------------------------------------

# Requests as the runner records them: microsecond Unix times (time.time()),
# within the board's span, each completing at or after it starts.
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
FIRST_US = int((datetime(2026, 6, 12, tzinfo=timezone.utc) - EPOCH).total_seconds())
LAST_US = int((datetime(2027, 6, 30, tzinfo=timezone.utc) - EPOCH).total_seconds())
REQUEST = st.tuples(
    st.integers(FIRST_US * 1_000_000, LAST_US * 1_000_000),
    st.integers(0, 6 * 3_600 * 1_000_000),
).map(lambda pair: (pair[0], pair[0] + pair[1]))
ROWS = st.lists(st.one_of(st.none(), REQUEST), min_size=1, max_size=40).filter(
    lambda rows: any(rows)
)


def exact_date(microseconds: int) -> date:
    """The UTC date of an integer microsecond time, in exact arithmetic."""
    return (EPOCH + timedelta(microseconds=microseconds)).date()


def window_of(rows: list[tuple[int, int] | None], start: str = START) -> str:
    pairs = [
        (None, None) if row is None else (row[0] / 1e6, row[1] / 1e6) for row in rows
    ]
    with tempfile.TemporaryDirectory() as scratch:
        path = write_predictions(Path(scratch) / "predictions.csv", pairs)
        return freezer.model_response_window(path, start)


@settings(max_examples=150, deadline=None)
@given(ROWS)
def test_the_end_is_the_latest_completion_and_the_window_holds_every_request(rows):
    window = window_of(rows)
    first, end = (date.fromisoformat(part) for part in window.split(" to "))
    timed = [row for row in rows if row is not None]
    assert first == date.fromisoformat(START)
    assert end == exact_date(max(completed for _, completed in timed))
    for started, completed in timed:
        assert first <= exact_date(started) <= exact_date(completed) <= end


@settings(max_examples=75, deadline=None)
@given(ROWS, st.randoms(use_true_random=False))
def test_the_window_ignores_row_order(rows, random):
    shuffled = list(rows)
    random.shuffle(shuffled)
    assert window_of(shuffled) == window_of(rows)


@settings(max_examples=75, deadline=None)
@given(ROWS, REQUEST)
def test_a_later_answer_never_moves_the_end_earlier(rows, extra):
    before = window_of(rows).split(" to ")[1]
    after = window_of([*rows, extra]).split(" to ")[1]
    assert after >= before
    assert after == max(before, exact_date(extra[1]).isoformat())
