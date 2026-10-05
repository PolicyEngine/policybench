"""Keep local taxes and credits out of the state outputs.

PolicyBench's state outputs are state-only (``benchmark_specs.json``):

- ``state_income_tax_before_refundable_credits``: "state individual income tax after
  nonrefundable credits and before refundable credits, excluding local income and
  payroll taxes";
- ``state_refundable_credits``: "total refundable state individual income tax
  credits".

Local income taxes have their own output, ``local_income_tax``.

policyengine-us builds each engine variable of those names by adding the variables
a parameter list names. On 2.15.17 three of those lists carry local entries
(``SCOPED_LISTS``):

- ``gov.states.household.state_income_tax_before_refundable_credits``:
  ``md_local_income_tax_before_refundable_credits`` (Maryland county income tax,
  added by upstream #8888; the 2026-09-28 reference system removes it with
  ``reference_audit/2026-09-28/fixes/latest_md_local_output_scope.py``) and
  ``nyc_income_tax_before_refundable_credits`` (New York City income tax, which
  nothing removed);
- ``gov.states.household.state_refundable_credits``: ``nyc_refundable_credits``;
- ``gov.states.ca.tax.income.credits.refundable``: ``ca_sf_wftc``, San Francisco's
  Working Families Tax Credit, which reaches ``state_refundable_credits`` through
  ``ca_refundable_credits``.

``reform`` removes every local entry, so the engine variables match the benchmark
outputs. Only the lists change; no formula or amount does. Maryland county tax still
reaches the federal SALT deduction through ``md_withheld_income_tax``'s county
estimate, and NYC tax net of NYC refundable credits (``nyc_income_tax``) is still in
``local_income_tax``.

Every one of these is zero for every frozen household: ``in_nyc`` is true only in
the five NYC counties and ``in_san_francisco`` only in San Francisco County, and a
household with no county takes its state's alphabetically first county (Albany
County for New York, Alameda County for California). ``scope_violations`` is the
check: it returns each listed local entry that is nonzero in a simulation.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

STATE_AGGREGATE = "state_income_tax_before_refundable_credits"
STATE_AGGREGATE_PARAMETER = (
    "gov.states.household.state_income_tax_before_refundable_credits"
)
STATE_REFUNDABLE_PARAMETER = "gov.states.household.state_refundable_credits"
CA_REFUNDABLE_PARAMETER = "gov.states.ca.tax.income.credits.refundable"
# Each list, the local entries 2.15.17 puts in it, and state entries it must keep.
SCOPED_LISTS = {
    STATE_AGGREGATE_PARAMETER: {
        "local": (
            "md_local_income_tax_before_refundable_credits",
            "nyc_income_tax_before_refundable_credits",
        ),
        "keeps": (
            "md_income_tax_before_refundable_credits",
            "ny_income_tax_before_refundable_credits",
        ),
    },
    STATE_REFUNDABLE_PARAMETER: {
        "local": ("nyc_refundable_credits",),
        "keeps": ("ny_refundable_credits", "ca_refundable_credits"),
    },
    CA_REFUNDABLE_PARAMETER: {
        "local": ("ca_sf_wftc",),
        "keeps": ("ca_eitc",),
    },
}
LOCAL_INCOME_TAX_COMPONENTS = SCOPED_LISTS[STATE_AGGREGATE_PARAMETER]["local"]
LOCAL_COMPONENTS = tuple(
    name for spec in SCOPED_LISTS.values() for name in spec["local"]
)
# Spelled as engine variable names so a new local entry is caught by name: any
# list entry containing one of these fragments is local.
LOCAL_NAME_FRAGMENTS = (
    "_local_",
    "nyc_",
    "_sf_",
    "san_francisco",
    "philadelphia",
    "kansas_city",
    "st_louis",
    "wilmington",
    "denver",
    "yonkers",
    "multnomah",
)
SCOPE_INSTANT = "2026-01-01"
# Where the lists are rewritten: the benchmark year and the years after it.
SCOPE_PERIOD = "year:2026-01-01:10"
FIX_ID = "policybench_output_scope"
DESCRIPTION = (
    "Exclude Maryland county tax and New York City and San Francisco taxes and "
    "credits from the state income tax and state refundable credit outputs "
    "(output definition)"
)


def is_local_component(name: str) -> bool:
    """Whether a list entry names a local (county or city) tax or credit."""
    return name in LOCAL_COMPONENTS or any(
        fragment in name for fragment in LOCAL_NAME_FRAGMENTS
    )


def scoped_components(components: Iterable[str]) -> list[str]:
    """A list without its local entries, order kept."""
    return [name for name in components if not is_local_component(name)]


def local_components(components: Iterable[str]) -> list[str]:
    """The local entries of a list, order kept."""
    return [name for name in components if is_local_component(name)]


def _parameter(parameters, path: str):
    node = parameters
    for part in path.split("."):
        node = getattr(node, part)
    return node


def listed_local_components(
    parameters, path: str = STATE_AGGREGATE_PARAMETER, instant: str = SCOPE_INSTANT
) -> list[str]:
    """The local entries one parameter list adds (default: the state income tax)."""
    return local_components(_parameter(parameters, path)(instant))


def all_listed_local_components(parameters, instant: str = SCOPE_INSTANT) -> list[str]:
    """Every local entry in every scoped list, in ``SCOPED_LISTS`` order."""
    return [
        name
        for path in SCOPED_LISTS
        for name in listed_local_components(parameters, path, instant)
    ]


def remove_local_components(parameters):
    """``modify_parameters`` callback: drop every local entry from every list."""
    for path, spec in SCOPED_LISTS.items():
        param = _parameter(parameters, path)
        current = list(param(SCOPE_INSTANT))
        kept = scoped_components(current)
        if kept != current:
            param.update(period=SCOPE_PERIOD, value=kept)
        after = param(SCOPE_INSTANT)
        assert not local_components(after), (path, after)
        for name in spec["keeps"]:
            assert name in after, (path, name)
    return parameters


def installed_parameter_list(path: str = STATE_AGGREGATE_PARAMETER) -> list[str]:
    """A list parameter of the installed policyengine-us, read from its YAML.

    The latest value is returned. The file is located without importing
    policyengine_us and parsed without building a tax-benefit system (about 40
    seconds), so a test can check every engine upgrade for a new local entry.
    """
    import importlib.util
    from pathlib import Path

    import yaml

    spec = importlib.util.find_spec("policyengine_us")
    if spec is None or not spec.submodule_search_locations:
        raise ModuleNotFoundError("policyengine_us is not installed")
    root = Path(next(iter(spec.submodule_search_locations)))
    path_on_disk = root / "parameters" / (path.replace(".", "/") + ".yaml")
    # BaseLoader keeps the 0000-01-01 key a string; the default loader rejects it.
    data = yaml.load(path_on_disk.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    values = data["values"]
    return list(values[sorted(values)[-1]])


def scope_violations(
    simulation: Any,
    components: Sequence[str],
    period: int | str,
    tolerance: float = 0.005,
) -> dict[str, float]:
    """Each listed local entry that is nonzero in ``simulation``, with its amount."""
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
