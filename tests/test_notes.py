"""Checks that published note prose stays tied to committed evidence."""

from __future__ import annotations

import csv
import gzip
import json
import re
import sys
from collections import Counter
from functools import cache
from pathlib import Path

import pytest

from policybench.snapshot_payload import read_run_payload, run_payload_path

ROOT = Path(__file__).resolve().parents[1]
NOTES_DIR = ROOT / "app/src/notes"
RUN_DIR = (
    ROOT / "paper/snapshot/20260501/runs/"
    "us_full_run_20260612_policyengine_4_16_1_populace"
)
PREDICTIONS_PATH = RUN_DIR / "predictions.csv.gz"
REFERENCES_PATH = RUN_DIR / "reference_outputs.csv"
REFERENCE_META_PATH = RUN_DIR / "reference_outputs.csv.meta.json"
PATHWAYS_PATH = ROOT / "notes/data/snap_pathways_20260901.csv"
PATHWAYS_META_PATH = PATHWAYS_PATH.with_suffix(PATHWAYS_PATH.suffix + ".meta.json")
SENSITIVITY_PATH = ROOT / "sensitivity/data/claude-fable-5-1-thinking.json"
SENSITIVITY_NOTE_PATH = ROOT / "sensitivity/claude-thinking-2026-08.md"

CLAUDE_NOTE = "2026-09-01-claude-fable-5-1-added"
SNAP_NOTE = "2026-09-03-six-snap-households"
ASTRA_NOTE = "2026-09-05-gpt-6-astra-debuts-second"
SOL6_NOTE = "2026-09-22-gpt-6-sol-debuts-first"
AUDIT_NOTE = "2026-09-22-reference-audit"
EXCLUSIONS_PATH = RUN_DIR / "reference_exclusions.json"
ADJUDICATIONS_PATH = (
    ROOT
    / "annotations"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
    / "us_adjudications.json"
)
CLAUDE_THINKING_SENSITIVITY_PATH = (
    ROOT / "sensitivity/data/claude-thinking-2026-08.json"
)
ASTRA_ROWS_PATH = ROOT / "notes/data/astra_vs_sol_20260905.csv"
TOP_MODELS = ("gpt-5.6-sol", "claude-fable-5.1", "kimi-k3")
PLACEHOLDER = re.compile(r"\{([A-Za-z][A-Za-z0-9]*)\}")

csv.field_size_limit(sys.maxsize)


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def _note(slug: str) -> dict:
    return _load_json(NOTES_DIR / f"{slug}.json")


@cache
def _dashboard() -> dict:
    return read_run_payload(RUN_DIR)


@cache
def _frozen_release() -> str:
    manifest = _load_json(ROOT / "paper/snapshot/20260501/manifest.json")
    return manifest["published_dashboard_artifact"]["tag"]


# A note keeps the release its facts were checked against. Facts of a note on
# the frozen release are recomputed here; a note on a superseded release keeps
# the facts verified when that release was frozen (git history holds the run).
SUPERSEDED_RELEASES = {
    "dashboard-data-20260901c": "2026-09-01",
    "dashboard-data-20260905c": "2026-09-05",
}
CURRENT_RELEASE_SNAPSHOT = "2026-09-22"


@cache
def _snap_predictions() -> dict[str, list[dict[str, str]]]:
    rows = {model: [] for model in TOP_MODELS}
    with gzip.open(PREDICTIONS_PATH, "rt", encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            if row["variable"] == "snap" and row["model"] in rows:
                rows[row["model"]].append(row)
    assert all(len(model_rows) == 100 for model_rows in rows.values())
    return rows


def _snap_references() -> dict[str, float]:
    with REFERENCES_PATH.open(encoding="utf-8", newline="") as source:
        return {
            row["scenario_id"]: float(row["value"])
            for row in csv.DictReader(source)
            if row["variable"] == "snap"
        }


def _display_one_decimal(value: float) -> float:
    return float(f"{value:.1f}")


def _sensitivity_row(markdown: str, label: str) -> tuple[float, float]:
    match = re.search(
        rf"^\|\s*{re.escape(label)}\s*\|"
        r"\s*([0-9.]+)\s*\([^)]*\)\s*\|"
        r"\s*(?:\*\*)?([0-9.]+)(?:\*\*)?\s*\|",
        markdown,
        re.MULTILINE,
    )
    assert match is not None
    return float(match.group(1)), float(match.group(2))


@pytest.mark.parametrize("path", sorted(NOTES_DIR.glob("*.json")))
def test_note_schema_and_placeholders(path: Path) -> None:
    note = _load_json(path)
    assert note["slug"] == path.stem
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", note["date"])
    if note["release"] == _frozen_release():
        assert note["boardSnapshot"] == CURRENT_RELEASE_SNAPSHOT
    else:
        assert note["boardSnapshot"] == SUPERSEDED_RELEASES[note["release"]]
    assert note["boardSnapshot"] <= note["date"] or note["release"] != _frozen_release()
    assert note["paragraphs"]
    assert note["data"]

    placeholders = {
        key
        for paragraph in note["paragraphs"]
        for key in PLACEHOLDER.findall(paragraph)
    }
    assert placeholders == set(note["facts"])


def _recompute_against_frozen_snapshot(note: dict) -> bool:
    """Whether the note's facts are recomputed here: only when its release is
    the frozen snapshot's. A note on a superseded release keeps the facts that
    were verified when that release was frozen; the test then checks the
    release is one the repository has published."""
    if note["release"] == _frozen_release():
        return True
    assert note["release"] in SUPERSEDED_RELEASES, note["release"]
    return False


def test_claude_fable_note_facts() -> None:
    note = _note(CLAUDE_NOTE)
    if not _recompute_against_frozen_snapshot(note):
        return
    board_rows = [
        row for row in _dashboard()["modelStats"] if row["condition"] == "no_tools"
    ]
    target = next(row for row in board_rows if row["model"] == "claude-fable-5.1")
    sensitivity = _load_json(SENSITIVITY_PATH)
    sensitivity_exact = float(sensitivity["sensitivity"]["exact"])
    markdown = SENSITIVITY_NOTE_PATH.read_text(encoding="utf-8")
    fable5_board, fable5_auto = _sensitivity_row(markdown, "Claude Fable 5")

    derived = {
        "exactRate": _display_one_decimal(target["exact"]),
        "rank": 1 + sum(row["exact"] > target["exact"] for row in board_rows),
        "nModels": len(board_rows),
        "parsed": target["nParsed"],
        "answers": target["n"],
        "autoRate": _display_one_decimal(sensitivity_exact),
        "autoRank": 1 + sum(row["exact"] > sensitivity_exact for row in board_rows),
        "fable5AutoRate": fable5_auto,
        "fable5BoardRate": fable5_board,
        "boardGap": _display_one_decimal(target["exact"] - fable5_board),
    }
    assert note["facts"] == derived
    assert sensitivity["release"] == note["release"]


def _reference_monthly_minimum() -> float:
    entries = _dashboard()["scenarioPredictions"]["scenario_030"]["snap"].values()
    explanation = next(entry["referenceExplanation"] for entry in entries)
    match = re.search(r"minimum allotment of \$([0-9.]+) per month", explanation)
    assert match is not None
    return float(match.group(1))


def _mention_count(rows: list[dict[str, str]], pattern: str) -> int:
    regex = re.compile(pattern, re.IGNORECASE)
    return sum(bool(regex.search(row["explanation"] or "")) for row in rows)


def test_six_snap_households_note_facts() -> None:
    note = _note(SNAP_NOTE)
    if not _recompute_against_frozen_snapshot(note):
        return
    references = _snap_references()
    eligible_ids = {
        scenario_id for scenario_id, value in references.items() if value > 0
    }
    predictions = _snap_predictions()
    denied_by_model = {
        model: {
            row["scenario_id"]
            for row in rows
            if row["scenario_id"] in eligible_ids
            and row["prediction"]
            and float(row["prediction"]) == 0
        }
        for model, rows in predictions.items()
    }
    denied_sets = list(denied_by_model.values())
    assert denied_sets[1:] == denied_sets[:-1]
    denied_ids = sorted(denied_sets[0])
    denied_references = {references[scenario_id] for scenario_id in denied_ids}
    assert len(denied_references) == 1

    with PATHWAYS_PATH.open(encoding="utf-8", newline="") as source:
        pathways = list(csv.DictReader(source))
    assert len(pathways) == 100
    assert all(
        abs(float(row["snap_recomputed"]) - float(row["snap_reference"])) <= 1
        for row in pathways
    )
    assert sum(row["snap_eligible"] == "True" for row in pathways) == len(eligible_ids)
    categorical_rows = [
        row for row in pathways if row["pathway"].startswith("categorical_")
    ]
    categorical_income = [
        row
        for row in pathways
        if row["pathway"] in {"categorical_income", "categorical_both"}
    ]
    categorical_assets = [
        row for row in pathways if row["pathway"] == "categorical_assets"
    ]

    pathway_meta = _load_json(PATHWAYS_META_PATH)
    reference_meta = _load_json(REFERENCE_META_PATH)
    regexes = note["mentionRegexes"]
    derived = {
        "eligibleCount": len(eligible_ids),
        "deniedCount": len(denied_ids),
        "deniedScenarios": denied_ids,
        "referenceAnnual": round(next(iter(denied_references)), 2),
        "referenceMonthly": _reference_monthly_minimum(),
        "categoricalOnlyCount": len(categorical_rows),
        "categoricalIncomeCount": len(categorical_income),
        "categoricalAssetCount": len(categorical_assets),
        "solCategoricalMentions": _mention_count(
            predictions["gpt-5.6-sol"], regexes["categorical"]
        ),
        "solAssetMentions": _mention_count(
            predictions["gpt-5.6-sol"], regexes["assets"]
        ),
        "fableBbceMentions": _mention_count(
            predictions["claude-fable-5.1"], regexes["bbce"]
        ),
        "kimiCategoricalMentions": _mention_count(
            predictions["kimi-k3"], regexes["categorical"]
        ),
        "pathwayEngineVersion": pathway_meta["policyengine_us_version"],
        "referenceEngineVersion": reference_meta["policyengine_bundles"]["us"][
            "model_version"
        ],
    }
    assert note["facts"] == derived


def test_categorical_asset_error_statements() -> None:
    predictions = _snap_predictions()
    with PATHWAYS_PATH.open(encoding="utf-8", newline="") as source:
        asset_rows = {
            row["scenario_id"]: float(row["snap_reference"])
            for row in csv.DictReader(source)
            if row["pathway"] == "categorical_assets"
        }
    assert len(asset_rows) == 4

    errors: dict[str, list[float]] = {}
    for model in ("gpt-5.6-sol", "claude-fable-5.1"):
        model_predictions = {
            row["scenario_id"]: float(row["prediction"]) for row in predictions[model]
        }
        errors[model] = [
            abs(model_predictions[scenario_id] - reference) / reference
            for scenario_id, reference in asset_rows.items()
        ]

    sol_errors = errors["gpt-5.6-sol"]
    fable_errors = errors["claude-fable-5.1"]
    assert sum(error <= 0.01 for error in sol_errors) == 3
    assert sum(0.01 < error <= 0.10 for error in sol_errors) == 1
    assert sum(error <= 0.01 for error in fable_errors) == 4


def _judge_annotations() -> dict[tuple[str, str, str], dict[str, str]]:
    path = (
        ROOT
        / "annotations/us_full_run_20260612_policyengine_4_16_1_populace"
        / "us_audit_row_annotations.csv"
    )
    with path.open(encoding="utf-8", newline="") as source:
        return {
            (row["model"], row["scenario_id"], row["variable"]): row
            for row in csv.DictReader(source)
        }


def test_astra_note_facts() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from astra_vs_sol_rows import (
        ASTRA,
        CLUSTER_ESI,
        CLUSTER_MEDICARE,
        CLUSTER_OTHER,
        SOL,
        comparison_rows,
    )

    note = _note(ASTRA_NOTE)
    if not _recompute_against_frozen_snapshot(note):
        return
    payload = _dashboard()
    annotations = _judge_annotations()

    expected_rows = comparison_rows(payload, annotations)
    with ASTRA_ROWS_PATH.open(encoding="utf-8", newline="") as source:
        committed = list(csv.DictReader(source))
    assert [
        (r["scenario_id"], r["variable"], r["direction"], r["cluster"])
        for r in committed
    ] == [
        (r["scenario_id"], r["variable"], r["direction"], r["cluster"])
        for r in expected_rows
    ]

    board_rows = [r for r in payload["modelStats"] if r["condition"] == "no_tools"]
    by_model = {r["model"]: r for r in board_rows}

    def rank(model: str) -> int:
        return 1 + sum(r["exact"] > by_model[model]["exact"] for r in board_rows)

    both_right = both_wrong = 0
    for variables in payload["scenarioPredictions"].values():
        for models in variables.values():
            astra, sol = models.get(ASTRA), models.get(SOL)
            if not astra or not sol or astra.get("scored") is False:
                continue
            hits = (astra.get("exact") == 100, sol.get("exact") == 100)
            both_right += hits == (True, True)
            both_wrong += hits == (False, False)
    astra_only = [r for r in expected_rows if r["direction"] == "astra_only"]
    sol_only = [r for r in expected_rows if r["direction"] == "sol_only"]
    excluded = {
        (e["scenarioId"], e["variable"]) for e in payload["referenceExclusions"]
    }
    regex = re.compile(note["mentionRegexes"]["esi"], re.IGNORECASE)

    def mentions(model: str) -> int:
        return sum(
            bool(regex.search(row["annotation"] or ""))
            for key, row in annotations.items()
            if key[0] == model
        )

    derived = {
        "astraExact": _display_one_decimal(by_model[ASTRA]["exact"]),
        "astraRank": rank(ASTRA),
        "nModels": len(board_rows),
        "solExact": _display_one_decimal(by_model[SOL]["exact"]),
        "fableExact": _display_one_decimal(by_model["claude-fable-5.1"]["exact"]),
        "fableRank": rank("claude-fable-5.1"),
        "scoredOutputs": by_model[ASTRA]["n"],
        "totalOutputs": by_model[ASTRA]["n"] + len(excluded),
        "excludedOutputs": len(excluded),
        "bothRight": both_right,
        "bothWrong": both_wrong,
        "astraOnlyMisses": len(astra_only),
        "solOnlyMisses": len(sol_only),
        "esiRows": sum(r["cluster"] == CLUSTER_ESI for r in astra_only),
        "medicareRows": sum(r["cluster"] == CLUSTER_MEDICARE for r in astra_only),
        "otherRows": sum(r["cluster"] == CLUSTER_OTHER for r in astra_only),
        "astraEsiMentions": mentions(ASTRA),
        "solEsiMentions": mentions(SOL),
        "solEsiRows": sum(r["cluster"] == CLUSTER_ESI for r in sol_only),
    }
    assert note["facts"] == derived
    # The excluded Medicare row the note mentions is real and outside the rows.
    assert ("scenario_074", "head_medicare_eligible") in excluded
    assert not any(
        r["scenario_id"] == "scenario_074" and "medicare" in r["variable"]
        for r in expected_rows
    )


def _rank(exact: float, rows: list[dict]) -> int:
    """1 + rows with strictly higher exact, as the app's wouldRank does."""
    return 1 + sum(row["exact"] > exact for row in rows)


def _cost_per_household(row: dict) -> float:
    return float(f"{row['costUsd'] / 100:.4f}")


def test_gpt6_sol_note_facts() -> None:
    note = _note(SOL6_NOTE)
    if not _recompute_against_frozen_snapshot(note):
        return
    board_rows = [
        row for row in _dashboard()["modelStats"] if row["condition"] == "no_tools"
    ]
    by_model = {row["model"]: row for row in board_rows}
    sol, opus, luna = (
        by_model["gpt-6-sol"],
        by_model["claude-opus-5.5"],
        by_model["gpt-6-luna"],
    )
    sol56, opus5 = by_model["gpt-5.6-sol"], by_model["claude-opus-5"]
    sensitivity = _load_json(CLAUDE_THINKING_SENSITIVITY_PATH)
    opus5_auto = float(
        sensitivity["runs"]["claude-opus-5-thinking"]["sensitivity"]["exact"]
    )
    meta = _load_json(REFERENCE_META_PATH)
    regenerated = {
        (change["scenario_id"], change.get("variable", "snap"))
        for revision in meta["revisions"]
        for change in revision["changed"]
    }
    derived = {
        "solExact": _display_one_decimal(sol["exact"]),
        "solRank": _rank(sol["exact"], board_rows),
        "nModels": len(board_rows),
        "solLead": _display_one_decimal(sol["exact"] - opus["exact"]),
        "opusExact": _display_one_decimal(opus["exact"]),
        "opusRank": _rank(opus["exact"], board_rows),
        "sol56Rank": _rank(sol56["exact"], board_rows),
        "sol56Exact": _display_one_decimal(sol56["exact"]),
        "lunaExact": _display_one_decimal(luna["exact"]),
        "lunaRank": _rank(luna["exact"], board_rows),
        "lunaCost": _cost_per_household(luna),
        "solCost": _cost_per_household(sol),
        "opusCost": _cost_per_household(opus),
        "opus5BoardExact": _display_one_decimal(opus5["exact"]),
        "opus5AutoExact": _display_one_decimal(opus5_auto),
        "opusGap": _display_one_decimal(opus["exact"] - opus5["exact"]),
        "scoredOutputs": opus["n"],
        "totalOutputs": sum(1 for _ in open(REFERENCES_PATH)) - 1,
        "regenerated": len(regenerated),
        "excluded": len(_load_json(EXCLUSIONS_PATH)["exclusions"]),
    }
    assert note["facts"] == derived
    for row in (sol, opus, luna):
        assert row["nParsed"] == row["n"]


def test_reference_audit_note_facts() -> None:
    note = _note(AUDIT_NOTE)
    if not _recompute_against_frozen_snapshot(note):
        return
    exclusions = _load_json(EXCLUSIONS_PATH)["exclusions"]
    adjudications = _load_json(ADJUDICATIONS_PATH)["adjudications"]
    flagged = [a for a in adjudications if a.get("judge_reference_suspect") is True]
    verdicts = [a["reference_verdict"] for a in flagged]
    defects = [e for e in exclusions if e["reason_code"] == "reference_engine_defect"]
    root_causes = {cause for e in defects for cause in e["root_cause"].split("+")}
    meta = _load_json(REFERENCE_META_PATH)
    regenerated = {
        (change["scenario_id"], change.get("variable", "snap"))
        for revision in meta["revisions"]
        for change in revision["changed"]
    }
    board_rows = _dashboard()["modelStats"]
    derived = {
        "flagged": len(flagged),
        "affirmed": verdicts.count("affirmed"),
        "regeneratedFlagged": verdicts.count("regenerated"),
        "unlistedFlagged": verdicts.count("unlisted_input"),
        "defectFlagged": verdicts.count("engine_defect"),
        "engineVersion": meta["policyengine_bundles"]["us"]["model_version"],
        "totalOutputs": sum(1 for _ in open(REFERENCES_PATH)) - 1,
        "defectOutputs": len(defects),
        "defectHouseholds": len({e["scenario_id"] for e in defects}),
        "defectRootCauses": len(root_causes),
        # Each flagged engine-defect verdict is one of the excluded outputs.
        "defectUnflagged": len(defects) - verdicts.count("engine_defect"),
        "unlistedOutputs": sum(
            e["reason_code"] == "reference_depends_on_unlisted_input"
            for e in exclusions
        ),
        "regenerated": len(regenerated),
        "regeneratedSnap": sum(variable == "snap" for _, variable in regenerated),
        "upstreamFixed": sum(
            1
            for revision in meta["revisions"]
            if revision.get("kind") == "upstream_fix"
        ),
        "regeneratedByFix": len(
            {
                (change["scenario_id"], change["variable"])
                for revision in meta["revisions"]
                if revision.get("kind") == "upstream_fix"
                for change in revision["changed"]
            }
        ),
        "scoredOutputs": board_rows[0]["n"],
    }
    assert len(flagged) == sum(
        verdicts.count(v)
        for v in ("affirmed", "regenerated", "unlisted_input", "engine_defect")
    )
    assert {row["n"] for row in board_rows} == {derived["scoredOutputs"]}
    flagged_defects = {
        (a["scenario_id"], a["variable"])
        for a in flagged
        if a["reference_verdict"] == "engine_defect"
    }
    assert flagged_defects <= {(e["scenario_id"], e["variable"]) for e in defects}
    assert note["facts"] == derived


BBCE_NOTE = "2026-09-23-five-snap-households-bbce"
PATHWAYS_0922_PATH = ROOT / "notes/data/snap_pathways_20260922.csv"
PATHWAYS_0922_META_PATH = PATHWAYS_0922_PATH.with_suffix(
    PATHWAYS_0922_PATH.suffix + ".meta.json"
)
BBCE_ROWS_PATH = ROOT / "notes/data/bbce_households_20260922.csv"
BBCE_ROWS_META_PATH = BBCE_ROWS_PATH.with_suffix(BBCE_ROWS_PATH.suffix + ".meta.json")
SNAP_FIX_PATH = ROOT / "reference_audit/2026-09-22/fixes/c13v3_plus_upstream_snap.py"
TOP_THREE_0922 = ("gpt-6-sol", "claude-opus-5.5", "gpt-5.6-sol")
PREFACE_UNLISTED_STATUS = (
    "Treat any unlisted numeric input as 0 and any other unlisted household "
    "fact, boolean, or status input as false."
)
PREFACE_TAKE_UP = "Assume tax filing and program take-up when required."
PREFACE_NO_INFERENCE = (
    "Do not infer unlisted income, expenses, assets, benefit receipt, rent, "
    "or health coverage."
)
PREFACE_SENTENCES = (PREFACE_UNLISTED_STATUS, PREFACE_TAKE_UP, PREFACE_NO_INFERENCE)


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _whole_or_cents(value: float) -> int | str:
    """A dollar amount as the note shows it: whole dollars as a number (the
    app adds thousands separators), otherwise a string with cents."""
    return int(value) if float(value).is_integer() else f"{value:,.2f}"


def _named_models(text: str, display_names: dict[str, str]) -> set[str]:
    """Board models whose display name appears in the text as a whole name,
    so "Claude Opus 5" does not match inside "Claude Opus 5.5"."""
    return {
        model
        for model, name in display_names.items()
        if re.search(rf"(?<![\w.-]){re.escape(name)}(?!\.?[\w-])", text)
    }


def _snap_output_references(variable: str) -> dict[str, float]:
    with REFERENCES_PATH.open(encoding="utf-8", newline="") as source:
        return {
            row["scenario_id"]: float(row["value"])
            for row in csv.DictReader(source)
            if row["variable"] == variable
        }


def test_bbce_households_note_facts() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from bbce_household_rows import bbce_households, household_rows

    note = _note(BBCE_NOTE)
    if not _recompute_against_frozen_snapshot(note):
        return
    payload = _dashboard()
    references = _snap_references()
    snap_exclusions = {
        e["scenario_id"]: e
        for e in _load_json(EXCLUSIONS_PATH)["exclusions"]
        if e["variable"] == "snap"
    }
    reference_meta = _load_json(REFERENCE_META_PATH)

    # The committed pathway recomputation is tied to these references: it
    # reproduces every scored SNAP reference, and it was run on the committed
    # scenarios, references and SNAP fix modules.
    with PATHWAYS_0922_PATH.open(encoding="utf-8", newline="") as source:
        pathways = list(csv.DictReader(source))
    pathway_meta = _load_json(PATHWAYS_0922_META_PATH)
    assert len(pathways) == 100
    for row in pathways:
        scenario_id = row["scenario_id"]
        assert float(row["snap_reference"]) == references[scenario_id]
        assert (row["snap_scored"] == "True") == (scenario_id not in snap_exclusions)
        if row["snap_scored"] == "True":
            assert abs(float(row["snap_recomputed"]) - references[scenario_id]) <= 1
    assert pathway_meta["reference_csv_sha256"] == _sha256_file(REFERENCES_PATH)
    assert pathway_meta["scenarios_sha256"] == _sha256_file(RUN_DIR / "scenarios.csv")
    assert pathway_meta["fix_module_sha256"] == _sha256_file(SNAP_FIX_PATH)
    for part, digest in pathway_meta["fix_parts_sha256"].items():
        assert _sha256_file(SNAP_FIX_PATH.parent / f"{part}.py") == digest
    engine_version = pathway_meta["policyengine_us_version"]
    assert (
        engine_version == reference_meta["policyengine_bundles"]["us"]["model_version"]
    )
    by_id = {row["scenario_id"]: row for row in pathways}

    # The five households and every model's answer for them.
    households = bbce_households(pathways)
    regexes = note["mentionRegexes"]
    rows = household_rows(payload, households, regexes["bbce"])
    with BBCE_ROWS_PATH.open(encoding="utf-8", newline="") as source:
        committed = list(csv.DictReader(source))
    assert committed == [
        {key: str(value) for key, value in row.items()} for row in rows
    ]
    rows_meta = _load_json(BBCE_ROWS_META_PATH)
    assert rows_meta["households"] == households
    assert rows_meta["mention_pattern"] == regexes["bbce"]
    assert rows_meta["release"] == note["release"] == _frozen_release()
    # The rows come from the committed run payload; the release asset is a
    # different file carrying the same US payload, pinned by the manifest.
    assert rows_meta["run_payload_sha256"] == _sha256_file(run_payload_path(RUN_DIR))
    manifest = _load_json(ROOT / "paper/snapshot/20260501/manifest.json")
    assert (
        rows_meta["release_payload_sha256"]
        == manifest["published_dashboard_artifact"]["sha256"]
    )
    assert rows_meta["rows"] == len(rows)

    five = [by_id[scenario_id] for scenario_id in households]
    amounts = {references[scenario_id] for scenario_id in households}
    minimums = {
        float(row[key])
        for row in five
        for key in ("min_allotment_jan", "min_allotment_oct")
    }
    assert len(amounts) == 1 and len(minimums) == 1
    reference_amount, minimum = amounts.pop(), minimums.pop()
    assert reference_amount == 12 * minimum
    assert {row["state"] for row in five} == {"CT", "MI", "TX", "WI"}
    assert all(int(row["household_size"]) <= 2 for row in five)
    assert all(
        float(row["expected_contribution_jan"]) > float(row["max_allotment_jan"])
        for row in five
    )
    # Every household's SNAP gross income is above the ordinary gross limit in
    # every month; the households that pass the gross test anyway are the
    # ones with an elderly or disabled member, whom the engine exempts from it.
    snap_parameters = pathway_meta["snap_parameters"]
    assert snap_parameters["2026-01-01"] == snap_parameters["2026-10-01"]
    snap_gross_limit = snap_parameters["2026-01-01"]["gross_income_limit_fpg"]
    assert all(
        float(row["gross_income_fpg_ratio_min"]) > snap_gross_limit for row in five
    )
    for row in five:
        exempt = row["elderly_or_disabled_member"] == "True"
        assert row["gross_income_test_months"] == ("12" if exempt else "0")
    # Categorical eligibility comes from the non-cash benefit: no TANF cash,
    # no SSI, and each ordinary test either holds all year or fails all year.
    tanf_references = _snap_output_references("tanf")
    ssi_references = _snap_output_references("ssi")
    for row in five:
        assert row["tanf_non_cash_eligible_months"] == "12"
        assert float(row["tanf"]) == 0
        assert tanf_references[row["scenario_id"]] == 0
        assert ssi_references[row["scenario_id"]] == 0
        for key in (
            "gross_income_test_months",
            "net_income_test_months",
            "asset_test_months",
        ):
            assert row[key] in {"0", "12"}

    board = [row for row in payload["modelStats"] if row["condition"] == "no_tools"]
    by_model = {row["model"]: row for row in board}
    predictions = payload["scenarioPredictions"]
    hits_by_household = {
        scenario_id: sum(
            row["within_1_dollar"] for row in rows if row["scenario_id"] == scenario_id
        )
        for scenario_id in households
    }
    assert hits_by_household["scenario_030"] == hits_by_household["scenario_045"] == 0
    hits_by_model = {
        model: sum(row["within_1_dollar"] for row in rows if row["model"] == model)
        for model in by_model
    }
    best = max(hits_by_model.values())
    assert [m for m, h in hits_by_model.items() if h == best] == ["gpt-6-astra"]
    assert best < len(households)
    astra = [predictions[s]["snap"]["gpt-6-astra"]["prediction"] for s in households]
    assert sorted(astra) == [0.0] * (len(households) - best) + [reference_amount] * best
    zero_all_five = [
        model
        for model in by_model
        if all(row["prediction"] == 0.0 for row in rows if row["model"] == model)
    ]
    # Answers that did not parse carry no value and no explanation; every
    # other answer has an explanation.
    missing = [row for row in rows if row["prediction"] == ""]
    for row in missing:
        entry = predictions[row["scenario_id"]]["snap"][row["model"]]
        assert entry["parsed"] is False and not entry.get("explanation")
    explained = [
        row
        for row in rows
        if (
            predictions[row["scenario_id"]]["snap"][row["model"]].get("explanation")
            or ""
        ).strip()
    ]
    assert len(explained) == len(rows) - len(missing)
    # The most common wrong amount other than $0, and twelve months of what.
    wrong_amounts = Counter(
        row["prediction"]
        for row in rows
        if row["prediction"] not in ("", 0.0) and not row["within_1_dollar"]
    ).most_common(2)
    (common_annual, common_count), (_, runner_up_count) = wrong_amounts
    assert common_count > runner_up_count
    assert float(common_annual / 12).is_integer()
    answers_common = [row for row in rows if row["prediction"] == common_annual]
    minimum_regex = re.compile("minimum", re.IGNORECASE)
    mentions = [row for row in rows if row["mentions_categorical_eligibility"]]

    # The top three on the board and their answers.
    ranks = [_rank(by_model[model]["exact"], board) for model in TOP_THREE_0922]
    assert ranks == [1, 2, 3]
    top_answers = {
        model: {s: predictions[s]["snap"][model]["prediction"] for s in households}
        for model in TOP_THREE_0922
    }
    sol6, opus, sol56 = (top_answers[model] for model in TOP_THREE_0922)
    assert [s for s, v in sol6.items() if v != 0] == ["scenario_030"]
    assert [s for s, v in opus.items() if v != 0] == ["scenario_030", "scenario_108"]
    assert set(sol56.values()) == {0.0}
    assert (
        "monthly wages"
        in predictions["scenario_030"]["snap"]["gpt-6-sol"]["explanation"]
    )
    assert (
        "financial and educational assistance are not counted"
        in predictions["scenario_030"]["snap"]["claude-opus-5.5"]["explanation"]
    )
    with (RUN_DIR / "scenarios.csv").open(encoding="utf-8", newline="") as source:
        scenario_030 = next(
            json.loads(row["scenario_json"])
            for row in csv.DictReader(source)
            if row["scenario_id"] == "scenario_030"
        )
    financial_assistance = scenario_030["adults"][0]["inputs"]["financial_assistance"]
    row_030 = by_id["scenario_030"]
    assert float(row_030["expected_contribution_jan"]) > float(
        row_030["max_allotment_jan"]
    )
    # The engine counts financial assistance as SNAP unearned income.
    for instant in ("2026-01-01", "2026-10-01"):
        assert (
            "financial_assistance"
            in pathway_meta["snap_parameters"][instant]["unearned_income_sources"]
        )
    bbce_regex = re.compile(regexes["bbce"], re.IGNORECASE)
    board_households = len(predictions)
    assert board_households == len(pathways) == len(payload["scenarios"])

    def bbce_mentions(model: str) -> int:
        entries = [variables["snap"][model] for variables in predictions.values()]
        assert len(entries) == board_households
        return sum(bool(bbce_regex.search(e.get("explanation") or "")) for e in entries)

    # The engine's BBCE rule and the four states' parameters.
    bbce = pathway_meta["bbce_parameters"]
    assert bbce["snap_categorical_eligibility_programs"] == [
        "ssi",
        "is_tanf_non_cash_eligible",
        "tanf",
    ]
    state_rules = bbce["state_tanf_non_cash"]
    assert state_rules["2026-01-01"] == state_rules["2026-10-01"]
    rules = state_rules["2026-01-01"]
    for state, rule in rules.items():
        assert (
            rule["gross_income_limit_fpg"]
            == rule["gross_income_limit_fpg_elderly_disabled"]
        )
        assert not rule["net_income_test_applies"]
        assert not rule["net_income_test_applies_elderly_disabled"]
        assert (rule["asset_limit"] is None) == (state != "TX")
    high = {rules[state]["gross_income_limit_fpg"] for state in ("CT", "MI", "WI")}
    assert len(high) == 1

    # What the prompt says, in every answer contract's variant, and the one
    # $0 explanation that argues from receipt.
    for scenario_id in households:
        variants = payload["scenarios"][scenario_id]["prompt"]
        assert set(variants) == {"tool", "json"}
        for prompt in variants.values():
            assert all(sentence in prompt for sentence in PREFACE_SENTENCES)
            assert not re.search(r"categorical|non-cash", prompt, re.IGNORECASE)
            tanf_lines = [line for line in prompt.splitlines() if "TANF" in line]
            assert tanf_lines == [
                "- tanf: annual Temporary Assistance for Needy Families (TANF) "
                "benefit amount"
            ]
    # Every quotation in the prompt paragraph is the preface's own wording.
    prompt_paragraph = next(
        paragraph for paragraph in note["paragraphs"] if "program take-up" in paragraph
    )
    quotes = re.findall(r'"([^"]+)"', prompt_paragraph)
    assert len(quotes) == len(PREFACE_SENTENCES)
    for quote, sentence in zip(quotes, PREFACE_SENTENCES):
        assert quote.rstrip(".,").lower() in sentence.lower()
    tanf_regex = re.compile(regexes["tanf"], re.IGNORECASE)
    zero_rows = [row for row in rows if row["prediction"] == 0.0]
    zero_tanf = [
        (row["model"], row["scenario_id"])
        for row in zero_rows
        if tanf_regex.search(
            predictions[row["scenario_id"]]["snap"][row["model"]]["explanation"] or ""
        )
    ]
    assert zero_tanf == [("claude-sonnet-4.6", "scenario_030")]
    sonnet = predictions["scenario_030"]["snap"]["claude-sonnet-4.6"]["explanation"]
    assert "households receiving TANF/SSI" in sonnet and "receives neither" in sonnet

    # What changed since the September 3 note.
    previous = _note(SNAP_NOTE)
    assert previous["facts"]["deniedScenarios"] == [*households, "scenario_112"]
    frozen = {float(row["snap_frozen"]) for row in five}
    frozen_jan = {float(row["frozen_engine_min_allotment_jan"]) for row in five}
    frozen_oct = {float(row["frozen_engine_min_allotment_oct"]) for row in five}
    assert len(frozen) == len(frozen_jan) == len(frozen_oct) == 1
    frozen_value, jan, oct_ = frozen.pop(), frozen_jan.pop(), frozen_oct.pop()
    assert abs(9 * jan + 3 * oct_ - frozen_value) < 0.01
    assert round(frozen_value, 2) == previous["facts"]["referenceAnnual"]
    fixes = {
        revision["root_cause"]: revision
        for revision in reference_meta["revisions"]
        if revision.get("kind") == "upstream_fix"
    }
    min_fix = fixes["r28_snap_min_allotment_rounding"]
    assert "#9162" in min_fix["upstream"]
    assert {c["scenario_id"] for c in min_fix["changed"]} >= set(households)
    excluded_112 = snap_exclusions["scenario_112"]
    assert excluded_112["reason_code"] == "reference_depends_on_unlisted_input"
    assert excluded_112["unlisted_input"] == "weekly_hours_worked_before_lsr"
    assumed_hours = re.search(
        r"the reference assumed (\d+) hours a week",
        excluded_112["alternative_reading"],
    )
    assert assumed_hours is not None
    assert "treat unlisted numeric inputs as 0" in excluded_112["alternative_reading"]
    assert (
        "Under the zero-hours reading the time limit applies"
        in excluded_112["alternative_reading"]
    )
    assert excluded_112["alternative_value"] == 0
    assert payload["scenarios"]["scenario_112"]["state"] == "TX"
    for prompt_112 in payload["scenarios"]["scenario_112"]["prompt"].values():
        assert PREFACE_UNLISTED_STATUS in prompt_112
        assert "hours" not in prompt_112.split("Provide the following")[0]
    assert {
        by_id["scenario_112"]["pathway_jan_sep"],
        by_id["scenario_112"]["pathway_oct_dec"],
    } == {"ordinary"}
    claude_note = _note(CLAUDE_NOTE)
    assert claude_note["boardSnapshot"] == previous["boardSnapshot"]

    # The models the prose names by hand, and what it says about each.
    from policybench.paper_results import MODEL_DISPLAY_NAMES

    display = {model: MODEL_DISPLAY_NAMES[model] for model in by_model}
    text = " ".join(note["paragraphs"])
    zero_tanf_model, zero_tanf_scenario = zero_tanf[0]
    assert _named_models(text, display) == {
        "gpt-6-astra",
        *TOP_THREE_0922,
        zero_tanf_model,
    }
    sol6_name, opus_name, sol56_name = (display[m] for m in TOP_THREE_0922)
    for fragment in (
        f"{display['gpt-6-astra']} gets the most",
        f"{sol6_name} answers $0 for four households and ${{sol6On030}}",
        f"{opus_name} answers ${{opusOn108}} for scenario_108",
        f"{sol56_name} answers $0 for all five",
        f"both {sol6_name} and {opus_name} compute the benefit from wages alone",
        f"the SNAP explanations of {sol6_name} mention categorical eligibility",
        f"{display[zero_tanf_model]}, on {zero_tanf_scenario}, writes",
    ):
        assert fragment in text, fragment

    derived = {
        "scoredEligible": sum(
            value > 0 and scenario_id not in snap_exclusions
            for scenario_id, value in references.items()
        ),
        "householdCount": len(households),
        "households": households,
        "referenceAmount": _whole_or_cents(reference_amount),
        "minimumMonthly": _whole_or_cents(minimum),
        "nModels": len(board),
        "answers": len(rows),
        "missingAnswers": len(missing),
        "hits": sum(hits_by_household.values()),
        "hits027": hits_by_household["scenario_027"],
        "hits073": hits_by_household["scenario_073"],
        "hits108": hits_by_household["scenario_108"],
        "zeroAllFive": len(zero_all_five),
        "astraHits": best,
        "commonAnnual": _whole_or_cents(common_annual),
        "commonMonthly": _whole_or_cents(common_annual / 12),
        "commonAnswers": len(answers_common),
        "commonAnswersMinimum": sum(
            bool(
                minimum_regex.search(
                    predictions[row["scenario_id"]]["snap"][row["model"]]["explanation"]
                    or ""
                )
            )
            for row in answers_common
        ),
        "fiveBbceMentions": len(mentions),
        "explanations": len(explained),
        "fiveBbceModels": len({row["model"] for row in mentions}),
        "fiveBbceZeros": sum(row["prediction"] == 0.0 for row in mentions),
        "sol6On030": _whole_or_cents(sol6["scenario_030"]),
        "opusOn108": _whole_or_cents(opus["scenario_108"]),
        "opusOn030": _whole_or_cents(opus["scenario_030"]),
        "financialAssistance": _whole_or_cents(financial_assistance),
        "maxAllotmentOne": _whole_or_cents(float(row_030["max_allotment_jan"])),
        "boardHouseholds": board_households,
        "sol6BbceMentions": bbce_mentions("gpt-6-sol"),
        "opusBbceMentions": bbce_mentions("claude-opus-5.5"),
        "sol56BbceMentions": bbce_mentions("gpt-5.6-sol"),
        "engineVersion": engine_version,
        "bbceGrossLimitHigh": round(100 * high.pop()),
        "bbceGrossLimitTx": round(100 * rules["TX"]["gross_income_limit_fpg"]),
        "bbceAssetLimitTx": _whole_or_cents(rules["TX"]["asset_limit"]),
        "snapGrossLimit": round(100 * snap_gross_limit),
        "failGross": sum(row["gross_income_test_months"] == "0" for row in five),
        "grossExempt": sum(row["elderly_or_disabled_member"] == "True" for row in five),
        "failNet": sum(row["net_income_test_months"] == "0" for row in five),
        "failAssets": sum(row["asset_test_months"] == "0" for row in five),
        "zeroAnswers": len(zero_rows),
        "zeroTanfMentions": len(zero_tanf),
        "previousModels": claude_note["facts"]["nModels"],
        "previousReference": f"{frozen_value:.2f}",
        "previousMonthlyJanSep": f"{jan:.2f}",
        "previousMonthlyOctDec": f"{oct_:.2f}",
        "assumedHours": int(assumed_hours.group(1)),
    }
    assert note["facts"] == derived


@pytest.mark.slow
def test_snap_pathways_20260922_regenerates() -> None:
    """Rerun the September 22 pathway recomputation and compare it with the
    committed CSV and meta, which the note test reads.

    It needs the engine version behind the references, which the repository's
    environment does not pin, so it skips elsewhere. Run it with

      PYTHONPATH=. <1.755.4 venv>/bin/python -m pytest -m slow \\
        tests/test_notes.py -k regenerates
    """
    from importlib.metadata import PackageNotFoundError, version

    committed_meta = _load_json(PATHWAYS_0922_META_PATH)
    needed = committed_meta["policyengine_us_version"]
    try:
        engine = version("policyengine-us")
    except PackageNotFoundError:
        pytest.skip("policyengine-us is not installed")
    if engine != needed:
        pytest.skip(f"needs policyengine-us {needed}, found {engine}")
    sys.path.insert(0, str(ROOT / "scripts"))
    from snap_pathways_20260922 import build, csv_text

    rows, meta = build()
    assert csv_text(rows) == PATHWAYS_0922_PATH.read_bytes().decode("utf-8")
    regenerated = json.loads(json.dumps(meta))
    for record in (regenerated, committed_meta):
        record.pop("generated_at_utc")
    assert regenerated == committed_meta
