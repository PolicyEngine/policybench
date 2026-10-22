"""The household-set builder and the tool pilot's --board path.

The build test runs the real engine on three of the frozen board's own
households, with sampling and the dataset download faked, so the references it
writes must equal the frozen ones on the frozen engine (policyengine-us
2.41.0). It is marked slow.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import household_set as hs  # noqa: E402
import tool_pilot_argon as pilot  # noqa: E402

ON_FROZEN_ENGINE = importlib.metadata.version("policyengine-us") == "2.41.0"
SOL = "gpt-6-sol"


def test_rename_gives_fresh_ids_in_draw_order():
    scenarios = hs.load_scenarios(hs.FROZEN_BOARD)[:3]
    renamed = hs.rename_scenarios(list(reversed(scenarios)), "mc")
    assert [s.id for s in renamed] == ["mc_000", "mc_001", "mc_002"]
    assert renamed[0].state == scenarios[2].state
    assert renamed[0].metadata == scenarios[2].metadata
    assert [s.id for s in scenarios] == ["scenario_000", "scenario_001", "scenario_002"]


@given(st.lists(st.text(min_size=1), unique=True, max_size=60), st.integers(1, 15))
def test_batches_partition_the_draw_in_order(ids, size):
    batches = hs.split_batches(ids, size)
    assert [sid for batch in batches for sid in batch] == ids
    assert all(len(batch) == size for batch in batches[:-1])
    assert all(1 <= len(batch) <= size for batch in batches)


def test_batches_refuse_a_size_below_one():
    with pytest.raises(ValueError):
        hs.split_batches(["a"], 0)


def test_differences_report_missing_and_moved_outputs():
    expected = pd.DataFrame(
        {
            "scenario_id": ["a", "a", "b"],
            "variable": ["x", "y", "x"],
            "value": [1.0, 2.0, 3.0],
        }
    )
    computed = pd.DataFrame(
        {"scenario_id": ["a", "a"], "variable": ["x", "y"], "value": [1.0, 2.5]}
    )
    diff = hs.differences(expected, computed, tolerance=1e-6)
    assert sorted(zip(diff.scenario_id, diff.variable)) == [("a", "y"), ("b", "x")]
    assert hs.differences(expected, computed, tolerance=1.0).scenario_id.tolist() == [
        "b"
    ]


def test_fix_module_pins_are_the_frozen_revision():
    pins = hs.fix_module_pins()
    assert pins == [
        {"module": p["module"], "path": p["path"], "sha256": p["sha256"]}
        for p in hs.frozen_fix_pins()
    ]


def test_the_frozen_board_reads_as_before():
    assert pilot.board_engine() == pilot.REFERENCE_ENGINE
    assert not pilot.is_household_set(pilot.SNAPSHOT)
    assert pilot.board_fix_module_sha256() == pilot.FIX_MODULE_SHA256
    assert pilot.board_path(argparse.Namespace()) == pilot.SNAPSHOT


@pytest.fixture(scope="module")
def household_board(tmp_path_factory):
    """A three-household set built from the frozen board's first households."""
    if not ON_FROZEN_ENGINE:
        pytest.skip("the build test reproduces the 2.41.0 references")
    import policybench.policyengine_runtime as runtime
    import policybench.scenarios as scenarios_module

    root = tmp_path_factory.mktemp("set")
    dataset = root / "populace_us_2024.h5"
    dataset.write_bytes(b"not a real dataset")
    digest = hs.sha256_file(dataset)
    sampled = hs.load_scenarios(hs.FROZEN_BOARD)[:3]
    patch = pytest.MonkeyPatch()
    patch.setattr(
        scenarios_module, "generate_scenarios", lambda n, seed, country: sampled[:n]
    )
    patch.setattr(runtime, "materialize_certified_us_dataset", lambda: str(dataset))
    patch.setattr(
        runtime,
        "policyengine_bundles_for_countries",
        lambda countries: {
            "us": {
                "bundle_id": "us-test",
                "certified_data_artifact_sha256": digest,
                "default_dataset_uri": "hf://policyengine/populace-us/x.h5@test",
            }
        },
    )
    out = root / "board"
    try:
        hs.main(
            ["build", "--n", "3", "--seed", "7", "--batch-size", "2", "--out", str(out)]
        )
    finally:
        patch.undo()
    return out, sampled


@pytest.mark.slow
def test_build_writes_the_frozen_references_for_frozen_households(household_board):
    out, sampled = household_board
    frozen = pd.read_csv(hs.FROZEN_BOARD / "reference_outputs.csv")
    built = pd.read_csv(out / "reference_outputs.csv")
    names = {f"mc_{i:03d}": s.id for i, s in enumerate(sampled)}
    built["frozen_id"] = built.scenario_id.map(names)
    merged = built.merge(
        frozen,
        left_on=["frozen_id", "variable"],
        right_on=["scenario_id", "variable"],
        suffixes=("", "_frozen"),
    )
    assert (
        len(merged)
        == len(built)
        == len(frozen[frozen.scenario_id.isin(names.values())])
    )
    from policybench.reference_exclusions import load_reference_exclusions

    excluded = {
        (e["scenario_id"], e["variable"])
        for e in load_reference_exclusions(hs.FROZEN_BOARD)
    }
    scored = merged[
        [(s, v) not in excluded for s, v in zip(merged.frozen_id, merged.variable)]
    ]
    assert (scored.value - scored.value_frozen).abs().max() < 1e-6


@pytest.mark.slow
def test_build_writes_a_board_the_pilot_reads(household_board):
    out, _ = household_board
    meta = json.loads((out / "reference_outputs.csv.meta.json").read_text())
    assert meta["board_kind"] == "household_set"
    assert meta["seed"] == 7 and meta["num_scenarios"] == 3
    assert meta["reference_csv_sha256"] == hs.sha256_file(out / "reference_outputs.csv")
    assert json.loads((out / "batches.json").read_text())["batches"] == [
        ["mc_000", "mc_001"],
        ["mc_002"],
    ]
    board = pilot.load_board(out)
    assert sorted(board["scenarios"]) == ["mc_000", "mc_001", "mc_002"]
    assert board["excluded"].empty
    assert pilot.is_household_set(out)
    assert pilot.board_engine(out) == "2.41.0"
    pilot.verify_fix_pins(snapshot=out)
    pilot._require_engine(out)


@pytest.mark.slow
def test_build_refuses_a_written_directory_and_a_dataset_off_the_bundle(
    household_board, tmp_path, monkeypatch
):
    out, _ = household_board
    with pytest.raises(SystemExit, match="not empty"):
        hs.main(["build", "--n", "3", "--seed", "7", "--out", str(out)])
    import policybench.policyengine_runtime as runtime

    dataset = tmp_path / "x.h5"
    dataset.write_bytes(b"other bytes")
    monkeypatch.setattr(
        runtime, "materialize_certified_us_dataset", lambda: str(dataset)
    )
    monkeypatch.setattr(
        runtime,
        "policyengine_bundles_for_countries",
        lambda countries: {"us": {"certified_data_artifact_sha256": "0" * 64}},
    )
    with pytest.raises(SystemExit, match="not the bundle's"):
        hs.main(["build", "--n", "1", "--seed", "1", "--out", str(tmp_path / "new")])


def _record(sid, variables, predictions, model, arm, prompt="v2-pilot"):
    record = {
        "scenario_id": sid,
        "model": model,
        "arm": arm,
        "prompt_version": prompt,
        "benchmark_search_rule": arm in ("web", "web+pe"),
        "variables": variables,
        "predictions": predictions,
        "explanations": {v: "x" for v in variables},
        "status": "complete",
        "turns": [{"total_cost_usd": 0.02, "calls": []}],
        "cap_hit": False,
        "wall_seconds": 1.0,
    }
    record["totals"] = pilot.household_totals(record)
    return record


def _write_run(directory, board, model, arm, miss=None, prompt="v2-pilot"):
    reference = board["reference"].set_index(["scenario_id", "variable"])["value"]
    (directory / "households").mkdir(parents=True)
    for sid in sorted(board["scenarios"]):
        variables = board["variables"][sid]
        predictions = {v: float(reference[(sid, v)]) for v in variables}
        if miss is not None and sid == miss[0]:
            predictions[miss[1]] = float(reference[(sid, miss[1])]) + 100
        record = _record(sid, variables, predictions, model, arm, prompt)
        (directory / "households" / f"{sid}.json").write_text(json.dumps(record))


@pytest.mark.slow
def test_a_household_set_scores_each_arm_against_its_no_tools_run(
    household_board, tmp_path
):
    out, _ = household_board
    board = pilot.load_board(out)
    amount = next(
        v
        for v in board["variables"]["mc_000"]
        if not v.endswith("_eligible") and v in set(board["scored"].variable)
    )
    none_dir, web_dir = tmp_path / "none", tmp_path / "web"
    _write_run(none_dir, board, SOL, "none", miss=("mc_000", amount))
    _write_run(web_dir, board, SOL, "web")
    pilot.command_score(
        argparse.Namespace(
            out_dir=str(web_dir),
            complete_only=False,
            board=str(out),
            baseline_dir=str(none_dir),
        )
    )
    score = json.loads((web_dir / "score.json").read_text())
    assert score["unweighted_hits"]["arm2"] == score["scored_outputs"]
    assert score["unweighted_hits"]["arm1"] == score["scored_outputs"] - 1
    usage = pd.read_csv(web_dir / "usage_by_household.csv")
    assert usage.arm1_cost_usd.round(6).tolist() == [0.02, 0.02, 0.02]

    with pytest.raises(SystemExit, match="--baseline-dir"):
        pilot.command_score(
            argparse.Namespace(
                out_dir=str(web_dir), complete_only=False, board=str(out)
            )
        )
    with pytest.raises(SystemExit, match="not gpt-6-sol none"):
        pilot.command_score(
            argparse.Namespace(
                out_dir=str(web_dir),
                complete_only=False,
                board=str(out),
                baseline_dir=str(web_dir),
            )
        )
    v1_dir = tmp_path / "none-v1"
    _write_run(v1_dir, board, SOL, "none", prompt="v1")
    with pytest.raises(SystemExit, match="another prompt version"):
        pilot.command_score(
            argparse.Namespace(
                out_dir=str(web_dir),
                complete_only=False,
                board=str(out),
                baseline_dir=str(v1_dir),
            )
        )
