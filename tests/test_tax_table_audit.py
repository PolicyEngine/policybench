"""The Tax Table audit (reference_audit/2026-10-10-tax-table): the constructed
table's invariants, its agreement with the tables the IRS published, the two
scorers' agreement, and the recorded evidence.

Invariants of the constructed Tax Table, for every taxable income under $100,000,
filing status column and year:
- it is a whole, non-negative number of dollars, and zero at zero;
- it is non-decreasing in taxable income, and constant inside a band;
- it is the rate schedule's tax at the band's midpoint, rounded to a dollar;
- it is within half a band-width times the band's top marginal rate, plus the
  half dollar of rounding, of the schedule's tax on the income itself, and so
  within one band-width times that rate;
- the columns are ordered as the schedules are: joint, head of household, single;
- above the ceiling the instructions' method is the rate schedule exactly.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
import shutil
import sys
import tempfile
from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from policybench.analysis import BINARY_PROGRAMS, weighted_hit_rate_scores_by_model
from policybench.spec import metric_type_for_output, output_group_id

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "reference_audit/2026-10-10-tax-table"
YEARS = (2025, 2026)
IRS_TABLES = {
    2025: AUDIT / "law/irs_tax_table_2025.csv",
    2026: AUDIT / "law/irs_tax_table_2026_draft.csv",
}
FEDERAL = "federal_income_tax_before_refundable_credits"


@cache
def _script(name: str):
    path = AUDIT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"tax_table_audit_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


T = _script("tax_table")

# Taxable income to the cent, as the references carry it.
incomes = st.integers(min_value=0, max_value=T.CEILING * 100 - 1).map(
    lambda cents: cents / 100
)
statuses = st.sampled_from(T.STATUSES)
years = st.sampled_from(YEARS)
# Amounts in cents up to $2,000,000. Dollars and cents are drawn apart because
# Hypothesis draws an integer range wider than 24 bits mostly from its small
# end: drawn as cents, 13 of 40 seeded runs missed a wrong top rate
# (scripts/top_rate_detection.py, verification/top_rate_detection.json).
wide_cents = st.builds(
    lambda dollars, cents: 100 * dollars + cents,
    st.integers(min_value=0, max_value=2_000_000),
    st.integers(min_value=0, max_value=99),
)


def _top_rate_in_band(income: float, status: str, year: int) -> float:
    _, upper = T.band(income)
    return T.marginal_rate(upper - 0.01, status, year)


# --- The construction's invariants -------------------------------------------


@settings(max_examples=2000, deadline=None)
@given(incomes, incomes, statuses, years)
def test_the_table_never_falls_as_taxable_income_rises(a, b, status, year):
    low, high = sorted((a, b))
    assert T.table_tax(low, status, year) <= T.table_tax(high, status, year)


@settings(max_examples=2000, deadline=None)
@given(incomes, statuses, years)
def test_the_table_is_whole_dollars_and_constant_inside_its_band(income, status, year):
    lower, upper = T.band(income)
    assert lower <= income < upper
    tax = T.table_tax(income, status, year)
    assert isinstance(tax, int) and tax >= 0
    assert T.table_tax(lower, status, year) == tax
    assert T.table_tax(upper - 0.01, status, year) == tax


@settings(max_examples=2000, deadline=None)
@given(incomes, statuses, years)
def test_the_table_is_the_schedule_at_the_midpoint_rounded_half_up(
    income, status, year
):
    lower, upper = T.band(income)
    at_midpoint = T.schedule_tax_cents(50 * (lower + upper), status, year)
    # Half a dollar rounds up; everything else rounds to the nearer dollar.
    assert T.table_tax(income, status, year) == (at_midpoint + 50) // 100


@settings(max_examples=3000, deadline=None)
@given(incomes, statuses, years)
def test_the_table_stays_within_half_a_band_of_the_schedule(income, status, year):
    lower, upper = T.band(income)
    width = upper - lower
    rate = _top_rate_in_band(income, status, year)
    gap = abs(T.table_tax(income, status, year) - T.schedule_tax(income, status, year))
    # The tax on the midpoint is within half a band of the tax on the income,
    # the whole-dollar rounding adds at most half a dollar, and the schedule tax
    # compared with is itself rounded to the cent.
    assert gap <= width / 2 * rate + 0.5 + 0.005 + 1e-9
    # The looser bound the audit was asked to state.
    assert gap <= width * rate + 0.005 + 1e-9


@settings(max_examples=1000, deadline=None)
@given(incomes, years)
def test_the_columns_are_ordered_as_the_schedules_are(income, year):
    joint, head, single, separate = (
        T.table_tax(income, status, year)
        for status in ("joint", "head_of_household", "single", "separate")
    )
    assert joint <= head <= single
    # Under the ceiling the separate schedule is the single schedule.
    assert separate == single


@settings(max_examples=500, deadline=None)
@given(wide_cents, statuses, years)
def test_at_or_above_the_ceiling_the_method_is_the_schedule(cents, status, year):
    income = T.CEILING + cents / 100
    assert T.line_16_tax(income, status, year) == T.schedule_tax(income, status, year)


@pytest.mark.parametrize("year", YEARS)
@pytest.mark.parametrize("status", T.STATUSES)
def test_the_table_starts_at_zero_and_meets_the_worksheet_at_the_ceiling(year, status):
    assert T.table_tax(0, status, year) == 0
    assert T.line_16_tax(0, status, year) == 0
    below = T.line_16_tax(T.CEILING - 0.01, status, year)
    at = T.line_16_tax(T.CEILING, status, year)
    # The last band's midpoint is $25 under the ceiling.
    rate = T.marginal_rate(T.CEILING, status, year)
    assert 0 <= at - below <= 25 * rate + 0.5 + 1e-9


def test_the_bands_tile_zero_to_the_ceiling():
    bands = T.bands()
    assert len(bands) == 2062
    assert bands[0][0] == 0 and bands[-1][1] == T.CEILING
    assert all(a[1] == b[0] for a, b in zip(bands, bands[1:]))
    assert {upper - lower for lower, upper in bands} == {5, 10, 25, 50}
    assert all(T.band(lower) == (lower, upper) for lower, upper in bands)
    for value in (-0.01, T.CEILING, float("nan")):
        with pytest.raises(ValueError):
            T.band(value)


@pytest.mark.parametrize("year", YEARS)
@pytest.mark.parametrize("status", T.STATUSES)
def test_the_printed_base_amounts_follow_from_the_thresholds_and_rates(year, status):
    """Each "$X plus r% of the excess over $T" of the revenue procedure: X is
    the schedule's tax on T."""
    thresholds = T.SCHEDULES[year][status]
    assert thresholds == tuple(sorted(thresholds))
    assert (
        tuple(T.schedule_tax_cents(100 * t, status, year) for t in thresholds)
        == T.BASE_AMOUNTS[year][status]
    )


@pytest.mark.parametrize("year", YEARS)
@pytest.mark.parametrize("status", T.STATUSES)
def test_the_schedule_is_each_printed_formula_inside_its_bracket(year, status):
    """ "$X plus r% of the excess over $T", $1,000 into every bracket: the
    first bracket's 10% of the taxable income, and the last bracket's 37%."""
    thresholds = (0, *T.SCHEDULES[year][status])
    bases = (0, *T.BASE_AMOUNTS[year][status])
    assert T.RATES == (10, 12, 22, 24, 32, 35, 37)
    for threshold, base, rate in zip(thresholds, bases, T.RATES, strict=True):
        cents = 100 * (threshold + 1000)
        # r% of $1,000 is r times 1,000 cents.
        assert T.schedule_tax_cents(cents, status, year) == base + rate * 1000
        assert T.marginal_rate(threshold + 1000, status, year) == rate / 100


@settings(max_examples=1000, deadline=None)
@given(wide_cents, wide_cents, statuses, years)
def test_the_schedule_is_non_decreasing_and_taxes_no_dollar_above_37_percent(
    a, b, status, year
):
    low, high = sorted((a, b))
    tax_low = T.schedule_tax_cents(low, status, year)
    tax_high = T.schedule_tax_cents(high, status, year)
    assert 0 <= tax_low <= tax_high
    assert tax_high - tax_low <= math.ceil(0.37 * (high - low)) + 1


# --- Against the tables the IRS published ------------------------------------


def _irs_table(year: int) -> list[dict]:
    with IRS_TABLES[year].open() as handle:
        return [{k: int(v) for k, v in row.items()} for row in csv.DictReader(handle)]


@pytest.mark.parametrize("year", YEARS)
def test_the_constructed_table_is_the_irs_table_in_every_cell(year):
    """2025: the Tax Table of Publication 1040 (2025). 2026: the IRS's early
    release draft of Publication 1040 (2026), posted 2026-09-16, after the
    reference freeze. All 2,062 bands and four columns of each."""
    published = _irs_table(year)
    built = T.constructed_table(year)
    assert [(r["at_least"], r["less_than"]) for r in published] == T.bands()
    assert len(published) * len(T.STATUSES) == 8248
    assert built == published


@pytest.mark.parametrize("year", YEARS)
def test_no_other_simple_rule_reproduces_the_irs_table(year):
    """The midpoint and the half-dollar rule are identified by the table, not
    assumed: the band's lower or upper bound, or another rounding of the tax
    on the midpoint, each miss more than a thousand cells."""
    misses = dict.fromkeys(
        ("lower_bound", "upper_bound", "half_down", "half_even", "truncate"), 0
    )
    for row in _irs_table(year):
        lower, upper = row["at_least"], row["less_than"]
        for status in T.STATUSES:
            thresholds = T.SCHEDULES[year][status]
            units = T._half_cents(lower + upper, thresholds)
            quotient, rest = divmod(units, 200)
            half_even = quotient + (rest > 100 or (rest == 100 and quotient % 2 == 1))
            candidates = {
                "lower_bound": (T._half_cents(2 * lower, thresholds) + 100) // 200,
                "upper_bound": (T._half_cents(2 * upper, thresholds) + 100) // 200,
                "half_down": (units + 99) // 200,
                "half_even": half_even,
                "truncate": quotient,
            }
            for rule, value in candidates.items():
                misses[rule] += value != row[status]
    assert min(misses.values()) > 1000


def test_the_parser_refuses_text_that_is_not_the_whole_table():
    parser = _script("parse_irs_tax_table")
    rows = [f"{lower:,} {upper:,} 1 1 1 1" for lower, upper in parser.expected_bands()]
    # After the Tax Table come the worksheet and the Earned Income Credit
    # table, whose rows can also be six numbers; they are not read.
    whole = "\n".join(rows) + f"\n2025 {parser.END}\n1 50 2 2 2 2\n"
    parsed = parser.parse(whole)
    assert len(parsed) == 2062
    assert [row[:2] for row in parsed] == parser.expected_bands()
    assert parser.expected_bands() == T.bands()
    with pytest.raises(SystemExit):
        parser.parse("\n".join(rows))  # no worksheet heading
    with pytest.raises(SystemExit):
        parser.parse("\n".join(rows[:-1]) + f"\n{parser.END}\n")  # a band missing
    with pytest.raises(SystemExit):
        parser.parse("\n".join(rows[1:] + rows[:1]) + f"\n{parser.END}\n")  # order


# --- The two scorers ---------------------------------------------------------

VARIABLES = (
    FEDERAL,
    "federal_refundable_credits",
    "state_income_tax_before_refundable_credits",
    "payroll_tax",
    "snap",
    "local_income_tax",
    "free_school_meals_eligible",
    "head_medicaid_eligible",
    "spouse_medicaid_eligible",
    "child1_medicaid_eligible",
    "child1_early_head_start_eligible",
    "child1_head_start_eligible",
    "dependent1_wic_eligible",
)


def test_the_independent_scorer_groups_and_types_outputs_as_the_repo_does():
    scorer = _script("independent_scorer")
    weights = scorer.group_weights()
    for variable in VARIABLES + ("head_medicare_eligible", "child12_chip_eligible"):
        group = scorer.output_group(variable, weights)
        assert group == output_group_id(variable)
        binary = (
            metric_type_for_output(variable) == "binary" or group in BINARY_PROGRAMS
        )
        assert scorer.is_flag(group) == binary
    assert all(scorer.is_flag(group) for group in BINARY_PROGRAMS)


@st.composite
def _toy_run(draw):
    """A small run: households, references, exclusions, a second accepted
    value for some amounts, and two models' answers."""
    households = [f"scenario_{i:03d}" for i in range(draw(st.integers(1, 4)))]
    reference, exclusions, also_accept = [], [], {}
    for household in households:
        chosen = draw(
            st.lists(st.sampled_from(VARIABLES), min_size=1, max_size=8, unique=True)
        )
        for variable in chosen:
            if variable.endswith("_eligible"):
                value = float(draw(st.integers(0, 1)))
            else:
                value = draw(st.integers(0, 4000)) / 4
                if draw(st.booleans()):
                    shift = draw(st.sampled_from([-8, -5, -4, -1, 1, 4, 5, 8, 16])) / 4
                    also_accept[(household, variable)] = value + shift
            reference.append((household, variable, value))
            if draw(st.integers(0, 5)) == 0:
                exclusions.append((household, variable))
    answers = []
    for model in ("model-a", "model-b"):
        for household, variable, value in reference:
            if variable.endswith("_eligible"):
                answer = draw(st.sampled_from([0.0, 1.0, 0.5, 2.0, None]))
            else:
                other = also_accept.get((household, variable), value)
                base = draw(st.sampled_from([value, other]))
                shift = draw(st.sampled_from([0, 1, 2, 3, 4, 5, -3, -4, -5, 400])) / 4
                answer = draw(st.sampled_from([base + shift, None]))
            if draw(st.integers(0, 9)):  # one answer in ten is absent
                answers.append((model, household, variable, answer))
    return households, reference, exclusions, also_accept, answers


def _write_run(directory: Path, reference, exclusions, answers) -> None:
    with (directory / "reference_outputs.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["scenario_id", "variable", "value", "impact_weight"])
        writer.writerows([s, v, repr(value), ""] for s, v, value in reference)
    (directory / "reference_exclusions.json").write_text(
        json.dumps(
            {"exclusions": [{"scenario_id": s, "variable": v} for s, v in exclusions]}
        )
    )
    with gzip.open(directory / "predictions.csv.gz", "wt", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["model", "scenario_id", "variable", "prediction"])
        writer.writerows(
            [m, s, v, "" if answer is None else repr(answer)]
            for m, s, v, answer in answers
        )


def _repo_exact(directory: Path, exclusions, also_accept=None) -> dict[str, float]:
    """The repo's headline exact rate; with a second accepted value, each model
    is scored against the accepted value nearer its own answer."""
    truth = pd.read_csv(directory / "reference_outputs.csv")
    excluded = set(exclusions)
    keep = [(s, v) not in excluded for s, v in zip(truth.scenario_id, truth.variable)]
    truth = truth[keep].reset_index(drop=True)
    predictions = pd.read_csv(directory / "predictions.csv.gz")
    out = {}
    for model, rows in predictions.groupby("model"):
        own = truth.copy()
        if also_accept:
            given_answers = {
                (s, v): p
                for s, v, p in zip(rows.scenario_id, rows.variable, rows.prediction)
            }
            values = []
            for s, v, value in zip(own.scenario_id, own.variable, own.value):
                other = also_accept.get((s, v))
                answer = given_answers.get((s, v))
                if other is not None and answer is not None and not pd.isna(answer):
                    if abs(answer - other) < abs(answer - value):
                        value = other
                values.append(value)
            own["value"] = values
        scored = weighted_hit_rate_scores_by_model(own, rows, {}, country="us")
        out[model] = (
            float(scored["weighted_exact"].iloc[0]) * 100 if len(scored) else None
        )
    return out


@settings(max_examples=150, deadline=None)
@given(_toy_run())
def test_the_independent_scorer_agrees_with_the_repo_scorer(tmp_path_factory, run):
    households, reference, exclusions, also_accept, answers = run
    if not answers or len(set(exclusions)) == len(reference):
        return
    directory = tmp_path_factory.mktemp("toy")
    _write_run(directory, reference, exclusions, answers)
    scorer = _script("independent_scorer")
    for accepted in (None, also_accept):
        if accepted is not None and not accepted:
            continue
        mine = scorer.exact_rates(directory, also_accept=accepted)
        theirs = _repo_exact(directory, exclusions, accepted)
        assert set(mine) == set(theirs)
        for model, rate in theirs.items():
            assert rate is not None
            assert mine[model] == pytest.approx(rate, abs=1e-9)
        if accepted:
            # Accepting a second value never lowers a model's rate.
            plain = scorer.exact_rates(directory)
            assert all(mine[m] >= plain[m] - 1e-12 for m in mine)


# --- The recorded evidence ---------------------------------------------------

VERIFICATION = AUDIT / "verification"
YEAR = 2026
CONVENTIONS = ("schedule", "either", "table", "exclude")


@cache
def _release_bytes(name: str) -> bytes:
    """A file of the frozen run as the release commit holds it (sha256-checked)."""
    try:
        return _script("release").read(name)
    except SystemExit as error:
        pytest.fail(str(error))


def _release_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(_release_bytes(name)))


@cache
def _sweep() -> pd.DataFrame:
    return pd.read_csv(VERIFICATION / "sweep_tax_table.csv")


@cache
def _units() -> pd.DataFrame:
    return pd.read_csv(VERIFICATION / "tax_units.csv")


@cache
def _cells() -> pd.DataFrame:
    return pd.read_csv(VERIFICATION / "federal_cells.csv")


@cache
def _impact() -> dict:
    return json.loads((VERIFICATION / "leaderboard_impact.json").read_text())


@cache
def _models() -> pd.DataFrame:
    return pd.read_csv(VERIFICATION / "leaderboard_impact_models.csv").set_index(
        "model"
    )


@cache
def _excluded() -> frozenset:
    record = json.loads(_release_bytes("reference_exclusions.json"))
    return frozenset((e["scenario_id"], e["variable"]) for e in record["exclusions"])


def test_a_surviving_spouse_reads_the_joint_column():
    """ "This column must also be used by a qualifying surviving spouse." """
    assert T.COLUMN_FOR_FILING_STATUS == {
        "SINGLE": "single",
        "JOINT": "joint",
        "SEPARATE": "separate",
        "HEAD_OF_HOUSEHOLD": "head_of_household",
        "SURVIVING_SPOUSE": "joint",
    }


def test_the_sweep_baseline_is_the_release_reference():
    sweep = _sweep()
    reference = _release_csv("reference_outputs.csv")
    frozen = {
        (row.scenario_id, row.variable): row.value for row in reference.itertuples()
    }
    recorded = {
        (row.scenario_id, row.variable): row.reference for row in sweep.itertuples()
    }
    assert len(sweep) == len(recorded) == 1984
    assert recorded == frozen
    scored = [key not in _excluded() for key in zip(sweep.scenario_id, sweep.variable)]
    assert list(sweep.scored) == scored and sum(scored) == 1926
    gap = (sweep.baseline - sweep.reference).abs()
    assert gap[sweep.scored].max() <= 1e-3
    # The copied formulas are the engine's: identical on every output.
    assert (sweep.schedule_copy == sweep.baseline).all()


def test_the_recorded_returns_follow_the_construction():
    """Each return's two look-ups (the amount taxed at the ordinary rates, and
    all taxable income), as the engine computed them under the schedule and
    under the table, against scripts/tax_table.py."""
    units = _units()
    assert (units.groupby(["system", "scenario_id"]).size() == 1).all()
    base = units[units.system == "baseline"].set_index("scenario_id")
    table = units[units.system == "table"].set_index("scenario_id")
    assert len(base) == len(table) == 100
    assert (base.foreign_earned_income_exclusion == 0).all()
    looked_up = 0
    for scenario_id, unit in base.iterrows():
        column = T.COLUMN_FOR_FILING_STATUS[unit.filing_status]
        # The engine subtracts in single precision; so does this.
        amount = float(
            max(
                np.float32(0),
                np.float32(unit.taxable_income)
                - np.float32(unit.capital_gains_excluded_from_taxable_income),
            )
        )
        schedule = T.schedule_tax(amount, column, YEAR)
        assert unit.income_tax_main_rates == pytest.approx(schedule, abs=0.05)
        under_table = table.loc[scenario_id].income_tax_main_rates
        if 0 <= amount < T.CEILING:
            assert under_table == T.table_tax(amount, column, YEAR)
            looked_up += amount > 0
        else:
            assert under_table == unit.income_tax_main_rates
        # The second look-up: the tax on all taxable income, which caps the
        # regular tax of a return with capital gains (worksheet lines 24, 46).
        total = float(max(np.float32(0), np.float32(unit.taxable_income)))
        on_all = unit.tax_on_taxable_income_at_main_rates
        assert on_all == pytest.approx(T.schedule_tax(total, column, YEAR), abs=0.05)
        on_all_table = table.loc[scenario_id].tax_on_taxable_income_at_main_rates
        if 0 <= total < T.CEILING:
            assert on_all_table == T.table_tax(total, column, YEAR)
        else:
            assert on_all_table == on_all
        # The regular tax is the first look-up plus the capped tax on the gains.
        for system, row in (("schedule", unit), ("table", table.loc[scenario_id])):
            capped = min(
                row.capital_gains_tax,
                max(
                    0.0,
                    row.tax_on_taxable_income_at_main_rates - row.income_tax_main_rates,
                ),
            )
            assert row.capital_gains_tax == pytest.approx(capped, abs=1e-6), system
            assert row.regular_tax_before_credits == pytest.approx(
                row.income_tax_main_rates + row.capital_gains_tax, abs=0.01
            )
    assert looked_up == 38


def test_the_cells_table_follows_from_the_sweep_and_the_irs_draft():
    cells, sweep, units = _cells(), _sweep(), _units()
    federal = sweep[sweep.variable == FEDERAL].reset_index(drop=True)
    assert list(cells.scenario_id) == list(federal.scenario_id)
    assert (cells.schedule_value == federal.baseline).all()
    assert (cells.constructed_table_value == federal.table).all()
    assert (cells.scored == federal.scored).all()
    draft = {row["at_least"]: row for row in _irs_table(YEAR)}
    base = units[units.system == "baseline"].set_index("scenario_id")
    applies = cells[cells.tax_table_applies]
    assert len(applies) == 38
    for cell in applies.itertuples():
        column = T.COLUMN_FOR_FILING_STATUS[cell.filing_status]
        lower, upper = T.band(cell.amount_at_ordinary_rates)
        assert cell.band == f"{lower}-{upper}"
        built = T.table_tax(cell.amount_at_ordinary_rates, column, YEAR)
        assert cell.constructed_table_tax_on_amount == built
        assert cell.irs_draft_2026_table_tax_on_amount == draft[lower][column] == built
        assert cell.filing_status == base.loc[cell.scenario_id].filing_status
        gap = abs(built - cell.schedule_tax_on_amount)
        assert gap <= (upper - lower) / 2 * cell.marginal_rate + 0.5 + 0.05


def test_the_recorded_counts_follow_from_the_recorded_cells():
    cells, sweep = _cells(), _sweep()
    summary = _impact()["federal_references"]
    scored = cells[cells.scored]
    changed = scored[scored.difference.abs() > 1e-6]
    assert summary["all"] == len(cells) == 100
    assert summary["scored"] == len(scored) == 84
    assert summary["scored_where_table_applies"] == scored.tax_table_applies.sum() == 33
    assert summary["scored_changed_by_any_amount"] == len(changed) == 30
    assert (
        summary["scored_differing_by_more_than_1"]
        == int(scored.differs_beyond_1.sum())
        == 21
    )
    assert (scored.differs_beyond_1 == (scored.difference.abs() > 1)).all()
    # The classes follow from each return's taxable income, and the counts
    # from the classes.
    classes = cells.taxable_income.map(
        lambda income: (
            "zero"
            if income <= 0
            else "under_100000"
            if income < T.CEILING
            else "100000_or_more"
        )
    )
    assert (cells.taxable_income_class == classes).all()
    assert (
        summary["scored_by_taxable_income"]
        == classes[cells.scored].value_counts().to_dict()
    )
    assert summary["all_by_taxable_income"] == classes.value_counts().to_dict()
    assert summary["scored_by_taxable_income"] == {
        "zero": 45,
        "under_100000": 33,
        "100000_or_more": 6,
    }
    rounding = summary["look_up_rounding_sensitivity"]
    differs = (scored.constructed_table_value - scored.table_whole_dollar_value).abs()
    assert rounding["scored_changed_by_any_amount"] == int((differs > 1e-6).sum())
    assert [row["scenario_id"] for row in rounding["scored_moved_by_more_than_1"]] == (
        list(scored.scenario_id[differs > 1])
    )
    assert rounding["scored_moved_by_more_than_1"] == [
        {"scenario_id": "scenario_042", "table": 2359.0, "table_whole_dollar": 2365.0}
    ]
    small = _impact()["answers_on_scored_outputs_changed_by_1_or_less"]
    assert small == {
        "outputs": 9,
        "rows": 423,
        "exact_differs_between_the_two_values": 0,
    }
    assert summary["scored_itemizers_where_table_applies"] == 0
    assert changed.difference.min() == pytest.approx(-2.9648, abs=1e-3)
    assert changed.difference.max() == pytest.approx(3.9717, abs=1e-3)
    # Under the ceiling no difference can pass half a $50 band at 22% plus the
    # half dollar of rounding.
    assert cells.difference.abs().max() <= 6.0
    moved = sweep[sweep.scored & sweep.table_moves]
    assert moved.variable.value_counts().to_dict() == {
        FEDERAL: 21,
        "federal_refundable_credits": 2,
    }
    scored_changes = sweep[sweep.scored & ((sweep.table - sweep.baseline).abs() > 1e-6)]
    assert set(scored_changes.variable) == {FEDERAL, "federal_refundable_credits"}
    assert len(scored_changes) == 32
    assert _impact()["scored_outputs_per_model"] == {
        "schedule": 1926,
        "table": 1926,
        "exclude": 1903,
    }


def _published_exact() -> dict[str, float]:
    payload = json.loads(gzip.decompress(_release_bytes("data.json.gz")))
    payload = payload["countries"]["us"] if "countries" in payload else payload
    return {row["model"]: row["exact"] for row in payload["modelStats"]}


def test_the_recorded_rates_agree_between_scorers_and_with_the_published_board():
    models, published = _models(), _published_exact()
    assert len(models) == len(published) == 47
    for model, rate in published.items():
        assert models.loc[model, "exact_schedule"] == pytest.approx(rate, abs=1e-9)
    for convention in CONVENTIONS:
        gap = (
            models[f"exact_{convention}"] - models[f"exact_{convention}_independent"]
        ).abs()
        assert gap.max() <= 1e-9
        agreement = _impact()["scorer_agreement"][convention]
        assert agreement["max_abs_gap_repo_vs_independent"] <= 1e-9
        assert agreement.get("max_abs_gap_function_vs_cli", 0.0) <= 1e-9
    # A second accepted value never lowers a rate.
    assert (models.exact_either >= models.exact_schedule - 1e-12).all()
    counts = models[
        ["matches_schedule", "matches_table", "matches_both", "matches_neither"]
    ]
    assert (counts.sum(axis=1) == models.cells).all() and (models.cells == 21).all()
    assert counts.sum().to_dict() == {
        "matches_schedule": 157,
        "matches_table": 2,
        "matches_both": 16,
        "matches_neither": 812,
    }


def test_the_independent_scorer_reproduces_the_release_under_each_convention():
    """On the release's own files: the independent scorer gives the published
    headline, and its rates under the other conventions are the recorded ones."""
    scorer = _script("independent_scorer")
    directory = Path(tempfile.mkdtemp(prefix="pb-tax-table-"))
    try:
        for name in (
            "reference_outputs.csv",
            "reference_exclusions.json",
            "predictions.csv.gz",
        ):
            (directory / name).write_bytes(_release_bytes(name))
        reference = scorer.read_reference(directory)
        answers = scorer.read_answers(directory)
    finally:
        shutil.rmtree(directory)
    assert len(reference) == 1926 and len(answers) == 47
    sweep, models = _sweep(), _models()
    scored = sweep[sweep.scored]
    changed = scored[(scored.table - scored.baseline).abs() > 1e-6]
    table_values = {
        (row.scenario_id, row.variable): float(row.table)
        for row in changed.itertuples()
    }
    moved = {
        (row.scenario_id, row.variable)
        for row in scored[scored.table_moves].itertuples()
    }
    computed = {
        "schedule": scorer.rates(reference, answers),
        "either": scorer.rates(reference, answers, also_accept=table_values),
        "table": scorer.rates(reference | table_values, answers),
        "exclude": scorer.rates(
            {key: value for key, value in reference.items() if key not in moved},
            answers,
        ),
    }
    published = _published_exact()
    for model, rate in published.items():
        assert computed["schedule"][model] == pytest.approx(rate, abs=1e-9)
        for convention in CONVENTIONS:
            assert computed[convention][model] == pytest.approx(
                models.loc[model, f"exact_{convention}"], abs=1e-9
            )


def test_the_law_record_was_checked_against_the_documents():
    law = _script("law_sources")
    check = json.loads((AUDIT / "law/excerpts_check.json").read_text())
    quotes = law.excerpts()
    assert check["all_checks_pass"] is True
    assert check["excerpts"] == check["excerpts_found"] == len(quotes) == 44
    assert check["excerpts_not_found"] == []
    assert all(check["rate_tables_equal_to_tax_table_py"].values())
    assert len(check["rate_tables_equal_to_tax_table_py"]) == 8
    sources = json.loads((AUDIT / "law/sources.json").read_text())["sources"]
    extractions = {source["extraction"]["name"] for source in sources}
    assert {source for source, _ in quotes} <= extractions
    for year, table in check["tax_tables"].items():
        committed = IRS_TABLES[int(year)].read_bytes()
        assert table["csv_sha256"] == hashlib.sha256(committed).hexdigest()
        assert table["parse_equals_committed_csv"] is True
        assert table["amounts"] == table["amounts_equal_to_constructed_table"] == 8248
    assert not any(check["occurrences_of_midpoint_or_middle"].values())


class _Statuses:
    """A filing status array, as the engine hands one to a formula."""

    def __init__(self, names):
        self.names = names

    def decode_to_str(self):
        return np.array(self.names)


class _Period:
    def __init__(self, year):
        self.start = type("Start", (), {"year": year})()


def test_the_look_up_rounding_variant_crosses_the_ceiling_onto_the_worksheet():
    """The sweep's look-up: the table under the ceiling; with the amount
    rounded to a whole dollar, an amount that rounds up to $100,000 takes the
    worksheet on $100,000, not the schedule tax on the unrounded amount."""
    sweep = _script("sweep_tax_table")
    amounts = np.array([99_999.40, 99_999.60, 21_749.71, 0.0, 150_000.25])
    statuses = _Statuses(["SINGLE", "SINGLE", "SINGLE", "JOINT", "SURVIVING_SPOUSE"])
    columns = ["single", "single", "single", "joint", "joint"]
    schedule = np.array(
        [T.schedule_tax(a, c, YEAR) for a, c in zip(amounts, columns, strict=True)]
    )
    args = (amounts, statuses, schedule, _Period(YEAR))
    plain = sweep.look_up("table")(*args)
    assert list(plain) == [
        T.table_tax(99_999.40, "single", YEAR),
        T.table_tax(99_999.60, "single", YEAR),
        2359,
        0,
        schedule[4],
    ]
    rounded = sweep.look_up("table_whole_dollar")(*args)
    assert rounded[0] == T.table_tax(99_999, "single", YEAR)
    assert rounded[1] == T.schedule_tax(100_000, "single", YEAR)
    assert rounded[1] != schedule[1] and rounded[1] != plain[1]
    assert rounded[2] == 2365
    assert rounded[3] == 0
    assert rounded[4] == T.schedule_tax(150_000, "joint", YEAR)
    # The copied formulas, and every other year, keep the schedule.
    assert list(sweep.look_up("schedule_copy")(*args)) == list(schedule)
    for variant in ("table", "table_whole_dollar"):
        other_year = sweep.look_up(variant)(amounts, statuses, schedule, _Period(2025))
        assert list(other_year) == list(schedule)


def test_no_tax_table_draft_is_in_the_archived_listings_before_the_freeze():
    """What the search behind "none found" covers, and that it found none."""
    law = _script("law_sources")
    history = json.loads((AUDIT / "law/draft_listing_history.json").read_text())
    captures = history["captures"]
    before = [c for c in captures if c["before_freeze"]]
    assert history["freeze"] == "2026-07-03"
    assert len(captures) == len(law.ARCHIVED_LISTINGS) == 18
    assert history["captures_on_or_before_freeze"] == len(before) == 14
    assert all(c["captured_utc"][:10] <= "2026-07-03" for c in before)
    assert max(c["captured_utc"] for c in before) == "2026-07-03T08:09Z"
    assert all(c["rows"] == 25 and not c["tax_table_products"] for c in captures)
    assert history["tax_table_products_listed_on_or_before_freeze"] == []
    assert history["tax_table_products_listed_in_later_captures"] == []
    assert history["posting_dates_covered_on_or_before_freeze"] == law.merge(
        [(c["first_posted"], c["last_posted"]) for c in before]
    )
    # One day in the period is on no archived page.
    assert history["posting_dates_covered_on_or_before_freeze"] == [
        ["2026-03-23", "2026-06-08"],
        ["2026-06-10", "2026-07-01"],
    ]
    assert history["distinct_rows_seen_on_or_before_freeze"] == 251
    # Each capture is 25 rows of a much longer listing: a sample of it.
    sizes = [c["drafts_in_the_whole_listing"] for c in before]
    assert history["drafts_in_the_whole_listing_on_or_before_freeze"] == [
        min(sizes),
        max(sizes),
    ]
    assert [min(sizes), max(sizes)] == [1215, 1219]
    seen = history["rows_seen_on_or_before_freeze"]
    assert len(seen) == len({tuple(row.values()) for row in seen}) == 251
    assert not any(law.is_tax_table_product(row) for row in seen)
    assert {row["posted"] for row in seen} <= {
        day
        for first, last in history["posting_dates_covered_on_or_before_freeze"]
        for day in pd.date_range(first, last).strftime("%Y-%m-%d")
    }
    assert min(row["posted"] for row in seen) == "2026-03-23"
    assert max(row["posted"] for row in seen) == "2026-07-01"
    today = {
        row["product"]: row for row in history["tax_table_products_listed_on_read_date"]
    }
    assert today["Publication 1040"]["revision"] == "2026"
    assert today["Publication 1040"]["posted"] == "2026-09-16"
    assert today["Instruction 1040"]["revision"] == "2025"
    # Ranges join when one starts the day after another ends, and not otherwise.
    assert law.merge([("2026-05-14", "2026-05-19"), ("2026-05-05", "2026-05-13")]) == [
        ["2026-05-05", "2026-05-19"]
    ]
    assert law.merge([("2026-06-10", "2026-06-17"), ("2026-06-03", "2026-06-08")]) == [
        ["2026-06-03", "2026-06-08"],
        ["2026-06-10", "2026-06-17"],
    ]
    assert law.is_tax_table_product(
        {"product": "Publication 1040", "title": "", "revision": "", "posted": ""}
    )
    assert not law.is_tax_table_product(
        {
            "product": "Form 8615",
            "title": "Tax for Certain Children",
            "revision": "",
            "posted": "",
        }
    )


def test_the_filers_ages_and_farm_income_are_the_release_households():
    """Form 8615 needs a filer under 24 and Schedule J income from farming or
    fishing: the recorded facts that bound where either could apply."""
    scenarios = _release_csv("scenarios.csv")
    cells = _cells().set_index("scenario_id")
    farm_inputs = ("farm_income", "farm_operations_income", "farm_rent_income")
    for scenario_id, text in zip(scenarios.scenario_id, scenarios.scenario_json):
        adults = json.loads(text)["adults"]
        heads = [a for a in adults if a.get("inputs", {}).get("is_tax_unit_head")]
        assert len(heads) == 1
        assert cells.loc[scenario_id, "head_age"] == heads[0]["age"]
        farm = any(
            float(a.get("inputs", {}).get(name) or 0) != 0
            for a in adults
            for name in farm_inputs
        )
        assert bool(cells.loc[scenario_id, "has_farm_income"]) == farm
    applies = cells[cells.tax_table_applies]
    recorded = _impact()["federal_references"]["returns_where_table_applies"]
    assert recorded["all"] == len(applies) == 38
    assert recorded["head_24_or_older"] == int((applies.head_age >= 24).sum()) == 36
    assert recorded["head_under_24"] == [
        {"scenario_id": "scenario_082", "head_age": 23},
        {"scenario_id": "scenario_091", "head_age": 22},
    ]
    assert recorded["with_farm_income"] == ["scenario_042", "scenario_064"]
    assert recorded["with_farm_income"] == list(applies.index[applies.has_farm_income])


def test_the_look_up_rounding_sensitivity_is_summarized_over_the_right_returns():
    sweep, units = _sweep(), _units()
    summary = json.loads((VERIFICATION / "sweep_summary.json").read_text())
    rounding = summary["look_up_rounding_sensitivity"]
    base = units[units.system == "baseline"]
    over = set(base.scenario_id[base.taxable_income >= T.CEILING])
    federal_over = sweep[(sweep.variable == FEDERAL) & sweep.scenario_id.isin(over)]
    gap = (federal_over.table - federal_over.table_whole_dollar).abs()
    assert rounding["federal_outputs_of_returns_at_100000_or_more"] == len(gap) == 13
    assert rounding["max_abs_difference_among_them"] == pytest.approx(gap.max())
    # At or over the ceiling the table variant is the schedule, so only the
    # rounding of the looked-up amount can move the output: under a dollar's tax.
    assert (federal_over.table == federal_over.baseline).all()
    assert gap.max() < 0.37
    every = (sweep.table - sweep.table_whole_dollar).abs()
    assert rounding["outputs_differing_from_table"] == int((every > 1e-6).sum())
    assert [row["scenario_id"] for row in rounding["differing_by_more_than_1"]] == list(
        sweep.scenario_id[every > 1]
    )
    scored_max = _impact()["federal_references"]["look_up_rounding_sensitivity"][
        "scored_max_abs_change_at_100000_or_more"
    ]
    scored_gap = gap[federal_over.scored]
    assert scored_max == pytest.approx(scored_gap.max()) and scored_max < 0.10


def test_the_income_generator_reaches_the_top_bracket():
    """The recorded experiment behind the wide generator above."""
    record = json.loads((VERIFICATION / "top_rate_detection.json").read_text())
    missed = record["runs_that_missed_the_fault"]
    assert record["runs_per_generator"] == 40
    assert missed["cents"] > 0
    assert missed["dollars_and_cents"] == 0


def test_the_state_record_counts_the_release_references():
    record = json.loads((VERIFICATION / "state_tax_tables.json").read_text())
    assert record["every_quotation_found"] is True
    assert all(state["quotations"] for state in record["states"])
    reference = _release_csv("reference_outputs.csv")
    scenarios = _release_csv("scenarios.csv").set_index("scenario_id")["state"]
    state_tax = "state_income_tax_before_refundable_credits"
    scored = np.array(
        [
            (s, v) not in _excluded()
            for s, v in zip(reference.scenario_id, reference.variable)
        ]
    )
    rows = reference[(reference.variable == state_tax) & scored]
    nonzero = rows[rows.value.abs() > 1e-6].scenario_id.map(scenarios).value_counts()
    recorded = {
        state["state"]: state["scored_nonzero_state_references"]
        for state in record["states"]
    }
    assert recorded == nonzero.to_dict()
    totals = record["scored_nonzero_state_references"]
    assert totals["all_states"] == totals["in_states_checked"] == 31
    assert totals["in_states_not_checked"] == {}
    with_table = {s["state"] for s in record["states"] if s["table_prescribed"]}
    assert sorted(with_table) == sorted(record["states_with_a_table"])
    assert totals["in_states_with_a_table"] == sum(
        count for state, count in recorded.items() if state in with_table
    )


def test_the_manifest_pins_every_evidence_file():
    """Rebuilding the manifest reproduces the committed one, so an evidence
    file cannot change without the manifest changing with it."""
    committed = json.loads((AUDIT / "manifest.json").read_text())
    assert _script("build_manifest").manifest() == committed
