"""Build a fresh US household set for PolicyBench, in the frozen board's layout.

Max, 2026-10-22: v2's head-to-head runs on fresh households from the latest
Microcosm build, with references from the latest policyengine-us, served as
one certified pair by the installed policyengine.py bundle. The run goes
slowly, in small batches with AI judges between them, because new microdata
can reach engine paths the frozen 100 households never did.

    household_set.py build --n 100 --seed 20261022 --batch-size 10 --out DIR
    household_set.py references --board DIR --out FILE
    household_set.py check-frozen --out FILE

``build`` samples households from the dataset the installed policyengine.py
bundle certifies (:func:`policybench.scenarios.generate_scenarios`, the board's
own sampler and eligibility rules), renames them ``mc_000`` onward so they
never share an id with the frozen board, computes every output on the
installed policyengine-us with the reference conventions
(reference_audit/2026-09-28/fixes/latest_final.py), and writes a board
directory the tool pilot reads with ``--board``:

    scenarios.csv (+ .meta.json)          the households, as the frozen board
    reference_outputs.csv (+ .meta.json)  value and impact_weight per output
    reference_exclusions.json             an empty exclusion record
    batches.json                          the households in batches, in draw order

The reference sidecar has the frozen board's shape: one ``engine_upgrade``
revision naming the engine and pinning every fix module by sha256, so the
pilot's pin check reads either board the same way.

``references`` recomputes a board's references and reports any output that
differs (the determinism check). ``check-frozen`` is the differential check
of the reference path: on the frozen board's own households it must reproduce
every scored reference, which holds only on the engine those references were
built with (policyengine-us 2.41.0).

The set is not public. It stays outside the repository until a release
publishes it, so a web-search arm cannot find its answers.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FROZEN_BOARD = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
FIX_MODULE = ROOT / "reference_audit/2026-09-28/fixes/latest_final.py"
YEAR = 2026
# The v1.1 reference run renamed this input for policyengine-us 1.755.4; the
# frozen households still carry the old name (reference_audit/2026-09-28/
# scripts/sweep.py build_situation). Harmless for a household without it.
RENAME = {"partnership_se_income": "partnership_self_employment_net_earnings"}
EXCLUSIONS_RULE = (
    "An output is excluded from scoring for every model when review finds its "
    "reference wrong in law or undetermined by the stated facts. A fresh household "
    "set starts with no exclusions; its batch judges propose them."
)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def installed_engine() -> str:
    from importlib import metadata

    return f"policyengine-us {metadata.version('policyengine-us')}"


def frozen_programs() -> list[str]:
    meta = json.loads((FROZEN_BOARD / "reference_outputs.csv.meta.json").read_text())
    return list(meta["programs"])


def frozen_fix_pins() -> list[dict]:
    """The fix modules the frozen 2.41.0 references were built with."""
    meta = json.loads((FROZEN_BOARD / "reference_outputs.csv.meta.json").read_text())
    revisions = [
        r
        for r in meta["revisions"]
        if r.get("kind") == "engine_upgrade"
        and r.get("engine_version") == "policyengine-us 2.41.0"
    ]
    if len(revisions) != 1:
        raise SystemExit("the frozen board has no single 2.41.0 engine_upgrade")
    return revisions[0]["fix_modules"]


def fix_module_pins(fix_module: Path = FIX_MODULE) -> list[dict]:
    """Each module the reform composes, at its current bytes.

    The set of modules is the frozen board's; each must exist and match the
    frozen pin, so a household set's references follow exactly the frozen
    conventions. Changing a convention for a new engine is an engine-upgrade
    audit, which pins its own modules.
    """
    pins, problems = [], []
    for pin in frozen_fix_pins():
        path = ROOT / pin["path"]
        if not path.exists():
            problems.append(f"{pin['path']} is missing")
            continue
        digest = sha256_file(path)
        if digest != pin["sha256"]:
            problems.append(f"{pin['path']} is not the frozen {pin['sha256'][:12]}")
        pins.append({"module": pin["module"], "path": pin["path"], "sha256": digest})
    if problems:
        raise SystemExit("; ".join(problems))
    return pins


def load_reform(fix_module: Path = FIX_MODULE):
    spec = importlib.util.spec_from_file_location("household_set_fixes", fix_module)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.reform


def reference_system(fix_module: Path = FIX_MODULE):
    from policyengine_us import CountryTaxBenefitSystem

    return CountryTaxBenefitSystem(reform=load_reform(fix_module))


def situation_for(scenario) -> dict:
    situation = scenario.to_pe_household()
    for person in situation["people"].values():
        for old, new in RENAME.items():
            if old in person:
                person[new] = person.pop(old)
    return situation


def compute_references(scenarios, programs: list[str], system) -> pd.DataFrame:
    """Every output of every household on ``system``: the ground-truth path
    (policybench.ground_truth._calculate_ground_truth_us_scalar) with the
    reference conventions."""
    from policyengine_us import Simulation

    from policybench.ground_truth import (
        _extract_person_impact_weight,
        _extract_person_value,
        _impact_weight_variable_for_output,
        _pe_variable_for_output,
    )
    from policybench.spec import expand_programs_for_scenario

    rows = []
    for scenario in scenarios:
        simulation = Simulation(
            tax_benefit_system=system, situation=situation_for(scenario)
        )
        for variable in expand_programs_for_scenario(programs, scenario):
            result = simulation.calculate(_pe_variable_for_output(variable, "us"), YEAR)
            weight_variable = _impact_weight_variable_for_output(variable, "us")
            weight = None
            if weight_variable is not None:
                weight = _extract_person_impact_weight(
                    result,
                    simulation.calculate(weight_variable, YEAR),
                    scenario,
                    variable,
                )
            rows.append(
                {
                    "scenario_id": scenario.id,
                    "variable": variable,
                    "value": float(_extract_person_value(result, scenario, variable)),
                    "impact_weight": weight,
                }
            )
    return pd.DataFrame(
        rows, columns=["scenario_id", "variable", "value", "impact_weight"]
    )


def rename_scenarios(scenarios, prefix: str) -> list:
    """The sampled households under fresh ids, in draw order."""
    return [
        dataclasses.replace(scenario, id=f"{prefix}_{index:03d}")
        for index, scenario in enumerate(scenarios)
    ]


def split_batches(ids: list[str], size: int) -> list[list[str]]:
    if size < 1:
        raise ValueError("batch size must be at least 1")
    return [ids[start : start + size] for start in range(0, len(ids), size)]


def load_scenarios(board: Path) -> list:
    from policybench.scenarios import scenario_from_dict

    frame = pd.read_csv(Path(board) / "scenarios.csv")
    return [scenario_from_dict(json.loads(text)) for text in frame["scenario_json"]]


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def explicit_dataset(repo: str, filename: str, revision: str) -> tuple[Path, dict]:
    """A published dataset named by repo, file and tag (not the bundle's), and
    what its release manifest says about the engine it was built for."""
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import EntryNotFoundError

    path = Path(hf_hub_download(repo, filename, revision=revision, repo_type="dataset"))
    record = {
        "uri": f"hf://datasets/{repo}/{filename}@{revision}",
        "release_manifest": None,
    }
    try:
        manifest_path = hf_hub_download(
            repo,
            f"releases/{revision}/release_manifest.json",
            revision=revision,
            repo_type="dataset",
        )
    except EntryNotFoundError:
        return path, record
    manifest = json.loads(Path(manifest_path).read_text())
    build = manifest.get("build") or {}
    record["release_manifest"] = {
        "sha256": sha256_file(Path(manifest_path)),
        "built_with_model_package": build.get("built_with_model_package"),
        "built_with_core_package": build.get("built_with_core_package"),
        "compatible_model_packages": manifest.get("compatible_model_packages"),
    }
    return path, record


# How a dataset's stated filing status reads as a scenario's.
STATED_FILING_STATUS = {
    "SINGLE": "single",
    "JOINT": "joint",
    "HEAD_OF_HOUSEHOLD": "head_of_household",
    "SEPARATE": "separate",
    "SURVIVING_SPOUSE": "surviving_spouse",
}


def stated_filing_status(path: Path) -> dict[int, str] | None:
    """Each tax unit's filing_status_input from a Populace H5 (pandas table
    format), or None when the file states none. Engines after 2.2.1 no longer
    read the column; they derive filing status from the household."""
    import h5py

    if not h5py.is_hdf5(path):
        return None
    with h5py.File(path, "r") as handle:
        if "tax_unit" not in handle or "table" not in handle["tax_unit"]:
            return None
        table = handle["tax_unit"]["table"][:]
    columns = {}
    for field in table.dtype.names:
        sub = table.dtype[field]
        for name in sub.names or (field,):
            columns[name] = table[field][name] if sub.names else table[field]
    if "filing_status_input" not in columns or "tax_unit_id" not in columns:
        return None
    return {
        int(unit): (value.decode() if isinstance(value, bytes) else str(value))
        for unit, value in zip(columns["tax_unit_id"], columns["filing_status_input"])
    }


def filing_status_mismatches(scenarios, stated: dict[int, str] | None) -> list[dict]:
    """Households whose scenario filing status (the engine's) is not the one
    the dataset states."""
    if stated is None:
        return []
    found = []
    for scenario in scenarios:
        unit = scenario.metadata.get("tax_unit_id")
        said = stated.get(int(unit)) if unit is not None else None
        if said is None:
            continue
        if STATED_FILING_STATUS.get(said, said.lower()) != scenario.filing_status:
            found.append(
                {
                    "scenario_id": scenario.id,
                    "tax_unit_id": int(unit),
                    "stated": said,
                    "engine": scenario.filing_status,
                }
            )
    return found


def command_build(args) -> None:
    from policybench.policyengine_runtime import (
        materialize_certified_us_dataset,
        policyengine_bundles_for_countries,
    )
    from policybench.scenarios import generate_scenarios, scenario_manifest

    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty; a household set is written once")
    named = [args.dataset_repo, args.dataset_file, args.dataset_revision]
    if any(named) and not all(named):
        raise SystemExit(
            "name a dataset by --dataset-repo, --dataset-file and --dataset-revision"
        )
    engine = installed_engine()
    pins = fix_module_pins(Path(args.fix_module))
    programs = frozen_programs()
    bundles = policyengine_bundles_for_countries(["us"])
    bundle = bundles["us"]
    if all(named):
        # Max, 2026-10-22: "we can still test before that but i'd like v2 to be
        # clean". A dataset other than the bundle's makes a test set only.
        dataset_path, dataset_record = explicit_dataset(*named)
        dataset_label = f"{Path(args.dataset_file).stem}@{args.dataset_revision}"
        certified_pair = False
    else:
        dataset_path = Path(materialize_certified_us_dataset())
        dataset_record = {"uri": bundle.get("default_dataset_uri")}
        dataset_label = None
        certified = bundle.get("certified_data_artifact_sha256")
        if certified and certified != sha256_file(dataset_path):
            raise SystemExit(
                f"{dataset_path} hashes to {sha256_file(dataset_path)}, not the "
                f"bundle's {certified}"
            )
        # The bundle certifies its data for its own model pin; the pair is
        # certified only when that pin is the installed engine.
        certified_pair = bundle.get("bundled_model_version") == bundle.get(
            "model_version"
        )
    if not certified_pair and args.purpose != "test":
        raise SystemExit(
            "this dataset and engine are not a certified pair: build it with "
            "--purpose test, or install a bundle that certifies the engine"
        )
    dataset_sha256 = sha256_file(dataset_path)

    sampled = generate_scenarios(
        n=args.n,
        seed=args.seed,
        country="us",
        dataset=str(dataset_path) if all(named) else None,
        dataset_label=dataset_label,
    )
    scenarios = rename_scenarios(sampled, args.id_prefix)
    mismatches = filing_status_mismatches(scenarios, stated_filing_status(dataset_path))
    references = compute_references(
        scenarios, programs, reference_system(Path(args.fix_module))
    )

    out.mkdir(parents=True, exist_ok=True)
    manifest = scenario_manifest(scenarios)
    manifest.to_csv(out / "scenarios.csv", index=False)
    references.to_csv(out / "reference_outputs.csv", index=False)
    batches = split_batches([s.id for s in scenarios], args.batch_size)
    (out / "batches.json").write_text(
        json.dumps({"batch_size": args.batch_size, "batches": batches}, indent=1) + "\n"
    )
    (out / "reference_exclusions.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "rule": EXCLUSIONS_RULE,
                "derivation": f"Built {_utc_now()[:10]} with no exclusions.",
                "exclusions": [],
            },
            indent=1,
        )
        + "\n"
    )
    generated = _utc_now()
    common = {
        "country": "us",
        "metadata_version": 1,
        "board_kind": "household_set",
        "purpose": args.purpose,
        "certified_pair": certified_pair,
        "generated_at_utc": generated,
        "num_scenarios": len(scenarios),
        "requested_num_scenarios": args.n,
        "seed": args.seed,
        "id_prefix": args.id_prefix,
        "program_set": "headline",
        "programs": programs,
        "policyengine_bundles": bundles,
        "dataset": {
            **dataset_record,
            "path_name": dataset_path.name,
            "sha256": dataset_sha256,
            "bundle_default_dataset_uri": bundle.get("default_dataset_uri"),
        },
        # The dataset states a filing status the engine no longer reads; these
        # households' scenarios carry the engine's, as their references do.
        "filing_status_mismatches": mismatches,
        "source_households": [
            {"scenario_id": s.id, **{k: s.metadata[k] for k in sorted(s.metadata)}}
            for s in scenarios
        ],
    }
    (out / "scenarios.csv.meta.json").write_text(
        json.dumps(
            {
                **common,
                "task": "scenario_manifest",
                "scenarios_csv_sha256": sha256_file(out / "scenarios.csv"),
            },
            indent=1,
        )
        + "\n"
    )
    (out / "reference_outputs.csv.meta.json").write_text(
        json.dumps(
            {
                **common,
                "task": "reference_outputs",
                "reference_csv_sha256": sha256_file(out / "reference_outputs.csv"),
                "scenarios_csv_sha256": sha256_file(out / "scenarios.csv"),
                "revisions": [
                    {
                        "kind": "engine_upgrade",
                        "engine_version": engine,
                        "date": generated[:10],
                        "builder": "scripts/household_set.py build",
                        "fix_module": {
                            "path": str(
                                Path(args.fix_module).resolve().relative_to(ROOT)
                            ),
                            "sha256": sha256_file(Path(args.fix_module)),
                        },
                        "fix_modules": pins,
                        "outputs": len(references),
                    }
                ],
            },
            indent=1,
        )
        + "\n"
    )
    print(
        f"{len(scenarios)} households, {len(references)} outputs on {engine}; "
        f"{len(batches)} batches of up to {args.batch_size} in {out}; purpose "
        f"{args.purpose}, certified pair {certified_pair}; "
        f"{len(mismatches)} filing status mismatches"
    )


def differences(
    expected: pd.DataFrame, computed: pd.DataFrame, tolerance: float
) -> pd.DataFrame:
    """Outputs whose computed value is missing or differs beyond ``tolerance``."""
    merged = expected.merge(
        computed[["scenario_id", "variable", "value"]],
        on=["scenario_id", "variable"],
        how="left",
        suffixes=("", "_computed"),
    )
    merged["delta"] = (merged["value_computed"] - merged["value"]).abs()
    return merged[merged["value_computed"].isna() | (merged["delta"] > tolerance)]


def command_references(args) -> None:
    board = Path(args.board)
    expected = pd.read_csv(board / "reference_outputs.csv")
    meta = json.loads((board / "reference_outputs.csv.meta.json").read_text())
    computed = compute_references(
        load_scenarios(board), meta["programs"], reference_system(Path(args.fix_module))
    )
    diff = differences(expected, computed, args.tolerance)
    computed.to_csv(args.out, index=False)
    print(
        f"{len(computed)} outputs recomputed on {installed_engine()}; "
        f"{len(diff)} differ"
    )
    if len(diff):
        print(diff.to_string(index=False))
        raise SystemExit(1)


def command_check_frozen(args) -> None:
    """The reference path on the frozen board must reproduce every scored output."""
    from policybench.reference_exclusions import (
        load_reference_exclusions,
        split_reference,
    )

    engine = installed_engine()
    if engine != "policyengine-us 2.41.0":
        raise SystemExit(f"{engine} is installed; the frozen references are 2.41.0's")
    fix_module_pins(FIX_MODULE)
    reference = pd.read_csv(FROZEN_BOARD / "reference_outputs.csv")
    scored, _ = split_reference(reference, load_reference_exclusions(FROZEN_BOARD))
    computed = compute_references(
        load_scenarios(FROZEN_BOARD), frozen_programs(), reference_system(FIX_MODULE)
    )
    computed.to_csv(args.out, index=False)
    diff = differences(scored, computed, args.tolerance)
    print(
        f"{len(scored)} scored outputs; {len(scored) - len(diff)} reproduced within "
        f"{args.tolerance} on {engine}"
    )
    if len(diff):
        print(diff.to_string(index=False))
        raise SystemExit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="sample a household set and its references")
    build.add_argument("--n", type=int, required=True)
    build.add_argument("--seed", type=int, required=True)
    build.add_argument("--batch-size", type=int, default=10)
    build.add_argument("--id-prefix", default="mc")
    build.add_argument("--fix-module", default=str(FIX_MODULE))
    build.add_argument("--out", required=True)
    build.add_argument(
        "--purpose",
        choices=["v2", "test"],
        default="v2",
        help="v2 needs a certified dataset-engine pair; test takes any",
    )
    build.add_argument("--dataset-repo", help="a published dataset, for a test set")
    build.add_argument("--dataset-file")
    build.add_argument("--dataset-revision")
    build.set_defaults(func=command_build)
    refs = sub.add_parser("references", help="recompute a board's references")
    refs.add_argument("--board", required=True)
    refs.add_argument("--fix-module", default=str(FIX_MODULE))
    refs.add_argument("--tolerance", type=float, default=1e-6)
    refs.add_argument("--out", required=True)
    refs.set_defaults(func=command_references)
    frozen = sub.add_parser("check-frozen", help="reproduce the frozen references")
    frozen.add_argument("--tolerance", type=float, default=1e-6)
    frozen.add_argument("--out", required=True)
    frozen.set_defaults(func=command_check_frozen)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
