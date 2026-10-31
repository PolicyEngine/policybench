"""Which references move when a Minnesota renter holds a qualifying CRP.

Release review r2 of the GPT-6.1 Terra board (2026-10-29) found that scenario
122's Minnesota refundable credits reference is $0 only because
mn_renters_credit_qualifying_crp, an input no prompt states, defaults to
False in policyengine-us. mn_renters_credit_eligible requires it, so with the
default no Minnesota household gets the renter's credit.

This sweep recomputes every output of every Minnesota household twice on the
installed policyengine-us, as the 2026-10-22 build computes its references
(reference_audit/2026-09-28/fixes/latest_final.py's reform, households built by
reference_audit/2026-09-28/scripts/sweep.py's build_situation, both pinned by
that build): once as built, and once with mn_renters_credit_qualifying_crp
set to true on every tax unit. The first pass must reproduce the build's
reference for every scored output. Every output the second pass moves beyond
the paper's exact-match tolerance is listed, with both values.

With --against base it checks the first pass against release 20261014's
references instead (the builder's load_base, pinned), for a run on
policyengine-us 2.41.0, the engine those references and the exclusion record's
ruled records name.

Usage: python sweep_crp.py OUT_JSON [--against build|base]
"""

import datetime
import importlib.util
import io
import json
import sys
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BUILDER_PATH = ROOT / "reference_audit/2026-10-22-engine-upgrade/scripts/build_references_upgrade.py"
BUILD = ROOT / "reference_audit/2026-10-22-engine-upgrade/reference-build"
INPUT = "mn_renters_credit_qualifying_crp"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def with_crp(situation: dict, scenario) -> dict:
    units = situation.get("tax_units") or {}
    if not units:
        raise SystemExit(f"{scenario.id}: the built household has no tax unit")
    for unit in units.values():
        unit[INPUT] = {str(YEAR): True}
    return situation


def main() -> None:
    out_path = Path(sys.argv[1])
    against = sys.argv[3] if sys.argv[2:3] == ["--against"] else "build"
    if against not in ("build", "base") or len(sys.argv) not in (2, 4):
        raise SystemExit("usage: sweep_crp.py OUT_JSON [--against build|base]")
    sys.path.insert(0, str(ROOT))
    builder = load("crp_builder", BUILDER_PATH)
    global YEAR
    YEAR = builder.YEAR
    import pandas as pd
    from policyengine_us import CountryTaxBenefitSystem

    from policybench.scenarios import scenario_from_dict

    base = builder.load_base()
    builder.fix_module_pins(base.meta, builder.FIXES)
    harness_pin = builder.harness_pin()
    harness = builder.load_module("crp_sweep_harness", builder.HARNESS)
    final = builder.load_module(f"crp_{builder.FIX_ENTRY}", builder.FIXES / f"{builder.FIX_ENTRY}.py")

    scenarios = pd.read_csv(io.StringIO(base.scenarios_csv))
    mn = sorted(
        row["scenario_id"]
        for _, row in scenarios.iterrows()
        if scenario_from_dict(json.loads(row["scenario_json"])).state == "MN"
    )
    if against == "base":
        values = {key: float(value) for key, value in base.reference.values().items()}
        exclusions = base.exclusions["exclusions"]
    else:
        reference = pd.read_csv(BUILD / "reference_outputs.csv")
        values = {(row.scenario_id, row.variable): float(row.value) for row in reference.itertuples()}
        exclusions = json.loads((BUILD / "reference_exclusions.json").read_text())["exclusions"]
    excluded = {(e["scenario_id"], e["variable"]) for e in exclusions}
    keys = [key for key in values if key[0] in set(mn)]

    system = CountryTaxBenefitSystem(reform=final.reform)
    plain = builder.compute_items(system, scenarios, keys, harness.build_situation)
    crp = builder.compute_items(system, scenarios, keys, harness.build_situation, patches=(with_crp,))

    mismatched = [
        {"scenario_id": k[0], "variable": k[1], "reference": values[k], "recomputed": plain[k]}
        for k in keys
        if k not in excluded and builder.beyond(k[1], values[k], plain[k])
    ]
    moved = [
        {
            "scenario_id": k[0],
            "variable": k[1],
            "scored": k not in excluded,
            "reference": values[k],
            "as_built": plain[k],
            "with_crp": crp[k],
        }
        for k in keys
        if builder.beyond(k[1], plain[k], crp[k])
    ]
    doc = {
        "question": f"Which outputs move when every Minnesota tax unit sets {INPUT} to true?",
        "engine": f"policyengine-us {version('policyengine-us')}",
        "policyengine_core": version("policyengine-core"),
        "computed_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "conventions": f"{builder.FIXES_REL}/{builder.FIX_ENTRY}.py",
        "harness": harness_pin,
        "references": (
            str(BUILD.relative_to(ROOT))
            if against == "build"
            else f"release 20261014 at {builder.BASE_COMMIT[:12]} (load_base)"
        ),
        "minnesota_households": mn,
        "outputs_checked": len(keys),
        "scored_outputs_checked": sum(k not in excluded for k in keys),
        "baseline_mismatches": mismatched,
        "moved": moved,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2) + "\n")
    print(
        f"{len(mn)} Minnesota households, {len(keys)} outputs; "
        f"{len(mismatched)} baseline mismatches; {len(moved)} moved with a qualifying CRP"
    )
    for item in moved:
        print(f"  {item['scenario_id']} {item['variable']}: {item['as_built']} -> {item['with_crp']} (scored={item['scored']})")
    if mismatched:
        raise SystemExit("the as-built pass does not reproduce the build's scored references")


if __name__ == "__main__":
    main()
