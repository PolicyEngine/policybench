"""Check each benchmark output's reference against the qualifiers in its definition.

Every PolicyBench output has a definition, the ``prompt`` text of its entry in
``benchmark_specs.json`` (the text the models saw), and a reference, the
policyengine-us variable named by its ``pe_variable``. That variable is
usually a sum of other variables. policyengine-core 3.32.8 sums the variables
a variable lists in ``adds`` and subtracts those in ``subtracts`` only when no
formula applies at the period, and either attribute may instead be a parameter
path whose value at the period's start is the list
(``Simulation._run_formula``). Some sums are written as formulas instead, such
as ``employee_payroll_tax``'s ``add(tax_unit, period, COMPONENTS)``;
``parse_formula_sum`` reads a formula's source and keeps it only when it is a
plain signed sum of other variables.

``component_tree`` walks that sum from the output's variable to its leaves,
carrying each component's path and its sign relative to the output. A leaf is
a variable the walk does not expand: an input, a formula that is not a plain
sum, a name that is not a variable, or a repeat of a variable already on the
path (a cycle). ``QUALIFIER_RULES`` are tests of what a definition says: each
rule has a pattern that detects a qualifier in the definition ("employee-side",
"excluding local income and payroll taxes", "before refundable credits", ...)
and a test that says whether one component breaks it. ``conformance_report``
applies the detected rules to every component, attaches the scored cells where
a breaking component is nonzero and reaches the reference (an ancestor with
``defined_for`` can zero it), lists the material leaves the definition
neither names nor excludes (``definition_silent``, information only), checks
that every expanded node equals the signed sum of its children in every cell,
and evaluates household scope from per-member records an engine run supplies.

Everything here is a pure function of an abstract variable graph
(``VariableInfo``) except ``variable_graph_from_system``, which reads a graph
from a policyengine-core tax-benefit system object without importing
policyengine. The engine-side driver is
``reference_audit/2026-10-05-reference-adversary/scripts/definition_conformance.py``.
"""

from __future__ import annotations

import ast
import inspect
import re
import textwrap
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_INSTANT = "2026-01-01"
# The frozen prompts list every output under this heading, so every output is
# asked for the household as a whole.
HOUSEHOLD_PROMPT_PHRASE = "Provide the following policy quantities for this household"
# Dollar amounts at or below this are treated as zero.
TOLERANCE = 0.005

ADDS = "adds"
SUBTRACTS = "subtracts"
FORMULA_ADDS = "formula_adds"
FORMULA_SUBTRACTS = "formula_subtracts"
EDGE_SIGNS = {ADDS: 1, SUBTRACTS: -1, FORMULA_ADDS: 1, FORMULA_SUBTRACTS: -1}

OPTIONAL_PASS_THROUGH = "optional_employer_pass_through"


@dataclass(frozen=True)
class VariableInfo:
    """One variable of the graph, as the sum walk needs it.

    ``adds`` and ``subtracts`` hold what policyengine-core sums when no
    formula applies. When the variable declared one of them as a parameter
    path, the path is in ``adds_parameter`` or ``subtracts_parameter`` and the
    tuple holds the parameter's value at the graph's instant.
    ``formula_adds`` and ``formula_subtracts`` hold the terms of a formula
    that is a plain signed sum (see ``parse_formula_sum``); they are empty for
    any other formula. ``parameter_text`` holds the descriptions of the
    parameters the formula reads, as further text evidence for the rules.
    ``defined_for`` names the variable whose positive values mark where the
    engine computes this one; elsewhere it takes its default (0), whatever its
    parts sum to.
    """

    name: str
    entity: str
    label: str = ""
    documentation: str = ""
    adds: tuple[str, ...] = ()
    subtracts: tuple[str, ...] = ()
    adds_parameter: str | None = None
    subtracts_parameter: str | None = None
    has_formula: bool = False
    definition_period: str = "year"
    formula_adds: tuple[str, ...] = ()
    formula_subtracts: tuple[str, ...] = ()
    parameter_text: str = ""
    defined_for: str | None = None

    def edges(self) -> tuple[tuple[str, str], ...]:
        """The ``(edge, child)`` pairs the engine sums for this variable, in order.

        A formula takes precedence over ``adds`` and ``subtracts`` at run time,
        so a variable with a formula expands only through the formula's terms.
        """
        if self.has_formula:
            return tuple((FORMULA_ADDS, child) for child in self.formula_adds) + tuple(
                (FORMULA_SUBTRACTS, child) for child in self.formula_subtracts
            )
        return tuple((ADDS, child) for child in self.adds) + tuple(
            (SUBTRACTS, child) for child in self.subtracts
        )


def _leaf_reason(info: VariableInfo | None) -> str | None:
    if info is None:
        return "not_a_variable"
    if info.edges():
        return None
    if info.has_formula:
        if info.adds or info.subtracts:
            return "formula_overrides_adds"
        return "formula"
    return "input"


def component_tree(graph: Mapping[str, VariableInfo], root: str) -> list[dict]:
    """Every node of ``root``'s sum, depth first in declaration order.

    Each node carries its ``path`` from the root, its ``sign`` relative to the
    root (the product of the edge signs along the path), the ``edge`` that
    reached it, the parameter path that edge came from (``via_parameter``),
    its entity and label, and ``kind``: ``root``, ``intermediate`` or
    ``leaf``. Leaves carry a ``leaf_reason``: ``input``, ``formula`` (a
    formula that is not a plain sum), ``formula_overrides_adds``,
    ``not_a_variable`` or ``cycle`` (the variable is already on the path, so
    the walk stops there).
    """
    nodes: list[dict] = []
    stack: list[tuple[str, tuple[str, ...], int, str | None, str | None]] = [
        (root, (), 1, None, None)
    ]
    while stack:
        name, ancestors, sign, edge, via_parameter = stack.pop()
        path = ancestors + (name,)
        info = graph.get(name)
        cycle = name in ancestors
        reason = "cycle" if cycle else _leaf_reason(info)
        if not ancestors:
            kind = "root" if reason is None else "leaf"
        else:
            kind = "intermediate" if reason is None else "leaf"
        nodes.append(
            {
                "name": name,
                "path": list(path),
                "depth": len(ancestors),
                "sign": sign,
                "edge": edge,
                "via_parameter": via_parameter,
                "entity": info.entity if info is not None else None,
                "label": info.label if info is not None else "",
                "defined_for": info.defined_for if info is not None else None,
                "kind": kind,
                "leaf_reason": reason,
            }
        )
        if reason is not None:
            continue
        children = []
        for child_edge, child in info.edges():
            parameter = None
            if child_edge == ADDS:
                parameter = info.adds_parameter
            elif child_edge == SUBTRACTS:
                parameter = info.subtracts_parameter
            children.append(
                (child, path, sign * EDGE_SIGNS[child_edge], child_edge, parameter)
            )
        stack.extend(reversed(children))
    return nodes


# ----- Qualifier rules ----- #


@dataclass(frozen=True)
class Component:
    """What a qualifier rule sees of one node of an output's sum."""

    name: str
    label: str
    documentation: str
    entity: str | None
    sign: int
    path: tuple[str, ...]
    kind: str
    parameter_text: str = ""
    law_classification: Mapping[str, Any] | None = None
    # Names subtracted by any ancestor of this node (its parent included).
    subtracted_along_path: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        """Label, documentation and parameter descriptions, one sentence apart."""
        parts = (self.label, self.documentation, self.parameter_text)
        return " ".join(
            part.strip() if part.strip().endswith(".") else f"{part.strip()}."
            for part in parts
            if part.strip()
        )


@dataclass(frozen=True)
class RuleHit:
    """A component that breaks a qualifier, with the reason and its evidence.

    ``evidence`` is ``variable_name`` (the variable's name or label),
    ``engine_text`` (its documentation or the descriptions of parameters its
    formula reads), ``law_classification`` (a cited classification supplied
    by the caller) or ``engine_text+law_classification``.
    """

    reason: str
    evidence: str


@dataclass(frozen=True)
class QualifierRule:
    """One qualifier a definition can carry and the component test for it.

    ``pattern`` detects the qualifier in a definition (case-insensitive).
    ``test`` reports a component that breaks it, or ``None``. A rule with
    ``scope="household"`` has no component test; ``conformance_report``
    evaluates it from household-scope records instead. ``effect`` names the
    variable whose cell value measures a hit's effect on the reference when
    that is not the component itself.
    """

    id: str
    description: str
    pattern: str
    test: Callable[[Component], RuleHit | None] | None = None
    scope: str = "component"
    effect: Callable[[Component], str | None] | None = None

    def detects(self, definition: str, *, household_prompt: bool = False) -> bool:
        if self.scope == "household" and household_prompt:
            return True
        return re.search(self.pattern, definition, re.IGNORECASE) is not None


def _describe(component: Component) -> str:
    if component.label:
        return f"'{component.name}' ({component.label})"
    return f"'{component.name}'"


_EMPLOYER_NAME = re.compile(r"(?:^|_)(?:employer|futa)(?:_|$)")
_EMPLOYER_LABEL = re.compile(
    r"\bemployer\b|\bFUTA\b|federal\s+unemployment\s+tax", re.IGNORECASE
)
_EMPLOYEE_NAME = re.compile(r"(?:^|_)employee(?:_|$)")
_EMPLOYEE_LABEL = re.compile(r"\bemployee\b", re.IGNORECASE)


def _employer_side(component: Component) -> RuleHit | None:
    employer = _EMPLOYER_NAME.search(component.name) or _EMPLOYER_LABEL.search(
        component.label
    )
    employee = _EMPLOYEE_NAME.search(component.name) or _EMPLOYEE_LABEL.search(
        component.label
    )
    if employer and not employee:
        return RuleHit(
            f"{_describe(component)} is an employer-side amount", "variable_name"
        )
    return None


# Wording that says an amount rests on an employer's optional election rather
# than on a contribution the law requires the employee to pay.
OPTIONAL_ELECTION = re.compile(
    r"assum\w*\s+(?:that\s+)?(?:the\s+|an\s+)?employers?\s+"
    r"(?:withholds?|deducts?|collects?|elects?|passes)"
    r"|maximum\s+permitted\s+employee\s+share"
    r"|employers?\s+(?:may|can)\s+(?:choose\s+to\s+|elect\s+to\s+)?"
    r"(?:deduct|withhold|collect|pass)"
    r"|allowed,?\s+but\s+not\s+required"
    r"|at\s+the\s+employer'?s\s+(?:option|discretion|election|choice)"
    r"|\boptional\b|\bvoluntar\w*",
    re.IGNORECASE,
)


def _sentence_around(text: str, match: re.Match[str]) -> str:
    start = text.rfind(".", 0, match.start()) + 1
    end = text.find(".", match.end())
    end = len(text) if end < 0 else end + 1
    return " ".join(text[start:end].split())


def _optional_election(component: Component) -> RuleHit | None:
    text = component.text
    match = OPTIONAL_ELECTION.search(text)
    law = component.law_classification or {}
    law_optional = law.get("classification") == OPTIONAL_PASS_THROUGH
    reasons = []
    evidence = []
    if match:
        reasons.append(
            f"{_describe(component)} rests on an optional employer election: "
            f'"{_sentence_around(text, match)}"'
        )
        evidence.append("engine_text")
    if law_optional:
        citation = law.get("citation") or "no citation given"
        reasons.append(
            f"{_describe(component)} is classified as an optional employer "
            f"pass-through ({citation})"
        )
        evidence.append("law_classification")
    if not reasons:
        return None
    return RuleHit("; ".join(reasons), "+".join(evidence))


def _self_employment_tax(component: Component) -> RuleHit | None:
    if re.search(r"self_employment\w*_tax|(?:^|_)se_tax(?:_|$)", component.name) or (
        re.search(
            r"self[- ]employment\s+(?:social\s+security\s+|medicare\s+)?tax",
            component.label,
            re.IGNORECASE,
        )
    ):
        return RuleHit(
            f"{_describe(component)} is self-employment tax", "variable_name"
        )
    return None


def _additional_medicare_tax(component: Component) -> RuleHit | None:
    if "additional_medicare" in component.name or re.search(
        r"additional\s+medicare", component.label, re.IGNORECASE
    ):
        return RuleHit(
            f"{_describe(component)} is Additional Medicare Tax", "variable_name"
        )
    return None


def _employee_payroll_tax(component: Component) -> RuleHit | None:
    if re.search(r"(?:^|_)employee(?:_|$)", component.name) and re.search(
        r"tax|contribution", component.name
    ):
        return RuleHit(
            f"{_describe(component)} is an employee payroll tax", "variable_name"
        )
    return None


def _premium_tax_credit(component: Component) -> RuleHit | None:
    if re.search(
        r"premium_tax_credit|(?:^|_)aca_ptc(?:_|$)", component.name
    ) or re.search(r"premium\s+tax\s+credit", component.label, re.IGNORECASE):
        return RuleHit(
            f"{_describe(component)} is the ACA Premium Tax Credit", "variable_name"
        )
    return None


# Name fragments of local (city or county) income, wage and earnings taxes.
LOCAL_NAME = re.compile(
    r"(?:^|_)local(?:_|$)|(?:^|_)nyc(?:_|$)|philadelphia|kansas_city|st_louis"
    r"|wilmington|denver|yonkers|(?:^|_)county(?:_|$)"
)
LOCAL_LABEL = re.compile(r"\b(?:local|county|city|NYC)\b", re.IGNORECASE)


def _local_tax(component: Component) -> RuleHit | None:
    if LOCAL_NAME.search(component.name) or LOCAL_LABEL.search(component.label):
        return RuleHit(
            f"{_describe(component)} is a local (city or county) amount",
            "variable_name",
        )
    return None


_NON_REFUNDABLE = re.compile(r"non_?refundable|non-?refundable", re.IGNORECASE)


def _is_refundable_credit(component: Component) -> bool:
    name = component.name
    label = component.label
    if _NON_REFUNDABLE.search(name) or _NON_REFUNDABLE.search(label):
        return False
    return bool(
        re.search(r"(?:^|_)refundable(?:_|$)", name)
        or re.search(r"(?:^|_)eitc(?:_|$)", name)
        or re.search(r"\brefundable\b", label, re.IGNORECASE)
        or re.search(r"earned\s+income\s+(?:tax\s+)?credit", label, re.IGNORECASE)
    )


def _refundable_credit_subtracted(component: Component) -> RuleHit | None:
    if component.sign < 0 and _is_refundable_credit(component):
        return RuleHit(
            f"{_describe(component)} is a refundable credit subtracted from an "
            "output defined before refundable credits",
            "variable_name",
        )
    return None


_BEFORE_CREDITS_NAME = re.compile(r"before_(?:non_?refundable_)?credits")


def _before_nonrefundable_credits(component: Component) -> RuleHit | None:
    # Names only: labels are looser. policyengine-us 2.15.17 labels
    # va_income_tax_before_refundable_credits "Virginia income tax before
    # credits" while its formula subtracts va_non_refundable_credits.
    if not _BEFORE_CREDITS_NAME.search(component.name):
        return None
    if any(_NON_REFUNDABLE.search(name) for name in component.subtracted_along_path):
        return None
    return RuleHit(
        f"{_describe(component)} is a tax before credits, and nothing on its path "
        "subtracts nonrefundable credits",
        "variable_name",
    )


def _companion_nonrefundable_credits(component: Component) -> str | None:
    """The variable holding the credits a before-credits component leaves out.

    Follows the policyengine-us naming convention ``<prefix>_non_refundable_
    credits`` (e.g. ``ms_non_refundable_credits`` for
    ``ms_income_tax_before_credits_unit``); the engine run only uses it when
    that variable exists.
    """
    prefix = component.name.split("_", 1)[0]
    return f"{prefix}_non_refundable_credits"


QUALIFIER_RULES: tuple[QualifierRule, ...] = (
    QualifierRule(
        id="employee_side",
        description="Employee-side output: no employer payroll tax, FUTA or "
        "employer unemployment-insurance tax.",
        pattern=r"\bemployee[- ]side\b|\bexclud\w*\s+employer\b",
        test=_employer_side,
    ),
    QualifierRule(
        id="mandatory",
        description="Mandatory amounts only: no amount that rests on an "
        "employer's optional election to pass a premium through to wages.",
        pattern=r"\bmandatory\b",
        test=_optional_election,
    ),
    QualifierRule(
        id="excludes_self_employment_tax",
        description="Self-employment tax is excluded.",
        pattern=r"\bexclud\w*\b[^.]*?\bself[- ]employment\s+tax",
        test=_self_employment_tax,
    ),
    QualifierRule(
        id="excludes_additional_medicare_tax",
        description="Additional Medicare Tax is excluded.",
        pattern=r"\bexclud\w*\b[^.]*?\badditional\s+medicare\s+tax",
        test=_additional_medicare_tax,
    ),
    QualifierRule(
        id="excludes_employee_payroll_taxes",
        description="Employee payroll taxes are excluded.",
        pattern=r"\bexclud\w*\b[^.]*?\bemployee\s+payroll\s+tax",
        test=_employee_payroll_tax,
    ),
    QualifierRule(
        id="excludes_premium_tax_credit",
        description="The ACA Premium Tax Credit is excluded.",
        pattern=r"\bexclud\w*\b[^.]*?\bpremium\s+tax\s+credit",
        test=_premium_tax_credit,
    ),
    QualifierRule(
        id="excludes_local_tax",
        description="Local income and payroll taxes are excluded.",
        pattern=r"\bexclud\w*\b[^.]*?\blocal\b",
        test=_local_tax,
    ),
    QualifierRule(
        id="state_scope",
        description="A state individual income tax amount: no city or county "
        "income tax or credit.",
        pattern=r"\bstate\s+individual\s+income\s+tax\b",
        test=_local_tax,
    ),
    QualifierRule(
        id="before_refundable_credits",
        description="Before refundable credits: no refundable credit is subtracted.",
        pattern=r"\bbefore\s+refundable\s+credits\b",
        test=_refundable_credit_subtracted,
    ),
    QualifierRule(
        id="after_nonrefundable_credits",
        description="After nonrefundable credits: a tax computed before credits "
        "needs its nonrefundable credits subtracted.",
        pattern=r"\bafter\s+non-?refundable\s+credits\b",
        test=_before_nonrefundable_credits,
        effect=_companion_nonrefundable_credits,
    ),
    QualifierRule(
        id="household_scope",
        description="A household amount: every member's income the output "
        "would count, including a dependent's own return.",
        pattern=r"\bhousehold\b",
        scope="household",
    ),
)


# ----- Definition-silent components ----- #

_STOPWORDS = frozenset(
    """
    a an and annual amount after at before by credit credits each federal for from
    in income individual liability non nonrefundable of on or per refundable side
    state states tax taxes the to total unit us usd with person household employee
    payroll contribution contributions
    """.split()
)
_STATE_NAME_TOKENS = frozenset(
    """
    alabama alaska arizona arkansas california colorado connecticut delaware district
    columbia florida georgia hawaii idaho illinois indiana iowa kansas kentucky
    louisiana maine maryland massachusetts michigan minnesota mississippi missouri
    montana nebraska nevada new hampshire jersey mexico york north carolina dakota
    ohio oklahoma oregon pennsylvania rhode island south tennessee texas utah vermont
    virginia washington west wisconsin wyoming
    """.split()
)


def _tokens(text: str) -> set[str]:
    text = text.lower().replace("non-refundable", "nonrefundable")
    text = text.replace("non refundable", "nonrefundable")
    return set(re.findall(r"[a-z0-9]+", text.replace("_", " ")))


def _distinctive_tokens(label: str) -> set[str]:
    return _tokens(label) - _STOPWORDS - _STATE_NAME_TOKENS


def _is_named(node: Mapping[str, Any], definition_tokens: set[str]) -> bool:
    label = node.get("label") or node["name"].replace("_", " ")
    distinctive = _distinctive_tokens(label)
    return not distinctive or bool(distinctive & definition_tokens)


# ----- Formula reading ----- #


class _Unsupported(Exception):
    """A formula construct outside the plain signed sums this module reads."""


@dataclass(frozen=True)
class _Terms:
    items: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class _Names:
    items: tuple[str, ...]


@dataclass(frozen=True)
class _ParamRef:
    path: str


class _FormulaReader:
    def __init__(
        self,
        func: ast.FunctionDef,
        resolve_name: Callable[[str], Any] | None,
        resolve_parameter: Callable[[str], Any] | None,
    ) -> None:
        args = [arg.arg for arg in func.args.args]
        self.entity_arg = args[0] if args else None
        self.parameters_arg = args[2] if len(args) >= 3 else None
        self.resolve_name = resolve_name
        self.resolve_parameter = resolve_parameter
        self.env: dict[str, Any] = {}

    def run(self, body: list[ast.stmt]) -> _Terms:
        for index, statement in enumerate(body):
            if isinstance(statement, ast.Expr) and isinstance(
                statement.value, ast.Constant
            ):
                continue
            if isinstance(statement, ast.Assign):
                if len(statement.targets) != 1 or not isinstance(
                    statement.targets[0], ast.Name
                ):
                    raise _Unsupported("assignment target")
                self.env[statement.targets[0].id] = self.value(statement.value)
                continue
            if isinstance(statement, ast.If):
                if not _returns_zero(statement.body):
                    raise _Unsupported("conditional")
                return self.run(list(statement.orelse) + list(body[index + 1 :]))
            if isinstance(statement, ast.Return):
                if statement.value is None:
                    raise _Unsupported("empty return")
                result = self.value(statement.value)
                if not isinstance(result, _Terms) or not result.items:
                    raise _Unsupported("return value")
                return result
            raise _Unsupported(type(statement).__name__)
        raise _Unsupported("no return")

    def names(self, value: Any) -> tuple[str, ...]:
        if isinstance(value, _Names):
            return value.items
        if isinstance(value, _ParamRef) and self.resolve_parameter is not None:
            resolved = self.resolve_parameter(value.path)
            if _is_name_list(resolved):
                return tuple(resolved)
        raise _Unsupported("list of variables")

    def value(self, node: ast.expr) -> Any:
        if isinstance(node, (ast.List, ast.Tuple)):
            items = []
            for element in node.elts:
                if not (
                    isinstance(element, ast.Constant) and isinstance(element.value, str)
                ):
                    raise _Unsupported("list element")
                items.append(element.value)
            return _Names(tuple(items))
        if isinstance(node, ast.Name):
            if node.id in self.env:
                return self.env[node.id]
            if self.resolve_name is not None:
                resolved = self.resolve_name(node.id)
                if _is_name_list(resolved):
                    return _Names(tuple(resolved))
            raise _Unsupported(f"name {node.id}")
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            path = _parameter_chain(node, self.parameters_arg, self.env)
            if path is None:
                raise _Unsupported("attribute")
            return _ParamRef(path)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            left = self.value(node.left)
            right = self.value(node.right)
            if not isinstance(left, _Terms) or not isinstance(right, _Terms):
                raise _Unsupported("arithmetic")
            sign = 1 if isinstance(node.op, ast.Add) else -1
            return _Terms(
                left.items + tuple((sign * s, name) for s, name in right.items)
            )
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            operand = self.value(node.operand)
            if not isinstance(operand, _Terms):
                raise _Unsupported("negation")
            return _Terms(tuple((-s, name) for s, name in operand.items))
        if isinstance(node, ast.Call):
            return self.call(node)
        raise _Unsupported(type(node).__name__)

    def call(self, node: ast.Call) -> _Terms:
        if node.keywords or not isinstance(node.func, ast.Name):
            raise _Unsupported("call")
        function = node.func.id
        if function == "add" and len(node.args) == 3:
            names = self.names(self.value(node.args[2]))
            return _Terms(tuple((1, name) for name in names))
        first = node.args[0] if node.args else None
        is_string = isinstance(first, ast.Constant) and isinstance(first.value, str)
        if function == "sum_contained_tax_units" and is_string:
            return _Terms(((1, first.value),))
        if function == self.entity_arg and is_string and len(node.args) == 2:
            return _Terms(((1, first.value),))
        raise _Unsupported(f"call {function}")


def _is_name_list(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and all(
        isinstance(item, str) for item in value
    )


def _returns_zero(body: list[ast.stmt]) -> bool:
    return (
        len(body) == 1
        and isinstance(body[0], ast.Return)
        and isinstance(body[0].value, ast.Constant)
        and body[0].value.value == 0
    )


def _parameter_chain(
    node: ast.expr, parameters_arg: str | None, env: Mapping[str, Any]
) -> str | None:
    """The dotted parameter path an expression such as ``p.rate`` reads."""
    parts: list[str] = []
    while True:
        if isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            parts.append(node.slice.value)
            node = node.value
        else:
            break
    parts.reverse()
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == (parameters_arg or "parameters")
    ):
        prefix: list[str] = []
    elif isinstance(node, ast.Name) and isinstance(env.get(node.id), _ParamRef):
        prefix = env[node.id].path.split(".")
    else:
        return None
    path = ".".join(prefix + parts)
    return path or None


def _function_def(source: str) -> ast.FunctionDef | None:
    try:
        module = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return None
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef):
            return node
    return None


def parse_formula_sum(
    source: str,
    *,
    resolve_name: Callable[[str], Any] | None = None,
    resolve_parameter: Callable[[str], Any] | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """Read a formula that is a plain signed sum into ``(adds, subtracts)``.

    The forms read are ``add(entity, period, LIST)``, where ``LIST`` is a
    literal list of names, a name bound to one (a module constant, resolved
    through ``resolve_name``) or a parameter whose value is one (resolved
    through ``resolve_parameter``); ``sum_contained_tax_units("name", ...)``;
    ``entity("name", period)``; names bound to any of these; ``+``, ``-`` and
    unary ``-`` over them; and a leading ``if ...: return 0`` guard, which is
    skipped. Anything else (``max_``, ``where``, products, loops, other
    branches) returns ``None``: the formula is then a leaf. A reading is a
    claim about the formula's source only; the engine run checks it against
    computed values in every cell.
    """
    func = _function_def(source)
    if func is None:
        return None
    reader = _FormulaReader(func, resolve_name, resolve_parameter)
    try:
        terms = reader.run(list(func.body))
    except _Unsupported:
        return None
    adds = tuple(name for sign, name in terms.items if sign > 0)
    subtracts = tuple(name for sign, name in terms.items if sign < 0)
    return adds, subtracts


class _ParameterPaths(ast.NodeVisitor):
    def __init__(self, parameters_arg: str) -> None:
        self.parameters_arg = parameters_arg
        self.env: dict[str, _ParamRef] = {}
        self.paths: set[str] = set()

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        path = _parameter_chain(node.value, self.parameters_arg, self.env)
        if path is not None and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                self.env[target.id] = _ParamRef(path)

    def _chain(self, node: ast.expr) -> None:
        path = _parameter_chain(node, self.parameters_arg, self.env)
        if path is None:
            self.generic_visit(node)
        else:
            self.paths.add(path)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self._chain(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self._chain(node)


def formula_parameter_paths(source: str) -> tuple[str, ...]:
    """The parameter paths a formula reads, as written (``p.rate`` resolved)."""
    func = _function_def(source)
    if func is None:
        return ()
    args = [arg.arg for arg in func.args.args]
    visitor = _ParameterPaths(args[2] if len(args) >= 3 else "parameters")
    for statement in func.body:
        visitor.visit(statement)
    return tuple(sorted(visitor.paths))


# ----- Reading a graph from a policyengine-core system ----- #


def _parameter_node(parameters: Any, path: str) -> Any:
    node = parameters
    for part in path.split("."):
        children = getattr(node, "children", None)
        if isinstance(children, Mapping) and part in children:
            node = children[part]
        else:
            node = getattr(node, part)
    return node


def _parameter_value(parameters: Any, path: str, instant: str) -> Any:
    return _parameter_node(parameters, path)(instant)


def _list_attribute(
    system: Any, value: Any, instant: str
) -> tuple[tuple[str, ...], str | None]:
    if value is None:
        return (), None
    if isinstance(value, str):
        return tuple(_parameter_value(system.parameters, value, instant)), value
    return tuple(value), None


def _parameter_descriptions(parameters: Any, paths: Iterable[str]) -> str:
    texts: list[str] = []
    for path in paths:
        parts = path.split(".")
        # Use the deepest prefix of the path that names a parameter node.
        for end in range(len(parts), 0, -1):
            try:
                node = _parameter_node(parameters, ".".join(parts[:end]))
            except (AttributeError, KeyError, TypeError):
                continue
            for text in (
                getattr(node, "description", None),
                (getattr(node, "metadata", None) or {}).get("label"),
            ):
                if isinstance(text, str) and text.strip():
                    text = " ".join(text.split())
                    if text not in texts:
                        texts.append(text)
            break
    return " ".join(texts)


def _closure_values(function: Any) -> dict[str, Any]:
    names = getattr(getattr(function, "__code__", None), "co_freevars", ())
    cells = getattr(function, "__closure__", None) or ()
    values = {}
    for name, cell in zip(names, cells, strict=False):
        try:
            values[name] = cell.cell_contents
        except ValueError:
            continue
    return values


def _read_formula(
    system: Any, formula: Any, instant: str
) -> tuple[tuple[tuple[str, ...], tuple[str, ...]] | None, tuple[str, ...]]:
    closure = _closure_values(formula)
    if getattr(formula, "__name__", "") == "sum_of_variables" and (
        "variables" in closure
    ):
        names, _ = _list_attribute(system, closure["variables"], instant)
        return (names, ()), ()
    try:
        source = inspect.getsource(formula)
    except (OSError, TypeError):
        return None, ()
    module_globals = getattr(formula, "__globals__", {})

    def resolve_name(name: str) -> Any:
        if name in closure:
            return closure[name]
        return module_globals.get(name)

    def resolve_parameter(path: str) -> Any:
        try:
            return _parameter_value(system.parameters, path, instant)
        except (AttributeError, KeyError, TypeError, ValueError):
            return None

    parsed = parse_formula_sum(
        source, resolve_name=resolve_name, resolve_parameter=resolve_parameter
    )
    return parsed, formula_parameter_paths(source)


def _defined_for_name(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "name", value))


def _variable_info(system: Any, variable: Any, instant: str) -> VariableInfo:
    adds, adds_parameter = _list_attribute(system, variable.adds, instant)
    subtracts, subtracts_parameter = _list_attribute(
        system, variable.subtracts, instant
    )
    formula = variable.get_formula(instant)
    formula_adds: tuple[str, ...] = ()
    formula_subtracts: tuple[str, ...] = ()
    parameter_text = ""
    if formula is not None:
        parsed, paths = _read_formula(system, formula, instant)
        if parsed is not None:
            formula_adds, formula_subtracts = parsed
        parameter_text = _parameter_descriptions(system.parameters, paths)
    period = getattr(variable, "definition_period", "year")
    return VariableInfo(
        name=variable.name,
        entity=variable.entity.key,
        label=" ".join(str(variable.label or "").split()),
        documentation=" ".join(str(variable.documentation or "").split()),
        adds=adds,
        subtracts=subtracts,
        adds_parameter=adds_parameter,
        subtracts_parameter=subtracts_parameter,
        has_formula=formula is not None,
        definition_period=str(getattr(period, "value", period)),
        formula_adds=formula_adds,
        formula_subtracts=formula_subtracts,
        parameter_text=parameter_text,
        defined_for=_defined_for_name(getattr(variable, "defined_for", None)),
    )


def variable_graph_from_system(
    system: Any,
    instant: str = DEFAULT_INSTANT,
    *,
    roots: Iterable[str] | None = None,
) -> dict[str, VariableInfo]:
    """Read the variable graph of a policyengine-core tax-benefit system.

    ``adds`` or ``subtracts`` given as a parameter path are resolved to the
    parameter's list at ``instant``, as policyengine-core does at a period's
    start. A variable has a formula when ``get_formula(instant)`` returns one;
    its source is then read with ``parse_formula_sum``. With ``roots``, only
    the variables their sums reach are read; otherwise every variable is.
    """
    variables = system.variables
    queue = list(variables) if roots is None else list(roots)
    graph: dict[str, VariableInfo] = {}
    while queue:
        name = queue.pop(0)
        if name in graph or name not in variables:
            continue
        info = _variable_info(system, variables[name], instant)
        graph[name] = info
        if roots is not None:
            queue.extend(child for _, child in info.edges())
    return graph


# ----- The report ----- #


def _spec_field(spec: Any, name: str) -> Any:
    if isinstance(spec, Mapping):
        return spec[name]
    return getattr(spec, name)


def _subtracted_along_path(
    graph: Mapping[str, VariableInfo], path: Sequence[str]
) -> tuple[str, ...]:
    names: list[str] = []
    for ancestor in path[:-1]:
        info = graph.get(ancestor)
        if info is None:
            continue
        for edge, child in info.edges():
            if EDGE_SIGNS[edge] < 0:
                names.append(child)
    return tuple(names)


def _component(
    node: Mapping[str, Any],
    graph: Mapping[str, VariableInfo],
    law_classifications: Mapping[str, Mapping[str, Any]],
) -> Component:
    info = graph.get(node["name"])
    return Component(
        name=node["name"],
        label=node["label"],
        documentation=info.documentation if info is not None else "",
        entity=node["entity"],
        sign=node["sign"],
        path=tuple(node["path"]),
        kind=node["kind"],
        parameter_text=info.parameter_text if info is not None else "",
        law_classification=law_classifications.get(node["name"]),
        subtracted_along_path=_subtracted_along_path(graph, node["path"]),
    )


def _is_under(path: Sequence[str], prefixes: Iterable[tuple[str, ...]]) -> bool:
    path = tuple(path)
    return any(path[: len(prefix)] == prefix for prefix in prefixes)


def _nonzero(value: Any, tolerance: float) -> bool:
    return isinstance(value, (int, float)) and abs(value) > tolerance


def _masking_ancestors(
    graph: Mapping[str, VariableInfo], path: Sequence[str]
) -> tuple[str, ...]:
    """Ancestors on ``path`` whose ``defined_for`` can zero what lies below them."""
    return tuple(
        name
        for name in path[:-1]
        if graph.get(name) is not None and graph[name].defined_for is not None
    )


def _cells_for(
    cells: Sequence[Mapping[str, Any]] | None,
    variable: str,
    scale: int,
    tolerance: float,
    masks: Sequence[str] = (),
) -> tuple[list[dict], bool | None, float]:
    """Cells where ``variable`` reaches the reference, if that is known, and the sum.

    A value does not reach the reference in a cell where an ancestor in
    ``masks`` (one with ``defined_for``) is zero.
    """
    if cells is None:
        return [], None, 0.0
    hits = []
    known = 0
    total = 0.0
    for cell in cells:
        values = cell.get("values") or {}
        if variable not in values or values[variable] is None:
            continue
        known += 1
        value = float(values[variable])
        if abs(value) <= tolerance:
            continue
        if any(
            values.get(mask) is not None and abs(float(values[mask])) <= tolerance
            for mask in masks
        ):
            continue
        effect = scale * value
        total += effect
        reference = cell.get("reference")
        hits.append(
            {
                "scenario_id": cell["scenario_id"],
                "output_id": cell.get("output_id"),
                "value": value,
                "effect_on_reference": effect,
                "reference": reference,
            }
        )
    if hits:
        return hits, True, total
    return hits, (False if known else None), total


def _conservation(
    tree: Sequence[Mapping[str, Any]],
    graph: Mapping[str, VariableInfo],
    cells: Sequence[Mapping[str, Any]],
    tolerance: float,
) -> dict[str, Any]:
    expanded = []
    seen = set()
    for node in tree:
        if node["kind"] in ("root", "intermediate") and node["name"] not in seen:
            seen.add(node["name"])
            expanded.append(node["name"])
    checked = 0
    failures = []
    masked = []
    for cell in cells:
        values = cell.get("values") or {}
        for name in expanded:
            info = graph[name]
            edges = info.edges()
            if values.get(name) is None or any(
                values.get(child) is None for _, child in edges
            ):
                continue
            total = sum(
                EDGE_SIGNS[edge] * float(values[child]) for edge, child in edges
            )
            value = float(values[name])
            scale = abs(value) + sum(abs(float(values[child])) for _, child in edges)
            checked += 1
            if abs(value - total) <= max(tolerance, 5e-7 * scale):
                continue
            record = {
                "scenario_id": cell["scenario_id"],
                "variable": name,
                "value": value,
                "sum_of_parts": total,
            }
            # The engine returns the default (0) wherever defined_for is not
            # positive, whatever the parts sum to.
            if info.defined_for is not None and abs(value) <= tolerance:
                record["defined_for"] = info.defined_for
                masked.append(record)
            else:
                failures.append(record)
    return {
        "expanded_nodes": expanded,
        "checks": checked,
        "failures": failures,
        "masked_by_defined_for": masked,
    }


def _household_mismatches(
    output_id: str,
    records: Sequence[Mapping[str, Any]],
    tolerance: float,
) -> tuple[list[dict], list[dict]]:
    mismatches = []
    notes = []
    for record in records:
        deltas = record.get("output_deltas") or {}
        own_return = record.get("own_return") or {}
        own_outputs = own_return.get("outputs") or {}
        if output_id not in deltas or output_id not in own_outputs:
            continue
        earned = float(record.get("earned_income") or 0.0)
        unearned = float(record.get("unearned_income") or 0.0)
        if earned + unearned <= tolerance:
            continue
        delta = float(deltas[output_id])
        if abs(delta) > tolerance:
            continue
        own = float(own_outputs[output_id])
        required = own_return.get("required_to_file")
        counted_by = {
            other: float(value)
            for other, value in sorted(deltas.items())
            if other != output_id and abs(float(value)) > tolerance
        }
        person = record["person"]
        entry = {
            "output_id": output_id,
            "rule": "household_scope",
            "scenario_id": record["scenario_id"],
            "person": person,
            "earned_income": earned,
            "unearned_income": unearned,
            "reference": (record.get("references") or {}).get(output_id),
            "change_without_person_income": delta,
            "own_return_value": own,
            "required_to_file": required,
            "own_return_details": {
                key: value for key, value in own_return.items() if key != "outputs"
            },
            "counted_by": counted_by,
        }
        filing = {
            True: "they would have a federal filing requirement",
            False: "they would have no federal filing requirement",
        }.get(required, "their filing requirement is unknown")
        counters = (
            f"{', '.join(counted_by)} count{'s' if len(counted_by) == 1 else ''} it"
            if counted_by
            else "no other scored output of this household counts it"
        )
        if abs(own) > tolerance:
            entry["reason"] = (
                f"{person}'s income (earned {earned:,.2f}, unearned "
                f"{unearned:,.2f}) is outside the reference's computation "
                f"(removing it moves the reference by {delta:,.2f}); on their own "
                f"return it would come to {own:,.2f}; {filing}; {counters}"
            )
            mismatches.append(entry)
        elif required:
            entry["reason"] = (
                f"{person}'s income is outside the reference's computation and "
                f"{filing}, but their own return comes to 0 for this output; "
                f"{counters}"
            )
            notes.append(entry)
    return mismatches, notes


def _normalize_law(
    law_classifications: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Mapping[str, Any]]:
    return dict(law_classifications or {})


def conformance_report(
    specs: Iterable[Any],
    graph: Mapping[str, VariableInfo],
    *,
    cell_components: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    household_scope: Sequence[Mapping[str, Any]] | None = None,
    household_prompt: bool = False,
    law_classifications: Mapping[str, Mapping[str, Any]] | None = None,
    rules: Sequence[QualifierRule] = QUALIFIER_RULES,
    tolerance: float = TOLERANCE,
) -> dict[str, Any]:
    """Test every output's components against the qualifiers its definition carries.

    ``specs`` are output specs (mappings or objects with ``id``,
    ``pe_variable`` and ``prompt``, the definition). ``cell_components`` maps
    an output id to its scored cells, each ``{"scenario_id", "output_id",
    "reference", "values": {variable: value}}`` where a value is the
    variable's total over the household's entities. ``household_scope`` holds
    one record per household member whose income an engine run removed:
    ``{"scenario_id", "person", "earned_income", "unearned_income",
    "output_deltas": {output_id: reference minus value without the member's
    income}, "references": {...}, "own_return": {"required_to_file",
    "outputs": {output_id: value on the member's own return}}}``.
    ``household_prompt`` says every output was asked for the household (the
    frozen prompts' "Provide the following policy quantities for this
    household"). ``law_classifications`` maps a variable to a cited
    classification such as ``{"classification":
    "optional_employer_pass_through", "citation": ...}``.

    The report depends only on the variables the outputs' sums reach and on
    the arguments; it never reads the rest of the graph.
    """
    law = _normalize_law(law_classifications)
    outputs = []
    flat_mismatches: list[dict] = []
    flat_silent: list[dict] = []
    household_notes: list[dict] = []
    conservation_failures = 0
    for spec in specs:
        output_id = str(_spec_field(spec, "id"))
        root = str(_spec_field(spec, "pe_variable"))
        definition = str(_spec_field(spec, "prompt"))
        tree = component_tree(graph, root)
        cells = None
        if cell_components is not None:
            cells = list(cell_components.get(output_id, ()))
        detected = [
            rule
            for rule in rules
            if rule.detects(definition, household_prompt=household_prompt)
        ]
        components = [_component(node, graph, law) for node in tree]
        rule_checks = []
        output_mismatches: list[dict] = []
        flagged: set[tuple[str, ...]] = set()
        for rule in detected:
            if rule.scope != "component" or rule.test is None:
                continue
            rule_flagged: set[tuple[str, ...]] = set()
            hits = 0
            for node, component in zip(tree, components, strict=True):
                if _is_under(node["path"], rule_flagged):
                    continue
                hit = rule.test(component)
                if hit is None:
                    continue
                hits += 1
                path = tuple(node["path"])
                rule_flagged.add(path)
                effect_variable = rule.effect(component) if rule.effect else None
                masks = _masking_ancestors(graph, node["path"])
                if effect_variable is None:
                    effect_cells = _cells_for(
                        cells, node["name"], node["sign"], tolerance, masks
                    )
                else:
                    effect_cells = _cells_for(
                        cells, effect_variable, 1, tolerance, masks
                    )
                hit_cells, material, total = effect_cells
                output_mismatches.append(
                    {
                        "output_id": output_id,
                        "rule": rule.id,
                        "component": node["name"],
                        "label": node["label"],
                        "path": node["path"],
                        "sign": node["sign"],
                        "entity": node["entity"],
                        "kind": node["kind"],
                        "evidence": hit.evidence,
                        "reason": hit.reason,
                        "effect_variable": effect_variable or node["name"],
                        "material": material,
                        "cells": hit_cells,
                        "total_effect_on_references": total,
                    }
                )
            flagged |= rule_flagged
            rule_checks.append(
                {
                    "rule": rule.id,
                    "status": "mismatch" if hits else "conforms",
                    "components_tested": len(tree),
                    "mismatches": hits,
                }
            )

        definition_tokens = _tokens(definition)
        named: set[tuple[str, ...]] = set()
        silent = []
        for node in tree:
            path = tuple(node["path"])
            # A member of a parameter list is named by the list's category (the
            # output is "all state refundable credits", say); any other node is
            # named when its label is generic or shares a word with the
            # definition. Everything under a named node counts as named.
            if len(path) > 1 and (
                node["via_parameter"] or _is_named(node, definition_tokens)
            ):
                named.add(path)
            if node["kind"] != "leaf" or len(path) == 1:
                continue
            if _is_under(path, flagged) or _is_under(path, named):
                continue
            if node["leaf_reason"] == "cycle":
                continue
            hit_cells, material, total = _cells_for(
                cells,
                node["name"],
                node["sign"],
                tolerance,
                _masking_ancestors(graph, node["path"]),
            )
            silent.append(
                {
                    "output_id": output_id,
                    "component": node["name"],
                    "label": node["label"],
                    "path": node["path"],
                    "sign": node["sign"],
                    "material": material,
                    "cells": hit_cells,
                    "total_effect_on_references": total,
                }
            )

        household_rule = next(
            (rule for rule in detected if rule.scope == "household"), None
        )
        household_mismatches: list[dict] = []
        if household_rule is not None and household_scope is not None:
            household_mismatches, notes = _household_mismatches(
                output_id, household_scope, tolerance
            )
            household_notes.extend(notes)
            rule_checks.append(
                {
                    "rule": household_rule.id,
                    "status": "mismatch" if household_mismatches else "conforms",
                    "records_tested": len(household_scope),
                    "mismatches": len(household_mismatches),
                }
            )
        elif household_rule is not None:
            rule_checks.append(
                {
                    "rule": household_rule.id,
                    "status": "not_evaluated",
                    "records_tested": 0,
                    "mismatches": 0,
                }
            )

        entry: dict[str, Any] = {
            "id": output_id,
            "pe_variable": root,
            "definition": definition,
            "qualifiers": [rule.id for rule in detected],
            "tree": tree,
            "rule_checks": rule_checks,
            "mismatches": output_mismatches,
            "household_scope_mismatches": household_mismatches,
            "definition_silent": silent,
        }
        if cells is not None:
            conservation = _conservation(tree, graph, cells, tolerance)
            conservation_failures += len(conservation["failures"])
            entry["conservation"] = conservation
            tree_names = {node["name"] for node in tree}
            entry["cells"] = [
                {
                    "scenario_id": cell["scenario_id"],
                    "output_id": cell.get("output_id"),
                    "reference": cell.get("reference"),
                    "nonzero_components": {
                        name: float(value)
                        for name, value in sorted((cell.get("values") or {}).items())
                        if name in tree_names and _nonzero(value, tolerance)
                    },
                }
                for cell in cells
            ]
        outputs.append(entry)
        flat_mismatches.extend(output_mismatches)
        flat_mismatches.extend(household_mismatches)
        flat_silent.extend(silent)

    by_rule: dict[str, dict[str, int]] = {}
    material_cells: set[tuple[str, str]] = set()
    for mismatch in flat_mismatches:
        counts = by_rule.setdefault(
            mismatch["rule"], {"mismatches": 0, "material": 0, "cells": 0}
        )
        counts["mismatches"] += 1
        if mismatch["rule"] == "household_scope":
            counts["material"] += 1
            counts["cells"] += 1
            material_cells.add((mismatch["scenario_id"], mismatch["output_id"]))
            continue
        if mismatch["material"]:
            counts["material"] += 1
        counts["cells"] += len(mismatch["cells"])
        for cell in mismatch["cells"]:
            material_cells.add(
                (cell["scenario_id"], cell.get("output_id") or mismatch["output_id"])
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "household_prompt": household_prompt,
        "tolerance": tolerance,
        "rules": [
            {
                "id": rule.id,
                "description": rule.description,
                "pattern": rule.pattern,
                "scope": rule.scope,
            }
            for rule in rules
        ],
        "outputs": outputs,
        "mismatches": flat_mismatches,
        "definition_silent": [item for item in flat_silent if item["material"]],
        "household_scope_notes": household_notes,
        "household_scope_records": list(household_scope or ()),
        "summary": {
            "outputs": len(outputs),
            "mismatches": len(flat_mismatches),
            "material_mismatches": sum(
                1
                for mismatch in flat_mismatches
                if mismatch.get("material") or mismatch["rule"] == "household_scope"
            ),
            "material_cells": len(material_cells),
            "by_rule": by_rule,
            "definition_silent_material": sum(
                1 for item in flat_silent if item["material"]
            ),
            "conservation_failures": conservation_failures,
        },
    }


# ----- Markdown ----- #


def _money(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value):,.2f}"


def _cell_list(cells: Sequence[Mapping[str, Any]], limit: int = 6) -> str:
    parts = [
        f"{cell['scenario_id']} {_money(cell['effect_on_reference'])}"
        for cell in cells[:limit]
    ]
    if len(cells) > limit:
        parts.append(f"... {len(cells) - limit} more")
    return "; ".join(parts)


def _escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(
    report: Mapping[str, Any], *, title: str, notes: Sequence[str] = ()
) -> str:
    """A short Markdown summary of a report's mismatches, then ``notes``."""
    summary = report["summary"]
    lines = [
        f"# {title}",
        "",
        f"{summary['outputs']} outputs; {summary['mismatches']} mismatches, "
        f"{summary['material_mismatches']} material, touching "
        f"{summary['material_cells']} scored cells; "
        f"{summary['definition_silent_material']} material definition-silent "
        f"components; {summary['conservation_failures']} conservation failures.",
        "",
        "## Component mismatches",
        "",
        "| Output | Rule | Component | Evidence | Material | Cells (effect on "
        "reference) | Reason |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    component_rows = [m for m in report["mismatches"] if m["rule"] != "household_scope"]
    component_rows.sort(
        key=lambda m: (not m["material"], m["output_id"], m["rule"], m["component"])
    )
    for mismatch in component_rows:
        material = {True: "yes", False: "no", None: "unknown"}[mismatch["material"]]
        lines.append(
            f"| {mismatch['output_id']} | {mismatch['rule']} | "
            f"`{mismatch['component']}` | {mismatch['evidence']} | {material} | "
            f"{_cell_list(mismatch['cells'])} | {_escape(mismatch['reason'])} |"
        )
    if not component_rows:
        lines.append("| none | | | | | | |")
    household_rows = [m for m in report["mismatches"] if m["rule"] == "household_scope"]
    lines += [
        "",
        "## Household scope",
        "",
        "| Scenario | Output | Person | Earned | Unearned | Reference | Own return | "
        "Must file | Counted by |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for mismatch in sorted(
        household_rows, key=lambda m: (m["scenario_id"], m["output_id"])
    ):
        counted = ", ".join(
            f"{name} {_money(value)}" for name, value in mismatch["counted_by"].items()
        )
        lines.append(
            f"| {mismatch['scenario_id']} | {mismatch['output_id']} | "
            f"{mismatch['person']} | {_money(mismatch['earned_income'])} | "
            f"{_money(mismatch['unearned_income'])} | "
            f"{_money(mismatch['reference'])} | "
            f"{_money(mismatch['own_return_value'])} | "
            f"{mismatch['required_to_file']} | {counted} |"
        )
    if not household_rows:
        lines.append("| none | | | | | | | | |")
    lines += [
        "",
        "## Material definition-silent components (information)",
        "",
        "| Output | Component | Label | Cells (effect on reference) |",
        "| --- | --- | --- | --- |",
    ]
    for item in report["definition_silent"]:
        lines.append(
            f"| {item['output_id']} | `{item['component']}` | "
            f"{_escape(item['label'])} | {_cell_list(item['cells'])} |"
        )
    if not report["definition_silent"]:
        lines.append("| none | | | |")
    if notes:
        lines += ["", "## Notes", ""]
        lines += [f"- {note}" for note in notes]
    lines.append("")
    return "\n".join(lines)
