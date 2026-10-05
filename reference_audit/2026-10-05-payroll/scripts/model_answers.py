"""Score every model's answer on each payroll_tax output that carries a state component.

Reads the published payload's scenarioPredictions for payroll_tax and scores each answer
with ``policybench.analysis.row_hit_scores`` (the $1 exact tolerance and the 1/5/10%
bands the board uses) against two references:

``published``
    The frozen reference: federal employee payroll tax plus every state program
    policyengine-us 2.15.17 puts in ``employee_state_payroll_tax``.
``no_optional``
    The frozen reference less the state programs classified in
    ``program_classification.json`` as optional employer pass-through (the employer may,
    but need not, deduct the employee share from wages).
``federal_only``
    Employee Social Security, Medicare and Additional Medicare Tax alone.

The published-reference scores must equal the payload's own per-row ``exact`` field; the
script stops if any differs.

  PYTHONPATH=<checkout> <policybench venv>/bin/python \\
    reference_audit/2026-10-05-payroll/scripts/model_answers.py
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pandas as pd

from policybench.analysis import row_hit_scores

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
OUT = HERE / "verification"
OUTPUT = "payroll_tax"


def main() -> None:
    payload = json.loads(gzip.decompress((RUN / "data.json.gz").read_bytes()))
    decomposition = pd.read_csv(OUT / "payroll_decomposition.csv")
    classification = json.loads((HERE / "program_classification.json").read_text())
    optional = {
        leaf
        for program in classification["programs"]
        if program["classification"] == "optional_employer_pass_through"
        for leaf in program["engine_variables"]
    }
    affected = decomposition[decomposition["employee_state_payroll_tax"].abs() > 0]

    rows = []
    summary = []
    for _, d in affected.iterrows():
        sid = d["scenario_id"]
        leaves = dict(
            (k, float(v))
            for k, v in (
                item.split("=") for item in str(d["state_programs"]).split(";") if item
            )
        )
        optional_amount = sum(v for k, v in leaves.items() if k in optional)
        references = {
            "published": float(d["reference"]),
            "no_optional": float(d["reference"]) - optional_amount,
            "federal_only": float(d["federal_total"]),
        }
        predictions = payload["scenarioPredictions"][sid][OUTPUT]
        counts = {name: 0 for name in references}
        within1 = {name: 0 for name in references}
        for model, cell in sorted(predictions.items()):
            if abs(cell["groundTruth"] - references["published"]) > 1e-3:
                raise SystemExit(f"{sid}: payload groundTruth differs from the CSV")
            pred = cell["prediction"] if cell["parsed"] else None
            row = {
                "scenario_id": sid,
                "state": d["state"],
                "model": model,
                "prediction": pred,
                "scored": cell["scored"],
            }
            for name, ref in references.items():
                hit = row_hit_scores(OUTPUT, ref, pred)
                row[f"exact_{name}"] = hit["exact"]
                row[f"within1pct_{name}"] = hit["within_1pct"]
                counts[name] += int(hit["exact"])
                within1[name] += int(hit["within_1pct"])
            if abs(row["exact_published"] * 100 - cell["exact"]) > 1e-9:
                raise SystemExit(f"{sid}/{model}: exact differs from the payload")
            rows.append(row)
        n = len(predictions)
        frame = pd.DataFrame([r for r in rows if r["scenario_id"] == sid])
        answered = frame["prediction"].dropna().round(2).value_counts()
        summary.append(
            {
                "scenario_id": sid,
                "state": d["state"],
                "scored": bool(not d["excluded"]),
                "state_programs": d["state_programs"],
                "optional_amount": round(optional_amount, 2),
                "reference_published": round(references["published"], 2),
                "reference_no_optional": round(references["no_optional"], 2),
                "reference_federal_only": round(references["federal_only"], 2),
                "models": n,
                "exact_published": counts["published"],
                "exact_no_optional": counts["no_optional"],
                "exact_federal_only": counts["federal_only"],
                "within1pct_published": within1["published"],
                "within1pct_no_optional": within1["no_optional"],
                "within1pct_federal_only": within1["federal_only"],
                "modal_answers": {
                    f"{value:.2f}": int(count)
                    for value, count in answered.head(4).items()
                },
            }
        )
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "model_answers.csv", index=False)
    (OUT / "model_answers_summary.json").write_text(
        json.dumps({"outputs": summary}, indent=2) + "\n"
    )
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(
            pd.DataFrame(summary).drop(columns=["modal_answers"]).to_string(index=False)
        )
    for item in summary:
        print(item["scenario_id"], item["modal_answers"])


if __name__ == "__main__":
    main()
