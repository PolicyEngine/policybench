"""Recompute every PolicyBench reference under each candidate 2026 Louisiana standard deduction.

La. R.S. 47:294(B) adjusts the standard deduction from January 1, 2026 by "the percentage
increase in the [CPI-U] ... for the previous calendar year". policyengine-us 2.15.17, the
version that built the published references, carries an explicit 2026 entry of $12,835
single and separate and $25,670 for the other statuses (PolicyEngine/policyengine-us#8411):
$12,500 times December 2025 CPI-U over December 2024 CPI-U, rounded to the dollar.

The reference system is the one that built the published references: policyengine-us
2.15.17 plus ``latest_final`` (the nine pre-freeze-law conventions and the Maryland
output-scope adapter), on households built by ``Scenario.to_pe_household``. The script
first recomputes every output under it and checks the result against the published
reference CSV. It then reruns every household with the Louisiana 2026 amounts replaced by
each candidate below. Each candidate sets the single and separate amount; the joint, head
of household and surviving spouse amounts are 200% of it (R.S. 47:294(A)(2)).

``engine``
    $12,835, the amount the references use (December to December, rounded).
``dec_dec_unrounded``
    $12,500 x 324.054 / 315.605: December to December, no rounding (the statute names none).
``annual_average``
    $12,500 x 321.943 / 313.689: 2025 annual average over 2024 annual average.
``ldr_published``
    $12,875: the only 2026 amount the Department of Revenue published before the freeze:
    its 2026 withholding tables (LAC 61:I.1501, Louisiana Register, January to May 2026),
    based on CPI-U data available on December 1, 2025 ($12,500 x 1.03), and the
    "estimated standard deduction" of its 2026 Form IT-540ESi worksheet.
``ldr_official``
    $12,838: the 2026 amount the Department of Revenue published on 2026-09-28, after the
    freeze, in Revenue Information Bulletin 26-019: $12,500 x 1.027, the 2.7% CPI-U
    multiplier, rounded to the dollar ($25,676 for the other statuses).
``hold_2025``
    $12,500: the 2025 amount, the last return amount Louisiana published before the freeze.

CPI-U values: BLS series CUUR0000SA0 (not seasonally adjusted, 1982-84=100), read from the
BLS public API on 2026-10-05: December 2024 315.605, December 2025 324.054, 2024 annual
average 313.689, 2025 annual average 321.943 (October 2025 not collected), September 2024
315.301, September 2025 324.800.

Run from a policybench checkout with the policyengine-us 2.15.17 venv:

  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=<checkout> \\
    <triage>/.venv-pe21517/bin/python \\
    reference_audit/2026-10-05-louisiana/scripts/sweep_la_standard_deduction.py \\
      --out-dir reference_audit/2026-10-05-louisiana/verification
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
AUDIT_0928 = ROOT / "reference_audit/2026-09-28"
AUDIT_0922 = ROOT / "reference_audit/2026-09-22"
YEAR = 2026
BINARY_SUFFIXES = ("_eligible",)
TOLERANCE = 1.0
# sweep.py's rename for the 1.755.4 harness; sweep_latest.py kept it on 2.15.17.
RENAME = {"partnership_se_income": "partnership_self_employment_net_earnings"}

CPI_U = {
    "2024-09": 315.301,
    "2024-12": 315.605,
    "2024-annual": 313.689,
    "2025-09": 324.800,
    "2025-12": 324.054,
    "2025-annual": 321.943,
}
BASE_2025 = 12_500
CANDIDATES = {
    "engine": 12_835,
    "dec_dec_unrounded": BASE_2025 * CPI_U["2025-12"] / CPI_U["2024-12"],
    "annual_average": BASE_2025 * CPI_U["2025-annual"] / CPI_U["2024-annual"],
    "ldr_published": 12_875,
    "ldr_official": 12_838,
    "hold_2025": BASE_2025,
}
SINGLE_STATUSES = ("SINGLE", "SEPARATE")
DOUBLE_STATUSES = ("JOINT", "HEAD_OF_HOUSEHOLD", "SURVIVING_SPOUSE")
PARAMETER = "gov.states.la.tax.income.deductions.standard.amount"
DIAGNOSTICS = (
    "adjusted_gross_income",
    "la_agi",
    "la_standard_deduction",
    "la_itemized_deductions",
    "la_taxable_income",
    "la_income_tax_before_non_refundable_credits",
    "la_non_refundable_credits",
    "la_income_tax_before_refundable_credits",
    "la_refundable_credits",
    "state_income_tax_before_refundable_credits",
)

_SYSTEMS: dict[str, object] = {}
_FIX_DIR = None


def _assemble_fixes() -> Path:
    """latest_final and its parts, plus the sales tax table the IRS module reads."""
    target = Path(tempfile.mkdtemp(prefix="la_standard_deduction_fixes_"))
    for path in (AUDIT_0928 / "fixes").glob("*.py"):
        shutil.copy2(path, target / path.name)
    shutil.copy2(AUDIT_0922 / "fixes/r19_irs_sales_tax_2025.json", target)
    return target


def _load_latest_final(fix_dir: Path):
    path = fix_dir / "latest_final.py"
    spec = importlib.util.spec_from_file_location("latest_final", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["latest_final"] = module
    spec.loader.exec_module(module)
    return module.reform


def _la_reform(single: float):
    from policyengine_core.reforms import Reform

    def modify(parameters):
        node = parameters.get_child(PARAMETER)
        for status in SINGLE_STATUSES:
            node.get_child(status).update(period=str(YEAR), value=single)
        for status in DOUBLE_STATUSES:
            node.get_child(status).update(period=str(YEAR), value=2 * single)
        return parameters

    class reform(Reform):
        def apply(self):
            self.modify_parameters(modify)

    return reform


def _system(candidate: str | None):
    """latest_final, then (for a candidate) the Louisiana 2026 amounts."""
    global _FIX_DIR
    key = candidate or "baseline"
    if key not in _SYSTEMS:
        from policyengine_us import CountryTaxBenefitSystem

        if _FIX_DIR is None:
            _FIX_DIR = _assemble_fixes()
        reforms = (_load_latest_final(_FIX_DIR),)
        if candidate is not None:
            reforms += (_la_reform(CANDIDATES[candidate]),)
        _SYSTEMS[key] = CountryTaxBenefitSystem(reform=reforms)
    return _SYSTEMS[key]


def build_situation(scenario) -> dict:
    situation = scenario.to_pe_household()
    for person in situation["people"].values():
        for old, new in RENAME.items():
            if old in person:
                person[new] = person.pop(old)
    return situation


def _outputs(sim, scenario, variables) -> dict[str, float]:
    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output

    values = {}
    for variable in variables:
        pe_variable = _pe_variable_for_output(variable, "us")
        values[variable] = float(
            _extract_person_value(sim.calculate(pe_variable, YEAR), scenario, variable)
        )
    return values


def _diagnostics(sim) -> dict[str, float]:
    values = {}
    for name in DIAGNOSTICS:
        try:
            values[name] = float(sim.calculate(name, YEAR).sum())
        except Exception:  # noqa: BLE001 - diagnostics only; a missing variable is NaN
            values[name] = float("nan")
    return values


def _simulate(situation: dict, candidate: str | None):
    from policyengine_us import Simulation

    return Simulation(tax_benefit_system=_system(candidate), situation=situation)


def sweep_scenario(args: tuple[str, list[str]]) -> dict:
    """Baseline and every candidate for one household."""
    from policybench.scenarios import scenario_from_dict

    scenario_json, variables = args
    scenario = scenario_from_dict(json.loads(scenario_json))
    situation = build_situation(scenario)
    base = _simulate(situation, None)
    result = {
        "scenario_id": scenario.id,
        "state": scenario.state,
        "baseline": _outputs(base, scenario, variables),
        "baseline_diagnostics": _diagnostics(base),
        "candidates": {},
    }
    for candidate in CANDIDATES:
        sim = _simulate(situation, candidate)
        result["candidates"][candidate] = {
            "outputs": _outputs(sim, scenario, variables),
            "diagnostics": _diagnostics(sim),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--scenarios", nargs="*")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    from policybench.scenarios import scenario_from_dict
    from policybench.spec import expand_programs_for_scenario

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = json.loads((RUN / "reference_outputs.csv.meta.json").read_text())
    programs = meta["programs"]
    reference = pd.read_csv(RUN / "reference_outputs.csv")
    indexed = reference.set_index(["scenario_id", "variable"])["value"]
    exclusions = json.loads((RUN / "reference_exclusions.json").read_text())[
        "exclusions"
    ]
    excluded = {(e["scenario_id"], e["variable"]): e for e in exclusions}
    scenarios = pd.read_csv(RUN / "scenarios.csv")
    if args.scenarios:
        scenarios = scenarios[scenarios["scenario_id"].isin(args.scenarios)]

    jobs = []
    for _, row in scenarios.iterrows():
        scenario = scenario_from_dict(json.loads(row["scenario_json"]))
        variables = [
            v
            for v in expand_programs_for_scenario(programs, scenario)
            if (scenario.id, v) in indexed.index
        ]
        jobs.append((row["scenario_json"], variables))

    engine = version("policyengine-us")
    print(f"policyengine-us {engine}; {len(jobs)} households", flush=True)
    print(
        "candidates (single; joint is 200%): "
        + ", ".join(f"{k}={v:.4f}" for k, v in CANDIDATES.items()),
        flush=True,
    )
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(sweep_scenario, jobs))
    results.sort(key=lambda r: r["scenario_id"])

    rows = []
    for result in results:
        sid = result["scenario_id"]
        for variable, base in result["baseline"].items():
            key = (sid, variable)
            ref = float(indexed[key])
            entry = excluded.get(key)
            binary = variable.endswith(BINARY_SUFFIXES)
            row = {
                "scenario_id": sid,
                "state": result["state"],
                "variable": variable,
                "reference": ref,
                "baseline": base,
                "baseline_matches_reference": (
                    round(base) == round(ref) if binary else abs(base - ref) <= 1e-3
                ),
                "excluded": entry is not None,
                "excluded_reason": entry["reason_code"] if entry else "",
            }
            for candidate in CANDIDATES:
                value = result["candidates"][candidate]["outputs"][variable]
                delta = value - base
                row[candidate] = value
                row[f"{candidate}_delta"] = delta
                row[f"{candidate}_moved"] = (
                    round(value) != round(base) if binary else abs(delta) > TOLERANCE
                )
                row[f"{candidate}_changed"] = (
                    round(value) != round(base) if binary else abs(delta) > 1e-6
                )
            rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(out_dir / "sweep_la_standard_deduction.csv", index=False)

    households = [
        {
            "scenario_id": r["scenario_id"],
            "state": r["state"],
            "baseline": r["baseline_diagnostics"],
            **{c: r["candidates"][c]["diagnostics"] for c in CANDIDATES},
        }
        for r in results
        if r["state"] == "LA"
    ]
    (out_dir / "sweep_la_households.json").write_text(
        json.dumps(
            {
                "policyengine_us": engine,
                "candidates_single": CANDIDATES,
                "cpi_u": CPI_U,
                "households": households,
            },
            indent=1,
            sort_keys=True,
        )
        + "\n"
    )

    scored = table[~table["excluded"]]
    mismatched = table[~table["baseline_matches_reference"] & ~table["excluded"]]
    print(
        f"baseline: {len(table)} outputs, {len(scored)} scored, "
        f"{len(mismatched)} scored outputs differ from the published reference"
    )
    if not mismatched.empty:
        print(mismatched[["scenario_id", "variable", "reference", "baseline"]])
    with pd.option_context("display.width", 220, "display.max_rows", 500):
        for candidate in CANDIDATES:
            changed = table[table[f"{candidate}_changed"]]
            moved = table[table[f"{candidate}_moved"]]
            print(
                f"\n{candidate} ({CANDIDATES[candidate]:.4f}): {len(changed)} outputs change, "
                f"{len(moved)} by more than ${TOLERANCE:g} "
                f"({int((~moved['excluded']).sum())} scored)"
            )
            if not changed.empty:
                print(
                    changed[
                        [
                            "scenario_id",
                            "state",
                            "variable",
                            "baseline",
                            candidate,
                            f"{candidate}_delta",
                            "excluded",
                        ]
                    ].to_string(index=False)
                )


if __name__ == "__main__":
    main()
