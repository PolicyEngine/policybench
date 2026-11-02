"""Input mapping on policyengine-us 2.15.17: stated usual weekly hours reach the SNAP work tests.

NOT a hold convention and NOT an engine fix. It is a situation-builder mapping, composed
with every pre-freeze-law convention (latest_conventions.py) so its sweep compares
one-for-one with out/latest_conventions.csv.

Why. The prompt shows the input hours_worked_last_week with the label "usual weekly
hours worked" (policybench/prompts.py, US_VARIABLE_DESCRIPTIONS). The sweep builder
(Scenario.to_pe_household) passes it to the engine under that name only. In
policyengine-us the SNAP work rules never read hours_worked_last_week; they read
weekly_hours_worked_before_lsr (2.15.17: meets_snap_abawd_work_requirements,
meets_snap_general_work_requirements, is_snap_work_registration_exempt_non_age,
meets_snap_work_exception). policybench/scenarios.py lists weekly_hours_worked_before_lsr
in EXCLUDED_INPUT_VARIABLES, so no scenario sets it. In 1.755.4 its default was 40
(variables/household/income/person/weekly_hours_worked.py), which happened to match a
stated 40; upstream 82745ca239 (PR #9261, merged a112cc5a0a on 2026-08-12, closes
#9254) changed the default to 0, so on 2.15.17 a person who states 40 usual weekly
hours fails the 20-hour ABAWD test (7 U.S.C. 2015(o)(2); 7 CFR 273.24(a)(1)).

What it does. For each person whose prompt shows usual weekly hours
(hours_worked_last_week, a prompt-visible input), copy that value into
weekly_hours_worked_before_lsr, unless the situation already sets it. Persons with no
stated hours are untouched and keep the engine default (0 in 2.15.17, which is also the
prompt's "Treat any unlisted numeric input as 0" rule).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from policybench.scenarios import is_excluded_prompt_input_name

FIX_ID = "latest_map_stated_hours"
DESCRIPTION = (
    "latest_conventions plus a situation-builder mapping: each person's stated usual weekly "
    "hours (hours_worked_last_week, shown in the prompt) also set weekly_hours_worked_before_lsr, "
    "the input the SNAP work tests read (its default fell from 40 to 0 in upstream #9261)"
)

SOURCE = "hours_worked_last_week"
TARGET = "weekly_hours_worked_before_lsr"


def _load(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(f"map_stated_hours_part_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


reform = _load("latest_conventions").reform

# The mapping is only sound while the source is a prompt-visible input and the target is not.
assert not is_excluded_prompt_input_name(SOURCE)
assert is_excluded_prompt_input_name(TARGET)


def patch(situation: dict, scenario) -> dict:
    for person in situation["people"].values():
        if SOURCE in person and TARGET not in person:
            person[TARGET] = dict(person[SOURCE])
    return situation
