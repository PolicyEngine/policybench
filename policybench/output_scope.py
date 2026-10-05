"""Keep local income taxes out of the state income tax output.

PolicyBench defines ``state_income_tax_before_refundable_credits`` as "state
individual income tax after nonrefundable credits and before refundable credits,
excluding local income and payroll taxes" (``benchmark_specs.json``). Local income
taxes have their own output, ``local_income_tax``.

policyengine-us builds its variable of the same name by adding the variables
listed in ``parameters/gov/states/household/
state_income_tax_before_refundable_credits.yaml``. On 2.15.17 that list carries
two local taxes:

- ``md_local_income_tax_before_refundable_credits``, Maryland county income tax,
  added by upstream #8888 (2026-07-05). The 2026-09-28 reference system removes it
  with ``reference_audit/2026-09-28/fixes/latest_md_local_output_scope.py``.
- ``nyc_income_tax_before_refundable_credits``, New York City income tax. Nothing
  removes it. It is zero for every frozen household: ``in_nyc`` is true only for
  the five NYC counties, and a household with no county takes its state's
  alphabetically first county (Albany County for New York).

``reform`` removes both, so the engine variable matches the benchmark output. The
county taxes stay where the engine puts them otherwise: Maryland county tax in
``md_withheld_income_tax`` (and so in the federal SALT deduction), NYC tax in
``local_income_tax``. Only the list changes; no formula or amount does.

``scope_violations`` is the assertion half: given a simulation on a system that
still lists a local tax, it returns each listed local tax that is nonzero, which
would put local tax in the state output.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

STATE_AGGREGATE = "state_income_tax_before_refundable_credits"
STATE_AGGREGATE_PARAMETER = (
    "gov.states.household.state_income_tax_before_refundable_credits"
)
LOCAL_INCOME_TAX_COMPONENTS = (
    "md_local_income_tax_before_refundable_credits",
    "nyc_income_tax_before_refundable_credits",
)
# Spelled as engine variable names so a new local entry is caught by name: any
# list entry containing one of these fragments is a local tax.
LOCAL_NAME_FRAGMENTS = (
    "_local_",
    "nyc_",
    "philadelphia",
    "kansas_city",
    "st_louis",
    "wilmington",
    "denver",
)
FIX_ID = "policybench_output_scope"
DESCRIPTION = (
    "Exclude Maryland county and New York City income tax from the state income "
    "tax output (output definition)"
)


def is_local_component(name: str) -> bool:
    """Whether a state-aggregate entry names a local (county or city) tax."""
    return name in LOCAL_INCOME_TAX_COMPONENTS or any(
        fragment in name for fragment in LOCAL_NAME_FRAGMENTS
    )


def scoped_components(components: Iterable[str]) -> list[str]:
    """The state aggregate's list without its local entries, order kept."""
    return [name for name in components if not is_local_component(name)]


def local_components(components: Iterable[str]) -> list[str]:
    """The local entries of a state-aggregate list, order kept."""
    return [name for name in components if is_local_component(name)]


def _aggregate_parameter(parameters):
    node = parameters
    for part in STATE_AGGREGATE_PARAMETER.split("."):
        node = getattr(node, part)
    return node


def listed_local_components(parameters, instant: str = "2026-01-01") -> list[str]:
    """The local taxes a parameter tree adds into the state aggregate."""
    return local_components(_aggregate_parameter(parameters)(instant))


def remove_local_components(parameters):
    """``modify_parameters`` callback: drop every local entry from the list."""
    param = _aggregate_parameter(parameters)
    current = list(param("2026-01-01"))
    kept = scoped_components(current)
    if kept != current:
        param.update(period="year:2015-01-01:20", value=kept)
    assert not local_components(param("2026-01-01"))
    assert "md_income_tax_before_refundable_credits" in param("2026-01-01")
    assert "ny_income_tax_before_refundable_credits" in param("2026-01-01")
    return parameters


def installed_state_aggregate() -> list[str]:
    """The installed policyengine-us state aggregate list, read from its YAML.

    The file is located without importing policyengine_us and parsed without
    building a tax-benefit system (about 40 seconds), so a test can check every
    engine upgrade for a new local entry cheaply.
    """
    import importlib.util
    from pathlib import Path

    import yaml

    spec = importlib.util.find_spec("policyengine_us")
    if spec is None or not spec.submodule_search_locations:
        raise ModuleNotFoundError("policyengine_us is not installed")
    root = Path(next(iter(spec.submodule_search_locations)))
    path = root / (
        "parameters/gov/states/household/"
        "state_income_tax_before_refundable_credits.yaml"
    )
    # BaseLoader keeps the 0000-01-01 key a string; the default loader rejects it.
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    values = data["values"]
    return list(values[sorted(values)[-1]])


def scope_violations(
    simulation: Any,
    components: Sequence[str],
    period: int | str,
    tolerance: float = 0.005,
) -> dict[str, float]:
    """Each listed local tax that is nonzero in ``simulation``, with its amount."""
    violations = {}
    for name in components:
        amount = float(simulation.calculate(name, period).sum())
        if abs(amount) > tolerance:
            violations[name] = amount
    return violations


def _build_reform():
    from policyengine_core.reforms import Reform

    class reform(Reform):
        def apply(self):
            self.modify_parameters(remove_local_components)

    reform.__module__ = __name__
    return reform


def __getattr__(name: str):
    # ``reform`` is built on first access, as a fix module's ``reform`` is read
    # (getattr(module, "reform")), so importing the helpers stays cheap: the CLI
    # imports this module to build its parser.
    if name == "reform":
        globals()["reform"] = _build_reform()
        return globals()["reform"]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
