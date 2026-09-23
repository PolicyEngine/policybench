"""Checks that published note prose stays tied to committed evidence."""

from __future__ import annotations

import csv
import gzip
import json
import re
import sys
from functools import cache
from pathlib import Path

import pytest

from policybench.snapshot_payload import read_run_payload

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
