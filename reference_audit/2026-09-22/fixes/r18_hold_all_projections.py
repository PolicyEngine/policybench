"""Every projected parameter value held at the parameter's last explicit value.

Audit of the reference convention "a scored reference follows from the stated facts
and from law published before the 2026-07-03 reference freeze". policyengine-us
1.755.4 fills parameter values past each parameter's last explicit (YAML) value by
uprating: it multiplies the last explicit value by the growth of an index (CPI,
chained CPI, SNAP's thrifty-food-plan index, California CPI, ...), most of whose
2026 values are forecasts. A reference that moves when those projections are removed
depends on a projection rather than on a published amount, and needs one of:
  - the amount was published before the freeze and the engine did not encode it:
    an engine defect (the projection may or may not match the published amount);
  - the amount was published after the freeze: the held convention applies (the
    last amount published before the freeze), as for SNAP (r13_hold_fy2026) and
    California (r12_hold_ca_2025).

Projected entries are found by loading the parameter tree a second time with
policyengine-core's uprate_parameters disabled and diffing each parameter's
values_list instants. The reform drops the projected entries, so each parameter
carries its last explicit value forward.

Env:
  HOLD_PREFIXES  comma-separated parameter-name prefixes to restrict the hold to
                 (default: every parameter); used to attribute a move to a family.
  HOLD_LIST      path to write the list of projected (parameter, instant) entries.
"""

from __future__ import annotations

import json
import os

import policyengine_us.system as pe_system
from policyengine_core.parameters import Parameter
from policyengine_core.reforms import Reform
from policyengine_us import CountryTaxBenefitSystem

FIX_ID = "r18_hold_all_projections"
LAST_DATE = "2026-12-31"


def _instants(system) -> dict[str, set[str]]:
    return {
        p.name: {v.instant_str for v in p.values_list}
        for p in system.parameters.get_descendants()
        if isinstance(p, Parameter)
    }


def _projected() -> dict[str, set[str]]:
    uprated = _instants(pe_system.system)
    original = pe_system.uprate_parameters
    pe_system.uprate_parameters = lambda parameters: parameters
    try:
        raw = _instants(CountryTaxBenefitSystem())
    finally:
        pe_system.uprate_parameters = original
    prefixes = [p for p in os.environ.get("HOLD_PREFIXES", "").split(",") if p]
    projected = {}
    for name, instants in uprated.items():
        if prefixes and not any(name.startswith(prefix) for prefix in prefixes):
            continue
        extra = {
            i for i in instants - raw.get(name, set()) if i <= LAST_DATE and i >= "2025-01-01"
        }
        if extra:
            projected[name] = extra
    return projected


PROJECTED = _projected()
if os.environ.get("HOLD_LIST"):
    with open(os.environ["HOLD_LIST"], "w") as f:
        json.dump({k: sorted(v) for k, v in sorted(PROJECTED.items())}, f, indent=1)


def _hold(parameters):
    for parameter in parameters.get_descendants():
        if isinstance(parameter, Parameter) and parameter.name in PROJECTED:
            drop = PROJECTED[parameter.name]
            parameter.values_list = [
                v for v in parameter.values_list if v.instant_str not in drop
            ]
            if parameter.parent is not None:
                parameter.parent.clear_parent_cache()
    return parameters


class reform(Reform):
    def apply(self):
        self.modify_parameters(_hold)
