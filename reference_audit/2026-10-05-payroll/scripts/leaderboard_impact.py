"""Score the frozen run as published, with the proposed exclusions, and with regenerated references.

Reads the pass's inputs from git, never from the working tree: the frozen run
(payload, predictions, references, scenarios, exclusions) as PASS_COMMIT (release
dashboard-data-20260930, #187) holds it, and this audit's proposals and #191's
records as AUDIT_COMMIT (#202, which merged both audits) holds them. Later releases
rewrite the working tree's run: dashboard-data-20261006 (#202) installed the four
proposed exclusions and #191's three, so a copy of today's run with them appended
carries duplicate exclusions, which the analyze CLI refuses. Each input in INPUTS is
staged under ``<scratch>/pass_inputs`` and must match its pinned sha256, or the script
stops before scoring anything. The scoring code is the checkout's; the ``published``
check below stops the script if that code no longer scores the pinned run as the
pinned payload records.

Copies the staged run (predictions, references, scenarios, exclusions) to scratch
directories and never writes the snapshot. Three copies are scored with
``python -m policybench.cli analyze``, the command the freeze runs:

``published``
    Unchanged. It must reproduce the published payload's scoring: every modelStats field
    except the cost and latency fields the freeze overlays, and programStats, heatmap,
    globalWeights and failureModes exactly. The script stops if it does not.
``exclude``
    The records in ``proposed_exclusions.json`` appended to the exclusion record.
``regenerate``
    The references in ``proposed_regenerations.json`` written into the reference CSV
    (and the copy's sidecar digest updated to match, as a release's sidecar would be).

Sensitivity: the open state income tax withholding proposal (PolicyEngine/policybench#191,
decision d963) excludes three federal outputs and may land in the same release. With
``--with-salt`` the script also scores that proposal alone (``salt``) and each option on
top of it (``exclude+salt``, ``regenerate+salt``), with its records as #191's head
``SALT_COMMIT`` holds them; the ``*+salt`` deltas are measured against ``salt``.
#202 merged that file unchanged (SALT_SHA256), so the script reads it from
AUDIT_COMMIT and does not need #191's closed branch.

  PYTHONPATH=<checkout> <policybench venv>/bin/python \\
    reference_audit/2026-10-05-payroll/scripts/leaderboard_impact.py --scratch <dir> \\
    [--with-salt]

The checkout needs PASS_COMMIT and AUDIT_COMMIT in its history (a shallow clone needs
``git fetch --unshallow``). ``--out-dir`` writes the verification files elsewhere;
tests/test_reference_audit_pins.py regenerates them that way and requires the
committed ones byte for byte.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
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
AUDIT_PATH = "reference_audit/2026-10-05-payroll"
EXCLUSIONS_PATH = f"{AUDIT_PATH}/proposed_exclusions.json"
REGENERATIONS_PATH = f"{AUDIT_PATH}/proposed_regenerations.json"
# #191's records: its reference_audit/2026-10-05/proposed_exclusions.json at its head
# SALT_COMMIT, which leaderboard_impact.json records; #202 merged the same bytes.
SALT_COMMIT = "8af912a062dd7ae1373de4c043ae2727d3406930"
SALT_RECORDS = "reference_audit/2026-10-05/proposed_exclusions.json"
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
    EXCLUSIONS_PATH: (
        AUDIT_COMMIT,
        "f23088c2d76ce2a0f1c535529952e579798920450c0ca47a9e975f3fe3c44157",
    ),
    REGENERATIONS_PATH: (
        AUDIT_COMMIT,
        "58386f369f6164cc9d63cc4dcc4423495e214e45948fb2e2479910fc8165efef",
    ),
    SALT_RECORDS: (AUDIT_COMMIT, SALT_SHA256),
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
VARIANTS = ("exclude", "regenerate")
OUTPUT = "payroll_tax"


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


def salt_exclusions(inputs: Path) -> list[dict]:
    """The #191 proposal's records, from the inputs staged under ``inputs``."""
    return json.loads((inputs / SALT_RECORDS).read_text())["exclusions"]


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


def stage(inputs: Path, target: Path, variant: str | None) -> Path:
    """Copy the run staged under ``inputs`` to ``target`` and apply ``variant``."""
    source = inputs / RUN_PATH
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in RUN_FILES:
        shutil.copy2(source / name, target / name)
    parts = set((variant or "").split("+")) - {""}
    extra = []
    if "exclude" in parts:
        extra += json.loads((inputs / EXCLUSIONS_PATH).read_text())["exclusions"]
    if "salt" in parts:
        extra += salt_exclusions(inputs)
    if extra:
        record = json.loads((target / "reference_exclusions.json").read_text())
        record["exclusions"].extend(extra)
        (target / "reference_exclusions.json").write_text(
            json.dumps(record, indent=2) + "\n"
        )
    if "regenerate" in parts:
        changes = json.loads((inputs / REGENERATIONS_PATH).read_text())["regenerated"]
        reference = pd.read_csv(target / "reference_outputs.csv", dtype={"value": str})
        index = reference.set_index(["scenario_id", "variable"]).index
        for change in changes:
            key = (change["scenario_id"], change["variable"])
            row = index.get_loc(key)
            if abs(float(reference.at[row, "value"]) - change["frozen_value"]) > 1e-9:
                raise SystemExit(f"{key}: frozen value differs from the reference CSV")
            reference.at[row, "value"] = repr(float(change["regenerated_value"]))
        reference.to_csv(target / "reference_outputs.csv", index=False)
        before = (source / "reference_outputs.csv").read_text().splitlines()
        after = (target / "reference_outputs.csv").read_text().splitlines()
        changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        if len(before) != len(after) or len(changed) != len(changes):
            raise SystemExit(
                f"regenerated CSV changes {len(changed)} lines, expected {len(changes)}"
            )
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
    payload = json.loads(dashboard.read_text())
    return payload["countries"]["us"]


def check_reproduces_published(base: dict, source: Path) -> None:
    """Stop unless ``base`` scores as the staged ``source/data.json.gz`` does."""
    published = json.loads(gzip.decompress((source / "data.json.gz").read_bytes()))
    for key in EXACT_PAYLOAD_KEYS:
        if published[key] != base[key]:
            raise SystemExit(f"unchanged copy does not reproduce published {key}")
    a = {m["model"]: m for m in published["modelStats"]}
    b = {m["model"]: m for m in base["modelStats"]}
    if set(a) != set(b):
        raise SystemExit("model sets differ")
    for model, row in a.items():
        for field, value in row.items():
            if field not in OVERLAID and value != b[model].get(field):
                raise SystemExit(f"{model}.{field}: {value} != {b[model].get(field)}")


def ranks(frame: pd.DataFrame, metric: str) -> pd.Series:
    return frame[metric].rank(ascending=False, method="min").astype(int)


def payroll_exact_counts(payload: dict) -> pd.Series:
    """Each model's count of exact payroll_tax rows among scored outputs."""
    counts: dict[str, int] = {}
    for outputs in payload["scenarioPredictions"].values():
        cells = outputs.get(OUTPUT, {})
        for model, cell in cells.items():
            if cell.get("scored"):
                counts[model] = counts.get(model, 0) + int(cell["exact"] == 100.0)
    return pd.Series(counts)


def compare(base: dict, other: dict) -> pd.DataFrame:
    a = pd.DataFrame(base["modelStats"]).set_index("model")
    b = pd.DataFrame(other["modelStats"]).set_index("model")
    rows = pd.DataFrame(index=a.index)
    for metric in METRICS:
        rows[f"{metric}_published"] = a[metric]
        rows[f"{metric}_proposed"] = b[metric]
        rows[f"{metric}_delta"] = b[metric] - a[metric]
    for metric in RANKED:
        rows[f"{metric}_rank_published"] = ranks(a, metric)
        rows[f"{metric}_rank_proposed"] = ranks(b, metric)
        rows[f"{metric}_rank_change"] = (
            rows[f"{metric}_rank_published"] - rows[f"{metric}_rank_proposed"]
        )
    rows["n_published"] = a["n"]
    rows["n_proposed"] = b["n"]
    rows["payroll_exact_published"] = payroll_exact_counts(base)
    rows["payroll_exact_proposed"] = payroll_exact_counts(other)
    rows["payroll_exact_delta"] = (
        rows["payroll_exact_proposed"] - rows["payroll_exact_published"]
    )
    return rows.sort_values("exact_rank_published")


def program_rows(base: dict, other: dict) -> pd.DataFrame:
    a = pd.DataFrame(base["programStats"]).set_index("variable")
    b = pd.DataFrame(other["programStats"]).set_index("variable")
    rows = pd.DataFrame(index=a.index)
    for metric in ("exact", "score", "n"):
        rows[f"{metric}_published"] = a[metric]
        rows[f"{metric}_proposed"] = b[metric]
        rows[f"{metric}_delta"] = b[metric] - a[metric]
    return rows[(rows.filter(like="_delta").abs() > 1e-9).any(axis=1)]


def summarize(
    models: pd.DataFrame,
    programs: pd.DataFrame,
    base: dict,
    other: dict,
    zero: dict,
    changed: list[str],
) -> dict:
    leader = models.sort_values("exact_rank_proposed").index[0]
    return {
        "changed_outputs": changed,
        "scored_outputs": {
            "published": int(base["modelStats"][0]["n"]),
            "proposed": int(other["modelStats"][0]["n"]),
        },
        "exact_delta_pp": {
            "min": float(models["exact_delta"].min()),
            "max": float(models["exact_delta"].max()),
            "mean": float(models["exact_delta"].mean()),
        },
        "score_delta": {
            "min": float(models["score_delta"].min()),
            "max": float(models["score_delta"].max()),
        },
        **{
            f"{metric}_rank_changes": {
                model: {
                    "published": int(row[f"{metric}_rank_published"]),
                    "proposed": int(row[f"{metric}_rank_proposed"]),
                }
                for model, row in models.iterrows()
                if row[f"{metric}_rank_change"] != 0
            }
            for metric in RANKED
        },
        "always_zero_baseline": zero,
        "leader_margin_over_always_zero_exact": {
            "model": leader,
            "published": float(
                models.loc[leader, "exact_published"] - zero["published"]["exact"]
            ),
            "proposed": float(
                models.loc[leader, "exact_proposed"] - zero["proposed"]["exact"]
            ),
        },
        "top5_exact_published": models.sort_values("exact_rank_published")
        .head(5)
        .index.tolist(),
        "top5_exact_proposed": models.sort_values("exact_rank_proposed")
        .head(5)
        .index.tolist(),
        "payroll_exact_delta_by_model": {
            model: int(delta)
            for model, delta in models["payroll_exact_delta"].items()
            if delta != 0
        },
        "payroll_program": programs.loc[[OUTPUT]].to_dict(orient="index")
        if OUTPUT in programs.index
        else {},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--with-salt", action="store_true")
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

    base_dir = stage(inputs, scratch / "published", None)
    base = analyze(base_dir)
    check_reproduces_published(base, inputs / RUN_PATH)
    zero_published = always_zero(base_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"published_reproduced": True}
    plan = [(variant, base, zero_published) for variant in VARIANTS]
    if args.with_salt:
        salt_dir = stage(inputs, scratch / "salt", "salt")
        salt = analyze(salt_dir)
        salt_zero = always_zero(salt_dir)
        plan.insert(0, ("salt", base, zero_published))
        plan += [(f"{variant}+salt", salt, salt_zero) for variant in VARIANTS]
        summary["salt_commit"] = SALT_COMMIT
    for variant, reference_payload, reference_zero in plan:
        run_dir = stage(inputs, scratch / variant, variant)
        other = analyze(run_dir)
        models = compare(reference_payload, other)
        programs = program_rows(reference_payload, other)
        zero = {"published": reference_zero, "proposed": always_zero(run_dir)}
        records = []
        if "exclude" in variant:
            records += json.loads((inputs / EXCLUSIONS_PATH).read_text())["exclusions"]
        if "regenerate" in variant:
            records += json.loads((inputs / REGENERATIONS_PATH).read_text())[
                "regenerated"
            ]
        if variant == "salt":
            records += salt_exclusions(inputs)
        changed = [f"{r['scenario_id']}/{r['variable']}" for r in records]
        models.to_csv(
            out_dir / f"leaderboard_impact_{variant.replace('+', '_plus_')}_models.csv"
        )
        programs.to_csv(
            out_dir
            / f"leaderboard_impact_{variant.replace('+', '_plus_')}_programs.csv"
        )
        summary[variant] = summarize(
            models, programs, reference_payload, other, zero, changed
        )
        summary[variant]["measured_against"] = (
            "salt" if variant.endswith("+salt") else "published"
        )
        with pd.option_context("display.width", 250, "display.max_rows", 100):
            print(f"\n=== {variant} ===")
            print(
                models[
                    [
                        "exact_published",
                        "exact_proposed",
                        "exact_delta",
                        "exact_rank_published",
                        "exact_rank_proposed",
                        "score_published",
                        "score_proposed",
                        "score_rank_published",
                        "score_rank_proposed",
                        "payroll_exact_published",
                        "payroll_exact_proposed",
                    ]
                ].round(4)
            )
            print(programs.round(4))
    (out_dir / "leaderboard_impact.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
