"""The committed reference audit backs every regenerated reference and exclusion."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "reference_audit" / "2026-09-22"
RUN_DIR = (
    ROOT
    / "paper"
    / "snapshot"
    / "20260501"
    / "runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
)
# The audit's records: the September 22 wave, and the 2026-09-24 revision that
# added r33 (release dashboard-data-20260922b excluded its output; from
# dashboard-data-20260922c, after its fix merged, the output is regenerated).
AUDIT_DATES = ("2026-09-22", "2026-09-24")
R33 = "r33_snap_child_support_treatment"
# policyengine-us#9586, squash-merged on 2026-09-24.
R33_MERGE_COMMIT = "d9e801df417352b8246a4c292a19ec082a518790"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _references() -> dict[tuple[str, str], float]:
    with (RUN_DIR / "reference_outputs.csv").open(newline="") as source:
        return {
            (row["scenario_id"], row["variable"]): float(row["value"])
            for row in csv.DictReader(source)
        }


def _exclusions() -> list[dict]:
    return _load(RUN_DIR / "reference_exclusions.json")["exclusions"]


def _revisions() -> list[dict]:
    return _load(RUN_DIR / "reference_outputs.csv.meta.json")["revisions"]


def _causes() -> dict[str, dict]:
    return {
        name: cause
        for name, cause in _load(AUDIT / "root_causes.json").items()
        if isinstance(cause, dict)
    }


def _moves() -> list[dict]:
    with (AUDIT / "sweep_moves.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    for row in rows:
        for field in ("frozen", "baseline", "recomputed", "delta"):
            row[field] = float(row[field])
        row["moved_over_1"] = row["moved_over_1"] == "True"
    return rows


def _source(revision: dict) -> str:
    if revision["kind"] == "convention":
        return revision["convention"]
    return revision["root_cause"]


def _pre_audit_references() -> dict[tuple[str, str], float]:
    """The references frozen on 2026-07-03, before any regeneration."""
    values = _references()
    for revision in _revisions():
        for change in revision["changed"]:
            values[(change["scenario_id"], change["variable"])] = change["frozen"]
    return values


def test_sweep_rows_are_internally_consistent():
    causes = _causes()
    rows = _moves()
    pre_audit = _pre_audit_references()
    # The value of every output under each source or combination a defect can be
    # measured against: a convention's rows, or a "baseline" combination's rows.
    value_under = {}
    for row in rows:
        if row["class"] in ("convention", "baseline"):
            value_under.setdefault(row["root_cause"], {})[
                (row["scenario_id"], row["variable"])
            ] = row["recomputed"]
    assert rows
    for row in rows:
        key = (row["root_cause"], row["scenario_id"], row["variable"])
        output = (row["scenario_id"], row["variable"])
        # Every module is measured from the pre-audit reference.
        assert abs(row["frozen"] - pre_audit[output]) < 1e-4, key
        assert abs(row["delta"] - (row["recomputed"] - row["baseline"])) < 1e-4, key
        if row["variable"].endswith("_eligible"):
            moved = row["recomputed"] != row["baseline"]
        else:
            moved = abs(row["recomputed"] - row["baseline"]) > 1
        assert row["moved_over_1"] == moved, key
        if row["class"] in ("screen", "baseline"):
            assert row["measured_against"] == "frozen", key
            assert row["baseline"] == row["frozen"], key
            continue
        cause = causes[row["root_cause"]]
        assert row["class"] == cause["class"], key
        expected = cause.get("measured_against", "frozen")
        assert row["measured_against"] == expected, key
        if expected == "frozen":
            assert row["baseline"] == row["frozen"], key
        else:
            # Measured on top of a convention or a combination of sources: the
            # baseline is that source's value, or the frozen value where it
            # changes nothing.
            assert expected in value_under, (key, expected)
            baseline = value_under[expected].get(output, row["frozen"])
            assert abs(row["baseline"] - baseline) < 1e-4, key


def test_every_regeneration_names_a_committed_fix():
    causes = _causes()
    references = _references()
    excluded = {(e["scenario_id"], e["variable"]) for e in _exclusions()}
    swept = {}
    for row in _moves():
        if abs(row["recomputed"] - row["baseline"]) > 1e-6:
            swept.setdefault(row["root_cause"], {})[
                (row["scenario_id"], row["variable"])
            ] = row
    revisions = _revisions()
    assert revisions
    for revision in revisions:
        module = AUDIT / "fixes" / revision["fix_module"]
        assert module.exists(), revision["fix_module"]
        digest = hashlib.sha256(module.read_bytes()).hexdigest()
        assert digest == revision["fix_module_sha256"], revision["fix_module"]
        source = _source(revision)
        if revision["kind"] == "convention":
            assert causes[source]["class"] == "convention"
        else:
            assert revision["kind"] == "upstream_fix"
            assert causes[source]["class"] == "engine_defect"
            assert causes[source]["upstream_fixed"] is True
            assert causes[source]["upstream"].startswith("fixed in ")
        changed = {(c["scenario_id"], c["variable"]): c for c in revision["changed"]}
        for key, change in changed.items():
            # A regenerated reference is scored and is the frozen CSV's value.
            assert key not in excluded, key
            assert abs(references[key] - change["regenerated"]) < 1e-6, key
        # Each source regenerates exactly the scored outputs its sweep moves.
        moved = {k for k in swept.get(source, {}) if k not in excluded}
        assert moved == set(changed), source


def test_every_convention_and_upstream_fix_has_a_revision():
    causes = _causes()
    expected = {
        name
        for name, cause in causes.items()
        if cause.get("class") == "convention" or cause.get("upstream_fixed")
    }
    assert {_source(r) for r in _revisions()} == expected


def test_every_new_exclusion_has_a_qualifying_move_of_its_class():
    causes = _causes()
    moved = {}
    for row in _moves():
        if row["moved_over_1"]:
            moved.setdefault((row["scenario_id"], row["variable"]), []).append(row)
    unlisted_texts = {
        name: cause["unlisted_input"]
        for name, cause in causes.items()
        if cause.get("class") == "unlisted_input"
    }
    new = [e for e in _exclusions() if e["decided_on"] in AUDIT_DATES]
    assert new
    for entry in new:
        key = (entry["scenario_id"], entry["variable"])
        rows = moved.get(key, [])
        if entry["reason_code"] == "reference_engine_defect":
            named = set(entry["root_cause"].split("+"))
            # An exclusion rests on defects not fixed upstream.
            assert not any(causes[c].get("upstream_fixed") for c in named), key
            supporting = {
                row["root_cause"] for row in rows if row["class"] == "engine_defect"
            }
            assert named <= supporting, (key, named, supporting)
            continue
        assert entry["reason_code"] == "reference_depends_on_unlisted_input", key
        supporting = [
            row["root_cause"]
            for row in rows
            if row["class"] == "unlisted_input"
            and unlisted_texts[row["root_cause"]] in entry["unlisted_input"]
        ]
        assert supporting, (key, entry["unlisted_input"])


def test_no_qualifying_move_is_left_unresolved():
    """A defect or unlisted-input move is excluded, or regenerated by its fix."""
    causes = _causes()
    excluded = {(e["scenario_id"], e["variable"]) for e in _exclusions()}
    regenerated_by = {}
    for revision in _revisions():
        for change in revision["changed"]:
            regenerated_by.setdefault(
                (change["scenario_id"], change["variable"]), set()
            ).add(_source(revision))
    for row in _moves():
        if row["class"] not in ("engine_defect", "unlisted_input"):
            continue
        if not row["moved_over_1"]:
            continue
        key = (row["scenario_id"], row["variable"])
        cause = causes[row["root_cause"]]
        if f"{key[0]}:{key[1]}" in cause.get("not_confirmed", {}):
            continue
        if key in excluded:
            continue
        assert cause.get("upstream_fixed"), (row["root_cause"], key)
        assert row["root_cause"] in regenerated_by.get(key, set()), (
            row["root_cause"],
            key,
        )


def test_snap_net_income_procedures_move_no_scored_reference():
    """Rounding or keeping cents in net income leaves every scored SNAP output."""
    excluded = {(e["scenario_id"], e["variable"]) for e in _exclusions()}
    references = _references()
    with (AUDIT / "snap_net_income_sensitivity.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    assert rows
    for row in rows:
        key = (row["scenario_id"], row["variable"])
        if key in excluded:
            continue
        # A scored output takes the nearest-dollar value (upstream #9318), and
        # keeping cents instead moves it by no more than the $1 tolerance.
        assert abs(float(row["nearest"]) - references[key]) < 1e-6, key
        assert abs(float(row["cents"]) - float(row["nearest"])) <= 1, key


def test_records_after_the_wave_carry_their_root_cause_date():
    """An exclusion or adjudication a later revision added (r33, 2026-09-24)
    takes its root cause's decided_on; every other audit record is the wave's."""
    causes = _causes()
    adjudications = _load(
        ROOT
        / "annotations"
        / "us_full_run_20260612_policyengine_4_16_1_populace"
        / "us_adjudications.json"
    )["adjudications"]
    adjudicated_on = {
        (e["scenario_id"], e["variable"]): e["adjudicated_on"] for e in adjudications
    }
    audit = [e for e in _exclusions() if e["decided_on"] != "2026-09-05"]
    assert audit
    for entry in audit:
        key = (entry["scenario_id"], entry["variable"])
        named = entry["root_cause"].split("+") if "root_cause" in entry else []
        expected = max(
            [causes[c].get("decided_on", AUDIT_DATES[0]) for c in named],
            default=AUDIT_DATES[0],
        )
        assert entry["decided_on"] == expected, key
        assert adjudicated_on[key] == expected, key
    # The 2026-09-24 revision added r33 alone. Release dashboard-data-20260922b
    # excluded its one output while the fix was open; policyengine-us#9586
    # merged the same day, so from dashboard-data-20260922c the output is
    # regenerated with the fix (rule 2) and no exclusion carries that date.
    assert not [e for e in _exclusions() if e["decided_on"] == AUDIT_DATES[1]]
    assert not [e for e in adjudications if e["adjudicated_on"] == AUDIT_DATES[1]]
    r33 = causes[R33]
    assert r33["class"] == "engine_defect" and r33["upstream_fixed"] is True
    assert r33["decided_on"] == AUDIT_DATES[1]
    assert r33["upstream"] == (
        "fixed in PolicyEngine/policyengine-us#9586 (merged 2026-09-24)"
    )
    assert "dashboard-data-20260922b excluded" in r33["note"]
    assert R33_MERGE_COMMIT in r33["note"]
    moved = [
        (row["scenario_id"], row["variable"])
        for row in _moves()
        if row["root_cause"] == R33
    ]
    assert moved == [("scenario_045", "snap")]


def test_r33_is_regenerated_with_the_merged_fix():
    """The r33 module embeds the merged parameter file, and its one output is
    regenerated at $0 and scored for every model."""
    module = (AUDIT / "fixes" / f"{R33}.py").read_text()
    assert f'UPSTREAM_MERGE_COMMIT = "{R33_MERGE_COMMIT}"' in module
    assert "3f15666" not in module.split('"""', 2)[2]
    (revision,) = [r for r in _revisions() if r.get("root_cause") == R33]
    assert revision["kind"] == "upstream_fix"
    assert revision["upstream"] == (
        "fixed in PolicyEngine/policyengine-us#9586 (merged 2026-09-24)"
    )
    assert revision["fix_module"] == f"{R33}.py"
    assert [
        (c["scenario_id"], c["variable"], c["regenerated"]) for c in revision["changed"]
    ] == [("scenario_045", "snap", 0.0)]
    key = ("scenario_045", "snap")
    assert _references()[key] == 0
    assert key not in {(e["scenario_id"], e["variable"]) for e in _exclusions()}
    # The SNAP convention and the minimum-rounding fix also move the output on
    # their own, so their revisions list it at the combined value.
    listing = {
        _source(r)
        for r in _revisions()
        for c in r["changed"]
        if (c["scenario_id"], c["variable"]) == key
    }
    assert listing == {"c_snap_hold_fy2026", "r28_snap_min_allotment_rounding", R33}
    # Measured on the SNAP convention, the fix moves it from $286.08 to $0.
    (row,) = [r for r in _moves() if r["root_cause"] == R33]
    assert row["measured_against"] == "c_snap_hold_fy2026"
    assert round(row["baseline"], 2) == 286.08 and row["recomputed"] == 0


def _regen_module():
    """The committed regen_references.py, loaded for its narrative tables."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "committed_regen_references", AUDIT / "scripts" / "regen_references.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reference_explanations() -> dict[tuple[str, str], str]:
    path = (
        ROOT
        / "annotations"
        / "us_full_run_20260612_policyengine_4_16_1_populace"
        / "us_case_reference_explanations.csv"
    )
    with path.open(newline="", encoding="utf-8") as source:
        return {
            (row["scenario_id"], row["variable"]): row["explanation"]
            for row in csv.DictReader(source)
        }


def test_frozen_narratives_state_the_frozen_path():
    """An excluded output whose frozen-bundle narrative misstated the engine's
    path carries the narrative rewritten from the frozen trace: it states the
    figures FROZEN_REQUIRED names, a hand-corrected one is published as
    written, and each is an excluded output that keeps its frozen reference."""
    regen = _regen_module()
    explanations = _reference_explanations()
    references = _references()
    excluded = {(e["scenario_id"], e["variable"]): e for e in _exclusions()}
    assert set(regen.HAND_CORRECTED) <= set(regen.FROZEN_NARRATIVES) | set(
        regen.REGENERATED_NARRATIVES
    )
    assert set(regen.FROZEN_REQUIRED) <= set(regen.FROZEN_NARRATIVES)
    for key in regen.FROZEN_NARRATIVES:
        assert key in excluded, key
        assert references[key] == excluded[key]["frozen_value"], key
        for figure in regen.FROZEN_REQUIRED.get(key, []):
            assert figure in explanations[key], (key, figure)
    for key, text in regen.HAND_CORRECTED.items():
        assert explanations[key] == text, key


def test_regenerated_narratives_state_the_fixed_path():
    """A regenerated output whose narrative is grounded in stated engine facts
    (REGENERATED_NARRATIVES) is scored at its regenerated value, and its
    published narrative states the figures REGENERATED_REQUIRED names."""
    regen = _regen_module()
    explanations = _reference_explanations()
    references = _references()
    excluded = {(e["scenario_id"], e["variable"]) for e in _exclusions()}
    regenerated = {
        (c["scenario_id"], c["variable"]): c["regenerated"]
        for r in _revisions()
        for c in r["changed"]
    }
    assert set(regen.REGENERATED_REQUIRED) <= set(regen.REGENERATED_NARRATIVES)
    assert not set(regen.REGENERATED_NARRATIVES) & set(regen.FROZEN_NARRATIVES)
    for key in regen.REGENERATED_NARRATIVES:
        assert key not in excluded, key
        assert references[key] == regenerated[key], key
        for figure in regen.REGENERATED_REQUIRED.get(key, []):
            assert figure in explanations[key], (key, figure)
    # scenario_045 SNAP (r33, fixed in #9586): the child support counts in
    # gross income, which is above both the 130% test and Michigan's 200% BBCE
    # limit, so the reference is $0. The ratios follow from the stated monthly
    # figures.
    key = ("scenario_045", "snap")
    narrative = explanations[key]
    assert references[key] == 0
    assert "annual 2026 SNAP amount of $0" in narrative
    assert "#9586" in narrative
    assert "287.68" not in narrative and "$24" not in narrative
    assert f"{100 * 3022.97 / 1304.17:.1f}%" == "231.8%"
    assert f"{100 * 3022.97 / 1330:.1f}%" == "227.3%"
    for figure in ("231.8%", "227.3%", "130%", "200%", "$433.33", "$1,102"):
        assert figure in narrative, figure
    assert round(3022.97 - 209 - 604.59 - 433.33 - 673.98) == 1102
