"""Build PolicyBench's US references on the newest policyengine-us (the 2026-09-29 upgrade).

Rulings:
- Max's ruling, 2026-09-28: "we should be using the latest pe for this always!"
  References come from the newest policyengine-us release when PolicyBench begins the
  reference sweep; at publication PolicyBench checks that the newest release gives the
  same values. The sweep began at 01:42 UTC on 2026-09-29, when the newest release was
  2.15.17 (uploaded to PyPI at 00:23 UTC; verification/sweep_timing.json).
  policyengine.py 6.1.2 is recorded for provenance only: its certified bundle is
  policyengine-us 2.2.1, and `import policyengine` refuses to load next to 2.15.17.
- Max, 2026-09-22 (reference sidecar rule): a scored reference follows from the stated
  facts and from law published before the 2026-07-03 reference freeze. The nine
  conventions that hold pre-freeze law are re-expressed for 2.15.17
  (sweep/fixes/latest_c_*.py, composed in latest_conventions.py).

Method:
- Every output is computed on 2.15.17 with latest_conventions plus
  latest_md_local_output_scope (the output-definition adapter: the benchmark's state
  income tax output excludes local tax; 2.15.17 folded Maryland county tax into it).
  Households are built by policybench's own Scenario.to_pe_household, which since this
  wave also passes stated usual weekly hours to weekly_hours_worked_before_lsr (upstream
  #9261 changed that input's default from 40 to 0).
- A scored output takes the computed value. It may move against the board (release
  20260922c) only if it is listed in --actions as a reviewed change, and it must then
  equal the listed value. A move not listed, a listed move that does not happen, or a
  listed value the engine does not produce stops the build. Moves of $1 or less are
  applied and recorded.
- An excluded output keeps the value its exclusion record names, as on 2026-09-22. It is
  not scored. Its 2.15.17 value and the reviewed reason it stays excluded are recorded:
  the reason is the full text of its cluster review's corrected_per_output entry in
  clusters.json (beside --actions), and final_actions.json must carry the same text.
- An output the audit excluded on review, apart from any engine change, is listed in
  --actions' audit_exclusions with its exclusion record. Its engine value must equal
  both the board's and the record's frozen_value, so the revision's changed list does
  not name it; the record is appended to the exclusions after the upgrade's own.

Dates are UTC days. The wave began on the evening of 2026-09-28, US Eastern time, which
is this directory's name; the sweep began at 01:42 UTC on 2026-09-29, so the records
date the upgrade 2026-09-29: the revision's date, the derivation, and each new
exclusion's basis, which takes the exclusion's decided_on. The first build ran at 11:57
UTC. The rebuild later that day changed only record text (the upgrade's date and
wording); its reference CSV is byte-identical, and the sidecar's regenerated_at_utc is
the rebuild's.

The first build ran in the triage directory, whose layout this script assumes:

  cd triage && PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 \\
    PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2 \\
    .venv-pepy612-us21517/bin/python build_references_latest.py \\
      --actions latest/final_actions.json --out-dir ../reference_v13

Later on 2026-09-29, rewrite_reference_records.py applied this script's record functions
(reviewed_reason, audit_exclusions, exclusion_derivation, dump_record) to the installed
records without recomputing any output: the rechecked outputs' full reviewed reasons,
and the one audit exclusion (scenario_023 head_medicaid_eligible). A rebuild writes the
same records.

The rebuild ran from this directory's committed files, laid out the same way (B is a
scratch directory), and scripts/install_adds0929_references.py installed its output:

  mkdir -p $B/sweep/fixes && cp scripts/build_references_latest.py $B/ \\
    && cp scripts/sweep.py $B/sweep/ && cp fixes/*.py $B/sweep/fixes/ \\
    && cp ../2026-09-22/fixes/r19_irs_sales_tax_2025.json $B/sweep/fixes/
  (cd $B && PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=<checkout> \\
    <triage>/.venv-pepy612-us21517/bin/python build_references_latest.py \\
      --actions <this directory>/final_actions.json --out-dir $B/out)
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import sys
from importlib.metadata import version
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
FIXES = HERE / "sweep" / "fixes"
BUNDLE = Path(
    "/Users/maxghenis/PolicyEngine/policybench/results/local/newmodels/publish/"
    "us_full_run_20260612_policyengine_4_16_1_populace/us"
)  # the frozen v1.1 bundle (policyengine-us 1.755.4), read-only
CHECKOUT = Path("/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2")
RUN = "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
# Release dashboard-data-20260922c: main at this commit. Read from git, not from the
# checkout, whose snapshot holds whatever this script last wrote.
BASE_COMMIT = "3220a7a62b6be83032e9313c9df539c619ad8932"


def _board() -> Path:
    import subprocess
    import tempfile

    out = Path(tempfile.mkdtemp(prefix="board-20260922c-"))
    for name in ("reference_outputs.csv", "reference_outputs.csv.meta.json", "reference_exclusions.json"):
        raw = subprocess.run(
            ["git", "-C", str(CHECKOUT), "show", f"{BASE_COMMIT}:{RUN}/{name}"],
            check=True, capture_output=True,
        ).stdout
        (out / name).write_bytes(raw)
    return out
YEAR = 2026
DATE = "2026-09-29"
ENGINE = "2.15.17"
PARTS = ("latest_conventions", "latest_md_local_output_scope")
CONVENTION_MODULES = (
    "latest_c_ca_hold_2025",
    "latest_c_irs_sales_tax_2025",
    "latest_c_wi_published_2026",
    "latest_c_id_hold_2025",
    "latest_c_mn_published_2026",
    "latest_c_md_2026",
    "latest_c_mi_published_2026",
    "latest_c_mo_published_2026",
    "latest_c_snap_hold_fy2026",
)
RULE = (
    "A scored reference follows from the stated facts and from law published before "
    "the 2026-07-03 reference freeze."
)
# Lead's ruling of 2026-09-29 on the wording: "newest" holds at a stated time.
ENGINE_RULE = (
    "References come from the newest policyengine-us release when PolicyBench begins "
    "the reference sweep; at publication PolicyBench checks that the newest release "
    "gives the same values."
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def dump_record(value: dict) -> str:
    """The serialization of the sidecar and the exclusion record."""
    return json.dumps(value, indent=2) + "\n"


def reviewed_reason(clusters: dict, entry: dict) -> str:
    """The full reason a rechecked excluded output stays excluded: its cluster
    review's corrected_per_output entry in clusters.json, verbatim."""
    key = (entry["scenario_id"], entry["variable"])
    reasons = [
        item["reason"]
        for item in clusters[entry["cluster"]]["review"]["corrected_per_output"]
        if (item["scenario_id"], item["variable"]) == key
    ]
    if len(reasons) != 1:
        raise SystemExit(f"{key}: {len(reasons)} reviewed reasons in {entry['cluster']}")
    return reasons[0]


def audit_exclusions(actions: dict) -> dict:
    """The exclusion records of the outputs the audit excluded on review, apart from
    any engine change (final_actions.json audit_exclusions), by output."""
    records = {}
    for item in actions.get("audit_exclusions", []):
        key = (item["scenario_id"], item["variable"])
        record = item["exclusion"]
        if (record["scenario_id"], record["variable"]) != key or key in records:
            raise SystemExit(f"malformed audit exclusion {key}")
        records[key] = record
    return records


def exclusion_derivation(base: str, decided: int, on_review: int) -> str:
    """The exclusion record's derivation: the 20260922c text, then the upgrade's.
    `decided` counts the records decided on DATE, `on_review` those among them the
    audit excluded on review."""
    text = (
        base
        + f" On {DATE} the references moved to policyengine-us {ENGINE} with the"
        " pre-freeze conventions. Every excluded output was recomputed there, and each"
        " one that moved was re-reviewed and stays excluded (the reference sidecar's"
        " engine_upgrade revision lists them). Records decided before that date keep"
        f" the values they were decided on; the {NUMBER_WORDS[decided]} records"
        f" decided that day were computed on {ENGINE}."
    )
    if on_review == 1:
        text += (
            " The audit excluded one of them on review of the release. Its reference"
            " did not move, so the engine_upgrade revision does not list it"
            " (final_actions.json audit_exclusions)."
        )
    elif on_review:
        text += (
            f" The audit excluded {NUMBER_WORDS[on_review]} of them on review of the"
            " release. Their references did not move, so the engine_upgrade revision"
            " does not list them (final_actions.json audit_exclusions)."
        )
    return text


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"build_{name}", FIXES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def moved(variable: str, a: float, b: float) -> bool:
    if variable.endswith("_eligible"):
        return round(a) != round(b)
    return abs(a - b) > 1.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actions", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    if version("policyengine-us") != ENGINE:
        raise SystemExit(f"need policyengine-us {ENGINE}, have {version('policyengine-us')}")

    sys.path.insert(0, str(HERE / "sweep"))
    from sweep import build_situation  # noqa: E402  (sweep.py's reference builder)

    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output
    from policybench.policyengine_runtime import policyengine_release_bundle
    from policybench.scenarios import scenario_from_dict
    from policybench.spec import expand_programs_for_scenario
    from policyengine_us import CountryTaxBenefitSystem, Simulation

    actions = json.loads(Path(args.actions).read_text())
    approved = {(a["scenario_id"], a["variable"]): a for a in actions["approved"]}
    rechecked = {(a["scenario_id"], a["variable"]): a for a in actions["excluded_rechecked"]}
    clusters = {
        c["id"]: c
        for c in json.loads(Path(args.actions).with_name("clusters.json").read_text())["clusters"]
    }
    audit = audit_exclusions(actions)

    BOARD = _board()
    modules = {name: load(name) for name in PARTS}
    system = CountryTaxBenefitSystem(reform=tuple(m.reform for m in modules.values()))
    board = pd.read_csv(BOARD / "reference_outputs.csv")
    board_meta = json.loads((BOARD / "reference_outputs.csv.meta.json").read_text())
    v11 = pd.read_csv(BUNDLE / "reference_outputs.csv").set_index(["scenario_id", "variable"])["value"]
    exclusion_file = json.loads((BOARD / "reference_exclusions.json").read_text())
    exclusions = exclusion_file["exclusions"]
    excluded = {(e["scenario_id"], e["variable"]) for e in exclusions}
    added = {(e["scenario_id"], e["variable"]): e for e in actions["new_exclusions"]}
    if set(added) & excluded:
        raise SystemExit("a new exclusion is already excluded")
    if set(audit) & (excluded | set(added) | set(approved)):
        raise SystemExit("an audit exclusion is already excluded, added or approved")
    scenarios = pd.read_csv(BUNDLE / "scenarios.csv")

    computed = {}
    for _, srow in scenarios.iterrows():
        scenario = scenario_from_dict(json.loads(srow["scenario_json"]))
        situation = build_situation(scenario)
        if scenario.id == "scenario_066":
            # The builder mapping this wave depends on (stated 40 hours reach SNAP).
            head = next(iter(situation["people"].values()))
            assert "weekly_hours_worked_before_lsr" in head, "builder hours mapping missing"
        sim = Simulation(tax_benefit_system=system, situation=situation)
        for variable in expand_programs_for_scenario(board_meta["programs"], scenario):
            key = (scenario.id, variable)
            computed[key] = float(
                _extract_person_value(
                    sim.calculate(_pe_variable_for_output(variable, "us"), YEAR), scenario, variable
                )
            )

    problems, changed, small, excluded_values = [], [], [], []
    new = board.copy()
    for idx, row in board.iterrows():
        key = (row["scenario_id"], row["variable"])
        value, old = computed[key], float(row["value"])
        if key in excluded:
            excluded_values.append((key, value, old))
            continue
        if key in audit:
            # Excluded on review, not for an engine change: the value must not move.
            if abs(value - old) > 1e-6 or abs(value - float(audit[key]["frozen_value"])) > 1e-6:
                problems.append(
                    f"audit exclusion {key}: engine {value}, board {old}, "
                    f"record {audit[key]['frozen_value']}"
                )
                continue
            new.loc[idx, "value"] = value
            continue
        if key in added:
            record = added[key]
            if abs(value - float(record["frozen_value"])) > 1e-3:
                problems.append(f"new exclusion {key}: engine {value} != record {record['frozen_value']}")
                continue
            new.loc[idx, "value"] = value
            changed.append({
                "scenario_id": key[0], "variable": key[1], "frozen": float(v11[key]),
                "previous": old, "regenerated": value,
                "cause": "excluded_reference_depends_on_unlisted_input",
                "basis": (
                    f"Newly excluded from scoring on {record['decided_on']} "
                    "(reference_exclusions.json): " + record["unlisted_input"]
                ),
            })
            continue
        if moved(key[1], value, old):
            if key not in approved:
                problems.append(f"unreviewed move {key}: {old} -> {value}")
                continue
            if abs(value - float(approved[key]["value"])) > 1e-3:
                problems.append(f"{key}: engine {value} != approved {approved[key]['value']}")
                continue
            changed.append({
                "scenario_id": key[0], "variable": key[1], "frozen": float(v11[key]),
                "previous": old, "regenerated": value, "cause": approved[key]["cause"],
                "basis": approved[key]["basis"],
            })
        elif abs(value - old) > 1e-6:
            small.append({
                "scenario_id": key[0], "variable": key[1], "frozen": float(v11[key]),
                "previous": old, "regenerated": value, "cause": "engine_upgrade_within_1",
                "basis": "Moves by $1 or less on policyengine-us 2.15.17; no score changes at the exact-match tolerance.",
            })
        new.loc[idx, "value"] = value
    for key in approved:
        if key in excluded or not moved(key[1], computed[key], float(board.set_index(["scenario_id", "variable"]).loc[key, "value"])):
            problems.append(f"approved change did not happen or is excluded: {key}")
    moved_excluded = [(k, v, o) for k, v, o in excluded_values if moved(k[1], v, o)]
    reasons = {}
    for key, value, old in moved_excluded:
        if key not in rechecked:
            problems.append(f"excluded output moved without a recheck: {key}: {old} -> {value}")
            continue
        reasons[key] = reviewed_reason(clusters, rechecked[key])
        if rechecked[key].get("reason", reasons[key]) != reasons[key]:
            problems.append(f"final_actions reason for {key} is not the reviewer's text")
    if problems:
        raise SystemExit("refusing to write references:\n  " + "\n  ".join(problems))

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    new.to_csv(out / "reference_outputs.csv", index=False)
    exclusion_file["exclusions"] = exclusions + list(added.values()) + list(audit.values())
    exclusion_file["derivation"] = exclusion_derivation(
        exclusion_file["derivation"], len(added) + len(audit), len(audit)
    )
    (out / "reference_exclusions.json").write_text(dump_record(exclusion_file))
    meta = json.loads(json.dumps(board_meta))
    meta["policyengine_bundles"]["us"] = policyengine_release_bundle("us")
    meta["reference_csv_sha256"] = sha256(out / "reference_outputs.csv")
    meta["regenerated_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    meta["revisions"].append({
        "date": DATE,
        "kind": "engine_upgrade",
        "root_cause": "engine_upgrade_policyengine_us_2_15_17",
        "outputs": "every scored output",
        "rule": (
            f"{RULE} {ENGINE_RULE} Max's ruling, 2026-09-28: 'we should be using the "
            "latest pe for this always!' The conventions that hold pre-freeze law are "
            "re-expressed for the release the sweep uses."
        ),
        "engine_version": f"policyengine-us {ENGINE}",
        "previous_engine_version": "policyengine-us 1.755.4",
        "policyengine_py": (
            "policyengine 6.1.2, provenance only: its certified US bundle is "
            "policyengine-us 2.2.1, and it refuses to import next to a newer model"
        ),
        "fix_modules": [
            {"module": f"{name}.py", "sha256": sha256(FIXES / f"{name}.py")}
            for name in (*CONVENTION_MODULES, *PARTS)
        ],
        "builder": (
            "policybench.scenarios.Scenario.to_pe_household passes stated usual weekly "
            "hours (hours_worked_last_week) to weekly_hours_worked_before_lsr as well; "
            "upstream policyengine-us#9261 changed that input's default from 40 to 0"
        ),
        "excluded_outputs_untouched": True,
        "excluded_outputs_rechecked": [
            {
                "scenario_id": k[0], "variable": k[1], "kept_value": o,
                "value_on_2_15_17": v, "reason": reasons[k],
            }
            for k, v, o in moved_excluded
        ],
        "changed": changed + small,
    })
    (out / "reference_outputs.csv.meta.json").write_text(dump_record(meta))

    # Engine traces of every changed output, for the derivation narratives
    # (regen_references.py narratives reads reference_traces.json the same way).
    import types

    sys.modules.setdefault("litellm", types.ModuleType("litellm"))  # tracing needs no LLM
    from policybench.case_reference_explanations import _find_target_tree, _render_trace

    by_id = scenarios.set_index("scenario_id")
    traces = {}
    for item in changed + small:
        scenario = scenario_from_dict(json.loads(by_id.loc[item["scenario_id"], "scenario_json"]))
        sim = Simulation(tax_benefit_system=system, situation=build_situation(scenario))
        sim.trace = True
        pe_variable = _pe_variable_for_output(item["variable"], "us")
        sim.calculate(pe_variable, YEAR)
        tree = _find_target_tree(sim.tracer.trees, pe_variable)
        traces[f"{item['scenario_id']}|{item['variable']}"] = {
            "pe_variable": pe_variable,
            "trace": "\n".join(_render_trace(tree)) if tree else "",
        }
    (out / "reference_traces.json").write_text(json.dumps(traces, indent=1))
    print(f"sha256 {meta['reference_csv_sha256']}")
    print(f"{len(changed)} reviewed changes, {len(small)} within $1, {len(moved_excluded)} excluded outputs rechecked")
    for c in changed + small:
        print(f"  {c['scenario_id']} {c['variable']:46s} {c['previous']:>11.2f} -> {c['regenerated']:>11.2f}  {c['cause']}")


if __name__ == "__main__":
    main()
