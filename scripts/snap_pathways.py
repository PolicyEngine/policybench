"""Recompute SNAP eligibility pathways for the frozen 100-household snapshot."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from policybench.ground_truth import (
    _build_us_vectorized_situation,
    _extract_us_vectorized_value,
)
from policybench.policyengine_runtime import get_us_situation_simulation_class
from policybench.scenarios import load_scenarios_from_manifest

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = (
    ROOT / "paper/snapshot/20260501/runs/"
    "us_full_run_20260612_policyengine_4_16_1_populace"
)
SCENARIOS_PATH = RUN_DIR / "scenarios.csv"
REFERENCE_PATH = RUN_DIR / "reference_outputs.csv"
OUTPUT_PATH = ROOT / "notes/data/snap_pathways_20260901.csv"
META_PATH = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".meta.json")
SCRIPT_PATH = "scripts/snap_pathways.py"
YEAR = 2026
MAX_REFERENCE_DIFFERENCE = 1.0

# policyengine-us 1.723.0 calls the underlying eligibility variable
# ``is_snap_eligible``. The output column keeps the requested shorter name and
# means a household has a positive computed allotment, matching how the note
# counts households that qualify in the frozen reference. The model-level gate
# is still calculated and checked while deriving each row.
VARIABLES = (
    "snap",
    "meets_snap_gross_income_test",
    "meets_snap_net_income_test",
    "meets_snap_asset_test",
    "is_tanf_non_cash_eligible",
    "is_snap_eligible",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bool(value: float) -> bool:
    if value not in (0, 1):
        raise ValueError(f"Expected a Boolean calculation, received {value!r}.")
    return bool(value)


def _pathway(
    *,
    snap_eligible: bool,
    gross: bool,
    net: bool,
    assets: bool,
    categorical: bool,
) -> str:
    if not snap_eligible:
        return "ineligible"
    if gross and net and assets:
        return "ordinary"
    if not categorical:
        raise ValueError(
            "A household with a positive SNAP allotment failed an ordinary "
            "eligibility test without categorical eligibility."
        )
    income_failure = not (gross and net)
    if income_failure and not assets:
        return "categorical_both"
    if income_failure:
        return "categorical_income"
    if not assets:
        return "categorical_assets"
    raise AssertionError("Unreachable SNAP pathway combination.")


def _snap_references() -> pd.Series:
    references = pd.read_csv(REFERENCE_PATH)
    snap = references.loc[references["variable"].eq("snap")].copy()
    if len(snap) != 100 or snap["scenario_id"].duplicated().any():
        raise ValueError(
            "Expected exactly one frozen SNAP reference for each of 100 scenarios."
        )
    return snap.set_index("scenario_id")["value"]


def build_rows() -> list[dict[str, object]]:
    """Calculate pathway inputs with the same vectorized builder as references."""
    scenarios = load_scenarios_from_manifest(SCENARIOS_PATH)
    if len(scenarios) != 100:
        raise ValueError(f"Expected 100 frozen scenarios, found {len(scenarios)}.")
    scenario_years = {scenario.year for scenario in scenarios}
    if scenario_years != {YEAR}:
        raise ValueError(f"Expected only {YEAR} scenarios, found {scenario_years}.")

    situation, scenario_indexes = _build_us_vectorized_situation(scenarios)
    simulation_class = get_us_situation_simulation_class()
    simulation = simulation_class(situation=situation)

    missing = [
        variable
        for variable in VARIABLES
        if variable not in simulation.tax_benefit_system.variables
    ]
    if missing:
        raise ValueError(f"Installed policyengine-us is missing variables: {missing}")

    calculations: dict[str, tuple[np.ndarray, str]] = {}
    for variable in VARIABLES:
        entity_key = simulation.tax_benefit_system.variables[variable].entity.key
        calculations[variable] = (
            np.asarray(simulation.calculate(variable, YEAR)),
            entity_key,
        )

    references = _snap_references()
    scenario_ids = {scenario.id for scenario in scenarios}
    if scenario_ids != set(references.index):
        raise ValueError("Frozen scenario and SNAP reference ids do not match.")

    rows: list[dict[str, object]] = []
    engine_eligible_without_allotment: list[str] = []
    for scenario in scenarios:
        index = scenario_indexes[scenario.id]

        def result(variable: str) -> float:
            values, entity_key = calculations[variable]
            return _extract_us_vectorized_value(
                values,
                scenario=scenario,
                variable=variable,
                entity_key=entity_key,
                index=index,
            )

        snap_reference = float(references.loc[scenario.id])
        snap_recomputed = result("snap")
        if not np.isfinite([snap_reference, snap_recomputed]).all():
            raise ValueError(f"{scenario.id} has a non-finite SNAP value.")
        gross = _bool(result("meets_snap_gross_income_test"))
        net = _bool(result("meets_snap_net_income_test"))
        assets = _bool(result("meets_snap_asset_test"))
        categorical = _bool(result("is_tanf_non_cash_eligible"))
        engine_eligible = _bool(result("is_snap_eligible"))
        snap_eligible = snap_recomputed > 0
        if snap_eligible and not engine_eligible:
            raise ValueError(
                f"{scenario.id} has a positive SNAP allotment but fails "
                "is_snap_eligible."
            )
        if engine_eligible and not snap_eligible:
            engine_eligible_without_allotment.append(scenario.id)

        rows.append(
            {
                "scenario_id": scenario.id,
                "state": scenario.state,
                "household_size": len(scenario.all_people),
                "snap_reference": snap_reference,
                "snap_recomputed": snap_recomputed,
                "meets_gross_income_test": gross,
                "meets_net_income_test": net,
                "meets_asset_test": assets,
                "is_tanf_non_cash_eligible": categorical,
                "snap_eligible": snap_eligible,
                "pathway": _pathway(
                    snap_eligible=snap_eligible,
                    gross=gross,
                    net=net,
                    assets=assets,
                    categorical=categorical,
                ),
            }
        )

    differences = [
        row
        for row in rows
        if abs(float(row["snap_recomputed"]) - float(row["snap_reference"]))
        > MAX_REFERENCE_DIFFERENCE
    ]
    if differences:
        details = "\n".join(
            f"  {row['scenario_id']}: reference={row['snap_reference']}, "
            f"recomputed={row['snap_recomputed']}"
            for row in differences
        )
        raise RuntimeError(
            "Recomputed SNAP differs from the frozen reference by more than "
            f"${MAX_REFERENCE_DIFFERENCE:.0f}:\n{details}"
        )

    if engine_eligible_without_allotment:
        print(
            "PolicyEngine's is_snap_eligible gate is true but the computed "
            "allotment is $0 for: " + ", ".join(engine_eligible_without_allotment)
        )
    return rows


def main() -> None:
    rows = build_rows()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT_PATH, index=False)
    metadata = {
        "policyengine_us_version": version("policyengine-us"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scenarios_sha256": _sha256(SCENARIOS_PATH),
        "script": SCRIPT_PATH,
    }
    META_PATH.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    pathway_counts = pd.Series(row["pathway"] for row in rows).value_counts()
    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH.relative_to(ROOT)}")
    for pathway in (
        "ordinary",
        "categorical_income",
        "categorical_assets",
        "categorical_both",
        "ineligible",
    ):
        print(f"  {pathway}: {int(pathway_counts.get(pathway, 0))}")


if __name__ == "__main__":
    main()
