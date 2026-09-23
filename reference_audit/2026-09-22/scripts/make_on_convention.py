"""Measure the SNAP rounding defects on top of the SNAP publication convention.

The SNAP convention (c_snap_hold_fy2026, fix r13_hold_fy2026_v3) regenerates SNAP
references with the FY2026 schedule held for October-December. The engine's SNAP
defects (r26, r27, r28, r30, r31) are measured against that convention's value,
since it is the value that would otherwise be published: an output is moved when
the convention plus the defect's fix differs from the convention alone by more
than $1. Reads the sweeps in sweep/out/ and writes:

  sweep/out/<defect>_on_c13v3.csv       frozen, convention, recomputed, delta, moved
  sweep/out/snap_net_income_sensitivity.csv
      the convention with r26 and r28 applied under three net-income procedures
      (the engine's floor, nearest dollar, cents kept) in every state, against
      the convention alone

Run after the sweeps (./run_one.sh <fix> for r13_hold_fy2026_v3, c13v3_plus_r26,
c13v3_plus_r27, c13v3_plus_r28, c13v3_plus_r30, c13v3_plus_r31, c13v3_r26_r28,
c13v3_r28_r29n, c13v3_r28_r29c):

  python3 make_on_convention.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent / "sweep" / "out"
KEY = ["scenario_id", "variable"]
DEFECTS = {
    "r26": "c13v3_plus_r26",
    "r27": "c13v3_plus_r27",
    "r28": "c13v3_plus_r28",
    "r30": "c13v3_plus_r30",
    "r31": "c13v3_plus_r31",
}
PROCEDURES = {
    "floor": "c13v3_r26_r28",
    "nearest": "c13v3_r28_r29n",
    "cents": "c13v3_r28_r29c",
}


def main() -> None:
    convention = pd.read_csv(OUT / "r13_hold_fy2026_v3.csv").set_index(KEY)
    for defect, combined in DEFECTS.items():
        frame = pd.read_csv(OUT / f"{combined}.csv").set_index(KEY)
        out = pd.DataFrame(index=frame.index)
        out["state"] = frame["state"]
        out["frozen"] = frame["frozen"]
        out["convention"] = convention["recomputed"]
        out["recomputed"] = frame["recomputed"]
        out["delta"] = out["recomputed"] - out["convention"]
        out["moved"] = out["delta"].abs() > 1
        out.reset_index().to_csv(OUT / f"{defect}_on_c13v3.csv", index=False)
        print(defect, int(out["moved"].sum()), "moved on top of the convention")

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
