"""Build the reference-exclusion and adjudication records from the 2026-09-22 triage.

Inputs:
  root_causes.json         per root cause: class, defect, law, correct rule, upstream
  sweep/out/<fix>.csv      verified sweeps (moved = |delta| > $1 or a flipped flag)
  verdicts.json            the per-case triage verdicts for the 25 flagged cases
  <annotations dir>        the final (post-judge) row annotations and case notes
  <audit cases dir>        verdict.meta.json sidecars (judge model per case)
  <exclusions.json>        the existing record (kept verbatim; new entries appended)
  <adjudications.json>     the existing record (kept; flagged entries get a verdict)

Writes the two records to --out-dir and prints a summary. Run with the
policyengine-us 1.755.4 triage venv so multi-cause outputs can be recomputed
under their combined fixes:

  cd /Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage
  PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/opus55 \\
    .venv-pe1755/bin/python build_records.py --annotations <dir> --out-dir records/
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "sweep"))
from sweep import BUNDLE, YEAR, build_situation  # noqa: E402

from policybench.ground_truth import (  # noqa: E402
    _extract_person_value,
    _pe_variable_for_output,
)
from policybench.scenarios import scenario_from_dict  # noqa: E402

DECIDED_ON = "2026-09-22"
ENGINE = "policyengine-us 1.755.4"
AUDIT_CASES = Path(
    "/Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit/audit/cases"
)
# The fix module whose sweep defines each root cause's moved set and values: the
# independently verified v2 modules (sweep/verify reports, 2026-09-22). r10 keeps
# its original module, which encodes the alternative reading of the unlisted input.
SWEEP_FOR = {
    "r01_ira_compensation": "r01_ira_compensation_v2",
    "r02_ira_219g": "r02_ira_219g_v2",
    "r03_estate_income": "r03_estate_income__qbi_false_v2",
    "r04_capital_gain_distributions": "r04_capital_gain_distributions_v2",
    "r05_nj_worker_ui": "r05_nj_worker_ui_v2",
    "r06_wi_act15_before_refundable": "r06_wi_act15_before_refundable_v2",
    "r07_idaho_health_premiums": "r07_idaho_health_premiums_v2",
    "r08_eitc_earned_income_deferrals": "r08_eitc_earned_income_deferrals_v2",
    "r09_ny_rptc_rent_cap": "r09_ny_rptc_rent_cap_v2",
    "r10_wi_homestead_income": "r10_wi_homestead_income",
    "r11_ca_itemized_conformity": "r11_ca_itemized_conformity_v2",
    "r14_unlisted_weekly_hours_v2": "r14_unlisted_weekly_hours_v2_v2",
    "r15_snap_mortgage_interest": "r15_snap_mortgage_interest_v2",
    "r16_survivor_benefits_federal": "r16_survivor_benefits_federal_v2",
    "r17_caleitc_agi_comparison": "r17_caleitc_agi_comparison",
    "r20_adult_dependent_child": "r067_adult_dependent_relationship",
    "r21_adult_dependent_nonchild": "r067_adult_dependent_nonchild",
    "r22_ma_part_a_loss_offset": "ma_part_a_loss_offset",
    "r23_ma_interest_source": "ma_part_a_ordinary_interest",
    "r24_disability_benefits_taxability": "r24_disability_benefits_taxable",
    "r25_niit_in_federal_output": "r25_niit_excluded",
}
REASON = {
    "engine_defect": "reference_engine_defect",
    "unlisted_input": "reference_depends_on_unlisted_input",
    "later_law": "reference_law_published_after_freeze",
}
ADJUDICATED_SOURCE = {
    "engine_defect": "reference_engine_defect",
    "unlisted_input": "prompt_ambiguity",
    "later_law": "reference_later_law",
}
# Precedence when one output moves under several root causes: an engine
# defect makes the frozen reference wrong on the stated facts, which settles
# the exclusion; an unlisted input comes next; later-published law last.
PRECEDENCE = ("engine_defect", "unlisted_input", "later_law")

# The four flagged references the triage affirmed. Reasoning is the case's
# verdict in one or two sentences; the basis is the law it rests on.
AFFIRMED = {
    ("scenario_028", "child3_chip_eligible"): {
        "subtype": "health_coverage",
        "basis": "42 U.S.C. 1397jj(b)(1)(C); 42 CFR 457.310(b)(2)(ii); Pennsylvania CHIP state plan 4.1.7",
        "reasoning": (
            "Child 3 has employer-sponsored group coverage, which bars CHIP; the "
            "household's income passes Pennsylvania's CHIP limit, so the judge's "
            "income-limit hypothesis fails."
        ),
    },
    ("scenario_056", "state_refundable_credits"): {
        "subtype": "credit_phaseout",
        "basis": "N.J.S.A. 54A:4-7(a)(4); Rev. Proc. 2025-32",
        "reasoning": (
            "New Jersey bases the earned income credit for filers 18 and older who "
            "fail only the federal age test on the federal maximum credit for "
            "filers without a qualifying child, and pays it as a flat yearly "
            "amount: 40% of the 2026 $664 maximum is $265.60. The judge's "
            "phase-in reading fails."
        ),
    },
    ("scenario_086", "federal_income_tax_before_refundable_credits"): {
        "subtype": "taxable_income_or_deductions",
        "basis": "26 U.S.C. 62(a)(2)(D), 62(d)(3); Rev. Proc. 2025-32 section 3.12",
        "reasoning": (
            "The 2026 educator expense cap is $350, so the head's $337.50 is fully "
            "deductible; the judge's $300 cap is not the law."
        ),
    },
    ("scenario_076", "state_income_tax_before_refundable_credits"): {
        "subtype": "state_local_rule",
        "basis": "Idaho Code 63-3029L (taxable years 2018 through 2025); Idaho Administrative Bulletin, July 1, 2026, Docket 35-0101-2601",
        "reasoning": (
            "Idaho's $205 child tax credit applies only to taxable years beginning "
            "in 2018 through 2025, so it does not reduce 2026 tax; the judge's "
            "missing-credit hypothesis fails. The reference applies the Idaho "
            "zero-rate threshold held at its published 2025 amount."
        ),
    },
    ("scenario_118", "state_refundable_credits"): {
        "subtype": "state_local_rule",
        "basis": "N.Y. Tax Law 606(e) as amended by Part RR of Chapter 59 of the Laws of 2025",
        "reasoning": (
            "From 2025 New York keys the real property tax credit to federal AGI and "
            "a flat table; with federal AGI of $0 and property tax above 3.5% of "
            "it, a filer 65 or older receives $375. The judge applied the repealed "
            "household-gross-income rule."
        ),
    },
}


def load_fix(fix_id: str):
    path = HERE / "sweep" / "fixes" / f"{fix_id}.py"
    spec = importlib.util.spec_from_file_location(f"fix_{fix_id}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "reform", None), getattr(module, "patch", None)


def flatten(reform) -> list:
    if reform is None:
        return []
    if isinstance(reform, (tuple, list)):
        return [r for item in reform for r in flatten(item)]
    return [reform]


def combined_value(scenario_id: str, variable: str, fixes: list[str]) -> float:
    """Recompute one output with every listed fix module applied together."""
    from policyengine_us import CountryTaxBenefitSystem, Simulation

    reforms, patches = [], []
    for fix in fixes:
        reform, patch = load_fix(fix)
        reforms.extend(flatten(reform))
        if patch is not None:
            patches.append(patch)
    scenarios = pd.read_csv(BUNDLE / "scenarios.csv")
    row = scenarios.loc[scenarios["scenario_id"] == scenario_id]
    scenario = scenario_from_dict(json.loads(row["scenario_json"].iloc[0]))
    situation = build_situation(scenario)
    for patch in patches:
        situation = patch(copy.deepcopy(situation), scenario)
    system = CountryTaxBenefitSystem(reform=tuple(reforms)) if reforms else None
    sim = (
        Simulation(tax_benefit_system=system, situation=situation)
        if system is not None
        else Simulation(situation=situation)
    )
    pe_variable = _pe_variable_for_output(variable, "us")
    return float(
        _extract_person_value(sim.calculate(pe_variable, YEAR), scenario, variable)
    )


PENDING_JUDGE: list[str] = []


def judge_model_for(scenario_id: str, variable: str) -> str:
    meta = AUDIT_CASES / f"us__{scenario_id}__{variable}" / "verdict.meta.json"
    if not meta.exists():
        # The case awaits a re-judge; the final build runs after judging and refuses this.
        PENDING_JUDGE.append(f"{scenario_id}:{variable}")
        return "pending"
    reported = json.loads(meta.read_text()).get("judge_model_reported") or []
    models = [m for m in reported if "haiku" not in m] or reported
    return models[-1] if models else "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--exclusions", type=Path, default=BUNDLE / "reference_exclusions.json")
    parser.add_argument("--adjudications", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--allow-pending-judge", action="store_true")
    args = parser.parse_args()
    adjudications_path = args.adjudications or args.annotations / "us_adjudications.json"

    causes = json.loads((HERE / "root_causes.json").read_text())
    exclusions_doc = json.loads(args.exclusions.read_text())
    existing = {(e["scenario_id"], e["variable"]) for e in exclusions_doc["exclusions"]}
    cases = pd.read_csv(args.annotations / "us_case_notes.csv")
    case_index = cases.set_index(["scenario_id", "variable"])

    flagged = set(
        map(
            tuple,
            cases.loc[
                cases["reference_suspect"].astype(str).str.lower() == "true",
                ["scenario_id", "variable"],
            ].values,
        )
    )
    # The wave's first Opus 5.5 pass flagged 25 references; re-judging a case after
    # GPT-6 rows joined it can drop a flag already adjudicated. A flag the wave
    # raised stays recorded as raised.
    first_pass = HERE / "flagged_sept22_first_pass.json"
    if first_pass.exists():
        flagged |= {tuple(k.split(":")) for k in json.loads(first_pass.read_text())}

    # 1. Every moved output and the root causes that move it.
    moved: dict[tuple[str, str], dict] = {}
    for cause, fix in SWEEP_FOR.items():
        if causes[cause]["class"] not in PRECEDENCE:
            continue
        not_confirmed = causes[cause].get("not_confirmed", {})
        frame = pd.read_csv(HERE / "sweep" / "out" / f"{fix}.csv")
        for _, r in frame[frame["moved"]].iterrows():
            key = (r["scenario_id"], r["variable"])
            if f"{key[0]}:{key[1]}" in not_confirmed:
                continue
            item = moved.setdefault(key, {"frozen": float(r["frozen"]), "causes": {}})
            item["causes"][cause] = float(r["recomputed"])

    # The publication conventions (class "convention"): the references are
    # regenerated under them, and an excluded output's corrected value applies
    # every convention that changes it alongside its own fixes.
    convention_fixes = {}
    for name, cause in causes.items():
        if isinstance(cause, dict) and cause.get("class") == "convention":
            frame = pd.read_csv(HERE / "sweep" / "out" / f"{cause['fix']}.csv")
            for key in map(tuple, frame.loc[frame["delta"].abs() > 1e-6, ["scenario_id", "variable"]].values):
                convention_fixes.setdefault(key, []).append(cause["fix"])

    new_exclusions, new_adjudications, summary = [], [], []
    for key, item in sorted(moved.items()):
        if key in existing:
            continue
        classes = {c: causes[c]["class"] for c in item["causes"]}
        klass = next(k for k in PRECEDENCE if k in classes.values())
        primary = sorted(c for c, k in classes.items() if k == klass)
        # Corrected value: the primary class's fixes applied together, and for an
        # engine defect also any later-law fix on the same output.
        applied = primary + sorted(
            c for c, k in classes.items() if klass == "engine_defect" and k == "later_law"
        )
        fixes = [SWEEP_FOR[c] for c in applied] + convention_fixes.get(key, [])
        if len(fixes) == 1:
            corrected = item["causes"][applied[0]]
        else:
            corrected = combined_value(key[0], key[1], fixes)
        texts = [causes[c] for c in primary]
        others = sorted(set(item["causes"]) - set(primary))
        entry = {
            "scenario_id": key[0],
            "variable": key[1],
            "reason_code": REASON[klass],
            "root_cause": "+".join(primary),
            "alternative_reading": " ".join(t["alternative_reading"] for t in texts),
            "frozen_value": item["frozen"],
            "alternative_value": round(corrected, 6),
            "engine_version": ENGINE,
            "decided_on": DECIDED_ON,
            "decided_by": "developer",
        }
        if klass == "engine_defect":
            entry["defect"] = "; ".join(t["defect"] for t in texts)
            entry["law"] = "; ".join(t["law"] for t in texts)
            entry["upstream"] = "; ".join(t["upstream"] for t in texts if t["upstream"]) or "to be filed"
        elif klass == "unlisted_input":
            entry["unlisted_input"] = " and ".join(t["unlisted_input"] for t in texts)
        else:
            entry["published"] = "; ".join(t["published"] for t in texts)
            entry["law"] = "; ".join(t["law"] for t in texts)
        if klass != "unlisted_input":
            entry.pop("unlisted_input", None)
        else:
            entry.pop("root_cause", None)
        notes = []
        if len(fixes) > 1:
            notes.append("Corrected value applies " + " and ".join(fixes) + " together.")
        if others:
            notes.append(
                "The output also moves under "
                + ", ".join(f"{c} ({causes[c]['class'].replace('_', ' ')})" for c in others)
                + "."
            )
        if notes:
            entry["note"] = " ".join(notes)
        new_exclusions.append(entry)

        case = case_index.loc[key]
        verdict = {"engine_defect": "engine_defect", "unlisted_input": "unlisted_input", "later_law": "later_law"}[klass]
        new_adjudications.append(
            {
                "country": "us",
                "scenario_id": key[0],
                "variable": key[1],
                "judge_model": judge_model_for(*key),
                "judge_failure_source": str(case["case_failure_sources"]).split(";")[0],
                "judge_failure_subtype": str(case["case_failure_subtypes"]).split(";")[0],
                "adjudicated_failure_source": ADJUDICATED_SOURCE[klass],
                "adjudicated_failure_subtype": causes[primary[0]]["subtype"],
                "adjudicated_on": DECIDED_ON,
                "adjudicator": "developer",
                "excluded_from_scoring": True,
                "judge_reference_suspect": key in flagged,
                "reference_verdict": verdict,
                "reference_basis": entry.get("law") or entry.get("unlisted_input"),
                "reasoning": (
                    f"The frozen reference is {item['frozen']:,.2f}; "
                    f"{'the corrected value' if klass == 'engine_defect' else 'the alternative'} is "
                    f"{corrected:,.2f}. "
                    + (entry.get("defect", "") + "." if klass == "engine_defect" else texts[0]["alternative_reading"])
                ).strip(),
            }
        )
        summary.append((key, klass, "+".join(primary), item["frozen"], corrected))

    # 2. Affirmed references.
    for key, spec in AFFIRMED.items():
        case = case_index.loc[key]
        new_adjudications.append(
            {
                "country": "us",
                "scenario_id": key[0],
                "variable": key[1],
                "judge_model": judge_model_for(*key),
                "judge_failure_source": str(case["case_failure_sources"]).split(";")[0],
                "judge_failure_subtype": str(case["case_failure_subtypes"]).split(";")[0],
                "adjudicated_failure_source": "llm_error",
                "adjudicated_failure_subtype": spec["subtype"],
                "adjudicated_on": DECIDED_ON,
                "adjudicator": "developer",
                "judge_reference_suspect": key in flagged,
                "reference_verdict": "affirmed",
                "reference_basis": spec["basis"],
                "reasoning": spec["reasoning"],
            }
        )

    # 2b. Flagged references the regeneration replaced: they stay scored.
    revisions = json.loads(
        (HERE.parent / "reference_v12" / "reference_outputs.csv.meta.json").read_text()
    )["revisions"]
    regenerated = {}
    for revision in revisions:
        for change in revision["changed"]:
            regenerated.setdefault((change["scenario_id"], change.get("variable", "snap")), (revision, change))
    done = {(e["scenario_id"], e["variable"]) for e in new_adjudications}
    for key in sorted(flagged):
        if key in done or key not in regenerated:
            continue
        revision, change = regenerated[key]
        convention = causes[revision.get("convention", "c_snap_hold_fy2026")]
        case = case_index.loc[key]
        new_adjudications.append(
            {
                "country": "us",
                "scenario_id": key[0],
                "variable": key[1],
                "judge_model": judge_model_for(*key),
                "judge_failure_source": str(case["case_failure_sources"]).split(";")[0],
                "judge_failure_subtype": str(case["case_failure_subtypes"]).split(";")[0],
                "adjudicated_failure_source": "llm_error",
                "adjudicated_failure_subtype": "thresholds_rates",
                "adjudicated_on": DECIDED_ON,
                "adjudicator": "developer",
                "judge_reference_suspect": True,
                "reference_verdict": "regenerated",
                "reference_basis": convention["basis"],
                "reasoning": (
                    f"The frozen {change['frozen']:,.2f} used a PolicyEngine projection of "
                    "an amount published after the reference freeze; the reference is "
                    "regenerated under the benchmark's rule. "
                    + convention["rule"]
                    + f" The regenerated reference is {change['regenerated']:,.2f}."
                ),
            }
        )

    # 3. Existing adjudications: flagged ones gain their reference verdict.
    adjudications_doc = json.loads(adjudications_path.read_text())
    for entry in adjudications_doc["adjudications"]:
        key = (entry["scenario_id"], entry["variable"])
        if key in flagged and not entry.get("reference_verdict"):
            entry["judge_reference_suspect"] = True
            entry["reference_verdict"] = "unlisted_input"
            entry["reference_basis"] = "42 U.S.C. 1382c(a)(3)(A); 20 CFR 416.905"
    new_keys = {(e["scenario_id"], e["variable"]) for e in new_adjudications}
    kept = [e for e in adjudications_doc["adjudications"] if (e["scenario_id"], e["variable"]) not in new_keys]
    adjudications_doc["adjudications"] = kept + new_adjudications
    exclusions_doc["exclusions"] = exclusions_doc["exclusions"] + new_exclusions

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "reference_exclusions.json").write_text(json.dumps(exclusions_doc, indent=2) + "\n")
    (args.out_dir / "us_adjudications.json").write_text(json.dumps(adjudications_doc, indent=2) + "\n")
    unresolved = flagged - {(e["scenario_id"], e["variable"]) for e in adjudications_doc["adjudications"] if e.get("reference_verdict")}
    for key, klass, cause, frozen, corrected in summary:
        print(f"{key[0]} {key[1]:46s} {klass:15s} {cause:60s} {frozen:>11.2f} -> {corrected:>11.2f}")
    print(
        f"exclusions: {len(exclusions_doc['exclusions'])} ({len(new_exclusions)} new); "
        f"adjudications: {len(adjudications_doc['adjudications'])}; "
        f"flagged cases without a verdict: {sorted(unresolved)}"
    )
    if PENDING_JUDGE:
        print(f"WARNING: {len(PENDING_JUDGE)} records name a case awaiting its re-judge: {PENDING_JUDGE}")
        if not args.allow_pending_judge:
            raise SystemExit("re-judge those cases first (or pass --allow-pending-judge for a dry run)")


if __name__ == "__main__":
    main()
