"""Score the frozen run under each combination of the Part B and SALT proposals.

Reads the pass's inputs from git, never from the working tree: the frozen run
(payload, predictions, references, scenarios, exclusions, and the legacy impact
summary) as PASS_COMMIT (release dashboard-data-20260930, #187) holds it, and this
audit's proposals, sweep and copy of #191's records as AUDIT_COMMIT (#202, which
merged this audit) holds them. Later releases rewrite the working tree's run:
dashboard-data-20261006 (#202) installed #191's three records and this audit's
Virginia record and rewrote the legacy impact summary, so a copy of today's run with
these records appended carries duplicate exclusions, which the analyze CLI refuses.
Each input in INPUTS is staged under ``<scratch>/pass_inputs`` and must match its
pinned sha256, or the script stops before scoring anything. The scoring code is the
checkout's; the ``published`` checks below stop the script if that code no longer
scores the pinned run as the pinned payload and impact summary record.

Copies the staged run (predictions, references, scenarios, exclusions) to scratch
directories and never writes the snapshot. Each copy is scored with ``python -m
policybench.cli analyze``, the command the freeze runs, and the dashboard payloads are
compared. The cases:

``published``
    The exclusion record unchanged. It must reproduce the published payload's scoring:
    every modelStats field except the cost and latency fields the freeze overlays, and
    programStats, heatmap, globalWeights and failureModes exactly.
``part_b``
    This audit's records if PolicyEngine/policybench#191 is not adopted: scenario_114's
    Virginia output and the standalone Part B record for its federal output.
``salt``
    #191's three records alone (022, 081 and 114 federal), as #191 scored them.
``salt_and_part_b``
    #191's three records and this audit's Virginia record.

Each case also recomputes the legacy household impact summary that the freeze writes
beside the analyze output (``impact_summary_by_model.csv``, pinned in the snapshot
manifest), with ``scripts/freeze_snapshot.household_impact_summary_by_model`` on the
scored reference; the published case must reproduce the frozen file.

``--weights-check`` also scores a copy whose eligibility impact weights are the ones
policyengine-us 2.15.17 computes (verification/sweep_part_b.csv) instead of the
published ones, which the 2026-09-29 rebuild did not recompute. It reports whether any
compared payload value changes and how the legacy impact summary moves.

#191's records are read from ``verification/inputs/pr191_proposed_exclusions.json``, a
copy of ``reference_audit/2026-10-05/proposed_exclusions.json`` at #191's head
8af912a0; its pinned sha256 is that file's.

  PYTHONPATH=<checkout> <triage>/.venv-pe21517/bin/python \\
    reference_audit/2026-10-05-medicare-part-b/scripts/leaderboard_impact.py \\
      --scratch <dir> --weights-check

The checkout needs PASS_COMMIT and AUDIT_COMMIT in its history (a shallow clone needs
``git fetch --unshallow``). ``--out-dir`` writes the verification files elsewhere;
tests/test_reference_audit_pins.py regenerates them that way and requires the
committed ones byte for byte.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT_DIR = HERE / "verification"
# The pass's inputs, pinned by commit and sha256.
PASS_COMMIT = "8b4c0ca146bb6f66deba6ce24009d49d70d92df2"
AUDIT_COMMIT = "9ce4ade8382962a9134860c23f56d92509b5e57f"
RUN_PATH = (
    "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
AUDIT_PATH = "reference_audit/2026-10-05-medicare-part-b"
FROZEN_IMPACT_PATH = f"{RUN_PATH}/analysis/impact_summary_by_model.csv"
PROPOSED_PATH = f"{AUDIT_PATH}/proposed_exclusions.json"
SWEEP_PATH = f"{AUDIT_PATH}/verification/sweep_part_b.csv"
SALT_COPY_PATH = f"{AUDIT_PATH}/verification/inputs/pr191_proposed_exclusions.json"
# #191's reference_audit/2026-10-05/proposed_exclusions.json at its head 8af912a0.
SALT_SHA256 = "3c330177762c46fa5c52b02f9f943e9d5a65e15855280b64e9b462ab27413272"
# Every file the script reads from the repository: path -> (commit, sha256).
# pass_inputs() stages each at the same path under its target.
INPUTS = {
    f"{RUN_PATH}/data.json.gz": (
        PASS_COMMIT,
        "1e029aaa87d1dfbd2ceee88419599a919dd7c9d4aba78a308ec48d008d54ae18",
    ),
    f"{RUN_PATH}/predictions.csv.gz": (
        PASS_COMMIT,
        "ca2c4c48c7fd3e680c9c61a7380ecfcb60ce95f913c5c363762e023949d8ad12",
    ),
    f"{RUN_PATH}/reference_outputs.csv": (
        PASS_COMMIT,
        "e8bbba8fd3e90f78e7c0e83df06227bc1c94563e92f7405fe12be853a30b2466",
    ),
    f"{RUN_PATH}/reference_outputs.csv.meta.json": (
        PASS_COMMIT,
        "816fef53c452d8520a321bc12bc29b28da1e7956a06818e5ec13d7fc7b371a4b",
    ),
    f"{RUN_PATH}/reference_exclusions.json": (
        PASS_COMMIT,
        "bf4e6a249aeee01d0b71f5834ef7a35c4bab2266d2c59d0e81b12a0da44281c2",
    ),
    f"{RUN_PATH}/scenarios.csv": (
        PASS_COMMIT,
        "71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a",
    ),
    f"{RUN_PATH}/scenarios.csv.meta.json": (
        PASS_COMMIT,
        "03a66e90b86e9bd0cc77f27520784bd581777762f749675dc716e24c1b8eaebb",
    ),
    FROZEN_IMPACT_PATH: (
        PASS_COMMIT,
        "e6e034adee408cc798897bc0825ace9740055ab20e528ce842bd06e2c81e0922",
    ),
    PROPOSED_PATH: (
        AUDIT_COMMIT,
        "fee2523738a2da96876e6cd3141325cb5939e0140a357c0b59b0f39d5b37eb76",
    ),
    SWEEP_PATH: (
        AUDIT_COMMIT,
        "a0f7820ca0b5b64118509dc39ae5469ecbde89e5f843065761d429b81458681b",
    ),
    SALT_COPY_PATH: (AUDIT_COMMIT, SALT_SHA256),
}
# Copied into each copy and scored; data.json.gz is only compared against.
RUN_FILES = (
    "predictions.csv.gz",
    "reference_outputs.csv",
    "reference_outputs.csv.meta.json",
    "reference_exclusions.json",
    "scenarios.csv",
    "scenarios.csv.meta.json",
)
# The freeze overlays these from the published payload; the analyze CLI does not.
OVERLAID = {"costUsd", "costPerHousehold", "totalTokens", "latencySeconds"}
METRICS = (
    "exact",
    "within1pct",
    "within5pct",
    "within10pct",
    "score",
    "outputGroupScore",
)
EXACT_PAYLOAD_KEYS = ("programStats", "heatmap", "globalWeights", "failureModes")
RANKED = ("exact", "within1pct", "score")


def always_zero(run_dir: Path) -> dict[str, float]:
    """The always-zero baseline, as paper_results._always_zero_weighted_rates scores it."""
    import numpy as np

    from policybench.analysis import weighted_hit_rate_scores_by_model
    from policybench.reference_exclusions import scored_reference_for
    from policybench.spec import get_output_ids, output_group_id

    truth, _ = scored_reference_for(run_dir / "reference_outputs.csv")
    headline = set(get_output_ids("us", "headline"))
    truth = truth[truth["variable"].map(output_group_id).isin(headline)]
    truth = truth.reset_index(drop=True)
    truth["scenario_id"] = truth["scenario_id"].astype(str)
    scenarios = pd.read_csv(run_dir / "scenarios.csv")
    market = dict(
        zip(
            scenarios["scenario_id"].astype(str),
            pd.to_numeric(scenarios["total_income"], errors="coerce").fillna(0.0),
        )
    )
    predictions = truth[["scenario_id", "variable"]].copy()
    predictions["model"] = "Always zero"
    predictions["prediction"] = np.zeros(len(truth))
    scored = weighted_hit_rate_scores_by_model(truth, predictions, market, country="us")
    return {
        "exact": float(scored["weighted_exact"].mean()) * 100,
        "within1pct": float(scored["weighted_within_1pct"].mean()) * 100,
    }


def overlaps(scratch: Path, root: Path) -> bool:
    """Whether ``scratch`` and ``root`` are one directory or one holds the other.

    Judged by filesystem identity (device and inode), not spelling, so case on a
    case-insensitive filesystem or a link cannot hide an overlap. ``scratch`` need
    not exist yet; its nearest existing ancestors decide.
    """

    def identities(path: Path) -> set[tuple[int, int]]:
        found = set()
        for part in (path, *path.parents):
            try:
                status = part.stat()
            except OSError:
                continue
            found.add((status.st_dev, status.st_ino))
        return found

    root_status = root.stat()
    if (root_status.st_dev, root_status.st_ino) in identities(scratch):
        return True
    try:
        scratch_status = scratch.stat()
    except OSError:
        return False
    return (scratch_status.st_dev, scratch_status.st_ino) in identities(root)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_input(commit: str, path: str, pinned: str, target: Path) -> Path:
    """Write ``path`` as ``commit`` holds it to ``target``, refusing any other bytes."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{path}"],
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit(
            f"cannot read {path} at {commit[:12]}; fetch full history "
            f"(git fetch --unshallow): {result.stderr.decode().strip()}"
        )
    digest = hashlib.sha256(result.stdout).hexdigest()
    if digest != pinned:
        raise SystemExit(
            f"{commit[:12]}:{path} has sha256 {digest}, not the pinned {pinned}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(result.stdout)
    return target


def pass_inputs(target: Path) -> Path:
    """Stage every input in INPUTS at its repository path under ``target``."""
    if target.exists():
        shutil.rmtree(target)
    for path, (commit, pinned) in INPUTS.items():
        git_input(commit, path, pinned, target / path)
    return target


def salt_records(path: Path) -> list[dict]:
    """#191's records, from the staged copy at ``path`` (pass_inputs checked it)."""
    return json.loads(path.read_text())["exclusions"]


def legacy_impact_summary(run_dir: Path) -> pd.DataFrame:
    """The freeze's impact_summary_by_model.csv, computed on a staged copy."""
    from policybench.reference_exclusions import scored_reference_for

    path = ROOT / "scripts/freeze_snapshot.py"
    spec = importlib.util.spec_from_file_location("freeze_snapshot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    truth, _ = scored_reference_for(run_dir / "reference_outputs.csv")
    predictions = pd.read_csv(run_dir / "predictions.csv.gz", low_memory=False)
    return module.household_impact_summary_by_model(truth, predictions)


def legacy_impact_change(base: pd.DataFrame, case: pd.DataFrame) -> dict:
    a = base.set_index("model")["mean_impact_score"]
    b = case.set_index("model")["mean_impact_score"].reindex(a.index)
    rank_a = a.rank(ascending=False, method="min")
    rank_b = b.rank(ascending=False, method="min")
    moved = rank_a != rank_b
    return {
        "mean_impact_score_delta": {
            "min": float((b - a).min()),
            "max": float((b - a).max()),
        },
        "models_changing_rank": int(moved.sum()),
        "rank_changes": {
            model: {"published": int(rank_a[model]), "case": int(rank_b[model])}
            for model in a.index[moved]
        },
    }


def stage(
    source: Path, target: Path, extra: list[dict], weights: pd.DataFrame | None = None
) -> Path:
    """Copy the staged run at ``source`` to ``target`` and apply the case."""
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in RUN_FILES:
        shutil.copy2(source / name, target / name)
    if extra:
        record = json.loads((target / "reference_exclusions.json").read_text())
        record["exclusions"].extend(extra)
        (target / "reference_exclusions.json").write_text(
            json.dumps(record, indent=2) + "\n"
        )
    if weights is not None:
        reference = pd.read_csv(target / "reference_outputs.csv")
        keyed = weights.set_index(["scenario_id", "variable"])["baseline_impact_weight"]
        keys = list(zip(reference["scenario_id"], reference["variable"]))
        has = reference["impact_weight"].notna()
        reference.loc[has, "impact_weight"] = [
            float(keyed[k]) for k, h in zip(keys, has) if h
        ]
        reference.to_csv(target / "reference_outputs.csv", index=False)
        # The analyzer checks the CSV against the digest its sidecar pins; repin the
        # scratch copy's sidecar to the rewritten CSV.
        meta_path = target / "reference_outputs.csv.meta.json"
        meta = json.loads(meta_path.read_text())
        meta["reference_csv_sha256"] = sha256(target / "reference_outputs.csv")
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    return target


def analyze(run_dir: Path) -> dict:
    out = run_dir / "analysis"
    dashboard = run_dir / "dashboard.json"
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "policybench.cli",
            "analyze",
            "-g",
            str(run_dir / "reference_outputs.csv"),
            "-p",
            str(run_dir / "predictions.csv.gz"),
            "-s",
            str(run_dir / "scenarios.csv"),
            "-o",
            str(out),
            "--app-data-output",
            str(dashboard),
            "--reference-digest",
            sha256(run_dir / "reference_outputs.csv"),
        ],
        cwd=ROOT,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return json.loads(dashboard.read_text())["countries"]["us"]


def payload_differences(a: dict, b: dict) -> list[str]:
    """Compared payload values that differ (modelStats less the overlaid fields)."""
    out = [key for key in EXACT_PAYLOAD_KEYS if a[key] != b[key]]
    x = {m["model"]: m for m in a["modelStats"]}
    y = {m["model"]: m for m in b["modelStats"]}
    if set(x) != set(y):
        return out + ["modelStats: model sets differ"]
    for model, row in x.items():
        for field, value in row.items():
            if field not in OVERLAID and value != y[model].get(field):
                out.append(f"modelStats.{model}.{field}")
    return out


def check_reproduces_published(base: dict, source: Path) -> None:
    """Stop unless ``base`` scores as the staged ``source/data.json.gz`` does."""
    published = json.loads(gzip.decompress((source / "data.json.gz").read_bytes()))
    diffs = payload_differences(published, base)
    if diffs:
        raise SystemExit(
            f"unchanged copy does not reproduce the published payload: {diffs[:10]}"
        )


def ranks(frame: pd.DataFrame, metric: str) -> pd.Series:
    return frame[metric].rank(ascending=False, method="min").astype(int)


def compare(base: dict, case: dict) -> pd.DataFrame:
    a = pd.DataFrame(base["modelStats"]).set_index("model")
    b = pd.DataFrame(case["modelStats"]).set_index("model")
    rows = pd.DataFrame(index=a.index)
    for metric in METRICS:
        rows[f"{metric}_published"] = a[metric]
        rows[f"{metric}_case"] = b[metric]
        rows[f"{metric}_delta"] = b[metric] - a[metric]
    for metric in RANKED:
        rows[f"{metric}_rank_published"] = ranks(a, metric)
        rows[f"{metric}_rank_case"] = ranks(b, metric)
    rows["n_published"] = a["n"]
    rows["n_case"] = b["n"]
    return rows.sort_values("exact_rank_published")


def program_rows(base: dict, case: dict) -> pd.DataFrame:
    a = pd.DataFrame(base["programStats"]).set_index("variable")
    b = pd.DataFrame(case["programStats"]).set_index("variable")
    rows = pd.DataFrame(index=a.index)
    for metric in ("exact", "score", "n"):
        rows[f"{metric}_published"] = a[metric]
        rows[f"{metric}_case"] = b[metric]
        rows[f"{metric}_delta"] = b[metric] - a[metric]
    return rows[(rows.filter(like="_delta").abs() > 1e-9).any(axis=1)]


def rank_changes(models: pd.DataFrame, metric: str) -> dict:
    return {
        model: {
            "published": int(row[f"{metric}_rank_published"]),
            "case": int(row[f"{metric}_rank_case"]),
        }
        for model, row in models.iterrows()
        if row[f"{metric}_rank_published"] != row[f"{metric}_rank_case"]
    }


def summarize(
    name: str, records: list[dict], base: dict, case: dict, zero: dict
) -> dict:
    models = compare(base, case)
    leader = models.sort_values("exact_rank_case").index[0]
    return {
        "case": name,
        "exclusions_added": [f"{r['scenario_id']}/{r['variable']}" for r in records],
        "scored_outputs": {
            "published": int(models["n_published"].iloc[0]),
            "case": int(models["n_case"].iloc[0]),
        },
        "exact_delta_pp": {
            "min": float(models["exact_delta"].min()),
            "max": float(models["exact_delta"].max()),
            "mean": float(models["exact_delta"].mean()),
        },
        "within1pct_delta_pp": {
            "min": float(models["within1pct_delta"].min()),
            "max": float(models["within1pct_delta"].max()),
        },
        "score_delta": {
            "min": float(models["score_delta"].min()),
            "max": float(models["score_delta"].max()),
        },
        **{f"{m}_rank_changes": rank_changes(models, m) for m in RANKED},
        "always_zero_baseline": zero,
        "leader": leader,
        "leader_exact": {
            "published": float(models.loc[leader, "exact_published"]),
            "case": float(models.loc[leader, "exact_case"]),
        },
        "leader_margin_over_always_zero_exact": {
            "published": float(
                models.loc[leader, "exact_published"] - zero["published"]["exact"]
            ),
            "case": float(models.loc[leader, "exact_case"] - zero["case"]["exact"]),
        },
        "programs": program_rows(base, case).round(6).reset_index().to_dict("records"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--weights-check", action="store_true")
    parser.add_argument(
        "--out-dir",
        default=str(OUT_DIR),
        help="where to write the verification files (default: %(default)s)",
    )
    args = parser.parse_args()
    scratch = Path(args.scratch).resolve()
    out_dir = Path(args.out_dir)
    # stage() and pass_inputs() delete and rewrite scratch/<name>, so scratch and
    # the repository must not overlap: neither may lie inside the other.
    if overlaps(scratch, ROOT):
        parser.error(f"--scratch must not overlap the repository ({ROOT})")
    inputs = pass_inputs(scratch / "pass_inputs")
    source = inputs / RUN_PATH

    proposal = json.loads((inputs / PROPOSED_PATH).read_text())
    va = proposal["exclusions"]
    federal = [c["record"] for c in proposal["conditional_on_salt_decision"]]
    salt = salt_records(inputs / SALT_COPY_PATH)
    cases = {
        "part_b": va + federal,
        "salt": salt,
        "salt_and_part_b": salt + va,
    }

    base_dir = stage(source, scratch / "published", [])
    base = analyze(base_dir)
    check_reproduces_published(base, source)
    zero_published = always_zero(base_dir)
    impact_base = legacy_impact_summary(base_dir)
    frozen_impact = pd.read_csv(inputs / FROZEN_IMPACT_PATH)
    pd.testing.assert_frame_equal(
        impact_base.reset_index(drop=True),
        frozen_impact,
        check_exact=False,
        rtol=0,
        atol=1e-12,
    )

    summaries, tables = [], {}
    for name, records in cases.items():
        run_dir = stage(source, scratch / name, records)
        case = analyze(run_dir)
        zero = {"published": zero_published, "case": always_zero(run_dir)}
        summary = summarize(name, records, base, case, zero)
        summary["legacy_impact_summary"] = legacy_impact_change(
            impact_base, legacy_impact_summary(run_dir)
        )
        summaries.append(summary)
        tables[name] = compare(base, case)

    # The marginal effect of the Virginia record on top of #191's records.
    salt_models = tables["salt"]
    both = tables["salt_and_part_b"]
    marginal = pd.DataFrame(
        {
            "exact_salt": salt_models["exact_case"],
            "exact_salt_and_part_b": both["exact_case"],
            "exact_delta": both["exact_case"] - salt_models["exact_case"],
            "rank_salt": salt_models["exact_rank_case"],
            "rank_salt_and_part_b": both["exact_rank_case"],
            "score_delta": both["score_case"] - salt_models["score_case"],
        }
    )
    marginal_summary = {
        "exact_delta_pp": {
            "min": float(marginal["exact_delta"].min()),
            "max": float(marginal["exact_delta"].max()),
        },
        "exact_rank_changes": {
            model: {
                "salt": int(r.rank_salt),
                "salt_and_part_b": int(r.rank_salt_and_part_b),
            }
            for model, r in marginal.iterrows()
            if r.rank_salt != r.rank_salt_and_part_b
        },
    }

    weights_check = None
    if args.weights_check:
        sweep = pd.read_csv(inputs / SWEEP_PATH)
        run_dir = stage(source, scratch / "weights_2_15_17", [], weights=sweep)
        moved = int(
            (
                sweep["reference_impact_weight"].notna()
                & (
                    (
                        sweep["reference_impact_weight"]
                        - sweep["baseline_impact_weight"]
                    ).abs()
                    > 1e-3
                )
            ).sum()
        )
        diffs = payload_differences(base, analyze(run_dir))
        weights_check = {
            "impact_weights_replaced": moved,
            "payload_differences": diffs,
            "legacy_impact_summary": legacy_impact_change(
                impact_base, legacy_impact_summary(run_dir)
            ),
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    wide = pd.concat(
        {
            name: table[
                ["exact_case", "exact_rank_case", "score_case", "score_rank_case"]
            ]
            for name, table in tables.items()
        },
        axis=1,
    )
    wide.columns = [f"{case}_{col.removesuffix('_case')}" for case, col in wide.columns]
    first = tables["part_b"]
    wide.insert(0, "exact_published", first["exact_published"])
    wide.insert(1, "exact_rank_published", first["exact_rank_published"])
    wide.insert(2, "score_published", first["score_published"])
    wide.insert(3, "score_rank_published", first["score_rank_published"])
    wide.to_csv(out_dir / "leaderboard_impact_models.csv")
    marginal.to_csv(out_dir / "leaderboard_impact_marginal.csv")
    result = {
        "published_reproduced": True,
        "legacy_impact_summary_reproduced": True,
        "cases": summaries,
        "virginia_record_on_top_of_salt": marginal_summary,
        "impact_weights_check": weights_check,
    }
    (out_dir / "leaderboard_impact.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    with pd.option_context("display.width", 250, "display.max_rows", 100):
        print(wide.round(4))
        print(marginal.round(4))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
