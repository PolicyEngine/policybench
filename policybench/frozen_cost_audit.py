"""Inventory retained release cost provenance without reconstructing missing calls."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from policybench.cost_publication import (
    render_markdown_report,
    validate_cost_publication,
)
from policybench.snapshot_payload import read_run_payload, run_payload_path


def _retained_amount(value) -> str | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return str(amount) if amount.is_finite() and amount >= 0 else None


def audit_frozen_costs(run_dir: str | Path) -> dict:
    """Return a hashed inventory, explicitly incomplete contract, and validation.

    Recorded aggregates remain verbatim diagnostic fields. No aggregate becomes
    a physical-call receipt, no pricecard is inferred, and no reference output
    or model response is recalculated. Any discovered ledger needs a separately
    evidenced complete contract before validation can accept it.
    """
    run_dir = Path(run_dir)
    payload_path = run_payload_path(run_dir)
    payload = read_run_payload(run_dir)
    rows = [row for row in payload["modelStats"] if row["condition"] == "no_tools"]
    models = sorted(row["model"] for row in rows)
    if not models or len(models) != len(set(models)):
        raise ValueError("Expected a nonempty, unique no-tools model roster.")
    if not isinstance(payload["scenarios"], dict) or not payload["scenarios"]:
        raise ValueError("Expected a nonempty scenario mapping in the frozen payload.")
    usage_path = run_dir / "analysis/usage_summary.csv"
    usage = {}
    if usage_path.exists():
        with usage_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["model"] in usage:
                    raise ValueError("Duplicate model in retained usage summary.")
                usage[row["model"]] = row
    ledger_paths = sorted(run_dir.rglob("*.spend.jsonl"))
    source_paths = [
        payload_path,
        *([usage_path] if usage_path.exists() else []),
        *ledger_paths,
    ]
    artifacts = [
        {
            "path": str(path.relative_to(run_dir)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in source_paths
    ]
    inventory = {
        "inventory_version": 1,
        "run_id": run_dir.name,
        "scenario_count": len(payload["scenarios"]),
        "artifacts": artifacts,
        "ledger_files": [str(path.relative_to(run_dir)) for path in ledger_paths],
        "models": {},
        "scope": "This retained bundle only; other original run directories may "
        "contain evidence that requires separate recovery and review.",
    }
    for row in rows:
        name = row["model"]
        recorded = usage.get(name, {})
        total = _retained_amount(recorded.get("total_cost_usd"))
        provider = _retained_amount(recorded.get("total_provider_reported_cost_usd"))
        reconstructed = _retained_amount(recorded.get("total_reconstructed_cost_usd"))
        carried = _retained_amount(row.get("costUsd"))
        if total is None:
            provenance = "aggregate_only" if carried is not None else "unknown"
        elif provider is not None and reconstructed is not None:
            provenance = "mixed_prediction_row_cost_fields"
        elif reconstructed is not None:
            provenance = "reconstructed_prediction_rows"
        elif provider is not None:
            provenance = "provider_reported_prediction_rows"
        else:
            provenance = "unattributed_prediction_rows"
        inventory["models"][name] = {
            "provenance": provenance,
            "legacy_payload_cost_usd": carried,
            "legacy_usage_total_usd": total,
            "legacy_provider_reported_subtotal_usd": provider,
            "legacy_reconstructed_subtotal_usd": reconstructed,
            "legacy_estimated_cost_rows": recorded.get("estimated_cost_rows"),
            "unknown_usage_fields": [
                field
                for field in (
                    "prompt_tokens",
                    "completion_tokens",
                    "reasoning_tokens",
                    "cached_prompt_tokens",
                    "cache_write_prompt_tokens",
                )
                if _retained_amount(recorded.get(field)) is None
            ],
            "billing_evidence": "unknown",
            "normalized_sync_basis": "unknown",
            "publication_eligible": False,
        }
    reason = (
        "The frozen bundle contains no physical-call ledger. Missing attempts "
        "are unrecoverable from its prediction rows and aggregates; contemporaneous "
        "evidence elsewhere has not been assessed."
        if not ledger_paths
        else "Ledgers exist, but complete attempt history, dated pricing, "
        "billing receipts, and recipe identity need a separately frozen contract."
    )
    contract = {
        "schema_version": 1,
        "run_id": run_dir.name,
        "evidence_kind": "retained",
        "metric": "operational_workflow_sync_uncached_v1",
        "pricing_date": None,
        "displayed_models": models,
        "scenario_ids": sorted(payload["scenarios"]),
        "history": {
            "status": "unknown" if ledger_paths else "unrecoverable",
            "evidence": {
                "reference": artifacts[0]["path"],
                "sha256": artifacts[0]["sha256"],
            },
            "reason": reason,
        },
        "recipes": {},
        "pricecards": {},
        "calls": {},
        "models": {
            name: {
                "model_id": None,
                "recipe_id": None,
                "pricecard_id": None,
                "expected_call_keys": [],
                "totals": {
                    "physical_requests": None,
                    "actual_billed_usd": None,
                    "normalized_sync_usd": None,
                },
            }
            for name in models
        },
    }
    return {
        "inventory": inventory,
        "contract": contract,
        "validation": validate_cost_publication(contract, []),
    }


def main(argv: list[str] | None = None) -> int:
    """Write an internal audit outside the input bundle; always exit ineligible."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output_dir.resolve().is_relative_to(args.run_dir.resolve()):
        parser.error("Write audit artifacts outside the frozen input bundle.")
    result = audit_frozen_costs(args.run_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in result.items():
        (args.output_dir / f"{name}.json").write_text(
            json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    report = render_markdown_report(result["validation"])
    report += "\n## Retained aggregate provenance\n\n"
    report += "These labels describe retained fields, not audited billing.\n\n"
    report += "| Model | Provenance | Legacy payload USD |\n| --- | --- | ---: |\n"
    for model, row in sorted(result["inventory"]["models"].items()):
        model = model.replace("|", "\\|").replace("\n", " ")
        report += (
            f"| {model} | {row['provenance']} | "
            f"{row['legacy_payload_cost_usd'] or 'unknown'} |\n"
        )
    (args.output_dir / "report.md").write_text(report, encoding="utf-8")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
