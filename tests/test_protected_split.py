"""Tests for the protected evaluation split."""

import json
import sys
from unittest.mock import patch

import pandas as pd
import pytest

from policybench.cli import _private_sibling_path, main
from policybench.scenarios import Person, Scenario, split_scenarios


def make_scenarios(count: int) -> list[Scenario]:
    return [
        Scenario(
            id=f"scenario_{index:03d}",
            country="us",
            state="CA",
            filing_status="single",
            adults=[Person(name="head", age=30 + index, employment_income=40_000.0)],
            year=2026,
        )
        for index in range(count)
    ]


def test_split_is_deterministic_and_disjoint():
    scenarios = make_scenarios(20)
    public_a, private_a = split_scenarios(scenarios, 0.25, seed=7)
    public_b, private_b = split_scenarios(scenarios, 0.25, seed=7)

    assert [s.id for s in public_a] == [s.id for s in public_b]
    assert [s.id for s in private_a] == [s.id for s in private_b]
    assert len(private_a) == 5
    assert {s.id for s in public_a} | {s.id for s in private_a} == {
        s.id for s in scenarios
    }
    assert {s.id for s in public_a} & {s.id for s in private_a} == set()


def test_split_membership_is_order_independent():
    scenarios = make_scenarios(20)
    _, private_forward = split_scenarios(scenarios, 0.3, seed=11)
    _, private_reversed = split_scenarios(list(reversed(scenarios)), 0.3, seed=11)
    assert {s.id for s in private_forward} == {s.id for s in private_reversed}


def test_split_preserves_input_order():
    scenarios = make_scenarios(10)
    public, private = split_scenarios(scenarios, 0.4, seed=3)
    original_order = [s.id for s in scenarios]
    assert [s.id for s in public] == [
        sid for sid in original_order if sid in {s.id for s in public}
    ]
    assert [s.id for s in private] == [
        sid for sid in original_order if sid in {s.id for s in private}
    ]


def test_seed_changes_membership():
    scenarios = make_scenarios(40)
    _, private_a = split_scenarios(scenarios, 0.5, seed=1)
    _, private_b = split_scenarios(scenarios, 0.5, seed=2)
    assert {s.id for s in private_a} != {s.id for s in private_b}


def test_zero_fraction_returns_everything_public():
    scenarios = make_scenarios(5)
    public, private = split_scenarios(scenarios, 0.0, seed=1)
    assert [s.id for s in public] == [s.id for s in scenarios]
    assert private == []


def test_tiny_fraction_rounds_to_zero():
    scenarios = make_scenarios(4)
    public, private = split_scenarios(scenarios, 0.1, seed=1)
    assert len(public) == 4
    assert private == []


def test_invalid_fraction_raises():
    scenarios = make_scenarios(3)
    with pytest.raises(ValueError, match="private_fraction"):
        split_scenarios(scenarios, 1.0, seed=1)
    with pytest.raises(ValueError, match="private_fraction"):
        split_scenarios(scenarios, -0.1, seed=1)


def test_private_sibling_path():
    assert str(_private_sibling_path("results/local/scenarios.csv")) == (
        "results/local/scenarios-private.csv"
    )


def _fake_ground_truth(scenarios, programs):
    return pd.DataFrame(
        {
            "scenario_id": [scenario.id for scenario in scenarios],
            "variable": ["snap"] * len(scenarios),
            "value": [100.0] * len(scenarios),
        }
    )


def test_reference_outputs_cli_writes_private_split(tmp_path):
    scenarios = make_scenarios(10)
    output = tmp_path / "reference_outputs.csv"
    manifest = tmp_path / "scenarios.csv"
    argv = [
        "policybench",
        "reference-outputs",
        "-o",
        str(output),
        "--scenario-manifest-output",
        str(manifest),
        "--private-fraction",
        "0.3",
        "--split-seed",
        "5",
    ]
    with (
        patch(
            "policybench.cli._load_reference_scenarios",
            return_value=(scenarios, None),
        ),
        patch(
            "policybench.ground_truth.calculate_ground_truth",
            side_effect=_fake_ground_truth,
        ),
        patch(
            "policybench.policyengine_runtime.runtime_metadata_for_country",
            return_value={},
        ),
        patch.object(sys, "argv", argv),
    ):
        main()

    private_output = tmp_path / "reference_outputs-private.csv"
    private_manifest = tmp_path / "scenarios-private.csv"
    assert output.exists() and manifest.exists()
    assert private_output.exists() and private_manifest.exists()

    public_ids = set(pd.read_csv(manifest)["scenario_id"])
    private_ids = set(pd.read_csv(private_manifest)["scenario_id"])
    assert len(private_ids) == 3
    assert public_ids | private_ids == {s.id for s in scenarios}
    assert public_ids & private_ids == set()
    assert set(pd.read_csv(output)["scenario_id"]) == public_ids
    assert set(pd.read_csv(private_output)["scenario_id"]) == private_ids

    public_meta = json.loads((tmp_path / "scenarios.csv.meta.json").read_text())
    private_meta = json.loads(
        (tmp_path / "scenarios-private.csv.meta.json").read_text()
    )
    assert public_meta["split"] == "public"
    assert public_meta["num_scenarios"] == 7
    assert private_meta["split"] == "private"
    assert private_meta["num_scenarios"] == 3
    assert private_meta["private_fraction"] == 0.3
    assert private_meta["split_seed"] == 5


def test_reference_outputs_cli_default_has_no_private_files(tmp_path):
    scenarios = make_scenarios(4)
    output = tmp_path / "reference_outputs.csv"
    manifest = tmp_path / "scenarios.csv"
    argv = [
        "policybench",
        "reference-outputs",
        "-o",
        str(output),
        "--scenario-manifest-output",
        str(manifest),
    ]
    with (
        patch(
            "policybench.cli._load_reference_scenarios",
            return_value=(scenarios, None),
        ),
        patch(
            "policybench.ground_truth.calculate_ground_truth",
            side_effect=_fake_ground_truth,
        ),
        patch(
            "policybench.policyengine_runtime.runtime_metadata_for_country",
            return_value={},
        ),
        patch.object(sys, "argv", argv),
    ):
        main()

    assert output.exists()
    assert not (tmp_path / "reference_outputs-private.csv").exists()
    meta = json.loads((tmp_path / "reference_outputs.csv.meta.json").read_text())
    assert meta["split"] == "public"
    assert meta["num_scenarios"] == 4
