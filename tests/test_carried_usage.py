"""Fable 5's carried usage: the export reports none of it, the carry restores it.

Claude Fable 5's frozen board rows record no cost, token or latency fields.
So analysis.model_cost_latency computes none of its usage, and
export_full_run reports none (it reported a $0 cost before
model_cost_latency stopped pricing unrecorded tokens). Every release driver
carries the four published fields from its base release (CARRIED_USAGE). It
then gates on serialized bytes, so key order counts as well as values.

Invariants:
- every driver carries the same four fields, in one order;
- the published Fable 5 row ends with those four fields in that order, so
  assigning them to an exported row that lacks them reproduces the published
  key order;
- release_20261006.export_payload's carry restores the published row byte
  for byte whether the export omits Fable 5's usage or reports a $0 cost, and
  it touches no other model;
- (slow, local) the committed snapshot's payload rebuilds byte for byte from
  its committed inputs through export_full_run and that carry.
"""

from __future__ import annotations

import gzip
import importlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_20261006 as release  # noqa: E402

from policybench.snapshot_payload import (  # noqa: E402
    read_run_payload,
    read_run_payload_text,
)

FABLE = "claude-fable-5"
CARRIED = ("costUsd", "costPerHousehold", "totalTokens", "latencySeconds")
FROZEN = ROOT / release.SNAPSHOT_RUN
DRIVERS = (
    "release_20261006",
    "release_20261013b",
    "finish_gpt61sol",
    "finish_haiku55",
    "finish_musewonder",
    "finish_argon",
)


@pytest.mark.parametrize("name", DRIVERS)
def test_every_driver_carries_fable_5s_four_fields_in_one_order(name):
    assert importlib.import_module(name).CARRIED_USAGE == {FABLE: CARRIED}


def test_the_published_fable_5_row_ends_with_the_carried_fields():
    """The precondition for the carry to reproduce the published bytes when
    the export reports none of Fable 5's usage."""
    rows = read_run_payload(FROZEN)["modelStats"]
    fable = next(row for row in rows if row["model"] == FABLE)
    assert tuple(fable)[-len(CARRIED) :] == CARRIED
    assert all(fable[key] > 0 for key in CARRIED)


STAT_KEYS = ("condition", "score", "exact", "n", "accuracy", "aggregateScore")


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    leading=st.lists(st.sampled_from(STAT_KEYS), unique=True),
    usage=st.tuples(
        st.floats(min_value=0.01, max_value=1e4),
        st.floats(min_value=1e-4, max_value=100),
        st.integers(min_value=1, max_value=10**9),
        st.floats(min_value=0.5, max_value=3600),
    ),
    exporter=st.sampled_from(["omits", "zero"]),
)
def test_the_carry_restores_the_published_row_whichever_way_the_export_reports_it(
    monkeypatch, leading, usage, exporter
):
    """release_20261006.export_payload's carry, run on a stubbed export: the
    carried Fable 5 row serializes as the published one, and the other model's
    row is the export's."""
    import policybench.dashboard_schema
    import policybench.full_run_export

    published = {"model": FABLE, **{key: 1.5 for key in leading}}
    published.update(zip(CARRIED, usage))
    exported_fable = {"model": FABLE, **{key: 1.5 for key in leading}}
    if exporter == "zero":
        exported_fable.update(costUsd=0.0, costPerHousehold=0.0)
    other = {"model": "other", "exact": 50.0, "costUsd": 0.0, "costPerHousehold": 0.0}
    base = {"countries": {"us": {"modelStats": [published, dict(other)]}}}
    export = {"countries": {"us": {"modelStats": [exported_fable, dict(other)]}}}
    monkeypatch.setattr(
        policybench.full_run_export, "export_full_run", lambda *a, **k: export
    )
    monkeypatch.setattr(
        policybench.dashboard_schema, "validate_dashboard_payload", lambda *a, **k: []
    )
    with tempfile.TemporaryDirectory() as scratch:
        bundle = Path(scratch) / "bundle"
        for rel in release.EXPORT_INPUTS:
            (bundle / rel).parent.mkdir(parents=True, exist_ok=True)
            (bundle / rel).write_bytes(b"")
        payload = release.export_payload(bundle, base)
    fable, rest = payload["countries"]["us"]["modelStats"]
    assert json.dumps(fable) == json.dumps(published)
    assert json.dumps(rest) == json.dumps(other)


@pytest.mark.slow
def test_the_committed_payload_rebuilds_through_export_and_the_carry(monkeypatch):
    """Local only, about a minute: export_full_run on the committed snapshot's
    inputs reports none of Fable 5's usage, and with release_20261006's carry
    the US payload is the committed one byte for byte."""
    from policybench.full_run_export import export_full_run

    monkeypatch.chdir(ROOT)
    committed = read_run_payload_text(FROZEN)
    base = {"countries": {"us": json.loads(committed)}}
    with tempfile.TemporaryDirectory() as scratch:
        bundle = Path(scratch) / release.RUN
        (bundle / "us").mkdir(parents=True)
        (bundle / "annotations").mkdir()
        for name in (*release.REFERENCE_FILES, release.EXCLUSIONS):
            shutil.copyfile(FROZEN / name, bundle / "us" / name)
        with gzip.open(FROZEN / "predictions.csv.gz", "rb") as source:
            (bundle / "us" / "predictions.csv").write_bytes(source.read())
        for name in release.ANNOTATION_CSVS:
            shutil.copyfile(
                ROOT / release.ANNOTATIONS / name, bundle / "annotations" / name
            )
        raw = export_full_run(bundle, countries=["us"], skip_app_data=True)
        payload = release.export_payload(bundle, base)
    raw_fable = next(
        row for row in raw["countries"]["us"]["modelStats"] if row["model"] == FABLE
    )
    assert not set(CARRIED) & set(raw_fable)
    assert json.dumps(payload["countries"]["us"], allow_nan=False) == committed
