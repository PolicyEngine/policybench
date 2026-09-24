"""Measure defects on top of the value that would otherwise be published.

The SNAP convention (c_snap_hold_fy2026, fix r13_hold_fy2026_v3) regenerates SNAP
references with the FY2026 schedule held for October-December. The engine's SNAP
defects (r26, r27, r28, r30, r31, r33) are measured against that convention's value:
an output is moved when the convention plus the defect's fix differs from the
convention alone by more than $1 (a binary output: when the flag flips). The
Wisconsin defect r32 only matters once #8839 puts the distributions in federal
AGI, so it is measured against the Wisconsin convention plus the #8839 backport
(cwi_plus_r04). Reads the sweeps in sweep/out/ and writes:

  sweep/out/<defect>_on_<base>.csv      frozen, baseline, recomputed, delta, moved
  sweep/out/snap_net_income_sensitivity.csv
      the convention with r26 and r28 applied under three net-income procedures
      (the engine's floor, nearest dollar, cents kept) in every state, against
      the convention alone
  sweep/out/r30_on_published_snap.csv, sweep/out/r33_on_published_snap.csv
      r30 and r33 against the convention with every upstream SNAP fix, the SNAP
      value actually published: a check that each moves the same outputs either
      way

Run after the sweeps (./run_one.sh <fix> for r13_hold_fy2026_v3, c13v3_plus_r26,
c13v3_plus_r27, c13v3_plus_r28, c13v3_plus_r30, c13v3_plus_r31, c13v3_plus_r33,
c13v3_r26_r28, c13v3_r28_r29n, c13v3_r28_r29c, c13v3_plus_upstream_snap,
c13v3_upstream_plus_r30, c13v3_upstream_plus_r33, cwi_plus_r04, cwi_plus_r04_r32):

  python3 make_on_convention.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent / "sweep" / "out"
KEY = ["scenario_id", "variable"]
# output name: (baseline sweep, baseline plus the defect's fix)
MEASUREMENTS = {
    "r26_on_c13v3": ("r13_hold_fy2026_v3", "c13v3_plus_r26"),
    "r27_on_c13v3": ("r13_hold_fy2026_v3", "c13v3_plus_r27"),
    "r28_on_c13v3": ("r13_hold_fy2026_v3", "c13v3_plus_r28"),
    "r30_on_c13v3": ("r13_hold_fy2026_v3", "c13v3_plus_r30"),
    "r31_on_c13v3": ("r13_hold_fy2026_v3", "c13v3_plus_r31"),
    "r33_on_c13v3": ("r13_hold_fy2026_v3", "c13v3_plus_r33"),
    "r32_on_cwi_r04": ("cwi_plus_r04", "cwi_plus_r04_r32"),
    "r30_on_published_snap": ("c13v3_plus_upstream_snap", "c13v3_upstream_plus_r30"),
    "r33_on_published_snap": ("c13v3_plus_upstream_snap", "c13v3_upstream_plus_r33"),
}
PROCEDURES = {
    "floor": "c13v3_r26_r28",
    "nearest": "c13v3_r28_r29n",
    "cents": "c13v3_r28_r29c",
}


def main() -> None:
    for name, (base, combined) in MEASUREMENTS.items():
        baseline = pd.read_csv(OUT / f"{base}.csv").set_index(KEY)
        frame = pd.read_csv(OUT / f"{combined}.csv").set_index(KEY)
        out = pd.DataFrame(index=frame.index)
        out["state"] = frame["state"]
        out["frozen"] = frame["frozen"]
        out["baseline"] = baseline["recomputed"]
        out["recomputed"] = frame["recomputed"]
        out["delta"] = out["recomputed"] - out["baseline"]
        binary = out.index.get_level_values("variable").str.endswith("_eligible")
        out["moved"] = out["delta"].abs() > 1
        out.loc[binary, "moved"] = out.loc[binary, "delta"] != 0
        out.reset_index().to_csv(OUT / f"{name}.csv", index=False)
        print(name, int(out["moved"].sum()), f"moved on top of {base}")
    convention = pd.read_csv(OUT / "r13_hold_fy2026_v3.csv").set_index(KEY)

    table = pd.DataFrame(index=convention.index)
    table["state"] = convention["state"]
    table["convention"] = convention["recomputed"]
    for name, fix in PROCEDURES.items():
        table[name] = pd.read_csv(OUT / f"{fix}.csv").set_index(KEY)["recomputed"]
    changed = (
        table[list(PROCEDURES)].sub(table["convention"], axis=0).abs().max(axis=1)
        > 1e-6
    )
    table = table[changed]
    table.reset_index().to_csv(OUT / "snap_net_income_sensitivity.csv", index=False)
    print(len(table), "outputs differ from the convention under some procedure")


if __name__ == "__main__":
    main()
