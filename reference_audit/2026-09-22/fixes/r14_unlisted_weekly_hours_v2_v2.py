"""r14 independent-verification revision: hours-input sensitivity, not an exact award.

Executable patch and reform are unchanged from r14_unlisted_weekly_hours_v2.
For each person with no prompt-visible hours field, use the prompt's numeric
zero default. Retain 1.755.4's other policy and assume no unlisted general-work
noncompliance (7 CFR 273.7(a)(1), (f)(1)). This removes the artificial work-
registration sanctions that v1 introduced for scenarios 012, 032 and 038.

The combined test changes the SNAP outputs for 056 and 112 to zero in the
1.755.4 sandbox. Those zeros are sensitivity results, not uniquely established
2026 legal entitlements. The unchanged ABAWD implementation does not track
prior countable months or geographic waivers. 7 U.S.C. 2015(o)(2) limits benefits
after three countable months in a 36-month period; zero hours alone does not
establish immediate ineligibility. NJ's official guidance also reports geographic
waivers during 2026. The scenarios do not state prior ABAWD months or locality.
The two exclusions rest on an unlisted hours dependency under otherwise frozen
engine assumptions; they must not be presented as validated zero-dollar awards.

Sources checked in the independent verification:
- https://www.ecfr.gov/current/title-7/section-273.7
- https://www.law.cornell.edu/uscode/text/7/2015#o
- https://www.nj.gov/humanservices/dfd/news/federal-changes/
"""

from __future__ import annotations

from policybench.scenarios import is_excluded_prompt_input_name
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *  # noqa: F401,F403  (Variable, Person, MONTH, ...)

FIX_ID = "r14_unlisted_weekly_hours_v2_v2"
DESCRIPTION = (
    "Set weekly_hours_worked_before_lsr to 0 for every person whose prompt lists no "
    "weekly hours (prompt: 'Treat any unlisted numeric input as 0'; 1.755.4 "
    "defaults it to 40), and treat non-exempt SNAP work registrants as compliant "
    "unless flagged noncompliant (7 CFR 273.7(a)(1), (f)(1); upstream 48a10d4d43), "
    "to isolate hours-input sensitivity under otherwise frozen engine assumptions; "
    "zero outputs do not establish exact legal entitlements."
)

HOURS_FIELDS = (
    "hours_worked_last_week",
    "weekly_hours_worked",
    "weekly_hours_worked_before_lsr",
    "hours_worked",
)
TARGET = "weekly_hours_worked_before_lsr"


def listed_hours_fields(person) -> list[str]:
    """Hours fields that the prompt actually shows for this person."""
    return [
        field
        for field in HOURS_FIELDS
        if field in person.inputs and not is_excluded_prompt_input_name(field)
    ]


def patch(situation: dict, scenario) -> dict:
    year = str(scenario.year)
    for person in list(scenario.adults) + list(scenario.children):
        if listed_hours_fields(person):
            continue
        situation["people"][person.name][TARGET] = {year: 0.0}
    return situation


class is_snap_work_registration_noncompliant(Variable):
    value_type = bool
    entity = Person
    label = "SNAP work registration noncompliant"
    definition_period = MONTH
    default_value = False
    documentation = (
        "Whether a non-exempt SNAP work registrant has refused or failed without "
        "good cause to comply with the work requirements (7 CFR 273.7(f)(1)). "
        "Backport of the upstream hook from commit 48a10d4d43."
    )
    reference = "https://www.ecfr.gov/current/title-7/section-273.7#p-273.7(f)(1)"


class meets_snap_general_work_requirements(Variable):
    value_type = bool
    entity = Person
    label = "Person is eligible for SNAP benefits via general work requirements"
    definition_period = MONTH
    reference = (
        "https://www.law.cornell.edu/cfr/text/7/273.7#a_1",
        "https://www.law.cornell.edu/cfr/text/7/273.7#f_1",
    )

    def formula(person, period, parameters):
        # Identical to 1.755.4 except the compliance line (see module docstring).
        p = parameters(period).gov.usda.snap.work_requirements.general
        age = person("monthly_age", period)
        weekly_hours_worked = person("weekly_hours_worked_before_lsr", period.this_year)
        worked_exempted_age = p.age_threshold.exempted.calc(age)
        is_disabled = person("is_disabled", period)
        is_dependent = person("is_tax_unit_dependent", period)
        is_child = age < p.age_threshold.caring_dependent_child
        has_child = person.spm_unit.any(is_dependent & is_child)
        has_incapacitated_person = person.spm_unit.any(
            person("is_incapable_of_self_care", period)
        )
        is_working = weekly_hours_worked >= p.weekly_hours_threshold
        exempted = (
            worked_exempted_age
            | is_disabled
            | has_child
            | has_incapacitated_person
            | is_working
        )
        compliant = person("is_snap_work_program_participant", period) | ~person(
            "is_snap_work_registration_noncompliant", period
        )
        return exempted | compliant


class reform(Reform):
    def apply(self):
        # update_variable adds a missing variable and replaces an existing one, so
        # apply() stays idempotent if it runs more than once on a system.
        self.update_variable(is_snap_work_registration_noncompliant)
        self.update_variable(meets_snap_general_work_requirements)
