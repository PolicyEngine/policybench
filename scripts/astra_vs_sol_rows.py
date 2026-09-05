"""Row-level comparison of GPT-6 Astra and GPT-5.6 Sol on the frozen board.

Writes ``notes/data/astra_vs_sol_20260905.csv``: every scored output one of
the two models gets right and the other misses, with both predictions, the
reference, the judge's row annotation, and a cluster label for Astra's two
repeated mechanisms. ``tests/test_notes.py`` regenerates the rows and
compares, so the note's counts stay tied to the frozen payload.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from policybench.snapshot_payload import read_run_payload

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = (
    ROOT
    / "paper/snapshot/20260501/runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
)
ANNOTATIONS = (
    ROOT
    / "annotations/us_full_run_20260612_policyengine_4_16_1_populace"
    / "us_audit_row_annotations.csv"
)
OUTPUT = ROOT / "notes/data/astra_vs_sol_20260905.csv"
SOL, ASTRA = "gpt-5.6-sol", "gpt-6-astra"

# Astra's two repeated mechanisms, identified from the judge annotations:
# an employer-sponsored insurance premium netted out of wages before a tax
# base, and a disability flag read as Medicare eligibility before 65.
ESI_ROWS = {
    ("scenario_037", "payroll_tax"),
    ("scenario_052", "payroll_tax"),
    ("scenario_064", "payroll_tax"),
    ("scenario_089", "payroll_tax"),
    ("scenario_091", "payroll_tax"),
    ("scenario_093", "payroll_tax"),
    ("scenario_110", "payroll_tax"),
    ("scenario_119", "payroll_tax"),
    ("scenario_120", "payroll_tax"),
    ("scenario_037", "federal_income_tax_before_refundable_credits"),
    ("scenario_089", "federal_income_tax_before_refundable_credits"),
    ("scenario_091", "federal_income_tax_before_refundable_credits"),
    ("scenario_089", "state_income_tax_before_refundable_credits"),
}
# Sol netted the same premium once, on scenario_045 (payroll tax and the
# refundable credits that key off earned income).
SOL_ESI_ROWS = {
    ("scenario_045", "payroll_tax"),
    ("scenario_045", "federal_refundable_credits"),
}
MEDICARE_SCENARIOS = {
    "scenario_008",
    "scenario_015",
    "scenario_027",
    "scenario_039",
    "scenario_074",
    "scenario_075",
    "scenario_079",
    "scenario_088",
    "scenario_093",
    "scenario_111",
    "scenario_116",
}
CLUSTER_ESI = "esi_premium_netted_from_wages"
CLUSTER_MEDICARE = "disability_read_as_medicare"
CLUSTER_OTHER = "other"

FIELDS = [
    "scenario_id",
    "variable",
    "direction",
    "cluster",
    "prediction_astra",
    "prediction_sol",
    "reference",
    "judge_failure_source",
    "judge_failure_subtype",
    "judge_annotation",
]


def _hit(record: dict) -> bool:
    return record.get("exact") == 100


def cluster_for(scenario_id: str, variable: str, direction: str) -> str:
    key = (scenario_id, variable)
    if direction == "astra_only":
        if key in ESI_ROWS:
            return CLUSTER_ESI
        if scenario_id in MEDICARE_SCENARIOS and "medicare" in variable:
            return CLUSTER_MEDICARE
        return CLUSTER_OTHER
    return CLUSTER_ESI if key in SOL_ESI_ROWS else CLUSTER_OTHER


def comparison_rows(payload: dict, annotations: dict) -> list[dict]:
    rows = []
    for scenario_id, variables in payload["scenarioPredictions"].items():
        for variable, models in variables.items():
            astra, sol = models.get(ASTRA), models.get(SOL)
            if not astra or not sol or astra.get("scored") is False:
                continue
            astra_hit, sol_hit = _hit(astra), _hit(sol)
            if astra_hit == sol_hit:
                continue
            direction = "astra_only" if sol_hit else "sol_only"
            judged = annotations.get(
                (ASTRA if direction == "astra_only" else SOL, scenario_id, variable),
                {},
            )
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "variable": variable,
                    "direction": direction,
                    "cluster": cluster_for(scenario_id, variable, direction),
                    "prediction_astra": astra["prediction"],
                    "prediction_sol": sol["prediction"],
                    "reference": astra["groundTruth"],
                    "judge_failure_source": judged.get("failure_source", ""),
                    "judge_failure_subtype": judged.get("failure_subtype", ""),
                    "judge_annotation": judged.get("annotation", ""),
                }
            )
    rows.sort(
        key=lambda row: (
            row["direction"],
            row["cluster"],
            row["scenario_id"],
            row["variable"],
        )
    )
    return rows


def load_annotations(path: Path = ANNOTATIONS) -> dict:
    with path.open(encoding="utf-8", newline="") as source:
        return {
            (row["model"], row["scenario_id"], row["variable"]): row
            for row in csv.DictReader(source)
        }


def main() -> None:
    payload = read_run_payload(RUN_DIR)
    rows = comparison_rows(payload, load_annotations())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as sink:
        writer = csv.DictWriter(sink, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    meta = {
        "release": "dashboard-data-20260905c",
        "source_run": RUN_DIR.name,
        "annotations_sha256": hashlib.sha256(ANNOTATIONS.read_bytes()).hexdigest(),
        "rows": len(rows),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/astra_vs_sol_rows.py",
    }
    OUTPUT.with_suffix(OUTPUT.suffix + ".meta.json").write_text(
        json.dumps(meta, indent=2) + "\n"
    )
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
