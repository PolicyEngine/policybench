from types import SimpleNamespace

import pytest

from policybench.cli import _load_reference_scenarios
from policybench.scenarios import Person, Scenario, scenario_manifest


def test_load_reference_scenarios_reuses_existing_manifest(tmp_path):
    scenario = Scenario(
        id="reuse_manifest",
        country="us",
        state="CA",
        filing_status="single",
        adults=[Person(name="head", age=35, employment_income=50_000.0)],
        year=2026,
    )
    manifest_path = tmp_path / "scenarios.csv"
    scenario_manifest([scenario]).to_csv(manifest_path, index=False)

    scenarios, manifest_input = _load_reference_scenarios(
        SimpleNamespace(
            scenario_manifest=str(manifest_path),
            country="us",
            exclude_scenario_manifest=None,
            num_scenarios=999,
            seed=1,
        )
    )

    assert manifest_input == str(manifest_path)
    assert [loaded.id for loaded in scenarios] == ["reuse_manifest"]


def test_load_reference_scenarios_rejects_country_mismatch(tmp_path):
    scenario = Scenario(
        id="uk_manifest",
        country="uk",
        state="LONDON",
        filing_status=None,
        adults=[Person(name="head", age=35, employment_income=50_000.0)],
        year=2026,
    )
    manifest_path = tmp_path / "scenarios.csv"
    scenario_manifest([scenario]).to_csv(manifest_path, index=False)

    with pytest.raises(SystemExit, match="country does not match"):
        _load_reference_scenarios(
            SimpleNamespace(
                scenario_manifest=str(manifest_path),
                country="us",
                exclude_scenario_manifest=None,
                num_scenarios=100,
                seed=42,
            )
        )
