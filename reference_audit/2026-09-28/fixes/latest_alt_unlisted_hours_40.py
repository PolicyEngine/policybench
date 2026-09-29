"""Alternative reading for the unlisted-hours exclusions (scenario_056, scenario_112 snap)
on policyengine-us 2.15.17 plus every pre-freeze-law convention.

NOT a reference fix and NOT a hold convention. Both outputs stay excluded: their root
cause (triage/root_causes.json, r14_unlisted_weekly_hours_v2) is an unlisted input,
weekly_hours_worked_before_lsr. This module only recomputes, on the new stack, the value
under the reading the 22c board used: a person whose prompt shows no weekly hours works
40 hours a week (the 1.755.4 default of weekly_hours_worked_before_lsr).

On 2.15.17 the readings swap. Upstream 82745ca239 (PR #9261, merged a112cc5a0a on
2026-08-12) made the default 0, which is the prompt's "Treat any unlisted numeric input
as 0" reading, so the 2.15.17 reference now takes the zero-hours reading and the
40-hour reading becomes the alternative.

Composition: latest_map_stated_hours (conventions plus stated usual weekly hours mapped
to weekly_hours_worked_before_lsr), then 40 hours for every person with no stated hours.
Diffing this sweep against out/latest_map_stated_hours.csv lists every output that
depends on the unlisted-hours reading.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

FIX_ID = "latest_alt_unlisted_hours_40"
DESCRIPTION = (
    "latest_map_stated_hours plus weekly_hours_worked_before_lsr = 40 for every person with "
    "no stated weekly hours (the 22c board's reading); recomputes an alternative_value, not a "
    "reference"
)
TARGET = "weekly_hours_worked_before_lsr"
ALTERNATIVE_HOURS = 40.0


def _load(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(f"alt_hours40_part_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_mapping = _load("latest_map_stated_hours")
reform = _mapping.reform


def patch(situation: dict, scenario) -> dict:
    situation = _mapping.patch(situation, scenario)
    year = str(scenario.year)
    for person in situation["people"].values():
        if TARGET not in person:
            person[TARGET] = {year: ALTERNATIVE_HOURS}
    return situation
