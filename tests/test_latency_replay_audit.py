"""The latency replay audit agrees with the frozen predictions.

``docs/latency_replay_audit/households.csv`` was built from artifacts outside
the repository (disk caches, spend ledgers, smoke files). These tests check
everything about it that the frozen predictions alone can check: that each
row is the household it names, that the sub-second households are exactly the
full replays plus the untraced ones, and that the id-time evidence recomputes.
They also pin the facts the paper and card state about the untimed models.
"""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from policybench.analysis import (
    REPLAYED_HOUSEHOLD_SECONDS,
    household_latency_seconds,
    model_cost_latency,
)
from policybench.config import PRICE_OVERRIDES_PER_1M
from policybench.paper_results import LATENCY_REPLAY_AUDIT, r
from scripts.audit_latency_replays import (
    MARGIN_SECONDS,
    id_created_at,
    provider_response_id,
)

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = (
    ROOT
    / "paper"
    / "snapshot"
    / "20260501"
    / "runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
)
AUDIT_DOC = ROOT / "docs" / "latency_replay_audit.md"
MANIFEST = ROOT / "paper" / "snapshot" / "20260501" / "manifest.json"
# Fable 5's usage, carried from its original run's per-call rows (release
# dashboard-data-20260701, claude-fable-5-predictions.csv.gz).
FABLE_CARRIED = {
    "costUsd": 54.109099999999955,
    "costPerHousehold": 0.5410909999999995,
    "totalTokens": 3850174,
    "latencySeconds": 97.6780539804895,
}


@pytest.fixture(scope="module")
def predictions() -> pd.DataFrame:
    return pd.read_csv(RUN_DIR / "predictions.csv.gz", low_memory=False)


@pytest.fixture(scope="module")
def households(predictions) -> pd.DataFrame:
    grouped = predictions.groupby(["model", "scenario_id"], sort=True)
    return pd.DataFrame(
        {
            "latency": household_latency_seconds(predictions),
            "first_response_id": grouped["provider_response_id"].first(),
            "started": grouped["request_started_at"].min(),
        }
    )


@pytest.fixture(scope="module")
def audit() -> pd.DataFrame:
    # An untraced household cites no evidence: an empty field, not NaN.
    return pd.read_csv(LATENCY_REPLAY_AUDIT).fillna({"evidence": ""})


@pytest.fixture(scope="module")
def model_stats() -> dict[str, dict]:
    payload = json.loads(gzip.open(RUN_DIR / "data.json.gz").read())
    return {row["model"]: row for row in payload["modelStats"]}


def test_each_audit_row_is_the_household_it_names(audit, households):
    assert not audit.duplicated(["model", "scenario_id"]).any()
    for row in audit.itertuples():
        household = households.loc[(row.model, row.scenario_id)]
        assert row.household_latency_seconds == pytest.approx(
            household["latency"], abs=1e-6
        ), row
        assert row.first_response_id == household["first_response_id"], row


def test_subsecond_households_are_the_full_replays_and_the_untraced(audit, households):
    """A full replay sums to under a second and a partial one does not, and no
    sub-second household is missing from the audit."""
    subsecond = set(
        households.index[households["latency"] < REPLAYED_HOUSEHOLD_SECONDS]
    )
    audited = {
        (m, s): kind for m, s, kind in audit[["model", "scenario_id", "replay"]].values
    }
    assert subsecond == {key for key, kind in audited.items() if kind != "partial"}
    for (model, scenario), kind in audited.items():
        seconds = households.loc[(model, scenario), "latency"]
        if kind == "partial":
            assert seconds >= REPLAYED_HOUSEHOLD_SECONDS, (model, scenario)
        else:
            assert seconds < REPLAYED_HOUSEHOLD_SECONDS, (model, scenario)


def test_replays_and_live_households_are_far_apart(households, audit):
    """Every full replay sums to under 0.12 s and the fastest household the
    audit does not list takes over 1.5 s, so the one-second line is not close
    to any household."""
    full = audit[audit["replay"] == "full"]
    assert full["household_latency_seconds"].max() < 0.12
    listed = set(zip(audit["model"], audit["scenario_id"]))
    unlisted = households[[key not in listed for key in households.index]]
    assert unlisted["latency"].dropna().min() > 1.5


def test_id_time_evidence_recomputes_and_is_complete(audit, households):
    """Where an id embeds its creation time, the audit cites it exactly when
    the response predates its request by more than the margin; on every other
    household that time sits within the margin of the request."""
    cited = {
        (m, s)
        for m, s, evidence in audit[["model", "scenario_id", "evidence"]].values
        if re.search(r"openrouter_id|openai_id", evidence)
    }
    checked = 0
    for (model, scenario), household in households.iterrows():
        created = id_created_at(provider_response_id(household["first_response_id"]))
        if created is None or pd.isna(household["started"]):
            continue
        checked += 1
        early = created < household["started"] - MARGIN_SECONDS
        assert early == ((model, scenario) in cited), (model, scenario)
        if not early:
            assert abs(household["started"] - created) <= MARGIN_SECONDS
    assert checked > 1000


def test_the_untraced_households_predate_per_call_timestamps(audit, predictions):
    untraced = audit[audit["replay"] == "untraced"]
    assert sorted(untraced["model"]) == ["claude-haiku-4.5", "grok-4.3"]
    for model in untraced["model"]:
        rows = predictions[predictions["model"] == model]
        assert rows["request_started_at"].isna().all(), model


def test_the_audit_doc_counts_are_the_csvs(audit):
    text = re.sub(r"\s+", " ", AUDIT_DOC.read_text())
    full = int((audit["replay"] == "full").sum())
    partial = int((audit["replay"] == "partial").sum())
    replayed_models = audit.loc[audit["replay"] != "untraced", "model"].nunique()
    assert (
        f"That is {full} full and {partial} partial replays across "
        f"{replayed_models} models."
    ) in text
    for line in AUDIT_DOC.read_text().splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 6 or not cells[1].isdigit():
            continue
        name, n_full, n_partial = cells[0], int(cells[1]), int(cells[2])
        model = next(m for m in audit["model"].unique() if r.model_name(m) == name)
        rows = audit[audit["model"] == model]
        assert n_full == int((rows["replay"] == "full").sum()), name
        assert n_partial == int((rows["replay"] == "partial").sum()), name


def test_the_audit_doc_medians_are_the_frozen_ones(households, model_stats):
    """The table's published median is modelStats', and its other median
    drops the model's sub-second households."""
    for line in AUDIT_DOC.read_text().splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 6 or not cells[1].isdigit():
            continue
        model = next(m for m in model_stats if r.model_name(m) == cells[0])
        published = float(cells[4].replace(",", ""))
        assert published == pytest.approx(
            model_stats[model]["latencySeconds"], abs=0.051
        ), model
        latency = households.loc[model, "latency"].dropna()
        kept = latency[latency >= REPLAYED_HOUSEHOLD_SECONDS]
        without = float(cells[5].split(" ")[0].replace(",", ""))
        assert without == pytest.approx(kept.median(), abs=0.051), model
        if "households" in cells[5]:
            assert f"({len(kept)} households)" in cells[5], model


def test_published_cost_and_latency_reproduce_except_fables_carried_usage(
    predictions, model_stats
):
    """modelStats' cost and latency are model_cost_latency's over the frozen
    rows; the only exceptions are Claude Fable 5's four carried fields."""
    computed = model_cost_latency(predictions, PRICE_OVERRIDES_PER_1M)
    for model, row in model_stats.items():
        for field in ("costUsd", "costPerHousehold", "latencySeconds", "totalTokens"):
            if model == "claude-fable-5" and field in FABLE_CARRIED:
                assert row[field] == FABLE_CARRIED[field]
                continue
            expected = computed.get(model, {}).get(field)
            if expected is None:
                assert row.get(field) is None, (model, field)
            else:
                assert row[field] == pytest.approx(expected, rel=1e-12), (model, field)


def test_the_untimed_models_are_the_batch_run_and_fables_rebuilt_rows(predictions):
    """GPT-5.5's batch rows have costs but no times; Fable 5's rebuilt rows
    have neither, nor raw payloads, but keep their explanations."""
    assert r.untimed_latency_models == ["claude-fable-5", "gpt-5.5"]
    gpt = predictions[predictions["model"] == "gpt-5.5"]
    assert gpt["request_started_at"].isna().all()
    assert gpt["total_cost_usd"].notna().all()
    fable = predictions[predictions["model"] == "claude-fable-5"]
    for column in ("elapsed_seconds", "total_cost_usd", "total_tokens", "raw_response"):
        assert fable[column].isna().all(), column
    assert fable["explanation"].notna().all()


def test_the_paper_dashes_exactly_the_untimed_and_replayed_medians(model_stats):
    assert r.latency_dash_models == [
        "glm-5.2",
        "gpt-5.5",
        "kimi-k2.6",
        "minimax-m3",
        "qwen-3.7-max",
    ]
    assert r.replayed_latency_models == [
        "glm-5.2",
        "kimi-k2.6",
        "minimax-m3",
        "qwen-3.7-max",
    ]
    for model in r.replayed_latency_models:
        assert model_stats[model]["latencySeconds"] < 0.05, model
    assert r.zero_cost_models == ["ox-alpha"]


def test_the_manifest_no_longer_says_fable_ran_through_the_batch_adapter():
    notes = " ".join(json.loads(MANIFEST.read_text())["reproducibility_notes"])
    assert "Anthropic batch adapter" not in notes
    assert "rebuilt from release dashboard-data-20260701" in notes


PAPER_HTML = ROOT / "app" / "public" / "paper" / "web" / "index.html"


def _cost_latency_rows() -> list[list[str]]:
    """The rendered cost-and-latency table's rows, as visible cell text."""
    from html import unescape

    page = PAPER_HTML.read_text()
    header = page.index("Latency (median)")
    table = page[page.rfind("<table", 0, header) : page.index("</table>", header)]
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
        rows.append(
            [
                unescape(re.sub(r"<[^>]+>", "", cell)).replace("​", "").strip()
                for cell in cells
            ]
        )
    return rows


def _visible_text() -> str:
    from html import unescape

    text = re.sub(r"<[^>]+>", " ", PAPER_HTML.read_text())
    text = re.sub(r"\s+", " ", unescape(text)).replace("​", "")
    # Quarto renders apostrophes as typographic quotes.
    return text.replace("’", "'").replace("‘", "'")


def test_every_dash_in_the_rendered_table_is_one_the_text_explains():
    header, *rows = _cost_latency_rows()
    assert header == ["Model", "Exact (%)", "Cost / household", "Latency (median)"]
    assert len(rows) == len(r.model_stats)
    latency_dash = sorted(row[0] for row in rows if row[3] == "—")
    cost_dash = sorted(row[0] for row in rows if row[2] == "—")
    assert latency_dash == sorted(r.model_name(m) for m in r.latency_dash_models)
    assert cost_dash == sorted(r.model_name(m) for m in r.zero_cost_models)
    # Fable 5's untimed rows are not dashed: its carried per-call median shows.
    fable = next(row for row in rows if row[0] == r.model_name("claude-fable-5"))
    assert fable[3] == f"{round(FABLE_CARRIED['latencySeconds'])} s"


def test_the_rendered_paper_states_why_each_latency_is_missing():
    text = _visible_text()
    assert (
        f"{r.batch_latency_models_fmt} ran through OpenAI's batch API, which "
        "records no per-call request time, so it shows a dash." in text
    )
    assert (
        f"{r.replayed_latency_models_fmt} were finished over several passes, "
        "each of which replayed the earlier passes' successful responses." in text
    )
    assert (
        f"records a replay on {r.replayed_latency_range_fmt} of its "
        f"{r.n_households_fmt} households" in text
    )
    assert (
        f"In {r.other_subsecond_model_count_fmt} other models, "
        f"{r.other_subsecond_household_count} households sum to under a second." in text
    )
    assert f"The audit traces {r.traced_other_subsecond_count} of them" in text
    assert f"more than {r.subsecond_median_shift_fmt} seconds" in text
    assert f"A further {r.partial_replay_count} households replay" in text
    assert "Claude Fable 5's board rows carry no usage or timing fields" in text


# ----- the builder's evidence rules (scripts/audit_latency_replays.py) -------


def _frozen(rows):
    """Frozen-style rows: (model, scenario, response id, start, household s)."""
    records = []
    for model, scenario, response_id, start, seconds in rows:
        for variable in ("a", "b"):
            records.append(
                {
                    "model": model,
                    "scenario_id": scenario,
                    "variable": variable,
                    "provider_response_id": response_id,
                    "request_started_at": start,
                    "elapsed_seconds": seconds / 2,
                }
            )
    return pd.DataFrame(records)


def _ledger(rows):
    """Ledger records: (response id, model, scenario, start, cache hit, smoke)."""
    return pd.DataFrame(
        [
            {
                "provider_response_id": response_id,
                "model": model,
                "scenario_id": scenario,
                "request_started_at": start,
                "request_completed_at": start + 30.0,
                "cache_hit": hit,
                "_smoke": smoke,
            }
            for response_id, model, scenario, start, hit, smoke in rows
        ]
    )


def _built(predictions, stored=None, ledgers=None, smoke_times=None):
    from scripts.audit_latency_replays import build

    rows = build(
        predictions,
        stored or {},
        ledgers if ledgers is not None else pd.DataFrame(),
        smoke_times or {},
    )
    return {(row["model"], row["scenario_id"]): row for row in rows}


def test_a_later_replay_of_a_live_board_response_is_not_evidence():
    """A run after the board that replays a response the board fetched live
    records a cache hit for the same id, but not at the board request."""
    board = _frozen([("m", "s1", "chatcmpl-live", 1_000.0, 30.0)])
    later = _ledger([("chatcmpl-live", "m", "s1", 5_000.0, True, False)])
    assert _built(board, ledgers=later) == {}
    same = _ledger([("chatcmpl-live", "m", "s1", 1_000.0, True, False)])
    row = _built(board, ledgers=same)[("m", "s1")]
    assert (row["replay"], row["evidence"]) == ("partial", "spend_ledger")
    other = _ledger([("chatcmpl-live", "m", "s2", 1_000.0, True, False)])
    assert _built(board, ledgers=other) == {}


def test_a_smoke_counts_only_if_it_finished_before_the_request():
    board = _frozen([("m", "s1", "chatcmpl-x", 1_000.0, 0.02)])
    after = _built(board, smoke_times={"chatcmpl-x": 1_500.0})[("m", "s1")]
    assert (after["replay"], after["evidence"]) == ("untraced", "")
    before = _built(board, smoke_times={"chatcmpl-x": 900.0})[("m", "s1")]
    assert (before["replay"], before["evidence"], before["source"]) == (
        "full",
        "smoke_file",
        "onboarding smoke",
    )
    ledger = _ledger([("chatcmpl-x", "m", "s1", 1_500.0, False, True)])
    late = _built(board, ledgers=ledger)[("m", "s1")]
    assert late["evidence"] == ""


def test_a_cached_response_counts_only_if_stored_before_the_request():
    board = _frozen([("m", "s1", "chatcmpl-x", 1_000.0, 45.0)])
    assert _built(board, stored={"chatcmpl-x": 1_010.0}) == {}
    row = _built(board, stored={"chatcmpl-x": 990.0})[("m", "s1")]
    assert (row["replay"], row["evidence"]) == ("partial", "cache")


def test_id_times_need_the_margin_and_live_households_are_not_listed():
    created = 1_783_264_675
    early = f"gen-{created}-abcdefghijABCDEFGHIJ"
    board = _frozen(
        [
            ("m", "s1", early, created + 120.0, 0.03),
            ("m", "s2", early.replace("abc", "xyz"), created + 10.0, 40.0),
            ("m", "s3", "chatcmpl-fast", created + 5.0, 0.04),
        ]
    )
    built = _built(board)
    assert built[("m", "s1")]["evidence"] == "openrouter_id"
    assert built[("m", "s1")]["replay"] == "full"
    assert ("m", "s2") not in built
    assert built[("m", "s3")]["replay"] == "untraced"


def test_smoke_file_times_read_columns_by_name(tmp_path):
    """Smoke CSVs order their columns differently; a row without a completion
    time cannot show order and is skipped, and files outside a smoke path are
    not read."""
    from scripts.audit_latency_replays import smoke_file_times

    smoke = tmp_path / "x_smoke" / "run"
    smoke.mkdir(parents=True)
    pd.DataFrame(
        {
            "request_completed_at": [20.0, 10.0, None],
            "provider_response_id": ["gen-a", "gen-a", "gen-b"],
        }
    ).to_csv(smoke / "predictions.csv", index=False)
    board = tmp_path / "board"
    board.mkdir()
    pd.DataFrame(
        {"provider_response_id": ["gen-c"], "request_completed_at": [5.0]}
    ).to_csv(board / "predictions.csv", index=False)
    assert smoke_file_times([tmp_path]) == {"gen-a": 10.0}
