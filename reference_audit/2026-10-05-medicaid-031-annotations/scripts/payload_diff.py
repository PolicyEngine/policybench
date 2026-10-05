"""Show that the rewrites change no published score: rebuild the payload both ways and diff.

Copies the frozen run's reference files and predictions into two scratch bundles (it never
writes the snapshot), one with the annotation files as committed at ``--base`` and one with
the working tree's, and runs ``policybench.full_run_export.export_country`` on each, the
export the release drivers run. It writes ``verification/payload_diff.json``: every payload
path that differs between the two rebuilds, and every path where the base rebuild differs
from the frozen payload (data.json.gz).

  uv run python reference_audit/2026-10-05-medicaid-031-annotations/scripts/payload_diff.py \\
      --base origin/main --scratch <dir>
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RUN_NAME = "us_full_run_20260612_policyengine_4_16_1_populace"
RUN = ROOT / "paper/snapshot/20260501/runs" / RUN_NAME
ANNOTATIONS = f"annotations/{RUN_NAME}"
RUN_FILES = (
    "reference_outputs.csv",
    "reference_outputs.csv.meta.json",
    "reference_exclusions.json",
    "scenarios.csv",
    "scenarios.csv.meta.json",
    "predictions.csv.gz",
)
ANNOTATION_FILES = (
    "us_audit_row_annotations.csv",
    "us_case_notes.csv",
    "us_case_reference_explanations.csv",
)


def _diff(a, b, path, out) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b), key=str):
            _diff(a.get(key, "<missing>"), b.get(key, "<missing>"), [*path, key], out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            _diff(x, y, [*path, i], out)
    elif a != b and not (isinstance(a, float) and isinstance(b, float) and a != a and b != b):
        out.append(path)


def main() -> None:
    from policybench.full_run_export import committed_reference_digest, export_country

    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--scratch", required=True, type=Path)
    args = parser.parse_args()

    digest = committed_reference_digest("us")
    payloads = {}
    for label in ("base", "working_tree"):
        bundle = args.scratch / label
        shutil.rmtree(bundle, ignore_errors=True)
        (bundle / "us").mkdir(parents=True)
        (bundle / "annotations").mkdir()
        for name in RUN_FILES:
            shutil.copy2(RUN / name, bundle / "us" / name)
        for name in ANNOTATION_FILES:
            target = bundle / "annotations" / name
            if label == "base":
                target.write_bytes(
                    subprocess.run(
                        ["git", "-C", str(ROOT), "show", f"{args.base}:{ANNOTATIONS}/{name}"],
                        capture_output=True,
                        check=True,
                    ).stdout
                )
            else:
                shutil.copy2(ROOT / ANNOTATIONS / name, target)
        payloads[label] = export_country(bundle / "us", reference_digest=digest)

    changed: list[list] = []
    _diff(payloads["base"], payloads["working_tree"], [], changed)
    frozen = json.loads(gzip.open(RUN / "data.json.gz").read())
    reproduction: list[list] = []
    _diff(frozen, payloads["base"], [], reproduction)
    stats = payloads["base"]["modelStats"]

    def label(path):
        if path and path[0] == "modelStats":
            return ["modelStats", stats[path[1]]["model"], *path[2:]]
        return path

    sections = sorted({str(p[0]) for p in changed})
    cells = sorted({(p[1], p[2]) for p in changed if p[0] == "scenarioPredictions"})
    fields = sorted({str(p[-1]) for p in changed})
    record = {
        "note": (
            "Payload rebuilt from the frozen run by export_country with the base's "
            "annotation files and with the working tree's. 'changed' lists every path "
            "that differs between the two rebuilds. 'base_vs_frozen' lists every path "
            "where the base rebuild differs from the frozen data.json.gz: claude-fable-5's "
            "usage, which the release drivers carry from the published payload "
            "(CARRIED_USAGE in scripts/finish_gpt61sol.py) because export cannot "
            "recompute it."
        ),
        "base": args.base,
        "changed_sections": sections,
        "changed_cells": [list(c) for c in cells],
        "changed_fields": fields,
        "changed_paths": len(changed),
        "changed_by_field": {f: sum(1 for p in changed if p[-1] == f) for f in fields},
        "base_vs_frozen": [[str(x) for x in label(p)] for p in reproduction],
    }
    out = HERE / "verification/payload_diff.json"
    out.write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps(record, indent=1))
    assert sections == ["scenarioPredictions"], sections
    assert cells == [("scenario_031", "head_medicaid_eligible")], cells
    assert set(fields) <= {"annotation", "caseAnnotation", "referenceExplanation"}, fields
    assert {p[1] for p in reproduction} <= {
        i for i, s in enumerate(stats) if s["model"] == "claude-fable-5"
    }, reproduction


if __name__ == "__main__":
    main()
