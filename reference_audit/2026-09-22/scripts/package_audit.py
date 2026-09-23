"""Assemble the committed reference-audit record from the triage tree.

Writes <dest> (default: the worktree's reference_audit/2026-09-22): the root
causes, every fix module the records and references rest on, the per-root-cause
sweep of all 1,984 references (sweep_moves.csv), the SNAP net-income sensitivity,
the build scripts and the verification reports. Run after build_records.py,
regen_references.py and make_on_convention.py:

  python3 package_audit.py [--dest <dir>]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

import pandas as pd

from make_on_convention import MEASUREMENTS

HERE = Path(__file__).resolve().parent
FIXES = HERE / "sweep" / "fixes"
OUT = HERE / "sweep" / "out"
WK = Path("/Users/maxghenis/PolicyEngine/_wk")
DEST = Path("/Users/maxghenis/PolicyEngine/policybench-wt/opus55/reference_audit/2026-09-22")

# Modules the recorded ones load at run time, and the measurement modules.
EXTRA_FIXES = [
    "r18_hold_all_projections.py",
    # Superseded: the first SNAP convention module the v7 reviews examined.
    "r13_hold_fy2026_v2.py",
    "r19_irs_sales_tax_2025.json",
    "r01_ira_compensation.py",
    "r02_ira_219g.py",
    "r03_estate_income_v2.py",
    "c13v3_plus_r26.py",
    "c13v3_plus_r27.py",
    "c13v3_plus_r28.py",
    "c13v3_plus_r30.py",
    "c13v3_plus_r31.py",
    "c13v3_plus_upstream_snap.py",
    "c13v3_upstream_plus_r30.py",
    "cwi_plus_r04.py",
    "cwi_plus_r04_r32.py",
    # Superseded for r04 on 2026-09-23: #8839 plus the Wisconsin part now in r32.
    "r04_capital_gain_distributions_v2.py",
    "c13v3_r26_r28.py",
    "c13v3_r28_r29n.py",
    "c13v3_r28_r29c.py",
    "r29_snap_net_nearest.py",
    "r29_snap_net_cents.py",
]
SCRIPTS = [
    HERE / "sweep" / "sweep.py",
    HERE / "sweep" / "run_one.sh",
    HERE / "build_records.py",
    HERE / "regen_references.py",
    HERE / "make_on_convention.py",
    HERE / "package_audit.py",
]
VERIFICATION = {
    "v1_r01.md": WK / "pb-triage-verify/sweep/verify/work/r01_report.md",
    "v1_r02.md": WK / "pb-triage-verify/sweep/verify/work/r02_legal.md",
    "v1_r03.md": WK / "pb-triage-verify/sweep/verify/work/r03_report.md",
    "v1_r16.md": WK / "pb-triage-verify/sweep/verify/work/r16_report.md",
    "v2_r04_r05_r06_r07_r10.md": WK / "pb-triage-verify-v2/sweep/verify/REPORT.md",
    "v3_r08_r09_r11_r12.md": WK / "pb-triage-verify-v3/sweep/verify/REPORT.md",
    "v4_r13_r14_r15.md": WK / "pb-triage-verify-v4/sweep/verify/SNAP_VERIFICATION.md",
    "v5a_projection_irs_wi_id_ca.md": WK / "pb-triage-verify-v5a/sweep/verify/r19_projected_parameter_audit.md",
    "v5b_projection_mn_md_mi_mo_il.md": WK / "pb-triage-verify-v5b/sweep/verify/r19_report.md",
    "v6_flag_067.md": WK / "pb-flag-v6-067/report.md",
    "v6_flag_076.md": WK / "pb-flag-v6-076/report.md",
    "v6_flag_081.md": WK / "pb-flag-v6-081/report.md",
    "v7_review_data.md": WK / "pb-review-b6a3238/report-data.md",
    "v7_review_claims.md": WK / "pb-review-b6a3238/report-claims.md",
    "v8_axiom_snap_rounding.md": WK / "axiom-pb-parity/snap/report.md",
    "v8_snap_state_rounding.md": WK / "snap-state-rounding/report.md",
    "v9_axiom_us-219.md": WK / "axenc-pb/reports/axiom-us-219.md",
    "v9_axiom_us-32c2.md": WK / "axenc-pb/reports/axiom-us-32c2.md",
    "v9_axiom_us-662.md": WK / "axenc-pb/reports/axiom-us-662.md",
    "v9_axiom_ca-17076.md": WK / "axenc-pb/reports/axiom-ca-17076.md",
    "v9_axiom_ca-17052.md": WK / "axenc-pb/reports/axiom-ca-17052.md",
    "v9_axiom_id-63-3022p.md": WK / "axenc-pb/reports/axiom-id-63-3022p.md",
    "v9_axiom_ma-62-2.md": WK / "axenc-pb/reports/axiom-ma-62-2.md",
    "v9_axiom_ca-mpp-snap.md": WK / "axenc-pb/reports/axiom-ca-mpp-snap.md",
    "v9_axiom_us-852-capgain.md": WK / "axenc-pb/reports/axiom-us-852-capgain.md",
    "v9_axiom_nj-43-21-7.md": WK / "axenc-pb/reports/axiom-nj-43-21-7.md",
    "v9_axiom_wi-71-05-54m.md": WK / "axenc-pb/reports/axiom-wi-71-05-54m.md",
    "v9_axiom_ny-606e.md": WK / "axenc-pb/reports/axiom-ny-606e.md",
    "v9_axiom_us-2014-sua.md": WK / "axenc-pb/reports/axiom-us-2014-sua.md",
}


def recorded_fixes(causes: dict) -> tuple[dict[str, str], dict[str, str]]:
    source = (HERE / "build_records.py").read_text()
    sweep_for = dict(re.findall(r'"(r\d\d_[a-z0-9_]+)": "([a-z0-9_]+)"', source.split("MEASURED_BY")[0]))
    measured_by = dict(re.findall(r'"(r\d\d_[a-z0-9_]+)": "([a-z0-9_]+)"', source.split("MEASURED_BY = {")[1].split("}")[0]))
    return sweep_for, measured_by


def sweep_moves(causes: dict, sweep_for: dict, measured_by: dict) -> pd.DataFrame:
    rows = []
    entries = [(k, causes[k]["class"], v) for k, v in sweep_for.items() if k in causes]
    entries += [(k, "convention", v["fix"]) for k, v in causes.items() if isinstance(v, dict) and v.get("class") == "convention"]
    entries += [("r18_hold_all_projections", "screen", "r18_hold_all_projections")]
    # A defect measured on top of a combination of sources that is not itself a
    # convention (r32: the WI convention plus #8839) gets that combination's own
    # rows, class "baseline", so its baseline values can be checked.
    convention_fixes = {v["fix"] for v in causes.values() if isinstance(v, dict) and v.get("class") == "convention"}
    for cause, measured in measured_by.items():
        base = MEASUREMENTS[measured][0]
        if base not in convention_fixes:
            entries.append((causes[cause]["measured_against"], "baseline", base))
    for cause, klass, fix in entries:
        measured = measured_by.get(cause)
        frame = pd.read_csv(OUT / f"{measured or fix}.csv")
        baseline = frame["baseline"] if measured else frame["frozen"]
        delta = frame["recomputed"] - baseline
        for i in frame.index[delta.abs() > 1e-6]:
            r = frame.loc[i]
            rows.append({
                "root_cause": cause,
                "class": klass,
                "fix_module": f"{fix}.py",
                "measured_against": causes[cause]["measured_against"] if measured else "frozen",
                "scenario_id": r["scenario_id"],
                "state": r["state"],
                "variable": r["variable"],
                "frozen": round(float(r["frozen"]), 6),
                "baseline": round(float(baseline[i]), 6),
                "recomputed": round(float(r["recomputed"]), 6),
                "delta": round(float(delta[i]), 6),
                "moved_over_1": bool(r["moved"]),
            })
    return pd.DataFrame(rows).sort_values(["root_cause", "scenario_id", "variable"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", type=Path, default=DEST)
    args = parser.parse_args()
    dest = args.dest
    causes = json.loads((HERE / "root_causes.json").read_text())
    sweep_for, measured_by = recorded_fixes(causes)

    if (dest / "fixes").exists():
        shutil.rmtree(dest / "fixes")
    for sub in ("fixes", "scripts", "verification"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
    modules = set(f"{v}.py" for v in sweep_for.values())
    modules |= {f"{v['fix']}.py" for v in causes.values() if isinstance(v, dict) and v.get("class") == "convention"}
    modules |= set(EXTRA_FIXES)
    for name in sorted(modules):
        shutil.copy2(FIXES / name, dest / "fixes" / name)
    shutil.copy2(HERE / "root_causes.json", dest / "root_causes.json")
    for script in SCRIPTS:
        shutil.copy2(script, dest / "scripts" / script.name)
    missing = []
    for name, source in VERIFICATION.items():
        if source.exists():
            shutil.copy2(source, dest / "verification" / name)
        else:
            missing.append(name)
    moves = sweep_moves(causes, sweep_for, measured_by)
    moves.to_csv(dest / "sweep_moves.csv", index=False)
    shutil.copy2(OUT / "snap_net_income_sensitivity.csv", dest / "snap_net_income_sensitivity.csv")
    print(f"{len(modules)} fix files, {len(moves)} sweep rows, verification missing: {missing}")


if __name__ == "__main__":
    main()
