"""Record the parameter values every PolicyBench reference reads, and where each 2026 value comes from.

For each scored reference (one scenario's one output) this script records every
parameter value the reference system reads while computing that output, then asks of
each 2026 value: is it a YAML entry dated in 2026, an older entry carried forward, a
value policyengine-core or policyengine-us computed while loading the parameter tree
(uprating, interpolation, or a projection written by ``Parameter.update``), or a value
the reference conventions (``latest_final``) set? The citations the value's YAML
carries are then classified by ``policybench.publication_sources``, which also sets
the flags and writes the report.

The reference system is the one that built the published references: policyengine-us
2.15.17 plus ``latest_final`` (reference_audit/2026-09-28/fixes), on households built
by ``Scenario.to_pe_household`` with ``partnership_se_income`` renamed, exactly as
reference_audit/2026-10-05/scripts/sweep_salt_withholding.py builds them.

How reads are recorded (policyengine-core 3.32.8, read this session):

* Formulas read parameters as ``parameters(period).gov...``. ``ParameterNode.
  _get_at_instant`` builds (and caches) a ``ParameterNodeAtInstant`` whose
  constructor evaluates every child at that instant, so wrapping leaf lookups would
  record the whole tree. Core's own ``FullTracer`` records accesses through
  ``TracingParameterNodeAtInstant``, but names a fancy-indexed read
  (``p.amount[filing_status]``) by its parent node, skips tax scales (only
  ``numpy.ndarray`` and ``ALLOWED_PARAM_TYPES`` children are recorded), and binds the
  tracer into the root's at-instant cache.
* So this script wraps ``ParameterNode._get_at_instant`` at the outermost call (a
  depth counter keeps the eager construction and tax-scale building unrecorded) and
  returns a recording proxy. The proxy records each leaf a formula reaches, names a
  fancy-indexed read element by element (``...amount.JOINT``), records a tax scale
  as a read of every bracket component, and forwards attribute writes (the HUD
  income-level formula assigns onto its parameter node). Direct ``Parameter`` and
  ``ParameterScale`` calls outside node construction (``adds`` parameter lists,
  ``parameters.gov.x(period)``) are recorded too. ``gov.abolitions.*`` switches,
  which core reads before every variable, are skipped.
* Each output is computed in a fresh ``Simulation`` with recording on, so every read
  it needs happens inside its own calculation. A sample of households is recomputed
  in reverse output order to check that no process-level cache hides a read.

Where a value comes from (policyengine-us 2.15.17 ``system.py``, read this session):
``CountryTaxBenefitSystem.__init__`` loads the YAML, interpolates, uprates
(``uprate_parameters``, which appends ``ParameterAtInstant`` entries with no file or
metadata), runs ``add_default_uprating``, applies a reform after that pipeline, and
then runs ``backdate_parameters`` (tools/parameters.py), which ``Parameter.update``s
each parameter's earliest value back to 2015-01-01. ``set_all_uprating_parameters``
(parameters/uprating_extensions.py, run first) writes the IRS uprating index and
other projections with ``Parameter.update``. This script logs every
``uprate_parameter`` addition and
every ``Parameter.update`` whose interval meets 2026, with its caller, while it builds
the plain 2.15.17 system and the reference system. A value's origin is then decided
against the plain system's entry (``policybench.publication_sources.
classify_origin``): the YAML file's own entries, then the uprating log, interpolation
metadata and the update log; a value is convention-set when the reference value
differs from the plain one or a ``latest_final`` part's update covers the instant.

The script first reproduces every published reference (|difference| <= 1e-3; binary
outputs by rounded value) from both an unrecorded household simulation and the
recorded per-output simulations, and refuses to report if any scored reference does
not reproduce.

Run from a policybench checkout with the policyengine-us 2.15.17 venv:

  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=<checkout> \\
    <triage>/.venv-pe21517/bin/python \\
      reference_audit/2026-10-05-reference-adversary/scripts/publication_sources.py \\
      --out-dir reference_audit/2026-10-05-reference-adversary/verification
"""

from __future__ import annotations

import argparse
import ast
import atexit
import importlib.util
import json
import math
import os
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
AUDIT_0928 = ROOT / "reference_audit/2026-09-28"
AUDIT_0922 = ROOT / "reference_audit/2026-09-22"
YEAR = 2026
TOLERANCE = 1e-3
BINARY_SUFFIXES = ("_eligible",)
RENAME = {"partnership_se_income": "partnership_self_employment_net_earnings"}
PAYLOAD_SHA256 = "1e029aaa87d1dfbd2ceee88419599a919dd7c9d4aba78a308ec48d008d54ae18"
SCORED_CELLS = 1928
SKIP_PREFIXES = ("gov.abolitions.",)
SCALE_COMPONENTS = ("threshold", "rate", "amount", "average_rate", "base")
REVERSE_CHECK_EVERY = 10

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _jsonable(value):
    """A recorded parameter value as JSON (numbers, bools, None, lists)."""
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    return repr(value)


def _assemble_fixes() -> Path:
    """latest_final and its parts, plus the sales tax table the IRS module reads."""
    target = Path(tempfile.mkdtemp(prefix="publication_sources_fixes_"))
    atexit.register(shutil.rmtree, target, True)
    for path in (AUDIT_0928 / "fixes").glob("*.py"):
        shutil.copy2(path, target / path.name)
    shutil.copy2(AUDIT_0922 / "fixes/r19_irs_sales_tax_2025.json", target)
    return target


def _load_reform(fix_dir: Path):
    path = fix_dir / "latest_final.py"
    spec = importlib.util.spec_from_file_location("latest_final", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["latest_final"] = module
    spec.loader.exec_module(module)
    return module.reform


def build_situation(scenario) -> dict:
    situation = scenario.to_pe_household()
    for person in situation["people"].values():
        for old, new in RENAME.items():
            if old in person:
                person[new] = person.pop(old)
    return situation


def _matches(value: float, reference: float, variable: str) -> bool:
    if variable.endswith(BINARY_SUFFIXES):
        return round(value) == round(reference)
    return abs(value - reference) <= TOLERANCE


# ---------------------------------------------------------------------------
# Read recording (worker processes)
# ---------------------------------------------------------------------------


class _Recorder:
    active = False
    depth = 0
    reads: dict = {}
    scales: set = set()
    conflicts: list = []


REC = _Recorder()
_SYSTEM = None


def _compose(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _skip(path: str) -> bool:
    return path.startswith(SKIP_PREFIXES)


def _store(path: str, instant: str, value) -> None:
    if _skip(path):
        return
    key = (path, instant)
    value = _jsonable(value)
    previous = REC.reads.setdefault(key, value)
    if previous != value and len(REC.conflicts) < 20:
        REC.conflicts.append([path, instant, previous, value])


def install_recording() -> None:
    """Wrap core's parameter lookups so formula reads are recorded (see docstring)."""
    from policyengine_core.enums import Enum, EnumArray
    from policyengine_core.parameters import (
        Parameter,
        ParameterNode,
        ParameterNodeAtInstant,
        ParameterScale,
        VectorialParameterNodeAtInstant,
    )
    from policyengine_core.taxscales import TaxScaleLike

    leaf_types = (np.ndarray, np.generic, float, int, bool, list, type(None))

    def extend(paths, key):
        if isinstance(paths, str):
            return _compose(paths, key)
        return np.array([_compose(p, key) for p in paths], dtype=object)

    def key_names(key):
        if isinstance(key, EnumArray):
            return np.asarray(key.decode_to_str()).astype(str)
        if key.dtype == object and len(key) and isinstance(key[0], Enum):
            return np.array([item.name for item in key])
        return key.astype(str)

    def extend_vector(paths, names):
        if isinstance(paths, str):
            return np.array([_compose(paths, name) for name in names], dtype=object)
        if len(paths) == 1 and len(names) != 1:
            paths = np.repeat(paths, len(names))
        return np.array(
            [_compose(p, name) for p, name in zip(paths, names)], dtype=object
        )

    def record(paths, instant, value):
        if not REC.active:
            return
        if isinstance(paths, str):
            _store(paths, instant, value)
            return
        array = np.asarray(value, dtype=object)
        elementwise = array.ndim == 1 and len(array) == len(paths)
        for index, path in enumerate(paths):
            _store(path, instant, array[index] if elementwise else value)

    def wrap(child, paths, instant):
        if isinstance(
            child, (ParameterNodeAtInstant, VectorialParameterNodeAtInstant)
        ):
            return RecordingNode(child, paths, instant)
        if isinstance(child, TaxScaleLike):
            if REC.active:
                for path in [paths] if isinstance(paths, str) else set(paths):
                    if not _skip(path):
                        REC.scales.add((path, instant))
            return child
        if isinstance(child, leaf_types):
            record(paths, instant, child)
        return child

    class RecordingNode:
        __slots__ = ("_raw", "_paths", "_instant")

        def __init__(self, raw, paths, instant):
            object.__setattr__(self, "_raw", raw)
            object.__setattr__(self, "_paths", paths)
            object.__setattr__(self, "_instant", instant)

        def __getattr__(self, key):
            child = getattr(self._raw, key)
            if key.startswith("_"):
                return child
            return wrap(child, extend(self._paths, key), self._instant)

        def __setattr__(self, key, value):
            setattr(self._raw, key, value)

        def __getitem__(self, key):
            if isinstance(key, str):
                return wrap(self._raw[key], extend(self._paths, key), self._instant)
            if hasattr(key, "__array__") and not isinstance(key, np.ndarray):
                key = np.asarray(key)
            child = self._raw[key]
            if isinstance(key, np.ndarray):
                return wrap(
                    child, extend_vector(self._paths, key_names(key)), self._instant
                )
            return wrap(child, extend(self._paths, str(key)), self._instant)

        def __iter__(self):
            return iter(self._raw)

        def __repr__(self):
            return f"RecordingNode({self._paths!r})"

    original_node = ParameterNode._get_at_instant
    original_parameter = Parameter._get_at_instant
    original_scale = ParameterScale._get_at_instant

    def node_at_instant(self, instant):
        outer = REC.active and not REC.depth
        REC.depth += 1
        try:
            raw = original_node(self, instant)
        finally:
            REC.depth -= 1
        return RecordingNode(raw, self.name, instant) if outer else raw

    def parameter_at_instant(self, instant):
        value = original_parameter(self, instant)
        if REC.active and not REC.depth:
            _store(self.name, instant, value)
        return value

    def scale_at_instant(self, instant):
        if REC.active and not REC.depth and not _skip(self.name):
            REC.scales.add((self.name, instant))
        REC.depth += 1
        try:
            return original_scale(self, instant)
        finally:
            REC.depth -= 1

    ParameterNode._get_at_instant = node_at_instant
    Parameter._get_at_instant = parameter_at_instant
    ParameterScale._get_at_instant = scale_at_instant


def _init_worker() -> None:
    global _SYSTEM
    install_recording()
    from policyengine_us import CountryTaxBenefitSystem

    _SYSTEM = CountryTaxBenefitSystem(reform=_load_reform(_assemble_fixes()))


def _output_value(sim, scenario, variable: str) -> float:
    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output

    pe_variable = _pe_variable_for_output(variable, "us")
    return float(
        _extract_person_value(sim.calculate(pe_variable, YEAR), scenario, variable)
    )


def _recorded_output(situation, scenario, variable):
    from policyengine_us import Simulation

    sim = Simulation(tax_benefit_system=_SYSTEM, situation=situation)
    REC.reads = {}
    REC.scales = set()
    REC.active = True
    try:
        value = _output_value(sim, scenario, variable)
    finally:
        REC.active = False
    return value, REC.reads, REC.scales


def record_scenario(args: tuple[str, list[str], bool]) -> dict:
    """Baseline, then one recorded fresh simulation per output, for one household."""
    from policyengine_us import Simulation

    from policybench.scenarios import scenario_from_dict

    scenario_json, variables, reverse_check = args
    scenario = scenario_from_dict(json.loads(scenario_json))
    situation = build_situation(scenario)
    started = time.time()
    REC.conflicts = []

    base = Simulation(tax_benefit_system=_SYSTEM, situation=situation)
    baseline = {v: _output_value(base, scenario, v) for v in variables}

    outputs = {}
    for variable in variables:
        value, reads, scales = _recorded_output(situation, scenario, variable)
        outputs[variable] = {
            "value": value,
            "reads": [[p, i, v] for (p, i), v in sorted(reads.items())],
            "scales": sorted([p, i] for p, i in scales),
        }

    order_mismatches = []
    if reverse_check:
        for variable in reversed(variables):
            value, reads, scales = _recorded_output(situation, scenario, variable)
            first = outputs[variable]
            same_reads = sorted(reads) == sorted(
                (p, i) for p, i, _ in first["reads"]
            )
            same_scales = sorted([p, i] for p, i in scales) == first["scales"]
            if not (same_reads and same_scales and value == first["value"]):
                order_mismatches.append(variable)

    return {
        "scenario_id": scenario.id,
        "state": scenario.state,
        "baseline": baseline,
        "outputs": outputs,
        "reverse_checked": reverse_check,
        "order_mismatches": order_mismatches,
        "value_conflicts": list(REC.conflicts),
        "seconds": time.time() - started,
    }


# ---------------------------------------------------------------------------
# Build logs (main process)
# ---------------------------------------------------------------------------

BUILD = {"label": None, "updates": [], "uprated": defaultdict(set), "fix_dir": None}


def _caller() -> tuple[str, str]:
    frame = sys._getframe(2)
    here = os.path.abspath(__file__)
    while frame is not None:
        filename = os.path.abspath(frame.f_code.co_filename)
        if "/policyengine_core/" not in filename and filename != here:
            return filename, frame.f_code.co_name
        frame = frame.f_back
    return "", ""


def _describe_caller(filename: str, function: str) -> dict:
    fix_dir = BUILD["fix_dir"]
    if fix_dir is not None and filename.startswith(str(fix_dir)):
        return {"kind": "convention", "module": Path(filename).stem, "function": function}
    marker = "/site-packages/"
    if marker in filename:
        filename = filename.split(marker, 1)[1]
    return {"kind": "load", "module": filename, "function": function}


def install_build_hooks() -> None:
    """Log uprating additions and 2026 ``Parameter.update`` calls while systems build."""
    from policyengine_core import periods
    from policyengine_core.parameters import Parameter

    # The operations package re-exports the function under the module's name.
    uprating = importlib.import_module(
        "policyengine_core.parameters.operations.uprate_parameters"
    )

    original_update = Parameter.update
    original_uprate = uprating.uprate_parameter
    last_day = f"{YEAR}-12-31"
    first_day = f"{YEAR}-01-01"

    def update(self, value=None, period=None, start=None, stop=None, remove_after=False):
        p_start, p_stop = start, stop
        if period is not None:
            p = periods.period(period) if isinstance(period, str) else period
            p_start, p_stop = p.start, p.stop
        start_str = str(p_start) if p_start is not None else "0000-01-01"
        stop_str = str(p_stop) if p_stop is not None else None
        if start_str <= last_day and (stop_str is None or stop_str >= first_day):
            filename, function = _caller()
            BUILD["updates"].append(
                {
                    "label": BUILD["label"],
                    "parameter": self.name,
                    "start": start_str,
                    "stop": stop_str,
                    "value": _jsonable(value),
                    "caller": _describe_caller(filename, function),
                }
            )
        return original_update(
            self,
            value=value,
            period=period,
            start=start,
            stop=stop,
            remove_after=remove_after,
        )

    def uprate_parameter(parameter, root, parameter_paths=None):
        before = {entry.instant_str for entry in parameter.values_list}
        original_uprate(parameter, root, parameter_paths)
        added = {entry.instant_str for entry in parameter.values_list} - before
        BUILD["uprated"][(BUILD["label"], parameter.name)].update(
            instant for instant in added if instant <= last_day
        )

    Parameter.update = update
    uprating.uprate_parameter = uprate_parameter


# ---------------------------------------------------------------------------
# Parameter facts (main process)
# ---------------------------------------------------------------------------


class Tree:
    """Name lookups, entries in effect and YAML facts for one built system."""

    def __init__(self, system, params_dir: Path, label: str):
        self.root = system.parameters
        self.params_dir = params_dir
        self.label = label
        self._cache = {}
        self._yaml_cache = {}

    def get(self, name: str):
        from policyengine_core.parameters.operations.get_parameter import (
            get_parameter,
        )

        if name not in self._cache:
            try:
                self._cache[name] = get_parameter(self.root, name)
            except ValueError:
                self._cache[name] = None
        return self._cache[name]

    @staticmethod
    def entry(parameter, instant: str):
        for entry in parameter.values_list:
            if entry.instant_str <= instant:
                return entry
        return None

    def file_root(self, file_path: str | None) -> str | None:
        if not file_path:
            return None
        path = Path(file_path)
        try:
            relative = path.resolve().relative_to(self.params_dir.resolve())
        except ValueError:
            return None
        if relative.suffix not in (".yaml", ".yml"):
            return None
        return ".".join(relative.with_suffix("").parts)

    def yaml_file(self, file_path: str):
        from policyengine_core.parameters.helpers import _load_yaml_file

        if file_path not in self._yaml_cache:
            text = Path(file_path).read_text(encoding="utf-8")
            self._yaml_cache[file_path] = (_load_yaml_file(file_path), text)
        return self._yaml_cache[file_path]


def _yaml_source(tree: Tree, parameter) -> dict | None:
    """The parameter's own YAML: file, key path, raw dated entries and file text."""
    from policybench.publication_sources import parameter_key_path

    root_name = tree.file_root(getattr(parameter, "file_path", None))
    if root_name is None or not (
        parameter.name == root_name or parameter.name.startswith(root_name)
    ):
        return None
    key_path = parameter_key_path(parameter.name, root_name)
    if key_path is None:
        return None
    data, text = tree.yaml_file(parameter.file_path)
    node = data
    for token in key_path:
        if token.startswith("["):
            if not isinstance(node, dict) or not isinstance(node.get("brackets"), list):
                return None
            index = int(token[1:-1])
            if index >= len(node["brackets"]):
                return None
            node = node["brackets"][index]
        else:
            # Breakdown keys such as household sizes load as ints.
            if not isinstance(node, dict):
                return None
            matches = [value for key, value in node.items() if str(key) == token]
            if len(matches) != 1:
                return None
            node = matches[0]
    if not isinstance(node, dict):
        return None
    values = node.get("values") if isinstance(node.get("values"), dict) else node
    entries = {}
    for key, entry in values.items():
        key = str(key)
        if len(key) != 10 or key[4] != "-" or key[7] != "-":
            continue
        if entry == "expected" or (isinstance(entry, dict) and entry.get("expected")):
            continue
        if isinstance(entry, dict):
            entries[key] = {
                "value": _jsonable(entry.get("value")),
                "reference": (entry.get("metadata") or {}).get("reference"),
            }
        else:
            entries[key] = {"value": _jsonable(entry), "reference": None}
    relative = Path(parameter.file_path).resolve().relative_to(
        tree.params_dir.resolve().parents[1]
    )
    return {
        "file": str(relative),
        "key_path": key_path,
        "entries": entries,
        "text": text,
    }


def _references(tree: Tree, parameter, yaml_source, entry_instant) -> list[dict]:
    """Citations from the value entry, the parameter and its same-file ancestors."""
    from policybench.publication_sources import ancestor_names, normalize_references

    found = []
    if yaml_source is not None and entry_instant in yaml_source["entries"]:
        found += normalize_references(
            yaml_source["entries"][entry_instant]["reference"], level="value"
        )
    found += normalize_references(parameter.metadata.get("reference"), "parameter")
    file_path = getattr(parameter, "file_path", None)
    for name in ancestor_names(parameter.name):
        node = tree.get(name)
        if node is None or getattr(node, "file_path", None) != file_path:
            continue
        metadata = getattr(node, "metadata", None) or {}
        found += normalize_references(metadata.get("reference"), level=f"file:{name}")
    unique, seen = [], set()
    for item in found:
        key = (item["title"], item["href"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _leaves(tree: Tree, path: str, instant: str, recorded=None, scale=False):
    """(leaf name, recorded value) pairs a read stands for; scales expand to leaves."""
    from policyengine_core.parameters import Parameter, ParameterScale

    node = tree.get(path)
    if scale:
        if not isinstance(node, ParameterScale):
            return [], f"scale read does not resolve to a scale: {path}"
        leaves = []
        for bracket in node.brackets:
            for component in SCALE_COMPONENTS:
                child = bracket.children.get(component)
                if isinstance(child, Parameter):
                    leaves.append((child.name, None))
        return leaves, None
    if not isinstance(node, Parameter):
        return [], f"leaf read does not resolve to a parameter: {path}"
    return [(node.name, recorded)], None


def _same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, bool) or isinstance(b, bool):
            return a == b
        return a == b or abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return a == b


def _parameter_fact(ref: Tree, plain: Tree, name: str, instant: str) -> dict:
    """Everything the report needs to know about one (parameter, instant) read."""
    from policybench.publication_sources import classify_origin

    parameter = ref.get(name)
    entry = Tree.entry(parameter, instant)
    plain_parameter = plain.get(name)
    plain_entry = Tree.entry(plain_parameter, instant) if plain_parameter else None
    yaml_source = _yaml_source(plain, plain_parameter) if plain_parameter else None
    conventions = sorted(
        {
            item["caller"]["module"]
            for item in BUILD["updates"]
            if item["label"] == "reference"
            and item["parameter"] == name
            and item["caller"]["kind"] == "convention"
            and item["start"] <= instant
            and (item["stop"] is None or item["stop"] >= instant)
        }
    )
    load_updates = [
        {
            "start": item["start"],
            "stop": item["stop"],
            "caller": f"{item['caller']['module']}:{item['caller']['function']}",
        }
        for item in BUILD["updates"]
        if item["label"] == "plain"
        and item["parameter"] == name
        and item["caller"]["kind"] == "load"
        and item["start"] <= instant
        and (item["stop"] is None or item["stop"] >= instant)
    ]
    value = _jsonable(entry.value) if entry is not None else None
    plain_value = _jsonable(plain_entry.value) if plain_entry is not None else None
    plain_instant = plain_entry.instant_str if plain_entry is not None else None
    uprating = (plain_parameter.metadata if plain_parameter else {}).get("uprating")
    origin, baseline_origin, detail = classify_origin(
        entry_instant=plain_instant,
        value=plain_value,
        yaml_entries=None if yaml_source is None else yaml_source["entries"],
        uprated_instants=BUILD["uprated"].get(("plain", name), set()),
        interpolated=bool(
            (plain_parameter.metadata if plain_parameter else {}).get("interpolation")
        ),
        load_updates=load_updates,
        reference_value=value,
        convention_modules=conventions,
        year=YEAR,
    )
    if origin == "uprated":
        detail["uprating"] = uprating
    metadata = parameter.metadata or {}
    return {
        "parameter": name,
        "instant": instant,
        "value": value,
        "entry_instant": entry.instant_str if entry is not None else None,
        "baseline_value": plain_value,
        "baseline_entry_instant": plain_instant,
        "differs_from_baseline": not _same(value, plain_value),
        "origin": origin,
        "baseline_origin": baseline_origin,
        "origin_detail": detail,
        "convention_modules": conventions,
        "indexed_parameter": uprating is not None,
        "uprating": uprating if isinstance(uprating, (str, dict)) else None,
        "label": metadata.get("label"),
        "unit": metadata.get("unit"),
        "period": metadata.get("period"),
        "description": getattr(parameter, "description", None),
        "yaml_file": None if yaml_source is None else yaml_source["file"],
        "yaml_key_path": None if yaml_source is None else yaml_source["key_path"],
        "references": _references(plain, plain_parameter, yaml_source, plain_instant)
        if plain_parameter is not None
        else [],
        "_yaml_text": None if yaml_source is None else yaml_source["text"],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _scored_cells_from_payload() -> tuple[set, str]:
    from policybench.consensus import file_sha256, load_us_payload

    path = RUN / "data.json.gz"
    sha = file_sha256(path)
    if sha != PAYLOAD_SHA256:
        raise SystemExit(f"{path}: sha256 {sha} is not the frozen {PAYLOAD_SHA256}")
    payload = load_us_payload(path)
    scored = set()
    for sid, outputs in payload["scenarioPredictions"].items():
        for variable, cell in outputs.items():
            flags = {bool(entry.get("scored")) for entry in cell.values()}
            if flags == {True}:
                scored.add((sid, variable))
            elif len(flags) > 1:
                raise SystemExit(f"{sid} {variable}: models disagree on scored")
    return scored, sha


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--scenarios", nargs="*")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--facts-out", help="also write the unclassified facts here")
    parser.add_argument(
        "--from-facts",
        help="skip the engine: rebuild the report from a --facts-out file",
    )
    args = parser.parse_args()
    if args.from_facts:
        from policybench.publication_sources import build_report, dumps_report

        saved = json.loads(Path(args.from_facts).read_text())
        report, markdown = build_report(
            saved["facts"], saved["other_instants"], saved["meta"]
        )
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "publication_sources.json").write_text(
            dumps_report(report)
        )
        (out_dir / "publication_sources.md").write_text(markdown)
        return

    started = time.time()
    install_build_hooks()
    BUILD["label"] = "plain"

    from policybench.scenarios import scenario_from_dict
    from policybench.spec import expand_programs_for_scenario

    out_dir = Path(args.out_dir)
    meta = json.loads((RUN / "reference_outputs.csv.meta.json").read_text())
    programs = meta["programs"]
    if isinstance(programs, str):
        programs = ast.literal_eval(programs)
    reference = pd.read_csv(RUN / "reference_outputs.csv")
    indexed = reference.set_index(["scenario_id", "variable"])["value"]
    exclusions = json.loads((RUN / "reference_exclusions.json").read_text())[
        "exclusions"
    ]
    excluded = {(e["scenario_id"], e["variable"]) for e in exclusions}
    scored, payload_sha = _scored_cells_from_payload()
    by_exclusion = {key for key in indexed.index if key not in excluded}
    if scored != by_exclusion or len(scored) != SCORED_CELLS:
        raise SystemExit(
            f"scored cells: payload {len(scored)}, reference rows minus exclusions "
            f"{len(by_exclusion)}, expected {SCORED_CELLS}"
        )
    scenarios = pd.read_csv(RUN / "scenarios.csv")
    if args.scenarios:
        scenarios = scenarios[scenarios["scenario_id"].isin(args.scenarios)]

    jobs = []
    for position, (_, row) in enumerate(scenarios.iterrows()):
        scenario = scenario_from_dict(json.loads(row["scenario_json"]))
        variables = [
            v
            for v in expand_programs_for_scenario(programs, scenario)
            if (scenario.id, v) in indexed.index
        ]
        jobs.append(
            (row["scenario_json"], variables, position % REVERSE_CHECK_EVERY == 0)
        )

    with ProcessPoolExecutor(
        max_workers=min(args.workers, len(jobs)), initializer=_init_worker
    ) as pool:
        futures = [pool.submit(record_scenario, job) for job in jobs]

        # Build both systems here while the workers run.
        build_started = time.time()
        import policyengine_us
        from policyengine_us import CountryTaxBenefitSystem

        plain_system = policyengine_us.system.system
        BUILD["label"] = "reference"
        BUILD["fix_dir"] = _assemble_fixes().resolve()
        reference_system = CountryTaxBenefitSystem(
            reform=_load_reform(BUILD["fix_dir"])
        )
        BUILD["label"] = None
        print(f"systems built in {time.time() - build_started:.0f}s", flush=True)

        results = []
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                f"{len(results)}/{len(jobs)} {result['scenario_id']} "
                f"{result['seconds']:.0f}s",
                flush=True,
            )
    results.sort(key=lambda r: r["scenario_id"])

    # 1. Reproduce the references; refuse to report otherwise.
    mismatches, unscored_mismatches, checked = [], [], 0
    for result in results:
        sid = result["scenario_id"]
        for variable, output in result["outputs"].items():
            ref = float(indexed[(sid, variable)])
            ok = _matches(output["value"], ref, variable) and _matches(
                result["baseline"][variable], ref, variable
            )
            checked += 1
            if not ok:
                row = [sid, variable, ref, result["baseline"][variable], output["value"]]
                (mismatches if (sid, variable) in scored else unscored_mismatches).append(
                    row
                )
    n_scored = sum(
        1
        for result in results
        for variable in result["outputs"]
        if (result["scenario_id"], variable) in scored
    )
    print(
        f"reproduction: {checked} outputs, {n_scored} scored, "
        f"{len(mismatches)} scored mismatches, {len(unscored_mismatches)} unscored"
    )
    if mismatches:
        for row in mismatches:
            print("MISMATCH", row)
        raise SystemExit("scored references do not reproduce; refusing to report")
    if not args.scenarios and n_scored != SCORED_CELLS:
        raise SystemExit(f"only {n_scored} scored cells were recomputed")

    order_mismatches = [
        [r["scenario_id"], v] for r in results for v in r["order_mismatches"]
    ]
    value_conflicts = [c for r in results for c in r["value_conflicts"]]

    # 2. Map reads to cells, expanding tax scales to their bracket leaves.
    from policybench.publication_sources import (
        build_report,
        dumps_report,
        entry_comments,
    )

    params_dir = Path(policyengine_us.__file__).parent / "parameters"
    ref_tree = Tree(reference_system, params_dir, "reference")
    plain_tree = Tree(plain_system, params_dir, "plain")
    cells_by_read = defaultdict(set)
    recorded_value = {}
    resolution_errors = set()
    for result in results:
        sid = result["scenario_id"]
        for variable, output in result["outputs"].items():
            cell = (sid, variable)
            for path, instant, value in output["reads"]:
                leaves, error = _leaves(ref_tree, path, instant, value)
                if error:
                    resolution_errors.add(error)
                for name, recorded in leaves:
                    cells_by_read[(name, instant)].add(cell)
                    recorded_value.setdefault((name, instant), recorded)
            for path, instant in output["scales"]:
                leaves, error = _leaves(ref_tree, path, instant, scale=True)
                if error:
                    resolution_errors.add(error)
                for name, _ in leaves:
                    cells_by_read[(name, instant)].add(cell)

    # 3. Cross-check each recorded leaf value against the reference tree.
    value_check = {"checked": 0, "mismatches": []}
    for (name, instant), recorded in recorded_value.items():
        if recorded is None:
            continue
        actual = _jsonable(ref_tree.get(name)(instant))
        value_check["checked"] += 1
        if not _same(actual, recorded) and len(value_check["mismatches"]) < 50:
            value_check["mismatches"].append([name, instant, recorded, actual])

    # 4. Facts per (parameter, 2026 value); other instants listed separately.
    groups = {}
    other_instants = []
    for (name, instant), cells in sorted(cells_by_read.items()):
        if not instant.startswith(str(YEAR)):
            parameter = ref_tree.get(name)
            other_instants.append(
                {
                    "parameter": name,
                    "instant": instant,
                    "value": _jsonable(parameter(instant)),
                    "scored_cells": sorted(f"{s}/{v}" for s, v in cells if (s, v) in scored),
                    "unscored_cells": sorted(
                        f"{s}/{v}" for s, v in cells if (s, v) not in scored
                    ),
                }
            )
            continue
        fact = _parameter_fact(ref_tree, plain_tree, name, instant)
        key = (name, fact["entry_instant"], json.dumps(fact["value"], sort_keys=True))
        group = groups.get(key)
        if group is None:
            text = fact.pop("_yaml_text")
            fact["yaml_comments"] = (
                entry_comments(
                    text, fact["yaml_key_path"], fact["baseline_entry_instant"]
                )
                if text is not None and fact["baseline_entry_instant"]
                else []
            )
            fact["instants"] = []
            fact["cells"] = set()
            fact.pop("instant")
            groups[key] = group = fact
        else:
            # Same value from the same entry: the origin must agree too.
            if fact["origin"] != group["origin"]:
                group.setdefault("origin_conflicts", []).append(
                    [instant, fact["origin"]]
                )
        group["instants"].append(instant)
        group["cells"] |= cells

    facts = []
    for group in groups.values():
        cells = group.pop("cells")
        group["scored_cells"] = sorted(f"{s}/{v}" for s, v in cells if (s, v) in scored)
        group["unscored_cells"] = sorted(
            f"{s}/{v}" for s, v in cells if (s, v) not in scored
        )
        facts.append(group)
    facts.sort(key=lambda f: (f["parameter"], f["entry_instant"] or ""))

    run_meta = {
        "policyengine_us": version("policyengine-us"),
        "policyengine_core": version("policyengine-core"),
        "reference_system": "policyengine-us 2.15.17 + latest_final "
        "(reference_audit/2026-09-28/fixes)",
        "payload": str((RUN / "data.json.gz").relative_to(ROOT)),
        "payload_sha256": payload_sha,
        "reference_outputs": str((RUN / "reference_outputs.csv").relative_to(ROOT)),
        "scenarios": int(len(results)),
        "outputs_recomputed": checked,
        "scored_cells_recomputed": n_scored,
        "scored_reference_mismatches": len(mismatches),
        "unscored_reference_mismatches": unscored_mismatches,
        "reverse_order_households": sum(r["reverse_checked"] for r in results),
        "reverse_order_mismatches": order_mismatches,
        "recorded_value_conflicts": value_conflicts,
        "recorded_value_check": value_check,
        "unresolved_read_paths": sorted(resolution_errors),
        "skipped_prefixes": list(SKIP_PREFIXES),
        "convention_modules_logged": sorted(
            {
                u["caller"]["module"]
                for u in BUILD["updates"]
                if u["label"] == "reference" and u["caller"]["kind"] == "convention"
            }
        ),
        "seconds": round(time.time() - started),
    }
    if args.facts_out:
        Path(args.facts_out).write_text(
            json.dumps(
                {"meta": run_meta, "facts": facts, "other_instants": other_instants},
                indent=1,
                sort_keys=True,
            )
            + "\n"
        )
    report, markdown = build_report(facts, other_instants, run_meta)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "publication_sources.json").write_text(
        dumps_report(report)
    )
    (out_dir / "publication_sources.md").write_text(markdown)
    print(markdown[:3000])


if __name__ == "__main__":
    main()
