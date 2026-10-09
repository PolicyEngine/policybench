"""Test every PolicyBench reference against the qualifiers in its output's definition.

For each headline output of the frozen US run, read the policyengine-us variable graph
of the reference system (policyengine-us 2.15.17 plus ``latest_final``: the nine
pre-freeze-law conventions and the Maryland output-scope adapter, built exactly as
reference_audit/2026-10-05/scripts/sweep_salt_withholding.py builds it), walk the sum
behind the output's variable to its leaves (policybench.definition_conformance), and test
each component against the qualifiers the definition carries (benchmark_specs.json
"prompt").

The script first recomputes every scored reference (the 1,928 cells the frozen payload
marks scored) and stops without writing anything unless all of them match
reference_outputs.csv within 1e-3. It then records, per scored cell, the value of every
node of the output's sum (each variable's total over the household's entities), and per
household member who is a tax-unit dependent with income:

* the change in every scored output when that member's income inputs are set to 0 (the
  inputs zeroed are those the engine's gross-income and market-income sums read), and
* that member's own federal and state return: the member alone in a tax unit, as its
  head, with ``claimed_as_dependent_on_another_return`` set, so the engine applies the
  dependent standard deduction (basic_standard_deduction) and its IRC 6012 filing test
  (tax_unit_is_required_to_file).

The "mandatory" qualifier of payroll_tax is tested two ways: against the engine's own
text (variable documentation and the descriptions of the parameters a formula reads)
and against the cited primary-law classification of state paid-leave programs in
PolicyEngine/policybench#194 (commit 049f4f09,
reference_audit/2026-10-05-payroll/program_classification.json), read from git.

Every input is the pass's, staged from git by pass_inputs.py and checked against its
pinned sha256 before anything is computed: the frozen run's payload, references,
reference sidecar and scenarios and the output definitions (benchmark_specs.json) as
release dashboard-data-20260930 (8b4c0ca1) committed them, #194's table, and
latest_final with its parts as 8b4c0ca1 held them (each worker stages its own copy).
The working tree's run, which later releases rewrite, is never read. The run record
names each input by its repository path.

Run from a policybench checkout with the policyengine-us 2.15.17 venv (the checkout
needs 8b4c0ca1 and 049f4f09 in its history):

  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=<checkout> \\
    <triage>/.venv-pe21517/bin/python \\
    reference_audit/2026-10-05-reference-adversary/scripts/definition_conformance.py \\
      --out-dir reference_audit/2026-10-05-reference-adversary/verification
"""

from __future__ import annotations

import argparse
import atexit
import copy
import gzip
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pass_inputs  # noqa: E402  (the pass's pinned inputs, beside this script)

ROOT = Path(__file__).resolve().parents[3]
# The frozen run's files main reads, staged from git.
RUN_FILES = (
    "data.json.gz",
    "reference_outputs.csv",
    "reference_outputs.csv.meta.json",
    "scenarios.csv",
)
YEAR = 2026
PERIOD = str(YEAR)
INSTANT = "2026-01-01"
REPRODUCE_TOLERANCE = 1e-3
TOLERANCE = 0.005
# sweep.py's rename for the 1.755.4 harness; sweep_latest.py kept it on 2.15.17.
RENAME = {"partnership_se_income": "partnership_self_employment_net_earnings"}
LAW_SOURCE = (
    f"PolicyEngine/policybench#194 @ {pass_inputs.LAW_COMMIT[:8]}:"
    f"{pass_inputs.LAW_PATH}"
)
# Gross income sources the engine counts as earned (irs_gross_income reads
# irs_employment_income, itself max(0, employment_income - pre_tax_contributions)).
EARNED_SOURCES = (
    "irs_employment_income",
    "self_employment_income",
    "sstb_self_employment_income",
)
OWN_RETURN_EXTRAS = (
    "tax_unit_is_required_to_file",
    "head_is_dependent_elsewhere",
    "filing_status",
    "irs_gross_income",
    "adjusted_gross_income",
    "standard_deduction",
    "basic_standard_deduction",
    "taxable_income",
)
PERSON_DIAGNOSTICS = (
    "is_tax_unit_dependent",
    "earned_income",
    "market_income",
    "irs_gross_income",
    "employee_social_security_tax",
    "employee_medicare_tax",
)

_SYSTEM = None
# The directory this process's reference system was built from.
_FIX_DIR = None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assemble_fixes() -> Path:
    """latest_final and its parts, plus the sales tax table the IRS module reads,
    staged from git (pass_inputs.FIXES_SHA256)."""
    global _FIX_DIR
    target = Path(tempfile.mkdtemp(prefix="definition_conformance_fixes_"))
    _FIX_DIR = pass_inputs.stage_fixes(target)
    return _FIX_DIR


def stage_inputs(target: Path) -> Path:
    """Stage what main reads besides the engine: the run's files under ``run/``, the
    output definitions and #194's law table, each refused unless it matches its pin."""
    pass_inputs.stage_run(target / "run", RUN_FILES)
    pass_inputs.git_input(
        pass_inputs.PASS_COMMIT,
        pass_inputs.SPECS_PATH,
        pass_inputs.SPECS_SHA256,
        target / Path(pass_inputs.SPECS_PATH).name,
    )
    pass_inputs.git_input(
        pass_inputs.LAW_COMMIT,
        pass_inputs.LAW_PATH,
        pass_inputs.LAW_SHA256,
        target / Path(pass_inputs.LAW_PATH).name,
    )
    return target


def _load_reform(fix_dir: Path):
    path = fix_dir / "latest_final.py"
    spec = importlib.util.spec_from_file_location("latest_final", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["latest_final"] = module
    spec.loader.exec_module(module)
    return module.reform


def _system():
    global _SYSTEM
    if _SYSTEM is None:
        from policyengine_us import CountryTaxBenefitSystem

        _SYSTEM = CountryTaxBenefitSystem(reform=_load_reform(_assemble_fixes()))
    return _SYSTEM


def build_situation(scenario) -> dict:
    situation = scenario.to_pe_household()
    for person in situation["people"].values():
        for old, new in RENAME.items():
            if old in person:
                person[new] = person.pop(old)
    return situation


def _simulation(situation: dict):
    from policyengine_us import Simulation

    return Simulation(tax_benefit_system=_system(), situation=situation)


def _total(sim, variable: str) -> float:
    return float(np.sum(sim.calculate(variable, YEAR)))


def _outputs(sim, scenario, output_ids) -> dict[str, float]:
    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output

    values = {}
    for output_id in output_ids:
        pe_variable = _pe_variable_for_output(output_id, "us")
        values[output_id] = float(
            _extract_person_value(sim.calculate(pe_variable, YEAR), scenario, output_id)
        )
    return values


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def own_return_situation(situation: dict, person: str) -> dict:
    """The member alone, as head of a tax unit, claimed as a dependent elsewhere."""
    data = copy.deepcopy(situation["people"][person])
    data["is_tax_unit_head"] = {PERIOD: True}
    data["is_tax_unit_spouse"] = {PERIOD: False}
    data["claimed_as_dependent_on_another_return"] = {PERIOD: True}
    household = {
        "members": [person],
        "state_code": copy.deepcopy(situation["households"]["household"]["state_code"]),
    }
    return {
        "people": {person: data},
        "marital_units": {"marital_unit": {"members": [person]}},
        "tax_units": {"tax_unit": {"members": [person]}},
        "spm_units": {"spm_unit": {"members": [person]}},
        "families": {"family": {"members": [person]}},
        "households": {"household": household},
    }


def scenario_cells(job: dict) -> dict:
    """Reference outputs, node values and household-scope records for one household."""
    from policybench.scenarios import scenario_from_dict

    scenario = scenario_from_dict(json.loads(job["scenario_json"]))
    situation = build_situation(scenario)
    sim = _simulation(situation)
    outputs = _outputs(sim, scenario, job["scored"])

    node_values: dict[str, float | None] = {}
    node_errors: dict[str, str] = {}
    for variable in job["node_variables"]:
        try:
            node_values[variable] = _total(sim, variable)
        except Exception as error:  # noqa: BLE001 - recorded, never silently dropped
            node_values[variable] = None
            node_errors[variable] = f"{type(error).__name__}: {error}"

    people = list(situation["people"])
    diagnostics = {
        name: np.asarray(sim.calculate(name, YEAR)) for name in PERSON_DIAGNOSTICS
    }
    sources = {
        source: np.asarray(sim.calculate(source, YEAR))
        for source in job["gross_income_sources"]
    }
    records = []
    without_gross_income = []
    for index, person in enumerate(people):
        if not bool(diagnostics["is_tax_unit_dependent"][index]):
            continue
        gross_parts = {
            source: float(max(0.0, values[index]))
            for source, values in sources.items()
            if values[index] > TOLERANCE
        }
        earned_gross = sum(
            value for source, value in gross_parts.items() if source in EARNED_SOURCES
        )
        unearned_gross = sum(
            value
            for source, value in gross_parts.items()
            if source not in EARNED_SOURCES
        )
        earned = float(diagnostics["earned_income"][index])
        person_inputs = situation["people"][person]
        variables = _system().variables
        monetary_inputs = {
            key: float(value[PERIOD])
            for key, value in person_inputs.items()
            if isinstance(value, dict)
            and _is_number(value.get(PERIOD))
            and value.get(PERIOD)
            and key in variables
            and getattr(variables[key], "unit", None) == "currency-USD"
        }
        if earned <= TOLERANCE and earned_gross + unearned_gross <= TOLERANCE:
            # Income the engine keeps out of federal gross income altogether
            # (SNAP's person-level income sources as the lens): which outputs
            # count it, for information.
            other = {
                key: value
                for key, value in monetary_inputs.items()
                if key in job["other_income_sources"]
            }
            if other:
                counterfactual = copy.deepcopy(situation)
                for key in other:
                    counterfactual["people"][person][key] = {PERIOD: 0.0}
                without = _outputs(_simulation(counterfactual), scenario, job["scored"])
                without_gross_income.append(
                    {
                        "scenario_id": scenario.id,
                        "person": person,
                        "income_inputs_outside_gross_income": other,
                        "output_deltas": {
                            output_id: outputs[output_id] - without[output_id]
                            for output_id in job["scored"]
                            if abs(outputs[output_id] - without[output_id]) > TOLERANCE
                        },
                    }
                )
            continue
        zeroed = {
            key: value
            for key, value in monetary_inputs.items()
            if key in job["income_inputs"]
        }
        counterfactual = copy.deepcopy(situation)
        for key in zeroed:
            counterfactual["people"][person][key] = {PERIOD: 0.0}
        without = _outputs(_simulation(counterfactual), scenario, job["scored"])

        own_sim = _simulation(own_return_situation(situation, person))
        own_outputs = {
            output_id: _total(own_sim, pe_variable)
            for output_id, pe_variable in job["own_return_outputs"].items()
        }
        extras = {}
        for name in OWN_RETURN_EXTRAS:
            values = own_sim.calculate(name, YEAR)
            if name == "filing_status":
                extras[name] = str(values.decode_to_str()[0])
            elif values.dtype == bool:
                extras[name] = bool(values[0])
            else:
                extras[name] = float(np.sum(values))
        records.append(
            {
                "scenario_id": scenario.id,
                "state": scenario.state,
                "person": person,
                "age": float(person_inputs["age"][PERIOD]),
                "is_tax_unit_dependent": True,
                "earned_income": earned,
                "unearned_income": unearned_gross,
                "gross_income_sources": gross_parts,
                "market_income": float(diagnostics["market_income"][index]),
                "irs_gross_income_on_household_return": float(
                    diagnostics["irs_gross_income"][index]
                ),
                "employee_social_security_tax": float(
                    diagnostics["employee_social_security_tax"][index]
                ),
                "employee_medicare_tax": float(
                    diagnostics["employee_medicare_tax"][index]
                ),
                "income_inputs_zeroed": zeroed,
                "other_monetary_inputs": {
                    key: value
                    for key, value in monetary_inputs.items()
                    if key not in zeroed
                },
                "references": outputs,
                "outputs_without_person_income": without,
                "output_deltas": {
                    output_id: outputs[output_id] - without[output_id]
                    for output_id in job["scored"]
                },
                "own_return": {
                    "required_to_file": extras["tax_unit_is_required_to_file"],
                    "outputs": own_outputs,
                    **extras,
                },
            }
        )
    return {
        "scenario_id": scenario.id,
        "state": scenario.state,
        "outputs": outputs,
        "node_values": node_values,
        "node_errors": node_errors,
        "household_scope": records,
        "dependents_with_income_outside_gross_income": without_gross_income,
    }


def law_classifications(path: Path) -> tuple[dict, dict]:
    """Variable -> cited classification, from the payroll audit's staged program table."""
    raw = path.read_bytes()
    table = json.loads(raw)
    classifications = {}
    entries = list(table.get("programs", [])) + list(
        table.get("programs_without_a_benchmark_household", [])
    )
    for entry in entries:
        if "classification" not in entry:
            continue
        for variable in entry.get("engine_variables", []):
            classifications[variable] = {
                "classification": entry["classification"],
                "citation": entry.get("law_citation"),
                "url": entry.get("law_url"),
                "program": entry.get("program"),
                "rule_text": entry.get("employee_share_rule_text"),
                "source": LAW_SOURCE,
            }
    meta = {
        "source": LAW_SOURCE,
        "available": True,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "test": table.get("test"),
        "variables": len(classifications),
    }
    return classifications, meta


def _notes(report: dict, scored: int) -> list[str]:
    """Mechanism notes for the Markdown summary, each tied to source read or run."""
    conservation = [
        output["conservation"]
        for output in report["outputs"]
        if "conservation" in output
    ]
    checks = sum(item["checks"] for item in conservation)
    failures = sum(len(item["failures"]) for item in conservation)
    masked = sum(len(item["masked_by_defined_for"]) for item in conservation)
    state_list = report["run"]["state_income_tax_list"]
    run = report["run"]
    deduction = run["household_scope_method"]["dependent_standard_deduction_2026"]
    by_component = {
        (mismatch["output_id"], mismatch.get("component")): mismatch
        for mismatch in report["mismatches"]
    }
    ms = by_component.get(
        (
            "state_income_tax_before_refundable_credits",
            "ms_income_tax_before_credits_unit",
        )
    )
    notes = [
        f"Baseline: policyengine-us {run['policyengine_us']} with latest_final "
        f"reproduces all {scored} scored references within 1e-3 of "
        "reference_outputs.csv before anything is reported.",
        "policyengine-core 3.32.8 sums `adds` and subtracts `subtracts` only when no "
        "formula applies, reading a string attribute as a parameter list at the "
        "period start (policyengine_core/simulations/simulation.py, "
        "`Simulation._run_formula`); a variable with `defined_for` takes its "
        "default wherever that variable is not positive (`Simulation._calculate`). "
        "Formula sums are read from source, and every expanded node equals the "
        f"signed sum of its parts in every scored cell: {checks} checks, "
        f"{failures} failures, {masked} zeroed by `defined_for`.",
        "payroll_tax is spm_unit_payroll_tax = sum_contained_tax_units("
        "'employee_payroll_tax') (variables/household/expense/tax/"
        "spm_unit_payroll_tax.py); employee_payroll_tax adds "
        "EMPLOYEE_PAYROLL_TAX_COMPONENTS, employee_state_payroll_tax among them "
        "(variables/gov/irs/tax/payroll/employee_payroll_tax.py); `add` sums a "
        "person variable over every member of the group, dependents included "
        "(policyengine_core/commons/formulas.py, `for_each_variable`).",
        "Federal income tax: irs_gross_income multiplies every source by not "
        "is_tax_unit_dependent (variables/gov/irs/income/taxable_income/"
        "adjusted_gross_income/irs_gross_income/irs_gross_income.py), and "
        "is_tax_unit_dependent is every member who is neither head nor spouse "
        "(variables/household/demographic/tax_unit/is_tax_unit_dependent.py). PA "
        "taxable income starts from irs_gross_income (variables/gov/states/pa/tax/"
        "income/taxable_income/pa_total_taxable_income.py). The household-scope "
        "rows measure the same thing directly: removing the dependent's income "
        "leaves the income tax references unchanged and lowers payroll_tax.",
        "Own return: the dependent alone as tax-unit head with "
        "claimed_as_dependent_on_another_return set. basic_standard_deduction "
        "then gives min(standard amount, max(earned income + "
        f"{deduction['gov.irs.deductions.standard.dependent.additional_earned_income']:,.0f}, "
        f"{deduction['gov.irs.deductions.standard.dependent.amount']:,.0f})) "
        "(gov.irs.deductions.standard.dependent.*; the 2026 amount cites "
        "Rev. Proc. 2025-32 p. 18 in its metadata, as does the 2026 single "
        f"amount of {deduction['gov.irs.deductions.standard.amount.SINGLE']:,.0f}); "
        "the filing test is tax_unit_is_required_to_file, the engine's IRC "
        "6012(a)(1) (variables/gov/irs/tax_unit_is_required_to_file.py).",
        "State income tax list (gov.states.household."
        f"state_income_tax_before_refundable_credits): {state_list['entries']} "
        "entries in the reference system. latest_md_local_output_scope removed "
        "md_local_income_tax_before_refundable_credits (present: "
        f"{state_list['md_local_income_tax_before_refundable_credits_present']}); "
        "nyc_income_tax_before_refundable_credits stays in it (present: "
        f"{state_list['nyc_income_tax_before_refundable_credits_present']}).",
        "Mandatory: 2.15.17's own documentation flags the MN, MA, DE, ME and VT "
        "contributions ('assuming the employer withholds the maximum permitted "
        "employee share'). The CO FAMLI and NY PFL/DBL variables and the "
        "parameters they read carry no such wording; they are flagged by the cited "
        f"classification in {LAW_SOURCE}.",
    ]
    if ms is not None:
        notes.append(
            "Mississippi: the state list carries ms_income_tax_before_credits_unit, "
            "which comes before Mississippi's nonrefundable credits (ms_income_tax "
            "subtracts ms_non_refundable_credits from it, variables/gov/states/ms/"
            "tax/income/ms_income_tax.py). Material in scored cells: "
            f"{ms['material']}."
        )
    return notes


def _scored_cells(payload: dict) -> dict[tuple[str, str], float]:
    scored = {}
    for scenario_id, outputs in payload["scenarioPredictions"].items():
        for output_id, models in outputs.items():
            first = next(iter(models.values()))
            if first["scored"]:
                scored[(scenario_id, output_id)] = float(first["groundTruth"])
    return scored


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--scenarios", nargs="*")
    args = parser.parse_args()

    from policybench.definition_conformance import (
        HOUSEHOLD_PROMPT_PHRASE,
        component_tree,
        conformance_report,
        render_markdown,
        variable_graph_from_system,
    )

    started = time.time()
    out_dir = Path(args.out_dir)
    staged = Path(tempfile.mkdtemp(prefix="definition_conformance_inputs_"))
    atexit.register(shutil.rmtree, staged, True)
    stage_inputs(staged)
    run = staged / "run"
    specs_path = staged / Path(pass_inputs.SPECS_PATH).name
    payload = json.loads(gzip.decompress((run / "data.json.gz").read_bytes()))
    meta = json.loads((run / "reference_outputs.csv.meta.json").read_text())
    programs = list(meta["programs"])
    specs = [
        spec
        for spec in json.loads(specs_path.read_text())["specs"]["policybench"][
            "countries"
        ]["us"]
        if spec["id"] in programs
    ]
    reference = pd.read_csv(run / "reference_outputs.csv")
    indexed = reference.set_index(["scenario_id", "variable"])["value"]
    scored = _scored_cells(payload)
    if args.scenarios:
        scored = {
            key: value for key, value in scored.items() if key[0] in args.scenarios
        }
    payload_vs_csv = [
        key
        for key, value in scored.items()
        if abs(value - float(indexed[key])) > REPRODUCE_TOLERANCE
    ]
    if payload_vs_csv:
        raise SystemExit(f"payload groundTruth differs from the CSV: {payload_vs_csv}")
    household_prompt = all(
        HOUSEHOLD_PROMPT_PHRASE in scenario["prompt"]["tool"]
        and HOUSEHOLD_PROMPT_PHRASE in scenario["prompt"]["json"]
        for scenario in payload["scenarios"].values()
    )

    system = _system()
    graph = variable_graph_from_system(
        system, INSTANT, roots=[spec["pe_variable"] for spec in specs]
    )
    laws, law_meta = law_classifications(staged / Path(pass_inputs.LAW_PATH).name)

    # A first, cell-free pass names the variables whose values measure a rule's
    # effect when that is not the component itself.
    static = conformance_report(
        specs, graph, household_prompt=household_prompt, law_classifications=laws
    )
    effect_variables = sorted(
        {
            mismatch["effect_variable"]
            for mismatch in static["mismatches"]
            if mismatch["effect_variable"] != mismatch["component"]
            and mismatch["effect_variable"] in system.variables
        }
    )
    amount_specs = [spec for spec in specs if spec["metric_type"] == "amount"]
    node_variables = sorted(
        {
            node["name"]
            for spec in amount_specs
            for node in component_tree(graph, spec["pe_variable"])
            if node["name"] in system.variables
        }
        | set(effect_variables)
    )
    gross_income_sources = list(system.parameters.gov.irs.gross_income.sources(INSTANT))
    market_income_sources = list(
        system.parameters.gov.household.market_income_sources(INSTANT)
    )
    income_graph = variable_graph_from_system(
        system,
        INSTANT,
        roots=gross_income_sources + market_income_sources + ["earned_income"],
    )
    # irs_employment_income's formula reads employment_income without summing it,
    # so the sum walk stops there; name the input explicitly.
    income_inputs = sorted(
        set(income_graph)
        | {"employment_income"}
        | {f"{name}_before_lsr" for name in income_graph}
    )
    other_income_sources = sorted(
        set(system.parameters.gov.usda.snap.income.sources.earned(INSTANT))
        | set(system.parameters.gov.usda.snap.income.sources.unearned(INSTANT))
    )
    own_return_outputs = {
        spec["id"]: spec["pe_variable"]
        for spec in amount_specs
        if graph[spec["pe_variable"]].entity == "tax_unit"
    }

    scenarios = pd.read_csv(run / "scenarios.csv")
    scored_by_scenario: dict[str, list[str]] = {}
    for scenario_id, output_id in scored:
        scored_by_scenario.setdefault(scenario_id, []).append(output_id)
    jobs = [
        {
            "scenario_json": row["scenario_json"],
            "scored": sorted(scored_by_scenario[row["scenario_id"]]),
            "node_variables": node_variables,
            "gross_income_sources": gross_income_sources,
            "income_inputs": income_inputs,
            "other_income_sources": other_income_sources,
            "own_return_outputs": own_return_outputs,
        }
        for _, row in scenarios.iterrows()
        if row["scenario_id"] in scored_by_scenario
    ]
    engine = version("policyengine-us")
    core = version("policyengine-core")
    print(
        f"policyengine-us {engine}, policyengine-core {core}; {len(jobs)} households, "
        f"{len(scored)} scored cells, {len(node_variables)} node variables",
        flush=True,
    )
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(scenario_cells, jobs))
    results.sort(key=lambda result: result["scenario_id"])
    by_scenario = {result["scenario_id"]: result for result in results}

    differences = []
    for (scenario_id, output_id), _ in sorted(scored.items()):
        value = by_scenario[scenario_id]["outputs"][output_id]
        ref = float(indexed[(scenario_id, output_id)])
        if abs(value - ref) > REPRODUCE_TOLERANCE:
            differences.append((scenario_id, output_id, ref, value))
    if differences:
        for difference in differences:
            print("does not reproduce:", difference)
        raise SystemExit(
            f"{len(differences)} of {len(scored)} scored references do not reproduce; "
            "nothing written"
        )
    print(f"baseline reproduces all {len(scored)} scored references", flush=True)

    cell_components = {}
    for spec in amount_specs:
        cells = []
        for scenario_id in sorted(by_scenario):
            if (scenario_id, spec["id"]) not in scored:
                continue
            cells.append(
                {
                    "scenario_id": scenario_id,
                    "output_id": spec["id"],
                    "reference": float(indexed[(scenario_id, spec["id"])]),
                    "values": by_scenario[scenario_id]["node_values"],
                }
            )
        cell_components[spec["id"]] = cells
    household_scope = [
        record for result in results for record in result["household_scope"]
    ]
    report = conformance_report(
        specs,
        graph,
        cell_components=cell_components,
        household_scope=household_scope,
        household_prompt=household_prompt,
        law_classifications=laws,
    )

    state_list = list(
        system.parameters.gov.states.household.state_income_tax_before_refundable_credits(
            INSTANT
        )
    )
    script = Path(__file__).resolve()
    report["run"] = {
        "script": str(script.relative_to(ROOT)),
        "script_sha256": _sha256(script),
        "module_sha256": _sha256(ROOT / "policybench/definition_conformance.py"),
        "policyengine_us": engine,
        "policyengine_core": core,
        "reference_system": "policyengine-us 2.15.17 + latest_final "
        "(reference_audit/2026-09-28/fixes)",
        "fixes_sha256": {
            path: _sha256(_FIX_DIR / Path(path).name)
            for path in pass_inputs.FIXES_SHA256
        },
        "instant": INSTANT,
        "payload": f"{pass_inputs.RUN_PATH}/data.json.gz",
        "payload_sha256": _sha256(run / "data.json.gz"),
        "reference_outputs_sha256": _sha256(run / "reference_outputs.csv"),
        "scenarios_sha256": _sha256(run / "scenarios.csv"),
        "benchmark_specs_sha256": _sha256(specs_path),
        "household_prompt_phrase": HOUSEHOLD_PROMPT_PHRASE,
        "household_prompt_in_every_scenario": household_prompt,
        "reproduction": {
            "scored_cells": len(scored),
            "tolerance": REPRODUCE_TOLERANCE,
            "differences": len(differences),
        },
        "node_variables": len(node_variables),
        "node_errors": {
            result["scenario_id"]: result["node_errors"]
            for result in results
            if result["node_errors"]
        },
        "effect_variables": effect_variables,
        "law_classification": law_meta,
        "household_scope_method": {
            "income_inputs_zeroed_from": "gov.irs.gross_income.sources, "
            "gov.household.market_income_sources, earned_income and their sums, "
            "plus employment_income",
            "own_return": "the member alone as head of a tax unit with "
            "claimed_as_dependent_on_another_return = true",
            "gross_income_sources": gross_income_sources,
            "dependent_standard_deduction_2026": {
                "gov.irs.deductions.standard.dependent.amount": float(
                    system.parameters.gov.irs.deductions.standard.dependent.amount(
                        INSTANT
                    )
                ),
                "gov.irs.deductions.standard.dependent.additional_earned_income": (
                    float(
                        system.parameters.gov.irs.deductions.standard.dependent.additional_earned_income(
                            INSTANT
                        )
                    )
                ),
                "gov.irs.deductions.standard.amount.SINGLE": float(
                    system.parameters.gov.irs.deductions.standard.amount.SINGLE(INSTANT)
                ),
            },
            "records": len(household_scope),
            "dependents_with_income_outside_gross_income": [
                item
                for result in results
                for item in result["dependents_with_income_outside_gross_income"]
            ],
            "other_income_lens": "gov.usda.snap.income.sources.earned and .unearned",
            "filing_requirement": "tax_unit_is_required_to_file on the member's own "
            "return (policyengine_us/variables/gov/irs/tax_unit_is_required_to_file.py,"
            " IRC 6012(a)(1)): gross income above the standard deduction plus the "
            "exemption amount (0 while suspended), or unearned income above 500 plus "
            "the additional standard deduction",
        },
        "state_income_tax_list": {
            "parameter": "gov.states.household.state_income_tax_before_refundable_credits",
            "entries": len(state_list),
            "md_local_income_tax_before_refundable_credits_present": (
                "md_local_income_tax_before_refundable_credits" in state_list
            ),
            "nyc_income_tax_before_refundable_credits_present": (
                "nyc_income_tax_before_refundable_credits" in state_list
            ),
        },
        "seconds": round(time.time() - started, 1),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "definition_conformance.json").write_text(
        json.dumps(report, indent=1, sort_keys=True, default=float) + "\n"
    )
    markdown = render_markdown(
        report, title="Definition conformance", notes=_notes(report, len(scored))
    )
    (out_dir / "definition_conformance.md").write_text(markdown)
    summary = report["summary"]
    print(json.dumps(summary, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
