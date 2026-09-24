"""Checks that published note prose stays tied to committed evidence."""

from __future__ import annotations

import csv
import gzip
import json
import re
import sys
from datetime import date
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
BBCE_ASSET_ROWS_PATH = ROOT / "notes/data/bbce_asset_households_20260922.csv"
BBCE_ASSET_ROWS_META_PATH = BBCE_ASSET_ROWS_PATH.with_suffix(
    BBCE_ASSET_ROWS_PATH.suffix + ".meta.json"
)
SNAP_FIX_PATH = ROOT / "reference_audit/2026-09-22/fixes/c13v3_plus_upstream_snap.py"
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
STATE_NAMES = {
    "CT": "Connecticut",
    "MI": "Michigan",
    "NC": "North Carolina",
    "NJ": "New Jersey",
    "PA": "Pennsylvania",
    "TX": "Texas",
    "VA": "Virginia",
    "WI": "Wisconsin",
}


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _whole_or_cents(value: float) -> int | str:
    """A dollar amount as the note shows it: whole dollars as a number (the
    app adds thousands separators), otherwise a string with cents."""
    return int(value) if float(value).is_integer() else f"{value:,.2f}"


def _percent(numerator: int, denominator: int) -> int:
    """A share as a whole-number percentage, rounded half up."""
    from decimal import ROUND_HALF_UP, Decimal

    share = Decimal(100 * numerator) / Decimal(denominator)
    return int(share.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _month_day(iso_date: str) -> str:
    """A date as the note writes it: "July 3"."""
    day = date.fromisoformat(iso_date)
    return f"{day:%B} {day.day}"


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


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def _scenario_inputs() -> dict[str, dict]:
    """Each household's frozen scenario: people with their inputs, and units."""
    return {
        row["scenario_id"]: json.loads(row["scenario_json"])
        for row in _read_csv(RUN_DIR / "scenarios.csv")
    }


def _person(scenario: dict, name: str) -> dict:
    """A person's inputs, with wages folded in as the prompt lists them."""
    person = next(
        p
        for group in ("adults", "children")
        for p in scenario[group]
        if p["name"] == name
    )
    return {
        "age": person["age"],
        "employment_income": person["employment_income"],
        **person["inputs"],
    }


def _household_block(prompt: str) -> str:
    """The listed household facts: from "Household:" to the requested outputs."""
    return prompt[prompt.index("Household:") : prompt.index("Provide the following")]


def _check_committed_rows(
    rows: list[dict],
    path: Path,
    meta_path: Path,
    households: list[str],
    patterns: dict[str, str],
    release: str,
) -> None:
    """The committed rows are the regenerated rows, from the committed payload
    of the note's release, with the note's own mention patterns."""
    assert _read_csv(path) == [
        {key: str(value) for key, value in row.items()} for row in rows
    ]
    meta = _load_json(meta_path)
    assert meta["households"] == households
    assert meta["mention_patterns"] == patterns
    assert meta["release"] == release == _frozen_release()
    # The rows come from the committed run payload; the release asset is a
    # different file carrying the same US payload, pinned by the manifest.
    assert meta["run_payload_sha256"] == _sha256_file(run_payload_path(RUN_DIR))
    manifest = _load_json(ROOT / "paper/snapshot/20260501/manifest.json")
    assert (
        meta["release_payload_sha256"]
        == manifest["published_dashboard_artifact"]["sha256"]
    )
    assert meta["rows"] == len(rows)


def test_bbce_households_note_facts() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from bbce_household_rows import (
        asset_household_rows,
        asset_test_households,
        bbce_households,
        household_rows,
    )

    from policybench.paper_results import MODEL_DISPLAY_NAMES

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
    scenarios = _scenario_inputs()
    text = " ".join(note["paragraphs"])

    # Every sentence of the note is pinned in full beside the evidence for it,
    # so a changed claim or a moved placeholder fails; the check at the end
    # fails on any sentence left unpinned.
    pinned: list[str] = []

    def pin(*sentences: str) -> None:
        for sentence in sentences:
            assert text.count(sentence) == 1, sentence
            pinned.append(sentence)

    # The committed pathway recomputation is tied to these references: it
    # reproduces every scored SNAP reference, and it was run on the committed
    # scenarios, references and SNAP fix modules.
    pathways = _read_csv(PATHWAYS_0922_PATH)
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
    assert (
        pathway_meta["policyengine_us_version"]
        == reference_meta["policyengine_bundles"]["us"]["model_version"]
    )
    by_id = {row["scenario_id"]: row for row in pathways}

    # Every model's answer for the five households at the minimum and the four
    # held back by savings, regenerated from the payload with the note's
    # mention patterns and compared with the committed rows.
    regexes = note["mentionRegexes"]
    households = bbce_households(pathways)
    five_patterns = {
        "mentions_categorical_eligibility": regexes["bbce"],
        "mentions_net_income_limit": regexes["netLimit"],
    }
    rows = household_rows(payload, households, five_patterns)
    _check_committed_rows(
        rows,
        BBCE_ROWS_PATH,
        BBCE_ROWS_META_PATH,
        households,
        five_patterns,
        note["release"],
    )
    asset_households = asset_test_households(pathways)
    asset_patterns = {
        "mentions_categorical_eligibility": regexes["bbce"],
        "mentions_assets": regexes["assets"],
    }
    asset_rows = asset_household_rows(payload, asset_households)
    _check_committed_rows(
        asset_rows,
        BBCE_ASSET_ROWS_PATH,
        BBCE_ASSET_ROWS_META_PATH,
        asset_households,
        asset_patterns,
        note["release"],
    )
    # "Assets" is the September 3 note's pattern.
    previous = _note(SNAP_NOTE)
    assert regexes["assets"] == previous["mentionRegexes"]["assets"]
    assert not set(households) & set(asset_households)

    # The correct amount: twelve months of the minimum benefit.
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
    assert all(
        [float(value) for value in row["monthly_snap"].split()] == [minimum] * 12
        for row in five
    )
    # At their incomes the ordinary formula pays nothing: 30% of net income is
    # at least the maximum allotment.
    assert all(
        float(row["expected_contribution_jan"]) >= float(row["max_allotment_jan"])
        for row in five
    )
    # SNAP pays every eligible household of one or two people at least the
    # minimum, and larger households none (7 CFR 273.10(e)(2)(ii)(C)). New
    # Jersey, Maryland and DC set their own minimums.
    federal_minimum = [
        row for row in pathways if row["state"] not in {"NJ", "MD", "DC"}
    ]
    for row in federal_minimum:
        small = int(row["household_size"]) <= 2
        for key in ("min_allotment_jan", "min_allotment_oct"):
            assert float(row[key]) == (minimum if small else 0)
    assert {
        int(row["household_size"])
        for row in federal_minimum
        if float(row["min_allotment_jan"]) > 0
    } == {1, 2}
    for row in pathways:
        if int(row["household_size"]) <= 2:
            assert all(
                value == 0 or value >= float(row["min_allotment_jan"])
                for value in (float(v) for v in row["monthly_snap"].split())
            )
    pin(
        "SNAP pays every eligible household of one or two people at least a "
        "minimum benefit, so a $0 answer calls the household ineligible and "
        "could keep someone who qualifies from applying.",
        "PolicyEngine puts the correct amount for each household at that "
        "minimum, ${minimumMonthly} a month or ${referenceAmount} for 2026.",
    )

    # Who the five are, and the ordinary tests each fails. Every one has gross
    # income above the ordinary gross limit; the ones that pass the gross test
    # anyway have a member the engine treats as elderly or disabled, which
    # exempts them from it, and fail the net income test instead.
    snap_parameters = pathway_meta["snap_parameters"]
    assert snap_parameters["2026-01-01"] == snap_parameters["2026-10-01"]
    snap_gross_limit = snap_parameters["2026-01-01"]["gross_income_limit_fpg"]
    for row in five:
        assert row["pathway_jan_sep"] == row["pathway_oct_dec"]
        assert row["pathway_jan_sep"] in {"categorical_income", "categorical_both"}
        assert float(row["gross_income_fpg_ratio_min"]) > snap_gross_limit
        exempt = row["elderly_or_disabled_member"] == "True"
        assert row["gross_income_test_months"] == ("12" if exempt else "0")
        for key in (
            "gross_income_test_months",
            "net_income_test_months",
            "asset_test_months",
        ):
            assert row[key] in {"0", "12"}
        assert "0" in {row["gross_income_test_months"], row["net_income_test_months"]}

    def failing(key: str) -> set[str]:
        return {row["scenario_id"] for row in five if row[key] == "0"}

    fail_gross = failing("gross_income_test_months")
    fail_net = failing("net_income_test_months")
    fail_assets = failing("asset_test_months")
    assert fail_gross == {"scenario_030", "scenario_045"}
    assert fail_net == {"scenario_027", "scenario_030", "scenario_073", "scenario_108"}
    assert fail_assets == {"scenario_027"}
    # "The two" that fail the gross test; "all three" others have an elderly
    # or disabled member and fail the net income test.
    exempt_from_gross = {
        row["scenario_id"]
        for row in five
        if row["elderly_or_disabled_member"] == "True"
    }
    assert exempt_from_gross == set(households) - fail_gross
    assert exempt_from_gross <= fail_net
    assert len(fail_gross) == 2 and len(exempt_from_gross) == 3
    states = {s: payload["scenarios"][s]["state"] for s in households}
    assert states == {
        "scenario_027": "CT",
        "scenario_030": "TX",
        "scenario_045": "MI",
        "scenario_073": "MI",
        "scenario_108": "WI",
    }
    names = {s: STATE_NAMES[state] for s, state in states.items()}
    sizes = {s: int(by_id[s]["household_size"]) for s in households}
    assert set(sizes.values()) <= {1, 2}
    # The Michigan worker who pays child support.
    worker = _person(scenarios["scenario_045"], "head")
    assert sizes["scenario_045"] == 1
    assert worker["employment_income"] > 0 and worker["child_support_expense"] > 0
    # The Texas resident with wages and financial assistance.
    texan = _person(scenarios["scenario_030"], "head")
    assert sizes["scenario_030"] == 1
    assert texan["employment_income"] > 0
    financial_assistance = texan["financial_assistance"]
    # The Connecticut couple on Social Security disability income, with savings
    # above the asset limit.
    couple = scenarios["scenario_027"]
    assert sizes["scenario_027"] == 2 and couple["filing_status"] == "joint"
    assert [p["name"] for p in couple["adults"]] == ["head", "spouse"]
    assert not couple["children"]
    couple_head = _person(couple, "head")
    assert couple_head["social_security_disability"] > 0
    savings = couple_head["bank_account_assets"]
    assert savings > 0 and not _person(couple, "spouse").get("bank_account_assets")
    # The disabled Michigan resident living alone: under 60, on Social Security
    # disability income, and counted by the engine as a disabled member.
    alone = _person(scenarios["scenario_073"], "head")
    assert sizes["scenario_073"] == 1
    assert alone["age"] < 60 and alone["social_security_disability"] > 0
    assert by_id["scenario_073"]["elderly_or_disabled_member"] == "True"
    # The surviving spouse in Wisconsin.
    widow = _person(scenarios["scenario_108"], "head")
    assert sizes["scenario_108"] == 1 and widow["is_surviving_spouse"] is True
    pin(
        "All {householdCount} households have gross income above "
        "{snapGrossLimit}% of the guideline.",
        f"A {names['scenario_045']} worker who pays child support and a "
        f"{{txAge}}-year-old {names['scenario_030']} resident with wages and "
        "${financialAssistance} of financial assistance fail SNAP's ordinary "
        "gross income test.",
        f"A {names['scenario_027']} couple on Social Security disability income, "
        f"a disabled {names['scenario_073']} resident living alone, and an "
        f"{{wiAge}}-year-old surviving spouse in {names['scenario_108']} fail "
        "SNAP's ordinary net income test.",
        "All three have an elderly or disabled member, and SNAP exempts such "
        "households from the gross income test.",
        f"The {names['scenario_027']} couple also holds ${{ctSavings}} in "
        "savings, above SNAP's asset limit.",
    )

    # The engine's BBCE rule: categorical eligibility through SSI, TANF cash,
    # or eligibility for (not receipt of) the TANF-funded non-cash benefit, and
    # the four states' limits for that benefit.
    bbce = pathway_meta["bbce_parameters"]
    assert bbce["snap_categorical_eligibility_programs"] == [
        "ssi",
        "is_tanf_non_cash_eligible",
        "tanf",
    ]
    state_rules = bbce["state_tanf_non_cash"]
    assert state_rules["2026-01-01"] == state_rules["2026-10-01"]
    rules = state_rules["2026-01-01"]
    assert set(rules) == set(states.values())
    for state, rule in rules.items():
        assert (
            rule["gross_income_limit_fpg"]
            == rule["gross_income_limit_fpg_elderly_disabled"]
        )
        assert not rule["net_income_test_applies"]
        assert not rule["net_income_test_applies_elderly_disabled"]
        assert (rule["asset_limit"] is None) == (state != "TX")
    high = max(rule["gross_income_limit_fpg"] for rule in rules.values())
    high_states = sorted(
        s for s, r in rules.items() if r["gross_income_limit_fpg"] == high
    )
    assert high_states == ["CT", "MI", "WI"]
    assert rules["TX"]["gross_income_limit_fpg"] < high
    high_limit = round(100 * high)
    # Each household is eligible for the non-cash benefit all year and under
    # its state's gross limit, and receives neither TANF cash nor SSI.
    tanf_references = _snap_output_references("tanf")
    ssi_references = _snap_output_references("ssi")
    for row in five:
        rule = rules[row["state"]]
        assert row["tanf_non_cash_eligible_months"] == "12"
        assert float(row["gross_income_fpg_ratio_min"]) < rule["gross_income_limit_fpg"]
        assert float(row["tanf"]) == 0
        assert tanf_references[row["scenario_id"]] == 0
        assert ssi_references[row["scenario_id"]] == 0
    high_names = [STATE_NAMES[s] for s in high_states]
    texas = names["scenario_030"]
    assert set(rules) - set(high_states) == {states["scenario_030"]}
    pin(
        "Each household qualifies only through broad-based categorical "
        "eligibility (BBCE).",
        # The rule, 7 CFR 273.2(j)(2)(ii): every member "receive[s] or [is]
        # authorized to receive" the TANF-funded non-cash service.
        "Under BBCE, a state extends SNAP to households that receive, or are "
        "authorized to receive, a non-cash benefit funded by Temporary "
        "Assistance for Needy Families (TANF).",
        f"{', '.join(high_names[:-1])}, and {high_names[-1]} open that benefit "
        "to households with gross income up to {bbceGrossLimitHigh}% of the "
        f"federal poverty guideline, and {texas} up to {{bbceGrossLimitTx}}%, "
        "against SNAP's ordinary limit of {snapGrossLimit}%.",
        "None of these states applies a net income test to the benefit, and "
        f"only {texas} keeps an asset limit.",
        "Each household has one or two people and falls under its state's BBCE "
        "limit, and at these incomes SNAP's ordinary formula pays nothing, so "
        "each gets the minimum.",
    )

    # The households held back by savings: they pass both income tests all
    # year, fail the asset test, qualify through BBCE, and get a benefit.
    held_back = [by_id[scenario_id] for scenario_id in asset_households]
    for row in held_back:
        assert row["gross_income_test_months"] == row["net_income_test_months"] == "12"
        assert row["asset_test_months"] == "0"
        assert row["tanf_non_cash_eligible_months"] == "12"
        assert float(row["snap_recomputed"]) > 0
        head = _person(scenarios[row["scenario_id"]], "head")
        spouse = next(
            (
                _person(scenarios[row["scenario_id"]], "spouse")
                for p in scenarios[row["scenario_id"]]["adults"]
                if p["name"] == "spouse"
            ),
            {},
        )
        assert (
            head.get("bank_account_assets", 0) + spouse.get("bank_account_assets", 0)
            > 0
        )
    asset_states = [STATE_NAMES[row["state"]] for row in held_back]
    pin(
        "PolicyBench also asks models about households in "
        f"{', '.join(asset_states[:-1])}, and {asset_states[-1]} that pass "
        "SNAP's income tests but hold savings above its asset limit, which BBCE "
        "removes in those states."
    )

    # The answers. Answers that did not parse carry no value and no
    # explanation; every other answer has an explanation.
    board = [row for row in payload["modelStats"] if row["condition"] == "no_tools"]
    by_model = {row["model"]: row for row in board}
    predictions = payload["scenarioPredictions"]
    display = {model: MODEL_DISPLAY_NAMES[model] for model in by_model}
    astra, opus_name, sol6_name = (
        display[m] for m in ("gpt-6-astra", "claude-opus-5.5", "gpt-6-sol")
    )

    def explanation(scenario_id: str, model: str) -> str:
        return predictions[scenario_id]["snap"][model].get("explanation") or ""

    assert len(rows) == len(board) * len(households)
    missing = [row for row in rows if row["prediction"] == ""]
    for row in missing:
        entry = predictions[row["scenario_id"]]["snap"][row["model"]]
        assert entry["parsed"] is False and not entry.get("explanation")
    explained = [
        row for row in rows if explanation(row["scenario_id"], row["model"]).strip()
    ]
    assert len(explained) == len(rows) - len(missing)
    zero_rows = [row for row in rows if row["prediction"] == 0.0]
    above_zero = [row for row in rows if row["prediction"] not in ("", 0.0)]
    assert all(row["prediction"] > 0 for row in above_zero)
    # Most models answer $0 for each of the five, and most miss the minimum.
    for scenario_id in households:
        zeros = sum(row["scenario_id"] == scenario_id for row in zero_rows)
        assert 2 * zeros > len(board), scenario_id
        hits_here = sum(
            row["within_1_dollar"] for row in rows if row["scenario_id"] == scenario_id
        )
        assert 2 * hits_here < len(board), scenario_id
    assert note["title"] == (
        "Most models miss SNAP's minimum benefit when broad-based categorical "
        "eligibility lifts the income limits"
    )
    pin(
        "For each of {householdCount} households that qualify for SNAP food "
        "benefits, most of the {nModels} models on PolicyBench answer $0.",
        "Of the {answers} answers PolicyBench requests for these households, "
        "{zeroAnswers} come to $0 and {hits} match the correct amount.",
    )
    hits_by_model = {
        model: sum(row["within_1_dollar"] for row in rows if row["model"] == model)
        for model in by_model
    }

    # Most models answer above $0 for each household held back by savings.
    asset_above_zero = [row for row in asset_rows if row["prediction"] not in ("", 0.0)]
    assert all(row["prediction"] > 0 for row in asset_above_zero)
    for scenario_id in asset_households:
        above = sum(row["scenario_id"] == scenario_id for row in asset_above_zero)
        assert 2 * above > len(board), scenario_id
    pin(
        "When savings rather than income stand in the way, most models answer "
        "above $0.",
        "For those {assetOnlyCount} households, {assetOnlyAbove0Share}% of "
        "answers come in above $0, against {fiveAbove0Share}% for the "
        "{householdCount} held back by income.",
    )
    asset_explained = [
        row
        for row in asset_rows
        if explanation(row["scenario_id"], row["model"]).strip()
    ]
    asset_mentions = [
        row for row in asset_rows if row["mentions_categorical_eligibility"]
    ]
    # The two models the prose names answer above $0 on every household held
    # back by savings and $0 on each of the five.
    for model in ("gpt-5.6-sol", "claude-fable-5.1"):
        assert all(
            row["prediction"] not in ("", 0.0)
            for row in asset_rows
            if row["model"] == model
        )
        assert all(row["prediction"] == 0.0 for row in rows if row["model"] == model)
    pin(
        f"{display['gpt-5.6-sol']} and {display['claude-fable-5.1']} answer "
        "above $0 for each household held back by savings and $0 for each of "
        "the {householdCount} held back by income."
    )
    five_mentions = [row for row in rows if row["mentions_categorical_eligibility"]]
    five_mention_zeros = [row for row in five_mentions if row["prediction"] == 0.0]
    # Every prompt asks for an explanation of each answer. The BBCE pattern
    # counts the name and "categorical eligibility"; the net income pattern
    # counts a net income limit or test (or its 100%-of-poverty level), which
    # none of the four states applies under BBCE (above).
    for scenario in payload["scenarios"].values():
        for prompt in scenario["prompt"].values():
            assert (
                "a numeric `value` and a non-empty, specific, concise "
                "`explanation`" in prompt
            )
    assert regexes["bbce"] == r"broad-based|\bbbce\b|categorical(?:ly)? eligib"
    assert regexes["netLimit"].startswith(r"\bnet[- ](?:income[- ])?(?:limit|test|")
    pin(
        "PolicyBench asks each model to explain every answer.",
        "For the households held back by savings, {assetOnlyBbceMentions} of "
        "{assetOnlyExplanations} explanations mention BBCE, by name or as "
        "categorical eligibility, and {assetOnlyBbceAssets} of those also "
        "mention assets.",
        "For the {householdCount} held back by income, {fiveBbceMentions} of "
        "{explanations} explanations mention BBCE, and {fiveBbceZeros} of those "
        "still end at $0.",
        "Of those {fiveBbceZeros}, {fiveBbceZeroWithNetLimit} mention a net "
        "income limit or test, though none of these households' states applies "
        "one under BBCE.",
    )

    # GPT-6 Astra gets the most, each hit citing its state's high gross limit
    # for categorical eligibility, and answers $0 for the two households that
    # fail the ordinary gross test.
    best = max(hits_by_model.values())
    assert [m for m, h in hits_by_model.items() if h == best] == ["gpt-6-astra"]
    astra_answers = {
        s: predictions[s]["snap"]["gpt-6-astra"]["prediction"] for s in households
    }
    astra_hits = sorted(
        s for s in households if predictions[s]["snap"]["gpt-6-astra"]["exact"] == 100
    )
    assert len(astra_hits) == best
    for scenario_id in astra_hits:
        assert states[scenario_id] in high_states
        assert (
            f"{STATE_NAMES[states[scenario_id]]}'s {high_limit}%-of-poverty categorical"
        ) in explanation(scenario_id, "gpt-6-astra")
    assert {s for s, v in astra_answers.items() if v == 0} == fail_gross
    assert set(astra_hits) | fail_gross == set(households)
    pin(
        f"{astra} gets {{astraHits}} of the {{householdCount}} households right, "
        "more than any other model, and cites the state's BBCE limit of "
        "{bbceGrossLimitHigh}% of the guideline each time.",
        f"It answers $0 for the {names['scenario_030']} resident and the "
        f"{names['scenario_045']} worker, the two households that fail SNAP's "
        "ordinary gross income test.",
    )

    # Claude Opus 5.5: the minimum for the Wisconsin surviving spouse, citing
    # Wisconsin's BBCE and its gross limit; $0 for the Connecticut couple and
    # the Michigan resident on disability income, citing the net income limit.
    opus = {
        s: predictions[s]["snap"]["claude-opus-5.5"]["prediction"] for s in households
    }
    assert opus["scenario_108"] == reference_amount
    opus_108 = explanation("scenario_108", "claude-opus-5.5")
    assert "Wisconsin's broad-based categorical eligibility" in opus_108
    assert f"under {high_limit}% FPL" in opus_108
    net_regex = re.compile(regexes["netLimit"], re.IGNORECASE)
    bbce_regex = re.compile(regexes["bbce"], re.IGNORECASE)
    for scenario_id in ("scenario_027", "scenario_073"):
        assert opus[scenario_id] == 0
        opus_text = explanation(scenario_id, "claude-opus-5.5")
        assert "net income limit" in opus_text and net_regex.search(opus_text)
        assert not bbce_regex.search(opus_text)
        assert rules[states[scenario_id]]["net_income_test_applies"] is False
    pin(
        f"{opus_name} answers ${{opusOn108}} for the {names['scenario_108']} "
        f"surviving spouse, citing {names['scenario_108']}'s BBCE and its "
        "{bbceGrossLimitHigh}% limit.",
        f"For the {names['scenario_027']} couple and the disabled "
        f"{names['scenario_073']} resident it answers $0, citing SNAP's "
        "ordinary net income test, which BBCE removes in both states.",
    )

    # GPT-6 Sol leads the board; its answers and its BBCE mentions across the
    # whole board, one explanation for each household.
    assert _rank(by_model["gpt-6-sol"]["exact"], board) == 1
    sol6 = {s: predictions[s]["snap"]["gpt-6-sol"]["prediction"] for s in households}
    assert [s for s, v in sol6.items() if v != 0] == ["scenario_030"]
    board_households = len(predictions)
    assert board_households == len(pathways) == len(payload["scenarios"])
    assert board_households == sum(
        bool(explanation(scenario_id, "gpt-6-sol").strip())
        for scenario_id in predictions
    )

    def bbce_mentions(model: str) -> int:
        entries = [variables["snap"][model] for variables in predictions.values()]
        assert len(entries) == board_households
        return sum(bool(bbce_regex.search(e.get("explanation") or "")) for e in entries)

    pin(
        f"{sol6_name}, which leads PolicyBench overall, answers $0 for "
        "{sol6ZeroCount} of the {householdCount} and mentions BBCE in "
        "{sol6BbceMentions} of its {boardHouseholds} SNAP explanations."
    )

    # The Texas resident: both models compute an ordinary benefit from wages
    # alone; the engine counts the financial assistance (and not the
    # educational assistance) as income, which takes the household above the
    # ordinary gross and net limits and leaves BBCE as its only route.
    assert sol6["scenario_030"] > 0 and opus["scenario_030"] > 0
    assert "monthly wages" in explanation("scenario_030", "gpt-6-sol")
    assert "financial and educational assistance are not counted" in explanation(
        "scenario_030", "claude-opus-5.5"
    )
    for instant in ("2026-01-01", "2026-10-01"):
        sources = snap_parameters[instant]["unearned_income_sources"]
        assert "financial_assistance" in sources
        assert "educational_assistance" not in sources
    row_030 = by_id["scenario_030"]
    ratio_030 = float(row_030["gross_income_fpg_ratio_min"])
    wages_030 = texan["employment_income"]
    wages_only_ratio = ratio_030 * wages_030 / (wages_030 + financial_assistance)
    assert wages_only_ratio < snap_gross_limit < ratio_030
    assert "scenario_030" in fail_gross & fail_net
    assert row_030["pathway_jan_sep"] == "categorical_income"
    # The prompt labels the money only "financial assistance".
    for prompt in payload["scenarios"]["scenario_030"]["prompt"].values():
        lines = [
            line
            for line in _household_block(prompt).splitlines()
            if "financial" in line.lower()
        ]
        assert lines == [f"- financial assistance: ${financial_assistance:,.0f}"]
    texas_paragraph = next(p for p in note["paragraphs"] if "labels that money" in p)
    assert re.findall(r'"([^"]+)"', texas_paragraph) == ["financial assistance"]
    pin(
        f"For the {names['scenario_030']} resident, {sol6_name} answers "
        f"${{sol6On030}} and {opus_name} answers ${{opusOn030}}, and both "
        "compute an ordinary benefit from wages alone.",
        "PolicyEngine also counts the ${financialAssistance} of financial "
        "assistance as income, which puts the household above SNAP's ordinary "
        "limits and leaves BBCE as its only route.",
        'The prompt labels that money only "financial assistance", so both '
        "answers turn on what counts as income, not on BBCE.",
    )

    # What the prompt says, in every household's prompt and every answer
    # contract's variant.
    all_prompts = [
        prompt
        for scenario in payload["scenarios"].values()
        for prompt in scenario["prompt"].values()
    ]
    assert len(all_prompts) == 2 * board_households
    for scenario in payload["scenarios"].values():
        assert set(scenario["prompt"]) == {"tool", "json"}
    for prompt in all_prompts:
        assert all(sentence in prompt for sentence in PREFACE_SENTENCES)
        assert not re.search("categorical", prompt, re.IGNORECASE)
        # "Non-cash" appears only in charitable non-cash donations.
        assert not re.search(
            "non-cash",
            prompt.replace("charitable non-cash donations", ""),
            re.IGNORECASE,
        )
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
    pin(
        "Prompts mention TANF only to ask for the household's TANF amount, and "
        "none mentions the non-cash benefit.",
        "Every prompt tells the model to treat any unlisted household fact or "
        'status "as false", to assume "program take-up when required", and not '
        'to infer unlisted "benefit receipt".',
        # The engine checks is_tanf_non_cash_eligible (above).
        "PolicyEngine applies BBCE to any household eligible for the non-cash "
        "benefit, without checking whether the household receives it or is "
        "authorized to receive it.",
        # Each fails the gross or the net income test, and none receives TANF
        # cash or SSI (above).
        "A model that requires receipt or authorization falls back on SNAP's "
        "ordinary tests, and each of the {householdCount} fails at least one.",
    )
    # The one $0 explanation that mentions TANF argues from receipt.
    tanf_regex = re.compile(regexes["tanf"], re.IGNORECASE)
    zero_tanf = [
        (row["model"], row["scenario_id"])
        for row in zero_rows
        if tanf_regex.search(explanation(row["scenario_id"], row["model"]))
    ]
    assert zero_tanf == [("claude-sonnet-4.6", "scenario_030")]
    zero_tanf_model, zero_tanf_household = zero_tanf[0]
    sonnet = explanation(zero_tanf_household, zero_tanf_model)
    assert "households receiving TANF/SSI" in sonnet and "receives neither" in sonnet
    pin(
        "Of the {zeroAnswers} $0 answers, {zeroTanfMentions} mentions TANF: "
        f"{display[zero_tanf_model]} writes that the "
        f"{names[zero_tanf_household]} resident receives neither TANF nor SSI."
    )

    # What changed since the September 3 note.
    assert previous["facts"]["deniedScenarios"] == [*households, "scenario_112"]
    assert previous["facts"]["deniedCount"] == len(previous["facts"]["deniedScenarios"])
    previous_text = " ".join(previous["paragraphs"])
    frozen = {float(row["snap_frozen"]) for row in five}
    frozen_jan = {float(row["frozen_engine_min_allotment_jan"]) for row in five}
    frozen_oct = {float(row["frozen_engine_min_allotment_oct"]) for row in five}
    assert len(frozen) == len(frozen_jan) == len(frozen_oct) == 1
    frozen_value, jan, oct_ = frozen.pop(), frozen_jan.pop(), frozen_oct.pop()
    assert abs(9 * jan + 3 * oct_ - frozen_value) < 0.01
    assert round(frozen_value, 2) == previous["facts"]["referenceAnnual"]
    assert jan == previous["facts"]["referenceMonthly"]
    # The October value was projected: USDA published FY2027 after the freeze,
    # and the frozen engine's October minimum differs from the FY2026 one.
    conventions = {
        revision["convention"]: revision
        for revision in reference_meta["revisions"]
        if revision.get("kind") == "convention"
    }
    hold_rule = conventions["c_snap_hold_fy2026"]["rule"]
    freeze = re.search(r"the (\d{4}-\d{2}-\d{2}) reference freeze", hold_rule)
    fy2027 = re.search(r"USDA published FY2027 on (\d{4}-\d{2}-\d{2})", hold_rule)
    assert freeze and fy2027 and freeze.group(1) < fy2027.group(1)
    assert oct_ != jan
    fixes = {
        revision["root_cause"]: revision
        for revision in reference_meta["revisions"]
        if revision.get("kind") == "upstream_fix"
    }
    min_fix = fixes["r28_snap_min_allotment_rounding"]
    assert "rounded to the nearest whole dollar" in min_fix["rule"]
    assert {c["scenario_id"] for c in min_fix["changed"]} >= set(households)
    assert min_fix["date"] == note["boardSnapshot"]
    assert "PolicyEngine/policyengine-us#9162" in min_fix["upstream"]
    merged = re.search(r"#9162 \(merged (\d{4}-\d{2}-\d{2})\)", min_fix["upstream"])
    assert merged is not None
    pin(
        f"The {_month_day(previous['date'])} note counted "
        "{previousHouseholdCount} households at ${previousReference} each; "
        "PolicyBench now scores {householdCount} of them, at ${referenceAmount}.",
        "The ${previousReference} came from the correct amounts PolicyBench "
        f"froze on {_month_day(freeze.group(1))}, which used an unrounded "
        "minimum: ${previousMonthlyJanSep} a month through September and a "
        "projected ${previousMonthlyOctDec} from October.",
        "PolicyEngine began rounding the minimum to the nearest dollar on "
        f"{_month_day(merged.group(1))} (policyengine-us #9162), and "
        f"PolicyBench's {_month_day(note['boardSnapshot'])} amounts apply that "
        "fix.",
    )
    # The household the note no longer scores: its reference assumed hours the
    # prompt does not list, and under the prompt's zero reading the engine
    # gives $0, the answer of the September 3 note's top three models.
    excluded_112 = snap_exclusions["scenario_112"]
    assert excluded_112["reason_code"] == "reference_depends_on_unlisted_input"
    assert excluded_112["unlisted_input"] == "weekly_hours_worked_before_lsr"
    alternative_reading = excluded_112["alternative_reading"]
    assumed_hours = re.search(
        r"the reference assumed (\d+) hours a week", alternative_reading
    )
    assert assumed_hours is not None
    assert "treat unlisted numeric inputs as 0" in alternative_reading
    assert "able-bodied adults without dependents" in alternative_reading
    assert "Under the zero-hours reading the time limit applies" in alternative_reading
    assert excluded_112["alternative_value"] == 0
    assert payload["scenarios"]["scenario_112"]["state"] == "TX"
    for prompt_112 in payload["scenarios"]["scenario_112"]["prompt"].values():
        assert PREFACE_UNLISTED_STATUS in prompt_112
        assert "hours" not in _household_block(prompt_112)
    top_three = [display[model] for model in TOP_MODELS]
    assert (
        f"The top three models on the board, {top_three[0]}, {top_three[1]}, and "
        f"{top_three[2]}, each predict $0 for the same"
    ) in previous_text
    for model in TOP_MODELS:
        assert predictions["scenario_112"]["snap"][model]["prediction"] == 0
    # What the September 3 note said about the asset test, which this note
    # corrects.
    assert "the net-income and asset tests waived" in previous_text
    pin(
        "PolicyBench no longer scores the other household, in "
        f"{STATE_NAMES[payload['scenarios']['scenario_112']['state']]}, because "
        "PolicyEngine computed its amount with {assumedHours} hours of work a "
        "week, which the prompt does not list.",
        "Under the prompt's rule that unlisted numbers are 0, the time limit for "
        "able-bodied adults without dependents applies, and PolicyEngine gives "
        "$0, the same answer as the top three models in that note.",
        "That note also said these states waive the asset test, but "
        f"{texas} keeps a ${{bbceAssetLimitTx}} asset limit.",
    )

    # The models the prose names by hand, and no sentence left unpinned.
    assert _named_models(text, display) == {
        "gpt-6-astra",
        "claude-opus-5.5",
        "gpt-6-sol",
        "gpt-5.6-sol",
        "claude-fable-5.1",
        zero_tanf_model,
    }
    unpinned = text
    for sentence in pinned:
        unpinned = unpinned.replace(sentence, "", 1)
    assert not unpinned.strip(), unpinned

    # The data links name each household as the prose does, and count the
    # households of each group.
    links = {entry["label"]: entry["href"] for entry in note["data"]}
    household_links = {
        f"{names['scenario_045']} worker": "scenario_045",
        f"{names['scenario_030']} resident": "scenario_030",
        f"{names['scenario_027']} couple": "scenario_027",
        f"Disabled {names['scenario_073']} resident": "scenario_073",
        f"{names['scenario_108']} surviving spouse": "scenario_108",
    }
    assert sorted(household_links.values()) == sorted(households)
    for label, scenario_id in household_links.items():
        assert links[label] == f"/?country=us&scenario={scenario_id}#scenarios"
    assert not any(re.search(r"scenario_\d", label) for label in links)
    number_words = {4: "four", 5: "five"}
    rows_url = "https://github.com/PolicyEngine/policybench/blob/main/"
    assert (
        links[
            f"Every model's answer for the {number_words[len(households)]} "
            "households held back by income"
        ]
        == rows_url + BBCE_ROWS_PATH.relative_to(ROOT).as_posix()
    )
    assert (
        links[
            f"Every model's answer for the {number_words[len(asset_households)]} "
            "households held back by savings"
        ]
        == rows_url + BBCE_ASSET_ROWS_PATH.relative_to(ROOT).as_posix()
    )

    derived = {
        "nModels": len(board),
        "householdCount": len(households),
        "minimumMonthly": _whole_or_cents(minimum),
        "referenceAmount": _whole_or_cents(reference_amount),
        "answers": len(rows),
        "zeroAnswers": len(zero_rows),
        "hits": sum(row["within_1_dollar"] for row in rows),
        "snapGrossLimit": round(100 * snap_gross_limit),
        "txAge": texan["age"],
        "financialAssistance": _whole_or_cents(financial_assistance),
        "wiAge": widow["age"],
        "ctSavings": _whole_or_cents(savings),
        "bbceGrossLimitHigh": high_limit,
        "bbceGrossLimitTx": round(100 * rules["TX"]["gross_income_limit_fpg"]),
        "assetOnlyCount": len(asset_households),
        "assetOnlyAbove0Share": _percent(len(asset_above_zero), len(asset_rows)),
        "fiveAbove0Share": _percent(len(above_zero), len(rows)),
        "assetOnlyBbceMentions": len(asset_mentions),
        "assetOnlyExplanations": len(asset_explained),
        "assetOnlyBbceAssets": sum(row["mentions_assets"] for row in asset_mentions),
        "fiveBbceMentions": len(five_mentions),
        "explanations": len(explained),
        "fiveBbceZeros": len(five_mention_zeros),
        "fiveBbceZeroWithNetLimit": sum(
            row["mentions_net_income_limit"] for row in five_mention_zeros
        ),
        "astraHits": best,
        "opusOn108": _whole_or_cents(opus["scenario_108"]),
        "sol6ZeroCount": sum(value == 0 for value in sol6.values()),
        "sol6BbceMentions": bbce_mentions("gpt-6-sol"),
        "boardHouseholds": board_households,
        "sol6On030": _whole_or_cents(sol6["scenario_030"]),
        "opusOn030": _whole_or_cents(opus["scenario_030"]),
        "zeroTanfMentions": len(zero_tanf),
        "previousHouseholdCount": previous["facts"]["deniedCount"],
        "previousReference": f"{frozen_value:.2f}",
        "previousMonthlyJanSep": f"{jan:.2f}",
        "previousMonthlyOctDec": f"{oct_:.2f}",
        "assumedHours": int(assumed_hours.group(1)),
        "bbceAssetLimitTx": _whole_or_cents(rules["TX"]["asset_limit"]),
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
