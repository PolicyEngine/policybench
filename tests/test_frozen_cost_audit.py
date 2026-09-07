"""Retained prediction aggregates cannot establish complete publication costs."""

import hashlib
import json
import socket
from pathlib import Path

from policybench.frozen_cost_audit import audit_frozen_costs


def test_real_frozen_release_is_ineligible_without_repricing_or_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline frozen audit attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    run = (
        Path(__file__).resolve().parents[1]
        / "paper/snapshot/20260501/runs"
        / "us_full_run_20260612_policyengine_4_16_1_populace"
    )
    result = audit_frozen_costs(run)
    inventory, contract, report = (
        result[key] for key in ("inventory", "contract", "validation")
    )
    assert len(inventory["models"]) == 39
    assert inventory["scenario_count"] == 100
    assert inventory["ledger_files"] == []
    assert contract["history"]["status"] == "unrecoverable"
    assert contract["pricecards"] == {}
    assert contract["recipes"] == {}
    assert report["schema_valid"]
    assert not report["accounting_eligible"]
    assert not report["public_costs_available"]
    assert report["totals"]["actual_billed_usd"] is None
    assert report["totals"]["normalized_sync_usd"] is None
    assert inventory["models"]["claude-fable-5"]["provenance"] == "aggregate_only"
    assert inventory["models"]["grok-build-0.1"]["provenance"] == "aggregate_only"
    assert (
        inventory["models"]["claude-sonnet-5"]["provenance"]
        == "reconstructed_prediction_rows"
    )
    for artifact in inventory["artifacts"]:
        assert (
            hashlib.sha256((run / artifact["path"]).read_bytes()).hexdigest()
            == artifact["sha256"]
        )


def test_aggregate_amount_never_fills_billed_cost(tmp_path):
    (tmp_path / "data.json").write_text(
        json.dumps(
            {
                "modelStats": [
                    {"model": "toy", "condition": "no_tools", "costUsd": 99}
                ],
                "scenarios": {"s1": {}},
            }
        )
    )
    result = audit_frozen_costs(tmp_path)
    assert result["inventory"]["models"]["toy"]["legacy_payload_cost_usd"] == "99"
    assert result["contract"]["models"]["toy"]["totals"]["actual_billed_usd"] is None
    assert result["validation"]["totals"]["actual_billed_usd"] is None


def test_discovered_ledger_does_not_create_a_completeness_attestation(tmp_path):
    (tmp_path / "data.json").write_text(
        json.dumps(
            {
                "modelStats": [
                    {"model": "toy", "condition": "no_tools", "costUsd": 99}
                ],
                "scenarios": {"s1": {}},
            }
        )
    )
    (tmp_path / "one.spend.jsonl").write_text('{"call_key":"one"}\n')
    result = audit_frozen_costs(tmp_path)
    assert result["contract"]["history"]["status"] == "unknown"
    assert result["inventory"]["ledger_files"] == ["one.spend.jsonl"]
    assert not result["validation"]["accounting_eligible"]
