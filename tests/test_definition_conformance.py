"""Tests for the definition-conformance check (no engine, no network)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from policybench.definition_conformance import (
    EDGE_SIGNS,
    HOUSEHOLD_PROMPT_PHRASE,
    QUALIFIER_RULES,
    Component,
    VariableInfo,
    component_tree,
    conformance_report,
    formula_parameter_paths,
    parse_formula_sum,
    render_markdown,
    variable_graph_from_system,
)
from policybench.spec import get_benchmark_spec

RULES = {rule.id: rule for rule in QUALIFIER_RULES}
SPECS = {
    output.id: output
    for output in get_benchmark_spec("policybench").outputs_for_country("us", None)
}


def add(*args):  # The name the formulas below call; never run.
    raise NotImplementedError


def sum_contained_tax_units(*args):  # Never run.
    raise NotImplementedError


def component(name, label="", documentation="", sign=1, **kwargs) -> Component:
    defaults = {
        "entity": "person",
        "path": ("root", name),
        "kind": "leaf",
    }
    defaults.update(kwargs)
    return Component(
        name=name, label=label, documentation=documentation, sign=sign, **defaults
    )


def info(name, entity="tax_unit", **kwargs) -> VariableInfo:
    return VariableInfo(name=name, entity=entity, **kwargs)


# ----- component_tree ----- #


def test_tree_signs_multiply_through_nested_subtracts():
    graph = {
        "root": info("root", adds=("a",), subtracts=("credits",)),
        "a": info("a", has_formula=True),
        "credits": info("credits", adds=("c1",), subtracts=("c2",)),
        "c1": info("c1", has_formula=True),
        "c2": info("c2", has_formula=True),
    }
    tree = component_tree(graph, "root")
    signs = {node["name"]: node["sign"] for node in tree}
    assert signs == {"root": 1, "a": 1, "credits": -1, "c1": -1, "c2": 1}
    assert [node["name"] for node in tree] == ["root", "a", "credits", "c1", "c2"]
    assert tree[0]["kind"] == "root"
    assert tree[2]["kind"] == "intermediate"
    assert {node["leaf_reason"] for node in tree if node["kind"] == "leaf"} == {
        "formula"
    }


def test_tree_stops_at_cycles():
    graph = {
        "a": info("a", adds=("b",)),
        "b": info("b", adds=("a", "c")),
        "c": info("c"),
    }
    tree = component_tree(graph, "a")
    assert [(node["name"], node["leaf_reason"]) for node in tree] == [
        ("a", None),
        ("b", None),
        ("a", "cycle"),
        ("c", "input"),
    ]
    assert tree[2]["path"] == ["a", "b", "a"]


def test_tree_leaf_reasons():
    graph = {
        "root": info(
            "root",
            adds=("input_var", "formula_var", "overridden", "not_in_graph"),
        ),
        "input_var": info("input_var"),
        "formula_var": info("formula_var", has_formula=True),
        "overridden": info("overridden", has_formula=True, adds=("x",)),
    }
    reasons = {
        node["name"]: node["leaf_reason"] for node in component_tree(graph, "root")
    }
    assert reasons == {
        "root": None,
        "input_var": "input",
        "formula_var": "formula",
        "overridden": "formula_overrides_adds",
        "not_in_graph": "not_a_variable",
    }


def test_formula_terms_expand_and_take_precedence_over_adds():
    graph = {
        "root": info(
            "root",
            has_formula=True,
            adds=("ignored",),
            formula_adds=("a",),
            formula_subtracts=("b",),
        ),
        "a": info("a"),
        "b": info("b"),
        "ignored": info("ignored"),
    }
    tree = component_tree(graph, "root")
    assert [(node["name"], node["sign"], node["edge"]) for node in tree] == [
        ("root", 1, None),
        ("a", 1, "formula_adds"),
        ("b", -1, "formula_subtracts"),
    ]


def test_tree_of_unknown_root_is_a_single_leaf():
    assert component_tree({}, "nope") == [
        {
            "name": "nope",
            "path": ["nope"],
            "depth": 0,
            "sign": 1,
            "edge": None,
            "via_parameter": None,
            "entity": None,
            "label": "",
            "defined_for": None,
            "kind": "leaf",
            "leaf_reason": "not_a_variable",
        }
    ]


# ----- Formula reading ----- #

INCOME_TAX_SOURCE = """
def formula(tax_unit, period, parameters):
    if parameters(period).gov.contrib.ubi_center.flat_tax.abolish:
        return 0
    else:
        added_components = add(
            tax_unit,
            period,
            ["income_tax_before_credits", "net_investment_income_tax"],
        )
        subtracted_components = add(
            tax_unit, period, ["income_tax_capped_non_refundable_credits"]
        )
        return added_components - subtracted_components
"""


def test_parse_guarded_difference_of_adds():
    assert parse_formula_sum(INCOME_TAX_SOURCE) == (
        ("income_tax_before_credits", "net_investment_income_tax"),
        ("income_tax_capped_non_refundable_credits",),
    )


def test_parse_module_constant_and_skip_guard_without_else():
    source = """
    def formula(tax_unit, period, parameters):
        if parameters(period).gov.contrib.abolish_payroll_tax:
            return 0
        return add(tax_unit, period, COMPONENTS)
    """
    constants = {"COMPONENTS": ["employee_social_security_tax", "x"]}
    assert parse_formula_sum(source, resolve_name=constants.get) == (
        ("employee_social_security_tax", "x"),
        (),
    )
    assert parse_formula_sum(source) is None


def test_parse_parameter_list_and_entity_calls():
    source = """
    def formula(tax_unit, period, parameters):
        p = parameters(period).gov.irs.credits
        refundable = add(tax_unit, period, p.refundable)
        return refundable - tax_unit("clawback", period) + -tax_unit("y", period)
    """
    parameters = {"gov.irs.credits.refundable": ["eitc", "refundable_ctc"]}
    assert parse_formula_sum(source, resolve_parameter=parameters.get) == (
        ("eitc", "refundable_ctc"),
        ("clawback", "y"),
    )


def test_parse_sum_contained_tax_units():
    source = """
    def formula(spm_unit, period, parameters):
        return sum_contained_tax_units("employee_payroll_tax", spm_unit, period)
    """
    assert parse_formula_sum(source) == (("employee_payroll_tax",), ())


@pytest.mark.parametrize(
    "body",
    [
        "return max_(0, add(tax_unit, period, ['a']))",
        "return where(tax_unit('c', period), add(tax_unit, period, ['a']), 0)",
        "return 0.5 * add(tax_unit, period, ['a'])",
        "return add(tax_unit, period, ['a'], options=['divide'])",
        "x = add(tax_unit, period, ['a'])\n    x += 1\n    return x",
        "if tax_unit('c', period):\n        return 1\n    return tax_unit('a', period)",
        "return 0",
        "return add(tax_unit, period, UNKNOWN)",
        "for v in ['a']:\n        pass\n    return tax_unit('a', period)",
    ],
)
def test_parse_rejects_anything_but_a_plain_sum(body):
    source = f"def formula(tax_unit, period, parameters):\n    {body}\n"
    assert parse_formula_sum(source) is None


def test_parse_rejects_text_without_a_function():
    assert parse_formula_sum("lambda tax_unit, period: 0") is None
    assert parse_formula_sum("def broken(:") is None


def test_formula_parameter_paths():
    source = """
    def formula(person, period, parameters):
        p = parameters(period).gov.states.ma.tax.payroll.paid_leave
        rate = p.family_rate + p.medical_rate * p.medical_employee_share
        other = parameters(period).gov.states["or"].tax.payroll.employee_rate
        cap = p.cap[person("filing_status", period)]
        return rate * person("wages", period) + other + cap
    """
    assert formula_parameter_paths(source) == (
        "gov.states.ma.tax.payroll.paid_leave",
        "gov.states.ma.tax.payroll.paid_leave.cap",
        "gov.states.ma.tax.payroll.paid_leave.family_rate",
        "gov.states.ma.tax.payroll.paid_leave.medical_employee_share",
        "gov.states.ma.tax.payroll.paid_leave.medical_rate",
        "gov.states.or.tax.payroll.employee_rate",
    )


# ----- Reading a graph from a system object ----- #

PAYROLL_COMPONENTS = ["employee_social_security_tax", "employee_state_payroll_tax"]


def employee_payroll_formula(tax_unit, period, parameters):
    if parameters(period).gov.contrib.abolish_payroll_tax:
        return 0
    else:
        return add(tax_unit, period, PAYROLL_COMPONENTS)


def paid_leave_formula(person, period, parameters):
    rate = parameters(period).gov.states.mn.paid_leave.employee_rate
    return rate * person("wages", period)


def _sum_of_variables(variables):
    def sum_of_variables(entity, period, parameters):
        return variables  # never run; the closure is what the reader uses

    return sum_of_variables


class FakeParameter:
    def __init__(self, values, description=None, label=None):
        self.values = values
        self.description = description
        self.metadata = {"label": label} if label else {}

    def __call__(self, instant):
        known = [start for start in self.values if start <= instant]
        return self.values[max(known)]


class FakeNode:
    def __init__(self, children, description=None):
        self.children = children
        self.description = description
        self.metadata = {}


class FakeVariable:
    def __init__(
        self,
        name,
        entity="tax_unit",
        adds=None,
        subtracts=None,
        formulas=None,
        label=None,
        documentation=None,
        defined_for=None,
    ):
        self.name = name
        self.entity = SimpleNamespace(key=entity)
        self.adds = adds
        self.subtracts = subtracts
        self.formulas = formulas or {}
        self.label = label
        self.documentation = documentation
        self.defined_for = defined_for
        self.definition_period = "year"

    def get_formula(self, instant):
        starts = [start for start in self.formulas if start <= instant]
        return self.formulas[max(starts)] if starts else None


def fake_system():
    parameters = FakeNode(
        {
            "gov": FakeNode(
                {
                    "household": FakeNode(
                        {
                            "state_list": FakeParameter(
                                {
                                    "2015-01-01": ["old_state_tax"],
                                    "2026-01-01": ["mn_tax", "nyc_tax"],
                                }
                            )
                        }
                    ),
                    "states": FakeNode(
                        {
                            "mn": FakeNode(
                                {
                                    "paid_leave": FakeNode(
                                        {
                                            "employee_rate": FakeParameter(
                                                {"2026-01-01": 0.0044},
                                                description="Employee rate, "
                                                "assuming the employer withholds "
                                                "the maximum permitted employee "
                                                "share.",
                                            )
                                        }
                                    )
                                }
                            )
                        }
                    ),
                }
            )
        }
    )
    variables = {
        "state_tax": FakeVariable("state_tax", adds="gov.household.state_list"),
        "mn_tax": FakeVariable("mn_tax", formulas={"2020-01-01": paid_leave_formula}),
        "nyc_tax": FakeVariable(
            "nyc_tax", label="NYC income tax", defined_for="in_nyc"
        ),
        "old_state_tax": FakeVariable("old_state_tax"),
        "employee_payroll_tax": FakeVariable(
            "employee_payroll_tax", formulas={"2015-01-01": employee_payroll_formula}
        ),
        "employee_social_security_tax": FakeVariable(
            "employee_social_security_tax", entity="person"
        ),
        "employee_state_payroll_tax": FakeVariable(
            "employee_state_payroll_tax", adds=["mn_paid_leave"]
        ),
        "mn_paid_leave": FakeVariable(
            "mn_paid_leave",
            entity="person",
            formulas={"2026-01-01": paid_leave_formula},
            documentation="Employee-side  Minnesota\n Paid Leave contribution.",
        ),
        "legacy_sum": FakeVariable(
            "legacy_sum", formulas={"2010-01-01": _sum_of_variables(["a", "b"])}
        ),
        "a": FakeVariable("a"),
        "b": FakeVariable("b"),
        "unreached": FakeVariable("unreached"),
    }
    return SimpleNamespace(variables=variables, parameters=parameters)


def test_graph_resolves_parameter_list_adds_at_the_instant():
    system = fake_system()
    graph = variable_graph_from_system(system, "2026-01-01", roots=["state_tax"])
    assert graph["state_tax"].adds == ("mn_tax", "nyc_tax")
    assert graph["state_tax"].adds_parameter == "gov.household.state_list"
    assert graph["nyc_tax"].defined_for == "in_nyc"
    assert set(graph) == {"state_tax", "mn_tax", "nyc_tax"}
    earlier = variable_graph_from_system(system, "2020-06-01", roots=["state_tax"])
    assert earlier["state_tax"].adds == ("old_state_tax",)
    tree = component_tree(graph, "state_tax")
    assert [node["via_parameter"] for node in tree] == [
        None,
        "gov.household.state_list",
        "gov.household.state_list",
    ]


def test_graph_reads_formula_sums_documentation_and_parameter_text():
    system = fake_system()
    graph = variable_graph_from_system(
        system, "2026-01-01", roots=["employee_payroll_tax", "legacy_sum"]
    )
    payroll = graph["employee_payroll_tax"]
    assert payroll.has_formula
    assert payroll.formula_adds == tuple(PAYROLL_COMPONENTS)
    assert graph["employee_state_payroll_tax"].adds == ("mn_paid_leave",)
    leave = graph["mn_paid_leave"]
    assert leave.documentation == "Employee-side Minnesota Paid Leave contribution."
    assert "maximum permitted employee share" in leave.parameter_text
    assert leave.formula_adds == ()
    assert graph["legacy_sum"].formula_adds == ("a", "b")
    assert "unreached" not in graph
    # Before its formula starts, a variable with only a formula is an input.
    early = variable_graph_from_system(system, "2025-01-01", roots=["mn_paid_leave"])
    assert not early["mn_paid_leave"].has_formula


def test_graph_without_roots_reads_every_variable():
    system = fake_system()
    assert set(variable_graph_from_system(system, "2026-01-01")) == set(
        system.variables
    )


# ----- Qualifier rules: detection on the real definitions ----- #

EXPECTED_QUALIFIERS = {
    "payroll_tax": {
        "employee_side",
        "mandatory",
        "excludes_self_employment_tax",
        "household_scope",
    },
    "self_employment_tax": {
        "excludes_additional_medicare_tax",
        "excludes_employee_payroll_taxes",
    },
    "federal_refundable_credits": {"excludes_premium_tax_credit"},
    "federal_income_tax_before_refundable_credits": {
        "before_refundable_credits",
        "after_nonrefundable_credits",
    },
    "state_income_tax_before_refundable_credits": {
        "excludes_local_tax",
        "state_scope",
        "before_refundable_credits",
        "after_nonrefundable_credits",
    },
    "state_refundable_credits": {"state_scope"},
    "snap": set(),
    "free_school_meals_eligible": {"household_scope"},
}


@pytest.mark.parametrize("output_id", sorted(EXPECTED_QUALIFIERS))
def test_rules_detect_the_qualifiers_in_the_real_definitions(output_id):
    definition = SPECS[output_id].prompt
    detected = {rule.id for rule in QUALIFIER_RULES if rule.detects(definition)}
    assert detected == EXPECTED_QUALIFIERS[output_id]


def test_household_prompt_makes_every_output_household_scoped():
    rule = RULES["household_scope"]
    assert not rule.detects(SPECS["snap"].prompt)
    assert rule.detects(SPECS["snap"].prompt, household_prompt=True)
    assert not RULES["mandatory"].detects("snap", household_prompt=True)


# ----- Qualifier rules: component tests ----- #


@pytest.mark.parametrize(
    ("rule_id", "hit", "miss"),
    [
        (
            "employee_side",
            component("employer_social_security_tax"),
            component("employee_social_security_tax"),
        ),
        ("employee_side", component("futa"), component("additional_medicare_tax")),
        (
            "excludes_self_employment_tax",
            component("self_employment_social_security_tax"),
            component("additional_medicare_tax", label="Additional Medicare Tax"),
        ),
        (
            "excludes_additional_medicare_tax",
            component("additional_medicare_tax", label="Additional Medicare Tax"),
            component("self_employment_medicare_tax"),
        ),
        (
            "excludes_employee_payroll_taxes",
            component("employee_medicare_tax"),
            component("self_employment_medicare_tax"),
        ),
        (
            "excludes_premium_tax_credit",
            component("aca_ptc"),
            component("eitc", label="Earned Income Tax Credit"),
        ),
        (
            "excludes_premium_tax_credit",
            component("assigned", label="Premium Tax Credit"),
            component("refundable_ctc"),
        ),
        (
            "excludes_local_tax",
            component("nyc_income_tax_before_refundable_credits"),
            component("md_income_tax_before_refundable_credits"),
        ),
        (
            "excludes_local_tax",
            component("md_local_income_tax_before_refundable_credits"),
            component("ny_income_tax_before_refundable_credits"),
        ),
        (
            "state_scope",
            component("md_montgomery_eitc", label="Montgomery County, Maryland EITC"),
            component("md_refundable_eitc", label="Maryland refundable EITC"),
        ),
        (
            "excludes_local_tax",
            component("pa_philadelphia_wage_tax"),
            component("pa_income_tax_before_refundable_credits"),
        ),
        (
            "before_refundable_credits",
            component("refundable_ctc", sign=-1),
            component("refundable_ctc", sign=1),
        ),
        (
            "before_refundable_credits",
            component("eitc", sign=-1),
            component("non_refundable_ctc", sign=-1),
        ),
        (
            "after_nonrefundable_credits",
            component("ms_income_tax_before_credits_unit"),
            component(
                "income_tax_before_credits",
                subtracted_along_path=("income_tax_capped_non_refundable_credits",),
            ),
        ),
        (
            "after_nonrefundable_credits",
            component("xx_income_tax_before_non_refundable_credits"),
            component(
                "va_income_tax_before_refundable_credits",
                label="Virginia income tax before credits",
            ),
        ),
    ],
)
def test_component_rules_hit_and_miss(rule_id, hit, miss):
    rule = RULES[rule_id]
    found = rule.test(hit)
    assert found is not None and found.reason
    assert rule.test(miss) is None


def test_mandatory_rule_reads_engine_text_and_law_classification():
    rule = RULES["mandatory"]
    by_text = rule.test(
        component(
            "mn_employee_paid_leave_contribution",
            documentation="Employee-side Minnesota Paid Leave contribution, assuming "
            "the employer withholds the maximum permitted employee share.",
        )
    )
    assert by_text.evidence == "engine_text"
    assert "maximum permitted employee share" in by_text.reason
    by_parameter = rule.test(
        component(
            "xx_leave",
            parameter_text="Employers may deduct up to half of the premium from wages.",
        )
    )
    assert by_parameter.evidence == "engine_text"
    by_law = rule.test(
        component(
            "co_employee_famli_contribution",
            documentation="Employee-side Colorado FAMLI payroll contribution.",
            law_classification={
                "classification": "optional_employer_pass_through",
                "citation": "C.R.S. 8-13.3-507(5)",
            },
        )
    )
    assert by_law.evidence == "law_classification"
    assert "C.R.S. 8-13.3-507(5)" in by_law.reason
    mandatory = component(
        "ca_employee_state_disability_insurance_contribution",
        documentation="Employee-side California State Disability Insurance "
        "withholding, which funds SDI and Paid Family Leave.",
        law_classification={"classification": "mandatory_employee_withholding"},
    )
    assert rule.test(mandatory) is None


# ----- The report ----- #

PAYROLL_DEFINITION = SPECS["payroll_tax"].prompt


def payroll_graph() -> dict[str, VariableInfo]:
    return {
        "spm_unit_payroll_tax": info(
            "spm_unit_payroll_tax",
            entity="spm_unit",
            has_formula=True,
            formula_adds=("employee_payroll_tax",),
        ),
        "employee_payroll_tax": info(
            "employee_payroll_tax",
            has_formula=True,
            formula_adds=(
                "employee_social_security_tax",
                "employee_medicare_tax",
                "additional_medicare_tax",
                "employee_state_payroll_tax",
            ),
        ),
        "employee_social_security_tax": info(
            "employee_social_security_tax",
            entity="person",
            has_formula=True,
            label="employee-side Social Security tax",
        ),
        "employee_medicare_tax": info(
            "employee_medicare_tax",
            entity="person",
            has_formula=True,
            label="employee-side health insurance payroll tax",
        ),
        "additional_medicare_tax": info(
            "additional_medicare_tax", has_formula=True, label="Additional Medicare Tax"
        ),
        "employee_state_payroll_tax": info(
            "employee_state_payroll_tax",
            adds=("mn_employee_state_payroll_tax", "ca_employee_state_payroll_tax"),
            label="Employee state payroll taxes and contributions",
        ),
        "mn_employee_state_payroll_tax": info(
            "mn_employee_state_payroll_tax",
            entity="person",
            adds=("mn_employee_paid_leave_contribution",),
            defined_for="MN",
            label="Minnesota employee state payroll tax",
        ),
        "mn_employee_paid_leave_contribution": info(
            "mn_employee_paid_leave_contribution",
            entity="person",
            has_formula=True,
            defined_for="MN",
            label="Minnesota employee paid leave contribution",
            documentation="Employee-side Minnesota Paid Leave contribution, "
            "assuming the employer withholds the maximum permitted employee share.",
        ),
        "ca_employee_state_payroll_tax": info(
            "ca_employee_state_payroll_tax",
            entity="person",
            adds=("ca_sdi",),
            label="California employee state payroll tax",
        ),
        "ca_sdi": info(
            "ca_sdi",
            entity="person",
            has_formula=True,
            label="California employee state disability insurance contribution",
        ),
    }


def payroll_values(state: float, federal: float = 1000.0, mn_parent=None) -> dict:
    mn_parent = state if mn_parent is None else mn_parent
    return {
        "spm_unit_payroll_tax": federal + mn_parent,
        "employee_payroll_tax": federal + mn_parent,
        "employee_social_security_tax": federal,
        "employee_medicare_tax": 0.0,
        "additional_medicare_tax": 0.0,
        "employee_state_payroll_tax": mn_parent,
        "mn_employee_state_payroll_tax": mn_parent,
        "mn_employee_paid_leave_contribution": state,
        "ca_employee_state_payroll_tax": 0.0,
        "ca_sdi": 0.0,
    }


PAYROLL_SPEC = {
    "id": "payroll_tax",
    "pe_variable": "spm_unit_payroll_tax",
    "prompt": PAYROLL_DEFINITION,
}


def test_report_lists_material_mandatory_mismatch_with_cells():
    cells = {
        "payroll_tax": [
            {
                "scenario_id": "scenario_032",
                "output_id": "payroll_tax",
                "reference": 2346.10,
                "values": payroll_values(127.60),
            },
            {
                "scenario_id": "scenario_001",
                "output_id": "payroll_tax",
                "reference": 1000.0,
                "values": payroll_values(0.0),
            },
        ]
    }
    report = conformance_report(
        [PAYROLL_SPEC], payroll_graph(), cell_components=cells, household_prompt=True
    )
    [mismatch] = report["mismatches"]
    assert mismatch["rule"] == "mandatory"
    assert mismatch["component"] == "mn_employee_paid_leave_contribution"
    assert mismatch["material"] is True
    assert [cell["scenario_id"] for cell in mismatch["cells"]] == ["scenario_032"]
    assert mismatch["cells"][0]["effect_on_reference"] == pytest.approx(127.60)
    assert mismatch["total_effect_on_references"] == pytest.approx(127.60)
    [output] = report["outputs"]
    checks = {check["rule"]: check["status"] for check in output["rule_checks"]}
    assert checks == {
        "employee_side": "conforms",
        "mandatory": "mismatch",
        "excludes_self_employment_tax": "conforms",
        "household_scope": "not_evaluated",
    }
    assert output["conservation"]["failures"] == []
    assert output["conservation"]["checks"] > 0
    assert output["cells"][0]["nonzero_components"][
        "mn_employee_paid_leave_contribution"
    ] == pytest.approx(127.60)
    assert report["summary"]["material_cells"] == 1
    markdown = render_markdown(report, title="Definition conformance")
    assert "`mn_employee_paid_leave_contribution`" in markdown
    assert "scenario_032 127.60" in markdown


def test_report_materiality_is_false_for_zero_cells_and_unknown_without_cells():
    zero_cells = {
        "payroll_tax": [
            {
                "scenario_id": "s",
                "output_id": "payroll_tax",
                "values": payroll_values(0),
            }
        ]
    }
    report = conformance_report(
        [PAYROLL_SPEC], payroll_graph(), cell_components=zero_cells
    )
    assert report["mismatches"][0]["material"] is False
    static = conformance_report([PAYROLL_SPEC], payroll_graph())
    assert static["mismatches"][0]["material"] is None
    assert "conservation" not in static["outputs"][0]


def test_report_ignores_values_masked_by_a_defined_for_ancestor():
    # The leaf is nonzero but its defined_for parent is 0, so nothing reaches the
    # reference: the engine returns the default wherever defined_for is not positive.
    cells = {
        "payroll_tax": [
            {
                "scenario_id": "s",
                "output_id": "payroll_tax",
                "values": payroll_values(50.0, mn_parent=0.0),
            }
        ]
    }
    report = conformance_report([PAYROLL_SPEC], payroll_graph(), cell_components=cells)
    assert report["mismatches"][0]["material"] is False
    conservation = report["outputs"][0]["conservation"]
    assert conservation["failures"] == []
    assert [item["variable"] for item in conservation["masked_by_defined_for"]] == [
        "mn_employee_state_payroll_tax"
    ]


def test_report_flags_conservation_failures():
    values = payroll_values(0.0)
    values["employee_payroll_tax"] += 7.0
    values["spm_unit_payroll_tax"] += 7.0
    cells = {"payroll_tax": [{"scenario_id": "s", "values": values}]}
    report = conformance_report([PAYROLL_SPEC], payroll_graph(), cell_components=cells)
    failures = report["outputs"][0]["conservation"]["failures"]
    assert [failure["variable"] for failure in failures] == ["employee_payroll_tax"]
    assert report["summary"]["conservation_failures"] == 1


def test_report_uses_law_classification_and_effect_variables():
    graph = payroll_graph()
    law = {
        "ca_sdi": {
            "classification": "optional_employer_pass_through",
            "citation": "hypothetical",
        }
    }
    report = conformance_report([PAYROLL_SPEC], graph, law_classifications=law)
    components = {m["component"]: m["evidence"] for m in report["mismatches"]}
    assert components == {
        "mn_employee_paid_leave_contribution": "engine_text",
        "ca_sdi": "law_classification",
    }
    state_graph = {
        "state_tax": info(
            "state_tax",
            adds=("ms_income_tax_before_credits_unit",),
            adds_parameter="gov.states.household.list",
        ),
        "ms_income_tax_before_credits_unit": info(
            "ms_income_tax_before_credits_unit", has_formula=True
        ),
    }
    spec = {
        "id": "state",
        "pe_variable": "state_tax",
        "prompt": SPECS["state_income_tax_before_refundable_credits"].prompt,
    }
    cells = {
        "state": [
            {
                "scenario_id": "scenario_012",
                "values": {
                    "state_tax": 900.0,
                    "ms_income_tax_before_credits_unit": 900.0,
                    "ms_non_refundable_credits": 25.0,
                },
            }
        ]
    }
    [mismatch] = conformance_report([spec], state_graph, cell_components=cells)[
        "mismatches"
    ]
    assert mismatch["rule"] == "after_nonrefundable_credits"
    assert mismatch["effect_variable"] == "ms_non_refundable_credits"
    assert mismatch["cells"][0]["effect_on_reference"] == pytest.approx(25.0)


def test_definition_silent_lists_material_unnamed_leaves_only():
    graph = {
        "income_tax_before_refundable_credits": info(
            "income_tax_before_refundable_credits",
            has_formula=True,
            formula_adds=("income_tax_before_credits", "net_investment_income_tax"),
            formula_subtracts=("income_tax_capped_non_refundable_credits",),
        ),
        "income_tax_before_credits": info(
            "income_tax_before_credits",
            adds=("income_tax_main_rates",),
            label="income tax before credits",
        ),
        "income_tax_main_rates": info(
            "income_tax_main_rates", has_formula=True, label="Income tax main rates"
        ),
        "net_investment_income_tax": info(
            "net_investment_income_tax",
            has_formula=True,
            label="Net investment income tax",
        ),
        "income_tax_capped_non_refundable_credits": info(
            "income_tax_capped_non_refundable_credits",
            has_formula=True,
            label="non-refundable tax credits",
        ),
    }
    spec = {
        "id": "federal",
        "pe_variable": "income_tax_before_refundable_credits",
        "prompt": SPECS["federal_income_tax_before_refundable_credits"].prompt,
    }
    values = {
        "income_tax_before_refundable_credits": 1100.0,
        "income_tax_before_credits": 1000.0,
        "income_tax_main_rates": 1000.0,
        "net_investment_income_tax": 150.0,
        "income_tax_capped_non_refundable_credits": 50.0,
    }
    report = conformance_report(
        [spec],
        graph,
        cell_components={"federal": [{"scenario_id": "s", "values": values}]},
    )
    assert [item["component"] for item in report["definition_silent"]] == [
        "net_investment_income_tax"
    ]
    assert report["mismatches"] == []
    quiet = dict(values, net_investment_income_tax=0.0)
    quiet["income_tax_before_refundable_credits"] = 950.0
    report = conformance_report(
        [spec],
        graph,
        cell_components={"federal": [{"scenario_id": "s", "values": quiet}]},
    )
    assert report["definition_silent"] == []
    [silent] = report["outputs"][0]["definition_silent"]
    assert silent["material"] is False


def household_record(**overrides) -> dict:
    record = {
        "scenario_id": "scenario_123",
        "person": "child1",
        "earned_income": 45000.0,
        "unearned_income": 0.0,
        "references": {"federal": 5200.24, "payroll_tax": 11194.0},
        "output_deltas": {"federal": 0.0, "payroll_tax": 3474.0},
        "own_return": {
            "required_to_file": True,
            "outputs": {"federal": 3220.0},
        },
    }
    record.update(overrides)
    return record


def test_household_scope_reports_dependent_income_outside_the_tax_unit():
    graph = {"income_tax": info("income_tax", has_formula=True)}
    spec = {
        "id": "federal",
        "pe_variable": "income_tax",
        "prompt": SPECS["federal_income_tax_before_refundable_credits"].prompt,
    }
    report = conformance_report(
        [spec], graph, household_scope=[household_record()], household_prompt=True
    )
    [mismatch] = report["mismatches"]
    assert mismatch["rule"] == "household_scope"
    assert mismatch["own_return_value"] == 3220.0
    assert mismatch["counted_by"] == {"payroll_tax": 3474.0}
    assert mismatch["reference"] == 5200.24
    assert "payroll_tax counts it" in mismatch["reason"]
    assert "filing requirement" in mismatch["reason"]
    markdown = render_markdown(report, title="t")
    assert "| scenario_123 | federal | child1 | 45,000.00 |" in markdown

    # Without the household prompt the federal definition is not household-scoped.
    assert (
        conformance_report([spec], graph, household_scope=[household_record()])[
            "mismatches"
        ]
        == []
    )


@pytest.mark.parametrize(
    ("overrides", "mismatches", "notes"),
    [
        # The output already counts the member's income.
        ({"output_deltas": {"federal": 812.0, "payroll_tax": 3474.0}}, 0, 0),
        # No income at all.
        ({"earned_income": 0.0}, 0, 0),
        # A filing requirement but nothing owed on the member's own return.
        (
            {"own_return": {"required_to_file": True, "outputs": {"federal": 0.0}}},
            0,
            1,
        ),
        # No own-return value for this output: not evaluated.
        ({"own_return": {"required_to_file": True, "outputs": {}}}, 0, 0),
    ],
)
def test_household_scope_negative_cases(overrides, mismatches, notes):
    graph = {"income_tax": info("income_tax", has_formula=True)}
    spec = {"id": "federal", "pe_variable": "income_tax", "prompt": "x"}
    report = conformance_report(
        [spec],
        graph,
        household_scope=[household_record(**overrides)],
        household_prompt=True,
    )
    assert len(report["mismatches"]) == mismatches
    assert len(report["household_scope_notes"]) == notes


def test_household_prompt_phrase_is_in_the_frozen_prompt_builder():
    from policybench import prompts

    source = open(prompts.__file__, encoding="utf-8").read()
    assert HOUSEHOLD_PROMPT_PHRASE in source


# ----- Properties ----- #

NAMES = [f"v{index}" for index in range(6)]


@st.composite
def graphs(draw, acyclic: bool = False):
    size = draw(st.integers(1, len(NAMES)))
    names = NAMES[:size]
    graph = {}
    for index, name in enumerate(names):
        pool = names[index + 1 :] if acyclic else names
        pool = pool + ([] if acyclic else ["missing"])
        kind = draw(st.sampled_from(["input", "adds", "formula", "formula_sum"]))
        children = st.lists(st.sampled_from(pool), max_size=2) if pool else st.just([])
        adds = tuple(draw(children))
        subtracts = tuple(draw(children))
        if kind == "input" or not pool:
            graph[name] = info(name)
        elif kind == "adds":
            graph[name] = info(name, adds=adds, subtracts=subtracts)
        elif kind == "formula":
            graph[name] = info(name, has_formula=True, adds=adds)
        else:
            graph[name] = info(
                name,
                has_formula=True,
                formula_adds=adds,
                formula_subtracts=subtracts,
            )
    return graph


def _dfs_parent(tree, position) -> int:
    """Index of a pre-order node's parent: the nearest earlier node one level up."""
    depth = tree[position]["depth"]
    for earlier in range(position - 1, -1, -1):
        if tree[earlier]["depth"] == depth - 1:
            return earlier
    raise AssertionError("no parent")


@settings(max_examples=200, deadline=None)
@given(graphs())
def test_tree_is_deterministic_and_independent_of_graph_order(graph):
    reordered = dict(reversed(list(graph.items())))
    assert component_tree(graph, "v0") == component_tree(graph, "v0")
    assert component_tree(graph, "v0") == component_tree(reordered, "v0")


@settings(max_examples=200, deadline=None)
@given(graphs())
def test_every_node_is_reached_by_its_path_and_signs_multiply(graph):
    tree = component_tree(graph, "v0")
    assert tree[0]["path"] == ["v0"] and tree[0]["sign"] == 1
    for position, node in enumerate(tree):
        path = node["path"]
        assert path[0] == "v0" and path[-1] == node["name"]
        assert node["depth"] == len(path) - 1
        # A variable repeats on its own path only as a cycle leaf at the end.
        assert len(set(path[:-1])) == len(path) - 1
        assert (node["leaf_reason"] == "cycle") == (node["name"] in path[:-1])
        if node["kind"] == "leaf" and node["leaf_reason"] != "cycle":
            assert node["name"] not in graph or not graph[node["name"]].edges()
        if position == 0:
            continue
        # Every step of the path is an edge of the graph, and the sign is the
        # product of the edge signs from the root down.
        parent = tree[_dfs_parent(tree, position)]
        assert parent["path"] == path[:-1]
        assert parent["kind"] in ("root", "intermediate")
        assert (node["edge"], node["name"]) in graph[parent["name"]].edges()
        product = 1
        current = position
        while current:
            product *= EDGE_SIGNS[tree[current]["edge"]]
            current = _dfs_parent(tree, current)
        assert node["sign"] == product
    # Every edge of every expanded node is walked exactly once per visit.
    for position, node in enumerate(tree):
        if node["kind"] not in ("root", "intermediate"):
            continue
        children = [
            (child["edge"], child["name"])
            for index, child in enumerate(tree)
            if index > position
            and child["depth"] == node["depth"] + 1
            and _dfs_parent(tree, index) == position
        ]
        assert children == list(graph[node["name"]].edges())


@settings(max_examples=200, deadline=None)
@given(
    graphs(acyclic=True),
    st.dictionaries(
        st.sampled_from(NAMES),
        st.floats(-1e4, 1e4, allow_nan=False).map(lambda x: round(x, 2)),
    ),
)
def test_values_built_from_the_sum_conserve_and_leaves_add_up(graph, leaf_values):
    # Fill every leaf from the draw and every expanded node from its parts.
    values = {}

    def value(name):
        if name not in values:
            edges = graph[name].edges() if name in graph else ()
            if edges:
                values[name] = sum(
                    EDGE_SIGNS[edge] * value(child) for edge, child in edges
                )
            else:
                values[name] = leaf_values.get(name, 0.0)
        return values[name]

    for name in graph:
        value(name)
    spec = {"id": "out", "pe_variable": "v0", "prompt": "anything"}
    report = conformance_report(
        [spec], graph, cell_components={"out": [{"scenario_id": "s", "values": values}]}
    )
    assert report["outputs"][0]["conservation"]["failures"] == []
    tree = component_tree(graph, "v0")
    leaf_total = sum(
        node["sign"] * values.get(node["name"], 0.0)
        for node in tree
        if node["kind"] == "leaf"
    )
    assert leaf_total == pytest.approx(values["v0"], abs=1e-6)


DEFINITIONS = [
    SPECS[output_id].prompt
    for output_id in (
        "payroll_tax",
        "self_employment_tax",
        "state_income_tax_before_refundable_credits",
        "federal_refundable_credits",
    )
]


@settings(max_examples=150, deadline=None)
@given(
    graphs(),
    st.sampled_from(DEFINITIONS),
    st.dictionaries(st.sampled_from(NAMES), st.floats(-100, 100, allow_nan=False)),
    st.lists(st.sampled_from(NAMES), max_size=3),
    st.booleans(),
)
def test_an_unrelated_variable_never_changes_the_report(
    graph, definition, values, unrelated_adds, household_prompt
):
    spec = {"id": "out", "pe_variable": "v0", "prompt": definition}
    kwargs = {
        "cell_components": {"out": [{"scenario_id": "s", "values": values}]},
        "household_scope": [household_record()],
        "household_prompt": household_prompt,
    }
    before = conformance_report([spec], graph, **kwargs)
    extended = dict(graph)
    extended["unrelated_employer_local_tax"] = info(
        "unrelated_employer_local_tax",
        adds=tuple(unrelated_adds),
        documentation="optional, assuming the employer withholds",
    )
    after = conformance_report([spec], extended, **kwargs)
    assert json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)
