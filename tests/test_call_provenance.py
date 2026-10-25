"""Per-row call provenance: live calls, cache replays and live time.

Every row writer fills ``live_calls``, ``cache_hit_calls`` and
``live_elapsed_seconds`` (``eval_no_tools.NO_TOOLS_CALL_PROVENANCE_COLUMNS``).
The invariants these tests execute, for every row a writer emits:

1. ``live_calls`` and ``cache_hit_calls`` are non-negative integers that count
   every response behind the row's time, live or replayed.
2. ``0 <= live_elapsed_seconds <= elapsed_seconds``, and the two are empty
   together.
3. A row whose responses were all cache hits has zero live calls and exactly
   zero live time.
4. A row with no cache hits has live time exactly equal to its elapsed time.
5. The counts and live time agree with the requests actually made (the mock's
   call history, which the spend ledger also records): exactly, when none of
   a group's requests failed; as a subset of the returned responses, counts
   and times together, when one did (a failed chunk or household keeps none of
   its time).
6. Batch rows never record a cache hit and carry no live time.
7. The columns round-trip through the run store and CSV byte for byte; a CSV
   written before they existed round-trips without them and classifies as
   unknown.
8. Adding the columns changes no published number.
"""

import bisect
import json
import math
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import litellm
import pandas as pd
import pytest
from hypothesis import HealthCheck, Phase, event, example, given, reject, settings
from hypothesis import strategies as st

import policybench.eval_no_tools as eval_no_tools
import policybench.row_repair as row_repair
from policybench.analysis import model_cost_latency, usage_summary_by_model
from policybench.batch_eval import BatchUnit, NormalizedResult, rows_from_unit
from policybench.call_provenance import (
    HOUSEHOLD_CALL_STATUSES,
    household_call_provenance,
)
from policybench.config import COUNTRY_PROGRAMS
from policybench.eval_no_tools import (
    NO_TOOLS_CALL_PROVENANCE_COLUMNS,
    NO_TOOLS_RESULT_COLUMNS,
    _aggregate_call_provenance,
    _aggregate_request_results,
    _build_resume_metadata,
    _request_call_provenance,
    _write_resume_metadata,
    run_no_tools_eval,
    run_no_tools_single_output_eval,
)
from policybench.retry_eval import merge_retry_predictions
from policybench.row_repair import (
    _append_rows,
    merge_row_repair_predictions,
    repair_prediction_row,
)
from policybench.runstore import (
    _RESPONSE_COLUMNS,
    RunStore,
    export_predictions_csv,
    import_run_csv,
)
from policybench.scenarios import Person, Scenario
from policybench.spend_ledger import read_spend_ledger, spend_ledger_path

PROVENANCE = list(NO_TOOLS_CALL_PROVENANCE_COLUMNS)
US_VARIABLES = COUNTRY_PROGRAMS["us"]
FROZEN_US_PREDICTIONS = (
    Path(__file__).resolve().parents[1]
    / "paper/snapshot/20260501/runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace/predictions.csv.gz"
)


def _scenario(scenario_id: str, income: float = 50_000.0) -> Scenario:
    return Scenario(
        id=scenario_id,
        state="CA",
        filing_status="single",
        adults=[Person(name="adult1", age=35, employment_income=income)],
        year=2026,
    )


def test_the_provenance_columns_close_the_row_schema_and_are_response_level():
    assert NO_TOOLS_RESULT_COLUMNS[-3:] == NO_TOOLS_CALL_PROVENANCE_COLUMNS
    assert set(NO_TOOLS_CALL_PROVENANCE_COLUMNS) <= set(_RESPONSE_COLUMNS)


def test_one_request_is_a_live_call_or_a_replay():
    assert _request_call_provenance(12.5, False) == {
        "live_calls": 1,
        "cache_hit_calls": 0,
        "live_elapsed_seconds": 12.5,
    }
    assert _request_call_provenance(0.02, True) == {
        "live_calls": 0,
        "cache_hit_calls": 1,
        "live_elapsed_seconds": 0.0,
    }


def test_no_responses_means_zero_calls_and_no_live_time():
    assert _aggregate_call_provenance([]) == {
        "live_calls": 0,
        "cache_hit_calls": 0,
        "live_elapsed_seconds": None,
    }
    aggregated = _aggregate_request_results([])
    assert aggregated["elapsed_seconds"] is None
    assert aggregated["live_elapsed_seconds"] is None


def test_a_result_without_provenance_makes_the_aggregate_unknown():
    results = [
        {"elapsed_seconds": 2.0, **_request_call_provenance(2.0, False)},
        {"elapsed_seconds": 1.0},
    ]

    aggregated = _aggregate_request_results(results)

    assert aggregated["elapsed_seconds"] == 3.0
    assert {column: aggregated[column] for column in PROVENANCE} == dict.fromkeys(
        PROVENANCE
    )


@given(
    st.lists(
        st.tuples(
            st.floats(min_value=0, max_value=1e5, allow_nan=False),
            st.booleans(),
        ),
        max_size=12,
    )
)
def test_aggregated_provenance_counts_every_response_and_bounds_live_time(pairs):
    results = [
        {"elapsed_seconds": elapsed, **_request_call_provenance(elapsed, hit)}
        for elapsed, hit in pairs
    ]

    aggregated = _aggregate_request_results(results)

    hits = sum(hit for _, hit in pairs)
    assert aggregated["cache_hit_calls"] == hits
    assert aggregated["live_calls"] == len(pairs) - hits
    if not pairs:
        assert aggregated["live_elapsed_seconds"] is None
        return
    live = aggregated["live_elapsed_seconds"]
    assert 0 <= live <= aggregated["elapsed_seconds"]
    if hits == len(pairs):
        assert live == 0
    if hits == 0:
        assert live == aggregated["elapsed_seconds"]
    assert live == pytest.approx(sum(e for e, hit in pairs if not hit))


# -- end to end through the real request path ---------------------------------

ANSWER_MODES = (
    # Weighted toward complete answers so most households finish; the other
    # modes drive repair rounds, budget escalation, explanation repairs, and
    # failed requests (retries, partial rounds, failed chunks and households).
    "answer",
    "answer",
    "answer",
    "values_only",
    "empty",
    "truncated",
    "raise",
)
EXPLANATION_MODES = ("answer", "answer", "empty", "raise")
# No layer treats this failure as fatal or as provider instability, so the run
# carries on and the household keeps whatever its other requests returned.
REQUEST_FAILURE = "malformed provider payload"
SECONDS = {"rel": 1e-9, "abs": 1e-6}


@dataclass(frozen=True)
class MockCall:
    group: tuple
    cache_hit: bool
    seconds: float
    raised: bool
    explanation_request: bool


def _answer_arguments(with_explanations: bool) -> str:
    outputs = {}
    for index, variable in enumerate(US_VARIABLES, start=1):
        entry = {"value": float(index)}
        if with_explanations:
            entry["explanation"] = f"Explanation for {variable}. value = {index}"
        outputs[variable] = entry
    return json.dumps({"outputs": outputs})


def _explanation_arguments() -> str:
    return json.dumps(
        {
            variable: f"Explanation for {variable}. value = {index}"
            for index, variable in enumerate(US_VARIABLES, start=1)
        }
    )


def _mock_response(
    mode: str, cache_hit: bool, *, explanation_request: bool, responses_api: bool
):
    """A chat or Responses API response answering the requested tool."""
    function_name = arguments = None
    if explanation_request and mode == "answer":
        function_name, arguments = "submit_explanations", _explanation_arguments()
    elif not explanation_request and mode in ("answer", "values_only"):
        function_name = "submit_outputs"
        arguments = _answer_arguments(mode == "answer")
    truncated = mode == "truncated"
    # litellm's caching handler sets this on every disk-cache replay
    # (litellm/caching/caching_handler.py); a provider response lacks it.
    hidden = {"cache_hit": cache_hit}
    if responses_api:
        output = []
        if function_name:
            output = [
                SimpleNamespace(
                    type="function_call", name=function_name, arguments=arguments
                )
            ]
        return SimpleNamespace(
            output_text="",
            output=output,
            status="incomplete" if truncated else "completed",
            incomplete_details=(
                SimpleNamespace(reason="max_output_tokens") if truncated else None
            ),
            usage=SimpleNamespace(input_tokens=12, output_tokens=3, total_tokens=15),
            _hidden_params=hidden,
        )
    tool_calls = []
    if function_name:
        tool_calls = [
            SimpleNamespace(
                function=SimpleNamespace(name=function_name, arguments=arguments)
            )
        ]
    message = SimpleNamespace(content=None, tool_calls=tool_calls, function_call=None)
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=message,
                finish_reason="length" if truncated else "stop",
            )
        ],
        usage=litellm.Usage(prompt_tokens=12, completion_tokens=3, total_tokens=15),
        _hidden_params=hidden,
    )


def _assert_row_invariants(rows: pd.DataFrame) -> None:
    for column in ("live_calls", "cache_hit_calls"):
        assert rows[column].notna().all()
        assert (rows[column] >= 0).all()
        assert (rows[column] == rows[column].round()).all()
    live = rows["live_elapsed_seconds"]
    elapsed = rows["elapsed_seconds"]
    assert (live.isna() == elapsed.isna()).all()
    responded = (rows["live_calls"] + rows["cache_hit_calls"]) > 0
    # Sync rows are timed exactly when some response stands behind them.
    assert (responded == elapsed.notna()).all()
    timed = elapsed.notna()
    assert (live[timed] >= 0).all()
    assert (live[timed] <= elapsed[timed]).all()
    all_hits = (rows["live_calls"] == 0) & (rows["cache_hit_calls"] > 0)
    assert (live[all_hits & timed] == 0).all()
    no_hits = rows["cache_hit_calls"] == 0
    assert (live[no_hits & timed] == elapsed[no_hits & timed]).all()


# Past this many (count, sum) states in either half of the subset search, an
# example is discarded (hypothesis.reject), never passed unchecked.
SUBSET_STATE_LIMIT = 1 << 20


def _tolerance(expected: float) -> float:
    """The widest gap ``pytest.approx(expected, **SECONDS)`` accepts."""
    return max(SECONDS["rel"] * abs(expected), SECONDS["abs"])


def _half_states(groups: list[tuple[float, int]], most: int) -> set[tuple[int, float]]:
    """Every (count, sum) reachable by taking 0..multiplicity of each distinct
    duration in ``groups``, with count at most ``most``."""
    states = {(0, 0.0)}
    for value, multiplicity in groups:
        states = {
            (count + taken, total + taken * value)
            for count, total in states
            for taken in range(min(multiplicity, most - count) + 1)
        }
        if len(states) > SUBSET_STATE_LIMIT:
            event("subset search rejected: too many states")
            reject()
    return states


def _subset_sums_near(
    durations: list[float], count: int, low: float, high: float
) -> list[float]:
    """The distinct sums in [low, high] of the ``count``-element sub-multisets
    of ``durations``.

    Meet in the middle over the distinct durations: equal durations are
    interchangeable, so each half enumerates how many of each to take. This is
    exact, and replaces a search over ``combinations`` that had to give up
    (and pass) above 200,000 combinations."""
    if count > len(durations):
        return []
    groups = sorted(Counter(durations).items())
    # Split where the halves' enumeration sizes (products of multiplicity + 1)
    # are closest.
    sizes = [multiplicity + 1 for _, multiplicity in groups]
    best, split, left_size = math.inf, 0, 1
    total_size = math.prod(sizes)
    for index in range(len(groups) + 1):
        if index:
            left_size *= sizes[index - 1]
        balance = max(left_size, total_size // left_size)
        if balance < best:
            best, split = balance, index
    left = _half_states(groups[:split], count)
    right_by_count: dict[int, list[float]] = {}
    for taken, total in _half_states(groups[split:], count):
        right_by_count.setdefault(taken, []).append(total)
    for sums in right_by_count.values():
        sums.sort()
    found = set()
    for taken, total in left:
        sums = right_by_count.get(count - taken, [])
        start = bisect.bisect_left(sums, low - total)
        for other in sums[start : bisect.bisect_right(sums, high - total)]:
            found.add(total + other)
    return sorted(found)


def _row_matches_a_subset(
    returned: list[MockCall],
    hits: int,
    live: int,
    live_seconds: float,
    seconds: float,
) -> bool:
    """Whether some subset of the returned responses has the row's counts and
    times: ``live`` live responses whose seconds sum to ``live_seconds`` and
    ``hits`` replays that bring the total to ``seconds``.

    The two choices are independent once the live sum is fixed, so this asks
    which live sums near ``live_seconds`` exist, then whether the replays can
    close the gap to ``seconds`` from any of them."""
    hit_seconds = [call.seconds for call in returned if call.cache_hit]
    live_durations = [call.seconds for call in returned if not call.cache_hit]
    if hits > len(hit_seconds) or live > len(live_durations):
        return False
    if hits + live == 0:
        return math.isnan(seconds) and math.isnan(live_seconds)
    if math.isnan(seconds) or math.isnan(live_seconds):
        return False
    live_gap = _tolerance(live_seconds)
    total_gap = _tolerance(seconds)
    for live_sum in _subset_sums_near(
        live_durations, live, live_seconds - live_gap, live_seconds + live_gap
    ):
        if _subset_sums_near(
            hit_seconds,
            hits,
            seconds - live_sum - total_gap,
            seconds - live_sum + total_gap,
        ):
            return True
    return False


def _row_matches_a_subset_by_combinations(
    returned: list[MockCall],
    hits: int,
    live: int,
    live_seconds: float,
    seconds: float,
) -> bool:
    """The definition, by brute force over ``combinations``: the reference the
    meet-in-the-middle search is checked against on small inputs."""
    hit_calls = [call for call in returned if call.cache_hit]
    live_calls = [call for call in returned if not call.cache_hit]
    if hits > len(hit_calls) or live > len(live_calls):
        return False
    if hits + live == 0:
        return math.isnan(seconds) and math.isnan(live_seconds)
    for chosen_live in combinations(live_calls, live):
        live_sum = sum(call.seconds for call in chosen_live)
        if live_sum != pytest.approx(live_seconds, **SECONDS):
            continue
        for chosen_hits in combinations(hit_calls, hits):
            total = live_sum + sum(call.seconds for call in chosen_hits)
            if total == pytest.approx(seconds, **SECONDS):
                return True
    return False


def _mock_call(cache_hit: bool, seconds: float) -> MockCall:
    return MockCall(
        group=("scenario_000",),
        cache_hit=cache_hit,
        seconds=seconds,
        raised=False,
        explanation_request=False,
    )


# Durations from a small pool, so equal values and exact subset sums are
# common, plus arbitrary floats.
subset_seconds = st.one_of(
    st.sampled_from([0.0, 0.5, 1.0, 2.0, 3.0, 1e-7, 899.9]),
    st.floats(min_value=0, max_value=900, allow_nan=False),
)


@settings(max_examples=400, deadline=None)
@given(
    calls=st.lists(st.tuples(st.booleans(), subset_seconds), max_size=9),
    data=st.data(),
)
def test_the_subset_search_agrees_with_brute_force(calls, data):
    """Differential: the meet-in-the-middle oracle and the combinations
    definition agree on every input small enough to enumerate. The targets
    are a real subset's sums (so a match exists), the same with one of the
    two times moved (the total right but the live time wrong, or the
    reverse), or drawn freely."""
    returned = [_mock_call(cache_hit, seconds) for cache_hit, seconds in calls]
    hit_seconds = [call.seconds for call in returned if call.cache_hit]
    live_durations = [call.seconds for call in returned if not call.cache_hit]
    target = data.draw(st.sampled_from(["real", "moved", "free"]), label="target")
    if target != "free":
        live_picked = data.draw(
            st.sets(st.sampled_from(range(len(live_durations))))
            if live_durations
            else st.just(set()),
            label="live picked",
        )
        hits_picked = data.draw(
            st.sets(st.sampled_from(range(len(hit_seconds))))
            if hit_seconds
            else st.just(set()),
            label="hits picked",
        )
        live, hits = len(live_picked), len(hits_picked)
        live_seconds = sum(live_durations[index] for index in live_picked)
        seconds = live_seconds + sum(hit_seconds[index] for index in hits_picked)
        if target == "moved":
            shift = data.draw(st.sampled_from([-1.0, -0.5, 0.5, 1.0]), label="shift")
            if data.draw(st.booleans(), label="move the live time"):
                live_seconds += shift
            else:
                seconds += shift
        elif live + hits == 0:
            live_seconds = seconds = math.nan
    else:
        live = data.draw(st.integers(0, 10), label="live")
        hits = data.draw(st.integers(0, 10), label="hits")
        live_seconds = data.draw(st.one_of(st.just(math.nan), subset_seconds))
        seconds = data.draw(st.one_of(st.just(math.nan), subset_seconds))
    arguments = (returned, hits, live, live_seconds, seconds)
    assert _row_matches_a_subset(*arguments) == (
        _row_matches_a_subset_by_combinations(*arguments)
    )


def test_the_subset_search_checks_what_combinations_could_not():
    """The case review r2 named: four Sonnet chunks return 28 one-second live
    responses and the row keeps 20 (C(28, 20) is over three million). Twenty
    calls and 20 seconds match; twenty calls and 19 seconds must not."""
    returned = [_mock_call(False, 1.0) for _ in range(28)]
    assert math.comb(28, 20) > 200_000
    assert _row_matches_a_subset(returned, 0, 20, 20.0, 20.0)
    assert not _row_matches_a_subset(returned, 0, 20, 19.0, 19.0)
    assert not _row_matches_a_subset(returned, 0, 20, 20.0, 21.0)
    # The total alone is not enough: the live time must match too.
    assert not _row_matches_a_subset(returned, 0, 20, 19.0, 20.0)
    mixed = [_mock_call(False, 1.0), _mock_call(False, 2.0), _mock_call(True, 3.0)]
    assert _row_matches_a_subset(mixed, 1, 1, 1.0, 4.0)
    assert not _row_matches_a_subset(mixed, 1, 1, 2.0, 4.0)
    distinct = [_mock_call(index % 3 == 0, 1.0 + index / 64) for index in range(36)]
    kept = distinct[:5] + distinct[9:20]
    assert _row_matches_a_subset(
        distinct,
        sum(call.cache_hit for call in kept),
        sum(not call.cache_hit for call in kept),
        sum(call.seconds for call in kept if not call.cache_hit),
        sum(call.seconds for call in kept),
    )
    assert not _row_matches_a_subset(distinct, 0, 20, 0.5, 0.5)


def _expected_status(returned: list[MockCall]) -> str:
    hits = sum(call.cache_hit for call in returned)
    if not returned:
        return "no_response"
    if hits == len(returned):
        return "full_replay"
    return "live" if hits == 0 else "partial_replay"


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    # Every example runs a whole evaluation, so shrinking a failure would take
    # many minutes; the failing example's labelled draws print unshrunk.
    phases=[Phase.explicit, Phase.reuse, Phase.generate],
)
@given(
    data=st.data(),
    writer=st.sampled_from(["household", "single_output"]),
    # Chat completions with one output per request (Claude Sonnet 4.6) and
    # unchunked (Claude Opus 4.6); the Responses API unchunked (GPT-5.4) and
    # three outputs per request (GPT-5.5).
    model_id=st.sampled_from(
        ["claude-sonnet-4-6", "claude-opus-4-6", "gpt-5.4", "gpt-5.5"]
    ),
    output_count=st.integers(min_value=1, max_value=4),
    household_count=st.integers(min_value=1, max_value=2),
)
def test_rows_record_each_responses_provenance_and_agree_with_the_ledger(
    data, writer, model_id, output_count, household_count
):
    """Drive run_no_tools_eval / run_no_tools_single_output_eval through the
    real request path. Each mocked response's cache flag, duration and shape
    is drawn per call: an answer to the requested tool, values only, nothing,
    a length cut, or a failure. Households mix replays with live calls across
    chunks, repair rounds, budget escalations, explanation repairs, retries,
    and partial rounds, failed chunks and failed households.

    Oracle: the mock's own call history. The spend ledger must record every
    physical request it saw. A group none of whose requests failed must count
    every response it returned, with their times. A failure can drop returned
    responses from the row (a chunk or household that raised keeps none of its
    time), so there the row must equal some subset of the returned responses,
    counts and times together."""
    programs = US_VARIABLES[:output_count]
    scenarios = [
        _scenario(f"scenario_{index:03d}", 40_000.0 + index)
        for index in range(household_count)
    ]
    responses_api = eval_no_tools._uses_responses_api(model_id)
    clock = [1_000.0]
    current = {"group": None}
    calls: list[MockCall] = []
    real_run_single = eval_no_tools.run_single_no_tools

    def tracking_run_single(scenario, variable, *args, **kwargs):
        key = (scenario.id,) if writer == "household" else (scenario.id, variable)
        current["group"] = key
        return real_run_single(scenario, variable, *args, **kwargs)

    def fake_request(**kwargs):
        explanation_request = "submit_explanations" in json.dumps(
            kwargs.get("tools"), default=str
        )
        modes = EXPLANATION_MODES if explanation_request else ANSWER_MODES
        mode = data.draw(st.sampled_from(modes), label="mode")
        cache_hit = data.draw(st.booleans(), label="cache_hit") and mode != "raise"
        seconds = data.draw(
            st.floats(min_value=0, max_value=900, allow_nan=False),
            label="seconds",
        )
        clock[0] += seconds
        calls.append(
            MockCall(
                group=current["group"],
                cache_hit=cache_hit,
                seconds=seconds,
                raised=mode == "raise",
                explanation_request=explanation_request,
            )
        )
        if mode == "raise":
            raise ValueError(REQUEST_FAILURE)
        if explanation_request and mode == "answer":
            event("an explanation repair was answered")
        return _mock_response(
            mode,
            cache_hit,
            explanation_request=explanation_request,
            responses_api=responses_api,
        )

    fake_time = SimpleNamespace(
        perf_counter=lambda: clock[0],
        time=time.time,
        sleep=lambda _seconds: None,
    )
    runner = (
        run_no_tools_eval if writer == "household" else run_no_tools_single_output_eval
    )
    with (
        tempfile.TemporaryDirectory() as tmp,
        patch.object(eval_no_tools, "completion", side_effect=fake_request),
        patch.object(eval_no_tools, "responses", side_effect=fake_request),
        patch.object(eval_no_tools, "time", fake_time),
        patch.object(eval_no_tools, "run_single_no_tools", tracking_run_single),
    ):
        output_path = Path(tmp) / "run" / "predictions.csv"
        output_path.parent.mkdir()
        frame = runner(
            scenarios,
            models={"Model": model_id},
            programs=programs,
            output_path=str(output_path),
        )
        ledger = read_spend_ledger(spend_ledger_path(output_path))

        assert list(frame.columns) == list(NO_TOOLS_RESULT_COLUMNS)
        _assert_row_invariants(frame)

        group_columns = ["scenario_id"]
        if writer == "single_output":
            group_columns.append("variable")
        for key, rows in frame.groupby(group_columns):
            group_calls = [call for call in calls if call.group == tuple(key)]
            returned = [call for call in group_calls if not call.raised]
            failed = len(group_calls) - len(returned)
            hits = sum(call.cache_hit for call in returned)

            # The spend ledger records every physical request the mock saw:
            # answered ones with their cache flag, failed ones as errors.
            records = [
                record
                for record in ledger
                if record["scenario_id"] == key[0]
                and (writer == "household" or record["variables"] == [key[1]])
            ]
            answered = [
                record
                for record in records
                if record["status"] in ("ok", "parse_error")
            ]
            assert len(answered) == len(returned)
            assert sum(record["cache_hit"] for record in answered) == hits
            assert sum(record["status"] == "provider_error" for record in records) == (
                failed
            )

            # One request group per household (or per output): every row
            # repeats its counts, and its live time sums like elapsed time.
            assert rows["live_calls"].nunique() == 1
            assert rows["cache_hit_calls"].nunique() == 1
            row_hits = int(rows["cache_hit_calls"].iloc[0])
            row_live = int(rows["live_calls"].iloc[0])
            row_live_seconds = rows["live_elapsed_seconds"].sum(min_count=1)
            row_seconds = rows["elapsed_seconds"].sum(min_count=1)
            if not failed:
                assert row_hits == hits
                assert row_live == len(returned) - hits
                live_seconds = sum(c.seconds for c in returned if not c.cache_hit)
                assert row_live_seconds == pytest.approx(live_seconds, **SECONDS)
                assert row_seconds == pytest.approx(
                    sum(call.seconds for call in returned), **SECONDS
                )
                # Differential: the ledger's own elapsed times for the same
                # calls give the same sums.
                assert sum(
                    record["elapsed_seconds"]
                    for record in answered
                    if not record["cache_hit"]
                ) == pytest.approx(row_live_seconds, **SECONDS)
                assert sum(record["elapsed_seconds"] for record in answered) == (
                    pytest.approx(row_seconds, **SECONDS)
                )
            else:
                event("a request in the group failed")
                assert _row_matches_a_subset(
                    returned, row_hits, row_live, row_live_seconds, row_seconds
                )

        # The household classifier reads the same facts back from the rows.
        status = household_call_provenance(frame)["status"]
        for scenario in scenarios:
            household_calls = [c for c in calls if c.group[0] == scenario.id]
            if any(call.raised for call in household_calls):
                rows = frame[frame["scenario_id"] == scenario.id]
                expected = _brute_force_status(rows.to_dict("records"))
            else:
                expected = _expected_status(household_calls)
            assert status[("Model", scenario.id)] == expected
            event(f"household {expected}")
            event(f"household calls {min(len(household_calls), 6)}+")
        event("responses api" if responses_api else "chat completions")

        # The CSV carries the same values, and the run store returns it byte
        # for byte with the counts queryable from usage_json.
        written = pd.read_csv(output_path, float_precision="round_trip")
        pd.testing.assert_frame_equal(
            written[PROVENANCE].astype(float),
            frame[PROVENANCE].astype(float),
            check_exact=True,
        )
        db_path = Path(tmp) / "run.db"
        run_id = import_run_csv(db_path, output_path)
        exported = export_predictions_csv(db_path, run_id, Path(tmp) / "out.csv")
        assert exported.read_bytes() == output_path.read_bytes()
        with RunStore(db_path) as store:
            stored = store.connection.execute(
                "SELECT scenario_id, usage_json FROM responses WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        for row in stored:
            usage = json.loads(row["usage_json"])
            expected_rows = frame[frame["scenario_id"] == row["scenario_id"]]
            assert usage["cache_hit_calls"] in set(expected_rows["cache_hit_calls"])
            assert usage["live_calls"] in set(expected_rows["live_calls"])
            # One scenario can hold several responses (one per output for the
            # single-output writer), so, like the counts, the stored live time
            # must be one of its rows' values; an empty one is left out.
            live_times = expected_rows["live_elapsed_seconds"]
            if "live_elapsed_seconds" in usage:
                assert any(
                    usage["live_elapsed_seconds"] == pytest.approx(value, rel=1e-15)
                    for value in live_times.dropna()
                )
            else:
                assert live_times.isna().any()


@pytest.mark.parametrize("repair_replayed", [True, False])
def test_an_explanation_repair_records_its_own_provenance(repair_replayed):
    """Three live answers carry values without explanations (the initial
    request and both repair rounds), so the household asks for explanations
    alone; that repair is a replay or a live call, and counts as one."""
    clock = [0.0]
    requests = []

    def fake_completion(**kwargs):
        explanation_request = "submit_explanations" in json.dumps(
            kwargs.get("tools"), default=str
        )
        requests.append(explanation_request)
        cache_hit = explanation_request and repair_replayed
        seconds = 0.02 if cache_hit else 7.0
        clock[0] += seconds
        return _mock_response(
            "answer" if explanation_request else "values_only",
            cache_hit,
            explanation_request=explanation_request,
            responses_api=False,
        )

    fake_time = SimpleNamespace(
        perf_counter=lambda: clock[0], time=time.time, sleep=lambda _s: None
    )
    with (
        patch.object(eval_no_tools, "completion", side_effect=fake_completion),
        patch.object(eval_no_tools, "time", fake_time),
    ):
        result = eval_no_tools.run_single_no_tools(
            _scenario("scenario_000"),
            ["payroll_tax"],
            "claude-opus-4-6",
            include_explanations=True,
        )

    assert requests == [False, False, False, True]
    assert result["explanations"]["payroll_tax"] is not None
    assert result["live_calls"] == (3 if repair_replayed else 4)
    assert result["cache_hit_calls"] == (1 if repair_replayed else 0)
    assert result["live_elapsed_seconds"] == pytest.approx(
        21.0 if repair_replayed else 28.0
    )
    assert result["elapsed_seconds"] == pytest.approx(
        21.02 if repair_replayed else 28.0
    )
    assert result["spend_ledger"][-1]["phase"] == "explanation_repair"
    assert result["spend_ledger"][-1]["cache_hit"] is repair_replayed


def test_responses_api_requests_record_replays_and_live_calls():
    """A Responses API household whose first answer is a replay with nothing
    usable, then a live repair: one call of each kind, and only the repair's
    time is live."""
    clock = [50.0]
    script = iter([(True, 0.03, "empty"), (False, 41.0, "answer")])

    def fake_responses(**_kwargs):
        cache_hit, seconds, mode = next(script)
        clock[0] += seconds
        return _mock_response(
            mode, cache_hit, explanation_request=False, responses_api=True
        )

    fake_time = SimpleNamespace(
        perf_counter=lambda: clock[0], time=time.time, sleep=lambda _s: None
    )
    with (
        patch.object(eval_no_tools, "responses", side_effect=fake_responses),
        patch.object(eval_no_tools, "time", fake_time),
    ):
        result = eval_no_tools.run_single_no_tools(
            _scenario("scenario_000"),
            ["payroll_tax"],
            "gpt-5.4",
            include_explanations=True,
        )

    assert result["predictions"]["payroll_tax"] is not None
    assert result["cache_hit_calls"] == 1
    assert result["live_calls"] == 1
    assert result["live_elapsed_seconds"] == pytest.approx(41.0)
    assert result["elapsed_seconds"] == pytest.approx(41.03)
    assert [record["cache_hit"] for record in result["spend_ledger"]] == [True, False]


def test_a_household_that_raised_records_no_responses(monkeypatch, tmp_path):
    def raising_run_single(*_args, **_kwargs):
        raise ValueError("malformed provider payload")

    monkeypatch.setattr(eval_no_tools, "run_single_no_tools", raising_run_single)

    frame = run_no_tools_eval(
        [_scenario("scenario_000")],
        models={"Model": "claude-opus-4-6"},
        programs=US_VARIABLES[:2],
        output_path=str(tmp_path / "predictions.csv"),
    )

    assert set(frame["live_calls"]) == {0}
    assert set(frame["cache_hit_calls"]) == {0}
    assert frame["live_elapsed_seconds"].isna().all()
    assert frame["elapsed_seconds"].isna().all()
    assert set(household_call_provenance(frame)["status"]) == {"no_response"}


def test_resumed_output_keeps_older_rows_empty(monkeypatch, tmp_path):
    """Rows written before the columns existed stay empty when a run resumes
    and later households fill them."""
    scenarios = [_scenario("scenario_000"), _scenario("scenario_001", 60_000.0)]
    models = {"Model": "claude-opus-4-6"}
    programs = US_VARIABLES[:2]
    output_path = tmp_path / "predictions.csv"
    _write_resume_metadata(
        str(output_path),
        _build_resume_metadata(
            task="eval_no_tools_batch",
            scenarios=scenarios,
            models=models,
            programs=programs,
            run_id=None,
            include_explanations=True,
        ),
    )
    older_columns = [c for c in NO_TOOLS_RESULT_COLUMNS if c not in PROVENANCE]
    older = pd.DataFrame(
        [
            {
                **dict.fromkeys(older_columns),
                "call_id": "Model:scenario_000",
                "model": "Model",
                "scenario_id": "scenario_000",
                "variable": variable,
                "prediction": 1.0,
                "explanation": "Explanation. value = 1",
                "raw_response": "{}",
                "elapsed_seconds": 0.01,
            }
            for variable in programs
        ],
        columns=older_columns,
    )
    older.to_csv(output_path, index=False)

    def live_run_single(_scenario, variables, *_args, **_kwargs):
        return {
            "predictions": dict.fromkeys(variables, 2.0),
            "explanations": dict.fromkeys(variables, "Explanation. value = 2"),
            "raw_response": "{}",
            "error": None,
            "elapsed_seconds": 8.0,
            **_request_call_provenance(8.0, False),
        }

    monkeypatch.setattr(eval_no_tools, "run_single_no_tools", live_run_single)
    run_no_tools_eval(
        scenarios,
        models=models,
        programs=programs,
        output_path=str(output_path),
    )

    written = pd.read_csv(output_path)
    assert list(written.columns) == list(NO_TOOLS_RESULT_COLUMNS)
    resumed = written[written["scenario_id"] == "scenario_000"]
    fresh = written[written["scenario_id"] == "scenario_001"]
    assert resumed[PROVENANCE].isna().all().all()
    assert set(fresh["live_calls"]) == {1}
    assert set(fresh["cache_hit_calls"]) == {0}
    assert fresh["live_elapsed_seconds"].tolist() == [4.0, 4.0]
    status = household_call_provenance(written)["status"]
    assert status[("Model", "scenario_000")] == "unknown"
    assert status[("Model", "scenario_001")] == "live"


# -- batch, row repair and retry writers --------------------------------------


@given(
    output_count=st.integers(min_value=1, max_value=6),
    answered=st.booleans(),
    prompt_tokens=st.integers(min_value=0, max_value=100_000),
)
def test_batch_rows_are_live_untimed_and_never_cache_hits(
    output_count, answered, prompt_tokens
):
    unit = BatchUnit(
        scenario_id="scenario_000",
        variables=US_VARIABLES[:output_count],
        chunk_index=0,
    )
    result = (
        NormalizedResult(
            custom_id=unit.custom_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=10,
        )
        if answered
        else None
    )

    rows = rows_from_unit(
        model_name="Model",
        model_id="claude-sonnet-4-6",
        unit=unit,
        predictions={},
        explanations={},
        raw_response=None,
        error=None if answered else "batch_missing: no result entry returned",
        result=result,
    )

    assert len(rows) == output_count
    for row in rows:
        assert row["cache_hit_calls"] == 0
        assert row["live_calls"] == int(answered)
        assert row["live_elapsed_seconds"] is None
        assert row["elapsed_seconds"] is None
    frame = pd.DataFrame(rows)
    expected = "live" if answered else "no_response"
    assert set(household_call_provenance(frame)["status"]) == {expected}


def test_row_repair_carries_the_repair_requests_provenance(monkeypatch):
    calls = iter(
        [
            {
                "predictions": {"payroll_tax": None},
                "explanations": {"payroll_tax": None},
                "raw_response": None,
                "error": "Missing predictions after repair: payroll_tax",
                "elapsed_seconds": 0.02,
                **_request_call_provenance(0.02, True),
            },
            ValueError("provider returned malformed JSON"),
            {
                "predictions": {"payroll_tax": 7.0},
                "explanations": {"payroll_tax": "Payroll. value = 7"},
                "raw_response": "{}",
                "error": None,
                "elapsed_seconds": 5.5,
                **_request_call_provenance(5.5, False),
            },
        ]
    )

    def scripted_run_single(*_args, **_kwargs):
        outcome = next(calls)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(row_repair, "run_single_no_tools", scripted_run_single)
    monkeypatch.setitem(row_repair.MODELS, "Model", "claude-opus-4-6")

    final, attempts = repair_prediction_row(
        country="us",
        scenario=_scenario("scenario_000"),
        model="Model",
        variable="payroll_tax",
        attempts_per_row=3,
    )

    assert [
        (row["live_calls"], row["cache_hit_calls"], row["live_elapsed_seconds"])
        for row in attempts
    ] == [(0, 1, 0.0), (0, 0, None), (1, 0, 5.5)]
    assert final["live_elapsed_seconds"] == 5.5


def test_append_rows_widens_an_older_header_and_keeps_its_cells(tmp_path):
    path = tmp_path / "row_repair_attempts.csv"
    path.write_text(
        "model,scenario_id,variable,prediction,explanation\n"
        'm,s1,tax,1.10,"Tax, federal. value = 1.10"\n'
    )

    _append_rows(
        path,
        [
            {
                "variable": "benefit",
                "model": "m",
                "scenario_id": "s2",
                "prediction": 2.0,
                "explanation": "Benefit. value = 2",
                "live_calls": 1,
                "cache_hit_calls": 0,
                "live_elapsed_seconds": 3.5,
            }
        ],
    )
    _append_rows(
        path,
        [{"model": "m", "scenario_id": "s3", "variable": "tax", "prediction": 4.0}],
    )

    lines = path.read_text().splitlines()
    assert lines[0] == (
        "model,scenario_id,variable,prediction,explanation,"
        "live_calls,cache_hit_calls,live_elapsed_seconds"
    )
    assert lines[1] == 'm,s1,tax,1.10,"Tax, federal. value = 1.10",,,'
    frame = pd.read_csv(path)
    assert frame["scenario_id"].tolist() == ["s1", "s2", "s3"]
    assert frame.loc[1, "variable"] == "benefit"
    assert frame.loc[1, "live_elapsed_seconds"] == 3.5
    assert math.isnan(frame.loc[2, "live_calls"])


def test_append_rows_replaces_a_headerless_empty_file(tmp_path):
    path = tmp_path / "row_repair_attempts.csv"
    pd.DataFrame().to_csv(path, index=False)

    _append_rows(path, [{"model": "m", "live_calls": 1}])

    assert pd.read_csv(path).to_dict("records") == [{"model": "m", "live_calls": 1}]


def test_row_repair_merge_fills_only_the_repaired_row(tmp_path):
    source_path = tmp_path / "source.csv"
    repair_path = tmp_path / "repair.csv"
    pd.DataFrame(
        {
            "model": ["model_a", "model_a"],
            "scenario_id": ["s1", "s1"],
            "variable": ["tax", "benefit"],
            "prediction": [1.0, None],
            "explanation": ["Tax. value = 1", None],
            "raw_response": [None, None],
            "error": [None, "Missing prediction after repair: benefit"],
        }
    ).to_csv(source_path, index=False)
    pd.DataFrame(
        {
            "country": ["us"],
            "attempt": [1],
            "model": ["model_a"],
            "scenario_id": ["s1"],
            "variable": ["benefit"],
            "prediction": [22.0],
            "explanation": ["Repair benefit. value = 22"],
            "raw_response": ["raw"],
            "error": [None],
            "elapsed_seconds": [6.0],
            "live_calls": [1],
            "cache_hit_calls": [0],
            "live_elapsed_seconds": [6.0],
        }
    ).to_csv(repair_path, index=False)

    outputs = merge_row_repair_predictions(
        source_predictions=source_path,
        repair_predictions=repair_path,
        output_dir=tmp_path / "merged",
    )

    merged = pd.read_csv(outputs["merged_predictions"]).set_index("variable")
    assert merged.loc["benefit", "live_calls"] == 1
    assert merged.loc["benefit", "live_elapsed_seconds"] == 6.0
    assert merged.loc["tax", PROVENANCE].isna().all()
    assert set(household_call_provenance(merged.reset_index())["status"]) == {"unknown"}


def test_a_repair_that_predates_the_columns_leaves_the_row_unknown(tmp_path):
    """An older repair file has no provenance. The row it replaces must not
    keep the source's values, which described another request: beside the
    repair's 2 seconds they would claim 10 live seconds."""
    source_path = tmp_path / "source.csv"
    repair_path = tmp_path / "repair.csv"
    pd.DataFrame(
        {
            "model": ["model_a", "model_a"],
            "scenario_id": ["s1", "s1"],
            "variable": ["tax", "benefit"],
            "prediction": [1.0, None],
            "explanation": ["Tax. value = 1", None],
            "raw_response": [None, None],
            "error": [None, "Missing prediction after repair: benefit"],
            "elapsed_seconds": [10.0, 10.0],
            "live_calls": [1, 1],
            "cache_hit_calls": [0, 0],
            "live_elapsed_seconds": [10.0, 10.0],
        }
    ).to_csv(source_path, index=False)
    pd.DataFrame(
        {
            "country": ["us"],
            "attempt": [1],
            "model": ["model_a"],
            "scenario_id": ["s1"],
            "variable": ["benefit"],
            "prediction": [22.0],
            "explanation": ["Repair benefit. value = 22"],
            "raw_response": ["raw"],
            "error": [None],
            "elapsed_seconds": [2.0],
        }
    ).to_csv(repair_path, index=False)

    outputs = merge_row_repair_predictions(
        source_predictions=source_path,
        repair_predictions=repair_path,
        output_dir=tmp_path / "merged",
    )

    merged = pd.read_csv(outputs["merged_predictions"]).set_index("variable")
    assert merged.loc["benefit", "elapsed_seconds"] == 2.0
    assert merged.loc["benefit", PROVENANCE].isna().all()
    assert merged.loc["tax", "live_calls"] == 1
    assert merged.loc["tax", "live_elapsed_seconds"] == 10.0
    timed = merged["live_elapsed_seconds"].notna()
    assert (
        merged.loc[timed, "live_elapsed_seconds"]
        <= merged.loc[timed, "elapsed_seconds"]
    ).all()
    assert set(household_call_provenance(merged.reset_index())["status"]) == {"unknown"}


def test_retry_merge_carries_the_retry_rows_provenance(tmp_path):
    source_path = tmp_path / "source.csv"
    retry_path = tmp_path / "retry.csv"
    target_path = tmp_path / "target.csv"
    pd.DataFrame(
        {
            "model": ["model_a", "model_a", "model_b"],
            "scenario_id": ["s1", "s1", "s1"],
            "variable": ["tax", "benefit", "tax"],
            "prediction": [1.0, None, 2.0],
            "explanation": ["Tax. value = 1", "", "Tax. value = 2"],
            "error": [None, "Missing predictions after repair: benefit", None],
        }
    ).to_csv(source_path, index=False)
    pd.DataFrame(
        {
            "model": ["model_a", "model_a"],
            "scenario_id": ["s1", "s1"],
            "variable": ["tax", "benefit"],
            "prediction": [10.0, 20.0],
            "explanation": ["Retry tax. value = 10", "Retry benefit. value = 20"],
            "error": [None, None],
            "elapsed_seconds": [0.01, 0.01],
            "live_calls": [0, 0],
            "cache_hit_calls": [1, 1],
            "live_elapsed_seconds": [0.0, 0.0],
        }
    ).to_csv(retry_path, index=False)
    pd.DataFrame({"model": ["model_a"], "scenario_id": ["s1"]}).to_csv(
        target_path, index=False
    )

    outputs = merge_retry_predictions(
        source_predictions=source_path,
        retry_predictions=retry_path,
        target_units=target_path,
        output_dir=tmp_path / "merged",
    )

    merged = pd.read_csv(outputs["merged_predictions"])
    retried = merged[merged["model"] == "model_a"]
    kept = merged[merged["model"] == "model_b"]
    assert set(retried["cache_hit_calls"]) == {1}
    assert set(retried["live_elapsed_seconds"]) == {0.0}
    assert kept[PROVENANCE].isna().all().all()
    status = household_call_provenance(merged)["status"]
    assert status[("model_a", "s1")] == "full_replay"
    assert status[("model_b", "s1")] == "unknown"


# -- run store ----------------------------------------------------------------

optional_count = st.one_of(st.none(), st.integers(min_value=0, max_value=40))
optional_seconds = st.one_of(
    st.none(), st.floats(min_value=0, max_value=1e4, allow_nan=False)
)


@settings(max_examples=50, deadline=None)
@given(
    st.lists(
        st.tuples(optional_count, optional_count, optional_seconds, optional_seconds),
        min_size=1,
        max_size=6,
    )
)
@example([(2, 1, 3.25, 3.5), (0, 3, 0.0, 0.015), (None, None, None, 0.1)])
@example([(1, 0, 0.1 + 0.2, 0.1 + 0.2)])
def test_run_store_round_trips_provenance_byte_for_byte(households):
    frame = pd.DataFrame(
        [
            {
                "call_id": f"Model:scenario_{index:03d}",
                "model": "Model",
                "scenario_id": f"scenario_{index:03d}",
                "variable": variable,
                "prediction": 1.0,
                "explanation": "Explanation. value = 1",
                "raw_response": "{}",
                "error": None,
                "elapsed_seconds": elapsed,
                "live_calls": live_calls,
                "cache_hit_calls": cache_hit_calls,
                "live_elapsed_seconds": live_elapsed,
            }
            for index, (live_calls, cache_hit_calls, live_elapsed, elapsed) in (
                enumerate(households)
            )
            for variable in ("payroll_tax", "self_employment_tax")
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "run" / "predictions.csv"
        csv_path.parent.mkdir()
        frame.to_csv(csv_path, index=False)
        db_path = Path(tmp) / "run.db"

        run_id = import_run_csv(db_path, csv_path)
        exported = export_predictions_csv(db_path, run_id, Path(tmp) / "out.csv")

        assert exported.read_bytes() == csv_path.read_bytes()
        with RunStore(db_path) as store:
            usage = {
                row["scenario_id"]: json.loads(row["usage_json"])
                for row in store.connection.execute(
                    "SELECT scenario_id, usage_json FROM responses"
                ).fetchall()
            }
        # The typed fields are what the repo's own reader (pd.read_csv with
        # default options) makes of the CSV; that parser may land an ulp from
        # the float that was written, so compare exactly against it and
        # closely against the drawn value.
        imported = pd.read_csv(csv_path).groupby("scenario_id").first()
        for index, (live_calls, cache_hit_calls, live_elapsed, _) in enumerate(
            households
        ):
            scenario_id = f"scenario_{index:03d}"
            stored = usage[scenario_id]
            assert stored.get("live_calls") == live_calls
            assert stored.get("cache_hit_calls") == cache_hit_calls
            if live_elapsed is None:
                assert "live_elapsed_seconds" not in stored
            else:
                assert isinstance(stored["live_elapsed_seconds"], float)
                assert (
                    stored["live_elapsed_seconds"]
                    == (imported.loc[scenario_id, "live_elapsed_seconds"])
                )
                assert stored["live_elapsed_seconds"] == pytest.approx(
                    live_elapsed, rel=1e-15, abs=1e-12
                )
                event("typed live time stored")


def test_run_store_round_trips_a_csv_that_predates_the_columns(tmp_path):
    frame = pd.DataFrame(
        {
            "call_id": ["Model:scenario_000"] * 2,
            "model": ["Model"] * 2,
            "scenario_id": ["scenario_000"] * 2,
            "variable": ["payroll_tax", "self_employment_tax"],
            "prediction": [1.0, 2.0],
            "explanation": ["A. value = 1", "B. value = 2"],
            "elapsed_seconds": [0.015, 0.015],
        }
    )
    csv_path = tmp_path / "run" / "predictions.csv"
    csv_path.parent.mkdir()
    frame.to_csv(csv_path, index=False)

    run_id = import_run_csv(tmp_path / "run.db", csv_path)
    exported = export_predictions_csv(tmp_path / "run.db", run_id, tmp_path / "o.csv")

    assert exported.read_bytes() == csv_path.read_bytes()
    assert not set(PROVENANCE) & set(pd.read_csv(exported).columns)


# -- analysis -------------------------------------------------------------------


def _brute_force_status(rows: list[dict]) -> str:
    if any(row["live_calls"] is None or row["cache_hit_calls"] is None for row in rows):
        return "unknown"
    any_live = any(row["live_calls"] > 0 for row in rows)
    any_hit = any(row["cache_hit_calls"] > 0 for row in rows)
    if any_live and any_hit:
        return "partial_replay"
    if any_hit:
        return "full_replay"
    if any_live:
        return "live"
    return "no_response"


provenance_rows = st.lists(
    st.fixed_dictionaries(
        {
            "variable": st.sampled_from(US_VARIABLES[:4]),
            "elapsed_seconds": optional_seconds,
            "live_calls": optional_count,
            "cache_hit_calls": optional_count,
            "live_elapsed_seconds": optional_seconds,
            "prompt_tokens": st.integers(min_value=0, max_value=5_000),
            "completion_tokens": st.integers(min_value=0, max_value=5_000),
            "total_cost_usd": st.floats(min_value=0, max_value=5, allow_nan=False),
        }
    ),
    min_size=1,
    max_size=5,
)


@settings(max_examples=150, deadline=None)
@given(
    st.dictionaries(
        st.tuples(st.sampled_from(["m1", "m2"]), st.sampled_from(["s1", "s2", "s3"])),
        provenance_rows,
        min_size=1,
    )
)
def test_household_classification_and_published_numbers(households):
    records = [
        {"model": model, "scenario_id": scenario_id, "prediction": 1.0, **row}
        for (model, scenario_id), rows in households.items()
        for row in rows
    ]
    frame = pd.DataFrame(records)

    provenance = household_call_provenance(frame)

    assert set(provenance.index) == set(households)
    assert set(provenance["status"]) <= set(HOUSEHOLD_CALL_STATUSES)
    for key, rows in households.items():
        assert provenance.loc[key, "status"] == _brute_force_status(rows)
        live = provenance.loc[key, "live_elapsed_seconds"]
        values = [row["live_elapsed_seconds"] for row in rows]
        if provenance.loc[key, "status"] == "unknown" or all(
            value is None for value in values
        ):
            assert math.isnan(live)
        else:
            assert live == pytest.approx(sum(v for v in values if v is not None))

    # Adding the provenance columns changes nothing published.
    without = frame.drop(columns=PROVENANCE)
    assert model_cost_latency(frame) == model_cost_latency(without)
    pd.testing.assert_frame_equal(
        usage_summary_by_model(frame), usage_summary_by_model(without)
    )


def test_frames_without_the_columns_classify_as_unknown():
    frame = pd.DataFrame(
        {
            "model": ["m", "m"],
            "scenario_id": ["s1", "s2"],
            "variable": ["tax", "tax"],
            "elapsed_seconds": [0.02, 30.0],
        }
    )

    provenance = household_call_provenance(frame)

    assert provenance["status"].tolist() == ["unknown", "unknown"]
    assert provenance["live_elapsed_seconds"].isna().all()
    assert household_call_provenance(pd.DataFrame()).empty


@pytest.mark.skipif(
    not FROZEN_US_PREDICTIONS.exists(), reason="frozen snapshot not checked out"
)
def test_the_frozen_us_run_predates_the_columns():
    """The frozen board predates the fields, so every household is unknown:
    its replays are identified only by the audit's evidence (#228)."""
    header = pd.read_csv(FROZEN_US_PREDICTIONS, nrows=0)
    assert not set(PROVENANCE) & set(header.columns)

    sample = pd.read_csv(
        FROZEN_US_PREDICTIONS,
        nrows=500,
        usecols=["model", "scenario_id", "variable", "elapsed_seconds"],
    )
    assert set(household_call_provenance(sample)["status"]) == {"unknown"}
