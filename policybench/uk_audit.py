"""A stratified UK household sample for auditing policyengine-uk.

Round 1 of the UK audit (October 2026) drew 100 households from the public UK
transfer dataset the way the US leg draws from its own data: weighted, without
strata. Most of them were working-age owner-occupiers or private renters in
England, so whole areas of the UK rules were barely touched. The transfer
dataset also carries no State Pension, no caring hours, no childcare costs,
no Attendance Allowance and no social tenancies.

This module draws round 2's households by stratum. Each stratum selects
transfer-data households with the structure it needs (a region, an age band,
children, a tenure) and then states the facts the data lacks: a State
Pension amount, caring hours, childcare costs, a council and its council tax
bill, a rental area. Every such fact is drawn from a documented distribution
with a seeded generator and stated in the prompt, and the reference reads
exactly those facts (``Scenario.to_pe_uk_situation``). The drawn values are
constructed, not observed: they are plausible circumstances chosen to
exercise the rules, not estimates of any population.

The sample is for finding engine defects. It is not representative of the
UK and is never weighted to the population.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from policybench.config import TAX_YEAR
from policybench.scenarios import (
    UK_PRIVATE_RENT_TENURE,
    Person,
    Scenario,
    _build_uk_person,
    _eligible_uk_households,
    _extract_uk_household_inputs,
    canonical_uk_scenario,
)

UK_AUDIT_SEED = 20261011
UK_AUDIT_SOURCE = "uk_calibrated_transfer_stratified_audit"

# State Pension age in 2026-27. The Pensions Act 2014 raises it from 66 to 67
# for people born on or after 6 April 1960, so a 66-year-old may not yet have
# reached it; the reference reads the stated date of birth. Strata that need
# pensioners select adults aged 67 and over.
PENSIONER_MIN_AGE = 67
WORKING_AGE_MAX = 64

# Weekly State Pension rates for 2026-27 (policyengine-uk 2.126.7 parameters
# gov.dwp.state_pension.*.amount at 2026-06-01). Used only to construct
# plausible State Pension amounts; the reference reads the stated amount.
NEW_STATE_PENSION_WEEKLY = 241.30
BASIC_STATE_PENSION_WEEKLY = 184.90
# Pensions Act 2014 s. 4: the new State Pension applies to people who reach
# pensionable age on or after 6 April 2016, so everyone born before 6 April
# 1951 is on the basic scheme.
NEW_STATE_PENSION_FIRST_BIRTH_DATE = 19510406
WEEKS_PER_YEAR = 52

# Statutory council tax band ratios to Band D (Local Government Finance Act
# 1992 s. 5(1) for England, as amended for Wales by the Council Tax (Valuation
# Bands) (Wales) Order 2003; Scotland: Council Tax (Substitution of
# Proportion) (Scotland) Order 2016).
ENGLAND_BAND_RATIOS = {
    "A": 6 / 9,
    "B": 7 / 9,
    "C": 8 / 9,
    "D": 1,
    "E": 11 / 9,
    "F": 13 / 9,
    "G": 15 / 9,
    "H": 18 / 9,
}
WALES_BAND_RATIOS = {**ENGLAND_BAND_RATIOS, "I": 21 / 9}
SCOTLAND_BAND_RATIOS = {
    "A": 240 / 360,
    "B": 280 / 360,
    "C": 320 / 360,
    "D": 1,
    "E": 473 / 360,
    "F": 585 / 360,
    "G": 705 / 360,
    "H": 882 / 360,
}


@dataclass(frozen=True)
class Council:
    """A council the sample can place a household in.

    ``band_d`` is the council's 2026-27 Band D council tax, used only to
    state a liability; ``band_d_source`` is where it was read. ``brma`` is
    the Broad Rental Market Area a private renter there is placed in.
    """

    local_authority: str
    region: str
    band_d: float
    brma: str
    band_d_source: str = ""


COUNCILS_PATH = Path(__file__).with_name("uk_audit_councils.csv")

# Working-age English councils whose Council Tax Reduction schemes
# policyengine-uk simulates (council_tax_reduction/config.py). Elsewhere in
# England a working-age claim falls back to a reported reduction
# (council_tax_reduction_scheme_supported), so its reference is not a
# function of the prompt.
SIMULATED_WORKING_AGE_CTR_COUNCILS = (
    "MERTON",
    "KINGSTON_UPON_THAMES",
    "NEWHAM",
    "WESTMINSTER",
    "OXFORD",
)

# The single person discount (Local Government Finance Act 1992 s. 11(1)):
# a quarter off where one adult is resident.
SINGLE_PERSON_DISCOUNT = 0.25


def load_councils(path: Path = COUNCILS_PATH) -> dict[str, tuple[Council, ...]]:
    """Councils by region, from the packaged table. Each Band D figure was
    read from the council's or government's published 2026-27 figures; the
    table cites the page. Councils whose figure could not be read from an
    official page are left out."""
    grouped: dict[str, list[Council]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            council = Council(
                local_authority=row["local_authority"],
                region=row["region"],
                band_d=float(row["band_d"]),
                brma=row["brma"],
                band_d_source=row.get("band_d_source", ""),
            )
            grouped.setdefault(council.region, []).append(council)
    return {region: tuple(items) for region, items in grouped.items()}


COUNCILS: dict[str, tuple[Council, ...]] = load_councils()


def band_ratio(region: str, band: str) -> float:
    if region == "SCOTLAND":
        return SCOTLAND_BAND_RATIOS[band]
    if region == "WALES":
        return WALES_BAND_RATIOS[band]
    return ENGLAND_BAND_RATIOS[band]


def valid_band(region: str, band: str) -> str:
    """The transfer data's band if the nation has it; Band I exists only in
    Wales, so elsewhere it becomes H."""
    table = (
        SCOTLAND_BAND_RATIOS
        if region == "SCOTLAND"
        else WALES_BAND_RATIOS
        if region == "WALES"
        else ENGLAND_BAND_RATIOS
    )
    if band in table:
        return band
    return "H"


@dataclass(frozen=True)
class Household:
    """A transfer-data household with the features strata select on."""

    household_id: int
    region: str
    tenure: str
    weight: float
    adult_ages: tuple[int, ...]
    child_ages: tuple[int, ...]
    adult_earnings: tuple[float, ...]
    adult_self_employment: tuple[float, ...]
    adult_income: tuple[float, ...]
    capital: float


def household_features(
    person_df: pd.DataFrame, household_df: pd.DataFrame
) -> list[Household]:
    """Features of every household the benchmark can prompt (one benefit
    unit, one or two adults)."""
    eligible = _eligible_uk_households(person_df, household_df)
    people = person_df[person_df["person_household_id"].isin(eligible["household_id"])]
    income_columns = [
        column
        for column in (
            "employment_income_before_lsr",
            "self_employment_income",
            "private_pension_income",
            "property_income",
            "savings_interest_income",
            "dividend_income",
            "miscellaneous_income",
        )
        if column in people.columns
    ]
    features = []
    by_household = dict(tuple(people.groupby("person_household_id")))
    for row in eligible.itertuples(index=False):
        members = by_household[int(row.household_id)]
        adults = members[members["age"] >= 18]
        children = members[members["age"] < 18]
        features.append(
            Household(
                household_id=int(row.household_id),
                region=str(row.region),
                tenure=str(row.tenure_type),
                weight=float(row.household_weight),
                adult_ages=tuple(int(a) for a in adults["age"]),
                child_ages=tuple(int(a) for a in children["age"]),
                adult_earnings=tuple(
                    float(v) for v in adults["employment_income_before_lsr"]
                ),
                adult_self_employment=tuple(
                    float(v) for v in adults["self_employment_income"]
                ),
                adult_income=tuple(
                    float(v) for v in adults[income_columns].sum(axis=1)
                ),
                capital=sum(
                    float(getattr(row, column, 0.0) or 0.0)
                    for column in CAPITAL_COLUMNS
                ),
            )
        )
    return features


Selector = Callable[[Household], bool]
Overlay = Callable[[Scenario, Household, np.random.Generator], Scenario]


@dataclass(frozen=True)
class Stratum:
    name: str
    count: int
    description: str
    select: Selector
    overlay: Overlay


# --- selectors -----------------------------------------------------------


def _all_working_age(h: Household) -> bool:
    return all(age <= WORKING_AGE_MAX for age in h.adult_ages)


def _gb(h: Household) -> bool:
    return h.region != "NORTHERN_IRELAND"


def select_scotland(h: Household) -> bool:
    return h.region == "SCOTLAND"


# Low income: every adult's transfer-data income (before any State Pension)
# below £15,000 and household capital below £16,000 (the Universal Credit and
# Housing Benefit capital limit), so the means-tested benefits have cells to
# test.
LOW_INCOME = 15_000
LOW_CAPITAL = 16_000
# Household holdings the prompt states that means tests can count as capital:
# savings, corporate financial wealth, and property other than the home.
CAPITAL_COLUMNS = (
    "savings",
    "corporate_wealth",
    "other_residential_property_value",
    "non_residential_property_value",
)


def _low_income(h: Household) -> bool:
    return max(h.adult_income) < LOW_INCOME and h.capital < LOW_CAPITAL


def select_scotland_low_income_families(h: Household) -> bool:
    return (
        h.region == "SCOTLAND"
        and any(age < 16 for age in h.child_ages)
        and _low_income(h)
        and _all_working_age(h)
    )


def select_pension_age_low_income(h: Household) -> bool:
    return select_pension_age(h) and _low_income(h)


def select_private_renters_low_income(h: Household) -> bool:
    return select_private_renters(h) and _low_income(h)


def select_pension_age(h: Household) -> bool:
    return (
        _gb(h)
        and all(age >= PENSIONER_MIN_AGE for age in h.adult_ages)
        and not h.child_ages
    )


def select_carers(h: Household) -> bool:
    return (
        _gb(h)
        and h.region != "SCOTLAND"
        and len(h.adult_ages) == 2
        and _all_working_age(h)
        and all(age >= 18 for age in h.adult_ages)
    )


def select_childcare(h: Household) -> bool:
    has_young_child = any(age <= 11 for age in h.child_ages)
    every_adult_works = all(
        earnings > 0 or self_employment > 0
        for earnings, self_employment in zip(h.adult_earnings, h.adult_self_employment)
    )
    return (
        _gb(h)
        and h.region != "SCOTLAND"
        and has_young_child
        and every_adult_works
        and _all_working_age(h)
    )


def select_child_benefit_charge(h: Household) -> bool:
    top = max(h.adult_income)
    return (
        _gb(h)
        and h.region != "SCOTLAND"
        and bool(h.child_ages)
        and 55_000 <= top <= 90_000
        and _all_working_age(h)
    )


def select_allowance_taper(h: Household) -> bool:
    top = max(h.adult_income)
    return (
        _gb(h)
        and h.region != "SCOTLAND"
        and 95_000 <= top <= 135_000
        and _all_working_age(h)
    )


def select_self_employed_loss(h: Household) -> bool:
    return (
        _gb(h)
        and h.region != "SCOTLAND"
        and any(value < 0 for value in h.adult_self_employment)
        and _all_working_age(h)
    )


def select_private_renters(h: Household) -> bool:
    return (
        _gb(h)
        and h.region != "SCOTLAND"
        and h.tenure == UK_PRIVATE_RENT_TENURE
        and _all_working_age(h)
    )


def select_any(h: Household) -> bool:
    """Any Great Britain household. Northern Ireland has domestic rates, not
    Council Tax, so the sample leaves it out."""
    return _gb(h)


# --- overlays ------------------------------------------------------------


def _with_person_inputs(person: Person, **inputs: Any) -> Person:
    merged = dict(person.inputs)
    for key, value in inputs.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return replace(person, inputs=merged)


def _drop_gift_aid(scenario: Scenario) -> Scenario:
    """Gift Aid is set to nil outside the control stratum: policyengine-uk
    gives it by deduction rather than by extending the rate bands (issue
    #2253, fix #2271 not yet released), which round 1 already measured."""
    return replace(
        scenario,
        adults=[_with_person_inputs(a, gift_aid=None) for a in scenario.adults],
        children=[_with_person_inputs(c, gift_aid=None) for c in scenario.children],
    )


def _council_for(
    scenario: Scenario,
    rng: np.random.Generator,
    prefer_simulated_ctr: bool,
) -> Council:
    councils = COUNCILS.get(scenario.state)
    if not councils:
        raise ValueError(f"No councils are set for region {scenario.state!r}.")
    if prefer_simulated_ctr:
        simulated = [
            c
            for c in councils
            if c.local_authority in SIMULATED_WORKING_AGE_CTR_COUNCILS
        ]
        if simulated:
            councils = tuple(simulated)
    return councils[int(rng.integers(len(councils)))]


def state_council(
    scenario: Scenario,
    rng: np.random.Generator,
    band: str,
    prefer_simulated_ctr: bool = False,
) -> Scenario:
    """Place the household in a council and state its Council Tax liability.

    The liability is the council's 2026-27 Band D times the statutory ratio
    for the household's band, less the single person discount where one
    adult lives there. policyengine-uk reads ``council_tax`` as the liability
    before Council Tax Reduction, so the prompt states it after the discount
    and says so. A private renter is placed in the council's rental area.
    """
    council = _council_for(scenario, rng, prefer_simulated_ctr)
    band = valid_band(scenario.state, band)
    inputs = dict(scenario.household_inputs)
    inputs["local_authority"] = council.local_authority
    inputs["council_tax_band"] = band
    charge = council.band_d * band_ratio(scenario.state, band)
    if len(scenario.adults) == 1:
        charge *= 1 - SINGLE_PERSON_DISCOUNT
    inputs["council_tax"] = float(round(charge))
    if inputs.get("tenure_type") == UK_PRIVATE_RENT_TENURE:
        inputs["brma"] = council.brma
    return replace(scenario, household_inputs=inputs)


def _date_of_birth(person: Person) -> int | None:
    value = person.inputs.get("date_of_birth")
    return None if value is None else int(value)


def draw_state_pension(person: Person, rng: np.random.Generator) -> float:
    """An annual 2026-27 State Pension for someone over pensionable age.

    New State Pension (pensionable age reached on or after 6 April 2016):
    70% the full rate, 20% a partial rate of 60-99% of it (a shorter
    National Insurance record), 10% the full rate plus a protected payment
    of £5-£60 a week. Basic State Pension: 25% the full basic rate, 60% the
    full basic rate plus £10-£120 a week of additional State Pension, 15% a
    partial basic rate of 60-99%.
    """
    dob = _date_of_birth(person)
    on_new_scheme = dob is not None and dob >= NEW_STATE_PENSION_FIRST_BIRTH_DATE
    u = rng.random()
    if on_new_scheme:
        if u < 0.70:
            weekly = NEW_STATE_PENSION_WEEKLY
        elif u < 0.90:
            weekly = NEW_STATE_PENSION_WEEKLY * rng.uniform(0.60, 0.99)
        else:
            weekly = NEW_STATE_PENSION_WEEKLY + rng.uniform(5, 60)
    else:
        if u < 0.25:
            weekly = BASIC_STATE_PENSION_WEEKLY
        elif u < 0.85:
            weekly = BASIC_STATE_PENSION_WEEKLY + rng.uniform(10, 120)
        else:
            weekly = BASIC_STATE_PENSION_WEEKLY * rng.uniform(0.60, 0.99)
    return float(round(weekly * WEEKS_PER_YEAR))


# Social rents for pension-age social tenants: £85-£150 a week.
SOCIAL_RENT_WEEKLY = (85, 150)
SOCIAL_TENURES = ("RENT_FROM_COUNCIL", "RENT_FROM_HA")


def state_pensions(scenario: Scenario, rng: np.random.Generator) -> Scenario:
    """A State Pension (``draw_state_pension``) for every adult aged 67 or
    over who has none stated. Everyone 67 or over in 2026-27 has reached
    pensionable age."""
    adults = [
        _with_person_inputs(
            adult, state_pension_reported=draw_state_pension(adult, rng)
        )
        if adult.age >= PENSIONER_MIN_AGE
        and not adult.inputs.get("state_pension_reported")
        else adult
        for adult in scenario.adults
    ]
    return replace(scenario, adults=adults)


def overlay_pension_age(
    scenario: Scenario, household: Household, rng: np.random.Generator
) -> Scenario:
    """Attendance Allowance for 30% of adults without PIP daily living (20%
    the lower rate, 10% the higher); 35% of owner-occupiers become
    social tenants paying £85-£150 a week, since the transfer data has
    none. The State Pension comes from ``state_pensions``."""
    adults = []
    for adult in scenario.adults:
        attendance = None
        if adult.inputs.get("pip_dl_category") in (None, "NONE"):
            u = rng.random()
            attendance = "LOWER" if u < 0.20 else "HIGHER" if u < 0.30 else None
        adults.append(_with_person_inputs(adult, aa_category=attendance))
    inputs = dict(scenario.household_inputs)
    if inputs.get("tenure_type") != UK_PRIVATE_RENT_TENURE and rng.random() < 0.35:
        inputs["tenure_type"] = SOCIAL_TENURES[int(rng.integers(2))]
        inputs["rent"] = float(round(rng.uniform(*SOCIAL_RENT_WEEKLY) * WEEKS_PER_YEAR))
    scenario = replace(scenario, adults=adults, household_inputs=inputs)
    return state_council(scenario, rng, band=_band(scenario, rng))


# Caring hours: a fifth below the 35-hour threshold.
CARE_HOURS = (20, 35, 40, 50, 60, 80)
CARE_HOURS_P = (0.15, 0.20, 0.20, 0.20, 0.13, 0.12)


def overlay_carers(
    scenario: Scenario, household: Household, rng: np.random.Generator
) -> Scenario:
    """The lower earner cares for the other adult.

    Caring hours are drawn from ``CARE_HOURS``. In 80% of households the
    cared-for adult has the PIP daily living component (standard or
    enhanced); in 20% they have no disability benefit. In 60% the carer's
    pay is replaced by £0-£300 a week, spanning the Carer's Allowance
    earnings limit; otherwise the transfer data's pay stands.
    """
    carer_index = int(np.argmin([a.employment_income for a in scenario.adults]))
    cared_index = 1 - carer_index
    adults = list(scenario.adults)
    carer = adults[carer_index]
    hours = float(rng.choice(CARE_HOURS, p=CARE_HOURS_P))
    if rng.random() < 0.60:
        weekly_pay = float(rng.uniform(0, 300))
        carer = replace(
            carer, employment_income=float(round(weekly_pay * WEEKS_PER_YEAR))
        )
    adults[carer_index] = _with_person_inputs(carer, care_hours=hours)
    cared = adults[cared_index]
    if rng.random() < 0.80:
        component = "STANDARD" if rng.random() < 0.5 else "ENHANCED"
        adults[cared_index] = _with_person_inputs(cared, pip_dl_category=component)
    else:
        adults[cared_index] = _with_person_inputs(cared, pip_dl_category=None)
    scenario = replace(scenario, adults=adults)
    return state_council(
        scenario, rng, band=_band(scenario, rng), prefer_simulated_ctr=True
    )


def overlay_childcare(
    scenario: Scenario, household: Household, rng: np.random.Generator
) -> Scenario:
    """Childcare costs for every child aged 11 or under, paid to a
    registered provider: £3,000-£15,000 a year under 5, £500-£5,000 from 5
    to 11."""
    children = []
    for child in scenario.children:
        if child.age <= 4:
            cost = rng.uniform(3_000, 15_000)
        elif child.age <= 11:
            cost = rng.uniform(500, 5_000)
        else:
            children.append(child)
            continue
        children.append(
            _with_person_inputs(
                child,
                childcare_expenses=float(round(cost)),
                tax_free_childcare_uses_qualifying_provider=True,
            )
        )
    scenario = replace(scenario, children=children)
    return state_council(
        scenario, rng, band=_band(scenario, rng), prefer_simulated_ctr=True
    )


def overlay_self_employed_loss(
    scenario: Scenario, household: Household, rng: np.random.Generator
) -> Scenario:
    """Half the loss-making self-employed are in gainful self-employment
    for Universal Credit; half are not."""
    adults = []
    for adult in scenario.adults:
        if adult.inputs.get("self_employment_income", 0) < 0:
            adult = _with_person_inputs(
                adult, uc_is_in_gainful_self_employment=bool(rng.random() < 0.5)
            )
        adults.append(adult)
    scenario = replace(scenario, adults=adults)
    return state_council(
        scenario, rng, band=_band(scenario, rng), prefer_simulated_ctr=True
    )


def overlay_council_only(
    scenario: Scenario, household: Household, rng: np.random.Generator
) -> Scenario:
    return state_council(
        scenario, rng, band=_band(scenario, rng), prefer_simulated_ctr=True
    )


def overlay_private_renters(
    scenario: Scenario, household: Household, rng: np.random.Generator
) -> Scenario:
    """Any council in the region, so renters spread across rental areas."""
    return state_council(scenario, rng, band=_band(scenario, rng))


def overlay_scotland(
    scenario: Scenario, household: Household, rng: np.random.Generator
) -> Scenario:
    return state_council(scenario, rng, band=_band(scenario, rng))


def _band(scenario: Scenario, rng: np.random.Generator) -> str:
    band = scenario.metadata.get("council_tax_band")
    if band:
        return str(band)
    return str(rng.choice(list("ABCDE")))


UK_AUDIT_STRATA: tuple[Stratum, ...] = (
    Stratum(
        "scotland_low_income_families",
        10,
        "Scotland: a child under 16, every adult's income under £15,000 and "
        "capital under £16,000",
        select_scotland_low_income_families,
        overlay_scotland,
    ),
    Stratum(
        "scotland",
        20,
        "Scottish taxpayers: transfer-data households in Scotland",
        select_scotland,
        overlay_scotland,
    ),
    Stratum(
        "pension_age_low_income",
        20,
        "Every adult 67 or over, no children, every adult's income other than "
        "the State Pension under £15,000, capital under £16,000",
        select_pension_age_low_income,
        overlay_pension_age,
    ),
    Stratum(
        "pension_age",
        20,
        "Every adult 67 or over, no children; State Pension and Attendance "
        "Allowance stated; some social tenants",
        select_pension_age,
        overlay_pension_age,
    ),
    Stratum(
        "carers",
        25,
        "Two working-age adults in England or Wales; one cares for the other",
        select_carers,
        overlay_carers,
    ),
    Stratum(
        "childcare",
        25,
        "Every adult working, a child aged 11 or under; childcare costs stated",
        select_childcare,
        overlay_childcare,
    ),
    Stratum(
        "child_benefit_charge",
        15,
        "Children, and an adult with income of £55,000-£90,000",
        select_child_benefit_charge,
        overlay_council_only,
    ),
    Stratum(
        "allowance_taper",
        10,
        "An adult with income of £95,000-£135,000",
        select_allowance_taper,
        overlay_council_only,
    ),
    Stratum(
        "self_employed_loss",
        20,
        "A working-age adult with a self-employment loss",
        select_self_employed_loss,
        overlay_self_employed_loss,
    ),
    Stratum(
        "private_renters_low_income",
        10,
        "Working-age private renters, every adult's income under £15,000 and "
        "capital under £16,000",
        select_private_renters_low_income,
        overlay_private_renters,
    ),
    Stratum(
        "private_renters",
        10,
        "Working-age private renters across rental areas",
        select_private_renters,
        overlay_private_renters,
    ),
    Stratum(
        "control",
        15,
        "Unstratified draw in Great Britain, as in round 1 (Gift Aid kept)",
        select_any,
        overlay_council_only,
    ),
)


def _scenario_for(
    household_id: int,
    person_df: pd.DataFrame,
    household_lookup: pd.DataFrame,
    index: int,
    year: int,
    dataset_year: int | None,
    stratum: str,
) -> Scenario:
    household_row = household_lookup.loc[household_id]
    members = person_df[person_df["person_household_id"] == household_id].sort_values(
        by=["age", "person_id"], ascending=[False, True]
    )
    adults, children = [], []
    for _, row in members.iterrows():
        if int(row["age"]) >= 18:
            adults.append(_build_uk_person(row, f"adult{len(adults) + 1}"))
        else:
            children.append(_build_uk_person(row, f"child{len(children) + 1}"))
    metadata: dict[str, Any] = {
        "household_id": int(household_id),
        "stratum": stratum,
        "benunit_ids": sorted(
            {int(b) for b in members["person_benunit_id"].dropna().astype(int)}
        ),
    }
    band = household_row.get("council_tax_band")
    if isinstance(band, str) and band:
        metadata["council_tax_band"] = band
    if dataset_year is not None:
        metadata["dataset_year"] = int(dataset_year)
    household_inputs = _extract_uk_household_inputs(household_row)
    # The transfer data's council tax comes from US property tax and its
    # bands from US home values; the sample states its own bill instead.
    household_inputs.pop("council_tax", None)
    household_inputs.pop("council_tax_band", None)
    return Scenario(
        id=f"scenario_{index:03d}",
        country="uk",
        state=str(household_row["region"]),
        filing_status=None,
        adults=adults,
        children=children,
        household_inputs=household_inputs,
        year=year,
        source_dataset=UK_AUDIT_SOURCE,
        metadata=metadata,
    )


def _weighted_draw(
    candidates: list[Household], n: int, rng: np.random.Generator, name: str = ""
) -> list[Household]:
    if len(candidates) < n:
        raise ValueError(
            f"Stratum {name!r} has {len(candidates)} candidate households for "
            f"{n} draws."
        )
    weights = np.array([max(c.weight, 0.0) for c in candidates], dtype=float)
    p = weights / weights.sum() if weights.sum() > 0 else None
    picks = rng.choice(len(candidates), size=n, replace=False, p=p)
    return [candidates[int(i)] for i in picks]


def stratified_uk_audit_scenarios(
    person_df: pd.DataFrame,
    household_df: pd.DataFrame,
    strata: Sequence[Stratum] = UK_AUDIT_STRATA,
    seed: int = UK_AUDIT_SEED,
    year: int = TAX_YEAR,
    dataset_year: int | None = None,
    excluded_household_ids: set[int] | None = None,
) -> list[Scenario]:
    """Draw each stratum in order, without replacement across strata.

    Within a stratum, households are drawn with probability proportional to
    their transfer-data weight. Each stratum has its own generator, spawned
    from ``seed``, so changing one stratum's count or overlay leaves the
    draws of the strata before it unchanged.
    """
    features = household_features(person_df, household_df)
    if excluded_household_ids:
        features = [f for f in features if f.household_id not in excluded_household_ids]
    household_lookup = household_df.set_index("household_id")
    taken: set[int] = set()
    scenarios: list[Scenario] = []
    generators = np.random.default_rng(seed).spawn(len(strata))
    for stratum, rng in zip(strata, generators):
        candidates = [
            f for f in features if f.household_id not in taken and stratum.select(f)
        ]
        for household in _weighted_draw(candidates, stratum.count, rng, stratum.name):
            taken.add(household.household_id)
            scenario = _scenario_for(
                household.household_id,
                person_df,
                household_lookup,
                index=len(scenarios),
                year=year,
                dataset_year=dataset_year,
                stratum=stratum.name,
            )
            if stratum.name != "control":
                scenario = _drop_gift_aid(scenario)
                scenario = state_pensions(scenario, rng)
            scenario = stratum.overlay(scenario, household, rng)
            scenarios.append(canonical_uk_scenario(scenario))
    return scenarios


def stratum_counts(scenarios: Sequence[Scenario]) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for scenario in scenarios:
        name = str(scenario.metadata.get("stratum"))
        counts[name] = counts.get(name, 0) + 1
    return counts


def write_uk_audit_sample(output: str | Path, seed: int = UK_AUDIT_SEED) -> dict:
    """Draw the sample from the pinned transfer dataset and write its
    scenario manifest, with a sidecar recording what it was drawn from."""
    import json
    from importlib.metadata import version

    from policybench.scenarios import (
        _hash_file,
        get_uk_dataset_path,
        load_uk_transfer_frames,
        scenario_manifest,
    )

    output = Path(output)
    person_df, household_df, dataset_year = load_uk_transfer_frames()
    scenarios = stratified_uk_audit_scenarios(
        person_df, household_df, seed=seed, dataset_year=dataset_year
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    scenario_manifest(scenarios).to_csv(output, index=False)
    dataset = get_uk_dataset_path()
    meta = {
        "seed": seed,
        "strata": {
            s.name: {"count": s.count, "description": s.description}
            for s in UK_AUDIT_STRATA
        },
        "counts": dict(stratum_counts(scenarios)),
        "dataset": dataset.name,
        "dataset_sha256": _hash_file(dataset),
        "dataset_year": dataset_year,
        "councils_sha256": _hash_file(COUNCILS_PATH),
        "policyengine_uk": version("policyengine-uk"),
        "policyengine_core": version("policyengine-core"),
    }
    Path(f"{output}.meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    return meta
