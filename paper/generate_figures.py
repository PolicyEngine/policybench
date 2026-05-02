"""Generate paper-ready derived artifacts from the current dashboard data.

This scaffold intentionally stays lightweight. It currently writes a small
manifest that future figure code can build on once we decide on the exact
plots for the manuscript.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DATA = ROOT / "app" / "src" / "data.json"
FIGURES_DIR = ROOT / "paper" / "figures"


def load_dashboard_summary(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    countries = payload.get("countries", {})
    return {
        "path": str(path.relative_to(ROOT)),
        "countries": sorted(countries),
        "global_models": len(payload.get("global", {}).get("modelStats", [])),
        "country_models": {
            country: len(country_payload.get("modelStats", []))
            for country, country_payload in countries.items()
        },
        "country_outputs": {
            country: len(country_payload.get("programStats", []))
            for country, country_payload in countries.items()
        },
    }


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {
        "dashboard": load_dashboard_summary(APP_DATA),
    }

    output_path = FIGURES_DIR / "manifest.json"
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
