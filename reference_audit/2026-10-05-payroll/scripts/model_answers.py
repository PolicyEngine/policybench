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

Reads the pass's inputs from git, never from the working tree: the published payload
as PASS_COMMIT (release dashboard-data-20260930, #187) holds it, and this audit's
decomposition and classification as AUDIT_COMMIT (#202, which merged this audit)
holds them. Each must match its pinned sha256 in INPUTS, or the script stops before
writing anything. Release dashboard-data-20261006 (#202) excluded the four outputs,
so its payload marks their rows unscored and the answers table would change.

  PYTHONPATH=<checkout> <policybench venv>/bin/python \\
    reference_audit/2026-10-05-payroll/scripts/model_answers.py

``--out-dir`` writes model_answers.csv and model_answers_summary.json elsewhere;
tests/test_reference_audit_pins.py regenerates them that way and requires the
committed ones byte for byte.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import subprocess
from pathlib import Path

import pandas as pd

from policybench.analysis import row_hit_scores

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT = HERE / "verification"
OUTPUT = "payroll_tax"
# The pass's inputs, pinned by commit and sha256.
PASS_COMMIT = "8b4c0ca146bb6f66deba6ce24009d49d70d92df2"
AUDIT_COMMIT = "9ce4ade8382962a9134860c23f56d92509b5e57f"
RUN_PATH = (
    "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
AUDIT_PATH = "reference_audit/2026-10-05-payroll"
DECOMPOSITION_PATH = f"{AUDIT_PATH}/verification/payroll_decomposition.csv"
CLASSIFICATION_PATH = f"{AUDIT_PATH}/program_classification.json"
# Every file the script reads from the repository: path -> (commit, sha256).
INPUTS = {
    f"{RUN_PATH}/data.json.gz": (
        PASS_COMMIT,
        "1e029aaa87d1dfbd2ceee88419599a919dd7c9d4aba78a308ec48d008d54ae18",
    ),
    DECOMPOSITION_PATH: (
        AUDIT_COMMIT,
        "fa34d6d98b7ea5fa00023ed93946948e48ea728e45702cea222355e008be9cab",
    ),
    CLASSIFICATION_PATH: (
        AUDIT_COMMIT,
        "282cbf25ce9110a3c5c51873b7ca0e89f1f5ed38592b0c5b51d393f08000089a",
    ),
}


def git_bytes(commit: str, path: str, pinned: str) -> bytes:
    """``path`` as ``commit`` holds it, refusing any other bytes."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{path}"],
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit(
            f"cannot read {path} at {commit[:12]}; fetch full history "
            f"(git fetch --unshallow): {result.stderr.decode().strip()}"
        )
    digest = hashlib.sha256(result.stdout).hexdigest()
    if digest != pinned:
        raise SystemExit(
            f"{commit[:12]}:{path} has sha256 {digest}, not the pinned {pinned}"
        )
    return result.stdout


def pass_input(path: str) -> bytes:
    """The input at ``path``, as INPUTS pins it."""
    commit, pinned = INPUTS[path]
    return git_bytes(commit, path, pinned)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        default=str(OUT),
        help="where to write the answer tables (default: %(default)s)",
    )
    out_dir = Path(parser.parse_args().out_dir)
    # Check every pin before reading anything, so a refused input writes nothing.
    for path in INPUTS:
        pass_input(path)
    payload = json.loads(gzip.decompress(pass_input(f"{RUN_PATH}/data.json.gz")))
    decomposition = pd.read_csv(io.BytesIO(pass_input(DECOMPOSITION_PATH)))
    classification = json.loads(pass_input(CLASSIFICATION_PATH))
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
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_dir / "model_answers.csv", index=False)
    (out_dir / "model_answers_summary.json").write_text(
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
