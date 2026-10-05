"""Impact weights of reference outputs, recomputed on the reference engine.

An eligibility output carries an impact weight: the dollar value PolicyEngine
pairs with it (its spec's ``impact_weight_variable``, such as ``medicaid``,
``medicare_cost`` or ``wic``) for the person or household the output names, and
0 where that person or household is not eligible
(``ground_truth._extract_impact_weight``). Every other output's weight is empty.

Invariant: every impact weight in a published reference CSV equals the weight
the reference system computes for that household on its own. The reference
system is the engine release and the convention modules that built the
reference values; ``ground_truth.calculate_ground_truth`` computes it in
state-isolated batches, which give what one simulation per household gives.

A reference rebuild that rewrote only the value column broke the invariant on
2026-09-29 (reference_audit/2026-10-05-impact-weights). This module recomputes
every weight, rewrites the weight column without touching another byte of the
CSV, and records the change as a sidecar revision; ``scripts/freeze_snapshot.py``
refuses to freeze a reference whose weights differ.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pandas as pd

from policybench.ground_truth import _impact_weight_variable_for_output
from policybench.reference_exclusions import (
    exclusions_path_for,
    load_reference_exclusions,
)

ROOT = Path(__file__).resolve().parents[1]
KEY = ["scenario_id", "variable"]
COLUMNS = ["scenario_id", "variable", "value", "impact_weight"]
REFERENCE_CSV = "reference_outputs.csv"
SIDECAR = "reference_outputs.csv.meta.json"
SCENARIOS = "scenarios.csv"
REVISION_KIND = "impact_weight_refresh"


@dataclass(frozen=True)
class ReferenceSystem:
    """The engine release and convention modules that build the references.

    Paths are relative to the repository root. ``entry`` defines ``reform``
    and ``PARTS``, the modules it composes; ``support`` holds data files the
    modules read beside themselves.
    """

    engine_version: str
    fixes: str
    entry: str
    support: tuple[str, ...]

    @property
    def engine(self) -> str:
        return f"policyengine-us {self.engine_version}"


# The 2026-09-29 references: policyengine-us 2.15.17 with latest_final
# (latest_conventions and latest_md_local_output_scope), as
# reference_audit/2026-09-28/scripts/build_references_latest.py built them.
REFERENCE_SYSTEM = ReferenceSystem(
    engine_version="2.15.17",
    fixes="reference_audit/2026-09-28/fixes",
    entry="latest_final.py",
    support=("reference_audit/2026-09-22/fixes/r19_irs_sales_tax_2025.json",),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def last_engine_revision(sidecar: dict) -> dict:
    """The sidecar's most recent engine_upgrade revision."""
    for revision in reversed(sidecar.get("revisions") or []):
        if revision.get("kind") == "engine_upgrade":
            return revision
    raise ValueError("the reference sidecar records no engine_upgrade revision")


def verify_reference_system(
    sidecar: dict,
    system: ReferenceSystem = REFERENCE_SYSTEM,
    root: Path = ROOT,
) -> None:
    """Check that ``system`` is the one the sidecar says built the references.

    The last engine_upgrade revision must name the system's engine, and every
    fix module it pins must match the file in ``system.fixes`` byte for byte.
    """
    revision = last_engine_revision(sidecar)
    if revision.get("engine_version") != system.engine:
        raise ValueError(
            f"the references were built on {revision.get('engine_version')}, "
            f"not {system.engine}"
        )
    fixes = root / system.fixes
    pinned = revision.get("fix_modules") or []
    if not pinned:
        raise ValueError("the engine_upgrade revision pins no fix modules")
    for item in pinned:
        path = fixes / item["module"]
        if not path.exists() or sha256(path) != item["sha256"]:
            raise ValueError(f"{path} does not match the sidecar's pin")


@lru_cache(maxsize=2)
def load_reference_system(
    system: ReferenceSystem = REFERENCE_SYSTEM,
    root: Path = ROOT,
) -> Any:
    """The reference tax-benefit system: the engine plus the entry's reform.

    Refuses when the installed policyengine-us is not the system's release.
    The fix modules are loaded from a scratch copy of ``system.fixes`` with
    the support files beside them, as the builder laid them out.
    """
    installed = version("policyengine-us")
    if installed != system.engine_version:
        raise RuntimeError(
            f"the reference system needs policyengine-us {system.engine_version}; "
            f"{installed} is installed"
        )
    from policyengine_us import CountryTaxBenefitSystem

    with tempfile.TemporaryDirectory(prefix="policybench_reference_system_") as tmp:
        staged = Path(tmp)
        for path in sorted((root / system.fixes).glob("*.py")):
            shutil.copy2(path, staged / path.name)
        for support in system.support:
            shutil.copy2(root / support, staged / Path(support).name)
        name = f"policybench_reference_system_{Path(system.entry).stem}"
        spec = importlib.util.spec_from_file_location(name, staged / system.entry)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return CountryTaxBenefitSystem(reform=module.reform)


def read_reference(path: Path) -> pd.DataFrame:
    """A reference CSV, its floats parsed exactly (round-trip precision)."""
    reference = pd.read_csv(path, float_precision="round_trip")
    if list(reference.columns) != COLUMNS:
        raise ValueError(f"{path} has columns {list(reference.columns)}")
    if reference.duplicated(KEY).any():
        raise ValueError(f"{path} repeats an output")
    return reference


def engine_reference_outputs(
    run_dir: Path,
    *,
    tax_benefit_system: Any = None,
) -> pd.DataFrame:
    """Every output of the run's households on the reference system.

    Reads ``scenarios.csv`` and the sidecar's ``programs`` from ``run_dir``.
    """
    from policybench.ground_truth import calculate_ground_truth
    from policybench.scenarios import scenario_from_dict

    sidecar = json.loads((run_dir / SIDECAR).read_text())
    if tax_benefit_system is None:
        verify_reference_system(sidecar)
        tax_benefit_system = load_reference_system()
    frame = pd.read_csv(run_dir / SCENARIOS)
    scenarios = [scenario_from_dict(json.loads(raw)) for raw in frame["scenario_json"]]
    return calculate_ground_truth(
        scenarios,
        programs=sidecar["programs"],
        tax_benefit_system=tax_benefit_system,
    )


def _aligned(reference: pd.DataFrame, engine: pd.DataFrame) -> pd.DataFrame:
    """The engine's value and weight on each reference row, in reference order."""
    engine = engine[COLUMNS].rename(
        columns={"value": "engine_value", "impact_weight": "engine_weight"}
    )
    if engine.duplicated(KEY).any():
        raise ValueError("the engine frame repeats an output")
    merged = reference.merge(engine, on=KEY, how="outer", indicator=True)
    unmatched = merged[merged["_merge"] != "both"]
    if not unmatched.empty:
        first = unmatched.iloc[0]
        raise ValueError(
            f"{len(unmatched)} outputs are not in both frames, e.g. "
            f"{first['scenario_id']} {first['variable']} ({first['_merge']})"
        )
    order = reference[KEY].merge(merged, on=KEY, how="left")
    order["engine_weight"] = pd.to_numeric(order["engine_weight"], errors="coerce")
    return order.drop(columns="_merge").reset_index(drop=True)


def _same(a: Any, b: Any) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    return float(a) == float(b)


def impact_weight_mismatches(
    reference: pd.DataFrame,
    engine: pd.DataFrame,
) -> pd.DataFrame:
    """Reference rows whose impact weight is not the engine's, exactly.

    A row that has a weight in one frame and none in the other counts.
    """
    aligned = _aligned(reference, engine)
    differs = [
        not _same(a, b)
        for a, b in zip(aligned["impact_weight"], aligned["engine_weight"])
    ]
    return (
        aligned.loc[differs, [*KEY, "value", "impact_weight", "engine_weight"]]
        .rename(columns={"impact_weight": "published"})
        .reset_index(drop=True)
    )


def scored_value_mismatches(
    reference: pd.DataFrame,
    engine: pd.DataFrame,
    excluded: set[tuple[str, str]],
) -> pd.DataFrame:
    """Scored reference rows whose value is not the engine's, exactly.

    Any such row means the engine frame was not computed on the system that
    built the references. Excluded rows keep the values their records name.
    """
    aligned = _aligned(reference, engine)
    scored = [
        (sid, var) not in excluded
        for sid, var in zip(aligned["scenario_id"], aligned["variable"])
    ]
    aligned = aligned[scored]
    differs = [
        not _same(a, b) for a, b in zip(aligned["value"], aligned["engine_value"])
    ]
    return aligned.loc[differs, [*KEY, "value", "engine_value"]].reset_index(drop=True)


def impact_weight_changes(
    reference: pd.DataFrame,
    engine: pd.DataFrame,
    causes: Mapping[tuple[str, str], str] | None = None,
) -> list[dict]:
    """The weight changes a refresh makes, in reference order.

    Refuses a row that would gain or lose a weight: which outputs carry one
    is fixed by the output specs, so such a row means the frames disagree on
    what the outputs are, which no refresh should paper over.
    """
    changes = []
    for row in impact_weight_mismatches(reference, engine).itertuples(index=False):
        if pd.isna(row.published) or pd.isna(row.engine_weight):
            raise ValueError(
                f"{row.scenario_id} {row.variable}: the weight would change "
                f"from {row.published} to {row.engine_weight}"
            )
        key = (row.scenario_id, row.variable)
        change = {
            "scenario_id": row.scenario_id,
            "variable": row.variable,
            "impact_weight_variable": _impact_weight_variable_for_output(
                row.variable, "us"
            ),
            "previous": float(row.published),
            "regenerated": float(row.engine_weight),
        }
        if causes is not None:
            if key not in causes:
                raise ValueError(f"no cause recorded for {key}")
            change["cause"] = causes[key]
        changes.append(change)
    return changes


def format_weight(weight: float | None) -> str:
    """A weight as the reference CSV writes it: pandas' float repr, or empty."""
    if weight is None or pd.isna(weight):
        return ""
    return repr(float(weight))


def rewrite_impact_weights(
    csv_text: str,
    weights: Mapping[tuple[str, str], float | None],
) -> str:
    """The reference CSV with each listed row's weight field replaced.

    Only the last field of a listed row changes; every other byte, the value
    column's included, is copied as it was. Rows not in ``weights`` are
    unchanged.
    """
    lines = csv_text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != ",".join(COLUMNS):
        raise ValueError("not a reference CSV")
    out = [lines[0]]
    seen = set()
    for line in lines[1:]:
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        fields = next(csv.reader(io.StringIO(body)))
        if len(fields) != len(COLUMNS) or '"' in body:
            raise ValueError(f"unexpected reference row: {body!r}")
        key = (fields[0], fields[1])
        if key in weights:
            seen.add(key)
            head = body[: body.rindex(",") + 1]
            body = head + format_weight(weights[key])
        out.append(body + ending)
    missing = set(weights) - seen
    if missing:
        raise ValueError(f"{len(missing)} listed rows are not in the CSV")
    return "".join(out)


def impact_weight_revision(
    changes: list[dict],
    *,
    date: str,
    system: ReferenceSystem = REFERENCE_SYSTEM,
    root: Path = ROOT,
    basis: str,
) -> dict:
    """The sidecar revision recording a refresh of the impact weights."""
    fixes = root / system.fixes
    entry = fixes / system.entry
    return {
        "date": date,
        "kind": REVISION_KIND,
        "root_cause": "impact_weights_not_rewritten",
        "outputs": "every output with an impact weight",
        "rule": (
            "Every impact weight equals the weight the reference system "
            "computes for its household on its own, and is 0 where the output "
            "is not eligible. The value column is unchanged."
        ),
        "basis": basis,
        "engine_version": system.engine,
        "reference_system": {
            "fix_module": system.entry,
            "fix_module_sha256": sha256(entry),
            "support": [
                {"file": Path(item).name, "sha256": sha256(root / item)}
                for item in system.support
            ],
        },
        "values_unchanged": True,
        "changed": changes,
    }


@dataclass(frozen=True)
class Refresh:
    csv_text: str
    sidecar: dict
    changes: list[dict]


def refresh_impact_weights(
    run_dir: Path,
    engine: pd.DataFrame,
    *,
    date: str,
    regenerated_at_utc: str,
    basis: str,
    causes: Mapping[tuple[str, str], str] | None = None,
) -> Refresh:
    """The run's reference CSV and sidecar with the engine's impact weights.

    Refuses unless every scored value equals the engine's (so ``engine`` was
    computed on the system that built the references) and every row keeps
    whether it carries a weight. Returns the rewritten CSV text, the sidecar
    with the refresh revision appended and the new CSV digest, and the changes.
    """
    csv_path = run_dir / REFERENCE_CSV
    reference = read_reference(csv_path)
    excluded = {
        (item["scenario_id"], item["variable"])
        for item in load_reference_exclusions(exclusions_path_for(csv_path))
    }
    values = scored_value_mismatches(reference, engine, excluded)
    if not values.empty:
        first = values.iloc[0]
        raise ValueError(
            f"{len(values)} scored values differ from the engine, e.g. "
            f"{first['scenario_id']} {first['variable']}: {first['value']} != "
            f"{first['engine_value']}"
        )
    changes = impact_weight_changes(reference, engine, causes)
    weights = {
        (item["scenario_id"], item["variable"]): item["regenerated"] for item in changes
    }
    original = csv_path.read_text()
    text = rewrite_impact_weights(original, weights)
    sidecar = json.loads((run_dir / SIDECAR).read_text())
    if changes:
        sidecar["revisions"].append(
            impact_weight_revision(changes, date=date, basis=basis)
        )
        sidecar["reference_csv_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        sidecar["regenerated_at_utc"] = regenerated_at_utc
    return Refresh(csv_text=text, sidecar=sidecar, changes=changes)


def verify_published_impact_weights(
    run_dir: Path,
    *,
    tax_benefit_system: Any = None,
) -> None:
    """Refuse a reference whose impact weights are not the reference engine's."""
    reference = read_reference(run_dir / REFERENCE_CSV)
    engine = engine_reference_outputs(run_dir, tax_benefit_system=tax_benefit_system)
    mismatches = impact_weight_mismatches(reference, engine)
    if mismatches.empty:
        return
    examples = "; ".join(
        f"{row.scenario_id} {row.variable}: {row.published} != {row.engine_weight}"
        for row in mismatches.head(3).itertuples(index=False)
    )
    raise SystemExit(
        f"{len(mismatches)} impact weights in {run_dir / REFERENCE_CSV} differ "
        f"from the reference engine's ({examples}). Refresh them with "
        "scripts/refresh_impact_weights.py write and install the result."
    )
