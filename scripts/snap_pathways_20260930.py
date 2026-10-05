"""Recompute SNAP eligibility pathways under the references of release 20260930.

Release dashboard-data-20260930 scores the references release
dashboard-data-20260929 built on policyengine-us 2.15.17 with the publication
conventions and the Maryland output-scope adapter
(``reference_audit/2026-09-28/fixes/latest_final.py``). This script runs that
configuration on each of the 100 frozen households and records, month by month,
the SNAP tests the BBCE note cites: SNAP's ordinary gross income, net income and
asset tests, the state's test for the TANF-funded non-cash benefit that confers
broad-based categorical eligibility (BBCE), the allotment and its parts, and the
pathway through which the household qualifies. It checks the recomputed annual
SNAP against every scored reference.

Pathways are recorded for each month, since one of the note's households, in
Arizona, qualifies only from March 2026, when Arizona raised its BBCE gross
income limit from 185% to 200% of the poverty guideline.

The meta records:

- the SNAP and state TANF non-cash parameters the note cites, on each date in
  2026 they change for the note's states;
- the engine's own formulas for SNAP categorical eligibility, eligibility for
  the TANF non-cash benefit, SNAP eligibility and the normal allotment, read
  from the installed policyengine-us, so the note's claims about how
  PolicyEngine applies BBCE are checked against the engine's code;
- each household whose SNAP output the release excludes, with the exclusion
  record's reason;
- for each household with a member the engine treats as elderly or disabled
  that lists employer-sponsored insurance premiums, the SNAP tests with those
  premiums read as paid by the household: policyengine-us documents the input
  as employer-paid, so the engine counts none of it as a medical expense.

It needs a policyengine-us 2.15.17 environment, as the reference builder does:

  OPENBLAS_NUM_THREADS=1 PYTHONPATH=. <2.15.17 venv>/bin/python \\
    scripts/snap_pathways_20260930.py

It refuses to run on any other version. ``tests/test_notes.py`` reruns
:func:`build` and compares it with the committed files when that version is
installed (a slow test, skipped elsewhere).
"""

from __future__ import annotations

import csv
import inspect
import json
import math
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from snap_pathways_20260922 import (  # noqa: E402
    EMPLOYER_PREMIUMS,
    PERSON_PREMIUMS,
    _boolean,
    _excluded_snap_rows,
    _load_fix,
    _monthly,
    _pathway,
    _premiums_paid_by_household,
    _sha256,
    _situation,
    csv_text,
    meta_text,
)

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = (
    ROOT / "paper/snapshot/20260501/runs/"
    "us_full_run_20260612_policyengine_4_16_1_populace"
)
SCENARIOS_PATH = RUN_DIR / "scenarios.csv"
REFERENCES_PATH = RUN_DIR / "reference_outputs.csv"
EXCLUSIONS_PATH = RUN_DIR / "reference_exclusions.json"
FIX_DIR = ROOT / "reference_audit/2026-09-28/fixes"
FIX_MODULE = "latest_final.py"
# latest_c_irs_sales_tax_2025.py reads this table from its own directory; the
# reference build copied it there from the September 22 audit
# (reference_audit/2026-09-28/scripts/build_references_latest.py).
SALES_TAX_TABLE = ROOT / "reference_audit/2026-09-22/fixes/r19_irs_sales_tax_2025.json"
OUTPUT_PATH = ROOT / "notes/data/snap_pathways_20260930.csv"
META_PATH = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".meta.json")
SCRIPT_PATH = "scripts/snap_pathways_20260930.py"
ENGINE_VERSION = "2.15.17"
YEAR = 2026
MONTHS = [f"{YEAR}-{month:02d}" for month in range(1, 13)]
MAX_REFERENCE_DIFFERENCE = 1.0
# The states of the note's households: held back by income, then by savings.
BBCE_STATES = ("AZ", "CT", "MI", "TX", "WI", "NC", "NJ", "PA", "VA")
# The dates in 2026 on which a parameter the note cites changes: Arizona's
# BBCE limit (March 1) and the federal fiscal year (October 1).
INSTANTS = (f"{YEAR}-01-01", f"{YEAR}-03-01", f"{YEAR}-10-01")
TESTS = (
    "meets_snap_gross_income_test",
    "meets_snap_net_income_test",
    "meets_snap_asset_test",
    "is_tanf_non_cash_eligible",
    "meets_tanf_non_cash_gross_income_test",
    "is_snap_eligible",
)
# The engine formulas whose code the meta records.
ENGINE_RULES = (
    "meets_snap_categorical_eligibility",
    "is_tanf_non_cash_eligible",
    "is_snap_eligible",
    "snap_normal_allotment",
    "meets_snap_gross_income_test",
)


def _reference_system():
    """policyengine-us with latest_final, loaded from a copy of the committed
    fix modules beside the sales tax table one of them reads."""
    from policyengine_us import CountryTaxBenefitSystem

    scratch = Path(tempfile.mkdtemp(prefix="snap-pathways-20260930-"))
    try:
        for module in FIX_DIR.glob("*.py"):
            shutil.copy(module, scratch / module.name)
        shutil.copy(SALES_TAX_TABLE, scratch / SALES_TAX_TABLE.name)
        fix = _load_fix(scratch / FIX_MODULE)
        return CountryTaxBenefitSystem(reform=fix.reform)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _fix_modules() -> dict[str, str]:
    """The sha256 of every committed module latest_final composes, and of the
    sales tax table."""
    digests = {path.name: _sha256(path) for path in sorted(FIX_DIR.glob("*.py"))}
    digests[SALES_TAX_TABLE.name] = _sha256(SALES_TAX_TABLE)
    return digests


def _bbce_parameters(system) -> dict:
    parameters = {}
    for instant in INSTANTS:
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


def _snap_parameters(system) -> dict:
    """The ordinary SNAP gross income limit and the unearned income sources."""
    parameters = {}
    for instant in INSTANTS:
        snap = system.parameters.gov.usda.snap(instant)
        parameters[instant] = {
            "gross_income_limit_fpg": float(snap.income.limit.gross),
            "unearned_income_sources": list(snap.income.sources.unearned),
        }
    return parameters


def _engine_rules(system) -> dict[str, str]:
    """Each named variable's formula, as the installed engine defines it."""
    rules = {}
    for name in ENGINE_RULES:
        formulas = system.variables[name].formulas
        if len(formulas) != 1:
            raise ValueError(f"{name} has {len(formulas)} formulas.")
        (formula,) = formulas.values()
        rules[name] = inspect.getsource(formula)
    return rules


def _rounded(values: list[float]) -> str:
    return " ".join(f"{round(value, 4):g}" for value in values)


def _pathways(snap: list[float], tests: dict, tanf_cash: list[float]) -> list[str]:
    return [
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


def _tests(sim, scenario_id: str) -> dict[str, list[bool]]:
    return {test: _boolean(_monthly(sim, test), scenario_id, test) for test in TESTS}


def build() -> tuple[list[dict], dict]:
    from policyengine_us import Simulation

    from policybench.scenarios import scenario_from_dict

    engine = version("policyengine-us")
    if engine != ENGINE_VERSION:
        raise SystemExit(f"Needs policyengine-us {ENGINE_VERSION}, found {engine}.")
    system = _reference_system()

    with REFERENCES_PATH.open(encoding="utf-8", newline="") as source:
        references = {
            row["scenario_id"]: float(row["value"])
            for row in csv.DictReader(source)
            if row["variable"] == "snap"
        }
    exclusions = json.loads(EXCLUSIONS_PATH.read_text())["exclusions"]
    excluded = {e["scenario_id"] for e in exclusions if e["variable"] == "snap"}

    with SCENARIOS_PATH.open(encoding="utf-8", newline="") as source:
        scenario_rows = list(csv.DictReader(source))
    if len(scenario_rows) != 100:
        raise ValueError(f"Expected 100 frozen scenarios, found {len(scenario_rows)}.")

    rows = []
    premium_readings = {}
    for scenario_row in scenario_rows:
        scenario = scenario_from_dict(json.loads(scenario_row["scenario_json"]))
        situation = _situation(scenario)
        sim = Simulation(tax_benefit_system=system, situation=situation)

        tests = _tests(sim, scenario.id)
        snap = _monthly(sim, "snap")
        tanf_cash = _monthly(sim, "tanf")
        gross_ratio = _monthly(sim, "snap_gross_income_fpg_ratio")
        # The household's gross income against the poverty guideline its
        # state's BBCE limit is a share of (tanf_non_cash_fpg).
        bbce_ratio = [
            income / fpg
            for income, fpg in zip(
                _monthly(sim, "snap_gross_test_income"),
                _monthly(sim, "tanf_non_cash_fpg"),
                strict=True,
            )
        ]
        # A member the engine treats as elderly or disabled exempts the
        # household from the ordinary gross income test.
        elderly_disabled = _boolean(
            _monthly(sim, "has_snap_elderly_disabled_member"),
            scenario.id,
            "has_snap_elderly_disabled_member",
        )
        # A month counts as eligible when the allotment is positive, as the
        # notes count households that qualify; the engine's own eligibility
        # flag must then hold.
        for index, month in enumerate(MONTHS):
            if snap[index] > 0 and not tests["is_snap_eligible"][index]:
                raise ValueError(
                    f"{scenario.id} {month}: allotment without eligibility."
                )
        row = {
            "scenario_id": scenario.id,
            "state": scenario.state,
            "household_size": len(scenario.all_people),
            "snap_reference": references[scenario.id],
            "snap_scored": scenario.id not in excluded,
            "snap_recomputed": round(sum(snap), 4),
            "elderly_or_disabled_months": sum(elderly_disabled),
            "gross_income_test_months": sum(tests["meets_snap_gross_income_test"]),
            "gross_income_fpg_ratio_min": round(min(gross_ratio), 4),
            "net_income_test_months": sum(tests["meets_snap_net_income_test"]),
            "asset_test_months": sum(tests["meets_snap_asset_test"]),
            "tanf_non_cash_eligible_months": sum(tests["is_tanf_non_cash_eligible"]),
            "tanf_non_cash_gross_test_months": sum(
                tests["meets_tanf_non_cash_gross_income_test"]
            ),
            "tanf_non_cash_gross_test_by_month": " ".join(
                str(int(value))
                for value in tests["meets_tanf_non_cash_gross_income_test"]
            ),
            "tanf_non_cash_gross_ratio_min": round(min(bbce_ratio), 4),
            "tanf_non_cash_gross_ratio_max": round(max(bbce_ratio), 4),
            "tanf": round(sum(tanf_cash), 4),
            "pathway_by_month": " ".join(_pathways(snap, tests, tanf_cash)),
            "monthly_snap": _rounded(snap),
            "monthly_min_allotment": _rounded(_monthly(sim, "snap_min_allotment")),
            "monthly_max_allotment": _rounded(_monthly(sim, "snap_max_allotment")),
            "monthly_expected_contribution": _rounded(
                _monthly(sim, "snap_expected_contribution")
            ),
        }
        rows.append(row)
        moved = (
            _premiums_paid_by_household(situation) if any(elderly_disabled) else None
        )
        if moved is not None:
            alt = Simulation(tax_benefit_system=system, situation=moved)
            alt_tests = _tests(alt, scenario.id)
            alt_snap = _monthly(alt, "snap")
            premium_readings[scenario.id] = {
                "monthly_net_income": _rounded(_monthly(sim, "snap_net_income")),
                "monthly_net_income_premiums_paid": _rounded(
                    _monthly(alt, "snap_net_income")
                ),
                "net_income_test_months_premiums_paid": sum(
                    alt_tests["meets_snap_net_income_test"]
                ),
                "pathway_by_month_premiums_paid": " ".join(
                    _pathways(alt_snap, alt_tests, _monthly(alt, "tanf"))
                ),
                "monthly_snap_premiums_paid": _rounded(alt_snap),
            }
        print(scenario.id, row["pathway_by_month"], row["snap_recomputed"], flush=True)

    mismatched = [
        row["scenario_id"]
        for row in rows
        if row["snap_scored"]
        and abs(row["snap_recomputed"] - row["snap_reference"])
        > MAX_REFERENCE_DIFFERENCE
    ]
    if mismatched:
        raise ValueError(f"Recomputed SNAP disagrees with the references: {mismatched}")

    run_meta = {
        "policyengine_us_version": engine,
        "configuration": (
            "policyengine-us 2.15.17 with latest_final (the nine publication "
            "conventions and the Maryland output-scope adapter), on households "
            "built by policybench.scenarios.Scenario.to_pe_household, as release "
            "dashboard-data-20260929 built the references release "
            "dashboard-data-20260930 scores"
        ),
        "fix_module": str((FIX_DIR / FIX_MODULE).relative_to(ROOT)),
        "fix_modules_sha256": _fix_modules(),
        "scenarios_sha256": _sha256(SCENARIOS_PATH),
        "reference_csv_sha256": _sha256(REFERENCES_PATH),
        "months": (
            "the *_months columns count the months of 2026 in which each test "
            "holds; the *_by_month and monthly_* columns list January to December"
        ),
        "bbce_parameters": _bbce_parameters(system),
        "snap_parameters": _snap_parameters(system),
        "engine_rules": _engine_rules(system),
        "excluded_snap_rows": {
            "note": (
                "Rows whose snap_scored is False show PolicyEngine's computation, "
                "which the release's exclusion record sets aside for every model "
                "(reference_exclusions.json)"
            ),
            "households": _excluded_snap_rows(exclusions),
        },
        "employer_premiums_paid_by_household": {
            "engine_documentation": system.variables[EMPLOYER_PREMIUMS].documentation,
            "reading": (
                f"{EMPLOYER_PREMIUMS} moved into {PERSON_PREMIUMS}, for households "
                "with a member the engine treats as elderly or disabled"
            ),
            "households": premium_readings,
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": SCRIPT_PATH,
    }
    return rows, run_meta


def main() -> None:
    rows, run_meta = build()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as target:
        target.write(csv_text(rows))
    META_PATH.write_text(meta_text(run_meta), encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
