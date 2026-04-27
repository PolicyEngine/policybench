"""Generate paper-ready derived artifacts from frozen benchmark exports.

This scaffold intentionally stays lightweight. It currently writes a small
manifest that future figure code can build on once we decide on the exact
plots for the manuscript.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "results" / "temporary_legacy_v1_results" / "paper_exports"
FIGURES_DIR = ROOT / "paper" / "figures"


def load_optional_csv(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    frame = pd.read_csv(path)
    return {
        "path": str(path.relative_to(ROOT)),
        "rows": int(len(frame)),
        "columns": frame.columns.tolist(),
    }


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {
        "exports": {
            "us_summary_by_model": load_optional_csv(
                EXPORT_DIR / "us_summary_by_model.csv"
            ),
            "uk_summary_by_model": load_optional_csv(
                EXPORT_DIR / "uk_summary_by_model.csv"
            ),
            "global_summary_by_model": load_optional_csv(
                EXPORT_DIR / "global_summary_by_model.csv"
            ),
            "us_summary_by_variable": load_optional_csv(
                EXPORT_DIR / "us_summary_by_variable.csv"
            ),
            "uk_summary_by_variable": load_optional_csv(
                EXPORT_DIR / "uk_summary_by_variable.csv"
            ),
        }
    }

    output_path = FIGURES_DIR / "manifest.json"
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
