"""Offline cost-contract boundaries; every rate and receipt here is synthetic."""

import copy
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from policybench.cost_publication import (
    content_digest,
    validate_cost_publication,
)
from policybench.spend_ledger import read_spend_ledger, upsert_spend_ledger

FIXTURES = Path(__file__).parent / "fixtures/cost_publication"


@pytest.fixture
def packet():
    contract = json.loads((FIXTURES / "synthetic.contract.json").read_text())
    records = read_spend_ledger(FIXTURES / "synthetic.spend.jsonl", strict=True)
    return contract, records


def codes(report):
    return {item["code"] for item in report["issues"]}


def rebind(contract, record):
    contract["calls"][record["call_key"]]["ledger_sha256"] = content_digest(record)


def test_success_retry_repair_batch_and_cache_reconcile_offline(packet, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Cost validation attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    contract, records = packet
    report = validate_cost_publication(contract, records)
    assert report["validation_passed"] is True
    assert report["accounting_eligible"] is False  # synthetic evidence
    assert report["public_costs_available"] is False
    assert report["totals"]["physical_requests"] == 4
    assert report["totals"]["cache_replays"] == 1
    # Three sync attempts at 1,000 input + 100 output tokens:
    # 3 * (1,000 * $2 + 100 * $4) / 1M = $0.0072.
    # Batch: (2,000 * $2 + 300 * $4) / 1M = $0.0052, no discount.
    assert report["totals"]["normalized_sync_usd"] == "0.0124"
    # Synthetic receipts differ from list-price estimates; replay adds zero.
    assert report["totals"]["actual_billed_usd"] == "0.0086"
    assert report["totals"]["normalized_sync_is_estimate"] is True


def test_duplicate_poll_is_counted_once(packet):
    contract, records = packet
    report = validate_cost_publication(contract, records + [copy.deepcopy(records[-1])])
    assert report["validation_passed"]
    assert report["duplicate_records"] == 1
    assert report["totals"]["physical_requests"] == 4


def test_conflicting_poll_cannot_replace_cost_evidence(packet):
    contract, records = packet
    conflicting = dict(records[-1], provider_reported_cost_usd=100)
    report = validate_cost_publication(contract, records + [conflicting])
    assert not report["validation_passed"]
    assert "conflicting_call" in codes(report)


@pytest.mark.parametrize(
    "field",
    [
        "prompt_tokens",
        "completion_tokens",
        "reasoning_tokens",
        "cached_prompt_tokens",
        "cache_write_prompt_tokens",
    ],
)
def test_unknown_usage_is_not_zero(packet, field):
    contract, records = packet
    records[0][field] = None
    rebind(contract, records[0])
    report = validate_cost_publication(contract, records)
    assert "unknown_usage" in codes(report)
    assert report["totals"]["normalized_sync_usd"] is None
    assert report["totals"]["normalized_sync_known_subtotal_usd"] == "0.01"
    assert not report["public_costs_available"]


def test_missing_retry_and_missing_displayed_model_block(packet):
    contract, records = packet
    report = validate_cost_publication(contract, records[1:])
    assert "call_inventory_mismatch" in codes(report)
    assert not report["validation_passed"]
    assert report["totals"]["actual_billed_usd"] is None
    assert report["totals"]["normalized_sync_usd"] is None
    contract["displayed_models"].append("omitted-model")
    assert "model_inventory_mismatch" in codes(
        validate_cost_publication(contract, records)
    )


@pytest.mark.parametrize("status", ["unknown", "unrecoverable"])
def test_historical_accepted_rows_cannot_reconstruct_missing_attempts(packet, status):
    contract, records = packet
    contract["history"]["status"] = status
    contract["history"]["reason"] = "Historical attempts were not retained."
    report = validate_cost_publication(contract, records)
    assert "incomplete_history" in codes(report)
    assert not report["accounting_eligible"]
    assert not report["public_costs_available"]


def test_mixed_pricing_snapshot_rejected_even_when_totals_match(packet):
    contract, records = packet
    old_id = next(iter(contract["pricecards"]))
    card = copy.deepcopy(contract["pricecards"][old_id])
    card["captured_on"] = "2026-09-06"
    other_id = content_digest(card)
    contract["pricecards"][other_id] = card
    contract["calls"][records[0]["call_key"]]["pricecard_id"] = other_id
    report = validate_cost_publication(contract, records)
    assert "mixed_cost_basis" in codes(report)
    assert "pricing_date_mismatch" in codes(report)


def test_frozen_recipe_and_ledger_tampering_rejected(packet):
    contract, records = packet
    next(iter(contract["recipes"].values()))["outputs_per_request"] = 99
    records[0]["prompt_tokens"] += 1
    report = validate_cost_publication(contract, records)
    assert "content_digest_mismatch" in codes(report)
    assert "ledger_digest_mismatch" in codes(report)


def test_batch_reconstructed_total_never_becomes_actual_billing(packet):
    contract, records = packet
    key = records[-1]["call_key"]
    contract["calls"][key]["billed_cost"] = {
        "amount_usd": None,
        "source": "unknown",
        "evidence": None,
    }
    report = validate_cost_publication(contract, records)
    assert report["totals"]["actual_billed_usd"] is None
    assert report["totals"]["actual_billed_known_subtotal_usd"] == "0.006"
    assert report["totals"]["normalized_sync_usd"] == "0.0124"
    assert "unknown_billed_cost" in codes(report)


def test_cache_replay_requires_retained_origin(packet):
    contract, records = packet
    replay = next(row for row in records if row.get("cache_hit"))
    contract["calls"][replay["call_key"]]["cache_replay_of"] = "sync:missing"
    report = validate_cost_publication(contract, records)
    assert "invalid_cache_origin" in codes(report)


def test_missing_sync_cache_flag_cannot_assert_a_new_physical_request(packet):
    contract, records = packet
    del records[0]["cache_hit"]
    rebind(contract, records[0])
    report = validate_cost_publication(contract, records)
    assert "unknown_cache_status" in codes(report)
    assert not report["accounting_eligible"]


def test_provider_receipt_must_match_provider_field(packet):
    contract, records = packet
    basis = contract["calls"][records[0]["call_key"]]["billed_cost"]
    basis["source"] = "provider_reported"
    basis["amount_usd"] = "99"
    assert "billed_cost_mismatch" in codes(validate_cost_publication(contract, records))


@pytest.mark.parametrize("value", [-1, True, 1.5, float("nan"), float("inf")])
def test_invalid_token_counts_fail_closed(packet, value):
    contract, records = packet
    records[0]["prompt_tokens"] = value
    report = validate_cost_publication(contract, records)
    assert not report["validation_passed"]
    assert not report["public_costs_available"]


def test_strict_ledger_reader_rejects_corruption(tmp_path):
    path = tmp_path / "bad.spend.jsonl"
    for text in ['{"call_key":"one"}\n{', "[]\n", '{"x":NaN}\n', '{"x":1,"x":2}\n']:
        path.write_text(text)
        with pytest.raises(ValueError):
            read_spend_ledger(path, strict=True)
    # Preserve the existing recovery-oriented reader's default behavior.
    path.write_text('{"call_key":"one"}\n{')
    assert read_spend_ledger(path) == [{"call_key": "one"}]


def test_current_ledger_upsert_handles_pending_then_duplicate_terminal(
    packet, tmp_path
):
    contract, records = packet
    path = tmp_path / "calls.spend.jsonl"
    pending = dict(records[-1], status="pending", total_cost_usd=None)
    upsert_spend_ledger(path, records[:-1] + [pending])
    upsert_spend_ledger(path, [records[-1], records[-1]])
    report = validate_cost_publication(contract, read_spend_ledger(path, strict=True))
    assert report["validation_passed"]
    assert report["totals"]["physical_requests"] == 4


def test_cli_writes_deterministic_reports_and_never_signals_public_readiness(tmp_path):
    output = tmp_path / "report.json"
    markdown = tmp_path / "report.md"
    command = [
        sys.executable,
        "-m",
        "policybench.cost_publication",
        "--contract",
        str(FIXTURES / "synthetic.contract.json"),
        "--ledger",
        str(FIXTURES / "synthetic.spend.jsonl"),
        "--json-out",
        str(output),
        "--markdown-out",
        str(markdown),
    ]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 1  # 0 is reserved for retained accounting evidence.
    before = output.read_bytes()
    second = subprocess.run(command, capture_output=True, text=True)
    assert second.returncode == 1
    assert before == output.read_bytes()
    assert "Public costs remain unavailable" in markdown.read_text()
    assert json.loads(before)["validation_passed"]


@pytest.mark.parametrize(
    "field", ["mode", "status", "model", "scenario_id", "variables"]
)
def test_malformed_ledger_fields_return_diagnostics_instead_of_crashing(packet, field):
    contract, records = packet
    records[0][field] = {"invalid": "object"}
    report = validate_cost_publication(contract, records)
    assert "invalid_ledger_record" in codes(report)
    assert not report["accounting_eligible"]


def test_reasoning_and_provider_cache_inclusion_semantics_are_explicit(packet):
    contract, records = packet
    # Same billed token totals, expressed in a provider's exclusive fields.
    for record in records:
        record["prompt_tokens"] -= (
            record["cached_prompt_tokens"] + record["cache_write_prompt_tokens"]
        )
        record["completion_tokens"] -= record["reasoning_tokens"]
        record["total_tokens"] = record["prompt_tokens"] + record["completion_tokens"]
        contract["calls"][record["call_key"]]["usage_basis"] = {
            "prompt_tokens": "excludes_cache",
            "completion_tokens": "excludes_reasoning",
        }
        rebind(contract, record)
    report = validate_cost_publication(contract, records)
    assert report["validation_passed"]
    assert report["totals"]["normalized_sync_usd"] == "0.0124"


@pytest.mark.parametrize("phase", ["initial", "retry", "repair", "explanation_repair"])
def test_terminal_failures_and_all_existing_repair_phases_count_as_spend(packet, phase):
    contract, records = packet
    records[0]["phase"] = phase
    records[0]["status"] = "provider_error"
    rebind(contract, records[0])
    report = validate_cost_publication(contract, records)
    assert report["validation_passed"]
    assert report["totals"]["physical_requests"] == 4


def test_unknown_rates_and_nonterminal_calls_block(packet):
    contract, records = packet
    records[0]["status"] = "pending"
    rebind(contract, records[0])
    old_id = next(iter(contract["pricecards"]))
    card = contract["pricecards"].pop(old_id)
    card["input_per_million_usd"] = None
    new_id = content_digest(card)
    contract["pricecards"][new_id] = card
    for basis in [*contract["models"].values(), *contract["calls"].values()]:
        basis["pricecard_id"] = new_id
    report = validate_cost_publication(contract, records)
    assert {"nonterminal_call", "unknown_price"} <= codes(report)
    assert report["totals"]["normalized_sync_usd"] is None


def test_retained_accounting_is_only_a_necessary_publication_condition(packet):
    # Exercise the retained-attestation branch with toy evidence in memory only.
    # No retained provider prices or receipts are claimed or emitted by this test.
    contract, records = packet
    contract["evidence_kind"] = "retained"
    old_id = next(iter(contract["pricecards"]))
    card = contract["pricecards"].pop(old_id)
    card["evidence_kind"] = "retained"
    new_id = content_digest(card)
    contract["pricecards"][new_id] = card
    for basis in [*contract["models"].values(), *contract["calls"].values()]:
        basis["pricecard_id"] = new_id
    for basis in contract["calls"].values():
        if basis["billed_cost"]["source"] == "synthetic":
            basis["billed_cost"]["source"] = "billing_export"
    report = validate_cost_publication(contract, records)
    assert report["validation_passed"]
    assert report["accounting_eligible"]
    assert not report["public_costs_available"]
    assert report["publication_blockers"] == ["issue118_release_review_required"]


def test_cli_refuses_to_overwrite_input_evidence(tmp_path):
    contract = tmp_path / "contract.json"
    contract.write_bytes((FIXTURES / "synthetic.contract.json").read_bytes())
    before = contract.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "policybench.cost_publication",
            "--contract",
            str(contract),
            "--json-out",
            str(contract),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert contract.read_bytes() == before


def test_different_call_keys_cannot_duplicate_one_batch_request(packet):
    contract, records = packet
    duplicate = dict(records[-1], call_key="batch:alias:u1")
    key = duplicate["call_key"]
    contract["calls"][key] = copy.deepcopy(contract["calls"][records[-1]["call_key"]])
    rebind(contract, duplicate)
    contract["models"][duplicate["model"]]["expected_call_keys"].append(key)
    report = validate_cost_publication(contract, records + [duplicate])
    assert "batch_identity_mismatch" in codes(report)
    assert not report["accounting_eligible"]
