"""Summarize what each sweep re-run on policyengine-us 2.15.17 moves.

On 2.15.17 PolicyBench re-ran four of the September 22 sweeps over every output
(the IRA deduction limit fix r02, the net investment income tax definition r25,
and the readings for mortgage residence and 40 unlisted weekly hours) and ran a
new one for the state and local tax refund reading. Each sweep adds one fix or
reading to a baseline sweep:

- latest_conventions: the nine ported publication conventions
  (fixes/latest_conventions.py);
- latest_map_stated_hours: the same, with each prompt's stated usual weekly
  hours also passed to weekly_hours_worked_before_lsr, as the scenario builder
  now does for the references (fixes/latest_map_stated_hours.py). The 40-hour
  sweep composes it (fixes/latest_alt_unlisted_hours_40.py).

This script reads the sweeps' CSVs (sweep_latest.py output, one row per output)
from the triage directory and writes verification/rerun_sweeps.json: each
sweep's source hash and module, and every output whose value differs from its
baseline or from latest_conventions by any amount, with the three values. The
tests recompute the claims the README, the card and the paper make from it.

Run from the checkout (the paths are those of the machine that ran the sweeps):

  .venv/bin/python reference_audit/2026-09-28/scripts/summarize_rerun_sweeps.py
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
OUT = Path(
    "/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/sweep/out"
)
TRIAGE = OUT.parents[1]
ENGINE = "2.15.17"
BASELINES = {
    "latest_conventions": {
        "csv": "latest_conventions.csv",
        "module": "fixes/latest_conventions.py",
    },
    "latest_map_stated_hours": {
        "csv": "latest_map_stated_hours.csv",
        "module": "fixes/latest_map_stated_hours.py",
    },
}
SWEEPS = [
    {
        "sweep": "latest_alt_r02_ira_219g",
        "csv": "latest_alt_r02_ira_219g.csv",
        "module": "fixes/latest_alt_r02_ira_219g.py",
        "adds": "the IRA deduction limit fix (IRC 219(g) active-participant "
        "phase-out; reference_audit/2026-09-22/fixes/r02_ira_219g_v2.py)",
        "september_22_root_cause": "r02_ira_219g",
        "baseline": "latest_conventions",
    },
    {
        "sweep": "latest_conventions_plus_r25_niit_excluded",
        "csv": "latest_conventions_r25_niit_excluded.csv",
        "module": "fixes/alt_conventions_r25.py",
        "adds": "the reading of federal income tax before refundable credits "
        "without the net investment income tax "
        "(reference_audit/2026-09-22/fixes/r25_niit_excluded.py)",
        "september_22_root_cause": "r25_niit_in_federal_output",
        "baseline": "latest_conventions",
    },
    {
        "sweep": "latest_alt_snap_mortgage_residence",
        "csv": "latest_alt_snap_mortgage_residence.csv",
        "module": "fixes/latest_alt_snap_mortgage_residence.py",
        "adds": "the reading that listed mortgage interest is on the occupied "
        "home, a SNAP shelter cost",
        "september_22_root_cause": "r15_snap_mortgage_interest",
        "baseline": "latest_conventions",
    },
    {
        "sweep": "latest_alt_unlisted_hours_40",
        "csv": "latest_alt_unlisted_hours_40.csv",
        "module": "fixes/latest_alt_unlisted_hours_40.py",
        "adds": "the reading that a person with no stated weekly hours works 40",
        "september_22_root_cause": "r14_unlisted_weekly_hours_v2",
        "baseline": "latest_map_stated_hours",
    },
    {
        "sweep": "latest_alt_salt_refund_no_prior_benefit",
        "csv": "latest_alt_salt_refund_no_prior_benefit.csv",
        "module": "fixes/latest_alt_salt_refund_no_prior_benefit.py",
        "adds": "the reading that a listed state and local tax refund is not "
        "income (26 U.S.C. 111(a)); new on 2.15.17",
        "september_22_root_cause": None,
        "baseline": "latest_conventions",
    },
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _values(name: str, fix: str | None = None) -> dict[tuple[str, str], float]:
    with (OUT / name).open(newline="") as source:
        rows = list(csv.DictReader(source))
    if len(rows) != 1984 or {r["engine"] for r in rows} != {ENGINE}:
        raise SystemExit(f"{name}: not a full sweep on policyengine-us {ENGINE}")
    if fix is not None and {r["fix"] for r in rows} != {fix}:
        raise SystemExit(f"{name}: not the {fix} sweep")
    return {(r["scenario_id"], r["variable"]): float(r["recomputed"]) for r in rows}


def main() -> None:
    conventions = _values(BASELINES["latest_conventions"]["csv"], "latest_conventions")
    values = {"latest_conventions": conventions}
    baselines = {}
    for name, spec in BASELINES.items():
        values[name] = _values(spec["csv"], name)
        entry = {
            "csv": spec["csv"],
            "csv_sha256": _sha256(OUT / spec["csv"]),
            "module": spec["module"],
            "module_sha256": _sha256(HERE / spec["module"]),
        }
        if name != "latest_conventions":
            entry["differs_from_latest_conventions"] = [
                {
                    "scenario_id": key[0],
                    "variable": key[1],
                    "latest_conventions": conventions[key],
                    name: value,
                }
                for key, value in sorted(values[name].items())
                if value != conventions[key]
            ]
        baselines[name] = entry
    sweeps = []
    for spec in SWEEPS:
        recomputed = _values(spec["csv"], spec["sweep"])
        base = values[spec["baseline"]]
        moves = [
            {
                "scenario_id": key[0],
                "variable": key[1],
                "baseline": base[key],
                "latest_conventions": conventions[key],
                "recomputed": value,
            }
            for key, value in sorted(recomputed.items())
            if value != base[key] or value != conventions[key]
        ]
        sweeps.append(
            {
                **spec,
                "csv_sha256": _sha256(OUT / spec["csv"]),
                "module_sha256": _sha256(HERE / spec["module"]),
                "outputs": len(recomputed),
                "moves": moves,
            }
        )
    record = {
        "note": (
            "What each sweep PolicyBench ran on policyengine-us 2.15.17 for an "
            "exclusion's fix or reading moves, written by "
            "scripts/summarize_rerun_sweeps.py from the sweeps' CSVs in "
            f"{OUT.relative_to(TRIAGE.parent)} (sweep_latest.py output; each "
            "csv_sha256 is the file read). A sweep adds its fix or reading to "
            "its baseline sweep. 'moves' lists every output whose recomputed "
            "value differs, by any amount, from the baseline's or from "
            "latest_conventions'. Every other output of the 1,984 has the same "
            "value in the sweep, its baseline and latest_conventions."
        ),
        "engine": ENGINE,
        "baselines": baselines,
        "sweeps": sweeps,
    }
    path = HERE / "verification" / "rerun_sweeps.json"
    path.write_text(json.dumps(record, indent=2) + "\n")
    for sweep in sweeps:
        print(f"{sweep['sweep']}: {len(sweep['moves'])} outputs differ")


if __name__ == "__main__":
    main()
