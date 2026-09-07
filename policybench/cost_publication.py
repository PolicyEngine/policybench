"""Offline publication accounting over the existing physical-call spend ledger.

This module never imports a provider client, reprices prediction rows, or enables
the public cost UI. The frozen v1 contract and release boundary are documented in
docs/cost_publication.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Iterable

from jsonschema import Draft202012Validator, FormatChecker

from policybench.spend_ledger import (
    _finite_float,
    _reject_constant,
    _strict_object,
    read_spend_ledger,
)

SCHEMA_PATH = Path(__file__).with_name("cost_publication.schema.json")
TOKEN_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "cached_prompt_tokens",
    "cache_write_prompt_tokens",
)
TERMINAL_STATUSES = {"ok", "parse_error", "provider_error"}
RELEASE_BLOCKER = "issue118_release_review_required"


def content_digest(value: dict) -> str:
    """SHA256 of UTF-8, sorted-key, compact, ASCII-escaped, finite JSON (v1)."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return (
        format(value, "f").rstrip("0").rstrip(".")
        if "." in format(value, "f")
        else str(value)
    )


def _number(value) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return Decimal(str(value))


def _issue(report: dict, code: str, path: str, message: str) -> None:
    report["issues"].append({"code": code, "path": path, "message": message})


def _empty_report() -> dict:
    return {
        "report_version": 1,
        "schema_valid": False,
        "validation_passed": False,
        "accounting_eligible": False,
        "public_costs_available": False,
        "publication_blockers": [RELEASE_BLOCKER],
        "issues": [],
        "models": {},
        "calls": {},
        "totals": {},
        "duplicate_records": 0,
        "provenance_limits": [
            "Evidence references and digests are attestations; source authenticity "
            "and historical completeness require independent review.",
            "Accounting eligibility is a necessary condition only. The GPT-5.5 "
            "rerun, historical provenance audit, UI tests, and all-model release "
            "approval in issue118 remain separate gates.",
        ],
    }


def _finish(report: dict, *, synthetic: bool = False) -> dict:
    report["issues"].sort(
        key=lambda item: (item["path"], item["code"], item["message"])
    )
    report["validation_passed"] = report["schema_valid"] and not report["issues"]
    report["accounting_eligible"] = report["validation_passed"] and not synthetic
    report["publication_blockers"] = sorted(
        {RELEASE_BLOCKER, *(item["code"] for item in report["issues"])}
        | ({"synthetic_evidence"} if synthetic else set())
    )
    return report


def _validate_catalogs(contract: dict, report: dict) -> None:
    for catalog in ("recipes", "pricecards"):
        for digest, value in contract[catalog].items():
            path = f"{catalog}/{digest}"
            if content_digest(value) != digest:
                _issue(
                    report, "content_digest_mismatch", path, "Frozen content changed."
                )
            unknown = [key for key, item in value.items() if item is None]
            if unknown:
                _issue(
                    report,
                    "unknown_cost_basis",
                    path,
                    f"Unknown: {', '.join(unknown)}.",
                )
            if catalog == "pricecards":
                if value["captured_on"] != contract["pricing_date"]:
                    _issue(
                        report,
                        "pricing_date_mismatch",
                        path,
                        "Use one snapshot date across models.",
                    )
                if (
                    value["effective_on"]
                    and contract["pricing_date"]
                    and value["effective_on"] > contract["pricing_date"]
                ):
                    _issue(
                        report,
                        "price_not_effective",
                        path,
                        "Price postdates the normalization date.",
                    )
                if value["evidence_kind"] != contract["evidence_kind"]:
                    _issue(
                        report,
                        "mixed_evidence_kind",
                        path,
                        "Synthetic and retained evidence cannot mix.",
                    )


def _index_records(
    records: Iterable[dict], report: dict, validator: Draft202012Validator
) -> dict[str, dict]:
    indexed = {}
    for index, record in enumerate(records):
        path = f"ledger/{index}"
        if not isinstance(record, dict):
            _issue(report, "invalid_ledger_record", path, "Expected a JSON object.")
            continue
        try:
            content_digest(record)
        except (TypeError, ValueError):
            _issue(
                report,
                "invalid_ledger_record",
                path,
                "Record contains invalid JSON values.",
            )
            continue
        key = record.get("call_key")
        if not isinstance(key, str) or not key.strip():
            _issue(
                report,
                "missing_call_key",
                path,
                "Physical calls require stable identities.",
            )
            continue
        errors = list(validator.iter_errors(record))
        if errors:
            for error in errors:
                _issue(report, "invalid_ledger_record", key, error.message)
            continue
        if key in indexed:
            if content_digest(indexed[key]) != content_digest(record):
                _issue(
                    report,
                    "conflicting_call",
                    key,
                    "Duplicate observations disagree; resolve in the source ledger.",
                )
            else:
                report["duplicate_records"] += 1
            continue
        indexed[key] = record
    return indexed


def _normalized_cost(
    record: dict, basis: dict, price: dict | None, report: dict
) -> Decimal | None:
    key = record["call_key"]
    usage = basis["usage_basis"]
    if usage is None:
        _issue(
            report, "unknown_usage_basis", key, "Token inclusion semantics are unknown."
        )
        return None
    unknown = [field for field in TOKEN_FIELDS if record.get(field) is None]
    invalid = [
        field
        for field in TOKEN_FIELDS
        if record.get(field) is not None
        and (type(record[field]) is not int or record[field] < 0)
    ]
    if unknown or invalid:
        _issue(
            report,
            "unknown_usage" if unknown else "invalid_usage",
            key,
            "Token fields need explicit nonnegative integers: "
            f"{', '.join(unknown + invalid)}.",
        )
        return None
    prompt, completion, reasoning, cached, written = (
        record[field] for field in TOKEN_FIELDS
    )
    if usage["prompt_tokens"] == "includes_cache":
        if cached + written > prompt:
            _issue(
                report,
                "inconsistent_usage",
                key,
                "Cache partitions exceed prompt tokens.",
            )
            return None
    else:
        prompt += cached + written
    if usage["completion_tokens"] == "includes_reasoning":
        if reasoning > completion:
            _issue(
                report,
                "inconsistent_usage",
                key,
                "Reasoning exceeds completion tokens.",
            )
            return None
    else:
        completion += reasoning
    total = record.get("total_tokens")
    if total is not None and (
        type(total) is not int
        or total != record["prompt_tokens"] + record["completion_tokens"]
    ):
        _issue(
            report,
            "inconsistent_usage",
            key,
            "Reported total must equal raw prompt plus completion tokens.",
        )
        return None
    if price is None or any(
        price[field] is None
        for field in ("input_per_million_usd", "output_per_million_usd")
    ):
        _issue(
            report,
            "unknown_price",
            key,
            "A complete synchronous pricecard is required.",
        )
        return None
    with localcontext() as context:
        context.prec = 100
        return (
            Decimal(prompt) * Decimal(price["input_per_million_usd"])
            + Decimal(completion) * Decimal(price["output_per_million_usd"])
        ) / 1_000_000


def _actual_cost(
    record: dict, basis: dict, report: dict, evidence_kind: str
) -> Decimal | None:
    billed = basis["billed_cost"]
    key = record["call_key"]
    amount = Decimal(billed["amount_usd"]) if billed["amount_usd"] is not None else None
    source = billed["source"]
    if amount is None or source == "unknown":
        _issue(
            report,
            "unknown_billed_cost",
            key,
            "List prices and carried totals are not billing evidence.",
        )
        return None
    if source == "local_cache":
        if record.get("cache_hit") is not True or amount != 0:
            _issue(
                report,
                "invalid_cache_billing",
                key,
                "Only a verified local replay has zero local-cache billing.",
            )
            return None
    elif billed["evidence"] is None:
        _issue(
            report,
            "missing_billing_evidence",
            key,
            "Retain a receipt reference and digest.",
        )
        return None
    if source == "synthetic" and evidence_kind != "synthetic":
        _issue(
            report,
            "mixed_evidence_kind",
            key,
            "Synthetic receipts cannot establish retained billing.",
        )
        return None
    if source == "provider_reported" and amount != _number(
        record.get("provider_reported_cost_usd")
    ):
        _issue(
            report,
            "billed_cost_mismatch",
            key,
            "Receipt amount differs from the provider-reported ledger field.",
        )
        return None
    return amount


def _validate_call(
    key: str, record: dict, basis: dict, contract: dict, indexed: dict, report: dict
) -> dict:
    recipe = contract["recipes"].get(basis["recipe_id"])
    price = contract["pricecards"].get(basis["pricecard_id"])
    model = contract["models"].get(record.get("model"))
    if basis["ledger_sha256"] != content_digest(record):
        _issue(
            report,
            "ledger_digest_mismatch",
            key,
            "Call metadata is not bound to this ledger record.",
        )
    if record.get("mode") not in {"sync", "batch"}:
        _issue(report, "unknown_transport", key, "Transport must be sync or batch.")
    if record.get("status") not in TERMINAL_STATUSES:
        _issue(
            report,
            "nonterminal_call",
            key,
            "Pending or unknown calls block complete accounting.",
        )
    if record.get("phase") not in {"initial", "repair", "retry", "explanation_repair"}:
        _issue(
            report,
            "unknown_phase",
            key,
            "Identify initial, retry, row repair, or explanation repair attempts.",
        )
    if record.get("mode") == "sync" and (
        type(record.get("attempt")) is not int or record["attempt"] < 1
    ):
        _issue(
            report,
            "unknown_attempt",
            key,
            "Synchronous attempts require a positive ordinal.",
        )
    if record.get("mode") == "batch" and (
        not record.get("batch_id") or not record.get("custom_id")
    ):
        _issue(
            report,
            "unknown_batch_identity",
            key,
            "Batch calls require batch_id and custom_id.",
        )
    elif record.get("mode") == "batch" and key != (
        f"batch:{record['batch_id']}:{record['custom_id']}"
    ):
        _issue(
            report,
            "batch_identity_mismatch",
            key,
            "Use the existing ledger's stable batch/job custom-ID call key.",
        )
    if recipe is None or price is None:
        _issue(
            report,
            "unknown_cost_basis",
            key,
            "Referenced recipe or pricecard is missing.",
        )
    if model and (
        basis["recipe_id"] != model["recipe_id"]
        or basis["pricecard_id"] != model["pricecard_id"]
    ):
        _issue(
            report,
            "mixed_cost_basis",
            key,
            "Every model row must use one frozen recipe and pricecard.",
        )
    if model and record.get("model_id") != model["model_id"]:
        _issue(
            report,
            "model_identity_mismatch",
            key,
            "Ledger provider model does not match the declared row.",
        )
    for item in (recipe, price):
        if item and (
            item["model_id"] != record.get("model_id")
            or (
                record.get("provider") is not None
                and item["provider"] != record["provider"]
            )
        ):
            _issue(
                report,
                "model_identity_mismatch",
                key,
                "Recipe/pricing identity differs from the ledger.",
            )
    if recipe and price and recipe["provider"] != price["provider"]:
        _issue(
            report,
            "model_identity_mismatch",
            key,
            "Recipe and pricecard providers differ.",
        )
    variables = record.get("variables")
    if (
        not isinstance(variables, list)
        or not variables
        or not all(isinstance(v, str) and v for v in variables)
    ):
        _issue(
            report, "unknown_outputs", key, "Retain the requested output identities."
        )
    elif len(set(variables)) != len(variables) or (
        recipe
        and recipe["outputs_per_request"] is not None
        and len(variables) > recipe["outputs_per_request"]
    ):
        _issue(
            report,
            "recipe_output_mismatch",
            key,
            "Requested outputs exceed the recipe or repeat.",
        )
    if (
        recipe
        and record.get("completion_budget_tokens") is not None
        and recipe["completion_token_limit"] is not None
        and not 0
        < record["completion_budget_tokens"]
        <= recipe["completion_token_limit"]
    ):
        _issue(
            report,
            "recipe_budget_mismatch",
            key,
            "Observed completion cap exceeds the recipe maximum or is zero.",
        )
    if record.get("scenario_id") not in contract["scenario_ids"]:
        _issue(
            report,
            "scenario_inventory_mismatch",
            key,
            "Call is outside the frozen scenario inventory.",
        )
    if record.get("cache_hit") not in (None, False, True) or (
        "cache_hit" in record and type(record["cache_hit"]) is not bool
    ):
        _issue(
            report,
            "invalid_cache_flag",
            key,
            "Cache flags must be booleans when present.",
        )
    replay = record.get("cache_hit") is True
    if record.get("mode") == "sync" and "cache_hit" not in record:
        _issue(
            report,
            "unknown_cache_status",
            key,
            "Synchronous records must distinguish physical calls from local replays.",
        )
    if record.get("mode") == "batch" and replay:
        _issue(
            report,
            "invalid_cache_flag",
            key,
            "Batch job entries represent physical calls, not local cache replays.",
        )
    actual = _actual_cost(record, basis, report, contract["evidence_kind"])
    if replay:
        original = indexed.get(basis["cache_replay_of"])
        same_fields = ("model", "model_id", "scenario_id", "variables", *TOKEN_FIELDS)
        origin_basis = contract["calls"].get(basis["cache_replay_of"])
        if (
            original is None
            or original.get("cache_hit") is True
            or original is record
            or any(original.get(field) != record.get(field) for field in same_fields)
            or origin_basis is None
            or any(
                origin_basis[field] != basis[field]
                for field in ("recipe_id", "pricecard_id", "usage_basis")
            )
        ):
            _issue(
                report,
                "invalid_cache_origin",
                key,
                "Replay requires a matching retained physical call in this run.",
            )
        if basis["billed_cost"]["source"] != "local_cache" or actual != 0:
            _issue(
                report,
                "invalid_cache_billing",
                key,
                "Replay must contribute zero new billed spend.",
            )
        if _number(record.get("total_cost_usd")) != 0:
            _issue(
                report,
                "invalid_cache_billing",
                key,
                "Replay ledger total must be zero.",
            )
        normalized = Decimal(0)
    else:
        if basis["cache_replay_of"] is not None:
            _issue(
                report,
                "invalid_cache_origin",
                key,
                "A physical call cannot also be a replay.",
            )
        normalized = _normalized_cost(record, basis, price, report)
    return {
        "model": record.get("model"),
        "model_id": record.get("model_id"),
        "scenario_id": record.get("scenario_id"),
        "transport": record.get("mode"),
        "phase": record.get("phase"),
        "status": record.get("status"),
        "physical_requests": int(not replay),
        "cache_replays": int(replay),
        "recipe_id": basis["recipe_id"],
        "pricecard_id": basis["pricecard_id"],
        "billed_source": basis["billed_cost"]["source"],
        "billing_evidence": basis["billed_cost"]["evidence"],
        "actual_billed_usd": _money(actual),
        "normalized_sync_usd": _money(normalized),
        "normalized_sync_is_estimate": True,
        "legacy_recorded_total_usd": record.get("total_cost_usd"),
        "legacy_cost_is_estimated": record.get("cost_is_estimated"),
        "usage": {field: record.get(field) for field in TOKEN_FIELDS},
        "usage_basis": basis["usage_basis"],
        "provider_response_id": record.get("provider_response_id"),
        "provider_resolved_model": record.get("provider_resolved_model"),
    }


def _totals(rows: list[dict], *, complete: bool = True) -> dict:
    result = {
        field: sum(row[field] for row in rows)
        for field in ("physical_requests", "cache_replays")
    }
    for metric in ("actual_billed", "normalized_sync"):
        values = [row[f"{metric}_usd"] for row in rows]
        with localcontext() as context:
            context.prec = 100
            subtotal = sum(
                (Decimal(value) for value in values if value is not None), Decimal(0)
            )
        result[f"{metric}_usd"] = (
            _money(subtotal)
            if complete and rows and all(value is not None for value in values)
            else None
        )
        result[f"{metric}_known_subtotal_usd"] = _money(subtotal)
        result[f"{metric}_unknown_calls"] = sum(value is None for value in values)
    result["normalized_sync_is_estimate"] = True
    result["inventory_complete"] = complete
    return result


def validate_cost_publication(contract: dict, records: Iterable[dict]) -> dict:
    """Reconcile a frozen cost contract with retained ledger objects, offline.

    Synthetic fixtures can pass validation, but only a complete retained contract
    can pass accounting eligibility. Neither outcome enables public costs.
    """
    report = _empty_report()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for error in validator.iter_errors(contract):
        _issue(
            report,
            "invalid_contract",
            "/".join(map(str, error.absolute_path)),
            error.message,
        )
    if report["issues"]:
        return _finish(report)
    report["schema_valid"] = True
    report["contract_sha256"] = content_digest(contract)
    report["run_id"] = contract["run_id"]
    report["metric"] = contract["metric"]
    report["evidence_kind"] = contract["evidence_kind"]
    report["pricing_date"] = contract["pricing_date"]
    report["history"] = contract["history"]
    report["recipes"] = contract["recipes"]
    report["pricecards"] = contract["pricecards"]
    if contract["pricing_date"] is None:
        _issue(
            report,
            "unknown_pricing_date",
            "pricing_date",
            "Freeze a dated pricing basis.",
        )
    _validate_catalogs(contract, report)
    if (
        contract["history"]["status"] != "complete"
        or contract["history"]["evidence"] is None
    ):
        _issue(
            report,
            "incomplete_history",
            "history",
            "Complete attempt history needs retained evidence; "
            "repricing cannot reconstruct omitted calls.",
        )
    displayed = set(contract["displayed_models"])
    if displayed != set(contract["models"]):
        _issue(
            report,
            "model_inventory_mismatch",
            "models",
            "Cost rows must exactly match all displayed models.",
        )
    ledger_validator = Draft202012Validator(
        {"$ref": "#/$defs/ledger_record", "$defs": schema["$defs"]}
    )
    indexed = _index_records(records, report, ledger_validator)
    if set(indexed) != set(contract["calls"]):
        _issue(
            report,
            "call_inventory_mismatch",
            "calls",
            "Every observed call needs a basis and every declared call "
            "needs a ledger record.",
        )
    expected_keys = [
        key
        for model in contract["models"].values()
        for key in model["expected_call_keys"]
    ]
    if len(expected_keys) != len(set(expected_keys)) or set(expected_keys) != set(
        indexed
    ):
        _issue(
            report,
            "call_inventory_mismatch",
            "models",
            "Model call inventories must partition the complete ledger.",
        )
    observed_models = {
        row.get("model")
        for row in indexed.values()
        if isinstance(row.get("model"), str)
    }
    if observed_models != displayed:
        _issue(
            report,
            "model_inventory_mismatch",
            "ledger",
            "Every displayed model needs physical-call evidence.",
        )
    for key, record in sorted(indexed.items()):
        if key in contract["calls"]:
            report["calls"][key] = _validate_call(
                key, record, contract["calls"][key], contract, indexed, report
            )
    for name, model in sorted(contract["models"].items()):
        if any(
            model[field] is None for field in ("model_id", "recipe_id", "pricecard_id")
        ):
            _issue(
                report,
                "unknown_cost_basis",
                f"models/{name}",
                "Model identity, recipe, and pricecard must be known.",
            )
        keys = {key for key, row in indexed.items() if row.get("model") == name}
        if keys != set(model["expected_call_keys"]):
            _issue(
                report,
                "call_inventory_mismatch",
                f"models/{name}",
                "Observed model calls differ from its declared inventory.",
            )
        scenarios = {
            indexed[key].get("scenario_id")
            for key in keys
            if isinstance(indexed[key].get("scenario_id"), str)
        }
        if scenarios != set(contract["scenario_ids"]):
            _issue(
                report,
                "scenario_inventory_mismatch",
                f"models/{name}",
                "Model does not cover the complete scenario inventory.",
            )
        rows = [row for row in report["calls"].values() if row["model"] == name]
        complete = (
            keys == set(model["expected_call_keys"])
            and len(rows) == len(keys)
            and contract["history"]["status"] == "complete"
            and contract["history"]["evidence"] is not None
            and scenarios == set(contract["scenario_ids"])
            and not any(
                item["code"] in {"invalid_ledger_record", "conflicting_call"}
                for item in report["issues"]
            )
        )
        totals = _totals(rows, complete=complete)
        for metric, expected in model["totals"].items():
            actual = totals[metric]
            if expected is None or actual is None:
                _issue(
                    report,
                    "unknown_model_total",
                    f"models/{name}/{metric}",
                    "Unknown totals cannot establish reconciliation.",
                )
            elif Decimal(str(expected)) != Decimal(str(actual)):
                _issue(
                    report,
                    "model_total_mismatch",
                    f"models/{name}/{metric}",
                    f"Declared {expected}; ledger gives {actual}.",
                )
        report["models"][name] = {
            "model_id": model["model_id"],
            "recipe_id": model["recipe_id"],
            "pricecard_id": model["pricecard_id"],
            "scenario_count": len(scenarios),
            "call_keys": sorted(keys),
            "totals": totals,
        }
    complete = (
        set(expected_keys) == set(indexed) == set(contract["calls"])
        and observed_models == displayed == set(contract["models"])
        and contract["history"]["status"] == "complete"
        and contract["history"]["evidence"] is not None
        and not any(
            item["code"]
            in {
                "invalid_ledger_record",
                "missing_call_key",
                "conflicting_call",
                "call_inventory_mismatch",
                "model_inventory_mismatch",
                "scenario_inventory_mismatch",
            }
            for item in report["issues"]
        )
    )
    report["totals"] = _totals(list(report["calls"].values()), complete=complete)
    report["missing_call_keys"] = sorted(set(expected_keys) - set(indexed))
    report["unexpected_call_keys"] = sorted(set(indexed) - set(expected_keys))
    return _finish(report, synthetic=contract["evidence_kind"] == "synthetic")


def render_markdown_report(report: dict) -> str:
    """Render internal diagnostics with separate complete totals and subtotals."""
    lines = [
        "# Cost publication validation",
        "",
        "Public costs remain unavailable.",
        "",
        f"Validation passed: {report['validation_passed']}. "
        f"Accounting eligible: {report['accounting_eligible']}.",
        "",
        f"Evidence kind: {report.get('evidence_kind', 'unknown')}. "
        f"Pricing date: {report.get('pricing_date') or 'unknown'}.",
        "",
        "This report checks accounting only. "
        "Issue118 release gates require separate review.",
        "",
        "| Model | Physical calls | Cache replays | Billed USD "
        "| Normalized sync USD (estimate) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, row in report["models"].items():
        totals = row["totals"]
        name = name.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {name} | {totals['physical_requests']} | {totals['cache_replays']} | "
            f"{totals['actual_billed_usd'] or 'unknown'} | "
            f"{totals['normalized_sync_usd'] or 'unknown'} |"
        )
    lines += [
        "",
        "Unknown totals stay null in JSON; "
        "known subtotals never substitute for totals.",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- {code}" for code in report["publication_blockers"])
    if report["issues"]:
        lines += ["", "## Findings", ""]
        lines.extend(
            f"- `{item['path']}`: {item['message']} ({item['code']})"
            for item in report["issues"]
        )
    lines += ["", "## Provenance limits", ""]
    lines.extend(f"- {text}" for text in report["provenance_limits"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write JSON/Markdown reports; exit 0 only for retained accounting eligibility."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--ledger", action="append", default=[], type=Path)
    parser.add_argument("--json-out", required=True, type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args(argv)
    inputs = {path.resolve() for path in [args.contract, *args.ledger]}
    outputs = [args.json_out.resolve()]
    if args.markdown_out:
        outputs.append(args.markdown_out.resolve())
    if inputs.intersection(outputs) or len(outputs) != len(set(outputs)):
        parser.error(
            "Report outputs must be distinct from each other and input evidence."
        )
    try:
        contract = json.loads(
            args.contract.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
        records = [
            record
            for path in args.ledger
            for record in read_spend_ledger(path, strict=True)
        ]
        report = validate_cost_publication(contract, records)
    except (OSError, ValueError) as error:
        report = _empty_report()
        _issue(report, "unreadable_evidence", "input", str(error))
        _finish(report)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(render_markdown_report(report), encoding="utf-8")
    return 0 if report["accounting_eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
