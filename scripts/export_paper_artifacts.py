"""Freeze current benchmark outputs into stable paper-export tables."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "results" / "paper_exports"

US_ANALYSIS_DIR = ROOT / "results" / "full_batch_20260329_1000" / "analysis"
UK_ANALYSIS_DIR = ROOT / "results" / "uk_full_batch_20260329_1000" / "analysis"


def export_csv(source: Path, destination_name: str) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Expected artifact at {source}")
    frame = pd.read_csv(source)
    destination = EXPORT_DIR / destination_name
    frame.to_csv(destination, index=False)
    print(f"Wrote {destination}")


def build_snapshot_metadata() -> dict:
    us_models = pd.read_csv(US_ANALYSIS_DIR / "summary_by_model.csv")
    uk_models = pd.read_csv(UK_ANALYSIS_DIR / "summary_by_model.csv")

    global_source = ROOT / "app" / "src" / "data.json"
    global_models: list[dict] = []
    if global_source.exists():
        payload = json.loads(global_source.read_text())
        global_models = payload["global"]["modelStats"]

    def top_model(frame: pd.DataFrame) -> dict:
        row = frame.sort_values("mean_score", ascending=False).iloc[0]
        return {
            "model": str(row["model"]),
            "score": round(float(row["mean_score"]) * 100, 2),
            "parsed_n": int(row["parsed_n"]),
            "total_n": int(row["total_n"]),
        }

    snapshot = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_name": "PolicyBench",
        "leaderboard_policy": {
            "paper_exports_are_frozen_snapshots": True,
            "live_site_may_change_after_export": True,
            "reference_outputs_term": "PolicyEngine reference outputs",
        },
        "sources": {
            "us_analysis_dir": str(US_ANALYSIS_DIR),
            "uk_analysis_dir": str(UK_ANALYSIS_DIR),
            "global_payload": str(global_source),
        },
        "countries": {
            "us": {
                "run_id": US_ANALYSIS_DIR.parent.name,
                "top_model": top_model(us_models),
                "models": int(len(us_models)),
            },
            "uk": {
                "run_id": UK_ANALYSIS_DIR.parent.name,
                "top_model": top_model(uk_models),
                "models": int(len(uk_models)),
            },
        },
        "global": {
            "shared_models": int(len(global_models)),
            "top_model": (global_models[0] if global_models else None),
        },
        "notes": [
            "Paper tables are frozen from the run directories above.",
            "PolicyEngine outputs are benchmark reference outputs, not administrative ground truth.",
            "Diagnostic runs are excluded from leaderboard scoring.",
        ],
    }
    return snapshot


def main() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    export_csv(US_ANALYSIS_DIR / "summary_by_model.csv", "us_summary_by_model.csv")
    export_csv(US_ANALYSIS_DIR / "summary_by_variable.csv", "us_summary_by_variable.csv")
    export_csv(US_ANALYSIS_DIR / "usage_summary.csv", "us_usage_summary.csv")

    export_csv(UK_ANALYSIS_DIR / "summary_by_model.csv", "uk_summary_by_model.csv")
    export_csv(UK_ANALYSIS_DIR / "summary_by_variable.csv", "uk_summary_by_variable.csv")
    export_csv(UK_ANALYSIS_DIR / "usage_summary.csv", "uk_usage_summary.csv")

    global_source = ROOT / "app" / "src" / "data.json"
    if global_source.exists():
        payload = json.loads(global_source.read_text())
        global_models = pd.DataFrame(payload["global"]["modelStats"])
        global_models.to_csv(EXPORT_DIR / "global_summary_by_model.csv", index=False)
        print(f"Wrote {EXPORT_DIR / 'global_summary_by_model.csv'}")

    snapshot = build_snapshot_metadata()
    snapshot_path = EXPORT_DIR / "benchmark_snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2) + "\n")
    print(f"Wrote {snapshot_path}")


if __name__ == "__main__":
    main()
