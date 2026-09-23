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
# r04 is the faithful backport of upstream #8839; the Wisconsin exclusion the v2
# module also applied is r32, which is not fixed upstream (split 2026-09-23).
SWEEP_FOR = {
    "r01_ira_compensation": "r01_ira_compensation_v2",
    "r02_ira_219g": "r02_ira_219g_v2",
    "r03_estate_income": "r03_estate_income__qbi_false_v2",
    "r04_capital_gain_distributions": "r04_capital_gain_distributions",
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
    "r26_snap_contribution_rounding": "r26_snap_contribution_rounding",
    "r27_snap_net_income_rounding": "r27_snap_net_income_rounding",
    "r28_snap_min_allotment_rounding": "r28_snap_min_allotment_rounding",
    "r30_snap_heat_and_eat_sua": "r30_snap_heat_and_eat_sua",
    "r31_snap_income_limit_rounding": "r31_snap_income_limit_rounding",
    "r32_wi_capital_gain_distributions": "r32_wi_capital_gain_distributions",
}
# The SNAP defects are measured on top of the SNAP publication convention
# (c_snap_hold_fy2026), since the convention's value is what would otherwise be
# published: <defect>_on_c13v3.csv compares the convention alone with the
# convention plus the defect's fix, and moved means more than $1. r32 needs the
# distributions in federal AGI, so it is measured on top of the Wisconsin
# convention plus #8839 (r32_on_cwi_r04.csv). make_on_convention.py writes both.
MEASURED_BY = {
    "r26_snap_contribution_rounding": "r26_on_c13v3",
    "r27_snap_net_income_rounding": "r27_on_c13v3",
    "r28_snap_min_allotment_rounding": "r28_on_c13v3",
    "r30_snap_heat_and_eat_sua": "r30_on_c13v3",
    "r31_snap_income_limit_rounding": "r31_on_c13v3",
    "r32_wi_capital_gain_distributions": "r32_on_cwi_r04",
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


_SYSTEMS: dict[tuple[str, ...], tuple] = {}


def _system_for(fixes: list[str]):
    """The tax-benefit system and situation patches for a set of fixes.

    Only the latest system is kept (one is several gigabytes), so callers
    compute outputs grouped by their fix set.
    """
    from policyengine_us import CountryTaxBenefitSystem

    key = tuple(fixes)
    if key not in _SYSTEMS:
        _SYSTEMS.clear()
        reforms, patches = [], []
        for fix in fixes:
            reform, patch = load_fix(fix)
            reforms.extend(flatten(reform))
            if patch is not None:
                patches.append(patch)
        system = CountryTaxBenefitSystem(reform=tuple(reforms)) if reforms else None
        _SYSTEMS[key] = (system, patches)
    return _SYSTEMS[key]


def combined_value(scenario_id: str, variable: str, fixes: list[str]) -> float:
    """Recompute one output with every listed fix module applied together."""
    from policyengine_us import Simulation

    system, patches = _system_for(fixes)
    scenarios = pd.read_csv(BUNDLE / "scenarios.csv")
    row = scenarios.loc[scenarios["scenario_id"] == scenario_id]
    scenario = scenario_from_dict(json.loads(row["scenario_json"].iloc[0]))
    situation = build_situation(scenario)
    for patch in patches:
        situation = patch(copy.deepcopy(situation), scenario)
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


def compute_many(requests: list[tuple[tuple[str, str], list[str]]]) -> dict:
    """Values for (output, fixes) requests, one tax-benefit system at a time."""
    values = {}
    for key, fixes in sorted(requests, key=lambda item: (item[1], item[0])):
        values[(key, tuple(fixes))] = combined_value(key[0], key[1], fixes)
    return values


# The alternative reading of each unlisted input behind the 2026-09-05
# exclusions, as a situation patch (sweep/fixes/u_*.py).
UNLISTED_PATCH = {
    "meets_ssi_disability_criteria": "u_ssi_disability_criteria",
    "months_receiving_social_security_disability": "u_ssdi_months",
}
FLAG_SOURCE_EARLIER_RUN = (
    "an earlier judge run in the 2026-09-22 wave (flagged_sept22_wave.json); "
    "the case's current verdict.json does not flag it"
)


def judge_flag_for(scenario_id: str, variable: str) -> bool:
    """Whether the case's current verdict.json flags the reference as suspect."""
    path = AUDIT_CASES / f"us__{scenario_id}__{variable}" / "verdict.json"
    return bool(path.exists() and json.loads(path.read_text()).get("reference_suspect"))


def judge_verdict_for(scenario_id: str, variable: str) -> tuple[str, str]:
    """The judge's own class for the case, from its verdict.json.

    Not us_case_notes.csv: apply_adjudications has already replaced the judge's
    class there with the adjudicated one by the time this script reads it.
    """
    path = AUDIT_CASES / f"us__{scenario_id}__{variable}" / "verdict.json"
    if not path.exists():
        PENDING_JUDGE.append(f"{scenario_id}:{variable}")
        return "pending", "pending"
    verdict = json.loads(path.read_text())
    return verdict["case_failure_source"], verdict["case_failure_subtype"]


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
    # Every flag any judge run of the wave raised (the verdicts-board42*.json
    # files, collected into flagged_sept22_wave.json), for the same reason.
    wave = HERE / "flagged_sept22_wave.json"
    if wave.exists():
        flagged |= {tuple(k.split(":")) for k in json.loads(wave.read_text())}

    # 1. Every moved output and the root causes that move it.
    moved: dict[tuple[str, str], dict] = {}
    for cause, fix in SWEEP_FOR.items():
        if causes[cause]["class"] not in PRECEDENCE:
            continue
        not_confirmed = causes[cause].get("not_confirmed", {})
        frame = pd.read_csv(HERE / "sweep" / "out" / f"{MEASURED_BY.get(cause, fix)}.csv")
        for _, r in frame[frame["moved"]].iterrows():
            key = (r["scenario_id"], r["variable"])
            if f"{key[0]}:{key[1]}" in not_confirmed:
                continue
            item = moved.setdefault(key, {"frozen": float(r["frozen"]), "causes": {}})
            item["causes"][cause] = float(r["recomputed"])

    # The publication conventions and the upstream fixes: the references are
    # regenerated under all of them together (regen_references.py), so an
    # excluded output's corrected value applies all of them with its own fixes.
    # A source that changes nothing for a household leaves its value alone, and
    # one that only matters in combination (a SNAP rounding fix once r30 cuts the
    # allotment below the maximum) still applies.
    published_fixes = [
        cause["fix"]
        for cause in causes.values()
        if isinstance(cause, dict) and cause.get("class") == "convention"
    ] + [
        SWEEP_FOR[name]
        for name, cause in causes.items()
        if isinstance(cause, dict) and cause.get("upstream_fixed")
    ]

    new_exclusions, new_adjudications, summary = [], [], []
    regenerated_by_fix = []
    decisions = {}
    for key, item in sorted(moved.items()):
        if key in existing:
            continue
        # Rule (Max, 2026-09-23): a defect fixed in policyengine-us after the
        # freeze is regenerated with the fix (regen_references.py), not excluded.
        # An output any unfixed defect or unlisted input moves stays excluded.
        if all(causes[c].get("upstream_fixed") for c in item["causes"]):
            regenerated_by_fix.append((key, sorted(item["causes"])))
            continue
        # The unfixed causes decide the exclusion; a defect fixed upstream only
        # enters the corrected value, since the regenerated reference applies it.
        fixed = sorted(c for c in item["causes"] if causes[c].get("upstream_fixed"))
        classes = {
            c: causes[c]["class"] for c in item["causes"] if c not in fixed
        }
        klass = next(k for k in PRECEDENCE if k in classes.values())
        primary = sorted(c for c, k in classes.items() if k == klass)
        # Corrected value: the primary class's fixes applied together, and for an
        # engine defect also any later-law fix on the same output, on top of every
        # publication convention and upstream fix, as the published references are.
        applied = primary + sorted(
            c for c, k in classes.items() if klass == "engine_defect" and k == "later_law"
        )
        decisions[key] = (klass, primary, [SWEEP_FOR[c] for c in applied])
    # One system per fix set, computed in fix-set order.
    corrected_values = {}
    for key in sorted(decisions, key=lambda k: (decisions[k][2], k)):
        fixes = decisions[key][2]
        corrected_values[key] = combined_value(key[0], key[1], fixes + published_fixes)

    for key, (klass, primary, fixes) in sorted(decisions.items()):
        item = moved[key]
        corrected = corrected_values[key]
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
        notes = [
            "Corrected value applies " + " and ".join(fixes)
            + (" together" if len(fixes) > 1 else "")
            + " with every publication convention and upstream fix."
        ]
        notes += [causes[c]["exclusion_note"] for c in primary if causes[c].get("exclusion_note")]
        if others:
            notes.append(
                "The output also moves under "
                + ", ".join(
                    f"{c} ({causes[c]['class'].replace('_', ' ')}"
                    + (", fixed upstream" if causes[c].get("upstream_fixed") else "")
                    + ")"
                    for c in others
                )
                + "."
            )
        entry["note"] = " ".join(notes)
        new_exclusions.append(entry)

        verdict = {"engine_defect": "engine_defect", "unlisted_input": "unlisted_input", "later_law": "later_law"}[klass]
        new_adjudications.append(
            {
                "country": "us",
                "scenario_id": key[0],
                "variable": key[1],
                "judge_model": judge_model_for(*key),
                "judge_failure_source": judge_verdict_for(*key)[0],
                "judge_failure_subtype": judge_verdict_for(*key)[1],
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
        new_adjudications.append(
            {
                "country": "us",
                "scenario_id": key[0],
                "variable": key[1],
                "judge_model": judge_model_for(*key),
                "judge_failure_source": judge_verdict_for(*key)[0],
                "judge_failure_subtype": judge_verdict_for(*key)[1],
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
            regenerated.setdefault((change["scenario_id"], change.get("variable", "snap")), []).append((revision, change))
    done = {(e["scenario_id"], e["variable"]) for e in new_adjudications}
    for key in sorted(flagged):
        if key in done or key not in regenerated:
            continue
        sources = regenerated[key]
        change = sources[0][1]
        parts, bases = [], []
        for revision, _ in sources:
            if revision.get("kind") == "upstream_fix":
                cause = causes[revision["root_cause"]]
                parts.append(
                    f"it corrects an engine defect fixed upstream ({cause['upstream']}): {cause['alternative_reading']}"
                )
                bases.append(cause["law"])
            else:
                convention = causes[revision["convention"]]
                parts.append(f"it applies the publication rule: {convention['rule']}")
                bases.append(convention["basis"])
        new_adjudications.append(
            {
                "country": "us",
                "scenario_id": key[0],
                "variable": key[1],
                "judge_model": judge_model_for(*key),
                "judge_failure_source": judge_verdict_for(*key)[0],
                "judge_failure_subtype": judge_verdict_for(*key)[1],
                "adjudicated_failure_source": "llm_error",
                # A convention changes parameter values, so the models' misses
                # against the regenerated reference are threshold and rate
                # errors; where an upstream fix also regenerates the reference,
                # the judge's own subtype stands.
                "adjudicated_failure_subtype": (
                    judge_verdict_for(*key)[1]
                    if any(r.get("kind") == "upstream_fix" for r, _ in sources)
                    else "thresholds_rates"
                ),
                "adjudicated_on": DECIDED_ON,
                "adjudicator": "developer",
                "judge_reference_suspect": True,
                "reference_verdict": "regenerated",
                "reference_basis": "; ".join(bases),
                "reasoning": (
                    f"The frozen {change['frozen']:,.2f} is regenerated as "
                    f"{change['regenerated']:,.2f}: " + "; ".join(parts)
                ),
            }
        )

    # 3. Existing adjudications: flagged ones gain their reference verdict, and
    # an entry whose case was re-judged after it was recorded takes the current
    # judge's model, date and verdict (the adjudication keeps the verdict it
    # resolves beside the decision).
    adjudications_doc = json.loads(adjudications_path.read_text())
    # This wave's entries are rebuilt from scratch on every run; keep only the
    # earlier waves' records, so an output this run no longer excludes loses
    # the adjudication a previous run gave it.
    adjudications_doc["adjudications"] = [
        e for e in adjudications_doc["adjudications"] if e.get("adjudicated_on") != DECIDED_ON
    ]
    refreshed = []
    for entry in adjudications_doc["adjudications"]:
        key = (entry["scenario_id"], entry["variable"])
        meta_path = AUDIT_CASES / f"us__{key[0]}__{key[1]}" / "verdict.meta.json"
        if meta_path.exists() and key in case_index.index:
            meta = json.loads(meta_path.read_text())
            judged_on = str(meta.get("judged_at_utc", ""))[:10]
            if judged_on and judged_on > str(entry.get("judged_on_utc", "")):
                entry["judge_model"] = judge_model_for(*key)
                entry["judged_on_utc"] = judged_on
                refreshed.append(f"{key[0]}:{key[1]}")
        # The judge's class is always the case's current verdict.json, which the
        # freezer checks (verify_adjudications_keep_judge_verdicts).
        if (AUDIT_CASES / f"us__{key[0]}__{key[1]}" / "verdict.json").exists():
            source, subtype = judge_verdict_for(*key)
            entry["judge_failure_source"] = source
            entry["judge_failure_subtype"] = subtype
        if key in flagged and not entry.get("reference_verdict"):
            entry["judge_reference_suspect"] = True
            entry["reference_verdict"] = "unlisted_input"
            entry["reference_basis"] = "42 U.S.C. 1382c(a)(3)(A); 20 CFR 416.905"
    new_keys = {(e["scenario_id"], e["variable"]) for e in new_adjudications}
    kept = [e for e in adjudications_doc["adjudications"] if (e["scenario_id"], e["variable"]) not in new_keys]
    adjudications_doc["adjudications"] = kept + new_adjudications
    # The 2026-09-05 exclusions keep their classification; their alternative
    # value is recomputed like every other corrected value, on top of every
    # publication convention and upstream fix, and a defect not fixed upstream
    # that also moves the output is named in the note.
    carried = [e for e in exclusions_doc["exclusions"] if e["decided_on"] != DECIDED_ON]
    requests = []
    for e in carried:
        key = (e["scenario_id"], e["variable"])
        requests.append((key, [UNLISTED_PATCH[e["unlisted_input"]]] + published_fixes))
        for c in sorted(moved.get(key, {}).get("causes", {})):
            if causes[c]["class"] == "engine_defect" and not causes[c].get("upstream_fixed"):
                requests += [(key, published_fixes), (key, [SWEEP_FOR[c]] + published_fixes)]
    carried_values = compute_many(requests)
    carried_sentences = {}
    for e in carried:
        key = (e["scenario_id"], e["variable"])
        fixes = [UNLISTED_PATCH[e["unlisted_input"]]] + published_fixes
        value = carried_values[(key, tuple(fixes))]
        notes = [e["note"]] if e.get("note") else []
        if abs(value - float(e["alternative_value"])) > 1e-6:
            notes.append(
                f"The 2026-09-05 record gave {float(e['alternative_value']):,.2f} under that "
                f"reading on the frozen engine; the {DECIDED_ON} audit recomputes it with "
                "every publication convention and upstream fix."
            )
            carried_sentences.setdefault(key, []).append(
                f"The {DECIDED_ON} audit recomputes the alternative as {value:,.2f} with every "
                f"publication convention and upstream fix (the frozen-engine value above was "
                f"{float(e['alternative_value']):,.2f})."
            )
            e["alternative_value"] = round(value, 6)
        for c in sorted(moved.get(key, {}).get("causes", {})):
            if causes[c]["class"] == "engine_defect" and not causes[c].get("upstream_fixed"):
                base = carried_values[(key, tuple(published_fixes))]
                fixed_value = carried_values[(key, tuple([SWEEP_FOR[c]] + published_fixes))]
                sentence = (
                    f"{c} (engine defect, not fixed upstream) also moves this output on "
                    f"the stated facts, from {base:,.2f} to {fixed_value:,.2f}; the record "
                    "keeps its 2026-09-05 classification."
                )
                notes.append(sentence)
                carried_sentences.setdefault(key, []).append(sentence)
        if notes:
            e["note"] = " ".join(notes)
    exclusions_doc["exclusions"] = exclusions_doc["exclusions"] + new_exclusions
    # judge_reference_suspect records every flag the wave raised; where the
    # case's current verdict does not carry it, the entry says which run did.
    # The carried 2026-09-05 adjudications state the recomputed alternative too,
    # so their reasoning agrees with the exclusion record (replaced, not
    # appended again, on each run).
    marker = f" The {DECIDED_ON} audit recomputes the alternative"
    for entry in adjudications_doc["adjudications"]:
        key = (entry["scenario_id"], entry["variable"])
        if entry.get("adjudicated_on") != DECIDED_ON:
            reasoning = entry["reasoning"].split(marker)[0]
            reasoning = reasoning.split(" r30_snap_heat_and_eat_sua (engine defect")[0]
            if key in carried_sentences:
                reasoning = reasoning + " " + " ".join(carried_sentences[key])
            entry["reasoning"] = reasoning
    for entry in adjudications_doc["adjudications"]:
        key = (entry["scenario_id"], entry["variable"])
        entry.pop("judge_reference_suspect_source", None)
        if entry.get("judge_reference_suspect") and not judge_flag_for(*key):
            entry["judge_reference_suspect_source"] = FLAG_SOURCE_EARLIER_RUN

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
    if regenerated_by_fix:
        print(f"regenerated with an upstream fix, not excluded ({len(regenerated_by_fix)}): "
              + ", ".join(f"{k[0]}:{k[1]} [{'+'.join(c)}]" for k, c in regenerated_by_fix))
    refreshed = [k for k in refreshed if tuple(k.split(":")) not in new_keys]
    if refreshed:
        print(f"refreshed judge fields on {len(refreshed)} existing adjudications: {refreshed}")
    if PENDING_JUDGE:
        print(f"WARNING: {len(PENDING_JUDGE)} records name a case awaiting its re-judge: {PENDING_JUDGE}")
        if not args.allow_pending_judge:
            raise SystemExit("re-judge those cases first (or pass --allow-pending-judge for a dry run)")


if __name__ == "__main__":
    main()
