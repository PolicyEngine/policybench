"""Recompute SNAP eligibility pathways under the September 22 reference configuration.

The September 22 SNAP references come from policyengine-us 1.755.4 with the
SNAP publication convention and every SNAP fix merged upstream after the freeze
(``reference_audit/2026-09-22/fixes/c13v3_plus_upstream_snap.py``). This script
recomputes, for each of the 100 frozen households, the monthly SNAP tests under
that configuration and the minimum allotment under both that configuration and
the unmodified engine, and checks the recomputed annual SNAP against the
published references.

It needs a policyengine-us 1.755.4 environment, as the audit harness does:

  PYTHONPATH=. <1.755.4 venv>/bin/python scripts/snap_pathways_20260922.py

The repository's own environment pins an older policyengine-us; the script
refuses to run on any version but 1.755.4.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = (
    ROOT / "paper/snapshot/20260501/runs/"
    "us_full_run_20260612_policyengine_4_16_1_populace"
)
SCENARIOS_PATH = RUN_DIR / "scenarios.csv"
REFERENCES_PATH = RUN_DIR / "reference_outputs.csv"
REFERENCE_META_PATH = RUN_DIR / "reference_outputs.csv.meta.json"
EXCLUSIONS_PATH = RUN_DIR / "reference_exclusions.json"
FIX_PATH = ROOT / "reference_audit/2026-09-22/fixes/c13v3_plus_upstream_snap.py"
OUTPUT_PATH = ROOT / "notes/data/snap_pathways_20260922.csv"
META_PATH = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".meta.json")
SCRIPT_PATH = "scripts/snap_pathways_20260922.py"
ENGINE_VERSION = "1.755.4"
YEAR = 2026
MONTHS = [f"{YEAR}-{month:02d}" for month in range(1, 13)]
MAX_REFERENCE_DIFFERENCE = 1.0
BBCE_STATES = ("CT", "MI", "TX", "WI")
# The v1.1 reference run renamed this input for policyengine-us 1.755.4, as the
# audit harness does (reference_audit/2026-09-22/scripts/sweep.py).
RENAME = {"partnership_se_income": "partnership_self_employment_net_earnings"}
TESTS = (
    "meets_snap_gross_income_test",
    "meets_snap_net_income_test",
    "meets_snap_asset_test",
    "is_tanf_non_cash_eligible",
    "is_snap_eligible",
)
csv.field_size_limit(sys.maxsize)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_fix(path: Path):
    spec = importlib.util.spec_from_file_location("snap_reference_fix", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["snap_reference_fix"] = module
    spec.loader.exec_module(module)
    return module


def _situation(scenario) -> dict:
    situation = scenario.to_pe_household()
    for person in situation["people"].values():
        for old, new in RENAME.items():
            if old in person:
                person[new] = person.pop(old)
    return situation


def _monthly(sim, variable: str) -> list[float]:
    return [float(sim.calculate(variable, month).sum()) for month in MONTHS]


def _boolean(values: list[float], scenario_id: str, variable: str) -> list[bool]:
    if any(value not in (0, 1) for value in values):
        raise ValueError(f"{scenario_id} {variable} is not Boolean: {values}")
    return [bool(value) for value in values]


def _one_pathway(pathways: list[str], scenario_id: str, months: str) -> str:
    # Inputs are annual and spread evenly, and the parameters change on
    # January 1 and October 1, so a pathway holds for each part of the year.
    if len(set(pathways)) != 1:
        raise ValueError(f"{scenario_id} pathway changes within {months}: {pathways}")
    return pathways[0]


def _pathway(*, eligible, gross, net, assets, tanf_non_cash, tanf_cash) -> str:
    if not eligible:
        return "ineligible"
    if gross and net and assets:
        return "ordinary"
    if tanf_non_cash and not tanf_cash:
        income_failure = not (gross and net)
        if income_failure and not assets:
            return "categorical_both"
        return "categorical_income" if income_failure else "categorical_assets"
    return "categorical_other"


def _bbce_parameters(system) -> dict:
    parameters = {}
    for instant in (f"{YEAR}-01-01", f"{YEAR}-10-01"):
        non_cash = system.parameters.gov.hhs.tanf.non_cash(instant)
        limits = non_cash.income_limit
        parameters[instant] = {
            state: {
                "gross_income_limit_fpg": float(limits.gross[state]),
                "gross_income_limit_fpg_elderly_disabled": float(
                    limits.gross_hheod[state]
                ),
                "net_income_test_applies": bool(limits.net_applies.non_hheod[state]),
                "net_income_test_applies_elderly_disabled": bool(
                    limits.net_applies.hheod[state]
                ),
                "asset_limit": (
                    None
                    if math.isinf(float(non_cash.asset_limit[state]))
                    else float(non_cash.asset_limit[state])
                ),
            }
            for state in BBCE_STATES
        }
    categorical = system.parameters.gov.usda.snap.categorical_eligibility(
        f"{YEAR}-01-01"
    )
    return {
        "state_tanf_non_cash": parameters,
        "snap_categorical_eligibility_programs": list(categorical),
    }


def build() -> tuple[list[dict], dict]:
    from policyengine_us import CountryTaxBenefitSystem, Simulation

    from policybench.scenarios import scenario_from_dict

    engine = version("policyengine-us")
    if engine != ENGINE_VERSION:
        raise SystemExit(f"Needs policyengine-us {ENGINE_VERSION}, found {engine}.")
    fix = _load_fix(FIX_PATH)
    reference_system = CountryTaxBenefitSystem(reform=fix.reform)
    frozen_system = CountryTaxBenefitSystem()

    with REFERENCES_PATH.open(encoding="utf-8", newline="") as source:
        references = {
            row["scenario_id"]: float(row["value"])
            for row in csv.DictReader(source)
            if row["variable"] == "snap"
        }
    excluded = {
        exclusion["scenario_id"]
        for exclusion in json.loads(EXCLUSIONS_PATH.read_text())["exclusions"]
        if exclusion["variable"] == "snap"
    }
    meta = json.loads(REFERENCE_META_PATH.read_text())
    frozen_values = dict(references)
    for revision in meta["revisions"]:
        for change in revision["changed"]:
            if change.get("variable", "snap") == "snap":
                frozen_values[change["scenario_id"]] = float(change["frozen"])

    with SCENARIOS_PATH.open(encoding="utf-8", newline="") as source:
        scenario_rows = list(csv.DictReader(source))
    if len(scenario_rows) != 100:
        raise ValueError(f"Expected 100 frozen scenarios, found {len(scenario_rows)}.")

    rows = []
    for scenario_row in scenario_rows:
        scenario = scenario_from_dict(json.loads(scenario_row["scenario_json"]))
        situation = _situation(scenario)
        sim = Simulation(tax_benefit_system=reference_system, situation=situation)
        frozen_sim = Simulation(tax_benefit_system=frozen_system, situation=situation)

        tests = {
            test: _boolean(_monthly(sim, test), scenario.id, test) for test in TESTS
        }
        snap = _monthly(sim, "snap")
        tanf_cash = _monthly(sim, "tanf")
        min_allotment = _monthly(sim, "snap_min_allotment")
        frozen_min_allotment = _monthly(frozen_sim, "snap_min_allotment")
        frozen_snap = sum(_monthly(frozen_sim, "snap"))
        # A month counts as eligible when the allotment is positive, as the
        # notes count households that qualify; the engine's own eligibility
        # flag must then hold.
        for index, month in enumerate(MONTHS):
            if snap[index] > 0 and not tests["is_snap_eligible"][index]:
                raise ValueError(
                    f"{scenario.id} {month}: allotment without eligibility."
                )
        pathways = [
            _pathway(
                eligible=snap[index] > 0,
                gross=tests["meets_snap_gross_income_test"][index],
                net=tests["meets_snap_net_income_test"][index],
                assets=tests["meets_snap_asset_test"][index],
                tanf_non_cash=tests["is_tanf_non_cash_eligible"][index],
                tanf_cash=tanf_cash[index] > 0,
            )
            for index in range(len(MONTHS))
        ]
        row = {
            "scenario_id": scenario.id,
            "state": scenario.state,
            "household_size": len(scenario.all_people),
            "snap_reference": references[scenario.id],
            "snap_scored": scenario.id not in excluded,
            "snap_recomputed": round(sum(snap), 4),
            "snap_frozen": frozen_values[scenario.id],
            "snap_frozen_engine": round(frozen_snap, 4),
            "gross_income_test_months": sum(tests["meets_snap_gross_income_test"]),
            "net_income_test_months": sum(tests["meets_snap_net_income_test"]),
            "asset_test_months": sum(tests["meets_snap_asset_test"]),
            "tanf_non_cash_eligible_months": sum(tests["is_tanf_non_cash_eligible"]),
            "tanf": round(sum(tanf_cash), 4),
            "pathway_jan_sep": _one_pathway(
                pathways[:9], scenario.id, "January-September"
            ),
            "pathway_oct_dec": _one_pathway(
                pathways[9:], scenario.id, "October-December"
            ),
            "min_allotment_jan": round(min_allotment[0], 4),
            "min_allotment_oct": round(min_allotment[9], 4),
            "frozen_engine_min_allotment_jan": round(frozen_min_allotment[0], 4),
            "frozen_engine_min_allotment_oct": round(frozen_min_allotment[9], 4),
            "max_allotment_jan": round(
                float(sim.calculate("snap_max_allotment", MONTHS[0]).sum()), 4
            ),
            "expected_contribution_jan": round(
                float(sim.calculate("snap_expected_contribution", MONTHS[0]).sum()), 4
            ),
            "monthly_snap": " ".join(f"{value:g}" for value in snap),
        }
        rows.append(row)
        print(
            scenario.id,
            row["pathway_jan_sep"],
            row["pathway_oct_dec"],
            row["snap_recomputed"],
            flush=True,
        )

    mismatched = [
        row
        for row in rows
        if row["snap_scored"]
        and abs(row["snap_recomputed"] - row["snap_reference"])
        > MAX_REFERENCE_DIFFERENCE
    ]
    frozen_mismatched = [
        row
        for row in rows
        if abs(row["snap_frozen_engine"] - row["snap_frozen"])
        > MAX_REFERENCE_DIFFERENCE
    ]
    if mismatched or frozen_mismatched:
        raise ValueError(
            "Recomputed SNAP disagrees with the published or frozen references: "
            f"{[row['scenario_id'] for row in mismatched]} "
            f"{[row['scenario_id'] for row in frozen_mismatched]}"
        )

    run_meta = {
        "policyengine_us_version": engine,
        "configuration": (
            "policyengine-us 1.755.4 with the SNAP publication convention and every "
            "SNAP fix merged upstream after the reference freeze, as the September 22 "
            "SNAP references were regenerated; the frozen_engine columns use the "
            "unmodified engine"
        ),
        "fix_module": str(FIX_PATH.relative_to(ROOT)),
        "fix_module_sha256": _sha256(FIX_PATH),
        "fix_parts_sha256": {
            part.__name__: _sha256(Path(part.__file__)) for part in fix._PARTS
        },
        "scenarios_sha256": _sha256(SCENARIOS_PATH),
        "reference_csv_sha256": _sha256(REFERENCES_PATH),
        "months": (
            "the *_months columns count the months of 2026 in which each test holds"
        ),
        "bbce_parameters": _bbce_parameters(reference_system),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": SCRIPT_PATH,
    }
    return rows, run_meta


def main() -> None:
    rows, run_meta = build()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    META_PATH.write_text(json.dumps(run_meta, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
