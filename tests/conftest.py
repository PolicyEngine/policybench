"""Shared fixtures for PolicyBench tests."""

import pytest

from policybench.scenarios import Person, Scenario


@pytest.fixture
def simple_single_scenario():
    """Single filer, no kids, $50k income in CA."""
    return Scenario(
        id="test_single",
        state="CA",
        filing_status="single",
        adults=[Person(name="adult1", age=35, employment_income=50_000.0)],
        children=[],
        year=2026,
    )


@pytest.fixture
def family_scenario():
    """Joint filers, 2 kids, $100k combined income in TX."""
    return Scenario(
        id="test_family",
        state="TX",
        filing_status="joint",
        adults=[
            Person(name="adult1", age=40, employment_income=70_000.0),
            Person(name="adult2", age=38, employment_income=30_000.0),
        ],
        children=[
            Person(name="child1", age=10, employment_income=0.0),
            Person(name="child2", age=5, employment_income=0.0),
        ],
        year=2026,
    )


@pytest.fixture
def low_income_scenario():
    """Single parent, 2 kids, $15k income in NY (EITC/SNAP eligible)."""
    return Scenario(
        id="test_low_income",
        state="NY",
        filing_status="head_of_household",
        adults=[Person(name="adult1", age=30, employment_income=15_000.0)],
        children=[
            Person(name="child1", age=8, employment_income=0.0),
            Person(name="child2", age=3, employment_income=0.0),
        ],
        year=2026,
    )


@pytest.fixture
def sample_scenarios(simple_single_scenario, family_scenario, low_income_scenario):
    """A small set of test scenarios."""
    return [simple_single_scenario, family_scenario, low_income_scenario]


# A three-household set built from the frozen board's first households, with
# sampling and the dataset download faked (tests/test_household_set.py,
# tests/test_batch_judge.py). Its references must be the frozen ones on the
# frozen engine, policyengine-us 2.41.0; on any other engine it is skipped.
@pytest.fixture(scope="session")
def household_board(tmp_path_factory):
    """A three-household set built from the frozen board's first households."""
    import importlib.metadata
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import household_set as hs

    if importlib.metadata.version("policyengine-us") != "2.41.0":
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
        scenarios_module,
        "generate_scenarios",
        lambda n, seed, country, **kwargs: sampled[:n],
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
                # The bundle certifies its data for the installed engine.
                "bundled_model_version": "2.41.0",
                "model_version": "2.41.0",
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
